import asyncio
import logging
from linkedin_scraper.models.scrapper import LinkedinJobScrapper

logging.basicConfig(level=logging.INFO)

async def test_scraper():
    scraper = LinkedinJobScrapper(role="Software Engineer", location="India", duration_minutes=2)
    await scraper.run()

if __name__ == "__main__":
    asyncio.run(test_scraper())
