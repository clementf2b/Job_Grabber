#!/usr/bin/env python3
"""
JobGrab — Hong Kong multi-board job scraper.
Usage: python main.py <keyword> [--pages N] [--period DAYS] [--sources ...] [--out jobs.json]

Working sources:  linkedin, michaelpage, ctgoodjobs
Blocked sources:  jobsdb / indeed / glassdoor (Cloudflare)
"""
import asyncio
import argparse
import json
import sys
from typing import List

from models import Job
from scrapers.linkedin import LinkedInScraper
from scrapers.michaelpage import MichaelPageScraper
from scrapers.ctgoodjobs import CTgoodjobsScraper

SCRAPERS = {
    "linkedin": LinkedInScraper,
    "michaelpage": MichaelPageScraper,
    "ctgoodjobs": CTgoodjobsScraper,
}


async def run_scraper(name: str, cls, keyword: str, location: str,
                      pages: int, period_days: int) -> List[Job]:
    print(f"[{name}] scraping '{keyword}' in {location}...")
    try:
        scraper = cls(keyword=keyword, location=location,
                      max_pages=pages, period_days=period_days)
        jobs = await scraper.run()
        print(f"[{name}] found {len(jobs)} jobs")
        return jobs
    except Exception as e:
        print(f"[{name}] ERROR: {e}", file=sys.stderr)
        return []


async def main():
    parser = argparse.ArgumentParser(description="JobGrab — multi-board HK job scraper")
    parser.add_argument("keyword", help="Job title / keyword to search")
    parser.add_argument("--location", default="Hong Kong")
    parser.add_argument("--pages", type=int, default=3, help="Pages per source (default: 3)")
    parser.add_argument("--period", type=int, default=7,
                        help="Only include jobs posted within N days (default: 7; 0=all)")
    parser.add_argument("--sources", default="linkedin,michaelpage,ctgoodjobs",
                        help="Comma-separated sources (default: all working)")
    parser.add_argument("--out", default="jobs.json")
    args = parser.parse_args()

    selected = [s.strip().lower() for s in args.sources.split(",")]
    tasks = [
        run_scraper(name, SCRAPERS[name], args.keyword, args.location, args.pages, args.period)
        for name in selected if name in SCRAPERS
    ]

    results = await asyncio.gather(*tasks)
    all_jobs: List[Job] = [job for batch in results for job in batch]

    # Deduplicate by URL (or title+company fallback), preserving order
    unique = list({(j.url or f"{j.title}|{j.company}"): j for j in all_jobs}.values())

    print(f"\nTotal unique jobs: {len(unique)}")
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump([j.to_dict() for j in unique], f, ensure_ascii=False, indent=2)
    print(f"Saved to {args.out}")

    print(f"\n{'Title':<45} {'Company':<30} {'Source':<12} {'Salary'}")
    print("-" * 110)
    for job in unique[:30]:
        print(f"{job.title[:44]:<45} {job.company[:29]:<30} {job.source:<12} {job.salary or '-'}")
    if len(unique) > 30:
        print(f"... and {len(unique) - 30} more (see {args.out})")


if __name__ == "__main__":
    asyncio.run(main())
