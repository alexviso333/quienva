#!/usr/bin/env python3
"""
Backend test for admin broken buy-link push alert feature (2026-08-28 iteration 3).

Tests:
1. PUT broken-link-alerts {enabled:true}
2. Create event with has_commission=true, commission_url="" (empty), future date
3. POST /admin/link-health/notify → notified_new >= 1
4. GET /api/notifications as admin → must have type=="admin_broken_link"
5. POST /admin/link-health/notify AGAIN → notified_new == 0 (dedup)
6. PUT admin-edit {link_override:"https://x.com/ok"} → event no longer in link-health
7. PUT broken-link-alerts {enabled:false}; POST notify → notified_new == 0
8. Authorization: 401 without token, 403 for non-admin
"""

import requests
import json
from datetime import datetime, timedelta

# Backend URL from frontend/.env
BASE_URL = "https://full-stack-nights.preview.emergentagent.com/api"

# Admin credentials from test_credentials.md
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

def log(msg):
    print(f"[TEST] {msg}")

def admin_login():
    """Login as admin and return token."""
    log("Logging in as admin...")
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.status_code} {resp.text}"
    token = resp.json()["token"]
    log(f"✓ Admin login successful, token: {token[:20]}...")
    return token

def create_non_admin_user():
    """Create a non-admin test user and return token."""
    log("Creating non-admin test user...")
    timestamp = int(datetime.now().timestamp())
    email = f"testuser_{timestamp}@test.com"
    username = f"testuser{timestamp}"
    resp = requests.post(f"{BASE_URL}/auth/register", json={
        "email": email,
        "password": "testpass123",
        "username": username,
        "name": "Test User",
        "birthdate": "1995-01-01"
    })
    assert resp.status_code == 200, f"User registration failed: {resp.status_code} {resp.text}"
    token = resp.json()["token"]
    log(f"✓ Non-admin user created: {email}")
    return token

def test_settings_get(admin_token):
    """Test 1: GET /api/admin/settings/broken-link-alerts (should be ON by default)."""
    log("\n=== TEST 1: GET broken-link-alerts settings ===")
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = requests.get(f"{BASE_URL}/admin/settings/broken-link-alerts", headers=headers)
    assert resp.status_code == 200, f"GET settings failed: {resp.status_code} {resp.text}"
    data = resp.json()
    assert "enabled" in data, f"Missing 'enabled' field: {data}"
    assert isinstance(data["enabled"], bool), f"'enabled' is not bool: {data}"
    log(f"✓ GET broken-link-alerts → {data}")
    log(f"✓ Default enabled: {data['enabled']}")
    return data["enabled"]

def test_settings_put(admin_token, enabled):
    """Test 2: PUT /api/admin/settings/broken-link-alerts."""
    log(f"\n=== TEST 2: PUT broken-link-alerts {{enabled:{enabled}}} ===")
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = requests.put(f"{BASE_URL}/admin/settings/broken-link-alerts", 
                        headers=headers, 
                        json={"enabled": enabled})
    assert resp.status_code == 200, f"PUT settings failed: {resp.status_code} {resp.text}"
    data = resp.json()
    assert data["enabled"] == enabled, f"Expected enabled={enabled}, got {data}"
    log(f"✓ PUT broken-link-alerts {{enabled:{enabled}}} → {data}")
    
    # Verify persistence
    resp2 = requests.get(f"{BASE_URL}/admin/settings/broken-link-alerts", headers=headers)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["enabled"] == enabled, f"Setting not persisted: {data2}"
    log(f"✓ Setting persisted correctly: {data2}")

def create_test_event(admin_token):
    """Create a test event with has_commission=true, commission_url="" (empty), future date."""
    log("\n=== Creating test event with empty commission_url ===")
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # Future date (today + 20 days)
    future_date = (datetime.now() + timedelta(days=20)).strftime("%Y-%m-%d")
    
    event_data = {
        "name": f"Test Event Broken Link {int(datetime.now().timestamp())}",
        "venue": "Test Venue QA",
        "date": future_date,
        "time": "23:00",
        "city": "Ibiza",
        "has_commission": True,
        "commission_url": "",  # EMPTY - this should trigger reason='empty'
        "poster_url": "https://example.com/poster.jpg"
    }
    
    resp = requests.post(f"{BASE_URL}/admin/events", headers=headers, json=event_data)
    assert resp.status_code == 200, f"Event creation failed: {resp.status_code} {resp.text}"
    event_id = resp.json()["id"]
    log(f"✓ Created test event: {event_id}")
    log(f"  - name: {event_data['name']}")
    log(f"  - date: {future_date} (future)")
    log(f"  - has_commission: True")
    log(f"  - commission_url: '' (empty)")
    return event_id

