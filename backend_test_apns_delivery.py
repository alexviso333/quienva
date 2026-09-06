#!/usr/bin/env python3
"""
Backend API Testing for APNs Push Notification Delivery Pipeline
Tests the APNs push notification delivery pipeline with diagnostics and real test-send
Review request: User granted iOS notification permission but pushes don't arrive
"""

import requests
import sys

# Backend URL from frontend/.env
BASE_URL = "https://poll-integration-dev.preview.emergentagent.com/api"

# Test credentials from /app/memory/test_credentials.md
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

def login(email, password):
    """Login and return auth token"""
    url = f"{BASE_URL}/auth/login"
    response = requests.post(url, json={"email": email, "password": password})
    if response.status_code != 200:
        print(f"❌ Login failed: {response.status_code}")
        print(f"Response: {response.text}")
        return None
    data = response.json()
    return data.get("token")

def test_1_apns_register():
    """
    TEST 1: POST /api/push/apns/register with 64 'a' chars
    - Should return 200 with {ok: true, configured: true}
    - APNs is configured locally with a valid key
    """
    print("\n" + "="*80)
    print("TEST 1: POST /api/push/apns/register with 64 'a' chars")
    print("="*80)
    
    token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    if not token:
        print("❌ FAIL: Could not login")
        return False
    
    url = f"{BASE_URL}/push/apns/register"
    headers = {"Authorization": f"Bearer {token}"}
    # Fake device token: 64 'a' chars as specified
    fake_token = "a" * 64
    payload = {"token": fake_token}
    
    response = requests.post(url, json=payload, headers=headers)
    print(f"POST {url}")
    print(f"Headers: Authorization: Bearer <token>")
    print(f"Body: {payload}")
    print(f"Status: {response.status_code}")
    
    if response.status_code != 200:
        print(f"❌ FAIL: Expected 200, got {response.status_code}")
        print(f"Response: {response.text}")
        return False
    
    data = response.json()
    print(f"Response: {data}")
    
    # Check ok field
    if not isinstance(data.get("ok"), bool) or data.get("ok") != True:
        print(f"❌ FAIL: Expected ok=true, got {data.get('ok')}")
        return False
    
    # Check configured field - MUST be true (APNs is configured with valid key)
    if not isinstance(data.get("configured"), bool):
        print(f"❌ FAIL: Expected configured to be boolean, got {type(data.get('configured'))}")
        return False
    
    if data.get("configured") != True:
        print(f"❌ FAIL: Expected configured=true (APNs is configured with valid key), got {data.get('configured')}")
        print(f"   Check backend/.env: APNS_KEY_ID, APNS_TEAM_ID, APNS_PRIVATE_KEY_PATH")
        return False
    
    print(f"✅ PASS: Received 200 with ok=true, configured=true")
    return True

