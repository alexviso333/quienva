"""Seed data for iteration-5 UI tests: marta (author+viewer), bob (accepted friend),
stranger (no relation). Bob uploads a story so marta sees a friend bubble.
Prints JSON with emails/passwords and the seeded event id."""
import json
import os
import uuid
from datetime import date, timedelta

import requests
from dotenv import dotenv_values

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/")
API = f"{BASE_URL}/api"
PWD = "test1234"
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
       b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
       b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")


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


marta = ensure("marta@test.com", "Marta Ruiz", "marta")
bob = ensure("bob@test.com", "Bob Costa", "bob")
stranger = ensure("stranger@test.com", "Stran Ger", "stranger")
befriend(marta, bob)

admin = requests.post(f"{API}/auth/login", json={
    "email": "admin@quienva.app", "password": "QuienVa2026!"}).json()
tag = uuid.uuid4().hex[:5]
ev = requests.post(f"{API}/admin/events", headers=h(admin["token"], True), json={
    "name": f"UI5 Reggaeton Night {tag}", "venue": "Sala UI5", "address": "Carrer UI 5",
    "date": (date.today() + timedelta(days=3)).isoformat(), "time": "23:30",
    "genre": "Reggaeton", "city": "Palma de Mallorca"}).json()

# clear old stories then add one from bob (visible to marta)
for s in requests.get(f"{API}/stories", headers=h(bob["token"])).json():
    if s["is_mine"]:
        requests.delete(f"{API}/stories/{s['id']}", headers=h(bob["token"]))
for s in requests.get(f"{API}/stories", headers=h(marta["token"])).json():
    if s["is_mine"]:
        requests.delete(f"{API}/stories/{s['id']}", headers=h(marta["token"]))

r = requests.post(f"{API}/stories", headers=h(bob["token"]),
                  files={"file": ("bob.png", PNG, "image/png")},
                  data={"caption": "Que noche en Palma", "event_id": ev["id"]})
print(json.dumps({
    "marta": marta["user"]["username"], "bob": bob["user"]["username"],
    "stranger": stranger["user"]["username"], "event_id": ev["id"],
    "event_name": ev["name"], "bob_story": r.status_code, "story": r.json(),
}, indent=2, ensure_ascii=False))
