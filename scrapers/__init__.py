from .linkedin import LinkedInScraper
from .michaelpage import MichaelPageScraper
from .ctgoodjobs import CTgoodjobsScraper

SCRAPERS: dict[str, type] = {
    "linkedin":    LinkedInScraper,
    "michaelpage": MichaelPageScraper,
    "ctgoodjobs":  CTgoodjobsScraper,
}

DOMAIN_SCRAPERS: dict[str, type] = {
    domain: cls
    for cls in SCRAPERS.values()
    for domain in cls.domains
}
