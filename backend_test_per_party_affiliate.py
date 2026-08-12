#!/usr/bin/env python3
"""
Backend test for ClubTickets affiliate link PER PARTY (not per venue)

CRITICAL CHANGE: Affiliate links are now applied PER PARTY, not per venue.
Only parties that are in the ClubTickets affiliate panel (CT226) get the aff= link.
Parties NOT in the panel keep their direct venue link WITHOUT aff=.

Test data:
- 58 events for venue "[UNVRS]" in Ibiza
- 57 are in affiliate panel (commission_url = clubtickets.com with aff=CT226)
- 1 is NOT in panel: "Jamie Jones Presents Paradise" on 2026-08-12
  (should have direct unvrs.com link WITHOUT aff=)

Test items:
1) Find "Jamie Jones Presents Paradise" (2026-08-12) at [UNVRS]
   - ASSERT commission_url does NOT contain "aff="
   - ASSERT commission_url is NOT a clubtickets.com URL
   - ASSERT commission_url is a direct https://www.unvrs.com/... link
   - ASSERT is_affiliate field is False

2) Find other [UNVRS] events that ARE in panel (e.g. "FISHER" on 2026-08-13)
   - ASSERT commission_url is clubtickets.com with aff=CT226
   - ASSERT is_affiliate is True

3) REGRESSION: 
   - GET /api/events?city=Ibiza still returns 200
   - Events ordering places affiliate (aff) events before non-affiliate ones
   - NO non-clubtickets.com URL contains an injected "aff=" param
   - GET /api/events with admin city="Palma de Mallorca" still returns 200
"""

import requests
import sys

# Backend URL - using localhost since we're in the same container
BASE_URL = "http://localhost:8001/api"

# Admin credentials
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

def login_admin():
    """Login as admin and return token"""
    print("\n=== ADMIN LOGIN ===")
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    print(f"POST /auth/login → {resp.status_code}")
    if resp.status_code != 200:
        print(f"ERROR: {resp.text}")
        sys.exit(1)
    
    data = resp.json()
    token = data.get("token")
    print(f"✓ Admin login successful")
    return token

def set_admin_city(token, city):
    """Set admin user's city"""
    print(f"\n=== SET ADMIN CITY TO {city} ===")
    resp = requests.put(f"{BASE_URL}/auth/profile", 
        headers={"Authorization": f"Bearer {token}"},
        json={"city": city}
    )
    print(f"PUT /auth/profile → {resp.status_code}")
    if resp.status_code != 200:
        print(f"ERROR: {resp.text}")
        return False
    print(f"✓ Admin city set to {city}")
    return True

def test_jamie_jones_non_affiliate(token):
    """
    TEST 1: Jamie Jones Presents Paradise (NOT in panel)
    Should have direct unvrs.com link WITHOUT aff=
    """
    print("\n" + "="*80)
    print("TEST 1: JAMIE JONES PRESENTS PARADISE (NOT IN PANEL)")
    print("="*80)
    
    # Get Ibiza events
    resp = requests.get(f"{BASE_URL}/events?city=Ibiza",
        headers={"Authorization": f"Bearer {token}"}
    )
    print(f"GET /events?city=Ibiza → {resp.status_code}")
    if resp.status_code != 200:
        print(f"❌ FAIL: Could not get events: {resp.text}")
        return False
    
    events = resp.json()
    print(f"✓ Found {len(events)} total Ibiza events")
    
    # Find Jamie Jones event
    jamie_jones = None
    for event in events:
        if (event.get("name") == "Jamie Jones Presents Paradise" and 
            event.get("venue") == "[UNVRS]" and 
            event.get("date") == "2026-08-12"):
            jamie_jones = event
            break
    
    if not jamie_jones:
        print(f"\n❌ FAIL: Could not find 'Jamie Jones Presents Paradise' at [UNVRS] on 2026-08-12")
        print(f"Searching for any Jamie Jones events...")
        jamie_events = [e for e in events if "Jamie Jones" in e.get("name", "")]
        if jamie_events:
            print(f"Found {len(jamie_events)} events with 'Jamie Jones' in name:")
            for e in jamie_events[:5]:
                print(f"  - {e.get('name')} at {e.get('venue')} on {e.get('date')}")
        return False
    
    print(f"\n✓ Found event: {jamie_jones.get('name')}")
    print(f"  Venue: {jamie_jones.get('venue')}")
    print(f"  Date: {jamie_jones.get('date')}")
    
    commission_url = jamie_jones.get("commission_url", "")
    is_affiliate = jamie_jones.get("is_affiliate", None)
    
    print(f"  commission_url: {commission_url}")
    print(f"  is_affiliate: {is_affiliate}")
    
    # ASSERTIONS
    all_passed = True
    
    # 1. commission_url should NOT contain "aff="
    if "aff=" in commission_url:
        print(f"\n❌ FAIL: commission_url contains 'aff=' (should NOT have affiliate param)")
        all_passed = False
    else:
        print(f"\n✓ PASS: commission_url does NOT contain 'aff='")
    
    # 2. commission_url should NOT be a clubtickets.com URL
    if "clubtickets.com" in commission_url:
        print(f"❌ FAIL: commission_url is a clubtickets.com URL (should be direct venue link)")
        all_passed = False
    else:
        print(f"✓ PASS: commission_url is NOT a clubtickets.com URL")
    
    # 3. commission_url should be a direct unvrs.com link
    if "unvrs.com" in commission_url or "www.unvrs.com" in commission_url:
        print(f"✓ PASS: commission_url is a direct unvrs.com link")
    else:
        print(f"❌ FAIL: commission_url is NOT a unvrs.com link (expected direct venue link)")
        all_passed = False
    
    # 4. is_affiliate should be False
    if is_affiliate is False:
        print(f"✓ PASS: is_affiliate is False")
    else:
        print(f"❌ FAIL: is_affiliate is {is_affiliate} (expected False)")
        all_passed = False
    
    return all_passed

