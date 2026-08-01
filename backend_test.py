#!/usr/bin/env python3
"""
Backend test for venue directory endpoints and danzu scraper verification.
Tests all venue CRUD operations, filtering, and scraper integration.
"""
import requests
import json
import sys
from datetime import datetime

# Base URL from frontend/.env
BASE_URL = "https://8c7ddfbe-7582-4efe-beca-08a944bba005.preview.emergentagent.com/api"

# Test credentials
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

# Color codes for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def log_test(name):
    print(f"\n{BLUE}[TEST]{RESET} {name}")

def log_pass(msg):
    print(f"  {GREEN}✓{RESET} {msg}")

def log_fail(msg):
    print(f"  {RED}✗{RESET} {msg}")

def log_info(msg):
    print(f"  {YELLOW}ℹ{RESET} {msg}")

# Track test results
passed = 0
failed = 0
test_results = []

def assert_test(condition, message, details=""):
    global passed, failed
    if condition:
        log_pass(message)
        passed += 1
        test_results.append(("PASS", message))
        return True
    else:
        log_fail(f"{message} {details}")
        failed += 1
        test_results.append(("FAIL", f"{message} {details}"))
        return False

# ============================================================================
# 1. AUTHENTICATION SETUP
# ============================================================================

log_test("Admin Login")
resp = requests.post(f"{BASE_URL}/auth/login", json={
    "email": ADMIN_EMAIL,
    "password": ADMIN_PASSWORD
})
assert_test(resp.status_code == 200, "Admin login returns 200", f"Got {resp.status_code}")
admin_token = resp.json().get("token")
assert_test(admin_token is not None, "Admin token received")
admin_headers = {"Authorization": f"Bearer {admin_token}"}

log_test("Register Normal User")
normal_email = f"testuser_{int(datetime.now().timestamp())}@test.com"
normal_username = f"testuser{int(datetime.now().timestamp())}"
normal_password = "testpass123"
resp = requests.post(f"{BASE_URL}/auth/register", json={
    "email": normal_email,
    "password": normal_password,
    "username": normal_username,
    "name": "Test User",
    "city": "Palma de Mallorca"
})
assert_test(resp.status_code == 200, "Normal user registration returns 200", f"Got {resp.status_code}")
normal_token = resp.json().get("token")
assert_test(normal_token is not None, "Normal user token received")
normal_headers = {"Authorization": f"Bearer {normal_token}"}

# ============================================================================
# 2. GET /api/venues (authenticated normal user)
# ============================================================================

log_test("GET /api/venues as authenticated normal user")
resp = requests.get(f"{BASE_URL}/venues", headers=normal_headers)
assert_test(resp.status_code == 200, "Returns 200", f"Got {resp.status_code}")

if resp.status_code == 200:
    venues = resp.json()
    assert_test(isinstance(venues, list), "Response is JSON array")
    assert_test(len(venues) >= 25 and len(venues) <= 30, 
                f"Returns ~27 venues", f"Got {len(venues)} venues")
    
    if len(venues) > 0:
        v = venues[0]
        required_fields = ["id", "name", "zone", "city", "type", "scraper_slug", 
                          "free_entry", "open_days", "upcoming_events"]
        for field in required_fields:
            assert_test(field in v, f"Venue has '{field}' field")
        
        assert_test(isinstance(v.get("free_entry"), bool), "free_entry is boolean")
        assert_test(isinstance(v.get("open_days"), list), "open_days is array")
        assert_test(isinstance(v.get("upcoming_events"), int), "upcoming_events is integer")
        
        # Verify open_days contains integers 0-6
        if isinstance(v.get("open_days"), list) and len(v.get("open_days", [])) > 0:
            all_valid = all(isinstance(d, int) and 0 <= d <= 6 for d in v["open_days"])
            assert_test(all_valid, "open_days contains integers 0-6")

log_test("GET /api/venues unauthenticated")
resp = requests.get(f"{BASE_URL}/venues")
assert_test(resp.status_code == 401, "Returns 401 without token", f"Got {resp.status_code}")

# ============================================================================
# 3. GET /api/venues with filters
# ============================================================================

log_test("GET /api/venues?zone=Magaluf")
resp = requests.get(f"{BASE_URL}/venues?zone=Magaluf", headers=normal_headers)
assert_test(resp.status_code == 200, "Returns 200", f"Got {resp.status_code}")

if resp.status_code == 200:
    venues = resp.json()
    assert_test(isinstance(venues, list), "Response is JSON array")
    if len(venues) > 0:
        all_magaluf = all(v.get("zone") == "Magaluf" for v in venues)
        assert_test(all_magaluf, "All venues have zone='Magaluf'", 
                   f"Found zones: {set(v.get('zone') for v in venues)}")
        log_info(f"Found {len(venues)} venues in Magaluf")

