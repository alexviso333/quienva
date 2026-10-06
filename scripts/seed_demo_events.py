import os, uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pymongo import MongoClient

mongo = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
db = mongo[os.environ.get("DB_NAME", "quienva")]

today = datetime.now(ZoneInfo("Europe/Madrid")).date()
imgs = [
    "https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=900&q=80",
    "https://images.unsplash.com/photo-1540039155733-5bb30b53aa14?w=900&q=80",
    "https://images.unsplash.com/photo-1566737236500-c8ac43014a67?w=900&q=80",
]
venues = [("Fitz Madrid", "Fitz", 0, True, 15), ("LuLa Club", "LuLa", 1, True, 12), ("Tiffany's", "Tiffany's Night", 2, False, None)]

db.events.delete_many({"_demo": True})
for i, (venue, name, dd, comm, price) in enumerate(venues):
    d = (today + timedelta(days=dd)).isoformat()
    db.events.insert_one({
        "id": str(uuid.uuid4()),
        "_demo": True,
        "city": "Madrid",
        "name": name,
        "venue": venue,
        "address": f"Calle Demo {i+1}, Madrid",
        "date": d,
        "time": "23:30",
        "genre": "reggaeton" if i % 2 else "techno",
        "image_url": imgs[i % len(imgs)],
        "current_price": price,
        "currency": "EUR",
        "sale_state": "a_la_venta" if comm else "no_a_la_venta",
        "has_commission": comm,
        "commission_url": "https://www.fourvenues.com/demo" if comm else "",
        "source": "demo",
    })
print("Seeded", db.events.count_documents({"_demo": True}), "events in Madrid")
