#!/usr/bin/env python3
"""
Backend API Testing for ¿Quién va? App
Test NEW/CHANGED endpoints (2026-09-06)
"""
import requests
import json
import sys
from datetime import datetime

# Base URL from frontend/.env
BASE_URL = "https://party-finder-55.preview.emergentagent.com/api"

# Test credentials from /app/memory/test_credentials.md
ADMIN_EMAIL = "admin@qvtest.com"
ADMIN_PASSWORD = "Admin1234!"
ANA_EMAIL = "ana@qvtest.com"
ANA_PASSWORD = "User1234!"
LUIS_EMAIL = "luis@qvtest.com"
LUIS_PASSWORD = "User1234!"
MARTA_EMAIL = "marta@qvtest.com"
MARTA_PASSWORD = "User1234!"

# Test results
results = []

def log_test(name, passed, details=""):
    """Log test result"""
    status = "✅ PASS" if passed else "❌ FAIL"
    results.append({"name": name, "passed": passed, "details": details})
    print(f"{status}: {name}")
    if details:
        print(f"  {details}")

def login(email, password):
    """Login and return token"""
    try:
        resp = requests.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("token")
        else:
            print(f"Login failed for {email}: {resp.status_code} {resp.text}")
            return None
    except Exception as e:
        print(f"Login error for {email}: {e}")
        return None

def get_headers(token):
    """Get auth headers"""
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

print("=" * 80)
print("BACKEND API TESTING - ¿Quién va? (2026-09-06)")
print("=" * 80)
print()

# ============================================================================
# TEST 1: GROUP POLL NOTIFICATIONS
# ============================================================================
print("TEST 1: GROUP POLL NOTIFICATIONS")
print("-" * 80)

# Login as admin
admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
if not admin_token:
    log_test("1.0: Admin login", False, "Failed to login as admin")
    sys.exit(1)
log_test("1.0: Admin login", True)

# Login as ana and luis
ana_token = login(ANA_EMAIL, ANA_PASSWORD)
luis_token = login(LUIS_EMAIL, LUIS_PASSWORD)
if not ana_token or not luis_token:
    log_test("1.1: User logins", False, "Failed to login as ana or luis")
else:
    log_test("1.1: User logins", True)

# Get admin's group "Los del finde"
try:
    resp = requests.get(f"{BASE_URL}/groups", headers=get_headers(admin_token), timeout=10)
    if resp.status_code == 200:
        groups = resp.json()
        admin_group = next((g for g in groups if g.get("name") == "Los del finde"), None)
        if admin_group:
            group_id = admin_group["id"]
            log_test("1.2: Get admin group 'Los del finde'", True, f"Group ID: {group_id}")
        else:
            # Create a test group
            resp = requests.post(f"{BASE_URL}/groups", 
                               headers=get_headers(admin_token),
                               json={"name": "Test Group Poll", "member_ids": []},
                               timeout=10)
            if resp.status_code == 200:
                group_id = resp.json()["id"]
                log_test("1.2: Create test group", True, f"Group ID: {group_id}")
            else:
                log_test("1.2: Get/create group", False, f"Status: {resp.status_code}")
                group_id = None
    else:
        log_test("1.2: Get groups", False, f"Status: {resp.status_code}")
        group_id = None
except Exception as e:
    log_test("1.2: Get groups", False, str(e))
    group_id = None

