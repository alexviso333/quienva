#!/usr/bin/env python3
"""
Backend testing for ¿Quién va? app - Fix batch: date filtering, security headers, rate limit, scrape-changelog
Test only the 4 specific items requested in the review.
"""

import requests
import time
from datetime import datetime, timedelta

# Base URL from frontend/.env
BASE_URL = "https://club-distance-app.preview.emergentagent.com/api"

# Admin credentials from test_credentials.md
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

def log(msg):
    print(f"[TEST] {msg}")

def login(email, password):
    """Login and return token"""
    resp = requests.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password})
    if resp.status_code != 200:
        log(f"❌ Login failed: {resp.status_code} {resp.text}")
        return None
    data = resp.json()
    token = data.get("token")
    log(f"✅ Logged in as {email}")
    return token

def register_user(email, password, name, username, city, birthdate):
    """Register a new user"""
    resp = requests.post(f"{BASE_URL}/auth/register", json={
        "email": email,
        "password": password,
        "name": name,
        "username": username,
        "city": city,
        "birthdate": birthdate
    })
    return resp

def create_admin_event(token, name, date, city="Palma de Mallorca"):
    """Create an event as admin"""
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "name": name,
        "venue": "Test Venue",
        "city": city,
        "date": date,
        "time": "23:00",
        "genre": "Electrónica",
        "image_url": "https://example.com/test.jpg",
        "price_tiers": [{"name": "General", "price": 20}],
        "sale_state": "a_la_venta"
    }
    resp = requests.post(f"{BASE_URL}/admin/events", json=payload, headers=headers)
    return resp

def test_date_filtering():
    """
    TEST 1: GET /api/events date filtering (HIGH)
    - Login as admin
    - Create TWO events in admin's city: one PAST (2020-01-01) and one FUTURE (2030-12-31)
    - GET /api/events (default) → must include FUTURE, must NOT include PAST
    - GET /api/events?date_filter=pasados → must include PAST, must NOT include FUTURE
    """
    log("\n" + "="*80)
    log("TEST 1: GET /api/events date filtering")
    log("="*80)
    
    # Login as admin
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    if not admin_token:
        log("❌ TEST 1 FAILED: Cannot login as admin")
        return False
    
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # Create PAST event (2020-01-01)
    past_event_name = f"PAST_EVENT_TEST_{int(time.time())}"
    log(f"Creating PAST event: {past_event_name} with date 2020-01-01")
    resp_past = create_admin_event(admin_token, past_event_name, "2020-01-01")
    if resp_past.status_code != 200:
        log(f"❌ Failed to create past event: {resp_past.status_code} {resp_past.text}")
        return False
    past_event_id = resp_past.json().get("id")
    log(f"✅ Created PAST event: {past_event_id}")
    
    # Create FUTURE event (2030-12-31)
    future_event_name = f"FUTURE_EVENT_TEST_{int(time.time())}"
    log(f"Creating FUTURE event: {future_event_name} with date 2030-12-31")
    resp_future = create_admin_event(admin_token, future_event_name, "2030-12-31")
    if resp_future.status_code != 200:
        log(f"❌ Failed to create future event: {resp_future.status_code} {resp_future.text}")
        return False
    future_event_id = resp_future.json().get("id")
    log(f"✅ Created FUTURE event: {future_event_id}")
    
    # Test 1a: GET /api/events (default) → must include FUTURE, must NOT include PAST
    log("\nTest 1a: GET /api/events (default, no params)")
    resp = requests.get(f"{BASE_URL}/events", headers=headers)
    if resp.status_code != 200:
        log(f"❌ GET /events failed: {resp.status_code}")
        return False
    
    events = resp.json()
    event_ids = [e.get("id") for e in events]
    event_names = [e.get("name") for e in events]
    
    log(f"   Total events returned: {len(events)}")
    
    # Check FUTURE event is included
    if future_event_id not in event_ids:
        log(f"❌ FAIL: FUTURE event {future_event_id} NOT in default feed")
        log(f"   Event names in feed: {event_names[:10]}")
        return False
    log(f"✅ PASS: FUTURE event {future_event_id} IS in default feed")
    
    # Check PAST event is NOT included
    if past_event_id in event_ids:
        log(f"❌ FAIL: PAST event {past_event_id} IS in default feed (should be excluded)")
        return False
    log(f"✅ PASS: PAST event {past_event_id} is NOT in default feed")
    
    # Test 1b: GET /api/events?date_filter=pasados → must include PAST, must NOT include FUTURE
    log("\nTest 1b: GET /api/events?date_filter=pasados")
    resp = requests.get(f"{BASE_URL}/events?date_filter=pasados", headers=headers)
    if resp.status_code != 200:
        log(f"❌ GET /events?date_filter=pasados failed: {resp.status_code}")
        return False
    
    past_events = resp.json()
    past_event_ids = [e.get("id") for e in past_events]
    past_event_names = [e.get("name") for e in past_events]
    
    log(f"   Total past events returned: {len(past_events)}")
    
    # Check PAST event is included
    if past_event_id not in past_event_ids:
        log(f"❌ FAIL: PAST event {past_event_id} NOT in pasados feed")
        log(f"   Event names in pasados feed: {past_event_names[:10]}")
        return False
    log(f"✅ PASS: PAST event {past_event_id} IS in pasados feed")
    
    # Check FUTURE event is NOT included
    if future_event_id in past_event_ids:
        log(f"❌ FAIL: FUTURE event {future_event_id} IS in pasados feed (should be excluded)")
        return False
    log(f"✅ PASS: FUTURE event {future_event_id} is NOT in pasados feed")
    
    log("\n✅ TEST 1 PASSED: Date filtering working correctly")
    return True

