#!/usr/bin/env python3
"""
Backend test for batch 3 features:
1. Notification preferences (GET/PUT /api/me/notif-prefs)
2. Venue enrichment (GET /api/venues, GET /api/admin/scrapers)
3. Regression tests (events, venues/{id}, scrapers/run-all, health)
"""
import requests
import json
import sys
from datetime import datetime

# Base URL from frontend/.env
BASE_URL = "https://explore-quienva.preview.emergentagent.com/api"

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

def print_summary():
    print(f"\n{'='*60}")
    print(f"{BLUE}TEST SUMMARY{RESET}")
    print(f"{'='*60}")
    print(f"Total: {passed + failed}")
    print(f"{GREEN}Passed: {passed}{RESET}")
    print(f"{RED}Failed: {failed}{RESET}")
    if failed > 0:
        print(f"\n{RED}FAILED TESTS:{RESET}")
        for status, msg in test_results:
            if status == "FAIL":
                print(f"  {RED}✗{RESET} {msg}")
    print(f"{'='*60}\n")

# Global variables for tokens
admin_token = None
user_token = None
user_id = None

def login_admin():
    """Login as admin and return token"""
    global admin_token
    log_test("Admin Login")
    r = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert_test(r.status_code == 200, f"Admin login returns 200", f"Got {r.status_code}: {r.text}")
    if r.status_code == 200:
        data = r.json()
        admin_token = data.get("token")
        assert_test(admin_token is not None, "Admin token received")
        log_info(f"Admin token: {admin_token[:20]}...")
    return admin_token

def register_fresh_user():
    """Register a fresh normal user for auth-scoped tests"""
    global user_token, user_id
    log_test("Register Fresh Normal User")
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    email = f"testuser_{timestamp}@test.com"
    username = f"testuser{timestamp}"
    password = "testpass123"
    
    r = requests.post(f"{BASE_URL}/auth/register", json={
        "email": email,
        "username": username,
        "password": password,
        "name": f"Test User {timestamp}",
        "city": "Palma de Mallorca"
    })
    assert_test(r.status_code == 200, f"User registration returns 200", f"Got {r.status_code}: {r.text}")
    if r.status_code == 200:
        data = r.json()
        user_token = data.get("token")
        user_id = data.get("user", {}).get("user_id")
        assert_test(user_token is not None, "User token received")
        assert_test(user_id is not None, "User ID received")
        log_info(f"User email: {email}")
        log_info(f"User ID: {user_id}")
        log_info(f"User token: {user_token[:20]}...")
    return user_token, user_id

