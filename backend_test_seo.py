#!/usr/bin/env python3
"""
SEO Endpoints Testing for ¿Quién va? Backend
Tests server-rendered SEO endpoints after 2026-08-11 iteration
"""

import requests
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup

# Configuration
BASE_URL = "http://localhost:8001"
HEADERS = {
    "x-forwarded-host": "www.quienva.me",
    "x-forwarded-proto": "https"
}

# Expected month/year in Spanish (Europe/Madrid timezone)
tz = ZoneInfo('Europe/Madrid')
now = datetime.now(tz)
months_es = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
EXPECTED_MONTH_YEAR = f"{months_es[now.month-1]} {now.year}"

print(f"Expected month/year in titles: {EXPECTED_MONTH_YEAR}")
print(f"Testing with headers: {HEADERS}\n")
print("="*80)

# Test counters
tests_passed = 0
tests_failed = 0
failures = []

def test_endpoint(name, url, checks):
    """Generic test function"""
    global tests_passed, tests_failed, failures
    
    print(f"\n{'='*80}")
    print(f"TEST: {name}")
    print(f"URL: {url}")
    print(f"{'='*80}")
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        
        # Check status code
        if response.status_code != 200:
            print(f"❌ FAILED: Expected 200, got {response.status_code}")
            tests_failed += 1
            failures.append(f"{name}: Status {response.status_code}")
            return False
        
        print(f"✅ Status: {response.status_code}")
        
        # Check content type
        content_type = response.headers.get('content-type', '')
        print(f"✅ Content-Type: {content_type}")
        
        # Run custom checks
        all_passed = True
        for check_name, check_func in checks.items():
            try:
                result = check_func(response)
                if result:
                    print(f"✅ {check_name}: PASS")
                else:
                    print(f"❌ {check_name}: FAIL")
                    all_passed = False
                    failures.append(f"{name}: {check_name} failed")
            except Exception as e:
                print(f"❌ {check_name}: ERROR - {str(e)}")
                all_passed = False
                failures.append(f"{name}: {check_name} error - {str(e)}")
        
        if all_passed:
            tests_passed += 1
            print(f"\n✅ {name}: ALL CHECKS PASSED")
        else:
            tests_failed += 1
            print(f"\n❌ {name}: SOME CHECKS FAILED")
        
        return all_passed
        
    except Exception as e:
        print(f"❌ FAILED: {str(e)}")
        tests_failed += 1
        failures.append(f"{name}: {str(e)}")
        return False


# Test 1: GET /api/ciudad/madrid
def test_ciudad_madrid():
    def check_title_h1(resp):
        soup = BeautifulSoup(resp.text, 'html.parser')
        title = soup.find('title')
        h1 = soup.find('h1')
        
        if not title or not h1:
            print(f"  Missing title or h1 tag")
            return False
        
        title_text = title.get_text()
        h1_text = h1.get_text()
        
        print(f"  Title: {title_text}")
        print(f"  H1: {h1_text}")
        
        if EXPECTED_MONTH_YEAR not in title_text:
            print(f"  ❌ Title missing '{EXPECTED_MONTH_YEAR}'")
            return False
        
        if EXPECTED_MONTH_YEAR not in h1_text:
            print(f"  ❌ H1 missing '{EXPECTED_MONTH_YEAR}'")
            return False
        
        return True
    
    def check_og_image(resp):
        soup = BeautifulSoup(resp.text, 'html.parser')
        og_image = soup.find('meta', property='og:image')
        og_width = soup.find('meta', property='og:image:width')
        og_height = soup.find('meta', property='og:image:height')
        
        if not og_image:
            print(f"  ❌ Missing og:image meta tag")
            return False
        
        image_url = og_image.get('content', '')
        print(f"  og:image: {image_url}")
        
        if not image_url.endswith('/og/og-madrid.png'):
            print(f"  ❌ og:image doesn't end with /og/og-madrid.png")
            return False
        
        if not og_width or og_width.get('content') != '1200':
            print(f"  ❌ Missing or incorrect og:image:width")
            return False
        
        if not og_height or og_height.get('content') != '630':
            print(f"  ❌ Missing or incorrect og:image:height")
            return False
        
        print(f"  og:image:width: {og_width.get('content')}")
        print(f"  og:image:height: {og_height.get('content')}")
        
        return True
    
    def check_favicon(resp):
        soup = BeautifulSoup(resp.text, 'html.parser')
        favicon = soup.find('link', rel='icon', href='/favicon.ico')
        
        if not favicon:
            print(f"  ❌ Missing favicon link")
            return False
        
        print(f"  Favicon: {favicon.get('href')}")
        return True
    
    return test_endpoint(
        "GET /api/ciudad/madrid",
        f"{BASE_URL}/api/ciudad/madrid",
        {
            "Title and H1 contain month/year": check_title_h1,
            "OG image for madrid": check_og_image,
            "Favicon present": check_favicon
        }
    )


