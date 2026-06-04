# BLOCKED — Cloudflare prevents headless scraping. Not registered in main.py.
# Kept for reference only.

import asyncio
import json
from typing import List
from playwright.async_api import Page
from .base import BaseScraper
from models import Job


class JobsDBScraper(BaseScraper):
    name = "JobsDB"
    # JobsDB uses a GraphQL-backed search API
    API = "https://xapi.supercharge-srp.co/job-search/graphql"

    async def scrape(self, page: Page) -> List[Job]:
        jobs: List[Job] = []

        for page_num in range(1, self.max_pages + 1):
            payload = {
                "query": """
                    query getJobSearch($keyword: String, $locationList: [String], $page: Int, $pageSize: Int) {
                        jobs(
                            keyword: $keyword
                            locationList: $locationList
                            page: $page
                            pageSize: $pageSize
                            siteKey: "HK-Main"
                        ) {
                            total
                            jobs {
                                id
                                title
                                company { name }
                                location { label }
                                salary { label }
                                listingDate
                                jobUrl
                                workTypes { label }
                            }
                        }
                    }
                """,
                "variables": {
                    "keyword": self.keyword,
                    "locationList": ["Hong Kong"],
                    "page": page_num,
                    "pageSize": 30,
                },
            }

            result = await page.evaluate(
                """async ([url, body]) => {
                    const r = await fetch(url, {
                        method: "POST",
                        headers: {"Content-Type": "application/json"},
                        body: JSON.stringify(body)
                    });
                    return r.json();
                }""",
                [self.API, payload],
            )

            items = (result.get("data") or {}).get("jobs", {}).get("jobs") or []
            if not items:
                break

            for item in items:
                salary = (item.get("salary") or {}).get("label")
                work_types = item.get("workTypes") or []
                job_type = work_types[0].get("label") if work_types else None
                company = (item.get("company") or {}).get("name", "")
                location = (item.get("location") or {}).get("label", self.location)

                jobs.append(Job(
                    title=item.get("title", ""),
                    company=company,
                    location=location,
                    source=self.name,
                    url=item.get("jobUrl", ""),
                    salary=salary,
                    job_type=job_type,
                    posted_at=item.get("listingDate"),
                ))

        return jobs

    async def run(self):
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            # navigate to jobsdb first so fetch has the right origin
            await page.goto("https://hk.jobsdb.com", wait_until="domcontentloaded", timeout=20000)
            try:
                jobs = await self.scrape(page)
            finally:
                await browser.close()
        return jobs
