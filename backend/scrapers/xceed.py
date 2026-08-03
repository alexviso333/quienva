"""Xceed adapter — scrapes xceed.me city event listings + per-event schema.org
JSON-LD for real ticket prices.

Flow per city:
  1. GET https://xceed.me/es/{city}/events  → discover event detail paths
     (/es/{city}/event/{slug}/{id}).
  2. For each event, GET the detail page and parse its `application/ld+json`
     `Event` block: name, startDate, `location` (venue, only NightClub /
     MusicVenue are kept — "good clubs"), and `offers[]` (name, price,
     availability). No auth / token needed; CloudFront-served, no challenge.
"""
from __future__ import annotations
import asyncio
import json
import logging
import re
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlparse

try:
    from zoneinfo import ZoneInfo
    _MADRID = ZoneInfo("Europe/Madrid")
except Exception:  # pragma: no cover
    _MADRID = None

import httpx

from .base import Scraper, ScrapedEvent

logger = logging.getLogger("scrapers.xceed")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36")
_HEADERS = {"User-Agent": UA, "Accept": "text/html", "Accept-Language": "es,en;q=0.8"}

MAX_EVENTS = 45
CONCURRENCY = 6
# Only real clubs/venues (drops boats, brunches, restaurants…).
_CLUB_TYPES = {"NightClub", "MusicVenue"}


def _to_float(x) -> Optional[float]:
    try:
        return float(str(x).replace(",", "."))
    except Exception:
        return None


def _first(x) -> str:
    if isinstance(x, str):
        return x
    if isinstance(x, list) and x:
        return _first(x[0])
    if isinstance(x, dict):
        return str(x.get("url") or x.get("contentUrl") or "")
    return ""


class XceedScraper(Scraper):
    """Scrapes one Xceed city listing → real club events with prices."""
    adapter_type = "xceed"

    def __init__(self, url: str, venue_name: str = "", city: str = "Ibiza", **_):
        super().__init__(url, venue_name, city)
        p = urlparse(self.url)
        self.origin = f"{p.scheme}://{p.netloc}"
        m = re.search(r"/es/([a-z0-9\-]+)/events", self.url)
        self.city_slug = m.group(1) if m else ""

    async def fetch(self) -> List[ScrapedEvent]:
        async with httpx.AsyncClient(timeout=30, headers=_HEADERS, follow_redirects=True) as client:
            listing = await self._get(client, self.url)
            paths, seen = [], set()
            for m in re.finditer(rf"/es/{re.escape(self.city_slug)}/event/[a-z0-9\-]+/(\d+)", listing or ""):
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
                    html = await self._get(client, u)
                    return self._parse_detail(html, u) if html else None

            results = await asyncio.gather(*(_one(u) for u in paths))
        return [e for e in results if e]

    async def _get(self, client: httpx.AsyncClient, url: str) -> str:
        try:
            r = await client.get(url)
            if r.status_code == 200:
                return r.text
        except Exception as e:
            logger.warning(f"[xceed] GET {url} failed: {e}")
        return ""

    def _parse_detail(self, html: str, url: str) -> Optional[ScrapedEvent]:
        ev = None
        for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S):
            try:
                j = json.loads(m.group(1))
            except Exception:
                continue
            for cand in (j if isinstance(j, list) else [j]):
                if isinstance(cand, dict) and cand.get("@type") == "Event" and cand.get("startDate"):
                    ev = cand
                    break
            if ev:
                break
        if not ev:
            return None

        loc = ev.get("location") or {}
        if isinstance(loc, list):
            loc = loc[0] if loc else {}
        if not isinstance(loc, dict) or loc.get("@type") not in _CLUB_TYPES:
            return None  # keep only real clubs
        venue = str(loc.get("name") or "").strip()
        if not venue:
            return None
        if re.search(r"\b(boat|cruise|crucero|barco|catamaran|yacht)\b", venue, re.I):
            return None  # not a real club

        date_str, time_str = self._when(ev.get("startDate"))
        if not date_str:
            return None

        offers = ev.get("offers") or []
        if isinstance(offers, dict):
            offers = [offers]
        tiers = []
        for o in offers:
            if not isinstance(o, dict):
                continue
            pr = _to_float(o.get("price") or o.get("lowPrice"))
            if pr is None:
                continue
            av = str(o.get("availability") or "")
            tiers.append({"name": str(o.get("name") or "Entrada")[:60], "price": pr,
                          "sold_out": ("SoldOut" in av or "OutOfStock" in av)})
        tiers.sort(key=lambda x: (x["sold_out"], x["price"]))
        available = [t for t in tiers if not t["sold_out"]]
        if not tiers:
            sale_state = "no_a_la_venta"
        elif not available:
            sale_state = "agotado"
        else:
            sale_state = "a_la_venta"

        eid = re.search(r"/(\d+)$", url)
        ext = f"xc:{eid.group(1)}" if eid else f"xc:{ev.get('slug') or venue}:{date_str}"
        geo = loc.get("geo") or {}
        lat = _to_float(geo.get("latitude")) if isinstance(geo, dict) else None
        lng = _to_float(geo.get("longitude")) if isinstance(geo, dict) else None
        img = _first(ev.get("image")) or _first(loc.get("image"))
        genre = ""
        return ScrapedEvent(
            external_id=ext,
            name=str(ev.get("name") or venue).strip()[:200],
            venue=venue, date=date_str, time=time_str,
            image_url=img, genre=genre, ticket_url=str(ev.get("url") or url),
            price_tiers=tiers, sale_state=sale_state, currency="EUR",
            description=str(ev.get("description") or "")[:800],
            lat=lat, lng=lng, venue_image=_first(loc.get("image")),
        )

    @staticmethod
    def _when(iso) -> tuple:
        if not iso:
            return "", ""
        s = str(iso).replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
        except Exception:
            m = re.match(r"(20\d{2}-\d{2}-\d{2})", str(iso))
            return (m.group(1), "") if m else ("", "")
        if dt.tzinfo and _MADRID:
            dt = dt.astimezone(_MADRID)
        return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")
