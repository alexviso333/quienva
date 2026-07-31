"""Iteration 6 backend tests:
- GET  /api/stories/archive            (own stories incl. expired, newest-first, reactions attached)
- POST /api/stories/{id}/react         (friend/owner only, notification for owner)
- GET/POST /api/events/{id}/messages   (event chat + notifications to voy/me_interesa)
- POST /api/admin/trigger-weekend-recap (weekend recap notification)
- GET  /api/events                     (data refresh: 6 upcoming demo events, no TEST/UI artifacts)
"""
import os
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
import requests
from dotenv import dotenv_values

ENV = dotenv_values("/app/backend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL"))
assert BASE_URL, "REACT_APP_BACKEND_URL missing"
API = f"{BASE_URL.rstrip('/')}/api"

ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "QuienVa2026!"

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


def _upload_story(tok, caption="TEST story", event_id=None):
    data = {"caption": caption}
    if event_id:
        data["event_id"] = event_id
    r = requests.post(f"{API}/stories", headers=_h(tok),
                      files={"file": (f"{uuid.uuid4().hex}.png", PNG, "image/png")}, data=data)
    assert r.status_code == 200, r.text
    return r.json()


def _admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _mongo():
    from pymongo import MongoClient
    cli = MongoClient(ENV["MONGO_URL"])
    return cli[ENV["DB_NAME"]], cli


@pytest.fixture(scope="module")
def admin_token():
    return _admin_token()


# ---------------------------------------------------------------------------
# (A) Stories archive
# ---------------------------------------------------------------------------
class TestStoriesArchive:
    def test_archive_requires_auth(self):
        r = requests.get(f"{API}/stories/archive")
        assert r.status_code in (401, 403), r.status_code

    def test_archive_empty_for_new_user(self):
        u = _register("arc_empty")
        r = requests.get(f"{API}/stories/archive", headers=_h(u["token"]))
        assert r.status_code == 200, r.text
        assert r.json() == []

    def test_archive_includes_expired_and_is_newest_first(self):
        u = _register("arc")
        s1 = _upload_story(u["token"], "TEST arc old")
        s2 = _upload_story(u["token"], "TEST arc new")

        # backdate s1 by 40h so it is outside the 24h feed window
        db, cli = _mongo()
        old = (datetime.now(timezone.utc) - timedelta(hours=40)).isoformat()
        db.stories.update_one({"id": s1["id"]},
                              {"$set": {"created_at": old,
                                        "expires_at": (datetime.now(timezone.utc) - timedelta(hours=16)).isoformat()}})
        cli.close()

        feed = requests.get(f"{API}/stories", headers=_h(u["token"]))
        assert feed.status_code == 200
        feed_ids = [s["id"] for s in feed.json()]
        assert s1["id"] not in feed_ids, "expired story must not be in the 24h feed"
        assert s2["id"] in feed_ids

        arc = requests.get(f"{API}/stories/archive", headers=_h(u["token"]))
        assert arc.status_code == 200, arc.text
        items = arc.json()
        ids = [s["id"] for s in items]
        assert s1["id"] in ids and s2["id"] in ids, ids
        # newest first
        created = [s["created_at"] for s in items]
        assert created == sorted(created, reverse=True), created
        for s in items:
            assert s["is_mine"] is True
            assert "_id" not in s
            assert s["image_url"]
            assert s["author"]["name"] == u["user"]["name"]
            assert isinstance(s.get("reactions"), list)

    def test_archive_only_own_stories(self):
        a = _register("arc_a")
        b = _register("arc_b")
        _friend_pair(a, b)
        sb = _upload_story(b["token"], "TEST friend story")
        arc = requests.get(f"{API}/stories/archive", headers=_h(a["token"]))
        assert arc.status_code == 200
        assert sb["id"] not in [s["id"] for s in arc.json()]


