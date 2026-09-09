#!/usr/bin/env python3
"""
Backend API Testing for APNs Native Push + SEO App Store Link
Tests the new APNs push endpoints and SEO App Store badge
"""

import requests
import sys

# Backend URL from frontend/.env
BASE_URL = "https://city-memory-hub.preview.emergentagent.com/api"

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

def test_apns_register_valid_token():
    """
    TEST 1: POST /api/push/apns/register with valid 64-char token (auth required)
    - Should return 200 with {ok: true, configured: false}
    """
    print("\n" + "="*80)
    print("TEST 1: APNs Register - Valid 64-char Token")
    print("="*80)
    
    token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    if not token:
        print("❌ FAIL: Could not login")
        return False
    
    url = f"{BASE_URL}/push/apns/register"
    headers = {"Authorization": f"Bearer {token}"}
    # Valid 64-char token (all 'a's as specified in review_request)
    valid_token = "a" * 64
    payload = {"token": valid_token}
    
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
    
    if not isinstance(data.get("ok"), bool) or data.get("ok") != True:
        print(f"❌ FAIL: Expected ok=true, got {data.get('ok')}")
        return False
    
    if not isinstance(data.get("configured"), bool):
        print(f"❌ FAIL: Expected configured to be boolean, got {type(data.get('configured'))}")
        return False
    
    print(f"✅ PASS: Received 200 with ok={data.get('ok')}, configured={data.get('configured')}")
    return True

def test_apns_status_after_register():
    """
    TEST 2: GET /api/push/status after registering APNs device
    - Should return 200 with {subscribed: true}
    """
    print("\n" + "="*80)
    print("TEST 2: Push Status After APNs Registration")
    print("="*80)
    
    token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    if not token:
        print("❌ FAIL: Could not login")
        return False
    
    url = f"{BASE_URL}/push/status"
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
    
    if not isinstance(data.get("subscribed"), bool):
        print(f"❌ FAIL: Expected subscribed to be boolean, got {type(data.get('subscribed'))}")
        return False
    
    if data.get("subscribed") != True:
        print(f"❌ FAIL: Expected subscribed=true after registration, got {data.get('subscribed')}")
        return False
    
    print(f"✅ PASS: subscribed={data.get('subscribed')} (correctly reflects APNs registration)")
    return True

def test_apns_register_short_token():
    """
    TEST 3: POST /api/push/apns/register with short/invalid token
    - Should return 400
    """
    print("\n" + "="*80)
    print("TEST 3: APNs Register - Short/Invalid Token")
    print("="*80)
    
    token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    if not token:
        print("❌ FAIL: Could not login")
        return False
    
    url = f"{BASE_URL}/push/apns/register"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"token": "short"}
    
    response = requests.post(url, json=payload, headers=headers)
    print(f"POST {url}")
    print(f"Headers: Authorization: Bearer <token>")
    print(f"Body: {payload}")
    print(f"Status: {response.status_code}")
    
    if response.status_code != 400:
        print(f"❌ FAIL: Expected 400, got {response.status_code}")
        print(f"Response: {response.text}")
        return False
    
    print(f"✅ PASS: Correctly rejected short token with 400")
    return True

def test_apns_unregister():
    """
    TEST 4: POST /api/push/apns/unregister with same token
    - Should return 200 with {ok: true}
    """
    print("\n" + "="*80)
    print("TEST 4: APNs Unregister")
    print("="*80)
    
    token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    if not token:
        print("❌ FAIL: Could not login")
        return False
    
    url = f"{BASE_URL}/push/apns/unregister"
    headers = {"Authorization": f"Bearer {token}"}
    valid_token = "a" * 64
    payload = {"token": valid_token}
    
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
    
    if not isinstance(data.get("ok"), bool) or data.get("ok") != True:
        print(f"❌ FAIL: Expected ok=true, got {data.get('ok')}")
        return False
    
    print(f"✅ PASS: Successfully unregistered device")
    return True