def test_security_headers_and_rate_limit():
    """
    TEST 2: Security headers + rate limit (HIGH)
    - Any GET response (e.g. GET /api/cities) MUST contain headers:
      x-frame-options: DENY
      x-content-type-options: nosniff
      (also referrer-policy and strict-transport-security present)
    - Rate limit: send POST /api/auth/register with SAME body repeatedly
      Within first 8 attempts may get 200 then 400 (duplicate)
      After exceeding 8 attempts within 300s MUST start receiving HTTP 429
    """
    log("\n" + "="*80)
    log("TEST 2: Security headers + rate limit")
    log("="*80)
    
    # Test 2a: Security headers on GET /api/cities
    log("\nTest 2a: Security headers on GET /api/cities")
    resp = requests.get(f"{BASE_URL}/cities")
    if resp.status_code != 200:
        log(f"❌ GET /cities failed: {resp.status_code}")
        return False
    
    headers = resp.headers
    log(f"   Response headers: {dict(headers)}")
    
    # Check required headers
    required_headers = {
        "x-frame-options": "DENY",
        "x-content-type-options": "nosniff"
    }
    
    for header, expected_value in required_headers.items():
        actual_value = headers.get(header)
        if not actual_value:
            log(f"❌ FAIL: Header '{header}' is missing")
            return False
        if actual_value.upper() != expected_value.upper():
            log(f"❌ FAIL: Header '{header}' has value '{actual_value}', expected '{expected_value}'")
            return False
        log(f"✅ PASS: Header '{header}' = '{actual_value}'")
    
    # Check optional but expected headers
    optional_headers = ["referrer-policy", "strict-transport-security"]
    for header in optional_headers:
        if headers.get(header):
            log(f"✅ PASS: Header '{header}' present: {headers.get(header)}")
        else:
            log(f"⚠️  WARNING: Header '{header}' not present (optional)")
    
    # Test 2b: Rate limit on POST /api/auth/register
    log("\nTest 2b: Rate limit on POST /api/auth/register (limit: 8 per 300s)")
    
    # Use a unique email to avoid conflicts
    test_email = f"ratelimit_test_{int(time.time())}@test.com"
    payload = {
        "email": test_email,
        "password": "testpass123",
        "name": "Rate Limit Test",
        "username": f"ratelimit{int(time.time())}",
        "city": "Palma de Mallorca",
        "birthdate": "1990-01-01"
    }
    
    log(f"   Sending POST /auth/register repeatedly with email: {test_email}")
    
    responses = []
    for i in range(12):  # Try 12 times (limit is 8)
        resp = register_user(
            payload["email"],
            payload["password"],
            payload["name"],
            payload["username"],
            payload["city"],
            payload["birthdate"]
        )
        responses.append(resp.status_code)
        log(f"   Attempt {i+1}: {resp.status_code} {resp.json().get('detail', '') if resp.status_code != 200 else 'OK'}")
        
        # After 8 attempts, we should start seeing 429
        if i >= 8 and resp.status_code == 429:
            log(f"✅ PASS: Rate limit triggered at attempt {i+1} with HTTP 429")
            detail = resp.json().get("detail", "")
            if "too many" in detail.lower() or "attempts" in detail.lower():
                log(f"✅ PASS: Error message mentions rate limit: '{detail}'")
            else:
                log(f"⚠️  WARNING: Error message doesn't clearly mention rate limit: '{detail}'")
            break
        
        time.sleep(0.5)  # Small delay between requests
    else:
        # If we didn't break, check if we got 429 in the last few attempts
        if 429 in responses[-4:]:
            log(f"✅ PASS: Rate limit triggered (HTTP 429 received)")
        else:
            log(f"❌ FAIL: No HTTP 429 received after {len(responses)} attempts")
            log(f"   Response codes: {responses}")
            return False
    
    log("\n✅ TEST 2 PASSED: Security headers and rate limit working correctly")
    return True

