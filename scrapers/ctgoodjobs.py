import asyncio
from typing import List
from urllib.parse import urlencode
from bs4 import BeautifulSoup
from playwright.async_api import Page
from .base import BaseScraper
from models import Job


class CTgoodjobsScraper(BaseScraper):
    name = "CTgoodjobs"
    BASE = "https://jobs.ctgoodjobs.hk/jobs"

    async def scrape(self, page: Page) -> List[Job]:
        jobs: List[Job] = []

        for page_num in range(1, self.max_pages + 1):
            params = {"q": self.keyword, "page": page_num}
            url = f"{self.BASE}?{urlencode(params)}"
            await page.goto(url, wait_until="networkidle", timeout=40000)
            await asyncio.sleep(2)

            html = await page.content()
            soup = BeautifulSoup(html, "lxml")

            cards = soup.select("[class*=job-card]")
            if not cards:
                break

            for card in cards:
                try:
                    title_el = card.select_one("a.jc-position h2, .jc-position h2, .jc-title h2")
                    link_el = card.select_one("a.jc-position, .jc-title a")
                    company_el = card.select_one("a.jc-company, .jc-company")
                    highlight_els = card.select(".jc-highlight li")

                    title = title_el.get_text(strip=True) if title_el else ""
                    company = company_el.get_text(strip=True) if company_el else ""
                    href = link_el.get("href", "") if link_el else ""
                    if href and not href.startswith("http"):
                        href = f"https://jobs.ctgoodjobs.hk{href}"

                    # location: first .jc-info text, stripping SVG
                    location = self.location
                    for loc_el in card.select(".jc-info"):
                        for svg in loc_el.find_all("svg"):
                            svg.decompose()
                        for icon in loc_el.find_all("i"):
                            icon.decompose()
                        loc_text = loc_el.get_text(strip=True)
                        if loc_text and not any(c.isdigit() for c in loc_text[:2]):
                            location = loc_text
                            break

                    description = " ".join(
                        el.get_text(strip=True) for el in highlight_els
                    ) if highlight_els else None

                    if title and company:
                        jobs.append(Job(
                            title=title,
                            company=company,
                            location=location,
                            source=self.name,
                            url=href,
                            description=description,
                        ))
                except Exception:
                    continue

        return jobs