# ---------------------------------------------------------------------------
# (B/C) Story reactions
# ---------------------------------------------------------------------------
class TestStoryReactions:
    def test_friend_can_react_and_owner_gets_notification_and_reaction(self):
        owner = _register("rx_owner")
        friend = _register("rx_friend")
        _friend_pair(owner, friend)
        s = _upload_story(owner["token"], "TEST reactme")

        r = requests.post(f"{API}/stories/{s['id']}/react", headers=_hj(friend["token"]),
                          json={"content": "❤️"})
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True}

        r2 = requests.post(f"{API}/stories/{s['id']}/react", headers=_hj(friend["token"]),
                           json={"content": "que envidia"})
        assert r2.status_code == 200, r2.text

        # owner notifications
        n = requests.get(f"{API}/notifications", headers=_h(owner["token"]))
        assert n.status_code == 200
        rx = [x for x in n.json() if x["type"] == "story_reaction"]
        assert len(rx) >= 2, n.json()
        assert rx[0]["data"]["story_id"] == s["id"]
        assert friend["user"]["name"] in rx[0]["message"]

        # owner sees received reactions on own story (archive + feed)
        arc = requests.get(f"{API}/stories/archive", headers=_h(owner["token"])).json()
        mine = [x for x in arc if x["id"] == s["id"]][0]
        contents = [c["content"] for c in mine["reactions"]]
        assert "❤️" in contents and "que envidia" in contents, contents
        assert mine["reactions"][0]["user"]["name"] == friend["user"]["name"]

    def test_reactions_not_exposed_to_viewer_of_friend_story(self):
        owner = _register("rx2_owner")
        friend = _register("rx2_friend")
        _friend_pair(owner, friend)
        s = _upload_story(owner["token"], "TEST hidden reactions")
        requests.post(f"{API}/stories/{s['id']}/react", headers=_hj(friend["token"]),
                      json={"content": "🔥"})
        feed = requests.get(f"{API}/stories", headers=_h(friend["token"])).json()
        target = [x for x in feed if x["id"] == s["id"]][0]
        assert target["is_mine"] is False
        assert "reactions" not in target, target

    def test_non_friend_cannot_react(self):
        owner = _register("rx3_owner")
        stranger = _register("rx3_str")
        s = _upload_story(owner["token"], "TEST private")
        r = requests.post(f"{API}/stories/{s['id']}/react", headers=_hj(stranger["token"]),
                          json={"content": "❤️"})
        assert r.status_code == 403, f"{r.status_code} {r.text}"
        n = requests.get(f"{API}/notifications", headers=_h(owner["token"])).json()
        assert [x for x in n if x["type"] == "story_reaction"] == []

    def test_self_reaction_allowed_without_notification(self):
        owner = _register("rx4_owner")
        s = _upload_story(owner["token"], "TEST self react")
        r = requests.post(f"{API}/stories/{s['id']}/react", headers=_hj(owner["token"]),
                          json={"content": "😂"})
        assert r.status_code == 200, r.text
        n = requests.get(f"{API}/notifications", headers=_h(owner["token"])).json()
        assert [x for x in n if x["type"] == "story_reaction"] == [], "self reaction must not notify"
        arc = requests.get(f"{API}/stories/archive", headers=_h(owner["token"])).json()
        assert "😂" in [c["content"] for c in arc[0]["reactions"]]

    def test_react_validation_and_errors(self):
        u = _register("rx5")
        s = _upload_story(u["token"], "TEST validation")
        r = requests.post(f"{API}/stories/{s['id']}/react", headers=_hj(u["token"]),
                          json={"content": "   "})
        assert r.status_code == 400, r.status_code
        r = requests.post(f"{API}/stories/{uuid.uuid4()}/react", headers=_hj(u["token"]),
                          json={"content": "hola"})
        assert r.status_code == 404, r.status_code
        r = requests.post(f"{API}/stories/{s['id']}/react", json={"content": "hola"})
        assert r.status_code in (401, 403), r.status_code
        r = requests.post(f"{API}/stories/{s['id']}/react", headers=_hj(u["token"]), json={})
        assert r.status_code == 422, r.status_code

    def test_long_reaction_truncated_to_200(self):
        u = _register("rx6")
        s = _upload_story(u["token"], "TEST long")
        r = requests.post(f"{API}/stories/{s['id']}/react", headers=_hj(u["token"]),
                          json={"content": "x" * 400})
        assert r.status_code == 200, r.text
        arc = requests.get(f"{API}/stories/archive", headers=_h(u["token"])).json()
        assert len(arc[0]["reactions"][0]["content"]) == 200


