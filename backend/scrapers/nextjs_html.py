"""Universal scraper for Next.js sites that embed events in __next_f.push chunks
(e.g. www.amokmallorca.com). Extracts JSON blocks with a permissive parser that
handles Next.js RSC-style escaping."""
from __future__ import annotations
import re
import json
import logging
import httpx
from typing import List, Optional
from .base import (
    Scraper, ScrapedEvent, parse_price_string, date_from_slug, parse_time,
)

logger = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# Regex that captures a single event object in the payload. Event blocks in
# Amok-style RSC payloads look like:
#   {"id":"cm...","fvEventId":"...","slug":"...","artist":"...",...}
# We look for the {"id":"cm... boundary and then match balanced braces manually.
_ID_RE = re.compile(r'\{"id":"(cm[a-z0-9]{22,26}|[a-f0-9-]{20,40})"')


def _extract_next_payload(html: str) -> str:
    """Return the concatenated & decoded __next_f.push payload."""
    parts = re.findall(r'self\.__next_f\.push\(\[\d+,"((?:[^"\\]|\\.)*)"\]\)', html, re.DOTALL)
    out = []
    for p in parts:
        try:
            out.append(p.encode("utf-8").decode("unicode_escape", errors="replace"))
        except Exception:
            out.append(p)
    return "".join(out)


def _find_balanced_json(payload: str, start_idx: int) -> Optional[str]:
    """Given the position of the opening '{', walk the payload counting braces
    (respecting strings & escapes) and return the full JSON blob as a string.
    Returns None on failure."""
    if start_idx >= len(payload) or payload[start_idx] != "{":
        return None
    depth = 0
    in_str = False
    esc = False
    i = start_idx
    L = len(payload)
    while i < L:
        c = payload[i]
        if esc:
            esc = False
        elif c == "\\":
            esc = True
        elif in_str:
            if c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return payload[start_idx:i + 1]
        i += 1
        # Safety cap to avoid runaway on malformed data
        if i - start_idx > 20000:
            return None
    return None


class NextJsHtmlScraper(Scraper):
    adapter_type = "nextjs_html"

    async def fetch(self) -> List[ScrapedEvent]:
        # Fetch the venue homepage; that's where the events array is embedded.
        async with httpx.AsyncClient(timeout=15, headers={"User-Agent": UA}, follow_redirects=True) as client:
            r = await client.get(self.url)
        r.raise_for_status()
        html = r.text
        payload = _extract_next_payload(html)
        if not payload:
            return []

        out: List[ScrapedEvent] = []
        seen_ids = set()
        for m in _ID_RE.finditer(payload):
            start = m.start()
            raw = _find_balanced_json(payload, start)
            if not raw:
                continue
            # Attempt to json.loads — some blocks contain the special token
            # "$undefined" which is not valid JSON. Replace before parsing.
            cleaned = raw.replace('"$undefined"', "null")
            try:
                obj = json.loads(cleaned)
            except Exception:
                continue
            ev = self._parse(obj)
            if not ev:
                continue
            if ev.external_id in seen_ids:
                continue
            seen_ids.add(ev.external_id)
            out.append(ev)
        return out

    def _parse(self, it: dict) -> ScrapedEvent | None:
        # Amok-style schema: id, fvEventId, slug, artist, subtitle, date, time,
        # venue, genre[list], price, vipPrice, artwork, hasVIP, ticketsSoldOut,
        # vipSoldOut, category, description.
        # Skip non-event objects that happen to have an 'id' matching our regex.
        # An event MUST have slug + (date or time) + (price or artwork).
        if not it.get("slug") or not (it.get("artist") or it.get("title") or it.get("name")):
            return None
        slug = str(it["slug"])
        # Prefer fvEventId (stable across the venue's site) but fall back to id.
        external_id = str(it.get("fvEventId") or it.get("id") or slug)
        name = str(it.get("artist") or it.get("title") or it.get("name") or "").strip()
        subtitle = (it.get("subtitle") or "").strip()
        if subtitle:
            name = f"{name} · {subtitle}" if len(f"{name} · {subtitle}") <= 90 else name

        # Date: primary via slug (contains dd-mm-yyyy); fallback to it['date'].
        date_iso = date_from_slug(slug)
        if not date_iso:
            return None

        # Time: the field looks like '23:45 – 06:00' — take the first HH:MM.
        time_str = parse_time(it.get("time") or "")

        artwork = str(it.get("artwork") or it.get("ogImage") or "")
        # Genre: list -> comma joined
        g = it.get("genre")
        if isinstance(g, list):
            genre = ", ".join(str(x) for x in g if x)
        else:
            genre = str(g or it.get("category") or "")

        # Tiers
        general = parse_price_string(it.get("price"))
        vip = parse_price_string(it.get("vipPrice"))
        general_sold = bool(it.get("ticketsSoldOut"))
        vip_sold = bool(it.get("vipSoldOut"))
        tiers = []
        if general is not None:
            tiers.append({"name": "General", "price": float(general), "sold_out": general_sold})
        if vip is not None and it.get("hasVIP"):
            tiers.append({"name": "VIP", "price": float(vip), "sold_out": vip_sold})

        if tiers and all(t["sold_out"] for t in tiers):
            state = "agotado"
        elif tiers:
            state = "a_la_venta"
        else:
            state = "no_a_la_venta"

        # Ticket URL: try common patterns — this varies wildly per site. We'll
        # leave it empty and rely on the commission_url set manually if needed.
        ticket_url = str(it.get("ticketUrl") or "")

        return ScrapedEvent(
            external_id=external_id,
            name=name,
            venue=self.venue_name or str(it.get("venue") or ""),
            date=date_iso,
            time=time_str,
            image_url=artwork,
            genre=genre,
            ticket_url=ticket_url,
            price_tiers=tiers,
            sale_state=state,
            description=str(it.get("description") or "")[:1000],
        )
