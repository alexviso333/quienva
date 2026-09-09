#!/usr/bin/env python3
"""
Backend testing for ¿Quién va? app - Name-privacy fix for blocked users
Test ONLY the name-privacy fix in blocked users list.
"""

import requests
import time
import json

# Base URL from frontend/.env
BASE_URL = "https://party-finder-55.preview.emergentagent.com/api"

# Admin credentials from test_credentials.md
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

def log(msg):
    print(f"[TEST] {msg}")

def login(email, password):
    """Login and return token"""
    resp = requests.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password})
    if resp.status_code != 200:
        log(f"❌ Login failed: {resp.status_code} {resp.text}")
        return None
    data = resp.json()
    token = data.get("token")
    log(f"✅ Logged in as {email}")
    return token

def register_user(email, password, name, username, city, birthdate):
    """Register a new user and return response"""
    resp = requests.post(f"{BASE_URL}/auth/register", json={
        "email": email,
        "password": password,
        "name": name,
        "username": username,
        "city": city,
        "birthdate": birthdate
    })
    return resp

def test_blocked_user_name_privacy():
    """
    TEST: Blocked user name privacy
    Steps:
    1. Register user A (any valid data, adult birthdate)
    2. Register user B with DISTINCT real name: name="Nombre Real B", username="userb<timestamp>"
    3. As A: POST /api/me/block with body {"user_id": "<B_user_id>"} → expect 200
    4. As A: GET /api/me/blocked → find the entry for B. ASSERT:
       - entry["name"] starts with "@" AND equals "@" + B's username (i.e. the @username, NOT the real name)
       - entry["name"] does NOT equal "Nombre Real B"
       - entry["email"] is null/None
    5. Regression: GET /api/auth/me as A → A still sees A's OWN real name (name field is A's real name, not @username)
    """
    log("\n" + "="*80)
    log("TEST: Blocked user name privacy")
    log("="*80)
    
    ts = int(time.time())
    
    # Step 1: Register user A
    log("\nStep 1: Register user A")
    user_a_email = f"usera_{ts}@test.com"
    user_a_username = f"usera{ts}"
    user_a_name = "Nombre Real A"
    user_a_password = "testpass123"
    
    resp_a = register_user(
        user_a_email,
        user_a_password,
        user_a_name,
        user_a_username,
        "Palma de Mallorca",
        "1990-01-01"  # Adult birthdate
    )
    
    if resp_a.status_code == 429:
        log(f"❌ FAIL: Rate limit hit (429). Wait and retry.")
        return False
    
    if resp_a.status_code != 200:
        log(f"❌ FAIL: Failed to register user A: {resp_a.status_code} {resp_a.text}")
        return False
    
    user_a_data = resp_a.json()
    user_a_id = user_a_data.get("user", {}).get("user_id")
    log(f"✅ PASS: Registered user A: {user_a_email} (user_id: {user_a_id})")
    
    # Login as user A
    token_a = login(user_a_email, user_a_password)
    if not token_a:
        log("❌ FAIL: Cannot login as user A")
        return False
    
    # Step 2: Register user B with DISTINCT real name
    log("\nStep 2: Register user B with distinct real name")
    user_b_email = f"userb_{ts}@test.com"
    user_b_username = f"userb{ts}"
    user_b_name = "Nombre Real B"  # DISTINCT real name
    user_b_password = "testpass123"
    
    resp_b = register_user(
        user_b_email,
        user_b_password,
        user_b_name,
        user_b_username,
        "Palma de Mallorca",
        "1992-05-15"  # Adult birthdate
    )
    
    if resp_b.status_code == 429:
        log(f"❌ FAIL: Rate limit hit (429). Wait and retry.")
        return False
    
    if resp_b.status_code != 200:
        log(f"❌ FAIL: Failed to register user B: {resp_b.status_code} {resp_b.text}")
        return False
    
    user_b_data = resp_b.json()
    user_b_id = user_b_data.get("user", {}).get("user_id")
    log(f"✅ PASS: Registered user B: {user_b_email} (user_id: {user_b_id})")
    log(f"   User B real name: '{user_b_name}'")
    log(f"   User B username: '{user_b_username}'")
    
    # Step 3: As A, block user B
    log("\nStep 3: As user A, block user B")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    resp_block = requests.post(
        f"{BASE_URL}/me/block",
        json={"user_id": user_b_id},
        headers=headers_a
    )
    
    if resp_block.status_code != 200:
        log(f"❌ FAIL: Failed to block user B: {resp_block.status_code} {resp_block.text}")
        return False
    
    block_data = resp_block.json()
    log(f"✅ PASS: Blocked user B: {block_data}")
    
    # Step 4: As A, GET /api/me/blocked and verify name privacy
    log("\nStep 4: As user A, GET /api/me/blocked and verify name privacy")
    resp_blocked = requests.get(f"{BASE_URL}/me/blocked", headers=headers_a)
    
    if resp_blocked.status_code != 200:
        log(f"❌ FAIL: Failed to get blocked list: {resp_blocked.status_code} {resp_blocked.text}")
        return False
    
    blocked_list = resp_blocked.json()
    log(f"✅ PASS: Retrieved blocked list with {len(blocked_list)} entries")
    
    # Find entry for user B
    entry_b = None
    for entry in blocked_list:
        if entry.get("user_id") == user_b_id:
            entry_b = entry
            break
    
    if not entry_b:
        log(f"❌ FAIL: User B not found in blocked list")
        log(f"   Blocked list: {json.dumps(blocked_list, indent=2)}")
        return False
    
    log(f"✅ PASS: Found user B in blocked list")
    log(f"   Entry for user B: {json.dumps(entry_b, indent=2)}")
    
    # ASSERTION 1: entry["name"] starts with "@"
    entry_name = entry_b.get("name", "")
    if not entry_name.startswith("@"):
        log(f"❌ FAIL: entry['name'] does NOT start with '@'")
        log(f"   Actual name: '{entry_name}'")
        return False
    log(f"✅ PASS: entry['name'] starts with '@': '{entry_name}'")
    
    # ASSERTION 2: entry["name"] equals "@" + B's username (lowercase)
    expected_name = f"@{user_b_username.lower()}"
    if entry_name != expected_name:
        log(f"❌ FAIL: entry['name'] does NOT equal '@{user_b_username.lower()}'")
        log(f"   Expected: '{expected_name}'")
        log(f"   Actual: '{entry_name}'")
        return False
    log(f"✅ PASS: entry['name'] equals '@{user_b_username.lower()}': '{entry_name}'")
    
    # ASSERTION 3: entry["name"] does NOT equal "Nombre Real B"
    if entry_name == user_b_name:
        log(f"❌ FAIL: entry['name'] equals the real name '{user_b_name}' (privacy leak!)")
        return False
    log(f"✅ PASS: entry['name'] does NOT equal real name '{user_b_name}'")
    
    # ASSERTION 4: entry["email"] is null/None
    entry_email = entry_b.get("email")
    if entry_email is not None:
        log(f"❌ FAIL: entry['email'] is NOT null (privacy leak!)")
        log(f"   Actual email: '{entry_email}'")
        return False
    log(f"✅ PASS: entry['email'] is null/None")
    
    # Step 5: Regression - GET /api/auth/me as A → A still sees A's OWN real name
    log("\nStep 5: Regression - GET /api/auth/me as A → A still sees own real name")
    resp_me = requests.get(f"{BASE_URL}/auth/me", headers=headers_a)
    
    if resp_me.status_code != 200:
        log(f"❌ FAIL: Failed to get /auth/me: {resp_me.status_code} {resp_me.text}")
        return False
    
    me_data = resp_me.json()
    my_name = me_data.get("name", "")
    
    log(f"   /auth/me response name: '{my_name}'")
    
    # ASSERTION 5: A sees their own real name, not @username
    if my_name != user_a_name:
        log(f"❌ FAIL: User A does NOT see their own real name")
        log(f"   Expected: '{user_a_name}'")
        log(f"   Actual: '{my_name}'")
        return False
    log(f"✅ PASS: User A sees their own real name: '{my_name}'")
    
    # ASSERTION 6: A's name is NOT @username
    if my_name.startswith("@"):
        log(f"❌ FAIL: User A sees @username instead of real name (regression!)")
        return False
    log(f"✅ PASS: User A's name is NOT @username")
    
    log("\n✅ TEST PASSED: All assertions passed - blocked user name privacy working correctly")
    return True

def main():
    """Run the test"""
    log("="*80)
    log("BACKEND TESTING: Name-privacy fix for blocked users")
    log("="*80)
    log(f"Base URL: {BASE_URL}")
    log("")
    
    try:
        result = test_blocked_user_name_privacy()
        
        # Summary
        log("\n" + "="*80)
        log("TEST SUMMARY")
        log("="*80)
        
        if result:
            log("✅ PASS: Blocked user name privacy test")
            log("\n🎉 TEST PASSED!")
            return 0
        else:
            log("❌ FAIL: Blocked user name privacy test")
            return 1
    
    except Exception as e:
        log(f"❌ TEST EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())
