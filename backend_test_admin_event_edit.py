#!/usr/bin/env python3
"""
Backend test for admin event edit endpoint with sticky buy-link override.
Tests the NEW PUT /api/admin/events/{event_id}/admin-edit endpoint.

Test scenarios:
1. Create event with commission_url, verify link_override is empty and auto_commission_url equals commission_url
2. Set link_override, verify commission_url uses override, link_override is set, auto_commission_url unchanged
3. Edit other fields (name), verify link_override persists (sticky)
4. Clear link_override with clear_link_override=true, verify commission_url reverts to automatic
5. Set override again, then clear with link_override="" (empty string)
6. Authorization: no auth → 401, non-admin → 403
7. Non-existent event → 404
8. Admin-only fields: non-admin user should not see link_override and auto_commission_url (null)
"""

import requests
import sys
from datetime import datetime, timedelta

# Backend URL from frontend/.env
BASE_URL = "https://seo-audit-fix-18.preview.emergentagent.com/api"

# Admin credentials from /app/memory/test_credentials.md
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

def log(msg):
    print(f"[TEST] {msg}")

def admin_login():
    """Login as admin and return token"""
    log("Logging in as admin...")
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if resp.status_code != 200:
        log(f"❌ Admin login failed: {resp.status_code} {resp.text}")
        sys.exit(1)
    token = resp.json()["token"]
    log(f"✅ Admin login successful, token: {token[:20]}...")
    return token

def create_test_user():
    """Create a non-admin test user and return token"""
    log("Creating non-admin test user...")
    timestamp = int(datetime.now().timestamp())
    email = f"testuser_{timestamp}@test.com"
    username = f"testuser{timestamp}"
    resp = requests.post(f"{BASE_URL}/auth/register", json={
        "email": email,
        "password": "testpass123",
        "name": f"Test User {timestamp}",
        "username": username,
        "birthdate": "1995-05-15",
        "city": "Palma de Mallorca"
    })
    if resp.status_code != 200:
        log(f"❌ User registration failed: {resp.status_code} {resp.text}")
        sys.exit(1)
    token = resp.json()["token"]
    log(f"✅ Non-admin user created: {email}, token: {token[:20]}...")
    return token

def create_test_event(admin_token, commission_url):
    """Create a test event via POST /api/admin/events"""
    log(f"Creating test event with commission_url={commission_url}...")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    resp = requests.post(f"{BASE_URL}/admin/events", 
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "name": "Test Event for Admin Edit",
            "venue": "Fitz Mallorca",
            "address": "Carrer de Felip II, 4, Palma",
            "date": tomorrow,
            "time": "23:00",
            "city": "Palma de Mallorca",
            "commission_url": commission_url,
            "has_commission": True,
            "sale_state": "a_la_venta",
            "price_tiers": [{"label": "General", "price": 25.0}]
        }
    )
    if resp.status_code != 200:
        log(f"❌ Event creation failed: {resp.status_code} {resp.text}")
        sys.exit(1)
    event = resp.json()
    event_id = event["id"]
    log(f"✅ Event created: {event_id}")
    return event_id

def get_event_as_admin(event_id, admin_token):
    """GET /api/events/{id} as admin"""
    resp = requests.get(f"{BASE_URL}/events/{event_id}",
        headers={"Authorization": f"Bearer {admin_token}"})
    if resp.status_code != 200:
        log(f"❌ GET event failed: {resp.status_code} {resp.text}")
        return None
    return resp.json()

def get_event_as_user(event_id, user_token):
    """GET /api/events/{id} as non-admin user"""
    resp = requests.get(f"{BASE_URL}/events/{event_id}",
        headers={"Authorization": f"Bearer {user_token}"})
    if resp.status_code != 200:
        log(f"❌ GET event as user failed: {resp.status_code} {resp.text}")
        return None
    return resp.json()

def admin_edit_event(event_id, admin_token, payload):
    """PUT /api/admin/events/{event_id}/admin-edit"""
    resp = requests.put(f"{BASE_URL}/admin/events/{event_id}/admin-edit",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=payload)
    return resp

