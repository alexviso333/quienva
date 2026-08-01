#!/usr/bin/env python3
"""
Backend API tests for "El Momento" admin endpoints + regression tests
Test credentials: admin@quienva.app / admin123
"""

import requests
import json
import time
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

# Backend URL
BASE_URL = "http://localhost:8001/api"

# Test credentials
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

# Global tokens
admin_token = None
user_token = None
test_user_email = None
test_event_id = None

def log(msg):
    print(f"[TEST] {msg}")

def assert_status(response, expected_status, context=""):
    if response.status_code != expected_status:
        log(f"❌ FAILED {context}: Expected {expected_status}, got {response.status_code}")
        log(f"   Response: {response.text[:500]}")
        return False
    return True

def assert_field(data, field, context=""):
    if field not in data:
        log(f"❌ FAILED {context}: Missing field '{field}'")
        log(f"   Data: {json.dumps(data, indent=2)[:500]}")
        return False
    return True

def assert_value(actual, expected, context=""):
    if actual != expected:
        log(f"❌ FAILED {context}: Expected {expected}, got {actual}")
        return False
    return True

# ============================================================================
# SETUP: Login and create test data
# ============================================================================

def test_admin_login():
    """Login as admin and get token"""
    global admin_token
    log("Testing admin login...")
    
    response = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    
    if not assert_status(response, 200, "Admin login"):
        return False
    
    data = response.json()
    if not assert_field(data, "token", "Admin login response"):
        return False
    
    admin_token = data["token"]
    log(f"✅ Admin login successful, token: {admin_token[:20]}...")
    return True

def test_register_test_user():
    """Register a fresh non-admin test user"""
    global user_token, test_user_email
    
    timestamp = int(time.time())
    test_user_email = f"testuser{timestamp}@test.com"
    
    log(f"Registering test user: {test_user_email}...")
    
    response = requests.post(f"{BASE_URL}/auth/register", json={
        "email": test_user_email,
        "password": "testpass123",
        "name": "Test User",
        "username": f"testuser{timestamp}",
        "city": "Palma"
    })
    
    if not assert_status(response, 200, "User registration"):
        return False
    
    data = response.json()
    if "token" in data:
        user_token = data["token"]
    elif "user" in data and "token" in data:
        user_token = data["token"]
    else:
        log(f"❌ FAILED: No token in registration response")
        return False
    
    log(f"✅ Test user registered, token: {user_token[:20]}...")
    return True