def test_2_push_diagnostics():
    """
    TEST 2: GET /api/push/diagnostics
    - Should return 200 with:
      - apns_configured: true
      - apns_environment: "production"
      - apns_bundle_id: "me.quienva.app"
      - apns_devices: >= 1 (we just registered one)
      - web_push_configured: present (boolean)
      - web_subscriptions: present (number)
    """
    print("\n" + "="*80)
    print("TEST 2: GET /api/push/diagnostics")
    print("="*80)
    
    token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    if not token:
        print("❌ FAIL: Could not login")
        return False
    
    url = f"{BASE_URL}/push/diagnostics"
    headers = {"Authorization": f"Bearer {token}"}
    
    response = requests.get(url, headers=headers)
    print(f"GET {url}")
    print(f"Headers: Authorization: Bearer <token>")
    print(f"Status: {response.status_code}")
    
    if response.status_code != 200:
        print(f"❌ FAIL: Expected 200, got {response.status_code}")
        print(f"Response: {response.text}")
        return False
    
    data = response.json()
    print(f"Response: {data}")
    
    # Check apns_configured
    if data.get("apns_configured") != True:
        print(f"❌ FAIL: Expected apns_configured=true, got {data.get('apns_configured')}")
        return False
    print(f"✅ apns_configured: true")
    
    # Check apns_environment
    if data.get("apns_environment") != "production":
        print(f"❌ FAIL: Expected apns_environment='production', got {data.get('apns_environment')}")
        return False
    print(f"✅ apns_environment: production")
    
    # Check apns_bundle_id
    if data.get("apns_bundle_id") != "me.quienva.app":
        print(f"❌ FAIL: Expected apns_bundle_id='me.quienva.app', got {data.get('apns_bundle_id')}")
        return False
    print(f"✅ apns_bundle_id: me.quienva.app")
    
    # Check apns_devices >= 1
    apns_devices = data.get("apns_devices")
    if not isinstance(apns_devices, int) or apns_devices < 1:
        print(f"❌ FAIL: Expected apns_devices >= 1, got {apns_devices}")
        return False
    print(f"✅ apns_devices: {apns_devices} (>= 1)")
    
    # Check web_push_configured field is present
    if "web_push_configured" not in data:
        print(f"❌ FAIL: Missing web_push_configured field")
        return False
    print(f"✅ web_push_configured: {data.get('web_push_configured')}")
    
    # Check web_subscriptions field is present
    if "web_subscriptions" not in data:
        print(f"❌ FAIL: Missing web_subscriptions field")
        return False
    print(f"✅ web_subscriptions: {data.get('web_subscriptions')}")
    
    print(f"✅ PASS: All diagnostics fields correct")
    return True

def test_3_push_test():
    """
    TEST 3: POST /api/push/test
    - Should return 200 with:
      - ok: boolean
      - apns_configured: true
      - apns_devices: >= 1
      - apns_results: list containing "gone" (BadDeviceToken = Apple ACCEPTED our auth)
      - web_sent: number
    - With fake token, apns_results should contain "gone" (proves Apple accepts our JWT/key/team)
    """
    print("\n" + "="*80)
    print("TEST 3: POST /api/push/test")
    print("="*80)
    
    token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    if not token:
        print("❌ FAIL: Could not login")
        return False
    
    url = f"{BASE_URL}/push/test"
    headers = {"Authorization": f"Bearer {token}"}
    
    response = requests.post(url, headers=headers)
    print(f"POST {url}")
    print(f"Headers: Authorization: Bearer <token>")
    print(f"Status: {response.status_code}")
    
    if response.status_code != 200:
        print(f"❌ FAIL: Expected 200, got {response.status_code}")
        print(f"Response: {response.text}")
        return False
    
    data = response.json()
    print(f"Response: {data}")
    
    # Check ok field
    if "ok" not in data or not isinstance(data.get("ok"), bool):
        print(f"❌ FAIL: Missing or invalid 'ok' field")
        return False
    print(f"✅ ok: {data.get('ok')}")
    
    # Check apns_configured
    if data.get("apns_configured") != True:
        print(f"❌ FAIL: Expected apns_configured=true, got {data.get('apns_configured')}")
        return False
    print(f"✅ apns_configured: true")
    
    # Check apns_devices >= 1
    apns_devices = data.get("apns_devices")
    if not isinstance(apns_devices, int) or apns_devices < 1:
        print(f"❌ FAIL: Expected apns_devices >= 1, got {apns_devices}")
        return False
    print(f"✅ apns_devices: {apns_devices} (>= 1)")
    
    # Check apns_results is a list
    apns_results = data.get("apns_results")
    if not isinstance(apns_results, list):
        print(f"❌ FAIL: Expected apns_results to be a list, got {type(apns_results)}")
        return False
    
    # Check apns_results is not empty
    if len(apns_results) == 0:
        print(f"❌ FAIL: apns_results is empty (expected at least one result)")
        return False
    print(f"✅ apns_results: {apns_results} (not empty)")
    
    # CRITICAL: Check apns_results contains "gone"
    # "gone" = BadDeviceToken response from Apple, which PROVES our JWT/key/team auth is ACCEPTED
    # A real device token would return "ok", but fake token returns "gone"
    if "gone" not in apns_results:
        print(f"❌ FAIL: apns_results does not contain 'gone'")
        print(f"   Expected: 'gone' (BadDeviceToken = Apple ACCEPTED our auth)")
        print(f"   Got: {apns_results}")
        print(f"   This means Apple rejected our credentials or the send path didn't execute")
        return False
    print(f"✅ apns_results contains 'gone' (BadDeviceToken = Apple ACCEPTED our JWT/key/team auth)")
    print(f"   This PROVES the APNs send path executes correctly!")
    print(f"   A real device token would return 'ok' instead of 'gone'")
    
    # Check web_sent field is present
    if "web_sent" not in data:
        print(f"❌ FAIL: Missing web_sent field")
        return False
    print(f"✅ web_sent: {data.get('web_sent')}")
    
    print(f"✅ PASS: Test push executed successfully, Apple accepted our credentials")
    return True

