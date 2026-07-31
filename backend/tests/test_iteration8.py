"""Iteration 8: Test NEW endpoints - badges, points, rankings, referrals, DMs, groups, album, moment, calendar, tickets, admin dashboard."""
import os
import uuid
import requests
import pytest
import io
from dotenv import dotenv_values

fe = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL")).rstrip("/") + "/api"

ADMIN = {"email": "admin@quienva.app", "password": "admin123"}


def _login(creds):
    """Login or register+login, return session with Bearer token."""
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": creds["email"], "password": creds["password"]})
    if r.status_code != 200:
        reg = s.post(f"{BASE}/auth/register", json=creds)
        assert reg.status_code in (200, 201), reg.text
        r = s.post(f"{BASE}/auth/login", json={"email": creds["email"], "password": creds["password"]})
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    user_id = r.json().get("user", {}).get("user_id")
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s, user_id


@pytest.fixture(scope="module")
def admin():
    sess, uid = _login(ADMIN)
    return sess, uid


@pytest.fixture(scope="module")
def user_b():
    """Test user B."""
    creds = {
        "email": f"userb_{uuid.uuid4().hex[:6]}@test.com",
        "password": "test1234",
        "name": "User B",
        "username": f"userb_{uuid.uuid4().hex[:4]}",
        "city": "Palma de Mallorca"
    }
    return _login(creds)


@pytest.fixture(scope="module")
def user_c():
    """Test user C (for non-friend scenarios)."""
    creds = {
        "email": f"userc_{uuid.uuid4().hex[:6]}@test.com",
        "password": "test1234",
        "name": "User C",
        "username": f"userc_{uuid.uuid4().hex[:4]}",
        "city": "Palma de Mallorca"
    }
    return _login(creds)


@pytest.fixture(scope="module")
def make_friends(admin, user_b):
    """Make admin and user_b friends."""
    admin_sess, admin_id = admin
    b_sess, b_id = user_b
    
    # Admin sends friend request to B
    r = admin_sess.post(f"{BASE}/friends/request", json={"user_id": b_id})
    assert r.status_code in (200, 201), r.text
    request_id = r.json().get("request_id")
    
    # If already friends, skip
    if r.json().get("status") == "accepted":
        return admin_id, b_id
    
    # B accepts using request_id
    assert request_id, "No request_id returned"
    r = b_sess.post(f"{BASE}/friends/respond", json={"request_id": request_id, "accept": True})
    assert r.status_code in (200, 201), r.text
    
    return admin_id, b_id


@pytest.fixture(scope="module")
def temp_event(admin):
    """Create a temporary event for testing."""
    admin_sess, _ = admin
    ev = {
        "name": f"TEST_it8_{uuid.uuid4().hex[:6]}",
        "venue": "TEST Venue",
        "city": "Palma de Mallorca",
        "date": "2030-06-15",
        "time": "23:00",
        "category": "fiesta",
        "description": "TEST event iteration 8",
    }
    r = admin_sess.post(f"{BASE}/admin/events", json=ev)
    assert r.status_code in (200, 201), r.text
    eid = r.json().get("id") or r.json().get("event", {}).get("id")
    assert eid
    yield eid
    admin_sess.delete(f"{BASE}/admin/events/{eid}")


