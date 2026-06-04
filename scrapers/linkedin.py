"""LinkedIn public job search scraper."""
import asyncio
import json
from typing import List, Optional
from urllib.parse import urlencode
from playwright.async_api import Page
from .base import BaseScraper
from .utils import UA, LINKEDIN_PERIOD, strip_html
from models import Job

# Number of reusable detail pages kept open during description fetching.
# Low value avoids LinkedIn rate-limiting.
DESCRIPTION_CONCURRENCY = 3


class LinkedInScraper(BaseScraper):
    name = "LinkedIn"
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
            await asyncio.sleep(2)

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
        # Creates DESCRIPTION_CONCURRENCY pages once and reuses them across
        # all jobs — avoids spinning up ~96 contexts (one per job).
        browser = page.context.browser
        pool: asyncio.Queue = asyncio.Queue()
        contexts = []
        for _ in range(DESCRIPTION_CONCURRENCY):
            ctx = await browser.new_context(user_agent=UA)
            p = await ctx.new_page()
            contexts.append(ctx)
            await pool.put(p)

        async def fetch_description(job: Job) -> Optional[str]:
            if not job.url or not job.url.startswith("http"):
                return None
            detail = await pool.get()
            try:
                await detail.goto(job.url, wait_until="domcontentloaded", timeout=25000)
                await asyncio.sleep(1.5)
                # Prefer JSON-LD structured data
                ld_el = await detail.query_selector('script[type="application/ld+json"]')
                if ld_el:
                    data = json.loads(await ld_el.inner_text())
                    desc = strip_html(data.get("description", ""))
                    if desc:
                        return desc[:1500]
                # Fallback: visible description element (already plain text)
                dom_el = await detail.query_selector(
                    ".show-more-less-html__markup, .description__text"
                )
                if dom_el:
                    return (await dom_el.inner_text()).strip()[:1500]
            except Exception:
                pass
            finally:
                await pool.put(detail)  # return page to pool
            return None

        print(f"[LinkedIn] fetching descriptions for {len(jobs)} jobs…")
        descriptions = await asyncio.gather(*[fetch_description(j) for j in jobs])
        for job, desc in zip(jobs, descriptions):
            if desc:
                job.description = desc

        # Close the pooled contexts now that all jobs are done
        for ctx in contexts:
            await ctx.close()

        return jobs
