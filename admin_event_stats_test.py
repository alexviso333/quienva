#!/usr/bin/env python3
"""
Backend API Testing for ¿Quién va? - Admin Event Stats & History
Test iteration: 2026-08-02h (Gran Hermano)
"""

import requests
import json
from datetime import datetime

# Base URL from frontend/.env
BASE_URL = "https://fullstack-chat-app-1.preview.emergentagent.com/api"

# Admin credentials from /app/memory/test_credentials.md
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
    if details and not passed:
        print(f"  Details: {details}")

# ============================================================================
# SETUP: Login as admin and create test user
# ============================================================================

print("\n" + "="*80)
print("SETUP: Login as admin and create test user")
print("="*80)

# Login as admin
resp = requests.post(f"{BASE_URL}/auth/login", json={
    "email": ADMIN_EMAIL,
    "password": ADMIN_PASSWORD
})
log_test("Admin login", resp.status_code == 200, f"Status: {resp.status_code}")
admin_token = resp.json().get("token") if resp.status_code == 200 else None
admin_headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}
admin_user_id = resp.json().get("user", {}).get("user_id") if resp.status_code == 200 else None

if not admin_token:
    print("❌ CRITICAL: Failed to login as admin. Exiting.")
    exit(1)

# Create a normal test user
username = f"normaluser_{datetime.now().timestamp()}"
email = f"{username}@test.com"
resp = requests.post(f"{BASE_URL}/auth/register", json={
    "email": email,
    "password": "Test123!",
    "name": "Normal User",
    "username": username,
    "city": "Palma"
})
if resp.status_code == 200:
    data = resp.json()
    normal_token = data.get("token")
    normal_user_id = data.get("user", {}).get("user_id") if "user" in data else data.get("user_id")
    normal_headers = {"Authorization": f"Bearer {normal_token}"}
    log_test("Create normal user", True, f"User ID: {normal_user_id}")
else:
    log_test("Create normal user", False, f"Status: {resp.status_code}")
    print("❌ CRITICAL: Failed to create normal user. Exiting.")
    exit(1)

# ============================================================================
# TEST 1: GET /api/admin/events/{event_id}/stats
# ============================================================================

print("\n" + "="*80)
print("TEST 1: GET /api/admin/events/{event_id}/stats")
print("="*80)

# First, get an event ID
resp = requests.get(f"{BASE_URL}/events", headers=admin_headers)
log_test("GET /events to get event ID", resp.status_code == 200, f"Status: {resp.status_code}")

event_id = None
if resp.status_code == 200:
    events = resp.json()
    if events and len(events) > 0:
        event_id = events[0]["id"]
        log_test("Found event ID", True, f"Event ID: {event_id}")
    else:
        log_test("Found event ID", False, "No events found")

if not event_id:
    print("❌ CRITICAL: No events found. Cannot test admin/events/{event_id}/stats. Exiting.")
    exit(1)

# Test 1.1: GET /api/admin/events/{event_id}/stats as admin -> 200
resp = requests.get(f"{BASE_URL}/admin/events/{event_id}/stats", headers=admin_headers)
log_test("GET /admin/events/{event_id}/stats as admin returns 200", 
         resp.status_code == 200, 
         f"Status: {resp.status_code}")

if resp.status_code == 200:
    data = resp.json()
    
    # Test 1.2: Verify response has top-level keys: event, funnel, people, history
    required_keys = ["event", "funnel", "people", "history"]
    has_all_keys = all(key in data for key in required_keys)
    log_test("Response has keys: event, funnel, people, history", 
             has_all_keys,
             f"Keys present: {list(data.keys())}")
    
    # Test 1.3: Verify funnel has required keys
    if "funnel" in data:
        funnel_keys = ["views", "interested", "going", "attended", "clicks", "tickets", 
                      "followers", "album_items", "captures", "conversion_pct", "est_commission"]
        has_funnel_keys = all(key in data["funnel"] for key in funnel_keys)
        log_test("Funnel has all required keys", 
                 has_funnel_keys,
                 f"Funnel keys: {list(data['funnel'].keys())}")
    else:
        log_test("Funnel has all required keys", False, "Funnel key missing from response")
    
    # Test 1.4: Verify people has required arrays
    if "people" in data:
        people_keys = ["going", "interested", "attended"]
        has_people_keys = all(key in data["people"] for key in people_keys)
        log_test("People has arrays: going, interested, attended", 
                 has_people_keys,
                 f"People keys: {list(data['people'].keys())}")
        
        # Verify they are arrays
        if has_people_keys:
            all_arrays = all(isinstance(data["people"][key], list) for key in people_keys)
            log_test("People arrays are lists", all_arrays)
    else:
        log_test("People has arrays: going, interested, attended", False, "People key missing from response")

