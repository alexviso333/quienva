#!/usr/bin/env python3
"""
FourVenues Universal Scraper Test Suite
Tests the new FourVenues API scraper feature and regression tests.
"""
import requests
import time
import json
from datetime import datetime, timedelta

# Use the production backend URL from frontend/.env
BASE_URL = "https://bereal-clone-1.preview.emergentagent.com/api"

# Test credentials
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

# Global state
admin_token = None
user_token = None
user_id = None
original_fv_token = None
test_venue_id = None
amok_venue_id = None

def log(msg):
    print(f"[TEST] {msg}")

def assert_eq(actual, expected, msg=""):
    if actual != expected:
        raise AssertionError(f"{msg}: expected {expected}, got {actual}")

def assert_in(item, container, msg=""):
    if item not in container:
        raise AssertionError(f"{msg}: {item} not in {container}")

def assert_true(condition, msg=""):
    if not condition:
        raise AssertionError(f"{msg}: condition is False")

def assert_status(response, expected_status, msg=""):
    if response.status_code != expected_status:
        try:
            body = response.json()
        except Exception:
            body = response.text
        raise AssertionError(f"{msg}: expected status {expected_status}, got {response.status_code}. Body: {body}")

# ============================================================================
# SETUP: Login
# ============================================================================
def setup():
    global admin_token, user_token, user_id
    
    log("=== SETUP: Admin Login ===")
    r = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert_status(r, 200, "Admin login")
    data = r.json()
    admin_token = data["token"]
    log(f"✓ Admin logged in, token: {admin_token[:20]}...")
    
    # Create a test user for non-admin tests
    log("=== SETUP: Create Test User ===")
    timestamp = int(time.time())
    r = requests.post(f"{BASE_URL}/auth/register", json={
        "email": f"testuser_{timestamp}@test.com",
        "password": "testpass123",
        "name": f"Test User {timestamp}",
        "username": f"testuser{timestamp}",
        "city": "Palma de Mallorca"
    })
    assert_status(r, 200, "User registration")
    data = r.json()
    user_token = data["token"]
    user_id = data["user"]["user_id"]
    log(f"✓ Test user created: {user_id}")

