#!/usr/bin/env python3
"""
Backend test for BUG FIX: cleanup_old_events preserves memories (recuerdos)

BUG: Past parties ("Recuerdos"/"Fiestas pasadas") disappeared ~3 days after the event 
because cleanup_old_events deleted every event with date < today-3days, including ones 
the user attended (plus their album/moment).

FIX: cleanup now PRESERVES any event that is a memory (someone with interest voy/estuve, 
OR any album_uploads photo, OR any moment capture in `captures`), and only deletes old 
events with NO engagement.

NEW ENDPOINT: POST /api/admin/maintenance/cleanup-old-events
"""

import requests
import json
from datetime import datetime, timedelta
import os
import sys

# Get backend URL from environment
BACKEND_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001")
API_BASE = f"{BACKEND_URL}/api"

# Test credentials from memory/test_credentials.md
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

# Test state
admin_token = None
user1_token = None
user2_token = None
event_a_id = None
event_b_id = None
event_c_id = None
user1_id = None
user2_id = None

def log(msg):
    """Print test log message"""
    print(f"[TEST] {msg}")

def login_admin():
    """Login as admin and get token"""
    global admin_token
    log("Logging in as admin...")
    resp = requests.post(f"{API_BASE}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.status_code} {resp.text}"
    data = resp.json()
    admin_token = data["token"]
    log(f"✅ Admin login successful, token: {admin_token[:20]}...")
    return admin_token

def register_user(name, email, username):
    """Register a new user and return token"""
    log(f"Registering user {username}...")
    resp = requests.post(f"{API_BASE}/auth/register", json={
        "name": name,
        "email": email,
        "username": username,
        "password": "test123",
        "birthdate": "1990-01-01",
        "city": "Palma de Mallorca"
    })
    assert resp.status_code == 200, f"User registration failed: {resp.status_code} {resp.text}"
    data = resp.json()
    token = data["token"]
    user_id = data["user"]["user_id"]
    log(f"✅ User {username} registered, user_id: {user_id}")
    return token, user_id

def create_old_event(name, days_ago=10):
    """Create an event with an OLD date (past the 3-day cutoff)"""
    global admin_token
    old_date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
    log(f"Creating event '{name}' with old date {old_date}...")
    
    resp = requests.post(f"{API_BASE}/admin/events", 
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "name": name,
            "venue": f"Test Venue {name}",
            "city": "Palma de Mallorca",
            "date": old_date,
            "time": "23:00",
            "genre": "Electrónica",
            "image_url": "https://example.com/test.jpg",
            "description": f"Test event {name}",
            "has_commission": False
        }
    )
    assert resp.status_code == 200, f"Event creation failed: {resp.status_code} {resp.text}"
    data = resp.json()
    event_id = data["id"]
    log(f"✅ Event '{name}' created with id: {event_id}, date: {old_date}")
    return event_id

def mark_interest(event_id, token, status="estuve"):
    """Mark interest on an event"""
    log(f"Marking interest '{status}' on event {event_id}...")
    resp = requests.post(f"{API_BASE}/events/{event_id}/interest",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": status}
    )
    assert resp.status_code == 200, f"Mark interest failed: {resp.status_code} {resp.text}"
    log(f"✅ Interest '{status}' marked on event {event_id}")

def trigger_moment(event_id):
    """Admin triggers moment for an event"""
    global admin_token
    log(f"Triggering moment for event {event_id}...")
    resp = requests.post(f"{API_BASE}/admin/events/{event_id}/moment/trigger",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert resp.status_code == 200, f"Trigger moment failed: {resp.status_code} {resp.text}"
    log(f"✅ Moment triggered for event {event_id}")

def upload_moment(event_id, token):
    """Upload a moment capture for an event"""
    log(f"Uploading moment capture for event {event_id}...")
    
    # Create a simple 1x1 pixel JPEG image
    import io
    from PIL import Image
    img = Image.new('RGB', (1, 1), color='red')
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='JPEG')
    img_bytes.seek(0)
    
    resp = requests.post(f"{API_BASE}/events/{event_id}/moment/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("test.jpg", img_bytes, "image/jpeg")}
    )
    assert resp.status_code == 200, f"Upload moment failed: {resp.status_code} {resp.text}"
    data = resp.json()
    log(f"✅ Moment uploaded for event {event_id}, capture_id: {data.get('id')}")
    return data

