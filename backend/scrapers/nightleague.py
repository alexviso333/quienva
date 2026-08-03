"""The Night League venues (Ushuaïa Ibiza, Hï Ibiza) — official-site scraper.

Both official sites are Nuxt apps that embed the full 2026 event calendar in
the `__NUXT_DATA__` payload (devalue-serialized flat array). Two data shapes
are supported:

  A) `ct-availability` node (Ushuaïa): a club-wide feed present on ANY event
     page → residency{slug,name,start,dates[]} → dates[]{date,active_tickets,
     tickets[{name,price}]}. Real ClubTickets prices, no Cloudflare (the venue's
     own server fetches & embeds them). ONE page fetch gives the whole club.
  B) schema.org JSON-LD `Event` objects (Hï): per residency page →
     `startDate` + `AggregateOffer`(lowPrice/availability) + per-date buy `url`.

No auth / token needed.
"""
from __future__ import annotations
import asyncio
import json
import logging
import re
from typing import List, Optional
from urllib.parse import urlparse

import httpx

from .base import Scraper, ScrapedEvent

logger = logging.getLogger("scrapers.nightleague")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36")
_HEADERS = {"User-Agent": UA, "Accept": "text/html", "Accept-Language": "es,en;q=0.8"}

MAX_PAGES = 30
CONCURRENCY = 5
_TAGS = {"Reactive", "ShallowReactive", "Ref", "ShallowRef",
         "EmptyRef", "EmptyShallowRef", "NuxtError"}
_COORDS = {"ushuaia": (38.885142, 1.405109), "hi": (38.885987, 1.403855)}


class _Devalue:
    """Resolve Nuxt/devalue flat-array references into plain Python."""

    def __init__(self, arr: list):
        self.arr = arr

    def resolve(self, idx, depth: int = 0, seen: tuple = ()):
        if not isinstance(idx, int):
            return idx
        if idx in seen or depth > 60 or idx < 0 or idx >= len(self.arr):
            return None
        seen = seen + (idx,)
        v = self.arr[idx]
        if isinstance(v, list):
            if len(v) >= 2 and isinstance(v[0], str) and v[0] in _TAGS:
                return self.resolve(v[1], depth + 1, seen)
            return [self.resolve(x, depth + 1, seen) for x in v]
        if isinstance(v, dict):
            return {k: self.resolve(vv, depth + 1, seen) for k, vv in v.items()}
        return v


def _to_float(x) -> Optional[float]:
    try:
        return float(str(x).replace(",", "."))
    except Exception:
        return None


def _first_img(x) -> str:
    if isinstance(x, str):
        return x
    if isinstance(x, list) and x:
        return _first_img(x[0])
    if isinstance(x, dict):
        return str(x.get("url") or x.get("src") or "")
    return ""


def _find_key(o, key: str):
    if isinstance(o, dict):
        if key in o:
            return o[key]
        for v in o.values():
            r = _find_key(v, key)
            if r is not None:
                return r
    elif isinstance(o, list):
        for v in o:
            r = _find_key(v, key)
            if r is not None:
                return r
    return None


