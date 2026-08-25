#!/usr/bin/env python3
"""
Backend test for ClubTickets affiliate link ENFORCEMENT on ALL 15 clubs
+ UNVRS real prices + cross-provider dedup

Test items:
1) SCRAPER RUNS: 6 specific venues (hi-ibiza, ushuaia-ibiza, unvrs-ibiza, lio-ibiza, es-paradis-ibiza, 528-ibiza)
2) AFFILIATE LINK ENFORCED: ALL events from 15 clubs must have clubtickets.com with aff=CT226 (exactly ONE aff=)
3) PRICES KEPT/ADDED: Hï, Ushuaïa, [UNVRS] events must have prices
4) CROSS-PROVIDER DEDUP: No duplicate (venue, date, name) in Ibiza feed
5) DIRECTORY: All 15 clubs appear exactly once
6) REGRESSION: Palma works, no aff injection into non-clubtickets URLs
"""

import requests
import sys
from collections import defaultdict

# Backend URL from frontend/.env
BASE_URL = "https://production-deploy-26.preview.emergentagent.com/api"

# Admin credentials
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

# 15 target clubs
TARGET_CLUBS = [
    "Lío Ibiza",
    "Eden Ibiza", 
    "Es Paradis Ibiza",
    "Chinois Ibiza",
    "Swag Ibiza",
    "Ibiza Rocks",
    "[UNVRS]",
    "O Beach Ibiza",
    "528 Ibiza",
    "Baloo Ibiza",
    "Bambuku Ibiza",
    "Playa Soleil",
    "Teatro Pereyra",
    "Ushuaïa Ibiza",
    "Hï Ibiza"
]

# Scrapers to test (slug)
SCRAPERS_TO_TEST = [
    "hi-ibiza",
    "ushuaia-ibiza", 
    "unvrs-ibiza",
    "lio-ibiza",
    "es-paradis-ibiza",
    "528-ibiza"
]

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
    print(f"✓ Admin login successful, token: {token[:20]}...")
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

def test_scraper_runs(token):
    """Test 1: SCRAPER RUNS for 6 specific venues"""
    print("\n" + "="*80)
    print("TEST 1: SCRAPER RUNS")
    print("="*80)
    
    # Get all scrapers
    resp = requests.get(f"{BASE_URL}/admin/scrapers", 
        headers={"Authorization": f"Bearer {token}"}
    )
    print(f"GET /admin/scrapers → {resp.status_code}")
    if resp.status_code != 200:
        print(f"❌ FAIL: Could not get scrapers list")
        return False
    
    scrapers = resp.json()
    print(f"✓ Found {len(scrapers)} total scrapers")
    
    # Find scrapers by slug
    scraper_map = {}
    for scraper in scrapers:
        slug = scraper.get("slug")
        if slug in SCRAPERS_TO_TEST:
            scraper_map[slug] = scraper
    
    print(f"\nFound {len(scraper_map)}/{len(SCRAPERS_TO_TEST)} target scrapers")
    
    results = {}
    for slug in SCRAPERS_TO_TEST:
        if slug not in scraper_map:
            print(f"\n❌ FAIL: Scraper '{slug}' not found")
            results[slug] = {"found": False}
            continue
        
        scraper = scraper_map[slug]
        scraper_id = scraper.get("id")
        name = scraper.get("name", slug)
        
        print(f"\n--- Testing scraper: {name} (slug: {slug}) ---")
        
        # Run scraper
        resp = requests.post(f"{BASE_URL}/admin/scrapers/{scraper_id}/run",
            headers={"Authorization": f"Bearer {token}"}
        )
        print(f"POST /admin/scrapers/{scraper_id}/run → {resp.status_code}")
        
        if resp.status_code != 200:
            print(f"❌ FAIL: Scraper run failed: {resp.text}")
            results[slug] = {"found": True, "ok": False, "events": 0}
            continue
        
        data = resp.json()
        ok = data.get("ok", False)
        events = data.get("events", 0)
        source = data.get("source", "unknown")
        
        print(f"  ok: {ok}")
        print(f"  events: {events}")
        print(f"  source: {source}")
        
        if ok and events > 0:
            print(f"✓ PASS: {name} scraper returned {events} events")
            results[slug] = {"found": True, "ok": True, "events": events, "source": source}
        else:
            print(f"❌ FAIL: {name} scraper returned ok={ok}, events={events}")
            results[slug] = {"found": True, "ok": ok, "events": events}
    
    # Summary
    print("\n--- SCRAPER RUNS SUMMARY ---")
    all_passed = True
    for slug in SCRAPERS_TO_TEST:
        result = results.get(slug, {})
        if result.get("found") and result.get("ok") and result.get("events", 0) > 0:
            print(f"✓ {slug}: {result['events']} events")
        else:
            print(f"❌ {slug}: FAILED")
            all_passed = False
    
    return all_passed

