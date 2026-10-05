#!/usr/bin/env python3
"""
Backend API Testing for ¿Quién va? FASE 3
Tests @username privacy and city-alerts opt-in features.
"""

import requests
import json
import sys
import time
from datetime import datetime

# Base URL from frontend/.env
BASE_URL = "https://who-goes-planner.preview.emergentagent.com/api"

# Admin credentials
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

# Test results tracking
tests_passed = 0
tests_failed = 0
test_details = []


def log_test(test_name, passed, details=""):
    """Log test result"""
    global tests_passed, tests_failed
    if passed:
        tests_passed += 1
        status = "✅ PASS"
    else:
        tests_failed += 1
        status = "❌ FAIL"
    
    message = f"{status}: {test_name}"
    if details:
        message += f" - {details}"
    print(message)
    test_details.append({"test": test_name, "passed": passed, "details": details})


def register_user(email, password, name, username, city, birthdate):
    """Register a new user"""
    try:
        response = requests.post(
            f"{BASE_URL}/auth/register",
            json={
                "email": email,
                "password": password,
                "name": name,
                "username": username,
                "city": city,
                "birthdate": birthdate
            },
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("token"), data.get("user", {}).get("user_id")
        else:
            print(f"Registration failed: {response.status_code} - {response.text}")
            return None, None
    except Exception as e:
        print(f"Registration error: {e}")
        return None, None


def login_user(email, password):
    """Login a user"""
    try:
        response = requests.post(
            f"{BASE_URL}/auth/login",
            json={"email": email, "password": password},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("token"), data.get("user", {}).get("user_id")
        else:
            print(f"Login failed: {response.status_code} - {response.text}")
            return None, None
    except Exception as e:
        print(f"Login error: {e}")
        return None, None


def test_username_privacy():
    """Test 1: @username privacy - hide real names from other users"""
    print("\n" + "="*80)
    print("TEST 1: @USERNAME PRIVACY")
    print("="*80)
    
    # Generate unique usernames with timestamp
    ts = str(int(time.time()))
    username_a = f"userA{ts}"
    username_b = f"userB{ts}"
    email_a = f"usera{ts}@test.com"
    email_b = f"userb{ts}@test.com"
    name_a = "Nombre Real A"
    name_b = "Nombre Real B"
    
    print(f"\nRegistering User A: {email_a}, username: {username_a}, name: {name_a}")
    token_a, user_id_a = register_user(
        email=email_a,
        password="test1234",
        name=name_a,
        username=username_a,
        city="Ibiza",
        birthdate="2000-01-01"
    )
    
    if not token_a:
        log_test("Register User A", False, "Registration failed")
        return
    log_test("Register User A", True, f"user_id: {user_id_a}")
    
    print(f"\nRegistering User B: {email_b}, username: {username_b}, name: {name_b}")
    token_b, user_id_b = register_user(
        email=email_b,
        password="test1234",
        name=name_b,
        username=username_b,
        city="Ibiza",
        birthdate="2000-01-01"
    )
    
    if not token_b:
        log_test("Register User B", False, "Registration failed")
        return
    log_test("Register User B", True, f"user_id: {user_id_b}")
    
    # Test 1a: Search by username should return @username, not real name
    print(f"\n--- Test 1a: Search by username '{username_b}' as User A ---")
    try:
        response = requests.get(
            f"{BASE_URL}/users/search",
            params={"q": username_b},
            headers={"Authorization": f"Bearer {token_a}"},
            timeout=10
        )
        
        if response.status_code != 200:
            log_test("1a: Search by username status", False, f"Expected 200, got {response.status_code}")
        else:
            log_test("1a: Search by username status", True, "200 OK")
            
            results = response.json()
            print(f"Search results: {json.dumps(results, indent=2, ensure_ascii=False)}")
            
            # Check if User B is in results
            user_b_found = None
            for user in results:
                if user.get("user_id") == user_id_b:
                    user_b_found = user
                    break
            
            if not user_b_found:
                log_test("1a: User B found in search", False, "User B not in search results")
            else:
                log_test("1a: User B found in search", True)
                
                # Check that name is @username, not real name
                returned_name = user_b_found.get("name", "")
                expected_name = f"@{username_b.lower()}"
                
                if returned_name == expected_name:
                    log_test("1a: Name is @username", True, f"Returned: {returned_name}")
                else:
                    log_test("1a: Name is @username", False, f"Expected '{expected_name}', got '{returned_name}'")
                
                # Check that real name is NOT in the response
                response_text = json.dumps(results)
                if name_b in response_text:
                    log_test("1a: Real name NOT in response", False, f"Found '{name_b}' in response")
                else:
                    log_test("1a: Real name NOT in response", True, f"'{name_b}' not found in response")
    
    except Exception as e:
        log_test("1a: Search by username", False, f"Error: {e}")
    
    # Test 1b: Search by real name should return 0 results
    print(f"\n--- Test 1b: Search by real name '{name_b}' as User A ---")
    try:
        response = requests.get(
            f"{BASE_URL}/users/search",
            params={"q": name_b},
            headers={"Authorization": f"Bearer {token_a}"},
            timeout=10
        )
        
        if response.status_code != 200:
            log_test("1b: Search by real name status", False, f"Expected 200, got {response.status_code}")
        else:
            log_test("1b: Search by real name status", True, "200 OK")
            
            results = response.json()
            print(f"Search results: {json.dumps(results, indent=2, ensure_ascii=False)}")
            
            # Check that User B is NOT in results
            user_b_found = False
            for user in results:
                if user.get("user_id") == user_id_b:
                    user_b_found = True
                    break
            
            if user_b_found:
                log_test("1b: Search by real name returns 0 results", False, "User B found when searching by real name")
            else:
                log_test("1b: Search by real name returns 0 results", True, "User B not found (correct)")
    
    except Exception as e:
        log_test("1b: Search by real name", False, f"Error: {e}")
    
    # Test 1c: Friend request and friend list should show @username
    print(f"\n--- Test 1c: Friend request and friend list ---")
    
    # A sends friend request to B
    try:
        response = requests.post(
            f"{BASE_URL}/friends/request",
            json={"user_id": user_id_b},
            headers={"Authorization": f"Bearer {token_a}"},
            timeout=10
        )
        
        if response.status_code != 200:
            log_test("1c: Send friend request", False, f"Expected 200, got {response.status_code}")
        else:
            log_test("1c: Send friend request", True, "Friend request sent")
    
    except Exception as e:
        log_test("1c: Send friend request", False, f"Error: {e}")
    
    # B accepts friend request
    try:
        # First, get the request ID
        response = requests.get(
            f"{BASE_URL}/friends/requests",
            headers={"Authorization": f"Bearer {token_b}"},
            timeout=10
        )
        
        if response.status_code != 200:
            log_test("1c: Get friend requests", False, f"Expected 200, got {response.status_code}")
        else:
            requests_list = response.json()
            print(f"Friend requests for User B: {json.dumps(requests_list, indent=2, ensure_ascii=False)}")
            
            if not requests_list:
                log_test("1c: Friend request received", False, "No friend requests found")
            else:
                request_id = requests_list[0].get("request_id")
                log_test("1c: Friend request received", True, f"request_id: {request_id}")
                
                # Check that requester name is @username
                requester_name = requests_list[0].get("user", {}).get("name", "")
                expected_name = f"@{username_a.lower()}"
                if requester_name == expected_name:
                    log_test("1c: Requester name is @username", True, f"Returned: {requester_name}")
                else:
                    log_test("1c: Requester name is @username", False, f"Expected '{expected_name}', got '{requester_name}'")
                
                # Accept the request
                response = requests.post(
                    f"{BASE_URL}/friends/respond",
                    json={"request_id": request_id, "accept": True},
                    headers={"Authorization": f"Bearer {token_b}"},
                    timeout=10
                )
                
                if response.status_code != 200:
                    log_test("1c: Accept friend request", False, f"Expected 200, got {response.status_code}")
                else:
                    log_test("1c: Accept friend request", True, "Friend request accepted")
    
    except Exception as e:
        log_test("1c: Accept friend request", False, f"Error: {e}")
    
    # A gets friend list
    print(f"\n--- Test 1c: Get friend list as User A ---")
    try:
        response = requests.get(
            f"{BASE_URL}/friends",
            headers={"Authorization": f"Bearer {token_a}"},
            timeout=10
        )
        
        if response.status_code != 200:
            log_test("1c: Get friends list (A)", False, f"Expected 200, got {response.status_code}")
        else:
            log_test("1c: Get friends list (A)", True, "200 OK")
            
            friends = response.json()
            print(f"Friends list for User A: {json.dumps(friends, indent=2, ensure_ascii=False)}")
            
            # Check that User B is in the list with @username
            user_b_found = None
            for friend in friends:
                if friend.get("user_id") == user_id_b:
                    user_b_found = friend
                    break
            
            if not user_b_found:
                log_test("1c: User B in friends list", False, "User B not found in friends list")
            else:
                log_test("1c: User B in friends list", True)
                
                friend_name = user_b_found.get("name", "")
                expected_name = f"@{username_b.lower()}"
                
                if friend_name == expected_name:
                    log_test("1c: Friend name is @username (A)", True, f"Returned: {friend_name}")
                else:
                    log_test("1c: Friend name is @username (A)", False, f"Expected '{expected_name}', got '{friend_name}'")
                
                # Check that real name is NOT in the response
                response_text = json.dumps(friends)
                if name_b in response_text:
                    log_test("1c: Real name NOT in friends list (A)", False, f"Found '{name_b}' in response")
                else:
                    log_test("1c: Real name NOT in friends list (A)", True, f"'{name_b}' not found in response")
    
    except Exception as e:
        log_test("1c: Get friends list (A)", False, f"Error: {e}")
    
    # B gets friend list
    print(f"\n--- Test 1c: Get friend list as User B ---")
    try:
        response = requests.get(
            f"{BASE_URL}/friends",
            headers={"Authorization": f"Bearer {token_b}"},
            timeout=10
        )
        
        if response.status_code != 200:
            log_test("1c: Get friends list (B)", False, f"Expected 200, got {response.status_code}")
        else:
            log_test("1c: Get friends list (B)", True, "200 OK")
            
            friends = response.json()
            print(f"Friends list for User B: {json.dumps(friends, indent=2, ensure_ascii=False)}")
            
            # Check that User A is in the list with @username
            user_a_found = None
            for friend in friends:
                if friend.get("user_id") == user_id_a:
                    user_a_found = friend
                    break
            
            if not user_a_found:
                log_test("1c: User A in friends list", False, "User A not found in friends list")
            else:
                log_test("1c: User A in friends list", True)
                
                friend_name = user_a_found.get("name", "")
                expected_name = f"@{username_a.lower()}"
                
                if friend_name == expected_name:
                    log_test("1c: Friend name is @username (B)", True, f"Returned: {friend_name}")
                else:
                    log_test("1c: Friend name is @username (B)", False, f"Expected '{expected_name}', got '{friend_name}'")
    
    except Exception as e:
        log_test("1c: Get friends list (B)", False, f"Error: {e}")
    
    # Test 1d: Get user profile/badges should show @username
    print(f"\n--- Test 1d: Get User B profile/badges as User A ---")
    try:
        response = requests.get(
            f"{BASE_URL}/users/{user_id_b}/badges",
            headers={"Authorization": f"Bearer {token_a}"},
            timeout=10
        )
        
        if response.status_code != 200:
            log_test("1d: Get user badges status", False, f"Expected 200, got {response.status_code}")
        else:
            log_test("1d: Get user badges status", True, "200 OK")
            
            data = response.json()
            print(f"User B badges/profile: {json.dumps(data, indent=2, ensure_ascii=False)}")
            
            user_info = data.get("user", {})
            user_name = user_info.get("name", "")
            expected_name = f"@{username_b.lower()}"
            
            if user_name == expected_name:
                log_test("1d: User name is @username", True, f"Returned: {user_name}")
            else:
                log_test("1d: User name is @username", False, f"Expected '{expected_name}', got '{user_name}'")
    
    except Exception as e:
        log_test("1d: Get user badges", False, f"Error: {e}")
    
    # Test 1e: REGRESSION - /auth/me should still return own real name
    print(f"\n--- Test 1e: REGRESSION - GET /auth/me should return own real name ---")
    try:
        response = requests.get(
            f"{BASE_URL}/auth/me",
            headers={"Authorization": f"Bearer {token_a}"},
            timeout=10
        )
        
        if response.status_code != 200:
            log_test("1e: Get /auth/me status", False, f"Expected 200, got {response.status_code}")
        else:
            log_test("1e: Get /auth/me status", True, "200 OK")
            
            data = response.json()
            print(f"User A /auth/me: {json.dumps(data, indent=2, ensure_ascii=False)}")
            
            returned_name = data.get("name", "")
            
            if returned_name == name_a:
                log_test("1e: Own real name returned", True, f"Returned: {returned_name}")
            else:
                log_test("1e: Own real name returned", False, f"Expected '{name_a}', got '{returned_name}'")
    
    except Exception as e:
        log_test("1e: Get /auth/me", False, f"Error: {e}")
    
    return token_a, user_id_a


def test_city_alerts_opt_in():
    """Test 2: City-wide change alerts opt-in"""
    print("\n" + "="*80)
    print("TEST 2: CITY-WIDE CHANGE ALERTS OPT-IN")
    print("="*80)
    
    # Register a fresh user
    ts = str(int(time.time()))
    email = f"cityalerts{ts}@test.com"
    username = f"cityalerts{ts}"
    
    print(f"\nRegistering fresh user: {email}")
    token, user_id = register_user(
        email=email,
        password="test1234",
        name="City Alerts Test",
        username=username,
        city="Ibiza",
        birthdate="2000-01-01"
    )
    
    if not token:
        log_test("Register user for city alerts test", False, "Registration failed")
        return
    log_test("Register user for city alerts test", True, f"user_id: {user_id}")
    
    # Test 2a: Default value should be False
    print(f"\n--- Test 2a: Check default city_change_alerts value ---")
    try:
        response = requests.get(
            f"{BASE_URL}/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        if response.status_code != 200:
            log_test("2a: Get /auth/me status", False, f"Expected 200, got {response.status_code}")
        else:
            log_test("2a: Get /auth/me status", True, "200 OK")
            
            data = response.json()
            city_change_alerts = data.get("city_change_alerts")
            
            print(f"city_change_alerts value: {city_change_alerts}")
            
            if city_change_alerts is False:
                log_test("2a: Default city_change_alerts is False", True, f"Value: {city_change_alerts}")
            else:
                log_test("2a: Default city_change_alerts is False", False, f"Expected False, got {city_change_alerts}")
    
    except Exception as e:
        log_test("2a: Check default value", False, f"Error: {e}")
    
    # Test 2b: Enable city alerts
    print(f"\n--- Test 2b: Enable city alerts ---")
    try:
        response = requests.put(
            f"{BASE_URL}/me/city-alerts",
            json={"enabled": True},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        if response.status_code != 200:
            log_test("2b: PUT /me/city-alerts (enable) status", False, f"Expected 200, got {response.status_code}")
        else:
            log_test("2b: PUT /me/city-alerts (enable) status", True, "200 OK")
            
            data = response.json()
            print(f"Response: {json.dumps(data, indent=2)}")
            
            city_change_alerts = data.get("city_change_alerts")
            
            if city_change_alerts is True:
                log_test("2b: city_change_alerts set to True", True, f"Value: {city_change_alerts}")
            else:
                log_test("2b: city_change_alerts set to True", False, f"Expected True, got {city_change_alerts}")
    
    except Exception as e:
        log_test("2b: Enable city alerts", False, f"Error: {e}")
    
    # Test 2c: Verify with GET /auth/me
    print(f"\n--- Test 2c: Verify city_change_alerts is True ---")
    try:
        response = requests.get(
            f"{BASE_URL}/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        if response.status_code != 200:
            log_test("2c: Get /auth/me status", False, f"Expected 200, got {response.status_code}")
        else:
            log_test("2c: Get /auth/me status", True, "200 OK")
            
            data = response.json()
            city_change_alerts = data.get("city_change_alerts")
            
            if city_change_alerts is True:
                log_test("2c: city_change_alerts reflects True", True, f"Value: {city_change_alerts}")
            else:
                log_test("2c: city_change_alerts reflects True", False, f"Expected True, got {city_change_alerts}")
    
    except Exception as e:
        log_test("2c: Verify enabled", False, f"Error: {e}")
    
    # Test 2d: Disable city alerts
    print(f"\n--- Test 2d: Disable city alerts ---")
    try:
        response = requests.put(
            f"{BASE_URL}/me/city-alerts",
            json={"enabled": False},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        if response.status_code != 200:
            log_test("2d: PUT /me/city-alerts (disable) status", False, f"Expected 200, got {response.status_code}")
        else:
            log_test("2d: PUT /me/city-alerts (disable) status", True, "200 OK")
            
            data = response.json()
            city_change_alerts = data.get("city_change_alerts")
            
            if city_change_alerts is False:
                log_test("2d: city_change_alerts set to False", True, f"Value: {city_change_alerts}")
            else:
                log_test("2d: city_change_alerts set to False", False, f"Expected False, got {city_change_alerts}")
    
    except Exception as e:
        log_test("2d: Disable city alerts", False, f"Error: {e}")
    
    # Test 2e: Verify with GET /auth/me
    print(f"\n--- Test 2e: Verify city_change_alerts is False ---")
    try:
        response = requests.get(
            f"{BASE_URL}/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        if response.status_code != 200:
            log_test("2e: Get /auth/me status", False, f"Expected 200, got {response.status_code}")
        else:
            log_test("2e: Get /auth/me status", True, "200 OK")
            
            data = response.json()
            city_change_alerts = data.get("city_change_alerts")
            
            if city_change_alerts is False:
                log_test("2e: city_change_alerts reflects False", True, f"Value: {city_change_alerts}")
            else:
                log_test("2e: city_change_alerts reflects False", False, f"Expected False, got {city_change_alerts}")
    
    except Exception as e:
        log_test("2e: Verify disabled", False, f"Error: {e}")


def test_event_follow_regression(token, user_id):
    """Test 3: REGRESSION - Event follow endpoints still work"""
    print("\n" + "="*80)
    print("TEST 3: REGRESSION - EVENT FOLLOW ENDPOINTS")
    print("="*80)
    
    # Get an event from the feed
    print(f"\n--- Get an event from feed ---")
    try:
        response = requests.get(
            f"{BASE_URL}/events",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        if response.status_code != 200:
            log_test("3: Get events status", False, f"Expected 200, got {response.status_code}")
            return
        
        events = response.json()
        
        if not events or not isinstance(events, list):
            log_test("3: Get events", False, "No events found in feed")
            return
        
        event_id = events[0].get("id")
        log_test("3: Get events", True, f"Found event: {event_id}")
        
        # Test 3a: Follow event
        print(f"\n--- Test 3a: Follow event {event_id} ---")
        response = requests.post(
            f"{BASE_URL}/events/{event_id}/follow",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        if response.status_code != 200:
            log_test("3a: POST /events/{id}/follow", False, f"Expected 200, got {response.status_code}")
        else:
            log_test("3a: POST /events/{id}/follow", True, "Event followed successfully")
        
        # Test 3b: Verify is_following flag in feed
        print(f"\n--- Test 3b: Verify is_following flag ---")
        response = requests.get(
            f"{BASE_URL}/events",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        if response.status_code != 200:
            log_test("3b: Get events after follow", False, f"Expected 200, got {response.status_code}")
        else:
            events = response.json()
            
            followed_event = None
            for event in events:
                if event.get("id") == event_id:
                    followed_event = event
                    break
            
            if not followed_event:
                log_test("3b: Event found in feed", False, "Event not found")
            else:
                is_following = followed_event.get("is_following")
                if is_following is True:
                    log_test("3b: is_following flag is True", True)
                else:
                    log_test("3b: is_following flag is True", False, f"Expected True, got {is_following}")
        
        # Test 3c: Unfollow event
        print(f"\n--- Test 3c: Unfollow event {event_id} ---")
        response = requests.delete(
            f"{BASE_URL}/events/{event_id}/follow",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        if response.status_code != 200:
            log_test("3c: DELETE /events/{id}/follow", False, f"Expected 200, got {response.status_code}")
        else:
            log_test("3c: DELETE /events/{id}/follow", True, "Event unfollowed successfully")
        
        # Test 3d: Verify is_following flag is False
        print(f"\n--- Test 3d: Verify is_following flag is False ---")
        response = requests.get(
            f"{BASE_URL}/events",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        if response.status_code != 200:
            log_test("3d: Get events after unfollow", False, f"Expected 200, got {response.status_code}")
        else:
            events = response.json()
            
            unfollowed_event = None
            for event in events:
                if event.get("id") == event_id:
                    unfollowed_event = event
                    break
            
            if not unfollowed_event:
                log_test("3d: Event found in feed", False, "Event not found")
            else:
                is_following = unfollowed_event.get("is_following")
                if is_following is False:
                    log_test("3d: is_following flag is False", True)
                else:
                    log_test("3d: is_following flag is False", False, f"Expected False, got {is_following}")
        
        # Test 3e: Verify feed returns only user's city events
        print(f"\n--- Test 3e: Verify feed filters by user's city ---")
        response = requests.get(
            f"{BASE_URL}/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        if response.status_code != 200:
            log_test("3e: Get user city", False, f"Expected 200, got {response.status_code}")
        else:
            user_data = response.json()
            user_city = user_data.get("city")
            
            response = requests.get(
                f"{BASE_URL}/events",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10
            )
            
            if response.status_code != 200:
                log_test("3e: Get events for city filter check", False, f"Expected 200, got {response.status_code}")
            else:
                events = response.json()
                
                all_same_city = True
                for event in events[:10]:  # Check first 10 events
                    event_city = event.get("city")
                    if event_city != user_city:
                        all_same_city = False
                        log_test("3e: Event city matches user city", False, f"Event city '{event_city}' != user city '{user_city}'")
                        break
                
                if all_same_city:
                    log_test("3e: Feed filters by user's city", True, f"All events are from '{user_city}'")
    
    except Exception as e:
        log_test("3: Event follow regression", False, f"Error: {e}")


def print_summary():
    """Print test summary"""
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"Total tests: {tests_passed + tests_failed}")
    print(f"✅ Passed: {tests_passed}")
    print(f"❌ Failed: {tests_failed}")
    print(f"Success rate: {tests_passed / (tests_passed + tests_failed) * 100:.1f}%")
    
    if tests_failed > 0:
        print("\n" + "="*80)
        print("FAILED TESTS:")
        print("="*80)
        for detail in test_details:
            if not detail["passed"]:
                print(f"❌ {detail['test']}")
                if detail["details"]:
                    print(f"   {detail['details']}")


def main():
    """Main test runner"""
    print("="*80)
    print("FASE 3 BACKEND TESTING - ¿Quién va?")
    print("="*80)
    print(f"Base URL: {BASE_URL}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    # Run tests
    token, user_id = test_username_privacy()
    test_city_alerts_opt_in()
    
    if token and user_id:
        test_event_follow_regression(token, user_id)
    else:
        print("\n⚠️  Skipping regression tests - no valid user token")
    
    # Print summary
    print_summary()
    
    # Exit with appropriate code
    sys.exit(0 if tests_failed == 0 else 1)


if __name__ == "__main__":
    main()
