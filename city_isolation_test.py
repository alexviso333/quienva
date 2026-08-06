#!/usr/bin/env python3
"""
City Isolation Testing for ¿Quién va?
Tests that each city operates as its own isolated app with proper region grouping.
"""
import requests
import json
from datetime import datetime

# Base URL from frontend/.env
BASE_URL = "https://mern-deployment-3.preview.emergentagent.com/api"

# Admin credentials (Palma de Mallorca user)
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

# Test results
results = []

def log_test(name, passed, details=""):
    """Log test result"""
    status = "✅ PASS" if passed else "❌ FAIL"
    results.append({"name": name, "passed": passed, "details": details})
    print(f"{status}: {name}")
    if details:
        print(f"  {details}")

def register_user(email, password, name, username, city, birthdate="2000-01-01"):
    """Register a new user"""
    url = f"{BASE_URL}/auth/register"
    payload = {
        "email": email,
        "password": password,
        "name": name,
        "username": username,
        "city": city,
        "birthdate": birthdate
    }
    resp = requests.post(url, json=payload)
    return resp

def login(email, password):
    """Login and return token"""
    url = f"{BASE_URL}/auth/login"
    payload = {"email": email, "password": password}
    resp = requests.post(url, json=payload)
    if resp.status_code == 200:
        return resp.json().get("token")
    return None

def get_venues(token):
    """Get venues for authenticated user"""
    url = f"{BASE_URL}/venues"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers)
    return resp

def get_zones(token):
    """Get zones for authenticated user"""
    url = f"{BASE_URL}/venues/meta/zones"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers)
    return resp

def get_events(token):
    """Get events for authenticated user"""
    url = f"{BASE_URL}/events"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers)
    return resp

def get_cities():
    """Get public cities list"""
    url = f"{BASE_URL}/cities"
    resp = requests.get(url)
    return resp

def get_share_event(event_id):
    """Get share page for event (public)"""
    url = f"{BASE_URL}/share/event/{event_id}"
    resp = requests.get(url)
    return resp

print("=" * 80)
print("CITY ISOLATION TESTING - ¿Quién va?")
print("=" * 80)
print()

# Mallorca region cities for validation
MALLORCA_REGION = [
    "Palma de Mallorca", "Mallorca", "Magaluf", "Can Picafort", "Alcúdia",
    "Cala Rajada", "Calvià", "Llucmajor", "Santa Ponsa", "Santanyí",
    "Cala d'Or", "Peguera", "Portals", "Sa Coma", "El Arenal", "s'Arenal"
]

# Test 1: VENUES ISOLATION - Ibiza user
print("\n" + "=" * 80)
print("TEST 1: VENUES ISOLATION - Ibiza User")
print("=" * 80)

timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
ibiza_email = f"ibiza_user_{timestamp}@test.com"
ibiza_username = f"ibizauser{timestamp}"

resp = register_user(ibiza_email, "test1234", "Ibiza User", ibiza_username, "Ibiza")
if resp.status_code == 200:
    log_test("Register Ibiza user", True, f"Email: {ibiza_email}")
    ibiza_token = login(ibiza_email, "test1234")
    
    if ibiza_token:
        log_test("Login Ibiza user", True)
        
        # Get venues for Ibiza user
        venues_resp = get_venues(ibiza_token)
        if venues_resp.status_code == 200:
            venues = venues_resp.json()
            log_test("GET /api/venues as Ibiza user", True, f"Returned {len(venues)} venues")
            
            if len(venues) > 0:
                log_test("Ibiza user sees >0 venues", True, f"Count: {len(venues)}")
                
                # Check all venues are Ibiza
                all_ibiza = all(v.get("city") == "Ibiza" for v in venues)
                log_test("All venues have city='Ibiza'", all_ibiza, 
                        f"Cities found: {set(v.get('city') for v in venues)}")
                
                # Check all venues have lat/lng
                all_have_coords = all(
                    v.get("lat") is not None and v.get("lng") is not None 
                    for v in venues
                )
                log_test("All Ibiza venues have lat AND lng", all_have_coords,
                        f"Venues without coords: {sum(1 for v in venues if v.get('lat') is None or v.get('lng') is None)}")
            else:
                log_test("Ibiza user sees >0 venues", False, "No venues returned")
        else:
            log_test("GET /api/venues as Ibiza user", False, f"Status: {venues_resp.status_code}")
    else:
        log_test("Login Ibiza user", False)
