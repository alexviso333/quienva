"""ClubTickets affiliate-catalog scraper.

ClubTickets' public site (clubtickets.com) is Cloudflare-protected, so it can't
be scraped directly. Instead we read OUR affiliate "links" panel
(admin.clubtickets.com/api/affiliate/<token>/links) — a plain, non-protected
HTML table that lists every club, party and date we're an affiliate for, with
the ticket URL for each (already carrying our ?aff=<code>).

Structure of the panel (rows in document order):
    <tr class="venue-row"> <td>[UNVRS]</td>            <td>.../clubbing/unvrs-ibiza?aff=CT226</td> </tr>
    <tr class="event-row"> <td> -- Anyma Presents ÆDEN</td> <td>.../unvrs-ibiza/anyma?aff=CT226</td> </tr>
    <tr class="date-row">  <td> -- -- 18/08/2026 </td>      <td>.../unvrs-ibiza/anyma/2026-08-18?aff=CT226</td> </tr>

One `ClubTicketsScraper` instance handles ONE venue (matched by its clubbing
slug); the panel HTML is fetched once and cached in-process (short TTL) so a
full run of N ClubTickets venues only downloads the panel once.
"""
from __future__ import annotations
import asyncio
import html as _html
import logging
import re
import time
from typing import List, Optional
from urllib.parse import urlparse, urlencode, parse_qsl, urlunparse

import httpx

from .base import Scraper, ScrapedEvent

logger = logging.getLogger("scrapers.clubtickets")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

# Approx coordinates per clubbing slug (best-effort, all Ibiza) so the map/detail
# view has a pin. Missing venues just fall back to None (no pin).
_COORDS = {
    "unvrs-ibiza": (38.9066, 1.4092),
    "ushuaia-ibiza": (38.885142, 1.405109),
    "hi-ibiza": (38.885987, 1.403855),
    "es-paradis": (38.9803, 1.2969),
    "eden-ibiza": (38.9799, 1.2966),
    "ibiza-rocks": (38.9807, 1.2999),
    "o-beach-ibiza": (38.9820, 1.2967),
    "lio": (38.9083, 1.4407),
    "club-chinois-ibiza": (38.9169, 1.4360),
    "swag": (38.9169, 1.4360),
    "528-ibiza": (38.9714, 1.3010),
    "baloo": (38.9700, 1.3000),
    "bambuku-ibiza": (39.0010, 1.5390),
    "playa-soleil": (38.9760, 1.2200),
    "teatro-pereyra": (38.9089, 1.4330),
}

# In-process cache of the affiliate panel HTML (shared across venue instances).
_PANEL_CACHE: dict = {"url": "", "html": "", "ts": 0.0}
_PANEL_TTL = 600  # seconds
_PANEL_LOCK = asyncio.Lock()

_ROW_RE = re.compile(
    r'<tr class="(venue|event|date)-row">\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*</tr>',
    re.S,
)


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    text = _html.unescape(text).strip()
    # Panel prefixes entries with " -- " / " -- -- " to show hierarchy.
    return text.lstrip("-").strip()


class ClubTicketsScraper(Scraper):
    """Reads the affiliate links panel and yields one venue's dated events."""
    adapter_type = "clubtickets"

    def __init__(self, url: str, venue_name: str = "", city: str = "Ibiza",
                 panel_url: str = "", aff_code: str = "", venue_slug: str = "", **_):
        super().__init__(url, venue_name, city)
        self.panel_url = panel_url or ""
        self.aff_code = (aff_code or "").strip()
        # Derive the clubbing slug from the venue URL if not explicitly given.
        slug = venue_slug
        if not slug:
            m = re.search(r"/clubbing/([a-z0-9\-]+)", self.url)
            slug = m.group(1) if m else ""
        self.venue_slug = slug
        self.lat, self.lng = _COORDS.get(slug, (None, None))

    async def _get_panel(self) -> str:
        """Fetch the affiliate panel HTML, cached in-process for a short TTL."""
        if not self.panel_url:
            return ""
        now = time.time()
        if (_PANEL_CACHE["url"] == self.panel_url and _PANEL_CACHE["html"]
                and now - _PANEL_CACHE["ts"] < _PANEL_TTL):
            return _PANEL_CACHE["html"]
        async with _PANEL_LOCK:
            now = time.time()
            if (_PANEL_CACHE["url"] == self.panel_url and _PANEL_CACHE["html"]
                    and now - _PANEL_CACHE["ts"] < _PANEL_TTL):
                return _PANEL_CACHE["html"]
            try:
                async with httpx.AsyncClient(
                    timeout=30, follow_redirects=True,
                    headers={"User-Agent": UA, "Accept": "text/html"},
                ) as client:
                    r = await client.get(self.panel_url)
                    if r.status_code == 200 and r.text:
                        _PANEL_CACHE.update(url=self.panel_url, html=r.text, ts=now)
                        return r.text
                    logger.warning(f"[clubtickets] panel HTTP {r.status_code}")
            except Exception as e:
                logger.warning(f"[clubtickets] panel fetch failed: {e}")
        return _PANEL_CACHE["html"] if _PANEL_CACHE["url"] == self.panel_url else ""

    def _tag(self, url: str) -> str:
        """Ensure the ticket URL carries OUR affiliate code (?aff=<code>)."""
        url = _html.unescape((url or "").strip())
        if not self.aff_code:
            return url
        try:
            p = urlparse(url)
            q = [(k, v) for k, v in parse_qsl(p.query) if k != "aff"]
            q.append(("aff", self.aff_code))
            return urlunparse(p._replace(query=urlencode(q)))
        except Exception:
            sep = "&" if "?" in url else "?"
            return f"{url}{sep}aff={self.aff_code}"

    async def fetch(self) -> List[ScrapedEvent]:
        if not self.venue_slug:
            return []
        panel = await self._get_panel()
        if not panel:
            return []

        out: List[ScrapedEvent] = []
        seen: set = set()
        cur_vslug: Optional[str] = None
        cur_ename: str = ""
        cur_eslug: str = ""
        prefix = f"/clubbing/{self.venue_slug}"

        for kind, label, raw_url in _ROW_RE.findall(panel):
            url = _html.unescape(raw_url.strip())
            m = re.search(r"/clubbing/([a-z0-9\-]+)(?:/([a-z0-9\-]+))?(?:/(\d{4}-\d{2}-\d{2}))?", url)
            if not m:
                continue
            vslug, eslug, date = m.group(1), m.group(2), m.group(3)
            if kind == "venue":
                cur_vslug = vslug
                if vslug == self.venue_slug and self.venue_name == "":
                    self.venue_name = _clean(label) or self.venue_name
            elif kind == "event":
                cur_eslug = eslug or ""
                cur_ename = _clean(label)
            elif kind == "date":
                if cur_vslug != self.venue_slug or not date:
                    continue
                if not url.startswith("http") and prefix not in url:
                    continue
                ext = f"ct:{self.venue_slug}:{eslug or cur_eslug}:{date}"
                if ext in seen:
                    continue
                seen.add(ext)
                name = cur_ename or (eslug or cur_eslug or self.venue_name).replace("-", " ").title()
                out.append(ScrapedEvent(
                    external_id=ext,
                    name=name[:120],
                    venue=self.venue_name,
                    date=date,
                    time="",
                    image_url="",
                    ticket_url=self._tag(url),
                    price_tiers=[],
                    sale_state="a_la_venta",
                    currency="EUR",
                    lat=self.lat, lng=self.lng,
                ))
        return out