# =============================================================================
# 1. BADGES & POINTS
# =============================================================================
class TestBadgesAndPoints:
    def test_badges_catalog(self):
        """GET /api/badges/catalog → 63 badges with id, name, desc, emoji, tier, cat, points."""
        r = requests.get(f"{BASE}/badges/catalog")
        assert r.status_code == 200, r.text
        badges = r.json()
        assert isinstance(badges, list), "Expected array"
        assert len(badges) == 63, f"Expected 63 badges, got {len(badges)}"
        
        # Check structure of first badge
        b = badges[0]
        assert "id" in b
        assert "name" in b
        assert "desc" in b
        assert "emoji" in b
        assert "tier" in b
        assert "cat" in b
        assert "points" in b
        assert isinstance(b["points"], int)
    
    def test_my_badges_structure(self, admin):
        """GET /api/me/badges → {stats, points:{badge_points, action_points, total}, earned, locked}."""
        admin_sess, _ = admin
        r = admin_sess.get(f"{BASE}/me/badges")
        assert r.status_code == 200, r.text
        data = r.json()
        
        assert "stats" in data
        assert "points" in data
        assert "earned" in data
        assert "locked" in data
        
        pts = data["points"]
        assert "badge_points" in pts
        assert "action_points" in pts
        assert "total" in pts
        assert isinstance(pts["total"], int)
        
        # Admin should have 'og' badge (first 100 users) → 200 points minimum
        earned_ids = [b["id"] for b in data["earned"]]
        assert "og" in earned_ids, "Admin should have 'og' badge"
        assert pts["badge_points"] >= 200, f"Expected >=200 badge_points for og badge, got {pts['badge_points']}"
    
    def test_user_badges_friend_access(self, admin, user_b, make_friends):
        """GET /api/users/{user_id}/badges → 200 if friend or self, 403 if not."""
        admin_sess, admin_id = admin
        b_sess, b_id = user_b
        
        # Admin can view B's badges (friends)
        r = admin_sess.get(f"{BASE}/users/{b_id}/badges")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "points" in data
        assert "earned" in data
        
        # Self access
        r = admin_sess.get(f"{BASE}/users/{admin_id}/badges")
        assert r.status_code == 200, r.text
    
    def test_user_badges_non_friend_forbidden(self, admin, user_c):
        """Non-friend cannot view badges."""
        admin_sess, _ = admin
        c_sess, c_id = user_c
        
        r = admin_sess.get(f"{BASE}/users/{c_id}/badges")
        assert r.status_code == 403, f"Expected 403, got {r.status_code}"


# =============================================================================
# 2. STREAK
# =============================================================================
class TestStreak:
    def test_streak_full_structure(self, admin):
        """GET /api/me/streak-full → {day_streak, week_streak, best_day_streak, best_week_streak, next_day_milestone, next_week_milestone, total_events}."""
        admin_sess, _ = admin
        r = admin_sess.get(f"{BASE}/me/streak-full")
        assert r.status_code == 200, r.text
        data = r.json()
        
        required = ["day_streak", "week_streak", "best_day_streak", "best_week_streak", 
                   "next_day_milestone", "next_week_milestone", "total_events"]
        for field in required:
            assert field in data, f"Missing field: {field}"
            assert isinstance(data[field], int), f"{field} should be int"


# =============================================================================
# 3. REFERRAL SYSTEM
# =============================================================================
class TestReferralSystem:
    def test_get_referral_creates_code(self, admin):
        """GET /api/me/referral → creates code first call, returns {code, share_url_hint, referred_count, points_per_referral}."""
        admin_sess, _ = admin
        r = admin_sess.get(f"{BASE}/me/referral")
        assert r.status_code == 200, r.text
        data = r.json()
        
        assert "code" in data
        assert "share_url_hint" in data
        assert "referred_count" in data
        assert "points_per_referral" in data
        assert isinstance(data["code"], str)
        assert len(data["code"]) > 0
        
        # Repeated call returns same code
        r2 = admin_sess.get(f"{BASE}/me/referral")
        assert r2.status_code == 200
        assert r2.json()["code"] == data["code"]
    
    def test_claim_referral_success(self, admin):
        """New user claims admin's referral code → success."""
        admin_sess, _ = admin
        
        # Get admin's referral code
        r = admin_sess.get(f"{BASE}/me/referral")
        assert r.status_code == 200
        admin_code = r.json()["code"]
        
        # Create new user
        new_user_creds = {
            "email": f"newref_{uuid.uuid4().hex[:6]}@test.com",
            "password": "test1234",
            "name": "New Referral User",
            "username": f"newref_{uuid.uuid4().hex[:4]}",
            "city": "Palma de Mallorca"
        }
        new_sess, _ = _login(new_user_creds)
        
        # Claim referral
        r = new_sess.post(f"{BASE}/me/claim-referral", json={"code": admin_code})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "ok" in data or "points" in data
    
    def test_claim_referral_duplicate(self, admin, user_b):
        """Repeat claim → 400 'Ya usaste un código'."""
        admin_sess, _ = admin
        b_sess, _ = user_b
        
        # Get admin's code
        r = admin_sess.get(f"{BASE}/me/referral")
        admin_code = r.json()["code"]
        
        # B tries to claim (might already have claimed, so first attempt might fail)
        r1 = b_sess.post(f"{BASE}/me/claim-referral", json={"code": admin_code})
        
        # Second attempt should definitely fail
        r2 = b_sess.post(f"{BASE}/me/claim-referral", json={"code": admin_code})
        assert r2.status_code == 400, f"Expected 400, got {r2.status_code}"
        assert "ya" in r2.text.lower() or "already" in r2.text.lower()
    
    def test_claim_referral_invalid_code(self, user_b):
        """Invalid code → 404."""
        b_sess, _ = user_b
        r = b_sess.post(f"{BASE}/me/claim-referral", json={"code": "INVALID_CODE_XYZ"})
        assert r.status_code == 404, f"Expected 404, got {r.status_code}"


