#!/usr/bin/env python3
"""
Backend Test: DYNAMIC CITIES Admin Feature (Fase 1)
Tests all admin city CRUD endpoints + scraped venue city reassignment
"""

import requests
import sys
import os
from datetime import datetime

# Get backend URL from environment
BACKEND_URL = os.getenv("REACT_APP_BACKEND_URL", "https://who-goes-planner.preview.emergentagent.com")
BASE_URL = f"{BACKEND_URL}/api"

# Admin credentials from backend/.env
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

# Test data
TEST_CITY_NAME = "Sevilla"
TEST_CITY_EMOJI = "🍊"

def print_test(msg):
    print(f"\n{'='*80}")
    print(f"TEST: {msg}")
    print('='*80)

def print_result(passed, msg):
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status}: {msg}")
    return passed

def login_admin():
    """Login as admin and return auth token"""
    print_test("Admin Login")
    url = f"{BASE_URL}/auth/login"
    payload = {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    
    try:
        resp = requests.post(url, json=payload, timeout=10)
        print(f"POST {url}")
        print(f"Status: {resp.status_code}")
        
        if resp.status_code != 200:
            print(f"Response: {resp.text}")
            print_result(False, f"Admin login failed with status {resp.status_code}")
            return None
        
        data = resp.json()
        token = data.get("token")
        
        if not token:
            print_result(False, "No token in login response")
            return None
        
        print_result(True, f"Admin login successful, token: {token[:20]}...")
        return token
    
    except Exception as e:
        print_result(False, f"Admin login exception: {e}")
        return None

def test_1_get_admin_cities(token):
    """Test 1: GET /api/admin/cities (requires admin)"""
    print_test("1. GET /api/admin/cities (admin required)")
    
    all_passed = True
    
    # Test 1a: Without auth token (should return 403 or 401)
    print("\n1a. Testing WITHOUT admin token (should return 403)...")
    url = f"{BASE_URL}/admin/cities"
    try:
        resp = requests.get(url, timeout=10)
        print(f"GET {url} (no auth)")
        print(f"Status: {resp.status_code}")
        
        if resp.status_code in [401, 403]:
            print_result(True, f"Correctly rejected with {resp.status_code}")
        else:
            all_passed = print_result(False, f"Expected 401/403, got {resp.status_code}")
    except Exception as e:
        all_passed = print_result(False, f"Exception: {e}")
    
    # Test 1b: With admin token (should return 200 with cities list)
    print("\n1b. Testing WITH admin token (should return 200)...")
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        print(f"GET {url} (with admin auth)")
        print(f"Status: {resp.status_code}")
        
        if resp.status_code != 200:
            print(f"Response: {resp.text}")
            all_passed = print_result(False, f"Expected 200, got {resp.status_code}")
            return all_passed
        
        data = resp.json()
        print(f"Response keys: {list(data.keys())}")
        
        # Verify response structure
        if "cities" not in data:
            all_passed = print_result(False, "Missing 'cities' key in response")
            return all_passed
        
        if "pending_city" not in data:
            all_passed = print_result(False, "Missing 'pending_city' key in response")
            return all_passed
        
        if "pending_events" not in data:
            all_passed = print_result(False, "Missing 'pending_events' key in response")
            return all_passed
        
        cities = data["cities"]
        pending_city = data["pending_city"]
        pending_events = data["pending_events"]
        
        print(f"Cities count: {len(cities)}")
        print(f"Pending city: {pending_city}")
        print(f"Pending events: {pending_events}")
        
        # Verify 5 seeded cities exist (note: Marbella is seeded as "Marbella / Puerto Banús")
        expected_cities = ["Palma de Mallorca", "Ibiza", "Madrid", "Barcelona", "Marbella / Puerto Banús"]
        city_labels = [c.get("label") for c in cities]
        
        print(f"\nCity labels found: {city_labels}")
        
        for expected in expected_cities:
            if expected in city_labels:
                print_result(True, f"Found seeded city: {expected}")
            else:
                all_passed = print_result(False, f"Missing seeded city: {expected}")
        
        # Verify each city has required fields
        print("\nVerifying city structure...")
        for city in cities:
            required_fields = ["id", "label", "emoji", "enabled", "events_upcoming"]
            missing = [f for f in required_fields if f not in city]
            if missing:
                all_passed = print_result(False, f"City '{city.get('label')}' missing fields: {missing}")
            else:
                print(f"  ✓ City '{city.get('label')}' has all required fields")
        
        if all_passed:
            print_result(True, "GET /api/admin/cities returns correct structure with 5 seeded cities")
        
    except Exception as e:
        all_passed = print_result(False, f"Exception: {e}")
    
    return all_passed

def test_2_create_city(token):
    """Test 2: POST /api/admin/cities to create Sevilla"""
    print_test("2. POST /api/admin/cities (create Sevilla)")
    
    all_passed = True
    
    # Test 2a: Create Sevilla
    print("\n2a. Creating city 'Sevilla' with emoji '🍊'...")
    url = f"{BASE_URL}/admin/cities"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"label": TEST_CITY_NAME, "emoji": TEST_CITY_EMOJI}
    
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        print(f"POST {url}")
        print(f"Payload: {payload}")
        print(f"Status: {resp.status_code}")
        
        if resp.status_code != 200:
            print(f"Response: {resp.text}")
            all_passed = print_result(False, f"Expected 200, got {resp.status_code}")
            return all_passed
        
        data = resp.json()
        print(f"Created city: {data}")
        
        # Verify response
        if data.get("id") != TEST_CITY_NAME:
            all_passed = print_result(False, f"Expected id='{TEST_CITY_NAME}', got '{data.get('id')}'")
        else:
            print_result(True, f"City created with id='{TEST_CITY_NAME}'")
        
        if data.get("label") != TEST_CITY_NAME:
            all_passed = print_result(False, f"Expected label='{TEST_CITY_NAME}', got '{data.get('label')}'")
        else:
            print_result(True, f"City has correct label")
        
        if data.get("emoji") != TEST_CITY_EMOJI:
            all_passed = print_result(False, f"Expected emoji='{TEST_CITY_EMOJI}', got '{data.get('emoji')}'")
        else:
            print_result(True, f"City has correct emoji")
        
    except Exception as e:
        all_passed = print_result(False, f"Exception: {e}")
        return all_passed
    
    # Test 2b: Verify Sevilla appears in public /api/cities
    print("\n2b. Verifying Sevilla appears in public GET /api/cities...")
    url = f"{BASE_URL}/cities"
    try:
        resp = requests.get(url, timeout=10)
        print(f"GET {url} (public, no auth)")
        print(f"Status: {resp.status_code}")
        
        if resp.status_code != 200:
            print(f"Response: {resp.text}")
            all_passed = print_result(False, f"Expected 200, got {resp.status_code}")
            return all_passed
        
        data = resp.json()
        cities = data.get("cities", [])
        city_labels = [c.get("label") for c in cities]
        
        print(f"Public cities: {city_labels}")
        
        if TEST_CITY_NAME in city_labels:
            print_result(True, f"'{TEST_CITY_NAME}' now appears in public cities list")
        else:
            all_passed = print_result(False, f"'{TEST_CITY_NAME}' NOT found in public cities list")
    
    except Exception as e:
        all_passed = print_result(False, f"Exception: {e}")
    
    # Test 2c: Try creating Sevilla again (should return 400 - already exists)
    print("\n2c. Attempting to create Sevilla again (should return 400)...")
    url = f"{BASE_URL}/admin/cities"
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        print(f"POST {url}")
        print(f"Status: {resp.status_code}")
        
        if resp.status_code == 400:
            print(f"Response: {resp.text}")
            print_result(True, "Correctly rejected duplicate city with 400")
        else:
            all_passed = print_result(False, f"Expected 400, got {resp.status_code}")
    
    except Exception as e:
        all_passed = print_result(False, f"Exception: {e}")
    
    return all_passed

