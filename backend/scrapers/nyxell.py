"""Nyxell adapter — scrapes a Nyxell RRPP (promoter) profile on open.nyxell.com.

Nyxell is a Nuxt/Vue ticketing platform. Its pages are server-side rendered, so
every promoter's event list and each event's ticket prices/sale-state are already
present in the returned HTML (no auth, no API token — the public `wsopen.nyxell.com`
API is WAF-protected, but the SSR markup carries the same data).

Flow (one RRPP profile, e.g. https://open.nyxell.com/rrpp/quienva):
  1. GET the profile page → enumerate event detail links
     (/rrpp/{slug}/event/{id}-{event-slug}) + each card's name/date/venue/poster.
  2. For each event, GET the detail page and parse the rendered ticket blocks:
     name, price ("15,00 €"), and sale-state via the language-independent emoji
     badges (💔 = sold out, 💨 = few left). Also geo coords (Google-Maps link),
     the venue+city title and the poster image.

Buy link = the event's own Nyxell RRPP URL, so every purchase is attributed to
this promoter profile.
"""
from __future__ import annotations
import asyncio
import html as _html
import logging
import re
from datetime import date, datetime
from typing import List, Optional
from urllib.parse import urlparse

import httpx

from .base import Scraper, ScrapedEvent, parse_price_string

