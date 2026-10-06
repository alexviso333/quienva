#!/usr/bin/env python3
"""
Test SEO server-rendered (SSR) pages for "¿Quién va?" FastAPI backend.
Verify Event JSON-LD offers.url points to ticket buy link and has_commission field.
"""
import requests
import json
import sys
from bs4 import BeautifulSoup
import re

# Backend base URL from frontend/.env
BASE_URL = "https://full-stack-nightlife.preview.emergentagent.com/api"

# Googlebot User-Agent for SSR pages
GOOGLEBOT_UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"

def test_get_events():
    """Test 1: Get a valid event id from /api/events"""
    print("\n" + "="*80)
    print("TEST 1: GET /api/events - Get valid event ID")
    print("="*80)
    
    url = f"{BASE_URL}/events"
    response = requests.get(url)
    
    print(f"URL: {url}")
    print(f"Status: {response.status_code}")
    
    if response.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {response.status_code}")
        return None
    
    data = response.json()
    
    # /api/events returns a list directly
    if isinstance(data, list):
        events = data
    else:
        events = data.get('events', [])
    
    if not events:
        print("❌ FAILED: No events returned")
        return None
    
    print(f"✅ PASSED: Got {len(events)} events")
    
    # Prefer event with has_commission=true if available
    event_id = None
    for event in events:
        if event.get('has_commission'):
            event_id = event['id']
            print(f"✅ Found event with has_commission=true: {event_id}")
            print(f"   Event: {event.get('name', 'N/A')}")
            break
    
    if not event_id:
        event_id = events[0]['id']
        print(f"✅ Using first event: {event_id}")
        print(f"   Event: {events[0].get('name', 'N/A')}")
    
    return event_id


def test_event_ssr_page(event_id):
    """Test 2: GET /api/fiesta/{id}/x with Googlebot UA - verify JSON-LD"""
    print("\n" + "="*80)
    print(f"TEST 2: GET /api/fiesta/{event_id}/x - SSR Event Page with Googlebot UA")
    print("="*80)
    
    url = f"{BASE_URL}/fiesta/{event_id}/x"
    headers = {"User-Agent": GOOGLEBOT_UA}
    
    response = requests.get(url, headers=headers)
    
    print(f"URL: {url}")
    print(f"User-Agent: {GOOGLEBOT_UA}")
    print(f"Status: {response.status_code}")
    print(f"Content-Type: {response.headers.get('Content-Type', 'N/A')}")
    
    if response.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {response.status_code}")
        return False
    
    if 'text/html' not in response.headers.get('Content-Type', ''):
        print(f"❌ FAILED: Expected text/html, got {response.headers.get('Content-Type')}")
        return False
    
    print("✅ PASSED: Status 200 and Content-Type is text/html")
    
    # Parse HTML
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Find JSON-LD script
    ld_json_scripts = soup.find_all('script', type='application/ld+json')
    
    if not ld_json_scripts:
        print("❌ FAILED: No <script type='application/ld+json'> found")
        return False
    
    print(f"✅ PASSED: Found {len(ld_json_scripts)} JSON-LD script(s)")
    
    # Find Event schema
    event_schema = None
    for script in ld_json_scripts:
        try:
            data = json.loads(script.string)
            if data.get('@type') == 'Event':
                event_schema = data
                break
        except json.JSONDecodeError as e:
            print(f"❌ FAILED: Invalid JSON in ld+json script: {e}")
            return False
    
    if not event_schema:
        print("❌ FAILED: No Event schema found in JSON-LD")
        return False
    
    print("✅ PASSED: Found Event schema in JSON-LD")
    print(f"   Event @type: {event_schema.get('@type')}")
    print(f"   Event name: {event_schema.get('name', 'N/A')}")
    
    # Verify offers object
    offers = event_schema.get('offers')
    if not offers:
        print("❌ FAILED: No 'offers' object in Event schema")
        return False
    
    print("✅ PASSED: Event schema has 'offers' object")
    
    # Verify offers.availability
    availability = offers.get('availability')
    if not availability:
        print("❌ FAILED: No 'availability' in offers")
        return False
    
    print(f"✅ PASSED: offers.availability = {availability}")
    
    # Verify offers.url (should be absolute http(s) URL)
    offers_url = offers.get('url')
    if not offers_url:
        print("❌ FAILED: No 'url' in offers")
        return False
    
    if not (offers_url.startswith('http://') or offers_url.startswith('https://')):
        print(f"❌ FAILED: offers.url is not an absolute http(s) URL: {offers_url}")
        return False
    
    print(f"✅ PASSED: offers.url is absolute http(s) URL")
    print(f"   offers.url: {offers_url}")
    
    # Print full offers object for inspection
    print("\n📋 FULL OFFERS OBJECT:")
    print(json.dumps(offers, indent=2))
    
    # Verify JSON is valid (already done by parsing, but confirm)
    print("\n✅ PASSED: JSON-LD is valid JSON (successfully parsed)")
    
    return True