log_test("GET /api/venues?type=pub")
resp = requests.get(f"{BASE_URL}/venues?type=pub", headers=normal_headers)
assert_test(resp.status_code == 200, "Returns 200", f"Got {resp.status_code}")

if resp.status_code == 200:
    venues = resp.json()
    assert_test(isinstance(venues, list), "Response is JSON array")
    if len(venues) > 0:
        all_pub = all(v.get("type") == "pub" for v in venues)
        assert_test(all_pub, "All venues have type='pub'", 
                   f"Found types: {set(v.get('type') for v in venues)}")
        log_info(f"Found {len(venues)} pubs")

# ============================================================================
# 4. Verify linkage: Amok venue with upcoming_events > 0
# ============================================================================

log_test("Verify Amok venue linkage")
resp = requests.get(f"{BASE_URL}/venues", headers=normal_headers)
if resp.status_code == 200:
    venues = resp.json()
    amok = next((v for v in venues if v.get("name") == "Amok"), None)
    
    if amok:
        log_info(f"Found Amok venue: id={amok.get('id')}, scraper_slug={amok.get('scraper_slug')}")
        assert_test(amok.get("scraper_slug") == "amok", "Amok has scraper_slug='amok'")
        assert_test(amok.get("upcoming_events") > 0, 
                   f"Amok has upcoming_events > 0", 
                   f"Got {amok.get('upcoming_events')} events")
        amok_id = amok.get("id")
    else:
        log_fail("Amok venue not found in list")
        amok_id = None
else:
    log_fail("Could not fetch venues to find Amok")
    amok_id = None

# ============================================================================
# 5. GET /api/venues/{id} for Amok venue
# ============================================================================

if amok_id:
    log_test(f"GET /api/venues/{amok_id} (Amok venue)")
    resp = requests.get(f"{BASE_URL}/venues/{amok_id}", headers=normal_headers)
    assert_test(resp.status_code == 200, "Returns 200", f"Got {resp.status_code}")
    
    if resp.status_code == 200:
        venue = resp.json()
        assert_test("events" in venue, "Response has 'events' array")
        
        if "events" in venue:
            events = venue["events"]
            assert_test(isinstance(events, list), "events is an array")
            assert_test(len(events) > 0, f"Amok has events", f"Got {len(events)} events")
            
            if len(events) > 0:
                e = events[0]
                required_event_fields = ["id", "name", "date", "current_price", "sale_state"]
                for field in required_event_fields:
                    assert_test(field in e, f"Event has '{field}' field")
                
                # current_price should be number or null
                cp = e.get("current_price")
                assert_test(cp is None or isinstance(cp, (int, float)), 
                           "current_price is number or null", f"Got {type(cp)}")
                
                # sale_state should be valid enum
                valid_states = ["a_la_venta", "pocas_entradas", "agotado", "no_a_la_venta"]
                assert_test(e.get("sale_state") in valid_states, 
                           f"sale_state is valid", f"Got '{e.get('sale_state')}'")

# Test venue with empty scraper_slug (Shamrock)
log_test("GET /api/venues/{id} for venue without scraper (Shamrock)")
resp = requests.get(f"{BASE_URL}/venues", headers=normal_headers)
if resp.status_code == 200:
    venues = resp.json()
    shamrock = next((v for v in venues if v.get("name") == "Shamrock"), None)
    
    if shamrock:
        shamrock_id = shamrock.get("id")
        log_info(f"Found Shamrock venue: id={shamrock_id}, scraper_slug='{shamrock.get('scraper_slug')}'")
        
        resp = requests.get(f"{BASE_URL}/venues/{shamrock_id}", headers=normal_headers)
        assert_test(resp.status_code == 200, "Returns 200", f"Got {resp.status_code}")
        
        if resp.status_code == 200:
            venue = resp.json()
            assert_test("events" in venue, "Response has 'events' field")
            assert_test(venue.get("events") == [], 
                       "Shamrock has empty events array", 
                       f"Got {len(venue.get('events', []))} events")
    else:
        log_info("Shamrock venue not found (may not be seeded)")

# ============================================================================
# 6. GET /api/venues/meta/zones
# ============================================================================

log_test("GET /api/venues/meta/zones (authenticated)")
resp = requests.get(f"{BASE_URL}/venues/meta/zones", headers=normal_headers)
assert_test(resp.status_code == 200, "Returns 200", f"Got {resp.status_code}")

