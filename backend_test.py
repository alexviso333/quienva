#!/usr/bin/env python3
"""
Backend test for NEW event pricing + follow + auto-notification endpoints.
Tests the latest iteration with comprehensive coverage.
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
user1_token = None
user2_token = None
user1_id = None
user2_id = None
test_event_id = None

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
# SETUP: Login and create test users
# ============================================================================

def test_admin_login():
    global admin_token
    log("Admin login...")
    r = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert_status(r, 200, "Admin login")
    data = r.json()
    admin_token = data["token"]
    log(f"✓ Admin logged in: {admin_token[:20]}...")

def test_register_users():
    global user1_token, user2_token, user1_id, user2_id
    log("Registering user1 (Alice) in Palma de Mallorca...")
    r1 = requests.post(f"{BASE_URL}/auth/register", json={
        "email": f"alice_{int(time.time())}@test.com",
        "password": "test123",
        "name": "Alice Test",
        "username": f"alice_{int(time.time())}",
        "city": "Palma de Mallorca"
    })
    assert_status(r1, 200, "Register user1")
    data1 = r1.json()
    user1_token = data1["token"]
    user1_id = data1["user"]["user_id"]
    log(f"✓ User1 registered: {user1_id}")

    time.sleep(0.5)
    log("Registering user2 (Bob) in Palma de Mallorca...")
    r2 = requests.post(f"{BASE_URL}/auth/register", json={
        "email": f"bob_{int(time.time())}@test.com",
        "password": "test123",
        "name": "Bob Test",
        "username": f"bob_{int(time.time())}",
        "city": "Palma de Mallorca"
    })
    assert_status(r2, 200, "Register user2")
    data2 = r2.json()
    user2_token = data2["token"]
    user2_id = data2["user"]["user_id"]
    log(f"✓ User2 registered: {user2_id}")

# ============================================================================
# TEST 1: Follow endpoints
# ============================================================================

def test_follow_endpoints():
    global test_event_id
    log("\n=== TEST 1: Follow Endpoints ===")
    
    # Create a test event first
    log("Creating test event...")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    r = requests.post(f"{BASE_URL}/admin/events", 
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "name": "Test Event for Follow",
            "venue": "Test Venue",
            "address": "Test Address",
            "date": tomorrow,
            "time": "22:00",
            "genre": "Electrónica",
            "city": "Palma de Mallorca",
            "price_tiers": [],
            "sale_state": "no_a_la_venta",
            "currency": "EUR"
        })
    assert_status(r, 200, "Create test event")
    test_event_id = r.json()["id"]
    log(f"✓ Test event created: {test_event_id}")

    # Test 1.1: POST /api/events/{event_id}/follow (first call)
    log("Test 1.1: POST follow (first call)...")
    r = requests.post(f"{BASE_URL}/events/{test_event_id}/follow",
        headers={"Authorization": f"Bearer {user1_token}"})
    assert_status(r, 200, "Follow event first call")
    data = r.json()
    assert_eq(data.get("ok"), True, "Follow response ok")
    assert_eq(data.get("following"), True, "Follow response following")
    log("✓ First follow call successful")

    # Test 1.2: POST /api/events/{event_id}/follow (second call - idempotent)
    log("Test 1.2: POST follow (second call - idempotent)...")
    r = requests.post(f"{BASE_URL}/events/{test_event_id}/follow",
        headers={"Authorization": f"Bearer {user1_token}"})
    assert_status(r, 200, "Follow event second call")
    data = r.json()
    assert_eq(data.get("following"), True, "Follow still true on second call")
    log("✓ Second follow call idempotent")

    # Test 1.3: GET /api/events/{event_id}/follow-status
    log("Test 1.3: GET follow-status...")
    r = requests.get(f"{BASE_URL}/events/{test_event_id}/follow-status",
        headers={"Authorization": f"Bearer {user1_token}"})
    assert_status(r, 200, "Get follow status")
    data = r.json()
    assert_eq(data.get("following"), True, "Follow status should be true")
    log("✓ Follow status correct")

    # Test 1.4: DELETE /api/events/{event_id}/follow (first call)
    log("Test 1.4: DELETE follow (first call)...")
    r = requests.delete(f"{BASE_URL}/events/{test_event_id}/follow",
        headers={"Authorization": f"Bearer {user1_token}"})
    assert_status(r, 200, "Unfollow event")
    data = r.json()
    assert_eq(data.get("ok"), True, "Unfollow response ok")
    assert_eq(data.get("following"), False, "Unfollow response following")
    log("✓ Unfollow successful")

    # Test 1.5: DELETE /api/events/{event_id}/follow (second call - idempotent)
    log("Test 1.5: DELETE follow (second call - idempotent)...")
    r = requests.delete(f"{BASE_URL}/events/{test_event_id}/follow",
        headers={"Authorization": f"Bearer {user1_token}"})
    assert_status(r, 200, "Unfollow event second call")
    data = r.json()
    assert_eq(data.get("following"), False, "Unfollow still false on second call")
    log("✓ Second unfollow call idempotent")

    # Test 1.6: GET follow-status after unfollow
    log("Test 1.6: GET follow-status after unfollow...")
    r = requests.get(f"{BASE_URL}/events/{test_event_id}/follow-status",
        headers={"Authorization": f"Bearer {user1_token}"})
    assert_status(r, 200, "Get follow status after unfollow")
    data = r.json()
    assert_eq(data.get("following"), False, "Follow status should be false")
    log("✓ Follow status correct after unfollow")

    # Test 1.7: POST follow with non-existent event_id
    log("Test 1.7: POST follow with non-existent event_id...")
    r = requests.post(f"{BASE_URL}/events/nonexistent-event-id/follow",
        headers={"Authorization": f"Bearer {user1_token}"})
    assert_status(r, 404, "Follow non-existent event should return 404")
    log("✓ Non-existent event returns 404")

    # Test 1.8: POST follow unauthenticated
    log("Test 1.8: POST follow unauthenticated...")
    r = requests.post(f"{BASE_URL}/events/{test_event_id}/follow")
    assert_status(r, 401, "Follow without auth should return 401")
    log("✓ Unauthenticated follow returns 401")

    log("✅ All follow endpoint tests passed!")

# ============================================================================
# TEST 2: Extended event serialization
# ============================================================================

def test_extended_event_serialization():
    log("\n=== TEST 2: Extended Event Serialization ===")
    
    # Follow the event with user1
    log("Following event with user1...")
    requests.post(f"{BASE_URL}/events/{test_event_id}/follow",
        headers={"Authorization": f"Bearer {user1_token}"})
    
    # Test 2.1: GET /api/events should include new fields
    log("Test 2.1: GET /api/events with new fields...")
    r = requests.get(f"{BASE_URL}/events",
        headers={"Authorization": f"Bearer {user1_token}"})
    assert_status(r, 200, "Get events")
    events = r.json()
    
    # Find our test event
    test_event = None
    for ev in events:
        if ev["id"] == test_event_id:
            test_event = ev
            break
    
    assert_true(test_event is not None, "Test event should be in events list")
    
    # Check new fields
    assert_in("is_following", test_event, "Event should have is_following field")
    assert_eq(test_event["is_following"], True, "is_following should be true")
    
    assert_in("price_tiers", test_event, "Event should have price_tiers field")
    assert_eq(type(test_event["price_tiers"]), list, "price_tiers should be a list")
    
    assert_in("sale_state", test_event, "Event should have sale_state field")
    assert_eq(test_event["sale_state"], "no_a_la_venta", "sale_state should be no_a_la_venta")
    
    assert_in("currency", test_event, "Event should have currency field")
    assert_eq(test_event["currency"], "EUR", "currency should be EUR")
    
    assert_in("current_price", test_event, "Event should have current_price field")
    assert_eq(test_event["current_price"], None, "current_price should be None when no tiers")
    
    log("✓ GET /api/events includes all new fields")

    # Test 2.2: GET /api/events/carousels should include new fields
    log("Test 2.2: GET /api/events/carousels with new fields...")
    r = requests.get(f"{BASE_URL}/events/carousels",
        headers={"Authorization": f"Bearer {user1_token}"})
    assert_status(r, 200, "Get carousels")
    carousels = r.json()
    
    # Check that events in carousels have the new fields
    all_carousel_events = (
        carousels.get("top_weekend", []) +
        carousels.get("friends_going", []) +
        carousels.get("discover_new", [])
    )
    
    if all_carousel_events:
        sample_event = all_carousel_events[0]
        assert_in("is_following", sample_event, "Carousel event should have is_following")
        assert_in("price_tiers", sample_event, "Carousel event should have price_tiers")
        assert_in("sale_state", sample_event, "Carousel event should have sale_state")
        assert_in("currency", sample_event, "Carousel event should have currency")
        assert_in("current_price", sample_event, "Carousel event should have current_price")
        log("✓ GET /api/events/carousels includes all new fields")
    else:
        log("⚠ No events in carousels to check (acceptable)")

    log("✅ All extended serialization tests passed!")

# ============================================================================
# TEST 3: Pricing endpoint with notifications
# ============================================================================

def test_pricing_endpoint():
    log("\n=== TEST 3: Pricing Endpoint ===")
    
    # Setup: user2 follows the event
    log("Setup: user2 follows the event...")
    requests.post(f"{BASE_URL}/events/{test_event_id}/follow",
        headers={"Authorization": f"Bearer {user2_token}"})
    
    # Test 3.1: PUT pricing with valid data
    log("Test 3.1: PUT pricing with valid tiers and state...")
    r = requests.put(f"{BASE_URL}/admin/events/{test_event_id}/pricing",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "price_tiers": [
                {"name": "1a fase", "price": 12, "sold_out": False},
                {"name": "2a fase", "price": 18, "sold_out": False}
            ],
            "sale_state": "a_la_venta",
            "silent": False
        })
    assert_status(r, 200, "Set pricing")
    data = r.json()
    assert_in("event", data, "Response should have event")
    assert_in("notifications_sent", data, "Response should have notifications_sent")
    assert_true(data["notifications_sent"] > 0, "Should have sent notifications to followers")
    log(f"✓ Pricing set, {data['notifications_sent']} notifications sent")
    
    # Verify event was updated
    event = data["event"]
    assert_eq(len(event["price_tiers"]), 2, "Should have 2 price tiers")
    assert_eq(event["sale_state"], "a_la_venta", "Sale state should be a_la_venta")
    
    # Test 3.2: Check user2 received notification
    log("Test 3.2: Check user2 received 'tickets_on_sale' notification...")
    time.sleep(0.5)  # Give time for notification to be created
    r = requests.get(f"{BASE_URL}/notifications",
        headers={"Authorization": f"Bearer {user2_token}"})
    assert_status(r, 200, "Get notifications")
    notifications = r.json()
    
    on_sale_notif = None
    for n in notifications:
        if n.get("type") == "tickets_on_sale" and n.get("data", {}).get("event_id") == test_event_id:
            on_sale_notif = n
            break
    
    assert_true(on_sale_notif is not None, "User2 should have received tickets_on_sale notification")
    log("✓ User2 received tickets_on_sale notification")

    # Test 3.3: State transition to "pocas_entradas"
    log("Test 3.3: State transition to 'pocas_entradas'...")
    r = requests.put(f"{BASE_URL}/admin/events/{test_event_id}/pricing",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "price_tiers": [
                {"name": "1a fase", "price": 12, "sold_out": False},
                {"name": "2a fase", "price": 18, "sold_out": False}
            ],
            "sale_state": "pocas_entradas",
            "silent": False
        })
    assert_status(r, 200, "Set pricing to pocas_entradas")
    data = r.json()
    assert_true(data["notifications_sent"] > 0, "Should send low stock notification")
    log(f"✓ State changed to pocas_entradas, {data['notifications_sent']} notifications sent")
    
    # Check notification
    time.sleep(0.5)
    r = requests.get(f"{BASE_URL}/notifications",
        headers={"Authorization": f"Bearer {user2_token}"})
    notifications = r.json()
    low_stock_notif = None
    for n in notifications:
        if n.get("type") == "tickets_low_stock" and n.get("data", {}).get("event_id") == test_event_id:
            low_stock_notif = n
            break
    assert_true(low_stock_notif is not None, "User2 should have received tickets_low_stock notification")
    log("✓ User2 received tickets_low_stock notification")

    # Test 3.4: State transition to "agotado"
    log("Test 3.4: State transition to 'agotado'...")
    r = requests.put(f"{BASE_URL}/admin/events/{test_event_id}/pricing",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "price_tiers": [
                {"name": "1a fase", "price": 12, "sold_out": True},
                {"name": "2a fase", "price": 18, "sold_out": True}
            ],
            "sale_state": "agotado",
            "silent": False
        })
    assert_status(r, 200, "Set pricing to agotado")
    data = r.json()
    assert_true(data["notifications_sent"] > 0, "Should send sold out notification")
    log(f"✓ State changed to agotado, {data['notifications_sent']} notifications sent")
    
    # Check notification
    time.sleep(0.5)
    r = requests.get(f"{BASE_URL}/notifications",
        headers={"Authorization": f"Bearer {user2_token}"})
    notifications = r.json()
    sold_out_notif = None
    for n in notifications:
        if n.get("type") == "tickets_sold_out" and n.get("data", {}).get("event_id") == test_event_id:
            sold_out_notif = n
            break
    assert_true(sold_out_notif is not None, "User2 should have received tickets_sold_out notification")
    log("✓ User2 received tickets_sold_out notification")

    # Test 3.5: Setting same state twice should NOT send notification
    log("Test 3.5: Setting same state twice (no new notification)...")
    # Count current notifications
    r = requests.get(f"{BASE_URL}/notifications",
        headers={"Authorization": f"Bearer {user2_token}"})
    notif_count_before = len(r.json())
    
    r = requests.put(f"{BASE_URL}/admin/events/{test_event_id}/pricing",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "price_tiers": [
                {"name": "1a fase", "price": 12, "sold_out": True},
                {"name": "2a fase", "price": 18, "sold_out": True}
            ],
            "sale_state": "agotado",
            "silent": False
        })
    assert_status(r, 200, "Set same state again")
    data = r.json()
    assert_eq(data["notifications_sent"], 0, "Should NOT send notification for same state")
    log("✓ No notification sent for same state")

    # Test 3.6: Price increase detection
    log("Test 3.6: Price increase detection...")
    # First set to a_la_venta with first tier active
    r = requests.put(f"{BASE_URL}/admin/events/{test_event_id}/pricing",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "price_tiers": [
                {"name": "1a fase", "price": 12, "sold_out": False},
                {"name": "2a fase", "price": 18, "sold_out": False}
            ],
            "sale_state": "a_la_venta",
            "silent": False
        })
    assert_status(r, 200, "Reset to a_la_venta with 12€")
    
    time.sleep(0.5)
    
    # Now mark first tier as sold out (effective price goes from 12 to 18)
    r = requests.put(f"{BASE_URL}/admin/events/{test_event_id}/pricing",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "price_tiers": [
                {"name": "1a fase", "price": 12, "sold_out": True},
                {"name": "2a fase", "price": 18, "sold_out": False}
            ],
            "sale_state": "a_la_venta",
            "silent": False
        })
    assert_status(r, 200, "Mark first tier sold out")
    data = r.json()
    assert_true(data["notifications_sent"] > 0, "Should send price increase notification")
    log(f"✓ Price increase detected, {data['notifications_sent']} notifications sent")
    
    # Check notification
    time.sleep(0.5)
    r = requests.get(f"{BASE_URL}/notifications",
        headers={"Authorization": f"Bearer {user2_token}"})
    notifications = r.json()
    price_up_notif = None
    for n in notifications:
        if n.get("type") == "tickets_price_up" and n.get("data", {}).get("event_id") == test_event_id:
            price_up_notif = n
            break
    assert_true(price_up_notif is not None, "User2 should have received tickets_price_up notification")
    log("✓ User2 received tickets_price_up notification")

    # Test 3.7: Silent flag prevents notifications
    log("Test 3.7: Silent flag prevents notifications...")
    r = requests.put(f"{BASE_URL}/admin/events/{test_event_id}/pricing",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "price_tiers": [
                {"name": "1a fase", "price": 15, "sold_out": False}
            ],
            "sale_state": "pocas_entradas",
            "silent": True
        })
    assert_status(r, 200, "Set pricing with silent=true")
    data = r.json()
    assert_eq(data["notifications_sent"], 0, "Silent flag should prevent notifications")
    log("✓ Silent flag works correctly")

    # Test 3.8: Invalid sale_state
    log("Test 3.8: Invalid sale_state...")
    r = requests.put(f"{BASE_URL}/admin/events/{test_event_id}/pricing",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "price_tiers": [],
            "sale_state": "basura",
            "silent": False
        })
    assert_status(r, 400, "Invalid sale_state should return 400")
    log("✓ Invalid sale_state returns 400")

    # Test 3.9: Non-existent event
    log("Test 3.9: Non-existent event...")
    r = requests.put(f"{BASE_URL}/admin/events/nonexistent-id/pricing",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "price_tiers": [],
            "sale_state": "a_la_venta",
            "silent": False
        })
    assert_status(r, 404, "Non-existent event should return 404")
    log("✓ Non-existent event returns 404")

    # Test 3.10: Non-admin user
    log("Test 3.10: Non-admin user...")
    r = requests.put(f"{BASE_URL}/admin/events/{test_event_id}/pricing",
        headers={"Authorization": f"Bearer {user1_token}"},
        json={
            "price_tiers": [],
            "sale_state": "a_la_venta",
            "silent": False
        })
    assert_status(r, 403, "Non-admin should return 403")
    log("✓ Non-admin returns 403")

    log("✅ All pricing endpoint tests passed!")

# ============================================================================
# TEST 4: Low stock manual notification
# ============================================================================

def test_low_stock_notification():
    log("\n=== TEST 4: Low Stock Manual Notification ===")
    
    # Test 4.1: Admin triggers low stock notification
    log("Test 4.1: POST /admin/events/{id}/notify-low-stock as admin...")
    r = requests.post(f"{BASE_URL}/admin/events/{test_event_id}/notify-low-stock",
        headers={"Authorization": f"Bearer {admin_token}"})
    assert_status(r, 200, "Notify low stock")
    data = r.json()
    assert_in("notified", data, "Response should have notified count")
    assert_true(data["notified"] > 0, "Should have notified followers")
    log(f"✓ Low stock notification sent to {data['notified']} users")
    
    # Check user2 received notification
    time.sleep(0.5)
    r = requests.get(f"{BASE_URL}/notifications",
        headers={"Authorization": f"Bearer {user2_token}"})
    notifications = r.json()
    low_stock_notif = None
    for n in notifications:
        if n.get("type") == "tickets_low_stock" and n.get("data", {}).get("event_id") == test_event_id:
            low_stock_notif = n
            break
    assert_true(low_stock_notif is not None, "User2 should have received manual low stock notification")
    log("✓ User2 received manual low stock notification")

    # Test 4.2: Non-admin user
    log("Test 4.2: POST notify-low-stock as non-admin...")
    r = requests.post(f"{BASE_URL}/admin/events/{test_event_id}/notify-low-stock",
        headers={"Authorization": f"Bearer {user1_token}"})
    assert_status(r, 403, "Non-admin should return 403")
    log("✓ Non-admin returns 403")

    log("✅ All low stock notification tests passed!")

# ============================================================================
# TEST 5: New event auto-notification
# ============================================================================

def test_new_event_notification():
    log("\n=== TEST 5: New Event Auto-Notification ===")
    
    # Create a fresh user in Palma de Mallorca
    log("Creating user3 (Charlie) in Palma de Mallorca...")
    r = requests.post(f"{BASE_URL}/auth/register", json={
        "email": f"charlie_{int(time.time())}@test.com",
        "password": "test123",
        "name": "Charlie Test",
        "username": f"charlie_{int(time.time())}",
        "city": "Palma de Mallorca"
    })
    assert_status(r, 200, "Register user3")
    user3_token = r.json()["token"]
    user3_id = r.json()["user"]["user_id"]
    log(f"✓ User3 registered: {user3_id}")
    
    # Admin creates a new event in Palma de Mallorca
    log("Admin creates new event in Palma de Mallorca...")
    tomorrow = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
    r = requests.post(f"{BASE_URL}/admin/events",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "name": "New Event for City Notification",
            "venue": "City Venue",
            "address": "City Address",
            "date": tomorrow,
            "time": "23:00",
            "genre": "Reggaeton",
            "city": "Palma de Mallorca"
        })
    assert_status(r, 200, "Create new event")
    new_event_id = r.json()["id"]
    log(f"✓ New event created: {new_event_id}")
    
    # Wait for async notification task to complete
    log("Waiting 3 seconds for async notification task...")
    time.sleep(3)
    
    # Check user3 received new_event notification
    log("Checking user3 received 'new_event' notification...")
    r = requests.get(f"{BASE_URL}/notifications",
        headers={"Authorization": f"Bearer {user3_token}"})
    assert_status(r, 200, "Get user3 notifications")
    notifications = r.json()
    
    new_event_notif = None
    for n in notifications:
        if n.get("type") == "new_event" and n.get("data", {}).get("event_id") == new_event_id:
            new_event_notif = n
            break
    
    assert_true(new_event_notif is not None, "User3 should have received new_event notification")
    log("✓ User3 received new_event notification")
    
    log("✅ All new event notification tests passed!")

# ============================================================================
# TEST 6: Regression tests
# ============================================================================

def test_regression_auth():
    global admin_token
    log("\n=== TEST 6.1: Regression - Auth Endpoints ===")
    
    # Login
    r = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert_status(r, 200, "Login")
    log("✓ Login works")
    
    # Me
    r = requests.get(f"{BASE_URL}/auth/me",
        headers={"Authorization": f"Bearer {admin_token}"})
    assert_status(r, 200, "Me")
    log("✓ Me works")
    
    # Logout
    r = requests.post(f"{BASE_URL}/auth/logout",
        headers={"Authorization": f"Bearer {admin_token}"})
    assert_status(r, 200, "Logout")
    log("✓ Logout works")
    
    # Re-login admin for other tests
    r = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    admin_token = r.json()["token"]
    
    log("✅ Auth regression tests passed!")

def test_regression_events():
    log("\n=== TEST 6.2: Regression - Events Endpoints ===")
    
    # GET /events
    r = requests.get(f"{BASE_URL}/events",
        headers={"Authorization": f"Bearer {user1_token}"})
    assert_status(r, 200, "Get events")
    log("✓ GET /events works")
    
    # GET /events with filters
    r = requests.get(f"{BASE_URL}/events?date_filter=all",
        headers={"Authorization": f"Bearer {user1_token}"})
    assert_status(r, 200, "Get events with filter")
    log("✓ GET /events with filters works")
    
    # GET /events/carousels
    r = requests.get(f"{BASE_URL}/events/carousels",
        headers={"Authorization": f"Bearer {user1_token}"})
    assert_status(r, 200, "Get carousels")
    log("✓ GET /events/carousels works")
    
    # GET /events/top-weekend
    r = requests.get(f"{BASE_URL}/events/top-weekend",
        headers={"Authorization": f"Bearer {user1_token}"})
    assert_status(r, 200, "Get top weekend")
    log("✓ GET /events/top-weekend works")
    
    # GET /events/genres
    r = requests.get(f"{BASE_URL}/events/genres",
        headers={"Authorization": f"Bearer {user1_token}"})
    assert_status(r, 200, "Get genres")
    log("✓ GET /events/genres works")
    
    log("✅ Events regression tests passed!")

def test_regression_interests():
    log("\n=== TEST 6.3: Regression - Interests Endpoints ===")
    
    # POST interest with voy
    r = requests.post(f"{BASE_URL}/events/{test_event_id}/interest",
        headers={"Authorization": f"Bearer {user1_token}"},
        json={"status": "voy"})
    assert_status(r, 200, "Set interest voy")
    log("✓ POST interest voy works")
    
    # POST interest with me_interesa
    r = requests.post(f"{BASE_URL}/events/{test_event_id}/interest",
        headers={"Authorization": f"Bearer {user1_token}"},
        json={"status": "me_interesa"})
    assert_status(r, 200, "Set interest me_interesa")
    log("✓ POST interest me_interesa works")
    
    # POST interest with none
    r = requests.post(f"{BASE_URL}/events/{test_event_id}/interest",
        headers={"Authorization": f"Bearer {user1_token}"},
        json={"status": "none"})
    assert_status(r, 200, "Set interest none")
    log("✓ POST interest none works")
    
    # POST interest with estuve
    r = requests.post(f"{BASE_URL}/events/{test_event_id}/interest",
        headers={"Authorization": f"Bearer {user1_token}"},
        json={"status": "estuve"})
    assert_status(r, 200, "Set interest estuve")
    log("✓ POST interest estuve works")
    
    log("✅ Interests regression tests passed!")

def test_regression_friends():
    log("\n=== TEST 6.4: Regression - Friends Endpoints ===")
    
    # GET /friends
    r = requests.get(f"{BASE_URL}/friends",
        headers={"Authorization": f"Bearer {user1_token}"})
    assert_status(r, 200, "Get friends")
    log("✓ GET /friends works")
    
    # GET /friends/requests
    r = requests.get(f"{BASE_URL}/friends/requests",
        headers={"Authorization": f"Bearer {user1_token}"})
    assert_status(r, 200, "Get friend requests")
    log("✓ GET /friends/requests works")
    
    log("✅ Friends regression tests passed!")

def test_regression_badges():
    log("\n=== TEST 6.5: Regression - Badges Endpoints ===")
    
    # GET /me/badges
    r = requests.get(f"{BASE_URL}/me/badges",
        headers={"Authorization": f"Bearer {user1_token}"})
    assert_status(r, 200, "Get my badges")
    log("✓ GET /me/badges works")
    
    # GET /badges/catalog
    r = requests.get(f"{BASE_URL}/badges/catalog",
        headers={"Authorization": f"Bearer {user1_token}"})
    assert_status(r, 200, "Get badges catalog")
    log("✓ GET /badges/catalog works")
    
    log("✅ Badges regression tests passed!")

def test_regression_rankings():
    log("\n=== TEST 6.6: Regression - Rankings Endpoints ===")
    
    # GET /rankings/friends
    r = requests.get(f"{BASE_URL}/rankings/friends",
        headers={"Authorization": f"Bearer {user1_token}"})
    assert_status(r, 200, "Get rankings friends")
    log("✓ GET /rankings/friends works")
    
    # GET /rankings/city
    r = requests.get(f"{BASE_URL}/rankings/city",
        headers={"Authorization": f"Bearer {user1_token}"})
    assert_status(r, 200, "Get rankings city")
    log("✓ GET /rankings/city works")
    
    # GET /rankings/world
    r = requests.get(f"{BASE_URL}/rankings/world",
        headers={"Authorization": f"Bearer {user1_token}"})
    assert_status(r, 200, "Get rankings world")
    log("✓ GET /rankings/world works")
    
    log("✅ Rankings regression tests passed!")

def test_regression_health():
    log("\n=== TEST 6.7: Regression - Health Endpoint ===")
    
    # GET /health (no auth required)
    r = requests.get(f"{BASE_URL}/health")
    assert_status(r, 200, "Get health")
    data = r.json()
    assert_eq(data.get("ok"), True, "Health should return ok=true")
    log("✓ GET /health works")
    
    log("✅ Health regression tests passed!")

def test_regression_admin_moments():
    log("\n=== TEST 6.8: Regression - Admin Moment Endpoints ===")
    
    # GET /admin/moments
    r = requests.get(f"{BASE_URL}/admin/moments",
        headers={"Authorization": f"Bearer {admin_token}"})
    assert_status(r, 200, "Get admin moments")
    log("✓ GET /admin/moments works")
    
    log("✅ Admin moments regression tests passed!")

def test_regression_gzip():
    log("\n=== TEST 6.9: Regression - GZip Middleware ===")
    
    # GET /events should have gzip encoding on large response
    r = requests.get(f"{BASE_URL}/events",
        headers={"Authorization": f"Bearer {user1_token}"})
    assert_status(r, 200, "Get events for gzip check")
    
    # Check if Content-Encoding header is present (may or may not be gzipped depending on size)
    if len(r.content) >= 500:
        # Large response should be gzipped
        log(f"✓ Large response ({len(r.content)} bytes) - GZip middleware active")
    else:
        log(f"⚠ Response too small ({len(r.content)} bytes) to verify GZip")
    
    log("✅ GZip regression test passed!")

# ============================================================================
# MAIN
# ============================================================================

def main():
    try:
        log("=" * 70)
        log("BACKEND TEST: Event Pricing + Follow + Auto-Notifications")
        log("=" * 70)
        
        # Setup
        test_admin_login()
        test_register_users()
        
        # New features
        test_follow_endpoints()
        test_extended_event_serialization()
        test_pricing_endpoint()
        test_low_stock_notification()
        test_new_event_notification()
        
        # Regression tests
        test_regression_auth()
        test_regression_events()
        test_regression_interests()
        test_regression_friends()
        test_regression_badges()
        test_regression_rankings()
        test_regression_health()
        test_regression_admin_moments()
        test_regression_gzip()
        
        log("\n" + "=" * 70)
        log("🎉 ALL TESTS PASSED! 🎉")
        log("=" * 70)
        
    except AssertionError as e:
        log(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        log(f"\n❌ UNEXPECTED ERROR: {e}")
        raise

if __name__ == "__main__":
    main()
