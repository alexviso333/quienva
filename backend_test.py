#!/usr/bin/env python3
"""
Guest / Public Browsing Mode Test
Tests the new guest mode where anonymous users can browse events and venues without authentication.
"""

import requests
import os

# Backend URL from environment
BACKEND_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://explore-quienva.preview.emergentagent.com")
BASE_URL = f"{BACKEND_URL}/api"

def test_guest_public_browsing():
    """
    Test guest/public browsing mode on the backend.
    
    PART A - GUEST (no Authorization header, no cookies):
    1. GET /api/events → 200, verify social fields empty (friends_going=[], friends_interested=[], my_status=null, my_has_ticket=false, is_following=null)
    2. GET /api/events/genres → 200
    3. GET /api/events/top-weekend → 200
    4. GET /api/events/carousels → 200
    5. GET /api/events/{id} → 200 with social fields empty, also test 404 for non-existent
    6. GET /api/venues → 200, GET /api/venues/meta/zones → 200, GET /api/venues/{id} → 200
    
    PART B - GUEST must be blocked (401):
    - GET /api/auth/me
    - GET /api/friends
    - GET /api/notifications/unread-count
    - POST /api/events/{id}/interest
    - POST /api/events/{id}/ticket
    - POST /api/events/{id}/follow
    
    PART C - AUTHENTICATED regression (login as admin):
    - All endpoints should still work with Bearer token
    """
    
    print("=" * 80)
    print("GUEST / PUBLIC BROWSING MODE TEST")
    print("=" * 80)
    
    # ========================================================================
    # PART A - GUEST ACCESS (NO AUTHORIZATION)
    # ========================================================================
    
    print("\n" + "=" * 80)
    print("PART A - GUEST ACCESS (NO AUTHORIZATION HEADER)")
    print("=" * 80)
    
    # Test 1: GET /api/events as guest
    print("\n[TEST A1] GET /api/events as guest...")
    events_resp = requests.get(f"{BASE_URL}/events")
    assert events_resp.status_code == 200, f"Expected 200, got {events_resp.status_code}: {events_resp.text}"
    events_data = events_resp.json()
    assert isinstance(events_data, list), f"Expected list, got {type(events_data)}"
    assert len(events_data) > 0, "Expected non-empty events list (should have ~250 seeded events)"
    
    print(f"✅ GET /api/events → 200 with {len(events_data)} events")
    
    # Verify social fields are empty for guest
    sample_event = events_data[0]
    print(f"\n   Verifying social fields for sample event (id={sample_event.get('id')}):")
    
    assert sample_event.get("friends_going") == [], f"Expected friends_going=[], got {sample_event.get('friends_going')}"
    print(f"   ✅ friends_going == []")
    
    assert sample_event.get("friends_interested") == [], f"Expected friends_interested=[], got {sample_event.get('friends_interested')}"
    print(f"   ✅ friends_interested == []")
    
    assert sample_event.get("my_status") is None, f"Expected my_status=null, got {sample_event.get('my_status')}"
    print(f"   ✅ my_status == null")
    
    assert sample_event.get("my_has_ticket") == False, f"Expected my_has_ticket=false, got {sample_event.get('my_has_ticket')}"
    print(f"   ✅ my_has_ticket == false")
    
    assert sample_event.get("is_following") is None, f"Expected is_following=null, got {sample_event.get('is_following')}"
    print(f"   ✅ is_following == null")
    
    # Store a valid event ID for later tests
    valid_event_id = sample_event.get("id")
    
    # Test 2: GET /api/events/genres as guest
    print("\n[TEST A2] GET /api/events/genres as guest...")
    genres_resp = requests.get(f"{BASE_URL}/events/genres")
    assert genres_resp.status_code == 200, f"Expected 200, got {genres_resp.status_code}: {genres_resp.text}"
    genres_data = genres_resp.json()
    assert isinstance(genres_data, list), f"Expected list, got {type(genres_data)}"
    print(f"✅ GET /api/events/genres → 200 with {len(genres_data)} genres")
    
    # Test 3: GET /api/events/top-weekend as guest
    print("\n[TEST A3] GET /api/events/top-weekend as guest...")
    top_weekend_resp = requests.get(f"{BASE_URL}/events/top-weekend")
    assert top_weekend_resp.status_code == 200, f"Expected 200, got {top_weekend_resp.status_code}: {top_weekend_resp.text}"
    top_weekend_data = top_weekend_resp.json()
    # Can be an object or null
    if top_weekend_data is not None:
        assert isinstance(top_weekend_data, dict), f"Expected dict or null, got {type(top_weekend_data)}"
        # If object, friends_going should be []
        assert top_weekend_data.get("friends_going") == [], f"Expected friends_going=[] for guest, got {top_weekend_data.get('friends_going')}"
        print(f"✅ GET /api/events/top-weekend → 200 with event object (friends_going=[])")
    else:
        print(f"✅ GET /api/events/top-weekend → 200 with null (no top weekend event)")
    
    # Test 4: GET /api/events/carousels as guest
    print("\n[TEST A4] GET /api/events/carousels as guest...")
    carousels_resp = requests.get(f"{BASE_URL}/events/carousels")
    assert carousels_resp.status_code == 200, f"Expected 200, got {carousels_resp.status_code}: {carousels_resp.text}"
    carousels_data = carousels_resp.json()
    assert isinstance(carousels_data, dict), f"Expected dict, got {type(carousels_data)}"
    
    # Verify required keys
    assert "top_weekend" in carousels_data, "Missing 'top_weekend' key"
    assert "friends_going" in carousels_data, "Missing 'friends_going' key"
    assert "discover_new" in carousels_data, "Missing 'discover_new' key"
    
    # friends_going should be empty for guest
    assert carousels_data.get("friends_going") == [], f"Expected friends_going=[] for guest, got {carousels_data.get('friends_going')}"
    print(f"✅ GET /api/events/carousels → 200 with keys: top_weekend, friends_going (=[]), discover_new")
    
    # Test 5a: GET /api/events/{id} with valid ID as guest
    print(f"\n[TEST A5a] GET /api/events/{valid_event_id} as guest...")
    event_detail_resp = requests.get(f"{BASE_URL}/events/{valid_event_id}")
    assert event_detail_resp.status_code == 200, f"Expected 200, got {event_detail_resp.status_code}: {event_detail_resp.text}"
    event_detail_data = event_detail_resp.json()
    
    # Verify social fields are empty
    assert event_detail_data.get("friends_going") == [], f"Expected friends_going=[], got {event_detail_data.get('friends_going')}"
    assert event_detail_data.get("my_status") is None, f"Expected my_status=null, got {event_detail_data.get('my_status')}"
    print(f"✅ GET /api/events/{valid_event_id} → 200 with friends_going=[], my_status=null")
    
    # Test 5b: GET /api/events/{id} with non-existent ID as guest
    print(f"\n[TEST A5b] GET /api/events/nonexistent-id as guest...")
    event_404_resp = requests.get(f"{BASE_URL}/events/nonexistent-id-12345")
    assert event_404_resp.status_code == 404, f"Expected 404, got {event_404_resp.status_code}: {event_404_resp.text}"
    print(f"✅ GET /api/events/nonexistent-id → 404")
    
    # Test 6a: GET /api/venues as guest
    print("\n[TEST A6a] GET /api/venues as guest...")
    venues_resp = requests.get(f"{BASE_URL}/venues")
    assert venues_resp.status_code == 200, f"Expected 200, got {venues_resp.status_code}: {venues_resp.text}"
    venues_data = venues_resp.json()
    assert isinstance(venues_data, list), f"Expected list, got {type(venues_data)}"
    print(f"✅ GET /api/venues → 200 with {len(venues_data)} venues")
    
    # Store a valid venue ID for later test
    valid_venue_id = None
    if len(venues_data) > 0:
        valid_venue_id = venues_data[0].get("id")
    
    # Test 6b: GET /api/venues/meta/zones as guest
    print("\n[TEST A6b] GET /api/venues/meta/zones as guest...")
    zones_resp = requests.get(f"{BASE_URL}/venues/meta/zones")
    assert zones_resp.status_code == 200, f"Expected 200, got {zones_resp.status_code}: {zones_resp.text}"
    zones_data = zones_resp.json()
    assert isinstance(zones_data, dict), f"Expected dict, got {type(zones_data)}"
    assert "zones" in zones_data, "Missing 'zones' key"
    assert isinstance(zones_data["zones"], list), f"Expected zones to be list, got {type(zones_data['zones'])}"
    print(f"✅ GET /api/venues/meta/zones → 200 with {{zones:[...]}} ({len(zones_data['zones'])} zones)")
    
    # Test 6c: GET /api/venues/{id} with valid ID as guest
    if valid_venue_id:
        print(f"\n[TEST A6c] GET /api/venues/{valid_venue_id} as guest...")
        venue_detail_resp = requests.get(f"{BASE_URL}/venues/{valid_venue_id}")
        assert venue_detail_resp.status_code == 200, f"Expected 200, got {venue_detail_resp.status_code}: {venue_detail_resp.text}"
        print(f"✅ GET /api/venues/{valid_venue_id} → 200")
    else:
        print(f"\n[TEST A6c] SKIPPED - no venues available")
    
    # ========================================================================
    # PART B - GUEST MUST BE BLOCKED (401)
    # ========================================================================
    
    print("\n" + "=" * 80)
    print("PART B - GUEST MUST BE BLOCKED (EXPECT 401)")
    print("=" * 80)
    
    # Test B1: GET /api/auth/me as guest
    print("\n[TEST B1] GET /api/auth/me as guest...")
    me_resp = requests.get(f"{BASE_URL}/auth/me")
    assert me_resp.status_code == 401, f"Expected 401, got {me_resp.status_code}: {me_resp.text}"
    print(f"✅ GET /api/auth/me → 401 (blocked)")
    
    # Test B2: GET /api/friends as guest
    print("\n[TEST B2] GET /api/friends as guest...")
    friends_resp = requests.get(f"{BASE_URL}/friends")
    assert friends_resp.status_code == 401, f"Expected 401, got {friends_resp.status_code}: {friends_resp.text}"
    print(f"✅ GET /api/friends → 401 (blocked)")
    
    # Test B3: GET /api/notifications/unread-count as guest
    print("\n[TEST B3] GET /api/notifications/unread-count as guest...")
    notif_resp = requests.get(f"{BASE_URL}/notifications/unread-count")
    assert notif_resp.status_code == 401, f"Expected 401, got {notif_resp.status_code}: {notif_resp.text}"
    print(f"✅ GET /api/notifications/unread-count → 401 (blocked)")
    
    # Test B4: POST /api/events/{id}/interest as guest
    print(f"\n[TEST B4] POST /api/events/{valid_event_id}/interest as guest...")
    interest_resp = requests.post(f"{BASE_URL}/events/{valid_event_id}/interest", json={"status": "voy"})
    assert interest_resp.status_code == 401, f"Expected 401, got {interest_resp.status_code}: {interest_resp.text}"
    print(f"✅ POST /api/events/{valid_event_id}/interest → 401 (blocked)")
    
    # Test B5: POST /api/events/{id}/ticket as guest
    print(f"\n[TEST B5] POST /api/events/{valid_event_id}/ticket as guest...")
    ticket_resp = requests.post(f"{BASE_URL}/events/{valid_event_id}/ticket", json={"have": True})
    assert ticket_resp.status_code == 401, f"Expected 401, got {ticket_resp.status_code}: {ticket_resp.text}"
    print(f"✅ POST /api/events/{valid_event_id}/ticket → 401 (blocked)")
    
    # Test B6: POST /api/events/{id}/follow as guest
    print(f"\n[TEST B6] POST /api/events/{valid_event_id}/follow as guest...")
    follow_resp = requests.post(f"{BASE_URL}/events/{valid_event_id}/follow")
    assert follow_resp.status_code == 401, f"Expected 401, got {follow_resp.status_code}: {follow_resp.text}"
    print(f"✅ POST /api/events/{valid_event_id}/follow → 401 (blocked)")
    
    # ========================================================================
    # PART C - AUTHENTICATED REGRESSION
    # ========================================================================
    
    print("\n" + "=" * 80)
    print("PART C - AUTHENTICATED REGRESSION (LOGIN AS ADMIN)")
    print("=" * 80)
    
    # Login as admin
    print("\n[SETUP] Logging in as admin...")
    admin_resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "admin@quienva.app",
        "password": "admin123"
    })
    assert admin_resp.status_code == 200, f"Admin login failed: {admin_resp.status_code} {admin_resp.text}"
    admin_token = admin_resp.json()["token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    print(f"✅ Admin login successful")
    
    # Test C1: GET /api/events as authenticated user
    print("\n[TEST C1] GET /api/events as authenticated admin...")
    auth_events_resp = requests.get(f"{BASE_URL}/events", headers=admin_headers)
    assert auth_events_resp.status_code == 200, f"Expected 200, got {auth_events_resp.status_code}: {auth_events_resp.text}"
    print(f"✅ GET /api/events → 200 (authenticated)")
    
    # Test C2: GET /api/events/carousels as authenticated user
    print("\n[TEST C2] GET /api/events/carousels as authenticated admin...")
    auth_carousels_resp = requests.get(f"{BASE_URL}/events/carousels", headers=admin_headers)
    assert auth_carousels_resp.status_code == 200, f"Expected 200, got {auth_carousels_resp.status_code}: {auth_carousels_resp.text}"
    print(f"✅ GET /api/events/carousels → 200 (authenticated)")
    
    # Test C3: GET /api/events/{id} as authenticated user
    print(f"\n[TEST C3] GET /api/events/{valid_event_id} as authenticated admin...")
    auth_event_resp = requests.get(f"{BASE_URL}/events/{valid_event_id}", headers=admin_headers)
    assert auth_event_resp.status_code == 200, f"Expected 200, got {auth_event_resp.status_code}: {auth_event_resp.text}"
    print(f"✅ GET /api/events/{valid_event_id} → 200 (authenticated)")
    
    # Test C4: GET /api/venues as authenticated user
    print("\n[TEST C4] GET /api/venues as authenticated admin...")
    auth_venues_resp = requests.get(f"{BASE_URL}/venues", headers=admin_headers)
    assert auth_venues_resp.status_code == 200, f"Expected 200, got {auth_venues_resp.status_code}: {auth_venues_resp.text}"
    print(f"✅ GET /api/venues → 200 (authenticated)")
    
    # Test C5: GET /api/auth/me as authenticated user
    print("\n[TEST C5] GET /api/auth/me as authenticated admin...")
    auth_me_resp = requests.get(f"{BASE_URL}/auth/me", headers=admin_headers)
    assert auth_me_resp.status_code == 200, f"Expected 200, got {auth_me_resp.status_code}: {auth_me_resp.text}"
    print(f"✅ GET /api/auth/me → 200 (authenticated)")
    
    # Test C6: GET /api/friends as authenticated user
    print("\n[TEST C6] GET /api/friends as authenticated admin...")
    auth_friends_resp = requests.get(f"{BASE_URL}/friends", headers=admin_headers)
    assert auth_friends_resp.status_code == 200, f"Expected 200, got {auth_friends_resp.status_code}: {auth_friends_resp.text}"
    print(f"✅ GET /api/friends → 200 (authenticated)")
    
    # Test C7: POST /api/events/{id}/interest as authenticated user
    print(f"\n[TEST C7] POST /api/events/{valid_event_id}/interest {{status:'voy'}} as authenticated admin...")
    auth_interest_resp = requests.post(f"{BASE_URL}/events/{valid_event_id}/interest", 
                                       headers=admin_headers, 
                                       json={"status": "voy"})
    assert auth_interest_resp.status_code == 200, f"Expected 200, got {auth_interest_resp.status_code}: {auth_interest_resp.text}"
    print(f"✅ POST /api/events/{valid_event_id}/interest {{status:'voy'}} → 200")
    
    # Test C8: Verify my_status is now "voy"
    print(f"\n[TEST C8] GET /api/events/{valid_event_id} to verify my_status='voy'...")
    verify_resp = requests.get(f"{BASE_URL}/events/{valid_event_id}", headers=admin_headers)
    assert verify_resp.status_code == 200, f"Expected 200, got {verify_resp.status_code}: {verify_resp.text}"
    verify_data = verify_resp.json()
    assert verify_data.get("my_status") == "voy", f"Expected my_status='voy', got {verify_data.get('my_status')}"
    print(f"✅ GET /api/events/{valid_event_id} → my_status='voy' (verified)")
    
    # Test C9: Clean up - set status back to "none"
    print(f"\n[TEST C9] POST /api/events/{valid_event_id}/interest {{status:'none'}} to clean up...")
    cleanup_resp = requests.post(f"{BASE_URL}/events/{valid_event_id}/interest", 
                                 headers=admin_headers, 
                                 json={"status": "none"})
    assert cleanup_resp.status_code == 200, f"Expected 200, got {cleanup_resp.status_code}: {cleanup_resp.text}"
    print(f"✅ POST /api/events/{valid_event_id}/interest {{status:'none'}} → 200 (cleaned up)")
    
    # ========================================================================
    # SUMMARY
    # ========================================================================
    
    print("\n" + "=" * 80)
    print("✅ ALL GUEST / PUBLIC BROWSING MODE TESTS PASSED")
    print("=" * 80)
    
    print("\nTest Summary:")
    print(f"  PART A - GUEST ACCESS: 11 tests passed")
    print(f"    ✅ GET /api/events → 200 with empty social fields")
    print(f"    ✅ GET /api/events/genres → 200")
    print(f"    ✅ GET /api/events/top-weekend → 200")
    print(f"    ✅ GET /api/events/carousels → 200 with friends_going=[]")
    print(f"    ✅ GET /api/events/{{id}} → 200 with empty social fields")
    print(f"    ✅ GET /api/events/nonexistent-id → 404")
    print(f"    ✅ GET /api/venues → 200")
    print(f"    ✅ GET /api/venues/meta/zones → 200")
    print(f"    ✅ GET /api/venues/{{id}} → 200")
    print(f"  PART B - GUEST BLOCKED: 6 tests passed")
    print(f"    ✅ All protected endpoints return 401 for guest")
    print(f"  PART C - AUTHENTICATED REGRESSION: 9 tests passed")
    print(f"    ✅ All endpoints work correctly with Bearer token")
    print(f"    ✅ Interest toggle works (voy → verified → none)")
    print(f"\n  TOTAL: 26 tests passed, 0 failed")
    
    return {
        "total_tests": 26,
        "passed": 26,
        "failed": 0,
        "valid_event_id": valid_event_id,
        "valid_venue_id": valid_venue_id
    }

if __name__ == "__main__":
    try:
        result = test_guest_public_browsing()
        print("\n✅ Test completed successfully!")
        print(f"\nResult: {result['passed']}/{result['total_tests']} tests passed")
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
