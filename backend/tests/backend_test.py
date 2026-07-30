"""Backend API tests for ¿Quién va? MVP.
Covers auth, friends, events feed & filters, admin CRUD, voy/me_interesa social proof,
privacy, notifications.
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fall back to reading frontend .env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.strip().split("=", 1)[1].rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "QuienVa2026!"


def _client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _register(session, email, password, name, username, city="Palma de Mallorca"):
    r = session.post(f"{API}/auth/register", json={
        "email": email, "password": password, "name": name,
        "username": username, "city": city,
    })
    return r


def _login(session, email, password):
    r = session.post(f"{API}/auth/login", json={"email": email, "password": password})
    return r


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ------------------- Session-scoped fixtures -------------------
@pytest.fixture(scope="session")
def admin_token():
    s = _client()
    r = _login(s, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def user_a():
    """Registered user A."""
    s = _client()
    uniq = uuid.uuid4().hex[:8]
    email = f"test_a_{uniq}@test.com"
    r = _register(s, email, "test1234", f"UserA{uniq}", f"testa{uniq}")
    assert r.status_code == 200, f"register A failed: {r.text}"
    data = r.json()
    return {"token": data["token"], "user": data["user"], "email": email, "password": "test1234"}


@pytest.fixture(scope="session")
def user_b():
    s = _client()
    uniq = uuid.uuid4().hex[:8]
    email = f"test_b_{uniq}@test.com"
    r = _register(s, email, "test1234", f"UserB{uniq}", f"testb{uniq}")
    assert r.status_code == 200
    data = r.json()
    return {"token": data["token"], "user": data["user"], "email": email, "password": "test1234"}


@pytest.fixture(scope="session")
def user_c():
    """Non-friend user for privacy tests."""
    s = _client()
    uniq = uuid.uuid4().hex[:8]
    email = f"test_c_{uniq}@test.com"
    r = _register(s, email, "test1234", f"UserC{uniq}", f"testc{uniq}")
    assert r.status_code == 200
    data = r.json()
    return {"token": data["token"], "user": data["user"]}


# ------------------- Auth -------------------
class TestAuth:
    def test_register_duplicate_email(self, user_a):
        s = _client()
        r = _register(s, user_a["email"], "x", "X", f"other{uuid.uuid4().hex[:6]}")
        assert r.status_code == 400

    def test_login_success(self, user_a):
        s = _client()
        r = _login(s, user_a["email"], user_a["password"])
        assert r.status_code == 200
        data = r.json()
        assert "token" in data and data["user"]["email"] == user_a["email"]

    def test_login_wrong_password(self, user_a):
        s = _client()
        r = _login(s, user_a["email"], "badpass")
        assert r.status_code == 401

    def test_me(self, user_a):
        r = requests.get(f"{API}/auth/me", headers=_auth_headers(user_a["token"]))
        assert r.status_code == 200
        assert r.json()["email"] == user_a["email"]

    def test_me_unauth(self):
        r = requests.get(f"{API}/auth/me")
        assert r.status_code == 401

    def test_logout(self, user_a):
        # Login fresh to get a disposable token
        s = _client()
        r = _login(s, user_a["email"], user_a["password"])
        tok = r.json()["token"]
        r2 = requests.post(f"{API}/auth/logout", headers=_auth_headers(tok))
        assert r2.status_code == 200
        r3 = requests.get(f"{API}/auth/me", headers=_auth_headers(tok))
        assert r3.status_code == 401

    def test_admin_login_and_role(self, admin_token):
        r = requests.get(f"{API}/auth/me", headers=_auth_headers(admin_token))
        assert r.status_code == 200
        assert r.json()["role"] == "admin"


# ------------------- Events feed & filters -------------------
class TestEventsFeed:
    def test_list_events(self, user_a):
        r = requests.get(f"{API}/events", headers=_auth_headers(user_a["token"]))
        assert r.status_code == 200
        evs = r.json()
        assert isinstance(evs, list) and len(evs) >= 1
        # Sorted by date ascending
        dates = [e["date"] for e in evs]
        assert dates == sorted(dates)
        # Serialization fields
        e0 = evs[0]
        for k in ("id", "name", "venue", "date", "has_commission", "friends_going", "total_going"):
            assert k in e0

    def test_filter_by_genre(self, user_a):
        r = requests.get(f"{API}/events?genre=House", headers=_auth_headers(user_a["token"]))
        assert r.status_code == 200
        for e in r.json():
            assert e["genre"] == "House"

    def test_filter_date_semana(self, user_a):
        r = requests.get(f"{API}/events?date_filter=semana", headers=_auth_headers(user_a["token"]))
        assert r.status_code == 200

    def test_genres(self, user_a):
        r = requests.get(f"{API}/events/genres", headers=_auth_headers(user_a["token"]))
        assert r.status_code == 200
        assert isinstance(r.json(), list) and len(r.json()) >= 1


# ------------------- Admin CRUD -------------------
class TestAdminEvents:
    def test_non_admin_forbidden(self, user_a):
        r = requests.post(f"{API}/admin/events", headers=_auth_headers(user_a["token"]),
                          json={"name": "x", "venue": "y", "date": "2030-01-01"})
        assert r.status_code == 403

    def test_admin_crud(self, admin_token):
        headers = _auth_headers(admin_token)
        payload = {
            "name": "TEST_Event_" + uuid.uuid4().hex[:6],
            "venue": "TEST Venue",
            "address": "Palma",
            "date": "2030-06-15",
            "time": "22:00",
            "genre": "Techno",
            "image_url": "",
            "has_commission": True,
            "commission_url": "https://fourvenues.com/",
            "more_info_url": "",
        }
        r = requests.post(f"{API}/admin/events", headers=headers, json=payload)
        assert r.status_code == 200, r.text
        ev = r.json()
        eid = ev["id"]
        assert ev["name"] == payload["name"]

        # verify appears in admin list
        r2 = requests.get(f"{API}/admin/events", headers=headers)
        assert r2.status_code == 200
        assert any(e["id"] == eid for e in r2.json())

        # edit
        payload["name"] = "TEST_Event_Edited"
        payload["has_commission"] = False
        payload["more_info_url"] = "https://example.com/info"
        r3 = requests.put(f"{API}/admin/events/{eid}", headers=headers, json=payload)
        assert r3.status_code == 200
        assert r3.json()["name"] == "TEST_Event_Edited"
        assert r3.json()["has_commission"] is False

        # delete
        r4 = requests.delete(f"{API}/admin/events/{eid}", headers=headers)
        assert r4.status_code == 200

        # verify gone
        r5 = requests.get(f"{API}/events/{eid}", headers=headers)
        assert r5.status_code == 404


# ------------------- Friends flow -------------------
@pytest.fixture(scope="session")
def make_friends(user_a, user_b):
    """Make A and B accepted friends. Returns (a,b)."""
    # search for B from A
    r = requests.get(f"{API}/users/search?q={user_b['user']['username']}",
                     headers=_auth_headers(user_a["token"]))
    assert r.status_code == 200
    results = r.json()
    assert any(u["user_id"] == user_b["user"]["user_id"] for u in results)

    # A sends friend request to B
    r2 = requests.post(f"{API}/friends/request",
                       headers=_auth_headers(user_a["token"]),
                       json={"user_id": user_b["user"]["user_id"]})
    assert r2.status_code == 200
    assert r2.json()["status"] == "pending"

    # B lists incoming requests
    r3 = requests.get(f"{API}/friends/requests", headers=_auth_headers(user_b["token"]))
    assert r3.status_code == 200
    reqs = r3.json()
    match = [x for x in reqs if x["user"]["user_id"] == user_a["user"]["user_id"]]
    assert len(match) == 1
    req_id = match[0]["request_id"]

    # B accepts
    r4 = requests.post(f"{API}/friends/respond",
                       headers=_auth_headers(user_b["token"]),
                       json={"request_id": req_id, "accept": True})
    assert r4.status_code == 200
    assert r4.json()["status"] == "accepted"

    # confirm friendship listed for both
    for u in (user_a, user_b):
        r5 = requests.get(f"{API}/friends", headers=_auth_headers(u["token"]))
        assert r5.status_code == 200
    return user_a, user_b


class TestFriends:
    def test_flow(self, make_friends):
        a, b = make_friends
        r = requests.get(f"{API}/friends", headers=_auth_headers(a["token"]))
        assert any(f["user_id"] == b["user"]["user_id"] for f in r.json())
        r2 = requests.get(f"{API}/friends", headers=_auth_headers(b["token"]))
        assert any(f["user_id"] == a["user"]["user_id"] for f in r2.json())


# ------------------- Voy / Me interesa + social proof + privacy + notifications -------------------
class TestInterestAndSocial:
    def _first_event_id(self, token):
        r = requests.get(f"{API}/events", headers=_auth_headers(token))
        assert r.status_code == 200
        return r.json()[0]["id"]

    def test_voy_toggle_and_social_proof(self, make_friends, user_c):
        a, b = make_friends
        eid = self._first_event_id(a["token"])

        # B marks Voy
        r = requests.post(f"{API}/events/{eid}/interest",
                          headers=_auth_headers(b["token"]),
                          json={"status": "voy"})
        assert r.status_code == 200 and r.json()["status"] == "voy"

        # A sees B in friends_going
        r2 = requests.get(f"{API}/events/{eid}", headers=_auth_headers(a["token"]))
        assert r2.status_code == 200
        data = r2.json()
        assert any(f["user_id"] == b["user"]["user_id"] for f in data["friends_going"])

        # Privacy: user_c is not a friend of B → should not see B
        r3 = requests.get(f"{API}/events/{eid}", headers=_auth_headers(user_c["token"]))
        assert r3.status_code == 200
        assert all(f["user_id"] != b["user"]["user_id"] for f in r3.json()["friends_going"])

        # Notification created for A (friend of B) about "friend_going"
        time.sleep(0.5)
        rn = requests.get(f"{API}/notifications", headers=_auth_headers(a["token"]))
        assert rn.status_code == 200
        assert any(n["type"] == "friend_going" and n["data"].get("event_id") == eid
                   for n in rn.json())

        # Unread count > 0
        ru = requests.get(f"{API}/notifications/unread-count", headers=_auth_headers(a["token"]))
        assert ru.status_code == 200 and ru.json()["count"] >= 1

        # Toggle to me_interesa (mutually exclusive)
        r4 = requests.post(f"{API}/events/{eid}/interest",
                           headers=_auth_headers(b["token"]),
                           json={"status": "me_interesa"})
        assert r4.status_code == 200 and r4.json()["status"] == "me_interesa"
        r5 = requests.get(f"{API}/events/{eid}", headers=_auth_headers(a["token"]))
        d5 = r5.json()
        assert all(f["user_id"] != b["user"]["user_id"] for f in d5["friends_going"])
        assert any(f["user_id"] == b["user"]["user_id"] for f in d5["friends_interested"])

        # Unmark
        r6 = requests.post(f"{API}/events/{eid}/interest",
                           headers=_auth_headers(b["token"]),
                           json={"status": "none"})
        assert r6.status_code == 200
        r7 = requests.get(f"{API}/events/{eid}", headers=_auth_headers(a["token"]))
        d7 = r7.json()
        assert all(f["user_id"] != b["user"]["user_id"] for f in d7["friends_going"])
        assert all(f["user_id"] != b["user"]["user_id"] for f in d7["friends_interested"])

    def test_persistence_across_requests(self, user_a):
        eid = self._first_event_id(user_a["token"])
        # set voy
        requests.post(f"{API}/events/{eid}/interest",
                      headers=_auth_headers(user_a["token"]),
                      json={"status": "voy"})
        # fresh session (re-login)
        s = _client()
        tok = _login(s, user_a["email"], user_a["password"]).json()["token"]
        r = requests.get(f"{API}/events/{eid}", headers=_auth_headers(tok))
        assert r.json()["my_status"] == "voy"
        # cleanup
        requests.post(f"{API}/events/{eid}/interest",
                      headers=_auth_headers(user_a["token"]),
                      json={"status": "none"})
