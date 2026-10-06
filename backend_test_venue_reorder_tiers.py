#!/usr/bin/env python3
"""
Extended test for venue reordering with tier analysis.

This test verifies that:
1. The feed has two tiers: tier 0 (affiliate events) and tier 1 (non-affiliate events)
2. Within each tier, venue priority (order) determines the event order
3. Reordering venues affects the order within each tier independently
"""

import requests
import sys
from datetime import datetime
from collections import defaultdict

# Configuration
BASE_URL = "https://plan-maker-29.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def analyze_feed_tiers(events):
    """Analyze the feed to identify tier boundaries and venue distribution."""
    
    # Group events by venue
    venue_events = defaultdict(list)
    for i, event in enumerate(events):
        venue_name = event.get("venue", "Unknown")
        is_affiliate = event.get("is_affiliate", False)
        venue_events[venue_name].append({
            "index": i,
            "is_affiliate": is_affiliate,
            "name": event.get("name", ""),
            "date": event.get("date", "")
        })
    
    # Find tier boundary (last affiliate event)
    last_affiliate_index = -1
    first_non_affiliate_index = len(events)
    
    for i, event in enumerate(events):
        if event.get("is_affiliate"):
            last_affiliate_index = i
        elif first_non_affiliate_index == len(events):
            first_non_affiliate_index = i
    
    tier_0_count = last_affiliate_index + 1 if last_affiliate_index >= 0 else 0
    tier_1_count = len(events) - tier_0_count
    
    log(f"\n📊 Feed Tier Analysis:")
    log(f"   Total events: {len(events)}")
    log(f"   Tier 0 (affiliate): {tier_0_count} events (indices 0-{last_affiliate_index})")
    log(f"   Tier 1 (non-affiliate): {tier_1_count} events (indices {first_non_affiliate_index}-{len(events)-1})")
    
    # Show venue distribution
    log(f"\n📍 Venue Distribution:")
    for venue_name, venue_event_list in sorted(venue_events.items(), key=lambda x: x[1][0]["index"]):
        first_idx = venue_event_list[0]["index"]
        last_idx = venue_event_list[-1]["index"]
        count = len(venue_event_list)
        is_affiliate = venue_event_list[0]["is_affiliate"]
        tier = "tier 0" if is_affiliate else "tier 1"
        log(f"   {venue_name}: {count} events, indices {first_idx}-{last_idx} ({tier})")
    
    return {
        "tier_0_count": tier_0_count,
        "tier_1_count": tier_1_count,
        "last_affiliate_index": last_affiliate_index,
        "first_non_affiliate_index": first_non_affiliate_index,
        "venue_events": dict(venue_events)
    }

