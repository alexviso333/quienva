import asyncio, os, uuid
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from motor.motor_asyncio import AsyncIOMotorClient

MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB = os.environ.get("DB_NAME", "quienva")


async def main():
    db = AsyncIOMotorClient(MONGO)[DB]
    today = datetime.now(ZoneInfo("Europe/Madrid")).date()
    specs = [
        ("Tuesdays at Tiffany's", "Tiffany's", today - timedelta(days=1), "23:30"),
        ("Perreo Intenso", "Chango", today - timedelta(days=2), "00:30"),
        ("Techno Night", "Fitz", today + timedelta(days=2), "23:00"),
        ("Reggaeton Party", "LuLa Club", today + timedelta(days=3), "23:59"),
        ("House Session", "Perro Negro", today + timedelta(days=5), "23:30"),
    ]
    ids = []
    for name, venue, d, t in specs:
        eid = str(uuid.uuid4())
        ids.append((eid, name, d.isoformat()))
        await db.events.update_one(
            {"name": name, "date": d.isoformat()},
            {"$setOnInsert": {
                "id": eid, "name": name, "venue": venue, "address": "Madrid",
                "date": d.isoformat(), "time": t, "city": "Madrid", "genre": "Reggaeton",
                "image_url": "", "created_at": datetime.now(timezone.utc).isoformat(),
                "sale_state": "a_la_venta", "current_price": 15,
            }}, upsert=True)
    # test user
    u = await db.users.find_one({"email": "test@quienva.app"})
    if not u:
        print("No test user yet — register it via the API first")
    else:
        uid = u["user_id"]
        for eid, name, d in ids[:2]:
            ev = await db.events.find_one({"name": name, "date": d}, {"_id": 0, "id": 1})
            await db.interests.update_one(
                {"user_id": uid, "event_id": ev["id"]},
                {"$set": {"status": "voy", "privacy": "amigos"},
                 "$setOnInsert": {"id": str(uuid.uuid4()),
                                  "created_at": datetime.now(timezone.utc).isoformat()},
                 "$unset": {"attendance_confirmed": "", "attendance_answered_at": ""}},
                upsert=True)
        print("test user interests seeded (2 past 'voy')")
    print("events:", await db.events.count_documents({}))


asyncio.run(main())
