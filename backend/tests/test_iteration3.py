"""Iteration 3 backend tests:
- date filter 'pasados' vs 'all' (upcoming)
- 'estuve' interest status + friends_attended in serialize
- mutual_count in /users/search, /users/by-username, /friends/requests
- POST /api/admin/trigger-reminders (admin gate, dedupe, matched-window)
"""
import os
import uuid
import pytest
import requests
from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.strip().split("=", 1)[1].rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "QuienVa2026!"
PALMA_TZ = ZoneInfo("Europe/Madrid")


def _h(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _register(email, username):
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": "test1234", "name": f"N{username}",
        "username": username, "city": "Palma de Mallorca",
    })
    assert r.status_code == 200, r.text
    return r.json()


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def _friend_pair(a, b):
    r1 = requests.post(f"{API}/friends/request", headers=_h(a["token"]),
                       json={"user_id": b["user"]["user_id"]})
    assert r1.status_code == 200
    if r1.json().get("status") == "accepted":
        return
    rr = requests.get(f"{API}/friends/requests", headers=_h(b["token"]))
    req = [x for x in rr.json() if x["user"]["user_id"] == a["user"]["user_id"]][0]
    requests.post(f"{API}/friends/respond", headers=_h(b["token"]),
                  json={"request_id": req["request_id"], "accept": True})


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)["token"]


@pytest.fixture(scope="module")
def user_a():
    uniq = uuid.uuid4().hex[:8]
    return _register(f"test_i3a_{uniq}@test.com", f"i3a{uniq}")


@pytest.fixture(scope="module")
def user_b():
    uniq = uuid.uuid4().hex[:8]
    return _register(f"test_i3b_{uniq}@test.com", f"i3b{uniq}")


# --------------------------------------------------------------------------
# Date filter (Recuerdos / all)
# --------------------------------------------------------------------------
class TestDateFilter:
    def test_all_returns_only_upcoming(self, user_a):
        r = requests.get(f"{API}/events", headers=_h(user_a["token"]),
                         params={"date_filter": "all", "genre": "all"})
        assert r.status_code == 200
        today = date.today()
        for ev in r.json():
            assert date.fromisoformat(ev["date"]) >= today, f"Upcoming got past event {ev['date']}"

    def test_pasados_returns_only_past_and_sorted_desc(self, user_a):
        r = requests.get(f"{API}/events", headers=_h(user_a["token"]),
                         params={"date_filter": "pasados", "genre": "all"})
        assert r.status_code == 200
        today = date.today()
        events = r.json()
        prev = None
        for ev in events:
            d = date.fromisoformat(ev["date"])
            assert d < today, f"Pasados got non-past event {ev['date']}"
            if prev is not None:
                assert d <= prev, "Pasados not sorted desc"
            prev = d


# --------------------------------------------------------------------------
# Estuve interest + friends_attended
# --------------------------------------------------------------------------
class TestEstuve:
    def test_estuve_status_and_coincidence(self, admin_token, user_a, user_b):
        # Make A and B friends
        _friend_pair(user_a, user_b)
        # Admin creates a past event
        past_d = (date.today() - timedelta(days=7)).isoformat()
        payload = {"name": "TEST_I3_PAST_" + uuid.uuid4().hex[:6], "venue": "V",
                   "address": "Palma", "date": past_d, "time": "22:00",
                   "genre": "Techno", "image_url": "", "has_commission": False,
                   "commission_url": "", "more_info_url": ""}
        rc = requests.post(f"{API}/admin/events", headers=_h(admin_token), json=payload)
        assert rc.status_code == 200
        eid = rc.json()["id"]

        # A marks estuve
        r1 = requests.post(f"{API}/events/{eid}/interest", headers=_h(user_a["token"]),
                           json={"status": "estuve"})
        assert r1.status_code == 200
        assert r1.json()["status"] == "estuve"

        # B marks estuve
        r2 = requests.post(f"{API}/events/{eid}/interest", headers=_h(user_b["token"]),
                           json={"status": "estuve"})
        assert r2.status_code == 200

        # A fetches event -> friends_attended contains B
        r3 = requests.get(f"{API}/events/{eid}", headers=_h(user_a["token"]))
        assert r3.status_code == 200
        ev = r3.json()
        assert ev["my_status"] == "estuve"
        assert ev["total_attended"] >= 2
        attended_ids = [f["user_id"] for f in ev["friends_attended"]]
        assert user_b["user"]["user_id"] in attended_ids

        # Event appears in Recuerdos for A
        r4 = requests.get(f"{API}/events", headers=_h(user_a["token"]),
                          params={"date_filter": "pasados", "genre": "all"})
        assert any(e["id"] == eid for e in r4.json())

        # And NOT in Todos
        r5 = requests.get(f"{API}/events", headers=_h(user_a["token"]),
                          params={"date_filter": "all", "genre": "all"})
        assert not any(e["id"] == eid for e in r5.json())

        # Unmark toggles off
        r6 = requests.post(f"{API}/events/{eid}/interest", headers=_h(user_a["token"]),
                           json={"status": "none"})
        assert r6.status_code == 200
        r7 = requests.get(f"{API}/events/{eid}", headers=_h(user_a["token"]))
        assert r7.json()["my_status"] is None

        # cleanup
        requests.delete(f"{API}/admin/events/{eid}", headers=_h(admin_token))