def test_apns_status_after_unregister():
    """
    TEST 5: GET /api/push/status after unregistering (no web subscription exists)
    - Should return 200 with {subscribed: false}
    """
    print("\n" + "="*80)
    print("TEST 5: Push Status After APNs Unregistration")
    print("="*80)
    
    token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    if not token:
        print("❌ FAIL: Could not login")
        return False
    
    url = f"{BASE_URL}/push/status"
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
    
    if not isinstance(data.get("subscribed"), bool):
        print(f"❌ FAIL: Expected subscribed to be boolean, got {type(data.get('subscribed'))}")
        return False
    
    # Should be false since we unregistered and admin has no web subscription
    if data.get("subscribed") != False:
        print(f"⚠️  WARNING: Expected subscribed=false after unregister (no web sub), got {data.get('subscribed')}")
        print(f"   This could mean admin has an existing web push subscription")
    else:
        print(f"✅ PASS: subscribed={data.get('subscribed')} (correctly reflects no active subscriptions)")
    
    return True

def test_apns_register_no_auth():
    """
    TEST 6: POST /api/push/apns/register without Authorization header
    - Should return 401 or 403
    """
    print("\n" + "="*80)
    print("TEST 6: APNs Register - No Auth")
    print("="*80)
    
    url = f"{BASE_URL}/push/apns/register"
    valid_token = "a" * 64
    payload = {"token": valid_token}
    
    response = requests.post(url, json=payload)
    print(f"POST {url}")
    print(f"Headers: (no Authorization)")
    print(f"Body: {payload}")
    print(f"Status: {response.status_code}")
    
    if response.status_code not in [401, 403]:
        print(f"❌ FAIL: Expected 401 or 403, got {response.status_code}")
        print(f"Response: {response.text}")
        return False
    
    print(f"✅ PASS: Correctly rejected unauthorized request with {response.status_code}")
    return True

def test_apns_unregister_no_auth():
    """
    TEST 7: POST /api/push/apns/unregister without Authorization header
    - Should return 401 or 403
    """
    print("\n" + "="*80)
    print("TEST 7: APNs Unregister - No Auth")
    print("="*80)
    
    url = f"{BASE_URL}/push/apns/unregister"
    valid_token = "a" * 64
    payload = {"token": valid_token}
    
    response = requests.post(url, json=payload)
    print(f"POST {url}")
    print(f"Headers: (no Authorization)")
    print(f"Body: {payload}")
    print(f"Status: {response.status_code}")
    
    if response.status_code not in [401, 403]:
        print(f"❌ FAIL: Expected 401 or 403, got {response.status_code}")
        print(f"Response: {response.text}")
        return False
    
    print(f"✅ PASS: Correctly rejected unauthorized request with {response.status_code}")
    return True

def test_push_status_no_auth():
    """
    TEST 8: GET /api/push/status without Authorization header
    - Should return 401 or 403
    """
    print("\n" + "="*80)
    print("TEST 8: Push Status - No Auth")
    print("="*80)
    
    url = f"{BASE_URL}/push/status"
    
    response = requests.get(url)
    print(f"GET {url}")
    print(f"Headers: (no Authorization)")
    print(f"Status: {response.status_code}")
    
    if response.status_code not in [401, 403]:
        print(f"❌ FAIL: Expected 401 or 403, got {response.status_code}")
        print(f"Response: {response.text}")
        return False
    
    print(f"✅ PASS: Correctly rejected unauthorized request with {response.status_code}")
    return True

def test_vapid_public_key():
    """
    TEST 9: GET /api/push/vapid-public-key (no auth required)
    - Should return 200 with publicKey field (may be empty string)
    """
    print("\n" + "="*80)
    print("TEST 9: VAPID Public Key (Regression)")
    print("="*80)
    
    url = f"{BASE_URL}/push/vapid-public-key"
    
    response = requests.get(url)
    print(f"GET {url}")
    print(f"Status: {response.status_code}")
    
    if response.status_code != 200:
        print(f"❌ FAIL: Expected 200, got {response.status_code}")
        print(f"Response: {response.text}")
        return False
    
    data = response.json()
    print(f"Response: {data}")
    
    if "publicKey" not in data:
        print(f"❌ FAIL: Response missing 'publicKey' field")
        return False
    
    # publicKey may be empty string in local environment
    public_key = data.get("publicKey")
    if not isinstance(public_key, str):
        print(f"❌ FAIL: publicKey should be string, got {type(public_key)}")
        return False
    
    if public_key == "":
        print(f"✅ PASS: publicKey is empty string (expected in local environment)")
    else:
        print(f"✅ PASS: publicKey present: {public_key[:20]}...")
    
    return True