# ---------------------------------------------------------------------------
# (C) Event chat
# ---------------------------------------------------------------------------
class TestEventChat:
    def _an_event(self, tok):
        evs = requests.get(f"{API}/events", headers=_h(tok)).json()
        assert evs, "no events available"
        return evs[0]

    def test_chat_requires_auth(self):
        u = _register("chat_auth")
        ev = self._an_event(u["token"])
        assert requests.get(f"{API}/events/{ev['id']}/messages").status_code in (401, 403)
        assert requests.post(f"{API}/events/{ev['id']}/messages",
                             json={"text": "hi"}).status_code in (401, 403)

    def test_post_and_list_messages_visible_to_other_user(self):
        a = _register("chat_a")
        b = _register("chat_b")
        ev = self._an_event(a["token"])
        text = f"TEST hola {uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/events/{ev['id']}/messages", headers=_hj(a["token"]),
                          json={"text": text})
        assert r.status_code == 200, r.text
        m = r.json()
        assert m["text"] == text
        assert m["is_mine"] is True
        assert m["author"]["name"] == a["user"]["name"]
        assert m["event_id"] == ev["id"]
        assert "_id" not in m

        # A sees it as mine
        la = requests.get(f"{API}/events/{ev['id']}/messages", headers=_h(a["token"]))
        assert la.status_code == 200
        mine = [x for x in la.json() if x["id"] == m["id"]]
        assert mine and mine[0]["is_mine"] is True

        # B sees it as not mine, chronological order
        lb = requests.get(f"{API}/events/{ev['id']}/messages", headers=_h(b["token"]))
        assert lb.status_code == 200
        msgs = lb.json()
        theirs = [x for x in msgs if x["id"] == m["id"]]
        assert theirs, "message not visible to other user"
        assert theirs[0]["is_mine"] is False
        created = [x["created_at"] for x in msgs]
        assert created == sorted(created)

    def test_participants_get_event_message_notification(self, admin_token):
        # dedicated event so notification counting is deterministic
        r = requests.post(f"{API}/admin/events", headers=_hj(admin_token), json={
            "name": f"TEST_chat_event_{uuid.uuid4().hex[:6]}", "venue": "TEST Venue",
            "date": (date.today() + timedelta(days=3)).isoformat(), "time": "23:00",
            "genre": "techno", "city": "Palma de Mallorca"})
        assert r.status_code == 200, r.text
        ev = r.json()
        try:
            sender = _register("chat_send")
            going = _register("chat_going")
            interested = _register("chat_int")
            outsider = _register("chat_out")

            assert requests.post(f"{API}/events/{ev['id']}/interest", headers=_hj(going["token"]),
                                 json={"status": "voy"}).status_code == 200
            assert requests.post(f"{API}/events/{ev['id']}/interest", headers=_hj(interested["token"]),
                                 json={"status": "me_interesa"}).status_code == 200

            text = "TEST nos vemos en la puerta"
            assert requests.post(f"{API}/events/{ev['id']}/messages", headers=_hj(sender["token"]),
                                 json={"text": text}).status_code == 200

            for u in (going, interested):
                n = requests.get(f"{API}/notifications", headers=_h(u["token"])).json()
                em = [x for x in n if x["type"] == "event_message"]
                assert len(em) == 1, f"{u['user']['username']} -> {n}"
                assert em[0]["data"]["event_id"] == ev["id"]
                assert sender["user"]["name"] in em[0]["message"]
                assert ev["name"] in em[0]["message"]

            for u in (outsider, sender):
                n = requests.get(f"{API}/notifications", headers=_h(u["token"])).json()
                assert [x for x in n if x["type"] == "event_message"] == [], u["user"]["username"]
        finally:
            requests.delete(f"{API}/admin/events/{ev['id']}", headers=_h(admin_token))

    def test_chat_errors(self):
        u = _register("chat_err")
        ev = self._an_event(u["token"])
        assert requests.post(f"{API}/events/{ev['id']}/messages", headers=_hj(u["token"]),
                             json={"text": "   "}).status_code == 400
        assert requests.post(f"{API}/events/{uuid.uuid4()}/messages", headers=_hj(u["token"]),
                             json={"text": "hola"}).status_code == 404
        assert requests.get(f"{API}/events/{uuid.uuid4()}/messages",
                            headers=_h(u["token"])).status_code == 404


