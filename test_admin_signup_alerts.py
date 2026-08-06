#!/usr/bin/env python3
"""
Backend test for admin signup notification feature.
Tests the global on/off setting for admin notifications when users register.
"""

import requests
import json
import time
from datetime import datetime

# Base URL from frontend/.env
BASE_URL = "https://204b173e-f0b3-4059-a373-e97cae5b5cd7.preview.emergentagent.com/api"

# Admin credentials from test_credentials.md
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

def log(msg):
    print(f"[TEST] {msg}")

def log_step(step_num, description):
    print(f"\n{'='*80}")
    print(f"STEP {step_num}: {description}")
    print(f"{'='*80}")

def register_unique_user(username_suffix):
    """Register a new user with unique credentials"""
    timestamp = int(time.time() * 1000)  # milliseconds for uniqueness
    email = f"user{username_suffix}_{timestamp}@test.com"
    username = f"user{username_suffix}{timestamp}"
    password = "testpass123"
    
    register_resp = requests.post(f"{BASE_URL}/auth/register", json={
        "email": email,
        "password": password,
        "username": username,
        "name": f"Test User {username_suffix}",
        "birthdate": "1995-06-15",  # Valid adult birthdate
        "city": "Palma de Mallorca"
    })
    
    if register_resp.status_code != 200:
        log(f"❌ Registration failed: {register_resp.status_code} {register_resp.text}")
        return None
    
    log(f"✓ Registered user: @{username} ({email})")
    return {
        "email": email,
        "username": username,
        "password": password,
        "token": register_resp.json()["token"]
    }

