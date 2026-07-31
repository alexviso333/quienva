"""Seed data for iteration-6 UI tests.
- marta (main UI user), bob (accepted friend), stranger (no relation)
- marta: 1 fresh story + 1 backdated (40h) story  -> archive must show both
- bob: 1 fresh story -> marta can open it and react
- bob marks 'voy' on the first demo event -> gets event_message notification when marta chats
Prints JSON summary.
"""
import json
import os
from datetime import datetime, timedelta, timezone

import requests
from dotenv import dotenv_values

FENV = dotenv_values("/app/frontend/.env")
BENV = dotenv_values("/app/backend/.env")
API = (os.environ.get("REACT_APP_BACKEND_URL") or FENV["REACT_APP_BACKEND_URL"]).rstrip("/") + "/api"
PWD = "test1234"
def _png():
    """Real 300x450 colourful PNG so the viewer/thumbnails render something visible."""
    import io
    from PIL import Image
    img = Image.new("RGB", (300, 450))
    px = img.load()
    for y in range(450):
        for x in range(300):
            px[x, y] = (255 - int(x * 0.5), int(y * 0.5), 180)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


PNG = _png()


def h(t, j=False):
    d = {"Authorization": f"Bearer {t}"}
    if j:
        d["Content-Type"] = "application/json"
    return d


def ensure(email, name, username):
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": PWD, "name": name,
        "username": username, "city": "Palma de Mallorca"})
    if r.status_code == 200:
        return r.json()
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": PWD})
    r.raise_for_status()
    return r.json()


def befriend(a, b):
    r = requests.post(f"{API}/friends/request", headers=h(a["token"], True),
                      json={"user_id": b["user"]["user_id"]})
    if r.status_code != 200 or r.json().get("status") == "accepted":
        return
    rr = requests.get(f"{API}/friends/requests", headers=h(b["token"])).json()
    m = [x for x in rr if x["user"]["user_id"] == a["user"]["user_id"]]
    if m:
        requests.post(f"{API}/friends/respond", headers=h(b["token"], True),
                      json={"request_id": m[0]["request_id"], "accept": True})


def clear_stories(u):
    from pymongo import MongoClient
    cli = MongoClient(BENV["MONGO_URL"])
    db = cli[BENV["DB_NAME"]]
    ids = [s["id"] for s in db.stories.find({"user_id": u["user"]["user_id"]}, {"id": 1})]
    db.stories.delete_many({"user_id": u["user"]["user_id"]})
    db.story_reactions.delete_many({"story_id": {"$in": ids}})
    db.notifications.delete_many({"user_id": u["user"]["user_id"],
                                  "type": {"$in": ["story_reaction", "event_message"]}})
    cli.close()


def upload(u, caption, event_id=None):
    data = {"caption": caption}
    if event_id:
        data["event_id"] = event_id
    r = requests.post(f"{API}/stories", headers=h(u["token"]),
                      files={"file": ("img.png", PNG, "image/png")}, data=data)
    r.raise_for_status()
    return r.json()


marta = ensure("marta@test.com", "Marta Ruiz", "marta")
bob = ensure("bob@test.com", "Bob Costa", "bob")
stranger = ensure("stranger@test.com", "Stran Ger", "stranger")
befriend(marta, bob)
for u in (marta, bob, stranger):
    clear_stories(u)

s_new = upload(marta, "Marta historia de hoy")
s_old = upload(marta, "Marta historia antigua")
bob_story = upload(bob, "Bob en la fiesta")

from pymongo import MongoClient  # noqa: E402
cli = MongoClient(BENV["MONGO_URL"])
db = cli[BENV["DB_NAME"]]
old = datetime.now(timezone.utc) - timedelta(hours=40)
db.stories.update_one({"id": s_old["id"]}, {"$set": {
    "created_at": old.isoformat(),
    "expires_at": (old + timedelta(hours=24)).isoformat()}})
cli.close()

events = requests.get(f"{API}/events", headers=h(marta["token"])).json()
ev = events[0]
requests.post(f"{API}/events/{ev['id']}/interest", headers=h(bob["token"], True),
              json={"status": "voy"})

print(json.dumps({
    "marta_story_fresh": s_new["id"], "marta_story_old": s_old["id"],
    "bob_story": bob_story["id"], "event_id": ev["id"], "event_name": ev["name"],
    "events_count": len(events),
}, indent=2, ensure_ascii=False))
