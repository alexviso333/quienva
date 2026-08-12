#!/usr/bin/env python3
"""
Test Wrapped feature in FRESH LOCAL environment (empty MongoDB, NO FourVenues token).
System current month is 2026-08, so previous month is 2026-07.

Admin: admin@quienva.app / admin123
"""

import requests
import json
import io
from datetime import datetime

# Backend URL from frontend/.env
BASE_URL = "https://ticket-matcher-5.preview.emergentagent.com/api"

def log(msg):
    print(f"[TEST] {msg}")

def admin_login():
    """Login as admin and return token"""
    log("Logging in as admin...")
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "admin@quienva.app",
        "password": "admin123"
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.status_code} {resp.text}"
    data = resp.json()
    assert "token" in data, "No token in login response"
    log(f"✓ Admin login successful")
    return data["token"]

def register_user(username, email, password, city="Palma de Mallorca"):
    """Register a new user and return token"""
    log(f"Registering user {username}...")
    resp = requests.post(f"{BASE_URL}/auth/register", json={
        "email": email,
        "username": username,
        "password": password,
        "name": f"User {username}",
        "birthdate": "1990-01-01",  # Adult birthdate
        "city": city
    })
    assert resp.status_code == 200, f"User registration failed: {resp.status_code} {resp.text}"
    data = resp.json()
    assert "token" in data, "No token in registration response"
    log(f"✓ User {username} registered")
    return data["token"]

def create_event(admin_token, name, date, venue, genre):
    """Create an event as admin and return event_id"""
    log(f"Creating event '{name}' on {date}...")
    resp = requests.post(f"{BASE_URL}/admin/events", 
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "name": name,
            "date": date,
            "time": "23:00",
            "venue": venue,
            "city": "Palma de Mallorca",
            "genre": genre,
            "image_url": "https://example.com/poster.jpg",
            "description": "Test event"
        })
    assert resp.status_code == 200, f"Event creation failed: {resp.status_code} {resp.text}"
    data = resp.json()
    event_id = data.get("id") or data.get("event_id")
    assert event_id, f"No event_id in response: {data}"
    log(f"✓ Event created: {event_id}")
    return event_id

def mark_interest(user_token, event_id, status):
    """Mark interest on an event"""
    log(f"Marking interest '{status}' on event {event_id}...")
    resp = requests.post(f"{BASE_URL}/events/{event_id}/interest",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"status": status})
    assert resp.status_code == 200, f"Mark interest failed: {resp.status_code} {resp.text}"
    log(f"✓ Interest marked: {status}")

def upload_album_photo(user_token, event_id):
    """Upload a photo to event album"""
    log(f"Uploading album photo to event {event_id}...")
    # Create a small test image (1x1 pixel PNG)
    img_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
    
    files = {'file': ('test.png', io.BytesIO(img_data), 'image/png')}
    resp = requests.post(f"{BASE_URL}/events/{event_id}/album/upload",
        headers={"Authorization": f"Bearer {user_token}"},
        files=files)
    assert resp.status_code == 200, f"Album upload failed: {resp.status_code} {resp.text}"
    log(f"✓ Album photo uploaded")