logger = logging.getLogger("scrapers.nyxell")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
_HEADERS = {"User-Agent": UA, "Accept": "text/html",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.6"}

MAX_EVENTS = 40
CONCURRENCY = 5

# Month abbreviations as Nyxell renders them (Spanish + English), lowercased.
_MONTHS = {
    "ene": 1, "jan": 1, "feb": 2, "mar": 3, "abr": 4, "apr": 4, "may": 5,
    "jun": 6, "jul": 7, "ago": 8, "aug": 8, "sep": 9, "sept": 9, "oct": 10,
    "nov": 11, "dic": 12, "dec": 12,
}


def _strip_tags(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = _html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


class NyxellScraper(Scraper):
    """Scrapes one Nyxell RRPP profile → its events with real prices/sale-state."""
    adapter_type = "nyxell"

    def __init__(self, url: str, venue_name: str = "", city: str = "Sevilla", **_):
        super().__init__(url, venue_name, city)
        p = urlparse(self.url)
        self.origin = f"{p.scheme}://{p.netloc}"
        # RRPP slug = segment right after '/rrpp/' (locale prefix optional).
        m = re.search(r"/rrpp/([a-z0-9\-]+)", self.url, re.I)
        self.rrpp_slug = m.group(1) if m else ""

    async def fetch(self) -> List[ScrapedEvent]:
        if not self.rrpp_slug:
            return []
        async with httpx.AsyncClient(timeout=30, headers=_HEADERS,
                                     follow_redirects=True) as client:
            listing = await self._get(client, self.url)
            if not listing:
                return []
            # Discover unique event ids + their detail path.
            paths, seen = [], set()
            pat = rf"/(?:[a-z]{{2}}/)?rrpp/{re.escape(self.rrpp_slug)}/event/(\d+)-[^\"'\s>]+"
            for m in re.finditer(pat, listing):
                eid = m.group(1)
                if eid in seen:
                    continue
                seen.add(eid)
                paths.append(self.origin + m.group(0))
            paths = paths[:MAX_EVENTS]
            if not paths:
                return []

            sem = asyncio.Semaphore(CONCURRENCY)

            async def _one(u: str):
                async with sem:
                    detail = await self._get(client, u)
                    return self._parse_detail(detail, u) if detail else None

            results = await asyncio.gather(*(_one(u) for u in paths))
        return [e for e in results if e]

    async def _get(self, client: httpx.AsyncClient, url: str) -> str:
        try:
            r = await client.get(url)
            if r.status_code == 200:
                return r.text
        except Exception as e:
            logger.warning(f"[nyxell] GET {url} failed: {e}")
        return ""

    def _parse_detail(self, html: str, url: str) -> Optional[ScrapedEvent]:
        eid_m = re.search(r"/event/(\d+)-", url)
        if not eid_m:
            return None
        ext = f"nyx:{eid_m.group(1)}"

        # --- date + time from the rendered event card ---
        day_m = re.search(r'event-card-date-day"[^>]*>(\d{1,2})<', html)
        mon_m = re.search(r'event-card-date-month"[^>]*>([A-Za-zÁÉÍÓÚáéíóú\.]+)<', html)
        if not (day_m and mon_m):
            return None
        month = _MONTHS.get(mon_m.group(1).strip(".").lower()[:4]) \
            or _MONTHS.get(mon_m.group(1).strip(".").lower()[:3])
        if not month:
            return None
        day = int(day_m.group(1))
        date_str = self._resolve_date(day, month)
        if not date_str:
            return None

        hour_m = re.search(r'event-card-hour"[^>]*>([^<]+)<', html)
        time_str = self._parse_time(hour_m.group(1)) if hour_m else ""

        # --- name ---
        name_m = re.search(r'<h2[^>]*event-card-name[^>]*>\s*([^<]+?)\s*</h2>', html, re.S)
        name = _html.unescape(name_m.group(1)).strip() if name_m else ""
        if not name:
            return None

        # --- venue (+ city) from the "event-detail-room" title ---
        venue = self.venue_name or ""
        room_m = re.search(r'event-detail-room[^>]*>.*?<h1[^>]*>([^<]+)</h1>', html, re.S)
        if room_m:
            room = _html.unescape(room_m.group(1)).strip()
            venue = room.split(",")[0].strip() or venue
        if not venue:
            venue = self.venue_name

        # --- poster image (S3 url in the card's CSS var; quotes are HTML-encoded) ---
        img = ""
        img_m = re.search(
            r"url\((?:&#39;|&quot;|['\"])?(https://[^'\")\s&]+\.(?:jpg|jpeg|png|webp))",
            html, re.I)
        if img_m:
            img = img_m.group(1)

        # --- geo coordinates from the Google-Maps link ---
        lat = lng = None
        geo_m = re.search(r"maps/search/\?api=1&(?:amp;)?query=(-?\d+\.\d+),(-?\d+\.\d+)", html)
        if geo_m:
            try:
                lat = float(geo_m.group(1))
                lng = float(geo_m.group(2))
            except Exception:
                lat = lng = None

        # --- description ---
        desc = ""
        desc_m = re.search(r'<p[^>]*event-detail-description[^>]*>(.*?)</p>', html, re.S)
        if desc_m:
            desc = _strip_tags(desc_m.group(1))[:800]

        # --- ticket tiers + sale state ---
        tiers, any_few = self._parse_tickets(html)
        available = [t for t in tiers if not t["sold_out"]]
        if not tiers:
            sale_state = "no_a_la_venta"
        elif not available:
            sale_state = "agotado"
        elif any_few:
            sale_state = "pocas_entradas"
        else:
            sale_state = "a_la_venta"

        return ScrapedEvent(
            external_id=ext,
            name=name[:200],
            venue=venue,
            date=date_str,
            time=time_str,
            image_url=img,
            genre="",
            ticket_url=url,
            price_tiers=tiers,
            sale_state=sale_state,
            currency="EUR",
            description=desc,
            lat=lat, lng=lng,
            venue_image="",
        )

    def _parse_tickets(self, html: str) -> tuple:
        """Return (tiers, any_few). Each tier: {name, price, sold_out}."""
        tiers, any_few = [], False
        blocks = re.split(r'class="ticket-name"', html)
        for b in blocks[1:]:
            # Bound the block so we don't leak into the next ticket / page.
            b = b[:1500]
            nm_m = re.match(r'[^>]*>([^<]+)<', b)
            tname = _html.unescape(nm_m.group(1)).strip() if nm_m else "Entrada"
            pr = None
            pr_m = re.search(r'(\d{1,4}(?:[.,]\d{1,2})?)\s*(?:&nbsp;|&#160;|\s)*€', b)
            if pr_m:
                pr = parse_price_string(pr_m.group(1))
            if pr is None:
                continue
            sold_out = ("💔" in b) or bool(re.search(r"sold\s*out|agotad", b, re.I))
            few = ("💨" in b) or bool(re.search(r"flying|vuelan|pocas", b, re.I))
            if few and not sold_out:
                any_few = True
            tiers.append({"name": tname[:60], "price": pr, "sold_out": sold_out})
        tiers.sort(key=lambda x: (x["sold_out"], x["price"]))
        return tiers, any_few

    @staticmethod
    def _resolve_date(day: int, month: int) -> Optional[str]:
        """Build YYYY-MM-DD from a day+month with no year, picking the next
        occurrence (Nyxell RRPP profiles only list upcoming events)."""
        today = date.today()
        year = today.year
        try:
            d = date(year, month, day)
        except ValueError:
            return None
        # If it already passed (with a small grace window), it's next year.
        if (today - d).days > 3:
            try:
                d = date(year + 1, month, day)
            except ValueError:
                return None
        return d.isoformat()

    @staticmethod
    def _parse_time(raw: str) -> str:
        """'12:00 AM' -> '' (midnight placeholder), '11:30 PM' -> '23:30',
        '23:30' -> '23:30'. Midnight is treated as a placeholder (hidden by the
        app) so the event keeps the date the venue published."""
        s = _html.unescape(raw or "").strip()
        m = re.search(r"(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)?", s)
        if not m:
            return ""
        hh, mm = int(m.group(1)), int(m.group(2))
        ap = (m.group(3) or "").upper()
        if ap == "AM":
            if hh == 12:
                hh = 0
        elif ap == "PM":
            if hh != 12:
                hh += 12
        if hh == 0 and mm == 0:
            return ""  # midnight placeholder
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return f"{hh:02d}:{mm:02d}"
        return ""
