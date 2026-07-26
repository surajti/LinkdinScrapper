import logging
import pytest
from linkedin_scraper.models.scrapper import LinkedinJobScrapper

logging.basicConfig(level=logging.INFO)

@pytest.mark.asyncio
async def test_scraper():
    scraper = LinkedinJobScrapper(
        role="Software Engineer",
        location="India",
        duration_minutes=2,
    )
    await scraper.run()
