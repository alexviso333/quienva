#!/usr/bin/env python3
"""
Backend test for Google OAuth native iOS fix (2026-08-30)

Tests:
1. GET /api/auth/google/config -> expect 200 with enabled, client_id, and NEW web_origin (non-empty)
2. POST /api/auth/google/callback with fake code -> expect 400 (not 500) when Google not configured
3. Regression tests: auth endpoints should not return 500s, correct auth gating
"""

import requests
import sys
import os

# Base URL from frontend/.env
BASE_URL = "https://reciprocal-landing.preview.emergentagent.com/api"

# Admin credentials from test_credentials.md
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

def test_google_config():
    """TEST 1: GET /api/auth/google/config should return enabled, client_id, and web_origin"""
    print("\n" + "="*80)
    print("TEST 1: GET /api/auth/google/config")
    print("="*80)
    
    url = f"{BASE_URL}/auth/google/config"
    resp = requests.get(url)
    
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.json()}")
    
    if resp.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {resp.status_code}")
        return False
    
    data = resp.json()
    
    # Check all three required keys
    required_keys = ["enabled", "client_id", "web_origin"]
    for key in required_keys:
        if key not in data:
            print(f"❌ FAILED: Missing required key '{key}'")
            return False
    
    # Check types
    if not isinstance(data["enabled"], bool):
        print(f"❌ FAILED: 'enabled' should be boolean, got {type(data['enabled'])}")
        return False
    
    if not isinstance(data["client_id"], str):
        print(f"❌ FAILED: 'client_id' should be string, got {type(data['client_id'])}")
        return False
    
    if not isinstance(data["web_origin"], str):
        print(f"❌ FAILED: 'web_origin' should be string, got {type(data['web_origin'])}")
        return False
    
    # CRITICAL: web_origin must be NON-EMPTY
    if not data["web_origin"]:
        print(f"❌ FAILED: 'web_origin' is empty string, must be non-empty")
        return False
    
    # Verify web_origin is the expected value (locally should be https://quienva.me)
    if data["web_origin"] != "https://quienva.me":
        print(f"⚠️  WARNING: web_origin is '{data['web_origin']}', expected 'https://quienva.me'")
    
    print(f"✅ PASSED: All required keys present")
    print(f"   - enabled: {data['enabled']} (bool)")
    print(f"   - client_id: '{data['client_id']}' (string)")
    print(f"   - web_origin: '{data['web_origin']}' (string, NON-EMPTY)")
    
    return True


def test_google_callback_fake_code():
    """TEST 2: POST /api/auth/google/callback with fake code should return 400 (not 500)"""
    print("\n" + "="*80)
    print("TEST 2: POST /api/auth/google/callback with fake code")
    print("="*80)
    
    url = f"{BASE_URL}/auth/google/callback"
    payload = {
        "code": "fake_invalid_code",
        "redirect_uri": "https://quienva.me/auth/callback"
    }
    
    resp = requests.post(url, json=payload)
    
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text}")
    
    # Since Google is not configured locally (GOOGLE_ENABLED=false), expect 400
    if resp.status_code == 400:
        data = resp.json()
        if "Google login no está configurado" in data.get("detail", ""):
            print(f"✅ PASSED: Returns 400 with correct message (Google not configured locally)")
            return True
        else:
            print(f"✅ PASSED: Returns 400 (acceptable, detail: {data.get('detail')})")
            return True
    
    # If Google were enabled, a bad code should give 401 (also acceptable)
    if resp.status_code == 401:
        print(f"✅ PASSED: Returns 401 (acceptable for invalid code)")
        return True
    
    # MUST NOT return 500
    if resp.status_code == 500:
        print(f"❌ FAILED: Returns 500 (server error), should be 400 or 401")
        return False
    
    print(f"⚠️  WARNING: Unexpected status {resp.status_code}, expected 400 or 401")
    return False


def test_auth_login_wrong_creds():
    """TEST 3: POST /api/auth/login with wrong credentials should return 400/401 (not 500)"""
    print("\n" + "="*80)
    print("TEST 3: POST /api/auth/login with wrong credentials")
    print("="*80)
    
    url = f"{BASE_URL}/auth/login"
    payload = {
        "email": "nonexistent@example.com",
        "password": "wrongpassword"
    }
    
    resp = requests.post(url, json=payload)
    
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text}")
    
    if resp.status_code in [400, 401]:
        print(f"✅ PASSED: Returns {resp.status_code} (correct error for wrong credentials)")
        return True
    
    if resp.status_code == 500:
        print(f"❌ FAILED: Returns 500 (server error), should be 400 or 401")
        return False
    
    print(f"⚠️  WARNING: Unexpected status {resp.status_code}, expected 400 or 401")
    return False


def test_auth_me_no_auth():
    """TEST 4: GET /api/auth/me without Authorization should return 401"""
    print("\n" + "="*80)
    print("TEST 4: GET /api/auth/me without Authorization")
    print("="*80)
    
    url = f"{BASE_URL}/auth/me"
    resp = requests.get(url)
    
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text}")
    
    if resp.status_code == 401:
        print(f"✅ PASSED: Returns 401 (correct, no auth)")
        return True
    
    print(f"❌ FAILED: Expected 401, got {resp.status_code}")
    return False


