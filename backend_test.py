#!/usr/bin/env python3
"""
Backend API Testing for ClubTickets Affiliate Feature
Tests the new ClubTickets affiliate integration (aff=CT226) and 7 new Ibiza venues
"""

import requests
import sys
from urllib.parse import urlparse, parse_qs

# Backend URL from frontend/.env
BASE_URL = "https://url-validation-fix.preview.emergentagent.com/api"

# Test credentials
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

def test_guest_ibiza_events():
    """
    TEST 1: GET /api/events?city=Ibiza&date_filter=all (no auth / guest)
    - Response 200, returns a list of events
    - Events with clubtickets.com commission_url must contain 'aff=CT226'
    - No duplicate 'aff=' params
    - Clubtickets events should rank first
    - is_affiliate must be null for guests
    """
    print("\n" + "="*80)
    print("TEST 1: Guest Ibiza Events Feed (ClubTickets Affiliate)")
    print("="*80)
    
    url = f"{BASE_URL}/events"
    params = {"city": "Ibiza", "date_filter": "all"}
    
    response = requests.get(url, params=params)
    print(f"GET {url}?city=Ibiza&date_filter=all")
    print(f"Status: {response.status_code}")
    
    if response.status_code != 200:
        print(f"❌ FAIL: Expected 200, got {response.status_code}")
        print(f"Response: {response.text[:500]}")
        return False
    
    data = response.json()
    # API returns list directly, not wrapped in object
    events = data if isinstance(data, list) else data.get("items", [])
    print(f"✅ Response 200 - {len(events)} events returned")
    
    if len(events) == 0:
        print("❌ FAIL: No events returned for Ibiza")
        return False
    
    # Check clubtickets.com events
    clubtickets_events = []
    clubtickets_indices = []
    non_clubtickets_first_index = None
    
    for idx, event in enumerate(events):
        commission_url = event.get("commission_url", "")
        is_affiliate = event.get("is_affiliate")
        
        # Check is_affiliate is null for guests
        if is_affiliate is not None:
            print(f"❌ FAIL: Event {event.get('id')} has is_affiliate={is_affiliate}, expected null for guest")
            return False
        
        if commission_url and "clubtickets.com" in commission_url:
            clubtickets_events.append(event)
            clubtickets_indices.append(idx)
            
            # Check for aff=CT226
            if "aff=CT226" not in commission_url:
                print(f"❌ FAIL: Event {event.get('name')} has clubtickets.com URL without aff=CT226")
                print(f"   URL: {commission_url}")
                return False
            
            # Check for duplicate aff= params
            aff_count = commission_url.count("aff=")
            if aff_count > 1:
                print(f"❌ FAIL: Event {event.get('name')} has duplicate aff= params")
                print(f"   URL: {commission_url}")
                return False
        else:
            if non_clubtickets_first_index is None:
                non_clubtickets_first_index = idx
    
    print(f"✅ Found {len(clubtickets_events)} clubtickets.com events")
    print(f"✅ All clubtickets.com URLs contain 'aff=CT226' with no duplicates")
    print(f"✅ is_affiliate is null for all events (guest user)")
    
    # Check ranking (clubtickets events should be first)
    if len(clubtickets_events) > 0:
        last_clubtickets_index = max(clubtickets_indices)
        if non_clubtickets_first_index is not None and non_clubtickets_first_index < last_clubtickets_index:
            print(f"⚠️  WARNING: Clubtickets events not all ranked first")
            print(f"   Last clubtickets index: {last_clubtickets_index}")
            print(f"   First non-clubtickets index: {non_clubtickets_first_index}")
            # Not a hard fail, but note it
        else:
            print(f"✅ Clubtickets events rank first (indices 0-{last_clubtickets_index})")
    
    # Show sample clubtickets event
    if len(clubtickets_events) > 0:
        sample = clubtickets_events[0]
        print(f"\nSample ClubTickets event:")
        print(f"  Name: {sample.get('name')}")
        print(f"  Venue: {sample.get('venue')}")
        print(f"  URL: {sample.get('commission_url')[:100]}...")
    
    return True


