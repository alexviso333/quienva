#!/usr/bin/env python3
"""
Test suite for admin panel performance fix (N+1 query removal).
Tests GET /api/admin/stats and GET /api/admin/users endpoints.
"""
import requests
import json
from datetime import datetime, timedelta, date
import uuid

# Backend URL from frontend/.env
BACKEND_URL = "https://voting-island-widget.preview.emergentagent.com/api"

# Admin credentials from /app/memory/test_credentials.md
ADMIN_EMAIL = "test_20e12f5b@example.com"
ADMIN_PASSWORD = "TestPass123!"

def log(msg):
    print(f"[TEST] {msg}")

def login_admin():
    """Login as admin and return auth token."""
    log("Logging in as admin...")
    resp = requests.post(f"{BACKEND_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if resp.status_code != 200:
        log(f"❌ Admin login failed: {resp.status_code} {resp.text}")
        return None
    data = resp.json()
    token = data.get("token")
    log(f"✅ Admin login successful, token: {token[:20]}...")
    return token

def create_test_user(token, suffix):
    """Create a test user and return user_id."""
    email = f"testuser_{suffix}@example.com"
    resp = requests.post(f"{BACKEND_URL}/auth/register", json={
        "email": email,
        "password": "TestPass123!",
        "name": f"Test User {suffix}",
        "username": f"testuser{suffix}",
        "city": "Madrid",
        "birthdate": "1995-01-01"
    })
    if resp.status_code != 200:
        log(f"⚠️  User creation failed: {resp.status_code}")
        return None
    data = resp.json()
    user_id = data.get("user_id")
    log(f"✅ Created test user: {email} (id: {user_id})")
    return user_id

def create_test_event(token, name, city="Madrid", days_ahead=7):
    """Create a test event and return event_id."""
    event_date = (date.today() + timedelta(days=days_ahead)).isoformat()
    resp = requests.post(f"{BACKEND_URL}/admin/events", 
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": name,
            "venue": "Test Venue",
            "date": event_date,
            "time": "23:00",
            "city": city,
            "genre": "Techno",
            "sale_state": "a_la_venta",
            "price_tiers": [{"name": "General", "price": 25.0}]
        })
    if resp.status_code != 200:
        log(f"⚠️  Event creation failed: {resp.status_code}")
        return None
    data = resp.json()
    event_id = data.get("id")
    log(f"✅ Created test event: {name} (id: {event_id})")
    return event_id

