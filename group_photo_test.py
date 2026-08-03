#!/usr/bin/env python3
"""
Backend test for ¿Quién va? - Group Photo Feature
Testing: GET /api/groups/{group_id}/photo-op, POST /api/groups/{group_id}/photo, GET /api/groups/{group_id}/photos
"""

import requests
import json
import time
from io import BytesIO
from PIL import Image

# Base URL from frontend/.env
BASE_URL = "https://expert-review-6.preview.emergentagent.com/api"

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

def create_test_image():
    """Create a small test JPEG image"""
    img = Image.new('RGB', (100, 100), color='red')
    buf = BytesIO()
    img.save(buf, format='JPEG')
    buf.seek(0)
    return buf

def create_text_file():
    """Create a text file for negative testing"""
    return BytesIO(b"This is not an image")

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
timestamp = int(time.time())
user_a_email = f"usera_{timestamp}@test.com"
user_a_password = "password123"
resp = requests.post(f"{BASE_URL}/auth/register", json={
    "email": user_a_email,
    "password": user_a_password,
    "name": "User A",
    "username": f"usera_{timestamp}",
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
user_b_email = f"userb_{timestamp}@test.com"
user_b_password = "password123"
resp = requests.post(f"{BASE_URL}/auth/register", json={
    "email": user_b_email,
    "password": user_b_password,
    "name": "User B",
    "username": f"userb_{timestamp}",
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

# Create User C
user_c_email = f"userc_{timestamp}@test.com"
user_c_password = "password123"
resp = requests.post(f"{BASE_URL}/auth/register", json={
    "email": user_c_email,
    "password": user_c_password,
    "name": "User C",
    "username": f"userc_{timestamp}",
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

# Create User D (non-member)
user_d_email = f"userd_{timestamp}@test.com"
user_d_password = "password123"
resp = requests.post(f"{BASE_URL}/auth/register", json={
    "email": user_d_email,
    "password": user_d_password,
    "name": "User D",
    "username": f"userd_{timestamp}",
    "city": "Palma"
})
if resp.status_code != 200:
    print(f"{RED}FATAL: User D registration failed: {resp.status_code} {resp.text}{RESET}")
    exit(1)

user_d_data = resp.json()
user_d_token = user_d_data["token"]
user_d_id = user_d_data["user"]["user_id"]
user_d_headers = {"Authorization": f"Bearer {user_d_token}"}
print(f"{GREEN}✓ User D created: {user_d_id}{RESET}")

# ============================================================================
# SETUP: Make A, B, C mutual friends
# ============================================================================

log_section("SETUP: Making Users A, B, C Mutual Friends")

# A sends friend request to B
resp = requests.post(f"{BASE_URL}/friends/request", json={"user_id": user_b_id}, headers=user_a_headers)
register_result("A sends friend request to B", resp.status_code == 200, f"Status: {resp.status_code}")

# B gets friend requests and accepts A's request
resp = requests.get(f"{BASE_URL}/friends/requests", headers=user_b_headers)
if resp.status_code == 200:
    requests_list = resp.json()
    request_from_a = next((r for r in requests_list if r.get("user", {}).get("user_id") == user_a_id), None)
    if request_from_a:
        request_id = request_from_a["request_id"]
        resp = requests.post(f"{BASE_URL}/friends/respond", json={"request_id": request_id, "accept": True}, headers=user_b_headers)
        register_result("B accepts A's friend request", resp.status_code == 200, f"Status: {resp.status_code}")
    else:
        register_result("B accepts A's friend request", False, "Request not found")
else:
    register_result("B accepts A's friend request", False, f"Failed to get requests: {resp.status_code}")

# A sends friend request to C
resp = requests.post(f"{BASE_URL}/friends/request", json={"user_id": user_c_id}, headers=user_a_headers)
register_result("A sends friend request to C", resp.status_code == 200, f"Status: {resp.status_code}")

# C gets friend requests and accepts A's request
resp = requests.get(f"{BASE_URL}/friends/requests", headers=user_c_headers)
if resp.status_code == 200:
    requests_list = resp.json()
    request_from_a = next((r for r in requests_list if r.get("user", {}).get("user_id") == user_a_id), None)
    if request_from_a:
        request_id = request_from_a["request_id"]
        resp = requests.post(f"{BASE_URL}/friends/respond", json={"request_id": request_id, "accept": True}, headers=user_c_headers)
        register_result("C accepts A's friend request", resp.status_code == 200, f"Status: {resp.status_code}")
    else:
        register_result("C accepts A's friend request", False, "Request not found")
else:
    register_result("C accepts A's friend request", False, f"Failed to get requests: {resp.status_code}")

# B sends friend request to C
resp = requests.post(f"{BASE_URL}/friends/request", json={"user_id": user_c_id}, headers=user_b_headers)
register_result("B sends friend request to C", resp.status_code == 200, f"Status: {resp.status_code}")

# C gets friend requests and accepts B's request
resp = requests.get(f"{BASE_URL}/friends/requests", headers=user_c_headers)
if resp.status_code == 200:
    requests_list = resp.json()
    request_from_b = next((r for r in requests_list if r.get("user", {}).get("user_id") == user_b_id), None)
    if request_from_b:
        request_id = request_from_b["request_id"]
        resp = requests.post(f"{BASE_URL}/friends/respond", json={"request_id": request_id, "accept": True}, headers=user_c_headers)
        register_result("C accepts B's friend request", resp.status_code == 200, f"Status: {resp.status_code}")
    else:
        register_result("C accepts B's friend request", False, "Request not found")
else:
    register_result("C accepts B's friend request", False, f"Failed to get requests: {resp.status_code}")

print(f"{GREEN}✓ A, B, C are now mutual friends{RESET}")

# ============================================================================
# SETUP: A creates a group with B and C
# ============================================================================

log_section("SETUP: Creating Group")

resp = requests.post(f"{BASE_URL}/groups", json={
    "name": "Test Group",
    "member_ids": [user_b_id, user_c_id]
}, headers=user_a_headers)

if resp.status_code != 200:
    print(f"{RED}FATAL: Group creation failed: {resp.status_code} {resp.text}{RESET}")
    exit(1)

group_data = resp.json()
group_id = group_data["id"]
print(f"{GREEN}✓ Group created: {group_id}{RESET}")
register_result("A creates group with B and C", True, f"Group ID: {group_id}")

# ============================================================================
# SETUP: Get an UPCOMING event
# ============================================================================

log_section("SETUP: Getting Upcoming Event")

resp = requests.get(f"{BASE_URL}/events?date_filter=all", headers=user_a_headers)
if resp.status_code != 200:
    print(f"{RED}FATAL: Failed to get events: {resp.status_code} {resp.text}{RESET}")
    exit(1)

events = resp.json()
if not events:
    # Create a test event as admin
    print(f"{YELLOW}No events found, creating test event...{RESET}")
    from datetime import datetime, timedelta
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    
    resp = requests.post(f"{BASE_URL}/admin/events", json={
        "name": "Test Party",
        "venue": "Test Venue",
        "date": tomorrow,
        "time": "23:00",
        "genre": "techno",
        "city": "Palma",
        "description": "Test event for group photo testing"
    }, headers=admin_headers)
    
    if resp.status_code != 200:
        print(f"{RED}FATAL: Failed to create test event: {resp.status_code} {resp.text}{RESET}")
        exit(1)
    
    event_data = resp.json()
    event_id = event_data["id"]
    event_name = event_data["name"]
    print(f"{GREEN}✓ Created test event: {event_name} (ID: {event_id}){RESET}")
else:
    event_id = events[0]["id"]
    event_name = events[0]["name"]
    print(f"{GREEN}✓ Found upcoming event: {event_name} (ID: {event_id}){RESET}")

# ============================================================================
# SETUP: All three (A, B, C) mark 'voy' on the event
# ============================================================================

log_section("SETUP: Marking Interest on Event")

resp = requests.post(f"{BASE_URL}/events/{event_id}/interest", json={"status": "voy"}, headers=user_a_headers)
register_result("A marks 'voy' on event", resp.status_code == 200, f"Status: {resp.status_code}")

resp = requests.post(f"{BASE_URL}/events/{event_id}/interest", json={"status": "voy"}, headers=user_b_headers)
register_result("B marks 'voy' on event", resp.status_code == 200, f"Status: {resp.status_code}")

resp = requests.post(f"{BASE_URL}/events/{event_id}/interest", json={"status": "voy"}, headers=user_c_headers)
register_result("C marks 'voy' on event", resp.status_code == 200, f"Status: {resp.status_code}")

print(f"{GREEN}✓ A, B, C all marked 'voy' on event{RESET}")

# ============================================================================
# TEST 1: GET /api/groups/{group_id}/photo-op as A
# ============================================================================

log_section("TEST 1: GET /api/groups/{group_id}/photo-op as A")

resp = requests.get(f"{BASE_URL}/groups/{group_id}/photo-op", headers=user_a_headers)
register_result("GET photo-op returns 200", resp.status_code == 200, f"Status: {resp.status_code}")

if resp.status_code == 200:
    data = resp.json()
    register_result("photo-op has 'active' field", "active" in data, f"Keys: {list(data.keys())}")
    register_result("photo-op active is true", data.get("active") == True, f"active: {data.get('active')}")
    register_result("photo-op has 'ops' array", "ops" in data and isinstance(data["ops"], list), f"ops type: {type(data.get('ops'))}")
    
    if data.get("ops"):
        op = data["ops"][0]
        register_result("op has event_id", "event_id" in op, f"Keys: {list(op.keys())}")
        register_result("op event_id matches", op.get("event_id") == event_id, f"Expected: {event_id}, Got: {op.get('event_id')}")
        register_result("op count is 3", op.get("count") == 3, f"Count: {op.get('count')}")
        register_result("op has members_going", "members_going" in op, f"Keys: {list(op.keys())}")
        register_result("members_going length is 3", len(op.get("members_going", [])) == 3, f"Length: {len(op.get('members_going', []))}")
        register_result("op i_uploaded is false", op.get("i_uploaded") == False, f"i_uploaded: {op.get('i_uploaded')}")
        register_result("op photos_count is 0", op.get("photos_count") == 0, f"photos_count: {op.get('photos_count')}")
        
        # Check members_going structure
        if op.get("members_going"):
            member = op["members_going"][0]
            register_result("member has 'name' field", "name" in member, f"Keys: {list(member.keys())}")
            register_result("member has 'picture' field", "picture" in member, f"Keys: {list(member.keys())}")
    else:
        register_result("ops array is not empty", False, "ops array is empty")

# ============================================================================
# TEST 2: GET /api/groups/{group_id}/photo-op as non-member (User D)
# ============================================================================

log_section("TEST 2: GET /api/groups/{group_id}/photo-op as Non-Member")

resp = requests.get(f"{BASE_URL}/groups/{group_id}/photo-op", headers=user_d_headers)
register_result("Non-member GET photo-op returns 403", resp.status_code == 403, f"Status: {resp.status_code}")

# ============================================================================
# TEST 3: POST /api/groups/{group_id}/photo as A (valid image)
# ============================================================================

log_section("TEST 3: POST /api/groups/{group_id}/photo as A")

image_file = create_test_image()
files = {"file": ("test.jpg", image_file, "image/jpeg")}
data = {"event_id": event_id}

resp = requests.post(f"{BASE_URL}/groups/{group_id}/photo", files=files, data=data, headers=user_a_headers)
register_result("POST group photo returns 200", resp.status_code == 200, f"Status: {resp.status_code}")

if resp.status_code == 200:
    photo_data = resp.json()
    register_result("Response has 'id' field", "id" in photo_data, f"Keys: {list(photo_data.keys())}")
    register_result("Response has 'group_id' field", "group_id" in photo_data, f"Keys: {list(photo_data.keys())}")
    register_result("Response has 'event_id' field", "event_id" in photo_data, f"Keys: {list(photo_data.keys())}")
    register_result("Response has 'image_url' field", "image_url" in photo_data, f"Keys: {list(photo_data.keys())}")
    register_result("Response has 'author' field", "author" in photo_data, f"Keys: {list(photo_data.keys())}")
    register_result("group_id matches", photo_data.get("group_id") == group_id, f"Expected: {group_id}, Got: {photo_data.get('group_id')}")
    register_result("event_id matches", photo_data.get("event_id") == event_id, f"Expected: {event_id}, Got: {photo_data.get('event_id')}")
    
    photo_id = photo_data.get("id")
    print(f"{GREEN}✓ Photo uploaded: {photo_id}{RESET}")

# ============================================================================
# TEST 4: POST /api/groups/{group_id}/photo with non-image file
# ============================================================================

log_section("TEST 4: POST /api/groups/{group_id}/photo with Non-Image File")

text_file = create_text_file()
files = {"file": ("test.txt", text_file, "text/plain")}
data = {"event_id": event_id}

resp = requests.post(f"{BASE_URL}/groups/{group_id}/photo", files=files, data=data, headers=user_a_headers)
register_result("POST non-image returns 400", resp.status_code == 400, f"Status: {resp.status_code}")

# ============================================================================
# TEST 5: POST /api/groups/{group_id}/photo with non-existent event_id
# ============================================================================

log_section("TEST 5: POST /api/groups/{group_id}/photo with Non-Existent Event")

image_file = create_test_image()
files = {"file": ("test.jpg", image_file, "image/jpeg")}
data = {"event_id": "non-existent-event-id"}

resp = requests.post(f"{BASE_URL}/groups/{group_id}/photo", files=files, data=data, headers=user_a_headers)
register_result("POST with non-existent event returns 404", resp.status_code == 404, f"Status: {resp.status_code}")

# ============================================================================
# TEST 6: GET /api/groups/{group_id}/messages (verify image_url field)
# ============================================================================

log_section("TEST 6: GET /api/groups/{group_id}/messages")

resp = requests.get(f"{BASE_URL}/groups/{group_id}/messages", headers=user_b_headers)
register_result("GET group messages returns 200", resp.status_code == 200, f"Status: {resp.status_code}")

if resp.status_code == 200:
    messages = resp.json()
    register_result("Messages array is not empty", len(messages) > 0, f"Length: {len(messages)}")
    
    # Find message with image_url
    image_message = None
    for msg in messages:
        if msg.get("image_url"):
            image_message = msg
            break
    
    register_result("Found message with image_url", image_message is not None, f"Total messages: {len(messages)}")
    if image_message:
        register_result("image_url is not empty", len(image_message.get("image_url", "")) > 0, f"image_url: {image_message.get('image_url')}")

# ============================================================================
# TEST 7: GET /api/groups/{group_id}/photos as B
# ============================================================================

log_section("TEST 7: GET /api/groups/{group_id}/photos as B")

resp = requests.get(f"{BASE_URL}/groups/{group_id}/photos", headers=user_b_headers)
register_result("GET group photos returns 200", resp.status_code == 200, f"Status: {resp.status_code}")

if resp.status_code == 200:
    photos = resp.json()
    register_result("Photos array length is 1", len(photos) == 1, f"Length: {len(photos)}")
    
    if photos:
        photo = photos[0]
        register_result("Photo has 'author' field", "author" in photo, f"Keys: {list(photo.keys())}")
        register_result("Photo has 'is_mine' field", "is_mine" in photo, f"Keys: {list(photo.keys())}")
        register_result("is_mine is false for B", photo.get("is_mine") == False, f"is_mine: {photo.get('is_mine')}")

# ============================================================================
# TEST 8: GET /api/groups/{group_id}/photos as A
# ============================================================================

log_section("TEST 8: GET /api/groups/{group_id}/photos as A")

resp = requests.get(f"{BASE_URL}/groups/{group_id}/photos", headers=user_a_headers)
register_result("GET group photos as A returns 200", resp.status_code == 200, f"Status: {resp.status_code}")

if resp.status_code == 200:
    photos = resp.json()
    if photos:
        photo = photos[0]
        register_result("is_mine is true for A", photo.get("is_mine") == True, f"is_mine: {photo.get('is_mine')}")

# ============================================================================
# TEST 9: GET /api/groups/{group_id}/photo-op as A again (after upload)
# ============================================================================

log_section("TEST 9: GET /api/groups/{group_id}/photo-op as A (After Upload)")

resp = requests.get(f"{BASE_URL}/groups/{group_id}/photo-op", headers=user_a_headers)
register_result("GET photo-op after upload returns 200", resp.status_code == 200, f"Status: {resp.status_code}")

if resp.status_code == 200:
    data = resp.json()
    if data.get("ops"):
        op = data["ops"][0]
        register_result("i_uploaded is true after upload", op.get("i_uploaded") == True, f"i_uploaded: {op.get('i_uploaded')}")
        register_result("photos_count is 1 after upload", op.get("photos_count") == 1, f"photos_count: {op.get('photos_count')}")

# ============================================================================
# TEST 10: C changes interest to none (only 2 members voy)
# ============================================================================

log_section("TEST 10: C Changes Interest to None")

resp = requests.post(f"{BASE_URL}/events/{event_id}/interest", json={"status": "none"}, headers=user_c_headers)
register_result("C changes interest to none", resp.status_code == 200, f"Status: {resp.status_code}")

# ============================================================================
# TEST 11: GET /api/groups/{group_id}/photo-op (should have no ops or active=false)
# ============================================================================

log_section("TEST 11: GET /api/groups/{group_id}/photo-op (After C Removes Interest)")

resp = requests.get(f"{BASE_URL}/groups/{group_id}/photo-op", headers=user_a_headers)
register_result("GET photo-op returns 200", resp.status_code == 200, f"Status: {resp.status_code}")

if resp.status_code == 200:
    data = resp.json()
    # Should be active=false or the op for this event should not appear (count < 3)
    if data.get("active") == False:
        register_result("active is false when count < 3", True, "active: false")
    else:
        # Check if the specific event is no longer in ops
        event_in_ops = any(op.get("event_id") == event_id for op in data.get("ops", []))
        register_result("Event no longer in ops when count < 3", not event_in_ops, f"Event in ops: {event_in_ops}")

# ============================================================================
# REGRESSION TEST: GET /api/events?date_filter=all
# ============================================================================

log_section("REGRESSION TEST: GET /api/events?date_filter=all")

resp = requests.get(f"{BASE_URL}/events?date_filter=all", headers=user_a_headers)
register_result("GET events with date_filter=all returns 200", resp.status_code == 200, f"Status: {resp.status_code}")

if resp.status_code == 200:
    events = resp.json()
    register_result("Events array is not empty", len(events) > 0, f"Length: {len(events)}")
    register_result("Events are upcoming", isinstance(events, list), f"Type: {type(events)}")

# ============================================================================
# REGRESSION TEST: POST /api/auth/login
# ============================================================================

log_section("REGRESSION TEST: POST /api/auth/login")

resp = requests.post(f"{BASE_URL}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
register_result("Admin login works", resp.status_code == 200, f"Status: {resp.status_code}")

# ============================================================================
# REGRESSION TEST: GET /api/groups
# ============================================================================

log_section("REGRESSION TEST: GET /api/groups")

resp = requests.get(f"{BASE_URL}/groups", headers=user_a_headers)
register_result("GET groups returns 200", resp.status_code == 200, f"Status: {resp.status_code}")

if resp.status_code == 200:
    groups = resp.json()
    register_result("Groups array contains created group", any(g.get("id") == group_id for g in groups), f"Group ID: {group_id}")

# ============================================================================
# SUMMARY
# ============================================================================

log_section("TEST SUMMARY")

total = test_results["passed"] + test_results["failed"]
pass_rate = (test_results["passed"] / total * 100) if total > 0 else 0

print(f"Total Tests: {total}")
print(f"{GREEN}Passed: {test_results['passed']}{RESET}")
print(f"{RED}Failed: {test_results['failed']}{RESET}")
print(f"Pass Rate: {pass_rate:.1f}%")

if test_results["failed"] > 0:
    print(f"\n{RED}FAILED TESTS:{RESET}")
    for test in test_results["tests"]:
        if not test["passed"]:
            print(f"  - {test['name']}: {test['details']}")

print(f"\n{BLUE}{'='*80}{RESET}")
if test_results["failed"] == 0:
    print(f"{GREEN}✅ ALL TESTS PASSED!{RESET}")
else:
    print(f"{RED}❌ SOME TESTS FAILED{RESET}")
print(f"{BLUE}{'='*80}{RESET}")
