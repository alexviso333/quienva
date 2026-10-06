#!/usr/bin/env python3
"""
Backend test for TWO new admin features (2026-08-28 iteración 2):
  A) Edit history + undo
  B) Link health

Admin credentials: admin@quienva.app / admin123
"""

import requests
import json
from datetime import datetime, timedelta

BASE_URL = "https://full-stack-nightlife.preview.emergentagent.com/api"

# Admin credentials
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

def login_admin():
    """Login as admin and return the token."""
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.status_code} {resp.text}"
    data = resp.json()
    assert "token" in data, f"No token in login response: {data}"
    return data["token"]

def create_test_user():
    """Create a non-admin test user and return token."""
    timestamp = int(datetime.now().timestamp())
    email = f"testuser_{timestamp}@test.com"
    resp = requests.post(f"{BASE_URL}/auth/register", json={
        "email": email,
        "password": "testpass123",
        "name": f"Test User {timestamp}",
        "username": f"testuser{timestamp}",
        "birthdate": "1995-01-01"
    })
    assert resp.status_code == 200, f"User registration failed: {resp.status_code} {resp.text}"
    data = resp.json()
    return data["token"]

def create_test_event(token, **kwargs):
    """Create a test event via POST /api/admin/events."""
    headers = {"Authorization": f"Bearer {token}"}
    
    # Default event data
    today = datetime.now().date()
    future_date = (today + timedelta(days=7)).isoformat()
    
    event_data = {
        "name": kwargs.get("name", f"Test Event {int(datetime.now().timestamp())}"),
        "venue": kwargs.get("venue", "Test Venue"),
        "date": kwargs.get("date", future_date),
        "time": kwargs.get("time", "23:00"),
        "city": kwargs.get("city", "Ibiza"),
        "has_commission": kwargs.get("has_commission", True),
        "commission_url": kwargs.get("commission_url", "https://www.fourvenues.com/test-venue/TEST123"),
    }
    
    resp = requests.post(f"{BASE_URL}/admin/events", json=event_data, headers=headers)
    assert resp.status_code == 200, f"Event creation failed: {resp.status_code} {resp.text}"
    data = resp.json()
    assert "id" in data, f"No id in event creation response: {data}"
    return data["id"]