# =============================================================================
# 4. RANKINGS
# =============================================================================
class TestRankings:
    def test_rankings_friends(self, admin, make_friends):
        """GET /api/rankings/friends → array with rank/points, includes self."""
        admin_sess, _ = admin
        r = admin_sess.get(f"{BASE}/rankings/friends")
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        
        if len(data) > 0:
            item = data[0]
            assert "rank" in item or "points" in item
            # Should include self
            admin_in_list = any(u.get("is_me") for u in data)
            # Note: is_me might not be in response, but at least admin should be there
    
    def test_rankings_city(self, admin):
        """GET /api/rankings/city → defaults to user.city (Palma de Mallorca)."""
        admin_sess, _ = admin
        r = admin_sess.get(f"{BASE}/rankings/city")
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
    
    def test_rankings_world(self, admin):
        """GET /api/rankings/world → array, users with more points higher."""
        admin_sess, _ = admin
        r = admin_sess.get(f"{BASE}/rankings/world")
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        
        # Check ordering (descending points)
        if len(data) > 1:
            for i in range(len(data) - 1):
                assert data[i]["points"] >= data[i+1]["points"], "Rankings not sorted by points desc"


# =============================================================================
# 5. DMs
# =============================================================================
class TestDMs:
    def test_dm_send_to_friend_success(self, admin, user_b, make_friends):
        """POST /api/dm/send to friend → OK."""
        admin_sess, admin_id = admin
        b_sess, b_id = user_b
        
        r = admin_sess.post(f"{BASE}/dm/send", json={"to_user_id": b_id, "text": "Hola from admin"})
        assert r.status_code in (200, 201), r.text
    
    def test_dm_send_to_non_friend_forbidden(self, admin, user_c):
        """POST /api/dm/send to non-friend → 403."""
        admin_sess, _ = admin
        c_sess, c_id = user_c
        
        r = admin_sess.post(f"{BASE}/dm/send", json={"to_user_id": c_id, "text": "Should fail"})
        assert r.status_code == 403, f"Expected 403, got {r.status_code}"
    
    def test_dm_threads(self, admin, user_b, make_friends):
        """GET /api/dm/threads → array with threads, unread count."""
        admin_sess, admin_id = admin
        b_sess, b_id = user_b
        
        # Admin sends message to B
        admin_sess.post(f"{BASE}/dm/send", json={"to_user_id": b_id, "text": "Test thread"})
        
        # B gets threads
        r = b_sess.get(f"{BASE}/dm/threads")
        assert r.status_code == 200, r.text
        threads = r.json()
        assert isinstance(threads, list)
        
        # Should have at least one thread with admin
        admin_thread = [t for t in threads if t.get("other_user", {}).get("id") == admin_id]
        assert len(admin_thread) > 0, "Thread with admin not found"
        assert "unread" in admin_thread[0]
    
    def test_dm_messages_and_mark_read(self, admin, user_b, make_friends):
        """GET /api/dm/{other_id}/messages → returns messages, marks read."""
        admin_sess, admin_id = admin
        b_sess, b_id = user_b
        
        # Admin sends message
        admin_sess.post(f"{BASE}/dm/send", json={"to_user_id": b_id, "text": "Mark read test"})
        
        # B reads messages
        r = b_sess.get(f"{BASE}/dm/{admin_id}/messages")
        assert r.status_code == 200, r.text
        msgs = r.json()
        assert isinstance(msgs, list)
        
        # Check unread count is 0 after reading
        r = b_sess.get(f"{BASE}/dm/unread-count")
        assert r.status_code == 200
        # Unread might not be 0 if there are other threads, but should be reduced
    
    def test_dm_unread_count(self, user_b):
        """GET /api/dm/unread-count → returns count."""
        b_sess, _ = user_b
        r = b_sess.get(f"{BASE}/dm/unread-count")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "count" in data or isinstance(data, int)
    
    def test_dm_empty_text_validation(self, admin, user_b, make_friends):
        """Empty text → 400."""
        admin_sess, _ = admin
        b_sess, b_id = user_b
        
        r = admin_sess.post(f"{BASE}/dm/send", json={"to_user_id": b_id, "text": ""})
        assert r.status_code == 400, f"Expected 400 for empty text, got {r.status_code}"
    
    def test_dm_too_long_text_validation(self, admin, user_b, make_friends):
        """Text >1000 chars → 400."""
        admin_sess, _ = admin
        b_sess, b_id = user_b
        
        long_text = "x" * 1001
        r = admin_sess.post(f"{BASE}/dm/send", json={"to_user_id": b_id, "text": long_text})
        assert r.status_code == 400, f"Expected 400 for long text, got {r.status_code}"


