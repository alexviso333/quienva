#!/usr/bin/env python3
"""
Test FourVenues affiliate logic for "¿Quién va?" backend.
Tests affiliate status endpoints and URL rewriting for events we carry vs. don't carry.
"""

import requests
import json
import sys
from datetime import datetime, timedelta

# Backend URL from environment
BASE_URL = "https://voting-island-widget.preview.emergentagent.com/api"

# Admin credentials
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

def login_admin():
    """Login as admin and return token."""
    print("\n🔐 Logging in as admin...")
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.status_code} {resp.text}"
    token = resp.json()["token"]
    print(f"✅ Admin login successful")
    return token

def register_user(city="Madrid"):
    """Register a normal user and return token."""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    email = f"testuser{timestamp}@test.com"
    username = f"user{timestamp}"
    
    resp = requests.post(f"{BASE_URL}/auth/register", json={
        "email": email,
        "password": "test123",
        "name": f"Test User {timestamp}",
        "username": username,
        "birthdate": "1995-01-01",
        "city": city
    })
    assert resp.status_code == 200, f"User registration failed: {resp.status_code} {resp.text}"
    token = resp.json()["token"]
    user_id = resp.json()["user"]["user_id"]
    print(f"✅ Registered user: {email} (city: {city})")
    return token, user_id

def test_affiliate_status(admin_token):
    """Test (A): Affiliate status endpoints."""
    print("\n" + "="*80)
    print("TEST (A): AFFILIATE STATUS ENDPOINTS")
    print("="*80)
    
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # Test 1: POST /api/admin/affiliate-refresh (admin)
    print("\n📝 Test A1: POST /api/admin/affiliate-refresh as admin")
    resp = requests.post(f"{BASE_URL}/admin/affiliate-refresh", headers=headers)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    print(f"✅ Response: {json.dumps(data, indent=2)}")
    assert "slug" in data, "Response missing 'slug' field"
    assert data["slug"] == "quienva", f"Expected slug='quienva', got '{data['slug']}'"
    assert "mine_count" in data, "Response missing 'mine_count' field"
    print(f"✅ Affiliate refresh successful: slug={data['slug']}, mine_count={data['mine_count']}")
    
    # Test 2: GET /api/admin/affiliate-status (admin)
    print("\n📝 Test A2: GET /api/admin/affiliate-status as admin")
    resp = requests.get(f"{BASE_URL}/admin/affiliate-status", headers=headers)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    print(f"✅ Response: {json.dumps(data, indent=2)}")
    assert "slug" in data, "Response missing 'slug' field"
    assert data["slug"] == "quienva", f"Expected slug='quienva', got '{data['slug']}'"
    assert "mine_count" in data, "Response missing 'mine_count' field"
    assert "venues" in data, "Response missing 'venues' field"
    assert isinstance(data["venues"], list), "venues should be a list"
    
    mine_count = data["mine_count"]
    assert mine_count > 0, f"Expected mine_count > 0 (affiliate map should be populated), got {mine_count}"
    print(f"✅ Affiliate status: slug={data['slug']}, mine_count={mine_count} (expected ~172)")
    print(f"✅ Venues list has {len(data['venues'])} entries")
    
    # Verify venues structure
    if data["venues"]:
        venue = data["venues"][0]
        assert "venue" in venue, "Venue entry missing 'venue' field"
        assert "city" in venue, "Venue entry missing 'city' field"
        assert "events" in venue, "Venue entry missing 'events' field"
        print(f"✅ Venue structure correct: {venue['venue']} ({venue['city']}) - {venue['events']} events")
    
    # Test 3: GET /api/admin/affiliate-status as non-admin (should be 403)
    print("\n📝 Test A3: GET /api/admin/affiliate-status as non-admin user")
    user_token, _ = register_user("Madrid")
    user_headers = {"Authorization": f"Bearer {user_token}"}
    resp = requests.get(f"{BASE_URL}/admin/affiliate-status", headers=user_headers)
    assert resp.status_code == 403, f"Expected 403 for non-admin, got {resp.status_code}"
    print(f"✅ Non-admin correctly rejected with 403")
    
    print("\n✅ TEST (A) PASSED: All affiliate status endpoints working correctly")
    return mine_count

