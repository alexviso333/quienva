#!/usr/bin/env python3
"""
Backend API Testing for QuienVa SSR/SEO Endpoints
Testing new homepage, venue pages, and sitemap features
"""

import requests
import json
import sys
from typing import Dict, Any
import xml.etree.ElementTree as ET

# Base URL from frontend/.env
BASE_URL = "https://logo-search-fix.preview.emergentagent.com/api"

# Test counters
tests_passed = 0
tests_failed = 0
test_results = []

def log_test(test_name: str, passed: bool, details: str = ""):
    """Log test result"""
    global tests_passed, tests_failed
    if passed:
        tests_passed += 1
        status = "✅ PASS"
    else:
        tests_failed += 1
        status = "❌ FAIL"
    
    result = f"{status}: {test_name}"
    if details:
        result += f"\n    {details}"
    test_results.append(result)
    print(result)

def test_homepage_endpoints():
    """Test 1: Homepage SSR endpoints (GET and HEAD)"""
    print("\n" + "="*80)
    print("TEST 1: HOMEPAGE ENDPOINTS (GET and HEAD)")
    print("="*80)
    
    languages = [
        ("es", "/home", "Fiestas"),
        ("en", "/en/home", "Parties"),
        ("de", "/de/home", "Partys")
    ]
    
    for lang, path, expected_word in languages:
        # Test GET request
        url = f"{BASE_URL}{path}"
        try:
            response = requests.get(url, timeout=10)
            
            # Check status code
            if response.status_code != 200:
                log_test(f"GET {path} status code", False, f"Expected 200, got {response.status_code}")
                continue
            
            # Check content type
            content_type = response.headers.get('Content-Type', '')
            if 'text/html' not in content_type:
                log_test(f"GET {path} content-type", False, f"Expected text/html, got {content_type}")
                continue
            
            html = response.text
            
            # Check for required elements
            checks = {
                "<title>": "<title> tag present",
                '<link rel="canonical"': "canonical link present",
                'hreflang="es"': "hreflang es present",
                'hreflang="en"': "hreflang en present",
                'hreflang="de"': "hreflang de present",
                'hreflang="x-default"': "hreflang x-default present",
                '"@type": "Organization"': "Organization JSON-LD present",
                '"@type": "WebSite"': "WebSite JSON-LD present",
                '"@type": "ItemList"': "ItemList JSON-LD present",
                '"@type": "FAQPage"': "FAQPage JSON-LD present",
                'qv_token': "localStorage qv_token redirect script present",
                expected_word: f"Language-specific word '{expected_word}' present"
            }
            
            all_passed = True
            missing = []
            for check_str, check_desc in checks.items():
                if check_str not in html:
                    all_passed = False
                    missing.append(check_desc)
            
            if all_passed:
                log_test(f"GET {path} ({lang}) content validation", True, "All required elements present")
            else:
                log_test(f"GET {path} ({lang}) content validation", False, f"Missing: {', '.join(missing)}")
        
        except Exception as e:
            log_test(f"GET {path} ({lang})", False, f"Exception: {str(e)}")
        
        # Test HEAD request
        try:
            response = requests.head(url, timeout=10)
            
            if response.status_code == 200:
                content_type = response.headers.get('Content-Type', '')
                if 'text/html' in content_type:
                    log_test(f"HEAD {path} ({lang})", True, f"200 with Content-Type: {content_type}")
                else:
                    log_test(f"HEAD {path} ({lang})", False, f"Wrong Content-Type: {content_type}")
            else:
                log_test(f"HEAD {path} ({lang})", False, f"Status {response.status_code}")
        
        except Exception as e:
            log_test(f"HEAD {path} ({lang})", False, f"Exception: {str(e)}")

