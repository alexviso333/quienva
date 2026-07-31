"""Seeds UI test data for iteration 4 frontend Playwright run.
Creates users A (subject) and B (friend), an upcoming event with B going,
a past event both attended, an event dated today that A marks me_interesa,
and triggers reminders so A has an interested_reminder notification.
Prints a JSON blob for the Playwright script.
"""
import json
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

BASE_URL = ""
with open("/app/frontend/.env") as f:
    for line in f:
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.strip().split("=", 1)[1].rstrip("/")
API = f"{BASE_URL}/api"
PALMA_TZ = ZoneInfo("Europe/Madrid")
ADMIN = ("admin@quienva.app", "QuienVa2026!")


def h(t):
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}


def reg(email, username, name):
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": "test1234", "name": name,
        "username": username, "city": "Palma de Mallorca"})
    r.raise_for_status()
    d = r.json()
    d["email"] = email
    return d


def login(e, p):
    r = requests.post(f"{API}/auth/login", json={"email": e, "password": p})
    r.raise_for_status()
    return r.json()


def befriend(a, b):
    r = requests.post(f"{API}/friends/request", headers=h(a["token"]),
                      json={"user_id": b["user"]["user_id"]})
    r.raise_for_status()
    if r.json().get("status") == "accepted":
        return
    reqs = requests.get(f"{API}/friends/requests", headers=h(b["token"])).json()
    rq = [x for x in reqs if x["user"]["user_id"] == a["user"]["user_id"]][0]
    requests.post(f"{API}/friends/respond", headers=h(b["token"]),
                  json={"request_id": rq["request_id"], "accept": True}).raise_for_status()


def mk(admin, name, d, t="23:30", **kw):
    p = {"name": name, "venue": "TEST_Sala Nova", "address": "Carrer de Test 7",
         "date": d, "time": t, "genre": "Techno", "city": "Palma de Mallorca"}
    p.update(kw)
    r = requests.post(f"{API}/admin/events", headers=h(admin), json=p)
    r.raise_for_status()
    return r.json()


def interest(tok, eid, st):
    requests.post(f"{API}/events/{eid}/interest", headers=h(tok), json={"status": st}).raise_for_status()


def main():
    admin = login(*ADMIN)["token"]
    u = uuid.uuid4().hex[:6]
    a = reg(f"uia{u}@test.com", f"uia{u}", "AnaUI")
    b = reg(f"uib{u}@test.com", f"uib{u}", "BrunoUI")
    befriend(a, b)

    today = datetime.now(PALMA_TZ).date()
    up = mk(admin, "TEST_UI Top Finde", (today + timedelta(days=2)).isoformat(),
            has_commission=True, commission_url="https://tickets.example.com/ui")
    past = mk(admin, "TEST_UI Recuerdo", (today - timedelta(days=8)).isoformat())
    todayev = mk(admin, "TEST_UI Hoy Interesa", today.isoformat(), t="23:59",
                 more_info_url="https://info.example.com/ui")

    interest(b["token"], up["id"], "voy")
    interest(b["token"], past["id"], "estuve")
    interest(a["token"], past["id"], "estuve")
    interest(a["token"], todayev["id"], "me_interesa")
    # streak for A: mark voy on an event in the current week
    monday = today - timedelta(days=today.weekday())
    weekev = mk(admin, "TEST_UI Semana", monday.isoformat())
    interest(a["token"], weekev["id"], "voy")

    requests.post(f"{API}/admin/trigger-reminders", headers=h(admin)).raise_for_status()

    streak = requests.get(f"{API}/me/streak", headers=h(a["token"])).json()
    top = requests.get(f"{API}/events/top-weekend", headers=h(a["token"])).json()
    print(json.dumps({
        "a_email": a["email"], "b_name": b["user"]["name"], "password": "test1234",
        "upcoming_id": up["id"], "past_id": past["id"], "today_id": todayev["id"],
        "week_id": weekev["id"], "streak": streak,
        "top_id": (top or {}).get("id"), "base_url": BASE_URL,
    }, indent=1))


main()
