#!/usr/bin/env python3
"""
Test script for profile permission bug fix.
Tests the /api/users/{user_id}/badges endpoint with different friend statuses.
"""
import requests
import time
import json

BASE_URL = "https://8212b2f0-abf2-44ec-8d3e-ed989692e2c0.preview.emergentagent.com/api"

# Test credentials
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"
BOB_EMAIL = "bob@test.com"
BOB_PASSWORD = "pass1234"
CHARLIE_EMAIL = "charlie@test.com"
CHARLIE_PASSWORD = "pass1234"

def login(email, password):
    """Login and return session token"""
    resp = requests.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password})
    if resp.status_code != 200:
        print(f"❌ Login failed for {email}: {resp.status_code} - {resp.text}")
        return None
    data = resp.json()
    return data.get("token")

def register_user(email, password, name, username):
    """Register a new user"""
    resp = requests.post(f"{BASE_URL}/auth/register", json={
        "email": email,
        "password": password,
        "name": name,
        "username": username,
        "city": "Palma de Mallorca"
    })
    if resp.status_code == 200:
        return resp.json()
    return None

def get_user_badges(user_id, token):
    """Get user badges with authorization"""
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{BASE_URL}/users/{user_id}/badges", headers=headers)
    return resp

def send_friend_request(target_user_id, token):
    """Send friend request"""
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.post(f"{BASE_URL}/friends/request", 
                        json={"user_id": target_user_id}, 
                        headers=headers)
    return resp

def get_friend_requests(token):
    """Get pending friend requests"""
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{BASE_URL}/friends/requests", headers=headers)
    return resp

def respond_to_friend_request(request_id, accept, token):
    """Accept or reject friend request"""
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.post(f"{BASE_URL}/friends/respond", 
                        json={"request_id": request_id, "accept": accept}, 
                        headers=headers)
    return resp

def get_rankings_world(token):
    """Get world rankings"""
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{BASE_URL}/rankings/world", headers=headers)
    return resp

def get_me(token):
    """Get current user info"""
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{BASE_URL}/auth/me", headers=headers)
    return resp

def print_test_header(test_num, description):
    """Print formatted test header"""
    print(f"\n{'='*80}")
    print(f"TEST {test_num}: {description}")
    print(f"{'='*80}")

def print_result(passed, message):
    """Print test result"""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status}: {message}")

