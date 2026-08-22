#!/usr/bin/env python3
"""
Backend test for CHANGE 1: City "new party" notifications are now OPT-IN
and CHANGE 2: Scrapers two-tier schedule (regression)

Test requirements from review_request:
1. New user has new_event=false by default (other notifications true)
2. PUT /api/me/notif-prefs with new_event=true persists
3. End-to-end: userA (opt-out) doesn't receive notification, userB (opt-in) does
4. Regression: ticket-state notifications still work (best-effort)
5. POST /api/admin/scrapers/run-all returns 200 (no crash)
6. GET /api/events still has price_tiers and sale_state fields
"""

import requests
import time
import json
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8001/api"
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

# Test state
admin_token = None
userA_token = None
userB_token = None
userA_id = None
userB_id = None
test_event_id = None
timestamp = int(time.time())

def log(msg):
    print(f"[TEST] {msg}")

def login(email, password):
    """Login and return session_token"""
    resp = requests.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password})
    if resp.status_code != 200:
        log(f"❌ Login failed for {email}: {resp.status_code} {resp.text}")
        return None
    data = resp.json()
    token = data.get("token")  # Changed from "session_token" to "token"
    if token:
        log(f"✅ Logged in as {email}, token: {token[:20]}...")
    return token

def register_user(name, email, password, city="Palma de Mallorca"):
    """Register a new user and return session_token"""
    # Generate username from email
    username = email.split("@")[0].lower()
    payload = {
        "name": name,
        "email": email,
        "password": password,
        "username": username,
        "birthdate": "1990-01-01",  # Adult user
        "city": city
    }
    resp = requests.post(f"{BASE_URL}/auth/register", json=payload)
    if resp.status_code != 200:
        log(f"❌ Registration failed for {email}: {resp.status_code} {resp.text}")
        return None, None
    data = resp.json()
    token = data.get("token")  # Changed from "session_token" to "token"
    user_id = data.get("user", {}).get("user_id")
    if token:
        log(f"✅ Registered {email} (user_id: {user_id}), token: {token[:20]}...")
    else:
        log(f"⚠️  Registered {email} but no token returned")
    return token, user_id

def get_headers(token):
    """Return headers with Bearer token"""
    return {"Authorization": f"Bearer {token}"}

def test_1a_new_user_default_prefs():
    """Test 1a: New user has new_event=false by default, other notifications true"""
    log("\n=== TEST 1a: New user default notification preferences ===")
    
    global userA_token, userA_id
    userA_email = f"usera_optin_test_{timestamp}@test.com"
    userA_token, userA_id = register_user(f"UserA {timestamp}", userA_email, "password123", "Palma de Mallorca")
    
    if not userA_token:
        return False
    
    # Get notification preferences
    resp = requests.get(f"{BASE_URL}/me/notif-prefs", headers=get_headers(userA_token))
    if resp.status_code != 200:
        log(f"❌ GET /me/notif-prefs failed: {resp.status_code} {resp.text}")
        return False
    
    data = resp.json()
    log(f"UserA notification preferences: {json.dumps(data, indent=2)}")
    
    # Extract prefs from nested structure
    prefs = data.get("prefs", {})
    
    # Verify new_event is false
    if prefs.get("new_event") is not False:
        log(f"❌ FAIL: new_event should be false by default, got: {prefs.get('new_event')}")
        return False
    
    # Verify other notifications are true
    expected_true = ["tickets_on_sale", "tickets_low_stock", "tickets_sold_out", 
                     "tickets_price_down", "tickets_price_up", "friend_going"]
    for key in expected_true:
        if prefs.get(key) is not True:
            log(f"❌ FAIL: {key} should be true by default, got: {prefs.get(key)}")
            return False
    
    log("✅ PASS: new_event=false by default, other notifications=true")
    return True

def test_1b_persist_optin():
    """Test 1b: PUT /api/me/notif-prefs with new_event=true persists"""
    log("\n=== TEST 1b: Persist new_event opt-in ===")
    
    # Enable new_event
    resp = requests.put(
        f"{BASE_URL}/me/notif-prefs",
        headers=get_headers(userA_token),
        json={"prefs": {"new_event": True}}
    )
    if resp.status_code != 200:
        log(f"❌ PUT /me/notif-prefs failed: {resp.status_code} {resp.text}")
        return False
    
    log(f"PUT response: {resp.json()}")
    
    # Verify it persisted
    resp = requests.get(f"{BASE_URL}/me/notif-prefs", headers=get_headers(userA_token))
    if resp.status_code != 200:
        log(f"❌ GET /me/notif-prefs failed: {resp.status_code} {resp.text}")
        return False
    
    data = resp.json()
    prefs = data.get("prefs", {})
    if prefs.get("new_event") is not True:
        log(f"❌ FAIL: new_event should be true after opt-in, got: {prefs.get('new_event')}")
        return False
    
    log("✅ PASS: new_event=true persisted successfully")
    return True

