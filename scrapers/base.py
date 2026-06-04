"""Base scraper — all board scrapers inherit from this."""
from abc import ABC, abstractmethod
from typing import List
from playwright.async_api import async_playwright, Page
from models import Job
from scrapers.utils import UA


class BaseScraper(ABC):
    name: str = ""
    headless: bool = True  # subclasses can override (e.g. headless=False for Cloudflare bypass)

    def __init__(self, keyword: str, location: str = "Hong Kong",
                 max_pages: int = 3, period_days: int = 7):
        self.keyword = keyword
        self.location = location
        self.max_pages = max_pages
        self.period_days = period_days  # passed to scrapers that support time filtering

    @abstractmethod
    async def scrape(self, page: Page) -> List[Job]:
        pass

    async def run(self) -> List[Job]:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            ctx = await browser.new_context(user_agent=UA, locale="en-US")
            page = await ctx.new_page()
            try:
                jobs = await self.scrape(page)
            finally:
                await browser.close()
        return jobs