def test_notification_preferences():
    """Test notification preferences endpoints"""
    log_test("1. Notification Preferences - GET /api/me/notif-prefs (authenticated)")
    
    # Test without token (should return 401)
    r = requests.get(f"{BASE_URL}/me/notif-prefs")
    assert_test(r.status_code == 401, "GET without token returns 401", f"Got {r.status_code}")
    
    # Test with user token (should return 200)
    headers = {"Authorization": f"Bearer {user_token}"}
    r = requests.get(f"{BASE_URL}/me/notif-prefs", headers=headers)
    assert_test(r.status_code == 200, "GET with token returns 200", f"Got {r.status_code}: {r.text}")
    
    if r.status_code == 200:
        data = r.json()
        assert_test("prefs" in data, "Response contains 'prefs' field")
        assert_test("keys" in data, "Response contains 'keys' field")
        
        prefs = data.get("prefs", {})
        keys = data.get("keys", [])
        
        # Check all 7 required keys
        expected_keys = ["new_event", "tickets_on_sale", "tickets_low_stock", 
                        "tickets_sold_out", "tickets_price_down", "tickets_price_up", "friend_going"]
        assert_test(len(keys) == 7, f"Keys array has 7 items", f"Got {len(keys)}: {keys}")
        assert_test(set(keys) == set(expected_keys), "Keys match expected list", 
                   f"Expected {expected_keys}, got {keys}")
        
        # Check all prefs are boolean and default to true
        for key in expected_keys:
            assert_test(key in prefs, f"Prefs contains '{key}'")
            assert_test(isinstance(prefs[key], bool), f"'{key}' is boolean", f"Got {type(prefs[key])}")
            assert_test(prefs[key] == True, f"'{key}' defaults to True", f"Got {prefs[key]}")
        
        log_info(f"Prefs: {json.dumps(prefs, indent=2)}")
    
    log_test("2. Notification Preferences - PUT /api/me/notif-prefs (update)")
    
    # Update tickets_sold_out to false
    r = requests.put(f"{BASE_URL}/me/notif-prefs", 
                     headers=headers,
                     json={"prefs": {"tickets_sold_out": False}})
    assert_test(r.status_code == 200, "PUT returns 200", f"Got {r.status_code}: {r.text}")
    
    if r.status_code == 200:
        data = r.json()
        prefs = data.get("prefs", {})
        assert_test(prefs.get("tickets_sold_out") == False, 
                   "tickets_sold_out is now False", f"Got {prefs.get('tickets_sold_out')}")
        
        # Check other 6 keys are still True
        other_keys = ["new_event", "tickets_on_sale", "tickets_low_stock", 
                     "tickets_price_down", "tickets_price_up", "friend_going"]
        for key in other_keys:
            assert_test(prefs.get(key) == True, f"'{key}' is still True", f"Got {prefs.get(key)}")
    
    # Verify with GET
    r = requests.get(f"{BASE_URL}/me/notif-prefs", headers=headers)
    if r.status_code == 200:
        data = r.json()
        prefs = data.get("prefs", {})
        assert_test(prefs.get("tickets_sold_out") == False, 
                   "GET confirms tickets_sold_out is False", f"Got {prefs.get('tickets_sold_out')}")
    
    log_test("3. Notification Preferences - PUT with unknown key (should be ignored)")
    
    # Update with bogus_key (should be ignored) and new_event=false
    r = requests.put(f"{BASE_URL}/me/notif-prefs", 
                     headers=headers,
                     json={"prefs": {"bogus_key": False, "new_event": False}})
    assert_test(r.status_code == 200, "PUT with unknown key returns 200", f"Got {r.status_code}: {r.text}")
    
    if r.status_code == 200:
        data = r.json()
        prefs = data.get("prefs", {})
        assert_test("bogus_key" not in prefs, "bogus_key NOT in stored prefs", 
                   f"Prefs keys: {list(prefs.keys())}")
        assert_test(prefs.get("new_event") == False, "new_event is now False", 
                   f"Got {prefs.get('new_event')}")
    
    # Restore new_event to true
    r = requests.put(f"{BASE_URL}/me/notif-prefs", 
                     headers=headers,
                     json={"prefs": {"new_event": True, "tickets_sold_out": True}})
    assert_test(r.status_code == 200, "Restore prefs returns 200", f"Got {r.status_code}")

def test_venue_enrichment():
    """Test venue enrichment endpoints"""
    log_test("4. Venue Enrichment - GET /api/venues (authenticated)")
    
    headers = {"Authorization": f"Bearer {user_token}"}
    r = requests.get(f"{BASE_URL}/venues", headers=headers)
    assert_test(r.status_code == 200, "GET /venues returns 200", f"Got {r.status_code}: {r.text}")
    
    if r.status_code == 200:
        venues = r.json()
        assert_test(isinstance(venues, list), "Response is a list", f"Got {type(venues)}")
        log_info(f"Found {len(venues)} venues")
        
        # Check EVERY venue has numeric lat and lng (not null)
        venues_with_coords = 0
        venues_without_coords = []
        for v in venues:
            if v.get("lat") is not None and v.get("lng") is not None:
                assert_test(isinstance(v["lat"], (int, float)), 
                           f"Venue '{v.get('name')}' has numeric lat", f"Got {type(v['lat'])}")
                assert_test(isinstance(v["lng"], (int, float)), 
                           f"Venue '{v.get('name')}' has numeric lng", f"Got {type(v['lng'])}")
                venues_with_coords += 1
            else:
                venues_without_coords.append(v.get("name"))
        
        assert_test(len(venues_without_coords) == 0, 
                   "ALL venues have lat/lng", 
                   f"Missing coords: {venues_without_coords}")
        
        # Check open_days is an array
        for v in venues:
            assert_test(isinstance(v.get("open_days", []), list), 
                       f"Venue '{v.get('name')}' has open_days as array", 
                       f"Got {type(v.get('open_days'))}")
        
        # Confirm NO venue has name == "Megasport"
        megasport_venues = [v for v in venues if v.get("name") == "Megasport"]
        assert_test(len(megasport_venues) == 0, 
                   "NO venue named 'Megasport'", 
                   f"Found {len(megasport_venues)} Megasport venues")
        
        # Check at least several venues have non-empty image_url
        venues_with_images = [v for v in venues if v.get("image_url", "").strip()]
        assert_test(len(venues_with_images) >= 3, 
                   f"At least 3 venues have image_url", 
                   f"Found {len(venues_with_images)} venues with images")
        
        log_info(f"Venues with coordinates: {venues_with_coords}/{len(venues)}")
        log_info(f"Venues with images: {len(venues_with_images)}/{len(venues)}")

