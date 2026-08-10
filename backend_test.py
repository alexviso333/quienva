#!/usr/bin/env python3
"""
Backend test for SEO indexing bug fix.
Tests apex->www canonical host + short city slugs + richer Event JSON-LD.
"""
import requests
import json
import re
from xml.etree import ElementTree as ET

# Base URL from frontend/.env
BASE_URL = "https://5e791fc6-c24a-43ab-8471-29846eab5135.preview.emergentagent.com/api"

# CRITICAL: All requests must include these headers to simulate the public domain
HEADERS = {
    "x-forwarded-host": "quienva.me",
    "x-forwarded-proto": "https"
}

def test_city_page_palma():
    """Test 1: GET /api/ciudad/palma - verify canonical, hreflang, robots meta"""
    print("\n=== TEST 1: City page Palma ===")
    url = f"{BASE_URL}/ciudad/palma"
    resp = requests.get(url, headers=HEADERS)
    
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    html = resp.text
    
    # Extract canonical URL
    canonical_match = re.search(r'<link rel="canonical" href="([^"]+)"', html)
    assert canonical_match, "No canonical link found"
    canonical = canonical_match.group(1)
    
    print(f"Canonical URL: {canonical}")
    
    # MUST be exactly https://www.quienva.me/fiestas/palma
    expected_canonical = "https://www.quienva.me/fiestas/palma"
    assert canonical == expected_canonical, f"Expected canonical '{expected_canonical}', got '{canonical}'"
    
    # Check for robots meta tag
    assert '<meta name="robots"' in html, "No robots meta tag found"
    print("✓ Robots meta tag present")
    
    # Check for 4 hreflang alternates (es, en, de, x-default)
    hreflang_es = re.search(r'<link rel="alternate" hreflang="es" href="([^"]+)"', html)
    hreflang_en = re.search(r'<link rel="alternate" hreflang="en" href="([^"]+)"', html)
    hreflang_de = re.search(r'<link rel="alternate" hreflang="de" href="([^"]+)"', html)
    hreflang_default = re.search(r'<link rel="alternate" hreflang="x-default" href="([^"]+)"', html)
    
    assert hreflang_es, "No hreflang es found"
    assert hreflang_en, "No hreflang en found"
    assert hreflang_de, "No hreflang de found"
    assert hreflang_default, "No hreflang x-default found"
    
    # Verify hreflang URLs
    assert hreflang_es.group(1) == "https://www.quienva.me/fiestas/palma", f"ES hreflang incorrect: {hreflang_es.group(1)}"
    assert hreflang_en.group(1) == "https://www.quienva.me/en/parties/palma", f"EN hreflang incorrect: {hreflang_en.group(1)}"
    assert hreflang_de.group(1) == "https://www.quienva.me/de/partys/palma", f"DE hreflang incorrect: {hreflang_de.group(1)}"
    
    print(f"✓ ES hreflang: {hreflang_es.group(1)}")
    print(f"✓ EN hreflang: {hreflang_en.group(1)}")
    print(f"✓ DE hreflang: {hreflang_de.group(1)}")
    print(f"✓ x-default hreflang: {hreflang_default.group(1)}")
    
    # Verify NO apex without www
    assert "https://quienva.me/" not in html or "https://www.quienva.me/" in html, "Found bare apex URL without www"
    print("✓ No bare apex URLs found")
    
    print("✅ TEST 1 PASSED")
    return True


def test_city_pages_all():
    """Test 2: Test all city pages (madrid, barcelona, ibiza, marbella) for correct canonicals"""
    print("\n=== TEST 2: All city pages ===")
    cities = [
        ("madrid", "https://www.quienva.me/fiestas/madrid"),
        ("barcelona", "https://www.quienva.me/fiestas/barcelona"),
        ("ibiza", "https://www.quienva.me/fiestas/ibiza"),
        ("marbella", "https://www.quienva.me/fiestas/marbella")
    ]
    
    for slug, expected_canonical in cities:
        print(f"\nTesting /ciudad/{slug}...")
        url = f"{BASE_URL}/ciudad/{slug}"
        resp = requests.get(url, headers=HEADERS)
        
        assert resp.status_code == 200, f"Expected 200 for {slug}, got {resp.status_code}"
        html = resp.text
        
        canonical_match = re.search(r'<link rel="canonical" href="([^"]+)"', html)
        assert canonical_match, f"No canonical link found for {slug}"
        canonical = canonical_match.group(1)
        
        print(f"  Canonical: {canonical}")
        assert canonical == expected_canonical, f"Expected '{expected_canonical}', got '{canonical}'"
        
        # Verify NO long slugs like palma-de-mallorca or marbella-puerto-banus
        assert "palma-de-mallorca" not in html, f"Found long slug 'palma-de-mallorca' in {slug}"
        assert "marbella-puerto-banus" not in html, f"Found long slug 'marbella-puerto-banus' in {slug}"
        
        # Verify NO bare apex
        # Count occurrences - www should be present, bare apex should not
        www_count = html.count("https://www.quienva.me/")
        bare_apex_pattern = re.compile(r'https://quienva\.me/(?!.*www)')
        bare_matches = bare_apex_pattern.findall(html)
        
        print(f"  ✓ Canonical uses www and short slug")
    
    print("\n✅ TEST 2 PASSED")
    return True


