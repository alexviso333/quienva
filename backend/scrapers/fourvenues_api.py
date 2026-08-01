"""Universal scraper for ANY club/promoter hosted on FourVenues.

FourVenues powers most nightlife venues in Palma (Amok, Fitz, Lunita,
Mar Salada, Over Club, Luna Palma, Palma Events...). Every microsite at
`site.fourvenues.com/es/<slug>` is backed by a clean JSON API:

  * List:    GET /api/events?slug=<slug>&startDate=<unix>&endDate=<unix>
             &pageSize=200&page=1&orderBy=startDate&orderType=asc
  * Tickets: GET /api/events/<code>/tickets-types?slug=<slug>
             -> price, isSoldOut, areFewLeft, sale dates, phases (options)

Both require a guest-token JWT in the Authorization header. The token is
long-lived (no exp claim) and shared across all microsites. It is provided
via the `guest_token` kwarg (backend reads it from settings / env).

This adapter is strictly richer than HTML scraping: it yields real prices,
sold-out and "few left" flags, so the app can fire precise notifications.
"""
from __future__ import annotations
import asyncio
import logging
import re
import time as _time
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

import httpx

from .base import Scraper, ScrapedEvent

logger = logging.getLogger(__name__)

API_BASE = "https://cli-api-service.fourvenues.com"
SITE_BASE = "https://site.fourvenues.com/es"
ORIGIN = "https://site.fourvenues.com"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
MADRID = ZoneInfo("Europe/Madrid")

# How far ahead to look for events, and cap on per-run detail fetches.
LOOKAHEAD_DAYS = 120
LOOKBACK_DAYS = 1
MAX_DETAIL_FETCHES = 120
DETAIL_CONCURRENCY = 6


class FourVenuesTokenError(Exception):
    """Raised when the guest token is missing/invalid (HTTP 401)."""


