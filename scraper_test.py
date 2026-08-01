#!/usr/bin/env python3
"""
Backend test for NEW scraper endpoints.
Tests all scraper CRUD operations, run endpoints, and regression tests.
"""
import requests
import time
import json
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8001/api"

# Test credentials
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

# Global state
admin_token = None
non_admin_token = None
non_admin_id = None
test_venue_id = None
fitz_venue_id = None

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

def assert_gte(actual, expected, msg=""):
    if actual < expected:
        raise AssertionError(f"{msg}: expected >= {expected}, got {actual}")

def assert_status(response, expected_status, msg=""):
    if response.status_code != expected_status:
        try:
            body = response.json()
        except Exception:
            body = response.text
        raise AssertionError(f"{msg}: expected status {expected_status}, got {response.status_code}. Body: {body}")

# ============================================================================
# SETUP: Login admin and create non-admin user
# ============================================================================
def setup():
    global admin_token, non_admin_token, non_admin_id
    
    log("=== SETUP: Login admin ===")
    r = requests.post(f"{BASE_URL}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert_status(r, 200, "Admin login")
    admin_token = r.json()["token"]
    log(f"✓ Admin logged in")
    
    log("=== SETUP: Create non-admin user ===")
    timestamp = int(time.time())
    non_admin_email = f"nonadmin_{timestamp}@test.com"
    r = requests.post(f"{BASE_URL}/auth/register", json={
        "email": non_admin_email,
        "password": "test123",
        "name": "Non Admin User",
        "username": f"nonadmin{timestamp}",
        "city": "Palma de Mallorca"
    })
    assert_status(r, 200, "Non-admin register")
    data = r.json()
    non_admin_token = data["token"]
    non_admin_id = data["user"]["user_id"]
    log(f"✓ Non-admin user created: {non_admin_id}")

# ============================================================================
# TEST 1: GET /api/admin/scrapers
# ============================================================================
def test_list_scrapers():
    global fitz_venue_id
    
    log("\n=== TEST 1: GET /api/admin/scrapers ===")
    
    # As admin → 200
    log("Test 1.1: As admin → 200 with seeded venues")
    r = requests.get(f"{BASE_URL}/admin/scrapers", headers={"Authorization": f"Bearer {admin_token}"})
    assert_status(r, 200, "List scrapers as admin")
    venues = r.json()
    assert_true(isinstance(venues, list), "Response should be a list")
    assert_gte(len(venues), 2, "Should have at least 2 seeded venues (Fitz + Amok)")
    
    # Check for Fitz Mallorca
    fitz = next((v for v in venues if v["name"] == "Fitz Mallorca"), None)
    assert_true(fitz is not None, "Fitz Mallorca should be in list")
    fitz_venue_id = fitz["id"]
    
    # Verify required fields
    required_fields = ["id", "name", "city", "adapter_type", "url", "active", 
                      "last_run_at", "last_run_ok", "last_run_events", 
                      "last_run_new", "last_run_updated", "last_run_error", "last_run_duration_ms"]
    for field in required_fields:
        assert_in(field, fitz, f"Fitz venue should have field: {field}")
    
    assert_eq(fitz["adapter_type"], "fourvenues_public_api", "Fitz should use fourvenues_public_api adapter")
    assert_eq(fitz["city"], "Palma de Mallorca", "Fitz should be in Palma de Mallorca")
    assert_eq(fitz["active"], True, "Fitz should be active")
    log(f"✓ Fitz Mallorca found with id: {fitz_venue_id}")
    
    # Check for Amok Mallorca
    amok = next((v for v in venues if v["name"] == "Amok Mallorca"), None)
    assert_true(amok is not None, "Amok Mallorca should be in list")
    assert_eq(amok["adapter_type"], "nextjs_html", "Amok should use nextjs_html adapter")
    log(f"✓ Amok Mallorca found with id: {amok['id']}")
    
    # As non-admin → 403
    log("Test 1.2: As non-admin → 403")
    r = requests.get(f"{BASE_URL}/admin/scrapers", headers={"Authorization": f"Bearer {non_admin_token}"})
    assert_status(r, 403, "List scrapers as non-admin should return 403")
    log("✓ Non-admin correctly denied")
    
    # Unauthenticated → 401
    log("Test 1.3: Unauthenticated → 401")
    r = requests.get(f"{BASE_URL}/admin/scrapers")
    assert_status(r, 401, "List scrapers without auth should return 401")
    log("✓ Unauthenticated correctly denied")

# ============================================================================
# TEST 2: POST /api/admin/scrapers
# ============================================================================
def test_create_scraper():
    global test_venue_id
    
    log("\n=== TEST 2: POST /api/admin/scrapers ===")
    
    # As admin with valid data → 201 or 200
    log("Test 2.1: As admin with valid data → 200/201")
    r = requests.post(f"{BASE_URL}/admin/scrapers", 
                     headers={"Authorization": f"Bearer {admin_token}"},
                     json={
                         "name": "Test Venue",
                         "city": "Palma de Mallorca",
                         "adapter_type": "nextjs_html",
                         "url": "https://example.com",
                         "active": True
                     })
    assert_true(r.status_code in [200, 201], f"Create scraper should return 200 or 201, got {r.status_code}")
    venue = r.json()
    assert_in("id", venue, "Created venue should have id")
    test_venue_id = venue["id"]
    assert_eq(venue["name"], "Test Venue", "Venue name should match")
    assert_eq(venue["adapter_type"], "nextjs_html", "Adapter type should match")
    assert_eq(venue["url"], "https://example.com", "URL should match")
    log(f"✓ Test venue created with id: {test_venue_id}")
    
    # Invalid adapter_type → 400
    log("Test 2.2: Invalid adapter_type 'foo' → 400")
    r = requests.post(f"{BASE_URL}/admin/scrapers",
                     headers={"Authorization": f"Bearer {admin_token}"},
                     json={
                         "name": "Invalid Venue",
                         "city": "Palma de Mallorca",
                         "adapter_type": "foo",
                         "url": "https://example.com",
                         "active": True
                     })
    assert_status(r, 400, "Invalid adapter_type should return 400")
    log("✓ Invalid adapter_type correctly rejected")
    
    # Non-admin → 403
    log("Test 2.3: Non-admin → 403")
    r = requests.post(f"{BASE_URL}/admin/scrapers",
                     headers={"Authorization": f"Bearer {non_admin_token}"},
                     json={
                         "name": "Another Venue",
                         "city": "Palma de Mallorca",
                         "adapter_type": "nextjs_html",
                         "url": "https://example.com",
                         "active": True
                     })
    assert_status(r, 403, "Non-admin create should return 403")
    log("✓ Non-admin correctly denied")

# ============================================================================
# TEST 3: PUT /api/admin/scrapers/{id}
# ============================================================================
def test_update_scraper():
    log("\n=== TEST 3: PUT /api/admin/scrapers/{id} ===")
    
    # As admin → 200
    log("Test 3.1: As admin → 200")
    r = requests.put(f"{BASE_URL}/admin/scrapers/{test_venue_id}",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    json={
                        "name": "Test Venue Updated",
                        "city": "Palma de Mallorca",
                        "adapter_type": "fourvenues_public_api",
                        "url": "https://example-updated.com",
                        "active": False
                    })
    assert_status(r, 200, "Update scraper should return 200")
    venue = r.json()
    assert_eq(venue["name"], "Test Venue Updated", "Name should be updated")
    assert_eq(venue["adapter_type"], "fourvenues_public_api", "Adapter type should be updated")
    assert_eq(venue["url"], "https://example-updated.com", "URL should be updated")
    assert_eq(venue["active"], False, "Active should be updated")
    log("✓ Venue updated successfully")
    
    # Non-existent id → 404
    log("Test 3.2: Non-existent id → 404")
    r = requests.put(f"{BASE_URL}/admin/scrapers/nonexistent-id",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    json={
                        "name": "Test",
                        "city": "Palma de Mallorca",
                        "adapter_type": "nextjs_html",
                        "url": "https://example.com",
                        "active": True
                    })
    assert_status(r, 404, "Update non-existent venue should return 404")
    log("✓ Non-existent venue correctly returns 404")
    
    # Non-admin → 403
    log("Test 3.3: Non-admin → 403")
    r = requests.put(f"{BASE_URL}/admin/scrapers/{test_venue_id}",
                    headers={"Authorization": f"Bearer {non_admin_token}"},
                    json={
                        "name": "Test",
                        "city": "Palma de Mallorca",
                        "adapter_type": "nextjs_html",
                        "url": "https://example.com",
                        "active": True
                    })
    assert_status(r, 403, "Non-admin update should return 403")
    log("✓ Non-admin correctly denied")

# ============================================================================
# TEST 4: DELETE /api/admin/scrapers/{id}
# ============================================================================
def test_delete_scraper():
    log("\n=== TEST 4: DELETE /api/admin/scrapers/{id} ===")
    
    # Non-admin → 403
    log("Test 4.1: Non-admin → 403")
    r = requests.delete(f"{BASE_URL}/admin/scrapers/{test_venue_id}",
                       headers={"Authorization": f"Bearer {non_admin_token}"})
    assert_status(r, 403, "Non-admin delete should return 403")
    log("✓ Non-admin correctly denied")
    
    # As admin → 200
    log("Test 4.2: As admin → 200")
    r = requests.delete(f"{BASE_URL}/admin/scrapers/{test_venue_id}",
                       headers={"Authorization": f"Bearer {admin_token}"})
    assert_status(r, 200, "Delete scraper should return 200")
    data = r.json()
    assert_eq(data.get("ok"), True, "Response should have ok: true")
    log("✓ Venue deleted successfully")
    
    # Non-existent id → 404
    log("Test 4.3: Non-existent id → 404")
    r = requests.delete(f"{BASE_URL}/admin/scrapers/nonexistent-id",
                       headers={"Authorization": f"Bearer {admin_token}"})
    assert_status(r, 404, "Delete non-existent venue should return 404")
    log("✓ Non-existent venue correctly returns 404")

# ============================================================================
# TEST 5: POST /api/admin/scrapers/{id}/run (Fitz venue)
# ============================================================================
def test_run_single_scraper():
    log("\n=== TEST 5: POST /api/admin/scrapers/{id}/run (Fitz) ===")
    
    # Non-admin → 403
    log("Test 5.1: Non-admin → 403")
    r = requests.post(f"{BASE_URL}/admin/scrapers/{fitz_venue_id}/run",
                     headers={"Authorization": f"Bearer {non_admin_token}"})
    assert_status(r, 403, "Non-admin run should return 403")
    log("✓ Non-admin correctly denied")
    
    # As admin → 200 with expected structure
    log("Test 5.2: As admin → 200 with correct structure")
    r = requests.post(f"{BASE_URL}/admin/scrapers/{fitz_venue_id}/run",
                     headers={"Authorization": f"Bearer {admin_token}"})
    assert_status(r, 200, "Run scraper should return 200")
    result = r.json()
    
    # Verify structure
    required_fields = ["venue_id", "venue_name", "ok", "events", "created", 
                      "updated", "unchanged", "error", "duration_ms"]
    for field in required_fields:
        assert_in(field, result, f"Result should have field: {field}")
    
    assert_eq(result["ok"], True, "Scraper run should be successful")
    assert_eq(result["venue_id"], fitz_venue_id, "Venue ID should match")
    assert_eq(result["venue_name"], "Fitz Mallorca", "Venue name should match")
    assert_gte(result["events"], 30, "Fitz should have at least 30 events")
    log(f"✓ Fitz scraper ran successfully: {result['events']} events, {result['created']} new, {result['updated']} updated")
    
    # Second run immediately after → idempotent (created=0, unchanged=events)
    log("Test 5.3: Second run immediately after → idempotent")
    time.sleep(1)  # Small delay
    r = requests.post(f"{BASE_URL}/admin/scrapers/{fitz_venue_id}/run",
                     headers={"Authorization": f"Bearer {admin_token}"})
    assert_status(r, 200, "Second run should return 200")
    result2 = r.json()
    assert_eq(result2["ok"], True, "Second run should be successful")
    assert_eq(result2["created"], 0, "Second run should create 0 new events (idempotent)")
    assert_eq(result2["unchanged"], result2["events"], "All events should be unchanged on second run")
    log(f"✓ Second run idempotent: {result2['unchanged']} unchanged, {result2['created']} created")

# ============================================================================
# TEST 6: POST /api/admin/scrapers/run-all
# ============================================================================
def test_run_all_scrapers():
    log("\n=== TEST 6: POST /api/admin/scrapers/run-all ===")
    
    # Non-admin → 403
    log("Test 6.1: Non-admin → 403")
    r = requests.post(f"{BASE_URL}/admin/scrapers/run-all",
                     headers={"Authorization": f"Bearer {non_admin_token}"})
    assert_status(r, 403, "Non-admin run-all should return 403")
    log("✓ Non-admin correctly denied")
    
    # As admin → 200 with expected structure
    log("Test 6.2: As admin → 200 with correct structure")
    r = requests.post(f"{BASE_URL}/admin/scrapers/run-all",
                     headers={"Authorization": f"Bearer {admin_token}"})
    assert_status(r, 200, "Run all scrapers should return 200")
    result = r.json()
    
    # Verify structure
    assert_in("venues_run", result, "Result should have venues_run")
    assert_in("total_new", result, "Result should have total_new")
    assert_in("total_updated", result, "Result should have total_updated")
    assert_in("results", result, "Result should have results array")
    
    assert_gte(result["venues_run"], 2, "Should run at least 2 venues (Fitz + Amok)")
    assert_true(isinstance(result["results"], list), "Results should be a list")
    log(f"✓ Run-all successful: {result['venues_run']} venues, {result['total_new']} new, {result['total_updated']} updated")

# ============================================================================
# TEST 7: Verify scraped events in feed
# ============================================================================
def test_scraped_events_in_feed():
    log("\n=== TEST 7: Verify scraped events in feed ===")
    
    # GET /api/events as authenticated user
    log("Test 7.1: GET /api/events returns scraped events")
    r = requests.get(f"{BASE_URL}/events", headers={"Authorization": f"Bearer {admin_token}"})
    assert_status(r, 200, "Get events should return 200")
    events = r.json()
    assert_true(isinstance(events, list), "Events should be a list")
    assert_gte(len(events), 50, "Should have at least 50 events (from scrapers)")
    log(f"✓ Found {len(events)} events in feed")
    
    # Find Fitz events (scraped from Fitz Mallorca)
    fitz_events = [e for e in events if "Fitz" in e.get("venue", "")]
    assert_gte(len(fitz_events), 1, "Should have at least 1 Fitz event")
    log(f"✓ Found {len(fitz_events)} Fitz Mallorca events")
    
    # Find Amok events (scraped from Amok Mallorca)
    amok_events = [e for e in events if "Amok" in e.get("venue", "")]
    assert_gte(len(amok_events), 1, "Should have at least 1 Amok event")
    log(f"✓ Found {len(amok_events)} Amok Mallorca events")
    
    # Total scraped events (Fitz + Amok)
    scraped_events = fitz_events + amok_events
    assert_gte(len(scraped_events), 50, "Should have at least 50 scraped events (Fitz ~37 + Amok ~76)")
    log(f"✓ Found {len(scraped_events)} total scraped events from Fitz and Amok")
    
    # Verify scraped event structure
    log("Test 7.2: Verify scraped event structure")
    sample_event = scraped_events[0]
    
    # Required fields (note: source and external_id are internal fields not exposed in API)
    assert_in("price_tiers", sample_event, "Event should have price_tiers")
    assert_true(isinstance(sample_event["price_tiers"], list), "price_tiers should be a list")
    
    # Check sale_state
    assert_in("sale_state", sample_event, "Event should have sale_state")
    valid_states = ["no_a_la_venta", "a_la_venta", "pocas_entradas", "agotado"]
    assert_in(sample_event["sale_state"], valid_states, f"sale_state should be one of {valid_states}")
    
    # Check current_price
    assert_in("current_price", sample_event, "Event should have current_price")
    if sample_event["price_tiers"]:
        # If there are price tiers, current_price should be a number or None
        assert_true(isinstance(sample_event["current_price"], (int, float, type(None))),
                   "current_price should be a number or None")
    
    log(f"✓ Sample event structure verified: venue={sample_event['venue']}, "
        f"sale_state={sample_event['sale_state']}, price_tiers={len(sample_event['price_tiers'])}")
    
    # Check price_tiers structure if present
    if sample_event["price_tiers"]:
        tier = sample_event["price_tiers"][0]
        assert_in("name", tier, "Price tier should have name")
        assert_in("price", tier, "Price tier should have price")
        assert_in("sold_out", tier, "Price tier should have sold_out")
        log(f"✓ Price tier structure verified: {tier['name']} - {tier['price']}€")

# ============================================================================
# REGRESSION TESTS
# ============================================================================
def test_regression_auth():
    global admin_token
    
    log("\n=== REGRESSION: Auth endpoints ===")
    
    # Login
    r = requests.post(f"{BASE_URL}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert_status(r, 200, "Login should work")
    temp_token = r.json()["token"]
    log("✓ Login working")
    
    # Me
    r = requests.get(f"{BASE_URL}/auth/me", headers={"Authorization": f"Bearer {temp_token}"})
    assert_status(r, 200, "Me endpoint should work")
    log("✓ Me endpoint working")
    
    # Logout
    r = requests.post(f"{BASE_URL}/auth/logout", headers={"Authorization": f"Bearer {temp_token}"})
    assert_status(r, 200, "Logout should work")
    log("✓ Logout working")
    
    # Re-login for subsequent tests
    r = requests.post(f"{BASE_URL}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    admin_token = r.json()["token"]

def test_regression_events():
    log("\n=== REGRESSION: Events endpoints ===")
    
    # GET /events
    r = requests.get(f"{BASE_URL}/events", headers={"Authorization": f"Bearer {admin_token}"})
    assert_status(r, 200, "Get events should work")
    log("✓ GET /events working")
    
    # GET /events/carousels
    r = requests.get(f"{BASE_URL}/events/carousels", headers={"Authorization": f"Bearer {admin_token}"})
    assert_status(r, 200, "Get carousels should work")
    log("✓ GET /events/carousels working")
    
    # GET /events/top-weekend
    r = requests.get(f"{BASE_URL}/events/top-weekend", headers={"Authorization": f"Bearer {admin_token}"})
    assert_true(r.status_code in [200, 204], "Get top-weekend should work")
    log("✓ GET /events/top-weekend working")
    
    # GET /events/genres
    r = requests.get(f"{BASE_URL}/events/genres", headers={"Authorization": f"Bearer {admin_token}"})
    assert_status(r, 200, "Get genres should work")
    log("✓ GET /events/genres working")

def test_regression_interests():
    log("\n=== REGRESSION: Interests endpoint ===")
    
    # Get an event
    r = requests.get(f"{BASE_URL}/events", headers={"Authorization": f"Bearer {admin_token}"})
    events = r.json()
    if events:
        event_id = events[0]["id"]
        
        # POST interest
        r = requests.post(f"{BASE_URL}/events/{event_id}/interest",
                         headers={"Authorization": f"Bearer {admin_token}"},
                         json={"status": "voy"})
        assert_status(r, 200, "Post interest should work")
        log("✓ POST /events/{id}/interest working")

def test_regression_follow():
    log("\n=== REGRESSION: Follow endpoints ===")
    
    # Get an event
    r = requests.get(f"{BASE_URL}/events", headers={"Authorization": f"Bearer {admin_token}"})
    events = r.json()
    if events:
        event_id = events[0]["id"]
        
        # POST follow
        r = requests.post(f"{BASE_URL}/events/{event_id}/follow",
                         headers={"Authorization": f"Bearer {admin_token}"})
        assert_status(r, 200, "Post follow should work")
        log("✓ POST /events/{id}/follow working")
        
        # DELETE follow
        r = requests.delete(f"{BASE_URL}/events/{event_id}/follow",
                           headers={"Authorization": f"Bearer {admin_token}"})
        assert_status(r, 200, "Delete follow should work")
        log("✓ DELETE /events/{id}/follow working")
        
        # GET follow-status
        r = requests.get(f"{BASE_URL}/events/{event_id}/follow-status",
                        headers={"Authorization": f"Bearer {admin_token}"})
        assert_status(r, 200, "Get follow-status should work")
        log("✓ GET /events/{id}/follow-status working")

def test_regression_pricing():
    log("\n=== REGRESSION: Pricing admin endpoint ===")
    
    # Get an event
    r = requests.get(f"{BASE_URL}/events", headers={"Authorization": f"Bearer {admin_token}"})
    events = r.json()
    if events:
        event_id = events[0]["id"]
        
        # PUT pricing
        r = requests.put(f"{BASE_URL}/admin/events/{event_id}/pricing",
                        headers={"Authorization": f"Bearer {admin_token}"},
                        json={
                            "price_tiers": [{"name": "General", "price": 15.0, "sold_out": False}],
                            "sale_state": "a_la_venta",
                            "silent": True
                        })
        assert_status(r, 200, "Put pricing should work")
        log("✓ PUT /admin/events/{id}/pricing working")

def test_regression_notify_low_stock():
    log("\n=== REGRESSION: Notify low stock endpoint ===")
    
    # Get an event
    r = requests.get(f"{BASE_URL}/events", headers={"Authorization": f"Bearer {admin_token}"})
    events = r.json()
    if events:
        event_id = events[0]["id"]
        
        # POST notify-low-stock
        r = requests.post(f"{BASE_URL}/admin/events/{event_id}/notify-low-stock",
                         headers={"Authorization": f"Bearer {admin_token}"})
        assert_status(r, 200, "Post notify-low-stock should work")
        log("✓ POST /admin/events/{id}/notify-low-stock working")

def test_regression_admin_moments():
    log("\n=== REGRESSION: Admin moments endpoints ===")
    
    # GET /admin/moments
    r = requests.get(f"{BASE_URL}/admin/moments", headers={"Authorization": f"Bearer {admin_token}"})
    assert_status(r, 200, "Get admin moments should work")
    log("✓ GET /admin/moments working")

def test_regression_friends():
    log("\n=== REGRESSION: Friends endpoints ===")
    
    # GET /friends
    r = requests.get(f"{BASE_URL}/friends", headers={"Authorization": f"Bearer {admin_token}"})
    assert_status(r, 200, "Get friends should work")
    log("✓ GET /friends working")

def test_regression_badges():
    log("\n=== REGRESSION: Badges endpoints ===")
    
    # GET /me/badges
    r = requests.get(f"{BASE_URL}/me/badges", headers={"Authorization": f"Bearer {admin_token}"})
    assert_status(r, 200, "Get me badges should work")
    log("✓ GET /me/badges working")
    
    # GET /badges/catalog
    r = requests.get(f"{BASE_URL}/badges/catalog", headers={"Authorization": f"Bearer {admin_token}"})
    assert_status(r, 200, "Get badges catalog should work")
    log("✓ GET /badges/catalog working")

def test_regression_rankings():
    log("\n=== REGRESSION: Rankings endpoints ===")
    
    # GET /rankings/friends
    r = requests.get(f"{BASE_URL}/rankings/friends", headers={"Authorization": f"Bearer {admin_token}"})
    assert_status(r, 200, "Get rankings friends should work")
    log("✓ GET /rankings/friends working")
    
    # GET /rankings/city
    r = requests.get(f"{BASE_URL}/rankings/city", headers={"Authorization": f"Bearer {admin_token}"})
    assert_status(r, 200, "Get rankings city should work")
    log("✓ GET /rankings/city working")
    
    # GET /rankings/world
    r = requests.get(f"{BASE_URL}/rankings/world", headers={"Authorization": f"Bearer {admin_token}"})
    assert_status(r, 200, "Get rankings world should work")
    log("✓ GET /rankings/world working")

def test_regression_chats():
    log("\n=== REGRESSION: Chats endpoints (quick sanity) ===")
    
    # GET /dm/threads
    r = requests.get(f"{BASE_URL}/dm/threads", headers={"Authorization": f"Bearer {admin_token}"})
    assert_status(r, 200, "Get DM threads should work")
    log("✓ GET /dm/threads working")
    
    # GET /groups
    r = requests.get(f"{BASE_URL}/groups", headers={"Authorization": f"Bearer {admin_token}"})
    assert_status(r, 200, "Get groups should work")
    log("✓ GET /groups working")

def test_regression_health():
    log("\n=== REGRESSION: Health endpoint ===")
    
    # GET /api/health (no auth)
    r = requests.get(f"{BASE_URL}/health")
    assert_status(r, 200, "Health endpoint should work without auth")
    log("✓ GET /api/health working")

# ============================================================================
# MAIN
# ============================================================================
def main():
    try:
        setup()
        
        # NEW SCRAPER ENDPOINTS
        test_list_scrapers()
        test_create_scraper()
        test_update_scraper()
        test_delete_scraper()
        test_run_single_scraper()
        test_run_all_scrapers()
        test_scraped_events_in_feed()
        
        # REGRESSION TESTS
        test_regression_auth()
        test_regression_events()
        test_regression_interests()
        test_regression_follow()
        test_regression_pricing()
        test_regression_notify_low_stock()
        test_regression_admin_moments()
        test_regression_friends()
        test_regression_badges()
        test_regression_rankings()
        test_regression_chats()
        test_regression_health()
        
        log("\n" + "="*80)
        log("🎉 ALL TESTS PASSED!")
        log("="*80)
        
    except AssertionError as e:
        log(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        log(f"\n❌ UNEXPECTED ERROR: {e}")
        raise

if __name__ == "__main__":
    main()
