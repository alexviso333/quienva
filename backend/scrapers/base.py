"""Common data models & base class for club scrapers."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Optional
import re
import unicodedata


@dataclass
class ScrapedEvent:
    """Normalized event data extracted from any venue's public source.
    All optional fields are None/empty when unknown."""
    external_id: str                 # unique id used by the source (fvEventId / slug)
    name: str
    venue: str
    date: str                        # YYYY-MM-DD (Europe/Madrid local date)
    time: str = ""                   # HH:MM (24h) or ""
    image_url: str = ""
    genre: str = ""
    ticket_url: str = ""
    price_tiers: List[dict] = field(default_factory=list)
    sale_state: str = "a_la_venta"   # a_la_venta | pocas_entradas | agotado | no_a_la_venta
    currency: str = "EUR"
    description: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScraperResult:
    venue_id: str
    venue_name: str
    ok: bool
    events: List[ScrapedEvent] = field(default_factory=list)
    error: Optional[str] = None
    duration_ms: int = 0


class Scraper:
    """Base class every adapter extends. Concrete classes override .fetch().
    Adapters MUST be async, use httpx, and honor short timeouts. They MUST
    never raise — return ScraperResult with ok=False on any failure."""
    adapter_type: str = "base"

    def __init__(self, url: str, venue_name: str = "", city: str = "Palma de Mallorca"):
        self.url = url.rstrip("/")
        self.venue_name = venue_name
        self.city = city

    async def fetch(self) -> List[ScrapedEvent]:
        raise NotImplementedError


# ---- Helpers used by adapters ----

def normalize_venue_key(name: str) -> str:
    """Turn a venue name into a comparable lowercase slug (used for dedup)."""
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def parse_price_string(s: str) -> Optional[float]:
    """Extract the first number from strings like 'From €20', '20€', '20,50', '20.5'."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    m = re.search(r"(\d+(?:[.,]\d+)?)", str(s))
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except Exception:
        return None


def date_from_slug(slug: str) -> Optional[str]:
    """Extract dd-mm-yyyy from an event slug like 'lunnas-31-07-2026' →
    returns '2026-07-31'. Returns None if not found."""
    if not slug:
        return None
    m = re.search(r"(\d{2})-(\d{2})-(20\d{2})", slug)
    if not m:
        return None
    d, mth, y = m.groups()
    return f"{y}-{mth}-{d}"


def parse_iso_date(iso: str) -> Optional[str]:
    """Extract the YYYY-MM-DD portion from an ISO datetime string."""
    if not iso:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(iso))
    return m.group(0) if m else None


def parse_time(s: str) -> str:
    """Return HH:MM from strings like '23:45', '23:45 – 06:00', '11:45pm'."""
    if not s:
        return ""
    m = re.search(r"(\d{1,2})[:.](\d{2})", str(s))
    if not m:
        return ""
    hh = int(m.group(1))
    mm = int(m.group(2))
    if 0 <= hh <= 23 and 0 <= mm <= 59:
        return f"{hh:02d}:{mm:02d}"
    return ""