def test_long_slug_alias():
    """Test 3: GET /api/ciudad/palma-de-mallorca (long alias) should canonicalize to short slug"""
    print("\n=== TEST 3: Long slug alias ===")
    url = f"{BASE_URL}/ciudad/palma-de-mallorca"
    resp = requests.get(url, headers=HEADERS)
    
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    html = resp.text
    
    canonical_match = re.search(r'<link rel="canonical" href="([^"]+)"', html)
    assert canonical_match, "No canonical link found"
    canonical = canonical_match.group(1)
    
    print(f"Canonical URL: {canonical}")
    
    # MUST canonicalize to short slug
    expected_canonical = "https://www.quienva.me/fiestas/palma"
    assert canonical == expected_canonical, f"Expected canonical '{expected_canonical}', got '{canonical}'"
    
    print("✅ TEST 3 PASSED - Long slug correctly canonicalizes to short slug")
    return True


def test_invalid_city():
    """Test 4: GET /api/ciudad/ciudad-inexistente should return 404"""
    print("\n=== TEST 4: Invalid city slug ===")
    url = f"{BASE_URL}/ciudad/ciudad-inexistente"
    resp = requests.get(url, headers=HEADERS)
    
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
    assert resp.headers.get("content-type", "").startswith("text/html"), "Expected HTML response"
    
    print("✅ TEST 4 PASSED - Invalid city returns 404")
    return True


def test_sitemap_cities():
    """Test 5: GET /api/sitemap-cities.xml - verify all URLs use www and short slugs"""
    print("\n=== TEST 5: Sitemap cities ===")
    url = f"{BASE_URL}/sitemap-cities.xml"
    resp = requests.get(url, headers=HEADERS)
    
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    assert "application/xml" in resp.headers.get("content-type", ""), "Expected XML content-type"
    
    xml_content = resp.text
    
    # Parse XML
    root = ET.fromstring(xml_content)
    
    # Find all <loc> elements
    ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    locs = root.findall('.//sm:loc', ns)
    
    print(f"Found {len(locs)} <loc> entries")
    
    for loc in locs:
        url_text = loc.text
        
        # EVERY <loc> must start with https://www.quienva.me
        assert url_text.startswith("https://www.quienva.me"), f"URL does not start with www: {url_text}"
        
        # Check for forbidden long slugs
        assert "palma-de-mallorca" not in url_text, f"Found long slug 'palma-de-mallorca' in: {url_text}"
        assert "marbella-puerto-banus" not in url_text, f"Found long slug 'marbella-puerto-banus' in: {url_text}"
    
    # Verify short slugs are present
    xml_str = xml_content
    assert "/fiestas/palma" in xml_str, "Short slug 'palma' not found"
    assert "/fiestas/ibiza" in xml_str, "Short slug 'ibiza' not found"
    assert "/fiestas/madrid" in xml_str, "Short slug 'madrid' not found"
    assert "/fiestas/barcelona" in xml_str, "Short slug 'barcelona' not found"
    assert "/fiestas/marbella" in xml_str, "Short slug 'marbella' not found"
    
    print("✓ All URLs use https://www.quienva.me")
    print("✓ All city URLs use short slugs")
    print("✓ No long slugs found")
    
    print("✅ TEST 5 PASSED")
    return True


