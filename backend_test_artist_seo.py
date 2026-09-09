#!/usr/bin/env python3
"""
Backend test for Artist/DJ SEO pages
Tests the new /artista/{slug} endpoints with Googlebot User-Agent
"""
import requests
import json
import sys
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET

# Backend base URL from frontend/.env
BASE_URL = "https://quienva-events.preview.emergentagent.com/api"

# Googlebot User-Agent for SSR pages
GOOGLEBOT_UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"

def test_artist_page_with_events():
    """
    Test 1: GET {BASE}/api/artista/carl-cox (Googlebot UA)
    Expect: 200, HTML with <h1> containing artist name, valid JSON-LD with @type:Event and offers,
    canonical link, hreflang links
    """
    print("\n" + "="*80)
    print("TEST 1: Artist page with events (carl-cox)")
    print("="*80)
    
    # Try multiple artist slugs in case one doesn't have events
    test_artists = ["carl-cox", "david-guetta", "anyma", "fisher", "solomun"]
    
    for slug in test_artists:
        url = f"{BASE_URL}/artista/{slug}"
        print(f"\nTrying: {url}")
        
        headers = {"User-Agent": GOOGLEBOT_UA}
        response = requests.get(url, headers=headers, allow_redirects=False)
        
        print(f"Status: {response.status_code}")
        
        if response.status_code == 404:
            print(f"  ❌ {slug} returned 404 (no upcoming events), trying next...")
            continue
        
        if response.status_code != 200:
            print(f"  ❌ Expected 200, got {response.status_code}")
            continue
        
        # Parse HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Check for <h1> containing artist name
        h1 = soup.find('h1')
        if not h1:
            print(f"  ❌ No <h1> found")
            continue
        
        h1_text = h1.get_text()
        print(f"  ✅ Found <h1>: {h1_text[:100]}")
        
        # Check for canonical link
        canonical = soup.find('link', rel='canonical')
        if not canonical:
            print(f"  ❌ No canonical link found")
            return False
        print(f"  ✅ Canonical link: {canonical.get('href')}")
        
        # Check for hreflang links
        hreflang_links = soup.find_all('link', rel='alternate', hreflang=True)
        if len(hreflang_links) < 3:
            print(f"  ❌ Expected at least 3 hreflang links (es/en/de), found {len(hreflang_links)}")
            return False
        print(f"  ✅ Found {len(hreflang_links)} hreflang links")
        for link in hreflang_links[:4]:
            print(f"     - {link.get('hreflang')}: {link.get('href')}")
        
        # Check for JSON-LD script tags
        json_ld_scripts = soup.find_all('script', type='application/ld+json')
        if not json_ld_scripts:
            print(f"  ❌ No JSON-LD script tags found")
            return False
        
        print(f"  ✅ Found {len(json_ld_scripts)} JSON-LD script tag(s)")
        
        # Validate at least one JSON-LD with @type:Event and offers
        found_valid_event = False
        for script in json_ld_scripts:
            try:
                data = json.loads(script.string)
                if data.get('@type') == 'Event':
                    print(f"     - Found Event JSON-LD: {data.get('name', 'N/A')[:60]}")
                    
                    # Check for offers
                    if 'offers' not in data:
                        print(f"       ❌ Event JSON-LD missing 'offers' field")
                        continue
                    
                    offers = data['offers']
                    print(f"       ✅ Event has 'offers' object")
                    
                    # Validate offers structure
                    if not isinstance(offers, dict):
                        print(f"       ❌ 'offers' is not an object")
                        continue
                    
                    # Check for required offers fields
                    if '@type' in offers and offers['@type'] == 'Offer':
                        print(f"       ✅ offers has @type: Offer")
                    
                    if 'url' in offers:
                        print(f"       ✅ offers has url: {offers['url'][:60]}...")
                    
                    found_valid_event = True
                    break
                    
            except json.JSONDecodeError as e:
                print(f"     ❌ Invalid JSON in script tag: {e}")
                continue
        
        if not found_valid_event:
            print(f"  ❌ No valid Event JSON-LD with offers found")
            return False
        
        print(f"\n✅ TEST 1 PASSED: {slug} page has all required elements")
        return True, slug
    
    print(f"\n❌ TEST 1 FAILED: None of the test artists returned a valid 200 page")
    return False, None


