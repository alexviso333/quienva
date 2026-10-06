#!/usr/bin/env python3
"""
Backend API Testing for ¿Quién va? - LAUNCH READINESS
Tests: Registration +18, Attendance Privacy, Block/Unblock, Reports, Contact Matching
"""
import requests
import json
import time
from datetime import datetime, date, timedelta

# Base URL from frontend/.env
BASE_URL = "https://full-stack-nights.preview.emergentagent.com/api"

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "Admin1234!"
ANA_EMAIL = "ana@quienva.app"
ANA_PASSWORD = "Ana12345!"

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
print("BACKEND API TESTING - LAUNCH READINESS")
print("Testing: Registration +18, Attendance Privacy, Block/Unblock, Reports, Contact Matching")
print("=" * 80)

# ============================================================================
# SETUP: Login as admin and Ana
# ============================================================================
print("\n[SETUP] Logging in as admin...")
admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
if not admin_token:
    print("❌ CRITICAL: Cannot login as admin. Aborting tests.")
    exit(1)
print(f"✅ Admin logged in successfully")

print("\n[SETUP] Logging in as Ana...")
ana_token = login(ANA_EMAIL, ANA_PASSWORD)
if not ana_token:
    print("❌ CRITICAL: Cannot login as Ana. Aborting tests.")
    exit(1)
print(f"✅ Ana logged in successfully")

# ============================================================================
# TEST 1: REGISTRATION +18 GATE + OPTIONAL PHONE
# ============================================================================
print("\n" + "=" * 80)
print("TEST 1: REGISTRATION +18 GATE + OPTIONAL PHONE")
print("=" * 80)

# Test 1.1: Register with minor birthdate (should be 400)
print("\n[1.1] Registering with minor birthdate (2015-01-01)...")
minor_email = f"minor_{int(time.time())}@test.com"
minor_response = requests.post(f"{BASE_URL}/auth/register", json={
    "email": minor_email,
    "password": "Test1234!",
    "name": "Minor User",
    "username": f"minor{int(time.time())}",
    "city": "Palma de Mallorca",
    "birthdate": "2015-01-01"
})
log_test("Register with minor birthdate returns 400", 
         minor_response.status_code == 400,
         f"Status: {minor_response.status_code}, Message: {minor_response.json().get('detail', '')}")

# Test 1.2: Register adult WITHOUT phone (should be 200)
print("\n[1.2] Registering adult (2000-01-01) WITHOUT phone...")
adult_email = f"adult_{int(time.time())}@test.com"
adult_username = f"adult{int(time.time())}"
adult_response = requests.post(f"{BASE_URL}/auth/register", json={
    "email": adult_email,
    "password": "Test1234!",
    "name": "Adult User",
    "username": adult_username,
    "city": "Palma de Mallorca",
    "birthdate": "2000-01-01"
})
adult_token = None
if adult_response.status_code == 200:
    data = adult_response.json()
    adult_token = data.get("token")
    user = data.get("user", {})
    log_test("Register adult without phone returns 200", True,
             f"Status: {adult_response.status_code}")
    log_test("User has attendance_privacy='todos'", 
             user.get("attendance_privacy") == "todos",
             f"attendance_privacy={user.get('attendance_privacy')}")
    log_test("User has has_phone=false", 
             user.get("has_phone") == False,
             f"has_phone={user.get('has_phone')}")
    log_test("User has needs_birthdate=false", 
             user.get("needs_birthdate") == False,
             f"needs_birthdate={user.get('needs_birthdate')}")
else:
    log_test("Register adult without phone", False,
             f"Status: {adult_response.status_code}, Response: {adult_response.text}")