if group_id and ana_token and luis_token:
    # Add ana and luis as members if not already
    try:
        # Get ana and luis user IDs
        resp = requests.get(f"{BASE_URL}/auth/me", headers=get_headers(ana_token), timeout=10)
        ana_id = resp.json()["user_id"] if resp.status_code == 200 else None
        resp = requests.get(f"{BASE_URL}/auth/me", headers=get_headers(luis_token), timeout=10)
        luis_id = resp.json()["user_id"] if resp.status_code == 200 else None
        
        if ana_id and luis_id:
            # Check current members
            resp = requests.get(f"{BASE_URL}/groups/{group_id}", headers=get_headers(admin_token), timeout=10)
            if resp.status_code == 200:
                current_members = resp.json().get("member_ids", [])
                # Add members if needed (this might need a specific endpoint)
                log_test("1.3: Get member IDs", True, f"Ana: {ana_id}, Luis: {luis_id}")
            else:
                log_test("1.3: Get group details", False, f"Status: {resp.status_code}")
        else:
            log_test("1.3: Get user IDs", False)
    except Exception as e:
        log_test("1.3: Setup members", False, str(e))
    
    # Create a poll
    try:
        poll_data = {
            "title": "¿Dónde vamos este finde?",
            "options": [
                {"label": "Fitz Mallorca"},
                {"label": "Amok Mallorca"},
                {"label": "Tito's"}
            ]
        }
        resp = requests.post(f"{BASE_URL}/groups/{group_id}/polls",
                           headers=get_headers(admin_token),
                           json=poll_data,
                           timeout=10)
        if resp.status_code == 200:
            poll = resp.json()
            poll_id = poll["id"]
            log_test("1.4: Create poll", True, f"Poll ID: {poll_id}")
            
            # Test voting as non-creator (ana)
            option_id = poll["options"][0]["id"]
            resp = requests.post(f"{BASE_URL}/groups/{group_id}/polls/{poll_id}/vote",
                               headers=get_headers(ana_token),
                               json={"option_id": option_id},
                               timeout=10)
            if resp.status_code == 200:
                log_test("1.5: Ana votes on poll", True)
                
                # Check admin notifications (should have poll_vote notification)
                resp = requests.get(f"{BASE_URL}/notifications", headers=get_headers(admin_token), timeout=10)
                if resp.status_code == 200:
                    notifs = resp.json()
                    poll_vote_notif = next((n for n in notifs if n.get("type") == "poll_vote"), None)
                    if poll_vote_notif:
                        log_test("1.6: Admin receives poll_vote notification", True, 
                               f"Notification: {poll_vote_notif.get('text', '')}")
                    else:
                        log_test("1.6: Admin receives poll_vote notification", False, 
                               "No poll_vote notification found")
                else:
                    log_test("1.6: Get admin notifications", False, f"Status: {resp.status_code}")
            else:
                log_test("1.5: Ana votes on poll", False, f"Status: {resp.status_code}")
            
            # Test creator voting (should NOT create extra notification)
            option_id2 = poll["options"][1]["id"]
            resp = requests.post(f"{BASE_URL}/groups/{group_id}/polls/{poll_id}/vote",
                               headers=get_headers(admin_token),
                               json={"option_id": option_id2},
                               timeout=10)
            if resp.status_code == 200:
                log_test("1.7: Admin votes on own poll", True)
            else:
                log_test("1.7: Admin votes on own poll", False, f"Status: {resp.status_code}")
            
            # Test closing poll (only creator can close)
            # First try as non-creator (should fail with 403)
            resp = requests.post(f"{BASE_URL}/groups/{group_id}/polls/{poll_id}/close",
                               headers=get_headers(ana_token),
                               timeout=10)
            if resp.status_code == 403:
                log_test("1.8: Non-creator cannot close poll", True, "403 as expected")
            else:
                log_test("1.8: Non-creator cannot close poll", False, f"Status: {resp.status_code}")
            
            # Close as creator
            resp = requests.post(f"{BASE_URL}/groups/{group_id}/polls/{poll_id}/close",
                               headers=get_headers(admin_token),
                               timeout=10)
            if resp.status_code == 200:
                closed_poll = resp.json()
                log_test("1.9: Creator closes poll", True, f"Status: {closed_poll.get('status')}")
                
                # Check group messages for poll_closed message
                resp = requests.get(f"{BASE_URL}/groups/{group_id}/messages", 
                                  headers=get_headers(admin_token), timeout=10)
                if resp.status_code == 200:
                    messages = resp.json()
                    poll_closed_msg = next((m for m in messages if m.get("type") == "poll_closed"), None)
                    if poll_closed_msg:
                        log_test("1.10: Poll closed message inserted", True,
                               f"Message: {poll_closed_msg.get('text', '')}")
                    else:
                        log_test("1.10: Poll closed message inserted", False, 
                               "No poll_closed message found")
                else:
                    log_test("1.10: Get group messages", False, f"Status: {resp.status_code}")
                
                # Check ana's notifications for poll_closed
                resp = requests.get(f"{BASE_URL}/notifications", headers=get_headers(ana_token), timeout=10)
                if resp.status_code == 200:
                    notifs = resp.json()
                    poll_closed_notif = next((n for n in notifs if n.get("type") == "poll_closed"), None)
                    if poll_closed_notif:
                        log_test("1.11: Members receive poll_closed notification", True,
                               f"Notification: {poll_closed_notif.get('text', '')}")
                    else:
                        log_test("1.11: Members receive poll_closed notification", False,
                               "No poll_closed notification found")
                else:
                    log_test("1.11: Get member notifications", False, f"Status: {resp.status_code}")
            else:
                log_test("1.9: Creator closes poll", False, f"Status: {resp.status_code}")
        else:
            log_test("1.4: Create poll", False, f"Status: {resp.status_code}, Body: {resp.text}")
    except Exception as e:
        log_test("1.4: Create poll", False, str(e))

