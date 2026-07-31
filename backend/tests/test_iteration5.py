"""Iteration 5 backend tests:
- POST/GET/DELETE /api/stories  (ephemeral 24h, friends-only privacy)
- GET /api/events/discover      (genre-based recommendations + popularity fallback)
"""
import os
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
import requests
from dotenv import dotenv_values

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL"))
assert BASE_URL, "REACT_APP_BACKEND_URL missing"
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "QuienVa2026!"

# 1x1 transparent PNG
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
       b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
       b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


def _hj(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _register(prefix):
    uniq = uuid.uuid4().hex[:8]
    email = f"TEST_{prefix}_{uniq}@test.com"
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": "test1234", "name": f"TEST {prefix} {uniq}",
        "username": f"test_{prefix}_{uniq}", "city": "Palma de Mallorca"})
    assert r.status_code == 200, r.text
    d = r.json()
    d["email"] = email
    return d


def _friend_pair(a, b):
    r1 = requests.post(f"{API}/friends/request", headers=_hj(a["token"]),
                       json={"user_id": b["user"]["user_id"]})
    assert r1.status_code == 200, r1.text
    if r1.json().get("status") == "accepted":
        return
    rr = requests.get(f"{API}/friends/requests", headers=_h(b["token"]))
    req = [x for x in rr.json() if x["user"]["user_id"] == a["user"]["user_id"]][0]
    r2 = requests.post(f"{API}/friends/respond", headers=_hj(b["token"]),
                       json={"request_id": req["request_id"], "accept": True})
    assert r2.status_code == 200, r2.text


def _upload_story(tok, caption="", event_id=None, name="pic.png"):
    data = {"caption": caption}
    if event_id:
        data["event_id"] = event_id
    return requests.post(f"{API}/stories", headers=_h(tok),
                         files={"file": (name, PNG, "image/png")}, data=data)


def _admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _mk_event(tok, name, genre, days_ahead=3):
    d = (date.today() + timedelta(days=days_ahead)).isoformat()
    r = requests.post(f"{API}/admin/events", headers=_hj(tok), json={
        "name": name, "venue": "TEST_Venue", "address": "Carrer TEST 1",
        "date": d, "time": "23:00", "genre": genre, "city": "Palma de Mallorca"})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- STORIES