class FourVenuesApiScraper(Scraper):
    adapter_type = "fourvenues_api"

    def __init__(self, url: str, venue_name: str = "", city: str = "Palma de Mallorca",
                 slug: Optional[str] = None, guest_token: Optional[str] = None, **_):
        super().__init__(url, venue_name, city)
        self.slug = (slug or self._slug_from_url(url) or "").strip().strip("/")
        self.guest_token = (guest_token or "").strip()

    @staticmethod
    def _slug_from_url(url: str) -> str:
        if not url:
            return ""
        m = re.search(r"/es/([a-z0-9][a-z0-9-]*)", url, re.I)
        if m:
            return m.group(1)
        # Fall back to the last path segment (allows storing just the slug).
        tail = url.rstrip("/").split("/")[-1]
        return tail if re.match(r"^[a-z0-9][a-z0-9-]*$", tail or "", re.I) else ""

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.guest_token}",
            "Origin": ORIGIN,
            "Referer": ORIGIN + "/",
            "User-Agent": UA,
            "Accept": "application/json",
        }

    async def fetch(self) -> List[ScrapedEvent]:
        if not self.slug:
            raise ValueError("FourVenues: falta el 'slug' de la discoteca")
        if not self.guest_token:
            raise FourVenuesTokenError("FourVenues: falta el guest-token")

        now = datetime.now(timezone.utc)
        start = int((now - timedelta(days=LOOKBACK_DAYS)).timestamp())
        end = int((now + timedelta(days=LOOKAHEAD_DAYS)).timestamp())
        params = {
            "startDate": start, "endDate": end, "slug": self.slug,
            "pageSize": 200, "page": 1, "orderBy": "startDate", "orderType": "asc",
        }

        async with httpx.AsyncClient(timeout=15, headers=self._headers()) as client:
            r = await client.get(f"{API_BASE}/api/events", params=params)
            if r.status_code == 401:
                raise FourVenuesTokenError(
                    "FourVenues: guest-token inválido o caducado (401). "
                    "Actualízalo en el panel de admin."
                )
            r.raise_for_status()
            payload = r.json()
            items = payload.get("data", []) if isinstance(payload, dict) else payload
            if not isinstance(items, list):
                items = []

            # Fetch ticket details concurrently (capped) to enrich price/state.
            items = items[:MAX_DETAIL_FETCHES]
            sem = asyncio.Semaphore(DETAIL_CONCURRENCY)

            async def _tickets(code: str):
                if not code:
                    return None
                async with sem:
                    try:
                        tr = await client.get(
                            f"{API_BASE}/api/events/{code}/tickets-types",
                            params={"slug": self.slug},
                        )
                        if tr.status_code == 401:
                            raise FourVenuesTokenError("401 en tickets-types")
                        if tr.status_code != 200:
                            return None
                        tp = tr.json()
                        return tp.get("data", []) if isinstance(tp, dict) else tp
                    except FourVenuesTokenError:
                        raise
                    except Exception as e:
                        logger.warning(f"[fourvenues {self.slug}] tickets {code} failed: {e}")
                        return None

            codes = [str(it.get("code") or "") for it in items]
            tickets_lists = await asyncio.gather(*(_tickets(c) for c in codes))

        out: List[ScrapedEvent] = []
        for it, tickets in zip(items, tickets_lists):
            try:
                ev = self._parse(it, tickets)
                if ev:
                    out.append(ev)
            except Exception as e:
                logger.warning(f"[fourvenues {self.slug}] parse failed: {e}")
        return out

    # ---- parsing helpers ----

    def _parse(self, it: dict, tickets: Optional[list]) -> Optional[ScrapedEvent]:
        code = str(it.get("code") or "")
        ev_id = str(it.get("id") or code)
        if not ev_id:
            return None
        name = str(it.get("name") or "").strip()
        if not name:
            return None

        dates = it.get("dates") or {}
        start_ts = dates.get("start") or dates.get("date")
        if not start_ts:
            return None
        dt = datetime.fromtimestamp(int(start_ts), tz=MADRID)
        date_str = dt.strftime("%Y-%m-%d")
        # Only emit a time if the source gave a real start datetime (not midnight-only date).
        time_str = dt.strftime("%H:%M") if dates.get("start") else ""

        org = it.get("organization") or {}
        venue = str(org.get("name") or self.venue_name or "").strip()

        genres = it.get("genres") or it.get("musicalGenres") or []
        genre = ""
        if isinstance(genres, list) and genres:
            genre = str(genres[0]).replace("-", " ").strip()
        elif isinstance(genres, str):
            genre = genres

        image = str(it.get("image") or org.get("cover") or "")
        loc = it.get("location") or {}
        address = str(loc.get("addressComplete") or "")

        ticket_url = f"{SITE_BASE}/{self.slug}/events/{code}" if code else self.url

        price_tiers, sale_state = self._pricing(tickets)

        return ScrapedEvent(
            external_id=f"fv:{ev_id}",
            name=name,
            venue=venue,
            date=date_str,
            time=time_str,
            image_url=image,
            genre=genre[:40],
            ticket_url=ticket_url,
            price_tiers=price_tiers,
            sale_state=sale_state,
            currency="EUR",
            description=str(it.get("description") or "")[:1000],
        )

    def _pricing(self, tickets: Optional[list]) -> tuple[list, str]:
        """Turn FourVenues ticket-types into (price_tiers, sale_state).

        Only public ('publica') ticket types count. Rules:
          - no public types                      -> no_a_la_venta
          - every public type sold out           -> agotado
          - all public types start selling later -> no_a_la_venta (próximamente)
          - any available type flagged few-left  -> pocas_entradas
          - otherwise                            -> a_la_venta
        """
        if tickets is None:
            # Unknown (detail fetch failed / not fetched) -> don't invent a state.
            return [], "no_a_la_venta"
        public = [t for t in tickets if isinstance(t, dict) and t.get("type", "publica") != "privada"]
        if not public:
            return [], "no_a_la_venta"

        now = _time.time()
        tiers = []
        any_available = False
        any_few = False
        all_future = True
        for t in public:
            sold = bool(t.get("isSoldOut"))
            few = bool(t.get("areFewLeft"))
            price = t.get("price")
            try:
                price = float(price) if price is not None else 0.0
            except Exception:
                price = 0.0
            d = t.get("dates") or {}
            frm = d.get("from")
            not_yet = bool(frm and float(frm) > now)
            if not not_yet:
                all_future = False
            tiers.append({
                "name": str(t.get("name") or "Entrada")[:60],
                "price": price,
                "sold_out": sold,
            })
            if not sold and not not_yet:
                any_available = True
                if few:
                    any_few = True

        # Sort so the cheapest available tier is first (drives current_price).
        tiers.sort(key=lambda x: (x["sold_out"], x["price"]))

        if all(t["sold_out"] for t in tiers):
            state = "agotado"
        elif all_future:
            state = "no_a_la_venta"
        elif any_few:
            state = "pocas_entradas"
        elif any_available:
            state = "a_la_venta"
        else:
            state = "agotado"
        return tiers, state