else:
    log_test("Register Ibiza user", False, f"Status: {resp.status_code}")

# Test 2: VENUES ISOLATION - Madrid user
print("\n" + "=" * 80)
print("TEST 2: VENUES ISOLATION - Madrid User")
print("=" * 80)

madrid_email = f"madrid_user_{timestamp}@test.com"
madrid_username = f"madriduser{timestamp}"

resp = register_user(madrid_email, "test1234", "Madrid User", madrid_username, "Madrid")
if resp.status_code == 200:
    log_test("Register Madrid user", True, f"Email: {madrid_email}")
    madrid_token = login(madrid_email, "test1234")
    
    if madrid_token:
        log_test("Login Madrid user", True)
        
        venues_resp = get_venues(madrid_token)
        if venues_resp.status_code == 200:
            venues = venues_resp.json()
            log_test("GET /api/venues as Madrid user", True, f"Returned {len(venues)} venues")
            
            if len(venues) > 0:
                log_test("Madrid user sees >0 venues", True, f"Count: {len(venues)}")
                
                all_madrid = all(v.get("city") == "Madrid" for v in venues)
                log_test("All venues have city='Madrid'", all_madrid,
                        f"Cities found: {set(v.get('city') for v in venues)}")
                
                all_have_coords = all(
                    v.get("lat") is not None and v.get("lng") is not None 
                    for v in venues
                )
                log_test("All Madrid venues have lat AND lng", all_have_coords)
            else:
                log_test("Madrid user sees >0 venues", False, "No venues returned")
        else:
            log_test("GET /api/venues as Madrid user", False, f"Status: {venues_resp.status_code}")
    else:
        log_test("Login Madrid user", False)
else:
    log_test("Register Madrid user", False, f"Status: {resp.status_code}")

# Test 3: VENUES ISOLATION - Barcelona user
print("\n" + "=" * 80)
print("TEST 3: VENUES ISOLATION - Barcelona User")
print("=" * 80)

barcelona_email = f"barcelona_user_{timestamp}@test.com"
barcelona_username = f"barcelonauser{timestamp}"

resp = register_user(barcelona_email, "test1234", "Barcelona User", barcelona_username, "Barcelona")
if resp.status_code == 200:
    log_test("Register Barcelona user", True, f"Email: {barcelona_email}")
    barcelona_token = login(barcelona_email, "test1234")
    
    if barcelona_token:
        log_test("Login Barcelona user", True)
        
        venues_resp = get_venues(barcelona_token)
        if venues_resp.status_code == 200:
            venues = venues_resp.json()
            log_test("GET /api/venues as Barcelona user", True, f"Returned {len(venues)} venues")
            
            if len(venues) > 0:
                log_test("Barcelona user sees >0 venues", True, f"Count: {len(venues)}")
                
                all_barcelona = all(v.get("city") == "Barcelona" for v in venues)
                log_test("All venues have city='Barcelona'", all_barcelona,
                        f"Cities found: {set(v.get('city') for v in venues)}")
                
                all_have_coords = all(
                    v.get("lat") is not None and v.get("lng") is not None 
                    for v in venues
                )
                log_test("All Barcelona venues have lat AND lng", all_have_coords)
            else:
                log_test("Barcelona user sees >0 venues", False, "No venues returned")
        else:
            log_test("GET /api/venues as Barcelona user", False, f"Status: {venues_resp.status_code}")
    else:
        log_test("Login Barcelona user", False)
else:
    log_test("Register Barcelona user", False, f"Status: {resp.status_code}")

# Test 4: VENUES ISOLATION - Marbella user
print("\n" + "=" * 80)
print("TEST 4: VENUES ISOLATION - Marbella User")
print("=" * 80)

marbella_email = f"marbella_user_{timestamp}@test.com"
marbella_username = f"marbellauser{timestamp}"

