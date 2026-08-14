"""Regresión: fix del 'mismo día' de ClubTickets.

ClubTickets quita las fiestas de HOY de nuestro panel de afiliados el mismo día
del evento, aunque siguen a la venta. Antes eso hacía que nuestro scraper perdiera
el enlace de afiliado (?aff=CT226) para las fiestas de hoy. Este test demuestra que
la MEMORIA persistente del panel las resucita y mantiene nuestro enlace.

Ejecutar:  cd /app/backend && set -a && . ./.env && set +a && \
           /root/.venv/bin/python /app/ct_same_day_link_fix_test.py
"""
import asyncio
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, "/app/backend")
import server as S  # noqa: E402
from scrapers.base import ScrapedEvent  # noqa: E402


async def main() -> bool:
    today = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
    now_iso = datetime.now(timezone.utc).isoformat()
    ok = True

    # El panel EN VIVO no trae las fiestas de HOY (así es como falla ClubTickets).
    from scrapers.clubtickets import get_panel_index
    live = await get_panel_index(S.CLUBTICKETS_LINKS_URL)
    live_today = sum(1 for v in live.values() for p in v if p.get("date") == today)
    print(f"[live] fiestas del panel para HOY ({today}): {live_today}")

    # Simula la memoria guardada AYER para las fiestas de HOY.
    samples = [
        ("unvrs-ibiza", "elrow", "elrow ibiza"),
        ("ushuaia-ibiza", "ants", "ANTS"),
        ("hi-ibiza", "black-coffee", "Black Coffee"),
        ("ibiza-rocks", "ibiza-anthems", "Ibiza Anthems with Disco"),
        ("swag", "gloss", "GLOSS"),
        ("club-chinois-ibiza", "the-masquerade", "The Masquerade"),
        ("eden-ibiza", "taconeo", "Taconeo Week 2"),
        ("es-paradis", "fiesta-del-agua", "Fiesta del Agua"),
        ("lio", "kodo", "Kodo"),
        ("528-ibiza", "andy-manumission", "Andy Manumission"),
    ]
    await S.db.ct_panel_memory.delete_many({"date": today})
    for ct_slug, eslug, name in samples:
        url = f"https://www.clubtickets.com/clubbing/{ct_slug}/{eslug}/{today}?aff=CT226"
        await S.db.ct_panel_memory.update_one(
            {"_id": f"{ct_slug}|{eslug}|{today}"},
            {"$set": {"ct_slug": ct_slug, "event_slug": eslug, "date": today,
                      "name": name, "url": url, "last_seen": now_iso,
                      "first_seen": now_iso}}, upsert=True)
    S._CT_MEM_LAST_WRITE = 9e18  # no reescribir memoria durante el test

    # 1) _ct_affiliate_url_for devuelve nuestro ?aff para cada fiesta de HOY.
    for ct_slug, eslug, name in samples:
        got = await S._ct_affiliate_url_for(ct_slug, today, name)
        good = bool(got) and "aff=CT226" in (got or "")
        print(f"  [{'OK' if good else 'FAIL'}] {ct_slug} '{name}' -> {got}")
        ok = ok and good

    # 2) Guardarraíl: fecha futura inexistente NO inventa enlace.
    none_res = await S._ct_affiliate_url_for("unvrs-ibiza", "2099-01-01", "No existe")
    print(f"  [{'OK' if none_res is None else 'FAIL'}] futura inexistente -> {none_res}")
    ok = ok and none_res is None

    # 3) Flujo real: evento de HOY scrapeado por OTRA fuente (Xceed) sin ?aff
    #    recibe nuestro enlace de afiliado al pasar por _apply_scraped_event.
    await S.db.events.delete_many({"external_id": "regr-xceed-andy"})
    se = ScrapedEvent(external_id="regr-xceed-andy", name="Andy Manumission",
                      venue="528 Ibiza", date=today, time="23:00",
                      ticket_url="https://xceed.me/es/ibiza/event/andy-123",
                      sale_state="a_la_venta")
    venue = {"id": "regr-xceed", "name": "Xceed · Ibiza", "city": "Ibiza",
             "adapter_type": "xceed", "last_run_at": now_iso}
    await S._apply_scraped_event(venue, se)
    ev = await S.db.events.find_one({"external_id": "regr-xceed-andy"}, {"_id": 0})
    good = ev and "aff=CT226" in (ev.get("commission_url") or "")
    print(f"  [{'OK' if good else 'FAIL'}] evento Xceed HOY -> {ev.get('commission_url') if ev else None}")
    ok = ok and bool(good)

    # limpieza
    await S.db.events.delete_many({"external_id": "regr-xceed-andy"})
    await S.db.ct_panel_memory.delete_many({"date": today})

    print("\nRESULTADO:", "TODO OK" if ok else "FALLOS")
    return ok


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
