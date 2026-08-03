#!/usr/bin/env python3
"""
Backend API tests for ¿Quién va? app
Testing iteration: Default privacy + moment_privacy field + DM read fix + weekly recap + discover
"""

import requests
import time
import random
import string
from datetime import datetime, timedelta

# Base URL from frontend/.env
BASE_URL = "https://d74373cf-d064-48e4-9df1-2467107df57c.preview.emergentagent.com/api"

# Admin credentials
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

# Test results
tests_passed = 0
tests_failed = 0
failed_tests = []

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def random_string(length=8):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def register_user(name=None, email=None, password="testpass123", city="Palma de Mallorca", birthdate="1998-05-05", username=None):
    """Register a new user and return token"""
    if not name:
        name = f"Test User {random_string(4)}"
    if not email:
        email = f"test_{random_string(8)}@test.com"
    if not username:
        username = f"user_{random_string(6)}"
    
    resp = requests.post(f"{BASE_URL}/auth/register", json={
        "name": name,
        "email": email,
        "password": password,
        "city": city,
        "birthdate": birthdate,
        "username": username
    })
    if resp.status_code != 200:
        log(f"❌ Failed to register user: {resp.status_code} - {resp.text}")
        return None, None, None
    data = resp.json()
    return data["token"], data["user"]["user_id"], email

def login(email, password):
    """Login and return token"""
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": email,
        "password": password
    })
    if resp.status_code != 200:
        return None
    return resp.json()["token"]

def make_friends(token_a, user_id_a, token_b, user_id_b):
    """Make two users friends"""
    # A sends friend request to B
    resp = requests.post(
        f"{BASE_URL}/friends/request",
        json={"user_id": user_id_b},
        headers={"Authorization": f"Bearer {token_a}"}
    )
    if resp.status_code != 200:
        log(f"❌ Failed to send friend request: {resp.status_code} - {resp.text}")
        return False
    
    # B gets friend requests
    resp = requests.get(
        f"{BASE_URL}/friends/requests",
        headers={"Authorization": f"Bearer {token_b}"}
    )
    if resp.status_code != 200:
        log(f"❌ Failed to get friend requests: {resp.status_code}")
        return False
    
    requests_list = resp.json()
    if not requests_list:
        log(f"❌ No friend requests found")
        return False
    
    request_id = requests_list[0]["request_id"]
    
    # B accepts friend request
    resp = requests.post(
        f"{BASE_URL}/friends/respond",
        json={"request_id": request_id, "accept": True},
        headers={"Authorization": f"Bearer {token_b}"}
    )
    if resp.status_code != 200:
        log(f"❌ Failed to accept friend request: {resp.status_code}")
        return False
    
    return True

def test(name, func):
    """Run a test and track results"""
    global tests_passed, tests_failed, failed_tests
    try:
        log(f"🧪 Testing: {name}")
        func()
        tests_passed += 1
        log(f"✅ PASSED: {name}")
    except AssertionError as e:
        tests_failed += 1
        failed_tests.append(name)
        log(f"❌ FAILED: {name} - {str(e)}")
    except Exception as e:
        tests_failed += 1
        failed_tests.append(name)
        log(f"❌ ERROR: {name} - {str(e)}")

# ============================================================================
# TEST 1: DEFAULT PRIVACY = amigos
# ============================================================================