def test_3_toggle_city(token):
    """Test 3: POST /api/admin/cities/Sevilla/toggle"""
    print_test("3. POST /api/admin/cities/Sevilla/toggle (disable/enable)")
    
    all_passed = True
    
    # Test 3a: Toggle to disabled
    print("\n3a. Toggling Sevilla to DISABLED...")
    url = f"{BASE_URL}/admin/cities/{TEST_CITY_NAME}/toggle"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        resp = requests.post(url, headers=headers, timeout=10)
        print(f"POST {url}")
        print(f"Status: {resp.status_code}")
        
        if resp.status_code != 200:
            print(f"Response: {resp.text}")
            all_passed = print_result(False, f"Expected 200, got {resp.status_code}")
            return all_passed
        
        data = resp.json()
        print(f"Response: {data}")
        
        if data.get("enabled") == False:
            print_result(True, "Sevilla toggled to disabled (enabled=false)")
        else:
            all_passed = print_result(False, f"Expected enabled=false, got {data.get('enabled')}")
    
    except Exception as e:
        all_passed = print_result(False, f"Exception: {e}")
        return all_passed
    
    # Test 3b: Verify Sevilla does NOT appear in public /api/cities (disabled cities hidden)
    print("\n3b. Verifying Sevilla does NOT appear in public GET /api/cities (disabled)...")
    url = f"{BASE_URL}/cities"
    try:
        resp = requests.get(url, timeout=10)
        print(f"GET {url}")
        print(f"Status: {resp.status_code}")
        
        if resp.status_code != 200:
            print(f"Response: {resp.text}")
            all_passed = print_result(False, f"Expected 200, got {resp.status_code}")
            return all_passed
        
        data = resp.json()
        cities = data.get("cities", [])
        city_labels = [c.get("label") for c in cities]
        
        print(f"Public cities: {city_labels}")
        
        if TEST_CITY_NAME not in city_labels:
            print_result(True, f"'{TEST_CITY_NAME}' correctly hidden from public list (disabled)")
        else:
            all_passed = print_result(False, f"'{TEST_CITY_NAME}' should NOT appear when disabled")
    
    except Exception as e:
        all_passed = print_result(False, f"Exception: {e}")
    
    # Test 3c: Toggle again to re-enable
    print("\n3c. Toggling Sevilla to ENABLED again...")
    url = f"{BASE_URL}/admin/cities/{TEST_CITY_NAME}/toggle"
    try:
        resp = requests.post(url, headers=headers, timeout=10)
        print(f"POST {url}")
        print(f"Status: {resp.status_code}")
        
        if resp.status_code != 200:
            print(f"Response: {resp.text}")
            all_passed = print_result(False, f"Expected 200, got {resp.status_code}")
            return all_passed
        
        data = resp.json()
        print(f"Response: {data}")
        
        if data.get("enabled") == True:
            print_result(True, "Sevilla toggled to enabled (enabled=true)")
        else:
            all_passed = print_result(False, f"Expected enabled=true, got {data.get('enabled')}")
    
    except Exception as e:
        all_passed = print_result(False, f"Exception: {e}")
        return all_passed
    
    # Test 3d: Verify Sevilla reappears in public /api/cities
    print("\n3d. Verifying Sevilla reappears in public GET /api/cities (re-enabled)...")
    url = f"{BASE_URL}/cities"
    try:
        resp = requests.get(url, timeout=10)
        print(f"GET {url}")
        print(f"Status: {resp.status_code}")
        
        if resp.status_code != 200:
            print(f"Response: {resp.text}")
            all_passed = print_result(False, f"Expected 200, got {resp.status_code}")
            return all_passed
        
        data = resp.json()
        cities = data.get("cities", [])
        city_labels = [c.get("label") for c in cities]
        
        print(f"Public cities: {city_labels}")
        
        if TEST_CITY_NAME in city_labels:
            print_result(True, f"'{TEST_CITY_NAME}' reappears in public list (re-enabled)")
        else:
            all_passed = print_result(False, f"'{TEST_CITY_NAME}' should appear when re-enabled")
    
    except Exception as e:
        all_passed = print_result(False, f"Exception: {e}")
    
    return all_passed

