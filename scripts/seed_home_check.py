import asyncio, os, uuid
from datetime import datetime, timezone, date, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent / "backend" / ".env")
client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]

CITIES = {
    "Madrid": "Madrid",
    "Barcelona": "Barcelona",
    "Ibiza": "Ibiza",
    "Palma de Mallorca": "Palma de Mallorca",
    "Marbella": "Marbella",
}
IMG = "https://images.unsplash.com/photo-1470225620780-dba8ba36b745"


async def main():
    await db.events.delete_many({"_seedcheck": True})
    today = date.today()
    n = 0
    for city_val in CITIES.values():
        for i in range(12):
            d = (today + timedelta(days=i + 1)).isoformat()
            doc = {
                "id": str(uuid.uuid4()),
                "name": f"Fiesta {city_val} #{i+1}",
                "venue": f"Club {city_val} {(i % 4) + 1}",
                "address": f"Calle {i}, {city_val}",
                "date": d, "time": "23:59", "image_url": IMG,
                "genre": "Techno", "city": city_val,
                "has_commission": False, "commission_url": "", "more_info_url": "",
                "featured": False, "price_tiers": [{"name": "General", "price": 15, "sold_out": False}],
                "sale_state": "a_la_venta", "currency": "EUR",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "_seedcheck": True,
            }
            await db.events.insert_one(doc)
            n += 1
    print("seeded", n, "events; total:", await db.events.count_documents({}))

asyncio.run(main())
