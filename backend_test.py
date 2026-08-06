#!/usr/bin/env python3
"""
Test script for affiliate system fix verification
Tests the fallback matching by (date + exact party name) + club name alias
"""

import requests
import json
from datetime import datetime

# Base URL from frontend/.env
BASE_URL = "https://event-scraper-hub-1.preview.emergentagent.com/api"

# Test credentials from memory/test_credentials.md
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

def log(msg):
    """Print timestamped log message"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def test_affiliate_system():
    """Test the affiliate system fix"""
    
    log("=" * 80)
    log("AFFILIATE SYSTEM FIX VERIFICATION")
    log("=" * 80)
    
    # Step 1: Login as admin
    log("\n[STEP 1] Login as admin...")
    login_resp = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert login_resp.status_code == 200, f"Login failed: {login_resp.status_code} {login_resp.text}"
    token = login_resp.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    log(f"✅ Admin login successful, token obtained")
    
    # Step 2: Get scraper IDs
    log("\n[STEP 2] Getting scraper IDs...")
    scrapers_resp = requests.get(f"{BASE_URL}/admin/scrapers", headers=headers)
    assert scrapers_resp.status_code == 200, f"Get scrapers failed: {scrapers_resp.status_code}"
    scrapers = scrapers_resp.json()
    log(f"✅ Retrieved {len(scrapers)} scrapers")
    
    # Find target scrapers
    target_venues = ["Chango Madrid", "Fitz Mallorca", "Fitz Madrid", "Amok Mallorca"]
    scraper_map = {}
    for scraper in scrapers:
        name = scraper.get("name", "")
        if any(target.lower() in name.lower() for target in target_venues):
            scraper_map[name] = scraper["id"]
            log(f"   Found: {name} (id: {scraper['id']})")
    
    # Step 3: Run scrapers for target venues
    log("\n[STEP 3] Running scrapers for target venues...")
    for venue_name, scraper_id in scraper_map.items():
        log(f"   Running scraper for {venue_name}...")
        run_resp = requests.post(
            f"{BASE_URL}/admin/scrapers/{scraper_id}/run",
            headers=headers
        )
        if run_resp.status_code == 200:
            result = run_resp.json()
            log(f"   ✅ {venue_name}: ok={result.get('ok')}, events={result.get('events', 0)}")
        else:
            log(f"   ⚠️ {venue_name}: {run_resp.status_code} {run_resp.text[:100]}")
    
    # Step 4: Refresh affiliate data
    log("\n[STEP 4] Refreshing affiliate data...")
    refresh_resp = requests.post(f"{BASE_URL}/admin/affiliate-refresh", headers=headers)
    assert refresh_resp.status_code == 200, f"Affiliate refresh failed: {refresh_resp.status_code}"
    refresh_data = refresh_resp.json()
    log(f"✅ Affiliate refresh successful: slug={refresh_data.get('slug')}, mine_count={refresh_data.get('mine_count')}")
    
    # Step 5: Get affiliate status and verify
    log("\n[STEP 5] Getting affiliate status...")
    status_resp = requests.get(f"{BASE_URL}/admin/affiliate-status", headers=headers)
    assert status_resp.status_code == 200, f"Affiliate status failed: {status_resp.status_code}"
    status_data = status_resp.json()
    
    matched_count = status_data.get("matched_count", 0)
    venues_data = status_data.get("venues", [])
    
    log(f"✅ Affiliate status retrieved:")
    log(f"   - slug: {status_data.get('slug')}")
    log(f"   - mine_count: {status_data.get('mine_count')}")
    log(f"   - matched_count: {matched_count}")
    log(f"   - venues: {len(venues_data)}")
    
    # Verify matched_count > 0
    assert matched_count > 0, f"❌ FAIL: matched_count should be > 0, got {matched_count}"
    log(f"✅ PASS: matched_count = {matched_count} (> 0)")
    
    # Check CHANGO venues
    log("\n   Checking CHANGO venues...")
    chango_venues = [v for v in venues_data if "CHANGO" in v.get("venue", "").upper()]
    if chango_venues:
        for cv in chango_venues:
            venue_name = cv.get("venue")
            events = cv.get("events", 0)
            matched = cv.get("matched", 0)
            log(f"   - {venue_name}: events={events}, matched={matched}")
            assert matched > 0, f"❌ FAIL: {venue_name} should have matched > 0, got {matched}"
        log(f"✅ PASS: All CHANGO venues have matched > 0")
    else:
        log(f"⚠️ WARNING: No CHANGO venues found in affiliate status")
    
    # Step 6: Test Madrid feed with Chango events
    log("\n[STEP 6] Testing Madrid feed for Chango events...")
    
    # Set city to Madrid
    profile_resp = requests.put(
        f"{BASE_URL}/auth/profile",
        headers=headers,
        json={"city": "Madrid"}
    )
    assert profile_resp.status_code == 200, f"Profile update failed: {profile_resp.status_code}"
    log(f"✅ City set to Madrid")
    
    # Get events
    events_resp = requests.get(
        f"{BASE_URL}/events?date_filter=all",
        headers=headers
    )
    assert events_resp.status_code == 200, f"Get events failed: {events_resp.status_code}"
    events = events_resp.json()
    log(f"✅ Retrieved {len(events)} events for Madrid")
    
    # Filter Chango events
    chango_events = [e for e in events if "chango" in e.get("venue", "").lower()]
    log(f"   Found {len(chango_events)} Chango events")
    
    # Check for "Vacanciones" and "CHANGO" events with is_affiliate=true
    vacanciones_events = [e for e in chango_events if "vacanciones" in e.get("name", "").lower() and e.get("is_affiliate") is True]
    chango_name_events = [e for e in chango_events if "chango" in e.get("name", "").lower() and e.get("is_affiliate") is True]
    
    log(f"   - Events with 'Vacanciones' and is_affiliate=true: {len(vacanciones_events)}")
    if vacanciones_events:
        for ev in vacanciones_events[:3]:  # Show first 3
            log(f"     • {ev.get('name')} at {ev.get('venue')} - commission_url: {ev.get('commission_url', '')[:80]}...")
    
    log(f"   - Events with 'CHANGO' in name and is_affiliate=true: {len(chango_name_events)}")
    if chango_name_events:
        for ev in chango_name_events[:3]:  # Show first 3
            log(f"     • {ev.get('name')} at {ev.get('venue')} - commission_url: {ev.get('commission_url', '')[:80]}...")
    
    # Verify at least some affiliate events exist
    affiliate_chango = [e for e in chango_events if e.get("is_affiliate") is True]
    if affiliate_chango:
        log(f"✅ PASS: Found {len(affiliate_chango)} Chango events with is_affiliate=true")
        
        # Verify commission_url format
        for ev in affiliate_chango[:5]:
            commission_url = ev.get("commission_url", "")
            if commission_url:
                assert commission_url.startswith("https://www.fourvenues.com/quienva/events/"), \
                    f"❌ FAIL: commission_url should start with 'https://www.fourvenues.com/quienva/events/', got {commission_url}"
        log(f"✅ PASS: Commission URLs correctly formatted")
    else:
        log(f"⚠️ WARNING: No Chango events with is_affiliate=true found")
    
    # Step 7: Verify ordering regression
    log("\n[STEP 7] Verifying feed ordering (affiliate first, then price descending)...")
    
    # Get all Madrid events
    all_events = events
    
    # Find first non-affiliate event
    first_non_affiliate_idx = None
    for i, ev in enumerate(all_events):
        if ev.get("is_affiliate") is False:
            first_non_affiliate_idx = i
            break
    
    # Verify all affiliate events come before non-affiliate
    affiliate_events = [e for e in all_events if e.get("is_affiliate") is True]
    if affiliate_events:
        log(f"   Found {len(affiliate_events)} affiliate events")
        
        # Check that all affiliate events are at the beginning
        for i, ev in enumerate(all_events[:len(affiliate_events)]):
            if ev.get("is_affiliate") is not True:
                log(f"❌ FAIL: Non-affiliate event found at position {i} before all affiliate events")
                log(f"   Event: {ev.get('name')} at {ev.get('venue')}")
                break
        else:
            log(f"✅ PASS: All affiliate events appear before non-affiliate events")
        
        # Check price ordering within affiliate events
        affiliate_prices = [e.get("current_price") for e in affiliate_events if e.get("current_price") is not None]
        if len(affiliate_prices) > 1:
            is_descending = all(affiliate_prices[i] >= affiliate_prices[i+1] for i in range(len(affiliate_prices)-1))
            if is_descending:
                log(f"✅ PASS: Affiliate events sorted by price descending: {affiliate_prices[:10]}")
            else:
                log(f"⚠️ WARNING: Affiliate events NOT sorted by price descending: {affiliate_prices[:10]}")
    else:
        log(f"⚠️ No affiliate events found in Madrid feed")
    
    # Step 8: Test Palma feed
    log("\n[STEP 8] Testing Palma de Mallorca feed...")
    
    # Set city to Palma
    profile_resp = requests.put(
        f"{BASE_URL}/auth/profile",
        headers=headers,
        json={"city": "Palma de Mallorca"}
    )
    assert profile_resp.status_code == 200, f"Profile update failed: {profile_resp.status_code}"
    log(f"✅ City set to Palma de Mallorca")
    
    # Get events
    events_resp = requests.get(
        f"{BASE_URL}/events?date_filter=all",
        headers=headers
    )
    assert events_resp.status_code == 200, f"Get events failed: {events_resp.status_code}"
    palma_events = events_resp.json()
    log(f"✅ Retrieved {len(palma_events)} events for Palma")
    
    # Check Fitz Mallorca events
    fitz_events = [e for e in palma_events if "fitz" in e.get("venue", "").lower() and "mallorca" in e.get("venue", "").lower()]
    fitz_affiliate = [e for e in fitz_events if e.get("is_affiliate") is True]
    log(f"   - Fitz Mallorca events: {len(fitz_events)}, with is_affiliate=true: {len(fitz_affiliate)}")
    
    if fitz_affiliate:
        log(f"✅ PASS: Fitz Mallorca events have is_affiliate=true")
        for ev in fitz_affiliate[:3]:
            log(f"     • {ev.get('name')} on {ev.get('date')}")
    else:
        log(f"⚠️ WARNING: No Fitz Mallorca events with is_affiliate=true")
    
    # Check AMOK event on 2026-09-05
    amok_events = [e for e in palma_events if "amok" in e.get("venue", "").lower()]
    amok_sept_5 = [e for e in amok_events if e.get("date") == "2026-09-05" and "tardeo" in e.get("name", "").lower() and "reggaeton" in e.get("name", "").lower()]
    
    log(f"   - AMOK events: {len(amok_events)}")
    log(f"   - AMOK event on 2026-09-05 'El Tardeo de Reggaeton Viejo': {len(amok_sept_5)}")
    
    if amok_sept_5:
        ev = amok_sept_5[0]
        log(f"     • Found: {ev.get('name')} on {ev.get('date')}")
        log(f"     • is_affiliate: {ev.get('is_affiliate')}")
        if ev.get("is_affiliate") is True:
            log(f"✅ PASS: AMOK 'El Tardeo de Reggaeton Viejo' on 2026-09-05 correctly marked as affiliate")
        else:
            log(f"❌ FAIL: AMOK event should have is_affiliate=true, got {ev.get('is_affiliate')}")
    else:
        log(f"⚠️ WARNING: AMOK 'El Tardeo de Reggaeton Viejo' on 2026-09-05 not found")
    
    # Check for massive false positives (other AMOK events should NOT be marked)
    other_amok = [e for e in amok_events if e.get("date") != "2026-09-05" and e.get("is_affiliate") is True]
    if other_amok:
        log(f"⚠️ WARNING: Found {len(other_amok)} other AMOK events marked as affiliate (potential false positives)")
        for ev in other_amok[:5]:
            log(f"     • {ev.get('name')} on {ev.get('date')}")
    else:
        log(f"✅ PASS: No massive false positives - other AMOK events not marked")
    
    log("\n" + "=" * 80)
    log("AFFILIATE SYSTEM FIX VERIFICATION COMPLETE")
    log("=" * 80)

if __name__ == "__main__":
    try:
        test_affiliate_system()
    except AssertionError as e:
        log(f"\n❌ TEST FAILED: {e}")
        exit(1)
    except Exception as e:
        log(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