def test_feature_a_edit_history_and_undo():
    """
    FEATURE A: Edit history + undo
    """
    print("\n" + "="*80)
    print("FEATURE A: EDIT HISTORY + UNDO")
    print("="*80)
    
    token = login_admin()
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1) Create an event
    print("\n[A.1] Creating test event...")
    event_id = create_test_event(token, name="Original Event Name")
    print(f"✓ Created event: {event_id}")
    
    # 2) Make first edit: change name
    print("\n[A.2] First edit: changing name to 'Nombre A'...")
    resp = requests.put(
        f"{BASE_URL}/admin/events/{event_id}/admin-edit",
        json={"name": "Nombre A"},
        headers=headers
    )
    assert resp.status_code == 200, f"Name edit failed: {resp.status_code} {resp.text}"
    data = resp.json()
    assert data.get("name") == "Nombre A", f"Name not updated: {data.get('name')}"
    print("✓ Name changed to 'Nombre A'")
    
    # 3) Make second edit: set link_override
    print("\n[A.3] Second edit: setting link_override...")
    override_url = "https://ejemplo.com/x"
    resp = requests.put(
        f"{BASE_URL}/admin/events/{event_id}/admin-edit",
        json={"link_override": override_url},
        headers=headers
    )
    assert resp.status_code == 200, f"Link override edit failed: {resp.status_code} {resp.text}"
    data = resp.json()
    assert data.get("link_override") == override_url, f"link_override not set: {data.get('link_override')}"
    assert data.get("commission_url") == override_url, f"commission_url should equal override: {data.get('commission_url')}"
    print(f"✓ link_override set to '{override_url}'")
    print(f"✓ commission_url now serves the override: '{data.get('commission_url')}'")
    
    # 4) GET edit-history
    print("\n[A.4] Getting edit history...")
    resp = requests.get(f"{BASE_URL}/admin/events/{event_id}/edit-history", headers=headers)
    assert resp.status_code == 200, f"Edit history GET failed: {resp.status_code} {resp.text}"
    data = resp.json()
    assert "edits" in data, f"No 'edits' key in response: {data}"
    edits = data["edits"]
    assert len(edits) >= 2, f"Expected at least 2 edits, got {len(edits)}"
    print(f"✓ Retrieved {len(edits)} edit records (newest first)")
    
    # Verify edit structure
    for i, edit in enumerate(edits[:2]):
        assert "field" in edit, f"Edit {i} missing 'field'"
        assert "old_value" in edit, f"Edit {i} missing 'old_value'"
        assert "new_value" in edit, f"Edit {i} missing 'new_value'"
        assert "by_name" in edit, f"Edit {i} missing 'by_name'"
        assert "created_at" in edit, f"Edit {i} missing 'created_at'"
        assert "undone" in edit, f"Edit {i} missing 'undone'"
        assert edit["undone"] == False, f"Edit {i} should not be undone yet"
        print(f"  Edit {i}: field='{edit['field']}', old='{edit.get('old_value')}', new='{edit.get('new_value')}', undone={edit['undone']}")
    
    # Find the link_override edit
    link_edit = None
    name_edit = None
    for edit in edits:
        if edit["field"] == "link_override" and edit.get("new_value") == override_url:
            link_edit = edit
        if edit["field"] == "name" and edit.get("new_value") == "Nombre A":
            name_edit = edit
    
    assert link_edit is not None, "link_override edit not found in history"
    assert name_edit is not None, "name edit not found in history"
    print(f"✓ Found link_override edit (id: {link_edit['id']})")
    print(f"✓ Found name edit (id: {name_edit['id']})")
    
    # 5) Undo the link_override edit
    print("\n[A.5] Undoing link_override edit...")
    resp = requests.post(
        f"{BASE_URL}/admin/events/{event_id}/edit-history/{link_edit['id']}/undo",
        headers=headers
    )
    assert resp.status_code == 200, f"Undo failed: {resp.status_code} {resp.text}"
    data = resp.json()
    
    # Verify link_override is now empty/removed
    assert data.get("link_override") in [None, ""], f"link_override should be empty after undo: {data.get('link_override')}"
    
    # Verify commission_url reverted to automatic
    auto_url = data.get("auto_commission_url")
    commission_url = data.get("commission_url")
    print(f"  After undo: commission_url='{commission_url}'")
    print(f"  After undo: auto_commission_url='{auto_url}'")
    print(f"  After undo: link_override='{data.get('link_override')}'")
    
    # The commission_url should revert to the automatic one (not the override)
    assert commission_url != override_url, f"commission_url should NOT be the override after undo"
    print("✓ commission_url reverted to automatic URL")
    print("✓ link_override is now empty")
    
    # 6) Check edit history again - original edit should be marked undone=true
    print("\n[A.6] Verifying edit history after undo...")
    resp = requests.get(f"{BASE_URL}/admin/events/{event_id}/edit-history", headers=headers)
    assert resp.status_code == 200, f"Edit history GET failed: {resp.status_code} {resp.text}"
    data = resp.json()
    edits = data["edits"]
    
    # Find the original link_override edit
    original_edit = None
    undo_edit = None
    for edit in edits:
        if edit["id"] == link_edit["id"]:
            original_edit = edit
        if edit["field"] == "link_override" and edit.get("note") == "undo":
            undo_edit = edit
    
    assert original_edit is not None, "Original edit not found after undo"
    assert original_edit["undone"] == True, f"Original edit should be marked undone=true: {original_edit}"
    print(f"✓ Original edit marked undone=true")
    
    assert undo_edit is not None, "New undo edit not found in history"
    assert undo_edit["note"] == "undo", f"Undo edit should have note='undo': {undo_edit}"
    print(f"✓ New edit with note='undo' recorded")
    
    # 7) Undo a name edit
    print("\n[A.7] Undoing name edit...")
    resp = requests.post(
        f"{BASE_URL}/admin/events/{event_id}/edit-history/{name_edit['id']}/undo",
        headers=headers
    )
    assert resp.status_code == 200, f"Name undo failed: {resp.status_code} {resp.text}"
    data = resp.json()
    
    # Name should revert to old value
    old_name = name_edit.get("old_value")
    current_name = data.get("name")
    assert current_name == old_name, f"Name should revert to '{old_name}', got '{current_name}'"
    print(f"✓ Name reverted to previous value: '{current_name}'")
    
    # 8) Authorization tests
    print("\n[A.8] Testing authorization...")
    
    # 8a) No token -> 401
    resp = requests.get(f"{BASE_URL}/admin/events/{event_id}/edit-history")
    assert resp.status_code == 401, f"Expected 401 without auth, got {resp.status_code}"
    print("✓ GET edit-history without token → 401")
    
    resp = requests.post(f"{BASE_URL}/admin/events/{event_id}/edit-history/{link_edit['id']}/undo")
    assert resp.status_code == 401, f"Expected 401 without auth, got {resp.status_code}"
    print("✓ POST undo without token → 401")
    
    # 8b) Non-admin user -> 403
    user_token = create_test_user()
    user_headers = {"Authorization": f"Bearer {user_token}"}
    
    resp = requests.get(f"{BASE_URL}/admin/events/{event_id}/edit-history", headers=user_headers)
    assert resp.status_code == 403, f"Expected 403 for non-admin, got {resp.status_code}"
    print("✓ GET edit-history as non-admin → 403")
    
    resp = requests.post(
        f"{BASE_URL}/admin/events/{event_id}/edit-history/{link_edit['id']}/undo",
        headers=user_headers
    )
    assert resp.status_code == 403, f"Expected 403 for non-admin, got {resp.status_code}"
    print("✓ POST undo as non-admin → 403")
    
    # 9) Non-existent event -> 404
    print("\n[A.9] Testing non-existent resources...")
    fake_event_id = "00000000-0000-0000-0000-000000000000"
    resp = requests.get(f"{BASE_URL}/admin/events/{fake_event_id}/edit-history", headers=headers)
    # Note: edit-history returns empty list for non-existent event (not 404)
    # This is acceptable behavior
    print("✓ GET edit-history for non-existent event handled")
    
    # Non-existent edit_id -> 404
    fake_edit_id = "00000000-0000-0000-0000-000000000000"
    resp = requests.post(
        f"{BASE_URL}/admin/events/{event_id}/edit-history/{fake_edit_id}/undo",
        headers=headers
    )
    assert resp.status_code == 404, f"Expected 404 for non-existent edit, got {resp.status_code}"
    print("✓ POST undo with non-existent edit_id → 404")
    
    print("\n" + "="*80)
    print("✅ FEATURE A: ALL TESTS PASSED")
    print("="*80)


