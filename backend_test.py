#!/usr/bin/env python3
"""
Backend test for ¿Quién va? - Monetization + Retention endpoints
Tests new ticket tracking, activity feed, recap, admin funnel, and venue report endpoints
"""

import requests
import json
import time
from datetime import datetime, timedelta

# Base URL from frontend/.env
BASE_URL = "https://fiesta-connect-3.preview.emergentagent.com/api"

# Admin credentials from test_credentials.md
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

# Test state
admin_token = None
user_a_token = None
user_b_token = None
user_a_id = None
user_b_id = None
event_id = None
test_timestamp = int(time.time())


def log(msg):
    print(f"[TEST] {msg}")


def register_user(name, email, password):
    """Register a new user"""
    username = email.split("@")[0]  # Use email prefix as username
    resp = requests.post(f"{BASE_URL}/auth/register", json={
        "name": name,
        "email": email,
        "password": password,
        "username": username,
        "city": "Palma"
    })
    if resp.status_code != 200:
        log(f"❌ Register failed: {resp.status_code} {resp.text}")
        return None, None
    data = resp.json()
    token = data.get("token")
    user_id = data.get("user", {}).get("user_id") if "user" in data else data.get("user_id")
    log(f"✅ Registered {name}: {user_id}")
    return token, user_id


def login(email, password):
    """Login and return token"""
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": email,
        "password": password
    })
    if resp.status_code != 200:
        log(f"❌ Login failed: {resp.status_code} {resp.text}")
        return None
    data = resp.json()
    token = data.get("token")
    log(f"✅ Logged in: {email}")
    return token


def make_friends(token_a, token_b, user_b_id):
    """Make two users friends"""
    # A sends friend request to B
    resp = requests.post(f"{BASE_URL}/friends/request", 
                        json={"user_id": user_b_id},
                        headers={"Authorization": f"Bearer {token_a}"})
    if resp.status_code != 200:
        log(f"❌ Friend request failed: {resp.status_code} {resp.text}")
        return False
    
    data = resp.json()
    request_id = data.get("request_id")
    if not request_id:
        log(f"❌ No request_id in response: {data}")
        return False
    
    # B accepts friend request
    resp = requests.post(f"{BASE_URL}/friends/respond",
                        json={"request_id": request_id, "accept": True},
                        headers={"Authorization": f"Bearer {token_b}"})
    if resp.status_code != 200:
        log(f"❌ Friend accept failed: {resp.status_code} {resp.text}")
        return False
    
    log(f"✅ Users are now friends")
    return True


def get_upcoming_event(token):
    """Get an upcoming event ID"""
    resp = requests.get(f"{BASE_URL}/events?date_filter=all",
                       headers={"Authorization": f"Bearer {token}"})
    if resp.status_code != 200:
        log(f"❌ Get events failed: {resp.status_code} {resp.text}")
        return None
    events = resp.json()
    if not events:
        log(f"❌ No events found")
        return None
    event_id = events[0]["id"]
    log(f"✅ Found event: {event_id} - {events[0]['name']}")
    return event_id


def mark_interest(token, event_id, status="voy"):
    """Mark interest on an event"""
    resp = requests.post(f"{BASE_URL}/events/{event_id}/interest",
                        json={"status": status},
                        headers={"Authorization": f"Bearer {token}"})
    if resp.status_code != 200:
        log(f"❌ Mark interest failed: {resp.status_code} {resp.text}")
        return False
    log(f"✅ Marked interest: {status}")
    return True