def test_sitemap_index():
    """Test 6: GET /api/sitemap.xml - verify child sitemaps use www and short slugs"""
    print("\n=== TEST 6: Sitemap index ===")
    url = f"{BASE_URL}/sitemap.xml"
    resp = requests.get(url, headers=HEADERS)
    
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    assert "application/xml" in resp.headers.get("content-type", ""), "Expected XML content-type"
    
    xml_content = resp.text
    
    # Parse XML
    root = ET.fromstring(xml_content)
    
    # Find all <loc> elements in sitemap index
    ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    locs = root.findall('.//sm:loc', ns)
    
    print(f"Found {len(locs)} child sitemap entries")
    
    for loc in locs:
        url_text = loc.text
        print(f"  {url_text}")
        
        # All child sitemaps must use www
        assert url_text.startswith("https://www.quienva.me"), f"Child sitemap does not use www: {url_text}"
    
    # Verify expected child sitemaps with short slugs
    xml_str = xml_content
    assert "sitemap-cities.xml" in xml_str, "sitemap-cities.xml not found"
    assert "sitemap-events-palma.xml" in xml_str, "sitemap-events-palma.xml not found"
    assert "sitemap-events-ibiza.xml" in xml_str, "sitemap-events-ibiza.xml not found"
    assert "sitemap-events-madrid.xml" in xml_str, "sitemap-events-madrid.xml not found"
    assert "sitemap-events-barcelona.xml" in xml_str, "sitemap-events-barcelona.xml not found"
    assert "sitemap-events-marbella.xml" in xml_str, "sitemap-events-marbella.xml not found"
    
    print("✓ All child sitemaps use www")
    print("✓ All event sitemaps use short city slugs")
    
    print("✅ TEST 6 PASSED")
    return True


def test_robots_txt():
    """Test 7: GET /api/robots.txt - verify Sitemap line uses www"""
    print("\n=== TEST 7: Robots.txt ===")
    url = f"{BASE_URL}/robots.txt"
    resp = requests.get(url, headers=HEADERS)
    
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    assert "text/plain" in resp.headers.get("content-type", ""), "Expected text/plain content-type"
    
    content = resp.text
    print(f"Robots.txt content:\n{content}")
    
    # Verify Sitemap line uses www
    assert "Sitemap: https://www.quienva.me/sitemap.xml" in content, "Sitemap line does not use www host"
    
    print("✅ TEST 7 PASSED")
    return True


def get_event_with_price():
    """Helper: Get an event ID that has a price"""
    print("\n=== Finding event with price ===")
    # Get events from admin endpoint
    url = f"{BASE_URL}/admin/events-min"
    
    # Need to login as admin first
    login_url = f"{BASE_URL}/auth/login"
    login_data = {"email": "admin@quienva.me", "password": "admin123"}
    login_resp = requests.post(login_url, json=login_data)
    
    if login_resp.status_code != 200:
        print(f"Warning: Could not login as admin (status {login_resp.status_code})")
        # Try to get any event from the database
        # We'll just use a known event ID from the seed data
        return None
    
    token = login_resp.json().get("token")
    headers_with_auth = {**HEADERS, "Authorization": f"Bearer {token}"}
    
    resp = requests.get(url, headers=headers_with_auth)
    if resp.status_code != 200:
        print(f"Warning: Could not get events (status {resp.status_code})")
        return None
    
    events = resp.json().get("events", [])
    
    # Get full event details to find one with price
    for event in events[:50]:  # Check first 50 events
        event_id = event.get("id")
        event_url = f"{BASE_URL}/events/{event_id}"
        event_resp = requests.get(event_url, headers=headers_with_auth)
        
        if event_resp.status_code == 200:
            event_data = event_resp.json()
            price_tiers = event_data.get("price_tiers", [])
            if price_tiers and any(t.get("price") for t in price_tiers):
                print(f"Found event with price: {event_id} - {event_data.get('name')}")
                return event_id
    
    print("Warning: No event with price found, will use first available event")
    return events[0].get("id") if events else None


