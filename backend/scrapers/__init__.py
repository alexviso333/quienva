from .base import ScrapedEvent, ScraperResult, Scraper
from .fitz_public_api import FitzPublicAPIScraper
from .nextjs_html import NextJsHtmlScraper

__all__ = [
    "ScrapedEvent", "ScraperResult", "Scraper",
    "FitzPublicAPIScraper", "NextJsHtmlScraper",
    "build_scraper",
]


def build_scraper(adapter_type: str, url: str, **kwargs) -> Scraper:
    """Factory: return the right scraper for the given adapter_type.
    Supported types: 'fourvenues_public_api', 'nextjs_html'.
    """
    if adapter_type == "fourvenues_public_api":
        return FitzPublicAPIScraper(url, **kwargs)
    if adapter_type == "nextjs_html":
        return NextJsHtmlScraper(url, **kwargs)
    raise ValueError(f"Unknown scraper adapter_type: {adapter_type}")
