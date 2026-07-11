import asyncio
import logging
import re
import time
from datetime import datetime
from typing import List, Optional

import requests
from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from backend.models import ProcessedJob
from backend.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


class LinkedinJobScrapper:
    """
    Scraper service that uses LinkedIn's Guest API + plain HTTP requests (no browser).
    Filters for jobs requiring >3 years of experience and saves results to the DB.
    """

    # Common headers that mimic a real browser request
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Referer": "https://www.linkedin.com/jobs/search/",
    }

    def __init__(self, role: str, location: str, duration_minutes: int):
        self.role = role
        self.location = location
        self.duration_seconds = duration_minutes * 60
        self.start_time: Optional[float] = None
        self._session = requests.Session()
        self._session.headers.update(self.HEADERS)

    # ------------------------------------------------------------------
    # Step 1 – collect job URLs via the LinkedIn Guest API
    # ------------------------------------------------------------------
    async def _get_job_urls_api(self, limit: int = 50) -> List[str]:
        """Fetch job listing URLs using LinkedIn's public Guest API (no login needed)."""
        api_url = (
            "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
        )
        job_urls: List[str] = []
        start = 0

        while len(job_urls) < limit:
            params = {
                "keywords": self.role,
                "location": self.location,
                "start": start,
            }
            try:
                resp = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda p=params: self._session.get(api_url, params=p, timeout=15),
                )
                if resp.status_code != 200:
                    logger.error(
                        "Guest API returned HTTP %s – stopping pagination.",
                        resp.status_code,
                    )
                    break

                # LinkedIn returns an HTML fragment; extract job-view hrefs
                found = re.findall(
                    r'href="(https://[a-z]{2,3}\.linkedin\.com/jobs/view/[^"?]+)',
                    resp.text,
                )
                if not found:
                    break

                for u in found:
                    if u not in job_urls:
                        job_urls.append(u)

                start += 25
                if len(found) < 10:
                    break  # probably the last page

                await asyncio.sleep(1)  # be polite

            except Exception:
                logger.exception("Error fetching job URLs from Guest API")
                break

        logger.info("Collected %d job URLs from Guest API", len(job_urls))
        return job_urls[:limit]

    # ------------------------------------------------------------------
    # Step 2 – fetch individual job detail via plain HTTP (no browser)
    # ------------------------------------------------------------------
    async def _fetch_job_detail(self, url: str):
        """
        Fetch a single LinkedIn job page and return (title, company, description).
        Returns None for each field that cannot be extracted.
        """
        try:
            resp = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._session.get(url, timeout=15),
            )
            if resp.status_code != 200:
                logger.warning("HTTP %s for %s", resp.status_code, url)
                return None, None, None

            soup = BeautifulSoup(resp.text, "lxml")

            # --- title ---
            title_tag = (
                soup.find("h1", class_=re.compile(r"top-card-layout__title|job-title", re.I))
                or soup.find("h1")
            )
            title = title_tag.get_text(strip=True) if title_tag else "Unknown Title"

            # --- company ---
            company_tag = soup.find(
                class_=re.compile(
                    r"topcard__org-name|top-card-layout__second-subline|"
                    r"job-details-jobs-unified-top-card__company-name",
                    re.I,
                )
            )
            if not company_tag:
                company_tag = soup.find("a", {"data-tracking-control-name": re.compile(r"company", re.I)})
            company = company_tag.get_text(strip=True) if company_tag else "Unknown Company"

            # --- description ---
            desc_tag = (
                soup.find(class_=re.compile(r"description__text|jobs-description|show-more-less-html", re.I))
                or soup.find(id=re.compile(r"job-details", re.I))
            )
            description = desc_tag.get_text(separator=" ", strip=True) if desc_tag else ""

            return title, company, description

        except Exception:
            logger.exception("Error fetching job detail for %s", url)
            return None, None, None

    # ------------------------------------------------------------------
    # Experience filter
    # ------------------------------------------------------------------
    def _has_more_than_3_years_experience(self, description: str) -> bool:
        """
        Returns True if the description signals >= 3 years of experience required.
        Accepts "3+ years", "4 years", "5 yrs", "10+ years" etc.
        Rejects "0-3 years" / "1-3 years" patterns (entry/mid-level).
        """
        if not description:
            return False

        desc_lower = description.lower()
        pattern = r"\b(?:[3-9]|\d{2,})\+?\s*(?:years?|yrs?)(?:\s*of)?\s*(?:experience)?\b"

        if re.search(pattern, desc_lower):
            negative_pattern = r"\b(?:0|1|2)\s*-\s*3\s*(?:years?|yrs?)\b"
            if not re.search(negative_pattern, desc_lower):
                return True

        return False

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------
    async def _is_job_processed(self, session: AsyncSession, linkedin_url: str) -> bool:
        result = await session.execute(
            select(ProcessedJob).where(ProcessedJob.linkedin_url == linkedin_url)
        )
        return result.scalar_one_or_none() is not None

    async def _save_job(
        self,
        session: AsyncSession,
        url: str,
        title: str,
        company: str,
        location: str,
        exp_text: str,
    ):
        new_job = ProcessedJob(
            linkedin_url=url,
            job_title=title,
            company=company,
            location=location,
            experience_text=exp_text,
        )
        session.add(new_job)
        await session.commit()

    # ------------------------------------------------------------------
    # Main entry-point
    # ------------------------------------------------------------------
    async def run(self):
        """Execute the scraper: collect URLs → fetch details → filter → save."""
        self.start_time = time.time()
        logger.info(
            "Starting scraper — role='%s', location='%s', duration=%d min",
            self.role,
            self.location,
            self.duration_seconds // 60,
        )

        job_urls = await self._get_job_urls_api(limit=100)
        if not job_urls:
            logger.warning("No jobs found via Guest API. Scraper stopping.")
            return

        async with AsyncSessionLocal() as db_session:
            for url in job_urls:
                if time.time() - self.start_time > self.duration_seconds:
                    logger.info("Duration limit reached. Stopping scraper.")
                    break

                # Skip already-processed URLs
                if await self._is_job_processed(db_session, url):
                    logger.debug("Already processed, skipping: %s", url)
                    continue

                title, company, description = await self._fetch_job_detail(url)
                if title is None:
                    # Could not fetch; store as processed so we don't retry endlessly
                    await self._save_job(
                        db_session, url, "Fetch Error", "Unknown", self.location, "Failed fetch"
                    )
                    continue

                if self._has_more_than_3_years_experience(description):
                    logger.info("✅ Match — %s @ %s", title, company)
                    await self._save_job(
                        db_session, url, title, company, self.location, "Passed >3 years filter"
                    )
                else:
                    logger.debug("❌ No match — %s @ %s", title, company)
                    await self._save_job(
                        db_session, url, title, company, self.location, "Failed filter"
                    )

                await asyncio.sleep(1.5)  # polite crawl delay

        logger.info("Scraping run completed.")
