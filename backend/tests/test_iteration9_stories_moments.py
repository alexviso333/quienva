"""Iteration 9 — Moments-as-Stories integration.

Verifies:
- GET /api/stories includes friend + self moment items with kind='moment' (<=24h).
- Non-friends (sara, tourist) are NOT in admin's /api/stories.
- POST /api/captures/{id}/like toggles like and reflects in /api/stories.
- Regression: POST /api/stories creates kind='story' story, react + delete still work.
"""
import io
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@quienva.app", "password": "admin123"}


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_token():
    return _login(**ADMIN)


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---------- moments-as-stories ----------

def test_stories_include_friend_moments(admin_headers):
    r = requests.get(f"{API}/stories", headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text
    items = r.json()
    assert isinstance(items, list)
    moments = [i for i in items if i.get("kind") == "moment"]
    assert len(moments) >= 4, f"expected >=4 moment items (lucia+marc x2), got {len(moments)}: {[m.get('author') for m in moments]}"
    usernames = {m["author"]["username"] for m in moments}
    assert "lucia" in usernames and "marc" in usernames
    # sara + tourist are NOT friends of admin -> must NOT appear
    assert "sara" not in usernames
    assert "tourist" not in usernames
    # required fields
    for m in moments:
        assert "id" in m and "image_url" in m and "created_at" in m
        assert "likes" in m and isinstance(m["likes"], int)
        assert "i_liked" in m and isinstance(m["i_liked"], bool)
        assert "is_mine" in m
        assert "event_name" in m  # nullable ok
        assert m["author"]["username"]


def test_stories_kind_field_present_for_real_stories(admin_headers):
    r = requests.get(f"{API}/stories", headers=admin_headers, timeout=30)
    assert r.status_code == 200
    for it in r.json():
        assert it.get("kind") in ("story", "moment")


# ---------- like toggle ----------

def test_like_capture_reflects_in_stories(admin_headers):
    r = requests.get(f"{API}/stories", headers=admin_headers, timeout=30)
    moments = [i for i in r.json() if i.get("kind") == "moment"]
    assert moments
    target = moments[0]
    cap_id = target["id"]
    initial_likes = target["likes"]
    initial_liked = target["i_liked"]

    # toggle 1
    lr = requests.post(f"{API}/captures/{cap_id}/like", headers=admin_headers, timeout=30)
    assert lr.status_code == 200, lr.text

    r2 = requests.get(f"{API}/stories", headers=admin_headers, timeout=30)
    m2 = next(i for i in r2.json() if i.get("kind") == "moment" and i["id"] == cap_id)
    assert m2["i_liked"] != initial_liked
    assert m2["likes"] == initial_likes + (1 if not initial_liked else -1)

    # toggle back to restore
    lr2 = requests.post(f"{API}/captures/{cap_id}/like", headers=admin_headers, timeout=30)
    assert lr2.status_code == 200
    r3 = requests.get(f"{API}/stories", headers=admin_headers, timeout=30)
    m3 = next(i for i in r3.json() if i.get("kind") == "moment" and i["id"] == cap_id)
    assert m3["i_liked"] == initial_liked
    assert m3["likes"] == initial_likes


# ---------- regression: real stories ----------

def _tiny_png_bytes():
    # 1x1 transparent PNG
    import base64
    return base64.b64decode(
        b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNgAAIAAAUAAeImBZsAAAAASUVORK5CYII="
    )


def test_regression_create_react_delete_story(admin_headers):
    files = {"file": ("t.png", _tiny_png_bytes(), "image/png")}
    data = {"caption": "TEST_regression_story"}
    cr = requests.post(f"{API}/stories", headers=admin_headers, files=files, data=data, timeout=30)
    assert cr.status_code == 200, cr.text
    story = cr.json()
    sid = story["id"]

    lr = requests.get(f"{API}/stories", headers=admin_headers, timeout=30)
    assert lr.status_code == 200
    stories_kind = [i for i in lr.json() if i.get("kind") == "story" and i.get("id") == sid]
    assert stories_kind, "created story not visible in /api/stories with kind='story'"

    # react to own story (admin viewing own story allowed)
    rr = requests.post(f"{API}/stories/{sid}/react", headers=admin_headers, json={"content": "hola"}, timeout=30)
    assert rr.status_code == 200, rr.text

    dr = requests.delete(f"{API}/stories/{sid}", headers=admin_headers, timeout=30)
    assert dr.status_code in (200, 204)

    lr2 = requests.get(f"{API}/stories", headers=admin_headers, timeout=30)
    assert not any(i.get("id") == sid and i.get("kind") == "story" for i in lr2.json())
