#!/usr/bin/env python3
"""
Backend test for ClubTickets admin features:
1. ClubTickets coverage panel (GET /api/admin/clubtickets-coverage)
2. Affiliate-link flip alert toggle (GET/PUT /api/admin/settings/affiliate-flip-alerts)
3. Changelog counts include affiliate_flip (GET /api/admin/scrape-changelog)
"""
import requests
import sys
import time

# Base URL from frontend/.env
BASE_URL = "https://plan-maker-29.preview.emergentagent.com/api"

# Admin credentials from test_credentials.md
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

def log(msg):
    print(f"[TEST] {msg}")

def admin_login():
    """Login as admin and return session cookies"""
    log("Logging in as admin...")
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if resp.status_code != 200:
        log(f"❌ Admin login failed: {resp.status_code} {resp.text}")
        sys.exit(1)
    log(f"✅ Admin login successful")
    return resp.cookies

def create_non_admin_user():
    """Create a non-admin user for 403 tests"""
    timestamp = int(time.time())
    email = f"testuser{timestamp}@test.com"
    username = f"testuser{timestamp}"
    log(f"Creating non-admin user: {email}")
    
    resp = requests.post(f"{BASE_URL}/auth/register", json={
        "email": email,
        "name": f"Test User {timestamp}",
        "username": username,
        "password": "testpass123",
        "birthdate": "1990-01-01",
        "city": "Ibiza"
    })
    if resp.status_code != 200:
        log(f"❌ Non-admin user registration failed: {resp.status_code} {resp.text}")
        sys.exit(1)
    
    # Login to get cookies
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": email,
        "password": "testpass123"
    })
    if resp.status_code != 200:
        log(f"❌ Non-admin user login failed: {resp.status_code} {resp.text}")
        sys.exit(1)
    
    log(f"✅ Non-admin user created and logged in")
    return resp.cookies

def test_clubtickets_coverage(admin_cookies, non_admin_cookies):
    """Test FEATURE 1: ClubTickets coverage panel"""
    log("\n=== FEATURE 1: ClubTickets Coverage Panel ===")
    
    # Test 1: GET as admin with default days
    log("Test 1.1: GET /api/admin/clubtickets-coverage as admin (default days)")
    resp = requests.get(f"{BASE_URL}/admin/clubtickets-coverage", cookies=admin_cookies)
    if resp.status_code != 200:
        log(f"❌ FAILED: Expected 200, got {resp.status_code}")
        log(f"Response: {resp.text}")
        return False
    
    data = resp.json()
    log(f"✅ PASSED: Status 200")
    
    # Validate response structure
    required_keys = ["aff_code", "updated_at", "totals", "venues"]
    for key in required_keys:
        if key not in data:
            log(f"❌ FAILED: Missing key '{key}' in response")
            return False
    log(f"✅ PASSED: All required keys present: {required_keys}")
    
    # Validate aff_code
    if not isinstance(data["aff_code"], str):
        log(f"❌ FAILED: aff_code is not a string: {data['aff_code']}")
        return False
    log(f"✅ PASSED: aff_code is string: {data['aff_code']}")
    
    # Validate totals structure
    totals = data["totals"]
    required_totals = ["parties", "matched", "unmatched", "with_price"]
    for key in required_totals:
        if key not in totals:
            log(f"❌ FAILED: Missing key '{key}' in totals")
            return False
        if not isinstance(totals[key], int):
            log(f"❌ FAILED: totals.{key} is not an int: {totals[key]}")
            return False
    log(f"✅ PASSED: totals has all required int fields: {required_totals}")
    
    # Validate totals.matched + totals.unmatched == totals.parties
    if totals["matched"] + totals["unmatched"] != totals["parties"]:
        log(f"❌ FAILED: matched ({totals['matched']}) + unmatched ({totals['unmatched']}) != parties ({totals['parties']})")
        return False
    log(f"✅ PASSED: matched + unmatched == parties ({totals['parties']})")
    
    # Validate venues is a non-empty list
    venues = data["venues"]
    if not isinstance(venues, list):
        log(f"❌ FAILED: venues is not a list: {type(venues)}")
        return False
    if len(venues) == 0:
        log(f"⚠️  WARNING: venues list is empty (expected ~15 Ibiza clubs)")
    else:
        log(f"✅ PASSED: venues is a non-empty list with {len(venues)} clubs")
    
    # Validate venue structure
    if len(venues) > 0:
        venue = venues[0]
        required_venue_keys = ["slug", "name", "total", "matched", "unmatched", "with_price", "parties"]
        for key in required_venue_keys:
            if key not in venue:
                log(f"❌ FAILED: Missing key '{key}' in venue")
                return False
        log(f"✅ PASSED: Venue has all required keys: {required_venue_keys}")
        
        # Validate parties structure
        parties = venue["parties"]
        if not isinstance(parties, list):
            log(f"❌ FAILED: venue.parties is not a list: {type(parties)}")
            return False
        
        if len(parties) > 0:
            party = parties[0]
            required_party_keys = ["name", "date", "matched", "has_price", "in_app_name", "event_id", "sale_state", "url"]
            for key in required_party_keys:
                if key not in party:
                    log(f"❌ FAILED: Missing key '{key}' in party")
                    return False
            
            # Validate party.matched is a boolean
            if not isinstance(party["matched"], bool):
                log(f"❌ FAILED: party.matched is not a boolean: {party['matched']} (type: {type(party['matched'])})")
                return False
            log(f"✅ PASSED: party.matched is boolean: {party['matched']}")
            
            # Validate party.has_price is a boolean
            if not isinstance(party["has_price"], bool):
                log(f"❌ FAILED: party.has_price is not a boolean: {party['has_price']}")
                return False
            log(f"✅ PASSED: party.has_price is boolean: {party['has_price']}")
    
    # Test 2: GET with optional ?days=30 parameter
    log("\nTest 1.2: GET /api/admin/clubtickets-coverage?days=30 as admin")
    resp = requests.get(f"{BASE_URL}/admin/clubtickets-coverage?days=30", cookies=admin_cookies)
    if resp.status_code != 200:
        log(f"❌ FAILED: Expected 200, got {resp.status_code}")
        return False
    log(f"✅ PASSED: Status 200 with days=30 parameter")
    
    # Test 3: GET as non-admin user (should be 403)
    log("\nTest 1.3: GET /api/admin/clubtickets-coverage as non-admin user (expect 403)")
    resp = requests.get(f"{BASE_URL}/admin/clubtickets-coverage", cookies=non_admin_cookies)
    if resp.status_code != 403:
        log(f"❌ FAILED: Expected 403, got {resp.status_code}")
        return False
    log(f"✅ PASSED: Status 403 for non-admin user")
    
    # Test 4: GET without auth (should be 401)
    log("\nTest 1.4: GET /api/admin/clubtickets-coverage without auth (expect 401)")
    resp = requests.get(f"{BASE_URL}/admin/clubtickets-coverage")
    if resp.status_code != 401:
        log(f"❌ FAILED: Expected 401, got {resp.status_code}")
        return False
    log(f"✅ PASSED: Status 401 without auth")
    
    log("\n✅ FEATURE 1 COMPLETE: All ClubTickets coverage panel tests passed")
    return True