resp = register_user(marbella_email, "test1234", "Marbella User", marbella_username, "Marbella")
if resp.status_code == 200:
    log_test("Register Marbella user", True, f"Email: {marbella_email}")
    marbella_token = login(marbella_email, "test1234")
    
    if marbella_token:
        log_test("Login Marbella user", True)
        
        venues_resp = get_venues(marbella_token)
        if venues_resp.status_code == 200:
            venues = venues_resp.json()
            log_test("GET /api/venues as Marbella user", True, f"Returned {len(venues)} venues")
            
            if len(venues) > 0:
                log_test("Marbella user sees >0 venues", True, f"Count: {len(venues)}")
                
                all_marbella = all(v.get("city") == "Marbella" for v in venues)
                log_test("All venues have city='Marbella'", all_marbella,
                        f"Cities found: {set(v.get('city') for v in venues)}")
                
                all_have_coords = all(
                    v.get("lat") is not None and v.get("lng") is not None 
                    for v in venues
                )
                log_test("All Marbella venues have lat AND lng", all_have_coords)
            else:
                log_test("Marbella user sees >0 venues", False, "No venues returned")
        else:
            log_test("GET /api/venues as Marbella user", False, f"Status: {venues_resp.status_code}")
    else:
        log_test("Login Marbella user", False)
else:
    log_test("Register Marbella user", False, f"Status: {resp.status_code}")

# Test 5: VENUES ISOLATION - Admin (Palma de Mallorca) - REGION GROUPING
print("\n" + "=" * 80)
print("TEST 5: VENUES ISOLATION - Admin (Palma de Mallorca) - REGION GROUPING")
print("=" * 80)

admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
if admin_token:
    log_test("Login admin", True)
    
    venues_resp = get_venues(admin_token)
    if venues_resp.status_code == 200:
        venues = venues_resp.json()
        log_test("GET /api/venues as admin", True, f"Returned {len(venues)} venues")
        
        if len(venues) > 0:
            log_test("Admin sees >0 venues", True, f"Count: {len(venues)}")
            
            # Check all venues are in Mallorca region
            venue_cities = [v.get("city") for v in venues]
            all_in_mallorca_region = all(city in MALLORCA_REGION for city in venue_cities)
            
            city_counts = {}
            for city in venue_cities:
                city_counts[city] = city_counts.get(city, 0) + 1
            
            log_test("All admin venues are in Mallorca region", all_in_mallorca_region,
                    f"City distribution: {json.dumps(city_counts, indent=2)}")
            
            # Check NO venues from other cities
            forbidden_cities = ["Ibiza", "Madrid", "Barcelona", "Marbella"]
            has_forbidden = any(city in forbidden_cities for city in venue_cities)
            log_test("Admin venues do NOT contain Ibiza/Madrid/Barcelona/Marbella", not has_forbidden,
                    f"Forbidden cities found: {[c for c in venue_cities if c in forbidden_cities]}")
            
            # Check all have coords
            all_have_coords = all(
                v.get("lat") is not None and v.get("lng") is not None 
                for v in venues
            )
            log_test("All admin venues have lat AND lng", all_have_coords)
        else:
            log_test("Admin sees >0 venues", False, "No venues returned")
    else:
        log_test("GET /api/venues as admin", False, f"Status: {venues_resp.status_code}")
else:
    log_test("Login admin", False)

# Test 6: ZONES ISOLATION - Ibiza vs Admin
print("\n" + "=" * 80)
print("TEST 6: ZONES ISOLATION - Ibiza vs Admin")
print("=" * 80)