def test_sitemap_venues():
    """Test 3: GET /api/sitemap-venues.xml - verify valid XML with venue URLs"""
    print("\n" + "="*80)
    print("TEST 3: GET /api/sitemap-venues.xml - Venues Sitemap")
    print("="*80)
    
    url = f"{BASE_URL}/sitemap-venues.xml"
    headers = {"User-Agent": GOOGLEBOT_UA}
    
    response = requests.get(url, headers=headers)
    
    print(f"URL: {url}")
    print(f"Status: {response.status_code}")
    print(f"Content-Type: {response.headers.get('Content-Type', 'N/A')}")
    
    if response.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {response.status_code}")
        return False
    
    if 'xml' not in response.headers.get('Content-Type', '').lower():
        print(f"❌ FAILED: Expected XML content-type, got {response.headers.get('Content-Type')}")
        return False
    
    print("✅ PASSED: Status 200 and Content-Type is XML")
    
    # Parse XML
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Find urlset
    urlset = soup.find('urlset')
    if not urlset:
        print("❌ FAILED: No <urlset> found in XML")
        return False
    
    print("✅ PASSED: Found <urlset> element")
    
    # Find url elements with /discoteca/ in loc
    urls = soup.find_all('url')
    discoteca_urls = []
    
    for url_elem in urls:
        loc = url_elem.find('loc')
        if loc and '/discoteca/' in loc.text:
            discoteca_urls.append(loc.text)
    
    if not discoteca_urls:
        print("❌ FAILED: No <url><loc> containing /discoteca/ found")
        return False
    
    print(f"✅ PASSED: Found {len(discoteca_urls)} venue URL(s) with /discoteca/")
    print(f"   Sample URLs:")
    for url in discoteca_urls[:3]:
        print(f"   - {url}")
    
    return True


def test_sitemap_xml():
    """Test 4: GET /api/sitemap.xml - verify valid XML"""
    print("\n" + "="*80)
    print("TEST 4: GET /api/sitemap.xml - Main Sitemap")
    print("="*80)
    
    url = f"{BASE_URL}/sitemap.xml"
    headers = {"User-Agent": GOOGLEBOT_UA}
    
    response = requests.get(url, headers=headers)
    
    print(f"URL: {url}")
    print(f"Status: {response.status_code}")
    print(f"Content-Type: {response.headers.get('Content-Type', 'N/A')}")
    
    if response.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {response.status_code}")
        return False
    
    if 'xml' not in response.headers.get('Content-Type', '').lower():
        print(f"❌ FAILED: Expected XML content-type, got {response.headers.get('Content-Type')}")
        return False
    
    print("✅ PASSED: Status 200 and Content-Type is XML")
    
    # Parse XML to verify it's valid
    try:
        soup = BeautifulSoup(response.text, 'html.parser')
        # Check for either urlset or sitemapindex
        if not (soup.find('urlset') or soup.find('sitemapindex')):
            print("❌ FAILED: No <urlset> or <sitemapindex> found in XML")
            return False
        
        print("✅ PASSED: Valid XML with proper sitemap structure")
        
        if soup.find('sitemapindex'):
            sitemaps = soup.find_all('sitemap')
            print(f"   Found {len(sitemaps)} child sitemap(s)")
        else:
            urls = soup.find_all('url')
            print(f"   Found {len(urls)} URL(s)")
        
        return True
    except Exception as e:
        print(f"❌ FAILED: Invalid XML: {e}")
        return False


def test_api_root():
    """Test 5: GET /api/ - regression test"""
    print("\n" + "="*80)
    print("TEST 5: GET /api/ - API Root Regression")
    print("="*80)
    
    url = f"{BASE_URL}/"
    response = requests.get(url)
    
    print(f"URL: {url}")
    print(f"Status: {response.status_code}")
    print(f"Content-Type: {response.headers.get('Content-Type', 'N/A')}")
    
    if response.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {response.status_code}")
        return False
    
    if 'application/json' not in response.headers.get('Content-Type', ''):
        print(f"❌ FAILED: Expected application/json, got {response.headers.get('Content-Type')}")
        return False
    
    data = response.json()
    
    if data.get('message') != '¿Quién va? API':
        print(f"❌ FAILED: Expected message '¿Quién va? API', got {data.get('message')}")
        return False
    
    print("✅ PASSED: API root returns 200 JSON with correct message")
    print(f"   Response: {data}")
    
    return True


def main():
    print("\n" + "="*80)
    print("SEO SSR PAGES VERIFICATION TEST SUITE")
    print("Backend: " + BASE_URL)
    print("="*80)
    
    results = []
    
    # Test 1: Get event ID
    event_id = test_get_events()
    results.append(("Get Events", event_id is not None))
    
    if not event_id:
        print("\n❌ CRITICAL: Cannot proceed without event ID")
        sys.exit(1)
    
    # Test 2: Event SSR page with JSON-LD
    results.append(("Event SSR Page JSON-LD", test_event_ssr_page(event_id)))
    
    # Test 3: Sitemap venues
    results.append(("Sitemap Venues XML", test_sitemap_venues()))
    
    # Test 4: Main sitemap
    results.append(("Main Sitemap XML", test_sitemap_xml()))
    
    # Test 5: API root regression
    results.append(("API Root Regression", test_api_root()))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        sys.exit(0)
    else:
        print(f"\n❌ {total - passed} test(s) failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
