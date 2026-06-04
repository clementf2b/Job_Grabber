# BLOCKED — Cloudflare prevents headless scraping. Not registered in main.py.
# Kept for reference only.

import asyncio
import re
from typing import List
from urllib.parse import urlencode
from bs4 import BeautifulSoup
from playwright.async_api import Page
from .base import BaseScraper
from models import Job


class GlassdoorScraper(BaseScraper):
    name = "Glassdoor"
    BASE = "https://www.glassdoor.com/Job/hong-kong-{keyword}-jobs-SRCH_IL.0,9_IM1007_KO10,{end}.htm"

    async def scrape(self, page: Page) -> List[Job]:
        jobs: List[Job] = []
        keyword_slug = self.keyword.lower().replace(" ", "-")
        end = 10 + len(keyword_slug)
        url = self.BASE.format(keyword=keyword_slug, end=end)

        for page_num in range(1, self.max_pages + 1):
            paginated = url if page_num == 1 else f"{url}?p={page_num}"
            await page.goto(paginated, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)

            # close sign-in modal
            try:
                await page.click('[alt="Close"], [data-test="modal-close"], button[class*="CloseButton"]', timeout=3000)
            except Exception:
                pass

            html = await page.content()
            soup = BeautifulSoup(html, "lxml")

            cards = soup.select("li[data-test='jobListing']")
            if not cards:
                cards = soup.select("article.JobCard_jobCardContent__o_ZeK")
            if not cards:
                break

            for card in cards:
                try:
                    title_el = card.select_one("[data-test='job-title'], .JobCard_jobTitle__GLyJ1")
                    company_el = card.select_one("[data-test='employer-name'], .EmployerProfile_compactEmployerName__9MGcV")
                    location_el = card.select_one("[data-test='emp-location'], .JobCard_location__N_iYE")
                    salary_el = card.select_one("[data-test='detailSalary'], .JobCard_salaryEstimate__arV5J")
                    link_el = card.select_one("a[data-test='job-title'], a.JobCard_trackingLink__zUSOo")

                    title = title_el.get_text(strip=True) if title_el else ""
                    company = company_el.get_text(strip=True) if company_el else ""
                    location = location_el.get_text(strip=True) if location_el else self.location
                    salary = salary_el.get_text(strip=True) if salary_el else None
                    href = link_el.get("href", "") if link_el else ""
                    if href and not href.startswith("http"):
                        href = f"https://www.glassdoor.com{href}"

                    if title and company:
                        jobs.append(Job(
                            title=title,
                            company=company,
                            location=location,
                            source=self.name,
                            url=href or paginated,
                            salary=salary,
                        ))
                except Exception:
                    continue

        return jobs