def test_artist_page_english(working_slug):
    """
    Test 2: GET {BASE}/api/en/artist/{slug}
    Expect: 200 with html lang="en"
    """
    print("\n" + "="*80)
    print(f"TEST 2: English artist page ({working_slug})")
    print("="*80)
    
    url = f"{BASE_URL}/en/artist/{working_slug}"
    print(f"URL: {url}")
    
    headers = {"User-Agent": GOOGLEBOT_UA}
    response = requests.get(url, headers=headers, allow_redirects=False)
    
    print(f"Status: {response.status_code}")
    
    if response.status_code != 200:
        print(f"❌ Expected 200, got {response.status_code}")
        return False
    
    # Parse HTML
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Check html lang attribute
    html_tag = soup.find('html')
    if not html_tag:
        print(f"❌ No <html> tag found")
        return False
    
    lang = html_tag.get('lang')
    if lang != 'en':
        print(f"❌ Expected html lang='en', got lang='{lang}'")
        return False
    
    print(f"✅ html lang='en' confirmed")
    print(f"✅ TEST 2 PASSED")
    return True


def test_artist_page_not_found():
    """
    Test 3: GET {BASE}/api/artista/no-existe-dj-xyz (Googlebot)
    Expect: 404 status
    """
    print("\n" + "="*80)
    print("TEST 3: Non-existent artist (404 guard)")
    print("="*80)
    
    url = f"{BASE_URL}/artista/no-existe-dj-xyz"
    print(f"URL: {url}")
    
    headers = {"User-Agent": GOOGLEBOT_UA}
    response = requests.get(url, headers=headers, allow_redirects=False)
    
    print(f"Status: {response.status_code}")
    
    if response.status_code != 404:
        print(f"❌ Expected 404, got {response.status_code}")
        return False
    
    print(f"✅ Correctly returns 404 for non-existent artist")
    print(f"✅ TEST 3 PASSED")
    return True


def test_sitemap_artists():
    """
    Test 4: GET {BASE}/api/sitemap-artists.xml
    Expect: 200, valid XML <urlset> with at least one <loc> containing /artista/
    """
    print("\n" + "="*80)
    print("TEST 4: Artist sitemap")
    print("="*80)
    
    url = f"{BASE_URL}/sitemap-artists.xml"
    print(f"URL: {url}")
    
    response = requests.get(url)
    
    print(f"Status: {response.status_code}")
    
    if response.status_code != 200:
        print(f"❌ Expected 200, got {response.status_code}")
        return False
    
    # Check content type
    content_type = response.headers.get('Content-Type', '')
    if 'xml' not in content_type.lower():
        print(f"⚠️  Warning: Content-Type is '{content_type}', expected XML")
    
    # Parse XML
    try:
        root = ET.fromstring(response.text)
        print(f"✅ Valid XML parsed")
    except ET.ParseError as e:
        print(f"❌ Invalid XML: {e}")
        return False
    
    # Check for urlset
    # Handle namespace
    ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    
    # Try with namespace first
    urls = root.findall('.//ns:url', ns)
    if not urls:
        # Try without namespace
        urls = root.findall('.//url')
    
    if not urls:
        print(f"❌ No <url> entries found in sitemap")
        return False
    
    print(f"✅ Found {len(urls)} URL entries")
    
    # Check for at least one /artista/ URL
    found_artista = False
    for url_elem in urls[:5]:  # Check first 5
        loc = url_elem.find('ns:loc', ns)
        if loc is None:
            loc = url_elem.find('loc')
        
        if loc is not None and loc.text:
            print(f"  - {loc.text}")
            if '/artista/' in loc.text:
                found_artista = True
    
    if not found_artista:
        print(f"❌ No URLs containing '/artista/' found")
        return False
    
    print(f"✅ Found URLs with /artista/ path")
    print(f"✅ TEST 4 PASSED")
    return True


