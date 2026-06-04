# BLOCKED — Cloudflare prevents headless scraping. Not registered in main.py.
# Kept for reference only.

import asyncio
from typing import List
from urllib.parse import urlencode, quote_plus
from bs4 import BeautifulSoup
from playwright.async_api import Page
from .base import BaseScraper
from models import Job


class IndeedScraper(BaseScraper):
    name = "Indeed"
    BASE = "https://hk.indeed.com/jobs"

    async def scrape(self, page: Page) -> List[Job]:
        jobs: List[Job] = []

        for page_num in range(self.max_pages):
            params = {
                "q": self.keyword,
                "l": self.location,
                "start": page_num * 10,
            }
            url = f"{self.BASE}?{urlencode(params)}"
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)

            html = await page.content()
            soup = BeautifulSoup(html, "lxml")

            cards = soup.select("div.job_seen_beacon")
            if not cards:
                # fallback selector
                cards = soup.select("td.resultContent")
            if not cards:
                break

            for card in cards:
                try:
                    title_el = card.select_one("h2.jobTitle span[title], h2.jobTitle a span")
                    company_el = card.select_one("[data-testid='company-name'], .companyName")
                    location_el = card.select_one("[data-testid='text-location'], .companyLocation")
                    salary_el = card.select_one("[data-testid='attribute_snippet_testid'], .salary-snippet-container")
                    link_el = card.select_one("h2.jobTitle a")

                    title = title_el.get_text(strip=True) if title_el else ""
                    company = company_el.get_text(strip=True) if company_el else ""
                    location = location_el.get_text(strip=True) if location_el else self.location
                    salary = salary_el.get_text(strip=True) if salary_el else None
                    href = link_el.get("href", "") if link_el else ""
                    if href and not href.startswith("http"):
                        href = f"https://hk.indeed.com{href}"

                    if title and company:
                        jobs.append(Job(
                            title=title,
                            company=company,
                            location=location,
                            source=self.name,
                            url=href or url,
                            salary=salary,
                        ))
                except Exception:
                    continue

        return jobs
