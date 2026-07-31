"""Iteration 4 backend tests:
- GET /api/events/{event_id} full detail + friends lists (going/interested/attended)
- GET /api/events/top-weekend (null when no friend going, event when a friend marks voy)
- GET /api/me/streak
- interested_reminder in generate_event_reminders via POST /api/admin/trigger-reminders
"""
import os
import uuid
import pytest
import requests
from datetime import date, datetime, timedelta
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
    assert r1.status_code == 200, r1.text
    if r1.json().get("status") == "accepted":
        return
    rr = requests.get(f"{API}/friends/requests", headers=_h(b["token"]))
    req = [x for x in rr.json() if x["user"]["user_id"] == a["user"]["user_id"]][0]
    r2 = requests.post(f"{API}/friends/respond", headers=_h(b["token"]),
                       json={"request_id": req["request_id"], "accept": True})
    assert r2.status_code == 200, r2.text


def _mk_event(admin_tok, name, d, t="23:00", **kw):
    payload = {"name": name, "venue": "TEST_Venue", "address": "Carrer TEST 1",
               "date": d, "time": t, "genre": "Techno", "city": "Palma de Mallorca"}
    payload.update(kw)
    r = requests.post(f"{API}/admin/events", headers=_h(admin_tok), json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def _interest(tok, eid, status):
    r = requests.post(f"{API}/events/{eid}/interest", headers=_h(tok), json={"status": status})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)["token"]


@pytest.fixture(scope="module")
def user_a():
    u = uuid.uuid4().hex[:8]
    return _register(f"test_i4a_{u}@test.com", f"i4a{u}")


@pytest.fixture(scope="module")
def user_b():
    u = uuid.uuid4().hex[:8]
    return _register(f"test_i4b_{u}@test.com", f"i4b{u}")


@pytest.fixture(scope="module")
def created_event_ids():
    return []


@pytest.fixture(scope="module", autouse=True)
def cleanup(admin_token, created_event_ids):
    yield
    for eid in created_event_ids:
        requests.delete(f"{API}/admin/events/{eid}", headers=_h(admin_token))


