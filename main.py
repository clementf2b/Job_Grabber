#!/usr/bin/env python3
"""
JobGrab — Hong Kong multi-board job scraper.
Usage: python main.py <keyword> [keyword2 ...] [--pages N] [--period DAYS] [--sources ...] [--out jobs.json]
       Default: 40 pages, no time filter (captures reposted jobs)

Examples:
  python main.py "software engineer"
  python main.py "software engineer" "quant developer" "quantitative analyst"

Working sources:  linkedin, michaelpage, ctgoodjobs
Blocked sources:  jobsdb / indeed / glassdoor (Cloudflare)
"""
import asyncio
import argparse
import sys
from typing import List
from urllib.parse import urlparse

from models import Job
from scrapers import SCRAPERS, DOMAIN_SCRAPERS
from db import init_db, upsert_jobs, count_jobs


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
    parser.add_argument("keywords", nargs="+", help="One or more job title / keywords to search")
    parser.add_argument("--location", default="Hong Kong")
    parser.add_argument("--pages", type=int, default=40,
                        help="Pages per source per keyword (default: 40, LinkedIn max is 40)")
    parser.add_argument("--period", type=int, default=0,
                        help="Only include jobs posted within N days (default: 0 = no filter, captures reposts)")
    parser.add_argument("--sources", default="linkedin,michaelpage,ctgoodjobs",
                        help="Comma-separated sources (default: all working)")
    parser.add_argument("--out", default="jobs.json")
    parser.add_argument("--urls", default="",
                        help="Comma-separated direct job-page URLs to scrape individually")
    args = parser.parse_args()

    selected = [s.strip().lower() for s in args.sources.split(",")]
    tasks = [
        run_scraper(name, SCRAPERS[name], kw, args.location, args.pages, args.period)
        for kw in args.keywords
        for name in selected if name in SCRAPERS
    ]

    results = await asyncio.gather(*tasks)
    all_jobs: List[Job] = [job for batch in results for job in batch]

    # Scrape individually-supplied URLs, dispatching by hostname.
    extra_urls = [u.strip() for u in args.urls.split(",") if u.strip()]
    if extra_urls:
        print(f"\nScraping {len(extra_urls)} individual URL(s)…")
        for u in extra_urls:
            host = urlparse(u).netloc
            cls = DOMAIN_SCRAPERS.get(host)
            if not cls:
                print(f"  ! no scraper registered for {host} — skipping {u}")
                continue
            scraper = cls(keyword=args.keywords[0], location=args.location)
            try:
                job = await scraper.run_single(u)
            except NotImplementedError:
                print(f"  ! {cls.name} scraper does not support single-URL scraping")
                continue
            if job:
                all_jobs.append(job)
                print(f"  + {job.title} @ {job.company}")
            else:
                print(f"  ! could not extract job from {u}")

    # Deduplicate by URL (or title+company fallback), preserving order.
    unique = list({(j.url or f"{j.title}|{j.company}"): j for j in all_jobs}.values())

    print(f"\nTotal unique jobs: {len(unique)}")
    init_db()
    upsert_jobs(unique)
    print(f"Saved to jobs.db (total in DB: {count_jobs()})")

    print(f"\n{'Title':<45} {'Company':<30} {'Source':<12} {'Salary'}")
    print("-" * 110)
    for job in unique[:30]:
        print(f"{job.title[:44]:<45} {job.company[:29]:<30} {job.source:<12} {job.salary or '-'}")
    if len(unique) > 30:
        print(f"... and {len(unique) - 30} more (see {args.out})")


if __name__ == "__main__":
    asyncio.run(main())