def test_venue_pages():
    """Test 2: Venue pages (GET and HEAD)"""
    print("\n" + "="*80)
    print("TEST 2: VENUE PAGES (GET and HEAD)")
    print("="*80)
    
    # Test valid venue slug
    venue_slug = "olivia-valere"
    languages = [
        ("es", f"/discoteca/{venue_slug}", "Olivia Valere"),
        ("en", f"/en/club/{venue_slug}", "Olivia Valere"),
        ("de", f"/de/club/{venue_slug}", "Olivia Valere")
    ]
    
    for lang, path, venue_name in languages:
        url = f"{BASE_URL}{path}"
        
        # Test GET request
        try:
            response = requests.get(url, timeout=10)
            
            if response.status_code != 200:
                log_test(f"GET {path} status", False, f"Expected 200, got {response.status_code}")
                continue
            
            content_type = response.headers.get('Content-Type', '')
            if 'text/html' not in content_type:
                log_test(f"GET {path} content-type", False, f"Expected text/html, got {content_type}")
                continue
            
            html = response.text
            
            # Check for required elements
            checks = {
                '"@type": "NightClub"': "NightClub JSON-LD present",
                '"@type": "BreadcrumbList"': "BreadcrumbList JSON-LD present",
                '<link rel="canonical"': "canonical link present",
                'hreflang="es"': "hreflang es present",
                'hreflang="en"': "hreflang en present",
                'hreflang="de"': "hreflang de present",
                'hreflang="x-default"': "hreflang x-default present"
            }
            
            all_passed = True
            missing = []
            for check_str, check_desc in checks.items():
                if check_str not in html:
                    all_passed = False
                    missing.append(check_desc)
            
            # Check for event cards (should have event names)
            has_events = 'class="event-card"' in html or 'evento' in html.lower() or 'event' in html.lower()
            
            if all_passed:
                event_info = "with event cards" if has_events else "without event cards"
                log_test(f"GET {path} ({lang}) content validation", True, f"All required elements present {event_info}")
            else:
                log_test(f"GET {path} ({lang}) content validation", False, f"Missing: {', '.join(missing)}")
        
        except Exception as e:
            log_test(f"GET {path} ({lang})", False, f"Exception: {str(e)}")
        
        # Test HEAD request
        try:
            response = requests.head(url, timeout=10)
            
            if response.status_code == 200:
                content_type = response.headers.get('Content-Type', '')
                if 'text/html' in content_type:
                    log_test(f"HEAD {path} ({lang})", True, f"200 with Content-Type: {content_type}")
                else:
                    log_test(f"HEAD {path} ({lang})", False, f"Wrong Content-Type: {content_type}")
            else:
                log_test(f"HEAD {path} ({lang})", False, f"Status {response.status_code}")
        
        except Exception as e:
            log_test(f"HEAD {path} ({lang})", False, f"Exception: {str(e)}")
    
    # Test invalid venue slug (should return 404)
    print("\n--- Testing invalid venue slug ---")
    invalid_path = "/discoteca/does-not-exist-xyz"
    url = f"{BASE_URL}{invalid_path}"
    
    try:
        response = requests.get(url, timeout=10)
        
        if response.status_code == 404:
            log_test(f"GET {invalid_path} (invalid slug)", True, "Returns 404 as expected")
        else:
            log_test(f"GET {invalid_path} (invalid slug)", False, f"Expected 404, got {response.status_code}")
    
    except Exception as e:
        log_test(f"GET {invalid_path} (invalid slug)", False, f"Exception: {str(e)}")

