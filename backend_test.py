#!/usr/bin/env python3
"""
Backend test for ¿Quién va? - Album Private + Selective Sharing + Active Moment
Testing iteration: Album redesign with private-by-default and selective sharing
"""

import requests
import json
import time
from io import BytesIO

# Base URL from frontend/.env
BASE_URL = "https://bereal-clone-1.preview.emergentagent.com/api"

# Test credentials
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

# Color codes for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"

def log_test(name, passed, details=""):
    status = f"{GREEN}✅ PASS{RESET}" if passed else f"{RED}❌ FAIL{RESET}"
    print(f"{status} - {name}")
    if details:
        print(f"  {details}")

def log_section(name):
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}{name}{RESET}")
    print(f"{BLUE}{'='*80}{RESET}\n")

# Test state
test_results = {"passed": 0, "failed": 0, "tests": []}

def register_result(name, passed, details=""):
    test_results["tests"].append({"name": name, "passed": passed, "details": details})
    if passed:
        test_results["passed"] += 1
    else:
        test_results["failed"] += 1
    log_test(name, passed, details)

# ============================================================================
# SETUP: Login and create test users
# ============================================================================

log_section("SETUP: Authentication and User Creation")

# Login as admin
resp = requests.post(f"{BASE_URL}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
if resp.status_code != 200:
    print(f"{RED}FATAL: Admin login failed: {resp.status_code} {resp.text}{RESET}")
    exit(1)

admin_token = resp.json()["token"]
admin_headers = {"Authorization": f"Bearer {admin_token}"}
print(f"{GREEN}✓ Admin logged in{RESET}")

# Create User A
user_a_email = f"usera_{int(time.time())}@test.com"
user_a_password = "password123"
resp = requests.post(f"{BASE_URL}/auth/register", json={
    "email": user_a_email,
    "password": user_a_password,
    "name": "User A",
    "username": f"usera_{int(time.time())}",
    "city": "Palma"
})
if resp.status_code != 200:
    print(f"{RED}FATAL: User A registration failed: {resp.status_code} {resp.text}{RESET}")
    exit(1)

user_a_data = resp.json()
user_a_token = user_a_data["token"]
user_a_id = user_a_data["user"]["user_id"]
user_a_headers = {"Authorization": f"Bearer {user_a_token}"}
print(f"{GREEN}✓ User A created: {user_a_id}{RESET}")

# Create User B
user_b_email = f"userb_{int(time.time())}@test.com"
user_b_password = "password123"
resp = requests.post(f"{BASE_URL}/auth/register", json={
    "email": user_b_email,
    "password": user_b_password,
    "name": "User B",
    "username": f"userb_{int(time.time())}",
    "city": "Palma"
})
if resp.status_code != 200:
    print(f"{RED}FATAL: User B registration failed: {resp.status_code} {resp.text}{RESET}")
    exit(1)

user_b_data = resp.json()
user_b_token = user_b_data["token"]
user_b_id = user_b_data["user"]["user_id"]
user_b_headers = {"Authorization": f"Bearer {user_b_token}"}
print(f"{GREEN}✓ User B created: {user_b_id}{RESET}")

# Create User C (non-friend)
user_c_email = f"userc_{int(time.time())}@test.com"
user_c_password = "password123"
resp = requests.post(f"{BASE_URL}/auth/register", json={
    "email": user_c_email,
    "password": user_c_password,
    "name": "User C",
    "username": f"userc_{int(time.time())}",
    "city": "Palma"
})
if resp.status_code != 200:
    print(f"{RED}FATAL: User C registration failed: {resp.status_code} {resp.text}{RESET}")
    exit(1)

user_c_data = resp.json()
user_c_token = user_c_data["token"]
user_c_id = user_c_data["user"]["user_id"]
user_c_headers = {"Authorization": f"Bearer {user_c_token}"}
print(f"{GREEN}✓ User C created: {user_c_id}{RESET}")

# Make A and B friends
resp = requests.post(f"{BASE_URL}/friends/request", json={"user_id": user_b_id}, headers=user_a_headers)
if resp.status_code != 200:
    print(f"{RED}FATAL: Friend request failed: {resp.status_code} {resp.text}{RESET}")
    exit(1)
print(f"{GREEN}✓ User A sent friend request to User B{RESET}")

# Get the request_id from the response
friend_request_data = resp.json()
request_id = friend_request_data.get("request_id")

resp = requests.post(f"{BASE_URL}/friends/respond", json={"request_id": request_id, "accept": True}, headers=user_b_headers)
if resp.status_code != 200:
    print(f"{RED}FATAL: Friend accept failed: {resp.status_code} {resp.text}{RESET}")
    exit(1)
print(f"{GREEN}✓ User B accepted friend request from User A{RESET}")

# Get an event to test with
resp = requests.get(f"{BASE_URL}/events", headers=admin_headers)
if resp.status_code != 200 or not resp.json():
    print(f"{RED}FATAL: No events available: {resp.status_code}{RESET}")
    exit(1)

test_event = resp.json()[0]
event_id = test_event["id"]
print(f"{GREEN}✓ Using event: {test_event['name']} (ID: {event_id}){RESET}")

# Both A and B mark interest "voy" on the event
resp = requests.post(f"{BASE_URL}/events/{event_id}/interest", json={"status": "voy"}, headers=user_a_headers)
register_result("User A marks 'voy' on event", resp.status_code == 200)

resp = requests.post(f"{BASE_URL}/events/{event_id}/interest", json={"status": "voy"}, headers=user_b_headers)
register_result("User B marks 'voy' on event", resp.status_code == 200)

# User C also marks interest (for testing)
resp = requests.post(f"{BASE_URL}/events/{event_id}/interest", json={"status": "voy"}, headers=user_c_headers)
register_result("User C marks 'voy' on event", resp.status_code == 200)

# ============================================================================
# TEST 1: ALBUM PRIVATE + SELECTIVE SHARING
# ============================================================================

log_section("TEST 1: ALBUM PRIVATE + SELECTIVE SHARING")

# 1.1: User A uploads a photo (should be private by default)
print(f"\n{YELLOW}Test 1.1: User A uploads photo (private by default){RESET}")
fake_image = BytesIO(b"fake_jpeg_data_for_testing")
fake_image.name = "test.jpg"
files = {"file": ("test.jpg", fake_image, "image/jpeg")}
resp = requests.post(f"{BASE_URL}/events/{event_id}/album/upload", files=files, headers=user_a_headers)
register_result("User A uploads photo", resp.status_code == 200)

if resp.status_code == 200:
    upload_data = resp.json()
    upload_id = upload_data["id"]
    register_result("Upload has 'shared=false' by default", upload_data.get("shared") == False)
    register_result("Upload has empty sharing lists", 
                   upload_data.get("shared_with_users") == [] and 
                   upload_data.get("shared_with_groups") == [])
    print(f"  Upload ID: {upload_id}")
else:
    print(f"{RED}  Failed to upload: {resp.text}{RESET}")
    upload_id = None

# 1.2: User without interest tries to upload (should get 403)
print(f"\n{YELLOW}Test 1.2: User without interest tries to upload{RESET}")
# Create a user with no interest
user_d_email = f"userd_{int(time.time())}@test.com"
resp = requests.post(f"{BASE_URL}/auth/register", json={
    "email": user_d_email,
    "password": "password123",
    "name": "User D",
    "username": f"userd_{int(time.time())}",
    "city": "Palma"
})
user_d_token = resp.json()["token"]
user_d_headers = {"Authorization": f"Bearer {user_d_token}"}

fake_image2 = BytesIO(b"fake_jpeg_data_for_testing")
files2 = {"file": ("test2.jpg", fake_image2, "image/jpeg")}
resp = requests.post(f"{BASE_URL}/events/{event_id}/album/upload", files=files2, headers=user_d_headers)
register_result("Upload without interest returns 403", resp.status_code == 403)

# 1.3: User B gets album (should NOT see A's private photo)
print(f"\n{YELLOW}Test 1.3: User B gets album (should NOT see A's private photo){RESET}")
resp = requests.get(f"{BASE_URL}/events/{event_id}/album", headers=user_b_headers)
register_result("User B can get album", resp.status_code == 200)

if resp.status_code == 200:
    album_data = resp.json()
    register_result("User B's 'mine' is empty", len(album_data.get("mine", [])) == 0)
    register_result("User B's 'shared' is empty (A's photo is private)", len(album_data.get("shared", [])) == 0)
    register_result("Album has correct structure", 
                   "event" in album_data and 
                   "mine" in album_data and 
                   "shared" in album_data and
                   "can_upload" in album_data and
                   "total_mine" in album_data and
                   "total_shared" in album_data)

# 1.4: User A shares with User B
print(f"\n{YELLOW}Test 1.4: User A shares photo with User B{RESET}")
if upload_id:
    resp = requests.post(f"{BASE_URL}/events/{event_id}/album/{upload_id}/share", 
                        json={"user_ids": [user_b_id], "group_ids": [], "all_friends": False},
                        headers=user_a_headers)
    register_result("User A shares with User B", resp.status_code == 200)
    
    if resp.status_code == 200:
        share_data = resp.json()
        register_result("Share response has 'shared=true'", share_data.get("shared") == True)

# 1.5: User B gets album again (should now see A's photo in 'shared')
print(f"\n{YELLOW}Test 1.5: User B gets album (should now see A's photo in 'shared'){RESET}")
resp = requests.get(f"{BASE_URL}/events/{event_id}/album", headers=user_b_headers)
register_result("User B can get album", resp.status_code == 200)

if resp.status_code == 200:
    album_data = resp.json()
    shared_items = album_data.get("shared", [])
    register_result("User B sees photo in 'shared'", len(shared_items) > 0)
    if len(shared_items) > 0:
        shared_photo = shared_items[0]
        register_result("Shared photo has 'is_mine=false'", shared_photo.get("is_mine") == False)
        register_result("Shared photo has author info", "author" in shared_photo)

# 1.6: User A gets album (should see photo in both 'mine' and 'shared')
print(f"\n{YELLOW}Test 1.6: User A gets album (should see photo in 'mine' and 'shared'){RESET}")
resp = requests.get(f"{BASE_URL}/events/{event_id}/album", headers=user_a_headers)
register_result("User A can get album", resp.status_code == 200)

if resp.status_code == 200:
    album_data = resp.json()
    mine_items = album_data.get("mine", [])
    shared_items = album_data.get("shared", [])
    register_result("User A sees photo in 'mine'", len(mine_items) > 0)
    register_result("User A sees photo in 'shared' (own shared photo)", len(shared_items) > 0)
    if len(mine_items) > 0:
        my_photo = mine_items[0]
        register_result("Photo in 'mine' has 'shared=true'", my_photo.get("shared") == True)

# 1.7: User B tries to share A's upload (should get 403)
print(f"\n{YELLOW}Test 1.7: User B tries to share A's upload (should get 403){RESET}")
if upload_id:
    resp = requests.post(f"{BASE_URL}/events/{event_id}/album/{upload_id}/share",
                        json={"user_ids": [user_c_id], "group_ids": [], "all_friends": False},
                        headers=user_b_headers)
    register_result("User B cannot share A's upload (403)", resp.status_code == 403)

# 1.8: User B tries to delete A's upload (should get 403)
print(f"\n{YELLOW}Test 1.8: User B tries to delete A's upload (should get 403){RESET}")
if upload_id:
    resp = requests.delete(f"{BASE_URL}/events/{event_id}/album/{upload_id}", headers=user_b_headers)
    register_result("User B cannot delete A's upload (403)", resp.status_code == 403)

# 1.9: User A unshares the photo
print(f"\n{YELLOW}Test 1.9: User A unshares the photo{RESET}")
if upload_id:
    resp = requests.post(f"{BASE_URL}/events/{event_id}/album/{upload_id}/unshare", headers=user_a_headers)
    register_result("User A unshares photo", resp.status_code == 200)
    
    if resp.status_code == 200:
        unshare_data = resp.json()
        register_result("Unshare response has 'shared=false'", unshare_data.get("shared") == False)

# 1.10: User B gets album (should NOT see A's photo anymore)
print(f"\n{YELLOW}Test 1.10: User B gets album (should NOT see A's photo anymore){RESET}")
resp = requests.get(f"{BASE_URL}/events/{event_id}/album", headers=user_b_headers)
register_result("User B can get album", resp.status_code == 200)

if resp.status_code == 200:
    album_data = resp.json()
    shared_items = album_data.get("shared", [])
    register_result("User B's 'shared' is empty (photo unshared)", len(shared_items) == 0)

# 1.11: Test all_friends sharing
print(f"\n{YELLOW}Test 1.11: User A shares with all_friends=true{RESET}")
if upload_id:
    resp = requests.post(f"{BASE_URL}/events/{event_id}/album/{upload_id}/share",
                        json={"user_ids": [], "group_ids": [], "all_friends": True},
                        headers=user_a_headers)
    register_result("User A shares with all_friends", resp.status_code == 200)

# 1.12: User B (friend) gets album (should see photo)
print(f"\n{YELLOW}Test 1.12: User B (friend) gets album (should see photo){RESET}")
resp = requests.get(f"{BASE_URL}/events/{event_id}/album", headers=user_b_headers)
register_result("User B can get album", resp.status_code == 200)

if resp.status_code == 200:
    album_data = resp.json()
    shared_items = album_data.get("shared", [])
    register_result("User B (friend) sees photo in 'shared'", len(shared_items) > 0)

# 1.13: User C (non-friend with interest) gets album (should NOT see photo)
print(f"\n{YELLOW}Test 1.13: User C (non-friend) gets album (should NOT see photo){RESET}")
resp = requests.get(f"{BASE_URL}/events/{event_id}/album", headers=user_c_headers)
register_result("User C can get album", resp.status_code == 200)

if resp.status_code == 200:
    album_data = resp.json()
    shared_items = album_data.get("shared", [])
    register_result("User C (non-friend) does NOT see photo", len(shared_items) == 0)

# 1.14: Test group sharing
print(f"\n{YELLOW}Test 1.14: Test group sharing{RESET}")
# Create a group with A and B
resp = requests.post(f"{BASE_URL}/groups", 
                    json={"name": "Test Group", "member_ids": [user_b_id]},
                    headers=user_a_headers)
register_result("User A creates group with User B", resp.status_code == 200)

if resp.status_code == 200:
    group_data = resp.json()
    group_id = group_data["id"]
    print(f"  Group ID: {group_id}")
    
    # Unshare first
    if upload_id:
        resp = requests.post(f"{BASE_URL}/events/{event_id}/album/{upload_id}/unshare", headers=user_a_headers)
        
        # Share with group
        resp = requests.post(f"{BASE_URL}/events/{event_id}/album/{upload_id}/share",
                            json={"user_ids": [], "group_ids": [group_id], "all_friends": False},
                            headers=user_a_headers)
        register_result("User A shares with group", resp.status_code == 200)
        
        # User B should see it
        resp = requests.get(f"{BASE_URL}/events/{event_id}/album", headers=user_b_headers)
        if resp.status_code == 200:
            album_data = resp.json()
            shared_items = album_data.get("shared", [])
            register_result("User B (group member) sees photo", len(shared_items) > 0)

# 1.15: Test sanitization (share with non-friend)
print(f"\n{YELLOW}Test 1.15: Test sanitization (share with non-friend){RESET}")
if upload_id:
    # Unshare first
    resp = requests.post(f"{BASE_URL}/events/{event_id}/album/{upload_id}/unshare", headers=user_a_headers)
    
    # Try to share with User C (non-friend)
    resp = requests.post(f"{BASE_URL}/events/{event_id}/album/{upload_id}/share",
                        json={"user_ids": [user_c_id], "group_ids": [], "all_friends": False},
                        headers=user_a_headers)
    register_result("Share request with non-friend returns 200 (sanitized)", resp.status_code == 200)
    
    # User C should NOT see it
    resp = requests.get(f"{BASE_URL}/events/{event_id}/album", headers=user_c_headers)
    if resp.status_code == 200:
        album_data = resp.json()
        shared_items = album_data.get("shared", [])
        register_result("User C (non-friend) does NOT see photo (sanitized)", len(shared_items) == 0)

# 1.16: Test 404 on non-existent upload
print(f"\n{YELLOW}Test 1.16: Test 404 on non-existent upload{RESET}")
fake_upload_id = "nonexistent-upload-id"
resp = requests.post(f"{BASE_URL}/events/{event_id}/album/{fake_upload_id}/share",
                    json={"user_ids": [user_b_id], "group_ids": [], "all_friends": False},
                    headers=user_a_headers)
register_result("Share non-existent upload returns 404", resp.status_code == 404)

resp = requests.post(f"{BASE_URL}/events/{event_id}/album/{fake_upload_id}/unshare", headers=user_a_headers)
register_result("Unshare non-existent upload returns 404", resp.status_code == 404)

resp = requests.delete(f"{BASE_URL}/events/{event_id}/album/{fake_upload_id}", headers=user_a_headers)
register_result("Delete non-existent upload returns 404", resp.status_code == 404)

# ============================================================================
# TEST 2: GET /api/me/active-moment
# ============================================================================

log_section("TEST 2: GET /api/me/active-moment")

# 2.1: Fresh user with no interest (should return active=false)
print(f"\n{YELLOW}Test 2.1: Fresh user with no interest{RESET}")
user_e_email = f"usere_{int(time.time())}@test.com"
resp = requests.post(f"{BASE_URL}/auth/register", json={
    "email": user_e_email,
    "password": "password123",
    "name": "User E",
    "username": f"usere_{int(time.time())}",
    "city": "Palma"
})
user_e_token = resp.json()["token"]
user_e_headers = {"Authorization": f"Bearer {user_e_token}"}

resp = requests.get(f"{BASE_URL}/me/active-moment", headers=user_e_headers)
register_result("Fresh user with no interest", resp.status_code == 200)

if resp.status_code == 200:
    moment_data = resp.json()
    register_result("Returns active=false", moment_data.get("active") == False)

# 2.2: User marks voy, admin triggers moment, check active-moment
print(f"\n{YELLOW}Test 2.2: User marks voy, admin triggers moment{RESET}")
# User E marks voy on event
resp = requests.post(f"{BASE_URL}/events/{event_id}/interest", json={"status": "voy"}, headers=user_e_headers)
register_result("User E marks 'voy' on event", resp.status_code == 200)

# Admin triggers moment
resp = requests.post(f"{BASE_URL}/admin/events/{event_id}/moment/trigger", headers=admin_headers)
register_result("Admin triggers moment", resp.status_code == 200)

# Check active-moment for User E
resp = requests.get(f"{BASE_URL}/me/active-moment", headers=user_e_headers)
register_result("User E gets active-moment", resp.status_code == 200)

if resp.status_code == 200:
    moment_data = resp.json()
    register_result("Returns active=true", moment_data.get("active") == True)
    register_result("Has event_id", "event_id" in moment_data)
    register_result("Has event_name", "event_name" in moment_data)
    register_result("Has prompt", "prompt" in moment_data)
    register_result("Has on_time (bool)", isinstance(moment_data.get("on_time"), bool))
    register_result("Has friends_captured (int)", isinstance(moment_data.get("friends_captured"), int))
    print(f"  Active moment: {moment_data.get('event_name')}")
    print(f"  On time: {moment_data.get('on_time')}")
    print(f"  Friends captured: {moment_data.get('friends_captured')}")

# 2.3: User uploads capture, check active-moment (should be false)
print(f"\n{YELLOW}Test 2.3: User uploads capture, check active-moment{RESET}")
fake_capture = BytesIO(b"fake_capture_data")
files = {"file": ("capture.jpg", fake_capture, "image/jpeg")}
resp = requests.post(f"{BASE_URL}/events/{event_id}/moment/upload", files=files, headers=user_e_headers)
register_result("User E uploads capture", resp.status_code == 200)

# Check active-moment again
resp = requests.get(f"{BASE_URL}/me/active-moment", headers=user_e_headers)
register_result("User E gets active-moment after capture", resp.status_code == 200)

if resp.status_code == 200:
    moment_data = resp.json()
    register_result("Returns active=false after capture", moment_data.get("active") == False)

# ============================================================================
# TEST 3: REGRESSION TESTS
# ============================================================================

log_section("TEST 3: REGRESSION TESTS")

# 3.1: Auth endpoints
print(f"\n{YELLOW}Test 3.1: Auth endpoints{RESET}")
resp = requests.post(f"{BASE_URL}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
register_result("POST /auth/login", resp.status_code == 200)

resp = requests.get(f"{BASE_URL}/auth/me", headers=admin_headers)
register_result("GET /auth/me", resp.status_code == 200)

# 3.2: Events endpoints
print(f"\n{YELLOW}Test 3.2: Events endpoints{RESET}")
resp = requests.get(f"{BASE_URL}/events", headers=admin_headers)
register_result("GET /events", resp.status_code == 200)

# 3.3: Interest endpoints
print(f"\n{YELLOW}Test 3.3: Interest endpoints{RESET}")
resp = requests.post(f"{BASE_URL}/events/{event_id}/interest", json={"status": "me_interesa"}, headers=admin_headers)
register_result("POST /events/{id}/interest", resp.status_code == 200)

# 3.4: Moment endpoints
print(f"\n{YELLOW}Test 3.4: Moment endpoints{RESET}")
resp = requests.get(f"{BASE_URL}/events/{event_id}/moment/status", headers=admin_headers)
register_result("GET /events/{id}/moment/status", resp.status_code == 200)

resp = requests.get(f"{BASE_URL}/events/{event_id}/moment/gallery", headers=user_e_headers)
# Should be 200 since user E uploaded
register_result("GET /events/{id}/moment/gallery", resp.status_code == 200)

# 3.5: Groups endpoints
print(f"\n{YELLOW}Test 3.5: Groups endpoints{RESET}")
resp = requests.get(f"{BASE_URL}/groups", headers=admin_headers)
register_result("GET /groups", resp.status_code == 200)

# 3.6: Friends endpoints
print(f"\n{YELLOW}Test 3.6: Friends endpoints{RESET}")
resp = requests.get(f"{BASE_URL}/friends", headers=admin_headers)
register_result("GET /friends", resp.status_code == 200)

# 3.7: Badges endpoints
print(f"\n{YELLOW}Test 3.7: Badges endpoints{RESET}")
resp = requests.get(f"{BASE_URL}/me/badges", headers=admin_headers)
register_result("GET /me/badges", resp.status_code == 200)

# 3.8: Rankings endpoints
print(f"\n{YELLOW}Test 3.8: Rankings endpoints{RESET}")
resp = requests.get(f"{BASE_URL}/rankings/world", headers=admin_headers)
register_result("GET /rankings/world", resp.status_code == 200)

# 3.9: Health endpoint
print(f"\n{YELLOW}Test 3.9: Health endpoint{RESET}")
resp = requests.get(f"{BASE_URL}/health")
register_result("GET /health", resp.status_code == 200)

# ============================================================================
# SUMMARY
# ============================================================================

log_section("TEST SUMMARY")

total_tests = test_results["passed"] + test_results["failed"]
pass_rate = (test_results["passed"] / total_tests * 100) if total_tests > 0 else 0

print(f"\n{BLUE}Total Tests: {total_tests}{RESET}")
print(f"{GREEN}Passed: {test_results['passed']}{RESET}")
print(f"{RED}Failed: {test_results['failed']}{RESET}")
print(f"{BLUE}Pass Rate: {pass_rate:.1f}%{RESET}\n")

if test_results["failed"] > 0:
    print(f"{RED}FAILED TESTS:{RESET}")
    for test in test_results["tests"]:
        if not test["passed"]:
            print(f"  ❌ {test['name']}")
            if test["details"]:
                print(f"     {test['details']}")

print(f"\n{BLUE}{'='*80}{RESET}\n")