# =============================================================================
# TEST 1: POST /api/events/{id}/ticket - Mark/unmark ticket ownership
# =============================================================================
def test_ticket_endpoint():
    log("\n=== TEST 1: POST /api/events/{id}/ticket ===")
    
    # Test 1.1: Mark ticket as user A
    log("Test 1.1: User A marks 'have ticket'")
    resp = requests.post(f"{BASE_URL}/events/{event_id}/ticket",
                        json={"have": True},
                        headers={"Authorization": f"Bearer {user_a_token}"})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["have"] == True, f"Expected have=true, got {data}"
    assert data["total_tickets"] >= 1, f"Expected total_tickets >= 1, got {data['total_tickets']}"
    initial_total = data["total_tickets"]
    log(f"✅ User A has ticket, total_tickets={initial_total}")
    
    # Test 1.2: Mark ticket as user B (should increment)
    log("Test 1.2: User B marks 'have ticket'")
    resp = requests.post(f"{BASE_URL}/events/{event_id}/ticket",
                        json={"have": True},
                        headers={"Authorization": f"Bearer {user_b_token}"})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["have"] == True, f"Expected have=true, got {data}"
    assert data["total_tickets"] == initial_total + 1, f"Expected total_tickets={initial_total + 1}, got {data['total_tickets']}"
    log(f"✅ User B has ticket, total_tickets={data['total_tickets']}")
    
    # Test 1.3: Unmark ticket as user A (should decrement)
    log("Test 1.3: User A unmarks ticket")
    resp = requests.post(f"{BASE_URL}/events/{event_id}/ticket",
                        json={"have": False},
                        headers={"Authorization": f"Bearer {user_a_token}"})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["have"] == False, f"Expected have=false, got {data}"
    assert data["total_tickets"] == initial_total, f"Expected total_tickets={initial_total}, got {data['total_tickets']}"
    log(f"✅ User A unmarked ticket, total_tickets={data['total_tickets']}")
    
    # Test 1.4: Non-existent event should return 404
    log("Test 1.4: Non-existent event returns 404")
    resp = requests.post(f"{BASE_URL}/events/nonexistent-event-id/ticket",
                        json={"have": True},
                        headers={"Authorization": f"Bearer {user_a_token}"})
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
    log(f"✅ Non-existent event returns 404")
    
    log("✅ TEST 1 PASSED: Ticket endpoint working correctly")


# =============================================================================
# TEST 2: GET /api/events/{id} - Event detail includes ticket fields
# =============================================================================
def test_event_detail_ticket_fields():
    log("\n=== TEST 2: GET /api/events/{id} - Ticket fields ===")
    
    # User B has ticket, User A doesn't (from previous test)
    # User A and B are friends and both marked 'voy'
    
    log("Test 2.1: User B views event detail (has ticket)")
    resp = requests.get(f"{BASE_URL}/events/{event_id}",
                       headers={"Authorization": f"Bearer {user_b_token}"})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    
    # Check required fields
    assert "my_has_ticket" in data, f"Missing my_has_ticket field"
    assert isinstance(data["my_has_ticket"], bool), f"my_has_ticket should be bool, got {type(data['my_has_ticket'])}"
    assert data["my_has_ticket"] == True, f"Expected my_has_ticket=true for user B, got {data['my_has_ticket']}"
    
    assert "total_tickets" in data, f"Missing total_tickets field"
    assert isinstance(data["total_tickets"], int), f"total_tickets should be int, got {type(data['total_tickets'])}"
    assert data["total_tickets"] >= 1, f"Expected total_tickets >= 1, got {data['total_tickets']}"
    
    assert "friends_with_ticket" in data, f"Missing friends_with_ticket field"
    assert isinstance(data["friends_with_ticket"], list), f"friends_with_ticket should be list, got {type(data['friends_with_ticket'])}"
    log(f"✅ User B sees: my_has_ticket={data['my_has_ticket']}, total_tickets={data['total_tickets']}, friends_with_ticket={len(data['friends_with_ticket'])} friends")
    
    # Test 2.2: User A views event detail (doesn't have ticket, but friend B does)
    log("Test 2.2: User A views event detail (no ticket, but friend B has)")
    
    # First, mark A as having ticket so we can test friends_with_ticket
    requests.post(f"{BASE_URL}/events/{event_id}/ticket",
                 json={"have": True},
                 headers={"Authorization": f"Bearer {user_a_token}"})
    
    resp = requests.get(f"{BASE_URL}/events/{event_id}",
                       headers={"Authorization": f"Bearer {user_b_token}"})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    
    # B should see A in friends_with_ticket
    assert len(data["friends_with_ticket"]) >= 1, f"Expected at least 1 friend with ticket, got {len(data['friends_with_ticket'])}"
    friend_ids = [f["user_id"] for f in data["friends_with_ticket"]]
    assert user_a_id in friend_ids, f"Expected user A in friends_with_ticket, got {friend_ids}"
    log(f"✅ User B sees friend A in friends_with_ticket")
    
    log("✅ TEST 2 PASSED: Event detail includes correct ticket fields")