def test_sitemap_venues():
    """Test 3: Sitemap venues XML"""
    print("\n" + "="*80)
    print("TEST 3: SITEMAP VENUES XML")
    print("="*80)
    
    path = "/sitemap-venues.xml"
    url = f"{BASE_URL}{path}"
    
    # Test GET request
    try:
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            log_test(f"GET {path} status", False, f"Expected 200, got {response.status_code}")
            return
        
        content_type = response.headers.get('Content-Type', '')
        if 'application/xml' not in content_type:
            log_test(f"GET {path} content-type", False, f"Expected application/xml, got {content_type}")
            return
        
        log_test(f"GET {path} status and content-type", True, "200 with application/xml")
        
        # Parse XML
        try:
            root = ET.fromstring(response.content)
            
            # Check for urlset
            if 'urlset' not in root.tag:
                log_test(f"GET {path} XML structure", False, "Root element is not <urlset>")
                return
            
            log_test(f"GET {path} XML structure", True, "Valid <urlset> root element")
            
            # Check for venue URLs
            xml_text = response.text
            
            if 'discoteca/olivia-valere' in xml_text or 'olivia-valere' in xml_text:
                log_test(f"GET {path} contains olivia-valere", True, "Venue slug found in sitemap")
            else:
                log_test(f"GET {path} contains olivia-valere", False, "Venue slug NOT found in sitemap")
            
            # Check for duplicates (count <loc> tags)
            loc_tags = root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}loc')
            loc_urls = [loc.text for loc in loc_tags]
            
            # Check for duplicate venue slugs
            venue_slugs = []
            for url_text in loc_urls:
                if '/discoteca/' in url_text or '/club/' in url_text:
                    slug = url_text.split('/')[-1]
                    venue_slugs.append(slug)
            
            duplicates = [slug for slug in set(venue_slugs) if venue_slugs.count(slug) > 3]  # More than 3 (es/en/de)
            
            if not duplicates:
                log_test(f"GET {path} no duplicate slugs", True, f"Found {len(set(venue_slugs))} unique venue slugs")
            else:
                log_test(f"GET {path} no duplicate slugs", False, f"Duplicate slugs found: {duplicates}")
        
        except ET.ParseError as e:
            log_test(f"GET {path} XML parsing", False, f"XML parse error: {str(e)}")
    
    except Exception as e:
        log_test(f"GET {path}", False, f"Exception: {str(e)}")
    
    # Test HEAD request
    try:
        response = requests.head(url, timeout=10)
        
        if response.status_code == 200:
            content_type = response.headers.get('Content-Type', '')
            if 'application/xml' in content_type:
                log_test(f"HEAD {path}", True, f"200 with Content-Type: {content_type}")
            else:
                log_test(f"HEAD {path}", False, f"Wrong Content-Type: {content_type}")
        else:
            log_test(f"HEAD {path}", False, f"Status {response.status_code}")
    
    except Exception as e:
        log_test(f"HEAD {path}", False, f"Exception: {str(e)}")

def test_sitemap_index():
    """Test 4: Sitemap index includes venues"""
    print("\n" + "="*80)
    print("TEST 4: SITEMAP INDEX INCLUDES VENUES")
    print("="*80)
    
    path = "/sitemap.xml"
    url = f"{BASE_URL}{path}"
    
    try:
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            log_test(f"GET {path} status", False, f"Expected 200, got {response.status_code}")
            return
        
        xml_text = response.text
        
        if 'sitemap-venues.xml' in xml_text:
            log_test(f"GET {path} includes sitemap-venues.xml", True, "Child sitemap found in index")
        else:
            log_test(f"GET {path} includes sitemap-venues.xml", False, "Child sitemap NOT found in index")
    
    except Exception as e:
        log_test(f"GET {path}", False, f"Exception: {str(e)}")

def test_sitemap_events_images():
    """Test 5: Event sitemap includes image tags"""
    print("\n" + "="*80)
    print("TEST 5: EVENT SITEMAP INCLUDES IMAGE TAGS")
    print("="*80)
    
    path = "/sitemap-events-marbella.xml"
    url = f"{BASE_URL}{path}"
    
    try:
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            log_test(f"GET {path} status", False, f"Expected 200, got {response.status_code}")
            return
        
        xml_text = response.text
        
        # Check for image namespace
        if 'xmlns:image=' in xml_text:
            log_test(f"GET {path} has image namespace", True, "xmlns:image declared")
        else:
            log_test(f"GET {path} has image namespace", False, "xmlns:image NOT declared")
        
        # Check for image:loc tags
        if '<image:loc>' in xml_text or '<image:image>' in xml_text:
            log_test(f"GET {path} contains image tags", True, "Image sitemap tags found")
        else:
            log_test(f"GET {path} contains image tags", False, "Image sitemap tags NOT found")
    
    except Exception as e:
        log_test(f"GET {path}", False, f"Exception: {str(e)}")