def test_sitemap_index():
    """
    Test 5: GET {BASE}/api/sitemap.xml
    Expect: 200 and XML should reference sitemap-artists.xml
    """
    print("\n" + "="*80)
    print("TEST 5: Main sitemap references artist sitemap")
    print("="*80)
    
    url = f"{BASE_URL}/sitemap.xml"
    print(f"URL: {url}")
    
    response = requests.get(url)
    
    print(f"Status: {response.status_code}")
    
    if response.status_code != 200:
        print(f"❌ Expected 200, got {response.status_code}")
        return False
    
    # Check if sitemap-artists.xml is referenced
    if 'sitemap-artists.xml' not in response.text:
        print(f"❌ sitemap-artists.xml not found in main sitemap")
        return False
    
    print(f"✅ sitemap-artists.xml is referenced in main sitemap")
    
    # Parse XML to validate structure
    try:
        root = ET.fromstring(response.text)
        print(f"✅ Valid XML parsed")
    except ET.ParseError as e:
        print(f"❌ Invalid XML: {e}")
        return False
    
    print(f"✅ TEST 5 PASSED")
    return True


def test_regression_api_root():
    """
    Test 6: Regression - GET {BASE}/api/
    Expect: 200 JSON {"message":"¿Quién va? API"}
    """
    print("\n" + "="*80)
    print("TEST 6: Regression - API root")
    print("="*80)
    
    url = f"{BASE_URL}/"
    print(f"URL: {url}")
    
    response = requests.get(url)
    
    print(f"Status: {response.status_code}")
    
    if response.status_code != 200:
        print(f"❌ Expected 200, got {response.status_code}")
        return False
    
    try:
        data = response.json()
        if data.get('message') != '¿Quién va? API':
            print(f"❌ Expected message '¿Quién va? API', got '{data.get('message')}'")
            return False
        
        print(f"✅ API root returns correct message")
        print(f"✅ TEST 6 PASSED")
        return True
    except json.JSONDecodeError:
        print(f"❌ Response is not valid JSON")
        return False


def main():
    print("\n" + "="*80)
    print("ARTIST/DJ SEO PAGES - BACKEND TESTING")
    print("="*80)
    print(f"Backend URL: {BASE_URL}")
    print(f"User-Agent: {GOOGLEBOT_UA}")
    
    results = []
    
    # Test 1: Artist page with events
    result1 = test_artist_page_with_events()
    if isinstance(result1, tuple):
        success, working_slug = result1
        results.append(("Artist page with events", success))
    else:
        success = result1
        working_slug = "carl-cox"  # fallback
        results.append(("Artist page with events", success))
    
    # Test 2: English artist page (only if test 1 passed)
    if results[0][1]:
        result2 = test_artist_page_english(working_slug)
        results.append(("English artist page", result2))
    else:
        print("\n⚠️  Skipping Test 2 (English page) because Test 1 failed")
        results.append(("English artist page", False))
    
    # Test 3: Non-existent artist (404)
    result3 = test_artist_page_not_found()
    results.append(("Non-existent artist (404)", result3))
    
    # Test 4: Artist sitemap
    result4 = test_sitemap_artists()
    results.append(("Artist sitemap", result4))
    
    # Test 5: Main sitemap references artist sitemap
    result5 = test_sitemap_index()
    results.append(("Main sitemap references artists", result5))
    
    # Test 6: Regression - API root
    result6 = test_regression_api_root()
    results.append(("Regression: API root", result6))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed ({passed*100//total}%)")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n❌ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