def test_4_delete_city(token):
    """Test 4: DELETE /api/admin/cities/Sevilla"""
    print_test("4. DELETE /api/admin/cities/Sevilla")
    
    all_passed = True
    
    # Test 4a: Delete Sevilla
    print("\n4a. Deleting city 'Sevilla'...")
    url = f"{BASE_URL}/admin/cities/{TEST_CITY_NAME}"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        resp = requests.delete(url, headers=headers, timeout=10)
        print(f"DELETE {url}")
        print(f"Status: {resp.status_code}")
        
        if resp.status_code != 200:
            print(f"Response: {resp.text}")
            all_passed = print_result(False, f"Expected 200, got {resp.status_code}")
            return all_passed
        
        data = resp.json()
        print(f"Response: {data}")
        
        # Verify response structure
        if "ok" not in data or data["ok"] != True:
            all_passed = print_result(False, "Expected ok=true in response")
        else:
            print_result(True, "City deleted successfully (ok=true)")
        
        if "events_moved" not in data:
            all_passed = print_result(False, "Missing 'events_moved' in response")
        else:
            print(f"  Events moved to Pendiente: {data['events_moved']}")
        
        if "venues_moved" not in data:
            all_passed = print_result(False, "Missing 'venues_moved' in response")
        else:
            print(f"  Venues moved to Pendiente: {data['venues_moved']}")
    
    except Exception as e:
        all_passed = print_result(False, f"Exception: {e}")
        return all_passed
    
    # Test 4b: Verify Sevilla does NOT appear in public /api/cities
    print("\n4b. Verifying Sevilla does NOT appear in public GET /api/cities (deleted)...")
    url = f"{BASE_URL}/cities"
    try:
        resp = requests.get(url, timeout=10)
        print(f"GET {url}")
        print(f"Status: {resp.status_code}")
        
        if resp.status_code != 200:
            print(f"Response: {resp.text}")
            all_passed = print_result(False, f"Expected 200, got {resp.status_code}")
            return all_passed
        
        data = resp.json()
        cities = data.get("cities", [])
        city_labels = [c.get("label") for c in cities]
        
        print(f"Public cities: {city_labels}")
        
        if TEST_CITY_NAME not in city_labels:
            print_result(True, f"'{TEST_CITY_NAME}' correctly removed from public list (deleted)")
        else:
            all_passed = print_result(False, f"'{TEST_CITY_NAME}' should NOT appear after deletion")
    
    except Exception as e:
        all_passed = print_result(False, f"Exception: {e}")
    
    return all_passed

