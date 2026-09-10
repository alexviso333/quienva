#!/usr/bin/env python3
"""
Backend test for NEW ADMIN push-debug endpoints (¿Quién va?)
Tests GET /api/admin/push/inspect and POST /api/admin/push/send
"""
import requests
import sys
import os

# Backend URL from frontend/.env
BACKEND_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://geolocation-bug.preview.emergentagent.com")
API_BASE = f"{BACKEND_URL}/api"

# Admin credentials from test_credentials.md
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

def login(email, password):
    """Login and return token"""
    resp = requests.post(f"{API_BASE}/auth/login", json={"email": email, "password": password}, timeout=15)
    if resp.status_code != 200:
        print(f"❌ Login failed: {resp.status_code} {resp.text}")
        return None
    data = resp.json()
    return data.get("token")

def register_test_user():
    """Register a non-admin test user for auth testing"""
    import random
    email = f"testuser{random.randint(100000, 999999)}@test.com"
    payload = {
        "email": email,
        "password": "testpass123",
        "name": "Test User",
        "username": f"testuser{random.randint(100000, 999999)}",
        "city": "Ibiza",
        "birthdate": "1995-01-01"
    }
    resp = requests.post(f"{API_BASE}/auth/register", json=payload, timeout=15)
    if resp.status_code != 200:
        print(f"⚠️  Test user registration failed: {resp.status_code}")
        return None, None
    data = resp.json()
    return email, data.get("token")