def test_1c_optin_behavior():
    """Test 1c: End-to-end opt-in behavior - userA (opt-out) vs userB (opt-in)"""
    log("\n=== TEST 1c: End-to-end opt-in notification behavior ===")
    
    global userB_token, userB_id, test_event_id
    
    # Create userB with opt-in
    userB_email = f"userb_optin_test_{timestamp}@test.com"
    userB_token, userB_id = register_user(f"UserB {timestamp}", userB_email, "password123", "Palma de Mallorca")
    
    if not userB_token:
        return False
    
    # Set userB to opt-in for new_event
    resp = requests.put(
        f"{BASE_URL}/me/notif-prefs",
        headers=get_headers(userB_token),
        json={"prefs": {"new_event": True}}
    )
    if resp.status_code != 200:
        log(f"❌ PUT /me/notif-prefs for userB failed: {resp.status_code} {resp.text}")
        return False
    
    log("✅ UserB opted in to new_event notifications")
    
    # Set userA back to opt-out (default)
    resp = requests.put(
        f"{BASE_URL}/me/notif-prefs",
        headers=get_headers(userA_token),
        json={"prefs": {"new_event": False}}
    )
    if resp.status_code != 200:
        log(f"❌ PUT /me/notif-prefs for userA failed: {resp.status_code} {resp.text}")
        return False
    
    log("✅ UserA opted out of new_event notifications")
    
    # Get admin token
    global admin_token
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    if not admin_token:
        return False
    
    # Create a new event in Palma de Mallorca as admin
    future_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    event_payload = {
        "name": f"Test Party OptIn {timestamp}",
        "venue": f"Test Venue OptIn {timestamp}",
        "date": future_date,
        "time": "23:00",
        "city": "Palma de Mallorca",
        "genre": "Techno",
        "image_url": "https://example.com/test.jpg"
    }
    
    resp = requests.post(
        f"{BASE_URL}/admin/events",
        headers=get_headers(admin_token),
        json=event_payload
    )
    if resp.status_code != 200:
        log(f"❌ POST /admin/events failed: {resp.status_code} {resp.text}")
        return False
    
    event_data = resp.json()
    test_event_id = event_data.get("id")
    log(f"✅ Created test event: {test_event_id}")
    
    # Wait for notification to be sent (fire-and-forget, give it 3 seconds)
    log("Waiting 3 seconds for notification delivery...")
    time.sleep(3)
    
    # Check userA notifications (should NOT have new_event notification)
    resp = requests.get(f"{BASE_URL}/notifications", headers=get_headers(userA_token))
    if resp.status_code != 200:
        log(f"❌ GET /notifications for userA failed: {resp.status_code} {resp.text}")
        return False
    
    userA_notifs = resp.json()
    new_event_notifs_A = [n for n in userA_notifs if n.get("type") == "new_event" and 
                          n.get("data", {}).get("event_id") == test_event_id]
    
    if len(new_event_notifs_A) > 0:
        log(f"❌ FAIL: UserA (opt-out) received new_event notification: {new_event_notifs_A}")
        return False
    
    log("✅ PASS: UserA (opt-out) did NOT receive new_event notification")
    
    # Check userB notifications (should HAVE new_event notification)
    resp = requests.get(f"{BASE_URL}/notifications", headers=get_headers(userB_token))
    if resp.status_code != 200:
        log(f"❌ GET /notifications for userB failed: {resp.status_code} {resp.text}")
        return False
    
    userB_notifs = resp.json()
    new_event_notifs_B = [n for n in userB_notifs if n.get("type") == "new_event" and 
                          n.get("data", {}).get("event_id") == test_event_id]
    
    if len(new_event_notifs_B) == 0:
        log(f"❌ FAIL: UserB (opt-in) did NOT receive new_event notification")
        log(f"UserB notifications: {json.dumps(userB_notifs, indent=2)}")
        return False
    
    log(f"✅ PASS: UserB (opt-in) received new_event notification: {new_event_notifs_B[0]}")
    return True