def test_default_privacy_amigos():
    """Register a NEW user and verify attendance_privacy and moment_privacy both default to 'amigos'"""
    log("Registering new user to test default privacy...")
    token, user_id, email = register_user()
    assert token, "Failed to register user"
    
    # GET /api/auth/me
    resp = requests.get(
        f"{BASE_URL}/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    
    user = resp.json()
    log(f"User data: attendance_privacy={user.get('attendance_privacy')}, moment_privacy={user.get('moment_privacy')}")
    
    assert user.get("attendance_privacy") == "amigos", f"Expected attendance_privacy='amigos', got '{user.get('attendance_privacy')}'"
    assert user.get("moment_privacy") == "amigos", f"Expected moment_privacy='amigos', got '{user.get('moment_privacy')}'"
    
    log("✓ Default privacy values are correct (both 'amigos')")

# ============================================================================
# TEST 2: MOMENT PRIVACY field validation
# ============================================================================

def test_moment_privacy_field():
    """Test PUT /api/auth/profile with moment_privacy field"""
    log("Registering user for moment_privacy tests...")
    token, user_id, email = register_user()
    assert token, "Failed to register user"
    
    # Test 1: Set moment_privacy to "publico" -> 200
    log("Test 1: Setting moment_privacy to 'publico'...")
    resp = requests.put(
        f"{BASE_URL}/auth/profile",
        json={"moment_privacy": "publico"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    # Verify it's reflected in GET /auth/me
    resp = requests.get(
        f"{BASE_URL}/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    user = resp.json()
    assert user.get("moment_privacy") == "publico", f"Expected 'publico', got '{user.get('moment_privacy')}'"
    log("✓ moment_privacy='publico' works")
    
    # Test 2: Invalid value "foo" -> 400
    log("Test 2: Setting moment_privacy to invalid value 'foo'...")
    resp = requests.put(
        f"{BASE_URL}/auth/profile",
        json={"moment_privacy": "foo"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 400, f"Expected 400 for invalid value, got {resp.status_code}"
    log("✓ Invalid moment_privacy value returns 400")
    
    # Test 3: Set back to "amigos" -> 200
    log("Test 3: Setting moment_privacy back to 'amigos'...")
    resp = requests.put(
        f"{BASE_URL}/auth/profile",
        json={"moment_privacy": "amigos"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    log("✓ moment_privacy='amigos' works")
    
    # REGRESSION: Test attendance_privacy still works
    log("Regression test: Setting attendance_privacy to 'amigos'...")
    resp = requests.put(
        f"{BASE_URL}/auth/profile",
        json={"attendance_privacy": "amigos"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    log("✓ attendance_privacy='amigos' works")
    
    log("Regression test: Setting attendance_privacy to invalid value 'foo'...")
    resp = requests.put(
        f"{BASE_URL}/auth/profile",
        json={"attendance_privacy": "foo"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 400, f"Expected 400 for invalid value, got {resp.status_code}"
    log("✓ Invalid attendance_privacy value returns 400")

# ============================================================================
# TEST 3: DM READ FIX - opening thread clears dm notifications
# ============================================================================

def test_dm_read_fix():
    """Test that opening a DM thread marks the dm notification as read"""
    log("Registering user A...")
    token_a, user_id_a, email_a = register_user(name="Alice")
    assert token_a, "Failed to register user A"
    
    log("Registering user B...")
    token_b, user_id_b, email_b = register_user(name="Bob")
    assert token_b, "Failed to register user B"
    
    # Make them friends
    log("Making users friends...")
    assert make_friends(token_a, user_id_a, token_b, user_id_b), "Failed to make users friends"
    log("✓ Users are now friends")
    
    # B sends DM to A
    log("B sends DM to A...")
    resp = requests.post(
        f"{BASE_URL}/dm/send",
        json={"to_user_id": user_id_a, "text": "hola"},
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert resp.status_code == 200, f"Failed to send DM: {resp.status_code} - {resp.text}"
    log("✓ DM sent successfully")
    
    # Wait a moment for notification to be created
    time.sleep(0.5)
    
    # As A: GET /api/notifications should contain an unread notification with type=="dm"
    log("As A: Checking notifications...")
    resp = requests.get(
        f"{BASE_URL}/notifications",
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert resp.status_code == 200, f"Failed to get notifications: {resp.status_code}"
    notifications = resp.json()
    
    dm_notif = None
    for n in notifications:
        if n.get("type") == "dm" and n.get("data", {}).get("user_id") == user_id_b:
            dm_notif = n
            break
    
    assert dm_notif is not None, "No dm notification found from user B"
    assert dm_notif.get("read") == False, f"Expected dm notification to be unread, got read={dm_notif.get('read')}"
    log(f"✓ Found unread dm notification from B: {dm_notif.get('message')}")
    
    # As A: GET /api/notifications/unread-count should be > 0
    resp = requests.get(
        f"{BASE_URL}/notifications/unread-count",
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert resp.status_code == 200, f"Failed to get unread count: {resp.status_code}"
    unread_count = resp.json().get("count", 0)
    assert unread_count > 0, f"Expected unread count > 0, got {unread_count}"
    log(f"✓ Unread notification count: {unread_count}")
    
    # Now as A: GET /api/dm/{B_userId}/messages (opens thread)
    log("As A: Opening DM thread with B...")
    resp = requests.get(
        f"{BASE_URL}/dm/{user_id_b}/messages",
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert resp.status_code == 200, f"Failed to get DM messages: {resp.status_code}"
    messages = resp.json()
    assert len(messages) > 0, "Expected at least one message"
    log(f"✓ Retrieved {len(messages)} message(s)")
    
    # Wait a moment for notification to be marked as read
    time.sleep(0.5)
    
    # THEN re-check as A: GET /api/notifications -> the dm notification from B must now have read==true
    log("As A: Re-checking notifications after opening thread...")
    resp = requests.get(
        f"{BASE_URL}/notifications",
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert resp.status_code == 200, f"Failed to get notifications: {resp.status_code}"
    notifications = resp.json()
    
    dm_notif_after = None
    for n in notifications:
        if n.get("type") == "dm" and n.get("data", {}).get("user_id") == user_id_b:
            dm_notif_after = n
            break
    
    assert dm_notif_after is not None, "DM notification disappeared after opening thread"
    assert dm_notif_after.get("read") == True, f"Expected dm notification to be read after opening thread, got read={dm_notif_after.get('read')}"
    log("✓ DM notification is now marked as read")
    
    # As A: GET /api/dm/unread-count should be 0 for that thread
    resp = requests.get(
        f"{BASE_URL}/dm/unread-count",
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert resp.status_code == 200, f"Failed to get dm unread count: {resp.status_code}"
    dm_unread = resp.json().get("count", 0)
    assert dm_unread == 0, f"Expected dm unread count to be 0, got {dm_unread}"
    log("✓ DM unread count is now 0")
    
    log("✓ DM READ FIX VERIFIED: Opening a chat clears its pending notification")

# ============================================================================
# TEST 4: WEEKLY RECAP
# ============================================================================

def test_weekly_recap():
    """Test POST /api/admin/trigger-weekend-recap"""
    log("Logging in as admin...")
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    assert admin_token, "Failed to login as admin"
    
    log("Triggering weekend recap...")
    resp = requests.post(
        f"{BASE_URL}/admin/trigger-weekend-recap",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    data = resp.json()
    assert "sent" in data, "Response missing 'sent' field"
    sent_count = data["sent"]
    log(f"✓ Weekend recap triggered successfully, sent to {sent_count} users")
    
    # Verify it's an integer
    assert isinstance(sent_count, int), f"Expected 'sent' to be an integer, got {type(sent_count)}"
    log("✓ Response format is correct")

# ============================================================================
# TEST 5: DISCOVER endpoint
# ============================================================================

def test_discover():
    """Test GET /api/discover returns correct structure and never includes requesting user"""
    log("Registering user for discover test...")
    token, user_id, email = register_user()
    assert token, "Failed to register user"
    
    log("Calling GET /api/discover...")
    resp = requests.get(
        f"{BASE_URL}/discover",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    
    data = resp.json()
    log(f"Discover response keys: {data.keys()}")
    
    # Verify structure
    assert "people" in data, "Response missing 'people' field"
    assert "moments" in data, "Response missing 'moments' field"
    assert "city" in data, "Response missing 'city' field"
    
    assert isinstance(data["people"], list), f"Expected 'people' to be a list, got {type(data['people'])}"
    assert isinstance(data["moments"], list), f"Expected 'moments' to be a list, got {type(data['moments'])}"
    assert isinstance(data["city"], str), f"Expected 'city' to be a string, got {type(data['city'])}"
    
    log(f"✓ Response structure correct: people={len(data['people'])}, moments={len(data['moments'])}, city='{data['city']}'")
    
    # CRITICAL: Verify people NEVER contains the requesting user's own user_id
    people_ids = [p.get("user_id") for p in data["people"]]
    assert user_id not in people_ids, f"CRITICAL BUG: Discover people list contains requesting user's own user_id ({user_id})"
    log(f"✓ VERIFIED: Requesting user ({user_id}) is NOT in people list")
    
    # Log some sample data if available
    if data["people"]:
        sample = data["people"][0]
        log(f"Sample person: {sample.get('name')} ({sample.get('user_id')})")
    
    if data["moments"]:
        sample = data["moments"][0]
        log(f"Sample moment: author={sample.get('author', {}).get('name')}, event={sample.get('event_name')}")

# ============================================================================
# REGRESSION TESTS
# ============================================================================

def test_regression_login():
    """Test POST /api/auth/login works"""
    log("Testing login with admin credentials...")
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    data = resp.json()
    assert "token" in data, "Response missing 'token' field"
    assert "user" in data, "Response missing 'user' field"
    log("✓ Login works correctly")

def test_regression_events():
    """Test GET /api/events returns 200"""
    log("Testing GET /api/events...")
    # Events endpoint requires authentication
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    assert admin_token, "Failed to login as admin"
    
    resp = requests.get(
        f"{BASE_URL}/events",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    data = resp.json()
    assert isinstance(data, list), f"Expected list, got {type(data)}"
    log(f"✓ GET /api/events works, returned {len(data)} events")

# ============================================================================
# RUN ALL TESTS
# ============================================================================

def main():
    log("=" * 80)
    log("BACKEND TESTING - ¿Quién va? App")
    log("Testing: Default privacy + moment_privacy + DM read fix + weekly recap + discover")
    log("=" * 80)
    
    # Main tests
    test("1. Default privacy = amigos", test_default_privacy_amigos)
    test("2. Moment privacy field validation", test_moment_privacy_field)
    test("3. DM read fix (opening thread clears notification)", test_dm_read_fix)
    test("4. Weekly recap endpoint", test_weekly_recap)
    test("5. Discover endpoint", test_discover)
    
    # Regression tests
    test("Regression: Login", test_regression_login)
    test("Regression: Events list", test_regression_events)
    
    # Summary
    log("=" * 80)
    log(f"TESTING COMPLETE")
    log(f"✅ Passed: {tests_passed}")
    log(f"❌ Failed: {tests_failed}")
    if failed_tests:
        log(f"Failed tests: {', '.join(failed_tests)}")
    log("=" * 80)
    
    return tests_failed == 0

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