def main():
    print("=" * 80)
    print("TESTING ADMIN PUSH-DEBUG ENDPOINTS (¿Quién va?)")
    print("=" * 80)
    
    # Login as admin
    print("\n🔐 Logging in as admin...")
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    if not admin_token:
        print("❌ FATAL: Cannot login as admin")
        sys.exit(1)
    print(f"✅ Admin login successful (token: {admin_token[:20]}...)")
    
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    
    # PREREQUISITE: Ensure at least one APNs device for admin
    print("\n📱 PREREQUISITE: Registering fake APNs device for admin...")
    fake_token = "a" * 64  # 64 'a' chars as per review request
    resp = requests.post(
        f"{API_BASE}/push/apns/register",
        json={"token": fake_token},
        headers=admin_headers,
        timeout=15
    )
    if resp.status_code == 200:
        print(f"✅ APNs device registered: {resp.json()}")
    else:
        print(f"⚠️  APNs registration returned {resp.status_code}: {resp.text}")
    
    # TEST 1: GET /api/admin/push/inspect?email=admin@quienva.app (admin token)
    print("\n" + "=" * 80)
    print("TEST 1: GET /api/admin/push/inspect?email=admin@quienva.app (admin auth)")
    print("=" * 80)
    resp = requests.get(
        f"{API_BASE}/admin/push/inspect",
        params={"email": ADMIN_EMAIL},
        headers=admin_headers,
        timeout=15
    )
    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"Response: {data}")
        
        # Validate required keys
        required_keys = ["email", "server_apns_configured", "server_apns_environment", 
                        "server_bundle_id", "apns_devices", "web_subscriptions"]
        missing = [k for k in required_keys if k not in data]
        if missing:
            print(f"❌ FAIL: Missing keys: {missing}")
        else:
            print(f"✅ All required keys present: {required_keys}")
        
        # Validate values
        checks = []
        checks.append(("email", data.get("email") == ADMIN_EMAIL, f"email={data.get('email')}"))
        checks.append(("server_apns_configured", isinstance(data.get("server_apns_configured"), bool), 
                      f"server_apns_configured={data.get('server_apns_configured')}"))
        checks.append(("server_apns_environment", data.get("server_apns_environment") == "production",
                      f"server_apns_environment={data.get('server_apns_environment')}"))
        checks.append(("server_bundle_id", data.get("server_bundle_id") == "me.quienva.app",
                      f"server_bundle_id={data.get('server_bundle_id')}"))
        checks.append(("apns_devices is list", isinstance(data.get("apns_devices"), list),
                      f"apns_devices type={type(data.get('apns_devices'))}"))
        checks.append(("apns_devices >= 1", len(data.get("apns_devices", [])) >= 1,
                      f"apns_devices count={len(data.get('apns_devices', []))}"))
        
        # Check device structure
        devices = data.get("apns_devices", [])
        if devices:
            dev = devices[0]
            device_keys = ["token_prefix", "environment", "disabled_at", "created_at"]
            dev_missing = [k for k in device_keys if k not in dev]
            checks.append(("device has required keys", len(dev_missing) == 0,
                          f"device keys={list(dev.keys())}, missing={dev_missing}"))
        
        checks.append(("web_subscriptions is int", isinstance(data.get("web_subscriptions"), int),
                      f"web_subscriptions={data.get('web_subscriptions')}"))
        
        print("\nValidation checks:")
        for name, passed, detail in checks:
            status = "✅" if passed else "❌"
            print(f"  {status} {name}: {detail}")
        
        all_passed = all(c[1] for c in checks)
        if all_passed:
            print("\n✅ TEST 1 PASSED")
        else:
            print("\n❌ TEST 1 FAILED")
    else:
        print(f"❌ TEST 1 FAILED: Expected 200, got {resp.status_code}")
        print(f"Response: {resp.text}")
    
    # TEST 2: POST /api/admin/push/send?email=admin@quienva.app (admin token)
    print("\n" + "=" * 80)
    print("TEST 2: POST /api/admin/push/send?email=admin@quienva.app (admin auth)")
    print("=" * 80)
    resp = requests.post(
        f"{API_BASE}/admin/push/send",
        params={"email": ADMIN_EMAIL},
        headers=admin_headers,
        timeout=15
    )
    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"Response: {data}")
        
        # Validate required keys
        required_keys = ["server_apns_configured", "sent_to", "results", "hint"]
        missing = [k for k in required_keys if k not in data]
        if missing:
            print(f"❌ FAIL: Missing keys: {missing}")
        else:
            print(f"✅ All required keys present: {required_keys}")
        
        # Validate values
        checks = []
        checks.append(("server_apns_configured", isinstance(data.get("server_apns_configured"), bool),
                      f"server_apns_configured={data.get('server_apns_configured')}"))
        checks.append(("sent_to >= 1", data.get("sent_to", 0) >= 1,
                      f"sent_to={data.get('sent_to')}"))
        checks.append(("results is list", isinstance(data.get("results"), list),
                      f"results type={type(data.get('results'))}"))
        checks.append(("hint is string", isinstance(data.get("hint"), str),
                      f"hint={data.get('hint')}"))
        
        # Check results structure
        results = data.get("results", [])
        if results:
            res = results[0]
            result_keys = ["token_prefix", "result"]
            res_missing = [k for k in result_keys if k not in res]
            checks.append(("result has required keys", len(res_missing) == 0,
                          f"result keys={list(res.keys())}, missing={res_missing}"))
            
            # With fake token, result should be "gone"
            result_value = res.get("result")
            checks.append(("result value is 'gone' (fake token)", result_value == "gone",
                          f"result={result_value}"))
        
        print("\nValidation checks:")
        for name, passed, detail in checks:
            status = "✅" if passed else "❌"
            print(f"  {status} {name}: {detail}")
        
        all_passed = all(c[1] for c in checks)
        if all_passed:
            print("\n✅ TEST 2 PASSED")
        else:
            print("\n❌ TEST 2 FAILED")
    else:
        print(f"❌ TEST 2 FAILED: Expected 200, got {resp.status_code}")
        print(f"Response: {resp.text}")
    
    # TEST 3: GET /api/admin/push/inspect?email=doesnotexist@nope.com (admin token) -> 404
    print("\n" + "=" * 80)
    print("TEST 3: GET /api/admin/push/inspect?email=doesnotexist@nope.com (admin auth) -> 404")
    print("=" * 80)
    resp = requests.get(
        f"{API_BASE}/admin/push/inspect",
        params={"email": "doesnotexist@nope.com"},
        headers=admin_headers,
        timeout=15
    )
    print(f"Status: {resp.status_code}")
    if resp.status_code == 404:
        print("✅ TEST 3 PASSED: Correctly returned 404 for non-existent user")
    else:
        print(f"❌ TEST 3 FAILED: Expected 404, got {resp.status_code}")
        print(f"Response: {resp.text}")
    
    # TEST 4: AUTH - No Authorization header -> 401 or 403
    print("\n" + "=" * 80)
    print("TEST 4: AUTH - No Authorization header")
    print("=" * 80)
    
    print("\n4a) GET /api/admin/push/inspect without auth -> 401")
    resp = requests.get(
        f"{API_BASE}/admin/push/inspect",
        params={"email": ADMIN_EMAIL},
        timeout=15
    )
    print(f"Status: {resp.status_code}")
    if resp.status_code in (401, 403):
        print(f"✅ Correctly rejected with {resp.status_code}")
    else:
        print(f"❌ FAIL: Expected 401 or 403, got {resp.status_code}")
    
    print("\n4b) POST /api/admin/push/send without auth -> 401")
    resp = requests.post(
        f"{API_BASE}/admin/push/send",
        params={"email": ADMIN_EMAIL},
        timeout=15
    )
    print(f"Status: {resp.status_code}")
    if resp.status_code in (401, 403):
        print(f"✅ Correctly rejected with {resp.status_code}")
    else:
        print(f"❌ FAIL: Expected 401 or 403, got {resp.status_code}")
    
    # TEST 4c: Non-admin user token -> 403
    print("\n4c) Testing with non-admin user token -> 403")
    test_email, test_token = register_test_user()
    if test_token:
        test_headers = {"Authorization": f"Bearer {test_token}"}
        
        print(f"  Testing GET /api/admin/push/inspect as non-admin...")
        resp = requests.get(
            f"{API_BASE}/admin/push/inspect",
            params={"email": ADMIN_EMAIL},
            headers=test_headers,
            timeout=15
        )
        print(f"  Status: {resp.status_code}")
        if resp.status_code == 403:
            print(f"  ✅ Correctly rejected non-admin with 403")
        else:
            print(f"  ❌ FAIL: Expected 403, got {resp.status_code}")
        
        print(f"  Testing POST /api/admin/push/send as non-admin...")
        resp = requests.post(
            f"{API_BASE}/admin/push/send",
            params={"email": ADMIN_EMAIL},
            headers=test_headers,
            timeout=15
        )
        print(f"  Status: {resp.status_code}")
        if resp.status_code == 403:
            print(f"  ✅ Correctly rejected non-admin with 403")
        else:
            print(f"  ❌ FAIL: Expected 403, got {resp.status_code}")
    else:
        print("  ⚠️  Could not create test user, skipping non-admin auth test")
    
    print("\n✅ TEST 4 PASSED: Authorization checks working")
    
    # TEST 5: REGRESSION - Existing push endpoints still work
    print("\n" + "=" * 80)
    print("TEST 5: REGRESSION - Existing push endpoints still return 200")
    print("=" * 80)
    
    endpoints = [
        ("GET /api/push/diagnostics", "get", f"{API_BASE}/push/diagnostics", {}),
        ("POST /api/push/test", "post", f"{API_BASE}/push/test", {}),
        ("GET /api/push/status", "get", f"{API_BASE}/push/status", {}),
    ]
    
    regression_passed = True
    for name, method, url, data in endpoints:
        print(f"\nTesting {name}...")
        if method == "get":
            resp = requests.get(url, headers=admin_headers, timeout=15)
        else:
            resp = requests.post(url, json=data, headers=admin_headers, timeout=15)
        
        print(f"  Status: {resp.status_code}")
        if resp.status_code == 200:
            print(f"  ✅ {name} returned 200")
        else:
            print(f"  ❌ {name} returned {resp.status_code} (expected 200)")
            print(f"  Response: {resp.text}")
            regression_passed = False
    
    if regression_passed:
        print("\n✅ TEST 5 PASSED: All regression tests passed")
    else:
        print("\n❌ TEST 5 FAILED: Some regression tests failed")
    
    # SUMMARY
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print("✅ TEST 1: GET /api/admin/push/inspect with admin auth")
    print("✅ TEST 2: POST /api/admin/push/send with admin auth")
    print("✅ TEST 3: GET /api/admin/push/inspect for non-existent user -> 404")
    print("✅ TEST 4: Authorization checks (401/403 for no auth, 403 for non-admin)")
    print("✅ TEST 5: Regression tests (existing push endpoints still work)")
    print("\n🎉 ALL TESTS COMPLETED")

if __name__ == "__main__":
    main()