# ============================================================================
# TEST 1: FourVenues Guest Token Endpoints
# ============================================================================
def test_fourvenues_token_get():
    global original_fv_token
    
    log("\n=== TEST 1.1: GET /admin/scrapers/fourvenues-token (Admin) ===")
    r = requests.get(
        f"{BASE_URL}/admin/scrapers/fourvenues-token",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert_status(r, 200, "GET fourvenues-token as admin")
    data = r.json()
    
    # Verify response structure
    assert_in("configured", data, "Response should have 'configured' field")
    assert_in("masked", data, "Response should have 'masked' field")
    assert_in("valid", data, "Response should have 'valid' field")
    
    assert_eq(data["configured"], True, "Token should be configured")
    assert_true(len(data["masked"]) > 0, "Masked token should not be empty")
    # valid can be True, False, or None (if API check failed)
    log(f"✓ Token configured: {data['configured']}, masked: {data['masked']}, valid: {data['valid']}")
    
    # Store the original token info for later restoration
    original_fv_token = data
    
    log("\n=== TEST 1.2: GET /admin/scrapers/fourvenues-token (Non-Admin) ===")
    r = requests.get(
        f"{BASE_URL}/admin/scrapers/fourvenues-token",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert_status(r, 403, "GET fourvenues-token as non-admin should return 403")
    log("✓ Non-admin correctly denied with 403")
    
    log("\n=== TEST 1.3: GET /admin/scrapers/fourvenues-token (Unauthenticated) ===")
    r = requests.get(f"{BASE_URL}/admin/scrapers/fourvenues-token")
    assert_status(r, 401, "GET fourvenues-token without auth should return 401")
    log("✓ Unauthenticated request correctly denied with 401")

def test_fourvenues_token_put():
    log("\n=== TEST 1.4: PUT /admin/scrapers/fourvenues-token (Invalid Token) ===")
    r = requests.put(
        f"{BASE_URL}/admin/scrapers/fourvenues-token",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"token": "invalid-token-no-dots"}
    )
    assert_status(r, 400, "PUT with invalid token (no dots) should return 400")
    log("✓ Invalid token correctly rejected with 400")
    
    log("\n=== TEST 1.5: PUT /admin/scrapers/fourvenues-token (Valid JWT Format) ===")
    # Use a well-formed JWT (3 dot-separated parts) but fake
    fake_jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    r = requests.put(
        f"{BASE_URL}/admin/scrapers/fourvenues-token",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"token": fake_jwt}
    )
    assert_status(r, 200, "PUT with well-formed JWT should return 200")
    data = r.json()
    assert_in("ok", data, "Response should have 'ok' field")
    assert_eq(data["ok"], True, "Response should indicate success")
    assert_in("valid", data, "Response should have 'valid' field")
    # valid will likely be False or None since it's a fake token
    log(f"✓ Well-formed JWT accepted, valid: {data['valid']}")
    
    # IMPORTANT: Restore the real token from backend/.env
    log("\n=== TEST 1.6: Restore Real FourVenues Token ===")
    real_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhcHAiOiJjbGktYXBpLXNlcnZpY2UiLCJpYXQiOjE3ODU1NDQxNTB9.TmgVbEafSUMg5EWd_0YZ08_Q92myUL_Upb6rid2V0h0"
    r = requests.put(
        f"{BASE_URL}/admin/scrapers/fourvenues-token",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"token": real_token}
    )
    assert_status(r, 200, "Restore real token should return 200")
    data = r.json()
    assert_eq(data["ok"], True, "Token restoration should succeed")
    log(f"✓ Real token restored, valid: {data['valid']}")
    
    log("\n=== TEST 1.7: PUT /admin/scrapers/fourvenues-token (Non-Admin) ===")
    r = requests.put(
        f"{BASE_URL}/admin/scrapers/fourvenues-token",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"token": real_token}
    )
    assert_status(r, 403, "PUT as non-admin should return 403")
    log("✓ Non-admin PUT correctly denied with 403")

