#!/usr/bin/env python3
"""
Test script for multilingual SEO landing pages (ES/EN/DE)
Tests city pages, event pages, sitemap.xml, and robots.txt
"""
import requests
import json
import re
from bs4 import BeautifulSoup
from datetime import datetime
from zoneinfo import ZoneInfo
import pymongo

# Base URL for the backend API
BASE_URL = "http://localhost:8001/api"

# Headers to simulate the public domain
HEADERS = {
    "x-forwarded-host": "quienva.me",
    "x-forwarded-proto": "https"
}

# Test results
results = {
    "passed": 0,
    "failed": 0,
    "tests": []
}

def log_test(name, passed, details=""):
    """Log a test result"""
    status = "✅ PASS" if passed else "❌ FAIL"
    results["tests"].append({"name": name, "passed": passed, "details": details})
    if passed:
        results["passed"] += 1
    else:
        results["failed"] += 1
    print(f"{status}: {name}")
    if details:
        print(f"  {details}")

def get_event_id_from_city(city_slug):
    """Extract an event ID from a city page"""
    try:
        resp = requests.get(f"{BASE_URL}/ciudad/{city_slug}", headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            # Look for event URLs in the HTML
            match = re.search(r'https://quienva\.me/fiesta/([a-f0-9-]+)', resp.text)
            if match:
                return match.group(1)
    except Exception as e:
        print(f"  Error extracting event ID: {e}")
    return None

def test_city_page(slug, lang, expected_lang_attr, expected_title_word, expected_canonical_path):
    """Test a city page in a specific language"""
    test_name = f"City page: {slug} ({lang})"
    
    # Determine the endpoint based on language
    if lang == "es":
        url = f"{BASE_URL}/ciudad/{slug}"
    elif lang == "en":
        url = f"{BASE_URL}/en/city/{slug}"
    elif lang == "de":
        url = f"{BASE_URL}/de/city/{slug}"
    else:
        log_test(test_name, False, f"Unknown language: {lang}")
        return
    
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        
        # Check status code
        if resp.status_code != 200:
            log_test(test_name, False, f"Expected 200, got {resp.status_code}")
            return
        
        # Parse HTML
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Check html lang attribute
        html_tag = soup.find('html')
        if not html_tag or html_tag.get('lang') != expected_lang_attr:
            log_test(test_name, False, f"Expected <html lang='{expected_lang_attr}'>, got {html_tag.get('lang') if html_tag else 'None'}")
            return
        
        # Check title contains expected word
        title = soup.find('title')
        if not title or expected_title_word not in title.text:
            log_test(test_name, False, f"Title doesn't contain '{expected_title_word}': {title.text if title else 'None'}")
            return
        
        # Check canonical link
        canonical = soup.find('link', rel='canonical')
        if not canonical or expected_canonical_path not in canonical.get('href', ''):
            log_test(test_name, False, f"Canonical doesn't contain '{expected_canonical_path}': {canonical.get('href') if canonical else 'None'}")
            return
        
        # Check hreflang links (should have es, en, de, x-default)
        hreflang_links = soup.find_all('link', rel='alternate', hreflang=True)
        hreflangs = {link.get('hreflang') for link in hreflang_links}
        expected_hreflangs = {'es', 'en', 'de', 'x-default'}
        if not expected_hreflangs.issubset(hreflangs):
            log_test(test_name, False, f"Missing hreflang links. Expected {expected_hreflangs}, got {hreflangs}")
            return
        
        # Check for JSON-LD script (Event schema)
        jsonld_scripts = soup.find_all('script', type='application/ld+json')
        if len(jsonld_scripts) == 0:
            log_test(test_name, False, "No JSON-LD scripts found (expected at least one Event schema)")
            return
        
        # Verify at least one JSON-LD is valid and has Event type
        found_event_schema = False
        for script in jsonld_scripts:
            try:
                data = json.loads(script.string)
                if data.get('@type') == 'Event':
                    found_event_schema = True
                    # Verify required fields
                    if not all(k in data for k in ['@context', 'name', 'startDate', 'location', 'url']):
                        log_test(test_name, False, f"Event JSON-LD missing required fields: {data}")
                        return
                    break
            except json.JSONDecodeError:
                continue
        
        if not found_event_schema:
            log_test(test_name, False, "No valid Event JSON-LD schema found")
            return
        
        log_test(test_name, True, f"All checks passed: lang={expected_lang_attr}, title contains '{expected_title_word}', canonical OK, hreflang OK, Event JSON-LD present")
        
    except Exception as e:
        log_test(test_name, False, f"Exception: {str(e)}")

def test_invalid_city():
    """Test that an invalid city slug returns 404 or redirect"""
    test_name = "Invalid city slug (ciudad-inexistente)"
    
    try:
        resp = requests.get(f"{BASE_URL}/ciudad/ciudad-inexistente", headers=HEADERS, timeout=10)
        
        # Should return 404 or a redirect HTML (not 500)
        if resp.status_code == 500:
            log_test(test_name, False, "Got 500 error (should be 404 or redirect)")
            return
        
        # Check if it's a redirect HTML
        if 'meta http-equiv' in resp.text.lower() or resp.status_code == 404:
            log_test(test_name, True, f"Correctly handled invalid city (status={resp.status_code})")
        else:
            log_test(test_name, False, f"Unexpected response for invalid city (status={resp.status_code})")
            
    except Exception as e:
        log_test(test_name, False, f"Exception: {str(e)}")

def test_event_page(event_id, lang, expected_lang_attr, expected_title_word):
    """Test an event page in a specific language"""
    test_name = f"Event page: {event_id[:8]}... ({lang})"
    
    # Determine the endpoint based on language
    if lang == "es":
        url = f"{BASE_URL}/fiesta/{event_id}"
    elif lang == "en":
        url = f"{BASE_URL}/en/party/{event_id}"
    elif lang == "de":
        url = f"{BASE_URL}/de/party/{event_id}"
    else:
        log_test(test_name, False, f"Unknown language: {lang}")
        return
    
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        
        # Check status code
        if resp.status_code != 200:
            log_test(test_name, False, f"Expected 200, got {resp.status_code}")
            return
        
        # Parse HTML
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Check html lang attribute
        html_tag = soup.find('html')
        if not html_tag or html_tag.get('lang') != expected_lang_attr:
            log_test(test_name, False, f"Expected <html lang='{expected_lang_attr}'>, got {html_tag.get('lang') if html_tag else 'None'}")
            return
        
        # Check title contains expected word (Tickets/Entradas/Uhrzeit)
        title = soup.find('title')
        if not title or expected_title_word not in title.text:
            log_test(test_name, False, f"Title doesn't contain '{expected_title_word}': {title.text if title else 'None'}")
            return
        
        # Check hreflang links
        hreflang_links = soup.find_all('link', rel='alternate', hreflang=True)
        hreflangs = {link.get('hreflang') for link in hreflang_links}
        expected_hreflangs = {'es', 'en', 'de', 'x-default'}
        if not expected_hreflangs.issubset(hreflangs):
            log_test(test_name, False, f"Missing hreflang links. Expected {expected_hreflangs}, got {hreflangs}")
            return
        
        # Check for Event JSON-LD
        jsonld_scripts = soup.find_all('script', type='application/ld+json')
        found_event = False
        for script in jsonld_scripts:
            try:
                data = json.loads(script.string)
                if data.get('@type') == 'Event':
                    found_event = True
                    # Verify required fields
                    required = ['@context', 'name', 'startDate', 'location', 'url']
                    if not all(k in data for k in required):
                        log_test(test_name, False, f"Event JSON-LD missing required fields: {list(data.keys())}")
                        return
                    
                    # Check location structure
                    loc = data.get('location', {})
                    if loc.get('@type') != 'Place' or 'address' not in loc:
                        log_test(test_name, False, f"Invalid location structure in JSON-LD")
                        return
                    
                    # Check if offers present when there's a price
                    # (This is optional but good to verify)
                    break
            except json.JSONDecodeError:
                continue
        
        if not found_event:
            log_test(test_name, False, "No Event JSON-LD found")
            return
        
        log_test(test_name, True, f"All checks passed: lang={expected_lang_attr}, title OK, hreflang OK, Event JSON-LD valid")
        
    except Exception as e:
        log_test(test_name, False, f"Exception: {str(e)}")

def test_event_with_slug(event_id, slug, lang):
    """Test event page with optional slug parameter"""
    test_name = f"Event with slug: {event_id[:8]}.../{slug} ({lang})"
    
    if lang == "es":
        url = f"{BASE_URL}/fiesta/{event_id}/{slug}"
    elif lang == "en":
        url = f"{BASE_URL}/en/party/{event_id}/{slug}"
    elif lang == "de":
        url = f"{BASE_URL}/de/party/{event_id}/{slug}"
    else:
        log_test(test_name, False, f"Unknown language: {lang}")
        return
    
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        
        if resp.status_code == 200:
            log_test(test_name, True, f"Event page with slug works (status=200)")
        else:
            log_test(test_name, False, f"Expected 200, got {resp.status_code}")
            
    except Exception as e:
        log_test(test_name, False, f"Exception: {str(e)}")

def test_invalid_event():
    """Test that an invalid event ID returns 404 or redirect (not 500)"""
    test_name = "Invalid event ID (nonexistentid123)"
    
    try:
        resp = requests.get(f"{BASE_URL}/fiesta/nonexistentid123", headers=HEADERS, timeout=10)
        
        # Should return 404 or a redirect HTML (not 500)
        if resp.status_code == 500:
            log_test(test_name, False, "Got 500 error (should be 404 or redirect)")
            return
        
        # Check if it's a redirect HTML
        if 'meta http-equiv' in resp.text.lower() or resp.status_code == 404:
            log_test(test_name, True, f"Correctly handled invalid event (status={resp.status_code})")
        else:
            log_test(test_name, False, f"Unexpected response for invalid event (status={resp.status_code})")
            
    except Exception as e:
        log_test(test_name, False, f"Exception: {str(e)}")

def test_sitemap():
    """Test sitemap.xml"""
    test_name = "Sitemap.xml"
    
    try:
        resp = requests.get(f"{BASE_URL}/sitemap.xml", headers=HEADERS, timeout=30)
        
        # Check status code
        if resp.status_code != 200:
            log_test(test_name, False, f"Expected 200, got {resp.status_code}")
            return
        
        # Check content type
        if 'xml' not in resp.headers.get('content-type', '').lower():
            log_test(test_name, False, f"Expected XML content-type, got {resp.headers.get('content-type')}")
            return
        
        # Parse XML
        soup = BeautifulSoup(resp.text, 'xml')
        
        # Check for urlset with xmlns:xhtml
        urlset = soup.find('urlset')
        if not urlset:
            log_test(test_name, False, "No <urlset> found")
            return
        
        if 'xmlns:xhtml' not in str(urlset):
            log_test(test_name, False, "xmlns:xhtml not declared in urlset")
            return
        
        # Check for city URLs in all 3 languages
        urls = soup.find_all('url')
        if len(urls) == 0:
            log_test(test_name, False, "No URLs found in sitemap")
            return
        
        # Extract all loc URLs
        locs = [url.find('loc').text for url in urls if url.find('loc')]
        
        # Check for city patterns
        city_patterns = ['/fiestas/', '/en/parties/', '/de/partys/']
        found_city_patterns = {pattern: any(pattern in loc for loc in locs) for pattern in city_patterns}
        if not all(found_city_patterns.values()):
            log_test(test_name, False, f"Missing city URL patterns: {found_city_patterns}")
            return
        
        # Check for event patterns
        event_patterns = ['/fiesta/', '/en/party/', '/de/party/']
        found_event_patterns = {pattern: any(pattern in loc for loc in locs) for pattern in event_patterns}
        if not all(found_event_patterns.values()):
            log_test(test_name, False, f"Missing event URL patterns: {found_event_patterns}")
            return
        
        # Check for xhtml:link alternates in at least one url entry
        found_xhtml_link = False
        for url in urls:
            xhtml_links = url.find_all('xhtml:link', rel='alternate')
            if len(xhtml_links) > 0:
                found_xhtml_link = True
                # Check hreflang attributes
                hreflangs = {link.get('hreflang') for link in xhtml_links}
                if 'es' in hreflangs and 'en' in hreflangs and 'de' in hreflangs:
                    break
        
        if not found_xhtml_link:
            log_test(test_name, False, "No <xhtml:link rel='alternate' hreflang=...> found in url entries")
            return
        
        log_test(test_name, True, f"Valid sitemap with {len(urls)} URLs, city patterns OK, event patterns OK, xhtml:link alternates present")
        
    except Exception as e:
        log_test(test_name, False, f"Exception: {str(e)}")

def test_robots():
    """Test robots.txt"""
    test_name = "Robots.txt"
    
    try:
        resp = requests.get(f"{BASE_URL}/robots.txt", headers=HEADERS, timeout=10)
        
        # Check status code
        if resp.status_code != 200:
            log_test(test_name, False, f"Expected 200, got {resp.status_code}")
            return
        
        # Check content type
        if 'text/plain' not in resp.headers.get('content-type', '').lower():
            log_test(test_name, False, f"Expected text/plain content-type, got {resp.headers.get('content-type')}")
            return
        
        # Check for required content
        text = resp.text
        if 'User-agent: *' not in text:
            log_test(test_name, False, "Missing 'User-agent: *'")
            return
        
        if 'Sitemap:' not in text:
            log_test(test_name, False, "Missing 'Sitemap:' line")
            return
        
        log_test(test_name, True, f"Valid robots.txt with User-agent and Sitemap")
        
    except Exception as e:
        log_test(test_name, False, f"Exception: {str(e)}")

def main():
    print("=" * 80)
    print("MULTILINGUAL SEO ENDPOINTS TEST")
    print("=" * 80)
    print(f"Base URL: {BASE_URL}")
    print(f"Headers: {HEADERS}")
    print()
    
    # Get a real event ID from the database
    client = pymongo.MongoClient("mongodb://localhost:27017")
    db = client["quienva_local"]
    today = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
    sample_event = db.events.find_one({"city": "Ibiza", "date": {"$gte": today}}, {"id": 1, "name": 1})
    event_id = sample_event.get('id') if sample_event else None
    
    if not event_id:
        print("❌ ERROR: No events found in database. Cannot test event pages.")
        return
    
    print(f"Using sample event ID: {event_id}")
    print()
    
    # 1) CITY PAGES
    print("=" * 80)
    print("1) CITY PAGES")
    print("=" * 80)
    
    # Test Ibiza in all 3 languages
    test_city_page("ibiza", "es", "es", "Fiestas", "/fiestas/ibiza")
    test_city_page("ibiza", "en", "en", "Parties", "/en/parties/ibiza")
    test_city_page("ibiza", "de", "de", "Partys", "/de/partys/ibiza")
    
    # Test invalid city
    test_invalid_city()
    
    print()
    
    # 2) EVENT PAGES
    print("=" * 80)
    print("2) EVENT PAGES")
    print("=" * 80)
    
    # Test event in all 3 languages
    test_event_page(event_id, "es", "es", "Entradas")
    test_event_page(event_id, "en", "en", "Tickets")
    test_event_page(event_id, "de", "de", "Tickets")
    
    # Test event with slug (optional parameter)
    test_event_with_slug(event_id, "global-pages", "es")
    
    # Test invalid event
    test_invalid_event()
    
    print()
    
    # 3) SITEMAP + ROBOTS
    print("=" * 80)
    print("3) SITEMAP + ROBOTS")
    print("=" * 80)
    
    test_sitemap()
    test_robots()
    
    print()
    
    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total tests: {results['passed'] + results['failed']}")
    print(f"✅ Passed: {results['passed']}")
    print(f"❌ Failed: {results['failed']}")
    print()
    
    if results['failed'] > 0:
        print("FAILED TESTS:")
        for test in results['tests']:
            if not test['passed']:
                print(f"  ❌ {test['name']}")
                if test['details']:
                    print(f"     {test['details']}")
    
    print("=" * 80)
    
    return results['failed'] == 0

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