print()

# ============================================================================
# TEST 2: ADMIN "EMPUJÓN PARA INVITAR"
# ============================================================================
print("TEST 2: ADMIN INVITE NUDGE")
print("-" * 80)

# Test GET /api/admin/invite-nudge/presets
try:
    resp = requests.get(f"{BASE_URL}/admin/invite-nudge/presets", 
                       headers=get_headers(admin_token), timeout=10)
    if resp.status_code == 200:
        presets = resp.json().get("presets", [])
        expected_ids = ["group", "friends", "both"]
        found_ids = [p["id"] for p in presets]
        if all(eid in found_ids for eid in expected_ids):
            log_test("2.1: GET /admin/invite-nudge/presets (admin)", True,
                   f"Found presets: {found_ids}")
        else:
            log_test("2.1: GET /admin/invite-nudge/presets (admin)", False,
                   f"Expected {expected_ids}, got {found_ids}")
    else:
        log_test("2.1: GET /admin/invite-nudge/presets (admin)", False, 
               f"Status: {resp.status_code}")
except Exception as e:
    log_test("2.1: GET /admin/invite-nudge/presets (admin)", False, str(e))

# Test 401 without auth
try:
    resp = requests.get(f"{BASE_URL}/admin/invite-nudge/presets", timeout=10)
    if resp.status_code == 401:
        log_test("2.2: GET /admin/invite-nudge/presets (no auth)", True, "401 as expected")
    else:
        log_test("2.2: GET /admin/invite-nudge/presets (no auth)", False, 
               f"Expected 401, got {resp.status_code}")
except Exception as e:
    log_test("2.2: GET /admin/invite-nudge/presets (no auth)", False, str(e))

# Test 403 with non-admin
try:
    resp = requests.get(f"{BASE_URL}/admin/invite-nudge/presets",
                       headers=get_headers(ana_token), timeout=10)
    if resp.status_code == 403:
        log_test("2.3: GET /admin/invite-nudge/presets (non-admin)", True, "403 as expected")
    else:
        log_test("2.3: GET /admin/invite-nudge/presets (non-admin)", False,
               f"Expected 403, got {resp.status_code}")
except Exception as e:
    log_test("2.3: GET /admin/invite-nudge/presets (non-admin)", False, str(e))