# --------------------------------------------------------------------------
# Mutual friends count
# --------------------------------------------------------------------------
class TestMutualFriends:
    def test_mutual_count_in_search_and_by_username(self):
        uniq = uuid.uuid4().hex[:8]
        a = _register(f"test_i3mA_{uniq}@test.com", f"i3ma{uniq}")
        b = _register(f"test_i3mB_{uniq}@test.com", f"i3mb{uniq}")
        c = _register(f"test_i3mC_{uniq}@test.com", f"i3mc{uniq}")
        # a-c friends, b-c friends
        _friend_pair(a, c)
        _friend_pair(b, c)

        # As A, search for B → mutual_count == 1
        rs = requests.get(f"{API}/users/search", headers=_h(a["token"]),
                          params={"q": b["user"]["username"]})
        assert rs.status_code == 200
        found = [u for u in rs.json() if u["user_id"] == b["user"]["user_id"]]
        assert found, f"B not returned in A's search: {rs.json()}"
        assert found[0].get("mutual_count") == 1

        # by-username also returns mutual_count
        rb = requests.get(f"{API}/users/by-username/{b['user']['username']}",
                          headers=_h(a["token"]))
        assert rb.status_code == 200
        assert rb.json().get("mutual_count") == 1

    def test_mutual_count_in_friend_requests(self):
        uniq = uuid.uuid4().hex[:8]
        a = _register(f"test_i3rA_{uniq}@test.com", f"i3ra{uniq}")
        b = _register(f"test_i3rB_{uniq}@test.com", f"i3rb{uniq}")
        c = _register(f"test_i3rC_{uniq}@test.com", f"i3rc{uniq}")
        # a-c and b-c friends
        _friend_pair(a, c)
        _friend_pair(b, c)
        # B sends request to A (still pending)
        r = requests.post(f"{API}/friends/request", headers=_h(b["token"]),
                          json={"user_id": a["user"]["user_id"]})
        assert r.status_code == 200
        # A lists incoming
        rr = requests.get(f"{API}/friends/requests", headers=_h(a["token"]))
        assert rr.status_code == 200
        incoming = [x for x in rr.json() if x["user"]["user_id"] == b["user"]["user_id"]]
        assert incoming, f"Pending req not found: {rr.json()}"
        assert incoming[0]["user"].get("mutual_count") == 1


# --------------------------------------------------------------------------
# Event reminders
# --------------------------------------------------------------------------
class TestReminders:
    def test_trigger_requires_admin(self, user_a):
        r = requests.post(f"{API}/admin/trigger-reminders", headers=_h(user_a["token"]))
        assert r.status_code == 403

    def test_trigger_returns_sent_count(self, admin_token):
        r = requests.post(f"{API}/admin/trigger-reminders", headers=_h(admin_token))
        assert r.status_code == 200
        assert "sent" in r.json()
        assert isinstance(r.json()["sent"], int)

    def test_reminder_creates_notification_and_dedupes(self, admin_token):
        # Create event today at ~2h from now (Europe/Madrid)
        now = datetime.now(PALMA_TZ)
        target = now + timedelta(hours=2)
        # If target crosses midnight, keep same date as event start
        event_date = target.date().isoformat()
        event_time = target.strftime("%H:%M")
        uniq = uuid.uuid4().hex[:6]

        payload = {"name": "TEST_I3_REM_" + uniq, "venue": "V",
                   "address": "Palma", "date": event_date, "time": event_time,
                   "genre": "Techno", "image_url": "", "has_commission": False,
                   "commission_url": "", "more_info_url": ""}
        rc = requests.post(f"{API}/admin/events", headers=_h(admin_token), json=payload)
        assert rc.status_code == 200, rc.text
        eid = rc.json()["id"]

        # Register a fresh user, mark voy
        u = _register(f"test_i3rem_{uniq}@test.com", f"i3rem{uniq}")
        ri = requests.post(f"{API}/events/{eid}/interest", headers=_h(u["token"]),
                           json={"status": "voy"})
        assert ri.status_code == 200

        # Trigger reminders
        rt1 = requests.post(f"{API}/admin/trigger-reminders", headers=_h(admin_token))
        assert rt1.status_code == 200
        assert rt1.json()["sent"] >= 1

        # user should have exactly one 'event_reminder' for this event
        rn = requests.get(f"{API}/notifications", headers=_h(u["token"]))
        assert rn.status_code == 200
        rems = [n for n in rn.json() if n["type"] == "event_reminder"
                and n["data"].get("event_id") == eid]
        assert len(rems) == 1, f"Expected 1 reminder, got {len(rems)}"
        assert "empieza pronto" in rems[0]["message"].lower() or "empieza" in rems[0]["message"].lower()

        # Trigger again — should NOT duplicate
        rt2 = requests.post(f"{API}/admin/trigger-reminders", headers=_h(admin_token))
        assert rt2.status_code == 200
        rn2 = requests.get(f"{API}/notifications", headers=_h(u["token"]))
        rems2 = [n for n in rn2.json() if n["type"] == "event_reminder"
                 and n["data"].get("event_id") == eid]
        assert len(rems2) == 1, f"Reminder duplicated: got {len(rems2)}"

        # cleanup
        requests.delete(f"{API}/admin/events/{eid}", headers=_h(admin_token))