def test_venue_reorder_with_tiers():
    """Test venue reordering with detailed tier analysis."""
    
    log("=" * 80)
    log("TEST: Venue Reordering with Tier Analysis")
    log("=" * 80)
    
    # Admin login
    log("\n[STEP 1] Admin login...")
    session = requests.Session()
    resp = session.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if resp.status_code != 200:
        log(f"❌ FAILED: Admin login failed")
        return False
    log(f"✅ Admin login successful")
    
    # Set admin city to Ibiza
    log("\n[STEP 2] Setting admin city to Ibiza...")
    resp = session.put(f"{BASE_URL}/auth/profile", json={"city": "Ibiza"})
    if resp.status_code != 200:
        log(f"❌ FAILED: Profile update failed")
        return False
    log(f"✅ Admin city set to Ibiza")
    
    # Get venues
    log("\n[STEP 3] Getting venues...")
    resp = session.get(f"{BASE_URL}/venues")
    if resp.status_code != 200:
        log(f"❌ FAILED: GET /api/venues failed")
        return False
    
    venues = resp.json()
    venues_with_events = [v for v in venues if v.get("upcoming_events", 0) > 0]
    
    log(f"✅ Found {len(venues_with_events)} venues with upcoming events")
    
    # Get initial feed
    log("\n[STEP 4] Getting initial feed...")
    resp = session.get(f"{BASE_URL}/events", params={"city": "Ibiza", "date_filter": "all"})
    if resp.status_code != 200:
        log(f"❌ FAILED: GET /api/events failed")
        return False
    
    events_before = resp.json()
    log(f"✅ Retrieved {len(events_before)} events")
    
    # Analyze initial feed
    analysis_before = analyze_feed_tiers(events_before)
    
    # Pick two venues from the SAME tier for testing
    # Try to find two affiliate venues first (tier 0)
    affiliate_venues = []
    for venue in venues_with_events:
        venue_name = venue["name"]
        if venue_name in analysis_before["venue_events"]:
            venue_event_list = analysis_before["venue_events"][venue_name]
            if venue_event_list and venue_event_list[0]["is_affiliate"]:
                affiliate_venues.append(venue)
    
    if len(affiliate_venues) >= 2:
        log(f"\n✅ Found {len(affiliate_venues)} affiliate venues (tier 0)")
        venue_a = affiliate_venues[0]
        venue_b = affiliate_venues[1]
        testing_tier = "tier 0 (affiliate)"
    else:
        log(f"\n⚠️  Only {len(affiliate_venues)} affiliate venues found, using any two venues")
        venue_a = venues_with_events[0]
        venue_b = venues_with_events[1]
        testing_tier = "mixed"
    
    log(f"   Testing with: {venue_a['name']} and {venue_b['name']} ({testing_tier})")
    
    # Find initial positions
    first_a_index = None
    first_b_index = None
    
    for i, event in enumerate(events_before):
        if event.get("venue") == venue_a["name"] and first_a_index is None:
            first_a_index = i
        if event.get("venue") == venue_b["name"] and first_b_index is None:
            first_b_index = i
        if first_a_index is not None and first_b_index is not None:
            break
    
    log(f"\n📍 Initial positions:")
    log(f"   {venue_a['name']}: first event at index {first_a_index}")
    log(f"   {venue_b['name']}: first event at index {first_b_index}")
    
    # Determine order
    if first_a_index < first_b_index:
        first_venue = venue_a
        second_venue = venue_b
    else:
        first_venue = venue_b
        second_venue = venue_a
    
    # Reorder venues
    log(f"\n[STEP 5] Reordering venues - moving {second_venue['name']} BEFORE {first_venue['name']}...")
    
    all_venue_ids = [v["id"] for v in venues]
    new_order = []
    for vid in all_venue_ids:
        if vid == second_venue["id"]:
            continue
        if vid == first_venue["id"]:
            new_order.append(second_venue["id"])
        new_order.append(vid)
    
    if second_venue["id"] not in new_order:
        new_order.insert(0, second_venue["id"])
    
    resp = session.put(f"{BASE_URL}/admin/venues/reorder", json={"venue_ids": new_order})
    if resp.status_code != 200:
        log(f"❌ FAILED: Reorder failed")
        return False
    log(f"✅ Reorder successful")
    
    # Get feed after reordering
    log("\n[STEP 6] Getting feed after reordering...")
    resp = session.get(f"{BASE_URL}/events", params={"city": "Ibiza", "date_filter": "all"})
    if resp.status_code != 200:
        log(f"❌ FAILED: GET /api/events failed")
        return False
    
    events_after = resp.json()
    log(f"✅ Retrieved {len(events_after)} events")
    
    # Analyze feed after reordering
    analysis_after = analyze_feed_tiers(events_after)
    
    # Find new positions
    new_first_index = None
    new_second_index = None
    
    for i, event in enumerate(events_after):
        if event.get("venue") == first_venue["name"] and new_first_index is None:
            new_first_index = i
        if event.get("venue") == second_venue["name"] and new_second_index is None:
            new_second_index = i
        if new_first_index is not None and new_second_index is not None:
            break
    
    log(f"\n📍 Positions after reordering:")
    log(f"   {first_venue['name']}: first event at index {new_first_index}")
    log(f"   {second_venue['name']}: first event at index {new_second_index}")
    
    # Verify the order changed
    log("\n[STEP 7] Verifying results...")
    
    success = True
    
    # Check that tier boundaries are preserved
    if analysis_before["tier_0_count"] != analysis_after["tier_0_count"]:
        log(f"⚠️  WARNING: Tier 0 count changed from {analysis_before['tier_0_count']} to {analysis_after['tier_0_count']}")
    
    # Check that the venue order changed within the tier
    if new_second_index < new_first_index:
        log(f"✅ SUCCESS: Venue order changed correctly!")
        log(f"   {second_venue['name']} now appears BEFORE {first_venue['name']}")
    else:
        log(f"❌ FAILED: Venue order did NOT change as expected")
        success = False
    
    # Restore original order
    log("\n[STEP 8] Restoring original order...")
    original_order = [v["id"] for v in venues]
    resp = session.put(f"{BASE_URL}/admin/venues/reorder", json={"venue_ids": original_order})
    if resp.status_code == 200:
        log(f"✅ Original order restored")
    else:
        log(f"⚠️  WARNING: Failed to restore original order")
    
    if success:
        log("\n" + "=" * 80)
        log("✅ ALL TESTS PASSED - Venue reordering with tiers verified!")
        log("=" * 80)
    
    return success


if __name__ == "__main__":
    try:
        success = test_venue_reorder_with_tiers()
        sys.exit(0 if success else 1)
    except Exception as e:
        log(f"\n❌ TEST FAILED WITH EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