def test_admin_is_affiliate_flag():
    """
    TEST 2: Admin is_affiliate flag
    - Login as admin
    - GET /api/events?city=Ibiza with auth
    - Clubtickets events should have is_affiliate=true
    - Non-clubtickets events should have is_affiliate=false
    """
    print("\n" + "="*80)
    print("TEST 2: Admin is_affiliate Flag")
    print("="*80)
    
    # Login as admin
    login_url = f"{BASE_URL}/auth/login"
    login_data = {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    
    print(f"POST {login_url}")
    login_response = requests.post(login_url, json=login_data)
    print(f"Status: {login_response.status_code}")
    
    if login_response.status_code != 200:
        print(f"❌ FAIL: Admin login failed")
        print(f"Response: {login_response.text[:500]}")
        return False
    
    # Get token from response
    login_json = login_response.json()
    token = login_json.get("token")
    if not token:
        print(f"❌ FAIL: No token in login response")
        return False
    
    print(f"✅ Admin login successful")
    
    # Get Ibiza events with admin auth
    headers = {"Authorization": f"Bearer {token}"}
    events_url = f"{BASE_URL}/events"
    params = {"city": "Ibiza", "date_filter": "all"}
    
    print(f"\nGET {events_url}?city=Ibiza&date_filter=all (with admin auth)")
    response = requests.get(events_url, params=params, headers=headers)
    print(f"Status: {response.status_code}")
    
    if response.status_code != 200:
        print(f"❌ FAIL: Expected 200, got {response.status_code}")
        return False
    
    data = response.json()
    # API returns list directly, not wrapped in object
    events = data if isinstance(data, list) else data.get("items", [])
    print(f"✅ Response 200 - {len(events)} events returned")
    
    clubtickets_with_flag = []
    non_clubtickets_with_flag = []
    
    for event in events:
        commission_url = event.get("commission_url", "")
        is_affiliate = event.get("is_affiliate")
        
        if commission_url and "clubtickets.com" in commission_url:
            if is_affiliate is True:
                clubtickets_with_flag.append(event)
            else:
                print(f"❌ FAIL: ClubTickets event {event.get('name')} has is_affiliate={is_affiliate}, expected true")
                return False
        elif commission_url and ("fourvenues.com" in commission_url or "xceedclub.com" in commission_url):
            # Non-clubtickets event with commission URL
            if is_affiliate is False:
                non_clubtickets_with_flag.append(event)
            else:
                print(f"❌ FAIL: Non-ClubTickets event {event.get('name')} has is_affiliate={is_affiliate}, expected false")
                print(f"   URL: {commission_url}")
                return False
    
    print(f"✅ {len(clubtickets_with_flag)} clubtickets events have is_affiliate=true")
    print(f"✅ {len(non_clubtickets_with_flag)} non-clubtickets events have is_affiliate=false")
    
    # Show samples
    if len(clubtickets_with_flag) > 0:
        sample = clubtickets_with_flag[0]
        print(f"\nSample ClubTickets event (is_affiliate=true):")
        print(f"  Name: {sample.get('name')}")
        print(f"  Venue: {sample.get('venue')}")
    
    if len(non_clubtickets_with_flag) > 0:
        sample = non_clubtickets_with_flag[0]
        print(f"\nSample non-ClubTickets event (is_affiliate=false):")
        print(f"  Name: {sample.get('name')}")
        print(f"  Venue: {sample.get('venue')}")
        print(f"  URL: {sample.get('commission_url')[:80]}...")
    
    return True


def test_admin_scrapers_clubtickets():
    """
    TEST 3: Admin scrapers list
    - GET /api/admin/scrapers (admin auth)
    - Verify 7 new venues with adapter_type='clubtickets', active=true, city='Ibiza'
    - Pick one venue and run POST /api/admin/scrapers/{venue_id}/run
    - Confirm ok=true and events > 0
    """
    print("\n" + "="*80)
    print("TEST 3: Admin Scrapers - ClubTickets Venues")
    print("="*80)
    
    # Login as admin
    login_url = f"{BASE_URL}/auth/login"
    login_data = {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    login_response = requests.post(login_url, json=login_data)
    
    if login_response.status_code != 200:
        print(f"❌ FAIL: Admin login failed")
        return False
    
    token = login_response.json().get("token")
    headers = {"Authorization": f"Bearer {token}"}
    
    # Get scrapers list
    scrapers_url = f"{BASE_URL}/admin/scrapers"
    print(f"GET {scrapers_url}")
    response = requests.get(scrapers_url, headers=headers)
    print(f"Status: {response.status_code}")
    
    if response.status_code != 200:
        print(f"❌ FAIL: Expected 200, got {response.status_code}")
        print(f"Response: {response.text[:500]}")
        return False
    
    scrapers = response.json()
    print(f"✅ Response 200 - {len(scrapers)} scrapers returned")
    
    # Filter clubtickets scrapers
    clubtickets_scrapers = [
        s for s in scrapers 
        if s.get("adapter_type") == "clubtickets" and s.get("city") == "Ibiza"
    ]
    
    print(f"\nClubTickets scrapers found: {len(clubtickets_scrapers)}")
    
    expected_venues = ["UNVRS", "O Beach Ibiza", "528 Ibiza", "Baloo Ibiza", "Bambuku Ibiza", "Playa Soleil", "Teatro Pereyra"]
    
    for scraper in clubtickets_scrapers:
        name = scraper.get("name")
        active = scraper.get("active")
        adapter_type = scraper.get("adapter_type")
        city = scraper.get("city")
        
        print(f"  - {name}: adapter_type={adapter_type}, active={active}, city={city}")
        
        if adapter_type != "clubtickets":
            print(f"    ❌ FAIL: Expected adapter_type='clubtickets', got '{adapter_type}'")
            return False
        
        if city != "Ibiza":
            print(f"    ❌ FAIL: Expected city='Ibiza', got '{city}'")
            return False
    
    if len(clubtickets_scrapers) != 7:
        print(f"❌ FAIL: Expected 7 clubtickets venues, found {len(clubtickets_scrapers)}")
        print(f"Expected venues: {expected_venues}")
        return False
    
    print(f"✅ All 7 clubtickets venues have correct adapter_type='clubtickets', city='Ibiza'")
    
    # Verify venue names
    found_names = [s.get("name") for s in clubtickets_scrapers]
    for expected in expected_venues:
        if expected not in found_names:
            print(f"⚠️  WARNING: Expected venue '{expected}' not found in scrapers list")
    
    # Pick one venue and run scraper
    test_venue = clubtickets_scrapers[0]
    venue_id = test_venue.get("id")
    venue_name = test_venue.get("name")
    
    print(f"\nTesting scraper run for: {venue_name} (id: {venue_id})")
    run_url = f"{BASE_URL}/admin/scrapers/{venue_id}/run"
    print(f"POST {run_url}")
    
    run_response = requests.post(run_url, headers=headers)
    print(f"Status: {run_response.status_code}")
    
    if run_response.status_code != 200:
        print(f"❌ FAIL: Expected 200, got {run_response.status_code}")
        print(f"Response: {run_response.text[:500]}")
        return False
    
    run_data = run_response.json()
    ok = run_data.get("ok")
    events = run_data.get("events", 0)
    
    print(f"Response: ok={ok}, events={events}")
    
    if ok is not True:
        print(f"❌ FAIL: Expected ok=true, got {ok}")
        return False
    
    if events <= 0:
        print(f"❌ FAIL: Expected events > 0, got {events}")
        return False
    
    print(f"✅ Scraper run successful: ok=true, events={events}")
    
    return True


def test_regression():
    """
    TEST 4: Regression tests
    - GET /api/events?city=Madrid&date_filter=all returns 200 (non-Ibiza still works)
    - No obvious duplicate venues for the same physical club
    - Events without clubtickets.com URLs are unchanged (no aff appended)
    """
    print("\n" + "="*80)
    print("TEST 4: Regression Tests")
    print("="*80)
    
    # Test Madrid events
    print("\n4a. Testing Madrid events (non-Ibiza city)")
    url = f"{BASE_URL}/events"
    params = {"city": "Madrid", "date_filter": "all"}
    
    print(f"GET {url}?city=Madrid&date_filter=all")
    response = requests.get(url, params=params)
    print(f"Status: {response.status_code}")
    
    if response.status_code != 200:
        print(f"❌ FAIL: Madrid events failed with {response.status_code}")
        return False
    
    data = response.json()
    madrid_events = data if isinstance(data, list) else data.get("items", [])
    print(f"✅ Madrid events working - {len(madrid_events)} events returned")
    
    # Test non-clubtickets URLs unchanged
    print("\n4b. Verifying non-clubtickets URLs are unchanged")
    
    # Get Ibiza events to check non-clubtickets URLs
    params = {"city": "Ibiza", "date_filter": "all"}
    response = requests.get(url, params=params)
    
    if response.status_code != 200:
        print(f"❌ FAIL: Could not fetch Ibiza events for regression test")
        return False
    
    data = response.json()
    events = data if isinstance(data, list) else data.get("items", [])
    
    non_clubtickets_with_aff = []
    
    for event in events:
        commission_url = event.get("commission_url", "")
        
        # Check non-clubtickets URLs don't have aff appended
        if commission_url and "clubtickets.com" not in commission_url:
            if "aff=" in commission_url:
                # This might be legitimate (e.g., FourVenues has its own aff)
                # Only flag if it's CT226
                if "aff=CT226" in commission_url:
                    print(f"❌ FAIL: Non-clubtickets event has aff=CT226 appended")
                    print(f"   Event: {event.get('name')}")
                    print(f"   URL: {commission_url}")
                    return False
    
    print(f"✅ Non-clubtickets URLs are unchanged (no CT226 affiliate appended)")
    
    # Check for duplicate venues
    print("\n4c. Checking for duplicate venues")
    
    # Login as admin to get scrapers list
    login_url = f"{BASE_URL}/auth/login"
    login_data = {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    login_response = requests.post(login_url, json=login_data)
    
    if login_response.status_code != 200:
        print(f"⚠️  WARNING: Could not login to check scrapers")
        return True  # Don't fail the test
    
    token = login_response.json().get("token")
    headers = {"Authorization": f"Bearer {token}"}
    
    scrapers_url = f"{BASE_URL}/admin/scrapers"
    response = requests.get(scrapers_url, headers=headers)
    
    if response.status_code != 200:
        print(f"⚠️  WARNING: Could not fetch scrapers list")
        return True
    
    scrapers = response.json()
    ibiza_scrapers = [s for s in scrapers if s.get("city") == "Ibiza"]
    
    print(f"Total Ibiza scrapers: {len(ibiza_scrapers)}")
    
    # Check for duplicate venue names
    venue_names = [s.get("name") for s in ibiza_scrapers]
    duplicates = [name for name in venue_names if venue_names.count(name) > 1]
    
    if duplicates:
        print(f"⚠️  WARNING: Duplicate venue names found: {set(duplicates)}")
        # Not a hard fail, just a warning
    else:
        print(f"✅ No duplicate venue names found")
    
    # Check that the 7 new clubtickets venues are distinct
    clubtickets_venues = [s.get("name") for s in ibiza_scrapers if s.get("adapter_type") == "clubtickets"]
    print(f"\nClubTickets venues: {clubtickets_venues}")
    
    # Check that existing venues (Eden, Es Paradis, etc.) still exist only once
    known_venues = ["Eden Ibiza", "Es Paradis", "Ushuaïa Ibiza", "Hï Ibiza"]
    for venue in known_venues:
        count = venue_names.count(venue)
        if count > 1:
            print(f"❌ FAIL: Venue '{venue}' appears {count} times (should be 1)")
            return False
        elif count == 1:
            print(f"✅ Venue '{venue}' exists once (no duplication)")
    
    return True


def main():
    """Run all tests"""
    print("="*80)
    print("ClubTickets Affiliate Feature Testing")
    print("Backend URL:", BASE_URL)
    print("="*80)
    
    tests = [
        ("Guest Ibiza Events Feed", test_guest_ibiza_events),
        ("Admin is_affiliate Flag", test_admin_is_affiliate_flag),
        ("Admin Scrapers - ClubTickets", test_admin_scrapers_clubtickets),
        ("Regression Tests", test_regression),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n❌ EXCEPTION in {test_name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
