"""Michael Page HK job scraper."""
from typing import List
from urllib.parse import urlencode
from bs4 import BeautifulSoup
from playwright.async_api import Page
from .base import BaseScraper
from .utils import el_text, make_absolute
from models import Job


class MichaelPageScraper(BaseScraper):
    name = "MichaelPage"
    domains = ("www.michaelpage.com.hk", "michaelpage.com.hk")
    BASE = "https://www.michaelpage.com.hk/jobs/information-technology"

    async def scrape(self, page: Page) -> List[Job]:
        jobs: List[Job] = []

        for page_num in range(self.max_pages):
            params = {"q": self.keyword}
            if page_num > 0:
                params["page"] = page_num
            url = f"{self.BASE}?{urlencode(params)}"
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            try:
                await page.wait_for_selector("li.views-row", timeout=8000)
            except Exception:
                break

            soup = BeautifulSoup(await page.content(), "lxml")
            rows = soup.select("li.views-row")
            if not rows:
                break

            for row in rows:
                try:
                    title_el = row.select_one(".job-title h3 a")
                    title = el_text(title_el)
                    if not title:
                        continue

                    href    = make_absolute(title_el.get("href", ""), "https://www.michaelpage.com.hk")
                    desc_el = row.select_one(".job_advert__job-summary-text p")

                    jobs.append(Job(
                        title=title,
                        company="(via Michael Page)",
                        location=el_text(row.select_one(".job-location")) or self.location,
                        source=self.name,
                        url=href,
                        salary=el_text(row.select_one(".job-salary")) or None,
                        job_type=el_text(row.select_one(".job-contract-type")) or None,
                        description=el_text(desc_el) or None,
                    ))
                except Exception:
                    continue

        return jobs