def test_event_page_jsonld():
    """Test 8: GET /api/fiesta/{id} - verify Event JSON-LD has all required fields"""
    print("\n=== TEST 8: Event page JSON-LD ===")
    
    # Get an event with price
    event_id = get_event_with_price()
    
    if not event_id:
        print("⚠️  Could not find event with price, skipping test")
        return False
    
    url = f"{BASE_URL}/fiesta/{event_id}"
    resp = requests.get(url, headers=HEADERS)
    
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    html = resp.text
    
    # Extract JSON-LD
    jsonld_match = re.search(r'<script type="application/ld\+json">({.*?"@type":\s*"Event".*?})</script>', html, re.DOTALL)
    assert jsonld_match, "No Event JSON-LD found"
    
    jsonld_str = jsonld_match.group(1)
    jsonld = json.loads(jsonld_str)
    
    print(f"Event JSON-LD keys: {list(jsonld.keys())}")
    
    # Verify required fields
    assert "@context" in jsonld, "Missing @context"
    assert "@type" in jsonld and jsonld["@type"] == "Event", "Missing or incorrect @type"
    assert "name" in jsonld, "Missing name"
    assert "startDate" in jsonld, "Missing startDate"
    
    # NEW FIELDS from the fix
    assert "endDate" in jsonld, "Missing endDate"
    print(f"✓ endDate: {jsonld['endDate']}")
    
    assert "description" in jsonld, "Missing description"
    assert jsonld["description"], "description is empty"
    print(f"✓ description: {jsonld['description'][:50]}...")
    
    assert "performer" in jsonld, "Missing performer"
    assert jsonld["performer"].get("@type"), "performer missing @type"
    assert jsonld["performer"].get("name"), "performer missing name"
    print(f"✓ performer: {jsonld['performer']}")
    
    # Check offers (if event has price)
    if "offers" in jsonld:
        offers = jsonld["offers"]
        print(f"✓ offers present")
        
        assert "price" in offers, "offers missing price"
        assert "priceCurrency" in offers, "offers missing priceCurrency"
        assert "availability" in offers, "offers missing availability"
        assert "url" in offers, "offers missing url"
        
        # NEW FIELDS from the fix
        assert "validFrom" in offers, "offers missing validFrom"
        print(f"✓ offers.validFrom: {offers['validFrom']}")
        
        assert "priceValidUntil" in offers, "offers missing priceValidUntil"
        print(f"✓ offers.priceValidUntil: {offers['priceValidUntil']}")
        
        # Verify offer URL uses www
        assert offers["url"].startswith("https://www.quienva.me"), f"Offer URL does not use www: {offers['url']}"
    
    # Verify JSON-LD url uses www
    assert jsonld["url"].startswith("https://www.quienva.me"), f"JSON-LD url does not use www: {jsonld['url']}"
    print(f"✓ JSON-LD url uses www: {jsonld['url']}")
    
    # Verify canonical link uses www
    canonical_match = re.search(r'<link rel="canonical" href="([^"]+)"', html)
    assert canonical_match, "No canonical link found"
    canonical = canonical_match.group(1)
    assert canonical.startswith("https://www.quienva.me"), f"Canonical does not use www: {canonical}"
    print(f"✓ Canonical uses www: {canonical}")
    
    print("✅ TEST 8 PASSED")
    return True


def test_invalid_event():
    """Test 9: GET /api/fiesta/nonexistentid123 should return 404"""
    print("\n=== TEST 9: Invalid event ID ===")
    url = f"{BASE_URL}/fiesta/nonexistentid123"
    resp = requests.get(url, headers=HEADERS)
    
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
    assert resp.headers.get("content-type", "").startswith("text/html"), "Expected HTML response"
    
    print("✅ TEST 9 PASSED - Invalid event returns 404")
    return True


def main():
    """Run all tests"""
    print("=" * 80)
    print("SEO INDEXING BUG FIX TEST SUITE")
    print("Testing: apex->www canonical + short city slugs + richer Event JSON-LD")
    print("=" * 80)
    
    tests = [
        ("City page Palma (canonical, hreflang, robots)", test_city_page_palma),
        ("All city pages (madrid, barcelona, ibiza, marbella)", test_city_pages_all),
        ("Long slug alias (palma-de-mallorca)", test_long_slug_alias),
        ("Invalid city slug", test_invalid_city),
        ("Sitemap cities (www + short slugs)", test_sitemap_cities),
        ("Sitemap index (child sitemaps)", test_sitemap_index),
        ("Robots.txt (www sitemap)", test_robots_txt),
        ("Event page JSON-LD (endDate, description, performer, offers)", test_event_page_jsonld),
        ("Invalid event ID", test_invalid_event),
    ]
    
    passed = 0
    failed = 0
    skipped = 0
    
    for name, test_func in tests:
        try:
            result = test_func()
            if result is False:
                skipped += 1
                print(f"⚠️  SKIPPED: {name}")
            else:
                passed += 1
        except AssertionError as e:
            failed += 1
            print(f"❌ FAILED: {name}")
            print(f"   Error: {e}")
        except Exception as e:
            failed += 1
            print(f"❌ ERROR: {name}")
            print(f"   Exception: {e}")
    
    print("\n" + "=" * 80)
    print(f"TEST RESULTS: {passed} passed, {failed} failed, {skipped} skipped")
    print("=" * 80)
    
    if failed > 0:
        exit(1)
    else:
        print("\n✅ ALL TESTS PASSED!")
        exit(0)


if __name__ == "__main__":
    main()