# Test 2: GET /api/ciudad/ibiza
def test_ciudad_ibiza():
    def check_title_h1(resp):
        soup = BeautifulSoup(resp.text, 'html.parser')
        title = soup.find('title')
        h1 = soup.find('h1')
        
        if not title or not h1:
            return False
        
        title_text = title.get_text()
        h1_text = h1.get_text()
        
        print(f"  Title: {title_text}")
        print(f"  H1: {h1_text}")
        
        return EXPECTED_MONTH_YEAR in title_text and EXPECTED_MONTH_YEAR in h1_text
    
    def check_og_image(resp):
        soup = BeautifulSoup(resp.text, 'html.parser')
        og_image = soup.find('meta', property='og:image')
        og_width = soup.find('meta', property='og:image:width')
        og_height = soup.find('meta', property='og:image:height')
        
        if not og_image:
            return False
        
        image_url = og_image.get('content', '')
        print(f"  og:image: {image_url}")
        
        return (image_url.endswith('/og/og-ibiza.png') and 
                og_width and og_width.get('content') == '1200' and
                og_height and og_height.get('content') == '630')
    
    def check_favicon(resp):
        soup = BeautifulSoup(resp.text, 'html.parser')
        favicon = soup.find('link', rel='icon', href='/favicon.ico')
        return favicon is not None
    
    return test_endpoint(
        "GET /api/ciudad/ibiza",
        f"{BASE_URL}/api/ciudad/ibiza",
        {
            "Title and H1 contain month/year": check_title_h1,
            "OG image for ibiza": check_og_image,
            "Favicon present": check_favicon
        }
    )


# Test 3: GET /api/home
def test_home():
    def check_og_image(resp):
        soup = BeautifulSoup(resp.text, 'html.parser')
        og_image = soup.find('meta', property='og:image')
        
        if not og_image:
            print(f"  ❌ Missing og:image meta tag")
            return False
        
        image_url = og_image.get('content', '')
        print(f"  og:image: {image_url}")
        
        if not image_url.endswith('/og/og-default.png'):
            print(f"  ❌ og:image doesn't end with /og/og-default.png")
            return False
        
        return True
    
    def check_favicon(resp):
        soup = BeautifulSoup(resp.text, 'html.parser')
        favicon = soup.find('link', rel='icon', href='/favicon.ico')
        
        if not favicon:
            print(f"  ❌ Missing favicon link")
            return False
        
        return True
    
    return test_endpoint(
        "GET /api/home",
        f"{BASE_URL}/api/home",
        {
            "OG image default": check_og_image,
            "Favicon present": check_favicon
        }
    )


# Test 4: GET /api/ciudad/madrid/esta-noche
def test_ciudad_madrid_esta_noche():
    def check_title_month(resp):
        soup = BeautifulSoup(resp.text, 'html.parser')
        title = soup.find('title')
        
        if not title:
            return False
        
        title_text = title.get_text()
        print(f"  Title: {title_text}")
        
        return EXPECTED_MONTH_YEAR in title_text
    
    return test_endpoint(
        "GET /api/ciudad/madrid/esta-noche",
        f"{BASE_URL}/api/ciudad/madrid/esta-noche",
        {
            "Title contains month/year": check_title_month
        }
    )


# Test 5: GET /api/ciudad/madrid/este-finde
def test_ciudad_madrid_este_finde():
    def check_title_month(resp):
        soup = BeautifulSoup(resp.text, 'html.parser')
        title = soup.find('title')
        
        if not title:
            return False
        
        title_text = title.get_text()
        print(f"  Title: {title_text}")
        
        return EXPECTED_MONTH_YEAR in title_text
    
    return test_endpoint(
        "GET /api/ciudad/madrid/este-finde",
        f"{BASE_URL}/api/ciudad/madrid/este-finde",
        {
            "Title contains month/year": check_title_month
        }
    )