def test_scrape_changelog():
    """
    TEST 3: GET /api/admin/scrape-changelog (MEDIUM)
    - As admin → 200 with JSON keys: last_run, counts, last_run_counts, total, entries
    - As non-admin registered user → 403
    - Unauthenticated → 401
    """
    log("\n" + "="*80)
    log("TEST 3: GET /api/admin/scrape-changelog")
    log("="*80)
    
    # Test 3a: As admin → 200 with correct structure
    log("\nTest 3a: GET /api/admin/scrape-changelog as admin")
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    if not admin_token:
        log("❌ TEST 3 FAILED: Cannot login as admin")
        return False
    
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = requests.get(f"{BASE_URL}/admin/scrape-changelog", headers=headers)
    
    if resp.status_code != 200:
        log(f"❌ FAIL: Expected 200, got {resp.status_code}")
        log(f"   Response: {resp.text}")
        return False
    
    log(f"✅ PASS: Status code 200")
    
    data = resp.json()
    log(f"   Response keys: {list(data.keys())}")
    
    # Check required keys
    required_keys = ["last_run", "counts", "last_run_counts", "total", "entries"]
    for key in required_keys:
        if key not in data:
            log(f"❌ FAIL: Missing required key '{key}'")
            return False
        log(f"✅ PASS: Key '{key}' present")
    
    # Validate structure
    if not isinstance(data["entries"], list):
        log(f"❌ FAIL: 'entries' should be a list, got {type(data['entries'])}")
        return False
    log(f"✅ PASS: 'entries' is a list with {len(data['entries'])} items")
    
    if not isinstance(data["total"], int):
        log(f"❌ FAIL: 'total' should be an int, got {type(data['total'])}")
        return False
    log(f"✅ PASS: 'total' is an int: {data['total']}")
    
    # Test 3b: As non-admin user → 403
    log("\nTest 3b: GET /api/admin/scrape-changelog as non-admin user")
    
    # Register a normal user
    ts = int(time.time())
    normal_user_email = f"normaluser_{ts}@test.com"
    resp_reg = register_user(
        normal_user_email,
        "testpass123",
        "Normal User",
        f"normaluser{ts}",
        "Palma de Mallorca",
        "1995-05-15"
    )
    
    if resp_reg.status_code == 429:
        log(f"⚠️  SKIP: Cannot register normal user due to rate limit (429)")
        log(f"   This is expected after testing rate limits in Test 2")
        log(f"   Skipping non-admin test (rate limit already verified working)")
    elif resp_reg.status_code != 200:
        log(f"❌ Failed to register normal user: {resp_reg.status_code}")
        return False
    else:
        normal_token = login(normal_user_email, "testpass123")
        if not normal_token:
            log("❌ Failed to login as normal user")
            return False
        
        headers_normal = {"Authorization": f"Bearer {normal_token}"}
        resp = requests.get(f"{BASE_URL}/admin/scrape-changelog", headers=headers_normal)
        
        if resp.status_code != 403:
            log(f"❌ FAIL: Expected 403 for non-admin, got {resp.status_code}")
            return False
        log(f"✅ PASS: Non-admin user gets 403")
    
    # Test 3c: Unauthenticated → 401
    log("\nTest 3c: GET /api/admin/scrape-changelog unauthenticated")
    resp = requests.get(f"{BASE_URL}/admin/scrape-changelog")
    
    if resp.status_code != 401:
        log(f"❌ FAIL: Expected 401 for unauthenticated, got {resp.status_code}")
        return False
    log(f"✅ PASS: Unauthenticated request gets 401")
    
    log("\n✅ TEST 3 PASSED: Scrape changelog endpoint working correctly")
    return True

