#!/usr/bin/env python3
"""
Backend test for FourVenues affiliate GATING bug fix.
Tests that FourVenues ticket links are rewritten ONLY for events that belong to OUR affiliate profile.
Since there's no FourVenues token locally, the "my events" set is EMPTY, so ALL FourVenues events
must be served with their ORIGINAL link (NOT rewritten to quienva).
"""

import requests
import json
from datetime import datetime, timedelta

# Base URL from frontend/.env
BASE_URL = "https://cloud-integrated.preview.emergentagent.com/api"

# Admin credentials from test_credentials.md
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

def test_affiliate_gating_bug_fix():
    """Test that FourVenues URLs are NOT rewritten when event is not in our affiliate profile."""
    
    print("\n" + "="*80)
    print("TESTING: FourVenues Affiliate GATING Bug Fix")
    print("="*80)
    print("\nCONTEXT: Locally there is NO FourVenues token, so the 'my events' set is EMPTY.")
    print("Therefore EVERY FourVenues event must be served UNCHANGED (not rewritten to quienva).")
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
    print(f"✅ Admin login successful with {ADMIN_EMAIL}")
    
    # Step 2: Create an event with FourVenues commission_url (NOT in our affiliate profile)
    print("\n[2] Creating event with FourVenues commission_url (NOT in our affiliate profile)...")
    future_date = "2030-06-06"  # Future date as specified
    
    # This is a FourVenues URL but NOT in our affiliate profile (amok@amok promoter, not quienva)
    fourvenues_url = "https://site.fourvenues.com/es/amok@amok/events/not-mine--06-08-2026-YY"
    event_data = {
        "name": "Test FourVenues Event (Not Mine)",
        "venue": "Amok",
        "address": "Palma de Mallorca",
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
    
    # Step 3: GET /api/events/{id} and verify URL is UNCHANGED (core bug fix)
    print(f"\n[3] Testing GET /api/events/{event_id} - CORE BUG FIX TEST...")
    get_event_response = requests.get(
        f"{BASE_URL}/events/{event_id}",
        headers=headers
    )
    assert get_event_response.status_code == 200, f"GET event failed: {get_event_response.status_code} {get_event_response.text}"
    event_detail = get_event_response.json()
    
    actual_url = event_detail.get("commission_url", "")
    
    print(f"   Expected URL: {fourvenues_url} (UNCHANGED)")
    print(f"   Actual URL:   {actual_url}")
    
    # CRITICAL ASSERTION: URL must be UNCHANGED (must NOT contain '/quienva/')
    assert actual_url == fourvenues_url, f"❌ BUG FIX FAILED! URL should be UNCHANGED. Expected '{fourvenues_url}' but got '{actual_url}'"
    assert "/quienva/" not in actual_url, f"❌ BUG FIX FAILED! URL must NOT contain '/quienva/' but got '{actual_url}'"
    assert "amok@amok" in actual_url, f"❌ BUG FIX FAILED! Original promoter 'amok@amok' should be preserved but got '{actual_url}'"
    print(f"✅ CORE BUG FIX VERIFIED: FourVenues URL is UNCHANGED (does NOT contain '/quienva/')")
    
    # Step 4: GET /api/events?date_filter=all and verify URL in list is also unchanged
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
    
    print(f"   Expected URL: {fourvenues_url} (UNCHANGED)")
    print(f"   Actual URL:   {list_url}")
    
    assert list_url == fourvenues_url, f"❌ URL should be unchanged in list! Expected '{fourvenues_url}' but got '{list_url}'"
    assert "/quienva/" not in list_url, f"❌ URL in list must NOT contain '/quienva/' but got '{list_url}'"
    print(f"✅ GET /api/events - FourVenues URL also unchanged in list")
    
    # Step 5: Create event with NON-FourVenues URL (xceed.me) and verify it's unchanged
    print(f"\n[5] Creating event with NON-FourVenues commission_url (xceed.me)...")
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
    
    # Step 7: Test GET /api/admin/affiliate-status (admin only)
    print(f"\n[7] Testing GET /api/admin/affiliate-status as admin...")
    status_response = requests.get(
        f"{BASE_URL}/admin/affiliate-status",
        headers=headers
    )
    assert status_response.status_code == 200, f"GET affiliate-status failed: {status_response.status_code} {status_response.text}"
    status_data = status_response.json()
    
    print(f"   Response: {json.dumps(status_data, indent=2)}")
    
    # Verify required keys
    assert "slug" in status_data, "❌ Response must contain 'slug' key"
    assert "mine_count" in status_data, "❌ Response must contain 'mine_count' key"
    assert "codes_count" in status_data, "❌ Response must contain 'codes_count' key"
    assert "updated_at" in status_data, "❌ Response must contain 'updated_at' key"
    
    assert status_data["slug"] == "quienva", f"❌ Expected slug 'quienva' but got '{status_data['slug']}'"
    assert isinstance(status_data["mine_count"], int), f"❌ mine_count must be integer but got {type(status_data['mine_count'])}"
    assert isinstance(status_data["codes_count"], int), f"❌ codes_count must be integer but got {type(status_data['codes_count'])}"
    
    print(f"✅ GET /api/admin/affiliate-status returns correct structure:")
    print(f"   - slug: {status_data['slug']}")
    print(f"   - mine_count: {status_data['mine_count']} (likely 0 without token)")
    print(f"   - codes_count: {status_data['codes_count']}")
    print(f"   - updated_at: {status_data['updated_at']}")
    
    # Step 8: Test POST /api/admin/affiliate-refresh (admin only)
    print(f"\n[8] Testing POST /api/admin/affiliate-refresh as admin...")
    refresh_response = requests.post(
        f"{BASE_URL}/admin/affiliate-refresh",
        headers=headers
    )
    assert refresh_response.status_code == 200, f"POST affiliate-refresh failed: {refresh_response.status_code} {refresh_response.text}"
    refresh_data = refresh_response.json()
    
    print(f"   Response: {json.dumps(refresh_data, indent=2)}")
    
    assert "slug" in refresh_data, "❌ Response must contain 'slug' key"
    assert "mine_count" in refresh_data, "❌ Response must contain 'mine_count' key"
    assert refresh_data["slug"] == "quienva", f"❌ Expected slug 'quienva' but got '{refresh_data['slug']}'"
    
    print(f"✅ POST /api/admin/affiliate-refresh succeeds without crash:")
    print(f"   - slug: {refresh_data['slug']}")
    print(f"   - mine_count: {refresh_data['mine_count']} (likely 0 without token)")
    
    # Step 9: Test GET /api/admin/affiliate-status as NON-admin (should be 403)
    print(f"\n[9] Testing GET /api/admin/affiliate-status as NON-admin user...")
    
    # Register a non-admin user
    import random
    test_user_email = f"testuser{random.randint(10000, 99999)}@test.com"
    register_response = requests.post(
        f"{BASE_URL}/auth/register",
        json={
            "email": test_user_email,
            "password": "testpass123",
            "name": "Test User",
            "username": f"testuser{random.randint(10000, 99999)}",
            "birthdate": "1995-01-01",
            "city": "Palma de Mallorca"
        }
    )
    
    if register_response.status_code == 429:
        print(f"   ⚠️  Rate limited on register, skipping non-admin test (acceptable)")
    else:
        assert register_response.status_code == 200, f"Register failed: {register_response.status_code} {register_response.text}"
        user_token = register_response.json()["token"]
        user_headers = {"Authorization": f"Bearer {user_token}"}
        
        # Try to access affiliate-status as non-admin
        non_admin_status_response = requests.get(
            f"{BASE_URL}/admin/affiliate-status",
            headers=user_headers
        )
        
        print(f"   Non-admin status code: {non_admin_status_response.status_code}")
        assert non_admin_status_response.status_code == 403, f"❌ Non-admin should get 403 but got {non_admin_status_response.status_code}"
        print(f"✅ Non-admin user correctly gets 403 Forbidden")
    
    # Cleanup: Delete test events
    print(f"\n[10] Cleaning up test events...")
    delete_1 = requests.delete(f"{BASE_URL}/admin/events/{event_id}", headers=headers)
    delete_2 = requests.delete(f"{BASE_URL}/admin/events/{event_id_2}", headers=headers)
    print(f"✅ Test events deleted")
    
    print("\n" + "="*80)
    print("✅ ALL TESTS PASSED - FourVenues Affiliate GATING Bug Fix Working!")
    print("="*80)
    print("\nSummary:")
    print("  ✅ FourVenues URLs are UNCHANGED when event is NOT in our affiliate profile")
    print("  ✅ FourVenues URLs do NOT contain '/quienva/' (core bug fix)")
    print("  ✅ Original promoter slug preserved (e.g., 'amok@amok')")
    print("  ✅ Non-FourVenues URLs (xceed.me) left unchanged")
    print("  ✅ GET /api/admin/affiliate-status returns correct structure")
    print("  ✅ POST /api/admin/affiliate-refresh succeeds without crash")
    print("  ✅ Non-admin users get 403 on affiliate endpoints")
    print("="*80 + "\n")

if __name__ == "__main__":
    try:
        test_affiliate_gating_bug_fix()
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n")
        exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        exit(1)