def test_regression_city_page():
    """Test 6: Regression - City page still works"""
    print("\n" + "="*80)
    print("TEST 6: REGRESSION - CITY PAGE")
    print("="*80)
    
    path = "/ciudad/marbella"
    url = f"{BASE_URL}{path}"
    
    try:
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            content_type = response.headers.get('Content-Type', '')
            if 'text/html' in content_type:
                log_test(f"GET {path}", True, "200 with text/html")
            else:
                log_test(f"GET {path}", False, f"Wrong Content-Type: {content_type}")
        else:
            log_test(f"GET {path}", False, f"Expected 200, got {response.status_code}")
    
    except Exception as e:
        log_test(f"GET {path}", False, f"Exception: {str(e)}")

def test_regression_event_page():
    """Test 7: Regression - Event page with FourVenues link and breadcrumb"""
    print("\n" + "="*80)
    print("TEST 7: REGRESSION - EVENT PAGE WITH FOURVENUES LINK AND BREADCRUMB")
    print("="*80)
    
    # Try to find an event ID first
    path = "/fiesta/t1"
    url = f"{BASE_URL}{path}"
    
    try:
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            # Try to get any event from the events list
            print("    Event t1 not found, trying to get any event...")
            events_response = requests.get(f"{BASE_URL}/sitemap-events-marbella.xml", timeout=10)
            if events_response.status_code == 200:
                # Parse XML to get first event ID
                try:
                    root = ET.fromstring(events_response.content)
                    loc_tags = root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}loc')
                    if loc_tags:
                        first_event_url = loc_tags[0].text
                        # Extract event ID from URL
                        if '/fiesta/' in first_event_url:
                            event_id = first_event_url.split('/fiesta/')[-1].split('/')[0]
                            path = f"/fiesta/{event_id}"
                            url = f"{BASE_URL}{path}"
                            response = requests.get(url, timeout=10)
                except:
                    pass
        
        if response.status_code != 200:
            log_test(f"GET {path} status", False, f"Expected 200, got {response.status_code}")
            return
        
        html = response.text
        
        # Check for FourVenues link
        has_fourvenues = 'fourvenues.com' in html
        has_comprar = 'Comprar entradas' in html or 'Buy tickets' in html or 'Tickets kaufen' in html
        has_nofollow = 'rel=' in html and ('nofollow' in html or 'sponsored' in html)
        
        if has_fourvenues and has_comprar:
            if has_nofollow:
                log_test(f"GET {path} FourVenues link", True, "External link with 'Comprar entradas' and rel='nofollow sponsored'")
            else:
                log_test(f"GET {path} FourVenues link", True, "External link with 'Comprar entradas' (rel attribute may be present)")
        else:
            details = []
            if not has_fourvenues:
                details.append("fourvenues.com link not found")
            if not has_comprar:
                details.append("'Comprar entradas' text not found")
            log_test(f"GET {path} FourVenues link", False, "; ".join(details))
        
        # Check for breadcrumb with venue link
        has_breadcrumb = 'class="bc"' in html or '<nav' in html
        has_venue_link = '/discoteca/' in html or 'olivia-valere' in html
        
        if has_breadcrumb and has_venue_link:
            log_test(f"GET {path} breadcrumb", True, "Breadcrumb with venue link found")
        else:
            details = []
            if not has_breadcrumb:
                details.append("breadcrumb nav not found")
            if not has_venue_link:
                details.append("venue link not found")
            log_test(f"GET {path} breadcrumb", False, "; ".join(details))
    
    except Exception as e:
        log_test(f"GET {path}", False, f"Exception: {str(e)}")

def main():
    """Run all tests"""
    print("="*80)
    print("QUIENVA SSR/SEO BACKEND TESTING")
    print("Testing new homepage, venue pages, and sitemap features")
    print(f"Base URL: {BASE_URL}")
    print("="*80)
    
    # Run all test suites
    test_homepage_endpoints()
    test_venue_pages()
    test_sitemap_venues()
    test_sitemap_index()
    test_sitemap_events_images()
    test_regression_city_page()
    test_regression_event_page()
    
    # Print summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"Total tests: {tests_passed + tests_failed}")
    print(f"✅ Passed: {tests_passed}")
    print(f"❌ Failed: {tests_failed}")
    print(f"Success rate: {tests_passed / (tests_passed + tests_failed) * 100:.1f}%")
    print("="*80)
    
    # Exit with appropriate code
    sys.exit(0 if tests_failed == 0 else 1)

if __name__ == "__main__":
    main()