if ibiza_token and admin_token:
    # Get zones for Ibiza user
    ibiza_zones_resp = get_zones(ibiza_token)
    if ibiza_zones_resp.status_code == 200:
        ibiza_zones = ibiza_zones_resp.json().get("zones", [])
        log_test("GET /api/venues/meta/zones as Ibiza user", True, 
                f"Zones: {ibiza_zones}")
        
        # Get zones for admin
        admin_zones_resp = get_zones(admin_token)
        if admin_zones_resp.status_code == 200:
            admin_zones = admin_zones_resp.json().get("zones", [])
            log_test("GET /api/venues/meta/zones as admin", True,
                    f"Zones: {admin_zones}")
            
            # Check zones are different
            zones_differ = set(ibiza_zones) != set(admin_zones)
            log_test("Ibiza zones differ from admin zones", zones_differ,
                    f"Ibiza: {ibiza_zones}, Admin: {admin_zones}")
            
            # Check no Mallorca zones in Ibiza
            mallorca_zone_keywords = ["Palma", "Magaluf", "Alcúdia", "Can Picafort", "Cala Rajada", "Santa Ponsa"]
            ibiza_has_mallorca_zones = any(
                any(keyword in zone for keyword in mallorca_zone_keywords)
                for zone in ibiza_zones
            )
            log_test("Ibiza user does NOT see Mallorca zones", not ibiza_has_mallorca_zones,
                    f"Ibiza zones: {ibiza_zones}")
            
            # Check no Ibiza zones in admin
            admin_has_ibiza_zones = any("Ibiza" in zone or "Eivissa" in zone for zone in admin_zones)
            log_test("Admin does NOT see Ibiza zones", not admin_has_ibiza_zones,
                    f"Admin zones: {admin_zones}")
        else:
            log_test("GET /api/venues/meta/zones as admin", False, f"Status: {admin_zones_resp.status_code}")
    else:
        log_test("GET /api/venues/meta/zones as Ibiza user", False, f"Status: {ibiza_zones_resp.status_code}")

# Test 7: FEED REGION - Admin (Palma) sees Mallorca region events
print("\n" + "=" * 80)
print("TEST 7: FEED REGION - Admin (Palma) sees Mallorca region events")
print("=" * 80)

if admin_token:
    events_resp = get_events(admin_token)
    if events_resp.status_code == 200:
        events = events_resp.json()
        log_test("GET /api/events as admin", True, f"Returned {len(events)} events")
        
        if len(events) > 0:
            # Get distinct cities
            event_cities = [e.get("city") for e in events if e.get("city")]
            distinct_cities = set(event_cities)
            
            city_counts = {}
            for city in event_cities:
                city_counts[city] = city_counts.get(city, 0) + 1
            
            log_test("Admin events city distribution", True,
                    f"Distinct cities: {distinct_cities}\nCounts: {json.dumps(city_counts, indent=2)}")
            
            # Check includes Palma de Mallorca
            has_palma = "Palma de Mallorca" in distinct_cities
            log_test("Admin events include city='Palma de Mallorca'", has_palma,
                    f"Palma count: {city_counts.get('Palma de Mallorca', 0)}")
            
            # Check includes Magaluf (region grouping)
            has_magaluf = "Magaluf" in distinct_cities
            log_test("Admin events include city='Magaluf' (region grouping)", has_magaluf,
                    f"Magaluf count: {city_counts.get('Magaluf', 0)}")
            
            # Check NO events from other cities
            forbidden_cities = ["Ibiza", "Madrid", "Barcelona", "Marbella"]
            has_forbidden = any(city in forbidden_cities for city in distinct_cities)
            log_test("Admin events do NOT contain Ibiza/Madrid/Barcelona/Marbella", not has_forbidden,
                    f"Forbidden cities found: {[c for c in distinct_cities if c in forbidden_cities]}")
        else:
            log_test("Admin sees >0 events", False, "No events returned")
    else:
        log_test("GET /api/events as admin", False, f"Status: {events_resp.status_code}")

# Test 8: FEED REGION - Ibiza user sees only Ibiza events
print("\n" + "=" * 80)
print("TEST 8: FEED REGION - Ibiza user sees only Ibiza events")
print("=" * 80)

if ibiza_token:
    events_resp = get_events(ibiza_token)
    if events_resp.status_code == 200:
        events = events_resp.json()
        log_test("GET /api/events as Ibiza user", True, f"Returned {len(events)} events")
        
        if len(events) > 0:
            # Get distinct cities
            event_cities = [e.get("city") for e in events if e.get("city")]
            distinct_cities = set(event_cities)
            
            log_test("Ibiza user events city distribution", True,
                    f"Distinct cities: {distinct_cities}")
            
            # Check all events are Ibiza
            all_ibiza = all(city == "Ibiza" for city in event_cities)
            log_test("All Ibiza user events have city='Ibiza'", all_ibiza,
                    f"Cities found: {distinct_cities}")
        else:
            log_test("Ibiza user sees >0 events", False, "No events returned")
    else:
        log_test("GET /api/events as Ibiza user", False, f"Status: {events_resp.status_code}")