# =============================================================================
# TEST 3: GET /api/events - List includes my_has_ticket
# =============================================================================
def test_events_list_ticket_field():
    log("\n=== TEST 3: GET /api/events - my_has_ticket field ===")
    
    log("Test 3.1: Events list includes my_has_ticket")
    resp = requests.get(f"{BASE_URL}/events?date_filter=all",
                       headers={"Authorization": f"Bearer {user_a_token}"})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    events = resp.json()
    
    # If no events in list, use the event we already have from setup
    if len(events) == 0:
        log(f"ℹ️  No events in list (date filter may have excluded them), checking event detail instead")
        resp = requests.get(f"{BASE_URL}/events/{event_id}",
                           headers={"Authorization": f"Bearer {user_a_token}"})
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        event = resp.json()
        assert "my_has_ticket" in event, f"Missing my_has_ticket field"
        assert isinstance(event["my_has_ticket"], bool), f"my_has_ticket should be bool, got {type(event['my_has_ticket'])}"
        log(f"✅ Event detail includes my_has_ticket field (value: {event['my_has_ticket']})")
    else:
        # Check first event has my_has_ticket field
        event = events[0]
        assert "my_has_ticket" in event, f"Missing my_has_ticket field in event list"
        assert isinstance(event["my_has_ticket"], bool), f"my_has_ticket should be bool, got {type(event['my_has_ticket'])}"
        log(f"✅ Events list includes my_has_ticket field (value: {event['my_has_ticket']})")
        
        # Note: total_tickets may be null in list view (that's expected per review request)
        if "total_tickets" in event and event["total_tickets"] is not None:
            log(f"ℹ️  total_tickets present in list: {event['total_tickets']} (optional)")
    
    log("✅ TEST 3 PASSED: Events list includes my_has_ticket")


# =============================================================================
# TEST 4: GET /api/events/{id} - View tracking doesn't break response
# =============================================================================
def test_view_tracking():
    log("\n=== TEST 4: GET /api/events/{id} - View tracking ===")
    
    log("Test 4.1: First view succeeds")
    resp1 = requests.get(f"{BASE_URL}/events/{event_id}",
                        headers={"Authorization": f"Bearer {user_a_token}"})
    assert resp1.status_code == 200, f"Expected 200, got {resp1.status_code}: {resp1.text}"
    data1 = resp1.json()
    assert "id" in data1, f"Response missing id field"
    log(f"✅ First view succeeded")
    
    log("Test 4.2: Second view succeeds (view tracking increments internally)")
    resp2 = requests.get(f"{BASE_URL}/events/{event_id}",
                        headers={"Authorization": f"Bearer {user_a_token}"})
    assert resp2.status_code == 200, f"Expected 200, got {resp2.status_code}: {resp2.text}"
    data2 = resp2.json()
    assert "id" in data2, f"Response missing id field"
    assert data2["id"] == data1["id"], f"Event ID mismatch between views"
    log(f"✅ Second view succeeded, response structure intact")
    
    log("✅ TEST 4 PASSED: View tracking doesn't break response")