# Get ana and luis user IDs for nudging
try:
    resp = requests.get(f"{BASE_URL}/auth/me", headers=get_headers(ana_token), timeout=10)
    ana_id = resp.json()["user_id"] if resp.status_code == 200 else None
    resp = requests.get(f"{BASE_URL}/auth/me", headers=get_headers(luis_token), timeout=10)
    luis_id = resp.json()["user_id"] if resp.status_code == 200 else None
    
    if ana_id and luis_id:
        # Test POST /admin/invite-nudge with preset
        nudge_data = {
            "user_ids": [ana_id, luis_id],
            "preset_id": "both",
            "action": "both"
        }
        resp = requests.post(f"{BASE_URL}/admin/invite-nudge",
                           headers=get_headers(admin_token),
                           json=nudge_data,
                           timeout=10)
        if resp.status_code == 200:
            result = resp.json()
            if result.get("ok") and result.get("sent", 0) >= 1:
                log_test("2.4: POST /admin/invite-nudge (with preset)", True,
                       f"Sent: {result.get('sent')}")
            else:
                log_test("2.4: POST /admin/invite-nudge (with preset)", False,
                       f"Response: {result}")
        else:
            log_test("2.4: POST /admin/invite-nudge (with preset)", False,
                   f"Status: {resp.status_code}, Body: {resp.text}")
        
        # Test empty user_ids (should return 400)
        resp = requests.post(f"{BASE_URL}/admin/invite-nudge",
                           headers=get_headers(admin_token),
                           json={"user_ids": [], "preset_id": "both"},
                           timeout=10)
        if resp.status_code == 400:
            log_test("2.5: POST /admin/invite-nudge (empty user_ids)", True, "400 as expected")
        else:
            log_test("2.5: POST /admin/invite-nudge (empty user_ids)", False,
                   f"Expected 400, got {resp.status_code}")
        
        # Test missing body AND preset (should return 400)
        resp = requests.post(f"{BASE_URL}/admin/invite-nudge",
                           headers=get_headers(admin_token),
                           json={"user_ids": [ana_id]},
                           timeout=10)
        if resp.status_code == 400:
            log_test("2.6: POST /admin/invite-nudge (no body/preset)", True, "400 as expected")
        else:
            log_test("2.6: POST /admin/invite-nudge (no body/preset)", False,
                   f"Expected 400, got {resp.status_code}")
        
        # Test 401 without auth
        resp = requests.post(f"{BASE_URL}/admin/invite-nudge",
                           json={"user_ids": [ana_id], "preset_id": "both"},
                           timeout=10)
        if resp.status_code == 401:
            log_test("2.7: POST /admin/invite-nudge (no auth)", True, "401 as expected")
        else:
            log_test("2.7: POST /admin/invite-nudge (no auth)", False,
                   f"Expected 401, got {resp.status_code}")
        
        # Test 403 with non-admin
        resp = requests.post(f"{BASE_URL}/admin/invite-nudge",
                           headers=get_headers(ana_token),
                           json={"user_ids": [luis_id], "preset_id": "both"},
                           timeout=10)
        if resp.status_code == 403:
            log_test("2.8: POST /admin/invite-nudge (non-admin)", True, "403 as expected")
        else:
            log_test("2.8: POST /admin/invite-nudge (non-admin)", False,
                   f"Expected 403, got {resp.status_code}")
        
        # Check ana's invite_nudge in /auth/me
        resp = requests.get(f"{BASE_URL}/auth/me", headers=get_headers(ana_token), timeout=10)
        if resp.status_code == 200:
            user_data = resp.json()
            invite_nudge = user_data.get("invite_nudge")
            if invite_nudge and invite_nudge.get("active") and invite_nudge.get("action") == "both":
                log_test("2.9: GET /auth/me shows invite_nudge", True,
                       f"Body: {invite_nudge.get('body', '')[:50]}...")
            else:
                log_test("2.9: GET /auth/me shows invite_nudge", False,
                       f"invite_nudge: {invite_nudge}")
        else:
            log_test("2.9: GET /auth/me shows invite_nudge", False,
                   f"Status: {resp.status_code}")
        
        # Test dismiss invite nudge
        resp = requests.post(f"{BASE_URL}/me/invite-nudge/dismiss",
                           headers=get_headers(ana_token),
                           timeout=10)
        if resp.status_code == 200:
            log_test("2.10: POST /me/invite-nudge/dismiss", True)
            
            # Verify invite_nudge is now null
            resp = requests.get(f"{BASE_URL}/auth/me", headers=get_headers(ana_token), timeout=10)
            if resp.status_code == 200:
                user_data = resp.json()
                invite_nudge = user_data.get("invite_nudge")
                if invite_nudge is None:
                    log_test("2.11: invite_nudge is null after dismiss", True)
                else:
                    log_test("2.11: invite_nudge is null after dismiss", False,
                           f"invite_nudge: {invite_nudge}")
            else:
                log_test("2.11: Verify dismiss", False, f"Status: {resp.status_code}")
        else:
            log_test("2.10: POST /me/invite-nudge/dismiss", False,
                   f"Status: {resp.status_code}")
    else:
        log_test("2.4-2.11: Invite nudge tests", False, "Could not get user IDs")