def run_tests():
    """Run all test scenarios"""
    log("=" * 80)
    log("STARTING ADMIN EVENT EDIT + STICKY BUY-LINK OVERRIDE TESTS")
    log("=" * 80)
    
    # Login as admin
    admin_token = admin_login()
    
    # Test 1: Create event with commission_url, verify initial state
    log("\n" + "=" * 80)
    log("TEST 1: Create event with commission_url, verify link_override empty")
    log("=" * 80)
    
    original_url = "https://www.fourvenues.com/fitz-mallorca/4RA8"
    event_id = create_test_event(admin_token, original_url)
    
    event = get_event_as_admin(event_id, admin_token)
    if not event:
        log("❌ TEST 1 FAILED: Could not retrieve event")
        sys.exit(1)
    
    # Verify initial state
    commission_url = event.get("commission_url", "")
    link_override = event.get("link_override", "")
    auto_commission_url = event.get("auto_commission_url", "")
    
    log(f"commission_url: {commission_url}")
    log(f"link_override: '{link_override}'")
    log(f"auto_commission_url: {auto_commission_url}")
    
    if commission_url != original_url:
        log(f"❌ TEST 1 FAILED: commission_url should be {original_url}, got {commission_url}")
        sys.exit(1)
    if link_override != "":
        log(f"❌ TEST 1 FAILED: link_override should be empty, got '{link_override}'")
        sys.exit(1)
    if auto_commission_url != original_url:
        log(f"❌ TEST 1 FAILED: auto_commission_url should be {original_url}, got {auto_commission_url}")
        sys.exit(1)
    
    log("✅ TEST 1 PASSED: Initial state correct (commission_url=original, link_override='', auto_commission_url=original)")
    
    # Test 2: Set link_override, verify it takes precedence
    log("\n" + "=" * 80)
    log("TEST 2: Set link_override, verify commission_url uses override")
    log("=" * 80)
    
    override_url = "https://site.fourvenues.com/es/fitz-mallorca/events/jueves-fitz-10-09-20261-4RA8"
    resp = admin_edit_event(event_id, admin_token, {"link_override": override_url})
    
    if resp.status_code != 200:
        log(f"❌ TEST 2 FAILED: admin-edit returned {resp.status_code}: {resp.text}")
        sys.exit(1)
    
    event = resp.json()
    commission_url = event.get("commission_url", "")
    link_override = event.get("link_override", "")
    auto_commission_url = event.get("auto_commission_url", "")
    
    log(f"commission_url: {commission_url}")
    log(f"link_override: {link_override}")
    log(f"auto_commission_url: {auto_commission_url}")
    
    if commission_url != override_url:
        log(f"❌ TEST 2 FAILED: commission_url should be override {override_url}, got {commission_url}")
        sys.exit(1)
    if link_override != override_url:
        log(f"❌ TEST 2 FAILED: link_override should be {override_url}, got {link_override}")
        sys.exit(1)
    if auto_commission_url != original_url:
        log(f"❌ TEST 2 FAILED: auto_commission_url should still be {original_url}, got {auto_commission_url}")
        sys.exit(1)
    
    # Verify via fresh GET
    event = get_event_as_admin(event_id, admin_token)
    if event.get("commission_url") != override_url:
        log(f"❌ TEST 2 FAILED: Fresh GET shows commission_url={event.get('commission_url')}, expected {override_url}")
        sys.exit(1)
    
    log("✅ TEST 2 PASSED: link_override set, commission_url uses override, auto_commission_url unchanged")
    
    # Test 3: Edit other fields (name), verify link_override persists (sticky)
    log("\n" + "=" * 80)
    log("TEST 3: Edit name, verify link_override persists (sticky)")
    log("=" * 80)
    
    new_name = "NUEVO NOMBRE"
    resp = admin_edit_event(event_id, admin_token, {"name": new_name})
    
    if resp.status_code != 200:
        log(f"❌ TEST 3 FAILED: admin-edit returned {resp.status_code}: {resp.text}")
        sys.exit(1)
    
    event = resp.json()
    
    if event.get("name") != new_name:
        log(f"❌ TEST 3 FAILED: name should be '{new_name}', got '{event.get('name')}'")
        sys.exit(1)
    if event.get("commission_url") != override_url:
        log(f"❌ TEST 3 FAILED: commission_url should still be override {override_url}, got {event.get('commission_url')}")
        sys.exit(1)
    if event.get("link_override") != override_url:
        log(f"❌ TEST 3 FAILED: link_override should still be {override_url}, got {event.get('link_override')}")
        sys.exit(1)
    
    log("✅ TEST 3 PASSED: Name changed, link_override persisted (sticky)")
    
    # Test 4: Clear link_override with clear_link_override=true
    log("\n" + "=" * 80)
    log("TEST 4: Clear link_override with clear_link_override=true")
    log("=" * 80)
    
    resp = admin_edit_event(event_id, admin_token, {"clear_link_override": True})
    
    if resp.status_code != 200:
        log(f"❌ TEST 4 FAILED: admin-edit returned {resp.status_code}: {resp.text}")
        sys.exit(1)
    
    event = resp.json()
    commission_url = event.get("commission_url", "")
    link_override = event.get("link_override", "")
    
    log(f"commission_url: {commission_url}")
    log(f"link_override: '{link_override}'")
    
    if commission_url != original_url:
        log(f"❌ TEST 4 FAILED: commission_url should revert to {original_url}, got {commission_url}")
        sys.exit(1)
    if link_override != "":
        log(f"❌ TEST 4 FAILED: link_override should be empty, got '{link_override}'")
        sys.exit(1)
    
    log("✅ TEST 4 PASSED: link_override cleared, commission_url reverted to automatic")
    
    # Test 5: Set override again, then clear with link_override="" (empty string)
    log("\n" + "=" * 80)
    log("TEST 5: Set override again, then clear with link_override='' (empty string)")
    log("=" * 80)
    
    # Set override again
    resp = admin_edit_event(event_id, admin_token, {"link_override": override_url})
    if resp.status_code != 200:
        log(f"❌ TEST 5 FAILED: Could not set override again: {resp.status_code}")
        sys.exit(1)
    
    event = resp.json()
    if event.get("commission_url") != override_url:
        log(f"❌ TEST 5 FAILED: Override not set correctly")
        sys.exit(1)
    
    # Clear with empty string
    resp = admin_edit_event(event_id, admin_token, {"link_override": ""})
    if resp.status_code != 200:
        log(f"❌ TEST 5 FAILED: admin-edit with empty string returned {resp.status_code}: {resp.text}")
        sys.exit(1)
    
    event = resp.json()
    commission_url = event.get("commission_url", "")
    link_override = event.get("link_override", "")
    
    log(f"commission_url: {commission_url}")
    log(f"link_override: '{link_override}'")
    
    if commission_url != original_url:
        log(f"❌ TEST 5 FAILED: commission_url should revert to {original_url}, got {commission_url}")
        sys.exit(1)
    if link_override != "":
        log(f"❌ TEST 5 FAILED: link_override should be empty, got '{link_override}'")
        sys.exit(1)
    
    log("✅ TEST 5 PASSED: link_override cleared with empty string, commission_url reverted to automatic")
    
    # Test 6: Authorization checks
    log("\n" + "=" * 80)
    log("TEST 6: Authorization checks (no auth → 401, non-admin → 403)")
    log("=" * 80)
    
    # 6a: No auth
    resp = requests.put(f"{BASE_URL}/admin/events/{event_id}/admin-edit",
        json={"name": "Should Fail"})
    if resp.status_code != 401:
        log(f"❌ TEST 6a FAILED: Expected 401 without auth, got {resp.status_code}")
        sys.exit(1)
    log("✅ TEST 6a PASSED: No auth → 401")
    
    # 6b: Non-admin user
    user_token = create_test_user()
    resp = requests.put(f"{BASE_URL}/admin/events/{event_id}/admin-edit",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"name": "Should Fail"})
    if resp.status_code != 403:
        log(f"❌ TEST 6b FAILED: Expected 403 for non-admin, got {resp.status_code}")
        sys.exit(1)
    log("✅ TEST 6b PASSED: Non-admin → 403")
    
    # Test 7: Non-existent event → 404
    log("\n" + "=" * 80)
    log("TEST 7: Non-existent event → 404")
    log("=" * 80)
    
    fake_id = "00000000-0000-0000-0000-000000000000"
    resp = admin_edit_event(fake_id, admin_token, {"name": "Should Fail"})
    if resp.status_code != 404:
        log(f"❌ TEST 7 FAILED: Expected 404 for non-existent event, got {resp.status_code}")
        sys.exit(1)
    log("✅ TEST 7 PASSED: Non-existent event → 404")
    
    # Test 8: Admin-only fields (non-admin should not see link_override and auto_commission_url)
    log("\n" + "=" * 80)
    log("TEST 8: Admin-only fields (non-admin should see null for link_override and auto_commission_url)")
    log("=" * 80)
    
    # Set override again for this test
    resp = admin_edit_event(event_id, admin_token, {"link_override": override_url})
    if resp.status_code != 200:
        log(f"❌ TEST 8 FAILED: Could not set override: {resp.status_code}")
        sys.exit(1)
    
    # Get as non-admin user
    event_as_user = get_event_as_user(event_id, user_token)
    if not event_as_user:
        log("❌ TEST 8 FAILED: Could not retrieve event as user")
        sys.exit(1)
    
    link_override_user = event_as_user.get("link_override")
    auto_commission_url_user = event_as_user.get("auto_commission_url")
    
    log(f"Non-admin sees link_override: {link_override_user}")
    log(f"Non-admin sees auto_commission_url: {auto_commission_url_user}")
    
    if link_override_user is not None:
        log(f"❌ TEST 8 FAILED: Non-admin should see link_override=null, got {link_override_user}")
        sys.exit(1)
    if auto_commission_url_user is not None:
        log(f"❌ TEST 8 FAILED: Non-admin should see auto_commission_url=null, got {auto_commission_url_user}")
        sys.exit(1)
    
    # Verify admin still sees them
    event_as_admin = get_event_as_admin(event_id, admin_token)
    if event_as_admin.get("link_override") != override_url:
        log(f"❌ TEST 8 FAILED: Admin should see link_override={override_url}")
        sys.exit(1)
    if event_as_admin.get("auto_commission_url") != original_url:
        log(f"❌ TEST 8 FAILED: Admin should see auto_commission_url={original_url}")
        sys.exit(1)
    
    log("✅ TEST 8 PASSED: Admin-only fields correctly hidden from non-admin users")
    
    # All tests passed
    log("\n" + "=" * 80)
    log("🎉 ALL TESTS PASSED! 🎉")
    log("=" * 80)
    log("\nSUMMARY:")
    log("✅ TEST 1: Initial state (commission_url=original, link_override='', auto_commission_url=original)")
    log("✅ TEST 2: Set link_override (commission_url uses override, auto_commission_url unchanged)")
    log("✅ TEST 3: Edit other fields (link_override persists - sticky)")
    log("✅ TEST 4: Clear with clear_link_override=true (commission_url reverts to automatic)")
    log("✅ TEST 5: Clear with link_override='' (commission_url reverts to automatic)")
    log("✅ TEST 6a: No auth → 401")
    log("✅ TEST 6b: Non-admin → 403")
    log("✅ TEST 7: Non-existent event → 404")
    log("✅ TEST 8: Admin-only fields hidden from non-admin users")

if __name__ == "__main__":
    try:
        run_tests()
    except KeyboardInterrupt:
        log("\n❌ Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        log(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