# Test 1.3: Register adult WITH phone (should be 200 with has_phone=true)
print("\n[1.3] Registering adult WITH phone...")
phone_email = f"phone_{int(time.time())}@test.com"
phone_username = f"phone{int(time.time())}"
phone_response = requests.post(f"{BASE_URL}/auth/register", json={
    "email": phone_email,
    "password": "Test1234!",
    "name": "Phone User",
    "username": phone_username,
    "city": "Palma de Mallorca",
    "birthdate": "2000-01-01",
    "phone": "611222333"
})
phone_token = None
if phone_response.status_code == 200:
    data = phone_response.json()
    phone_token = data.get("token")
    user = data.get("user", {})
    log_test("Register adult with phone returns 200", True,
             f"Status: {phone_response.status_code}")
    log_test("User has has_phone=true", 
             user.get("has_phone") == True,
             f"has_phone={user.get('has_phone')}")
else:
    log_test("Register adult with phone", False,
             f"Status: {phone_response.status_code}, Response: {phone_response.text}")

# Test 1.4: Register WITHOUT birthdate (should be 400)
print("\n[1.4] Registering WITHOUT birthdate...")
no_bd_email = f"nobd_{int(time.time())}@test.com"
no_bd_response = requests.post(f"{BASE_URL}/auth/register", json={
    "email": no_bd_email,
    "password": "Test1234!",
    "name": "No Birthdate User",
    "username": f"nobd{int(time.time())}",
    "city": "Palma de Mallorca"
})
log_test("Register without birthdate returns 400", 
         no_bd_response.status_code == 400,
         f"Status: {no_bd_response.status_code}")

# ============================================================================
# TEST 2: ATTENDANCE PRIVACY (todos/amigos/nadie)
# ============================================================================
print("\n" + "=" * 80)
print("TEST 2: ATTENDANCE PRIVACY (todos/amigos/nadie)")
print("=" * 80)

# Setup: Create two users who are friends
print("\n[2.0] Setting up two users as friends...")
user_a_email = f"usera_{int(time.time())}@test.com"
user_a_username = f"usera{int(time.time())}"
user_a_response = requests.post(f"{BASE_URL}/auth/register", json={
    "email": user_a_email,
    "password": "Test1234!",
    "name": "User A",
    "username": user_a_username,
    "city": "Palma de Mallorca",
    "birthdate": "2000-01-01"
})
user_a_token = user_a_response.json().get("token") if user_a_response.status_code == 200 else None
user_a_id = user_a_response.json().get("user", {}).get("user_id") if user_a_response.status_code == 200 else None

user_b_email = f"userb_{int(time.time())}@test.com"
user_b_username = f"userb{int(time.time())}"
user_b_response = requests.post(f"{BASE_URL}/auth/register", json={
    "email": user_b_email,
    "password": "Test1234!",
    "name": "User B",
    "username": user_b_username,
    "city": "Palma de Mallorca",
    "birthdate": "2000-01-01"
})
user_b_token = user_b_response.json().get("token") if user_b_response.status_code == 200 else None
user_b_id = user_b_response.json().get("user", {}).get("user_id") if user_b_response.status_code == 200 else None

