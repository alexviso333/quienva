"""Iteration 2 backend tests: invite-by-username, weekly digest, push endpoints,
and regression on duplicate friend request no longer 400-ing.
"""
import os
import uuid
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.strip().split("=", 1)[1].rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "QuienVa2026!"


def _headers(tok):
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


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)["token"]


@pytest.fixture(scope="module")
def inviter():
    """A user who will be invited to (target of invite)."""
    uniq = uuid.uuid4().hex[:8]
    email = f"test_inv_{uniq}@test.com"
    data = _register(email, f"invitee{uniq}")
    return {"token": data["token"], "user": data["user"], "email": email}


class TestInviteByUsername:
    def test_request_by_username_success(self, inviter):
        # brand new user registers, then sends request-by-username to inviter
        uniq = uuid.uuid4().hex[:8]
        newu = _register(f"test_new_{uniq}@test.com", f"newu{uniq}")
        r = requests.post(f"{API}/friends/request-by-username",
                          headers=_headers(newu["token"]),
                          json={"username": inviter["user"]["username"]})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] in ("pending", "accepted")
        assert "user" in data and data["user"]["username"] == inviter["user"]["username"]

        # inviter has a friend_request notification (or friendship exists)
        rn = requests.get(f"{API}/notifications", headers=_headers(inviter["token"]))
        assert rn.status_code == 200
        assert any(n["type"] == "friend_request"
                   and n["data"].get("user_id") == newu["user"]["user_id"]
                   for n in rn.json())

    def test_request_by_username_unknown(self, inviter):
        r = requests.post(f"{API}/friends/request-by-username",
                          headers=_headers(inviter["token"]),
                          json={"username": "no_such_user_" + uuid.uuid4().hex[:6]})
        assert r.status_code == 404

    def test_duplicate_friend_request_no_400(self):
        """Regression: sending a request to someone you're already friends with must NOT 400."""
        uniq = uuid.uuid4().hex[:8]
        a = _register(f"test_dup_a_{uniq}@test.com", f"dupa{uniq}")
        b = _register(f"test_dup_b_{uniq}@test.com", f"dupb{uniq}")
        # a → b
        r1 = requests.post(f"{API}/friends/request", headers=_headers(a["token"]),
                           json={"user_id": b["user"]["user_id"]})
        assert r1.status_code == 200
        # b accepts
        rr = requests.get(f"{API}/friends/requests", headers=_headers(b["token"]))
        req_id = [x for x in rr.json() if x["user"]["user_id"] == a["user"]["user_id"]][0]["request_id"]
        requests.post(f"{API}/friends/respond", headers=_headers(b["token"]),
                      json={"request_id": req_id, "accept": True})
        # a → b again (already accepted) — must be 200 with status accepted
        r2 = requests.post(f"{API}/friends/request", headers=_headers(a["token"]),
                           json={"user_id": b["user"]["user_id"]})
        assert r2.status_code == 200, r2.text
        assert r2.json()["status"] == "accepted"
        # also via username
        r3 = requests.post(f"{API}/friends/request-by-username", headers=_headers(a["token"]),
                           json={"username": b["user"]["username"]})
        assert r3.status_code == 200
        assert r3.json()["status"] == "accepted"


class TestWeeklyDigest:
    def test_trigger_requires_admin(self, inviter):
        r = requests.post(f"{API}/admin/trigger-weekly-digest",
                          headers=_headers(inviter["token"]))
        assert r.status_code == 403

    def test_trigger_creates_digest(self, admin_token):
        # Set up: A & B friends, B marks voy on the nearest event (within 7 days ideally,
        # but seed events may all be far in future — we just verify endpoint returns and
        # that when a plan exists in-window, the notification is created).
        uniq = uuid.uuid4().hex[:8]
        a = _register(f"test_wd_a_{uniq}@test.com", f"wda{uniq}")
        b = _register(f"test_wd_b_{uniq}@test.com", f"wdb{uniq}")
        # friend up
        requests.post(f"{API}/friends/request", headers=_headers(a["token"]),
                      json={"user_id": b["user"]["user_id"]})
        rr = requests.get(f"{API}/friends/requests", headers=_headers(b["token"]))
        req_id = [x for x in rr.json() if x["user"]["user_id"] == a["user"]["user_id"]][0]["request_id"]
        requests.post(f"{API}/friends/respond", headers=_headers(b["token"]),
                      json={"request_id": req_id, "accept": True})

        # Admin creates a fresh event within the next 7 days
        from datetime import date, timedelta
        d = (date.today() + timedelta(days=3)).isoformat()
        payload = {
            "name": "TEST_WD_" + uniq, "venue": "V", "address": "Palma",
            "date": d, "time": "22:00", "genre": "Techno", "image_url": "",
            "has_commission": False, "commission_url": "", "more_info_url": "",
        }
        rc = requests.post(f"{API}/admin/events", headers=_headers(admin_token), json=payload)
        assert rc.status_code == 200, rc.text
        eid = rc.json()["id"]

        # B marks voy
        ri = requests.post(f"{API}/events/{eid}/interest", headers=_headers(b["token"]),
                           json={"status": "voy"})
        assert ri.status_code == 200

        # Trigger digest
        rt = requests.post(f"{API}/admin/trigger-weekly-digest", headers=_headers(admin_token))
        assert rt.status_code == 200
        assert rt.json()["sent"] >= 1

        # A receives a weekly_digest notification
        time.sleep(0.5)
        rn = requests.get(f"{API}/notifications", headers=_headers(a["token"]))
        assert rn.status_code == 200
        digests = [n for n in rn.json() if n["type"] == "weekly_digest"]
        assert len(digests) >= 1
        assert "esta semana" in digests[0]["message"]

        # cleanup
        requests.delete(f"{API}/admin/events/{eid}", headers=_headers(admin_token))


class TestPushEndpoints:
    def test_vapid_public_key(self, inviter):
        # public key endpoint (auth optional in some designs — server has no Depends)
        r = requests.get(f"{API}/push/vapid-public-key")
        assert r.status_code == 200
        assert "publicKey" in r.json()

    def test_status_requires_auth(self):
        r = requests.get(f"{API}/push/status")
        assert r.status_code == 401

    def test_status_authed(self, inviter):
        r = requests.get(f"{API}/push/status", headers=_headers(inviter["token"]))
        assert r.status_code == 200
        assert "subscribed" in r.json()
        assert isinstance(r.json()["subscribed"], bool)

    def test_subscribe_and_status_and_unsubscribe(self, inviter):
        endpoint = f"https://example.com/push/{uuid.uuid4().hex}"
        payload = {"endpoint": endpoint, "keys": {"p256dh": "abc", "auth": "def"}}
        r = requests.post(f"{API}/push/subscribe", headers=_headers(inviter["token"]), json=payload)
        assert r.status_code == 200 and r.json().get("ok") is True

        r2 = requests.get(f"{API}/push/status", headers=_headers(inviter["token"]))
        assert r2.json()["subscribed"] is True

        r3 = requests.post(f"{API}/push/unsubscribe", headers=_headers(inviter["token"]), json=payload)
        assert r3.status_code == 200

    def test_subscribe_requires_auth(self):
        r = requests.post(f"{API}/push/subscribe",
                          json={"endpoint": "x", "keys": {"p256dh": "a", "auth": "b"}})
        assert r.status_code == 401