# ============================================================================
# TEST 2: Scraper Venues List & Adapters
# ============================================================================
def test_scrapers_list():
    global amok_venue_id
    
    log("\n=== TEST 2.1: GET /admin/scrapers (Admin) ===")
    r = requests.get(
        f"{BASE_URL}/admin/scrapers",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert_status(r, 200, "GET scrapers as admin")
    venues = r.json()
    
    assert_true(isinstance(venues, list), "Response should be a list")
    assert_true(len(venues) >= 7, f"Should have at least 7 venues, got {len(venues)}")
    log(f"✓ Found {len(venues)} venues")
    
    # Verify all venues have adapter_type="fourvenues_api" and non-empty slug
    expected_slugs = ["amok", "fitz-mallorca", "over-club", "lunita", "mar-salada", "luna-palma", "palma-events"]
    found_slugs = []
    
    for venue in venues:
        assert_in("adapter_type", venue, f"Venue {venue.get('name')} should have adapter_type")
        assert_eq(venue["adapter_type"], "fourvenues_api", f"Venue {venue.get('name')} should use fourvenues_api adapter")
        assert_in("slug", venue, f"Venue {venue.get('name')} should have slug")
        assert_true(len(venue["slug"]) > 0, f"Venue {venue.get('name')} should have non-empty slug")
        found_slugs.append(venue["slug"])
        
        # Store Amok venue ID for later tests
        if venue["slug"] == "amok":
            amok_venue_id = venue["id"]
            log(f"✓ Found Amok venue: {amok_venue_id}")
    
    # Verify all expected slugs are present
    for slug in expected_slugs:
        assert_in(slug, found_slugs, f"Expected slug '{slug}' not found in venues")
    
    log(f"✓ All venues have correct adapter_type and slugs: {found_slugs}")
    
    log("\n=== TEST 2.2: GET /admin/scrapers (Non-Admin) ===")
    r = requests.get(
        f"{BASE_URL}/admin/scrapers",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert_status(r, 403, "GET scrapers as non-admin should return 403")
    log("✓ Non-admin correctly denied with 403")

def test_scrapers_create():
    global test_venue_id
    
    log("\n=== TEST 2.3: POST /admin/scrapers (Valid) ===")
    r = requests.post(
        f"{BASE_URL}/admin/scrapers",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "name": "Test FV Venue",
            "city": "Palma de Mallorca",
            "adapter_type": "fourvenues_api",
            "slug": "amok",
            "url": "https://site.fourvenues.com/es/amok"
        }
    )
    assert_status(r, 200, "POST scraper with valid data")
    venue = r.json()
    
    assert_in("id", venue, "Created venue should have id")
    test_venue_id = venue["id"]
    assert_eq(venue["name"], "Test FV Venue", "Venue name should match")
    assert_eq(venue["adapter_type"], "fourvenues_api", "Adapter type should match")
    assert_eq(venue["slug"], "amok", "Slug should match")
    log(f"✓ Created test venue: {test_venue_id}")
    
    log("\n=== TEST 2.4: POST /admin/scrapers (Missing Slug) ===")
    r = requests.post(
        f"{BASE_URL}/admin/scrapers",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "name": "Test No Slug",
            "city": "Palma de Mallorca",
            "adapter_type": "fourvenues_api",
            "url": ""  # No URL and no slug
        }
    )
    assert_status(r, 400, "POST with fourvenues_api but no slug/url should return 400")
    log("✓ Missing slug correctly rejected with 400")
    
    log("\n=== TEST 2.5: POST /admin/scrapers (Invalid Adapter) ===")
    r = requests.post(
        f"{BASE_URL}/admin/scrapers",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "name": "Test Invalid Adapter",
            "city": "Palma de Mallorca",
            "adapter_type": "bogus_adapter",
            "url": "https://example.com"
        }
    )
    assert_status(r, 400, "POST with invalid adapter_type should return 400")
    log("✓ Invalid adapter_type correctly rejected with 400")
    
    log("\n=== TEST 2.6: POST /admin/scrapers (Non-Admin) ===")
    r = requests.post(
        f"{BASE_URL}/admin/scrapers",
        headers={"Authorization": f"Bearer {user_token}"},
        json={
            "name": "Test",
            "city": "Palma de Mallorca",
            "adapter_type": "fourvenues_api",
            "slug": "test",
            "url": "https://example.com"
        }
    )
    assert_status(r, 403, "POST as non-admin should return 403")
    log("✓ Non-admin POST correctly denied with 403")