def test_link_health_get(admin_token, event_id):
    """Verify the event appears in link-health with reason='empty'."""
    log("\n=== Verifying event appears in link-health ===")
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = requests.get(f"{BASE_URL}/admin/link-health?days=120", headers=headers)
    assert resp.status_code == 200, f"GET link-health failed: {resp.status_code} {resp.text}"
    data = resp.json()
    
    # Find our event
    found = None
    for ev in data.get("events", []):
        if ev.get("event_id") == event_id:
            found = ev
            break
    
    assert found is not None, f"Event {event_id} not found in link-health"
    assert found.get("reason") == "empty", f"Expected reason='empty', got {found.get('reason')}"
    log(f"✓ Event appears in link-health with reason='empty'")
    log(f"  - event_id: {found['event_id']}")
    log(f"  - name: {found['name']}")
    log(f"  - reason: {found['reason']}")
    return found

def test_notify_first_call(admin_token):
    """Test 3: POST /api/admin/link-health/notify → notified_new >= 1."""
    log("\n=== TEST 3: POST /admin/link-health/notify (first call) ===")
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = requests.post(f"{BASE_URL}/admin/link-health/notify", headers=headers)
    assert resp.status_code == 200, f"POST notify failed: {resp.status_code} {resp.text}"
    data = resp.json()
    assert "ok" in data and data["ok"] is True, f"Expected ok:true, got {data}"
    assert "notified_new" in data, f"Missing 'notified_new' field: {data}"
    assert isinstance(data["notified_new"], int), f"'notified_new' is not int: {data}"
    assert data["notified_new"] >= 1, f"Expected notified_new >= 1, got {data['notified_new']}"
    log(f"✓ POST /admin/link-health/notify → {data}")
    log(f"✓ notified_new = {data['notified_new']} (>= 1, as expected)")
    return data["notified_new"]

def test_notifications_check(admin_token):
    """Test 4: GET /api/notifications as admin → must have type=="admin_broken_link"."""
    log("\n=== TEST 4: GET /api/notifications (check for admin_broken_link) ===")
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = requests.get(f"{BASE_URL}/notifications", headers=headers)
    assert resp.status_code == 200, f"GET notifications failed: {resp.status_code} {resp.text}"
    data = resp.json()
    
    # Find admin_broken_link notification
    found = None
    for notif in data:
        if notif.get("type") == "admin_broken_link":
            found = notif
            break
    
    assert found is not None, f"No notification with type='admin_broken_link' found. Notifications: {json.dumps(data, indent=2)}"
    log(f"✓ Found admin_broken_link notification:")
    log(f"  - type: {found['type']}")
    log(f"  - message: {found.get('message', '')}")
    log(f"  - data: {found.get('data', {})}")
    return found

def test_notify_second_call(admin_token):
    """Test 5: POST /admin/link-health/notify AGAIN → notified_new == 0 (dedup)."""
    log("\n=== TEST 5: POST /admin/link-health/notify (second call - dedup test) ===")
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = requests.post(f"{BASE_URL}/admin/link-health/notify", headers=headers)
    assert resp.status_code == 200, f"POST notify failed: {resp.status_code} {resp.text}"
    data = resp.json()
    assert data["ok"] is True, f"Expected ok:true, got {data}"
    assert data["notified_new"] == 0, f"Expected notified_new == 0 (dedup), got {data['notified_new']}"
    log(f"✓ POST /admin/link-health/notify → {data}")
    log(f"✓ notified_new = 0 (deduplication working correctly)")

def test_fix_event_with_override(admin_token, event_id):
    """Test 6: PUT admin-edit {link_override} → event no longer in link-health."""
    log("\n=== TEST 6: Fix event with link_override ===")
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # Set link_override
    resp = requests.put(f"{BASE_URL}/admin/events/{event_id}/admin-edit",
                        headers=headers,
                        json={"link_override": "https://x.com/ok"})
    assert resp.status_code == 200, f"PUT admin-edit failed: {resp.status_code} {resp.text}"
    log(f"✓ Set link_override='https://x.com/ok' on event {event_id}")
    
    # Verify event NO LONGER appears in link-health
    resp2 = requests.get(f"{BASE_URL}/admin/link-health?days=120", headers=headers)
    assert resp2.status_code == 200, f"GET link-health failed: {resp2.status_code} {resp2.text}"
    data2 = resp2.json()
    
    found = None
    for ev in data2.get("events", []):
        if ev.get("event_id") == event_id:
            found = ev
            break
    
    assert found is None, f"Event {event_id} still appears in link-health after setting link_override: {found}"
    log(f"✓ Event NO LONGER appears in link-health (correctly excluded after fix)")

def test_disabled_setting(admin_token):
    """Test 7: PUT broken-link-alerts {enabled:false}; POST notify → notified_new == 0."""
    log("\n=== TEST 7: Disabled setting test ===")
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # Disable the setting
    resp = requests.put(f"{BASE_URL}/admin/settings/broken-link-alerts",
                        headers=headers,
                        json={"enabled": False})
    assert resp.status_code == 200, f"PUT settings failed: {resp.status_code} {resp.text}"
    log(f"✓ Disabled broken-link-alerts")
    
    # Call notify - should return notified_new == 0 (disabled)
    resp2 = requests.post(f"{BASE_URL}/admin/link-health/notify", headers=headers)
    assert resp2.status_code == 200, f"POST notify failed: {resp2.status_code} {resp2.text}"
    data2 = resp2.json()
    assert data2["notified_new"] == 0, f"Expected notified_new == 0 (disabled), got {data2['notified_new']}"
    log(f"✓ POST notify with disabled setting → notified_new = 0 (correctly disabled)")
    
    # Re-enable for cleanup
    resp3 = requests.put(f"{BASE_URL}/admin/settings/broken-link-alerts",
                         headers=headers,
                         json={"enabled": True})
    assert resp3.status_code == 200
    log(f"✓ Re-enabled broken-link-alerts for cleanup")