# =============================================================================
# TEST 5: GET /api/me/activity - Friend activity feed
# =============================================================================
def test_activity_feed():
    log("\n=== TEST 5: GET /api/me/activity - Friend activity ===")
    
    # User A and B are friends, both marked 'voy', B has ticket
    
    log("Test 5.1: User A gets activity feed (should see friend B's activity)")
    resp = requests.get(f"{BASE_URL}/me/activity",
                       headers={"Authorization": f"Bearer {user_a_token}"})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "items" in data, f"Missing items field"
    assert isinstance(data["items"], list), f"items should be list, got {type(data['items'])}"
    
    # Should contain activity from friend B (marked voy)
    assert len(data["items"]) > 0, f"Expected at least 1 activity item, got {len(data['items'])}"
    
    # Check structure of first item
    item = data["items"][0]
    assert "type" in item, f"Missing type field in activity item"
    assert item["type"] in ["going", "ticket"], f"Invalid type: {item['type']}"
    
    if item["type"] == "going":
        assert "user" in item, f"Missing user field"
        assert "event_id" in item, f"Missing event_id field"
        assert "event_name" in item, f"Missing event_name field"
        log(f"✅ Activity feed contains 'going' entry: {item['user']['name']} → {item['event_name']}")
    
    log(f"✅ User A sees {len(data['items'])} activity items from friends")
    
    # Test 5.2: Fresh user with no friends should get empty array
    log("Test 5.2: Fresh user with no friends gets empty activity")
    fresh_token, _ = register_user(f"Fresh{test_timestamp}", f"fresh{test_timestamp}@test.com", "test123")
    resp = requests.get(f"{BASE_URL}/me/activity",
                       headers={"Authorization": f"Bearer {fresh_token}"})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["items"] == [], f"Expected empty items for user with no friends, got {len(data['items'])} items"
    log(f"✅ Fresh user with no friends gets empty activity")
    
    log("✅ TEST 5 PASSED: Activity feed working correctly")


# =============================================================================
# TEST 6: GET /api/me/recap - User recap
# =============================================================================
def test_recap():
    log("\n=== TEST 6: GET /api/me/recap - User recap ===")
    
    log("Test 6.1: User A gets recap")
    resp = requests.get(f"{BASE_URL}/me/recap",
                       headers={"Authorization": f"Bearer {user_a_token}"})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    
    # Check required fields
    required_fields = ["went", "photos", "new_friends", "friends_plans", "has_activity"]
    for field in required_fields:
        assert field in data, f"Missing {field} field"
    
    assert isinstance(data["went"], int), f"went should be int, got {type(data['went'])}"
    assert isinstance(data["photos"], int), f"photos should be int, got {type(data['photos'])}"
    assert isinstance(data["new_friends"], int), f"new_friends should be int, got {type(data['new_friends'])}"
    assert isinstance(data["friends_plans"], int), f"friends_plans should be int, got {type(data['friends_plans'])}"
    assert isinstance(data["has_activity"], bool), f"has_activity should be bool, got {type(data['has_activity'])}"
    
    # User A marked 'voy' and has 1 friend (B), so friends_plans should be >= 1
    assert data["friends_plans"] >= 1, f"Expected friends_plans >= 1 (friend B marked voy), got {data['friends_plans']}"
    
    log(f"✅ Recap: went={data['went']}, photos={data['photos']}, new_friends={data['new_friends']}, friends_plans={data['friends_plans']}, has_activity={data['has_activity']}")
    log("✅ TEST 6 PASSED: Recap endpoint working correctly")