# Test 1.5: GET /api/admin/events/{event_id}/stats as non-admin -> 403
resp = requests.get(f"{BASE_URL}/admin/events/{event_id}/stats", headers=normal_headers)
log_test("GET /admin/events/{event_id}/stats as non-admin returns 403", 
         resp.status_code == 403,
         f"Status: {resp.status_code}")

# Test 1.6: GET /api/admin/events/{event_id}/stats unauthenticated -> 401
resp = requests.get(f"{BASE_URL}/admin/events/{event_id}/stats")
log_test("GET /admin/events/{event_id}/stats unauthenticated returns 401", 
         resp.status_code == 401,
         f"Status: {resp.status_code}")

# Test 1.7: GET /api/admin/events/{event_id}/stats with non-existent event -> 404
fake_event_id = "nonexistent-event-id-12345"
resp = requests.get(f"{BASE_URL}/admin/events/{fake_event_id}/stats", headers=admin_headers)
log_test("GET /admin/events/{event_id}/stats with non-existent event returns 404", 
         resp.status_code == 404,
         f"Status: {resp.status_code}")

# ============================================================================
# TEST 2: GET /api/admin/events/{event_id}/history
# ============================================================================

print("\n" + "="*80)
print("TEST 2: GET /api/admin/events/{event_id}/history")
print("="*80)

# Test 2.1: GET /api/admin/events/{event_id}/history as admin -> 200
resp = requests.get(f"{BASE_URL}/admin/events/{event_id}/history", headers=admin_headers)
log_test("GET /admin/events/{event_id}/history as admin returns 200", 
         resp.status_code == 200,
         f"Status: {resp.status_code}")

if resp.status_code == 200:
    data = resp.json()
    
    # Test 2.2: Verify response has keys: event_id, name, entries, total
    required_keys = ["event_id", "name", "entries", "total"]
    has_all_keys = all(key in data for key in required_keys)
    log_test("Response has keys: event_id, name, entries, total", 
             has_all_keys,
             f"Keys present: {list(data.keys())}")
    
    # Test 2.3: Verify entries is a list
    if "entries" in data:
        is_list = isinstance(data["entries"], list)
        log_test("entries is a list", is_list, f"Type: {type(data['entries'])}")
    else:
        log_test("entries is a list", False, "entries key missing")

# Test 2.4: GET /api/admin/events/{event_id}/history as non-admin -> 403
resp = requests.get(f"{BASE_URL}/admin/events/{event_id}/history", headers=normal_headers)
log_test("GET /admin/events/{event_id}/history as non-admin returns 403", 
         resp.status_code == 403,
         f"Status: {resp.status_code}")

# Test 2.5: GET /api/admin/events/{event_id}/history unauthenticated -> 401
resp = requests.get(f"{BASE_URL}/admin/events/{event_id}/history")
log_test("GET /admin/events/{event_id}/history unauthenticated returns 401", 
         resp.status_code == 401,
         f"Status: {resp.status_code}")

# ============================================================================
# TEST 3: Manual pricing change records history
# ============================================================================

print("\n" + "="*80)
print("TEST 3: Manual pricing change records history")
print("="*80)

# Test 3.1: Get current history total
resp = requests.get(f"{BASE_URL}/admin/events/{event_id}/history", headers=admin_headers)
initial_total = 0
if resp.status_code == 200:
    initial_total = resp.json().get("total", 0)
    log_test("Get initial history total", True, f"Initial total: {initial_total}")
else:
    log_test("Get initial history total", False, f"Status: {resp.status_code}")

# Test 3.2: Change pricing via PUT /api/admin/events/{event_id}/pricing
# First get current event to see current pricing
resp = requests.get(f"{BASE_URL}/admin/events/{event_id}/stats", headers=admin_headers)
current_event = None
if resp.status_code == 200:
    current_event = resp.json().get("event", {})
    log_test("Get current event pricing", True)
else:
    log_test("Get current event pricing", False, f"Status: {resp.status_code}")

# Change pricing - modify sale_state and/or price
new_pricing = {
    "price_tiers": [
        {"name": "General", "price": 25.0, "sold_out": False},
        {"name": "VIP", "price": 40.0, "sold_out": False}
    ],
    "sale_state": "pocas_entradas",  # Change state
    "silent": False
}

