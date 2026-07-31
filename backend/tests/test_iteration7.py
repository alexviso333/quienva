"""Iteration 7 regressions: event chat latest-100, weekend recap idempotency, event delete cleanup."""
import os
import uuid
import requests
import pytest
from dotenv import dotenv_values

fe = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL")).rstrip("/") + "/api"

ADMIN = {"email": "admin@quienva.app", "password": "QuienVa2026!"}
USERS = {
    "marta": {"email": "marta@test.com", "password": "test1234", "name": "Marta", "username": "marta"},
    "bob": {"email": "bob@test.com", "password": "test1234", "name": "Bob", "username": "bob"},
}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": creds["email"], "password": creds["password"]})
    if r.status_code != 200:
        reg = s.post(f"{BASE}/auth/register", json=creds)
        assert reg.status_code in (200, 201), reg.text
        r = s.post(f"{BASE}/auth/login", json={"email": creds["email"], "password": creds["password"]})
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def marta():
    return _login(USERS["marta"])


@pytest.fixture(scope="module")
def bob():
    return _login(USERS["bob"])


@pytest.fixture(scope="module")
def temp_event(admin):
    ev = {
        "name": f"TEST_it7_{uuid.uuid4().hex[:6]}",
        "venue": "TEST Venue",
        "city": "Palma de Mallorca",
        "date": "2030-01-01",
        "time": "23:00",
        "category": "fiesta",
        "description": "TEST event iteration 7",
    }
    r = admin.post(f"{BASE}/admin/events", json=ev)
    assert r.status_code in (200, 201), r.text
    eid = r.json().get("id") or r.json().get("event", {}).get("id")
    assert eid
    yield eid
    admin.delete(f"{BASE}/admin/events/{eid}")


# --- Event chat: latest up to 100 messages returned (newest not dropped) ---
class TestChatLatest100:
    def test_returns_latest_messages_not_oldest(self, marta, temp_event):
        total = 105
        for i in range(total):
            r = marta.post(f"{BASE}/events/{temp_event}/messages", json={"text": f"TEST_msg_{i:03d}"})
            assert r.status_code in (200, 201), r.text

        r = marta.get(f"{BASE}/events/{temp_event}/messages")
        assert r.status_code == 200
        msgs = r.json()
        assert len(msgs) == 100, f"expected 100 got {len(msgs)}"
        texts = [m["text"] for m in msgs]
        # newest message must be present and last (chronological asc)
        assert texts[-1] == f"TEST_msg_{total-1:03d}", texts[-3:]
        # oldest 5 dropped
        assert "TEST_msg_000" not in texts
        assert texts[0] == "TEST_msg_005"
        # chronological ascending
        assert all(msgs[i]["created_at"] <= msgs[i + 1]["created_at"] for i in range(len(msgs) - 1))
        # payload sanity
        assert msgs[-1]["is_mine"] is True
        assert msgs[-1]["author"]["name"]
        assert "_id" not in msgs[-1]


# --- Weekend recap idempotency ---
class TestWeekendRecapIdempotent:
    def test_double_trigger_no_duplicates(self, admin, marta):
        r1 = admin.post(f"{BASE}/admin/trigger-weekend-recap")
        assert r1.status_code == 200, r1.text
        assert isinstance(r1.json().get("sent"), int)

        def recap_count(sess):
            rr = sess.get(f"{BASE}/notifications")
            assert rr.status_code == 200
            return len([n for n in rr.json() if n["type"] == "weekend_recap"])

        before_marta = recap_count(marta)
        before_admin = recap_count(admin)

        r2 = admin.post(f"{BASE}/admin/trigger-weekend-recap")
        assert r2.status_code == 200
        assert r2.json()["sent"] == 0, f"second trigger sent {r2.json()['sent']} duplicates"

        assert recap_count(marta) == before_marta
        assert recap_count(admin) == before_admin

    def test_non_admin_forbidden(self, bob):
        r = bob.post(f"{BASE}/admin/trigger-weekend-recap")
        assert r.status_code == 403

    def test_no_auth_unauthorized(self):
        r = requests.post(f"{BASE}/admin/trigger-weekend-recap")
        assert r.status_code == 401


# --- Event delete cleanup: notifications + chat messages purged ---
class TestEventDeleteCleanup:
    def test_delete_removes_messages_and_notifications(self, admin, marta, bob):
        ev = {
            "name": f"TEST_it7_del_{uuid.uuid4().hex[:6]}",
            "venue": "TEST Venue",
            "city": "Palma de Mallorca",
            "date": "2030-02-02",
            "time": "22:00",
            "category": "fiesta",
            "description": "TEST delete cleanup",
        }
        r = admin.post(f"{BASE}/admin/events", json=ev)
        assert r.status_code in (200, 201), r.text
        eid = r.json().get("id")

        # bob marks voy so he gets event_message notifications
        assert bob.post(f"{BASE}/events/{eid}/interest", json={"status": "voy"}).status_code in (200, 201)
        assert marta.post(f"{BASE}/events/{eid}/messages", json={"text": "TEST cleanup msg"}).status_code in (200, 201)

        notifs = bob.get(f"{BASE}/notifications").json()
        related = [n for n in notifs if (n.get("data") or {}).get("event_id") == eid]
        assert len(related) >= 1, "bob should have gotten an event_message notification"

        assert marta.get(f"{BASE}/events/{eid}/messages").status_code == 200

        d = admin.delete(f"{BASE}/admin/events/{eid}")
        assert d.status_code == 200, d.text

        # event gone
        assert marta.get(f"{BASE}/events/{eid}").status_code == 404
        # chat endpoint 404 (event gone)
        assert marta.get(f"{BASE}/events/{eid}/messages").status_code == 404
        # notifications purged
        notifs2 = bob.get(f"{BASE}/notifications").json()
        stale = [n for n in notifs2 if (n.get("data") or {}).get("event_id") == eid]
        assert stale == [], f"stale notifications remain: {stale}"


# --- Story reactions regression ---
class TestStoryReactionsRegression:
    def test_friend_reacts_owner_notified_and_sees_reaction(self, marta, bob):
        feed = bob.get(f"{BASE}/stories")
        assert feed.status_code == 200
        marta_stories = [s for s in feed.json() if s["author"]["username"] == "marta"]
        if not marta_stories:
            pytest.fail("seed missing: marta has no active story (run setup_ui_iteration6.py)")
        sid = marta_stories[0]["id"]

        r = bob.post(f"{BASE}/stories/{sid}/react", json={"content": "TEST_react_it7"})
        assert r.status_code in (200, 201), r.text

        notifs = marta.get(f"{BASE}/notifications").json()
        sr = [n for n in notifs if n["type"] == "story_reaction" and (n.get("data") or {}).get("story_id") == sid]
        assert sr, "owner did not receive story_reaction notification"

        arch = marta.get(f"{BASE}/stories/archive").json()
        target = [s for s in arch if s["id"] == sid]
        assert target, "story not in own archive"
        contents = [x["content"] for x in target[0].get("reactions", [])]
        assert "TEST_react_it7" in contents

    def test_non_friend_forbidden(self, marta):
        stranger = _login({"email": "stranger@test.com", "password": "test1234",
                           "name": "Stranger", "username": "stranger"})
        arch = marta.get(f"{BASE}/stories/archive").json()
        assert arch, "marta has no stories"
        sid = arch[0]["id"]
        r = stranger.post(f"{BASE}/stories/{sid}/react", json={"content": "TEST_nope"})
        assert r.status_code == 403, r.status_code