def test_affiliate_flip_alerts(admin_cookies, non_admin_cookies):
    """Test FEATURE 2: Affiliate-link flip alert toggle"""
    log("\n=== FEATURE 2: Affiliate-link Flip Alert Toggle ===")
    
    # Test 1: GET as admin (should default to enabled=true)
    log("Test 2.1: GET /api/admin/settings/affiliate-flip-alerts as admin")
    resp = requests.get(f"{BASE_URL}/admin/settings/affiliate-flip-alerts", cookies=admin_cookies)
    if resp.status_code != 200:
        log(f"❌ FAILED: Expected 200, got {resp.status_code}")
        log(f"Response: {resp.text}")
        return False
    
    data = resp.json()
    if "enabled" not in data:
        log(f"❌ FAILED: Missing 'enabled' key in response")
        return False
    
    if not isinstance(data["enabled"], bool):
        log(f"❌ FAILED: enabled is not a boolean: {data['enabled']}")
        return False
    
    log(f"✅ PASSED: Status 200 with enabled={data['enabled']} (default ON expected)")
    initial_state = data["enabled"]
    
    # Test 2: PUT to disable (enabled=false)
    log("\nTest 2.2: PUT /api/admin/settings/affiliate-flip-alerts {enabled: false}")
    resp = requests.put(f"{BASE_URL}/admin/settings/affiliate-flip-alerts", 
                       json={"enabled": False}, 
                       cookies=admin_cookies)
    if resp.status_code != 200:
        log(f"❌ FAILED: Expected 200, got {resp.status_code}")
        log(f"Response: {resp.text}")
        return False
    
    data = resp.json()
    if data.get("enabled") != False:
        log(f"❌ FAILED: Expected enabled=false, got {data.get('enabled')}")
        return False
    log(f"✅ PASSED: Status 200 with enabled=false")
    
    # Test 3: GET to verify it's disabled
    log("\nTest 2.3: GET /api/admin/settings/affiliate-flip-alerts (verify disabled)")
    resp = requests.get(f"{BASE_URL}/admin/settings/affiliate-flip-alerts", cookies=admin_cookies)
    if resp.status_code != 200:
        log(f"❌ FAILED: Expected 200, got {resp.status_code}")
        return False
    
    data = resp.json()
    if data.get("enabled") != False:
        log(f"❌ FAILED: Expected enabled=false, got {data.get('enabled')}")
        return False
    log(f"✅ PASSED: Verified enabled=false persisted")
    
    # Test 4: PUT to enable (enabled=true)
    log("\nTest 2.4: PUT /api/admin/settings/affiliate-flip-alerts {enabled: true}")
    resp = requests.put(f"{BASE_URL}/admin/settings/affiliate-flip-alerts", 
                       json={"enabled": True}, 
                       cookies=admin_cookies)
    if resp.status_code != 200:
        log(f"❌ FAILED: Expected 200, got {resp.status_code}")
        return False
    
    data = resp.json()
    if data.get("enabled") != True:
        log(f"❌ FAILED: Expected enabled=true, got {data.get('enabled')}")
        return False
    log(f"✅ PASSED: Status 200 with enabled=true (left enabled at the end)")
    
    # Test 5: GET as non-admin user (should be 403)
    log("\nTest 2.5: GET /api/admin/settings/affiliate-flip-alerts as non-admin (expect 403)")
    resp = requests.get(f"{BASE_URL}/admin/settings/affiliate-flip-alerts", cookies=non_admin_cookies)
    if resp.status_code != 403:
        log(f"❌ FAILED: Expected 403, got {resp.status_code}")
        return False
    log(f"✅ PASSED: Status 403 for non-admin user")
    
    # Test 6: GET without auth (should be 401)
    log("\nTest 2.6: GET /api/admin/settings/affiliate-flip-alerts without auth (expect 401)")
    resp = requests.get(f"{BASE_URL}/admin/settings/affiliate-flip-alerts")
    if resp.status_code != 401:
        log(f"❌ FAILED: Expected 401, got {resp.status_code}")
        return False
    log(f"✅ PASSED: Status 401 without auth")
    
    log("\n✅ FEATURE 2 COMPLETE: All affiliate-flip-alerts toggle tests passed")
    return True