# Test 6: GET /api/blog/donde-salir-esta-noche-espana
def test_blog_donde_salir():
    def check_title(resp):
        soup = BeautifulSoup(resp.text, 'html.parser')
        title = soup.find('title')
        
        if not title:
            return False
        
        title_text = title.get_text()
        print(f"  Title: {title_text}")
        
        expected = "¿Dónde salir esta noche en España"
        if expected not in title_text:
            print(f"  ❌ Title doesn't contain '{expected}'")
            return False
        
        return True
    
    return test_endpoint(
        "GET /api/blog/donde-salir-esta-noche-espana",
        f"{BASE_URL}/api/blog/donde-salir-esta-noche-espana",
        {
            "Title correct": check_title
        }
    )


# Test 7: GET /api/blog/mejores-fiestas-este-finde-espana
def test_blog_mejores_fiestas():
    def check_title(resp):
        soup = BeautifulSoup(resp.text, 'html.parser')
        title = soup.find('title')
        
        if not title:
            return False
        
        title_text = title.get_text()
        print(f"  Title: {title_text}")
        
        expected = "Las mejores fiestas de este fin de semana en España"
        if expected not in title_text:
            print(f"  ❌ Title doesn't contain '{expected}'")
            return False
        
        return True
    
    return test_endpoint(
        "GET /api/blog/mejores-fiestas-este-finde-espana",
        f"{BASE_URL}/api/blog/mejores-fiestas-este-finde-espana",
        {
            "Title correct": check_title
        }
    )


# Test 8: GET /api/sitemap-blog.xml
def test_sitemap_blog():
    def check_slugs(resp):
        content = resp.text
        
        slug1 = "donde-salir-esta-noche-espana"
        slug2 = "mejores-fiestas-este-finde-espana"
        
        if slug1 not in content:
            print(f"  ❌ Missing slug: {slug1}")
            return False
        
        if slug2 not in content:
            print(f"  ❌ Missing slug: {slug2}")
            return False
        
        print(f"  ✓ Found slug: {slug1}")
        print(f"  ✓ Found slug: {slug2}")
        
        return True
    
    return test_endpoint(
        "GET /api/sitemap-blog.xml",
        f"{BASE_URL}/api/sitemap-blog.xml",
        {
            "Contains both blog slugs": check_slugs
        }
    )