def test_fisher_affiliate(token):
    """
    TEST 2: FISHER event (IN panel)
    Should have clubtickets.com link WITH aff=CT226
    """
    print("\n" + "="*80)
    print("TEST 2: FISHER EVENT (IN PANEL)")
    print("="*80)
    
    # Get Ibiza events
    resp = requests.get(f"{BASE_URL}/events?city=Ibiza",
        headers={"Authorization": f"Bearer {token}"}
    )
    print(f"GET /events?city=Ibiza → {resp.status_code}")
    if resp.status_code != 200:
        print(f"❌ FAIL: Could not get events: {resp.text}")
        return False
    
    events = resp.json()
    
    # Find FISHER event at [UNVRS] on 2026-08-13
    fisher = None
    for event in events:
        if (event.get("name") == "FISHER" and 
            event.get("venue") == "[UNVRS]" and 
            event.get("date") == "2026-08-13"):
            fisher = event
            break
    
    if not fisher:
        print(f"\n⚠️  Could not find 'FISHER' at [UNVRS] on 2026-08-13")
        print(f"Searching for any [UNVRS] events with affiliate links...")
        unvrs_affiliate_events = [
            e for e in events 
            if e.get("venue") == "[UNVRS]" and 
               "clubtickets.com" in e.get("commission_url", "") and
               "aff=CT226" in e.get("commission_url", "")
        ]
        if unvrs_affiliate_events:
            fisher = unvrs_affiliate_events[0]
            print(f"Using alternative [UNVRS] affiliate event: {fisher.get('name')} on {fisher.get('date')}")
        else:
            print(f"❌ FAIL: Could not find any [UNVRS] events with affiliate links")
            return False
    
    print(f"\n✓ Found event: {fisher.get('name')}")
    print(f"  Venue: {fisher.get('venue')}")
    print(f"  Date: {fisher.get('date')}")
    
    commission_url = fisher.get("commission_url", "")
    is_affiliate = fisher.get("is_affiliate", None)
    
    print(f"  commission_url: {commission_url}")
    print(f"  is_affiliate: {is_affiliate}")
    
    # ASSERTIONS
    all_passed = True
    
    # 1. commission_url should be clubtickets.com
    if "clubtickets.com" in commission_url:
        print(f"\n✓ PASS: commission_url is a clubtickets.com URL")
    else:
        print(f"\n❌ FAIL: commission_url is NOT a clubtickets.com URL")
        all_passed = False
    
    # 2. commission_url should contain aff=CT226
    if "aff=CT226" in commission_url:
        print(f"✓ PASS: commission_url contains 'aff=CT226'")
    else:
        print(f"❌ FAIL: commission_url does NOT contain 'aff=CT226'")
        all_passed = False
    
    # 3. is_affiliate should be True
    if is_affiliate is True:
        print(f"✓ PASS: is_affiliate is True")
    else:
        print(f"❌ FAIL: is_affiliate is {is_affiliate} (expected True)")
        all_passed = False
    
    return all_passed