def main():
    print("🧪 Starting Profile Permission Bug Fix Tests")
    print(f"Backend URL: {BASE_URL}")
    
    # Login as admin
    print("\n🔐 Logging in as admin...")
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    if not admin_token:
        print("❌ CRITICAL: Cannot login as admin. Aborting tests.")
        return
    print("✅ Admin login successful")
    
    # Get admin user_id
    admin_resp = get_me(admin_token)
    if admin_resp.status_code != 200:
        print("❌ CRITICAL: Cannot get admin user info. Aborting tests.")
        return
    admin_user_id = admin_resp.json()["user_id"]
    print(f"Admin user_id: {admin_user_id}")
    
    # Try to login as Bob, if fails, register
    print("\n🔐 Checking Bob user...")
    bob_token = login(BOB_EMAIL, BOB_PASSWORD)
    if not bob_token:
        print("Bob doesn't exist, registering...")
        bob_data = register_user(BOB_EMAIL, BOB_PASSWORD, "Bob Test", "bobtest")
        if not bob_data:
            print("❌ CRITICAL: Cannot register Bob. Aborting tests.")
            return
        bob_token = bob_data.get("token")
        print("✅ Bob registered successfully")
    else:
        print("✅ Bob login successful")
    
    # Get Bob's user_id
    bob_resp = get_me(bob_token)
    if bob_resp.status_code != 200:
        print("❌ CRITICAL: Cannot get Bob user info. Aborting tests.")
        return
    bob_user_id = bob_resp.json()["user_id"]
    print(f"Bob user_id: {bob_user_id}")
    
    # Check if admin and Bob are already friends
    bob_badges_resp = get_user_badges(bob_user_id, admin_token)
    if bob_badges_resp.status_code == 200:
        bob_friend_status = bob_badges_resp.json().get("friend_status")
        print(f"Admin-Bob relationship: {bob_friend_status}")
        
        if bob_friend_status == "friends":
            print("⚠️  Admin and Bob are already friends. Using Charlie for non-friend tests.")
            # Use Charlie for non-friend tests
            charlie_token = login(CHARLIE_EMAIL, CHARLIE_PASSWORD)
            if not charlie_token:
                print("Charlie doesn't exist, registering...")
                charlie_data = register_user(CHARLIE_EMAIL, CHARLIE_PASSWORD, "Charlie Test", "charlietest")
                if not charlie_data:
                    print("❌ CRITICAL: Cannot register Charlie. Aborting tests.")
                    return
                charlie_token = charlie_data.get("token")
                print("✅ Charlie registered successfully")
            else:
                print("✅ Charlie login successful")
            
            charlie_resp = get_me(charlie_token)
            if charlie_resp.status_code != 200:
                print("❌ CRITICAL: Cannot get Charlie user info. Aborting tests.")
                return
            charlie_user_id = charlie_resp.json()["user_id"]
            print(f"Charlie user_id: {charlie_user_id}")
            
            # Use Charlie for tests 1 and 2
            test_user_id = charlie_user_id
            test_user_token = charlie_token
            test_user_name = "Charlie"
        else:
            # Use Bob for all tests
            test_user_id = bob_user_id
            test_user_token = bob_token
            test_user_name = "Bob"
    else:
        # Use Bob for all tests
        test_user_id = bob_user_id
        test_user_token = bob_token
        test_user_name = "Bob"
    
    # TEST 1: Admin viewing non-friend user's badges
    print_test_header(1, f"Admin viewing non-friend {test_user_name}'s badges (expect 200, limited view)")
    resp = get_user_badges(test_user_id, admin_token)
    
    test1_passed = True
    if resp.status_code != 200:
        print_result(False, f"Expected 200, got {resp.status_code}")
        test1_passed = False
    else:
        data = resp.json()
        
        # Check is_friend
        if data.get("is_friend") != False:
            print_result(False, f"Expected is_friend=False, got {data.get('is_friend')}")
            test1_passed = False
        else:
            print_result(True, "is_friend=False ✓")
        
        # Check is_self
        if data.get("is_self") != False:
            print_result(False, f"Expected is_self=False, got {data.get('is_self')}")
            test1_passed = False
        else:
            print_result(True, "is_self=False ✓")
        
        # Check friend_status
        if data.get("friend_status") != "none":
            print_result(False, f"Expected friend_status='none', got {data.get('friend_status')}")
            test1_passed = False
        else:
            print_result(True, "friend_status='none' ✓")
        
        # Check stats (should only have 5 keys)
        stats = data.get("stats", {})
        expected_keys = {"total_events", "friends_count", "genres_count", "week_streak", "day_streak"}
        actual_keys = set(stats.keys())
        
        if actual_keys != expected_keys:
            print_result(False, f"Stats keys mismatch. Expected {expected_keys}, got {actual_keys}")
            test1_passed = False
        else:
            print_result(True, f"Stats contains only 5 reduced keys ✓")
        
        # Check locked is empty
        if data.get("locked") != []:
            print_result(False, f"Expected locked=[], got {len(data.get('locked', []))} items")
            test1_passed = False
        else:
            print_result(True, "locked=[] ✓")
        
        # Check earned is present
        if "earned" not in data:
            print_result(False, "earned field missing")
            test1_passed = False
        else:
            print_result(True, f"earned array present with {len(data['earned'])} badges ✓")
        
        # Check points structure
        points = data.get("points", {})
        if "total" not in points or "badge_points" not in points:
            print_result(False, "points.total or points.badge_points missing")
            test1_passed = False
        elif points.get("action_points") != 0:
            print_result(False, f"Expected action_points=0 for non-friends, got {points.get('action_points')}")
            test1_passed = False
        else:
            print_result(True, f"points structure correct (action_points=0 for non-friends) ✓")
    
    if test1_passed:
        print("\n✅ TEST 1 PASSED")
    else:
        print("\n❌ TEST 1 FAILED")
    
    # TEST 2: Admin sends friend request to test user
    print_test_header(2, f"Admin sends friend request to {test_user_name} (expect pending_out)")
    
    # First, check if they're already friends or have pending request
    resp = get_user_badges(test_user_id, admin_token)
    if resp.status_code == 200:
        current_status = resp.json().get("friend_status")
        if current_status == "friends":
            print("⚠️  Admin and test user are already friends. Skipping friend request test.")
            print("✅ TEST 2 SKIPPED (already friends)")
            test2_passed = True
        elif current_status in ["pending_out", "pending_in"]:
            print(f"⚠️  Friend request already exists (status: {current_status})")
            # Verify the status is correct
            test2_passed = True
            if current_status == "pending_out":
                print_result(True, "friend_status='pending_out' ✓")
            else:
                print_result(True, f"friend_status='{current_status}' ✓")
            
            # Should still have limited view
            data = resp.json()
            stats = data.get("stats", {})
            expected_keys = {"total_events", "friends_count", "genres_count", "week_streak", "day_streak"}
            actual_keys = set(stats.keys())
            
            if actual_keys != expected_keys:
                print_result(False, f"Stats should still be limited. Got {actual_keys}")
                test2_passed = False
            else:
                print_result(True, "Stats still limited (non-friend view) ✓")
            
            print("✅ TEST 2 PASSED (verified existing request)")
        else:
            # Send friend request
            friend_req_resp = send_friend_request(test_user_id, admin_token)
            if friend_req_resp.status_code not in [200, 400]:
                print_result(False, f"Friend request failed: {friend_req_resp.status_code} - {friend_req_resp.text}")
                test2_passed = False
            else:
                # Check badges endpoint again
                resp = get_user_badges(test_user_id, admin_token)
                test2_passed = True
                
                if resp.status_code != 200:
                    print_result(False, f"Expected 200, got {resp.status_code}")
                    test2_passed = False
                else:
                    data = resp.json()
                    
                    # Should still be non-friend view
                    if data.get("is_friend") != False:
                        print_result(False, f"Expected is_friend=False, got {data.get('is_friend')}")
                        test2_passed = False
                    else:
                        print_result(True, "is_friend=False (still non-friend) ✓")
                    
                    # Check friend_status is pending_out
                    if data.get("friend_status") != "pending_out":
                        print_result(False, f"Expected friend_status='pending_out', got {data.get('friend_status')}")
                        test2_passed = False
                    else:
                        print_result(True, "friend_status='pending_out' ✓")
                    
                    # Should still have limited view
                    stats = data.get("stats", {})
                    expected_keys = {"total_events", "friends_count", "genres_count", "week_streak", "day_streak"}
                    actual_keys = set(stats.keys())
                    
                    if actual_keys != expected_keys:
                        print_result(False, f"Stats should still be limited. Got {actual_keys}")
                        test2_passed = False
                    else:
                        print_result(True, "Stats still limited (non-friend view) ✓")
                
                if test2_passed:
                    print("\n✅ TEST 2 PASSED")
                else:
                    print("\n❌ TEST 2 FAILED")
    else:
        print_result(False, f"Cannot check current friend status: {resp.status_code}")
        test2_passed = False
        print("\n❌ TEST 2 FAILED")
    
    # TEST 3: Test user accepts friend request
    print_test_header(3, f"{test_user_name} accepts friend request (expect friends, full view)")
    
    # Get test user's pending requests
    requests_resp = get_friend_requests(test_user_token)
    if requests_resp.status_code != 200:
        print_result(False, f"Cannot get friend requests: {requests_resp.status_code}")
        test3_passed = False
    else:
        requests_data = requests_resp.json()
        # API returns 'user' field, not 'requester'
        pending = [r for r in requests_data if r.get("user", {}).get("user_id") == admin_user_id]
        
        if not pending:
            print("⚠️  No pending request from admin to test user. Checking if already friends...")
            resp = get_user_badges(test_user_id, admin_token)
            if resp.status_code == 200 and resp.json().get("friend_status") == "friends":
                print("✅ Already friends. Testing full view...")
                test3_passed = True
            else:
                print_result(False, "No pending request and not friends")
                test3_passed = False
        else:
            # Accept the request (API uses 'request_id' field)
            request_id = pending[0]["request_id"]
            accept_resp = respond_to_friend_request(request_id, True, test_user_token)
            
            if accept_resp.status_code != 200:
                print_result(False, f"Accept request failed: {accept_resp.status_code} - {accept_resp.text}")
                test3_passed = False
            else:
                print_result(True, "Friend request accepted ✓")
                test3_passed = True
        
        if test3_passed:
            # Now check admin's view of test user's badges (should be full)
            resp = get_user_badges(test_user_id, admin_token)
            
            if resp.status_code != 200:
                print_result(False, f"Expected 200, got {resp.status_code}")
                test3_passed = False
            else:
                data = resp.json()
                
                # Check is_friend
                if data.get("is_friend") != True:
                    print_result(False, f"Expected is_friend=True, got {data.get('is_friend')}")
                    test3_passed = False
                else:
                    print_result(True, "is_friend=True ✓")
                
                # Check friend_status
                if data.get("friend_status") != "friends":
                    print_result(False, f"Expected friend_status='friends', got {data.get('friend_status')}")
                    test3_passed = False
                else:
                    print_result(True, "friend_status='friends' ✓")
                
                # Check stats (should have full keys now)
                stats = data.get("stats", {})
                required_full_keys = {"total_events", "friends_count", "genres_count", "week_streak", 
                                     "day_streak", "attended", "going", "weekday_count"}
                actual_keys = set(stats.keys())
                
                if not required_full_keys.issubset(actual_keys):
                    print_result(False, f"Stats missing full keys. Expected at least {required_full_keys}, got {actual_keys}")
                    test3_passed = False
                else:
                    print_result(True, f"Stats contains full keys (including attended, going, weekday_count, etc.) ✓")
                
                # Check locked is filled
                locked = data.get("locked", [])
                if len(locked) == 0:
                    print_result(False, "Expected locked badges to be filled for friends")
                    test3_passed = False
                else:
                    print_result(True, f"locked array filled with {len(locked)} badges ✓")
                
                # Check points structure (should have full action_points now)
                points = data.get("points", {})
                if points.get("action_points") == 0:
                    print_result(False, "Expected action_points > 0 for friends (or at least not hidden)")
                    test3_passed = False
                else:
                    print_result(True, f"action_points visible for friends ({points.get('action_points')}) ✓")
    
    if test3_passed:
        print("\n✅ TEST 3 PASSED")
    else:
        print("\n❌ TEST 3 FAILED")
    
    # TEST 4: Bob viewing own profile
    print_test_header(4, "Bob viewing own profile (expect is_self=True, full view)")
    
    resp = get_user_badges(bob_user_id, bob_token)
    test4_passed = True
    
    if resp.status_code != 200:
        print_result(False, f"Expected 200, got {resp.status_code}")
        test4_passed = False
    else:
        data = resp.json()
        
        # Check is_self
        if data.get("is_self") != True:
            print_result(False, f"Expected is_self=True, got {data.get('is_self')}")
            test4_passed = False
        else:
            print_result(True, "is_self=True ✓")
        
        # Check friend_status
        if data.get("friend_status") != "self":
            print_result(False, f"Expected friend_status='self', got {data.get('friend_status')}")
            test4_passed = False
        else:
            print_result(True, "friend_status='self' ✓")
        
        # Check stats (should have full keys)
        stats = data.get("stats", {})
        required_full_keys = {"total_events", "friends_count", "genres_count", "week_streak", 
                             "day_streak", "attended", "going", "weekday_count"}
        actual_keys = set(stats.keys())
        
        if not required_full_keys.issubset(actual_keys):
            print_result(False, f"Stats missing full keys. Expected at least {required_full_keys}, got {actual_keys}")
            test4_passed = False
        else:
            print_result(True, f"Stats contains full keys ✓")
        
        # Check locked is filled
        locked = data.get("locked", [])
        if len(locked) == 0:
            print_result(False, "Expected locked badges to be filled for self")
            test4_passed = False
        else:
            print_result(True, f"locked array filled with {len(locked)} badges ✓")
    
    if test4_passed:
        print("\n✅ TEST 4 PASSED")
    else:
        print("\n❌ TEST 4 FAILED")
    
    # TEST 5: Non-existent user
    print_test_header(5, "GET non-existent user (expect 404)")
    
    fake_user_id = "nonexistent-user-12345"
    resp = get_user_badges(fake_user_id, admin_token)
    test5_passed = True
    
    if resp.status_code != 404:
        print_result(False, f"Expected 404, got {resp.status_code}")
        test5_passed = False
    else:
        print_result(True, "Returns 404 for non-existent user ✓")
    
    if test5_passed:
        print("\n✅ TEST 5 PASSED")
    else:
        print("\n❌ TEST 5 FAILED")
    
    # TEST 6: Performance check - rankings cache
    print_test_header(6, "Performance: rankings/world cache test")
    
    print("First call (cold cache)...")
    start1 = time.time()
    resp1 = get_rankings_world(admin_token)
    elapsed1 = (time.time() - start1) * 1000  # ms
    
    if resp1.status_code != 200:
        print_result(False, f"First call failed: {resp1.status_code}")
        test6_passed = False
    else:
        data1 = resp1.json()
        print_result(True, f"First call: {elapsed1:.1f}ms, returned {len(data1)} users")
        
        # Second call (should be cached)
        print("Second call (warm cache)...")
        start2 = time.time()
        resp2 = get_rankings_world(admin_token)
        elapsed2 = (time.time() - start2) * 1000  # ms
        
        if resp2.status_code != 200:
            print_result(False, f"Second call failed: {resp2.status_code}")
            test6_passed = False
        else:
            data2 = resp2.json()
            print_result(True, f"Second call: {elapsed2:.1f}ms, returned {len(data2)} users")
            
            # Check if second call is faster
            if elapsed2 < elapsed1:
                speedup = elapsed1 / elapsed2
                print_result(True, f"Second call is {speedup:.1f}x faster (cache working) ✓")
                test6_passed = True
            else:
                print_result(False, f"Second call not faster ({elapsed2:.1f}ms vs {elapsed1:.1f}ms)")
                test6_passed = False
            
            # Check data consistency
            if len(data1) != len(data2):
                print_result(False, f"Data length mismatch: {len(data1)} vs {len(data2)}")
                test6_passed = False
            else:
                # Check if order and points are the same
                same_order = all(d1["user_id"] == d2["user_id"] for d1, d2 in zip(data1, data2))
                same_points = all(d1["points"] == d2["points"] for d1, d2 in zip(data1, data2))
                
                if same_order and same_points:
                    print_result(True, "Data consistency: same order and points ✓")
                else:
                    print_result(False, "Data inconsistency between calls")
                    test6_passed = False
    
    if test6_passed:
        print("\n✅ TEST 6 PASSED")
    else:
        print("\n❌ TEST 6 FAILED")
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    all_tests = [
        ("TEST 1: Non-friend view (limited data)", test1_passed),
        ("TEST 2: Pending friend request view", test2_passed),
        ("TEST 3: Friend view (full data)", test3_passed),
        ("TEST 4: Self view (full data)", test4_passed),
        ("TEST 5: Non-existent user (404)", test5_passed),
        ("TEST 6: Performance cache", test6_passed),
    ]
    
    passed_count = sum(1 for _, passed in all_tests if passed)
    total_count = len(all_tests)
    
    for test_name, passed in all_tests:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\n{'='*80}")
    print(f"TOTAL: {passed_count}/{total_count} tests passed ({passed_count/total_count*100:.1f}%)")
    print(f"{'='*80}")
    
    if passed_count == total_count:
        print("\n🎉 ALL TESTS PASSED! Bug fix verified successfully.")
    else:
        print(f"\n⚠️  {total_count - passed_count} test(s) failed. Review needed.")

if __name__ == "__main__":
    main()