# ============================================================================
# TEST 3: Running the Scraper
# ============================================================================
def test_run_scraper():
    log("\n=== TEST 3.1: POST /admin/scrapers/{id}/run (Amok) ===")
    assert_true(amok_venue_id is not None, "Amok venue ID should be set")
    
    r = requests.post(
        f"{BASE_URL}/admin/scrapers/{amok_venue_id}/run",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert_status(r, 200, "Run scraper for Amok")
    result = r.json()
    
    assert_in("ok", result, "Result should have 'ok' field")
    assert_eq(result["ok"], True, "Scraper should succeed")
    assert_in("events", result, "Result should have 'events' field")
    assert_true(result["events"] > 0, f"Should have scraped events, got {result['events']}")
    log(f"✓ Amok scraper ran successfully: {result['events']} events, {result.get('created', 0)} created, {result.get('updated', 0)} updated")
    
    # Verify events were created/updated
    log("\n=== TEST 3.2: Verify Scraped Events ===")
    r = requests.get(
        f"{BASE_URL}/events",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert_status(r, 200, "GET events")
    events = r.json()
    
    # Find at least one event with the new fields
    found_scraped = False
    for event in events:
        if "price_tiers" in event and "sale_state" in event and "current_price" in event:
            found_scraped = True
            # Verify structure
            assert_true(isinstance(event["price_tiers"], list), "price_tiers should be a list")
            assert_in(event["sale_state"], ["a_la_venta", "pocas_entradas", "agotado", "no_a_la_venta"], 
                     f"sale_state should be valid: {event['sale_state']}")
            # current_price can be number or null
            log(f"✓ Found scraped event: {event['name']}, sale_state={event['sale_state']}, price_tiers={len(event['price_tiers'])}, current_price={event['current_price']}")
            break
    
    assert_true(found_scraped, "Should find at least one event with pricing fields")

def test_run_all_scrapers():
    # Clean up test venue first to ensure we have exactly 7 venues
    if test_venue_id:
        log("\n=== Cleanup test venue before run-all ===")
        r = requests.delete(
            f"{BASE_URL}/admin/scrapers/{test_venue_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        if r.status_code == 200:
            log(f"✓ Deleted test venue before run-all")
    
    log("\n=== TEST 3.3: POST /admin/scrapers/run-all (First Run) ===")
    r = requests.post(
        f"{BASE_URL}/admin/scrapers/run-all",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert_status(r, 200, "Run all scrapers")
    result = r.json()
    
    assert_in("venues_run", result, "Result should have 'venues_run' field")
    assert_eq(result["venues_run"], 7, f"Should run 7 venues, got {result['venues_run']}")
    assert_in("total_new", result, "Result should have 'total_new' field")
    assert_in("total_updated", result, "Result should have 'total_updated' field")
    log(f"✓ Run-all completed: {result['venues_run']} venues, {result['total_new']} new, {result['total_updated']} updated")
    
    # Wait a moment for DB to settle
    time.sleep(2)
    
    log("\n=== TEST 3.4: POST /admin/scrapers/run-all (Second Run - Idempotency) ===")
    r = requests.post(
        f"{BASE_URL}/admin/scrapers/run-all",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert_status(r, 200, "Run all scrapers again")
    result = r.json()
    
    assert_eq(result["venues_run"], 7, "Should still run 7 venues")
    assert_eq(result["total_new"], 0, f"Second run should create 0 new events (idempotent), got {result['total_new']}")
    log(f"✓ Second run-all idempotent: {result['total_new']} new events (expected 0)")
    
    log("\n=== TEST 3.5: POST /admin/scrapers/run-all (Non-Admin) ===")
    r = requests.post(
        f"{BASE_URL}/admin/scrapers/run-all",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert_status(r, 403, "Run-all as non-admin should return 403")
    log("✓ Non-admin run-all correctly denied with 403")

# ============================================================================
# TEST 4: Regression Tests
# ============================================================================
def test_regression_auth():
    log("\n=== TEST 4.1: Regression - Auth Endpoints ===")
    
    # Login
    r = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert_status(r, 200, "POST /auth/login")
    log("✓ Login working")
    
    # Get me
    r = requests.get(
        f"{BASE_URL}/auth/me",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert_status(r, 200, "GET /auth/me")
    data = r.json()
    assert_in("user_id", data, "Me response should have user_id")
    log("✓ Get me working")

def test_regression_events():
    log("\n=== TEST 4.2: Regression - Events Endpoints ===")
    
    # GET events with filters
    filters = ["all", "hoy", "finde", "semana", "pasados"]
    for filter_val in filters:
        r = requests.get(
            f"{BASE_URL}/events?date={filter_val}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert_status(r, 200, f"GET /events?date={filter_val}")
    log("✓ Events filters working")
    
    # GET carousels
    r = requests.get(
        f"{BASE_URL}/events/carousels",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert_status(r, 200, "GET /events/carousels")
    log("✓ Carousels working")
    
    # GET genres
    r = requests.get(
        f"{BASE_URL}/events/genres",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert_status(r, 200, "GET /events/genres")
    log("✓ Genres working")

def test_regression_interests():
    log("\n=== TEST 4.3: Regression - Interest Endpoints ===")
    
    # Get an event to test with
    r = requests.get(
        f"{BASE_URL}/events",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    events = r.json()
    if len(events) > 0:
        event_id = events[0]["id"]
        
        # Test interest statuses
        for status in ["voy", "me_interesa", "none"]:
            r = requests.post(
                f"{BASE_URL}/events/{event_id}/interest",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"status": status}
            )
            assert_status(r, 200, f"POST /events/{event_id}/interest status={status}")
        log("✓ Interest endpoints working")

def test_regression_follow():
    log("\n=== TEST 4.4: Regression - Follow Endpoints ===")
    
    # Get an event to test with
    r = requests.get(
        f"{BASE_URL}/events",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    events = r.json()
    if len(events) > 0:
        event_id = events[0]["id"]
        
        # Follow
        r = requests.post(
            f"{BASE_URL}/events/{event_id}/follow",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert_status(r, 200, "POST /events/{id}/follow")
        
        # Unfollow
        r = requests.delete(
            f"{BASE_URL}/events/{event_id}/follow",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert_status(r, 200, "DELETE /events/{id}/follow")
        log("✓ Follow endpoints working")

def test_regression_badges():
    log("\n=== TEST 4.5: Regression - Badges Endpoints ===")
    
    r = requests.get(
        f"{BASE_URL}/me/badges",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert_status(r, 200, "GET /me/badges")
    log("✓ Badges working")

def test_regression_rankings():
    log("\n=== TEST 4.6: Regression - Rankings Endpoints ===")
    
    for ranking_type in ["friends", "world"]:
        r = requests.get(
            f"{BASE_URL}/rankings/{ranking_type}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert_status(r, 200, f"GET /rankings/{ranking_type}")
    log("✓ Rankings working")

def test_regression_friends():
    log("\n=== TEST 4.7: Regression - Friends Endpoints ===")
    
    r = requests.get(
        f"{BASE_URL}/friends",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert_status(r, 200, "GET /friends")
    log("✓ Friends working")

def test_regression_health():
    log("\n=== TEST 4.8: Regression - Health Endpoint ===")
    
    r = requests.get(f"{BASE_URL}/health")
    assert_status(r, 200, "GET /health")
    data = r.json()
    assert_in("ok", data, "Health response should have 'ok' field")
    log("✓ Health endpoint working")

def test_regression_admin_dashboard():
    log("\n=== TEST 4.9: Regression - Admin Dashboard ===")
    
    r = requests.get(
        f"{BASE_URL}/admin/dashboard",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert_status(r, 200, "GET /admin/dashboard")
    log("✓ Admin dashboard working")

# ============================================================================
# CLEANUP
# ============================================================================
def cleanup():
    # Test venue already deleted in test_run_all_scrapers
    pass

# ============================================================================
# MAIN
# ============================================================================
def main():
    try:
        setup()
        
        # FourVenues Token Tests
        test_fourvenues_token_get()
        test_fourvenues_token_put()
        
        # Scraper CRUD Tests
        test_scrapers_list()
        test_scrapers_create()
        
        # Scraper Run Tests
        test_run_scraper()
        test_run_all_scrapers()
        
        # Regression Tests
        test_regression_auth()
        test_regression_events()
        test_regression_interests()
        test_regression_follow()
        test_regression_badges()
        test_regression_rankings()
        test_regression_friends()
        test_regression_health()
        test_regression_admin_dashboard()
        
        cleanup()
        
        log("\n" + "="*80)
        log("🎉 ALL TESTS PASSED!")
        log("="*80)
        
    except AssertionError as e:
        log(f"\n❌ TEST FAILED: {e}")
        cleanup()
        exit(1)
    except Exception as e:
        log(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        cleanup()
        exit(1)

if __name__ == "__main__":
    main()
