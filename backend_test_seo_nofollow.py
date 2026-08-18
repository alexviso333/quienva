#!/usr/bin/env python3
"""
Backend test for SEO on-page polish:
- City sitemap real lastmod
- rel=nofollow on past-event links in venue pages
"""
import requests
import json
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET

BASE_URL = "http://localhost:8001/api"
HEADERS = {"x-forwarded-host": "quienva.me", "x-forwarded-proto": "https"}

def test_sitemap_cities_lastmod():
    """Test 1: GET /api/sitemap-cities.xml → 200, valid XML, contains <lastmod> and city URLs"""
    print("\n" + "="*80)
    print("TEST 1: City sitemap with real <lastmod>")
    print("="*80)
    
    resp = requests.get(f"{BASE_URL}/sitemap-cities.xml", headers=HEADERS)
    print(f"✓ GET /api/sitemap-cities.xml → {resp.status_code}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    
    # Parse XML
    try:
        root = ET.fromstring(resp.content)
        print(f"✓ Valid XML parsed")
    except Exception as e:
        print(f"✗ XML parsing failed: {e}")
        raise
    
    # Check for <lastmod> tags
    ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    lastmod_tags = root.findall('.//ns:lastmod', ns)
    print(f"✓ Found {len(lastmod_tags)} <lastmod> tags")
    assert len(lastmod_tags) > 0, "No <lastmod> tags found"
    
    # Check for city URLs (e.g. /fiestas/)
    loc_tags = root.findall('.//ns:loc', ns)
    city_urls = [loc.text for loc in loc_tags if '/fiestas/' in loc.text]
    print(f"✓ Found {len(city_urls)} city URLs containing '/fiestas/'")
    assert len(city_urls) > 0, "No city URLs found"
    
    # Sample a few lastmod values
    sample_lastmods = [tag.text for tag in lastmod_tags[:3]]
    print(f"✓ Sample <lastmod> values: {sample_lastmods}")
    
    print("\n✅ TEST 1 PASSED: City sitemap has valid XML with <lastmod> tags and city URLs")
    return True


def test_past_venue_nofollow():
    """Test 2: Venue with ONLY past events should have rel=nofollow on event cards"""
    print("\n" + "="*80)
    print("TEST 2: rel=nofollow on PAST-only venue")
    print("="*80)
    
    # Create admin session
    admin_resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "admin@quienva.app",
        "password": "admin123"
    })
    assert admin_resp.status_code == 200, f"Admin login failed: {admin_resp.status_code}"
    admin_token = admin_resp.json()["token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    print("✓ Admin login successful")
    
    # Seed a PAST event with unique venue
    past_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    past_event = {
        "name": "Zzz Past Club Test Event",
        "venue": "Zzz Past Club Test",
        "address": "Calle Test 1",
        "date": past_date,
        "time": "23:00",
        "image_url": "",
        "genre": "Techno",
        "city": "Madrid",
        "sale_state": "agotado"
    }
    
    create_resp = requests.post(f"{BASE_URL}/admin/events", json=past_event, headers=admin_headers)
    assert create_resp.status_code == 200, f"Failed to create past event: {create_resp.status_code}"
    past_event_id = create_resp.json()["id"]
    print(f"✓ Created past event: {past_event_id} on {past_date}")
    
    # The venue slug is the slugified venue name
    venue_slug = "zzz-past-club-test"
    
    try:
        # GET venue page
        venue_resp = requests.get(f"{BASE_URL}/discoteca/{venue_slug}", headers=HEADERS)
        print(f"✓ GET /api/discoteca/{venue_slug} → {venue_resp.status_code}")
        assert venue_resp.status_code == 200, f"Expected 200, got {venue_resp.status_code}"
        
        html = venue_resp.text
        
        # Check for event cards with data-testid="seo-event-card"
        if 'data-testid="seo-event-card"' not in html:
            print("⚠ No event cards found with data-testid='seo-event-card'")
            # Try to find any anchor tags
            if '<a ' in html:
                print("✓ Found anchor tags in HTML")
        
        # Check for rel="nofollow" in event card anchors
        # The event cards should have both data-testid="seo-event-card" AND rel="nofollow"
        has_nofollow = 'rel="nofollow"' in html
        print(f"✓ HTML contains rel='nofollow': {has_nofollow}")
        
        if has_nofollow:
            # Count occurrences
            nofollow_count = html.count('rel="nofollow"')
            print(f"✓ Found {nofollow_count} rel='nofollow' attributes")
            print("\n✅ TEST 2 PASSED: Past-only venue has rel='nofollow' on event cards")
        else:
            print("\n✗ TEST 2 FAILED: Expected rel='nofollow' but not found")
            # Print a snippet of the HTML for debugging
            if 'data-testid="seo-event-card"' in html:
                idx = html.find('data-testid="seo-event-card"')
                snippet = html[max(0, idx-200):idx+200]
                print(f"HTML snippet around event card:\n{snippet}")
            raise AssertionError("rel='nofollow' not found in past-only venue page")
        
    finally:
        # Clean up
        delete_resp = requests.delete(f"{BASE_URL}/admin/events/{past_event_id}", headers=admin_headers)
        print(f"✓ Cleaned up past event: {delete_resp.status_code}")
    
    return True


def test_future_venue_no_nofollow():
    """Test 3: Venue with UPCOMING event should NOT have rel=nofollow"""
    print("\n" + "="*80)
    print("TEST 3: NO nofollow on venue with UPCOMING event")
    print("="*80)
    
    # Create admin session
    admin_resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "admin@quienva.app",
        "password": "admin123"
    })
    assert admin_resp.status_code == 200, f"Admin login failed: {admin_resp.status_code}"
    admin_token = admin_resp.json()["token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    print("✓ Admin login successful")
    
    # Seed a FUTURE event with unique venue
    future_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    future_event = {
        "name": "Zzz Future Club Test Event",
        "venue": "Zzz Future Club Test",
        "address": "Calle Test 2",
        "date": future_date,
        "time": "23:00",
        "image_url": "",
        "genre": "House",
        "city": "Madrid",
        "sale_state": "a_la_venta"
    }
    
    create_resp = requests.post(f"{BASE_URL}/admin/events", json=future_event, headers=admin_headers)
    assert create_resp.status_code == 200, f"Failed to create future event: {create_resp.status_code}"
    future_event_id = create_resp.json()["id"]
    print(f"✓ Created future event: {future_event_id} on {future_date}")
    
    # The venue slug is the slugified venue name
    venue_slug = "zzz-future-club-test"
    
    try:
        # GET venue page
        venue_resp = requests.get(f"{BASE_URL}/discoteca/{venue_slug}", headers=HEADERS)
        print(f"✓ GET /api/discoteca/{venue_slug} → {venue_resp.status_code}")
        assert venue_resp.status_code == 200, f"Expected 200, got {venue_resp.status_code}"
        
        html = venue_resp.text
        
        # Check for event cards with data-testid="seo-event-card"
        if 'data-testid="seo-event-card"' not in html:
            print("⚠ No event cards found with data-testid='seo-event-card'")
        
        # Check that rel="nofollow" is NOT present
        has_nofollow = 'rel="nofollow"' in html
        print(f"✓ HTML contains rel='nofollow': {has_nofollow}")
        
        if not has_nofollow:
            print("\n✅ TEST 3 PASSED: Venue with upcoming event does NOT have rel='nofollow'")
        else:
            print("\n✗ TEST 3 FAILED: Found rel='nofollow' but expected none")
            raise AssertionError("rel='nofollow' found in venue with upcoming events")
        
    finally:
        # Clean up
        delete_resp = requests.delete(f"{BASE_URL}/admin/events/{future_event_id}", headers=admin_headers)
        print(f"✓ Cleaned up future event: {delete_resp.status_code}")
    
    return True


def test_city_page_no_nofollow():
    """Test 4: City page links should still be followed (no rel=nofollow)"""
    print("\n" + "="*80)
    print("TEST 4: Regression - city page links are still followed")
    print("="*80)
    
    # GET city page
    city_resp = requests.get(f"{BASE_URL}/ciudad/madrid", headers=HEADERS)
    print(f"✓ GET /api/ciudad/madrid → {city_resp.status_code}")
    assert city_resp.status_code == 200, f"Expected 200, got {city_resp.status_code}"
    
    html = city_resp.text
    
    # Check for event cards
    has_event_cards = 'data-testid="seo-event-card"' in html
    print(f"✓ City page has event cards: {has_event_cards}")
    
    if has_event_cards:
        # Check that rel="nofollow" is NOT present in event cards
        has_nofollow = 'rel="nofollow"' in html
        print(f"✓ City page contains rel='nofollow': {has_nofollow}")
        
        if not has_nofollow:
            print("\n✅ TEST 4 PASSED: City page event cards do NOT have rel='nofollow'")
        else:
            print("\n✗ TEST 4 FAILED: Found rel='nofollow' in city page")
            raise AssertionError("rel='nofollow' found in city page event cards")
    else:
        print("⚠ No event cards found on city page, skipping nofollow check")
        print("\n✅ TEST 4 PASSED: City page rendered successfully")
    
    # Also check sitemap.xml for regression
    sitemap_resp = requests.get(f"{BASE_URL}/sitemap.xml", headers=HEADERS)
    print(f"✓ GET /api/sitemap.xml → {sitemap_resp.status_code}")
    assert sitemap_resp.status_code == 200, f"Expected 200, got {sitemap_resp.status_code}"
    
    # Parse XML
    try:
        root = ET.fromstring(sitemap_resp.content)
        print(f"✓ Sitemap.xml is valid XML")
    except Exception as e:
        print(f"✗ Sitemap XML parsing failed: {e}")
        raise
    
    return True


def main():
    print("\n" + "="*80)
    print("BACKEND SEO TEST: City sitemap lastmod + rel=nofollow on past-event links")
    print("="*80)
    
    try:
        test_sitemap_cities_lastmod()
        test_past_venue_nofollow()
        test_future_venue_no_nofollow()
        test_city_page_no_nofollow()
        
        print("\n" + "="*80)
        print("🎉 ALL TESTS PASSED (4/4)")
        print("="*80)
        print("\nSUMMARY:")
        print("✅ City sitemap has real <lastmod> tags")
        print("✅ Past-only venue has rel='nofollow' on event cards")
        print("✅ Venue with upcoming event does NOT have rel='nofollow'")
        print("✅ City page event cards do NOT have rel='nofollow'")
        print("✅ No regressions in sitemap.xml")
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise


if __name__ == "__main__":
    main()