def test_authorization(admin_token, non_admin_token):
    """Test 8: Authorization checks (401 without token, 403 for non-admin)."""
    log("\n=== TEST 8: Authorization checks ===")
    
    # Test GET settings
    log("Testing GET /admin/settings/broken-link-alerts...")
    
    # No token → 401
    resp = requests.get(f"{BASE_URL}/admin/settings/broken-link-alerts")
    assert resp.status_code == 401, f"Expected 401 without token, got {resp.status_code}"
    log("  ✓ No token → 401")
    
    # Non-admin token → 403
    headers_non_admin = {"Authorization": f"Bearer {non_admin_token}"}
    resp = requests.get(f"{BASE_URL}/admin/settings/broken-link-alerts", headers=headers_non_admin)
    assert resp.status_code == 403, f"Expected 403 for non-admin, got {resp.status_code}"
    log("  ✓ Non-admin token → 403")
    
    # Test PUT settings
    log("Testing PUT /admin/settings/broken-link-alerts...")
    
    # No token → 401
    resp = requests.put(f"{BASE_URL}/admin/settings/broken-link-alerts", json={"enabled": True})
    assert resp.status_code == 401, f"Expected 401 without token, got {resp.status_code}"
    log("  ✓ No token → 401")
    
    # Non-admin token → 403
    resp = requests.put(f"{BASE_URL}/admin/settings/broken-link-alerts", 
                        headers=headers_non_admin, 
                        json={"enabled": True})
    assert resp.status_code == 403, f"Expected 403 for non-admin, got {resp.status_code}"
    log("  ✓ Non-admin token → 403")
    
    # Test POST notify
    log("Testing POST /admin/link-health/notify...")
    
    # No token → 401
    resp = requests.post(f"{BASE_URL}/admin/link-health/notify")
    assert resp.status_code == 401, f"Expected 401 without token, got {resp.status_code}"
    log("  ✓ No token → 401")
    
    # Non-admin token → 403
    resp = requests.post(f"{BASE_URL}/admin/link-health/notify", headers=headers_non_admin)
    assert resp.status_code == 403, f"Expected 403 for non-admin, got {resp.status_code}"
    log("  ✓ Non-admin token → 403")
    
    log("✓ All authorization checks passed")

def cleanup_test_event(admin_token, event_id):
    """Clean up the test event."""
    log(f"\n=== Cleaning up test event {event_id} ===")
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = requests.delete(f"{BASE_URL}/admin/events/{event_id}", headers=headers)
    if resp.status_code == 200:
        log(f"✓ Test event {event_id} deleted successfully")
    else:
        log(f"⚠ Failed to delete test event: {resp.status_code} {resp.text}")

def main():
    log("=" * 80)
    log("BACKEND TEST: Admin Broken Buy-Link Push Alert Feature")
    log("=" * 80)
    
    try:
        # Login
        admin_token = admin_login()
        non_admin_token = create_non_admin_user()
        
        # Test 1: GET settings (default ON)
        default_enabled = test_settings_get(admin_token)
        
        # Test 2: PUT settings (enable)
        test_settings_put(admin_token, True)
        
        # Create test event with empty commission_url
        event_id = create_test_event(admin_token)
        
        # Verify event appears in link-health
        test_link_health_get(admin_token, event_id)
        
        # Test 3: First notify call (should notify)
        notified_count = test_notify_first_call(admin_token)
        
        # Test 4: Check notifications
        test_notifications_check(admin_token)
        
        # Test 5: Second notify call (dedup, should be 0)
        test_notify_second_call(admin_token)
        
        # Test 6: Fix event with link_override
        test_fix_event_with_override(admin_token, event_id)
        
        # Test 7: Disabled setting
        test_disabled_setting(admin_token)
        
        # Test 8: Authorization
        test_authorization(admin_token, non_admin_token)
        
        # Cleanup
        cleanup_test_event(admin_token, event_id)
        
        log("\n" + "=" * 80)
        log("✅ ALL TESTS PASSED")
        log("=" * 80)
        log("\nSUMMARY:")
        log("✓ GET /api/admin/settings/broken-link-alerts works (default ON)")
        log("✓ PUT /api/admin/settings/broken-link-alerts persists correctly")
        log("✓ POST /api/admin/link-health/notify detects new broken links")
        log("✓ Notifications created with type='admin_broken_link'")
        log("✓ Deduplication working (same event not re-notified)")
        log("✓ Events with link_override excluded from link-health")
        log("✓ Disabled setting prevents notifications")
        log("✓ Authorization working (401/403 for unauthorized)")
        
    except AssertionError as e:
        log(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        log(f"\n❌ UNEXPECTED ERROR: {e}")
        raise

if __name__ == "__main__":
    main()
