"""Seed a realistic dataset into the LOCAL test Mongo to verify the
/events/top-weekend performance fix (N+1 removal).

Creates:
  - user "me" (city Madrid) + a session token (printed at the end)
  - K friends, all accepted friendships with "me"
  - N upcoming events in Madrid within the weekend window
  - interests: friends marking "voy" on events; one event is the clear winner

Run:  python3 scripts/seed_perf_test.py
"""
import os
import sys
from datetime import datetime, date, timedelta, timezone

from pymongo import MongoClient

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "quienva_local_test")

N_EVENTS = 160          # events in the city within the weekend window
K_FRIENDS = 40          # number of friends
WINNER_IDX = 42         # event index that will have the most friends going
SESSION_TOKEN = "perftest-session-token-me"
MY_UID = "me-uid"
CITY = "Madrid"

client = MongoClient(MONGO_URL)
db = client[DB_NAME]

# Clean slate for the collections we touch.
for col in ["users", "friendships", "events", "interests", "sessions", "tickets"]:
    db[col].delete_many({})

today = datetime.now(timezone.utc).date()

# --- me + friends ---
db.users.insert_one({
    "user_id": MY_UID, "email": "me@test.dev", "name": "Yo",
    "username": "yo", "city": CITY, "role": "user",
})
friend_ids = []
for i in range(K_FRIENDS):
    fid = f"friend-{i}"
    friend_ids.append(fid)
    db.users.insert_one({
        "user_id": fid, "email": f"{fid}@test.dev", "name": f"Amigo {i}",
        "username": f"amigo{i}", "city": CITY, "role": "user",
        "picture": "",
    })
    db.friendships.insert_one({
        "id": f"fr-{i}", "requester_id": MY_UID, "addressee_id": fid,
        "status": "accepted",
    })

# --- events within the weekend window (today .. today+6) ---
events = []
for i in range(N_EVENTS):
    d = today + timedelta(days=i % 7)
    ev = {
        "id": f"ev-{i}",
        "name": f"Fiesta {i}",
        "venue": f"Sala {i}",
        "address": "Calle Falsa 123",
        "date": d.isoformat(),
        "time": "23:00",
        "image_url": "",
        "genre": "techno",
        "city": CITY,
        "price_tiers": [],
        "sale_state": "no_a_la_venta",
        "currency": "EUR",
        "featured": False,
    }
    events.append(ev)
db.events.insert_many(events)

# --- interests: spread some, but make WINNER_IDX have ALL friends going ---
interests = []
for i, ev in enumerate(events):
    if i == WINNER_IDX:
        going = friend_ids                      # everyone goes -> winner
    else:
        going = friend_ids[: (i % 5)]           # 0..4 friends going
    for fid in going:
        interests.append({
            "event_id": ev["id"], "user_id": fid,
            "status": "voy", "privacy": "todos",
        })
if interests:
    db.interests.insert_many(interests)

# --- session for "me" ---
db.sessions.insert_one({
    "session_token": SESSION_TOKEN,
    "user_id": MY_UID,
    "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
    "created_at": datetime.now(timezone.utc).isoformat(),
})

print("SEED DONE")
print(f"  db={DB_NAME} events={N_EVENTS} friends={K_FRIENDS} interests={len(interests)}")
print(f"  expected winner event id = ev-{WINNER_IDX} (name 'Fiesta {WINNER_IDX}')")
print(f"  SESSION_TOKEN={SESSION_TOKEN}")
print(f"  Use header:  Authorization: Bearer {SESSION_TOKEN}")
