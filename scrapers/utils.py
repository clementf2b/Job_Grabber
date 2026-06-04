"""Shared utilities used across all scrapers."""
import re

# Common user-agent string reused by every scraper and browser context
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Map period in days → LinkedIn f_TPR query value (0 = no filter)
LINKEDIN_PERIOD = {1: "r86400", 3: "r259200", 7: "r604800", 30: "r2592000"}


def strip_html(text: str) -> str:
    """Remove HTML tags and decode common entities from a string."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = (text
            .replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
            .replace("&nbsp;", " ").replace("&quot;", '"').replace("&#39;", "'"))
    return re.sub(r"\s+", " ", text).strip()
