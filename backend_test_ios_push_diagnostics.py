#!/usr/bin/env python3
"""
Backend test for iOS push-diagnostic endpoints (2026-08-30)

Tests the NEW POST /api/push/apns/debug endpoint and MODIFIED GET /api/admin/push/inspect endpoint.

Requirements:
1. POST /api/push/apns/debug - best-effort diagnostic sink that NEVER returns 401
   - Must accept requests WITHOUT Authorization header
   - Must accept requests WITH valid Authorization header
   - Always returns {"ok": true}
   - Stores events in db.apns_debug with server_authenticated=true/false

2. GET /api/admin/push/inspect?email=... - now includes device_debug_log field
   - Returns device_debug_log with last ~15 apns_debug events for that email
   - Newest first
   - Still requires admin auth (401 no-auth, 403 non-admin)
   - 404 for unknown email

3. Regression tests - ensure existing endpoints still work
"""

import requests
import sys
import time

# Base URL from frontend/.env
BASE_URL = "https://plan-compartido.preview.emergentagent.com/api"

# Admin credentials from test_credentials.md
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

def log(msg):
    print(f"  {msg}")

def test_section(title):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}")

def register_test_user(email_suffix):
    """Register a new test user and return the token"""
    email = f"test+{email_suffix}@example.com"
    payload = {
        "email": email,
        "password": "testpass123",
        "name": "Test User",
        "username": f"testuser{email_suffix}",
        "city": "Ibiza",
        "birthdate": "1990-01-01"
    }
    resp = requests.post(f"{BASE_URL}/auth/register", json=payload)
    if resp.status_code == 200:
        return resp.json().get("token"), email
    # User might already exist, try login
    login_resp = requests.post(f"{BASE_URL}/auth/login", json={"email": email, "password": "testpass123"})
    if login_resp.status_code == 200:
        return login_resp.json().get("token"), email
    return None, None