def test_changelog_affiliate_flip(admin_cookies):
    """Test FEATURE 3: Changelog counts include affiliate_flip"""
    log("\n=== FEATURE 3: Changelog Counts Include affiliate_flip ===")
    
    # Test: GET /api/admin/scrape-changelog?limit=10 as admin
    log("Test 3.1: GET /api/admin/scrape-changelog?limit=10 as admin")
    resp = requests.get(f"{BASE_URL}/admin/scrape-changelog?limit=10", cookies=admin_cookies)
    if resp.status_code != 200:
        log(f"❌ FAILED: Expected 200, got {resp.status_code}")
        log(f"Response: {resp.text}")
        return False
    
    data = resp.json()
    log(f"✅ PASSED: Status 200")
    
    # Validate response structure
    if "counts" not in data:
        log(f"❌ FAILED: Missing 'counts' key in response")
        return False
    
    counts = data["counts"]
    if not isinstance(counts, dict):
        log(f"❌ FAILED: counts is not a dict: {type(counts)}")
        return False
    
    # Validate affiliate_flip key exists in counts
    if "affiliate_flip" not in counts:
        log(f"❌ FAILED: Missing 'affiliate_flip' key in counts object")
        log(f"Available keys: {list(counts.keys())}")
        return False
    
    affiliate_flip_count = counts["affiliate_flip"]
    if not isinstance(affiliate_flip_count, int):
        log(f"❌ FAILED: affiliate_flip is not an int: {affiliate_flip_count} (type: {type(affiliate_flip_count)})")
        return False
    
    log(f"✅ PASSED: counts object contains 'affiliate_flip' key with int value: {affiliate_flip_count}")
    
    # Validate other expected keys
    expected_keys = ["new", "price_up", "price_down", "state", "sold_out", "on_sale", "affiliate_flip"]
    for key in expected_keys:
        if key not in counts:
            log(f"⚠️  WARNING: Missing expected key '{key}' in counts")
        else:
            if not isinstance(counts[key], int):
                log(f"❌ FAILED: counts.{key} is not an int: {counts[key]}")
                return False
    log(f"✅ PASSED: All expected count keys are integers")
    
    log("\n✅ FEATURE 3 COMPLETE: Changelog affiliate_flip count test passed")
    return True

def main():
    log("Starting ClubTickets admin features backend tests...")
    log(f"Base URL: {BASE_URL}")
    
    # Login as admin
    admin_cookies = admin_login()
    
    # Create non-admin user for 403 tests
    non_admin_cookies = create_non_admin_user()
    
    # Run all tests
    results = []
    
    # FEATURE 1: ClubTickets coverage panel
    results.append(("ClubTickets Coverage Panel", test_clubtickets_coverage(admin_cookies, non_admin_cookies)))
    
    # FEATURE 2: Affiliate-link flip alert toggle
    results.append(("Affiliate-link Flip Alert Toggle", test_affiliate_flip_alerts(admin_cookies, non_admin_cookies)))
    
    # FEATURE 3: Changelog counts include affiliate_flip
    results.append(("Changelog affiliate_flip Count", test_changelog_affiliate_flip(admin_cookies)))
    
    # Summary
    log("\n" + "="*60)
    log("TEST SUMMARY")
    log("="*60)
    
    passed = 0
    failed = 0
    for name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        log(f"{status}: {name}")
        if result:
            passed += 1
        else:
            failed += 1
    
    log("="*60)
    log(f"Total: {passed} passed, {failed} failed")
    log("="*60)
    
    if failed > 0:
        sys.exit(1)
    else:
        log("\n🎉 ALL TESTS PASSED!")
        sys.exit(0)

if __name__ == "__main__":
    main()
