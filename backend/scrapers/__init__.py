from .base import ScrapedEvent, ScraperResult, Scraper
from .fitz_public_api import FitzPublicAPIScraper
from .nextjs_html import NextJsHtmlScraper
from .fourvenues_api import FourVenuesApiScraper, FourVenuesTokenError

__all__ = [
    "ScrapedEvent", "ScraperResult", "Scraper",
    "FitzPublicAPIScraper", "NextJsHtmlScraper", "FourVenuesApiScraper",
    "FourVenuesTokenError", "build_scraper",
]


def build_scraper(adapter_type: str, url: str, **kwargs) -> Scraper:
    """Factory: return the right scraper for the given adapter_type.
    Supported types: 'fourvenues_api' (universal, preferred),
    'fourvenues_public_api' (legacy /api/fourvenues), 'nextjs_html'.
    """
    if adapter_type == "fourvenues_api":
        return FourVenuesApiScraper(url, **kwargs)
    if adapter_type == "fourvenues_public_api":
        # Legacy adapter doesn't accept slug/guest_token kwargs.
        kwargs.pop("slug", None)
        kwargs.pop("guest_token", None)
        return FitzPublicAPIScraper(url, **kwargs)
    if adapter_type == "nextjs_html":
        kwargs.pop("slug", None)
        kwargs.pop("guest_token", None)
        return NextJsHtmlScraper(url, **kwargs)
    raise ValueError(f"Unknown scraper adapter_type: {adapter_type}")