if resp.status_code == 200:
    data = resp.json()
    assert_test("zones" in data, "Response has 'zones' field")
    
    if "zones" in data:
        zones = data["zones"]
        assert_test(isinstance(zones, list), "zones is an array")
        assert_test(len(zones) > 0, "zones is non-empty", f"Got {len(zones)} zones")
        
        # Verify sorted
        if len(zones) > 1:
            is_sorted = zones == sorted(zones)
            assert_test(is_sorted, "zones are sorted alphabetically")
        
        log_info(f"Zones: {', '.join(zones)}")

# ============================================================================
# 7. Admin CRUD on /api/admin/venues
# ============================================================================

created_venue_id = None

log_test("POST /api/admin/venues (create venue as admin)")
new_venue = {
    "name": "Test Local QA",
    "zone": "Palma",
    "city": "Palma de Mallorca",
    "type": "pub",
    "free_entry": True,
    "open_days": [4, 5]
}
resp = requests.post(f"{BASE_URL}/admin/venues", json=new_venue, headers=admin_headers)
assert_test(resp.status_code == 200, "Returns 200", f"Got {resp.status_code}")

if resp.status_code == 200:
    venue = resp.json()
    assert_test("id" in venue, "Response has 'id' field")
    created_venue_id = venue.get("id")
    assert_test(venue.get("name") == "Test Local QA", "Venue name matches")
    assert_test(venue.get("zone") == "Palma", "Venue zone matches")
    assert_test(venue.get("type") == "pub", "Venue type matches")
    assert_test(venue.get("free_entry") == True, "Venue free_entry matches")
    assert_test(venue.get("open_days") == [4, 5], "Venue open_days matches")
    log_info(f"Created venue with id: {created_venue_id}")

log_test("POST /api/admin/venues as non-admin")
resp = requests.post(f"{BASE_URL}/admin/venues", json=new_venue, headers=normal_headers)
assert_test(resp.status_code == 403, "Returns 403", f"Got {resp.status_code}")

if created_venue_id:
    log_test(f"PUT /api/admin/venues/{created_venue_id} (update as admin)")
    update_data = {
        "name": "Test Local QA",
        "zone": "Palma",
        "city": "Palma de Mallorca",
        "type": "pub",
        "free_entry": True,
        "open_days": [0, 6]  # Changed from [4, 5]
    }
    resp = requests.put(f"{BASE_URL}/admin/venues/{created_venue_id}", 
                       json=update_data, headers=admin_headers)
    assert_test(resp.status_code == 200, "Returns 200", f"Got {resp.status_code}")
    
    if resp.status_code == 200:
        venue = resp.json()
        assert_test(venue.get("open_days") == [0, 6], 
                   "open_days updated correctly", 
                   f"Got {venue.get('open_days')}")
    
    # Verify update appears in list
    log_test("Verify updated venue appears in GET /api/venues")
    resp = requests.get(f"{BASE_URL}/venues", headers=normal_headers)
    if resp.status_code == 200:
        venues = resp.json()
        updated_venue = next((v for v in venues if v.get("id") == created_venue_id), None)
        if updated_venue:
            assert_test(updated_venue.get("open_days") == [0, 6], 
                       "Updated venue reflects changes in list")
        else:
            log_info("Updated venue not found in list (may need to be active)")

log_test("PUT /api/admin/venues/{non_existent_id}")
fake_id = "00000000-0000-0000-0000-000000000000"
resp = requests.put(f"{BASE_URL}/admin/venues/{fake_id}", 
                   json=update_data, headers=admin_headers)
assert_test(resp.status_code == 404, "Returns 404 for non-existent id", f"Got {resp.status_code}")

log_test("PUT /api/admin/venues as non-admin")
if created_venue_id:
    resp = requests.put(f"{BASE_URL}/admin/venues/{created_venue_id}", 
                       json=update_data, headers=normal_headers)
    assert_test(resp.status_code == 403, "Returns 403", f"Got {resp.status_code}")

if created_venue_id:
    log_test(f"DELETE /api/admin/venues/{created_venue_id} (as admin)")
    resp = requests.delete(f"{BASE_URL}/admin/venues/{created_venue_id}", headers=admin_headers)
    assert_test(resp.status_code == 200, "Returns 200", f"Got {resp.status_code}")
    
    if resp.status_code == 200:
        data = resp.json()
        assert_test(data.get("ok") == True, "Response has ok:true")
    
    # Try to delete again
    log_test(f"DELETE /api/admin/venues/{created_venue_id} again")
    resp = requests.delete(f"{BASE_URL}/admin/venues/{created_venue_id}", headers=admin_headers)
    assert_test(resp.status_code == 404, "Returns 404 on second delete", f"Got {resp.status_code}")

