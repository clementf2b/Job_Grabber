"""CTgoodjobs HK job scraper."""
from typing import List
from urllib.parse import urlencode
from bs4 import BeautifulSoup
from playwright.async_api import Page
from .base import BaseScraper
from .utils import el_text, make_absolute
from models import Job


class CTgoodjobsScraper(BaseScraper):
    name = "CTgoodjobs"
    domains = ("jobs.ctgoodjobs.hk",)
    BASE = "https://jobs.ctgoodjobs.hk/jobs"

    async def scrape(self, page: Page) -> List[Job]:
        jobs: List[Job] = []

        for page_num in range(1, self.max_pages + 1):
            params = {"q": self.keyword, "page": page_num}
            url = f"{self.BASE}?{urlencode(params)}"
            await page.goto(url, wait_until="domcontentloaded", timeout=40000)
            try:
                await page.wait_for_selector("[class*=job-card]", timeout=8000)
            except Exception:
                break

            soup = BeautifulSoup(await page.content(), "lxml")
            cards = soup.select("[class*=job-card]")
            if not cards:
                break

            for card in cards:
                try:
                    title_el      = card.select_one("a.jc-position h2, .jc-position h2, .jc-title h2")
                    link_el       = card.select_one("a.jc-position, .jc-title a")
                    company_el    = card.select_one("a.jc-company, .jc-company")
                    highlight_els = card.select(".jc-highlight li")

                    title   = el_text(title_el)
                    company = el_text(company_el)
                    href    = make_absolute(link_el.get("href", "") if link_el else "", "https://jobs.ctgoodjobs.hk")

                    loc_el   = card.select_one(".jc-info")
                    location = self.location
                    if loc_el:
                        loc_text = " ".join(
                            t for t in loc_el.stripped_strings
                            if not any(c.isdigit() for c in t[:2])
                        )
                        location = loc_text or self.location

                    description = " ".join(el_text(el) for el in highlight_els) or None

                    if title and company:
                        jobs.append(Job(
                            title=title, company=company, location=location,
                            source=self.name, url=href, description=description,
                        ))
                except Exception:
                    continue

        return jobs