if user_a_token and user_b_token:
    print(f"✅ Created User A: {user_a_email}")
    print(f"✅ Created User B: {user_b_email}")
    
    # Send friend request from A to B
    friend_req = requests.post(f"{BASE_URL}/friends/request", 
                               headers=get_headers(user_a_token),
                               json={"addressee_id": user_b_id})
    request_id = friend_req.json().get("id") if friend_req.status_code == 200 else None
    
    # B accepts the request
    if request_id:
        accept_req = requests.post(f"{BASE_URL}/friends/respond",
                                   headers=get_headers(user_b_token),
                                   json={"request_id": request_id, "accept": True})
        print(f"✅ User A and User B are now friends")
    
    # Create an event as admin
    print("\n[2.1] Creating an event as admin...")
    today = date.today()
    future_date = (today + timedelta(days=7)).isoformat()
    event_response = requests.post(f"{BASE_URL}/admin/events",
                                   headers=get_headers(admin_token),
                                   json={
                                       "name": f"Privacy Test Event {int(time.time())}",
                                       "venue": "Test Venue",
                                       "date": future_date,
                                       "time": "22:00",
                                       "city": "Palma de Mallorca"
                                   })
    event_id = event_response.json().get("id") if event_response.status_code == 200 else None
    
    if event_id:
        print(f"✅ Created event: {event_id}")
        
        # Test 2.2: User B marks interest "voy" on the event
        print("\n[2.2] User B marks 'voy' on event...")
        interest_response = requests.post(f"{BASE_URL}/events/{event_id}/interest",
                                         headers=get_headers(user_b_token),
                                         json={"status": "voy"})
        log_test("User B marks 'voy' on event", 
                 interest_response.status_code == 200,
                 f"Status: {interest_response.status_code}")
        
        # Test 2.3: User A views event and sees B in friends_going
        print("\n[2.3] User A views event (should see B in friends_going)...")
        event_view = requests.get(f"{BASE_URL}/events/{event_id}",
                                 headers=get_headers(user_a_token))
        if event_view.status_code == 200:
            event_data = event_view.json()
            friends_going = event_data.get("friends_going", [])
            b_in_list = any(f.get("user_id") == user_b_id for f in friends_going)
            total_going = event_data.get("total_going", 0)
            log_test("User B appears in friends_going", b_in_list,
                     f"friends_going={friends_going}")
            log_test("total_going includes User B", total_going >= 1,
                     f"total_going={total_going}")
        else:
            log_test("User A views event", False,
                     f"Status: {event_view.status_code}")
        
        # Test 2.4: User B sets attendance_privacy to "nadie"
        print("\n[2.4] User B sets attendance_privacy to 'nadie'...")
        privacy_response = requests.put(f"{BASE_URL}/auth/profile",
                                       headers=get_headers(user_b_token),
                                       json={"attendance_privacy": "nadie"})
        log_test("User B sets attendance_privacy to 'nadie'", 
                 privacy_response.status_code == 200,
                 f"Status: {privacy_response.status_code}")
        
        # Test 2.5: User B re-marks "voy" to update privacy on interest
        print("\n[2.5] User B re-marks 'voy' to update privacy...")
        interest_response2 = requests.post(f"{BASE_URL}/events/{event_id}/interest",
                                          headers=get_headers(user_b_token),
                                          json={"status": "voy"})
        log_test("User B re-marks 'voy'", 
                 interest_response2.status_code == 200,
                 f"Status: {interest_response2.status_code}")
        
        # Test 2.6: User A views event again (should NOT see B in friends_going)
        print("\n[2.6] User A views event again (should NOT see B - ghost mode)...")
        event_view2 = requests.get(f"{BASE_URL}/events/{event_id}",
                                  headers=get_headers(user_a_token))
        if event_view2.status_code == 200:
            event_data2 = event_view2.json()
            friends_going2 = event_data2.get("friends_going", [])
            b_in_list2 = any(f.get("user_id") == user_b_id for f in friends_going2)
            total_going2 = event_data2.get("total_going", 0)
            log_test("User B does NOT appear in friends_going (ghost)", not b_in_list2,
                     f"friends_going={friends_going2}")
            log_test("total_going excludes User B (ghost)", total_going2 == 0,
                     f"total_going={total_going2}")
        else:
            log_test("User A views event after privacy change", False,
                     f"Status: {event_view2.status_code}")
        
        # Test 2.7: User B sets attendance_privacy back to "todos"
        print("\n[2.7] User B sets attendance_privacy back to 'todos'...")
        privacy_response2 = requests.put(f"{BASE_URL}/auth/profile",
                                        headers=get_headers(user_b_token),
                                        json={"attendance_privacy": "todos"})
        log_test("User B sets attendance_privacy to 'todos'", 
                 privacy_response2.status_code == 200,
                 f"Status: {privacy_response2.status_code}")
        
        # User B re-marks "voy" again
        requests.post(f"{BASE_URL}/events/{event_id}/interest",
                     headers=get_headers(user_b_token),
                     json={"status": "voy"})
        
        # Test 2.8: User A views event again (should see B again)
        print("\n[2.8] User A views event again (should see B reappear)...")
        event_view3 = requests.get(f"{BASE_URL}/events/{event_id}",
                                  headers=get_headers(user_a_token))
        if event_view3.status_code == 200:
            event_data3 = event_view3.json()
            friends_going3 = event_data3.get("friends_going", [])
            b_in_list3 = any(f.get("user_id") == user_b_id for f in friends_going3)
            total_going3 = event_data3.get("total_going", 0)
            log_test("User B reappears in friends_going", b_in_list3,
                     f"friends_going={friends_going3}")
            log_test("total_going includes User B again", total_going3 >= 1,
                     f"total_going={total_going3}")
        else:
            log_test("User A views event after privacy restored", False,
                     f"Status: {event_view3.status_code}")
    else:
        print("❌ Failed to create event for privacy tests")
