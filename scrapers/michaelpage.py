"""Michael Page HK job scraper."""
import asyncio
from typing import List
from urllib.parse import urlencode
from bs4 import BeautifulSoup, Tag
from playwright.async_api import Page
from .base import BaseScraper
from .utils import strip_html
from models import Job


def _el_text(el: Tag | None) -> str:
    """Strip font-awesome <i> icons then return plain text of a BS4 element."""
    if not el:
        return ""
    for icon in el.find_all("i"):
        icon.decompose()
    return el.get_text(strip=True)


class MichaelPageScraper(BaseScraper):
    name = "MichaelPage"
    BASE = "https://www.michaelpage.com.hk/jobs/information-technology"

    async def scrape(self, page: Page) -> List[Job]:
        jobs: List[Job] = []

        for page_num in range(self.max_pages):
            params = {"q": self.keyword}
            if page_num > 0:
                params["page"] = page_num
            url = f"{self.BASE}?{urlencode(params)}"
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(1)

            soup = BeautifulSoup(await page.content(), "lxml")
            rows = soup.select("li.views-row")
            if not rows:
                break

            for row in rows:
                try:
                    title_el = row.select_one(".job-title h3 a")
                    title = title_el.get_text(strip=True) if title_el else ""
                    if not title:
                        continue

                    href = title_el.get("href", "") if title_el else ""
                    if href and not href.startswith("http"):
                        href = f"https://www.michaelpage.com.hk{href}"

                    desc_el = row.select_one(".job_advert__job-summary-text p")

                    jobs.append(Job(
                        title=title,
                        company="(via Michael Page)",
                        location=_el_text(row.select_one(".job-location")) or self.location,
                        source=self.name,
                        url=href,
                        salary=_el_text(row.select_one(".job-salary")) or None,
                        job_type=_el_text(row.select_one(".job-contract-type")) or None,
                        description=strip_html(desc_el.get_text(strip=True)) if desc_el else None,
                    ))
                except Exception:
                    continue

        return jobs