# ---------------------------------------------------------------------------
# (D) Weekend recap
# ---------------------------------------------------------------------------
class TestWeekendRecap:
    def test_requires_admin(self):
        u = _register("recap_user")
        r = requests.post(f"{API}/admin/trigger-weekend-recap", headers=_h(u["token"]))
        assert r.status_code == 403, r.status_code
        assert requests.post(f"{API}/admin/trigger-weekend-recap").status_code in (401, 403)

    def test_trigger_returns_sent_count(self, admin_token):
        r = requests.post(f"{API}/admin/trigger-weekend-recap", headers=_h(admin_token))
        assert r.status_code == 200, r.text
        d = r.json()
        assert "sent" in d and isinstance(d["sent"], int) and d["sent"] >= 0, d

    def test_recap_generated_for_user_with_previous_weekend_activity(self, admin_token):
        today = date.today()
        days_back = (today.weekday() + 1) % 7 or 7
        last_sunday = today - timedelta(days=days_back)
        # event inside last Fri-Sun window
        r = requests.post(f"{API}/admin/events", headers=_hj(admin_token), json={
            "name": f"TEST_recap_event_{uuid.uuid4().hex[:6]}", "venue": "TEST Venue",
            "date": last_sunday.isoformat(), "time": "23:30", "genre": "techno",
            "city": "Palma de Mallorca"})
        assert r.status_code == 200, r.text
        ev = r.json()
        try:
            u = _register("recap_act")
            assert requests.post(f"{API}/events/{ev['id']}/interest", headers=_hj(u["token"]),
                                 json={"status": "estuve"}).status_code == 200
            t = requests.post(f"{API}/admin/trigger-weekend-recap", headers=_h(admin_token))
            assert t.status_code == 200, t.text
            assert t.json()["sent"] >= 1
            n = requests.get(f"{API}/notifications", headers=_h(u["token"])).json()
            recaps = [x for x in n if x["type"] == "weekend_recap"]
            assert len(recaps) >= 1, n
            assert "finde" in recaps[0]["message"]
            assert recaps[0]["read"] is False
        finally:
            requests.delete(f"{API}/admin/events/{ev['id']}", headers=_h(admin_token))

    def test_no_recap_for_user_without_activity(self, admin_token):
        u = _register("recap_idle")
        assert requests.post(f"{API}/admin/trigger-weekend-recap",
                             headers=_h(admin_token)).status_code == 200
        n = requests.get(f"{API}/notifications", headers=_h(u["token"])).json()
        assert [x for x in n if x["type"] == "weekend_recap"] == [], n


# ---------------------------------------------------------------------------
# Data refresh
# ---------------------------------------------------------------------------
class TestDataRefresh:
    def test_default_feed_has_6_upcoming_demo_events(self):
        u = _register("data")
        r = requests.get(f"{API}/events", headers=_h(u["token"]))
        assert r.status_code == 200, r.text
        evs = r.json()
        assert len(evs) == 6, [e["name"] for e in evs]
        today = date.today()
        for e in evs:
            assert date.fromisoformat(e["date"]) >= today, e
            assert not e["name"].upper().startswith(("TEST", "UI5", "UI4", "ITERATION")), e["name"]
            assert "_id" not in e
        dates = [e["date"] for e in evs]
        assert dates == sorted(dates), dates

    def test_no_test_artifact_events_in_db(self, admin_token):
        r = requests.get(f"{API}/admin/events", headers=_h(admin_token))
        assert r.status_code == 200
        leftovers = [e["name"] for e in r.json()
                     if e["name"].upper().startswith(("UI5", "UI4", "ITERATION"))]
        assert leftovers == [], leftovers

    def test_pasados_filter_still_works(self):
        u = _register("data_past")
        r = requests.get(f"{API}/events?date_filter=pasados", headers=_h(u["token"]))
        assert r.status_code == 200, r.text
        today = date.today()
        for e in r.json():
            assert date.fromisoformat(e["date"]) < today, e