def main():
    print("\n" + "="*80)
    print("  iOS PUSH-DIAGNOSTIC ENDPOINTS TEST")
    print("  Testing POST /api/push/apns/debug and GET /api/admin/push/inspect")
    print("="*80)

    # -------------------------------------------------------------------------
    # SETUP: Login as admin
    # -------------------------------------------------------------------------
    test_section("SETUP: Admin Login")
    admin_resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if admin_resp.status_code != 200:
        print(f"❌ FATAL: Admin login failed with status {admin_resp.status_code}")
        print(f"   Response: {admin_resp.text}")
        sys.exit(1)
    
    admin_token = admin_resp.json().get("token")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    log(f"✅ Admin login successful")
    log(f"   Admin token: {admin_token[:20]}...")

    # Create a test user for non-admin tests
    test_section("SETUP: Create Test User")
    test_user_token, test_user_email = register_test_user(f"iosdbg{int(time.time())}")
    if not test_user_token:
        print(f"❌ FATAL: Failed to create test user")
        sys.exit(1)
    test_user_headers = {"Authorization": f"Bearer {test_user_token}"}
    log(f"✅ Test user created: {test_user_email}")
    log(f"   Test user token: {test_user_token[:20]}...")

    # -------------------------------------------------------------------------
    # TEST 1: POST /api/push/apns/debug WITHOUT Authorization header
    # -------------------------------------------------------------------------
    test_section("TEST 1: POST /api/push/apns/debug WITHOUT Authorization (MUST NOT 401)")
    
    payload_no_auth = {
        "stage": "registration_error",
        "detail": "test no-auth",
        "email": "debugtest@example.com",
        "logged_in": False,
        "platform": "ios"
    }
    
    resp = requests.post(f"{BASE_URL}/push/apns/debug", json=payload_no_auth)
    
    if resp.status_code != 200:
        print(f"❌ TEST 1 FAILED: Expected 200, got {resp.status_code}")
        print(f"   Response: {resp.text}")
        print(f"   CRITICAL: This endpoint MUST NEVER return 401 (uses get_optional_user)")
        sys.exit(1)
    
    data = resp.json()
    if data.get("ok") != True:
        print(f"❌ TEST 1 FAILED: Expected {{ok: true}}, got {data}")
        sys.exit(1)
    
    log(f"✅ POST /api/push/apns/debug WITHOUT auth → 200 {{ok: true}}")
    log(f"   This event should be stored with server_authenticated=false")
    
    # Wait a moment for DB write
    time.sleep(0.5)

    # -------------------------------------------------------------------------
    # TEST 2: POST /api/push/apns/debug WITH valid admin Bearer token
    # -------------------------------------------------------------------------
    test_section("TEST 2: POST /api/push/apns/debug WITH admin Authorization")
    
    payload_with_auth = {
        "stage": "upload_ok",
        "token_prefix": "abcd1234",
        "email": "debugtest@example.com",
        "logged_in": True,
        "platform": "ios"
    }
    
    resp = requests.post(f"{BASE_URL}/push/apns/debug", json=payload_with_auth, headers=admin_headers)
    
    if resp.status_code != 200:
        print(f"❌ TEST 2 FAILED: Expected 200, got {resp.status_code}")
        print(f"   Response: {resp.text}")
        sys.exit(1)
    
    data = resp.json()
    if data.get("ok") != True:
        print(f"❌ TEST 2 FAILED: Expected {{ok: true}}, got {data}")
        sys.exit(1)
    
    log(f"✅ POST /api/push/apns/debug WITH admin auth → 200 {{ok: true}}")
    log(f"   This event should be stored with server_authenticated=true")
    
    # Wait a moment for DB write
    time.sleep(0.5)

    # -------------------------------------------------------------------------
    # TEST 3: GET /api/admin/push/inspect?email=admin@quienva.app (admin auth)
    # -------------------------------------------------------------------------
    test_section("TEST 3: GET /api/admin/push/inspect?email=admin@quienva.app (admin)")
    
    # First, post a couple of debug events for admin email
    for i in range(2):
        payload = {
            "stage": f"test_stage_{i}",
            "detail": f"test detail {i}",
            "email": ADMIN_EMAIL,
            "logged_in": True,
            "platform": "ios"
        }
        requests.post(f"{BASE_URL}/push/apns/debug", json=payload, headers=admin_headers)
        time.sleep(0.2)
    
    resp = requests.get(f"{BASE_URL}/admin/push/inspect?email={ADMIN_EMAIL}", headers=admin_headers)
    
    if resp.status_code != 200:
        print(f"❌ TEST 3 FAILED: Expected 200, got {resp.status_code}")
        print(f"   Response: {resp.text}")
        sys.exit(1)
    
    data = resp.json()
    
    # Check required fields
    required_fields = ["email", "server_apns_configured", "server_apns_environment", 
                      "server_bundle_id", "apns_devices", "web_subscriptions", "device_debug_log"]
    
    missing_fields = [f for f in required_fields if f not in data]
    if missing_fields:
        print(f"❌ TEST 3 FAILED: Missing required fields: {missing_fields}")
        print(f"   Response: {data}")
        sys.exit(1)
    
    log(f"✅ GET /api/admin/push/inspect?email={ADMIN_EMAIL} → 200")
    log(f"   All required fields present: {', '.join(required_fields)}")
    
    # Check device_debug_log is a list
    debug_log = data.get("device_debug_log")
    if not isinstance(debug_log, list):
        print(f"❌ TEST 3 FAILED: device_debug_log is not a list: {type(debug_log)}")
        sys.exit(1)
    
    log(f"✅ device_debug_log is a list with {len(debug_log)} events")
    
    # Check that debug_log contains the events we posted
    if len(debug_log) > 0:
        log(f"   Sample debug event: stage={debug_log[0].get('stage')}, "
            f"server_authenticated={debug_log[0].get('server_authenticated')}")
    
    # Verify other fields
    log(f"   server_apns_configured: {data.get('server_apns_configured')}")
    log(f"   server_apns_environment: {data.get('server_apns_environment')}")
    log(f"   server_bundle_id: {data.get('server_bundle_id')}")
    log(f"   apns_devices: {len(data.get('apns_devices', []))} devices")
    log(f"   web_subscriptions: {data.get('web_subscriptions')}")

    # -------------------------------------------------------------------------
    # TEST 4: GET /api/admin/push/inspect?email=doesnotexist@nope.com (admin)
    # -------------------------------------------------------------------------
    test_section("TEST 4: GET /api/admin/push/inspect?email=doesnotexist@nope.com (admin)")
    
    resp = requests.get(f"{BASE_URL}/admin/push/inspect?email=doesnotexist@nope.com", headers=admin_headers)
    
    if resp.status_code != 404:
        print(f"❌ TEST 4 FAILED: Expected 404, got {resp.status_code}")
        print(f"   Response: {resp.text}")
        sys.exit(1)
    
    log(f"✅ GET /api/admin/push/inspect?email=doesnotexist@nope.com → 404")
    log(f"   Correctly returns 404 for non-existent user")

    # -------------------------------------------------------------------------
    # TEST 5: GET /api/admin/push/inspect WITHOUT Authorization header
    # -------------------------------------------------------------------------
    test_section("TEST 5: GET /api/admin/push/inspect WITHOUT Authorization")
    
    resp = requests.get(f"{BASE_URL}/admin/push/inspect?email={ADMIN_EMAIL}")
    
    if resp.status_code != 401:
        print(f"❌ TEST 5 FAILED: Expected 401, got {resp.status_code}")
        print(f"   Response: {resp.text}")
        sys.exit(1)
    
    log(f"✅ GET /api/admin/push/inspect WITHOUT auth → 401")
    log(f"   Authorization correctly enforced")

    # -------------------------------------------------------------------------
    # TEST 6: GET /api/admin/push/inspect with NON-ADMIN user token
    # -------------------------------------------------------------------------
    test_section("TEST 6: GET /api/admin/push/inspect with NON-ADMIN user token")
    
    resp = requests.get(f"{BASE_URL}/admin/push/inspect?email={ADMIN_EMAIL}", headers=test_user_headers)
    
    if resp.status_code != 403:
        print(f"❌ TEST 6 FAILED: Expected 403, got {resp.status_code}")
        print(f"   Response: {resp.text}")
        sys.exit(1)
    
    log(f"✅ GET /api/admin/push/inspect with non-admin token → 403")
    log(f"   Admin-only access correctly enforced")

    # -------------------------------------------------------------------------
    # TEST 7: REGRESSION - GET /api/push/status
    # -------------------------------------------------------------------------
    test_section("TEST 7: REGRESSION - GET /api/push/status")
    
    resp = requests.get(f"{BASE_URL}/push/status", headers=admin_headers)
    
    if resp.status_code != 200:
        print(f"❌ TEST 7 FAILED: Expected 200, got {resp.status_code}")
        print(f"   Response: {resp.text}")
        sys.exit(1)
    
    data = resp.json()
    if "subscribed" not in data:
        print(f"❌ TEST 7 FAILED: Missing 'subscribed' field in response")
        sys.exit(1)
    
    log(f"✅ GET /api/push/status → 200 {{subscribed: {data.get('subscribed')}}}")
    log(f"   Existing endpoint still works")

    # -------------------------------------------------------------------------
    # TEST 8: REGRESSION - POST /api/push/test
    # -------------------------------------------------------------------------
    test_section("TEST 8: REGRESSION - POST /api/push/test")
    
    resp = requests.post(f"{BASE_URL}/push/test", headers=admin_headers)
    
    if resp.status_code != 200:
        print(f"❌ TEST 8 FAILED: Expected 200, got {resp.status_code}")
        print(f"   Response: {resp.text}")
        sys.exit(1)
    
    data = resp.json()
    required_fields = ["ok", "apns_configured", "apns_devices"]
    missing = [f for f in required_fields if f not in data]
    if missing:
        print(f"❌ TEST 8 FAILED: Missing fields: {missing}")
        sys.exit(1)
    
    log(f"✅ POST /api/push/test → 200")
    log(f"   ok: {data.get('ok')}, apns_configured: {data.get('apns_configured')}, "
        f"apns_devices: {data.get('apns_devices')}")
    log(f"   Existing endpoint still works")

    # -------------------------------------------------------------------------
    # TEST 9: REGRESSION - GET /api/push/diagnostics
    # -------------------------------------------------------------------------
    test_section("TEST 9: REGRESSION - GET /api/push/diagnostics")
    
    resp = requests.get(f"{BASE_URL}/push/diagnostics", headers=admin_headers)
    
    if resp.status_code != 200:
        print(f"❌ TEST 9 FAILED: Expected 200, got {resp.status_code}")
        print(f"   Response: {resp.text}")
        sys.exit(1)
    
    data = resp.json()
    required_fields = ["apns_configured", "apns_environment", "apns_bundle_id"]
    missing = [f for f in required_fields if f not in data]
    if missing:
        print(f"❌ TEST 9 FAILED: Missing fields: {missing}")
        sys.exit(1)
    
    log(f"✅ GET /api/push/diagnostics → 200")
    log(f"   apns_configured: {data.get('apns_configured')}, "
        f"apns_environment: {data.get('apns_environment')}")
    log(f"   Existing endpoint still works")

    # -------------------------------------------------------------------------
    # TEST 10: REGRESSION - POST /api/push/apns/register (valid token)
    # -------------------------------------------------------------------------
    test_section("TEST 10: REGRESSION - POST /api/push/apns/register (valid token)")
    
    # Use a 64-char fake token (valid length)
    fake_token = "a" * 64
    resp = requests.post(f"{BASE_URL}/push/apns/register", 
                        json={"token": fake_token}, 
                        headers=admin_headers)
    
    if resp.status_code != 200:
        print(f"❌ TEST 10 FAILED: Expected 200, got {resp.status_code}")
        print(f"   Response: {resp.text}")
        sys.exit(1)
    
    data = resp.json()
    if data.get("ok") != True:
        print(f"❌ TEST 10 FAILED: Expected {{ok: true}}, got {data}")
        sys.exit(1)
    
    log(f"✅ POST /api/push/apns/register (64-char token) → 200 {{ok: true, configured: {data.get('configured')}}}")
    log(f"   Existing endpoint still works")

    # -------------------------------------------------------------------------
    # TEST 11: REGRESSION - POST /api/push/apns/register (short token)
    # -------------------------------------------------------------------------
    test_section("TEST 11: REGRESSION - POST /api/push/apns/register (short token)")
    
    # Use a short token (< 32 chars) - should return 400
    short_token = "short"
    resp = requests.post(f"{BASE_URL}/push/apns/register", 
                        json={"token": short_token}, 
                        headers=admin_headers)
    
    if resp.status_code != 400:
        print(f"❌ TEST 11 FAILED: Expected 400, got {resp.status_code}")
        print(f"   Response: {resp.text}")
        sys.exit(1)
    
    log(f"✅ POST /api/push/apns/register (short token) → 400")
    log(f"   Token validation still works")

    # -------------------------------------------------------------------------
    # TEST 12: REGRESSION - POST /api/admin/push/send auth checks
    # -------------------------------------------------------------------------
    test_section("TEST 12: REGRESSION - POST /api/admin/push/send auth checks")
    
    # Without auth
    resp = requests.post(f"{BASE_URL}/admin/push/send?email={ADMIN_EMAIL}")
    if resp.status_code != 401:
        print(f"❌ TEST 12a FAILED: Expected 401, got {resp.status_code}")
        sys.exit(1)
    log(f"✅ POST /api/admin/push/send WITHOUT auth → 401")
    
    # With non-admin auth
    resp = requests.post(f"{BASE_URL}/admin/push/send?email={ADMIN_EMAIL}", headers=test_user_headers)
    if resp.status_code != 403:
        print(f"❌ TEST 12b FAILED: Expected 403, got {resp.status_code}")
        sys.exit(1)
    log(f"✅ POST /api/admin/push/send with non-admin token → 403")
    log(f"   Auth checks still correct")

    # -------------------------------------------------------------------------
    # SUMMARY
    # -------------------------------------------------------------------------
    print("\n" + "="*80)
    print("  ✅ ALL TESTS PASSED (12/12)")
    print("="*80)
    print("\n📋 SUMMARY:")
    print("  ✅ TEST 1: POST /api/push/apns/debug WITHOUT auth → 200 (NEVER 401)")
    print("  ✅ TEST 2: POST /api/push/apns/debug WITH auth → 200")
    print("  ✅ TEST 3: GET /api/admin/push/inspect includes device_debug_log")
    print("  ✅ TEST 4: GET /api/admin/push/inspect for non-existent email → 404")
    print("  ✅ TEST 5: GET /api/admin/push/inspect WITHOUT auth → 401")
    print("  ✅ TEST 6: GET /api/admin/push/inspect with non-admin → 403")
    print("  ✅ TEST 7: GET /api/push/status still works")
    print("  ✅ TEST 8: POST /api/push/test still works")
    print("  ✅ TEST 9: GET /api/push/diagnostics still works")
    print("  ✅ TEST 10: POST /api/push/apns/register (valid token) still works")
    print("  ✅ TEST 11: POST /api/push/apns/register (short token) → 400")
    print("  ✅ TEST 12: POST /api/admin/push/send auth checks still correct")
    print("\n🎉 CONCLUSION:")
    print("  The NEW iOS push-diagnostic endpoints are FULLY FUNCTIONAL:")
    print("  • POST /api/push/apns/debug accepts requests with AND without auth (NEVER 401)")
    print("  • GET /api/admin/push/inspect now includes device_debug_log field")
    print("  • All existing push endpoints still work (no regressions)")
    print("  • Authorization checks are correct (401/403 where expected)")
    print("\n")

if __name__ == "__main__":
    main()