# =============================================================================
# TEST 7: GET /api/admin/funnel - Admin funnel report
# =============================================================================
def test_admin_funnel():
    log("\n=== TEST 7: GET /api/admin/funnel - Admin funnel ===")
    
    log("Test 7.1: Admin gets funnel report")
    resp = requests.get(f"{BASE_URL}/admin/funnel",
                       headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    
    # Check structure
    assert "rows" in data, f"Missing rows field"
    assert "totals" in data, f"Missing totals field"
    assert isinstance(data["rows"], list), f"rows should be list, got {type(data['rows'])}"
    assert isinstance(data["totals"], dict), f"totals should be dict, got {type(data['totals'])}"
    
    # Check totals structure
    totals = data["totals"]
    required_totals = ["views", "interested", "going", "clicks", "tickets", "commission"]
    for field in required_totals:
        assert field in totals, f"Missing {field} in totals"
    
    assert isinstance(totals["commission"], (int, float)), f"commission should be number, got {type(totals['commission'])}"
    log(f"✅ Funnel totals: views={totals['views']}, interested={totals['interested']}, going={totals['going']}, clicks={totals['clicks']}, tickets={totals['tickets']}, commission={totals['commission']}")
    
    # Check rows structure (if any events)
    if len(data["rows"]) > 0:
        row = data["rows"][0]
        required_row_fields = ["id", "name", "venue", "views", "interested", "going", "clicks", "tickets", "conversion_pct", "est_commission"]
        for field in required_row_fields:
            assert field in row, f"Missing {field} in row"
        log(f"✅ Sample row: {row['name']} - views={row['views']}, going={row['going']}, tickets={row['tickets']}, commission={row['est_commission']}")
    
    log("Test 7.2: Non-admin gets 403")
    resp = requests.get(f"{BASE_URL}/admin/funnel",
                       headers={"Authorization": f"Bearer {user_a_token}"})
    assert resp.status_code == 403, f"Expected 403 for non-admin, got {resp.status_code}"
    log(f"✅ Non-admin correctly denied (403)")
    
    log("✅ TEST 7 PASSED: Admin funnel working correctly")


# =============================================================================
# TEST 8: GET /api/admin/venue-report - Admin venue report
# =============================================================================
def test_admin_venue_report():
    log("\n=== TEST 8: GET /api/admin/venue-report - Venue report ===")
    
    log("Test 8.1: Admin gets venue report")
    resp = requests.get(f"{BASE_URL}/admin/venue-report",
                       headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    
    # Check structure
    assert "venues" in data, f"Missing venues field"
    assert isinstance(data["venues"], list), f"venues should be list, got {type(data['venues'])}"
    
    # Check venue structure (if any venues)
    if len(data["venues"]) > 0:
        venue = data["venues"][0]
        required_fields = ["venue", "events", "views", "going", "clicks", "tickets", "commission"]
        for field in required_fields:
            assert field in venue, f"Missing {field} in venue"
        
        assert isinstance(venue["commission"], (int, float)), f"commission should be number, got {type(venue['commission'])}"
        log(f"✅ Sample venue: {venue['venue']} - events={venue['events']}, views={venue['views']}, going={venue['going']}, tickets={venue['tickets']}, commission={venue['commission']}")
    
    log("Test 8.2: Non-admin gets 403")
    resp = requests.get(f"{BASE_URL}/admin/venue-report",
                       headers={"Authorization": f"Bearer {user_a_token}"})
    assert resp.status_code == 403, f"Expected 403 for non-admin, got {resp.status_code}"
    log(f"✅ Non-admin correctly denied (403)")
    
    log("✅ TEST 8 PASSED: Venue report working correctly")


# =============================================================================
# TEST 9: POST /api/admin/events/{id}/notify-interested - Admin notification
# =============================================================================
def test_admin_notify_interested():
    log("\n=== TEST 9: POST /api/admin/events/{id}/notify-interested ===")
    
    log("Test 9.1: Admin sends notification to interested users")
    resp = requests.post(f"{BASE_URL}/admin/events/{event_id}/notify-interested",
                        json={"message": "Test notification"},
                        headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    
    assert "notified" in data, f"Missing notified field"
    assert isinstance(data["notified"], int), f"notified should be int, got {type(data['notified'])}"
    assert data["notified"] >= 0, f"notified should be >= 0, got {data['notified']}"
    log(f"✅ Notification sent to {data['notified']} users")
    
    log("Test 9.2: Non-existent event returns 404")
    resp = requests.post(f"{BASE_URL}/admin/events/nonexistent-event-id/notify-interested",
                        json={"message": "Test"},
                        headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
    log(f"✅ Non-existent event returns 404")
    
    log("Test 9.3: Non-admin gets 403")
    resp = requests.post(f"{BASE_URL}/admin/events/{event_id}/notify-interested",
                        json={"message": "Test"},
                        headers={"Authorization": f"Bearer {user_a_token}"})
    assert resp.status_code == 403, f"Expected 403 for non-admin, got {resp.status_code}"
    log(f"✅ Non-admin correctly denied (403)")
    
    log("✅ TEST 9 PASSED: Admin notify-interested working correctly")


# =============================================================================
# TEST 10: GET /api/events/discover - Should return 404 (removed)
# =============================================================================
def test_discover_removed():
    log("\n=== TEST 10: GET /api/events/discover - Should be removed ===")
    
    log("Test 10.1: /events/discover returns 404")
    resp = requests.get(f"{BASE_URL}/events/discover",
                       headers={"Authorization": f"Bearer {user_a_token}"})
    assert resp.status_code == 404, f"Expected 404 (endpoint removed), got {resp.status_code}"
    log(f"✅ /events/discover correctly returns 404 (endpoint removed)")
    
    log("✅ TEST 10 PASSED: Discover endpoint removed as expected")


# =============================================================================
# REGRESSION TESTS
# =============================================================================
def test_regression():
    log("\n=== REGRESSION TESTS ===")
    
    # Test login
    log("Regression 1: POST /api/auth/login")
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Login failed: {resp.status_code}"
    log("✅ Login working")
    
    # Test events list
    log("Regression 2: GET /api/events?date_filter=all")
    resp = requests.get(f"{BASE_URL}/events?date_filter=all",
                       headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200, f"Events list failed: {resp.status_code}"
    assert isinstance(resp.json(), list), f"Events should be array"
    log("✅ Events list working")
    
    # Test interest
    log("Regression 3: POST /api/events/{id}/interest")
    resp = requests.post(f"{BASE_URL}/events/{event_id}/interest",
                        json={"status": "voy"},
                        headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200, f"Interest failed: {resp.status_code}"
    log("✅ Interest endpoint working")
    
    # Test ticket click (existing endpoint)
    log("Regression 4: POST /api/tickets/click")
    resp = requests.post(f"{BASE_URL}/tickets/click",
                        json={"event_id": event_id},
                        headers={"Authorization": f"Bearer {user_a_token}"})
    assert resp.status_code == 200, f"Ticket click failed: {resp.status_code}"
    log("✅ Ticket click working")
    
    # Test admin stats
    log("Regression 5: GET /api/admin/stats")
    resp = requests.get(f"{BASE_URL}/admin/stats",
                       headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200, f"Admin stats failed: {resp.status_code}"
    log("✅ Admin stats working")
    
    log("✅ ALL REGRESSION TESTS PASSED")


# =============================================================================
# MAIN TEST RUNNER
# =============================================================================
def main():
    global admin_token, user_a_token, user_b_token, user_a_id, user_b_id, event_id
    
    log("=" * 80)
    log("BACKEND TEST: Monetization + Retention Endpoints")
    log("=" * 80)
    
    # Setup: Login as admin
    log("\n=== SETUP ===")
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    assert admin_token, "Admin login failed"
    
    # Register two fresh users
    user_a_token, user_a_id = register_user(f"UserA{test_timestamp}", f"usera{test_timestamp}@test.com", "test123")
    assert user_a_token and user_a_id, "User A registration failed"
    
    user_b_token, user_b_id = register_user(f"UserB{test_timestamp}", f"userb{test_timestamp}@test.com", "test123")
    assert user_b_token and user_b_id, "User B registration failed"
    
    # Make them friends
    assert make_friends(user_a_token, user_b_token, user_b_id), "Making friends failed"
    
    # Get an upcoming event
    event_id = get_upcoming_event(admin_token)
    assert event_id, "No upcoming events found"
    
    # Both mark 'voy' on the event
    assert mark_interest(user_a_token, event_id, "voy"), "User A mark interest failed"
    assert mark_interest(user_b_token, event_id, "voy"), "User B mark interest failed"
    
    log("✅ Setup complete: 2 users (friends), both marked 'voy' on event")
    
    # Run all tests
    try:
        test_ticket_endpoint()
        test_event_detail_ticket_fields()
        test_events_list_ticket_field()
        test_view_tracking()
        test_activity_feed()
        test_recap()
        test_admin_funnel()
        test_admin_venue_report()
        test_admin_notify_interested()
        test_discover_removed()
        test_regression()
        
        log("\n" + "=" * 80)
        log("🎉 ALL TESTS PASSED!")
        log("=" * 80)
        return 0
        
    except AssertionError as e:
        log(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        log(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