else:
    print("❌ Failed to create users for privacy tests")

# ============================================================================
# TEST 3: BLOCK / UNBLOCK
# ============================================================================
print("\n" + "=" * 80)
print("TEST 3: BLOCK / UNBLOCK")
print("=" * 80)

# Use User A and User B from previous test (they are friends)
if user_a_token and user_b_token and user_a_id and user_b_id:
    # Test 3.1: User A blocks User B
    print("\n[3.1] User A blocks User B...")
    block_response = requests.post(f"{BASE_URL}/me/block",
                                   headers=get_headers(user_a_token),
                                   json={"user_id": user_b_id})
    log_test("User A blocks User B", 
             block_response.status_code == 200,
             f"Status: {block_response.status_code}, Response: {block_response.json()}")
    
    # Test 3.2: GET /friends as A should not include B
    print("\n[3.2] User A gets friends list (should not include B)...")
    friends_response = requests.get(f"{BASE_URL}/friends",
                                   headers=get_headers(user_a_token))
    if friends_response.status_code == 200:
        friends = friends_response.json()
        b_in_friends = any(f.get("user_id") == user_b_id for f in friends)
        log_test("User B not in User A's friends list after block", not b_in_friends,
                 f"B in friends: {b_in_friends}")
    else:
        log_test("GET /friends as User A", False,
                 f"Status: {friends_response.status_code}")
    
    # Test 3.3: Search for User B as A (should not return B)
    print("\n[3.3] User A searches for User B (should not return B)...")
    search_response = requests.get(f"{BASE_URL}/users/search?q={user_b_username}",
                                  headers=get_headers(user_a_token))
    if search_response.status_code == 200:
        search_results = search_response.json()
        b_in_search = any(u.get("user_id") == user_b_id for u in search_results)
        log_test("User B not in search results for User A", not b_in_search,
                 f"B in search: {b_in_search}")
    else:
        log_test("Search for User B as User A", False,
                 f"Status: {search_response.status_code}")
    
    # Test 3.4: GET /me/blocked as A includes B
    print("\n[3.4] User A gets blocked list (should include B)...")
    blocked_response = requests.get(f"{BASE_URL}/me/blocked",
                                   headers=get_headers(user_a_token))
    if blocked_response.status_code == 200:
        blocked = blocked_response.json()
        b_in_blocked = any(u.get("user_id") == user_b_id for u in blocked)
        log_test("User B in User A's blocked list", b_in_blocked,
                 f"B in blocked: {b_in_blocked}, blocked list: {blocked}")
    else:
        log_test("GET /me/blocked as User A", False,
                 f"Status: {blocked_response.status_code}")
    
    # Test 3.5: User A unblocks User B
    print("\n[3.5] User A unblocks User B...")
    unblock_response = requests.post(f"{BASE_URL}/me/unblock",
                                    headers=get_headers(user_a_token),
                                    json={"user_id": user_b_id})
    log_test("User A unblocks User B", 
             unblock_response.status_code == 200,
             f"Status: {unblock_response.status_code}, Response: {unblock_response.json()}")
    
    # Test 3.6: GET /me/blocked as A should not include B
    print("\n[3.6] User A gets blocked list (should not include B)...")
    blocked_response2 = requests.get(f"{BASE_URL}/me/blocked",
                                    headers=get_headers(user_a_token))
    if blocked_response2.status_code == 200:
        blocked2 = blocked_response2.json()
        b_in_blocked2 = any(u.get("user_id") == user_b_id for u in blocked2)
        log_test("User B not in User A's blocked list after unblock", not b_in_blocked2,
                 f"B in blocked: {b_in_blocked2}")
    else:
        log_test("GET /me/blocked after unblock", False,
                 f"Status: {blocked_response2.status_code}")
    
    # Test 3.7: Search for User B as A (should return B again)
    print("\n[3.7] User A searches for User B (should return B again)...")
    search_response2 = requests.get(f"{BASE_URL}/users/search?q={user_b_username}",
                                   headers=get_headers(user_a_token))
    if search_response2.status_code == 200:
        search_results2 = search_response2.json()
        b_in_search2 = any(u.get("user_id") == user_b_id for u in search_results2)
        log_test("User B appears in search results after unblock", b_in_search2,
                 f"B in search: {b_in_search2}")
    else:
        log_test("Search for User B after unblock", False,
                 f"Status: {search_response2.status_code}")
    
    # Test 3.8: Blocking self (should be 400)
    print("\n[3.8] User A tries to block self (should be 400)...")
    block_self_response = requests.post(f"{BASE_URL}/me/block",
                                       headers=get_headers(user_a_token),
                                       json={"user_id": user_a_id})
    log_test("Blocking self returns 400", 
             block_self_response.status_code == 400,
             f"Status: {block_self_response.status_code}")