def test_negative_case(admin_token):
    """Test (B): NEGATIVE case - events we DON'T carry must NOT be rewritten."""
    print("\n" + "="*80)
    print("TEST (B): NEGATIVE CASE - Events we DON'T carry")
    print("="*80)
    
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # Create an event we DON'T carry
    future_date = (datetime.now() + timedelta(days=1400)).strftime("%Y-%m-%d")  # 2030-06-06
    event_data = {
        "name": "Fiesta Random No Mia",
        "venue": "Local Random Inexistente",
        "city": "Madrid",
        "date": future_date,
        "time": "23:00",
        "has_commission": True,
        "commission_url": "https://site.fourvenues.com/es/amok@amok/events/random-ZZ"
    }
    
    print(f"\n📝 Test B1: Create event we DON'T carry")
    print(f"   Name: {event_data['name']}")
    print(f"   Venue: {event_data['venue']}")
    print(f"   City: {event_data['city']}")
    print(f"   Date: {event_data['date']}")
    print(f"   Original commission_url: {event_data['commission_url']}")
    
    resp = requests.post(f"{BASE_URL}/admin/events", json=event_data, headers=headers)
    assert resp.status_code == 200, f"Event creation failed: {resp.status_code} {resp.text}"
    event = resp.json()
    event_id = event["id"]
    print(f"✅ Event created with id: {event_id}")
    
    # Test B2: GET event as admin - commission_url must be UNCHANGED
    print(f"\n📝 Test B2: GET /api/events/{event_id} as admin")
    resp = requests.get(f"{BASE_URL}/events/{event_id}", headers=headers)
    assert resp.status_code == 200, f"GET event failed: {resp.status_code} {resp.text}"
    event = resp.json()
    
    commission_url = event.get("commission_url", "")
    is_affiliate = event.get("is_affiliate")
    
    print(f"   commission_url: {commission_url}")
    print(f"   is_affiliate: {is_affiliate}")
    
    # CRITICAL ASSERTION: commission_url must be UNCHANGED (NOT rewritten to /quienva/)
    assert commission_url == "https://site.fourvenues.com/es/amok@amok/events/random-ZZ", \
        f"❌ FAIL: commission_url was rewritten! Expected 'https://site.fourvenues.com/es/amok@amok/events/random-ZZ', got '{commission_url}'"
    assert "/quienva/" not in commission_url, \
        f"❌ FAIL: commission_url contains '/quienva/' when it shouldn't: {commission_url}"
    print(f"✅ CRITICAL: commission_url is UNCHANGED (does NOT contain '/quienva/')")
    
    # Admin should see is_affiliate field
    assert is_affiliate is not None, "Admin should see is_affiliate field (not null)"
    assert is_affiliate == False, f"Expected is_affiliate=false for event we don't carry, got {is_affiliate}"
    print(f"✅ is_affiliate={is_affiliate} (correct for event we don't carry)")
    
    print("\n✅ TEST (B) PASSED: Events we DON'T carry are NOT rewritten")
    return event_id

