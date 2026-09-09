"""Seed a few events that MATCH the real quienva affiliate feed (Sevilla) plus one
that does NOT, so the backend testing agent can verify is_affiliate / commission_url
consistency via the API. Idempotent-ish (upserts by id)."""
import asyncio, os, sys, uuid
sys.path.insert(0, "/app/backend")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "quienva")
import server


async def main():
    n = await server.refresh_affiliate_events()
    print("affiliate map:", n, "fresh:", server._affiliate_map_is_fresh())
    # Pick real carried keys whose venue looks like a Sevilla club.
    sev_terms = ("rosso", "baku", "bak", "libano", "líbano", "roller", "kaotica", "granuja")
    picked = []
    for (vnorm, d, nnorm), code in server._AFFILIATE_MAP.items():
        if any(t in vnorm for t in sev_terms):
            picked.append((vnorm, d, nnorm, code))
        if len(picked) >= 4:
            break
    print("picked carried Sevilla keys:", len(picked))
    inserted = []
    for (vnorm, d, nnorm, code) in picked:
        eid = "seed_" + code
        doc = {
            "id": eid,
            # store readable-ish names; matching re-normalizes so norm form is enough
            "name": nnorm.upper(),
            "venue": vnorm.upper(),
            "date": d,
            "time": "23:59",
            "city": "Sevilla",
            "genre": "",
            "image_url": "",
            "has_commission": True,
            # club's OWN direct link (must get rewritten to quienva by the server)
            "commission_url": f"https://site.fourvenues.com/es/someclub/events/{code}CLUB",
            "sale_state": "a_la_venta",
            "price_tiers": [{"name": "Entrada", "price": 15.0, "sold_out": False}],
            "source": "seed",
        }
        await server.db.events.update_one({"id": eid}, {"$set": doc}, upsert=True)
        inserted.append(eid)
    # One NON-carried Sevilla event (fake club we don't carry) -> must keep direct link.
    fake = {
        "id": "seed_notcarried",
        "name": "FIESTA QUE NO LLEVAMOS 2099",
        "venue": "CLUB DESCONOCIDO XYZ",
        "date": next(iter(server._AFFILIATE_MAP))[1] if server._AFFILIATE_MAP else "2026-09-20",
        "time": "23:59", "city": "Sevilla", "genre": "",
        "image_url": "", "has_commission": True,
        "commission_url": "https://site.fourvenues.com/es/club-desconocido/events/ZZZZ",
        "sale_state": "a_la_venta",
        "price_tiers": [{"name": "Entrada", "price": 10.0, "sold_out": False}],
        "source": "seed",
    }
    await server.db.events.update_one({"id": "seed_notcarried"}, {"$set": fake}, upsert=True)
    print("inserted carried:", inserted, "+ 1 non-carried")

    # Show what the server WOULD serve for each (sanity)
    for eid in inserted + ["seed_notcarried"]:
        ev = await server.db.events.find_one({"id": eid}, {"_id": 0})
        print(" ", eid, "->", server._commission_url_for(ev),
              "| badge=", server._served_link_is_ours(ev))

asyncio.run(main())
