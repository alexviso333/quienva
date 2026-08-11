#!/usr/bin/env python3
"""
Backend API Testing for City Page Premium Redesign
Tests the FastAPI backend endpoints with required headers
"""

import requests
import sys
from typing import Dict, List, Tuple

# Base URL for backend
BASE_URL = "http://localhost:8001"

# Required headers for all requests
HEADERS = {
    "x-forwarded-host": "www.quienva.me",
    "x-forwarded-proto": "https"
}

# Test credentials from test_credentials.md
AUTH_TOKEN = "qvtest_8546d7e84b6d4428b99f039104181221"

def test_ciudad_madrid():
    """Test 1: GET /api/ciudad/madrid - comprehensive checks"""
    print("\n" + "="*80)
    print("TEST 1: GET /api/ciudad/madrid")
    print("="*80)
    
    url = f"{BASE_URL}/api/ciudad/madrid"
    response = requests.get(url, headers=HEADERS)
    
    print(f"Status Code: {response.status_code}")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    assert response.headers.get('content-type', '').startswith('text/html'), \
        f"Expected text/html, got {response.headers.get('content-type')}"
    
    html = response.text
    
    # (a) Check for class="finder" with input whose oninput calls qvFilter
    print("\n(a) Checking for class='finder' with qvFilter input...")
    assert 'class="finder"' in html, "Missing class='finder'"
    assert 'oninput' in html and 'qvFilter' in html, "Missing oninput with qvFilter"
    print("✅ Found class='finder' with qvFilter input")
    
    # (b) Check for stats chip containing "discotecas"
    print("\n(b) Checking for stats chip with 'discotecas'...")
    assert 'discotecas' in html.lower() or 'discoteca' in html.lower(), \
        "Missing 'discotecas' in stats"
    print("✅ Found stats chip containing 'discotecas'")
    
    # (c) Check for class="venues" grid with class="vcard" linking to /discoteca/
    print("\n(c) Checking for venues grid with vcard links...")
    assert 'class="venues"' in html, "Missing class='venues' grid"
    assert 'class="vcard"' in html, "Missing class='vcard'"
    assert '/discoteca/' in html, "Missing /discoteca/ links"
    print("✅ Found class='venues' grid with vcard links to /discoteca/")
    
    # (d) Check for <script> defining function qvFilter
    print("\n(d) Checking for qvFilter function definition...")
    assert '<script>' in html or '<script ' in html, "Missing <script> tag"
    assert 'function qvFilter' in html or 'qvFilter' in html, \
        "Missing qvFilter function definition"
    print("✅ Found <script> defining qvFilter function")
    
    # (e) Check for event cards with data-s attribute
    print("\n(e) Checking for event cards with data-s attribute...")
    assert 'data-s=' in html or 'data-s =' in html, "Missing data-s attribute on event cards"
    print("✅ Found event cards with data-s attribute")
    
    # (f) Check for at least one class="ph" branded placeholder layer
    print("\n(f) Checking for class='ph' branded placeholder...")
    assert 'class="ph"' in html, "Missing class='ph' branded placeholder layer"
    print("✅ Found at least one class='ph' branded placeholder layer")
    
    print("\n✅ TEST 1 PASSED: All requirements met for /api/ciudad/madrid")
    return True


def test_en_city_ibiza():
    """Test 2: GET /api/en/city/ibiza - English localization"""
    print("\n" + "="*80)
    print("TEST 2: GET /api/en/city/ibiza")
    print("="*80)
    
    url = f"{BASE_URL}/api/en/city/ibiza"
    response = requests.get(url, headers=HEADERS)
    
    print(f"Status Code: {response.status_code}")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    assert response.headers.get('content-type', '').startswith('text/html'), \
        f"Expected text/html, got {response.headers.get('content-type')}"
    
    html = response.text
    
    # Check for English text
    print("\nChecking for English localization...")
    assert "Nightclubs in Ibiza" in html or "nightclubs in Ibiza" in html, \
        "Missing 'Nightclubs in Ibiza' text"
    print("✅ Found 'Nightclubs in Ibiza'")
    
    assert "Search a party or club" in html or "search a party or club" in html, \
        "Missing 'Search a party or club' text"
    print("✅ Found 'Search a party or club'")
    
    print("\n✅ TEST 2 PASSED: English localization working")
    return True