# --------------------------------------------------------------------------
# GET /api/events/{event_id}
# --------------------------------------------------------------------------
class TestEventDetail:
    def test_detail_shape_and_fields(self, admin_token, user_a, created_event_ids):
        d = (datetime.now(PALMA_TZ).date() + timedelta(days=3)).isoformat()
        ev = _mk_event(admin_token, "TEST_Detail_Upcoming", d, has_commission=True,
                       commission_url="https://tickets.example.com/x")
        created_event_ids.append(ev["id"])

        r = requests.get(f"{API}/events/{ev['id']}", headers=_h(user_a["token"]))
        assert r.status_code == 200, r.text
        data = r.json()
        assert "_id" not in data
        assert data["id"] == ev["id"]
        assert data["name"] == "TEST_Detail_Upcoming"
        assert data["venue"] == "TEST_Venue"
        assert data["address"] == "Carrer TEST 1"
        assert data["date"] == d
        assert data["time"] == "23:00"
        assert data["has_commission"] is True
        assert data["commission_url"] == "https://tickets.example.com/x"
        assert data["my_status"] is None
        for k in ("friends_going", "friends_interested", "friends_attended"):
            assert isinstance(data[k], list) and data[k] == []
        assert data["total_going"] == 0

    def test_detail_404_unknown_id(self, user_a):
        r = requests.get(f"{API}/events/does-not-exist-{uuid.uuid4().hex}", headers=_h(user_a["token"]))
        assert r.status_code == 404
        assert "detail" in r.json()

    def test_detail_requires_auth(self, admin_token, created_event_ids):
        d = (datetime.now(PALMA_TZ).date() + timedelta(days=4)).isoformat()
        ev = _mk_event(admin_token, "TEST_Detail_Auth", d)
        created_event_ids.append(ev["id"])
        r = requests.get(f"{API}/events/{ev['id']}")
        assert r.status_code in (401, 403), r.status_code

    def test_detail_interest_toggle_persists(self, admin_token, user_a, created_event_ids):
        d = (datetime.now(PALMA_TZ).date() + timedelta(days=5)).isoformat()
        ev = _mk_event(admin_token, "TEST_Detail_Toggle", d)
        created_event_ids.append(ev["id"])
        tok = user_a["token"]

        _interest(tok, ev["id"], "voy")
        assert requests.get(f"{API}/events/{ev['id']}", headers=_h(tok)).json()["my_status"] == "voy"
        _interest(tok, ev["id"], "me_interesa")
        got = requests.get(f"{API}/events/{ev['id']}", headers=_h(tok)).json()
        assert got["my_status"] == "me_interesa"
        assert got["total_going"] == 0 and got["total_interested"] == 1
        _interest(tok, ev["id"], "none")
        assert requests.get(f"{API}/events/{ev['id']}", headers=_h(tok)).json()["my_status"] is None

    def test_detail_friend_lists_populated(self, admin_token, user_a, user_b, created_event_ids):
        _friend_pair(user_a, user_b)
        d = (datetime.now(PALMA_TZ).date() + timedelta(days=6)).isoformat()
        ev = _mk_event(admin_token, "TEST_Detail_Friends", d)
        created_event_ids.append(ev["id"])

        _interest(user_b["token"], ev["id"], "voy")
        data = requests.get(f"{API}/events/{ev['id']}", headers=_h(user_a["token"])).json()
        assert [f["user_id"] for f in data["friends_going"]] == [user_b["user"]["user_id"]]
        assert data["friends_going"][0]["name"] == user_b["user"]["name"]
        assert "picture" in data["friends_going"][0]
        assert data["friends_interested"] == []

        _interest(user_b["token"], ev["id"], "me_interesa")
        data = requests.get(f"{API}/events/{ev['id']}", headers=_h(user_a["token"])).json()
        assert data["friends_going"] == []
        assert [f["user_id"] for f in data["friends_interested"]] == [user_b["user"]["user_id"]]

    def test_past_event_friends_attended(self, admin_token, user_a, user_b, created_event_ids):
        _friend_pair(user_a, user_b)
        d = (datetime.now(PALMA_TZ).date() - timedelta(days=10)).isoformat()
        ev = _mk_event(admin_token, "TEST_Detail_Past", d)
        created_event_ids.append(ev["id"])
        _interest(user_b["token"], ev["id"], "estuve")
        data = requests.get(f"{API}/events/{ev['id']}", headers=_h(user_a["token"])).json()
        assert [f["user_id"] for f in data["friends_attended"]] == [user_b["user"]["user_id"]]
        assert data["total_attended"] == 1


# --------------------------------------------------------------------------
# GET /api/events/top-weekend
# --------------------------------------------------------------------------
class TestTopWeekend:
    def test_route_not_shadowed_by_event_id(self, user_a):
        r = requests.get(f"{API}/events/top-weekend", headers=_h(user_a["token"]))
        assert r.status_code == 200, r.text  # would be 404 if {event_id} matched first

    def test_null_when_no_friend_going(self, admin_token, created_event_ids):
        u = uuid.uuid4().hex[:8]
        lonely = _register(f"test_i4lone_{u}@test.com", f"i4l{u}")
        r = requests.get(f"{API}/events/top-weekend", headers=_h(lonely["token"]))
        assert r.status_code == 200
        assert r.json() is None, r.text

    def test_returns_event_with_most_friends_going(self, admin_token, created_event_ids):
        u = uuid.uuid4().hex[:8]
        a = _register(f"test_i4tw_a{u}@test.com", f"i4twa{u}")
        b = _register(f"test_i4tw_b{u}@test.com", f"i4twb{u}")
        c = _register(f"test_i4tw_c{u}@test.com", f"i4twc{u}")
        _friend_pair(a, b)
        _friend_pair(a, c)

        today = datetime.now(PALMA_TZ).date()
        ev1 = _mk_event(admin_token, "TEST_TW_One", (today + timedelta(days=1)).isoformat())
        ev2 = _mk_event(admin_token, "TEST_TW_Two", (today + timedelta(days=2)).isoformat())
        created_event_ids += [ev1["id"], ev2["id"]]

        _interest(b["token"], ev1["id"], "voy")
        top = requests.get(f"{API}/events/top-weekend", headers=_h(a["token"])).json()
        assert top is not None and top["id"] == ev1["id"]
        assert len(top["friends_going"]) == 1

        # two friends on ev2 -> becomes the top
        _interest(b["token"], ev2["id"], "voy")
        _interest(c["token"], ev2["id"], "voy")
        top = requests.get(f"{API}/events/top-weekend", headers=_h(a["token"])).json()
        assert top["id"] == ev2["id"], top["name"]
        assert len(top["friends_going"]) == 2

    def test_ignores_me_interesa_and_past_events(self, admin_token, created_event_ids):
        u = uuid.uuid4().hex[:8]
        a = _register(f"test_i4ig_a{u}@test.com", f"i4iga{u}")
        b = _register(f"test_i4ig_b{u}@test.com", f"i4igb{u}")
        _friend_pair(a, b)
        today = datetime.now(PALMA_TZ).date()
        up = _mk_event(admin_token, "TEST_TW_Interesa", (today + timedelta(days=2)).isoformat())
        past = _mk_event(admin_token, "TEST_TW_Past", (today - timedelta(days=2)).isoformat())
        created_event_ids += [up["id"], past["id"]]
        _interest(b["token"], up["id"], "me_interesa")
        _interest(b["token"], past["id"], "voy")
        assert requests.get(f"{API}/events/top-weekend", headers=_h(a["token"])).json() is None


