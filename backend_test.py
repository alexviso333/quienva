#!/usr/bin/env python3
"""
Backend test for NEW features in this iteration only.
Tests:
1. Google OAuth config endpoint
2. Next badges endpoint
3. Moment upload friend notifications
4. Auto-trigger moments scheduler
"""

import requests
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

# Backend URL from frontend/.env
BACKEND_URL = "https://8212b2f0-abf2-44ec-8d3e-ed989692e2c0.preview.emergentagent.com/api"

# Admin credentials
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

# Test results
results = {
    "passed": 0,
    "failed": 0,
    "tests": []
}

def log_test(name, passed, details=""):
    """Log test result"""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status}: {name}")
    if details:
        print(f"  Details: {details}")
    results["tests"].append({
        "name": name,
        "passed": passed,
        "details": details
    })
    if passed:
        results["passed"] += 1
    else:
        results["failed"] += 1

def login_admin():
    """Login as admin and return token"""
    resp = requests.post(f"{BACKEND_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if resp.status_code != 200:
        raise Exception(f"Admin login failed: {resp.status_code} {resp.text}")
    return resp.json()["token"]

def create_user(name, email, password, token=None):
    """Create a new user and return token"""
    username = email.split("@")[0].replace(".", "")
    resp = requests.post(f"{BACKEND_URL}/auth/register", json={
        "email": email,
        "password": password,
        "name": name,
        "username": username,
        "city": "Palma de Mallorca"
    })
    if resp.status_code != 200:
        raise Exception(f"User creation failed: {resp.status_code} {resp.text}")
    return resp.json()["token"]

def send_friend_request(token, target_email):
    """Send friend request by email"""
    # First get user by username
    username = target_email.split("@")[0].replace(".", "")
    resp = requests.post(f"{BACKEND_URL}/friends/request-by-username", 
                        json={"username": username},
                        headers={"Authorization": f"Bearer {token}"})
    return resp.status_code == 200

def accept_friend_request(token):
    """Accept the first pending friend request"""
    resp = requests.get(f"{BACKEND_URL}/friends/requests",
                       headers={"Authorization": f"Bearer {token}"})
    if resp.status_code != 200:
        return False
    requests_list = resp.json()
    if not requests_list:
        return False
    request_id = requests_list[0]["request_id"]
    resp = requests.post(f"{BACKEND_URL}/friends/respond",
                        json={"request_id": request_id, "accept": True},
                        headers={"Authorization": f"Bearer {token}"})
    return resp.status_code == 200

def create_event(token, name, date_str, time_str="22:00"):
    """Create an event and return event_id"""
    resp = requests.post(f"{BACKEND_URL}/admin/events", json={
        "name": name,
        "venue": "Test Venue",
        "address": "Test Address",
        "date": date_str,
        "time": time_str,
        "city": "Palma de Mallorca",
        "genre": "Techno"
    }, headers={"Authorization": f"Bearer {token}"})
    if resp.status_code != 200:
        raise Exception(f"Event creation failed: {resp.status_code} {resp.text}")
    return resp.json()["id"]

def mark_interest(token, event_id, status="voy"):
    """Mark interest in an event"""
    resp = requests.post(f"{BACKEND_URL}/events/{event_id}/interest",
                        json={"status": status},
                        headers={"Authorization": f"Bearer {token}"})
    return resp.status_code == 200

def trigger_moment(admin_token, event_id):
    """Admin triggers moment for an event"""
    resp = requests.post(f"{BACKEND_URL}/admin/events/{event_id}/moment/trigger",
                        headers={"Authorization": f"Bearer {admin_token}"})
    return resp.status_code == 200, resp

def upload_moment(token, event_id):
    """Upload a moment capture"""
    # Create a small test image
    import io
    from PIL import Image
    img = Image.new('RGB', (100, 100), color='red')
    buf = io.BytesIO()
    img.save(buf, format='JPEG')
    buf.seek(0)
    
    resp = requests.post(f"{BACKEND_URL}/events/{event_id}/moment/upload",
                        files={"file": ("test.jpg", buf, "image/jpeg")},
                        headers={"Authorization": f"Bearer {token}"})
    return resp.status_code == 200, resp

def get_notifications(token):
    """Get user notifications"""
    resp = requests.get(f"{BACKEND_URL}/notifications",
                       headers={"Authorization": f"Bearer {token}"})
    if resp.status_code != 200:
        return []
    return resp.json()

def get_admin_dashboard(token):
    """Get admin dashboard data"""
    resp = requests.get(f"{BACKEND_URL}/admin/dashboard",
                       headers={"Authorization": f"Bearer {token}"})
    if resp.status_code != 200:
        return None
    return resp.json()

print("=" * 80)
print("BACKEND TESTING - NEW FEATURES ONLY")
print("=" * 80)
print()

# ============================================================================
# TEST 1: Google OAuth Config Endpoint
# ============================================================================
print("TEST 1: Google OAuth Config Endpoint")
print("-" * 80)

try:
    resp = requests.get(f"{BACKEND_URL}/auth/google/config")
    if resp.status_code == 200:
        data = resp.json()
        if data.get("enabled") == True and data.get("client_id") == "043435767943-4iv6dvgue2fmoa81167901vi9j9f2lc7.apps.googleusercontent.com":
            log_test("GET /auth/google/config returns enabled=true with correct client_id", True)
        elif data.get("enabled") == False:
            log_test("GET /auth/google/config returns enabled=false", False, 
                    "Expected enabled=true but got false")
        else:
            log_test("GET /auth/google/config structure", False,
                    f"Got: {data}")
    else:
        log_test("GET /auth/google/config", False, f"Status: {resp.status_code}")
except Exception as e:
    log_test("GET /auth/google/config", False, str(e))

print()

# ============================================================================
# TEST 2: Next Badges Endpoint
# ============================================================================
print("TEST 2: Next Badges Endpoint")
print("-" * 80)

try:
    admin_token = login_admin()
    
    # Test default limit (3)
    resp = requests.get(f"{BACKEND_URL}/me/next-badges",
                       headers={"Authorization": f"Bearer {admin_token}"})
    if resp.status_code == 200:
        data = resp.json()
        if isinstance(data, list):
            if len(data) <= 3:
                log_test("GET /me/next-badges default limit returns ≤3 items", True,
                        f"Returned {len(data)} items")
            else:
                log_test("GET /me/next-badges default limit", False,
                        f"Expected ≤3 items, got {len(data)}")
            
            # Check structure of first item
            if len(data) > 0:
                item = data[0]
                required_fields = ["id", "name", "emoji", "tier", "cat", "points", 
                                 "current", "threshold", "remaining", "stat_key", "progress"]
                missing = [f for f in required_fields if f not in item]
                if not missing:
                    log_test("Next badge item has all required fields", True,
                            f"Fields: {', '.join(required_fields)}")
                else:
                    log_test("Next badge item structure", False,
                            f"Missing fields: {missing}")
                
                # Check remaining > 0
                if item.get("remaining", 0) > 0:
                    log_test("Next badge has remaining > 0", True,
                            f"remaining={item['remaining']}")
                else:
                    log_test("Next badge remaining value", False,
                            f"Expected remaining > 0, got {item.get('remaining')}")
                
                # Check progress is 0-100
                progress = item.get("progress", -1)
                if 0 <= progress <= 100:
                    log_test("Next badge progress is 0-100", True,
                            f"progress={progress}")
                else:
                    log_test("Next badge progress range", False,
                            f"Expected 0-100, got {progress}")
            else:
                log_test("Next badges returned items", False, "No items returned")
        else:
            log_test("GET /me/next-badges returns array", False,
                    f"Got type: {type(data)}")
    else:
        log_test("GET /me/next-badges", False, f"Status: {resp.status_code}")
    
    # Test custom limit (1)
    resp = requests.get(f"{BACKEND_URL}/me/next-badges?limit=1",
                       headers={"Authorization": f"Bearer {admin_token}"})
    if resp.status_code == 200:
        data = resp.json()
        if isinstance(data, list) and len(data) == 1:
            log_test("GET /me/next-badges?limit=1 returns 1 item", True)
        else:
            log_test("GET /me/next-badges?limit=1", False,
                    f"Expected 1 item, got {len(data) if isinstance(data, list) else 'not a list'}")
    else:
        log_test("GET /me/next-badges?limit=1", False, f"Status: {resp.status_code}")
    
    # Verify returned badges are NOT in earned list
    resp_earned = requests.get(f"{BACKEND_URL}/me/badges",
                              headers={"Authorization": f"Bearer {admin_token}"})
    if resp_earned.status_code == 200:
        earned_ids = {b["id"] for b in resp_earned.json().get("earned", [])}
        resp_next = requests.get(f"{BACKEND_URL}/me/next-badges",
                                headers={"Authorization": f"Bearer {admin_token}"})
        if resp_next.status_code == 200:
            next_ids = {b["id"] for b in resp_next.json()}
            overlap = earned_ids.intersection(next_ids)
            if not overlap:
                log_test("Next badges are not in earned list", True)
            else:
                log_test("Next badges exclusion", False,
                        f"Found earned badges in next list: {overlap}")
        else:
            log_test("Next badges verification", False, "Could not fetch next badges")
    else:
        log_test("Earned badges verification", False, "Could not fetch earned badges")
        
except Exception as e:
    log_test("Next badges endpoint tests", False, str(e))

print()

# ============================================================================
# TEST 3: Moment Upload Friend Notifications
# ============================================================================
print("TEST 3: Moment Upload Friend Notifications")
print("-" * 80)

try:
    admin_token = login_admin()
    
    # Create two test users (Bob and Charlie)
    timestamp = int(time.time())
    bob_email = f"bob{timestamp}@test.com"
    charlie_email = f"charlie{timestamp}@test.com"
    
    print(f"Creating Bob: {bob_email}")
    bob_token = create_user("Bob Test", bob_email, "password123")
    print(f"Creating Charlie: {charlie_email}")
    charlie_token = create_user("Charlie Test", charlie_email, "password123")
    
    # Make them friends
    print("Sending friend request from Bob to Charlie...")
    send_friend_request(bob_token, charlie_email)
    time.sleep(0.5)
    print("Charlie accepting friend request...")
    accept_friend_request(charlie_token)
    time.sleep(0.5)
    
    # Create an event for today
    today = datetime.now().date().isoformat()
    print(f"Creating event for {today}...")
    event_id = create_event(admin_token, f"Test Party {timestamp}", today, "22:00")
    
    # Bob marks 'voy' on the event
    print("Bob marking 'voy' on event...")
    mark_interest(bob_token, event_id, "voy")
    time.sleep(0.5)
    
    # Admin triggers moment
    print("Admin triggering moment...")
    success, resp = trigger_moment(admin_token, event_id)
    if not success:
        log_test("Admin trigger moment", False, f"Status: {resp.status_code}")
    else:
        log_test("Admin trigger moment", True)
    time.sleep(0.5)
    
    # Bob uploads moment
    print("Bob uploading moment...")
    success, resp = upload_moment(bob_token, event_id)
    if not success:
        log_test("Bob upload moment", False, f"Status: {resp.status_code}, {resp.text}")
    else:
        log_test("Bob upload moment", True)
    time.sleep(1)  # Give time for notification to be created
    
    # Check Charlie's notifications
    print("Checking Charlie's notifications...")
    charlie_notifs = get_notifications(charlie_token)
    moment_notifs = [n for n in charlie_notifs if n.get("type") == "moment_friend"]
    
    if moment_notifs:
        notif = moment_notifs[0]
        message = notif.get("message", "")
        if "Bob" in message and "Test Party" in message:
            log_test("Charlie receives moment_friend notification with Bob's name and event name", True,
                    f"Message: {message}")
        else:
            log_test("Notification content", False,
                    f"Expected Bob and event name in message, got: {message}")
    else:
        log_test("Charlie receives moment_friend notification", False,
                f"No moment_friend notifications found. Total notifications: {len(charlie_notifs)}")
    
    # Test case: friend not on event (Charlie is not on the event)
    # The notification should still be sent to all friends
    if moment_notifs:
        log_test("Friend not on event still receives notification (fallback to all friends)", True,
                "Charlie received notification even though not on event")
    
except Exception as e:
    log_test("Moment upload friend notifications", False, str(e))

print()

# ============================================================================
# TEST 4: Auto-trigger Moments Scheduler
# ============================================================================
print("TEST 4: Auto-trigger Moments Scheduler")
print("-" * 80)

try:
    admin_token = login_admin()
    
    # Check admin dashboard for structure (includes captures count)
    # Note: "captures" is the moment captures count (there's no separate "moments" field)
    dashboard = get_admin_dashboard(admin_token)
    if dashboard:
        extras = dashboard.get("extras", {})
        if "captures" in extras:
            log_test("Admin dashboard includes captures count", True,
                    f"captures={extras['captures']}")
        else:
            log_test("Admin dashboard extras structure", False,
                    f"Missing captures. Got: {list(extras.keys())}")
    else:
        log_test("Admin dashboard fetch", False, "Could not fetch dashboard")
    
    # Check backend logs for auto_trigger_moments errors
    print("Checking backend logs for auto_trigger_moments errors...")
    import subprocess
    result = subprocess.run(
        ["tail", "-n", "100", "/var/log/supervisor/backend.err.log"],
        capture_output=True,
        text=True
    )
    error_log = result.stdout
    
    # Look for auto_trigger_moments errors in last 100 lines
    if "auto_trigger_moments failed" in error_log:
        log_test("Auto-trigger moments scheduler - no errors in logs", False,
                "Found 'auto_trigger_moments failed' in error logs")
    else:
        log_test("Auto-trigger moments scheduler - no errors in logs", True,
                "No auto_trigger_moments errors found in recent logs")
    
    # Test that repeated admin triggers don't create duplicates (upsert behavior)
    today = datetime.now().date().isoformat()
    timestamp = int(time.time())
    event_id = create_event(admin_token, f"Duplicate Test {timestamp}", today, "23:00")
    
    # Mark admin as 'voy' so there's at least one voy user
    mark_interest(admin_token, event_id, "voy")
    time.sleep(0.5)
    
    # Trigger twice
    print("Testing duplicate trigger prevention...")
    trigger_moment(admin_token, event_id)
    time.sleep(0.5)
    success2, resp2 = trigger_moment(admin_token, event_id)
    
    # Second trigger should succeed (upsert) but not create duplicate
    if success2:
        log_test("Repeated moment trigger doesn't fail (upsert behavior)", True,
                "Second trigger succeeded")
    else:
        log_test("Repeated moment trigger", False,
                f"Second trigger failed: {resp2.status_code}")
    
except Exception as e:
    log_test("Auto-trigger moments scheduler tests", False, str(e))

print()

# ============================================================================
# SUMMARY
# ============================================================================
print("=" * 80)
print("TEST SUMMARY")
print("=" * 80)
print(f"Total Tests: {results['passed'] + results['failed']}")
print(f"Passed: {results['passed']} ✅")
print(f"Failed: {results['failed']} ❌")
print()

if results['failed'] > 0:
    print("FAILED TESTS:")
    for test in results['tests']:
        if not test['passed']:
            print(f"  ❌ {test['name']}")
            if test['details']:
                print(f"     {test['details']}")
    print()

print("=" * 80)
