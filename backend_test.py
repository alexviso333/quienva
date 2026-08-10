#!/usr/bin/env python3
"""
Backend Test for 3 New Features (¿Quién va? app)
Tests TASK 4, TASK 2, and TASK 3 as specified in the review request.
"""

import requests
import os
import time
from datetime import datetime

# Backend URL from environment
BACKEND_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://5e791fc6-c24a-43ab-8471-29846eab5135.preview.emergentagent.com")
BASE_URL = f"{BACKEND_URL}/api"

# Admin credentials
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

def login_admin():
    """Login as admin and return token and headers."""
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.status_code} {resp.text}"
    token = resp.json()["token"]
    return token, {"Authorization": f"Bearer {token}"}

def register_user(email, password, username, city="Ibiza"):
    """Register a new user and return token and headers."""
    resp = requests.post(f"{BASE_URL}/auth/register", json={
        "email": email,
        "password": password,
        "username": username,
        "name": f"Test User {username}",
        "city": city,
        "birthdate": "1995-01-01"
    })
    assert resp.status_code == 200, f"User registration failed: {resp.status_code} {resp.text}"
    token = resp.json()["token"]
    return token, {"Authorization": f"Bearer {token}"}

def test_task_4_events_min():
    """
    TASK 4 — GET /api/admin/events-min (notification composer fix)
    
    Tests:
    1. As admin, GET /admin/events-min → 200 with {events:[...]}
       - Every event has date >= today (Europe/Madrid)
       - List is sorted ascending by date
       - NO event has city == "Pendiente"
       - Each item has id, name, venue, date, city
    2. GET /admin/events-min?city=Madrid → only Madrid events
       GET /admin/events-min?city=Ibiza → only Ibiza events
       GET /admin/events-min?city=Palma de Mallorca → only Palma de Mallorca events
       Verify results are non-empty and correctly filtered
    3. GET /admin/events-min as non-admin → 403
       Unauthenticated → 401
    """
    print("\n" + "=" * 80)
    print("TASK 4 — GET /api/admin/events-min (notification composer fix)")
    print("=" * 80)
    
    # Get admin token
    admin_token, admin_headers = login_admin()
    print("✅ Admin login successful")
    
    # Test 1: GET /admin/events-min as admin
    print("\n[TEST 4.1] GET /admin/events-min as admin...")
    resp = requests.get(f"{BASE_URL}/admin/events-min", headers=admin_headers)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "events" in data, f"Missing 'events' key in response"
    events = data["events"]
    assert isinstance(events, list), f"Expected events to be a list, got {type(events)}"
    assert len(events) > 0, f"Expected non-empty events list, got {len(events)}"
    print(f"✅ GET /admin/events-min → 200 with {len(events)} events")
    
    # Verify every event has date >= today
    today = datetime.now().date().isoformat()
    for event in events:
        assert "id" in event, f"Event missing 'id' field"
        assert "name" in event, f"Event missing 'name' field"
        assert "venue" in event, f"Event missing 'venue' field"
        assert "date" in event, f"Event missing 'date' field"
        assert "city" in event, f"Event missing 'city' field"
        assert event["date"] >= today, f"Event {event['id']} has date {event['date']} < today {today}"
        assert event["city"] != "Pendiente", f"Event {event['id']} has city='Pendiente' (should be excluded)"
    print(f"✅ All events have date >= today ({today})")
    print(f"✅ All events have required fields: id, name, venue, date, city")
    print(f"✅ NO event has city == 'Pendiente'")
    
    # Verify list is sorted ascending by date
    dates = [event["date"] for event in events]
    assert dates == sorted(dates), f"Events are not sorted ascending by date"
    print(f"✅ Events are sorted ascending by date (soonest first)")
    
    # Test 2a: GET /admin/events-min?city=Madrid
    print("\n[TEST 4.2a] GET /admin/events-min?city=Madrid...")
    resp = requests.get(f"{BASE_URL}/admin/events-min?city=Madrid", headers=admin_headers)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    madrid_events = data["events"]
    assert len(madrid_events) > 0, f"Expected non-empty Madrid events list, got {len(madrid_events)}"
    for event in madrid_events:
        # Madrid region includes "Madrid" city
        assert event["city"] == "Madrid", f"Event {event['id']} has city='{event['city']}' (expected Madrid)"
    print(f"✅ GET /admin/events-min?city=Madrid → 200 with {len(madrid_events)} Madrid events (no leakage)")
    
    # Test 2b: GET /admin/events-min?city=Ibiza
    print("\n[TEST 4.2b] GET /admin/events-min?city=Ibiza...")
    resp = requests.get(f"{BASE_URL}/admin/events-min?city=Ibiza", headers=admin_headers)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    ibiza_events = data["events"]
    assert len(ibiza_events) > 0, f"Expected non-empty Ibiza events list, got {len(ibiza_events)}"
    for event in ibiza_events:
        assert event["city"] == "Ibiza", f"Event {event['id']} has city='{event['city']}' (expected Ibiza)"
    print(f"✅ GET /admin/events-min?city=Ibiza → 200 with {len(ibiza_events)} Ibiza events (no leakage)")
    
    # Test 2c: GET /admin/events-min?city=Palma de Mallorca
    print("\n[TEST 4.2c] GET /admin/events-min?city=Palma de Mallorca...")
    resp = requests.get(f"{BASE_URL}/admin/events-min?city=Palma de Mallorca", headers=admin_headers)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    palma_events = data["events"]
    assert len(palma_events) > 0, f"Expected non-empty Palma events list, got {len(palma_events)}"
    for event in palma_events:
        # Palma de Mallorca region may include other Mallorca cities
        # But for this test, we expect "Palma de Mallorca" specifically
        assert event["city"] == "Palma de Mallorca", f"Event {event['id']} has city='{event['city']}' (expected Palma de Mallorca)"
    print(f"✅ GET /admin/events-min?city=Palma de Mallorca → 200 with {len(palma_events)} Palma events (no leakage)")
    
    # Test 3a: GET /admin/events-min as non-admin
    print("\n[TEST 4.3a] GET /admin/events-min as non-admin user...")
    user_token, user_headers = register_user(
        f"testuser_{int(time.time())}@test.com",
        "TestPass123!",
        f"testuser{int(time.time())}",
        "Ibiza"
    )
    resp = requests.get(f"{BASE_URL}/admin/events-min", headers=user_headers)
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
    print(f"✅ GET /admin/events-min as non-admin → 403")
    
    # Test 3b: GET /admin/events-min unauthenticated
    print("\n[TEST 4.3b] GET /admin/events-min unauthenticated...")
    resp = requests.get(f"{BASE_URL}/admin/events-min")
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"
    print(f"✅ GET /admin/events-min unauthenticated → 401")
    
    print("\n✅ TASK 4 — ALL TESTS PASSED (8 tests)")
    return True