def test_positive_case(admin_token):
    """Test (C): POSITIVE case - events we DO carry should be rewritten to OUR slug."""
    print("\n" + "="*80)
    print("TEST (C): POSITIVE CASE - Events we DO carry")
    print("="*80)
    
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # Create an event we DO carry (matching one in our affiliate profile)
    # Using REGGAETON MILLENNIAL FEST 2026 - ALICANTE which IS in our profile
    # (verified via FourVenues API: date 2026-08-07, slug: reggaeton-millennial-fest-2026---alicante-07-08-2026)
    event_data = {
        "name": "REGGAETON MILLENNIAL FEST 2026 - ALICANTE",
        "venue": "REGGAETON MILLENNIAL FEST",
        "city": "Madrid",  # City in our app doesn't have to match FourVenues location
        "date": "2026-08-07",
        "time": "23:00",
        "has_commission": True,
        "commission_url": "https://site.fourvenues.com/es/whatever/events/x"
    }
    
    print(f"\n📝 Test C1: Create event we DO carry")
    print(f"   Name: {event_data['name']}")
    print(f"   Venue: {event_data['venue']}")
    print(f"   City: {event_data['city']}")
    print(f"   Date: {event_data['date']}")
    print(f"   Original commission_url: {event_data['commission_url']}")
    
    resp = requests.post(f"{BASE_URL}/admin/events", json=event_data, headers=headers)
    assert resp.status_code == 200, f"Event creation failed: {resp.status_code} {resp.text}"
    event = resp.json()
    event_id = event["id"]
    print(f"✅ Event created with id: {event_id}")
    
    # Test C2: GET event as ADMIN - commission_url must be rewritten to OUR slug
    print(f"\n📝 Test C2: GET /api/events/{event_id} as ADMIN")
    resp = requests.get(f"{BASE_URL}/events/{event_id}", headers=headers)
    assert resp.status_code == 200, f"GET event failed: {resp.status_code} {resp.text}"
    event = resp.json()
    
    commission_url = event.get("commission_url", "")
    is_affiliate = event.get("is_affiliate")
    
    print(f"   commission_url: {commission_url}")
    print(f"   is_affiliate: {is_affiliate}")
    
    # CRITICAL ASSERTION: commission_url must be rewritten to our quienva slug
    expected_url = "https://www.fourvenues.com/quienva/events/reggaeton-millennial-fest-2026---alicante-07-08-2026"
    assert commission_url == expected_url, \
        f"❌ FAIL: commission_url not rewritten correctly! Expected '{expected_url}', got '{commission_url}'"
    assert "/quienva/" in commission_url, \
        f"❌ FAIL: commission_url does NOT contain '/quienva/': {commission_url}"
    print(f"✅ CRITICAL: commission_url rewritten to OUR slug (contains '/quienva/')")
    
    # Admin should see is_affiliate=true
    assert is_affiliate is not None, "Admin should see is_affiliate field (not null)"
    assert is_affiliate == True, f"Expected is_affiliate=true for event we carry, got {is_affiliate}"
    print(f"✅ is_affiliate={is_affiliate} (correct for event we carry)")
    
    # Test C3: GET event as NORMAL USER - commission_url should be same, but is_affiliate should be null
    print(f"\n📝 Test C3: GET /api/events/{event_id} as normal user")
    user_token, _ = register_user("Madrid")
    user_headers = {"Authorization": f"Bearer {user_token}"}
    resp = requests.get(f"{BASE_URL}/events/{event_id}", headers=user_headers)
    assert resp.status_code == 200, f"GET event failed: {resp.status_code} {resp.text}"
    event = resp.json()
    
    commission_url_user = event.get("commission_url", "")
    is_affiliate_user = event.get("is_affiliate")
    
    print(f"   commission_url: {commission_url_user}")
    print(f"   is_affiliate: {is_affiliate_user}")
    
    # commission_url should be the SAME rewritten URL
    assert commission_url_user == expected_url, \
        f"❌ FAIL: Normal user sees different URL! Expected '{expected_url}', got '{commission_url_user}'"
    print(f"✅ Normal user sees same rewritten URL")
    
    # is_affiliate should be null for normal users (not exposed)
    assert is_affiliate_user is None, \
        f"Expected is_affiliate=null for normal user, got {is_affiliate_user}"
    print(f"✅ is_affiliate={is_affiliate_user} (correctly hidden from normal users)")
    
    print("\n✅ TEST (C) PASSED: Events we DO carry are rewritten to OUR slug")
    return event_id

def cleanup_events(admin_token, event_ids):
    """Clean up test events."""
    print("\n🧹 Cleaning up test events...")
    headers = {"Authorization": f"Bearer {admin_token}"}
    for event_id in event_ids:
        try:
            resp = requests.delete(f"{BASE_URL}/admin/events/{event_id}", headers=headers)
            if resp.status_code == 200:
                print(f"✅ Deleted event {event_id}")
        except Exception as e:
            print(f"⚠️  Failed to delete event {event_id}: {e}")

def main():
    print("="*80)
    print("FOURVENUES AFFILIATE LOGIC TEST")
    print("Testing affiliate status and URL rewriting")
    print("="*80)
    
    try:
        # Login as admin
        admin_token = login_admin()
        
        # Test (A): Affiliate status endpoints
        mine_count = test_affiliate_status(admin_token)
        
        # Test (B): NEGATIVE case - events we DON'T carry
        negative_event_id = test_negative_case(admin_token)
        
        # Test (C): POSITIVE case - events we DO carry
        positive_event_id = test_positive_case(admin_token)
        
        # Cleanup
        cleanup_events(admin_token, [negative_event_id, positive_event_id])
        
        # Final summary
        print("\n" + "="*80)
        print("🎉 ALL TESTS PASSED!")
        print("="*80)
        print(f"✅ (A) Affiliate status: slug='quienva', mine_count={mine_count} (>0)")
        print(f"✅ (B) NEGATIVE case: Events we DON'T carry are NOT rewritten")
        print(f"✅ (C) POSITIVE case: Events we DO carry ARE rewritten to /quienva/")
        print("="*80)
        
        return 0
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