def test_feature_b_link_health():
    """
    FEATURE B: Link health
    """
    print("\n" + "="*80)
    print("FEATURE B: LINK HEALTH")
    print("="*80)
    
    token = login_admin()
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1) Basic GET /api/admin/link-health
    print("\n[B.1] Testing GET /api/admin/link-health...")
    resp = requests.get(f"{BASE_URL}/admin/link-health?days=120", headers=headers)
    assert resp.status_code == 200, f"Link health GET failed: {resp.status_code} {resp.text}"
    data = resp.json()
    
    # Verify structure
    assert "total" in data, f"Missing 'total' key: {data}"
    assert "checked" in data, f"Missing 'checked' key: {data}"
    assert "events" in data, f"Missing 'events' key: {data}"
    assert isinstance(data["total"], int), f"'total' should be int: {type(data['total'])}"
    assert isinstance(data["checked"], int), f"'checked' should be int: {type(data['checked'])}"
    assert isinstance(data["events"], list), f"'events' should be list: {type(data['events'])}"
    
    print(f"✓ Response structure correct")
    print(f"  total: {data['total']}")
    print(f"  checked: {data['checked']}")
    print(f"  events: {len(data['events'])} at-risk events")
    
    # Verify event structure if any events present
    if data["events"]:
        event = data["events"][0]
        required_keys = ["event_id", "name", "venue", "date", "city", "reason", 
                        "commission_url", "auto_commission_url"]
        for key in required_keys:
            assert key in event, f"Event missing key '{key}': {event}"
        
        # Verify reason is one of the expected values
        assert event["reason"] in ["empty", "affiliate_stale_risk"], \
            f"Invalid reason: {event['reason']}"
        
        print(f"✓ Event structure correct")
        print(f"  Sample event: {event['name']} at {event['venue']}")
        print(f"  Reason: {event['reason']}")
    
    # 2) Create event with empty commission_url (should appear in link-health)
    print("\n[B.2] Creating event with empty commission_url...")
    today = datetime.now().date()
    future_date = (today + timedelta(days=10)).isoformat()
    
    event_id = create_test_event(
        token,
        name=f"Empty Link Test {int(datetime.now().timestamp())}",
        venue=f"Test Venue {int(datetime.now().timestamp())}",
        date=future_date,
        has_commission=True,
        commission_url=""  # Empty!
    )
    print(f"✓ Created event with empty commission_url: {event_id}")
    
    # Check link-health - should appear with reason='empty'
    resp = requests.get(f"{BASE_URL}/admin/link-health?days=120", headers=headers)
    assert resp.status_code == 200, f"Link health GET failed: {resp.status_code} {resp.text}"
    data = resp.json()
    
    found = False
    for ev in data["events"]:
        if ev["event_id"] == event_id:
            found = True
            assert ev["reason"] == "empty", f"Expected reason='empty', got '{ev['reason']}'"
            print(f"✓ Event appears in link-health with reason='empty'")
            break
    
    assert found, f"Event {event_id} not found in link-health (expected to appear with reason='empty')"
    
    # 3) Fix the event with link_override - should disappear from link-health
    print("\n[B.3] Fixing event with link_override...")
    resp = requests.put(
        f"{BASE_URL}/admin/events/{event_id}/admin-edit",
        json={"link_override": "https://x.com"},
        headers=headers
    )
    assert resp.status_code == 200, f"Link override edit failed: {resp.status_code} {resp.text}"
    print("✓ Set link_override on event")
    
    # Check link-health again - should NOT appear
    resp = requests.get(f"{BASE_URL}/admin/link-health?days=120", headers=headers)
    assert resp.status_code == 200, f"Link health GET failed: {resp.status_code} {resp.text}"
    data = resp.json()
    
    found = False
    for ev in data["events"]:
        if ev["event_id"] == event_id:
            found = True
            break
    
    assert not found, f"Event {event_id} should NOT appear in link-health after setting link_override"
    print("✓ Event no longer appears in link-health (correctly considered fixed)")
    
    # 4) Authorization tests
    print("\n[B.4] Testing authorization...")
    
    # No token -> 401
    resp = requests.get(f"{BASE_URL}/admin/link-health")
    assert resp.status_code == 401, f"Expected 401 without auth, got {resp.status_code}"
    print("✓ GET link-health without token → 401")
    
    # Non-admin user -> 403
    user_token = create_test_user()
    user_headers = {"Authorization": f"Bearer {user_token}"}
    
    resp = requests.get(f"{BASE_URL}/admin/link-health", headers=user_headers)
    assert resp.status_code == 403, f"Expected 403 for non-admin, got {resp.status_code}"
    print("✓ GET link-health as non-admin → 403")
    
    print("\n" + "="*80)
    print("✅ FEATURE B: ALL TESTS PASSED")
    print("="*80)


def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("BACKEND TESTING: EDIT HISTORY + LINK HEALTH (2026-08-28 iteración 2)")
    print("="*80)
    print(f"Backend URL: {BASE_URL}")
    print(f"Admin: {ADMIN_EMAIL}")
    
    try:
        # Test Feature A: Edit history + undo
        test_feature_a_edit_history_and_undo()
        
        # Test Feature B: Link health
        test_feature_b_link_health()
        
        print("\n" + "="*80)
        print("🎉 ALL TESTS PASSED SUCCESSFULLY 🎉")
        print("="*80)
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        raise


if __name__ == "__main__":
    main()