def test_admin_scrapers():
    """Test admin scrapers endpoint"""
    log_test("5. Admin Scrapers - GET /api/admin/scrapers (admin only)")
    
    # Test with admin token
    headers = {"Authorization": f"Bearer {admin_token}"}
    r = requests.get(f"{BASE_URL}/admin/scrapers", headers=headers)
    assert_test(r.status_code == 200, "GET /admin/scrapers returns 200", f"Got {r.status_code}: {r.text}")
    
    if r.status_code == 200:
        scrapers = r.json()
        assert_test(isinstance(scrapers, list), "Response is a list", f"Got {type(scrapers)}")
        log_info(f"Found {len(scrapers)} scrapers")
        
        # Should have ~12 venues
        assert_test(len(scrapers) >= 10 and len(scrapers) <= 15, 
                   f"Has ~12 venues (10-15)", f"Got {len(scrapers)} venues")
        
        # Confirm NO venue has slug == "megasport"
        megasport_scrapers = [s for s in scrapers if s.get("slug") == "megasport"]
        assert_test(len(megasport_scrapers) == 0, 
                   "NO scraper with slug 'megasport'", 
                   f"Found {len(megasport_scrapers)} megasport scrapers")
        
        # Log all scraper names and slugs
        log_info("Scrapers:")
        for s in scrapers:
            log_info(f"  - {s.get('name')} (slug: {s.get('slug')}, adapter: {s.get('adapter_type')})")

def test_regression_events():
    """Test regression - events endpoint"""
    log_test("6. Regression - GET /api/events (authenticated)")
    
    headers = {"Authorization": f"Bearer {user_token}"}
    r = requests.get(f"{BASE_URL}/events", headers=headers)
    assert_test(r.status_code == 200, "GET /events returns 200", f"Got {r.status_code}: {r.text}")
    
    if r.status_code == 200:
        events = r.json()
        assert_test(isinstance(events, list), "Response is a list", f"Got {type(events)}")
        assert_test(len(events) > 0, "Events list is not empty", f"Got {len(events)} events")
        log_info(f"Found {len(events)} events")
        
        # Check some events have non-empty price_tiers
        events_with_prices = [e for e in events if e.get("price_tiers") and len(e["price_tiers"]) > 0]
        assert_test(len(events_with_prices) > 0, 
                   "Some events have price_tiers", 
                   f"Found {len(events_with_prices)} events with prices")
        
        # Check sale_state values
        valid_sale_states = ["a_la_venta", "pocas_entradas", "agotado", "no_a_la_venta"]
        events_with_sale_state = [e for e in events if e.get("sale_state") in valid_sale_states]
        assert_test(len(events_with_sale_state) > 0, 
                   "Some events have valid sale_state", 
                   f"Found {len(events_with_sale_state)} events with sale_state")
        
        # Log sample event with pricing
        if events_with_prices:
            sample = events_with_prices[0]
            log_info(f"Sample event with pricing:")
            log_info(f"  Name: {sample.get('name')}")
            log_info(f"  Sale state: {sample.get('sale_state')}")
            log_info(f"  Price tiers: {sample.get('price_tiers')}")
            log_info(f"  Current price: {sample.get('current_price')}")