def test_affiliate_enforcement(token):
    """Test 2: AFFILIATE LINK ENFORCED on ALL 15 clubs"""
    print("\n" + "="*80)
    print("TEST 2: AFFILIATE LINK ENFORCED (KEY FIX)")
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
    
    # Group events by venue
    events_by_venue = defaultdict(list)
    for event in events:
        venue_name = event.get("venue", "")
        events_by_venue[venue_name].append(event)
    
    print(f"\nChecking affiliate links for {len(TARGET_CLUBS)} target clubs...")
    
    all_passed = True
    club_results = {}
    
    for club_name in TARGET_CLUBS:
        club_events = events_by_venue.get(club_name, [])
        
        if not club_events:
            print(f"\n❌ FAIL: {club_name} - NO EVENTS FOUND")
            club_results[club_name] = {"events": 0, "passed": False}
            all_passed = False
            continue
        
        print(f"\n--- {club_name}: {len(club_events)} events ---")
        
        # Check each event
        non_clubtickets = []
        missing_aff = []
        duplicate_aff = []
        
        for event in club_events:
            commission_url = event.get("commission_url", "")
            
            # Must be clubtickets.com
            if "clubtickets.com" not in commission_url:
                non_clubtickets.append({
                    "name": event.get("name"),
                    "date": event.get("date"),
                    "url": commission_url
                })
                continue
            
            # Must have exactly ONE aff=CT226
            aff_count = commission_url.count("aff=")
            if "aff=CT226" not in commission_url:
                missing_aff.append({
                    "name": event.get("name"),
                    "date": event.get("date"),
                    "url": commission_url
                })
            elif aff_count > 1:
                duplicate_aff.append({
                    "name": event.get("name"),
                    "date": event.get("date"),
                    "url": commission_url
                })
        
        # Report results for this club
        if non_clubtickets:
            print(f"  ❌ {len(non_clubtickets)} events are NOT clubtickets.com:")
            for evt in non_clubtickets[:3]:  # Show first 3
                print(f"     - {evt['name']} ({evt['date']}): {evt['url'][:80]}")
            all_passed = False
        
        if missing_aff:
            print(f"  ❌ {len(missing_aff)} clubtickets events MISSING aff=CT226:")
            for evt in missing_aff[:3]:
                print(f"     - {evt['name']} ({evt['date']}): {evt['url'][:80]}")
            all_passed = False
        
        if duplicate_aff:
            print(f"  ❌ {len(duplicate_aff)} events have DUPLICATE aff= params:")
            for evt in duplicate_aff[:3]:
                print(f"     - {evt['name']} ({evt['date']}): {evt['url'][:80]}")
            all_passed = False
        
        passed = not non_clubtickets and not missing_aff and not duplicate_aff
        
        if passed:
            print(f"  ✓ PASS: All {len(club_events)} events have clubtickets.com with aff=CT226")
        
        club_results[club_name] = {
            "events": len(club_events),
            "non_clubtickets": len(non_clubtickets),
            "missing_aff": len(missing_aff),
            "duplicate_aff": len(duplicate_aff),
            "passed": passed
        }
    
    # Summary
    print("\n--- AFFILIATE ENFORCEMENT SUMMARY ---")
    for club_name in TARGET_CLUBS:
        result = club_results.get(club_name, {})
        if result.get("passed"):
            print(f"✓ {club_name}: {result['events']} events, all clubtickets with aff=CT226")
        else:
            print(f"❌ {club_name}: {result.get('events', 0)} events, " +
                  f"non_ct={result.get('non_clubtickets', 0)}, " +
                  f"missing_aff={result.get('missing_aff', 0)}, " +
                  f"dup_aff={result.get('duplicate_aff', 0)}")
    
    return all_passed