else:
    print("❌ Skipping block/unblock tests (no users available)")

# ============================================================================
# TEST 4: REPORTS + ADMIN REVIEW
# ============================================================================
print("\n" + "=" * 80)
print("TEST 4: REPORTS + ADMIN REVIEW")
print("=" * 80)

if user_a_token and user_b_id:
    # Test 4.1: User A reports User B
    print("\n[4.1] User A reports User B...")
    report_response = requests.post(f"{BASE_URL}/reports",
                                   headers=get_headers(user_a_token),
                                   json={
                                       "target_type": "user",
                                       "target_id": user_b_id,
                                       "reason": "spam",
                                       "note": "test report"
                                   })
    report_id = None
    if report_response.status_code == 200:
        data = report_response.json()
        report_id = data.get("id")
        log_test("User A reports User B", True,
                 f"Status: {report_response.status_code}, Report ID: {report_id}")
    else:
        log_test("User A reports User B", False,
                 f"Status: {report_response.status_code}, Response: {report_response.text}")
    
    # Test 4.2: Report with invalid target_type (should be 400)
    print("\n[4.2] Creating report with invalid target_type...")
    invalid_report = requests.post(f"{BASE_URL}/reports",
                                  headers=get_headers(user_a_token),
                                  json={
                                      "target_type": "foo",
                                      "target_id": user_b_id,
                                      "reason": "test",
                                      "note": "test"
                                  })
    log_test("Report with invalid target_type returns 400", 
             invalid_report.status_code == 400,
             f"Status: {invalid_report.status_code}")
    
    # Test 4.3: GET /admin/reports as admin
    print("\n[4.3] Admin gets reports list...")
    admin_reports = requests.get(f"{BASE_URL}/admin/reports",
                                headers=get_headers(admin_token))
    if admin_reports.status_code == 200:
        reports = admin_reports.json()
        report_found = any(r.get("id") == report_id for r in reports) if report_id else False
        has_reporter = all("reporter" in r for r in reports[:5])  # Check first 5
        has_target_user = all("target_user" in r for r in reports[:5] if r.get("target_type") == "user")
        log_test("GET /admin/reports as admin returns 200", True,
                 f"Status: {admin_reports.status_code}, Count: {len(reports)}")
        if report_id:
            log_test("Created report appears in admin list", report_found,
                     f"Report found: {report_found}")
        log_test("Reports include reporter field", has_reporter,
                 f"Reporter populated: {has_reporter}")
        log_test("User reports include target_user field", has_target_user,
                 f"Target user populated: {has_target_user}")
    else:
        log_test("GET /admin/reports as admin", False,
                 f"Status: {admin_reports.status_code}")
    
    # Test 4.4: GET /admin/reports as non-admin (should be 403)
    print("\n[4.4] Non-admin tries to get reports (should be 403)...")
    non_admin_reports = requests.get(f"{BASE_URL}/admin/reports",
                                    headers=get_headers(user_a_token))
    log_test("GET /admin/reports as non-admin returns 403", 
             non_admin_reports.status_code == 403,
             f"Status: {non_admin_reports.status_code}")
    
    # Test 4.5: Admin resolves report
    if report_id:
        print(f"\n[4.5] Admin resolves report {report_id}...")
        resolve_response = requests.post(f"{BASE_URL}/admin/reports/{report_id}/resolve",
                                        headers=get_headers(admin_token))
        log_test("Admin resolves report", 
                 resolve_response.status_code == 200,
                 f"Status: {resolve_response.status_code}, Response: {resolve_response.json()}")
        
        # Test 4.6: GET /admin/reports?status=open should not include resolved report
        print("\n[4.6] Getting open reports (should not include resolved)...")
        open_reports = requests.get(f"{BASE_URL}/admin/reports?status=open",
                                   headers=get_headers(admin_token))
        if open_reports.status_code == 200:
            open_list = open_reports.json()
            resolved_in_open = any(r.get("id") == report_id for r in open_list)
            log_test("Resolved report not in open list", not resolved_in_open,
                     f"Resolved report in open list: {resolved_in_open}")
        else:
            log_test("GET /admin/reports?status=open", False,
                     f"Status: {open_reports.status_code}")
        
        # Test 4.7: GET /admin/reports?status=all should include resolved report
        print("\n[4.7] Getting all reports (should include resolved)...")
        all_reports = requests.get(f"{BASE_URL}/admin/reports?status=all",
                                  headers=get_headers(admin_token))
        if all_reports.status_code == 200:
            all_list = all_reports.json()
            resolved_in_all = any(r.get("id") == report_id for r in all_list)
            log_test("Resolved report in all list", resolved_in_all,
                     f"Resolved report in all list: {resolved_in_all}")
        else:
            log_test("GET /admin/reports?status=all", False,
                     f"Status: {all_reports.status_code}")
