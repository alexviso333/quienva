#!/usr/bin/env python3
"""
Backend test for venue reordering bug fix.

BUG FIX VERIFICATION:
Reordering venues in the admin "Prioridad de discotecas" must change the order
events appear in the feed (GET /api/events). The feed sorts affiliate events first
(tier 0), then others (tier 1); within EACH tier it now sorts by venue priority
(venues.order). After the fix, ALL of the higher-priority venue's events should
precede the lower-priority venue's events within the same tier.

STEPS:
1) Set admin city to Ibiza
2) GET /api/venues (as admin, city now Ibiza). Pick TWO venues that both have upcoming_events > 0
3) GET /api/events?city=Ibiza&date_filter=all as admin. Record the FIRST index at which
   an event with venue == A.name appears, and the first index for venue == B.name
4) PUT /api/admin/venues/reorder with the full list BUT with B moved to be BEFORE A
5) GET /api/events?city=Ibiza&date_filter=all again. Assert that venue B now has its
   first event appearing BEFORE venue A's first event
6) Restore: PUT /api/admin/venues/reorder with the original order
7) Auth check: PUT /api/admin/venues/reorder as a NON-admin user → expect 403
"""

import requests
import sys
from datetime import datetime

# Configuration
BASE_URL = "https://fiesta-rebuild.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def test_venue_reorder_bug_fix():
    """Test that venue reordering changes the feed order."""
    
    log("=" * 80)
    log("TEST: Venue Reordering Bug Fix")
    log("=" * 80)
    
    # Step 1: Admin login
    log("\n[STEP 1] Admin login...")
    session = requests.Session()
    resp = session.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if resp.status_code != 200:
        log(f"❌ FAILED: Admin login failed with status {resp.status_code}")
        log(f"Response: {resp.text}")
        return False
    log(f"✅ Admin login successful")
    
    # Step 2: Set admin city to Ibiza
    log("\n[STEP 2] Setting admin city to Ibiza...")
    resp = session.put(f"{BASE_URL}/auth/profile", json={"city": "Ibiza"})
    if resp.status_code != 200:
        log(f"❌ FAILED: Profile update failed with status {resp.status_code}")
        log(f"Response: {resp.text}")
        return False
    log(f"✅ Admin city set to Ibiza")
    
    # Step 3: Get venues with upcoming events
    log("\n[STEP 3] Getting venues with upcoming events...")
    resp = session.get(f"{BASE_URL}/venues")
    if resp.status_code != 200:
        log(f"❌ FAILED: GET /api/venues failed with status {resp.status_code}")
        return False
    
    venues = resp.json()
    venues_with_events = [v for v in venues if v.get("upcoming_events", 0) > 0]
    
    if len(venues_with_events) < 2:
        log(f"❌ FAILED: Need at least 2 venues with upcoming events, found {len(venues_with_events)}")
        return False
    
    # Pick two venues with events
    venue_a = venues_with_events[0]
    venue_b = venues_with_events[1]
    
    log(f"✅ Found {len(venues_with_events)} venues with upcoming events")
    log(f"   Venue A: {venue_a['name']} (id: {venue_a['id']}, upcoming_events: {venue_a['upcoming_events']})")
    log(f"   Venue B: {venue_b['name']} (id: {venue_b['id']}, upcoming_events: {venue_b['upcoming_events']})")
    
    # Step 4: Get initial feed order
    log("\n[STEP 4] Getting initial feed order...")
    resp = session.get(f"{BASE_URL}/events", params={"city": "Ibiza", "date_filter": "all"})
    if resp.status_code != 200:
        log(f"❌ FAILED: GET /api/events failed with status {resp.status_code}")
        return False
    
    events = resp.json()
    log(f"✅ Retrieved {len(events)} events from feed")
    
    # Find first occurrence of each venue
    first_a_index = None
    first_b_index = None
    
    for i, event in enumerate(events):
        if event.get("venue") == venue_a["name"] and first_a_index is None:
            first_a_index = i
        if event.get("venue") == venue_b["name"] and first_b_index is None:
            first_b_index = i
        if first_a_index is not None and first_b_index is not None:
            break
    
    if first_a_index is None or first_b_index is None:
        log(f"❌ FAILED: Could not find events for both venues in feed")
        log(f"   Venue A first index: {first_a_index}")
        log(f"   Venue B first index: {first_b_index}")
        return False
    
    log(f"✅ Initial feed order:")
    log(f"   Venue A ({venue_a['name']}) first event at index: {first_a_index}")
    log(f"   Venue B ({venue_b['name']}) first event at index: {first_b_index}")
    
    # Determine which venue appears first
    if first_a_index < first_b_index:
        log(f"   → Venue A appears BEFORE Venue B (A at {first_a_index}, B at {first_b_index})")
        first_venue = venue_a
        second_venue = venue_b
        first_index = first_a_index
        second_index = first_b_index
    else:
        log(f"   → Venue B appears BEFORE Venue A (B at {first_b_index}, A at {first_a_index})")
        first_venue = venue_b
        second_venue = venue_a
        first_index = first_b_index
        second_index = first_a_index
    
    # Step 5: Get current venue order
    log("\n[STEP 5] Getting current venue order...")
    all_venue_ids = [v["id"] for v in venues]
    log(f"✅ Current venue order has {len(all_venue_ids)} venues")
    
    # Step 6: Reorder venues - move second venue BEFORE first venue
    log(f"\n[STEP 6] Reordering venues - moving {second_venue['name']} BEFORE {first_venue['name']}...")
    
    # Create new order with second venue before first venue
    new_order = []
    for vid in all_venue_ids:
        if vid == second_venue["id"]:
            continue  # Skip second venue for now
        if vid == first_venue["id"]:
            new_order.append(second_venue["id"])  # Insert second venue before first
        new_order.append(vid)
    
    # If second venue wasn't inserted yet (was after first in original order), add it at the end
    if second_venue["id"] not in new_order:
        new_order.insert(0, second_venue["id"])
    
    resp = session.put(f"{BASE_URL}/admin/venues/reorder", json={"venue_ids": new_order})
    if resp.status_code != 200:
        log(f"❌ FAILED: PUT /api/admin/venues/reorder failed with status {resp.status_code}")
        log(f"Response: {resp.text}")
        return False
    
    result = resp.json()
    log(f"✅ Venue reorder successful: {result}")
    
    # Step 7: Get feed order after reordering
    log("\n[STEP 7] Getting feed order after reordering...")
    resp = session.get(f"{BASE_URL}/events", params={"city": "Ibiza", "date_filter": "all"})
    if resp.status_code != 200:
        log(f"❌ FAILED: GET /api/events failed with status {resp.status_code}")
        return False
    
    events_after = resp.json()
    log(f"✅ Retrieved {len(events_after)} events from feed")
    
    # Find first occurrence of each venue after reordering
    new_first_index = None
    new_second_index = None
    
    for i, event in enumerate(events_after):
        if event.get("venue") == first_venue["name"] and new_first_index is None:
            new_first_index = i
        if event.get("venue") == second_venue["name"] and new_second_index is None:
            new_second_index = i
        if new_first_index is not None and new_second_index is not None:
            break
    
    if new_first_index is None or new_second_index is None:
        log(f"❌ FAILED: Could not find events for both venues in feed after reordering")
        return False
    
    log(f"✅ Feed order after reordering:")
    log(f"   {first_venue['name']} first event at index: {new_first_index}")
    log(f"   {second_venue['name']} first event at index: {new_second_index}")
    
    # Step 8: Verify the order changed
    log("\n[STEP 8] Verifying feed order changed...")
    
    # The venue we moved up (second_venue) should now appear BEFORE the other venue (first_venue)
    if new_second_index < new_first_index:
        log(f"✅ SUCCESS: Feed order changed correctly!")
        log(f"   Before reorder: {first_venue['name']} at {first_index}, {second_venue['name']} at {second_index}")
        log(f"   After reorder:  {first_venue['name']} at {new_first_index}, {second_venue['name']} at {new_second_index}")
        log(f"   → {second_venue['name']} now appears BEFORE {first_venue['name']} ✓")
    else:
        log(f"❌ FAILED: Feed order did NOT change as expected!")
        log(f"   Before reorder: {first_venue['name']} at {first_index}, {second_venue['name']} at {second_index}")
        log(f"   After reorder:  {first_venue['name']} at {new_first_index}, {second_venue['name']} at {new_second_index}")
        log(f"   → {second_venue['name']} still appears AFTER {first_venue['name']} ✗")
        return False
    
    # Step 9: Restore original order
    log("\n[STEP 9] Restoring original venue order...")
    resp = session.put(f"{BASE_URL}/admin/venues/reorder", json={"venue_ids": all_venue_ids})
    if resp.status_code != 200:
        log(f"⚠️  WARNING: Failed to restore original order (status {resp.status_code})")
    else:
        log(f"✅ Original venue order restored")
    
    # Step 10: Test authorization (non-admin should get 403)
    log("\n[STEP 10] Testing authorization (non-admin user)...")
    
    # Register a throwaway adult user
    timestamp = int(datetime.now().timestamp())
    test_email = f"testuser_{timestamp}@test.com"
    test_username = f"testuser{timestamp}"
    user_session = requests.Session()
    resp = user_session.post(f"{BASE_URL}/auth/register", json={
        "email": test_email,
        "password": "testpass123",
        "name": "Test User",
        "username": test_username,
        "birthdate": "1990-01-01",
        "city": "Ibiza"
    })
    
    if resp.status_code != 200:
        log(f"⚠️  WARNING: Could not create test user (status {resp.status_code})")
    else:
        log(f"✅ Created test user: {test_email}")
        
        # Try to reorder as non-admin
        resp = user_session.put(f"{BASE_URL}/admin/venues/reorder", json={"venue_ids": all_venue_ids})
        if resp.status_code == 403:
            log(f"✅ Non-admin correctly rejected with 403")
        else:
            log(f"❌ FAILED: Non-admin got status {resp.status_code} (expected 403)")
            return False
    
    log("\n" + "=" * 80)
    log("✅ ALL TESTS PASSED - Venue reordering bug fix verified!")
    log("=" * 80)
    return True


if __name__ == "__main__":
    try:
        success = test_venue_reorder_bug_fix()
        sys.exit(0 if success else 1)
    except Exception as e:
        log(f"\n❌ TEST FAILED WITH EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