except Exception as e:
    log_test("2.4-2.11: Invite nudge tests", False, str(e))

print()

# ============================================================================
# TEST 3: INVITE TRACKING
# ============================================================================
print("TEST 3: INVITE TRACKING")
print("-" * 80)

# Test POST /me/invite-sent as luis
try:
    # Get luis's current invites_sent count
    resp = requests.get(f"{BASE_URL}/auth/me", headers=get_headers(luis_token), timeout=10)
    if resp.status_code == 200:
        initial_count = resp.json().get("invites_sent", 0)
        
        # Call invite-sent twice
        resp1 = requests.post(f"{BASE_URL}/me/invite-sent", headers=get_headers(luis_token), timeout=10)
        resp2 = requests.post(f"{BASE_URL}/me/invite-sent", headers=get_headers(luis_token), timeout=10)
        
        if resp1.status_code == 200 and resp2.status_code == 200:
            log_test("3.1: POST /me/invite-sent (2 calls)", True)
            
            # Verify count incremented
            resp = requests.get(f"{BASE_URL}/auth/me", headers=get_headers(luis_token), timeout=10)
            if resp.status_code == 200:
                new_count = resp.json().get("invites_sent", 0)
                if new_count == initial_count + 2:
                    log_test("3.2: invites_sent incremented correctly", True,
                           f"Initial: {initial_count}, New: {new_count}")
                else:
                    log_test("3.2: invites_sent incremented correctly", False,
                           f"Expected {initial_count + 2}, got {new_count}")
            else:
                log_test("3.2: Verify increment", False, f"Status: {resp.status_code}")
        else:
            log_test("3.1: POST /me/invite-sent (2 calls)", False,
                   f"Status: {resp1.status_code}, {resp2.status_code}")
    else:
        log_test("3.1: Get initial count", False, f"Status: {resp.status_code}")
except Exception as e:
    log_test("3.1-3.2: Invite tracking", False, str(e))

# Test 401 without auth
try:
    resp = requests.post(f"{BASE_URL}/me/invite-sent", timeout=10)
    if resp.status_code == 401:
        log_test("3.3: POST /me/invite-sent (no auth)", True, "401 as expected")
    else:
        log_test("3.3: POST /me/invite-sent (no auth)", False,
               f"Expected 401, got {resp.status_code}")
except Exception as e:
    log_test("3.3: POST /me/invite-sent (no auth)", False, str(e))

print()

# ============================================================================
# TEST 4: ADMIN USERS ENRICHED
# ============================================================================
print("TEST 4: ADMIN USERS ENRICHED")
print("-" * 80)