def cleanup_old_events():
    """Run the cleanup endpoint"""
    global admin_token
    log("Running cleanup_old_events...")
    resp = requests.post(f"{API_BASE}/admin/maintenance/cleanup-old-events",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert resp.status_code == 200, f"Cleanup failed: {resp.status_code} {resp.text}"
    data = resp.json()
    log(f"✅ Cleanup complete: deleted={data['deleted']}, kept={data['kept']}, old_total={data['old_total']}")
    return data

def get_event(event_id, token=None):
    """Get event by ID"""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    resp = requests.get(f"{API_BASE}/events/{event_id}", headers=headers)
    return resp

def get_past_events(token):
    """Get user's past events"""
    resp = requests.get(f"{API_BASE}/me/past-events",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200, f"Get past events failed: {resp.status_code} {resp.text}"
    return resp.json()

def get_moment_status(event_id, token):
    """Get moment status for an event"""
    resp = requests.get(f"{API_BASE}/events/{event_id}/moment/status",
        headers={"Authorization": f"Bearer {token}"}
    )
    return resp

def get_moment_gallery(event_id, token):
    """Get moment gallery for an event"""
    resp = requests.get(f"{API_BASE}/events/{event_id}/moment/gallery",
        headers={"Authorization": f"Bearer {token}"}
    )
    return resp

# ============================================================================
# TEST 1: Attended past event is preserved; unengaged old event is deleted
# ============================================================================
def test_1_attended_event_preserved():
    global admin_token, user1_token, user1_id, event_a_id, event_b_id
    
    log("\n" + "="*80)
    log("TEST 1: Attended past event is preserved; unengaged old event is deleted")
    log("="*80)
    
    # 1. Login admin
    admin_token = login_admin()
    
    # 2. Create event A with OLD date (~10 days ago)
    event_a_id = create_old_event("Event A - Attended", days_ago=10)
    
    # 3. Create event B with OLD date (no engagement)
    event_b_id = create_old_event("Event B - Unengaged", days_ago=10)
    
    # 4. Register/login normal user U1
    user1_token, user1_id = register_user("User One", "user1@test.com", "user1test")
    
    # 5. As U1: mark 'estuve' on event A
    mark_interest(event_a_id, user1_token, "estuve")
    
    # 6. As admin: run cleanup
    cleanup_result = cleanup_old_events()
    
    # Verify cleanup results
    assert cleanup_result["kept"] >= 1, f"Expected kept >= 1, got {cleanup_result['kept']}"
    assert cleanup_result["deleted"] >= 1, f"Expected deleted >= 1, got {cleanup_result['deleted']}"
    log(f"✅ Cleanup results: deleted={cleanup_result['deleted']}, kept={cleanup_result['kept']}")
    
    # 7. Verify event A still exists (200)
    resp_a = get_event(event_a_id, user1_token)
    assert resp_a.status_code == 200, f"Event A should exist (200), got {resp_a.status_code}"
    log(f"✅ Event A still exists (preserved as memory)")
    
    # 8. Verify event B was deleted (404)
    resp_b = get_event(event_b_id, user1_token)
    assert resp_b.status_code == 404, f"Event B should be deleted (404), got {resp_b.status_code}"
    log(f"✅ Event B was deleted (no engagement)")
    
    # 9. As U1: GET /me/past-events should include event A
    past_events = get_past_events(user1_token)
    event_ids = [e["id"] for e in past_events["items"]]
    assert event_a_id in event_ids, f"Event A should be in past-events, got: {event_ids}"
    log(f"✅ Event A appears in /me/past-events")
    
    log("\n✅ TEST 1 PASSED: Attended event preserved, unengaged event deleted")

# ============================================================================
# TEST 2: A moment capture also preserves the event (even with no interest)
# ============================================================================
def test_2_moment_preserves_event():
    global admin_token, user2_token, user2_id, event_c_id
    
    log("\n" + "="*80)
    log("TEST 2: A moment capture also preserves the event (even with no interest)")
    log("="*80)
    
    # 1. Create event C with OLD date
    event_c_id = create_old_event("Event C - Moment Only", days_ago=10)
    
    # 2. As admin: trigger moment for event C
    trigger_moment(event_c_id)
    
    # 3. Register/login user U2
    user2_token, user2_id = register_user("User Two", "user2@test.com", "user2test")
    
    # 4. As U2: mark interest 'voy' on event C (required to upload moment)
    mark_interest(event_c_id, user2_token, "voy")
    
    # 5. As U2: upload moment capture
    upload_moment(event_c_id, user2_token)
    
    # 6. As U2: remove interest (to test that moment alone preserves)
    mark_interest(event_c_id, user2_token, "none")
    
    # 7. As admin: run cleanup
    cleanup_result = cleanup_old_events()
    log(f"Cleanup results: deleted={cleanup_result['deleted']}, kept={cleanup_result['kept']}")
    
    # 8. Verify event C still exists (preserved by moment capture)
    resp_c = get_event(event_c_id, user2_token)
    assert resp_c.status_code == 200, f"Event C should exist (200), got {resp_c.status_code}"
    log(f"✅ Event C still exists (preserved by moment capture, even without interest)")
    
    log("\n✅ TEST 2 PASSED: Moment capture preserves event even without interest")

# ============================================================================
# TEST 3: Moment is retrievable for a PAST event (memory)
# ============================================================================
def test_3_moment_retrievable_for_past_event():
    global user2_token, event_c_id
    
    log("\n" + "="*80)
    log("TEST 3: Moment is retrievable for a PAST event (memory)")
    log("="*80)
    
    # 1. As U2: GET moment status for event C
    resp_status = get_moment_status(event_c_id, user2_token)
    assert resp_status.status_code == 200, f"Moment status failed: {resp_status.status_code}"
    status_data = resp_status.json()
    assert status_data["my_capture"] is not None, "my_capture should not be null"
    log(f"✅ Moment status retrieved, my_capture exists")
    
    # 2. As U2: GET moment gallery for event C
    resp_gallery = get_moment_gallery(event_c_id, user2_token)
    assert resp_gallery.status_code == 200, f"Moment gallery failed: {resp_gallery.status_code}"
    gallery_data = resp_gallery.json()
    assert len(gallery_data) > 0, "Gallery should have at least 1 capture"
    
    # Verify U2's capture is in the gallery
    user2_captures = [c for c in gallery_data if c["user_id"] == user2_id]
    assert len(user2_captures) > 0, "U2's capture should be in gallery"
    log(f"✅ Moment gallery retrieved with {len(gallery_data)} capture(s), U2's capture present")
    
    log("\n✅ TEST 3 PASSED: Moment is retrievable for past event")

# ============================================================================
# TEST 4: Stability regression - past events stay present
# ============================================================================
def test_4_stability_regression():
    global user1_token, event_a_id
    
    log("\n" + "="*80)
    log("TEST 4: Stability regression - past events stay present")
    log("="*80)
    
    # Call GET /me/past-events multiple times
    for i in range(5):
        past_events = get_past_events(user1_token)
        event_ids = [e["id"] for e in past_events["items"]]
        assert event_a_id in event_ids, f"Event A should be in past-events (attempt {i+1})"
        log(f"  Attempt {i+1}: Event A present in past-events ✓")
    
    # Call GET /events/{A} multiple times
    for i in range(5):
        resp_a = get_event(event_a_id, user1_token)
        assert resp_a.status_code == 200, f"Event A should exist (attempt {i+1})"
        log(f"  Attempt {i+1}: Event A exists (200) ✓")
    
    log(f"✅ Event A is stable across 10 API calls (5 past-events + 5 single event)")
    
    log("\n✅ TEST 4 PASSED: Past events remain stable and don't disappear")

# ============================================================================
# Main test runner
# ============================================================================
def main():
    log("\n" + "="*80)
    log("BACKEND TEST: cleanup_old_events preserves memories (recuerdos)")
    log("="*80)
    log(f"Backend URL: {API_BASE}")
    log(f"Admin credentials: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    
    try:
        # Run all tests in sequence
        test_1_attended_event_preserved()
        test_2_moment_preserves_event()
        test_3_moment_retrievable_for_past_event()
        test_4_stability_regression()
        
        log("\n" + "="*80)
        log("🎉 ALL TESTS PASSED (4/4)")
        log("="*80)
        log("\nSUMMARY:")
        log("✅ TEST 1: Attended event preserved, unengaged event deleted")
        log("✅ TEST 2: Moment capture preserves event even without interest")
        log("✅ TEST 3: Moment is retrievable for past event")
        log("✅ TEST 4: Past events remain stable and don't disappear")
        log("\n🎯 CONCLUSION:")
        log("The cleanup_old_events bug fix is working perfectly. Past parties (recuerdos)")
        log("are preserved when users have attended (voy/estuve) or uploaded moments/photos.")
        log("Unengaged old events are correctly deleted. The /me/past-events endpoint")
        log("returns stable results and moments are retrievable for past events.")
        
        return 0
        
    except AssertionError as e:
        log(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        log(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