# --------------------------------------------------------------------------
# GET /api/me/streak
# --------------------------------------------------------------------------
class TestStreak:
    def test_streak_zero_for_new_user(self):
        u = uuid.uuid4().hex[:8]
        n = _register(f"test_i4st0_{u}@test.com", f"i4st0{u}")
        r = requests.get(f"{API}/me/streak", headers=_h(n["token"]))
        assert r.status_code == 200, r.text
        assert r.json() == {"streak": 0}

    def test_streak_one_current_week(self, admin_token, created_event_ids):
        u = uuid.uuid4().hex[:8]
        n = _register(f"test_i4st1_{u}@test.com", f"i4st1{u}")
        today = datetime.now(PALMA_TZ).date()
        monday = today - timedelta(days=today.weekday())
        ev = _mk_event(admin_token, "TEST_Streak_ThisWeek", monday.isoformat())
        created_event_ids.append(ev["id"])
        _interest(n["token"], ev["id"], "voy")
        assert requests.get(f"{API}/me/streak", headers=_h(n["token"])).json()["streak"] == 1

    def test_streak_three_consecutive_weeks(self, admin_token, created_event_ids):
        u = uuid.uuid4().hex[:8]
        n = _register(f"test_i4st3_{u}@test.com", f"i4st3{u}")
        today = datetime.now(PALMA_TZ).date()
        monday = today - timedelta(days=today.weekday())
        for w, status in ((0, "voy"), (1, "estuve"), (2, "estuve")):
            ev = _mk_event(admin_token, f"TEST_Streak_W{w}", (monday - timedelta(days=7 * w)).isoformat())
            created_event_ids.append(ev["id"])
            _interest(n["token"], ev["id"], status)
        assert requests.get(f"{API}/me/streak", headers=_h(n["token"])).json()["streak"] == 3

    def test_streak_breaks_on_gap(self, admin_token, created_event_ids):
        u = uuid.uuid4().hex[:8]
        n = _register(f"test_i4stg_{u}@test.com", f"i4stg{u}")
        today = datetime.now(PALMA_TZ).date()
        monday = today - timedelta(days=today.weekday())
        for w in (0, 3):
            ev = _mk_event(admin_token, f"TEST_StreakGap_W{w}", (monday - timedelta(days=7 * w)).isoformat())
            created_event_ids.append(ev["id"])
            _interest(n["token"], ev["id"], "estuve")
        assert requests.get(f"{API}/me/streak", headers=_h(n["token"])).json()["streak"] == 1

    def test_streak_ignores_me_interesa(self, admin_token, created_event_ids):
        u = uuid.uuid4().hex[:8]
        n = _register(f"test_i4sti_{u}@test.com", f"i4sti{u}")
        today = datetime.now(PALMA_TZ).date()
        monday = today - timedelta(days=today.weekday())
        ev = _mk_event(admin_token, "TEST_Streak_Interesa", monday.isoformat())
        created_event_ids.append(ev["id"])
        _interest(n["token"], ev["id"], "me_interesa")
        assert requests.get(f"{API}/me/streak", headers=_h(n["token"])).json()["streak"] == 0

    def test_streak_requires_auth(self):
        r = requests.get(f"{API}/me/streak")
        assert r.status_code in (401, 403)