def test_5_scraped_venue_city_reassignment(token):
    """Test 5: Scraped venue city reassignment via PUT /api/admin/scrapers/{id}"""
    print_test("5. Scraped venue city reassignment (PUT /api/admin/scrapers/{id})")
    
    all_passed = True
    
    # Test 5a: Get list of scraped venues
    print("\n5a. Getting list of scraped venues...")
    url = f"{BASE_URL}/admin/scrapers"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        print(f"GET {url}")
        print(f"Status: {resp.status_code}")
        
        if resp.status_code != 200:
            print(f"Response: {resp.text}")
            all_passed = print_result(False, f"Expected 200, got {resp.status_code}")
            return all_passed
        
        venues = resp.json()
        print(f"Total scraped venues: {len(venues)}")
        
        if len(venues) == 0:
            all_passed = print_result(False, "No scraped venues found to test with")
            return all_passed
        
        # Pick the first venue with a city
        test_venue = None
        for v in venues:
            if v.get("city") and v.get("city") != "Pendiente":
                test_venue = v
                break
        
        if not test_venue:
            all_passed = print_result(False, "No suitable venue found (all are Pendiente)")
            return all_passed
        
        venue_id = test_venue["id"]
        venue_name = test_venue["name"]
        original_city = test_venue["city"]
        
        print(f"\nSelected test venue:")
        print(f"  ID: {venue_id}")
        print(f"  Name: {venue_name}")
        print(f"  Original city: {original_city}")
        
        print_result(True, f"Found test venue: {venue_name} (city: {original_city})")
        
    except Exception as e:
        all_passed = print_result(False, f"Exception: {e}")
        return all_passed
    
    # Test 5b: Change venue city to "Pendiente"
    print("\n5b. Changing venue city to 'Pendiente'...")
    url = f"{BASE_URL}/admin/scrapers/{venue_id}"
    
    # Build the full venue object with city changed to "Pendiente"
    # Note: ScrapedVenueInput only has: name, city, adapter_type, url, slug, active
    payload = {
        "name": test_venue["name"],
        "city": "Pendiente",
        "adapter_type": test_venue["adapter_type"],
        "url": test_venue["url"],
        "slug": test_venue.get("slug", ""),
        "active": test_venue.get("active", True)
    }
    
    try:
        resp = requests.put(url, json=payload, headers=headers, timeout=10)
        print(f"PUT {url}")
        print(f"Payload: {payload}")
        print(f"Status: {resp.status_code}")
        
        if resp.status_code != 200:
            print(f"Response: {resp.text}")
            all_passed = print_result(False, f"Expected 200, got {resp.status_code}")
            return all_passed
        
        data = resp.json()
        print(f"Updated venue city: {data.get('city')}")
        
        if data.get("city") == "Pendiente":
            print_result(True, "Venue city changed to 'Pendiente'")
        else:
            all_passed = print_result(False, f"Expected city='Pendiente', got '{data.get('city')}'")
    
    except Exception as e:
        all_passed = print_result(False, f"Exception: {e}")
        return all_passed
    
    # Test 5c: Verify the change persists (re-GET the venue)
    print("\n5c. Verifying the change persists (re-GET scrapers)...")
    url = f"{BASE_URL}/admin/scrapers"
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        print(f"GET {url}")
        print(f"Status: {resp.status_code}")
        
        if resp.status_code != 200:
            print(f"Response: {resp.text}")
            all_passed = print_result(False, f"Expected 200, got {resp.status_code}")
            return all_passed
        
        venues = resp.json()
        updated_venue = next((v for v in venues if v["id"] == venue_id), None)
        
        if not updated_venue:
            all_passed = print_result(False, "Venue not found after update")
            return all_passed
        
        if updated_venue.get("city") == "Pendiente":
            print_result(True, "Venue city persisted as 'Pendiente'")
        else:
            all_passed = print_result(False, f"Expected city='Pendiente', got '{updated_venue.get('city')}'")
    
    except Exception as e:
        all_passed = print_result(False, f"Exception: {e}")
        return all_passed
    
    # Test 5d: Change venue city back to original
    print(f"\n5d. Changing venue city back to original '{original_city}'...")
    url = f"{BASE_URL}/admin/scrapers/{venue_id}"
    payload["city"] = original_city
    
    try:
        resp = requests.put(url, json=payload, headers=headers, timeout=10)
        print(f"PUT {url}")
        print(f"Payload city: {original_city}")
        print(f"Status: {resp.status_code}")
        
        if resp.status_code != 200:
            print(f"Response: {resp.text}")
            all_passed = print_result(False, f"Expected 200, got {resp.status_code}")
            return all_passed
        
        data = resp.json()
        print(f"Updated venue city: {data.get('city')}")
        
        if data.get("city") == original_city:
            print_result(True, f"Venue city restored to '{original_city}'")
        else:
            all_passed = print_result(False, f"Expected city='{original_city}', got '{data.get('city')}'")
    
    except Exception as e:
        all_passed = print_result(False, f"Exception: {e}")
        return all_passed
    
    # Test 5e: Verify the restoration persists
    print("\n5e. Verifying the restoration persists (re-GET scrapers)...")
    url = f"{BASE_URL}/admin/scrapers"
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        print(f"GET {url}")
        print(f"Status: {resp.status_code}")
        
        if resp.status_code != 200:
            print(f"Response: {resp.text}")
            all_passed = print_result(False, f"Expected 200, got {resp.status_code}")
            return all_passed
        
        venues = resp.json()
        restored_venue = next((v for v in venues if v["id"] == venue_id), None)
        
        if not restored_venue:
            all_passed = print_result(False, "Venue not found after restoration")
            return all_passed
        
        if restored_venue.get("city") == original_city:
            print_result(True, f"Venue city persisted as '{original_city}' (restored)")
        else:
            all_passed = print_result(False, f"Expected city='{original_city}', got '{restored_venue.get('city')}'")
    
    except Exception as e:
        all_passed = print_result(False, f"Exception: {e}")
    
    return all_passed