# Test 9: Event JSON-LD offers
def test_event_jsonld_offers():
    print(f"\n{'='*80}")
    print(f"TEST: Event JSON-LD offers structure")
    print(f"{'='*80}")
    
    global tests_passed, tests_failed, failures
    
    try:
        # First, get an event ID from ciudad/palma
        print("Step 1: Fetching /api/ciudad/palma to extract event ID...")
        resp = requests.get(f"{BASE_URL}/api/ciudad/palma", headers=HEADERS, timeout=10)
        
        if resp.status_code != 200:
            print(f"❌ Failed to fetch ciudad/palma: {resp.status_code}")
            tests_failed += 1
            failures.append("Event JSON-LD: Failed to fetch ciudad/palma")
            return False
        
        # Extract event ID from fiesta/<uuid> pattern
        soup = BeautifulSoup(resp.text, 'html.parser')
        event_id = None
        
        # Look for links with /fiesta/ pattern
        for link in soup.find_all('a', href=True):
            href = link['href']
            match = re.search(r'/fiesta/([a-f0-9-]{36})', href)
            if match:
                event_id = match.group(1)
                break
        
        if not event_id:
            print(f"❌ Could not extract event ID from ciudad/palma")
            tests_failed += 1
            failures.append("Event JSON-LD: No event ID found")
            return False
        
        print(f"✅ Found event ID: {event_id}")
        
        # Now fetch the event page
        print(f"\nStep 2: Fetching /api/fiesta/{event_id}...")
        event_url = f"{BASE_URL}/api/fiesta/{event_id}"
        resp = requests.get(event_url, headers=HEADERS, timeout=10)
        
        if resp.status_code != 200:
            print(f"❌ Failed to fetch event: {resp.status_code}")
            tests_failed += 1
            failures.append(f"Event JSON-LD: Failed to fetch event {event_id}")
            return False
        
        print(f"✅ Status: {resp.status_code}")
        
        # Parse JSON-LD
        soup = BeautifulSoup(resp.text, 'html.parser')
        jsonld_scripts = soup.find_all('script', type='application/ld+json')
        
        if not jsonld_scripts:
            print(f"❌ No JSON-LD scripts found")
            tests_failed += 1
            failures.append("Event JSON-LD: No JSON-LD found")
            return False
        
        print(f"✅ Found {len(jsonld_scripts)} JSON-LD script(s)")
        
        # Find Event type JSON-LD
        event_jsonld = None
        for script in jsonld_scripts:
            try:
                data = json.loads(script.string)
                if data.get('@type') == 'Event':
                    event_jsonld = data
                    break
            except Exception:
                continue
        
        if not event_jsonld:
            print(f"❌ No Event type JSON-LD found")
            tests_failed += 1
            failures.append("Event JSON-LD: No Event type found")
            return False
        
        print(f"✅ Found Event JSON-LD")
        
        # Check required fields
        all_passed = True
        
        # Check offers
        if 'offers' not in event_jsonld:
            print(f"❌ Missing 'offers' field")
            all_passed = False
        else:
            offers = event_jsonld['offers']
            print(f"✅ 'offers' field present")
            
            # Check offers subfields
            required_offer_fields = ['url', 'availability', 'validFrom']
            for field in required_offer_fields:
                if field not in offers:
                    print(f"  ❌ Missing offers.{field}")
                    all_passed = False
                else:
                    print(f"  ✅ offers.{field}: {offers[field]}")
        
        # Check other required Event fields
        required_event_fields = ['endDate', 'description', 'performer']
        for field in required_event_fields:
            if field not in event_jsonld:
                print(f"❌ Missing '{field}' field")
                all_passed = False
            else:
                value = event_jsonld[field]
                if field == 'performer':
                    print(f"✅ '{field}': {value}")
                else:
                    print(f"✅ '{field}': {value[:100] if len(str(value)) > 100 else value}")
        
        if all_passed:
            tests_passed += 1
            print(f"\n✅ Event JSON-LD offers: ALL CHECKS PASSED")
        else:
            tests_failed += 1
            failures.append("Event JSON-LD: Missing required fields")
            print(f"\n❌ Event JSON-LD offers: SOME CHECKS FAILED")
        
        return all_passed
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        tests_failed += 1
        failures.append(f"Event JSON-LD: {str(e)}")
        return False


# Test 10: Regression - EN city page
def test_en_city_madrid():
    def check_status(resp):
        return True  # Already checked by test_endpoint
    
    return test_endpoint(
        "GET /api/en/city/madrid (regression)",
        f"{BASE_URL}/api/en/city/madrid",
        {
            "Returns 200": check_status
        }
    )


# Test 11: Regression - DE city page
def test_de_city_madrid():
    def check_status(resp):
        return True  # Already checked by test_endpoint
    
    return test_endpoint(
        "GET /api/de/city/madrid (regression)",
        f"{BASE_URL}/api/de/city/madrid",
        {
            "Returns 200": check_status
        }
    )


# Run all tests
if __name__ == "__main__":
    print("\n" + "="*80)
    print("SEO ENDPOINTS TESTING - 2026-08-11 ITERATION")
    print("="*80)
    
    test_ciudad_madrid()
    test_ciudad_ibiza()
    test_home()
    test_ciudad_madrid_esta_noche()
    test_ciudad_madrid_este_finde()
    test_blog_donde_salir()
    test_blog_mejores_fiestas()
    test_sitemap_blog()
    test_event_jsonld_offers()
    test_en_city_madrid()
    test_de_city_madrid()
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"✅ Tests Passed: {tests_passed}")
    print(f"❌ Tests Failed: {tests_failed}")
    print(f"Total Tests: {tests_passed + tests_failed}")
    
    if failures:
        print("\n" + "="*80)
        print("FAILURES:")
        print("="*80)
        for failure in failures:
            print(f"  • {failure}")
    
    print("\n" + "="*80)
    
    if tests_failed == 0:
        print("🎉 ALL TESTS PASSED!")
        exit(0)
    else:
        print("⚠️  SOME TESTS FAILED")
        exit(1)
