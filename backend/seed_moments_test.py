import asyncio, uuid
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
import bcrypt

DB = "quienva_local"
CITY = "Palma de Mallorca"
IMGS = [
    "https://images.unsplash.com/photo-1598278448430-dd1e593c47fa?fm=jpg&q=85&w=800",
    "https://images.unsplash.com/photo-1708449530105-ea7d453a6f89?fm=jpg&q=85&w=800",
    "https://images.unsplash.com/photo-1616189221668-386d14f76678?fm=jpg&q=85&w=800",
    "https://images.unsplash.com/photo-1713450605366-6a8f724c5411?fm=jpg&q=85&w=800",
]


def h(p):
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()


async def main():
    db = AsyncIOMotorClient("mongodb://localhost:27017")[DB]
    admin = await db.users.find_one({"email": "admin@quienva.app"})
    admin_id = admin["user_id"]

    users = [
        {"email": "lucia@test.com", "username": "lucia", "name": "Lucía", "priv": "amigos"},
        {"email": "marc@test.com", "username": "marc", "name": "Marc", "priv": "amigos"},
        {"email": "sara@test.com", "username": "sara", "name": "Sara", "priv": "publico"},
        {"email": "tourist@test.com", "username": "tourist", "name": "Tom (guiri)", "priv": "publico"},
    ]
    ids = {}
    for u in users:
        existing = await db.users.find_one({"email": u["email"]})
        if existing:
            ids[u["username"]] = existing["user_id"]
            await db.users.update_one({"user_id": existing["user_id"]}, {"$set": {"moment_privacy": u["priv"]}})
            continue
        uid = f"user_{uuid.uuid4().hex[:12]}"
        ids[u["username"]] = uid
        await db.users.insert_one({
            "user_id": uid, "email": u["email"], "username": u["username"], "name": u["name"],
            "picture": "", "city": CITY, "role": "user", "auth_provider": "email",
            "password_hash": h("test123"), "birthdate": "2000-01-01",
            "attendance_privacy": "amigos", "moment_privacy": u["priv"], "blocked_users": [],
            "city_change_alerts": True, "created_at": datetime.now(timezone.utc).isoformat(),
        })

    # Friendships: admin <-> lucia, admin <-> marc (accepted). sara/tourist NOT friends (public only).
    for uname in ("lucia", "marc"):
        fid = ids[uname]
        exists = await db.friendships.find_one({
            "status": "accepted",
            "$or": [{"requester_id": admin_id, "addressee_id": fid},
                    {"requester_id": fid, "addressee_id": admin_id}],
        })
        if not exists:
            await db.friendships.insert_one({
                "id": str(uuid.uuid4()), "requester_id": admin_id, "addressee_id": fid,
                "status": "accepted", "created_at": datetime.now(timezone.utc).isoformat(),
            })

    # Captures: for each seeded user, 2 captures with recent timestamps.
    ev = await db.events.find_one({"city": {"$regex": "Mallorca|Palma", "$options": "i"}}, {"_id": 0, "id": 1, "name": 1})
    await db.captures.delete_many({"user_id": {"$in": list(ids.values())}})
    now = datetime.now(timezone.utc)
    i = 0
    for uname, uid in ids.items():
        for k in range(2):
            i += 1
            await db.captures.insert_one({
                "id": str(uuid.uuid4()), "event_id": (ev["id"] if ev and k == 0 else None),
                "user_id": uid, "image_url": IMGS[i % len(IMGS)], "on_time": True,
                "seconds_late": 0, "created_at": (now - timedelta(minutes=i * 7)).isoformat(),
            })

    print("seeded users:", ids)
    print("friends of admin (lucia, marc). public momentos: sara, tourist")
    print("captures:", await db.captures.count_documents({"user_id": {"$in": list(ids.values())}}))
    print("event tagged:", ev)


asyncio.run(main())
