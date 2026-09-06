"""Backend tests for the 'Monta tu grupo' viral loop (Fase A).

Covers:
 - POST /api/groups (create group)
 - GET /api/groups/{id}/invite (returns {code, group_name, url})
 - POST /api/me/claim-group-invite (auto-join + auto-friend + notifications)
 - Idempotency: claim twice -> already_member=true
 - Security: 403 for non-members on invite, 404 for unknown code
"""
import os
import uuid
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback: read frontend/.env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")


def _register(suffix: str) -> dict:
    """Register a fresh user and return {token, user_id, name, email}."""
    unique = f"{int(time.time()*1000)}_{suffix}_{uuid.uuid4().hex[:6]}"
    email = f"TEST_viral_{unique}@example.com"
    username = f"tviral{unique[-10:]}".lower()
    payload = {
        "email": email,
        "password": "TestPass2026!",
        "name": f"Viral{suffix}",
        "username": username,
        "city": "Palma de Mallorca",
        "birthdate": "2000-01-01",
    }
    r = requests.post(f"{BASE_URL}/api/auth/register", json=payload, timeout=30)
    assert r.status_code in (200, 201), f"register failed {r.status_code}: {r.text}"
    data = r.json()
    token = data.get("token") or data.get("access_token")
    assert token, f"no token in response: {data}"
    user = data.get("user") or {}
    return {
        "token": token,
        "user_id": user.get("id") or user.get("user_id"),
        "name": user.get("name", payload["name"]),
        "email": email,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture(scope="module")
def user_a():
    return _register("A")


@pytest.fixture(scope="module")
def user_b():
    return _register("B")


@pytest.fixture(scope="module")
def user_c():
    """Third user, non-member of A's group, for the 403 check."""
    return _register("C")


@pytest.fixture(scope="module")
def group_a(user_a):
    """Group created by user_a with only themselves."""
    r = requests.post(
        f"{BASE_URL}/api/groups",
        json={"name": "TEST_ViralGroup", "picture": "", "member_ids": []},
        headers=user_a["headers"], timeout=30,
    )
    assert r.status_code == 200, f"create group: {r.status_code} {r.text}"
    g = r.json()
    assert "id" in g and g["name"] == "TEST_ViralGroup"
    assert user_a["user_id"] in g["member_ids"]
    return g


# --- POST /api/groups ---------------------------------------------------------
class TestCreateGroup:
    def test_create_group_persists(self, user_a, group_a):
        r = requests.get(f"{BASE_URL}/api/groups", headers=user_a["headers"], timeout=30)
        assert r.status_code == 200
        groups = r.json()
        assert any(g["id"] == group_a["id"] for g in groups)


# --- GET /api/groups/{id}/invite ---------------------------------------------
class TestInviteLink:
    def test_invite_link_shape(self, user_a, group_a):
        r = requests.get(
            f"{BASE_URL}/api/groups/{group_a['id']}/invite",
            headers=user_a["headers"], timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "code" in data and isinstance(data["code"], str) and len(data["code"]) >= 4
        assert data["group_name"] == "TEST_ViralGroup"
        assert data["url"] == f"https://quienva.me/?g={data['code']}"

    def test_invite_forbidden_for_non_member(self, user_c, group_a):
        r = requests.get(
            f"{BASE_URL}/api/groups/{group_a['id']}/invite",
            headers=user_c["headers"], timeout=30,
        )
        assert r.status_code in (403, 404), f"expected 403/404 got {r.status_code}: {r.text}"


# --- POST /api/me/claim-group-invite -----------------------------------------
class TestClaimViralLoop:
    def test_claim_full_flow(self, user_a, user_b, group_a):
        # A gets code
        r = requests.get(
            f"{BASE_URL}/api/groups/{group_a['id']}/invite",
            headers=user_a["headers"], timeout=30,
        )
        code = r.json()["code"]

        # B claims
        r = requests.post(
            f"{BASE_URL}/api/me/claim-group-invite",
            json={"code": code},
            headers=user_b["headers"], timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert data.get("already_member") is not True

        # (a) B sees the group with member_ids includes A + B (size >=2)
        r = requests.get(f"{BASE_URL}/api/groups", headers=user_b["headers"], timeout=30)
        assert r.status_code == 200
        groups_b = r.json()
        target = next((g for g in groups_b if g["id"] == group_a["id"]), None)
        assert target is not None, "B did not auto-join the group"
        assert user_a["user_id"] in target["member_ids"]
        assert user_b["user_id"] in target["member_ids"]
        assert len(target["member_ids"]) >= 2

        # (b) B has A as accepted friend
        r = requests.get(f"{BASE_URL}/api/friends", headers=user_b["headers"], timeout=30)
        assert r.status_code == 200, r.text
        friends = r.json()
        # Friends payload can be list of users or wrapped dict
        friends_list = friends if isinstance(friends, list) else friends.get("friends", [])
        friend_ids = [f.get("user_id") or f.get("id") for f in friends_list]
        assert user_a["user_id"] in friend_ids, f"A not in B's friends: {friends_list}"

        # (c) A's notifications contain 'se ha unido a tu grupo'
        r = requests.get(f"{BASE_URL}/api/notifications", headers=user_a["headers"], timeout=30)
        assert r.status_code == 200
        notifs_a = r.json()
        notifs_a_list = notifs_a if isinstance(notifs_a, list) else notifs_a.get("items", [])
        texts_a = " || ".join(str(n.get("text", "") or n.get("message", "")) for n in notifs_a_list)
        assert "se ha unido a tu grupo" in texts_a, f"A missing join notif: {texts_a}"

        # (d) B's notifications contain 'te ha añadido a su grupo'
        r = requests.get(f"{BASE_URL}/api/notifications", headers=user_b["headers"], timeout=30)
        assert r.status_code == 200
        notifs_b = r.json()
        notifs_b_list = notifs_b if isinstance(notifs_b, list) else notifs_b.get("items", [])
        texts_b = " || ".join(str(n.get("text", "") or n.get("message", "")) for n in notifs_b_list)
        assert "te ha añadido a su grupo" in texts_b, f"B missing added-to notif: {texts_b}"

    def test_claim_idempotent(self, user_a, user_b, group_a):
        # Second claim from B => already_member=true, no duplicates
        r = requests.get(
            f"{BASE_URL}/api/groups/{group_a['id']}/invite",
            headers=user_a["headers"], timeout=30,
        )
        code = r.json()["code"]

        r = requests.post(
            f"{BASE_URL}/api/me/claim-group-invite",
            json={"code": code},
            headers=user_b["headers"], timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("already_member") is True

        # Ensure no duplicate membership
        r = requests.get(f"{BASE_URL}/api/groups", headers=user_b["headers"], timeout=30)
        target = next(g for g in r.json() if g["id"] == group_a["id"])
        assert target["member_ids"].count(user_b["user_id"]) == 1

    def test_claim_unknown_code_404(self, user_c):
        r = requests.post(
            f"{BASE_URL}/api/me/claim-group-invite",
            json={"code": "ZZNOEXIST"},
            headers=user_c["headers"], timeout=30,
        )
        assert r.status_code == 404, f"expected 404 got {r.status_code}: {r.text}"
