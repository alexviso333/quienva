#!/usr/bin/env python3
"""
Backend test for FourVenues affiliate URL rewrite functionality.
Tests that all FourVenues ticket links are rewritten to go through the 'quienva' promoter slug.
"""

import requests
import json
from datetime import datetime, timedelta

# Base URL from frontend/.env
BASE_URL = "https://admin-event-ranking.preview.emergentagent.com/api"

# Admin credentials from test_credentials.md
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

def test_fourvenues_affiliate_rewrite():
    """Test FourVenues affiliate URL rewrite through 'quienva' promoter slug."""
    
    print("\n" + "="*80)
    print("TESTING: FourVenues Affiliate URL Rewrite")
    print("="*80)
    
    # Step 1: Login as admin
    print("\n[1] Logging in as admin...")
    login_response = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert login_response.status_code == 200, f"Login failed: {login_response.status_code} {login_response.text}"
    token = login_response.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    print(f"✅ Admin login successful")
    
    # Step 2: Create an event with FourVenues commission_url
    print("\n[2] Creating event with FourVenues commission_url...")
    future_date = (datetime.now() + timedelta(days=1400)).strftime("%Y-%m-%d")  # 2030-06-06 equivalent
    
    fourvenues_url = "https://site.fourvenues.com/es/test-venue@tv/events/mi-fiesta--06-08-2026-A9XM"
    event_data = {
        "name": "Test FourVenues Event",
        "venue": "Test Venue",
        "address": "Test Address",
        "date": future_date,
        "time": "23:00",
        "city": "Palma de Mallorca",
        "has_commission": True,
        "commission_url": fourvenues_url,
        "genre": "Electrónica",
        "image_url": "https://example.com/image.jpg"
    }
    
    create_response = requests.post(
        f"{BASE_URL}/admin/events",
        json=event_data,
        headers=headers
    )
    assert create_response.status_code == 200, f"Event creation failed: {create_response.status_code} {create_response.text}"
    event = create_response.json()
    event_id = event["id"]
    print(f"✅ Event created with ID: {event_id}")
    print(f"   Original URL: {fourvenues_url}")
    
    # Step 3: GET /api/events/{id} and verify URL rewrite
    print(f"\n[3] Testing GET /api/events/{event_id}...")
    get_event_response = requests.get(
        f"{BASE_URL}/events/{event_id}",
        headers=headers
    )
    assert get_event_response.status_code == 200, f"GET event failed: {get_event_response.status_code} {get_event_response.text}"
    event_detail = get_event_response.json()
    
    expected_url = "https://www.fourvenues.com/quienva/events/mi-fiesta--06-08-2026-A9XM"
    actual_url = event_detail.get("commission_url", "")
    
    print(f"   Expected URL: {expected_url}")
    print(f"   Actual URL:   {actual_url}")
    
    assert actual_url == expected_url, f"❌ URL rewrite failed! Expected '{expected_url}' but got '{actual_url}'"
    print(f"✅ GET /api/events/{event_id} - URL correctly rewritten to 'quienva' slug")
    
    # Verify query and hash are stripped
    assert "?" not in actual_url, "❌ Query parameters should be stripped"
    assert "#" not in actual_url, "❌ Hash fragments should be stripped"
    assert actual_url.startswith("https://www.fourvenues.com/"), "❌ Base should be www.fourvenues.com"
    print(f"✅ Query/hash stripped, base is www.fourvenues.com")
    
    # Step 4: GET /api/events?date_filter=all and verify URL in list
    print(f"\n[4] Testing GET /api/events?date_filter=all...")
    list_events_response = requests.get(
        f"{BASE_URL}/events?date_filter=all",
        headers=headers
    )
    assert list_events_response.status_code == 200, f"GET events list failed: {list_events_response.status_code} {list_events_response.text}"
    events_list = list_events_response.json()
    
    # Find our event in the list
    found_event = None
    for ev in events_list:
        if ev["id"] == event_id:
            found_event = ev
            break
    
    assert found_event is not None, f"❌ Event {event_id} not found in events list"
    list_url = found_event.get("commission_url", "")
    
    print(f"   Expected URL: {expected_url}")
    print(f"   Actual URL:   {list_url}")
    
    assert list_url == expected_url, f"❌ URL rewrite failed in list! Expected '{expected_url}' but got '{list_url}'"
    print(f"✅ GET /api/events - URL correctly rewritten in list")
    
    # Step 5: Create event with NON-FourVenues URL and verify it's unchanged
    print(f"\n[5] Creating event with NON-FourVenues commission_url...")
    xceed_url = "https://xceed.me/es/palma/event/test/123"
    event_data_2 = {
        "name": "Test Xceed Event",
        "venue": "Test Venue 2",
        "address": "Test Address 2",
        "date": future_date,
        "time": "23:00",
        "city": "Palma de Mallorca",
        "has_commission": True,
        "commission_url": xceed_url,
        "genre": "Reggaeton",
        "image_url": "https://example.com/image2.jpg"
    }
    
    create_response_2 = requests.post(
        f"{BASE_URL}/admin/events",
        json=event_data_2,
        headers=headers
    )
    assert create_response_2.status_code == 200, f"Event 2 creation failed: {create_response_2.status_code} {create_response_2.text}"
    event_2 = create_response_2.json()
    event_id_2 = event_2["id"]
    print(f"✅ Event 2 created with ID: {event_id_2}")
    print(f"   Original URL: {xceed_url}")
    
    # GET the non-FourVenues event and verify URL is UNCHANGED
    print(f"\n[6] Testing GET /api/events/{event_id_2} (non-FourVenues)...")
    get_event_2_response = requests.get(
        f"{BASE_URL}/events/{event_id_2}",
        headers=headers
    )
    assert get_event_2_response.status_code == 200, f"GET event 2 failed: {get_event_2_response.status_code} {get_event_2_response.text}"
    event_2_detail = get_event_2_response.json()
    
    actual_url_2 = event_2_detail.get("commission_url", "")
    
    print(f"   Expected URL: {xceed_url} (unchanged)")
    print(f"   Actual URL:   {actual_url_2}")
    
    assert actual_url_2 == xceed_url, f"❌ Non-FourVenues URL should be unchanged! Expected '{xceed_url}' but got '{actual_url_2}'"
    assert actual_url_2.startswith("https://xceed.me/"), "❌ Non-FourVenues URL should remain xceed.me"
    print(f"✅ Non-FourVenues URL correctly left unchanged")
    
    # Cleanup: Delete test events
    print(f"\n[7] Cleaning up test events...")
    delete_1 = requests.delete(f"{BASE_URL}/admin/events/{event_id}", headers=headers)
    delete_2 = requests.delete(f"{BASE_URL}/admin/events/{event_id_2}", headers=headers)
    print(f"✅ Test events deleted")
    
    print("\n" + "="*80)
    print("✅ ALL TESTS PASSED - FourVenues affiliate URL rewrite working correctly!")
    print("="*80)
    print("\nSummary:")
    print("  ✅ FourVenues URLs rewritten to 'quienva' promoter slug")
    print("  ✅ Query parameters and hash fragments stripped")
    print("  ✅ Base URL normalized to www.fourvenues.com")
    print("  ✅ Non-FourVenues URLs left unchanged")
    print("  ✅ Rewrite works in both GET /events/{id} and GET /events list")
    print("="*80 + "\n")

if __name__ == "__main__":
    try:
        test_fourvenues_affiliate_rewrite()
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n")
        exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        exit(1)
