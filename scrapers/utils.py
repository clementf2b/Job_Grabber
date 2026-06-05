"""Shared utilities used across all scrapers."""
import re
from bs4 import Tag

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Map period in days → LinkedIn f_TPR query value (0 = no filter)
LINKEDIN_PERIOD = {1: "r86400", 3: "r259200", 7: "r604800", 14: "r1209600", 30: "r2592000"}


def strip_html(text: str) -> str:
    """Remove HTML tags and decode common entities from a string."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = (text
            .replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
            .replace("&nbsp;", " ").replace("&quot;", '"').replace("&#39;", "'"))
    return re.sub(r"\s+", " ", text).strip()


def el_text(el: Tag | None) -> str:
    """Return plain text of a BS4 element, stripping icon tags (<i>, <svg>)."""
    if not el:
        return ""
    for tag in el.find_all(["i", "svg"]):
        tag.decompose()
    return el.get_text(strip=True)


def make_absolute(href: str, base: str) -> str:
    """Prepend base URL to href if it's a relative path."""
    if href and not href.startswith("http"):
        return base.rstrip("/") + href
    return href