def test_auth_register_valid():
    """TEST 5: POST /api/auth/register with valid body should return 200 with token (or 400 for validation, not 500)"""
    print("\n" + "="*80)
    print("TEST 5: POST /api/auth/register with valid body")
    print("="*80)
    
    url = f"{BASE_URL}/auth/register"
    
    # Generate unique email
    import time
    unique_email = f"testuser_{int(time.time())}@example.com"
    
    payload = {
        "email": unique_email,
        "password": "testpass123",
        "name": "Test User",
        "username": f"testuser{int(time.time())}",
        "birthdate": "1990-01-01"
    }
    
    resp = requests.post(url, json=payload)
    
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text[:200]}")
    
    if resp.status_code == 200:
        data = resp.json()
        if "token" in data:
            print(f"✅ PASSED: Returns 200 with token")
            return True
        else:
            print(f"⚠️  WARNING: Returns 200 but no token in response")
            return True
    
    if resp.status_code == 400:
        print(f"✅ PASSED: Returns 400 (validation error, acceptable)")
        return True
    
    if resp.status_code == 500:
        print(f"❌ FAILED: Returns 500 (server error), should be 200 or 400")
        return False
    
    print(f"⚠️  WARNING: Unexpected status {resp.status_code}")
    return False


def test_auth_me_with_admin_token():
    """TEST 6: GET /api/auth/me WITH admin token should return 200 with admin user"""
    print("\n" + "="*80)
    print("TEST 6: GET /api/auth/me WITH admin token")
    print("="*80)
    
    # First login as admin
    login_url = f"{BASE_URL}/auth/login"
    login_payload = {
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    }
    
    login_resp = requests.post(login_url, json=login_payload)
    
    if login_resp.status_code != 200:
        print(f"❌ FAILED: Admin login failed with status {login_resp.status_code}")
        print(f"Response: {login_resp.text}")
        return False
    
    login_data = login_resp.json()
    token = login_data.get("token")
    
    if not token:
        print(f"❌ FAILED: Admin login succeeded but no token in response")
        return False
    
    print(f"Admin login successful, token: {token[:20]}...")
    
    # Now call /api/auth/me with the token
    me_url = f"{BASE_URL}/auth/me"
    headers = {"Authorization": f"Bearer {token}"}
    
    me_resp = requests.get(me_url, headers=headers)
    
    print(f"Status: {me_resp.status_code}")
    print(f"Response: {me_resp.text[:200]}")
    
    if me_resp.status_code == 200:
        data = me_resp.json()
        if data.get("email") == ADMIN_EMAIL:
            print(f"✅ PASSED: Returns 200 with admin user (email: {data.get('email')})")
            return True
        else:
            print(f"⚠️  WARNING: Returns 200 but email doesn't match (got: {data.get('email')})")
            return True
    
    print(f"❌ FAILED: Expected 200, got {me_resp.status_code}")
    return False


def test_live_activity_token_no_auth():
    """TEST 7: POST /api/live-activity/token without auth should return 401"""
    print("\n" + "="*80)
    print("TEST 7: POST /api/live-activity/token without auth")
    print("="*80)
    
    url = f"{BASE_URL}/live-activity/token"
    payload = {
        "activity_id": "test_activity_123",
        "token": "fake_token_abc"
    }
    
    resp = requests.post(url, json=payload)
    
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text}")
    
    if resp.status_code == 401:
        print(f"✅ PASSED: Returns 401 (correct, no auth)")
        return True
    
    print(f"❌ FAILED: Expected 401, got {resp.status_code}")
    return False


def test_push_apns_register_no_auth():
    """TEST 8: POST /api/push/apns/register without auth should return 401"""
    print("\n" + "="*80)
    print("TEST 8: POST /api/push/apns/register without auth")
    print("="*80)
    
    url = f"{BASE_URL}/push/apns/register"
    payload = {
        "token": "a" * 64  # Valid 64-char token
    }
    
    resp = requests.post(url, json=payload)
    
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text}")
    
    if resp.status_code == 401:
        print(f"✅ PASSED: Returns 401 (correct, no auth)")
        return True
    
    print(f"❌ FAILED: Expected 401, got {resp.status_code}")
    return False


def main():
    print("\n" + "="*80)
    print("BACKEND TEST: Google OAuth Native iOS Fix + Regressions")
    print("="*80)
    print(f"Base URL: {BASE_URL}")
    print(f"Admin: {ADMIN_EMAIL}")
    
    tests = [
        ("GET /api/auth/google/config", test_google_config),
        ("POST /api/auth/google/callback (fake code)", test_google_callback_fake_code),
        ("POST /api/auth/login (wrong creds)", test_auth_login_wrong_creds),
        ("GET /api/auth/me (no auth)", test_auth_me_no_auth),
        ("POST /api/auth/register (valid)", test_auth_register_valid),
        ("GET /api/auth/me (with admin token)", test_auth_me_with_admin_token),
        ("POST /api/live-activity/token (no auth)", test_live_activity_token_no_auth),
        ("POST /api/push/apns/register (no auth)", test_push_apns_register_no_auth),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ EXCEPTION in {name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