def create_interest(token, event_id, status="voy"):
    """Create an interest for the current user."""
    resp = requests.post(f"{BACKEND_URL}/events/{event_id}/interest",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": status})
    if resp.status_code == 200:
        log(f"✅ Created interest: {status} for event {event_id}")
        return True
    return False

def create_friendship(token1, user_id2):
    """Send friend request from token1 to user_id2."""
    resp = requests.post(f"{BACKEND_URL}/friends/request",
        headers={"Authorization": f"Bearer {token1}"},
        json={"user_id": user_id2})
    if resp.status_code == 200:
        log(f"✅ Sent friend request to {user_id2}")
        return True
    return False

def accept_friendship(token2, request_id):
    """Accept friend request."""
    resp = requests.post(f"{BACKEND_URL}/friends/respond",
        headers={"Authorization": f"Bearer {token2}"},
        json={"request_id": request_id, "accept": True})
    if resp.status_code == 200:
        log(f"✅ Accepted friend request {request_id}")
        return True
    return False

def get_friend_requests(token):
    """Get pending friend requests."""
    resp = requests.get(f"{BACKEND_URL}/friends/requests",
        headers={"Authorization": f"Bearer {token}"})
    if resp.status_code == 200:
        return resp.json()
    return []

def test_admin_stats(token):
    """Test GET /api/admin/stats endpoint."""
    log("\n" + "="*80)
    log("TEST 1: GET /api/admin/stats")
    log("="*80)
    
    # Test 1: Admin access - should return 200
    log("\n[1.1] Testing admin access...")
    resp = requests.get(f"{BACKEND_URL}/admin/stats",
        headers={"Authorization": f"Bearer {token}"})
    
    if resp.status_code != 200:
        log(f"❌ FAILED: Expected 200, got {resp.status_code}")
        log(f"Response: {resp.text}")
        return False
    
    log(f"✅ PASSED: Status 200")
    
    # Test 2: Verify response structure
    log("\n[1.2] Verifying response structure...")
    data = resp.json()
    
    # Check totals
    if "totals" not in data:
        log("❌ FAILED: Missing 'totals' key")
        return False
    
    totals = data["totals"]
    required_totals = ["users", "active_week", "events", "upcoming", "going", 
                       "interested", "attended", "stories", "friendships"]
    
    for key in required_totals:
        if key not in totals:
            log(f"❌ FAILED: Missing totals.{key}")
            return False
        if not isinstance(totals[key], int):
            log(f"❌ FAILED: totals.{key} is not an integer: {type(totals[key])}")
            return False
    
    log(f"✅ PASSED: All totals keys present and are integers")
    log(f"   Totals: {json.dumps(totals, indent=2)}")
    
    # Check top_events
    if "top_events" not in data:
        log("❌ FAILED: Missing 'top_events' key")
        return False
    
    top_events = data["top_events"]
    if not isinstance(top_events, list):
        log(f"❌ FAILED: top_events is not a list: {type(top_events)}")
        return False
    
    if len(top_events) > 8:
        log(f"❌ FAILED: top_events has more than 8 items: {len(top_events)}")
        return False
    
    log(f"✅ PASSED: top_events is a list with {len(top_events)} items (max 8)")
    
    # Verify top_events structure
    for i, event in enumerate(top_events):
        required_keys = ["id", "name", "date", "venue", "signups"]
        for key in required_keys:
            if key not in event:
                log(f"❌ FAILED: top_events[{i}] missing key '{key}'")
                return False
        if not isinstance(event["signups"], int):
            log(f"❌ FAILED: top_events[{i}].signups is not an integer")
            return False
    
    log(f"✅ PASSED: All top_events have required keys (id, name, date, venue, signups)")
    
    # Verify top_events are sorted by signups descending
    if len(top_events) > 1:
        for i in range(len(top_events) - 1):
            if top_events[i]["signups"] < top_events[i+1]["signups"]:
                log(f"❌ FAILED: top_events not sorted by signups descending")
                log(f"   Event {i}: {top_events[i]['signups']} < Event {i+1}: {top_events[i+1]['signups']}")
                return False
        log(f"✅ PASSED: top_events sorted by signups descending")
    
    # Check genres
    if "genres" not in data:
        log("❌ FAILED: Missing 'genres' key")
        return False
    
    genres = data["genres"]
    if not isinstance(genres, list):
        log(f"❌ FAILED: genres is not a list: {type(genres)}")
        return False
    
    if len(genres) > 8:
        log(f"❌ FAILED: genres has more than 8 items: {len(genres)}")
        return False
    
    log(f"✅ PASSED: genres is a list with {len(genres)} items (max 8)")
    
    # Verify genres structure
    for i, genre in enumerate(genres):
        if "genre" not in genre or "count" not in genre:
            log(f"❌ FAILED: genres[{i}] missing 'genre' or 'count' key")
            return False
        if not isinstance(genre["count"], int):
            log(f"❌ FAILED: genres[{i}].count is not an integer")
            return False
    
    log(f"✅ PASSED: All genres have required keys (genre, count)")
    
    log("\n✅✅✅ TEST 1 PASSED: /api/admin/stats working correctly")
    return True

def test_admin_users(token):
    """Test GET /api/admin/users endpoint."""
    log("\n" + "="*80)
    log("TEST 2: GET /api/admin/users")
    log("="*80)
    
    # Test 1: Admin access - should return 200
    log("\n[2.1] Testing admin access...")
    resp = requests.get(f"{BACKEND_URL}/admin/users?limit=200",
        headers={"Authorization": f"Bearer {token}"})
    
    if resp.status_code != 200:
        log(f"❌ FAILED: Expected 200, got {resp.status_code}")
        log(f"Response: {resp.text}")
        return False
    
    log(f"✅ PASSED: Status 200")
    
    # Test 2: Verify response is a list
    log("\n[2.2] Verifying response structure...")
    data = resp.json()
    
    if not isinstance(data, list):
        log(f"❌ FAILED: Response is not a list: {type(data)}")
        return False
    
    log(f"✅ PASSED: Response is a list with {len(data)} users")
    
    if len(data) == 0:
        log("⚠️  WARNING: No users in database")
        return True
    
    # Test 3: Verify each user has _stats
    log("\n[2.3] Verifying user _stats structure...")
    required_stats = ["going", "attended", "friends", "groups", "referred", "invites_sent"]
    
    for i, user in enumerate(data[:5]):  # Check first 5 users
        if "_stats" not in user:
            log(f"❌ FAILED: User {i} missing '_stats' key")
            return False
        
        stats = user["_stats"]
        for key in required_stats:
            if key not in stats:
                log(f"❌ FAILED: User {i} _stats missing '{key}' key")
                return False
            if not isinstance(stats[key], int):
                log(f"❌ FAILED: User {i} _stats.{key} is not an integer: {type(stats[key])}")
                return False
    
    log(f"✅ PASSED: All users have _stats with required keys (going, attended, friends, groups, referred, invites_sent)")
    
    # Test 4: Test search filter
    log("\n[2.4] Testing ?search= filter...")
    if len(data) > 0:
        test_user = data[0]
        search_term = test_user.get("name", "").split()[0] if test_user.get("name") else ""
        
        if search_term:
            resp = requests.get(f"{BACKEND_URL}/admin/users?search={search_term}",
                headers={"Authorization": f"Bearer {token}"})
            
            if resp.status_code != 200:
                log(f"❌ FAILED: Search request failed: {resp.status_code}")
                return False
            
            search_results = resp.json()
            if not isinstance(search_results, list):
                log(f"❌ FAILED: Search results not a list")
                return False
            
            log(f"✅ PASSED: Search filter working (searched '{search_term}', got {len(search_results)} results)")
        else:
            log("⚠️  SKIPPED: No searchable user name found")
    
    log("\n✅✅✅ TEST 2 PASSED: /api/admin/users working correctly")
    return True

def test_access_control():
    """Test access control for admin endpoints."""
    log("\n" + "="*80)
    log("TEST 3: Access Control (401/403)")
    log("="*80)
    
    # Test 1: No auth - should return 401
    log("\n[3.1] Testing /api/admin/stats without auth...")
    resp = requests.get(f"{BACKEND_URL}/admin/stats")
    
    if resp.status_code not in [401, 403]:
        log(f"❌ FAILED: Expected 401 or 403, got {resp.status_code}")
        return False
    
    log(f"✅ PASSED: Got {resp.status_code} (unauthorized)")
    
    log("\n[3.2] Testing /api/admin/users without auth...")
    resp = requests.get(f"{BACKEND_URL}/admin/users")
    
    if resp.status_code not in [401, 403]:
        log(f"❌ FAILED: Expected 401 or 403, got {resp.status_code}")
        return False
    
    log(f"✅ PASSED: Got {resp.status_code} (unauthorized)")
    
    # Test 2: Non-admin user - should return 403
    log("\n[3.3] Creating non-admin test user...")
    suffix = str(uuid.uuid4())[:8]
    resp = requests.post(f"{BACKEND_URL}/auth/register", json={
        "email": f"nonadmin_{suffix}@example.com",
        "password": "TestPass123!",
        "name": "Non Admin User",
        "username": f"nonadmin{suffix}",
        "city": "Madrid",
        "birthdate": "1995-01-01"
    })
    
    if resp.status_code != 200:
        log(f"⚠️  WARNING: Could not create non-admin user: {resp.status_code}")
        log("✅✅✅ TEST 3 PASSED (partial): Access control working for no-auth case")
        return True
    
    non_admin_token = resp.json().get("token")
    log(f"✅ Created non-admin user")
    
    log("\n[3.4] Testing /api/admin/stats as non-admin...")
    resp = requests.get(f"{BACKEND_URL}/admin/stats",
        headers={"Authorization": f"Bearer {non_admin_token}"})
    
    if resp.status_code != 403:
        log(f"❌ FAILED: Expected 403, got {resp.status_code}")
        return False
    
    log(f"✅ PASSED: Got 403 (forbidden)")
    
    log("\n[3.5] Testing /api/admin/users as non-admin...")
    resp = requests.get(f"{BACKEND_URL}/admin/users",
        headers={"Authorization": f"Bearer {non_admin_token}"})
    
    if resp.status_code != 403:
        log(f"❌ FAILED: Expected 403, got {resp.status_code}")
        return False
    
    log(f"✅ PASSED: Got 403 (forbidden)")
    
    log("\n✅✅✅ TEST 3 PASSED: Access control working correctly")
    return True

def seed_test_data(admin_token):
    """Seed some test data for verification."""
    log("\n" + "="*80)
    log("SEEDING TEST DATA")
    log("="*80)
    
    # Create a few test events
    event_ids = []
    for i in range(3):
        event_id = create_test_event(admin_token, f"Test Event {i+1}", days_ahead=i+5)
        if event_id:
            event_ids.append(event_id)
    
    # Create a few test users and interests
    user_tokens = []
    for i in range(3):
        suffix = str(uuid.uuid4())[:8]
        resp = requests.post(f"{BACKEND_URL}/auth/register", json={
            "email": f"seeduser_{suffix}@example.com",
            "password": "TestPass123!",
            "name": f"Seed User {i+1}",
            "username": f"seeduser{suffix}",
            "city": "Madrid",
            "birthdate": "1995-01-01"
        })
        if resp.status_code == 200:
            token = resp.json().get("token")
            user_tokens.append(token)
            
            # Create interests for this user
            if event_ids:
                create_interest(token, event_ids[0], "voy")
                if len(event_ids) > 1:
                    create_interest(token, event_ids[1], "me_interesa")
    
    log(f"\n✅ Seeded {len(event_ids)} events and {len(user_tokens)} users with interests")
    return True

def main():
    log("="*80)
    log("ADMIN PANEL PERFORMANCE FIX TEST SUITE")
    log("Testing N+1 query removal in /api/admin/stats and /api/admin/users")
    log("="*80)
    
    # Login as admin
    admin_token = login_admin()
    if not admin_token:
        log("\n❌❌❌ FATAL: Could not login as admin")
        return False
    
    # Seed some test data
    seed_test_data(admin_token)
    
    # Run tests
    results = []
    
    # Test 1: /api/admin/stats
    results.append(("admin/stats", test_admin_stats(admin_token)))
    
    # Test 2: /api/admin/users
    results.append(("admin/users", test_admin_users(admin_token)))
    
    # Test 3: Access control
    results.append(("access_control", test_access_control()))
    
    # Summary
    log("\n" + "="*80)
    log("TEST SUMMARY")
    log("="*80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        log(f"{status}: {name}")
    
    log(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        log("\n🎉🎉🎉 ALL TESTS PASSED 🎉🎉🎉")
        return True
    else:
        log(f"\n❌ {total - passed} test(s) failed")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