def count_admin_signup_notifications(admin_token):
    """Count how many admin_new_signup notifications exist"""
    notif_resp = requests.get(
        f"{BASE_URL}/notifications",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    if notif_resp.status_code != 200:
        log(f"❌ Failed to get notifications: {notif_resp.status_code}")
        return -1
    
    notifications = notif_resp.json()  # Returns list directly
    signup_notifications = [n for n in notifications if n.get("type") == "admin_new_signup"]
    return len(signup_notifications)

def find_notification_for_username(admin_token, username):
    """Check if there's a notification mentioning the given username"""
    notif_resp = requests.get(
        f"{BASE_URL}/notifications",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    if notif_resp.status_code != 200:
        return False
    
    notifications = notif_resp.json()  # Returns list directly
    # Usernames are stored lowercase, so search for lowercase version
    username_lower = username.lower()
    for notif in notifications:
        if notif.get("type") == "admin_new_signup":
            message = notif.get("message", "")
            if f"@{username_lower}" in message.lower():
                return True
    return False

def main():
    log("="*80)
    log("ADMIN SIGNUP ALERTS FEATURE TEST")
    log("Testing: Admins get in-app notification on user registration")
    log("with global on/off setting (default ON)")
    log("="*80)
    
    # =========================================================================
    # STEP 1: DEFAULT ON - Login admin and verify setting is enabled by default
    # =========================================================================
    log_step(1, "DEFAULT ON: Verify signup alerts enabled by default")
    
    log("Logging in as admin...")
    admin_login_resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    
    if admin_login_resp.status_code != 200:
        log(f"❌ CRITICAL: Admin login failed: {admin_login_resp.status_code} {admin_login_resp.text}")
        return False
    
    admin_token = admin_login_resp.json()["token"]
    log(f"✓ Admin logged in successfully")
    
    # GET /api/admin/settings/signup-alerts
    log("Checking default signup-alerts setting...")
    get_setting_resp = requests.get(
        f"{BASE_URL}/admin/settings/signup-alerts",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    if get_setting_resp.status_code != 200:
        log(f"❌ FAIL: GET /admin/settings/signup-alerts returned {get_setting_resp.status_code}")
        log(f"Response: {get_setting_resp.text}")
        return False
    
    setting_data = get_setting_resp.json()
    if not isinstance(setting_data.get("enabled"), bool):
        log(f"❌ FAIL: Response missing 'enabled' boolean field")
        log(f"Response: {json.dumps(setting_data, indent=2)}")
        return False
    
    if setting_data["enabled"] != True:
        log(f"❌ FAIL: Default setting should be enabled=true, got {setting_data['enabled']}")
        return False
    
    log(f"✓ PASS: Default setting is enabled=true")
    
    # =========================================================================
    # STEP 2: ALERT ON SIGNUP - Register U1 and verify admin gets notification
    # =========================================================================
    log_step(2, "ALERT ON SIGNUP: Register U1 and verify admin notification")
    
    # Count current admin_new_signup notifications
    log("Counting existing admin_new_signup notifications...")
    initial_count = count_admin_signup_notifications(admin_token)
    if initial_count < 0:
        log(f"❌ FAIL: Could not retrieve notifications")
        return False
    log(f"✓ Current admin_new_signup notification count: {initial_count}")
    
    # Register user U1
    log("Registering user U1...")
    time.sleep(0.5)  # Small delay to ensure unique timestamp
    u1 = register_unique_user("U1")
    if not u1:
        log(f"❌ FAIL: Could not register U1")
        return False
    
    # Wait a moment for notification to be created
    time.sleep(1)
    
    # Check if admin received notification for U1
    log(f"Checking if admin received notification for @{u1['username']}...")
    if not find_notification_for_username(admin_token, u1['username']):
        log(f"❌ FAIL: No admin_new_signup notification found mentioning @{u1['username']}")
        return False
    
    log(f"✓ PASS: Admin received notification mentioning @{u1['username']}")
    
    # Count notifications again
    c1 = count_admin_signup_notifications(admin_token)
    if c1 <= initial_count:
        log(f"❌ FAIL: Notification count did not increase (was {initial_count}, now {c1})")
        return False
    
    log(f"✓ PASS: Notification count increased from {initial_count} to {c1}")
    log(f"Recording C1 = {c1} for later comparison")
    
    # =========================================================================
    # STEP 3: DISABLE - Turn off alerts and verify U2 registration creates no notification
    # =========================================================================
    log_step(3, "DISABLE: Turn off alerts, register U2, verify NO new notification")
    
    # PUT /api/admin/settings/signup-alerts with {"enabled": false}
    log("Disabling signup alerts...")
    disable_resp = requests.put(
        f"{BASE_URL}/admin/settings/signup-alerts",
        json={"enabled": False},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    if disable_resp.status_code != 200:
        log(f"❌ FAIL: PUT /admin/settings/signup-alerts returned {disable_resp.status_code}")
        log(f"Response: {disable_resp.text}")
        return False
    
    disable_data = disable_resp.json()
    if disable_data.get("enabled") != False:
        log(f"❌ FAIL: Expected enabled=false, got {disable_data}")
        return False
    
    log(f"✓ PASS: Signup alerts disabled (enabled=false)")
    
    # Verify GET also returns false
    log("Verifying GET returns enabled=false...")
    verify_resp = requests.get(
        f"{BASE_URL}/admin/settings/signup-alerts",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    if verify_resp.status_code != 200 or verify_resp.json().get("enabled") != False:
        log(f"❌ FAIL: GET did not return enabled=false after disabling")
        return False
    log(f"✓ Verified: GET returns enabled=false")
    
    # Register user U2
    log("Registering user U2 (alerts are OFF)...")
    time.sleep(0.5)
    u2 = register_unique_user("U2")
    if not u2:
        log(f"❌ FAIL: Could not register U2")
        return False
    
    # Wait a moment
    time.sleep(1)
    
    # Count notifications - should still be C1 (no new notification)
    log("Checking notification count (should still be C1)...")
    c2 = count_admin_signup_notifications(admin_token)
    if c2 != c1:
        log(f"❌ FAIL: Notification count changed when alerts were OFF")
        log(f"Expected: {c1}, Got: {c2}")
        # Check if U2 notification was created
        if find_notification_for_username(admin_token, u2['username']):
            log(f"❌ CRITICAL: Found notification for @{u2['username']} even though alerts were disabled!")
        return False
    
    log(f"✓ PASS: Notification count unchanged at {c1} (no notification for U2)")
    
    # Verify no notification for U2
    if find_notification_for_username(admin_token, u2['username']):
        log(f"❌ FAIL: Found notification for @{u2['username']} even though alerts were disabled!")
        return False
    
    log(f"✓ PASS: No notification found for @{u2['username']} (as expected)")
    
    # =========================================================================
    # STEP 4: RE-ENABLE - Turn alerts back on and verify U3 registration creates notification
    # =========================================================================
    log_step(4, "RE-ENABLE: Turn alerts back on, register U3, verify NEW notification")
    
    # PUT /api/admin/settings/signup-alerts with {"enabled": true}
    log("Re-enabling signup alerts...")
    enable_resp = requests.put(
        f"{BASE_URL}/admin/settings/signup-alerts",
        json={"enabled": True},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    if enable_resp.status_code != 200:
        log(f"❌ FAIL: PUT /admin/settings/signup-alerts returned {enable_resp.status_code}")
        log(f"Response: {enable_resp.text}")
        return False
    
    enable_data = enable_resp.json()
    if enable_data.get("enabled") != True:
        log(f"❌ FAIL: Expected enabled=true, got {enable_data}")
        return False
    
    log(f"✓ PASS: Signup alerts re-enabled (enabled=true)")
    
    # Register user U3
    log("Registering user U3 (alerts are ON again)...")
    time.sleep(0.5)
    u3 = register_unique_user("U3")
    if not u3:
        log(f"❌ FAIL: Could not register U3")
        return False
    
    # Wait a moment for notification
    time.sleep(1)
    
    # Check if admin received notification for U3
    log(f"Checking if admin received notification for @{u3['username']}...")
    if not find_notification_for_username(admin_token, u3['username']):
        log(f"❌ FAIL: No admin_new_signup notification found mentioning @{u3['username']}")
        return False
    
    log(f"✓ PASS: Admin received notification mentioning @{u3['username']}")
    
    # Count notifications - should be C1 + 1
    log("Checking notification count (should be C1 + 1)...")
    c3 = count_admin_signup_notifications(admin_token)
    expected_count = c1 + 1
    if c3 != expected_count:
        log(f"❌ FAIL: Expected notification count {expected_count}, got {c3}")
        return False
    
    log(f"✓ PASS: Notification count increased to {c3} (C1 + 1 = {c1} + 1)")
    
    # =========================================================================
    # STEP 5: PERMISSIONS - Test authorization
    # =========================================================================
    log_step(5, "PERMISSIONS: Test non-admin and unauthenticated access")
    
    # Test GET as normal user (should be 403)
    log("Testing GET /admin/settings/signup-alerts as normal user...")
    normal_user_token = u1['token']  # Use U1's token
    
    get_as_user_resp = requests.get(
        f"{BASE_URL}/admin/settings/signup-alerts",
        headers={"Authorization": f"Bearer {normal_user_token}"}
    )
    
    if get_as_user_resp.status_code != 403:
        log(f"❌ FAIL: GET as normal user should return 403, got {get_as_user_resp.status_code}")
        return False
    
    log(f"✓ PASS: GET as normal user returns 403")
    
    # Test PUT as normal user (should be 403)
    log("Testing PUT /admin/settings/signup-alerts as normal user...")
    put_as_user_resp = requests.put(
        f"{BASE_URL}/admin/settings/signup-alerts",
        json={"enabled": True},
        headers={"Authorization": f"Bearer {normal_user_token}"}
    )
    
    if put_as_user_resp.status_code != 403:
        log(f"❌ FAIL: PUT as normal user should return 403, got {put_as_user_resp.status_code}")
        return False
    
    log(f"✓ PASS: PUT as normal user returns 403")
    
    # Test GET without auth (should be 401)
    log("Testing GET /admin/settings/signup-alerts without auth...")
    get_no_auth_resp = requests.get(f"{BASE_URL}/admin/settings/signup-alerts")
    
    if get_no_auth_resp.status_code != 401:
        log(f"❌ FAIL: GET without auth should return 401, got {get_no_auth_resp.status_code}")
        return False
    
    log(f"✓ PASS: GET without auth returns 401")
    
    # Test PUT without auth (should be 401)
    log("Testing PUT /admin/settings/signup-alerts without auth...")
    put_no_auth_resp = requests.put(
        f"{BASE_URL}/admin/settings/signup-alerts",
        json={"enabled": True}
    )
    
    if put_no_auth_resp.status_code != 401:
        log(f"❌ FAIL: PUT without auth should return 401, got {put_no_auth_resp.status_code}")
        return False
    
    log(f"✓ PASS: PUT without auth returns 401")
    
    # =========================================================================
    # FINAL SUMMARY
    # =========================================================================
    print("\n" + "="*80)
    print("✅ ALL TESTS PASSED!")
    print("="*80)
    print(f"Summary:")
    print(f"  - Default setting: enabled=true ✓")
    print(f"  - U1 registration created notification (count: {initial_count} → {c1}) ✓")
    print(f"  - Disabled alerts: enabled=false ✓")
    print(f"  - U2 registration created NO notification (count stayed at {c1}) ✓")
    print(f"  - Re-enabled alerts: enabled=true ✓")
    print(f"  - U3 registration created notification (count: {c1} → {c3}) ✓")
    print(f"  - Authorization: GET/PUT as non-admin → 403 ✓")
    print(f"  - Authorization: GET/PUT without auth → 401 ✓")
    print("="*80)
    
    return True

if __name__ == "__main__":
    try:
        success = main()
        exit(0 if success else 1)
    except Exception as e:
        log(f"❌ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