# Test 9: REGRESSION - GET /api/events returns 401 without token
print("\n" + "=" * 80)
print("TEST 9: REGRESSION - GET /api/events returns 401 without token")
print("=" * 80)

url = f"{BASE_URL}/events"
resp = requests.get(url)
log_test("GET /api/events without token returns 401", resp.status_code == 401,
        f"Status: {resp.status_code}")

# Test 10: REGRESSION - GET /api/cities returns exactly 5 cities (public)
print("\n" + "=" * 80)
print("TEST 10: REGRESSION - GET /api/cities returns exactly 5 cities")
print("=" * 80)

cities_resp = get_cities()
if cities_resp.status_code == 200:
    cities_data = cities_resp.json()
    cities = cities_data.get("cities", [])
    log_test("GET /api/cities returns 200", True, f"Returned {len(cities)} cities")
    
    log_test("GET /api/cities returns exactly 5 cities", len(cities) == 5,
            f"Cities: {[c.get('label') for c in cities]}")
    
    expected_cities = ["Palma de Mallorca", "Ibiza", "Madrid", "Barcelona"]
    city_labels = [c.get("label") for c in cities]
    has_all_expected = all(city in city_labels for city in expected_cities)
    # Check Marbella (may be labeled "Marbella" or "Marbella / Puerto Banús")
    has_marbella = any("Marbella" in label for label in city_labels)
    log_test("Cities include all expected cities", has_all_expected and has_marbella,
            f"Expected: {expected_cities} + Marbella, Got: {city_labels}")
else:
    log_test("GET /api/cities returns 200", False, f"Status: {cities_resp.status_code}")

# Test 11: REGRESSION - GET /api/share/event/{id} returns 200 with OG tags
print("\n" + "=" * 80)
print("TEST 11: REGRESSION - GET /api/share/event/{id} returns 200 with OG tags")
print("=" * 80)

# Get an event ID from Ibiza user's events
if ibiza_token:
    events_resp = get_events(ibiza_token)
    if events_resp.status_code == 200:
        events = events_resp.json()
        if len(events) > 0:
            event_id = events[0].get("id")
            log_test("Got event ID for share test", True, f"Event ID: {event_id}")
            
            share_resp = get_share_event(event_id)
            if share_resp.status_code == 200:
                log_test("GET /api/share/event/{id} returns 200", True)
                
                html = share_resp.text
                has_og_title = "og:title" in html
                has_og_description = "og:description" in html
                has_og_image = "og:image" in html
                
                log_test("Share page contains og:title", has_og_title)
                log_test("Share page contains og:description", has_og_description)
                log_test("Share page contains og:image", has_og_image)
                
                is_html = share_resp.headers.get("content-type", "").startswith("text/html")
                log_test("Share page is text/html", is_html,
                        f"Content-Type: {share_resp.headers.get('content-type')}")
            else:
                log_test("GET /api/share/event/{id} returns 200", False, 
                        f"Status: {share_resp.status_code}")
        else:
            log_test("Got event ID for share test", False, "No events available")
    else:
        log_test("Got event ID for share test", False, f"Status: {events_resp.status_code}")

# Summary
print("\n" + "=" * 80)
print("TEST SUMMARY")
print("=" * 80)

passed = sum(1 for r in results if r["passed"])
failed = sum(1 for r in results if not r["passed"])
total = len(results)

print(f"\nTotal tests: {total}")
print(f"Passed: {passed} ✅")
print(f"Failed: {failed} ❌")
print(f"Success rate: {(passed/total*100):.1f}%")

if failed > 0:
    print("\n" + "=" * 80)
    print("FAILED TESTS:")
    print("=" * 80)
    for r in results:
        if not r["passed"]:
            print(f"\n❌ {r['name']}")
            if r["details"]:
                print(f"   {r['details']}")

print("\n" + "=" * 80)
print("TESTING COMPLETE")
print("=" * 80)