def test_prices_kept(token):
    """Test 3: PRICES KEPT/ADDED for Hï, Ushuaïa, [UNVRS]"""
    print("\n" + "="*80)
    print("TEST 3: PRICES KEPT/ADDED")
    print("="*80)
    
    # Get Ibiza events
    resp = requests.get(f"{BASE_URL}/events?city=Ibiza",
        headers={"Authorization": f"Bearer {token}"}
    )
    print(f"GET /events?city=Ibiza → {resp.status_code}")
    if resp.status_code != 200:
        print(f"❌ FAIL: Could not get events")
        return False
    
    events = resp.json()
    
    # Check specific venues
    target_venues = ["Hï Ibiza", "Ushuaïa Ibiza", "[UNVRS]"]
    
    all_passed = True
    for venue_name in target_venues:
        venue_events = [e for e in events if e.get("venue") == venue_name]
        
        if not venue_events:
            print(f"\n❌ FAIL: {venue_name} - NO EVENTS FOUND")
            all_passed = False
            continue
        
        print(f"\n--- {venue_name}: {len(venue_events)} events ---")
        
        # Check prices
        with_prices = 0
        without_prices = 0
        sample_prices = []
        
        for event in venue_events:
            price_tiers = event.get("price_tiers", [])
            if price_tiers and len(price_tiers) > 0:
                with_prices += 1
                if len(sample_prices) < 3:
                    sample_prices.append({
                        "name": event.get("name"),
                        "price": price_tiers[0].get("price", 0)
                    })
            else:
                without_prices += 1
        
        print(f"  Events with prices: {with_prices}/{len(venue_events)}")
        print(f"  Events without prices: {without_prices}/{len(venue_events)}")
        
        if sample_prices:
            print(f"  Sample prices:")
            for sp in sample_prices:
                print(f"    - {sp['name']}: {sp['price']}€")
        
        if with_prices > 0:
            print(f"  ✓ PASS: {venue_name} has events with prices")
        else:
            print(f"  ❌ FAIL: {venue_name} has NO events with prices")
            all_passed = False
    
    return all_passed

def test_cross_provider_dedup(token):
    """Test 4: CROSS-PROVIDER DEDUP - no duplicate (venue, date, name)"""
    print("\n" + "="*80)
    print("TEST 4: CROSS-PROVIDER DEDUP")
    print("="*80)
    
    # Get Ibiza events
    resp = requests.get(f"{BASE_URL}/events?city=Ibiza",
        headers={"Authorization": f"Bearer {token}"}
    )
    print(f"GET /events?city=Ibiza → {resp.status_code}")
    if resp.status_code != 200:
        print(f"❌ FAIL: Could not get events")
        return False
    
    events = resp.json()
    print(f"✓ Found {len(events)} total Ibiza events")
    
    # Check for duplicates by (venue, date, name)
    seen = {}
    duplicates = []
    
    for event in events:
        venue = event.get("venue", "")
        date = event.get("date", "")
        name = event.get("name", "")
        
        key = (venue, date, name)
        
        if key in seen:
            duplicates.append({
                "venue": venue,
                "date": date,
                "name": name,
                "event1": seen[key],
                "event2": event
            })
        else:
            seen[key] = event
    
    if duplicates:
        print(f"\n❌ FAIL: Found {len(duplicates)} duplicate event groups:")
        for dup in duplicates:
            print(f"\n  Duplicate: {dup['name']} at {dup['venue']} on {dup['date']}")
            print(f"    Event 1: {dup['event1'].get('commission_url', 'no url')[:80]}")
            print(f"    Event 2: {dup['event2'].get('commission_url', 'no url')[:80]}")
        return False
    else:
        print(f"✓ PASS: No duplicate events found (all {len(events)} events are unique by venue+date+name)")
        return True