def test_task_2_affiliate_set_city():
    """
    TASK 2 — POST /api/admin/affiliate/set-city (manual city reassignment + PENDING_CITY)
    
    Tests:
    1. GET /api/cities → 200 and response contains pending_city == "Pendiente"
    2. As admin, create an event with a DISTINCTIVE venue via POST /api/admin/events
       Use unique venue name like "ZZTestClub QA" and city "Ibiza"
       Capture the created event id
    3. POST /admin/affiliate/set-city {venue:"ZZTestClub QA", city:"Pendiente"} → 200
       with {ok:true} and events_updated >= 1
       Then GET the event and confirm its city == "Pendiente"
       Confirm it is NOT returned by GET /admin/events-min (pending excluded)
       Confirm it is NOT in an Ibiza user's public feed GET /events
    4. POST /admin/affiliate/set-city {venue:"ZZTestClub QA", city:"Madrid"} → 200
       Confirm the event city is now "Madrid"
       Confirm it appears in GET /admin/events-min?city=Madrid
    5. Validation:
       - POST with invalid city "Atlantis" → 400
       - POST with neither slug nor venue → 400
       - POST as non-admin → 403
    """
    print("\n" + "=" * 80)
    print("TASK 2 — POST /api/admin/affiliate/set-city (manual city reassignment)")
    print("=" * 80)
    
    # Get admin token
    admin_token, admin_headers = login_admin()
    print("✅ Admin login successful")
    
    # Test 1: GET /api/cities
    print("\n[TEST 2.1] GET /api/cities → verify pending_city present...")
    resp = requests.get(f"{BASE_URL}/cities")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "pending_city" in data, f"Missing 'pending_city' key in response"
    assert data["pending_city"] == "Pendiente", f"Expected pending_city='Pendiente', got '{data['pending_city']}'"
    print(f"✅ GET /api/cities → 200 with pending_city='Pendiente'")
    
    # Test 2: Create an event with distinctive venue
    print("\n[TEST 2.2] POST /api/admin/events with distinctive venue 'ZZTestClub QA'...")
    unique_venue = f"ZZTestClub QA {int(time.time())}"
    event_data = {
        "name": f"Test Event {int(time.time())}",
        "venue": unique_venue,
        "address": "Test Address 123",
        "date": "2026-09-15",
        "time": "23:00",
        "city": "Ibiza",
        "genre": "Techno",
        "image_url": "https://example.com/test.jpg",
        "price_tiers": [{"name": "General", "price": 25.0}],
        "sale_state": "a_la_venta"
    }
    resp = requests.post(f"{BASE_URL}/admin/events", headers=admin_headers, json=event_data)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    created_event = resp.json()
    event_id = created_event["id"]
    assert created_event["city"] == "Ibiza", f"Expected city='Ibiza', got '{created_event['city']}'"
    print(f"✅ POST /api/admin/events → 200, created event {event_id} with venue '{unique_venue}' in Ibiza")
    
    # Test 3a: POST /admin/affiliate/set-city to move to "Pendiente"
    print(f"\n[TEST 2.3a] POST /admin/affiliate/set-city {{venue:'{unique_venue}', city:'Pendiente'}}...")
    resp = requests.post(f"{BASE_URL}/admin/affiliate/set-city", headers=admin_headers, json={
        "venue": unique_venue,
        "city": "Pendiente"
    })
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["ok"] == True, f"Expected ok=true, got {data}"
    assert data["events_updated"] >= 1, f"Expected events_updated >= 1, got {data['events_updated']}"
    print(f"✅ POST /admin/affiliate/set-city → 200 with ok=true, events_updated={data['events_updated']}")
    
    # Test 3b: Verify event city is now "Pendiente"
    print(f"\n[TEST 2.3b] GET /events/{event_id} to verify city='Pendiente'...")
    resp = requests.get(f"{BASE_URL}/events/{event_id}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    event = resp.json()
    assert event["city"] == "Pendiente", f"Expected city='Pendiente', got '{event['city']}'"
    print(f"✅ Event {event_id} city is now 'Pendiente'")
    
    # Test 3c: Verify event is NOT in /admin/events-min (pending excluded)
    print(f"\n[TEST 2.3c] GET /admin/events-min → verify event NOT in list (pending excluded)...")
    resp = requests.get(f"{BASE_URL}/admin/events-min", headers=admin_headers)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    events = resp.json()["events"]
    event_ids = [e["id"] for e in events]
    assert event_id not in event_ids, f"Event {event_id} should NOT be in /admin/events-min (pending excluded)"
    print(f"✅ Event {event_id} is NOT in /admin/events-min (correctly excluded)")
    
    # Test 3d: Verify event is NOT in Ibiza user's public feed
    print(f"\n[TEST 2.3d] GET /events as Ibiza user → verify event NOT in feed...")
    ibiza_user_token, ibiza_user_headers = register_user(
        f"ibizauser_{int(time.time())}@test.com",
        "TestPass123!",
        f"ibizauser{int(time.time())}",
        "Ibiza"
    )
    resp = requests.get(f"{BASE_URL}/events", headers=ibiza_user_headers)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    events = resp.json()
    event_ids = [e["id"] for e in events]
    assert event_id not in event_ids, f"Event {event_id} should NOT be in Ibiza user's feed (pending excluded)"
    print(f"✅ Event {event_id} is NOT in Ibiza user's feed (correctly hidden)")
    
    # Test 4a: POST /admin/affiliate/set-city to move to "Madrid"
    print(f"\n[TEST 2.4a] POST /admin/affiliate/set-city {{venue:'{unique_venue}', city:'Madrid'}}...")
    resp = requests.post(f"{BASE_URL}/admin/affiliate/set-city", headers=admin_headers, json={
        "venue": unique_venue,
        "city": "Madrid"
    })
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["ok"] == True, f"Expected ok=true, got {data}"
    print(f"✅ POST /admin/affiliate/set-city → 200 with ok=true")
    
    # Test 4b: Verify event city is now "Madrid"
    print(f"\n[TEST 2.4b] GET /events/{event_id} to verify city='Madrid'...")
    resp = requests.get(f"{BASE_URL}/events/{event_id}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    event = resp.json()
    assert event["city"] == "Madrid", f"Expected city='Madrid', got '{event['city']}'"
    print(f"✅ Event {event_id} city is now 'Madrid'")
    
    # Test 4c: Verify event appears in /admin/events-min?city=Madrid
    print(f"\n[TEST 2.4c] GET /admin/events-min?city=Madrid → verify event in list...")
    resp = requests.get(f"{BASE_URL}/admin/events-min?city=Madrid", headers=admin_headers)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    events = resp.json()["events"]
    event_ids = [e["id"] for e in events]
    assert event_id in event_ids, f"Event {event_id} should be in /admin/events-min?city=Madrid"
    print(f"✅ Event {event_id} is now in /admin/events-min?city=Madrid")
    
    # Test 5a: Validation - invalid city "Atlantis"
    print(f"\n[TEST 2.5a] POST /admin/affiliate/set-city with invalid city 'Atlantis' → 400...")
    resp = requests.post(f"{BASE_URL}/admin/affiliate/set-city", headers=admin_headers, json={
        "venue": unique_venue,
        "city": "Atlantis"
    })
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    print(f"✅ POST /admin/affiliate/set-city with invalid city → 400")
    
    # Test 5b: Validation - missing both slug and venue
    print(f"\n[TEST 2.5b] POST /admin/affiliate/set-city with neither slug nor venue → 400...")
    resp = requests.post(f"{BASE_URL}/admin/affiliate/set-city", headers=admin_headers, json={
        "city": "Madrid"
    })
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    print(f"✅ POST /admin/affiliate/set-city with neither slug nor venue → 400")
    
    # Test 5c: Validation - non-admin user
    print(f"\n[TEST 2.5c] POST /admin/affiliate/set-city as non-admin → 403...")
    user_token, user_headers = register_user(
        f"testuser2_{int(time.time())}@test.com",
        "TestPass123!",
        f"testuser2{int(time.time())}",
        "Madrid"
    )
    resp = requests.post(f"{BASE_URL}/admin/affiliate/set-city", headers=user_headers, json={
        "venue": unique_venue,
        "city": "Madrid"
    })
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
    print(f"✅ POST /admin/affiliate/set-city as non-admin → 403")
    
    print("\n✅ TASK 2 — ALL TESTS PASSED (13 tests)")
    return True

def test_task_3_username_uniqueness():
    """
    TASK 3 — PUT /api/auth/profile username uniqueness
    
    Tests:
    1. Register two users A and B
       Note their usernames from /auth/me
    2. As A, PUT /auth/profile {username:"qauniqueusername1"} → 200
       GET /auth/me shows username "qauniqueusername1"
    3. As A, PUT /auth/profile {username:"<B's exact username>"} → 400
       with detail about username already existing
    4. As A, PUT /auth/profile {username:"qauniqueusername1"} (own current) → 200 (no clash)
    """
    print("\n" + "=" * 80)
    print("TASK 3 — PUT /api/auth/profile username uniqueness")
    print("=" * 80)
    
    # Test 1: Register two users A and B
    print("\n[TEST 3.1] Register user A and user B...")
    ts = int(time.time())
    user_a_token, user_a_headers = register_user(
        f"usera_{ts}@test.com",
        "TestPass123!",
        f"usera{ts}",
        "Madrid"
    )
    user_b_token, user_b_headers = register_user(
        f"userb_{ts}@test.com",
        "TestPass123!",
        f"userb{ts}",
        "Barcelona"
    )
    print(f"✅ Registered user A and user B")
    
    # Get user A's username
    resp = requests.get(f"{BASE_URL}/auth/me", headers=user_a_headers)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    user_a_data = resp.json()
    user_a_username = user_a_data["username"]
    print(f"   User A username: {user_a_username}")
    
    # Get user B's username
    resp = requests.get(f"{BASE_URL}/auth/me", headers=user_b_headers)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    user_b_data = resp.json()
    user_b_username = user_b_data["username"]
    print(f"   User B username: {user_b_username}")
    
    # Test 2: As A, change username to unique value
    print(f"\n[TEST 3.2] As user A, PUT /auth/profile {{username:'qauniqueusername1'}}...")
    new_username = f"qauniqueusername1{ts}"
    resp = requests.put(f"{BASE_URL}/auth/profile", headers=user_a_headers, json={
        "username": new_username
    })
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    print(f"✅ PUT /auth/profile {{username:'{new_username}'}} → 200")
    
    # Verify username changed in /auth/me
    resp = requests.get(f"{BASE_URL}/auth/me", headers=user_a_headers)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    user_a_data = resp.json()
    assert user_a_data["username"] == new_username, f"Expected username='{new_username}', got '{user_a_data['username']}'"
    print(f"✅ GET /auth/me shows username='{new_username}'")
    
    # Test 3: As A, try to change username to B's username (should fail)
    print(f"\n[TEST 3.3] As user A, PUT /auth/profile {{username:'{user_b_username}'}} (B's username) → 400...")
    resp = requests.put(f"{BASE_URL}/auth/profile", headers=user_a_headers, json={
        "username": user_b_username
    })
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    error_data = resp.json()
    assert "detail" in error_data, f"Missing 'detail' key in error response"
    assert "ya existe" in error_data["detail"].lower() or "already" in error_data["detail"].lower(), \
        f"Expected error message about username already existing, got: {error_data['detail']}"
    print(f"✅ PUT /auth/profile with B's username → 400 with detail: '{error_data['detail']}'")
    
    # Test 4: As A, change username to own current username (should succeed - no-op)
    print(f"\n[TEST 3.4] As user A, PUT /auth/profile {{username:'{new_username}'}} (own current) → 200...")
    resp = requests.put(f"{BASE_URL}/auth/profile", headers=user_a_headers, json={
        "username": new_username
    })
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    print(f"✅ PUT /auth/profile with own current username → 200 (no clash)")
    
    print("\n✅ TASK 3 — ALL TESTS PASSED (4 tests)")
    return True

def main():
    """Run all tests."""
    print("=" * 80)
    print("BACKEND TEST — 3 NEW FEATURES (¿Quién va? app)")
    print("=" * 80)
    print(f"Backend URL: {BACKEND_URL}")
    print(f"Admin: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    print(f"System date: 2026-08-10 (all events are upcoming)")
    print("=" * 80)
    
    total_tests = 0
    passed_tests = 0
    failed_tests = 0
    
    # Test TASK 4
    try:
        test_task_4_events_min()
        passed_tests += 8
        total_tests += 8
    except AssertionError as e:
        print(f"\n❌ TASK 4 FAILED: {e}")
        failed_tests += 1
        total_tests += 8
    except Exception as e:
        print(f"\n❌ TASK 4 ERROR: {e}")
        import traceback
        traceback.print_exc()
        failed_tests += 1
        total_tests += 8
    
    # Test TASK 2
    try:
        test_task_2_affiliate_set_city()
        passed_tests += 13
        total_tests += 13
    except AssertionError as e:
        print(f"\n❌ TASK 2 FAILED: {e}")
        failed_tests += 1
        total_tests += 13
    except Exception as e:
        print(f"\n❌ TASK 2 ERROR: {e}")
        import traceback
        traceback.print_exc()
        failed_tests += 1
        total_tests += 13
    
    # Test TASK 3
    try:
        test_task_3_username_uniqueness()
        passed_tests += 4
        total_tests += 4
    except AssertionError as e:
        print(f"\n❌ TASK 3 FAILED: {e}")
        failed_tests += 1
        total_tests += 4
    except Exception as e:
        print(f"\n❌ TASK 3 ERROR: {e}")
        import traceback
        traceback.print_exc()
        failed_tests += 1
        total_tests += 4
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Total tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {failed_tests}")
    
    if failed_tests == 0:
        print("\n✅ ALL TESTS PASSED")
        return 0
    else:
        print(f"\n❌ {failed_tests} TEST(S) FAILED")
        return 1

if __name__ == "__main__":
    exit(main())