def trigger_moment(admin_token, event_id):
    """Trigger El Momento for an event"""
    log(f"Triggering moment for event {event_id}...")
    resp = requests.post(f"{BASE_URL}/admin/events/{event_id}/moment/trigger",
        headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200, f"Moment trigger failed: {resp.status_code} {resp.text}"
    log(f"✓ Moment triggered")

def upload_moment(user_token, event_id):
    """Upload a moment capture"""
    log(f"Uploading moment capture to event {event_id}...")
    # Create a small test image (1x1 pixel PNG)
    img_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
    
    files = {'file': ('moment.png', io.BytesIO(img_data), 'image/png')}
    resp = requests.post(f"{BASE_URL}/events/{event_id}/moment/upload",
        headers={"Authorization": f"Bearer {user_token}"},
        files=files)
    assert resp.status_code == 200, f"Moment upload failed: {resp.status_code} {resp.text}"
    log(f"✓ Moment uploaded")

def get_wrapped(user_token, month=None):
    """Get wrapped data"""
    url = f"{BASE_URL}/me/wrapped"
    if month:
        url += f"?month={month}"
    log(f"Getting wrapped data (month={month or 'default'})...")
    resp = requests.get(url, headers={"Authorization": f"Bearer {user_token}"})
    assert resp.status_code == 200, f"Get wrapped failed: {resp.status_code} {resp.text}"
    data = resp.json()
    log(f"✓ Wrapped data retrieved")
    return data

def get_wrapped_year(user_token, year=None):
    """Get wrapped year data"""
    url = f"{BASE_URL}/me/wrapped/year"
    if year:
        url += f"?year={year}"
    log(f"Getting wrapped year data (year={year or 'default'})...")
    resp = requests.get(url, headers={"Authorization": f"Bearer {user_token}"})
    assert resp.status_code == 200, f"Get wrapped year failed: {resp.status_code} {resp.text}"
    data = resp.json()
    log(f"✓ Wrapped year data retrieved")
    return data

def main():
    print("=" * 80)
    print("WRAPPED FEATURE TESTING - FRESH LOCAL ENVIRONMENT")
    print("System current month: 2026-08, previous month: 2026-07")
    print("=" * 80)
    print()
    
    # SEED PHASE
    print("SEED PHASE: Creating events and data")
    print("-" * 80)
    
    # Step 1: Login admin
    admin_token = admin_login()
    
    # Step 2: Create events
    # evJul1: date 2026-07-12, venue "Sala J", genre "Reggaeton"
    evJul1 = create_event(admin_token, "Fiesta Reggaeton Julio 1", "2026-07-12", "Sala J", "Reggaeton")
    
    # evJul2: date 2026-07-20, venue "Sala K", genre "Techno"
    evJul2 = create_event(admin_token, "Fiesta Techno Julio 2", "2026-07-20", "Sala K", "Techno")
    
    # evAug: date 2026-08-05, venue "Sala A", genre "House"
    evAug = create_event(admin_token, "Fiesta House Agosto", "2026-08-05", "Sala A", "House")
    
    # Step 3: Register user U1
    u1_token = register_user("u1test", "u1test@example.com", "password123")
    
    # Step 4: U1 marks interest on all 3 events
    mark_interest(u1_token, evJul1, "estuve")
    mark_interest(u1_token, evJul2, "estuve")
    mark_interest(u1_token, evAug, "estuve")
    
    # Step 5: U1 uploads 1 photo to evJul1
    upload_album_photo(u1_token, evJul1)
    
    # Step 6: Admin triggers moment for evJul1, U1 uploads moment
    trigger_moment(admin_token, evJul1)
    upload_moment(u1_token, evJul1)
    
    print()
    print("SEED COMPLETE")
    print("=" * 80)
    print()
    
    # VERIFICATION PHASE
    print("VERIFICATION PHASE: Testing Wrapped endpoints")
    print("-" * 80)
    
    # Test 5: GET /api/me/wrapped (NO month param) -> should return July data
    print("\n[TEST 5] GET /api/me/wrapped (default - should be July 2026)")
    wrapped_default = get_wrapped(u1_token)
    
    print(f"  month: {wrapped_default.get('month')}")
    print(f"  has_data: {wrapped_default.get('has_data')}")
    print(f"  parties: {wrapped_default.get('parties')}")
    print(f"  photos: {wrapped_default.get('photos')}")
    print(f"  moments: {wrapped_default.get('moments')}")
    print(f"  gallery length: {len(wrapped_default.get('gallery', []))}")
    
    # Assertions for Test 5
    assert wrapped_default.get('month') == '2026-07', f"Expected month='2026-07', got '{wrapped_default.get('month')}'"
    assert wrapped_default.get('has_data') == True, f"Expected has_data=true, got {wrapped_default.get('has_data')}"
    assert wrapped_default.get('parties') == 2, f"Expected parties=2 (only July events), got {wrapped_default.get('parties')}"
    assert wrapped_default.get('photos') >= 1, f"Expected photos>=1, got {wrapped_default.get('photos')}"
    assert wrapped_default.get('moments') >= 1, f"Expected moments>=1, got {wrapped_default.get('moments')}"
    
    # Check gallery
    gallery = wrapped_default.get('gallery', [])
    assert len(gallery) >= 2, f"Expected gallery length>=2, got {len(gallery)}"
    
    # Verify each gallery item has url and kind
    for item in gallery:
        assert 'url' in item and item['url'], f"Gallery item missing non-empty 'url': {item}"
        assert 'kind' in item and item['kind'] in ['photo', 'moment'], f"Gallery item has invalid 'kind': {item}"
    
    # Verify at least one photo and one moment in gallery
    photo_count = sum(1 for item in gallery if item.get('kind') == 'photo')
    moment_count = sum(1 for item in gallery if item.get('kind') == 'moment')
    assert photo_count >= 1, f"Expected at least 1 photo in gallery, got {photo_count}"
    assert moment_count >= 1, f"Expected at least 1 moment in gallery, got {moment_count}"
    
    print("  ✓ All assertions passed for default wrapped (July)")
    
    # Test 6: GET /api/me/wrapped?month=2026-08 -> should return August data
    print("\n[TEST 6] GET /api/me/wrapped?month=2026-08 (August)")
    wrapped_aug = get_wrapped(u1_token, "2026-08")
    
    print(f"  month: {wrapped_aug.get('month')}")
    print(f"  parties: {wrapped_aug.get('parties')}")
    
    assert wrapped_aug.get('month') == '2026-08', f"Expected month='2026-08', got '{wrapped_aug.get('month')}'"
    assert wrapped_aug.get('parties') == 1, f"Expected parties=1 (only August event), got {wrapped_aug.get('parties')}"
    
    print("  ✓ All assertions passed for August wrapped")
    
    # Test 7: GET /api/me/wrapped/year?year=2026 -> should return full year data
    print("\n[TEST 7] GET /api/me/wrapped/year?year=2026 (Full year)")
    wrapped_year = get_wrapped_year(u1_token, "2026")
    
    print(f"  year: {wrapped_year.get('year')}")
    print(f"  parties: {wrapped_year.get('parties')}")
    print(f"  gallery length: {len(wrapped_year.get('gallery', []))}")
    
    assert wrapped_year.get('parties') == 3, f"Expected parties=3 (all events), got {wrapped_year.get('parties')}"
    assert 'gallery' in wrapped_year, "Expected 'gallery' field in year wrapped"
    assert isinstance(wrapped_year.get('gallery'), list), "Expected 'gallery' to be a list"
    
    print("  ✓ All assertions passed for year wrapped")
    
    print()
    print("=" * 80)
    print("ALL TESTS PASSED ✓")
    print("=" * 80)
    print()
    print("SUMMARY:")
    print(f"  ✓ Test 5: Default wrapped returns July 2026 (previous month)")
    print(f"  ✓ Test 5: has_data=true, parties=2 (only July events)")
    print(f"  ✓ Test 5: photos>=1, moments>=1 (counted by event, not upload date)")
    print(f"  ✓ Test 5: gallery has >=2 items with url and kind fields")
    print(f"  ✓ Test 5: gallery has at least 1 photo and 1 moment")
    print(f"  ✓ Test 6: August wrapped returns parties=1 (only August event)")
    print(f"  ✓ Test 7: Year wrapped returns parties=3 (all events)")
    print(f"  ✓ Test 7: Year wrapped has gallery field (list)")
    print()
    print("CRITICAL VERIFICATION:")
    print("  Photos and moments uploaded 'now' (August) are correctly counted")
    print("  toward JULY because media is counted by EVENT, not upload date.")
    print()

if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print()
        print("=" * 80)
        print("TEST FAILED ✗")
        print("=" * 80)
        print(f"Error: {e}")
        print()
        exit(1)
    except Exception as e:
        print()
        print("=" * 80)
        print("TEST ERROR ✗")
        print("=" * 80)
        print(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        print()
        exit(1)
