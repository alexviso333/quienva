#!/usr/bin/env python3
"""
Backend API Testing for ¿Quién va? - Iteration 2026-08-02j
Tests: Featured Events, Notify Segmentation, Scheduling
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

# Test results tracking
tests_passed = 0
tests_failed = 0
test_results = []

def log_test(name, passed, details=""):
    global tests_passed, tests_failed
    if passed:
        tests_passed += 1
        status = "✅ PASS"
    else:
        tests_failed += 1
        status = "❌ FAIL"
    result = f"{status}: {name}"
    if details:
        result += f" - {details}"
    test_results.append(result)
    print(result)

def register_user(email, password, name, username, city="Palma de Mallorca"):
    """Register a new user"""
    response = requests.post(f"{BASE_URL}/auth/register", json={
        "email": email,
        "password": password,
        "name": name,
        "username": username,
        "city": city
    })
    return response

def login(email, password):
    """Login and return token"""
    response = requests.post(f"{BASE_URL}/auth/login", json={
        "email": email,
        "password": password
    })
    if response.status_code == 200:
        data = response.json()
        return data.get("token")
    return None

def get_headers(token):
    """Get authorization headers"""
    return {"Authorization": f"Bearer {token}"}

print("=" * 80)
print("BACKEND API TESTING - Iteration 2026-08-02j")
print("Testing: Featured Events, Notify Segmentation, Scheduling")
print("=" * 80)

# ============================================================================
# SETUP: Login as admin and register normal user
# ============================================================================
print("\n[SETUP] Logging in as admin...")
admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
if not admin_token:
    print("❌ CRITICAL: Cannot login as admin. Aborting tests.")
    exit(1)
print(f"✅ Admin logged in successfully")

print("\n[SETUP] Registering normal user...")
normal_email = f"testuser_{int(time.time())}@test.com"
normal_password = "testpass123"
normal_name = "Test User"
normal_username = f"testuser{int(time.time())}"
reg_response = register_user(normal_email, normal_password, normal_name, normal_username, "Palma de Mallorca")
if reg_response.status_code == 200:
    normal_token = reg_response.json().get("token")
    print(f"✅ Normal user registered: {normal_email}")
else:
    print(f"❌ Failed to register normal user: {reg_response.status_code}")
    normal_token = None

# ============================================================================
# TEST 1: FEATURED EVENTS
# ============================================================================
print("\n" + "=" * 80)
print("TEST 1: FEATURED EVENTS")
print("=" * 80)

# Get an upcoming event in Palma de Mallorca
print("\n[1.1] Getting an upcoming event in Palma de Mallorca...")
events_response = requests.get(f"{BASE_URL}/events", headers=get_headers(normal_token))
log_test("GET /events as normal user", events_response.status_code == 200, 
         f"Status: {events_response.status_code}")

event_id = None
if events_response.status_code == 200:
    events = events_response.json()
    if events:
        # Find an event in Palma de Mallorca
        for ev in events:
            if ev.get("city") == "Palma de Mallorca":
                event_id = ev["id"]
                print(f"✅ Found event: {ev['name']} (ID: {event_id})")
                break

if not event_id:
    print("❌ No events found in Palma de Mallorca. Cannot continue featured tests.")
else:
    # Test 1.2: Set event as featured (admin)
    print(f"\n[1.2] Setting event {event_id} as featured (admin)...")
    featured_response = requests.put(
        f"{BASE_URL}/admin/events/{event_id}/featured",
        headers=get_headers(admin_token),
        json={"featured": True}
    )
    log_test("PUT /admin/events/{id}/featured with featured:true (admin)", 
             featured_response.status_code == 200 and 
             featured_response.json().get("ok") == True and 
             featured_response.json().get("featured") == True,
             f"Status: {featured_response.status_code}, Response: {featured_response.json()}")

    # Test 1.3: Verify event appears as featured in GET /events
    print(f"\n[1.3] Verifying event appears as featured in GET /events...")
    events_response = requests.get(f"{BASE_URL}/events", headers=get_headers(normal_token))
    if events_response.status_code == 200:
        events = events_response.json()
        featured_event = next((e for e in events if e["id"] == event_id), None)
        if featured_event:
            is_featured = featured_event.get("featured") == True
            # Check if it's among the first items (featured events should float to top)
            event_index = next((i for i, e in enumerate(events) if e["id"] == event_id), -1)
            is_first = event_index >= 0 and event_index < 5  # Should be in top 5
            log_test("Featured event has featured:true flag", is_featured,
                    f"featured={featured_event.get('featured')}")
            log_test("Featured event appears among first items", is_first,
                    f"Position: {event_index + 1} of {len(events)}")
        else:
            log_test("Featured event found in list", False, "Event not found")
    else:
        log_test("GET /events after featuring", False, f"Status: {events_response.status_code}")

    # Test 1.4: Unset featured flag
    print(f"\n[1.4] Unsetting featured flag...")
    unfeatured_response = requests.put(
        f"{BASE_URL}/admin/events/{event_id}/featured",
        headers=get_headers(admin_token),
        json={"featured": False}
    )
    log_test("PUT /admin/events/{id}/featured with featured:false", 
             unfeatured_response.status_code == 200 and 
             unfeatured_response.json().get("featured") == False,
             f"Status: {unfeatured_response.status_code}, Response: {unfeatured_response.json()}")

    # Test 1.5: Verify featured flag is false
    print(f"\n[1.5] Verifying featured flag is false...")
    events_response = requests.get(f"{BASE_URL}/events", headers=get_headers(normal_token))
    if events_response.status_code == 200:
        events = events_response.json()
        event = next((e for e in events if e["id"] == event_id), None)
        if event:
            log_test("Event featured flag is false after unsetting", 
                    event.get("featured") == False,
                    f"featured={event.get('featured')}")
        else:
            log_test("Event found after unfeaturing", False, "Event not found")

    # Test 1.6: Non-admin tries to set featured (should be 403)
    print(f"\n[1.6] Non-admin trying to set featured (should be 403)...")
    non_admin_response = requests.put(
        f"{BASE_URL}/admin/events/{event_id}/featured",
        headers=get_headers(normal_token),
        json={"featured": True}
    )
    log_test("Non-admin PUT /admin/events/{id}/featured returns 403", 
             non_admin_response.status_code == 403,
             f"Status: {non_admin_response.status_code}")

    # Test 1.7: Invalid event ID (should be 404)
    print(f"\n[1.7] Setting featured on invalid event ID (should be 404)...")
    invalid_response = requests.put(
        f"{BASE_URL}/admin/events/invalid-event-id-12345/featured",
        headers=get_headers(admin_token),
        json={"featured": True}
    )
    log_test("PUT /admin/events/{invalid_id}/featured returns 404", 
             invalid_response.status_code == 404,
             f"Status: {invalid_response.status_code}")

    # Test 1.8: GET /admin/events/{id}/stats includes featured field
    print(f"\n[1.8] Verifying GET /admin/events/{id}/stats includes featured field...")
    # First set it to true
    requests.put(
        f"{BASE_URL}/admin/events/{event_id}/featured",
        headers=get_headers(admin_token),
        json={"featured": True}
    )
    stats_response = requests.get(
        f"{BASE_URL}/admin/events/{event_id}/stats",
        headers=get_headers(admin_token)
    )
    if stats_response.status_code == 200:
        stats = stats_response.json()
        event_data = stats.get("event", {})
        log_test("GET /admin/events/{id}/stats includes featured field", 
                "featured" in event_data and event_data["featured"] == True,
                f"featured={event_data.get('featured')}")
    else:
        log_test("GET /admin/events/{id}/stats", False, 
                f"Status: {stats_response.status_code}")

# ============================================================================
# TEST 2: NOTIFY SEGMENTATION
# ============================================================================
print("\n" + "=" * 80)
print("TEST 2: NOTIFY SEGMENTATION")
print("=" * 80)

# Test 2.1: Get a real genre from the system
print("\n[2.1] Getting available genres...")
genres_response = requests.get(f"{BASE_URL}/events/genres", headers=get_headers(normal_token))
real_genre = None
if genres_response.status_code == 200:
    genres = genres_response.json()
    if genres:
        real_genre = genres[0]
        print(f"✅ Found genre: {real_genre}")
        log_test("GET /events/genres", True, f"Found {len(genres)} genres")
    else:
        print("⚠️ No genres found in system")
        log_test("GET /events/genres", True, "No genres available")
else:
    log_test("GET /events/genres", False, f"Status: {genres_response.status_code}")

# Test 2.2: Send notification to city audience
print("\n[2.2] Sending notification to city audience (Palma de Mallorca)...")
city_notify_response = requests.post(
    f"{BASE_URL}/admin/notify/send",
    headers=get_headers(admin_token),
    json={
        "preset_id": "generic_new",
        "audience": "city",
        "city": "Palma de Mallorca"
    }
)
if city_notify_response.status_code == 200:
    data = city_notify_response.json()
    log_test("POST /admin/notify/send with city audience", 
             data.get("ok") == True and 
             data.get("audience") == "city" and 
             "notified" in data and 
             data.get("queued") == True,
             f"Response: {data}")
else:
    log_test("POST /admin/notify/send with city audience", False,
             f"Status: {city_notify_response.status_code}, Response: {city_notify_response.text}")

# Test 2.3: Send notification to genre audience (if genre available)
if real_genre:
    print(f"\n[2.3] Sending notification to genre audience ({real_genre})...")
    genre_notify_response = requests.post(
        f"{BASE_URL}/admin/notify/send",
        headers=get_headers(admin_token),
        json={
            "body": "hola melomanos",
            "audience": "genre",
            "genre": real_genre
        }
    )
    if genre_notify_response.status_code == 200:
        data = genre_notify_response.json()
        log_test("POST /admin/notify/send with genre audience", 
                data.get("ok") == True and 
                data.get("audience") == "genre",
                f"Response: {data}")
    else:
        log_test("POST /admin/notify/send with genre audience", False,
                f"Status: {genre_notify_response.status_code}, Response: {genre_notify_response.text}")
else:
    print("\n[2.3] Skipping genre notification test (no genres available)")

# Test 2.4: Send notification with genre audience but empty genre (should be 400)
print("\n[2.4] Sending notification with genre audience but empty genre (should be 400)...")
empty_genre_response = requests.post(
    f"{BASE_URL}/admin/notify/send",
    headers=get_headers(admin_token),
    json={
        "body": "test message",
        "audience": "genre",
        "genre": ""
    }
)
log_test("POST /admin/notify/send with empty genre returns 400", 
         empty_genre_response.status_code == 400,
         f"Status: {empty_genre_response.status_code}")

# Test 2.5: Send notification with city audience but empty city (should be 400)
print("\n[2.5] Sending notification with city audience but empty city (should be 400)...")
empty_city_response = requests.post(
    f"{BASE_URL}/admin/notify/send",
    headers=get_headers(admin_token),
    json={
        "body": "test message",
        "audience": "city",
        "city": ""
    }
)
log_test("POST /admin/notify/send with empty city returns 400", 
         empty_city_response.status_code == 400,
         f"Status: {empty_city_response.status_code}")

# Test 2.6: Non-admin tries to send notification (should be 403)
print("\n[2.6] Non-admin trying to send notification (should be 403)...")
non_admin_notify_response = requests.post(
    f"{BASE_URL}/admin/notify/send",
    headers=get_headers(normal_token),
    json={
        "preset_id": "generic_new",
        "audience": "all"
    }
)
log_test("Non-admin POST /admin/notify/send returns 403", 
         non_admin_notify_response.status_code == 403,
         f"Status: {non_admin_notify_response.status_code}")

# ============================================================================
# TEST 3: SCHEDULING
# ============================================================================
print("\n" + "=" * 80)
print("TEST 3: SCHEDULING")
print("=" * 80)

# Test 3.1: Schedule notification for future
print("\n[3.1] Scheduling notification for future (2030-01-01T12:00:00)...")
schedule_response = requests.post(
    f"{BASE_URL}/admin/notify/send",
    headers=get_headers(admin_token),
    json={
        "preset_id": "generic_new",
        "audience": "all",
        "send_at": "2030-01-01T12:00:00"
    }
)
scheduled_id = None
if schedule_response.status_code == 200:
    data = schedule_response.json()
    scheduled_id = data.get("id")
    log_test("POST /admin/notify/send with future send_at", 
             data.get("ok") == True and 
             data.get("scheduled") == True and 
             "id" in data and 
             "send_at" in data,
             f"Response: {data}")
else:
    log_test("POST /admin/notify/send with future send_at", False,
             f"Status: {schedule_response.status_code}, Response: {schedule_response.text}")

# Test 3.2: GET scheduled notifications
print("\n[3.2] Getting scheduled notifications...")
get_scheduled_response = requests.get(
    f"{BASE_URL}/admin/notify/scheduled",
    headers=get_headers(admin_token)
)
if get_scheduled_response.status_code == 200:
    data = get_scheduled_response.json()
    scheduled_list = data.get("scheduled", [])
    found_scheduled = any(s.get("id") == scheduled_id for s in scheduled_list) if scheduled_id else False
    log_test("GET /admin/notify/scheduled returns list", 
             "scheduled" in data and isinstance(scheduled_list, list),
             f"Found {len(scheduled_list)} scheduled notifications")
    if scheduled_id:
        log_test("Scheduled notification appears in list", found_scheduled,
                f"Looking for ID: {scheduled_id}")
else:
    log_test("GET /admin/notify/scheduled", False,
             f"Status: {get_scheduled_response.status_code}")

# Test 3.3: DELETE scheduled notification
if scheduled_id:
    print(f"\n[3.3] Deleting scheduled notification {scheduled_id}...")
    delete_response = requests.delete(
        f"{BASE_URL}/admin/notify/scheduled/{scheduled_id}",
        headers=get_headers(admin_token)
    )
    if delete_response.status_code == 200:
        data = delete_response.json()
        log_test("DELETE /admin/notify/scheduled/{id}", 
                data.get("ok") == True and data.get("cancelled") == True,
                f"Response: {data}")
    else:
        log_test("DELETE /admin/notify/scheduled/{id}", False,
                f"Status: {delete_response.status_code}")

    # Test 3.4: Verify it's no longer in the list
    print(f"\n[3.4] Verifying scheduled notification is no longer in list...")
    get_scheduled_response = requests.get(
        f"{BASE_URL}/admin/notify/scheduled",
        headers=get_headers(admin_token)
    )
    if get_scheduled_response.status_code == 200:
        data = get_scheduled_response.json()
        scheduled_list = data.get("scheduled", [])
        still_found = any(s.get("id") == scheduled_id for s in scheduled_list)
        log_test("Cancelled notification no longer in pending list", not still_found,
                f"Still found: {still_found}")
    else:
        log_test("GET /admin/notify/scheduled after delete", False,
                f"Status: {get_scheduled_response.status_code}")
else:
    print("\n[3.3-3.4] Skipping delete tests (no scheduled ID)")

# Test 3.5: DELETE unknown scheduled notification (should be 404)
print("\n[3.5] Deleting unknown scheduled notification (should be 404)...")
delete_unknown_response = requests.delete(
    f"{BASE_URL}/admin/notify/scheduled/unknown-id-12345",
    headers=get_headers(admin_token)
)
log_test("DELETE /admin/notify/scheduled/{unknown_id} returns 404", 
         delete_unknown_response.status_code == 404,
         f"Status: {delete_unknown_response.status_code}")

# Test 3.6: Schedule notification with past date (should send now)
print("\n[3.6] Scheduling notification with past date (should send now)...")
past_schedule_response = requests.post(
    f"{BASE_URL}/admin/notify/send",
    headers=get_headers(admin_token),
    json={
        "preset_id": "generic_new",
        "audience": "all",
        "send_at": "2020-01-01T12:00:00"
    }
)
if past_schedule_response.status_code == 200:
    data = past_schedule_response.json()
    # Should NOT have scheduled:true, should have notified/queued
    has_scheduled = data.get("scheduled") == True
    has_notified = "notified" in data or "queued" in data
    log_test("POST /admin/notify/send with past send_at sends now", 
             not has_scheduled and has_notified,
             f"Response: {data}")
else:
    log_test("POST /admin/notify/send with past send_at", False,
             f"Status: {past_schedule_response.status_code}, Response: {past_schedule_response.text}")

# Test 3.7: Non-admin tries to get scheduled (should be 403)
print("\n[3.7] Non-admin trying to get scheduled notifications (should be 403)...")
non_admin_scheduled_response = requests.get(
    f"{BASE_URL}/admin/notify/scheduled",
    headers=get_headers(normal_token)
)
log_test("Non-admin GET /admin/notify/scheduled returns 403", 
         non_admin_scheduled_response.status_code == 403,
         f"Status: {non_admin_scheduled_response.status_code}")

# Test 3.8: Non-admin tries to delete scheduled (should be 403)
print("\n[3.8] Non-admin trying to delete scheduled notification (should be 403)...")
non_admin_delete_response = requests.delete(
    f"{BASE_URL}/admin/notify/scheduled/some-id",
    headers=get_headers(normal_token)
)
log_test("Non-admin DELETE /admin/notify/scheduled/{id} returns 403", 
         non_admin_delete_response.status_code == 403,
         f"Status: {non_admin_delete_response.status_code}")

# ============================================================================
# TEST 4: REGRESSION - Admin Funnel
# ============================================================================
print("\n" + "=" * 80)
print("TEST 4: REGRESSION - Admin Funnel")
print("=" * 80)

print("\n[4.1] Testing GET /admin/funnel?scope=all...")
funnel_response = requests.get(
    f"{BASE_URL}/admin/funnel?scope=all",
    headers=get_headers(admin_token)
)
if funnel_response.status_code == 200:
    data = funnel_response.json()
    has_rows = "rows" in data
    has_totals = "totals" in data
    log_test("GET /admin/funnel?scope=all returns 200", True,
             f"Status: {funnel_response.status_code}")
    log_test("Response has 'rows' field", has_rows,
             f"rows present: {has_rows}")
    log_test("Response has 'totals' field", has_totals,
             f"totals present: {has_totals}")
else:
    log_test("GET /admin/funnel?scope=all", False,
             f"Status: {funnel_response.status_code}")

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "=" * 80)
print("TEST SUMMARY")
print("=" * 80)
print(f"\nTotal Tests: {tests_passed + tests_failed}")
print(f"✅ Passed: {tests_passed}")
print(f"❌ Failed: {tests_failed}")
print(f"Pass Rate: {(tests_passed / (tests_passed + tests_failed) * 100):.1f}%")

print("\n" + "=" * 80)
print("DETAILED RESULTS")
print("=" * 80)
for result in test_results:
    print(result)

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)