class NightLeagueScraper(Scraper):
    """Scrapes theushuaiaexperience.com / hiibiza.com official calendars."""
    adapter_type = "nightleague"

    def __init__(self, url: str, venue_name: str = "", city: str = "Ibiza", **_):
        super().__init__(url, venue_name, city)
        p = urlparse(self.url)
        self.origin = f"{p.scheme}://{p.netloc}"
        self.netloc = p.netloc
        key = "ushuaia" if "ushuaia" in p.netloc else ("hi" if "hiibiza" in p.netloc else "")
        self.lat, self.lng = _COORDS.get(key, (None, None))

    async def fetch(self) -> List[ScrapedEvent]:
        async with httpx.AsyncClient(timeout=25, headers=_HEADERS, follow_redirects=True) as client:
            landing = await self._get(client, self.url)
            cal = await self._get(client, f"{self.origin}/events-calendar")
            prefix = self._prefix(landing) or self._prefix(cal)
            urls = self._discover(landing, prefix) | self._discover(cal, prefix)
            urls = list(urls)[:MAX_PAGES]
            if not urls:
                return []

            # Shape A: ct-availability is a club-wide feed on any page → one fetch.
            first = await self._get(client, urls[0])
            ct = self._parse_ct(first)
            if ct:
                return ct

            # Shape B: JSON-LD is per-residency → fetch every page.
            sem = asyncio.Semaphore(CONCURRENCY)

            async def _one(u: str):
                async with sem:
                    html = await self._get(client, u)
                    return self._parse_jsonld(html, self._slug_of(u)) if html else []

            results = await asyncio.gather(*(_one(u) for u in urls))

        out, seen = [], set()
        for lst in results:
            for ev in lst:
                if ev.external_id in seen:
                    continue
                seen.add(ev.external_id)
                out.append(ev)
        return out

    # ---- helpers ----

    @staticmethod
    def _slug_of(url: str) -> str:
        m = re.search(r"events/20\d{2}/([a-z0-9\-]+)", url)
        return m.group(1) if m else ""

    @staticmethod
    def _prefix(html: str) -> str:
        m = re.search(r'href="(/[^"]*events/20\d{2})/[a-z0-9\-]+"', html or "")
        return m.group(1) if m else ""

    def _discover(self, html: str, prefix: str = "") -> set:
        urls = {self.origin + p
                for p in re.findall(r'href="(/[^"]*events/20\d{2}/[a-z0-9\-]+)"', html or "")}
        # Calendar pages expose bare slugs in JSON, not <a href> — rebuild them.
        if prefix:
            for slug in re.findall(r"events/20\d{2}/([a-z0-9\-]+)", html or ""):
                urls.add(f"{self.origin}{prefix}/{slug}")
        return urls

    async def _get(self, client: httpx.AsyncClient, url: str) -> str:
        try:
            r = await client.get(url)
            if r.status_code == 200:
                return r.text
        except Exception as e:
            logger.warning(f"[nightleague] GET {url} failed: {e}")
        return ""

    @staticmethod
    def _root(html: str):
        m = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
        if not m:
            return None
        try:
            return _Devalue(json.loads(m.group(1))).resolve(0)
        except Exception:
            return None

    @staticmethod
    def _og_image(html: str) -> str:
        m = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html or "")
        return m.group(1) if m else ""

    # ---- Shape A: Ushuaïa ct-availability (whole club) ----

    def _parse_ct(self, html: str) -> List[ScrapedEvent]:
        root = self._root(html)
        if root is None:
            return []
        node = _find_key(root, "ct-availability")
        if not isinstance(node, list) or not node:
            return []
        og = self._og_image(html)
        base = self._clubtickets_base(root)
        out = []
        for resi in node:
            if not isinstance(resi, dict) or not resi.get("slug"):
                continue
            rslug = str(resi["slug"])
            name = str(resi.get("name") or self.venue_name).strip()
            rtime = str(resi.get("start") or "")[:5]
            cover = _first_img(resi.get("cover_file") or resi.get("logo_file")) or og
            for d in resi.get("dates") or []:
                if not isinstance(d, dict):
                    continue
                date_str = str(d.get("date") or "")[:10]
                if not re.match(r"20\d{2}-\d{2}-\d{2}$", date_str):
                    continue
                tiers = []
                for t in d.get("tickets") or []:
                    pr = _to_float(t.get("price")) if isinstance(t, dict) else None
                    if pr is None:
                        continue
                    tiers.append({"name": str(t.get("name") or "Entrada")[:60],
                                  "price": pr, "sold_out": False})
                tiers.sort(key=lambda x: x["price"])
                if tiers:
                    sale_state = "a_la_venta"
                elif d.get("active_tickets") == 0:
                    sale_state = "agotado"
                else:
                    sale_state = "no_a_la_venta"
                buy = f"{base}/{rslug}/{date_str}" if base else ""
                out.append(ScrapedEvent(
                    external_id=f"nl:{self.netloc}:{rslug}:{date_str}",
                    name=name, venue=self.venue_name, date=date_str, time=rtime,
                    image_url=cover, ticket_url=buy, price_tiers=tiers,
                    sale_state=sale_state, currency="EUR",
                    lat=self.lat, lng=self.lng, venue_image=cover,
                ))
        return out

    @staticmethod
    def _clubtickets_base(root) -> str:
        found = {"v": ""}

        def walk(o):
            if found["v"]:
                return
            if isinstance(o, str):
                m = re.match(r"(https://www\.clubtickets\.com/clubbing/[a-z0-9\-]+)/[a-z0-9\-]+/\{", o)
                if m:
                    found["v"] = m.group(1)
            elif isinstance(o, dict):
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)

        walk(root)
        return found["v"]

    # ---- Shape B: Hï schema.org JSON-LD ----

    def _parse_jsonld(self, html: str, slug: str) -> List[ScrapedEvent]:
        root = self._root(html)
        if root is None:
            return []
        og = self._og_image(html)
        events = []

        def walk(o):
            if isinstance(o, dict):
                if o.get("startDate") and "offers" in o:
                    events.append(o)
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)

        walk(root)
        out, seen = [], set()
        for e in events:
            dm = re.match(r"(20\d{2}-\d{2}-\d{2})(?:T(\d{2}:\d{2}))?", str(e.get("startDate") or ""))
            if not dm:
                continue
            date_str, time_str = dm.group(1), (dm.group(2) or "")
            if date_str in seen:
                continue
            seen.add(date_str)
            off = e.get("offers") or {}
            if isinstance(off, list):
                off = off[0] if off else {}
            low = _to_float(off.get("lowPrice") or off.get("price"))
            avail = str(off.get("availability") or "")
            sold = "SoldOut" in avail or "OutOfStock" in avail
            if sold:
                sale_state = "agotado"
            elif "InStock" in avail and low is not None:
                sale_state = "a_la_venta"
            else:
                sale_state = "no_a_la_venta"
            tiers = [{"name": "Entrada", "price": low, "sold_out": sold}] if low is not None else []
            img = _first_img(e.get("image")) or og
            out.append(ScrapedEvent(
                external_id=f"nl:{self.netloc}:{slug}:{date_str}",
                name=str(e.get("name") or self.venue_name).strip(),
                venue=self.venue_name, date=date_str, time=time_str,
                image_url=img, ticket_url=str(e.get("url") or ""),
                price_tiers=tiers, sale_state=sale_state, currency="EUR",
                lat=self.lat, lng=self.lng, venue_image=img,
            ))
        return out