def test_regression(token):
    """
    TEST 3: REGRESSION TESTS
    - Ibiza feed still works
    - Affiliate events rank first
    - No aff injection into non-clubtickets URLs
    - Palma still works
    """
    print("\n" + "="*80)
    print("TEST 3: REGRESSION TESTS")
    print("="*80)
    
    all_passed = True
    
    # 3a. GET /api/events?city=Ibiza returns 200
    print("\n--- 3a. Ibiza feed still works ---")
    resp = requests.get(f"{BASE_URL}/events?city=Ibiza",
        headers={"Authorization": f"Bearer {token}"}
    )
    print(f"GET /events?city=Ibiza → {resp.status_code}")
    if resp.status_code != 200:
        print(f"❌ FAIL: Ibiza feed returned {resp.status_code}")
        all_passed = False
    else:
        events = resp.json()
        print(f"✓ PASS: Ibiza feed returns 200 with {len(events)} events")
        
        # 3b. Check ordering: affiliate events should come first
        print("\n--- 3b. Affiliate events rank first ---")
        first_non_affiliate_index = None
        last_affiliate_index = None
        
        for i, event in enumerate(events):
            is_affiliate = event.get("is_affiliate", False)
            if is_affiliate:
                last_affiliate_index = i
            elif first_non_affiliate_index is None:
                first_non_affiliate_index = i
        
        if last_affiliate_index is not None and first_non_affiliate_index is not None:
            if last_affiliate_index < first_non_affiliate_index:
                print(f"✓ PASS: Affiliate events rank first (last affiliate at index {last_affiliate_index}, first non-affiliate at {first_non_affiliate_index})")
            else:
                print(f"❌ FAIL: Ordering broken - found non-affiliate at index {first_non_affiliate_index} before affiliate at {last_affiliate_index}")
                all_passed = False
        else:
            print(f"⚠️  Could not verify ordering (affiliate events: {last_affiliate_index}, non-affiliate: {first_non_affiliate_index})")
        
        # 3c. Check no aff injection into non-clubtickets URLs
        print("\n--- 3c. No aff injection into non-clubtickets URLs ---")
        injected = []
        for event in events:
            commission_url = event.get("commission_url", "")
            if commission_url and "clubtickets.com" not in commission_url and "aff=" in commission_url:
                injected.append({
                    "name": event.get("name"),
                    "venue": event.get("venue"),
                    "url": commission_url
                })
        
        if injected:
            print(f"❌ FAIL: Found {len(injected)} non-clubtickets URLs with 'aff=' injected:")
            for evt in injected[:3]:
                print(f"  - {evt['name']} at {evt['venue']}: {evt['url'][:80]}")
            all_passed = False
        else:
            print(f"✓ PASS: No 'aff=' injected into non-clubtickets URLs")
    
    # 3d. Palma still works
    print("\n--- 3d. Palma feed still works ---")
    if not set_admin_city(token, "Palma de Mallorca"):
        print(f"❌ FAIL: Could not set admin city to Palma de Mallorca")
        all_passed = False
    else:
        resp = requests.get(f"{BASE_URL}/events",
            headers={"Authorization": f"Bearer {token}"}
        )
        print(f"GET /events (Palma) → {resp.status_code}")
        if resp.status_code != 200:
            print(f"❌ FAIL: Palma feed returned {resp.status_code}")
            all_passed = False
        else:
            palma_events = resp.json()
            print(f"✓ PASS: Palma feed returns 200 with {len(palma_events)} events")
        
        # Set city back to Ibiza
        set_admin_city(token, "Ibiza")
    
    return all_passed

def main():
    print("="*80)
    print("CLUBTICKETS PER-PARTY AFFILIATE LINK TESTING")
    print("="*80)
    print("\nCRITICAL CHANGE: Affiliate links now applied PER PARTY, not per venue")
    print("Only parties in the ClubTickets panel get aff=CT226")
    print("Parties NOT in panel keep their direct venue link WITHOUT aff=")
    
    # Login
    token = login_admin()
    
    # Set admin city to Ibiza
    if not set_admin_city(token, "Ibiza"):
        print("\n❌ CRITICAL: Could not set admin city to Ibiza")
        sys.exit(1)
    
    # Run tests
    results = {}
    
    results["jamie_jones_non_affiliate"] = test_jamie_jones_non_affiliate(token)
    results["fisher_affiliate"] = test_fisher_affiliate(token)
    results["regression"] = test_regression(token)
    
    # Final summary
    print("\n" + "="*80)
    print("FINAL SUMMARY")
    print("="*80)
    
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    all_passed = all(results.values())
    
    if all_passed:
        print("\n✅ ALL TESTS PASSED")
        print("\nCONCLUSION:")
        print("- Jamie Jones event (NOT in panel) has direct unvrs.com link WITHOUT aff=")
        print("- Other [UNVRS] events (IN panel) have clubtickets.com links WITH aff=CT226")
        print("- Affiliate events rank first in feed")
        print("- No aff injection into non-clubtickets URLs")
        print("- Palma feed still works")
        sys.exit(0)
    else:
        print("\n❌ SOME TESTS FAILED")
        sys.exit(1)

if __name__ == "__main__":
    main()