def main():
    print("\n" + "="*80)
    print("BACKEND TEST: DYNAMIC CITIES ADMIN FEATURE (Fase 1)")
    print("="*80)
    print(f"Backend URL: {BACKEND_URL}")
    print(f"Test started: {datetime.now().isoformat()}")
    print("="*80)
    
    # Login as admin
    token = login_admin()
    if not token:
        print("\n❌ FATAL: Admin login failed. Cannot proceed with tests.")
        sys.exit(1)
    
    # Run all tests
    results = []
    
    results.append(("Test 1: GET /api/admin/cities", test_1_get_admin_cities(token)))
    results.append(("Test 2: POST /api/admin/cities (create Sevilla)", test_2_create_city(token)))
    results.append(("Test 3: POST /api/admin/cities/Sevilla/toggle", test_3_toggle_city(token)))
    results.append(("Test 4: DELETE /api/admin/cities/Sevilla", test_4_delete_city(token)))
    results.append(("Test 5: PUT /api/admin/scrapers/{id} (city reassignment)", test_5_scraped_venue_city_reassignment(token)))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print("\n" + "="*80)
    print(f"OVERALL: {passed}/{total} tests passed ({100*passed//total}%)")
    print("="*80)
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED! Dynamic cities admin feature is working correctly.")
        sys.exit(0)
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please review the failures above.")
        sys.exit(1)

if __name__ == "__main__":
    main()