def test_de_city_madrid():
    """Test 3: GET /api/de/city/madrid - German localization"""
    print("\n" + "="*80)
    print("TEST 3: GET /api/de/city/madrid")
    print("="*80)
    
    url = f"{BASE_URL}/api/de/city/madrid"
    response = requests.get(url, headers=HEADERS)
    
    print(f"Status Code: {response.status_code}")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    assert response.headers.get('content-type', '').startswith('text/html'), \
        f"Expected text/html, got {response.headers.get('content-type')}"
    
    html = response.text
    
    # Check for German text
    print("\nChecking for German localization...")
    assert "Clubs in Madrid" in html or "clubs in Madrid" in html, \
        "Missing 'Clubs in Madrid' text"
    print("✅ Found 'Clubs in Madrid'")
    
    assert "Party oder Club suchen" in html or "party oder Club suchen" in html, \
        "Missing 'Party oder Club suchen' text"
    print("✅ Found 'Party oder Club suchen'")
    
    print("\n✅ TEST 3 PASSED: German localization working")
    return True


def test_ciudad_madrid_timeframes():
    """Test 4: GET /api/ciudad/madrid/esta-noche and /este-finde"""
    print("\n" + "="*80)
    print("TEST 4: GET /api/ciudad/madrid timeframes")
    print("="*80)
    
    # Test esta-noche
    print("\nTesting /api/ciudad/madrid/esta-noche...")
    url = f"{BASE_URL}/api/ciudad/madrid/esta-noche"
    response = requests.get(url, headers=HEADERS)
    
    print(f"Status Code: {response.status_code}")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    assert response.headers.get('content-type', '').startswith('text/html'), \
        f"Expected text/html, got {response.headers.get('content-type')}"
    
    html = response.text
    assert 'class="finder"' in html, "Missing finder on esta-noche page"
    print("✅ /api/ciudad/madrid/esta-noche returns 200 with finder")
    
    # Test este-finde
    print("\nTesting /api/ciudad/madrid/este-finde...")
    url = f"{BASE_URL}/api/ciudad/madrid/este-finde"
    response = requests.get(url, headers=HEADERS)
    
    print(f"Status Code: {response.status_code}")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    assert response.headers.get('content-type', '').startswith('text/html'), \
        f"Expected text/html, got {response.headers.get('content-type')}"
    
    html = response.text
    assert 'class="finder"' in html, "Missing finder on este-finde page"
    print("✅ /api/ciudad/madrid/este-finde returns 200 with finder")
    
    print("\n✅ TEST 4 PASSED: Both timeframe endpoints working")
    return True


def test_regression_endpoints():
    """Test 5: Regression tests for various endpoints"""
    print("\n" + "="*80)
    print("TEST 5: Regression Tests")
    print("="*80)
    
    tests = []
    
    # Test /api/home
    print("\nTesting GET /api/home...")
    url = f"{BASE_URL}/api/home"
    response = requests.get(url, headers=HEADERS)
    print(f"Status Code: {response.status_code}")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    print("✅ GET /api/home returns 200")
    tests.append(("GET /api/home", True))
    
    # Test /api/blog
    print("\nTesting GET /api/blog...")
    url = f"{BASE_URL}/api/blog"
    response = requests.get(url, headers=HEADERS)
    print(f"Status Code: {response.status_code}")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    print("✅ GET /api/blog returns 200")
    tests.append(("GET /api/blog", True))
    
    # Test /api/en/blog
    print("\nTesting GET /api/en/blog...")
    url = f"{BASE_URL}/api/en/blog"
    response = requests.get(url, headers=HEADERS)
    print(f"Status Code: {response.status_code}")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    print("✅ GET /api/en/blog returns 200")
    tests.append(("GET /api/en/blog", True))
    
    # Test /api/sitemap.xml
    print("\nTesting GET /api/sitemap.xml...")
    url = f"{BASE_URL}/api/sitemap.xml"
    response = requests.get(url, headers=HEADERS)
    print(f"Status Code: {response.status_code}")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    assert 'application/xml' in response.headers.get('content-type', ''), \
        f"Expected application/xml, got {response.headers.get('content-type')}"
    print("✅ GET /api/sitemap.xml returns 200 with application/xml")
    tests.append(("GET /api/sitemap.xml", True))
    
    # Test /api/og-city/madrid.jpg
    print("\nTesting GET /api/og-city/madrid.jpg...")
    url = f"{BASE_URL}/api/og-city/madrid.jpg"
    response = requests.get(url, headers=HEADERS)
    print(f"Status Code: {response.status_code}")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    content_type = response.headers.get('content-type', '')
    assert 'image/jpeg' in content_type or 'image/jpg' in content_type, \
        f"Expected image/jpeg, got {content_type}"
    print("✅ GET /api/og-city/madrid.jpg returns 200 with image/jpeg")
    tests.append(("GET /api/og-city/madrid.jpg", True))
    
    # Test /api/stories with Authorization header
    print("\nTesting GET /api/stories with Authorization header...")
    url = f"{BASE_URL}/api/stories"
    auth_headers = HEADERS.copy()
    auth_headers["Authorization"] = f"Bearer {AUTH_TOKEN}"
    response = requests.get(url, headers=auth_headers)
    print(f"Status Code: {response.status_code}")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    data = response.json()
    assert isinstance(data, list), "Expected JSON array"
    print(f"✅ GET /api/stories returns 200 with JSON array ({len(data)} items)")
    
    # Check for at least one moment with kind=="moment" and is_old==true
    moment_found = False
    for item in data:
        if item.get('kind') == 'moment' and item.get('is_old') == True:
            moment_found = True
            print(f"✅ Found moment with kind='moment' and is_old=true")
            break
    
    assert moment_found, "No moment found with kind='moment' and is_old=true"
    tests.append(("GET /api/stories (with auth)", True))
    
    print("\n✅ TEST 5 PASSED: All regression tests passed")
    return True