def test_regression_venue_detail():
    """Test regression - venue detail endpoint"""
    log_test("7. Regression - GET /api/venues/{id} for Amok venue")
    
    headers = {"Authorization": f"Bearer {user_token}"}
    
    # First get all venues to find Amok
    r = requests.get(f"{BASE_URL}/venues", headers=headers)
    if r.status_code != 200:
        log_fail("Could not fetch venues list")
        return
    
    venues = r.json()
    amok_venue = None
    for v in venues:
        if "amok" in v.get("name", "").lower():
            amok_venue = v
            break
    
    if not amok_venue:
        log_info("Amok venue not found in venues list, skipping test")
        return
    
    venue_id = amok_venue.get("id")
    log_info(f"Found Amok venue: {amok_venue.get('name')} (id: {venue_id})")
    
    # Get venue detail
    r = requests.get(f"{BASE_URL}/venues/{venue_id}", headers=headers)
    assert_test(r.status_code == 200, f"GET /venues/{venue_id} returns 200", f"Got {r.status_code}: {r.text}")
    
    if r.status_code == 200:
        venue = r.json()
        assert_test("events" in venue, "Response contains 'events' field")
        
        events = venue.get("events", [])
        assert_test(len(events) > 0, "Events array is non-empty", f"Got {len(events)} events")
        log_info(f"Amok venue has {len(events)} upcoming events")
        
        # Check each event has current_price and sale_state
        for event in events:
            assert_test("current_price" in event, 
                       f"Event '{event.get('name')}' has current_price field")
            assert_test("sale_state" in event, 
                       f"Event '{event.get('name')}' has sale_state field")
        
        # Log sample event
        if events:
            sample = events[0]
            log_info(f"Sample Amok event:")
            log_info(f"  Name: {sample.get('name')}")
            log_info(f"  Date: {sample.get('date')}")
            log_info(f"  Sale state: {sample.get('sale_state')}")
            log_info(f"  Current price: {sample.get('current_price')}")

def test_regression_scrapers_run_all():
    """Test regression - scrapers run-all endpoint"""
    log_test("8. Regression - POST /api/admin/scrapers/run-all (admin only)")
    
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # First run
    log_info("Running first scraper run...")
    r = requests.post(f"{BASE_URL}/admin/scrapers/run-all", headers=headers)
    assert_test(r.status_code == 200, "First run returns 200", f"Got {r.status_code}: {r.text}")
    
    if r.status_code == 200:
        data = r.json()
        assert_test("venues_run" in data, "Response contains 'venues_run'")
        venues_run = data.get("venues_run", 0)
        assert_test(venues_run >= 10 and venues_run <= 15, 
                   f"venues_run is ~12 (10-15)", f"Got {venues_run}")
        log_info(f"First run: venues_run={venues_run}, total_new={data.get('total_new')}, total_updated={data.get('total_updated')}")
    
    # Second run (should be idempotent)
    log_info("Running second scraper run (idempotent check)...")
    r = requests.post(f"{BASE_URL}/admin/scrapers/run-all", headers=headers)
    assert_test(r.status_code == 200, "Second run returns 200", f"Got {r.status_code}: {r.text}")
    
    if r.status_code == 200:
        data = r.json()
        total_new = data.get("total_new", -1)
        assert_test(total_new == 0, 
                   "Second run: total_new should be 0 (idempotent)", 
                   f"Got total_new={total_new}")
        log_info(f"Second run: venues_run={data.get('venues_run')}, total_new={total_new}, total_updated={data.get('total_updated')}")

def test_regression_health():
    """Test regression - health endpoint"""
    log_test("9. Regression - GET /api/health (public)")
    
    r = requests.get(f"{BASE_URL}/health")
    assert_test(r.status_code == 200, "GET /health returns 200", f"Got {r.status_code}: {r.text}")
    
    if r.status_code == 200:
        data = r.json()
        assert_test("ok" in data, "Response contains 'ok' field")
        assert_test(data.get("ok") == True, "ok is True", f"Got {data.get('ok')}")
        log_info(f"Health check response: {json.dumps(data, indent=2)}")

def main():
    print(f"\n{'='*60}")
    print(f"{BLUE}BATCH 3 BACKEND TESTING{RESET}")
    print(f"{'='*60}")
    print(f"Base URL: {BASE_URL}")
    print(f"Admin: {ADMIN_EMAIL}")
    print(f"{'='*60}\n")
    
    # Setup: Login and register user
    if not login_admin():
        print(f"{RED}Failed to login as admin. Aborting.{RESET}")
        sys.exit(1)
    
    if not register_fresh_user():
        print(f"{RED}Failed to register test user. Aborting.{RESET}")
        sys.exit(1)
    
    # Run tests
    try:
        test_notification_preferences()
        test_venue_enrichment()
        test_admin_scrapers()
        test_regression_events()
        test_regression_venue_detail()
        test_regression_scrapers_run_all()
        test_regression_health()
    except Exception as e:
        log_fail(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
    
    # Print summary
    print_summary()
    
    # Exit with appropriate code
    sys.exit(0 if failed == 0 else 1)

if __name__ == "__main__":
    main()