def test_4_auth_required():
    """
    TEST 4: Auth required on all push endpoints
    - POST /api/push/apns/register without auth -> 401 or 403
    - GET /api/push/diagnostics without auth -> 401 or 403
    - POST /api/push/test without auth -> 401 or 403
    """
    print("\n" + "="*80)
    print("TEST 4: Auth required on all push endpoints")
    print("="*80)
    
    all_passed = True
    
    # Test 4a: POST /api/push/apns/register without auth
    print("\n--- 4a: POST /api/push/apns/register without auth ---")
    url = f"{BASE_URL}/push/apns/register"
    payload = {"token": "a" * 64}
    response = requests.post(url, json=payload)
    print(f"POST {url} (no auth)")
    print(f"Status: {response.status_code}")
    if response.status_code not in [401, 403]:
        print(f"❌ FAIL: Expected 401 or 403, got {response.status_code}")
        all_passed = False
    else:
        print(f"✅ PASS: Correctly rejected with {response.status_code}")
    
    # Test 4b: GET /api/push/diagnostics without auth
    print("\n--- 4b: GET /api/push/diagnostics without auth ---")
    url = f"{BASE_URL}/push/diagnostics"
    response = requests.get(url)
    print(f"GET {url} (no auth)")
    print(f"Status: {response.status_code}")
    if response.status_code not in [401, 403]:
        print(f"❌ FAIL: Expected 401 or 403, got {response.status_code}")
        all_passed = False
    else:
        print(f"✅ PASS: Correctly rejected with {response.status_code}")
    
    # Test 4c: POST /api/push/test without auth
    print("\n--- 4c: POST /api/push/test without auth ---")
    url = f"{BASE_URL}/push/test"
    response = requests.post(url)
    print(f"POST {url} (no auth)")
    print(f"Status: {response.status_code}")
    if response.status_code not in [401, 403]:
        print(f"❌ FAIL: Expected 401 or 403, got {response.status_code}")
        all_passed = False
    else:
        print(f"✅ PASS: Correctly rejected with {response.status_code}")
    
    if all_passed:
        print(f"\n✅ PASS: All endpoints correctly require authentication")
    else:
        print(f"\n❌ FAIL: Some endpoints did not require authentication")
    
    return all_passed