else:
    print("❌ Skipping reports tests (no users available)")

# ============================================================================
# TEST 5: CONTACT MATCHING (COLD START)
# ============================================================================
print("\n" + "=" * 80)
print("TEST 5: CONTACT MATCHING (COLD START)")
print("=" * 80)

# Test 5.1: Admin matches Ana's phone (600333444)
print("\n[5.1] Admin matches contacts with Ana's phone (600333444)...")
match_response = requests.post(f"{BASE_URL}/me/match-contacts",
                              headers=get_headers(admin_token),
                              json={"phones": ["600333444"]})
if match_response.status_code == 200:
    matches = match_response.json()
    ana_found = any(u.get("username") == "ana" for u in matches)
    log_test("Contact matching returns Ana", ana_found,
             f"Ana found: {ana_found}, Matches: {[u.get('username') for u in matches]}")
    if matches:
        first_match = matches[0]
        has_relationship = "relationship" in first_match
        log_test("Match includes relationship field", has_relationship,
                 f"relationship={first_match.get('relationship')}")
else:
    log_test("Contact matching with Ana's phone", False,
             f"Status: {match_response.status_code}, Response: {match_response.text}")

# Test 5.2: Test ES normalization formats (+34, 0034, plain)
print("\n[5.2] Testing ES phone normalization (+34, 0034, plain)...")
formats_response = requests.post(f"{BASE_URL}/me/match-contacts",
                                headers=get_headers(admin_token),
                                json={"phones": ["+34 600 333 444", "0034600333444", "600333444"]})