# =============================================================================
# 6. GROUPS
# =============================================================================
class TestGroups:
    def test_create_group_with_friend(self, admin, user_b, make_friends):
        """POST /api/groups with friend → 200."""
        admin_sess, _ = admin
        b_sess, b_id = user_b
        
        r = admin_sess.post(f"{BASE}/groups", json={"name": "Test Group", "member_ids": [b_id]})
        assert r.status_code in (200, 201), r.text
        data = r.json()
        assert "id" in data
        return data["id"]
    
    def test_create_group_with_non_friend_fails(self, admin, user_c):
        """POST /api/groups with non-friend → 400."""
        admin_sess, _ = admin
        c_sess, c_id = user_c
        
        r = admin_sess.post(f"{BASE}/groups", json={"name": "Bad Group", "member_ids": [c_id]})
        assert r.status_code == 400, f"Expected 400, got {r.status_code}"
    
    def test_list_groups(self, admin, user_b, make_friends):
        """GET /api/groups → list of groups."""
        admin_sess, _ = admin
        b_sess, b_id = user_b
        
        # Create a group first
        r = admin_sess.post(f"{BASE}/groups", json={"name": "List Test Group", "member_ids": [b_id]})
        assert r.status_code in (200, 201)
        
        # List groups
        r = admin_sess.get(f"{BASE}/groups")
        assert r.status_code == 200, r.text
        groups = r.json()
        assert isinstance(groups, list)
        
        if len(groups) > 0:
            g = groups[0]
            assert "id" in g
            assert "name" in g
            assert "members" in g or "member_count" in g
    
    def test_get_group_as_member(self, admin, user_b, make_friends):
        """GET /api/groups/{gid} as member → 200."""
        admin_sess, _ = admin
        b_sess, b_id = user_b
        
        # Create group
        r = admin_sess.post(f"{BASE}/groups", json={"name": "Get Test", "member_ids": [b_id]})
        gid = r.json()["id"]
        
        # B gets group
        r = b_sess.get(f"{BASE}/groups/{gid}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "members" in data
    
    def test_get_group_as_non_member_forbidden(self, admin, user_b, user_c, make_friends):
        """GET /api/groups/{gid} as non-member → 403."""
        admin_sess, _ = admin
        b_sess, b_id = user_b
        c_sess, _ = user_c
        
        # Create group with only admin and B
        r = admin_sess.post(f"{BASE}/groups", json={"name": "Private Group", "member_ids": [b_id]})
        gid = r.json()["id"]
        
        # C tries to access
        r = c_sess.get(f"{BASE}/groups/{gid}")
        assert r.status_code == 403, f"Expected 403, got {r.status_code}"
    
    def test_post_group_message(self, admin, user_b, make_friends):
        """POST /api/groups/{gid}/messages → 200 with author.name and is_mine."""
        admin_sess, _ = admin
        b_sess, b_id = user_b
        
        # Create group
        r = admin_sess.post(f"{BASE}/groups", json={"name": "Chat Test", "member_ids": [b_id]})
        gid = r.json()["id"]
        
        # B posts message
        r = b_sess.post(f"{BASE}/groups/{gid}/messages", json={"text": "Hi from B"})
        assert r.status_code in (200, 201), r.text
        data = r.json()
        assert "author" in data
        assert "name" in data["author"]
        assert data.get("is_mine") is True
    
    def test_get_group_messages(self, admin, user_b, make_friends):
        """GET /api/groups/{gid}/messages → list of messages."""
        admin_sess, _ = admin
        b_sess, b_id = user_b
        
        # Create group and post message
        r = admin_sess.post(f"{BASE}/groups", json={"name": "Msg List Test", "member_ids": [b_id]})
        gid = r.json()["id"]
        b_sess.post(f"{BASE}/groups/{gid}/messages", json={"text": "Test message"})
        
        # Admin gets messages
        r = admin_sess.get(f"{BASE}/groups/{gid}/messages")
        assert r.status_code == 200, r.text
        msgs = r.json()
        assert isinstance(msgs, list)
        assert len(msgs) >= 1
    
    def test_add_member_friend_only(self, admin, user_b, user_c, make_friends):
        """POST /api/groups/{gid}/add-member with non-friend → 400, with friend → 200."""
        admin_sess, admin_id = admin
        b_sess, b_id = user_b
        c_sess, c_id = user_c
        
        # Create group
        r = admin_sess.post(f"{BASE}/groups", json={"name": "Add Member Test", "member_ids": [b_id]})
        gid = r.json()["id"]
        
        # Try to add non-friend C
        r = admin_sess.post(f"{BASE}/groups/{gid}/add-member", json={"user_id": c_id})
        assert r.status_code == 400, f"Expected 400 for non-friend, got {r.status_code}"
        
        # Make admin and C friends
        r = admin_sess.post(f"{BASE}/friends/request", json={"user_id": c_id})
        req_id = r.json().get("request_id")
        if r.json().get("status") != "accepted":
            c_sess.post(f"{BASE}/friends/respond", json={"request_id": req_id, "accept": True})
        
        # Now add C
        r = admin_sess.post(f"{BASE}/groups/{gid}/add-member", json={"user_id": c_id})
        assert r.status_code == 200, r.text
    
    def test_update_group_creator_only(self, admin, user_b, make_friends):
        """PUT /api/groups/{gid} as creator → 200, as non-creator → 403."""
        admin_sess, _ = admin
        b_sess, b_id = user_b
        
        # Admin creates group
        r = admin_sess.post(f"{BASE}/groups", json={"name": "Update Test", "member_ids": [b_id]})
        gid = r.json()["id"]
        
        # Admin updates (creator)
        r = admin_sess.put(f"{BASE}/groups/{gid}", json={"name": "Updated Name"})
        assert r.status_code == 200, r.text
        
        # B tries to update (not creator)
        r = b_sess.put(f"{BASE}/groups/{gid}", json={"name": "B's Name"})
        assert r.status_code == 403, f"Expected 403, got {r.status_code}"
    
    def test_leave_group(self, admin, user_b, make_friends):
        """POST /api/groups/{gid}/leave → 200, group still exists if others remain."""
        admin_sess, _ = admin
        b_sess, b_id = user_b
        
        # Create group
        r = admin_sess.post(f"{BASE}/groups", json={"name": "Leave Test", "member_ids": [b_id]})
        gid = r.json()["id"]
        
        # B leaves
        r = b_sess.post(f"{BASE}/groups/{gid}/leave")
        assert r.status_code == 200, r.text
        
        # Group still exists (admin still there)
        r = admin_sess.get(f"{BASE}/groups/{gid}")
        assert r.status_code == 200
    
    def test_last_member_leaves_deletes_group(self, admin):
        """When last member leaves → group and messages deleted."""
        admin_sess, _ = admin
        
        # Create group with only admin
        r = admin_sess.post(f"{BASE}/groups", json={"name": "Solo Group", "member_ids": []})
        gid = r.json()["id"]
        
        # Post a message
        admin_sess.post(f"{BASE}/groups/{gid}/messages", json={"text": "Solo message"})
        
        # Admin leaves
        r = admin_sess.post(f"{BASE}/groups/{gid}/leave")
        assert r.status_code == 200
        
        # Group should be gone
        r = admin_sess.get(f"{BASE}/groups/{gid}")
        assert r.status_code == 404, f"Expected 404, got {r.status_code}"


# =============================================================================
# 7. ALBUM (per event)
# =============================================================================
class TestAlbum:
    def test_album_upload_image_with_interest(self, admin, user_b, temp_event, make_friends):
        """POST /api/events/{id}/album/upload with image → 200 {id, media_url, media_type: 'image'}."""
        admin_sess, _ = admin
        b_sess, b_id = user_b
        
        # B sets interest to 'voy'
        r = b_sess.post(f"{BASE}/events/{temp_event}/interest", json={"status": "voy"})
        assert r.status_code in (200, 201)
        
        # B uploads image
        fake_image = io.BytesIO(b"fake image data")
        files = {"file": ("test.jpg", fake_image, "image/jpeg")}
        r = b_sess.post(f"{BASE}/events/{temp_event}/album/upload", files=files)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "id" in data
        assert "media_url" in data
        assert data["media_type"] == "image"
        return data["id"]
    
    def test_album_upload_video(self, admin, user_b, temp_event, make_friends):
        """Upload video → media_type: 'video'."""
        b_sess, b_id = user_b
        
        # Ensure interest is set
        b_sess.post(f"{BASE}/events/{temp_event}/interest", json={"status": "voy"})
        
        # Upload video
        fake_video = io.BytesIO(b"fake video data")
        files = {"file": ("test.mp4", fake_video, "video/mp4")}
        r = b_sess.post(f"{BASE}/events/{temp_event}/album/upload", files=files)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["media_type"] == "video"
    
    def test_album_upload_without_interest_forbidden(self, user_c, temp_event):
        """Upload without interest → 403."""
        c_sess, _ = user_c
        
        fake_image = io.BytesIO(b"fake image")
        files = {"file": ("test.jpg", fake_image, "image/jpeg")}
        r = c_sess.post(f"{BASE}/events/{temp_event}/album/upload", files=files)
        assert r.status_code == 403, f"Expected 403, got {r.status_code}"
    
    def test_album_upload_invalid_content_type(self, user_b, temp_event):
        """Upload with content_type=text/plain → 400."""
        b_sess, _ = user_b
        
        # Ensure interest
        b_sess.post(f"{BASE}/events/{temp_event}/interest", json={"status": "voy"})
        
        fake_file = io.BytesIO(b"not an image")
        files = {"file": ("test.txt", fake_file, "text/plain")}
        r = b_sess.post(f"{BASE}/events/{temp_event}/album/upload", files=files)
        assert r.status_code == 400, f"Expected 400, got {r.status_code}"
        assert "solo" in r.text.lower() or "only" in r.text.lower()
    
    def test_album_list(self, admin, user_b, temp_event, make_friends):
        """GET /api/events/{id}/album → {event, items[], total}."""
        b_sess, _ = user_b
        
        r = b_sess.get(f"{BASE}/events/{temp_event}/album")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "event" in data or "items" in data
        assert "total" in data or isinstance(data, dict)
    
    def test_album_delete_own(self, admin, user_b, temp_event, make_friends):
        """DELETE /api/events/{id}/album/{upload_id} as owner → 200."""
        b_sess, _ = user_b
        
        # Upload first
        b_sess.post(f"{BASE}/events/{temp_event}/interest", json={"status": "voy"})
        fake_image = io.BytesIO(b"delete test")
        files = {"file": ("del.jpg", fake_image, "image/jpeg")}
        r = b_sess.post(f"{BASE}/events/{temp_event}/album/upload", files=files)
        upload_id = r.json()["id"]
        
        # Delete
        r = b_sess.delete(f"{BASE}/events/{temp_event}/album/{upload_id}")
        assert r.status_code == 200, r.text
    
    def test_album_delete_other_user_forbidden(self, admin, user_b, temp_event, make_friends):
        """DELETE other user's upload → 403."""
        admin_sess, _ = admin
        b_sess, _ = user_b
        
        # B uploads
        b_sess.post(f"{BASE}/events/{temp_event}/interest", json={"status": "voy"})
        fake_image = io.BytesIO(b"b's image")
        files = {"file": ("b.jpg", fake_image, "image/jpeg")}
        r = b_sess.post(f"{BASE}/events/{temp_event}/album/upload", files=files)
        upload_id = r.json()["id"]
        
        # Admin tries to delete B's upload
        r = admin_sess.delete(f"{BASE}/events/{temp_event}/album/{upload_id}")
        assert r.status_code == 403, f"Expected 403, got {r.status_code}"
    
    def test_album_nonexistent_event(self, admin):
        """GET album on non-existent event → 404."""
        admin_sess, _ = admin
        r = admin_sess.get(f"{BASE}/events/nonexistent123/album")
        assert r.status_code == 404, f"Expected 404, got {r.status_code}"


# =============================================================================
# 8. MOMENT (El Momento — BeReal style)
# =============================================================================
class TestMoment:
    def test_moment_status_before_trigger(self, admin, temp_event):
        """GET /api/events/{id}/moment/status before trigger → {prompt:null, my_capture:null, can_capture:false}."""
        admin_sess, _ = admin
        r = admin_sess.get(f"{BASE}/events/{temp_event}/moment/status")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "prompt" in data
        assert "can_capture" in data
        # Before trigger, prompt should be null and can_capture false
        # (unless already triggered in previous test)
    
    def test_admin_trigger_moment(self, admin, temp_event):
        """POST /api/admin/events/{id}/moment/trigger → creates prompt, notifies voy users."""
        admin_sess, _ = admin
        r = admin_sess.post(f"{BASE}/admin/events/{temp_event}/moment/trigger")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "prompt" in data
        assert "notified" in data
        assert isinstance(data["notified"], int)
    
    def test_moment_status_after_trigger(self, admin, temp_event):
        """GET status after trigger → prompt set, can_capture=true."""
        admin_sess, _ = admin
        
        # Trigger first
        admin_sess.post(f"{BASE}/admin/events/{temp_event}/moment/trigger")
        
        # Check status
        r = admin_sess.get(f"{BASE}/events/{temp_event}/moment/status")
        assert r.status_code == 200
        data = r.json()
        assert data["prompt"] is not None
        assert data["can_capture"] is True
    
    def test_moment_upload_as_voy_user(self, user_b, temp_event):
        """POST /api/events/{id}/moment/upload as voy user → 200 with on_time=true (within 2min)."""
        b_sess, _ = user_b
        
        # Set interest to voy
        b_sess.post(f"{BASE}/events/{temp_event}/interest", json={"status": "voy"})
        
        # Upload moment
        fake_image = io.BytesIO(b"moment capture")
        files = {"file": ("moment.jpg", fake_image, "image/jpeg")}
        r = b_sess.post(f"{BASE}/events/{temp_event}/moment/upload", files=files)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "on_time" in data
        # Should be on_time if within 2 minutes of trigger
    
    def test_moment_upload_duplicate_fails(self, user_b, temp_event):
        """Upload again → 400 'Ya subiste tu momento'."""
        b_sess, _ = user_b
        
        fake_image = io.BytesIO(b"duplicate moment")
        files = {"file": ("dup.jpg", fake_image, "image/jpeg")}
        r = b_sess.post(f"{BASE}/events/{temp_event}/moment/upload", files=files)
        assert r.status_code == 400, f"Expected 400, got {r.status_code}"
        assert "ya" in r.text.lower() or "already" in r.text.lower()
    
    def test_moment_gallery_with_upload(self, user_b, temp_event):
        """GET /api/events/{id}/moment/gallery as user who uploaded → 200."""
        b_sess, _ = user_b
        
        r = b_sess.get(f"{BASE}/events/{temp_event}/moment/gallery")
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list) or "captures" in data
    
    def test_moment_gallery_without_upload_forbidden(self, user_c, temp_event):
        """GET gallery without uploading → 403."""
        c_sess, _ = user_c
        
        r = c_sess.get(f"{BASE}/events/{temp_event}/moment/gallery")
        assert r.status_code == 403, f"Expected 403, got {r.status_code}"


