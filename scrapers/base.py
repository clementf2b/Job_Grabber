"""Base scraper — all board scrapers inherit from this."""
from abc import ABC, abstractmethod
from typing import List, Optional
from playwright.async_api import async_playwright, Page
from models import Job
from scrapers.utils import UA


class BaseScraper(ABC):
    name: str = ""
    domains: tuple[str, ...] = ()  # hostname(s) this scraper handles, used for --urls dispatch
    headless: bool = True

    def __init__(self, keyword: str, location: str = "Hong Kong",
                 max_pages: int = 3, period_days: int = 7):
        self.keyword = keyword
        self.location = location
        self.max_pages = max_pages
        self.period_days = period_days

    @abstractmethod
    async def scrape(self, page: Page) -> List[Job]:
        pass

    async def scrape_single(self, url: str, page: Page) -> Optional[Job]:
        """Override in subclasses to support scraping a single job URL."""
        raise NotImplementedError(f"{self.__class__.__name__} does not support scrape_single")

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

    async def run_single(self, url: str) -> Optional[Job]:
        """Scrape a single job URL, owning the full browser lifecycle."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            ctx = await browser.new_context(user_agent=UA, locale="en-US")
            page = await ctx.new_page()
            try:
                return await self.scrape_single(url, page)
            finally:
                await browser.close()