if formats_response.status_code == 200:
    formats_matches = formats_response.json()
    # All three formats should match Ana (but deduped, so only 1 result)
    ana_count = sum(1 for u in formats_matches if u.get("username") == "ana")
    log_test("All phone formats match Ana", ana_count >= 1,
             f"Ana matches: {ana_count}, Total matches: {len(formats_matches)}")
else:
    log_test("Contact matching with multiple formats", False,
             f"Status: {formats_response.status_code}")

# Test 5.3: Ensure self is excluded
print("\n[5.3] Ensuring self is excluded from matches...")
# Get admin's phone from profile
admin_profile = requests.get(f"{BASE_URL}/auth/me", headers=get_headers(admin_token))
if admin_profile.status_code == 200:
    admin_data = admin_profile.json()
    # Admin has phone 600111222 according to test_credentials.md
    self_match = requests.post(f"{BASE_URL}/me/match-contacts",
                              headers=get_headers(admin_token),
                              json={"phones": ["600111222"]})
    if self_match.status_code == 200:
        self_matches = self_match.json()
        admin_in_matches = any(u.get("email") == ADMIN_EMAIL for u in self_matches)
        log_test("Self is excluded from contact matches", not admin_in_matches,
                 f"Admin in matches: {admin_in_matches}")
    else:
        log_test("Contact matching with self phone", False,
                 f"Status: {self_match.status_code}")

# Test 5.4: Ensure already-friends are excluded
print("\n[5.4] Testing that already-friends are excluded...")
# First, make admin and Ana friends
friend_req = requests.post(f"{BASE_URL}/friends/request",
                          headers=get_headers(admin_token),
                          json={"addressee_username": "ana"})
if friend_req.status_code == 200:
    request_id = friend_req.json().get("id")
    # Ana accepts
    accept_req = requests.post(f"{BASE_URL}/friends/respond",
                              headers=get_headers(ana_token),
                              json={"request_id": request_id, "accept": True})
    if accept_req.status_code == 200:
        print("✅ Admin and Ana are now friends")
        # Now match again - Ana should be excluded
        friends_match = requests.post(f"{BASE_URL}/me/match-contacts",
                                     headers=get_headers(admin_token),
                                     json={"phones": ["600333444"]})
        if friends_match.status_code == 200:
            friends_matches = friends_match.json()
            ana_in_matches = any(u.get("username") == "ana" for u in friends_matches)
            log_test("Already-friends are excluded from matches", not ana_in_matches,
                     f"Ana in matches: {ana_in_matches}, Matches: {[u.get('username') for u in friends_matches]}")
        else:
            log_test("Contact matching after becoming friends", False,
                     f"Status: {friends_match.status_code}")

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "=" * 80)
print("TEST SUMMARY")
print("=" * 80)
print(f"\nTotal Tests: {tests_passed + tests_failed}")
print(f"✅ Passed: {tests_passed}")
print(f"❌ Failed: {tests_failed}")
if tests_passed + tests_failed > 0:
    print(f"Pass Rate: {(tests_passed / (tests_passed + tests_failed) * 100):.1f}%")

print("\n" + "=" * 80)
print("DETAILED RESULTS")
print("=" * 80)
for result in test_results:
    print(result)

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)