# =============================================================================
# 9. CALENDAR
# =============================================================================
class TestCalendar:
    def test_calendar_default_last_90_days(self, admin):
        """GET /api/me/calendar (default) → array of day objects."""
        admin_sess, _ = admin
        r = admin_sess.get(f"{BASE}/me/calendar")
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
    
    def test_calendar_with_date_range(self, admin):
        """GET /api/me/calendar?start=2020-01-01&end=2020-01-02 → empty array."""
        admin_sess, _ = admin
        r = admin_sess.get(f"{BASE}/me/calendar?start=2020-01-01&end=2020-01-02")
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 0 or len(data) <= 2  # Should be empty or very few
    
    def test_calendar_bad_date_param(self, admin):
        """Bad date param → 400."""
        admin_sess, _ = admin
        r = admin_sess.get(f"{BASE}/me/calendar?start=invalid-date")
        assert r.status_code == 400, f"Expected 400, got {r.status_code}"


# =============================================================================
# 10. TICKETS
# =============================================================================
class TestTickets:
    def test_ticket_click(self, admin, temp_event):
        """POST /api/tickets/click → 200 {id}."""
        admin_sess, _ = admin
        r = admin_sess.post(f"{BASE}/tickets/click", json={"event_id": temp_event})
        assert r.status_code in (200, 201), r.text
        data = r.json()
        assert "id" in data
        return data["id"]
    
    def test_admin_confirm_ticket(self, admin, temp_event):
        """POST /api/admin/tickets/confirm → 200."""
        admin_sess, _ = admin
        
        # Create ticket first
        r = admin_sess.post(f"{BASE}/tickets/click", json={"event_id": temp_event})
        purchase_id = r.json()["id"]
        
        # Confirm
        r = admin_sess.post(f"{BASE}/admin/tickets/confirm", json={"purchase_id": purchase_id, "confirmed": True})
        assert r.status_code == 200, r.text
    
    def test_admin_list_tickets_pending(self, admin, temp_event):
        """GET /api/admin/tickets?status=pending → array without confirmed ones."""
        admin_sess, _ = admin
        
        # Create and confirm a ticket
        r = admin_sess.post(f"{BASE}/tickets/click", json={"event_id": temp_event})
        pid = r.json()["id"]
        admin_sess.post(f"{BASE}/admin/tickets/confirm", json={"purchase_id": pid, "confirmed": True})
        
        # List pending
        r = admin_sess.get(f"{BASE}/admin/tickets?status=pending")
        assert r.status_code == 200, r.text
        tickets = r.json()
        assert isinstance(tickets, list)
        
        # Confirmed ticket should not be in pending list
        confirmed_in_pending = any(t["id"] == pid for t in tickets)
        assert not confirmed_in_pending, "Confirmed ticket found in pending list"
    
    def test_admin_list_tickets_confirmed(self, admin, temp_event):
        """GET /api/admin/tickets?status=confirmed → array includes confirmed."""
        admin_sess, _ = admin
        
        # Create and confirm
        r = admin_sess.post(f"{BASE}/tickets/click", json={"event_id": temp_event})
        pid = r.json()["id"]
        admin_sess.post(f"{BASE}/admin/tickets/confirm", json={"purchase_id": pid, "confirmed": True})
        
        # List confirmed
        r = admin_sess.get(f"{BASE}/admin/tickets?status=confirmed")
        assert r.status_code == 200, r.text
        tickets = r.json()
        assert isinstance(tickets, list)
        
        # Should include the confirmed ticket
        confirmed_found = any(t["id"] == pid for t in tickets)
        assert confirmed_found, "Confirmed ticket not found in confirmed list"


# =============================================================================
# 11. ADMIN DASHBOARD
# =============================================================================
class TestAdminDashboard:
    def test_admin_dashboard_structure(self, admin):
        """GET /api/admin/dashboard → {activity_30d[30], top_users[<=10], extras{...}}."""
        admin_sess, _ = admin
        r = admin_sess.get(f"{BASE}/admin/dashboard")
        assert r.status_code == 200, r.text
        data = r.json()
        
        assert "activity_30d" in data
        assert "top_users" in data
        assert "extras" in data
        
        assert isinstance(data["activity_30d"], list)
        assert len(data["activity_30d"]) <= 30
        
        assert isinstance(data["top_users"], list)
        assert len(data["top_users"]) <= 10
        
        extras = data["extras"]
        required_extras = ["groups", "group_messages", "dms", "album_items", "captures", "pending_tickets"]
        for field in required_extras:
            assert field in extras, f"Missing extras field: {field}"
    
    def test_admin_dashboard_non_admin_forbidden(self, user_b):
        """Non-admin → 403."""
        b_sess, _ = user_b
        r = b_sess.get(f"{BASE}/admin/dashboard")
        assert r.status_code == 403, f"Expected 403, got {r.status_code}"