resp = requests.put(f"{BASE_URL}/admin/events/{event_id}/pricing", 
                    headers=admin_headers,
                    json=new_pricing)
log_test("PUT /admin/events/{event_id}/pricing", 
         resp.status_code == 200,
         f"Status: {resp.status_code}")

# Test 3.3: Get history again and verify total increased
resp = requests.get(f"{BASE_URL}/admin/events/{event_id}/history", headers=admin_headers)
if resp.status_code == 200:
    data = resp.json()
    new_total = data.get("total", 0)
    entries = data.get("entries", [])
    
    # Check if total increased
    total_increased = new_total > initial_total
    log_test("History total increased after pricing change", 
             total_increased,
             f"Initial: {initial_total}, New: {new_total}")
    
    # Test 3.4: Verify new entry has source="admin"
    if entries and len(entries) > 0:
        latest_entry = entries[0]  # Sorted by created_at desc
        has_admin_source = latest_entry.get("source") == "admin"
        log_test("Latest history entry has source='admin'", 
                 has_admin_source,
                 f"Source: {latest_entry.get('source')}")
        
        # Test 3.5: Verify kind is one of: state, price_up, price_down, pricing_edited
        valid_kinds = ["state", "price_up", "price_down", "pricing_edited"]
        kind = latest_entry.get("kind")
        has_valid_kind = kind in valid_kinds
        log_test("Latest history entry has valid kind", 
                 has_valid_kind,
                 f"Kind: {kind}, Valid kinds: {valid_kinds}")
        
        # Print the new entry for verification
        print(f"\n📝 New history entry:")
        print(f"   Source: {latest_entry.get('source')}")
        print(f"   Kind: {latest_entry.get('kind')}")
        print(f"   Created at: {latest_entry.get('created_at')}")
        print(f"   Details: {latest_entry.get('details', {})}")
    else:
        log_test("Latest history entry has source='admin'", False, "No entries found")
        log_test("Latest history entry has valid kind", False, "No entries found")
else:
    log_test("History total increased after pricing change", False, f"Status: {resp.status_code}")

# ============================================================================
# TEST 4: Regression tests
# ============================================================================

print("\n" + "="*80)
print("TEST 4: Regression tests")
print("="*80)

# Test 4.1: GET /api/admin/stats
resp = requests.get(f"{BASE_URL}/admin/stats", headers=admin_headers)
log_test("GET /admin/stats returns 200", 
         resp.status_code == 200,
         f"Status: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    log_test("GET /admin/stats has basic structure", 
             isinstance(data, dict),
             f"Response type: {type(data)}")

# Test 4.2: GET /api/admin/dashboard
resp = requests.get(f"{BASE_URL}/admin/dashboard", headers=admin_headers)
log_test("GET /admin/dashboard returns 200", 
         resp.status_code == 200,
         f"Status: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    log_test("GET /admin/dashboard has basic structure", 
             isinstance(data, dict),
             f"Response type: {type(data)}")

# Test 4.3: GET /api/admin/funnel?scope=all
resp = requests.get(f"{BASE_URL}/admin/funnel?scope=all", headers=admin_headers)
log_test("GET /admin/funnel?scope=all returns 200", 
         resp.status_code == 200,
         f"Status: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    has_rows = "rows" in data
    has_totals = "totals" in data
    log_test("GET /admin/funnel has rows[] and totals{}", 
             has_rows and has_totals,
             f"Keys: {list(data.keys())}")

# Test 4.4: GET /api/admin/scrape-changelog
resp = requests.get(f"{BASE_URL}/admin/scrape-changelog", headers=admin_headers)
log_test("GET /admin/scrape-changelog returns 200", 
         resp.status_code == 200,
         f"Status: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    log_test("GET /admin/scrape-changelog has basic structure", 
             isinstance(data, dict),
             f"Response type: {type(data)}")

# ============================================================================
# SUMMARY
# ============================================================================

print("\n" + "="*80)
print("TEST SUMMARY")
print("="*80)
print(f"Total tests: {results['passed'] + results['failed']}")
print(f"✅ Passed: {results['passed']}")
print(f"❌ Failed: {results['failed']}")
print(f"Pass rate: {(results['passed'] / (results['passed'] + results['failed']) * 100):.1f}%")

if results['failed'] > 0:
    print("\n❌ FAILED TESTS:")
    for test in results['tests']:
        if not test['passed']:
            print(f"  - {test['name']}")
            if test['details']:
                print(f"    {test['details']}")

print("\n" + "="*80)
