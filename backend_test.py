#!/usr/bin/env python3
"""
Backend API Testing for ¿Quién va? Multi-City Expansion
Tests the new multi-city features and WhatsApp share OG page.
"""

import requests
import json
import sys
from datetime import datetime

# Base URL from frontend/.env
BASE_URL = "https://perf-boost-103.preview.emergentagent.com/api"

# Admin credentials
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

# Test results tracking
tests_passed = 0
tests_failed = 0
test_details = []


def log_test(test_name, passed, details=""):
    """Log test result"""
    global tests_passed, tests_failed
    if passed:
        tests_passed += 1
        status = "✅ PASS"
    else:
        tests_failed += 1
        status = "❌ FAIL"
    
    message = f"{status}: {test_name}"
    if details:
        message += f" - {details}"
    print(message)
    test_details.append({"test": test_name, "passed": passed, "details": details})


def test_cities_endpoint():
    """Test 1: GET /api/cities (PUBLIC, no auth required)"""
    print("\n" + "="*80)
    print("TEST 1: GET /api/cities (PUBLIC endpoint)")
    print("="*80)
    
    try:
        response = requests.get(f"{BASE_URL}/cities", timeout=10)
        
        # Check status code
        if response.status_code != 200:
            log_test("Cities endpoint status", False, f"Expected 200, got {response.status_code}")
            return None
        log_test("Cities endpoint status", True, "200 OK")
        
        # Check response structure
        data = response.json()
        if "cities" not in data:
            log_test("Cities response structure", False, "Missing 'cities' key")
            return None
        log_test("Cities response structure", True, "Has 'cities' key")
        
        cities = data["cities"]
        
        # Check count
        if len(cities) != 5:
            log_test("Cities count", False, f"Expected 5 cities, got {len(cities)}")
        else:
            log_test("Cities count", True, "Exactly 5 cities")
        
        # Check required city IDs
        city_ids = [c["id"] for c in cities]
        required_ids = ["Palma de Mallorca", "Ibiza", "Madrid", "Barcelona", "Marbella"]
        
        for required_id in required_ids:
            if required_id in city_ids:
                log_test(f"City '{required_id}' present", True)
            else:
                log_test(f"City '{required_id}' present", False, f"Missing from {city_ids}")
        
        # Check structure of each city
        for city in cities:
            has_id = "id" in city
            has_label = "label" in city
            has_emoji = "emoji" in city
            
            if has_id and has_label and has_emoji:
                log_test(f"City '{city.get('id', 'unknown')}' structure", True, "Has id, label, emoji")
            else:
                missing = []
                if not has_id: missing.append("id")
                if not has_label: missing.append("label")
                if not has_emoji: missing.append("emoji")
                log_test(f"City structure", False, f"Missing: {', '.join(missing)}")
        
        print(f"\nCities returned: {json.dumps(cities, indent=2, ensure_ascii=False)}")
        return cities
        
    except Exception as e:
        log_test("Cities endpoint", False, f"Exception: {str(e)}")
        return None


