#!/usr/bin/env python3
"""
Backend testing for Sprint 2+3 changes:
- (A) COUNTS SPLIT IN SERIALIZER: going_count, interested_count, my_intent
- (B) PATCH /api/events/{event_id}/intent endpoint
- (C) GET /api/events/{event_id}/people?status=voy|me_interesa|estuve
- (D) CONVERSION METRICS: guest_views tracking and GET /api/admin/landing-metrics
"""

import requests
import os
import sys
from datetime import datetime, timedelta

# Base URL from environment
BASE_URL = os.getenv("REACT_APP_BACKEND_URL", "http://localhost:8001")
API_URL = f"{BASE_URL}/api"

# Admin credentials from test_credentials.md
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

# Test results
test_results = []

def log_test(test_name, passed, details=""):
    """Log test result"""
    status = "✅ PASS" if passed else "❌ FAIL"
    test_results.append({"name": test_name, "passed": passed, "details": details})
    print(f"{status}: {test_name}")
    if details:
        print(f"  Details: {details}")

def admin_login():
    """Login as admin and return token"""
    resp = requests.post(f"{API_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if resp.status_code != 200:
        print(f"❌ Admin login failed: {resp.status_code} {resp.text}")
        sys.exit(1)
    token = resp.json()["token"]
    print(f"✅ Admin login successful")
    return token

def create_test_user(suffix):
    """Create a test user and return (user_id, token)"""
    # Calculate birthdate for 18+ requirement (born in 1995)
    birthdate = "1995-01-01"
    
    username = f"testuser_{suffix}_{datetime.now().timestamp()}"
    email = f"{username}@test.com"
    
    resp = requests.post(f"{API_URL}/auth/register", json={
        "name": f"Test User {suffix}",
        "username": username,
        "email": email,
        "password": "testpass123",
        "birthdate": birthdate
    })
    
    if resp.status_code != 200:
        print(f"❌ Failed to create test user {suffix}: {resp.status_code} {resp.text}")
        sys.exit(1)
    
    data = resp.json()
    print(f"✅ Created test user: {username} (user_id: {data['user']['user_id']})")
    return data["user"]["user_id"], data["token"]

def get_first_event(token=None):
    """Get the first event from the events list"""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    resp = requests.get(f"{API_URL}/events", headers=headers)
    if resp.status_code != 200:
        print(f"❌ Failed to get events: {resp.status_code}")
        return None
    
    events = resp.json()
    if not events:
        print(f"❌ No events found in database")
        return None
    
    return events[0]

def main():
    print("=" * 80)
    print("SPRINT 2+3 BACKEND TESTING")
    print("=" * 80)
    print()
    
    # Login as admin
    admin_token = admin_login()
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    
    # Create 3 test users
    print("\n--- Creating test users ---")
    user1_id, user1_token = create_test_user("A")
    user2_id, user2_token = create_test_user("B")
    user3_id, user3_token = create_test_user("C")
    
    user1_headers = {"Authorization": f"Bearer {user1_token}"}
    user2_headers = {"Authorization": f"Bearer {user2_token}"}
    user3_headers = {"Authorization": f"Bearer {user3_token}"}
    
    # Get a test event
    print("\n--- Getting test event ---")
    event = get_first_event(admin_token)
    if not event:
        print("❌ Cannot proceed without events in database")
        sys.exit(1)
    
    event_id = event["id"]
    print(f"✅ Using test event: {event['name']} (id: {event_id})")
    
    print("\n" + "=" * 80)
    print("(A) COUNTS SPLIT IN SERIALIZER")
    print("=" * 80)
    
    # Test A1: GET /api/events as guest - check for going_count, interested_count, my_intent
    print("\n--- Test A1: GET /api/events as guest ---")
    resp = requests.get(f"{API_URL}/events")
    if resp.status_code == 200:
        events = resp.json()
        if events:
            first_event = events[0]
            has_going_count = "going_count" in first_event and isinstance(first_event["going_count"], int)
            has_interested_count = "interested_count" in first_event and isinstance(first_event["interested_count"], int)
            has_my_intent = "my_intent" in first_event and isinstance(first_event["my_intent"], str)
            my_intent_is_none = first_event.get("my_intent") == "none"
            
            # Check backward compatibility
            has_total_going = "total_going" in first_event
            has_total_interested = "total_interested" in first_event
            has_total_attended = "total_attended" in first_event
            
            all_passed = (has_going_count and has_interested_count and has_my_intent and 
                         my_intent_is_none and has_total_going and has_total_interested and has_total_attended)
            
            details = f"going_count: {first_event.get('going_count')} (int: {has_going_count}), " \
                     f"interested_count: {first_event.get('interested_count')} (int: {has_interested_count}), " \
                     f"my_intent: '{first_event.get('my_intent')}' (is 'none': {my_intent_is_none}), " \
                     f"backward compat: total_going={has_total_going}, total_interested={has_total_interested}, total_attended={has_total_attended}"
            
            log_test("A1: GET /api/events as guest has going_count, interested_count, my_intent='none'", 
                    all_passed, details)
        else:
            log_test("A1: GET /api/events as guest", False, "No events returned")
    else:
        log_test("A1: GET /api/events as guest", False, f"Status {resp.status_code}")
    
    # Test A2: GET /api/events/{event_id} as guest
    print("\n--- Test A2: GET /api/events/{event_id} as guest ---")
    resp = requests.get(f"{API_URL}/events/{event_id}")
    if resp.status_code == 200:
        event_detail = resp.json()
        has_going_count = "going_count" in event_detail and isinstance(event_detail["going_count"], int)
        has_interested_count = "interested_count" in event_detail and isinstance(event_detail["interested_count"], int)
        has_my_intent = "my_intent" in event_detail and isinstance(event_detail["my_intent"], str)
        my_intent_is_none = event_detail.get("my_intent") == "none"
        
        all_passed = has_going_count and has_interested_count and has_my_intent and my_intent_is_none
        
        details = f"going_count: {event_detail.get('going_count')}, " \
                 f"interested_count: {event_detail.get('interested_count')}, " \
                 f"my_intent: '{event_detail.get('my_intent')}'"
        
        log_test("A2: GET /api/events/{id} as guest has correct fields", all_passed, details)
    else:
        log_test("A2: GET /api/events/{id} as guest", False, f"Status {resp.status_code}")
    
    print("\n" + "=" * 80)
    print("(B) PATCH /api/events/{event_id}/intent")
    print("=" * 80)
    
    # Get baseline counts
    resp = requests.get(f"{API_URL}/events/{event_id}", headers=user1_headers)
    baseline_event = resp.json()
    baseline_going = baseline_event.get("going_count", 0)
    baseline_interested = baseline_event.get("interested_count", 0)
    print(f"Baseline counts: going={baseline_going}, interested={baseline_interested}")
    
    # Test B1: PATCH with intent="interested"
    print("\n--- Test B1: PATCH /api/events/{event_id}/intent with 'interested' ---")
    resp = requests.patch(f"{API_URL}/events/{event_id}/intent", 
                         json={"intent": "interested"}, 
                         headers=user1_headers)
    if resp.status_code == 200:
        data = resp.json()
        correct_status = data.get("status") == "me_interesa"
        correct_intent = data.get("intent") == "interested"
        
        log_test("B1: PATCH intent='interested' returns correct response", 
                correct_status and correct_intent,
                f"status: {data.get('status')}, intent: {data.get('intent')}")
        
        # Verify counts changed
        resp2 = requests.get(f"{API_URL}/events/{event_id}", headers=user1_headers)
        if resp2.status_code == 200:
            updated_event = resp2.json()
            new_interested = updated_event.get("interested_count", 0)
            my_intent = updated_event.get("my_intent")
            
            count_increased = new_interested == baseline_interested + 1
            intent_correct = my_intent == "interested"
            
            log_test("B1: interested_count incremented and my_intent='interested'",
                    count_increased and intent_correct,
                    f"interested_count: {baseline_interested} -> {new_interested}, my_intent: {my_intent}")
    else:
        log_test("B1: PATCH intent='interested'", False, f"Status {resp.status_code}: {resp.text}")
    
    # Test B2: PATCH with intent="going" on SAME event (should update, not duplicate)
    print("\n--- Test B2: PATCH /api/events/{event_id}/intent with 'going' (update) ---")
    resp = requests.patch(f"{API_URL}/events/{event_id}/intent", 
                         json={"intent": "going"}, 
                         headers=user1_headers)
    if resp.status_code == 200:
        data = resp.json()
        correct_status = data.get("status") == "voy"
        correct_intent = data.get("intent") == "going"
        
        log_test("B2: PATCH intent='going' returns correct response", 
                correct_status and correct_intent,
                f"status: {data.get('status')}, intent: {data.get('intent')}")
        
        # Verify counts: going should increase by 1, interested should go back to baseline
        resp2 = requests.get(f"{API_URL}/events/{event_id}", headers=user1_headers)
        if resp2.status_code == 200:
            updated_event = resp2.json()
            new_going = updated_event.get("going_count", 0)
            new_interested = updated_event.get("interested_count", 0)
            my_intent = updated_event.get("my_intent")
            
            going_increased = new_going == baseline_going + 1
            interested_back = new_interested == baseline_interested
            intent_correct = my_intent == "going"
            
            all_correct = going_increased and interested_back and intent_correct
            
            log_test("B2: going_count +1, interested_count back to baseline, my_intent='going'",
                    all_correct,
                    f"going: {baseline_going} -> {new_going}, interested: {baseline_interested} -> {new_interested}, my_intent: {my_intent}")
    else:
        log_test("B2: PATCH intent='going'", False, f"Status {resp.status_code}: {resp.text}")
    
    # Test B3: PATCH with invalid intent
    print("\n--- Test B3: PATCH with invalid intent ---")
    resp = requests.patch(f"{API_URL}/events/{event_id}/intent", 
                         json={"intent": "xxx"}, 
                         headers=user1_headers)
    log_test("B3: PATCH intent='xxx' returns 400", resp.status_code == 400, f"Status: {resp.status_code}")
    
    # Test B4: PATCH on non-existent event
    print("\n--- Test B4: PATCH on non-existent event ---")
    resp = requests.patch(f"{API_URL}/events/nonexistent-id-12345/intent", 
                         json={"intent": "going"}, 
                         headers=user1_headers)
    log_test("B4: PATCH on non-existent event returns 404", resp.status_code == 404, f"Status: {resp.status_code}")
    
    # Test B5: PATCH without auth
    print("\n--- Test B5: PATCH without auth ---")
    resp = requests.patch(f"{API_URL}/events/{event_id}/intent", 
                         json={"intent": "going"})
    log_test("B5: PATCH without auth returns 401", resp.status_code == 401, f"Status: {resp.status_code}")
    
    print("\n" + "=" * 80)
    print("(C) GET /api/events/{event_id}/people")
    print("=" * 80)
    
    # Setup: Have user2 and user3 mark "going" on the event
    print("\n--- Setup: User2 and User3 mark 'going' ---")
    requests.patch(f"{API_URL}/events/{event_id}/intent", 
                  json={"intent": "going"}, 
                  headers=user2_headers)
    requests.patch(f"{API_URL}/events/{event_id}/intent", 
                  json={"intent": "going"}, 
                  headers=user3_headers)
    print("✅ User2 and User3 marked as going")
    
    # Test C1: GET /api/events/{event_id}/people?status=voy as logged-in user
    print("\n--- Test C1: GET /api/events/{event_id}/people?status=voy ---")
    resp = requests.get(f"{API_URL}/events/{event_id}/people?status=voy", 
                       headers=user1_headers)
    if resp.status_code == 200:
        data = resp.json()
        has_event_id = "event_id" in data
        has_status = data.get("status") == "voy"
        has_count = "count" in data and isinstance(data["count"], int)
        has_people = "people" in data and isinstance(data["people"], list)
        
        # Check people structure
        people = data.get("people", [])
        count_matches = data.get("count") == len(people)
        
        # Check if user1 (requesting user) appears with is_me=true
        user1_in_list = any(p.get("user_id") == user1_id and p.get("is_me") == True for p in people)
        
        # Check if user1 is sorted first
        user1_first = people[0].get("user_id") == user1_id if people else False
        
        # Check people have required fields
        all_have_fields = all(
            "user_id" in p and "name" in p and "username" in p and 
            "picture" in p and "is_friend" in p and "is_me" in p
            for p in people
        )
        
        # Check name is @username format (not real name)
        all_usernames = all(p.get("name", "").startswith("@") for p in people)
        
        all_passed = (has_event_id and has_status and has_count and has_people and 
                     count_matches and user1_in_list and user1_first and 
                     all_have_fields and all_usernames)
        
        details = f"event_id: {has_event_id}, status: {has_status}, count: {data.get('count')}, " \
                 f"people count: {len(people)}, count matches: {count_matches}, " \
                 f"user1 in list: {user1_in_list}, user1 first: {user1_first}, " \
                 f"all have fields: {all_have_fields}, all @usernames: {all_usernames}"
        
        log_test("C1: GET people?status=voy returns correct structure", all_passed, details)
    else:
        log_test("C1: GET people?status=voy", False, f"Status {resp.status_code}: {resp.text}")
    
    # Test C2: Invalid status
    print("\n--- Test C2: GET people with invalid status ---")
    resp = requests.get(f"{API_URL}/events/{event_id}/people?status=foo", 
                       headers=user1_headers)
    log_test("C2: GET people?status=foo returns 400", resp.status_code == 400, f"Status: {resp.status_code}")
    
    # Test C3: Non-existent event
    print("\n--- Test C3: GET people for non-existent event ---")
    resp = requests.get(f"{API_URL}/events/nonexistent-id-12345/people?status=voy", 
                       headers=user1_headers)
    log_test("C3: GET people for non-existent event returns 404", resp.status_code == 404, f"Status: {resp.status_code}")
    
    # Test C4: Without auth
    print("\n--- Test C4: GET people without auth ---")
    resp = requests.get(f"{API_URL}/events/{event_id}/people?status=voy")
    log_test("C4: GET people without auth returns 401", resp.status_code == 401, f"Status: {resp.status_code}")
    
    # Test C5: Privacy test - user with attendance_privacy="nadie" should not appear
    print("\n--- Test C5: Privacy test (attendance_privacy='nadie') ---")
    # First, set user3's attendance_privacy to "nadie"
    resp = requests.put(f"{API_URL}/auth/profile", 
                       json={"attendance_privacy": "nadie"}, 
                       headers=user3_headers)
    if resp.status_code == 200:
        # Now check if user3 appears in the people list
        resp2 = requests.get(f"{API_URL}/events/{event_id}/people?status=voy", 
                           headers=user1_headers)
        if resp2.status_code == 200:
            people = resp2.json().get("people", [])
            user3_in_list = any(p.get("user_id") == user3_id for p in people)
            
            log_test("C5: User with attendance_privacy='nadie' does NOT appear in people list",
                    not user3_in_list,
                    f"user3 in list: {user3_in_list} (should be False)")
        else:
            log_test("C5: Privacy test", False, f"Failed to get people list: {resp2.status_code}")
    else:
        log_test("C5: Privacy test", False, f"Failed to set privacy: {resp.status_code}")
    
    print("\n" + "=" * 80)
    print("(D) CONVERSION METRICS")
    print("=" * 80)
    
    # Test D1: GET /api/events/{event_id} as guest increments guest_views
    print("\n--- Test D1: GET /api/events/{event_id} as guest increments guest_views ---")
    # Get current guest_views from admin metrics
    resp = requests.get(f"{API_URL}/admin/landing-metrics", headers=admin_headers)
    if resp.status_code == 200:
        before_data = resp.json()
        before_guest_views = before_data.get("totals", {}).get("guest_views", 0)
        
        # Make a guest request (no auth)
        resp2 = requests.get(f"{API_URL}/events/{event_id}")
        guest_request_ok = resp2.status_code == 200
        
        # Wait a moment for the fire-and-forget update
        import time
        time.sleep(1)
        
        # Check if guest_views increased
        resp3 = requests.get(f"{API_URL}/admin/landing-metrics", headers=admin_headers)
        if resp3.status_code == 200:
            after_data = resp3.json()
            after_guest_views = after_data.get("totals", {}).get("guest_views", 0)
            
            guest_views_increased = after_guest_views >= before_guest_views + 1
            
            log_test("D1: GET /api/events/{id} as guest increments guest_views",
                    guest_request_ok and guest_views_increased,
                    f"guest_views: {before_guest_views} -> {after_guest_views}, guest request: {guest_request_ok}")
        else:
            log_test("D1: guest_views increment", False, f"Failed to get metrics after: {resp3.status_code}")
    else:
        log_test("D1: guest_views increment", False, f"Failed to get metrics before: {resp.status_code}")
    
    # Test D2: POST /api/metrics/event-signup
    print("\n--- Test D2: POST /api/metrics/event-signup ---")
    resp = requests.get(f"{API_URL}/admin/landing-metrics", headers=admin_headers)
    if resp.status_code == 200:
        before_data = resp.json()
        before_signups = before_data.get("totals", {}).get("signups", 0)
        
        # Post signup metric (no auth needed)
        resp2 = requests.post(f"{API_URL}/metrics/event-signup", 
                             json={"event_id": event_id})
        signup_ok = resp2.status_code == 200 and resp2.json().get("ok") == True
        
        # Wait a moment
        import time
        time.sleep(1)
        
        # Check if signups increased
        resp3 = requests.get(f"{API_URL}/admin/landing-metrics", headers=admin_headers)
        if resp3.status_code == 200:
            after_data = resp3.json()
            after_signups = after_data.get("totals", {}).get("signups", 0)
            
            signups_increased = after_signups >= before_signups + 1
            
            log_test("D2: POST /api/metrics/event-signup increments signups",
                    signup_ok and signups_increased,
                    f"signups: {before_signups} -> {after_signups}, post ok: {signup_ok}")
        else:
            log_test("D2: signups increment", False, f"Failed to get metrics after: {resp3.status_code}")
    else:
        log_test("D2: signups increment", False, f"Failed to get metrics before: {resp.status_code}")
    
    # Test D3: GET /api/admin/landing-metrics as admin
    print("\n--- Test D3: GET /api/admin/landing-metrics as admin ---")
    resp = requests.get(f"{API_URL}/admin/landing-metrics", headers=admin_headers)
    if resp.status_code == 200:
        data = resp.json()
        has_totals = "totals" in data
        has_events = "events" in data and isinstance(data["events"], list)
        
        totals = data.get("totals", {})
        has_views = "views" in totals
        has_guest_views = "guest_views" in totals
        has_signups = "signups" in totals
        has_conversion = "conversion" in totals
        
        totals_ok = has_views and has_guest_views and has_signups and has_conversion
        
        # Check if our test event appears in events list
        events = data.get("events", [])
        test_event_in_list = any(e.get("event_id") == event_id for e in events)
        
        # Check event structure
        if test_event_in_list:
            test_event_data = next(e for e in events if e.get("event_id") == event_id)
            event_has_guest_views = "guest_views" in test_event_data and test_event_data["guest_views"] >= 1
            event_has_signups = "signups" in test_event_data and test_event_data["signups"] >= 1
        else:
            event_has_guest_views = False
            event_has_signups = False
        
        all_passed = has_totals and has_events and totals_ok and test_event_in_list and event_has_guest_views and event_has_signups
        
        details = f"totals: {totals_ok}, events: {has_events}, test_event in list: {test_event_in_list}, " \
                 f"event guest_views>=1: {event_has_guest_views}, event signups>=1: {event_has_signups}"
        
        log_test("D3: GET /api/admin/landing-metrics returns correct structure", all_passed, details)
    else:
        log_test("D3: GET /api/admin/landing-metrics as admin", False, f"Status {resp.status_code}: {resp.text}")
    
    # Test D4: GET /api/admin/landing-metrics as non-admin
    print("\n--- Test D4: GET /api/admin/landing-metrics as non-admin ---")
    resp = requests.get(f"{API_URL}/admin/landing-metrics", headers=user1_headers)
    log_test("D4: GET /api/admin/landing-metrics as non-admin returns 403", 
            resp.status_code == 403, f"Status: {resp.status_code}")
    
    # Test D5: GET /api/admin/landing-metrics without auth
    print("\n--- Test D5: GET /api/admin/landing-metrics without auth ---")
    resp = requests.get(f"{API_URL}/admin/landing-metrics")
    log_test("D5: GET /api/admin/landing-metrics without auth returns 401", 
            resp.status_code == 401, f"Status: {resp.status_code}")
    
    # Test D6: Light regression - GET /api/events still returns 200
    print("\n--- Test D6: Regression - GET /api/events ---")
    resp = requests.get(f"{API_URL}/events")
    log_test("D6: GET /api/events returns 200", resp.status_code == 200, f"Status: {resp.status_code}")
    
    # Print summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    total_tests = len(test_results)
    passed_tests = sum(1 for t in test_results if t["passed"])
    failed_tests = total_tests - passed_tests
    
    print(f"\nTotal tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {failed_tests}")
    print(f"Success rate: {passed_tests/total_tests*100:.1f}%")
    
    if failed_tests > 0:
        print("\n❌ FAILED TESTS:")
        for t in test_results:
            if not t["passed"]:
                print(f"  - {t['name']}")
                if t["details"]:
                    print(f"    {t['details']}")
    
    print("\n" + "=" * 80)
    
    return failed_tests == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
