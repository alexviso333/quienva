import asyncio, os, uuid
from datetime import datetime, timezone, timedelta, date
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent / "backend" / ".env")
client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]

EVENTS = [
    {"name": "Techno Underground", "venue": "Sala Focus", "address": "C/ Bartomeu Rosselló, Palma",
     "time": "23:59", "genre": "Techno", "offset": 1,
     "image_url": "https://images.unsplash.com/photo-1470225620780-dba8ba36b745",
     "has_commission": True, "commission_url": "https://fourvenues.com/", "sale_state": "a_la_venta",
     "price_tiers": [{"name": "General", "price": 15, "sold_out": False}]},
    {"name": "Reggaeton Party", "venue": "Tito's Palma", "address": "Passeig Marítim, Palma",
     "time": "00:30", "genre": "Reggaeton", "offset": 2,
     "image_url": "https://images.unsplash.com/photo-1517983079452-bbaa6a081a6b?crop=entropy&cs=srgb&fm=jpg&q=85",
     "has_commission": True, "commission_url": "https://fourvenues.com/", "sale_state": "pocas_entradas",
     "price_tiers": [{"name": "Anticipada", "price": 12, "sold_out": False}]},
    {"name": "Sunset Sessions", "venue": "Purobeach", "address": "Cala Estància, Palma",
     "time": "19:00", "genre": "House", "offset": 3,
     "image_url": "https://images.unsplash.com/photo-1563784462029-e9cc28281850?crop=entropy&cs=srgb&fm=jpg&q=85",
     "has_commission": False, "commission_url": "", "more_info_url": "https://www.instagram.com/purobeach/",
     "sale_state": "no_a_la_venta", "price_tiers": []},
]

async def main():
    today = date.today()
    for e in EVENTS:
        d = (today + timedelta(days=e.pop("offset"))).isoformat()
        doc = {
            "id": str(uuid.uuid4()),
            "name": e["name"], "venue": e["venue"], "address": e.get("address", ""),
            "date": d, "time": e.get("time", ""), "image_url": e.get("image_url", ""),
            "genre": e.get("genre", ""), "city": "Palma de Mallorca",
            "has_commission": e.get("has_commission", False),
            "commission_url": e.get("commission_url", ""),
            "more_info_url": e.get("more_info_url", ""),
            "featured": False,
            "price_tiers": e.get("price_tiers", []),
            "sale_state": e.get("sale_state", "no_a_la_venta"),
            "currency": "EUR",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.events.update_one({"name": doc["name"], "venue": doc["venue"]}, {"$set": doc}, upsert=True)
        print("seeded:", doc["name"], doc["date"])
    print("total events:", await db.events.count_documents({}))

asyncio.run(main())