def register_user(email, password, name, username, city, birthdate="2000-01-01"):
    """Helper: Register a new user"""
    try:
        response = requests.post(
            f"{BASE_URL}/auth/register",
            json={
                "email": email,
                "password": password,
                "name": name,
                "username": username,
                "city": city,
                "birthdate": birthdate
            },
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            return data.get("token")
        else:
            print(f"  ⚠️  Registration failed for {email}: {response.status_code} - {response.text[:200]}")
            return None
            
    except Exception as e:
        print(f"  ⚠️  Registration exception for {email}: {str(e)}")
        return None


def get_events(token):
    """Helper: Get events for a user"""
    try:
        response = requests.get(
            f"{BASE_URL}/events",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            return None
            
    except Exception as e:
        print(f"  ⚠️  Get events exception: {str(e)}")
        return None


def test_city_feed_filtering():
    """Test 2: City feed filtering - events match user's city"""
    print("\n" + "="*80)
    print("TEST 2: CITY FEED FILTERING")
    print("="*80)
    
    cities_to_test = [
        ("Ibiza", "ibiza"),
        ("Madrid", "madrid"),
        ("Barcelona", "barcelona"),
        ("Marbella", "marbella"),
        ("Palma de Mallorca", "mallorca")
    ]
    
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    
    for city_name, city_slug in cities_to_test:
        print(f"\n--- Testing city: {city_name} ---")
        
        # Register user with this city
        email = f"test_{city_slug}_{timestamp}@test.com"
        username = f"test{city_slug}{timestamp}"
        name = f"Test {city_name}"
        
        token = register_user(email, "testpass123", name, username, city_name)
        
        if not token:
            log_test(f"{city_name}: User registration", False, "Failed to register user")
            continue
        
        log_test(f"{city_name}: User registration", True, f"Registered {email}")
        
        # Get events for this user
        events = get_events(token)
        
        if events is None:
            log_test(f"{city_name}: Get events", False, "Failed to fetch events")
            continue
        
        if not isinstance(events, list):
            log_test(f"{city_name}: Events response type", False, f"Expected list, got {type(events)}")
            continue
        
        log_test(f"{city_name}: Get events", True, f"Fetched {len(events)} events")
        
        # Check if we got events
        if len(events) == 0:
            log_test(f"{city_name}: Events count", False, f"Expected >0 events, got 0")
            continue
        else:
            log_test(f"{city_name}: Events count", True, f"Got {len(events)} events")
        
        # Verify ALL events match the user's city
        mismatched_events = []
        for event in events:
            event_city = event.get("city", "")
            if event_city != city_name:
                mismatched_events.append({
                    "id": event.get("id"),
                    "name": event.get("name"),
                    "city": event_city
                })
        
        if mismatched_events:
            log_test(
                f"{city_name}: City filtering", 
                False, 
                f"Found {len(mismatched_events)} events with wrong city: {mismatched_events[:3]}"
            )
        else:
            log_test(f"{city_name}: City filtering", True, f"All {len(events)} events match city '{city_name}'")
        
        # Show sample events
        if events:
            print(f"  Sample events for {city_name}:")
            for event in events[:3]:
                print(f"    - {event.get('name')} @ {event.get('venue')} (city: {event.get('city')})")


def test_share_og_page():
    """Test 3: WhatsApp/social share OG page"""
    print("\n" + "="*80)
    print("TEST 3: SHARE OG PAGE (WhatsApp preview)")
    print("="*80)
    
    # First, get an event ID from Ibiza
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    email = f"test_share_{timestamp}@test.com"
    username = f"testshare{timestamp}"
    
    token = register_user(email, "testpass123", "Test Share", username, "Ibiza")
    
    if not token:
        log_test("Share OG: Get test event", False, "Failed to register user")
        return
    
    events = get_events(token)
    
    if not events or len(events) == 0:
        log_test("Share OG: Get test event", False, "No events available")
        return
    
    event_id = events[0]["id"]
    event_name = events[0]["name"]
    log_test("Share OG: Get test event", True, f"Using event: {event_name} (ID: {event_id})")
    
    # Test valid event share page
    print(f"\n--- Testing share page for event: {event_id} ---")
    
    try:
        # Note: /api/share/event/{id} not /share/event/{id}
        response = requests.get(f"{BASE_URL}/share/event/{event_id}", timeout=10)
        
        if response.status_code != 200:
            log_test("Share OG: Valid event status", False, f"Expected 200, got {response.status_code}")
        else:
            log_test("Share OG: Valid event status", True, "200 OK")
        
        # Check content type
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type:
            log_test("Share OG: Content-Type", True, f"text/html")
        else:
            log_test("Share OG: Content-Type", False, f"Expected text/html, got {content_type}")
        
        html = response.text
        
        # Check for required OG meta tags
        required_tags = [
            ('og:title', '<meta property="og:title"'),
            ('og:description', '<meta property="og:description"'),
            ('og:image', '<meta property="og:image"'),
        ]
        
        for tag_name, tag_pattern in required_tags:
            if tag_pattern in html:
                log_test(f"Share OG: {tag_name} present", True)
            else:
                log_test(f"Share OG: {tag_name} present", False, "Meta tag not found in HTML")
        
        # Check for redirect (meta refresh or JS)
        has_meta_refresh = 'http-equiv="refresh"' in html or 'http-equiv=refresh' in html
        has_js_redirect = 'window.location' in html
        
        if has_meta_refresh or has_js_redirect:
            log_test("Share OG: Redirect present", True, "Has meta refresh or JS redirect")
        else:
            log_test("Share OG: Redirect present", False, "No redirect found")
        
        # Check if redirect points to /event/{id}
        if f"/event/{event_id}" in html:
            log_test("Share OG: Redirect target", True, f"Points to /event/{event_id}")
        else:
            log_test("Share OG: Redirect target", False, f"Should point to /event/{event_id}")
        
        # Check for absolute image URL
        if 'og:image' in html:
            # Extract og:image content
            import re
            og_image_match = re.search(r'<meta property="og:image" content="([^"]+)"', html)
            if og_image_match:
                og_image_url = og_image_match.group(1)
                if og_image_url.startswith("http://") or og_image_url.startswith("https://"):
                    log_test("Share OG: Image URL absolute", True, f"URL: {og_image_url[:80]}...")
                else:
                    log_test("Share OG: Image URL absolute", False, f"Not absolute: {og_image_url}")
        
        print(f"\n  HTML preview (first 500 chars):\n{html[:500]}...")
        
    except Exception as e:
        log_test("Share OG: Valid event", False, f"Exception: {str(e)}")
    
    # Test non-existent event (should redirect to /feed, not crash)
    print(f"\n--- Testing share page for non-existent event ---")
    
    try:
        response = requests.get(f"{BASE_URL}/share/event/doesnotexist-123", timeout=10)
        
        if response.status_code != 200:
            log_test("Share OG: Non-existent event status", False, f"Expected 200, got {response.status_code}")
        else:
            log_test("Share OG: Non-existent event status", True, "200 OK (no crash)")
        
        html = response.text
        
        # Should redirect to /feed
        if "/feed" in html:
            log_test("Share OG: Non-existent redirect", True, "Redirects to /feed")
        else:
            log_test("Share OG: Non-existent redirect", False, "Should redirect to /feed")
        
    except Exception as e:
        log_test("Share OG: Non-existent event", False, f"Exception: {str(e)}")


def test_regression():
    """Test 4: Regression tests"""
    print("\n" + "="*80)
    print("TEST 4: REGRESSION TESTS")
    print("="*80)
    
    # Test POST /auth/register with new city values
    print("\n--- Testing registration with new city values ---")
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    
    for city in ["Ibiza", "Madrid", "Barcelona", "Marbella", "Palma de Mallorca"]:
        email = f"test_reg_{city.lower().replace(' ', '')}_{timestamp}@test.com"
        username = f"testreg{city.lower().replace(' ', '')}{timestamp}"
        
        token = register_user(email, "testpass123", f"Test {city}", username, city)
        
        if token:
            log_test(f"Regression: Register with city '{city}'", True)
        else:
            log_test(f"Regression: Register with city '{city}'", False, "Registration failed")
    
    # Test POST /auth/login
    print("\n--- Testing login ---")
    
    try:
        response = requests.post(
            f"{BASE_URL}/auth/login",
            json={
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            },
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if "token" in data:
                log_test("Regression: Login", True, "Admin login successful")
            else:
                log_test("Regression: Login", False, "No token in response")
        else:
            log_test("Regression: Login", False, f"Status {response.status_code}")
            
    except Exception as e:
        log_test("Regression: Login", False, f"Exception: {str(e)}")
    
    # Test GET /events requires auth (401 without token)
    print("\n--- Testing events endpoint requires auth ---")
    
    try:
        response = requests.get(f"{BASE_URL}/events", timeout=10)
        
        if response.status_code == 401:
            log_test("Regression: Events requires auth", True, "Returns 401 without token")
        else:
            log_test("Regression: Events requires auth", False, f"Expected 401, got {response.status_code}")
            
    except Exception as e:
        log_test("Regression: Events requires auth", False, f"Exception: {str(e)}")


def print_summary():
    """Print test summary"""
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    total = tests_passed + tests_failed
    pass_rate = (tests_passed / total * 100) if total > 0 else 0
    
    print(f"\nTotal tests: {total}")
    print(f"Passed: {tests_passed} ✅")
    print(f"Failed: {tests_failed} ❌")
    print(f"Pass rate: {pass_rate:.1f}%")
    
    if tests_failed > 0:
        print("\n❌ FAILED TESTS:")
        for detail in test_details:
            if not detail["passed"]:
                print(f"  - {detail['test']}")
                if detail["details"]:
                    print(f"    {detail['details']}")
    
    print("\n" + "="*80)
    
    return tests_failed == 0


def main():
    """Run all tests"""
    print("="*80)
    print("BACKEND API TESTING: Multi-City Expansion + WhatsApp Share")
    print("="*80)
    print(f"Base URL: {BASE_URL}")
    print(f"Admin: {ADMIN_EMAIL}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    # Run all tests
    test_cities_endpoint()
    test_city_feed_filtering()
    test_share_og_page()
    test_regression()
    
    # Print summary
    all_passed = print_summary()
    
    # Exit with appropriate code
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