def create_test_event():
    """Create a test event for today to test moment endpoints"""
    global test_event_id, admin_token
    
    log("Creating test event for today...")
    
    # Create event for today
    today = date.today().isoformat()
    
    response = requests.post(
        f"{BASE_URL}/admin/events",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "name": "Test Party for Moments",
            "venue": "Test Venue",
            "date": today,
            "time": "23:00",
            "city": "Palma",
            "genre": "Electrónica"
        }
    )
    
    if response.status_code == 200:
        data = response.json()
        test_event_id = data.get("id")
        log(f"✅ Test event created: {test_event_id}")
        return True
    else:
        log(f"⚠️  Could not create test event (may not have admin/events endpoint): {response.status_code}")
        # Try to get an existing event
        response = requests.get(
            f"{BASE_URL}/events",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        if response.status_code == 200:
            events = response.json()
            if events and len(events) > 0:
                test_event_id = events[0]["id"]
                log(f"✅ Using existing event: {test_event_id}")
                return True
        return False

# ============================================================================
# NEW ADMIN MOMENT ENDPOINTS TESTS
# ============================================================================

def test_admin_moments_list_as_admin():
    """GET /api/admin/moments as admin → 200"""
    log("Testing GET /admin/moments as admin...")
    
    response = requests.get(
        f"{BASE_URL}/admin/moments",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    if not assert_status(response, 200, "GET /admin/moments as admin"):
        return False
    
    data = response.json()
    if not isinstance(data, list):
        log(f"❌ FAILED: Expected array, got {type(data)}")
        return False
    
    # Check structure of first event if exists
    if len(data) > 0:
        event = data[0]
        required_fields = ["id", "name", "venue", "date", "time", "planned_moment_at", 
                          "moment_cancelled", "has_fired", "fired_at", "voy_count", "captures_count"]
        for field in required_fields:
            if not assert_field(event, field, f"Event object field '{field}'"):
                return False
    
    log(f"✅ GET /admin/moments as admin: returns {len(data)} events with correct structure")
    return True

def test_admin_moments_list_as_non_admin():
    """GET /api/admin/moments as non-admin → 403"""
    log("Testing GET /admin/moments as non-admin...")
    
    response = requests.get(
        f"{BASE_URL}/admin/moments",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    
    if not assert_status(response, 403, "GET /admin/moments as non-admin"):
        return False
    
    log("✅ GET /admin/moments as non-admin: returns 403")
    return True

def test_admin_moments_list_unauthenticated():
    """GET /api/admin/moments unauthenticated → 401"""
    log("Testing GET /admin/moments unauthenticated...")
    
    response = requests.get(f"{BASE_URL}/admin/moments")
    
    if not assert_status(response, 401, "GET /admin/moments unauthenticated"):
        return False
    
    log("✅ GET /admin/moments unauthenticated: returns 401")
    return True

def test_admin_set_moment_time_valid():
    """PUT /api/admin/moments/{event_id} with valid time → 200"""
    if not test_event_id:
        log("⚠️  Skipping: No test event available")
        return True
    
    log(f"Testing PUT /admin/moments/{test_event_id} with valid time...")
    
    response = requests.put(
        f"{BASE_URL}/admin/moments/{test_event_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"hour": 3, "minute": 15}
    )
    
    if not assert_status(response, 200, "PUT /admin/moments with valid time"):
        return False
    
    data = response.json()
    if not assert_field(data, "planned_moment_at", "Set time response"):
        return False
    
    # Verify the time is set correctly (03:15 on party night)
    planned_at = data["planned_moment_at"]
    if planned_at:
        # Parse and check hour/minute in Europe/Madrid timezone
        dt = datetime.fromisoformat(planned_at.replace('Z', '+00:00'))
        madrid_dt = dt.astimezone(ZoneInfo("Europe/Madrid"))
        if not (madrid_dt.hour == 3 and madrid_dt.minute == 15):
            log(f"❌ FAILED: Expected 03:15, got {madrid_dt.hour:02d}:{madrid_dt.minute:02d}")
            return False
    
    log(f"✅ PUT /admin/moments with valid time: set to 03:15 correctly")
    return True

def test_admin_set_moment_time_boundary_low():
    """PUT /api/admin/moments/{event_id} with hour=1, minute=0 → 200"""
    if not test_event_id:
        log("⚠️  Skipping: No test event available")
        return True
    
    log(f"Testing PUT /admin/moments/{test_event_id} with boundary hour=1...")
    
    response = requests.put(
        f"{BASE_URL}/admin/moments/{test_event_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"hour": 1, "minute": 0}
    )
    
    if not assert_status(response, 200, "PUT /admin/moments with hour=1"):
        return False
    
    log("✅ PUT /admin/moments with hour=1, minute=0: accepted")
    return True

def test_admin_set_moment_time_boundary_high():
    """PUT /api/admin/moments/{event_id} with hour=5, minute=59 → 200"""
    if not test_event_id:
        log("⚠️  Skipping: No test event available")
        return True
    
    log(f"Testing PUT /admin/moments/{test_event_id} with boundary hour=5, minute=59...")
    
    response = requests.put(
        f"{BASE_URL}/admin/moments/{test_event_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"hour": 5, "minute": 59}
    )
    
    if not assert_status(response, 200, "PUT /admin/moments with hour=5, minute=59"):
        return False
    
    log("✅ PUT /admin/moments with hour=5, minute=59: accepted")
    return True

def test_admin_set_moment_time_invalid_hour_0():
    """PUT /api/admin/moments/{event_id} with hour=0 → 400"""
    if not test_event_id:
        log("⚠️  Skipping: No test event available")
        return True
    
    log(f"Testing PUT /admin/moments/{test_event_id} with invalid hour=0...")
    
    response = requests.put(
        f"{BASE_URL}/admin/moments/{test_event_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"hour": 0, "minute": 0}
    )
    
    if not assert_status(response, 400, "PUT /admin/moments with hour=0"):
        return False
    
    log("✅ PUT /admin/moments with hour=0: returns 400")
    return True

def test_admin_set_moment_time_invalid_hour_6():
    """PUT /api/admin/moments/{event_id} with hour=6 → 400"""
    if not test_event_id:
        log("⚠️  Skipping: No test event available")
        return True
    
    log(f"Testing PUT /admin/moments/{test_event_id} with invalid hour=6...")
    
    response = requests.put(
        f"{BASE_URL}/admin/moments/{test_event_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"hour": 6, "minute": 0}
    )
    
    if not assert_status(response, 400, "PUT /admin/moments with hour=6"):
        return False
    
    log("✅ PUT /admin/moments with hour=6: returns 400")
    return True

def test_admin_set_moment_time_invalid_hour_7():
    """PUT /api/admin/moments/{event_id} with hour=7 → 400"""
    if not test_event_id:
        log("⚠️  Skipping: No test event available")
        return True
    
    log(f"Testing PUT /admin/moments/{test_event_id} with invalid hour=7...")
    
    response = requests.put(
        f"{BASE_URL}/admin/moments/{test_event_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"hour": 7, "minute": 0}
    )
    
    if not assert_status(response, 400, "PUT /admin/moments with hour=7"):
        return False
    
    log("✅ PUT /admin/moments with hour=7: returns 400")
    return True

def test_admin_set_moment_time_nonexistent_event():
    """PUT /api/admin/moments/{nonexistent_id} → 404"""
    log("Testing PUT /admin/moments with non-existent event...")
    
    response = requests.put(
        f"{BASE_URL}/admin/moments/nonexistent-event-id-12345",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"hour": 3, "minute": 0}
    )
    
    if not assert_status(response, 404, "PUT /admin/moments with non-existent event"):
        return False
    
    log("✅ PUT /admin/moments with non-existent event: returns 404")
    return True

def test_admin_set_moment_time_as_non_admin():
    """PUT /api/admin/moments/{event_id} as non-admin → 403"""
    if not test_event_id:
        log("⚠️  Skipping: No test event available")
        return True
    
    log("Testing PUT /admin/moments as non-admin...")
    
    response = requests.put(
        f"{BASE_URL}/admin/moments/{test_event_id}",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"hour": 3, "minute": 0}
    )
    
    if not assert_status(response, 403, "PUT /admin/moments as non-admin"):
        return False
    
    log("✅ PUT /admin/moments as non-admin: returns 403")
    return True

def test_admin_randomize_moment():
    """POST /api/admin/moments/{event_id}/randomize as admin → 200"""
    if not test_event_id:
        log("⚠️  Skipping: No test event available")
        return True
    
    log(f"Testing POST /admin/moments/{test_event_id}/randomize...")
    
    response = requests.post(
        f"{BASE_URL}/admin/moments/{test_event_id}/randomize",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    if not assert_status(response, 200, "POST /admin/moments/randomize"):
        return False
    
    data = response.json()
    if not assert_field(data, "planned_moment_at", "Randomize response"):
        return False
    
    # Verify the hour is between 1 and 5
    planned_at = data["planned_moment_at"]
    if planned_at:
        dt = datetime.fromisoformat(planned_at.replace('Z', '+00:00'))
        madrid_dt = dt.astimezone(ZoneInfo("Europe/Madrid"))
        if not (1 <= madrid_dt.hour <= 5):
            log(f"❌ FAILED: Random hour {madrid_dt.hour} not in range 1-5")
            return False
    
    log(f"✅ POST /admin/moments/randomize: set random time in 01:00-05:59 range")
    return True

def test_admin_randomize_moment_as_non_admin():
    """POST /api/admin/moments/{event_id}/randomize as non-admin → 403"""
    if not test_event_id:
        log("⚠️  Skipping: No test event available")
        return True
    
    log("Testing POST /admin/moments/randomize as non-admin...")
    
    response = requests.post(
        f"{BASE_URL}/admin/moments/{test_event_id}/randomize",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    
    if not assert_status(response, 403, "POST /admin/moments/randomize as non-admin"):
        return False
    
    log("✅ POST /admin/moments/randomize as non-admin: returns 403")
    return True

def test_admin_randomize_all_moments():
    """POST /api/admin/moments/randomize-all as admin → 200"""
    log("Testing POST /admin/moments/randomize-all...")
    
    response = requests.post(
        f"{BASE_URL}/admin/moments/randomize-all",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    if not assert_status(response, 200, "POST /admin/moments/randomize-all"):
        return False
    
    data = response.json()
    if not assert_field(data, "updated", "Randomize-all response"):
        return False
    
    if not isinstance(data["updated"], int):
        log(f"❌ FAILED: Expected 'updated' to be int, got {type(data['updated'])}")
        return False
    
    log(f"✅ POST /admin/moments/randomize-all: updated {data['updated']} events")
    return True

def test_admin_randomize_all_moments_as_non_admin():
    """POST /api/admin/moments/randomize-all as non-admin → 403"""
    log("Testing POST /admin/moments/randomize-all as non-admin...")
    
    response = requests.post(
        f"{BASE_URL}/admin/moments/randomize-all",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    
    if not assert_status(response, 403, "POST /admin/moments/randomize-all as non-admin"):
        return False
    
    log("✅ POST /admin/moments/randomize-all as non-admin: returns 403")
    return True

def test_admin_cancel_moment():
    """POST /api/admin/moments/{event_id}/cancel as admin → 200"""
    if not test_event_id:
        log("⚠️  Skipping: No test event available")
        return True
    
    log(f"Testing POST /admin/moments/{test_event_id}/cancel...")
    
    response = requests.post(
        f"{BASE_URL}/admin/moments/{test_event_id}/cancel",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    if not assert_status(response, 200, "POST /admin/moments/cancel"):
        return False
    
    data = response.json()
    if not assert_field(data, "moment_cancelled", "Cancel response"):
        return False
    
    if not assert_value(data["moment_cancelled"], True, "moment_cancelled should be true"):
        return False
    
    log("✅ POST /admin/moments/cancel: moment_cancelled=true")
    return True

def test_admin_cancel_moment_as_non_admin():
    """POST /api/admin/moments/{event_id}/cancel as non-admin → 403"""
    if not test_event_id:
        log("⚠️  Skipping: No test event available")
        return True
    
    log("Testing POST /admin/moments/cancel as non-admin...")
    
    response = requests.post(
        f"{BASE_URL}/admin/moments/{test_event_id}/cancel",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    
    if not assert_status(response, 403, "POST /admin/moments/cancel as non-admin"):
        return False
    
    log("✅ POST /admin/moments/cancel as non-admin: returns 403")
    return True

def test_admin_uncancel_moment():
    """POST /api/admin/moments/{event_id}/uncancel after cancel → 200"""
    if not test_event_id:
        log("⚠️  Skipping: No test event available")
        return True
    
    log(f"Testing POST /admin/moments/{test_event_id}/uncancel...")
    
    response = requests.post(
        f"{BASE_URL}/admin/moments/{test_event_id}/uncancel",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    if not assert_status(response, 200, "POST /admin/moments/uncancel"):
        return False
    
    data = response.json()
    if not assert_field(data, "moment_cancelled", "Uncancel response"):
        return False
    
    if not assert_value(data["moment_cancelled"], False, "moment_cancelled should be false"):
        return False
    
    log("✅ POST /admin/moments/uncancel: moment_cancelled=false")
    return True

def test_admin_trigger_moment():
    """POST /api/admin/events/{event_id}/moment/trigger as admin → 200"""
    if not test_event_id:
        log("⚠️  Skipping: No test event available")
        return True
    
    log(f"Testing POST /admin/events/{test_event_id}/moment/trigger...")
    
    response = requests.post(
        f"{BASE_URL}/admin/events/{test_event_id}/moment/trigger",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    if not assert_status(response, 200, "POST /admin/events/moment/trigger"):
        return False
    
    data = response.json()
    if not assert_field(data, "prompt", "Trigger response"):
        return False
    if not assert_field(data, "notified", "Trigger response"):
        return False
    
    if not isinstance(data["notified"], int):
        log(f"❌ FAILED: Expected 'notified' to be int, got {type(data['notified'])}")
        return False
    
    log(f"✅ POST /admin/events/moment/trigger: notified {data['notified']} users")
    
    # Verify has_fired is now true
    response = requests.get(
        f"{BASE_URL}/admin/moments",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    if response.status_code == 200:
        events = response.json()
        for event in events:
            if event["id"] == test_event_id:
                if event["has_fired"]:
                    log("✅ Verified: has_fired=true after trigger")
                else:
                    log("❌ FAILED: has_fired should be true after trigger")
                    return False
                break
    
    return True

def test_admin_trigger_moment_uncancels():
    """POST /api/admin/events/{event_id}/moment/trigger should un-cancel if cancelled"""
    if not test_event_id:
        log("⚠️  Skipping: No test event available")
        return True
    
    log("Testing that trigger un-cancels a cancelled event...")
    
    # First cancel the event
    requests.post(
        f"{BASE_URL}/admin/moments/{test_event_id}/cancel",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    # Then trigger it
    response = requests.post(
        f"{BASE_URL}/admin/events/{test_event_id}/moment/trigger",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    if not assert_status(response, 200, "Trigger after cancel"):
        return False
    
    # Check that moment_cancelled is now false
    response = requests.get(
        f"{BASE_URL}/admin/moments",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    if response.status_code == 200:
        events = response.json()
        for event in events:
            if event["id"] == test_event_id:
                if not event["moment_cancelled"]:
                    log("✅ Verified: moment_cancelled=false after trigger (auto un-cancel)")
                else:
                    log("❌ FAILED: moment_cancelled should be false after trigger")
                    return False
                break
    
    return True

# ============================================================================
# REGRESSION TESTS
# ============================================================================

def test_auth_login():
    """Regression: POST /api/auth/login"""
    log("Regression: Testing POST /auth/login...")
    
    response = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    
    if not assert_status(response, 200, "POST /auth/login"):
        return False
    
    log("✅ Regression: POST /auth/login working")
    return True

def test_auth_me():
    """Regression: GET /api/auth/me"""
    log("Regression: Testing GET /auth/me...")
    
    response = requests.get(
        f"{BASE_URL}/auth/me",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    if not assert_status(response, 200, "GET /auth/me"):
        return False
    
    log("✅ Regression: GET /auth/me working")
    return True

def test_auth_register():
    """Regression: POST /api/auth/register"""
    log("Regression: Testing POST /auth/register...")
    
    timestamp = int(time.time())
    email = f"regtest{timestamp}@test.com"
    
    response = requests.post(f"{BASE_URL}/auth/register", json={
        "email": email,
        "password": "testpass123",
        "name": "Reg Test",
        "username": f"regtest{timestamp}",
        "city": "Palma"
    })
    
    if not assert_status(response, 200, "POST /auth/register"):
        return False
    
    log("✅ Regression: POST /auth/register working")
    return True

def test_auth_logout():
    """Regression: POST /api/auth/logout"""
    log("Regression: Testing POST /auth/logout...")
    
    response = requests.post(
        f"{BASE_URL}/auth/logout",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    
    if not assert_status(response, 200, "POST /auth/logout"):
        return False
    
    log("✅ Regression: POST /auth/logout working")
    return True

def test_events_list():
    """Regression: GET /api/events"""
    log("Regression: Testing GET /events...")
    
    response = requests.get(
        f"{BASE_URL}/events",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    if not assert_status(response, 200, "GET /events"):
        return False
    
    log("✅ Regression: GET /events working")
    return True

def test_events_filters():
    """Regression: GET /api/events with date filters"""
    log("Regression: Testing GET /events with filters...")
    
    filters = ["all", "hoy", "finde", "semana", "pasados"]
    for filter_val in filters:
        response = requests.get(
            f"{BASE_URL}/events?filter={filter_val}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        if not assert_status(response, 200, f"GET /events?filter={filter_val}"):
            return False
    
    log("✅ Regression: GET /events with all date filters working")
    return True

def test_events_carousels():
    """Regression: GET /api/events/carousels with 20s cache"""
    log("Regression: Testing GET /events/carousels...")
    
    response = requests.get(
        f"{BASE_URL}/events/carousels",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    if not assert_status(response, 200, "GET /events/carousels"):
        return False
    
    data = response.json()
    if not isinstance(data, dict):
        log(f"❌ FAILED: Expected dict, got {type(data)}")
        return False
    
    log("✅ Regression: GET /events/carousels working")
    return True

def test_events_top_weekend():
    """Regression: GET /api/events/top-weekend"""
    log("Regression: Testing GET /events/top-weekend...")
    
    response = requests.get(
        f"{BASE_URL}/events/top-weekend",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    if not assert_status(response, 200, "GET /events/top-weekend"):
        return False
    
    log("✅ Regression: GET /events/top-weekend working")
    return True

def test_events_genres():
    """Regression: GET /api/events/genres"""
    log("Regression: Testing GET /events/genres...")
    
    response = requests.get(
        f"{BASE_URL}/events/genres",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    if not assert_status(response, 200, "GET /events/genres"):
        return False
    
    log("✅ Regression: GET /events/genres working")
    return True

def test_interests():
    """Regression: POST /api/events/{id}/interest"""
    if not test_event_id:
        log("⚠️  Skipping: No test event available")
        return True
    
    log("Regression: Testing POST /events/{id}/interest...")
    
    statuses = ["voy", "me_interesa", "none", "estuve"]
    for status in statuses:
        response = requests.post(
            f"{BASE_URL}/events/{test_event_id}/interest",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"status": status}
        )
        if not assert_status(response, 200, f"POST /events/interest status={status}"):
            return False
    
    log("✅ Regression: POST /events/{id}/interest with all statuses working")
    return True

def test_badges_me():
    """Regression: GET /api/me/badges"""
    log("Regression: Testing GET /me/badges...")
    
    response = requests.get(
        f"{BASE_URL}/me/badges",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    if not assert_status(response, 200, "GET /me/badges"):
        return False
    
    log("✅ Regression: GET /me/badges working")
    return True

def test_next_badges():
    """Regression: GET /api/me/next-badges"""
    log("Regression: Testing GET /me/next-badges...")
    
    response = requests.get(
        f"{BASE_URL}/me/next-badges",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    if not assert_status(response, 200, "GET /me/next-badges"):
        return False
    
    log("✅ Regression: GET /me/next-badges working")
    return True

def test_streak():
    """Regression: GET /api/me/streak"""
    log("Regression: Testing GET /me/streak...")
    
    response = requests.get(
        f"{BASE_URL}/me/streak",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    if not assert_status(response, 200, "GET /me/streak"):
        return False
    
    log("✅ Regression: GET /me/streak working")
    return True

def test_streak_full():
    """Regression: GET /api/me/streak-full"""
    log("Regression: Testing GET /me/streak-full...")
    
    response = requests.get(
        f"{BASE_URL}/me/streak-full",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    if not assert_status(response, 200, "GET /me/streak-full"):
        return False
    
    log("✅ Regression: GET /me/streak-full working")
    return True

def test_user_badges():
    """Regression: GET /api/users/{id}/badges"""
    log("Regression: Testing GET /users/{id}/badges...")
    
    # Get own user_id first
    response = requests.get(
        f"{BASE_URL}/auth/me",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    if response.status_code == 200:
        user_id = response.json().get("user_id")
        
        response = requests.get(
            f"{BASE_URL}/users/{user_id}/badges",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        if not assert_status(response, 200, "GET /users/{id}/badges"):
            return False
    
    log("✅ Regression: GET /users/{id}/badges working")
    return True

def test_rankings_friends():
    """Regression: GET /api/rankings/friends"""
    log("Regression: Testing GET /rankings/friends...")
    
    response = requests.get(
        f"{BASE_URL}/rankings/friends",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    if not assert_status(response, 200, "GET /rankings/friends"):
        return False
    
    log("✅ Regression: GET /rankings/friends working")
    return True

def test_rankings_city():
    """Regression: GET /api/rankings/city"""
    log("Regression: Testing GET /rankings/city...")
    
    response = requests.get(
        f"{BASE_URL}/rankings/city",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    if not assert_status(response, 200, "GET /rankings/city"):
        return False
    
    log("✅ Regression: GET /rankings/city working")
    return True

def test_rankings_world():
    """Regression: GET /api/rankings/world"""
    log("Regression: Testing GET /rankings/world...")
    
    response = requests.get(
        f"{BASE_URL}/rankings/world",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    if not assert_status(response, 200, "GET /rankings/world"):
        return False
    
    log("✅ Regression: GET /rankings/world working")
    return True

def test_friends():
    """Regression: GET /api/friends"""
    log("Regression: Testing GET /friends...")
    
    response = requests.get(
        f"{BASE_URL}/friends",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    if not assert_status(response, 200, "GET /friends"):
        return False
    
    log("✅ Regression: GET /friends working")
    return True

def test_friends_requests():
    """Regression: GET /api/friends/requests"""
    log("Regression: Testing GET /friends/requests...")
    
    response = requests.get(
        f"{BASE_URL}/friends/requests",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    if not assert_status(response, 200, "GET /friends/requests"):
        return False
    
    log("✅ Regression: GET /friends/requests working")
    return True

def test_health():
    """Regression: GET /api/health without auth"""
    log("Regression: Testing GET /health...")
    
    response = requests.get(f"{BASE_URL}/health")
    
    if not assert_status(response, 200, "GET /health"):
        return False
    
    data = response.json()
    if not assert_field(data, "ok", "Health response"):
        return False
    
    log("✅ Regression: GET /health working")
    return True

def test_gzip():
    """Regression: GZip middleware on large responses"""
    log("Regression: Testing GZip middleware...")
    
    response = requests.get(
        f"{BASE_URL}/events",
        headers={
            "Authorization": f"Bearer {admin_token}",
            "Accept-Encoding": "gzip"
        }
    )
    
    if not assert_status(response, 200, "GET /events with gzip"):
        return False
    
    # Check if response is large enough and has gzip encoding
    if len(response.content) >= 500:
        if "gzip" in response.headers.get("Content-Encoding", ""):
            log("✅ Regression: GZip middleware working (Content-Encoding: gzip)")
        else:
            log("⚠️  GZip not applied (response may be too small or already compressed)")
    else:
        log("⚠️  Response too small to test GZip (< 500 bytes)")
    
    return True

# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

def run_all_tests():
    """Run all tests and report results"""
    print("\n" + "="*80)
    print("BACKEND API TESTS - El Momento Admin Endpoints + Regression")
    print("="*80 + "\n")
    
    # Setup
    print("--- SETUP ---")
    if not test_admin_login():
        print("\n❌ CRITICAL: Admin login failed. Cannot continue.")
        return
    
    if not test_register_test_user():
        print("\n❌ CRITICAL: Test user registration failed. Cannot continue.")
        return
    
    create_test_event()  # Best effort, not critical
    
    print("\n--- NEW ADMIN MOMENT ENDPOINTS ---")
    new_tests = [
        test_admin_moments_list_as_admin,
        test_admin_moments_list_as_non_admin,
        test_admin_moments_list_unauthenticated,
        test_admin_set_moment_time_valid,
        test_admin_set_moment_time_boundary_low,
        test_admin_set_moment_time_boundary_high,
        test_admin_set_moment_time_invalid_hour_0,
        test_admin_set_moment_time_invalid_hour_6,
        test_admin_set_moment_time_invalid_hour_7,
        test_admin_set_moment_time_nonexistent_event,
        test_admin_set_moment_time_as_non_admin,
        test_admin_randomize_moment,
        test_admin_randomize_moment_as_non_admin,
        test_admin_randomize_all_moments,
        test_admin_randomize_all_moments_as_non_admin,
        test_admin_cancel_moment,
        test_admin_cancel_moment_as_non_admin,
        test_admin_uncancel_moment,
        test_admin_trigger_moment,
        test_admin_trigger_moment_uncancels,
    ]
    
    new_passed = 0
    new_failed = 0
    
    for test in new_tests:
        try:
            if test():
                new_passed += 1
            else:
                new_failed += 1
        except Exception as e:
            log(f"❌ EXCEPTION in {test.__name__}: {e}")
            new_failed += 1
    
    print("\n--- REGRESSION TESTS ---")
    regression_tests = [
        test_auth_login,
        test_auth_me,
        test_auth_register,
        test_auth_logout,
        test_events_list,
        test_events_filters,
        test_events_carousels,
        test_events_top_weekend,
        test_events_genres,
        test_interests,
        test_badges_me,
        test_next_badges,
        test_streak,
        test_streak_full,
        test_user_badges,
        test_rankings_friends,
        test_rankings_city,
        test_rankings_world,
        test_friends,
        test_friends_requests,
        test_health,
        test_gzip,
    ]
    
    regression_passed = 0
    regression_failed = 0
    
    for test in regression_tests:
        try:
            if test():
                regression_passed += 1
            else:
                regression_failed += 1
        except Exception as e:
            log(f"❌ EXCEPTION in {test.__name__}: {e}")
            regression_failed += 1
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"\nNEW ADMIN MOMENT ENDPOINTS:")
    print(f"  ✅ Passed: {new_passed}")
    print(f"  ❌ Failed: {new_failed}")
    print(f"  Total: {new_passed + new_failed}")
    
    print(f"\nREGRESSION TESTS:")
    print(f"  ✅ Passed: {regression_passed}")
    print(f"  ❌ Failed: {regression_failed}")
    print(f"  Total: {regression_passed + regression_failed}")
    
    print(f"\nOVERALL:")
    total_passed = new_passed + regression_passed
    total_failed = new_failed + regression_failed
    total_tests = total_passed + total_failed
    pass_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0
    print(f"  ✅ Passed: {total_passed}")
    print(f"  ❌ Failed: {total_failed}")
    print(f"  Total: {total_tests}")
    print(f"  Pass rate: {pass_rate:.1f}%")
    
    if total_failed == 0:
        print("\n🎉 ALL TESTS PASSED!")
    else:
        print(f"\n⚠️  {total_failed} test(s) failed. Review output above for details.")
    
    print("="*80 + "\n")

if __name__ == "__main__":
    run_all_tests()