log_test("DELETE /api/admin/venues as non-admin")
if created_venue_id:
    # Create another venue to test non-admin delete
    resp = requests.post(f"{BASE_URL}/admin/venues", json={
        "name": "Test Venue 2",
        "zone": "Palma",
        "city": "Palma de Mallorca",
        "type": "pub",
        "free_entry": True,
        "open_days": [5]
    }, headers=admin_headers)
    
    if resp.status_code == 200:
        temp_id = resp.json().get("id")
        resp = requests.delete(f"{BASE_URL}/admin/venues/{temp_id}", headers=normal_headers)
        assert_test(resp.status_code == 403, "Returns 403", f"Got {resp.status_code}")
        
        # Clean up
        requests.delete(f"{BASE_URL}/admin/venues/{temp_id}", headers=admin_headers)

# ============================================================================
# 8. Confirm danzu scraper in GET /api/admin/scrapers
# ============================================================================

log_test("GET /api/admin/scrapers (confirm danzu scraper)")
resp = requests.get(f"{BASE_URL}/admin/scrapers", headers=admin_headers)
assert_test(resp.status_code == 200, "Returns 200", f"Got {resp.status_code}")

if resp.status_code == 200:
    scrapers = resp.json()
    assert_test(isinstance(scrapers, list), "Response is JSON array")
    
    danzu = next((s for s in scrapers if s.get("slug") == "danzu"), None)
    
    if danzu:
        log_info(f"Found danzu scraper: name='{danzu.get('name')}', adapter_type='{danzu.get('adapter_type')}'")
        assert_test(danzu.get("adapter_type") == "fourvenues_api", 
                   "danzu has adapter_type='fourvenues_api'", 
                   f"Got '{danzu.get('adapter_type')}'")
        assert_test("Danzû" in danzu.get("name", ""), 
                   "danzu name contains 'Danzû'", 
                   f"Got '{danzu.get('name')}'")
    else:
        log_fail("danzu scraper not found in scrapers list")
        log_info(f"Available slugs: {[s.get('slug') for s in scrapers]}")

# ============================================================================
# 9. Light regression: GET /api/events
# ============================================================================

log_test("Light regression: GET /api/events")
resp = requests.get(f"{BASE_URL}/events", headers=normal_headers)
assert_test(resp.status_code == 200, "Returns 200", f"Got {resp.status_code}")

if resp.status_code == 200:
    events = resp.json()
    assert_test(isinstance(events, list), "Response is JSON array")
    assert_test(len(events) > 0, "Returns at least some events", f"Got {len(events)} events")
    
    if len(events) > 0:
        # Find events with price_tiers
        events_with_prices = [e for e in events if e.get("price_tiers") and len(e.get("price_tiers", [])) > 0]
        
        if len(events_with_prices) > 0:
            log_info(f"Found {len(events_with_prices)} events with price_tiers")
            e = events_with_prices[0]
            
            assert_test("price_tiers" in e, "Event has price_tiers field")
            assert_test(isinstance(e.get("price_tiers"), list), "price_tiers is array")
            
            if len(e.get("price_tiers", [])) > 0:
                tier = e["price_tiers"][0]
                assert_test("name" in tier and "price" in tier, "Price tier has name and price")
            
            assert_test("sale_state" in e, "Event has sale_state field")
            valid_states = ["a_la_venta", "pocas_entradas", "agotado", "no_a_la_venta"]
            assert_test(e.get("sale_state") in valid_states, 
                       f"sale_state is valid enum", 
                       f"Got '{e.get('sale_state')}'")
        else:
            log_info("No events with price_tiers found (may be expected)")

# ============================================================================
# 10. Light regression: GET /api/health
# ============================================================================

log_test("Light regression: GET /api/health")
resp = requests.get(f"{BASE_URL}/health")
assert_test(resp.status_code == 200, "Returns 200", f"Got {resp.status_code}")

if resp.status_code == 200:
    data = resp.json()
    assert_test(data.get("ok") == True, "Response has ok:true", f"Got {data}")

# ============================================================================
# SUMMARY
# ============================================================================

print("\n" + "="*80)
print(f"{BLUE}TEST SUMMARY{RESET}")
print("="*80)
print(f"Total tests: {passed + failed}")
print(f"{GREEN}Passed: {passed}{RESET}")
print(f"{RED}Failed: {failed}{RESET}")
print(f"Pass rate: {(passed/(passed+failed)*100):.1f}%")

if failed > 0:
    print(f"\n{RED}FAILED TESTS:{RESET}")
    for status, msg in test_results:
        if status == "FAIL":
            print(f"  ✗ {msg}")

print("\n" + "="*80)

sys.exit(0 if failed == 0 else 1)
