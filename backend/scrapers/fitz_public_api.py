"""Scraper for clubs exposing a public /api/fourvenues JSON endpoint.
Currently confirmed working: fitzmallorca.com/api/fourvenues."""
from __future__ import annotations
import httpx
import logging
from typing import List
from .base import (
    Scraper, ScrapedEvent, parse_price_string, parse_iso_date, parse_time,
)

logger = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


class FitzPublicAPIScraper(Scraper):
    adapter_type = "fourvenues_public_api"

    def _endpoint(self) -> str:
        base = self.url
        if base.endswith("/api/fourvenues"):
            return base
        return f"{base}/api/fourvenues"

    async def fetch(self) -> List[ScrapedEvent]:
        endpoint = self._endpoint()
        async with httpx.AsyncClient(timeout=12, headers={"User-Agent": UA}) as client:
            r = await client.get(endpoint)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list):
            # Some sites wrap in {data: [...]}
            data = data.get("data", data.get("events", []))
        out: List[ScrapedEvent] = []
        for it in data:
            try:
                ev = self._parse(it)
                if ev:
                    out.append(ev)
            except Exception as e:
                logger.warning(f"[fitz] parse item failed: {e}")
                continue
        return out

    def _parse(self, it: dict) -> ScrapedEvent | None:
        # Common Fourvenues "public" schema (as seen on fitzmallorca.com)
        ev_id = str(it.get("id") or it.get("slug") or "")
        if not ev_id:
            return None
        slug = str(it.get("slug") or it.get("artistSlug") or "")
        name = str(it.get("title") or it.get("name") or it.get("artist") or "").strip()
        if not name:
            return None
        date_iso = parse_iso_date(it.get("date") or it.get("startDate") or "")
        if not date_iso:
            return None
        time_str = parse_time(it.get("time") or "")
        img = str(it.get("image") or it.get("artwork") or it.get("imageUrl") or "")
        ticket_price = parse_price_string(
            it.get("ticketPrice") or it.get("price") or it.get("totalPrice") or None
        )
        vip_from = parse_price_string(it.get("vipFrom") or it.get("vipPrice") or None)
        sold_out = bool(it.get("soldOut") or it.get("ticketsSoldOut") or it.get("isSoldOut"))
        ticket_url = str(it.get("ticketUrl") or it.get("link") or "")
        tiers = []
        if ticket_price is not None:
            tiers.append({"name": "General", "price": float(ticket_price), "sold_out": sold_out})
        if vip_from is not None:
            tiers.append({"name": "VIP", "price": float(vip_from), "sold_out": bool(it.get("vipSoldOut"))})
        # Determine overall sale state
        if tiers and all(t["sold_out"] for t in tiers):
            state = "agotado"
        elif tiers:
            state = "a_la_venta"
        else:
            state = "no_a_la_venta"
        return ScrapedEvent(
            external_id=ev_id,
            name=name,
            venue=self.venue_name or "",
            date=date_iso,
            time=time_str,
            image_url=img,
            genre=str(it.get("category") or it.get("genre") or ""),
            ticket_url=ticket_url,
            price_tiers=tiers,
            sale_state=state,
            description=str(it.get("description") or "")[:1000],
        )