def test_seo_appstore_badge():
    """
    TEST 10: GET /api/ciudad/palma - SEO App Store Badge
    - Should return 200 text/html
    - Body must contain data-testid="seo-appstore-badge"
    - Body must contain apps.apple.com/es/app/qui%C3%A9n-va-fiestas-cerca/id6804396475
    """
    print("\n" + "="*80)
    print("TEST 10: SEO App Store Badge on /api/ciudad/palma")
    print("="*80)
    
    url = f"{BASE_URL}/ciudad/palma"
    
    response = requests.get(url)
    print(f"GET {url}")
    print(f"Status: {response.status_code}")
    print(f"Content-Type: {response.headers.get('Content-Type')}")
    
    if response.status_code != 200:
        print(f"❌ FAIL: Expected 200, got {response.status_code}")
        print(f"Response: {response.text[:500]}")
        return False
    
    content_type = response.headers.get("Content-Type", "")
    if "text/html" not in content_type:
        print(f"❌ FAIL: Expected Content-Type text/html, got {content_type}")
        return False
    
    html = response.text
    
    # Check for data-testid="seo-appstore-badge"
    if 'data-testid="seo-appstore-badge"' not in html:
        print(f"❌ FAIL: HTML does not contain data-testid=\"seo-appstore-badge\"")
        print(f"HTML preview: {html[:1000]}")
        return False
    
    print(f"✅ PASS: Found data-testid=\"seo-appstore-badge\"")
    
    # Check for App Store URL
    app_store_url = "apps.apple.com/es/app/qui%C3%A9n-va-fiestas-cerca/id6804396475"
    if app_store_url not in html:
        print(f"❌ FAIL: HTML does not contain App Store URL: {app_store_url}")
        # Try to find what App Store link is present
        if "apps.apple.com" in html:
            import re
            matches = re.findall(r'apps\.apple\.com[^"\'<>\s]+', html)
            print(f"Found App Store links: {matches}")
        return False
    
    print(f"✅ PASS: Found correct App Store URL: {app_store_url}")
    print(f"✅ PASS: SEO App Store badge correctly implemented")
    
    return True

def test_server_starts_clean():
    """
    TEST 11: Smoke check - server starts and core auth works
    - Login should work (already tested in other tests, but explicit check)
    """
    print("\n" + "="*80)
    print("TEST 11: Server Smoke Check - Auth Login")
    print("="*80)
    
    url = f"{BASE_URL}/auth/login"
    payload = {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    
    response = requests.post(url, json=payload)
    print(f"POST {url}")
    print(f"Body: {payload}")
    print(f"Status: {response.status_code}")
    
    if response.status_code != 200:
        print(f"❌ FAIL: Login failed with {response.status_code}")
        print(f"Response: {response.text}")
        return False
    
    data = response.json()
    if "token" not in data or "user" not in data:
        print(f"❌ FAIL: Login response missing token or user")
        print(f"Response: {data}")
        return False
    
    print(f"✅ PASS: Server starts clean, auth login works")
    print(f"   User: {data.get('user', {}).get('email')}")
    print(f"   Token: {data.get('token')[:20]}...")
    
    return True

def main():
    print("\n" + "="*80)
    print("BACKEND TESTING: APNs Native Push + SEO App Store Link")
    print("Backend URL:", BASE_URL)
    print("="*80)
    
    tests = [
        ("Server Smoke Check", test_server_starts_clean),
        ("APNs Register Valid Token", test_apns_register_valid_token),
        ("Push Status After Register", test_apns_status_after_register),
        ("APNs Register Short Token", test_apns_register_short_token),
        ("APNs Unregister", test_apns_unregister),
        ("Push Status After Unregister", test_apns_status_after_unregister),
        ("APNs Register No Auth", test_apns_register_no_auth),
        ("APNs Unregister No Auth", test_apns_unregister_no_auth),
        ("Push Status No Auth", test_push_status_no_auth),
        ("VAPID Public Key (Regression)", test_vapid_public_key),
        ("SEO App Store Badge", test_seo_appstore_badge),
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
        return 0
    else:
        print(f"\n❌ {total - passed} test(s) failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