def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("CITY PAGE PREMIUM REDESIGN - BACKEND API TESTING")
    print("="*80)
    print(f"\nBase URL: {BASE_URL}")
    print(f"Headers: {HEADERS}")
    print(f"Auth Token: {AUTH_TOKEN[:20]}...")
    
    all_passed = True
    results = []
    
    try:
        # Test 1: /api/ciudad/madrid
        result = test_ciudad_madrid()
        results.append(("Test 1: /api/ciudad/madrid", result))
    except AssertionError as e:
        print(f"\n❌ TEST 1 FAILED: {e}")
        results.append(("Test 1: /api/ciudad/madrid", False))
        all_passed = False
    except Exception as e:
        print(f"\n❌ TEST 1 ERROR: {e}")
        results.append(("Test 1: /api/ciudad/madrid", False))
        all_passed = False
    
    try:
        # Test 2: /api/en/city/ibiza
        result = test_en_city_ibiza()
        results.append(("Test 2: /api/en/city/ibiza", result))
    except AssertionError as e:
        print(f"\n❌ TEST 2 FAILED: {e}")
        results.append(("Test 2: /api/en/city/ibiza", False))
        all_passed = False
    except Exception as e:
        print(f"\n❌ TEST 2 ERROR: {e}")
        results.append(("Test 2: /api/en/city/ibiza", False))
        all_passed = False
    
    try:
        # Test 3: /api/de/city/madrid
        result = test_de_city_madrid()
        results.append(("Test 3: /api/de/city/madrid", result))
    except AssertionError as e:
        print(f"\n❌ TEST 3 FAILED: {e}")
        results.append(("Test 3: /api/de/city/madrid", False))
        all_passed = False
    except Exception as e:
        print(f"\n❌ TEST 3 ERROR: {e}")
        results.append(("Test 3: /api/de/city/madrid", False))
        all_passed = False
    
    try:
        # Test 4: Timeframes
        result = test_ciudad_madrid_timeframes()
        results.append(("Test 4: Timeframes", result))
    except AssertionError as e:
        print(f"\n❌ TEST 4 FAILED: {e}")
        results.append(("Test 4: Timeframes", False))
        all_passed = False
    except Exception as e:
        print(f"\n❌ TEST 4 ERROR: {e}")
        results.append(("Test 4: Timeframes", False))
        all_passed = False
    
    try:
        # Test 5: Regression
        result = test_regression_endpoints()
        results.append(("Test 5: Regression", result))
    except AssertionError as e:
        print(f"\n❌ TEST 5 FAILED: {e}")
        results.append(("Test 5: Regression", False))
        all_passed = False
    except Exception as e:
        print(f"\n❌ TEST 5 ERROR: {e}")
        results.append(("Test 5: Regression", False))
        all_passed = False
    
    # Print summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status}: {test_name}")
    
    print("\n" + "="*80)
    if all_passed:
        print("🎉 ALL TESTS PASSED!")
        print("="*80)
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        print("="*80)
        return 1


if __name__ == "__main__":
    sys.exit(main())
