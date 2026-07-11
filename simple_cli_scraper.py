import argparse
import asyncio
from linkedin_scraper.scrapers.job_search import JobSearchScraper
from linkedin_scraper.scrapers.job import JobScraper
from linkedin_scraper.core.browser import BrowserManager
import logging
import os

# Reduce logging noise
logging.getLogger("linkedin_scraper.core.browser").setLevel(logging.WARNING)

async def main():
    parser = argparse.ArgumentParser(description="Simple CLI LinkedIn Job Scraper")
    parser.add_argument("--keywords", "-k", type=str, required=True, help="Job keywords to search for (e.g. 'Software Engineer')")
    parser.add_argument("--location", "-l", type=str, default="", help="Job location (e.g. 'New York')")
    parser.add_argument("--limit", "-n", type=int, default=5, help="Number of jobs to scrape")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    
    args = parser.parse_args()
    
    print(f"\n🚀 Starting scraper for '{args.keywords}' in '{args.location}'")
    print(f"📊 Target limit: {args.limit} jobs\n")
    
    session_file = "linkedin_session.json"
    
    async with BrowserManager(headless=args.headless) as browser:
        if os.path.exists(session_file):
            try:
                await browser.load_session(session_file)
                print("✓ Using saved LinkedIn session")
            except Exception as e:
                print(f"⚠ Could not load session: {e}. Searching as guest.")
        else:
            print("⚠ No session found. Searching as guest.")
            
        search_scraper = JobSearchScraper(browser.page)
        
        print(f"🔍 Searching for job URLs...")
        job_urls = await search_scraper.search(
            keywords=args.keywords,
            location=args.location,
            limit=args.limit
        )
        
        if not job_urls:
            print("\n❌ No jobs found.")
            return
            
        print(f"✓ Found {len(job_urls)} jobs. Scraping details...\n")
        
        job_scraper = JobScraper(browser.page)
        
        for idx, url in enumerate(job_urls, 1):
            try:
                job = await job_scraper.scrape(url)
                
            
                print(f"Job {idx} of {len(job_urls)}")
                print(f"Title:      {job.job_title}")
                print(f"Company:    {job.company}")
                print(f"Location:   {job.location}")
                if job.posted_date:
                    print(f"Posted:     {job.posted_date}")
                if job.applicant_count:
                    print(f"Applicants: {job.applicant_count}")
                print(f"URL:        {url}")
                print(f"Description snippet:")
                desc = job.job_description or "N/A"
                print(f"  {desc[:150].replace(chr(10), ' ')}...")
                print("="*60 + "\n")
            except Exception as e:
                print(f"❌ Failed to scrape {url}: {e}\n")

if __name__ == "__main__":
    asyncio.run(main())