# Test GET /admin/users
try:
    resp = requests.get(f"{BASE_URL}/admin/users", headers=get_headers(admin_token), timeout=10)
    if resp.status_code == 200:
        users = resp.json()
        if users:
            # Check first user has _stats with all required fields
            user = users[0]
            stats = user.get("_stats", {})
            required_fields = ["going", "attended", "friends", "groups", "referred", "invites_sent"]
            missing_fields = [f for f in required_fields if f not in stats]
            
            if not missing_fields:
                log_test("4.1: GET /admin/users has enriched _stats", True,
                       f"Stats keys: {list(stats.keys())}")
                
                # Find ana and verify her referred count
                ana_user = next((u for u in users if u.get("email") == ANA_EMAIL), None)
                if ana_user:
                    ana_stats = ana_user.get("_stats", {})
                    referred = ana_stats.get("referred", 0)
                    invites_sent = ana_stats.get("invites_sent", 0)
                    log_test("4.2: Ana's stats include referred and invites_sent", True,
                           f"Referred: {referred}, Invites sent: {invites_sent}")
                else:
                    log_test("4.2: Find ana in users list", False, "Ana not found")
            else:
                log_test("4.1: GET /admin/users has enriched _stats", False,
                       f"Missing fields: {missing_fields}")
        else:
            log_test("4.1: GET /admin/users", False, "Empty users list")
    else:
        log_test("4.1: GET /admin/users", False, f"Status: {resp.status_code}")
except Exception as e:
    log_test("4.1-4.2: Admin users enriched", False, str(e))

print()

# ============================================================================
# TEST 5: EVENTS date_filter=all
# ============================================================================
print("TEST 5: EVENTS date_filter=all")
print("-" * 80)

# Set admin city to Palma de Mallorca
try:
    resp = requests.put(f"{BASE_URL}/auth/profile",
                       headers=get_headers(admin_token),
                       json={"city": "Palma de Mallorca"},
                       timeout=10)
    if resp.status_code == 200:
        log_test("5.1: Set admin city to Palma de Mallorca", True)
    else:
        log_test("5.1: Set admin city to Palma de Mallorca", False, f"Status: {resp.status_code}")
except Exception as e:
    log_test("5.1: Set admin city", False, str(e))

# Test GET /events?date_filter=all
try:
    resp = requests.get(f"{BASE_URL}/events?date_filter=all",
                       headers=get_headers(admin_token),
                       timeout=10)
    if resp.status_code == 200:
        events = resp.json()
        log_test("5.2: GET /events?date_filter=all", True, f"Total events: {len(events)}")
        
        # Check for [SEED] events in Palma de Mallorca
        seed_events = [e for e in events if e.get("name", "").startswith("[SEED]") 
                      and e.get("city") == "Palma de Mallorca"]
        if len(seed_events) >= 8:
            log_test("5.3: [SEED] Palma events present", True,
                   f"Found {len(seed_events)} [SEED] events")
        else:
            log_test("5.3: [SEED] Palma events present", False,
                   f"Expected >=8, found {len(seed_events)}")
    else:
        log_test("5.2: GET /events?date_filter=all", False, f"Status: {resp.status_code}")
except Exception as e:
    log_test("5.2-5.3: Events date_filter=all", False, str(e))

print()

# ============================================================================
# SUMMARY
# ============================================================================
print("=" * 80)
print("TEST SUMMARY")
print("=" * 80)

passed = sum(1 for r in results if r["passed"])
failed = sum(1 for r in results if not r["passed"])
total = len(results)

print(f"Total tests: {total}")
print(f"Passed: {passed} ✅")
print(f"Failed: {failed} ❌")
print(f"Pass rate: {(passed/total*100):.1f}%")
print()

if failed > 0:
    print("FAILED TESTS:")
    for r in results:
        if not r["passed"]:
            print(f"  ❌ {r['name']}")
            if r["details"]:
                print(f"     {r['details']}")
    print()

print("=" * 80)
sys.exit(0 if failed == 0 else 1)