class TestStories:
    @pytest.fixture(scope="class")
    def actors(self):
        a = _register("sa")   # author
        b = _register("sb")   # accepted friend
        c = _register("sc")   # stranger
        _friend_pair(a, b)
        created_events = []
        admin = _admin_token()
        ev = _mk_event(admin, f"TEST_StoryEvent_{uuid.uuid4().hex[:6]}", "Techno")
        created_events.append(ev["id"])
        yield {"a": a, "b": b, "c": c, "event": ev, "admin": admin}
        for eid in created_events:
            requests.delete(f"{API}/admin/events/{eid}", headers=_h(admin))

    def test_stories_requires_auth(self):
        assert requests.get(f"{API}/stories").status_code in (401, 403)
        assert _upload_story("bogus-token").status_code in (401, 403)

    def test_upload_story_shape_and_ttl(self, actors):
        r = _upload_story(actors["a"]["token"], caption="TEST_caption uno")
        assert r.status_code == 200, r.text
        s = r.json()
        assert "_id" not in s
        assert s["caption"] == "TEST_caption uno"
        assert s["image_url"].startswith("/api/files/")
        assert s["event_id"] is None
        created = datetime.fromisoformat(s["created_at"])
        expires = datetime.fromisoformat(s["expires_at"])
        assert 23.5 < (expires - created).total_seconds() / 3600 < 24.5
        # image publicly served
        img = requests.get(f"{BASE_URL}{s['image_url']}")
        assert img.status_code == 200, img.status_code
        assert img.headers.get("content-type", "").startswith("image/")
        actors["story_id"] = s["id"]

    def test_author_sees_own_story_is_mine(self, actors):
        r = requests.get(f"{API}/stories", headers=_h(actors["a"]["token"]))
        assert r.status_code == 200
        mine = [s for s in r.json() if s["user_id"] == actors["a"]["user"]["user_id"]]
        assert len(mine) >= 1
        s = mine[0]
        assert s["is_mine"] is True
        assert s["author"]["username"] == actors["a"]["user"]["username"]
        assert s["author"]["name"] == actors["a"]["user"]["name"]
        assert "_id" not in s

    def test_accepted_friend_sees_story(self, actors):
        r = requests.get(f"{API}/stories", headers=_h(actors["b"]["token"]))
        assert r.status_code == 200
        found = [s for s in r.json() if s["user_id"] == actors["a"]["user"]["user_id"]]
        assert len(found) >= 1, "accepted friend should see author's story"
        assert found[0]["is_mine"] is False

    def test_non_friend_cannot_see_story(self, actors):
        r = requests.get(f"{API}/stories", headers=_h(actors["c"]["token"]))
        assert r.status_code == 200
        assert r.json() == [], f"stranger must see no stories, got {r.json()}"

    def test_story_tied_to_event_returns_event_name(self, actors):
        r = _upload_story(actors["a"]["token"], caption="con evento",
                          event_id=actors["event"]["id"])
        assert r.status_code == 200, r.text
        sid = r.json()["id"]
        g = requests.get(f"{API}/stories", headers=_h(actors["b"]["token"]))
        s = [x for x in g.json() if x["id"] == sid]
        assert s, "event story not visible to friend"
        assert s[0]["event_name"] == actors["event"]["name"]
        assert s[0]["event_id"] == actors["event"]["id"]

    def test_friend_cannot_delete_others_story(self, actors):
        up = _upload_story(actors["a"]["token"], caption="no borrar")
        sid = up.json()["id"]
        d = requests.delete(f"{API}/stories/{sid}", headers=_h(actors["b"]["token"]))
        assert d.status_code in (200, 403, 404)
        still = requests.get(f"{API}/stories", headers=_h(actors["a"]["token"])).json()
        assert any(s["id"] == sid for s in still), "friend deleted someone else's story!"

    def test_owner_delete_removes_story(self, actors):
        up = _upload_story(actors["a"]["token"], caption="borrable")
        sid = up.json()["id"]
        d = requests.delete(f"{API}/stories/{sid}", headers=_h(actors["a"]["token"]))
        assert d.status_code == 200
        after = requests.get(f"{API}/stories", headers=_h(actors["a"]["token"])).json()
        assert not any(s["id"] == sid for s in after)

    def test_pending_friend_request_does_not_grant_access(self, actors):
        d = _register("sd")
        requests.post(f"{API}/friends/request", headers=_hj(d["token"]),
                      json={"user_id": actors["a"]["user"]["user_id"]})
        r = requests.get(f"{API}/stories", headers=_h(d["token"]))
        assert r.status_code == 200
        assert not any(s["user_id"] == actors["a"]["user"]["user_id"] for s in r.json()), \
            "pending (not accepted) friend must not see stories"

    def test_older_than_24h_filtered_out(self, actors):
        """Insert a >24h-old story straight into Mongo and verify GET filters it."""
        from pymongo import MongoClient
        env = dotenv_values("/app/backend/.env")
        cli = MongoClient(env["MONGO_URL"])
        db = cli[env["DB_NAME"]]
        old_id = str(uuid.uuid4())
        old = datetime.now(timezone.utc) - timedelta(hours=30)
        db.stories.insert_one({
            "id": old_id, "user_id": actors["a"]["user"]["user_id"],
            "image_url": "/api/files/none.png", "caption": "TEST_old", "event_id": None,
            "created_at": old.isoformat(),
            "expires_at": (old + timedelta(hours=24)).isoformat()})
        try:
            r = requests.get(f"{API}/stories", headers=_h(actors["a"]["token"]))
            assert r.status_code == 200
            assert not any(s["id"] == old_id for s in r.json()), "expired story returned"
        finally:
            db.stories.delete_one({"id": old_id})
            cli.close()

    def test_cleanup_author_stories(self, actors):
        tok = actors["a"]["token"]
        for s in requests.get(f"{API}/stories", headers=_h(tok)).json():
            if s["is_mine"]:
                requests.delete(f"{API}/stories/{s['id']}", headers=_h(tok))
        assert requests.get(f"{API}/stories", headers=_h(tok)).json() == []


