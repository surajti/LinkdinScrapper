import asyncio
import json
import logging
import random
import re
from collections import OrderedDict
from typing import List, Optional
 
import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
 
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
 
from .database import get_db
from .models import ProcessedJob, DeletedJob
 
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
 
app = FastAPI()
 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
 
# ------------------ MODELS ------------------
 
class SearchRequest(BaseModel):
    role: str
    location: str
    limit: int = 25
    posted_within_minutes: int = 60
 
class JobResult(BaseModel):
    title: str
    company: str
    location: str
    url: str
    posted_time: str
    followers: int = 0
    experience_years: Optional[int] = None
 
 
# ------------------ CONFIG ------------------
 
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
]

def get_random_headers() -> dict:
    user_agent = random.choice(USER_AGENTS)
    return {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.linkedin.com/",
        "Sec-Ch-Ua": '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "cross-site",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }

HEADERS = get_random_headers()

CONCURRENCY = 3
 
# Normalize any user-supplied location string to a canonical expansion key.
# All keys and values must be lowercase — resolve_location() lowercases input before lookup.
LOCATION_ALIASES: dict[str, str] = {
    # India — every realistic variation a user might type
    "india": "india",
    "भारत": "india",          # Hindi
    "in": "india",
    "ind": "india",
    "🇮🇳": "india",
    "indian": "india",
    "hindusthan": "india",
    "hindustan": "india",
 
    # Bengaluru / Bangalore
    "bengaluru": "bengaluru",
    "bangalore": "bengaluru",
    "blr": "bengaluru",
    "bengalore": "bengaluru",  # common misspelling
 
    # Delhi NCR
    "delhi": "delhi",
    "new delhi": "delhi",
    "ncr": "delhi",
    "delhi ncr": "delhi",
    "new delhi, india": "delhi",
 
    # Gurugram
    "gurugram": "gurugram",
    "gurgaon": "gurugram",
    "ggn": "gurugram",
    "gurugram, haryana, india": "gurugram",
 
    # Noida
    "noida": "noida",
    "greater noida": "noida",
    "noida, uttar pradesh, india": "noida",
 
    # Mumbai
    "mumbai": "mumbai",
    "bombay": "mumbai",
    "bom": "mumbai",
 
    # Hyderabad
    "hyderabad": "hyderabad",
    "hyd": "hyderabad",
    "hyderabad, telangana, india": "hyderabad", 
}
 
# Canonical expansion key → list of LinkedIn location strings to search in parallel.
LOCATION_EXPANSION: dict[str, list[str]] = {
    "india": [
        "Gurugram, Haryana, India",
        "Noida, Uttar Pradesh, India",
        "Bengaluru, Karnataka, India",
        "Hyderabad, Telangana, India",
        "Delhi, India",
    ],
    "bengaluru": [
        "Bengaluru, Karnataka, India",
        "Bengaluru Urban, Karnataka, India",
    ],
    "delhi": [
        "Delhi, India",
        "Gurugram, Haryana, India",
        "Noida, Uttar Pradesh, India",
        "Faridabad, Haryana, India",
    ],
    "gurugram": [
        "Gurugram, Haryana, India",
        "Delhi, India",
    ],
    "noida": [
        "Noida, Uttar Pradesh, India",
        "Greater Noida, Uttar Pradesh, India",
        "Delhi, India",
    ]
}
 
 
def resolve_location(raw: str) -> list[str]:
    """
    Map any user-supplied location string → list of LinkedIn search locations.
    Falls back to passing the raw string as-is if no alias/expansion is found.
    """
    key = LOCATION_ALIASES.get(raw.strip().lower())
    if key:
        return LOCATION_EXPANSION.get(key, [raw])
    # No alias hit — try direct expansion key match
    direct = LOCATION_EXPANSION.get(raw.strip().lower())
    if direct:
        return direct
    # Unknown location: pass through as-is (single search)
    return [raw]
 
 
# ------------------ LRU CACHE (bounded) ------------------
 
class _LRUCache(OrderedDict):
    """Simple bounded LRU cache so COMPANY_CACHE never leaks memory."""
    def __init__(self, maxsize: int = 500):
        self._maxsize = maxsize
        super().__init__()
 
    def __setitem__(self, key, value):
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        if len(self) > self._maxsize:
            self.popitem(last=False)
 
COMPANY_CACHE: _LRUCache = _LRUCache(maxsize=500)
 
 
# ------------------ HELPERS ------------------
 
async def fetch_company_followers(client: httpx.AsyncClient, company_url: str) -> int:
    if company_url in COMPANY_CACHE:
        return COMPANY_CACHE[company_url]
 
    try:
        # Add a random delay to prevent aggressive concurrent fetches
        await asyncio.sleep(random.uniform(1.0, 3.0))
        
        r = None
        for attempt in range(3):
            r = await client.get(company_url, headers=get_random_headers(), timeout=15)
            if r.status_code == 429:
                retry_after = r.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    wait = int(retry_after)
                else:
                    wait = 2 ** attempt * 5 + random.uniform(2, 5)
                logger.warning(f"429 on company page {company_url} (attempt {attempt+1}), sleeping {wait}s")
                await asyncio.sleep(wait)
                continue
            break

        if r and r.status_code == 200:
            soup = BeautifulSoup(r.text, "lxml")
            followers_node = soup.find(string=re.compile(r"followers", re.I))
            if followers_node:
                # Extract only the number immediately before "followers"
                match = re.search(r"([\d,]+)\s+followers", followers_node.strip(), re.I)
                if match:
                    followers = int(match.group(1).replace(",", ""))
                    COMPANY_CACHE[company_url] = followers
                    return followers
    except Exception as e:
        logger.error(f"Error fetching company followers for {company_url}: {e}")
 
    COMPANY_CACHE[company_url] = 0
    return 0
 
 
# ------------------ SCRAPER ------------------
 
async def _get_urls_for_location(
    client: httpx.AsyncClient,
    role: str,
    location: str,
    limit: int,
    f_tpr: str,
) -> list[str]:
    """Fetch job URLs for a single location string. Returns up to `limit` URLs."""
    api_url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    seen: set[str] = set()
    results: list[str] = []
    start = 0
 
    while len(results) < limit:
        params = {
            "keywords": role,
            "location": location,
            "start": start,
            "f_TPR": f_tpr,
        }
 
        try:
            # Random delay before fetching page to prevent rapid bursts
            await asyncio.sleep(random.uniform(1.0, 3.0))
            r = await client.get(api_url, params=params, headers=get_random_headers(), timeout=15)
        except Exception as e:
            logger.error(f"Request error for location={location}: {e}")
            break
 
        if r.status_code == 429:
            retry_after = r.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                wait = int(retry_after)
            else:
                wait = 15 + random.uniform(2, 5)
            logger.warning(f"429 on URL listing for {location}, backing off {wait}s")
            await asyncio.sleep(wait)
            continue
 
        if r.status_code != 200:
            logger.warning(f"Non-200 ({r.status_code}) for location={location}")
            break
 
        soup = BeautifulSoup(r.text, "lxml")
        anchors = soup.find_all("a", href=True)
 
        new_this_page = 0
        for a in anchors:
            link: str = a["href"]
            if "/jobs/view/" not in link:
                continue
            if link.startswith("/"):
                link = "https://www.linkedin.com" + link
            # Strip query params so the same job from different searches deduplicates
            link = link.split("?")[0]
            if link not in seen:
                seen.add(link)
                results.append(link)
                new_this_page += 1
 
        logger.info(f"[{location}] page start={start} → +{new_this_page} links ({len(results)} total)")
 
        if new_this_page == 0:          # no new job links on this page → stop
            break
 
        start += 25
        await asyncio.sleep(random.uniform(1.5, 3.5))
 
    return results[:limit]
 
 
async def get_job_urls(
    client: httpx.AsyncClient,
    role: str,
    location: str,
    limit: int,
    minutes: int,
) -> list[str]:
    """
    Resolve `location` to one or more LinkedIn search locations, fan out in
    parallel, then merge + deduplicate results.
    """
    if minutes < 60:
        logger.warning(f"posted_within_minutes={minutes} below minimum 60, clamping.")
        minutes = 60
    f_tpr = f"r{minutes * 60}"
 
    # Expand broad regions / aliases (e.g. "India", "Gurgaon", "BLR") into city searches
    expanded: list[str] = resolve_location(location)
 
    # How many URLs to ask from each sub-location so we get at least `limit` total
    per_location_limit = max(limit, limit // len(expanded) + 10)
 
    # Limit to 2 concurrent city searches to prevent hitting rate limit immediately
    loc_sem = asyncio.Semaphore(2)
    async def safe_get_urls(loc: str):
        async with loc_sem:
            return await _get_urls_for_location(client, role, loc, per_location_limit, f_tpr)
 
    tasks = [safe_get_urls(loc) for loc in expanded]
    all_results: list[list[str]] = await asyncio.gather(*tasks)
 
    # Interleave results so every city gets representation, then deduplicate
    seen: set[str] = set()
    merged: list[str] = []
    for batch in zip(*[r for r in all_results]):   # round-robin across cities
        for url in batch:
            if url not in seen:
                seen.add(url)
                merged.append(url)
            if len(merged) >= limit * 2:            # fetch a buffer so filters don't starve
                break
 
    # Append any remaining from cities that returned more results
    for city_results in all_results:
        for url in city_results:
            if url not in seen:
                seen.add(url)
                merged.append(url)
 
    logger.info(f"Total URLs after fan-out merge: {len(merged)} across {len(expanded)} location(s)")
    return merged
 
 
async def fetch_job(client: httpx.AsyncClient, url: str) -> Optional[JobResult]:
    try:
        # Add a random delay (jitter) BEFORE the first request to avoid concurrent burst
        await asyncio.sleep(random.uniform(0.5, 2.5))
        
        # Retry on 429 with exponential backoff
        r = None
        for attempt in range(3):
            r = await client.get(url, headers=get_random_headers(), timeout=15)
            if r.status_code == 429:
                retry_after = r.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    wait = int(retry_after)
                else:
                    wait = 2 ** attempt * 5 + random.uniform(2, 5)   # 7-10s, 9-14s, 13-21s
                logger.warning(f"429 on {url} (attempt {attempt+1}), sleeping {wait}s")
                await asyncio.sleep(wait)
                continue
            break
 
        if r is None or r.status_code != 200:
            return None
 
        soup = BeautifulSoup(r.text, "lxml")
 
        title_tag   = soup.find("h1")
        company_tag = soup.find(class_=re.compile(r"company|org-name", re.I))
        location_tag = soup.find(class_=re.compile(r"location|bullet", re.I))
        posted_tag  = soup.find(class_=re.compile(r"posted|date", re.I))
 
        company_url = None
        description = ""
        for s in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(s.string or "")
                if "description" in data:
                    description += " " + data["description"]
                if "hiringOrganization" in data and "sameAs" in data["hiringOrganization"]:
                    company_url = data["hiringOrganization"]["sameAs"]
            except (json.JSONDecodeError, KeyError, TypeError):
                pass
 
        if not description:
            description = soup.get_text()
 
        title_text = title_tag.get_text(strip=True) if title_tag else "Unknown"
        if re.search(r'\bintern(ship)?\b', title_text, re.I):
            return None
 
        desc_lower = description.lower()
        matches = re.findall(
            r'\b(\d+)\s*(?:to|-)?\s*(\d+)?\s*(?:\+|plus)?\s*(?:years|yrs)\b',
            desc_lower,
        )
        exp_years: Optional[int] = None
        if matches:
            mins = [int(m[0]) for m in matches if m[0].isdigit()]
            if mins:
                exp_years = min(mins)
 
        if exp_years is not None and (exp_years < 2 or exp_years > 6):
            return None
 
        followers = 0
        if company_url:
            followers = await fetch_company_followers(client, company_url)
 
        return JobResult(
            title=title_text,
            company=company_tag.get_text(strip=True) if company_tag else "Unknown",
            location=location_tag.get_text(strip=True) if location_tag else "Unknown",
            url=url,
            posted_time=posted_tag.get_text(strip=True) if posted_tag else "Recently posted",
            followers=followers,
            experience_years=exp_years,
        )
 
    except Exception as e:
        logger.error(f"Job parse error for {url}: {e}")
        return None
 
 
# ------------------ SEARCH ------------------
 
@app.post("/api/search", response_model=List[JobResult])
async def search(req: SearchRequest, db: AsyncSession = Depends(get_db)):
 
    async with httpx.AsyncClient(
        headers=HEADERS,
        limits=httpx.Limits(max_connections=20),
        timeout=httpx.Timeout(20.0),
    ) as client:
 
        urls = await get_job_urls(
            client,
            req.role,
            req.location,
            req.limit,
            req.posted_within_minutes,
        )
 
        if not urls:
            return []
 
        # Filter already-seen URLs — run DB queries sequentially since SQLAlchemy sessions do not support concurrent operations
        done_q = await db.execute(select(ProcessedJob.linkedin_url).where(ProcessedJob.linkedin_url.in_(urls)))
        del_q = await db.execute(select(DeletedJob.linkedin_url).where(DeletedJob.linkedin_url.in_(urls)))
        skip_urls = set(done_q.scalars().all()) | set(del_q.scalars().all())
        urls_to_fetch = [u for u in urls if u not in skip_urls]
 
        if not urls_to_fetch:
            return []
 
        jobs = []
        chunk_size = CONCURRENCY
        for i in range(0, len(urls_to_fetch), chunk_size):
            if len(jobs) >= req.limit:
                logger.info(f"Collected enough jobs ({len(jobs)} >= {req.limit}). Stopping early.")
                break

            chunk = urls_to_fetch[i : i + chunk_size]
            logger.info(f"Fetching chunk {i // chunk_size + 1}: {len(chunk)} urls")
            
            chunk_results = await asyncio.gather(*[fetch_job(client, u) for u in chunk])
            
            for r in chunk_results:
                if r is not None:
                    jobs.append(r)
            
            if i + chunk_size < len(urls_to_fetch) and len(jobs) < req.limit:
                sleep_time = random.uniform(1.0, 2.5)
                logger.info(f"Sleeping {sleep_time:.2f}s before next chunk...")
                await asyncio.sleep(sleep_time)

        jobs.sort(key=lambda x: x.followers, reverse=True)

        logger.info(f"Returning {len(jobs)} jobs for role='{req.role}' location='{req.location}'")
        return jobs[:req.limit]
 
 
# ------------------ DONE TRACK ------------------
 
@app.post("/api/done")
async def mark_done(job: JobResult, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        select(ProcessedJob).where(ProcessedJob.linkedin_url == job.url)
    )
    if existing.scalar():
        return {"status": "already saved"}
 
    db.add(ProcessedJob(
        linkedin_url=job.url,
        job_title=job.title,
        company=job.company,
        location=job.location,
    ))
    await db.commit()
    return {"status": "saved"}
 
 
@app.post("/api/delete")
async def delete_job(job: JobResult, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        select(DeletedJob).where(DeletedJob.linkedin_url == job.url)
    )
    if existing.scalar():
        return {"status": "already deleted"}
 
    db.add(DeletedJob(
        linkedin_url=job.url,
        job_title=job.title,
        company=job.company,
        location=job.location,
    ))
    await db.commit()
    return {"status": "deleted"}
 
 
@app.get("/api/done", response_model=List[JobResult])
async def get_done_jobs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ProcessedJob).order_by(ProcessedJob.processed_at.desc())
    )
    jobs = result.scalars().all()
    return [
        JobResult(
            title=job.job_title or "Unknown",
            company=job.company or "Unknown",
            location=job.location or "Unknown",
            url=job.linkedin_url,
            posted_time=(
                f"Done at {job.processed_at.strftime('%Y-%m-%d %H:%M')}"
                if job.processed_at else "Recently"
            ),
        )
        for job in jobs
    ]
 
 
# ------------------ HEALTH ------------------
 
@app.get("/api/health")
async def health():
    return {"status": "ok"}