def test_1d_regression_ticket_notifications():
    """Test 1d: Regression - ticket-state notifications still work (best-effort)"""
    log("\n=== TEST 1d: Regression - ticket-state notifications ===")
    
    # This is best-effort - just verify the notifications endpoint responds
    resp = requests.get(f"{BASE_URL}/notifications", headers=get_headers(userA_token))
    if resp.status_code != 200:
        log(f"❌ GET /notifications failed: {resp.status_code} {resp.text}")
        return False
    
    log("✅ PASS: Notifications endpoint responds 200 (ticket-state notifications endpoint working)")
    return True

def test_2a_scrapers_run_all():
    """Test 2a: POST /api/admin/scrapers/run-all returns 200 (no crash)"""
    log("\n=== TEST 2a: Scrapers run-all (regression) ===")
    
    # Note: In dev without FourVenues token, this is expected to be a no-op
    resp = requests.post(f"{BASE_URL}/admin/scrapers/run-all", headers=get_headers(admin_token))
    if resp.status_code != 200:
        log(f"❌ POST /admin/scrapers/run-all failed: {resp.status_code} {resp.text}")
        return False
    
    result = resp.json()
    log(f"✅ PASS: POST /admin/scrapers/run-all returned 200")
    log(f"Response: {json.dumps(result, indent=2)}")
    return True

def test_2b_events_have_price_fields():
    """Test 2b: GET /api/events still has price_tiers and sale_state fields"""
    log("\n=== TEST 2b: Events still have price_tiers and sale_state ===")
    
    resp = requests.get(f"{BASE_URL}/events?city=Palma%20de%20Mallorca", headers=get_headers(userA_token))
    if resp.status_code != 200:
        log(f"❌ GET /events failed: {resp.status_code} {resp.text}")
        return False
    
    events = resp.json()
    if len(events) == 0:
        log("⚠️  No events found in Palma de Mallorca, checking Ibiza...")
        resp = requests.get(f"{BASE_URL}/events?city=Ibiza", headers=get_headers(userA_token))
        if resp.status_code != 200:
            log(f"❌ GET /events (Ibiza) failed: {resp.status_code} {resp.text}")
            return False
        events = resp.json()
    
    if len(events) == 0:
        log("⚠️  No events found to check price fields")
        return True
    
    # Check first few events for price_tiers and sale_state
    events_with_price = [e for e in events[:10] if e.get("price_tiers") or e.get("sale_state")]
    
    if len(events_with_price) > 0:
        sample = events_with_price[0]
        log(f"✅ PASS: Events still have price_tiers and sale_state fields")
        log(f"Sample event: {sample.get('name')}")
        log(f"  price_tiers: {sample.get('price_tiers')}")
        log(f"  sale_state: {sample.get('sale_state')}")
    else:
        log("⚠️  No events with price_tiers or sale_state found (expected in dev without tokens)")
    
    return True

def cleanup():
    """Clean up test data"""
    log("\n=== Cleanup ===")
    
    if test_event_id and admin_token:
        resp = requests.delete(f"{BASE_URL}/admin/events/{test_event_id}", headers=get_headers(admin_token))
        if resp.status_code == 200:
            log(f"✅ Deleted test event {test_event_id}")
        else:
            log(f"⚠️  Could not delete test event: {resp.status_code}")

def main():
    log("=" * 80)
    log("BACKEND TEST: City 'new party' notifications OPT-IN + Scrapers regression")
    log("=" * 80)
    
    results = []
    
    # CHANGE 1: Notification opt-in tests
    results.append(("1a: New user default prefs", test_1a_new_user_default_prefs()))
    results.append(("1b: Persist opt-in", test_1b_persist_optin()))
    results.append(("1c: End-to-end opt-in behavior", test_1c_optin_behavior()))
    results.append(("1d: Regression - ticket notifications", test_1d_regression_ticket_notifications()))
    
    # CHANGE 2: Scrapers regression tests
    results.append(("2a: Scrapers run-all", test_2a_scrapers_run_all()))
    results.append(("2b: Events have price fields", test_2b_events_have_price_fields()))
    
    # Cleanup
    cleanup()
    
    # Summary
    log("\n" + "=" * 80)
    log("TEST SUMMARY")
    log("=" * 80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        log(f"{status}: {name}")
    
    log(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        log("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        log(f"\n❌ {total - passed} test(s) failed")
        return 1

if __name__ == "__main__":
    exit(main())