def test_directory(token):
    """Test 5: DIRECTORY - all 15 clubs appear exactly once"""
    print("\n" + "="*80)
    print("TEST 5: DIRECTORY")
    print("="*80)
    
    # Get venues
    resp = requests.get(f"{BASE_URL}/venues?type=discoteca",
        headers={"Authorization": f"Bearer {token}"}
    )
    print(f"GET /venues?type=discoteca → {resp.status_code}")
    if resp.status_code != 200:
        print(f"❌ FAIL: Could not get venues: {resp.text}")
        return False
    
    venues = resp.json()
    print(f"✓ Found {len(venues)} total discoteca venues")
    
    # Count occurrences of each target club
    club_counts = {club: 0 for club in TARGET_CLUBS}
    
    for venue in venues:
        name = venue.get("name", "")
        if name in TARGET_CLUBS:
            club_counts[name] += 1
    
    # Check results
    all_passed = True
    print("\n--- DIRECTORY CHECK ---")
    for club_name in TARGET_CLUBS:
        count = club_counts[club_name]
        if count == 0:
            print(f"❌ {club_name}: NOT FOUND")
            all_passed = False
        elif count == 1:
            print(f"✓ {club_name}: appears exactly once")
        else:
            print(f"❌ {club_name}: appears {count} times (DUPLICATE)")
            all_passed = False
    
    return all_passed

def test_regression(token):
    """Test 6: REGRESSION - Palma works, no aff injection"""
    print("\n" + "="*80)
    print("TEST 6: REGRESSION")
    print("="*80)
    
    # Set city to Palma de Mallorca
    if not set_admin_city(token, "Palma de Mallorca"):
        return False
    
    # Get Palma events
    resp = requests.get(f"{BASE_URL}/events",
        headers={"Authorization": f"Bearer {token}"}
    )
    print(f"\nGET /events (Palma) → {resp.status_code}")
    if resp.status_code != 200:
        print(f"❌ FAIL: Could not get Palma events: {resp.text}")
        return False
    
    events = resp.json()
    print(f"✓ Found {len(events)} Palma events")
    
    if len(events) == 0:
        print(f"❌ FAIL: Palma has no events (regression)")
        return False
    
    # Check that non-clubtickets URLs don't have aff=CT226
    injected = []
    for event in events:
        commission_url = event.get("commission_url", "")
        if commission_url and "clubtickets.com" not in commission_url and "aff=CT226" in commission_url:
            injected.append({
                "name": event.get("name"),
                "venue": event.get("venue"),
                "url": commission_url
            })
    
    if injected:
        print(f"\n❌ FAIL: Found {len(injected)} non-clubtickets URLs with aff=CT226 injected:")
        for evt in injected[:3]:
            print(f"  - {evt['name']} at {evt['venue']}: {evt['url'][:80]}")
        return False
    else:
        print(f"✓ PASS: No aff=CT226 injected into non-clubtickets URLs")
    
    # Set city back to Ibiza
    set_admin_city(token, "Ibiza")
    
    return True

def main():
    print("="*80)
    print("CLUBTICKETS AFFILIATE ENFORCEMENT TESTING")
    print("="*80)
    
    # Login
    token = login_admin()
    
    # Set admin city to Ibiza
    if not set_admin_city(token, "Ibiza"):
        print("\n❌ CRITICAL: Could not set admin city to Ibiza")
        sys.exit(1)
    
    # Run tests
    results = {}
    
    results["scraper_runs"] = test_scraper_runs(token)
    results["affiliate_enforcement"] = test_affiliate_enforcement(token)
    results["prices_kept"] = test_prices_kept(token)
    results["cross_provider_dedup"] = test_cross_provider_dedup(token)
    results["directory"] = test_directory(token)
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
        sys.exit(0)
    else:
        print("\n❌ SOME TESTS FAILED")
        sys.exit(1)

if __name__ == "__main__":
    main()