# --------------------------------------------------------------------------
# interested_reminder (RECORDAR INTERESADOS)
# --------------------------------------------------------------------------
class TestInterestedReminder:
    def test_interested_reminder_created_and_dedupes(self, admin_token, created_event_ids):
        u = uuid.uuid4().hex[:8]
        n = _register(f"test_i4rem_{u}@test.com", f"i4rem{u}")
        today = datetime.now(PALMA_TZ).date().isoformat()
        # time far in future of day so the 'voy' 3h window is not triggered accidentally
        ev = _mk_event(admin_token, "TEST_Reminder_Interesa", today, t="23:59")
        created_event_ids.append(ev["id"])
        _interest(n["token"], ev["id"], "me_interesa")

        r = requests.post(f"{API}/admin/trigger-reminders", headers=_h(admin_token))
        assert r.status_code == 200, r.text
        assert r.json()["sent"] >= 1

        notifs = requests.get(f"{API}/notifications", headers=_h(n["token"])).json()
        mine = [x for x in notifs if x["type"] == "interested_reminder"
                and x.get("data", {}).get("event_id") == ev["id"]]
        assert len(mine) == 1, notifs
        assert "TEST_Reminder_Interesa" in mine[0]["message"]
        assert mine[0]["message"].startswith("Hoy:")
        assert "te animas" in mine[0]["message"]

        # second run must not duplicate
        requests.post(f"{API}/admin/trigger-reminders", headers=_h(admin_token))
        notifs = requests.get(f"{API}/notifications", headers=_h(n["token"])).json()
        mine2 = [x for x in notifs if x["type"] == "interested_reminder"
                 and x.get("data", {}).get("event_id") == ev["id"]]
        assert len(mine2) == 1

    def test_no_interested_reminder_for_future_day(self, admin_token, created_event_ids):
        u = uuid.uuid4().hex[:8]
        n = _register(f"test_i4remf_{u}@test.com", f"i4remf{u}")
        d = (datetime.now(PALMA_TZ).date() + timedelta(days=4)).isoformat()
        ev = _mk_event(admin_token, "TEST_Reminder_Future", d, t="23:00")
        created_event_ids.append(ev["id"])
        _interest(n["token"], ev["id"], "me_interesa")
        requests.post(f"{API}/admin/trigger-reminders", headers=_h(admin_token))
        notifs = requests.get(f"{API}/notifications", headers=_h(n["token"])).json()
        assert not [x for x in notifs if x.get("data", {}).get("event_id") == ev["id"]]

    def test_voy_reminder_still_works_and_dedupes_independently(self, admin_token, created_event_ids):
        u = uuid.uuid4().hex[:8]
        n = _register(f"test_i4voy_{u}@test.com", f"i4voy{u}")
        now = datetime.now(PALMA_TZ)
        start = now + timedelta(hours=1)
        if start.date() != now.date():
            pytest.skip("Cannot build a same-day +1h event window near midnight")
        ev = _mk_event(admin_token, "TEST_Reminder_Voy", now.date().isoformat(),
                       t=start.strftime("%H:%M"))
        created_event_ids.append(ev["id"])
        _interest(n["token"], ev["id"], "voy")
        requests.post(f"{API}/admin/trigger-reminders", headers=_h(admin_token))
        notifs = requests.get(f"{API}/notifications", headers=_h(n["token"])).json()
        voys = [x for x in notifs if x["type"] == "event_reminder"
                and x.get("data", {}).get("event_id") == ev["id"]]
        assert len(voys) == 1, notifs
        assert "empieza pronto" in voys[0]["message"]
        # no interested_reminder for a 'voy' user
        assert not [x for x in notifs if x["type"] == "interested_reminder"
                    and x.get("data", {}).get("event_id") == ev["id"]]
        requests.post(f"{API}/admin/trigger-reminders", headers=_h(admin_token))
        notifs = requests.get(f"{API}/notifications", headers=_h(n["token"])).json()
        assert len([x for x in notifs if x["type"] == "event_reminder"
                    and x.get("data", {}).get("event_id") == ev["id"]]) == 1

    def test_trigger_reminders_admin_only(self, user_a):
        r = requests.post(f"{API}/admin/trigger-reminders", headers=_h(user_a["token"]))
        assert r.status_code == 403, r.status_code
