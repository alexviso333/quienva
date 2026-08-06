#!/usr/bin/env python3
"""
Test script for GET /api/me/wrapped endpoint (Monthly Wrapped feature)
Following the exact test scenario from the review request.

System current month: 2026-08
Creates events with dates INSIDE 2026-08 (format YYYY-MM-DD)
Tests wrapped endpoint with seeded data.
"""

import requests
import json
import io
from datetime import datetime

# Backend URL from frontend/.env
BASE_URL = "https://204b173e-f0b3-4059-a373-e97cae5b5cd7.preview.emergentagent.com/api"

# Admin credentials from test_credentials.md
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

# Test results tracking
test_results = []

def log_test(step, status, details=""):
    """Log test result"""
    result = f"{'✅' if status else '❌'} STEP {step}: {details}"
    test_results.append(result)
    print(result)
    return status

def create_test_image():
    """Create a minimal valid JPEG image for testing"""
    # Minimal JPEG header + data
    jpeg_data = (
        b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
        b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c'
        b'\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c'
        b'\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01'
        b'\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00'
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xda\x00\x08\x01\x01\x00\x00'
        b'?\x00\x7f\xff\xd9'
    )
    return io.BytesIO(jpeg_data)

def main():
    print("=" * 80)
    print("TESTING: GET /api/me/wrapped - Monthly Wrapped Endpoint")
    print("=" * 80)
    print()

    # ========================================================================
    # STEP 1: Login as admin
    # ========================================================================
    print("STEP 1: Login as admin")
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    
    if resp.status_code != 200:
        log_test(1, False, f"Admin login failed: {resp.status_code} - {resp.text}")
        return
    
    admin_token = resp.json()["token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    log_test(1, True, "Admin login successful")
    print()

    # ========================================================================
    # STEP 2: Create 3 events with dates in 2026-08
    # ========================================================================
    print("STEP 2: Create 3 events with dates in 2026-08")
    print("  - 2 events with genre 'Reggaeton'")
    print("  - 1 event with genre 'Techno'")
    print("  - All with DISTINCT venues (Sala A, Sala B, Sala C)")
    
    events_data = [
        {
            "name": "Fiesta Reggaeton 1",
            "venue": "Sala A",
            "date": "2026-08-15",
            "time": "23:00",
            "genre": "Reggaeton",
            "description": "Test event 1",
            "city": "Palma de Mallorca"
        },
        {
            "name": "Fiesta Reggaeton 2",
            "venue": "Sala B",
            "date": "2026-08-20",
            "time": "23:00",
            "genre": "Reggaeton",
            "description": "Test event 2",
            "city": "Palma de Mallorca"
        },
        {
            "name": "Fiesta Techno",
            "venue": "Sala C",
            "date": "2026-08-25",
            "time": "23:00",
            "genre": "Techno",
            "description": "Test event 3",
            "city": "Palma de Mallorca"
        }
    ]
    
    created_events = []
    for i, event_data in enumerate(events_data, 1):
        resp = requests.post(f"{BASE_URL}/admin/events", json=event_data, headers=admin_headers)
        if resp.status_code not in [200, 201]:
            log_test(2, False, f"Failed to create event {i}: {resp.status_code} - {resp.text}")
            return
        event = resp.json()
        created_events.append(event)
        print(f"  ✓ Created event {i}: {event['name']} at {event['venue']} ({event['genre']})")
    
    ev1, ev2, ev3 = created_events
    log_test(2, True, f"Created 3 events: {ev1['id']}, {ev2['id']}, {ev3['id']}")
    print()

    # ========================================================================
    # STEP 3: Register and login user U1
    # ========================================================================
    print("STEP 3: Register and login user U1")
    
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    u1_data = {
        "email": f"u1_{timestamp}@test.com",
        "username": f"u1_{timestamp}",
        "password": "password123",
        "name": "User One",
        "birthdate": "1995-01-01",
        "city": "Palma de Mallorca"
    }
    
    resp = requests.post(f"{BASE_URL}/auth/register", json=u1_data)
    if resp.status_code not in [200, 201]:
        log_test(3, False, f"Failed to register U1: {resp.status_code} - {resp.text}")
        return
    
    u1_token = resp.json()["token"]
    u1_headers = {"Authorization": f"Bearer {u1_token}"}
    
    # Get U1's user_id
    resp = requests.get(f"{BASE_URL}/auth/me", headers=u1_headers)
    u1_user_id = resp.json()["user_id"]
    
    log_test(3, True, f"Registered U1: {u1_data['email']} (user_id: {u1_user_id})")
    print()

    # ========================================================================
    # STEP 4: U1 marks 'estuve' on all 3 events
    # ========================================================================
    print("STEP 4: U1 marks 'estuve' on all 3 events")
    
    for i, event in enumerate(created_events, 1):
        resp = requests.post(
            f"{BASE_URL}/events/{event['id']}/interest",
            json={"status": "estuve"},
            headers=u1_headers
        )
        if resp.status_code != 200:
            log_test(4, False, f"Failed to mark interest on event {i}: {resp.status_code} - {resp.text}")
            return
        print(f"  ✓ U1 marked 'estuve' on event {i}: {event['name']}")
    
    log_test(4, True, "U1 marked 'estuve' on all 3 events")
    print()

    # ========================================================================
    # STEP 5: U1 uploads album photo to ev1
    # ========================================================================
    print("STEP 5: U1 uploads album photo to ev1")
    
    # First, check the album upload endpoint to see what field name it expects
    # Based on the backend code, it should be 'files' for multi-upload
    files = {'files': ('test.jpg', create_test_image(), 'image/jpeg')}
    resp = requests.post(
        f"{BASE_URL}/events/{ev1['id']}/album/upload",
        files=files,
        headers=u1_headers
    )
    
    if resp.status_code != 200:
        log_test(5, False, f"Failed to upload album photo: {resp.status_code} - {resp.text}")
        return
    
    album_upload = resp.json()
    log_test(5, True, f"U1 uploaded album photo to ev1")
    print()

    # ========================================================================
    # STEP 6: Admin triggers moment on ev1, U1 uploads moment capture
    # ========================================================================
    print("STEP 6: Admin triggers moment on ev1, U1 uploads moment capture")
    
    # Admin triggers moment
    resp = requests.post(
        f"{BASE_URL}/admin/events/{ev1['id']}/moment/trigger",
        headers=admin_headers
    )
    if resp.status_code != 200:
        log_test(6, False, f"Failed to trigger moment: {resp.status_code} - {resp.text}")
        return
    print(f"  ✓ Admin triggered moment on ev1")
    
    # U1 uploads moment capture
    files = {'file': ('moment.jpg', create_test_image(), 'image/jpeg')}
    resp = requests.post(
        f"{BASE_URL}/events/{ev1['id']}/moment/upload",
        files=files,
        headers=u1_headers
    )
    
    if resp.status_code != 200:
        log_test(6, False, f"Failed to upload moment: {resp.status_code} - {resp.text}")
        return
    
    log_test(6, True, "Admin triggered moment and U1 uploaded capture")
    print()

    # ========================================================================
    # STEP 7: Register user U2 and create friendship with U1
    # ========================================================================
    print("STEP 7: Register user U2 and create friendship with U1")
    
    u2_data = {
        "email": f"u2_{timestamp}@test.com",
        "username": f"u2_{timestamp}",
        "password": "password123",
        "name": "User Two",
        "birthdate": "1996-01-01",
        "city": "Palma de Mallorca"
    }
    
    resp = requests.post(f"{BASE_URL}/auth/register", json=u2_data)
    if resp.status_code not in [200, 201]:
        log_test(7, False, f"Failed to register U2: {resp.status_code} - {resp.text}")
        return
    
    u2_token = resp.json()["token"]
    u2_headers = {"Authorization": f"Bearer {u2_token}"}
    
    # Get U2's user_id
    resp = requests.get(f"{BASE_URL}/auth/me", headers=u2_headers)
    u2_user_id = resp.json()["user_id"]
    u2_username = resp.json()["username"]
    
    print(f"  ✓ Registered U2: {u2_data['email']} (user_id: {u2_user_id})")
    
    # U1 sends friend request to U2
    resp = requests.post(
        f"{BASE_URL}/friends/request-by-username",
        json={"username": u2_username},
        headers=u1_headers
    )
    if resp.status_code != 200:
        log_test(7, False, f"Failed to send friend request: {resp.status_code} - {resp.text}")
        return
    
    request_id = resp.json()["request_id"]
    print(f"  ✓ U1 sent friend request to U2 (request_id: {request_id})")
    
    # U2 accepts friend request
    resp = requests.post(
        f"{BASE_URL}/friends/respond",
        json={"request_id": request_id, "accept": True},
        headers=u2_headers
    )
    if resp.status_code != 200:
        log_test(7, False, f"Failed to accept friend request: {resp.status_code} - {resp.text}")
        return
    
    print(f"  ✓ U2 accepted friend request")
    log_test(7, True, "U1 and U2 are now friends")
    print()

    # ========================================================================
    # STEP 8: U2 marks 'voy' on ev1 and ev2
    # ========================================================================
    print("STEP 8: U2 marks 'voy' on ev1 and ev2")
    
    resp = requests.post(
        f"{BASE_URL}/events/{ev1['id']}/interest",
        json={"status": "voy"},
        headers=u2_headers
    )
    if resp.status_code != 200:
        log_test(8, False, f"Failed to mark voy on ev1: {resp.status_code} - {resp.text}")
        return
    print(f"  ✓ U2 marked 'voy' on ev1")
    
    resp = requests.post(
        f"{BASE_URL}/events/{ev2['id']}/interest",
        json={"status": "voy"},
        headers=u2_headers
    )
    if resp.status_code != 200:
        log_test(8, False, f"Failed to mark voy on ev2: {resp.status_code} - {resp.text}")
        return
    print(f"  ✓ U2 marked 'voy' on ev2")
    
    log_test(8, True, "U2 marked 'voy' on ev1 and ev2")
    print()

    # ========================================================================
    # STEP 9: VERIFY - U1 GET /api/me/wrapped (no month param)
    # ========================================================================
    print("=" * 80)
    print("STEP 9: VERIFY - U1 GET /api/me/wrapped (no month param)")
    print("=" * 80)
    
    resp = requests.get(f"{BASE_URL}/me/wrapped", headers=u1_headers)
    if resp.status_code != 200:
        log_test(9, False, f"Failed to get wrapped: {resp.status_code} - {resp.text}")
        return
    
    wrapped = resp.json()
    print("\nWrapped Response:")
    print(json.dumps(wrapped, indent=2))
    print()
    
    # Verify all required fields
    checks = []
    
    # month == "2026-08"
    if wrapped.get("month") == "2026-08":
        checks.append(("month == '2026-08'", True))
        print("  ✅ month == '2026-08'")
    else:
        checks.append(("month == '2026-08'", False))
        print(f"  ❌ month == '{wrapped.get('month')}' (expected '2026-08')")
    
    # has_data == true
    if wrapped.get("has_data") == True:
        checks.append(("has_data == true", True))
        print("  ✅ has_data == true")
    else:
        checks.append(("has_data == true", False))
        print(f"  ❌ has_data == {wrapped.get('has_data')} (expected true)")
    
    # parties == 3
    if wrapped.get("parties") == 3:
        checks.append(("parties == 3", True))
        print("  ✅ parties == 3")
    else:
        checks.append(("parties == 3", False))
        print(f"  ❌ parties == {wrapped.get('parties')} (expected 3)")
    
    # venues == 3
    if wrapped.get("venues") == 3:
        checks.append(("venues == 3", True))
        print("  ✅ venues == 3")
    else:
        checks.append(("venues == 3", False))
        print(f"  ❌ venues == {wrapped.get('venues')} (expected 3)")
    
    # top_venue is not null
    if wrapped.get("top_venue") is not None:
        checks.append(("top_venue is not null", True))
        print(f"  ✅ top_venue is not null: {wrapped.get('top_venue')}")
    else:
        checks.append(("top_venue is not null", False))
        print(f"  ❌ top_venue is null")
    
    # top_genre == "Reggaeton"
    if wrapped.get("top_genre") == "Reggaeton":
        checks.append(("top_genre == 'Reggaeton'", True))
        print("  ✅ top_genre == 'Reggaeton'")
    else:
        checks.append(("top_genre == 'Reggaeton'", False))
        print(f"  ❌ top_genre == '{wrapped.get('top_genre')}' (expected 'Reggaeton')")
    
    # photos >= 1
    if wrapped.get("photos", 0) >= 1:
        checks.append(("photos >= 1", True))
        print(f"  ✅ photos >= 1 (actual: {wrapped.get('photos')})")
    else:
        checks.append(("photos >= 1", False))
        print(f"  ❌ photos == {wrapped.get('photos')} (expected >= 1)")
    
    # moments >= 1
    if wrapped.get("moments", 0) >= 1:
        checks.append(("moments >= 1", True))
        print(f"  ✅ moments >= 1 (actual: {wrapped.get('moments')})")
    else:
        checks.append(("moments >= 1", False))
        print(f"  ❌ moments == {wrapped.get('moments')} (expected >= 1)")
    
    # friends_coincided >= 1
    if wrapped.get("friends_coincided", 0) >= 1:
        checks.append(("friends_coincided >= 1", True))
        print(f"  ✅ friends_coincided >= 1 (actual: {wrapped.get('friends_coincided')})")
    else:
        checks.append(("friends_coincided >= 1", False))
        print(f"  ❌ friends_coincided == {wrapped.get('friends_coincided')} (expected >= 1)")
    
    # top_friends is non-empty list containing U2
    top_friends = wrapped.get("top_friends", [])
    if isinstance(top_friends, list) and len(top_friends) > 0:
        u2_display_name = f"@{u2_username.lower()}"
        u2_in_top_friends = any(friend.get("name") == u2_display_name for friend in top_friends)
        if u2_in_top_friends:
            checks.append(("top_friends contains U2", True))
            print(f"  ✅ top_friends is non-empty and contains U2 ({u2_display_name})")
        else:
            checks.append(("top_friends contains U2", False))
            print(f"  ❌ top_friends does not contain U2 ({u2_display_name})")
            print(f"     top_friends: {top_friends}")
    else:
        checks.append(("top_friends is non-empty", False))
        print(f"  ❌ top_friends is empty or not a list: {top_friends}")
    
    # title is non-empty string
    if isinstance(wrapped.get("title"), str) and len(wrapped.get("title", "")) > 0:
        checks.append(("title is non-empty string", True))
        print(f"  ✅ title is non-empty string: '{wrapped.get('title')}'")
    else:
        checks.append(("title is non-empty string", False))
        print(f"  ❌ title is not a non-empty string: {wrapped.get('title')}")
    
    all_passed = all(check[1] for check in checks)
    log_test(9, all_passed, f"Wrapped verification: {sum(1 for c in checks if c[1])}/{len(checks)} checks passed")
    print()

    # ========================================================================
    # STEP 10: VERIFY - U1 GET /api/me/wrapped?month=2020-01 (empty month)
    # ========================================================================
    print("=" * 80)
    print("STEP 10: VERIFY - U1 GET /api/me/wrapped?month=2020-01 (empty month)")
    print("=" * 80)
    
    resp = requests.get(f"{BASE_URL}/me/wrapped?month=2020-01", headers=u1_headers)
    if resp.status_code != 200:
        log_test(10, False, f"Failed to get wrapped for 2020-01: {resp.status_code} - {resp.text}")
        return
    
    wrapped_empty = resp.json()
    print("\nWrapped Response (2020-01):")
    print(json.dumps(wrapped_empty, indent=2))
    print()
    
    checks_empty = []
    
    # has_data == false
    if wrapped_empty.get("has_data") == False:
        checks_empty.append(("has_data == false", True))
        print("  ✅ has_data == false")
    else:
        checks_empty.append(("has_data == false", False))
        print(f"  ❌ has_data == {wrapped_empty.get('has_data')} (expected false)")
    
    # parties == 0
    if wrapped_empty.get("parties") == 0:
        checks_empty.append(("parties == 0", True))
        print("  ✅ parties == 0")
    else:
        checks_empty.append(("parties == 0", False))
        print(f"  ❌ parties == {wrapped_empty.get('parties')} (expected 0)")
    
    # month == "2020-01"
    if wrapped_empty.get("month") == "2020-01":
        checks_empty.append(("month == '2020-01'", True))
        print("  ✅ month == '2020-01'")
    else:
        checks_empty.append(("month == '2020-01'", False))
        print(f"  ❌ month == '{wrapped_empty.get('month')}' (expected '2020-01')")
    
    # month_label is non-empty string
    if isinstance(wrapped_empty.get("month_label"), str) and len(wrapped_empty.get("month_label", "")) > 0:
        checks_empty.append(("month_label is non-empty", True))
        print(f"  ✅ month_label is non-empty: '{wrapped_empty.get('month_label')}'")
    else:
        checks_empty.append(("month_label is non-empty", False))
        print(f"  ❌ month_label is empty or not a string: {wrapped_empty.get('month_label')}")
    
    all_passed_empty = all(check[1] for check in checks_empty)
    log_test(10, all_passed_empty, f"Empty month verification: {sum(1 for c in checks_empty if c[1])}/{len(checks_empty)} checks passed")
    print()

    # ========================================================================
    # STEP 11: VERIFY - U1 GET /api/me/wrapped?month=2026-08 (explicit month)
    # ========================================================================
    print("=" * 80)
    print("STEP 11: VERIFY - U1 GET /api/me/wrapped?month=2026-08 (explicit month)")
    print("=" * 80)
    
    resp = requests.get(f"{BASE_URL}/me/wrapped?month=2026-08", headers=u1_headers)
    if resp.status_code != 200:
        log_test(11, False, f"Failed to get wrapped for 2026-08: {resp.status_code} - {resp.text}")
        return
    
    wrapped_explicit = resp.json()
    print("\nWrapped Response (2026-08 explicit):")
    print(json.dumps(wrapped_explicit, indent=2))
    print()
    
    # Verify same numbers as step 9
    checks_explicit = []
    
    if wrapped_explicit.get("parties") == wrapped.get("parties"):
        checks_explicit.append(("parties matches default", True))
        print(f"  ✅ parties == {wrapped_explicit.get('parties')} (matches default)")
    else:
        checks_explicit.append(("parties matches default", False))
        print(f"  ❌ parties == {wrapped_explicit.get('parties')} (expected {wrapped.get('parties')})")
    
    if wrapped_explicit.get("venues") == wrapped.get("venues"):
        checks_explicit.append(("venues matches default", True))
        print(f"  ✅ venues == {wrapped_explicit.get('venues')} (matches default)")
    else:
        checks_explicit.append(("venues matches default", False))
        print(f"  ❌ venues == {wrapped_explicit.get('venues')} (expected {wrapped.get('venues')})")
    
    if wrapped_explicit.get("top_genre") == wrapped.get("top_genre"):
        checks_explicit.append(("top_genre matches default", True))
        print(f"  ✅ top_genre == '{wrapped_explicit.get('top_genre')}' (matches default)")
    else:
        checks_explicit.append(("top_genre matches default", False))
        print(f"  ❌ top_genre == '{wrapped_explicit.get('top_genre')}' (expected '{wrapped.get('top_genre')}')")
    
    if wrapped_explicit.get("photos") == wrapped.get("photos"):
        checks_explicit.append(("photos matches default", True))
        print(f"  ✅ photos == {wrapped_explicit.get('photos')} (matches default)")
    else:
        checks_explicit.append(("photos matches default", False))
        print(f"  ❌ photos == {wrapped_explicit.get('photos')} (expected {wrapped.get('photos')})")
    
    if wrapped_explicit.get("moments") == wrapped.get("moments"):
        checks_explicit.append(("moments matches default", True))
        print(f"  ✅ moments == {wrapped_explicit.get('moments')} (matches default)")
    else:
        checks_explicit.append(("moments matches default", False))
        print(f"  ❌ moments == {wrapped_explicit.get('moments')} (expected {wrapped.get('moments')})")
    
    if wrapped_explicit.get("friends_coincided") == wrapped.get("friends_coincided"):
        checks_explicit.append(("friends_coincided matches default", True))
        print(f"  ✅ friends_coincided == {wrapped_explicit.get('friends_coincided')} (matches default)")
    else:
        checks_explicit.append(("friends_coincided matches default", False))
        print(f"  ❌ friends_coincided == {wrapped_explicit.get('friends_coincided')} (expected {wrapped.get('friends_coincided')})")
    
    all_passed_explicit = all(check[1] for check in checks_explicit)
    log_test(11, all_passed_explicit, f"Explicit month verification: {sum(1 for c in checks_explicit if c[1])}/{len(checks_explicit)} checks passed")
    print()

    # ========================================================================
    # FINAL SUMMARY
    # ========================================================================
    print("=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80)
    print()
    
    for result in test_results:
        print(result)
    
    print()
    total_tests = len(test_results)
    passed_tests = sum(1 for r in test_results if r.startswith("✅"))
    
    if passed_tests == total_tests:
        print(f"🎉 ALL TESTS PASSED: {passed_tests}/{total_tests}")
        print()
        print("WRAPPED ENDPOINT VERIFICATION COMPLETE:")
        print(f"  - Default month (2026-08): parties={wrapped.get('parties')}, venues={wrapped.get('venues')}, top_genre={wrapped.get('top_genre')}")
        print(f"  - Photos: {wrapped.get('photos')}, Moments: {wrapped.get('moments')}")
        print(f"  - Friends coincided: {wrapped.get('friends_coincided')}")
        print(f"  - Top friends: {[f.get('name') for f in wrapped.get('top_friends', [])]}")
        print(f"  - Empty month (2020-01): has_data={wrapped_empty.get('has_data')}, parties={wrapped_empty.get('parties')}")
        print(f"  - Explicit month (2026-08): matches default values ✓")
    else:
        print(f"❌ SOME TESTS FAILED: {passed_tests}/{total_tests} passed")
        print()
        print("Failed tests:")
        for result in test_results:
            if result.startswith("❌"):
                print(f"  {result}")

if __name__ == "__main__":
    main()