# ---------------------------------------------------------------- DISCOVER
class TestDiscover:
    @pytest.fixture(scope="class")
    def ctx(self):
        admin = _admin_token()
        tag = uuid.uuid4().hex[:6]
        evs = {
            "regA": _mk_event(admin, f"TEST_Reg_A_{tag}", "Reggaeton", 2),
            "regB": _mk_event(admin, f"TEST_Reg_B_{tag}", "Reggaeton", 4),
            "regC": _mk_event(admin, f"TEST_Reg_C_{tag}", "Reggaeton", 6),
            "tech": _mk_event(admin, f"TEST_Tech_{tag}", "Techno", 3),
        }
        u = _register("dsc")
        yield {"admin": admin, "evs": evs, "u": u}
        for e in evs.values():
            requests.delete(f"{API}/admin/events/{e['id']}", headers=_h(admin))

    def test_discover_requires_auth(self):
        assert requests.get(f"{API}/events/discover").status_code in (401, 403)

    def test_discover_not_shadowed_by_event_id_route(self, ctx):
        r = requests.get(f"{API}/events/discover", headers=_h(ctx["u"]["token"]))
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)

    def test_new_user_gets_nonempty_popular_fallback(self, ctx):
        r = requests.get(f"{API}/events/discover", headers=_h(ctx["u"]["token"]))
        data = r.json()
        assert len(data) > 0, "brand-new user got empty discover list"
        pops = [d["total_going"] + d["total_interested"] for d in data]
        assert pops == sorted(pops, reverse=True), f"fallback not sorted by popularity: {pops}"
        for d in data:
            assert d["date"] >= date.today().isoformat()

    def test_genre_prioritised_and_interacted_excluded(self, ctx):
        tok = ctx["u"]["token"]
        # engage with a Reggaeton event
        ri = requests.post(f"{API}/events/{ctx['evs']['regA']['id']}/interest",
                           headers=_hj(tok), json={"status": "me_interesa"})
        assert ri.status_code == 200, ri.text
        r = requests.get(f"{API}/events/discover", headers=_h(tok))
        assert r.status_code == 200
        data = r.json()
        ids = [d["id"] for d in data]
        assert ctx["evs"]["regA"]["id"] not in ids, "interacted event must be excluded"
        assert data, "discover empty after interaction"
        assert data[0]["genre"] == "Reggaeton", f"top rec genre={data[0]['genre']}"
        assert ctx["evs"]["regB"]["id"] in ids and ctx["evs"]["regC"]["id"] in ids
        # Reggaeton items must come before non-Reggaeton items
        first_other = next((i for i, d in enumerate(data) if d["genre"] != "Reggaeton"), len(data))
        assert all(d["genre"] == "Reggaeton" for d in data[:first_other])
        assert all(d["genre"] != "Reggaeton" for d in data[first_other:])

    def test_discover_items_have_event_detail_shape(self, ctx):
        r = requests.get(f"{API}/events/discover", headers=_h(ctx["u"]["token"]))
        d = r.json()[0]
        for k in ("id", "name", "venue", "date", "time", "genre", "my_status",
                  "total_going", "total_interested", "friends_going"):
            assert k in d, f"missing key {k}"
        assert "_id" not in d
