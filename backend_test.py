#!/usr/bin/env python3
"""
Backend testing for ¿Quién va? app - Iteration 2026-08-02i
Testing: Bug fix (reject ticket), notify feature, performance endpoints
"""

import requests
import json
import time
from datetime import datetime

# Base URL from frontend/.env
BASE_URL = "https://04ef964d-e7a3-4272-aa05-db85d0d80903.preview.emergentagent.com/api"

# Test credentials
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

# Test results
results = {
    "passed": 0,
    "failed": 0,
    "tests": []
}

def log_test(name, passed, details=""):
    """Log test result"""
    status = "✅ PASS" if passed else "❌ FAIL"
    results["tests"].append({"name": name, "passed": passed, "details": details})
    if passed:
        results["passed"] += 1
    else:
        results["failed"] += 1
    print(f"{status}: {name}")
    if details:
        print(f"  → {details}")

def register_user(email, password, name, username):
    """Register a new user"""
    try:
        resp = requests.post(f"{BASE_URL}/auth/register", json={
            "email": email,
            "password": password,
            "name": name,
            "username": username,
            "city": "Palma"
        }, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception as e:
        print(f"Register error: {e}")
        return None

def login(email, password):
    """Login and return token"""
    try:
        resp = requests.post(f"{BASE_URL}/auth/login", json={
            "email": email,
            "password": password
        }, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("token")
        return None
    except Exception as e:
        print(f"Login error: {e}")
        return None

def get_headers(token):
    """Get authorization headers"""
    return {"Authorization": f"Bearer {token}"}

# ============================================================================
# SETUP: Login admin and create normal user
# ============================================================================
print("\n" + "="*80)
print("SETUP: Logging in and creating test user")
print("="*80)

admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
if not admin_token:
    print("❌ CRITICAL: Cannot login as admin")
    exit(1)
print(f"✅ Admin logged in")

# Create a normal user for testing
test_user_email = f"testuser_{int(time.time())}@test.com"
test_user_password = "TestPass123!"
test_user_name = "Test User"
test_user_username = f"testuser{int(time.time())}"

user_data = register_user(test_user_email, test_user_password, test_user_name, test_user_username)
if not user_data:
    print("❌ CRITICAL: Cannot register test user")
    exit(1)

user_token = user_data.get("token")
if not user_token:
    print("❌ CRITICAL: No token from registration")
    exit(1)
print(f"✅ Test user created: {test_user_email}")

# ============================================================================
# CRITICAL BUG FIX: Reject pending ticket removes it from pending list
# ============================================================================
print("\n" + "="*80)
print("CRITICAL BUG FIX: Reject pending ticket removes it from pending list")
print("="*80)

# Step 1: Get an event to create ticket purchases
try:
    resp = requests.get(f"{BASE_URL}/events", headers=get_headers(user_token), timeout=10)
    if resp.status_code != 200:
        print(f"❌ Error getting events: Status {resp.status_code}, Body: {resp.text[:200]}")
        exit(1)
    events = resp.json()
    if not events or len(events) == 0:
        print("❌ No events available for testing")
        # Try to get events as admin
        resp = requests.get(f"{BASE_URL}/events", headers=get_headers(admin_token), timeout=10)
        if resp.status_code == 200:
            events = resp.json()
        if not events or len(events) == 0:
            print("❌ No events available even as admin")
            exit(1)
    test_event_id = events[0]["id"]
    print(f"✅ Using event: {events[0]['name']} (ID: {test_event_id})")
except Exception as e:
    print(f"❌ Error getting events: {e}")
    exit(1)

# Step 2: Create 2 ticket purchases as normal user
purchase_ids = []
for i in range(2):
    try:
        resp = requests.post(
            f"{BASE_URL}/tickets/click",
            json={"event_id": test_event_id},
            headers=get_headers(user_token),
            timeout=10
        )
        if resp.status_code == 200:
            purchase_id = resp.json().get("id")
            purchase_ids.append(purchase_id)
            log_test(f"Create ticket purchase #{i+1}", True, f"Purchase ID: {purchase_id}")
        else:
            log_test(f"Create ticket purchase #{i+1}", False, f"Status: {resp.status_code}")
    except Exception as e:
        log_test(f"Create ticket purchase #{i+1}", False, str(e))

if len(purchase_ids) < 2:
    print("❌ CRITICAL: Could not create 2 ticket purchases")
    exit(1)

# Step 3: GET /api/admin/tickets?status=pending as admin -> purchases appear
try:
    resp = requests.get(
        f"{BASE_URL}/admin/tickets?status=pending",
        headers=get_headers(admin_token),
        timeout=10
    )
    if resp.status_code == 200:
        pending_tickets = resp.json()
        pending_ids = [t["id"] for t in pending_tickets]
        both_present = all(pid in pending_ids for pid in purchase_ids)
        log_test(
            "GET /admin/tickets?status=pending shows both purchases",
            both_present,
            f"Found {len([p for p in purchase_ids if p in pending_ids])}/2 purchases"
        )
    else:
        log_test("GET /admin/tickets?status=pending", False, f"Status: {resp.status_code}")
except Exception as e:
    log_test("GET /admin/tickets?status=pending", False, str(e))

# Step 4: REJECT first purchase (confirmed: false)
try:
    resp = requests.post(
        f"{BASE_URL}/admin/tickets/confirm",
        json={"purchase_id": purchase_ids[0], "confirmed": False},
        headers=get_headers(admin_token),
        timeout=10
    )
    log_test(
        "POST /admin/tickets/confirm (REJECT)",
        resp.status_code == 200,
        f"Status: {resp.status_code}"
    )
except Exception as e:
    log_test("POST /admin/tickets/confirm (REJECT)", False, str(e))

# Step 5: GET /admin/tickets?status=pending again -> rejected purchase MUST be GONE
try:
    resp = requests.get(
        f"{BASE_URL}/admin/tickets?status=pending",
        headers=get_headers(admin_token),
        timeout=10
    )
    if resp.status_code == 200:
        pending_tickets = resp.json()
        pending_ids = [t["id"] for t in pending_tickets]
        rejected_not_present = purchase_ids[0] not in pending_ids
        log_test(
            "BUG FIX VERIFIED: Rejected ticket NOT in pending list",
            rejected_not_present,
            f"Rejected ID {purchase_ids[0]} {'NOT found' if rejected_not_present else 'STILL FOUND (BUG!)'} in pending"
        )
    else:
        log_test("GET /admin/tickets?status=pending (after reject)", False, f"Status: {resp.status_code}")
except Exception as e:
    log_test("GET /admin/tickets?status=pending (after reject)", False, str(e))

# Step 6: CONFIRM second purchase (confirmed: true)
try:
    resp = requests.post(
        f"{BASE_URL}/admin/tickets/confirm",
        json={"purchase_id": purchase_ids[1], "confirmed": True},
        headers=get_headers(admin_token),
        timeout=10
    )
    log_test(
        "POST /admin/tickets/confirm (CONFIRM)",
        resp.status_code == 200,
        f"Status: {resp.status_code}"
    )
except Exception as e:
    log_test("POST /admin/tickets/confirm (CONFIRM)", False, str(e))

# Step 7: GET /admin/tickets?status=confirmed shows confirmed ticket
try:
    resp = requests.get(
        f"{BASE_URL}/admin/tickets?status=confirmed",
        headers=get_headers(admin_token),
        timeout=10
    )
    if resp.status_code == 200:
        confirmed_tickets = resp.json()
        confirmed_ids = [t["id"] for t in confirmed_tickets]
        confirmed_present = purchase_ids[1] in confirmed_ids
        log_test(
            "GET /admin/tickets?status=confirmed shows confirmed ticket",
            confirmed_present,
            f"Confirmed ID {purchase_ids[1]} {'found' if confirmed_present else 'NOT found'}"
        )
    else:
        log_test("GET /admin/tickets?status=confirmed", False, f"Status: {resp.status_code}")
except Exception as e:
    log_test("GET /admin/tickets?status=confirmed", False, str(e))

# Step 8: GET /admin/tickets?status=pending does NOT show confirmed ticket
try:
    resp = requests.get(
        f"{BASE_URL}/admin/tickets?status=pending",
        headers=get_headers(admin_token),
        timeout=10
    )
    if resp.status_code == 200:
        pending_tickets = resp.json()
        pending_ids = [t["id"] for t in pending_tickets]
        confirmed_not_in_pending = purchase_ids[1] not in pending_ids
        log_test(
            "Confirmed ticket NOT in pending list",
            confirmed_not_in_pending,
            f"Confirmed ID {purchase_ids[1]} {'NOT in pending (correct)' if confirmed_not_in_pending else 'STILL in pending (BUG!)'}"
        )
    else:
        log_test("GET /admin/tickets?status=pending (check confirmed not present)", False, f"Status: {resp.status_code}")
except Exception as e:
    log_test("GET /admin/tickets?status=pending (check confirmed not present)", False, str(e))

# ============================================================================
# NEW NOTIFY FEATURE
# ============================================================================
print("\n" + "="*80)
print("NEW NOTIFY FEATURE")
print("="*80)

# Test 1: GET /api/admin/notify/presets as admin
try:
    resp = requests.get(
        f"{BASE_URL}/admin/notify/presets",
        headers=get_headers(admin_token),
        timeout=10
    )
    if resp.status_code == 200:
        data = resp.json()
        has_presets = "presets" in data and isinstance(data["presets"], list)
        if has_presets and len(data["presets"]) > 0:
            preset = data["presets"][0]
            required_fields = ["id", "label", "emoji", "needs_event", "title", "body"]
            all_fields_present = all(field in preset for field in required_fields)
            log_test(
                "GET /admin/notify/presets returns correct structure",
                all_fields_present,
                f"Found {len(data['presets'])} presets with all required fields"
            )
        else:
            log_test("GET /admin/notify/presets", False, "No presets or wrong structure")
    else:
        log_test("GET /admin/notify/presets", False, f"Status: {resp.status_code}")
except Exception as e:
    log_test("GET /admin/notify/presets", False, str(e))

# Test 2: GET /admin/notify/presets as non-admin -> 403
try:
    resp = requests.get(
        f"{BASE_URL}/admin/notify/presets",
        headers=get_headers(user_token),
        timeout=10
    )
    log_test(
        "GET /admin/notify/presets as non-admin returns 403",
        resp.status_code == 403,
        f"Status: {resp.status_code}"
    )
except Exception as e:
    log_test("GET /admin/notify/presets as non-admin", False, str(e))

# Test 3: GET /api/admin/events-min as admin
try:
    resp = requests.get(
        f"{BASE_URL}/admin/events-min",
        headers=get_headers(admin_token),
        timeout=10
    )
    if resp.status_code == 200:
        data = resp.json()
        has_events = "events" in data and isinstance(data["events"], list)
        if has_events and len(data["events"]) > 0:
            event = data["events"][0]
            required_fields = ["id", "name", "venue", "date"]
            all_fields_present = all(field in event for field in required_fields)
            log_test(
                "GET /admin/events-min returns correct structure",
                all_fields_present,
                f"Found {len(data['events'])} events with required fields"
            )
            # Save an event ID for later tests
            notify_test_event_id = event["id"]
        else:
            log_test("GET /admin/events-min", False, "No events or wrong structure")
            notify_test_event_id = test_event_id  # fallback
    else:
        log_test("GET /admin/events-min", False, f"Status: {resp.status_code}")
        notify_test_event_id = test_event_id  # fallback
except Exception as e:
    log_test("GET /admin/events-min", False, str(e))
    notify_test_event_id = test_event_id  # fallback

# Test 4: GET /admin/events-min with ?q= filter
try:
    resp = requests.get(
        f"{BASE_URL}/admin/events-min?q=fiesta",
        headers=get_headers(admin_token),
        timeout=10
    )
    if resp.status_code == 200:
        data = resp.json()
        has_events = "events" in data and isinstance(data["events"], list)
        log_test(
            "GET /admin/events-min?q=fiesta filters correctly",
            has_events,
            f"Found {len(data['events']) if has_events else 0} events matching 'fiesta'"
        )
    else:
        log_test("GET /admin/events-min?q=fiesta", False, f"Status: {resp.status_code}")
except Exception as e:
    log_test("GET /admin/events-min?q=fiesta", False, str(e))

# Test 5: GET /admin/events-min as non-admin -> 403
try:
    resp = requests.get(
        f"{BASE_URL}/admin/events-min",
        headers=get_headers(user_token),
        timeout=10
    )
    log_test(
        "GET /admin/events-min as non-admin returns 403",
        resp.status_code == 403,
        f"Status: {resp.status_code}"
    )
except Exception as e:
    log_test("GET /admin/events-min as non-admin", False, str(e))

# Test 6: POST /admin/notify/send with preset_id + event_id + audience="event"
try:
    resp = requests.post(
        f"{BASE_URL}/admin/notify/send",
        json={
            "preset_id": "low_stock",
            "event_id": notify_test_event_id,
            "audience": "event"
        },
        headers=get_headers(admin_token),
        timeout=10
    )
    if resp.status_code == 200:
        data = resp.json()
        correct_structure = (
            data.get("ok") == True and
            data.get("audience") == "event" and
            isinstance(data.get("notified"), int)
        )
        log_test(
            "POST /admin/notify/send (preset + event + audience=event)",
            correct_structure,
            f"Response: {json.dumps(data)}"
        )
    else:
        log_test("POST /admin/notify/send (preset + event)", False, f"Status: {resp.status_code}, Body: {resp.text}")
except Exception as e:
    log_test("POST /admin/notify/send (preset + event)", False, str(e))

# Test 7: POST /admin/notify/send with preset_id + audience="all"
try:
    resp = requests.post(
        f"{BASE_URL}/admin/notify/send",
        json={
            "preset_id": "generic_new",
            "audience": "all"
        },
        headers=get_headers(admin_token),
        timeout=10
    )
    if resp.status_code == 200:
        data = resp.json()
        correct_structure = (
            data.get("ok") == True and
            data.get("audience") == "all" and
            isinstance(data.get("notified"), int) and
            data.get("queued") == True
        )
        log_test(
            "POST /admin/notify/send (preset + audience=all)",
            correct_structure,
            f"Response: {json.dumps(data)}"
        )
    else:
        log_test("POST /admin/notify/send (preset + all)", False, f"Status: {resp.status_code}, Body: {resp.text}")
except Exception as e:
    log_test("POST /admin/notify/send (preset + all)", False, str(e))

# Test 8: POST /admin/notify/send with body containing {name} but NO event_id -> 400
try:
    resp = requests.post(
        f"{BASE_URL}/admin/notify/send",
        json={
            "body": "{name} test notification",
            "audience": "event"
        },
        headers=get_headers(admin_token),
        timeout=10
    )
    log_test(
        "POST /admin/notify/send (body with {name} but no event_id) returns 400",
        resp.status_code == 400,
        f"Status: {resp.status_code}"
    )
except Exception as e:
    log_test("POST /admin/notify/send (body with {name} no event)", False, str(e))

# Test 9: POST /admin/notify/send with audience="event" but empty body and no preset_id -> 400
try:
    resp = requests.post(
        f"{BASE_URL}/admin/notify/send",
        json={
            "audience": "event"
        },
        headers=get_headers(admin_token),
        timeout=10
    )
    log_test(
        "POST /admin/notify/send (no body, no preset) returns 400",
        resp.status_code == 400,
        f"Status: {resp.status_code}"
    )
except Exception as e:
    log_test("POST /admin/notify/send (no body, no preset)", False, str(e))

# Test 10: POST /admin/notify/send as non-admin -> 403
try:
    resp = requests.post(
        f"{BASE_URL}/admin/notify/send",
        json={
            "preset_id": "generic_new",
            "audience": "all"
        },
        headers=get_headers(user_token),
        timeout=10
    )
    log_test(
        "POST /admin/notify/send as non-admin returns 403",
        resp.status_code == 403,
        f"Status: {resp.status_code}"
    )
except Exception as e:
    log_test("POST /admin/notify/send as non-admin", False, str(e))

# ============================================================================
# PERFORMANCE/REGRESSION TESTS
# ============================================================================
print("\n" + "="*80)
print("PERFORMANCE/REGRESSION TESTS")
print("="*80)

# Test 1: GET /api/admin/funnel?scope=all
try:
    start_time = time.time()
    resp = requests.get(
        f"{BASE_URL}/admin/funnel?scope=all",
        headers=get_headers(admin_token),
        timeout=15
    )
    elapsed_ms = (time.time() - start_time) * 1000
    
    if resp.status_code == 200:
        data = resp.json()
        has_rows = "rows" in data and isinstance(data["rows"], list)
        has_totals = "totals" in data and isinstance(data["totals"], dict)
        if has_totals:
            required_totals = ["views", "interested", "going", "clicks", "tickets", "commission"]
            totals_complete = all(field in data["totals"] for field in required_totals)
        else:
            totals_complete = False
        
        correct_structure = has_rows and has_totals and totals_complete
        log_test(
            "GET /admin/funnel?scope=all returns correct structure",
            correct_structure,
            f"Response time: {elapsed_ms:.1f}ms, Rows: {len(data.get('rows', []))}"
        )
    else:
        log_test("GET /admin/funnel?scope=all", False, f"Status: {resp.status_code}")
except Exception as e:
    log_test("GET /admin/funnel?scope=all", False, str(e))

# Test 2: GET /api/admin/venue-report
try:
    start_time = time.time()
    resp = requests.get(
        f"{BASE_URL}/admin/venue-report",
        headers=get_headers(admin_token),
        timeout=15
    )
    elapsed_ms = (time.time() - start_time) * 1000
    
    if resp.status_code == 200:
        data = resp.json()
        has_venues = "venues" in data and isinstance(data["venues"], list)
        log_test(
            "GET /admin/venue-report returns correct structure",
            has_venues,
            f"Response time: {elapsed_ms:.1f}ms, Venues: {len(data.get('venues', []))}"
        )
    else:
        log_test("GET /admin/venue-report", False, f"Status: {resp.status_code}")
except Exception as e:
    log_test("GET /admin/venue-report", False, str(e))

# Test 3: GET /api/admin/events/{id}/stats
try:
    start_time = time.time()
    resp = requests.get(
        f"{BASE_URL}/admin/events/{notify_test_event_id}/stats",
        headers=get_headers(admin_token),
        timeout=15
    )
    elapsed_ms = (time.time() - start_time) * 1000
    
    if resp.status_code == 200:
        data = resp.json()
        has_event = "event" in data
        has_funnel = "funnel" in data and isinstance(data["funnel"], dict)
        has_people = "people" in data and isinstance(data["people"], dict)
        has_history = "history" in data
        
        correct_structure = has_event and has_funnel and has_people and has_history
        log_test(
            "GET /admin/events/{id}/stats returns correct structure",
            correct_structure,
            f"Response time: {elapsed_ms:.1f}ms"
        )
    else:
        log_test("GET /admin/events/{id}/stats", False, f"Status: {resp.status_code}")
except Exception as e:
    log_test("GET /admin/events/{id}/stats", False, str(e))

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "="*80)
print("TEST SUMMARY")
print("="*80)
print(f"Total tests: {results['passed'] + results['failed']}")
print(f"✅ Passed: {results['passed']}")
print(f"❌ Failed: {results['failed']}")
print(f"Pass rate: {results['passed'] / (results['passed'] + results['failed']) * 100:.1f}%")

if results['failed'] > 0:
    print("\n❌ FAILED TESTS:")
    for test in results['tests']:
        if not test['passed']:
            print(f"  - {test['name']}")
            if test['details']:
                print(f"    {test['details']}")

print("\n" + "="*80)