def test_5_regression():
    """
    TEST 5: Regression tests
    - GET /api/push/status still works (returns 200 with subscribed boolean)
    - GET /api/push/vapid-public-key still works (returns 200 with publicKey)
    - POST /api/push/subscribe still works (doesn't 500)
    """
    print("\n" + "="*80)
    print("TEST 5: Regression tests")
    print("="*80)
    
    token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    if not token:
        print("❌ FAIL: Could not login")
        return False
    
    all_passed = True
    
    # Test 5a: GET /api/push/status
    print("\n--- 5a: GET /api/push/status ---")
    url = f"{BASE_URL}/push/status"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    print(f"GET {url}")
    print(f"Status: {response.status_code}")
    if response.status_code != 200:
        print(f"❌ FAIL: Expected 200, got {response.status_code}")
        all_passed = False
    else:
        data = response.json()
        print(f"Response: {data}")
        if "subscribed" not in data or not isinstance(data.get("subscribed"), bool):
            print(f"❌ FAIL: Missing or invalid 'subscribed' field")
            all_passed = False
        else:
            print(f"✅ PASS: GET /api/push/status works, subscribed={data.get('subscribed')}")
    
    # Test 5b: GET /api/push/vapid-public-key
    print("\n--- 5b: GET /api/push/vapid-public-key ---")
    url = f"{BASE_URL}/push/vapid-public-key"
    response = requests.get(url)
    print(f"GET {url}")
    print(f"Status: {response.status_code}")
    if response.status_code != 200:
        print(f"❌ FAIL: Expected 200, got {response.status_code}")
        all_passed = False
    else:
        data = response.json()
        print(f"Response: {data}")
        if "publicKey" not in data:
            print(f"❌ FAIL: Missing 'publicKey' field")
            all_passed = False
        else:
            print(f"✅ PASS: GET /api/push/vapid-public-key works")
    
    # Test 5c: POST /api/push/subscribe (should not 500, may return 400 with invalid payload)
    print("\n--- 5c: POST /api/push/subscribe ---")
    url = f"{BASE_URL}/push/subscribe"
    headers = {"Authorization": f"Bearer {token}"}
    # Send minimal payload (may be invalid, but should not 500)
    payload = {"endpoint": "https://test.example.com", "keys": {"p256dh": "test", "auth": "test"}}
    response = requests.post(url, json=payload, headers=headers)
    print(f"POST {url}")
    print(f"Status: {response.status_code}")
    if response.status_code == 500:
        print(f"❌ FAIL: Endpoint returned 500 (regression)")
        print(f"Response: {response.text}")
        all_passed = False
    else:
        print(f"✅ PASS: POST /api/push/subscribe does not 500 (status: {response.status_code})")
    
    if all_passed:
        print(f"\n✅ PASS: All regression tests passed")
    else:
        print(f"\n❌ FAIL: Some regression tests failed")
    
    return all_passed

def main():
    print("\n" + "="*80)
    print("BACKEND TESTING: APNs Push Notification Delivery Pipeline")
    print("Backend URL:", BASE_URL)
    print("Testing admin credentials:", ADMIN_EMAIL)
    print("="*80)
    
    tests = [
        ("1. POST /api/push/apns/register (64 'a' chars)", test_1_apns_register),
        ("2. GET /api/push/diagnostics", test_2_push_diagnostics),
        ("3. POST /api/push/test (real test-send)", test_3_push_test),
        ("4. Auth required on all endpoints", test_4_auth_required),
        ("5. Regression tests", test_5_regression),
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
        print("\n🎉 ALL TESTS PASSED!")
        print("\nCONCLUSION:")
        print("The APNs push notification delivery pipeline is working correctly:")
        print("✅ Device registration works (POST /api/push/apns/register)")
        print("✅ Diagnostics show APNs is configured (GET /api/push/diagnostics)")
        print("✅ Test push executes and Apple accepts our credentials (POST /api/push/test)")
        print("✅ Auth is required on all endpoints")
        print("✅ No regressions in existing endpoints")
        print("\nThe 'gone' response in apns_results PROVES that:")
        print("- Our JWT/key/team authentication is ACCEPTED by Apple")
        print("- The APNs send path executes correctly")
        print("- A real device token would receive the push (would return 'ok' instead of 'gone')")
        print("\nIf pushes still don't arrive on iOS, the issue is likely:")
        print("- The device token is not being registered correctly in the iOS app")
        print("- The iOS app is not requesting notification permissions correctly")
        print("- The device is in a different environment (sandbox vs production)")
        return 0
    else:
        print(f"\n❌ {total - passed} test(s) failed")
        print("\nPlease check the failed tests above for details.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
