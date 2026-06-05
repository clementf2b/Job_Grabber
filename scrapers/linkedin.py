"""LinkedIn public job search scraper."""
import asyncio
import json
from typing import List, Optional
from urllib.parse import urlencode
from playwright.async_api import Page
from .base import BaseScraper
from .utils import UA, LINKEDIN_PERIOD, strip_html
from models import Job

# Reusable detail pages kept open during description fetching.
# Low value avoids LinkedIn rate-limiting.
DESCRIPTION_CONCURRENCY = 3


class LinkedInScraper(BaseScraper):
    name = "LinkedIn"
    domains = ("linkedin.com", "www.linkedin.com")
    BASE = "https://www.linkedin.com/jobs/search"

    async def scrape(self, page: Page) -> List[Job]:
        jobs: List[Job] = []

        # ── Step 1: collect job cards from search-results pages ──────────
        params: dict = {"keywords": self.keyword, "location": self.location}
        period_filter = LINKEDIN_PERIOD.get(self.period_days)
        if period_filter:
            params["f_TPR"] = period_filter

        for page_num in range(self.max_pages):
            params["start"] = page_num * 25
            url = f"{self.BASE}?{urlencode(params)}"
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            try:
                await page.wait_for_selector(".base-card", timeout=8000)
            except Exception:
                break

            cards = await page.query_selector_all(".base-card")
            if not cards:
                break

            for card in cards:
                try:
                    title_el    = await card.query_selector(".base-search-card__title")
                    company_el  = await card.query_selector(".base-search-card__subtitle")
                    location_el = await card.query_selector(".job-search-card__location")
                    link_el     = await card.query_selector("a.base-card__full-link")
                    time_el     = await card.query_selector("time")

                    title     = (await title_el.inner_text()).strip()   if title_el    else ""
                    company   = (await company_el.inner_text()).strip()  if company_el  else ""
                    location  = (await location_el.inner_text()).strip() if location_el else self.location
                    href      = await link_el.get_attribute("href")      if link_el     else ""
                    posted_at = await time_el.get_attribute("datetime")  if time_el     else None

                    if title and company:
                        jobs.append(Job(
                            title=title, company=company, location=location,
                            source=self.name, url=href or url, posted_at=posted_at,
                        ))
                except Exception:
                    continue

        # ── Step 2: fetch descriptions via a reusable page pool ──────────
        # Reuses pages from the existing browser context — no extra contexts needed.
        pool: asyncio.Queue = asyncio.Queue()
        pool_pages = []
        for _ in range(DESCRIPTION_CONCURRENCY):
            p = await page.context.new_page()
            pool_pages.append(p)
            await pool.put(p)

        async def fetch_description(job: Job) -> None:
            if not job.url or not job.url.startswith("http"):
                return
            detail = await pool.get()
            try:
                await detail.goto(job.url, wait_until="domcontentloaded", timeout=25000)
                try:
                    await detail.wait_for_selector(
                        'script[type="application/ld+json"], .show-more-less-html__markup',
                        timeout=6000,
                    )
                except Exception:
                    pass
                ld_el = await detail.query_selector('script[type="application/ld+json"]')
                if ld_el:
                    data = json.loads(await ld_el.inner_text())
                    desc = strip_html(data.get("description", ""))
                    if desc:
                        job.description = desc[:1500]
                        return
                dom_el = await detail.query_selector(
                    ".show-more-less-html__markup, .description__text"
                )
                if dom_el:
                    job.description = (await dom_el.inner_text()).strip()[:1500]
            except Exception:
                pass
            finally:
                await pool.put(detail)

        print(f"[LinkedIn] fetching descriptions for {len(jobs)} jobs…")
        await asyncio.gather(*[fetch_description(j) for j in jobs])

        for p in pool_pages:
            await p.close()

        return jobs

    async def _parse_detail_page(self, page: Page, url: str) -> Optional[Job]:
        """Parse a LinkedIn job-view page and return a Job, or None on failure."""
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            try:
                await page.wait_for_selector(
                    'script[type="application/ld+json"], h1',
                    timeout=8000,
                )
            except Exception:
                pass

            # Prefer JSON-LD structured data (most complete)
            ld_el = await page.query_selector('script[type="application/ld+json"]')
            if ld_el:
                data = json.loads(await ld_el.inner_text())
                title = data.get("title", "").strip()
                company_raw = data.get("hiringOrganization", {})
                company = (company_raw.get("name", "") if isinstance(company_raw, dict) else "").strip()

                location_raw = data.get("jobLocation", {})
                if isinstance(location_raw, dict):
                    addr = location_raw.get("address", {})
                    location = (addr.get("addressLocality") or addr.get("addressRegion") or self.location).strip()
                else:
                    location = self.location

                salary: Optional[str] = None
                salary_raw = data.get("baseSalary", {})
                if isinstance(salary_raw, dict):
                    val = salary_raw.get("value", {})
                    if isinstance(val, dict):
                        lo, hi, unit = val.get("minValue"), val.get("maxValue"), val.get("unitText", "")
                        salary = (f"{lo}–{hi} {unit}" if lo and hi else f"{lo or hi} {unit}").strip() or None

                description = strip_html(data.get("description", ""))[:1500] or None
                date_posted = data.get("datePosted") or data.get("validThrough")
                job_type = (data.get("employmentType") or "").replace("_", " ").title() or None

                if title and company:
                    return Job(title=title, company=company, location=location,
                               source=self.name, url=url, description=description,
                               salary=salary, job_type=job_type, posted_at=date_posted)

            # Fallback: visible DOM elements
            title_el   = await page.query_selector("h1.top-card-layout__title, h1.jobs-unified-top-card__job-title")
            company_el = await page.query_selector("a.topcard__org-name-link, .jobs-unified-top-card__company-name")
            desc_el    = await page.query_selector(".show-more-less-html__markup, .description__text")
            time_el    = await page.query_selector("time")

            title   = (await title_el.inner_text()).strip()    if title_el   else ""
            company = (await company_el.inner_text()).strip()   if company_el else ""
            desc    = (await desc_el.inner_text()).strip()[:1500] if desc_el else None
            posted  = await time_el.get_attribute("datetime")  if time_el   else None

            if title and company:
                return Job(title=title, company=company, location=self.location,
                           source=self.name, url=url, description=desc, posted_at=posted)
        except Exception as e:
            print(f"[LinkedIn] failed to scrape {url}: {e}")
        return None

    async def scrape_single(self, url: str, page: Page) -> Optional[Job]:
        return await self._parse_detail_page(page, url)
