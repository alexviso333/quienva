#!/usr/bin/env python3
"""
Backend test for two new features:
(A) SEO: empty city pages must be noindex + excluded from sitemap
(B) Dynamic city map coordinates (lat/lng)

Admin credentials: admin@quienva.app / admin123
"""
import requests
import sys
import os
from urllib.parse import quote

# Get backend URL from environment
BACKEND_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001")
API_BASE = f"{BACKEND_URL}/api"

# Admin credentials from test_credentials.md
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

# Test results tracking
tests_passed = 0
tests_failed = 0
failures = []

def log_test(test_num, description, passed, details=""):
    global tests_passed, tests_failed, failures
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"\n{status} - Test {test_num}: {description}")
    if details:
        print(f"  {details}")
    if passed:
        tests_passed += 1
    else:
        tests_failed += 1
        failures.append(f"Test {test_num}: {description} - {details}")

def admin_login():
    """Login as admin and return session with auth cookie/token"""
    resp = requests.post(f"{API_BASE}/auth/login", 
                        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    if resp.status_code != 200:
        print(f"❌ Admin login failed: {resp.status_code} {resp.text}")
        sys.exit(1)
    
    session = requests.Session()
    # Copy cookies from login response
    session.cookies.update(resp.cookies)
    
    # Also try to get token from response body if present
    try:
        data = resp.json()
        if "token" in data:
            session.headers["Authorization"] = f"Bearer {data['token']}"
    except:
        pass
    
    print(f"✅ Admin login successful")
    return session

def test_seo_empty_city():
    """
    === (A) SEO: empty city pages must be noindex + excluded from sitemap ===
    """
    print("\n" + "="*80)
    print("PART A: SEO - Empty City Pages (noindex + sitemap exclusion)")
    print("="*80)
    
    session = admin_login()
    
    # Test 1: Get current cities to identify which have events
    print("\n--- Test 1: GET /api/cities to see current cities ---")
    resp = requests.get(f"{API_BASE}/cities")
    if resp.status_code != 200:
        log_test("1", "GET /api/cities", False, f"Status {resp.status_code}")
        return
    
    cities_data = resp.json()
    cities = cities_data.get("cities", [])
    print(f"Found {len(cities)} cities: {[c.get('label') for c in cities]}")
    log_test("1", "GET /api/cities", True, f"Retrieved {len(cities)} cities")
    
    # Test 2a: Check city with events (e.g., Ibiza) - should be INDEX
    print("\n--- Test 2a: City WITH events (Ibiza) - should be INDEX ---")
    
    # First check if Ibiza has events
    resp = requests.get(f"{API_BASE}/events?city=Ibiza&date_filter=all")
    ibiza_has_events = False
    if resp.status_code == 200:
        events = resp.json().get("events", [])
        ibiza_has_events = len(events) > 0
        print(f"Ibiza has {len(events)} upcoming events")
    
    # Test Spanish city page
    resp = requests.get(f"{API_BASE}/ciudad/ibiza", 
                       headers={"x-forwarded-host": "quienva.me", 
                               "x-forwarded-proto": "https"})
    
    if resp.status_code != 200:
        log_test("2a", "GET /api/ciudad/ibiza (Spanish)", False, 
                f"Status {resp.status_code}")
    else:
        html = resp.text
        has_index_meta = 'content="index,follow' in html
        has_noindex_meta = 'content="noindex' in html
        has_noindex_header = "X-Robots-Tag" in resp.headers and "noindex" in resp.headers.get("X-Robots-Tag", "")
        
        if ibiza_has_events:
            # Should be INDEX (no noindex)
            passed = has_index_meta and not has_noindex_meta and not has_noindex_header
            details = f"Meta: {'index,follow' if has_index_meta else 'NOT FOUND'}, "
            details += f"X-Robots-Tag: {resp.headers.get('X-Robots-Tag', 'NOT PRESENT')}"
            log_test("2a", "Ibiza (WITH events) - should be INDEX", passed, details)
        else:
            # Should be NOINDEX
            passed = has_noindex_meta and has_noindex_header
            details = f"Meta: {'noindex' if has_noindex_meta else 'NOT FOUND'}, "
            details += f"X-Robots-Tag: {resp.headers.get('X-Robots-Tag', 'NOT PRESENT')}"
            log_test("2a", "Ibiza (NO events) - should be NOINDEX", passed, details)
    
    # Test 2b: English city page
    resp = requests.get(f"{API_BASE}/en/city/ibiza",
                       headers={"x-forwarded-host": "quienva.me",
                               "x-forwarded-proto": "https"})
    
    if resp.status_code == 200:
        html = resp.text
        has_index_meta = 'content="index,follow' in html
        has_noindex_meta = 'content="noindex' in html
        has_noindex_header = "X-Robots-Tag" in resp.headers and "noindex" in resp.headers.get("X-Robots-Tag", "")
        
        if ibiza_has_events:
            passed = has_index_meta and not has_noindex_meta and not has_noindex_header
            details = f"Meta: {'index,follow' if has_index_meta else 'NOT FOUND'}"
        else:
            passed = has_noindex_meta and has_noindex_header
            details = f"Meta: {'noindex' if has_noindex_meta else 'NOT FOUND'}"
        
        log_test("2b", "GET /api/en/city/ibiza (English)", passed, details)
    else:
        log_test("2b", "GET /api/en/city/ibiza (English)", False, 
                f"Status {resp.status_code}")
    
    # Test 3: Create a brand-new empty city to test NOINDEX behavior
    print("\n--- Test 3: Create empty test city (should be NOINDEX) ---")
    
    test_city_label = "Testville ZZ"
    test_city_slug = "testville-zz"
    
    # Create the city
    resp = session.post(f"{API_BASE}/admin/cities",
                       json={"label": test_city_label, "emoji": "🧪", 
                            "enabled": True})
    
    if resp.status_code != 200:
        log_test("3a", "POST /api/admin/cities (create test city)", False,
                f"Status {resp.status_code}: {resp.text}")
        return
    
    city_data = resp.json()
    print(f"Created test city: {city_data}")
    log_test("3a", "POST /api/admin/cities (create test city)", True,
            f"Created '{test_city_label}'")
    
    # Test 3b: GET the empty city page - should be NOINDEX
    print(f"\n--- Test 3b: GET empty city page /{test_city_slug} - should be NOINDEX ---")
    
    resp = requests.get(f"{API_BASE}/ciudad/{test_city_slug}",
                       headers={"x-forwarded-host": "quienva.me",
                               "x-forwarded-proto": "https"})
    
    if resp.status_code != 200:
        log_test("3b", f"GET /api/ciudad/{test_city_slug} (empty city)", False,
                f"Status {resp.status_code}")
    else:
        html = resp.text
        has_noindex_meta = 'content="noindex,follow"' in html or 'content="noindex' in html
        has_noindex_header = "X-Robots-Tag" in resp.headers and "noindex" in resp.headers.get("X-Robots-Tag", "")
        
        passed = has_noindex_meta and has_noindex_header
        details = f"Meta robots: {'noindex,follow FOUND' if has_noindex_meta else 'NOT FOUND'}, "
        details += f"X-Robots-Tag: {resp.headers.get('X-Robots-Tag', 'NOT PRESENT')}"
        
        log_test("3b", f"Empty city {test_city_label} - NOINDEX meta tag", 
                has_noindex_meta, details)
        log_test("3c", f"Empty city {test_city_label} - X-Robots-Tag header",
                has_noindex_header, 
                f"Header value: {resp.headers.get('X-Robots-Tag', 'NOT PRESENT')}")
    
    # Test 4: Check sitemap-cities.xml - empty city should NOT appear
    print("\n--- Test 4: GET /api/sitemap-cities.xml - empty city should NOT appear ---")
    
    resp = requests.get(f"{API_BASE}/sitemap-cities.xml",
                       headers={"x-forwarded-host": "quienva.me",
                               "x-forwarded-proto": "https"})
    
    if resp.status_code != 200:
        log_test("4a", "GET /api/sitemap-cities.xml", False,
                f"Status {resp.status_code}")
    else:
        xml = resp.text
        
        # Homepage should always be present
        has_homepage = '<loc>https://www.quienva.me/</loc>' in xml or '<loc>https://quienva.me/</loc>' in xml
        log_test("4a", "Sitemap contains homepage /", has_homepage,
                "Homepage <loc> found" if has_homepage else "Homepage NOT FOUND")
        
        # Ibiza should be present if it has events
        has_ibiza = 'ibiza' in xml.lower()
        if ibiza_has_events:
            log_test("4b", "Sitemap contains Ibiza (has events)", has_ibiza,
                    "Ibiza found in sitemap" if has_ibiza else "Ibiza NOT FOUND")
        
        # Empty test city should NOT be present
        has_testville = test_city_slug in xml.lower() or test_city_label.lower() in xml.lower()
        log_test("4c", f"Sitemap does NOT contain empty city '{test_city_label}'",
                not has_testville,
                "Empty city correctly excluded" if not has_testville else "❌ Empty city FOUND in sitemap")
    
    # Cleanup: Delete the test city
    print(f"\n--- Cleanup: Delete test city '{test_city_label}' ---")
    city_id_encoded = quote(test_city_label)
    resp = session.delete(f"{API_BASE}/admin/cities/{city_id_encoded}")
    if resp.status_code == 200:
        print(f"✅ Test city '{test_city_label}' deleted successfully")
    else:
        print(f"⚠️  Failed to delete test city: {resp.status_code}")

def test_dynamic_city_coordinates():
    """
    === (B) Dynamic city map coordinates ===
    """
    print("\n" + "="*80)
    print("PART B: Dynamic City Map Coordinates (lat/lng)")
    print("="*80)
    
    session = admin_login()
    
    # Test 5: GET /api/cities - verify lat/lng present
    print("\n--- Test 5: GET /api/cities - verify lat/lng for all cities ---")
    
    resp = requests.get(f"{API_BASE}/cities")
    if resp.status_code != 200:
        log_test("5", "GET /api/cities", False, f"Status {resp.status_code}")
        return
    
    cities_data = resp.json()
    cities = cities_data.get("cities", [])
    
    all_have_coords = True
    for city in cities:
        label = city.get("label", "")
        lat = city.get("lat")
        lng = city.get("lng")
        
        if lat is None or lng is None:
            print(f"  ❌ {label}: lat={lat}, lng={lng} (MISSING)")
            all_have_coords = False
        else:
            print(f"  ✅ {label}: lat={lat}, lng={lng}")
            
            # Verify Sevilla coordinates
            if "Sevilla" in label:
                # Should be approximately lat 37.389, lng -5.984
                lat_ok = 37.0 < lat < 38.0
                lng_ok = -6.5 < lng < -5.5
                if lat_ok and lng_ok:
                    log_test("5a", f"Sevilla coordinates (~37.389, -5.984)", True,
                            f"lat={lat}, lng={lng}")
                else:
                    log_test("5a", f"Sevilla coordinates (~37.389, -5.984)", False,
                            f"lat={lat}, lng={lng} - OUT OF RANGE")
            
            # Verify Madrid coordinates
            if "Madrid" in label:
                # Should be approximately lat 40.416, lng -3.703
                lat_ok = 40.0 < lat < 41.0
                lng_ok = -4.0 < lng < -3.0
                if lat_ok and lng_ok:
                    log_test("5b", f"Madrid coordinates (~40.416, -3.703)", True,
                            f"lat={lat}, lng={lng}")
                else:
                    log_test("5b", f"Madrid coordinates (~40.416, -3.703)", False,
                            f"lat={lat}, lng={lng} - OUT OF RANGE")
    
    log_test("5", "All cities have lat/lng", all_have_coords,
            f"{len(cities)} cities checked")
    
    # Test 6: POST /api/admin/cities with explicit lat/lng
    print("\n--- Test 6: POST /api/admin/cities with explicit lat/lng ---")
    
    test_city_label = "CoordTest City"
    test_lat = 10.5
    test_lng = 20.25
    
    resp = session.post(f"{API_BASE}/admin/cities",
                       json={"label": test_city_label, "emoji": "📍",
                            "lat": test_lat, "lng": test_lng, "enabled": True})
    
    if resp.status_code != 200:
        log_test("6a", "POST /api/admin/cities with lat/lng", False,
                f"Status {resp.status_code}: {resp.text}")
    else:
        city_data = resp.json()
        created_lat = city_data.get("lat")
        created_lng = city_data.get("lng")
        
        passed = created_lat == test_lat and created_lng == test_lng
        log_test("6a", "POST /api/admin/cities with lat/lng", passed,
                f"Created with lat={created_lat}, lng={created_lng}")
    
    # Test 6b: Verify in GET /api/cities
    print("\n--- Test 6b: Verify new city appears in GET /api/cities with correct coords ---")
    
    resp = requests.get(f"{API_BASE}/cities")
    if resp.status_code == 200:
        cities = resp.json().get("cities", [])
        coord_city = next((c for c in cities if c.get("label") == test_city_label), None)
        
        if coord_city:
            lat = coord_city.get("lat")
            lng = coord_city.get("lng")
            passed = lat == test_lat and lng == test_lng
            log_test("6b", f"GET /api/cities contains '{test_city_label}' with correct coords",
                    passed, f"lat={lat}, lng={lng}")
        else:
            log_test("6b", f"GET /api/cities contains '{test_city_label}'", False,
                    "City not found in response")
    
    # Cleanup
    print(f"\n--- Cleanup: Delete '{test_city_label}' ---")
    city_id_encoded = quote(test_city_label)
    resp = session.delete(f"{API_BASE}/admin/cities/{city_id_encoded}")
    if resp.status_code == 200:
        print(f"✅ Test city '{test_city_label}' deleted")
    
    # Test 7: POST /api/admin/cities WITHOUT lat/lng - should auto-fill from defaults
    print("\n--- Test 7: POST /api/admin/cities WITHOUT lat/lng (auto-fill from defaults) ---")
    
    test_city_label = "Valencia"
    
    resp = session.post(f"{API_BASE}/admin/cities",
                       json={"label": test_city_label, "enabled": True})
    
    if resp.status_code != 200:
        log_test("7a", "POST /api/admin/cities without lat/lng", False,
                f"Status {resp.status_code}: {resp.text}")
    else:
        city_data = resp.json()
        lat = city_data.get("lat")
        lng = city_data.get("lng")
        
        # Valencia default should be approximately lat 39.46, lng -0.37
        has_coords = lat is not None and lng is not None
        if has_coords:
            lat_ok = 39.0 < lat < 40.0
            lng_ok = -1.0 < lng < 0.0
            passed = lat_ok and lng_ok
            log_test("7a", "Valencia auto-filled with default coords (~39.46, -0.37)",
                    passed, f"lat={lat}, lng={lng}")
        else:
            log_test("7a", "Valencia auto-filled with default coords", False,
                    f"lat={lat}, lng={lng} - NO COORDS")
    
    # Test 7b: Verify in GET /api/cities
    resp = requests.get(f"{API_BASE}/cities")
    if resp.status_code == 200:
        cities = resp.json().get("cities", [])
        valencia = next((c for c in cities if c.get("label") == test_city_label), None)
        
        if valencia:
            lat = valencia.get("lat")
            lng = valencia.get("lng")
            has_coords = lat is not None and lng is not None
            if has_coords:
                lat_ok = 39.0 < lat < 40.0
                lng_ok = -1.0 < lng < 0.0
                passed = lat_ok and lng_ok
                log_test("7b", f"GET /api/cities shows Valencia with coords", passed,
                        f"lat={lat}, lng={lng}")
            else:
                log_test("7b", f"GET /api/cities shows Valencia with coords", False,
                        "No coords found")
        else:
            log_test("7b", "GET /api/cities contains Valencia", False,
                    "City not found")
    
    # Cleanup
    print(f"\n--- Cleanup: Delete '{test_city_label}' ---")
    city_id_encoded = quote(test_city_label)
    resp = session.delete(f"{API_BASE}/admin/cities/{city_id_encoded}")
    if resp.status_code == 200:
        print(f"✅ Test city '{test_city_label}' deleted")

def main():
    print("="*80)
    print("BACKEND TEST: SEO Empty Cities + Dynamic City Coordinates")
    print("="*80)
    print(f"Backend URL: {API_BASE}")
    print(f"Admin: {ADMIN_EMAIL}")
    
    try:
        # Part A: SEO empty city pages
        test_seo_empty_city()
        
        # Part B: Dynamic city coordinates
        test_dynamic_city_coordinates()
        
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"✅ Passed: {tests_passed}")
    print(f"❌ Failed: {tests_failed}")
    print(f"Total: {tests_passed + tests_failed}")
    
    if failures:
        print("\n❌ FAILED TESTS:")
        for failure in failures:
            print(f"  - {failure}")
    
    if tests_failed == 0:
        print("\n🎉 ALL TESTS PASSED!")
        sys.exit(0)
    else:
        print(f"\n❌ {tests_failed} TEST(S) FAILED")
        sys.exit(1)

if __name__ == "__main__":
    main()