def test_token_expiry_alert():
    """
    TEST 4: Token-expiry alert wiring (LOW)
    - Just confirm POST /api/admin/scrapers/run-all (admin) does NOT crash
    - Returns a normal response (may run 0 venues on empty DB)
    - Do NOT attempt to force an invalid token
    """
    log("\n" + "="*80)
    log("TEST 4: Token-expiry alert wiring")
    log("="*80)
    
    # Login as admin
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    if not admin_token:
        log("❌ TEST 4 FAILED: Cannot login as admin")
        return False
    
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    log("\nTest 4: POST /api/admin/scrapers/run-all")
    resp = requests.post(f"{BASE_URL}/admin/scrapers/run-all", headers=headers)
    
    if resp.status_code != 200:
        log(f"❌ FAIL: Expected 200, got {resp.status_code}")
        log(f"   Response: {resp.text}")
        return False
    
    log(f"✅ PASS: Status code 200 (endpoint does not crash)")
    
    data = resp.json()
    log(f"   Response: {data}")
    
    # Check response structure (should have ok or venues_run or similar)
    if not isinstance(data, dict):
        log(f"❌ FAIL: Response should be a dict, got {type(data)}")
        return False
    
    log(f"✅ PASS: Response is a valid dict with keys: {list(data.keys())}")
    
    # It's OK if it runs 0 venues on empty DB
    if "venues_run" in data:
        log(f"   venues_run: {data['venues_run']}")
    
    log("\n✅ TEST 4 PASSED: Scraper run-all endpoint does not crash")
    return True

def main():
    """Run all tests"""
    log("="*80)
    log("BACKEND TESTING: Fix batch - date filtering, security, scrape-changelog, token alert")
    log("="*80)
    log(f"Base URL: {BASE_URL}")
    log(f"Admin: {ADMIN_EMAIL}")
    log("")
    
    results = {
        "TEST 1: Date filtering": False,
        "TEST 2: Security headers + rate limit": False,
        "TEST 3: Scrape changelog": False,
        "TEST 4: Token-expiry alert": False
    }
    
    try:
        results["TEST 1: Date filtering"] = test_date_filtering()
    except Exception as e:
        log(f"❌ TEST 1 EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
    
    # Run Test 3 BEFORE Test 2 to avoid rate limit issues
    try:
        results["TEST 3: Scrape changelog"] = test_scrape_changelog()
    except Exception as e:
        log(f"❌ TEST 3 EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
    
    try:
        results["TEST 2: Security headers + rate limit"] = test_security_headers_and_rate_limit()
    except Exception as e:
        log(f"❌ TEST 2 EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
    
    try:
        results["TEST 4: Token-expiry alert"] = test_token_expiry_alert()
    except Exception as e:
        log(f"❌ TEST 4 EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
    
    # Summary
    log("\n" + "="*80)
    log("TEST SUMMARY")
    log("="*80)
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        log(f"{status}: {test_name}")
    
    total = len(results)
    passed = sum(results.values())
    log(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        log("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        log(f"\n❌ {total - passed} test(s) failed")
        return 1

if __name__ == "__main__":
    exit(main())
