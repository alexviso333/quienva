#!/usr/bin/env python3
"""
Backend test for ¿Quién va? FastAPI app
Testing focus areas from review request:
1. SEO city landing pages show ALL events (>24) - HIGH PRIORITY
2. Auth regression (google/apple callbacks, email/password flow) - HIGH PRIORITY
3. General regression (GET /api/cities, GET /api/events)
"""

import requests
import json
import uuid
from datetime import datetime, timedelta
from pymongo import MongoClient
import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment
load_dotenv(Path('/app/backend/.env'))

# Configuration
BASE_URL = "https://voting-island-widget.preview.emergentagent.com/api"
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'quienva')

# MongoDB connection
mongo_client = MongoClient(MONGO_URL)
db = mongo_client[DB_NAME]

# Test results
test_results = {
    "passed": 0,
    "failed": 0,
    "errors": []
}

def log_test(name, passed, details=""):
    """Log test result"""
    if passed:
        test_results["passed"] += 1
        print(f"✅ {name}")
    else:
        test_results["failed"] += 1
        test_results["errors"].append(f"{name}: {details}")
        print(f"❌ {name}: {details}")
    if details and passed:
        print(f"   {details}")

def seed_events_for_city(city_id, count=30):
    """Seed test events for a city"""
    print(f"\n📦 Seeding {count} events for {city_id}...")
    
    # Get today's date in Europe/Madrid timezone
    today = datetime.now()
    
    events = []
    for i in range(count):
        event_date = (today + timedelta(days=i)).strftime("%Y-%m-%d")
        event = {
            "id": str(uuid.uuid4()),
            "name": f"Test Event {i+1} - {city_id}",
            "venue": f"Test Venue {(i % 5) + 1}",
            "city": city_id,
            "date": event_date,
            "time": "23:00",
            "image_url": f"https://example.com/image{i}.jpg",
            "price_tiers": [{"label": "General", "price": 20 + i}],
            "commission_url": f"https://example.com/event{i}",
            "sale_state": "on_sale",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        events.append(event)
    
    # Insert events
    if events:
        db.events.insert_many(events)
        print(f"✅ Seeded {len(events)} events for {city_id}")
    
    return len(events)

def cleanup_test_events():
    """Clean up test events"""
    result = db.events.delete_many({"name": {"$regex": "^Test Event"}})
    print(f"🧹 Cleaned up {result.deleted_count} test events")

def test_seo_city_pages():
    """Test 1: SEO city landing pages show ALL events (>24)"""
    print("\n" + "="*80)
    print("TEST 1: SEO CITY LANDING PAGES SHOW ALL EVENTS (HIGH PRIORITY)")
    print("="*80)
    
    # Seed MORE than 24 events for Madrid
    city_id = "Madrid"
    event_count = seed_events_for_city(city_id, 30)
    
    # Test 1a: GET /api/ciudad/madrid (HTML)
    print(f"\n1a. Testing GET /api/ciudad/madrid...")
    try:
        resp = requests.get(f"{BASE_URL}/ciudad/madrid", timeout=30)
        log_test(
            "GET /api/ciudad/madrid returns 200",
            resp.status_code == 200,
            f"Status: {resp.status_code}"
        )
        
        if resp.status_code == 200:
            html = resp.text
            
            # Count seo-event-card items
            card_count = html.count('data-testid="seo-event-card"')
            log_test(
                f"Renders MORE than 24 event cards (found {card_count})",
                card_count > 24,
                f"Expected >24, got {card_count}"
            )
            
            # Check stats header count
            # Look for pattern like "30 planes" or similar
            import re
            stats_match = re.search(r'(\d+)\s+planes?', html, re.IGNORECASE)
            if stats_match:
                stats_count = int(stats_match.group(1))
                log_test(
                    f"Stats header count matches seeded events",
                    stats_count >= 30,
                    f"Stats shows {stats_count} events"
                )
            
            # Check JSON-LD blocks are capped
            jsonld_count = html.count('application/ld+json')
            log_test(
                f"JSON-LD blocks are capped (~30 event blocks)",
                jsonld_count < 50,
                f"Found {jsonld_count} JSON-LD blocks (should be ~30-35)"
            )
            
    except Exception as e:
        log_test("GET /api/ciudad/madrid", False, str(e))
    
    # Test 1b: Timeframe pages still work
    print(f"\n1b. Testing timeframe pages...")
    try:
        resp = requests.get(f"{BASE_URL}/ciudad/madrid/esta-noche", timeout=30)
        log_test(
            "GET /api/ciudad/madrid/esta-noche returns 200",
            resp.status_code == 200,
            f"Status: {resp.status_code}"
        )
    except Exception as e:
        log_test("GET /api/ciudad/madrid/esta-noche", False, str(e))
    
    try:
        resp = requests.get(f"{BASE_URL}/ciudad/madrid/este-finde", timeout=30)
        log_test(
            "GET /api/ciudad/madrid/este-finde returns 200",
            resp.status_code == 200,
            f"Status: {resp.status_code}"
        )
    except Exception as e:
        log_test("GET /api/ciudad/madrid/este-finde", False, str(e))
    
    # Test 1c: Home page is UNCHANGED
    print(f"\n1c. Testing home page unchanged...")
    try:
        resp = requests.get(f"{BASE_URL}/home", timeout=30)
        log_test(
            "GET /api/home returns 200 HTML",
            resp.status_code == 200 and 'text/html' in resp.headers.get('content-type', ''),
            f"Status: {resp.status_code}, Content-Type: {resp.headers.get('content-type')}"
        )
    except Exception as e:
        log_test("GET /api/home", False, str(e))

def test_auth_regression():
    """Test 2: Auth regression (google/apple callbacks, email/password flow)"""
    print("\n" + "="*80)
    print("TEST 2: AUTH REGRESSION (HIGH PRIORITY)")
    print("="*80)
    
    # Test 2a: Google callback with invalid body (must NOT return 500)
    print(f"\n2a. Testing Google callback with invalid body...")
    try:
        payload = {
            "code": "bad_code_12345",
            "redirect_uri": "http://example.com",
            "guest_city": None
        }
        resp = requests.post(f"{BASE_URL}/auth/google/callback", json=payload, timeout=10)
        log_test(
            "POST /api/auth/google/callback with invalid code returns 400/401 (NOT 500)",
            resp.status_code in [400, 401],
            f"Status: {resp.status_code} (expected 400/401, not 500)"
        )
    except Exception as e:
        log_test("POST /api/auth/google/callback graceful error", False, str(e))
    
    # Test 2b: Apple callback with invalid identity_token (must NOT return 500)
    print(f"\n2b. Testing Apple callback with invalid token...")
    try:
        payload = {
            "identity_token": "invalid_token_xyz",
            "guest_city": None
        }
        resp = requests.post(f"{BASE_URL}/auth/apple/callback", json=payload, timeout=10)
        log_test(
            "POST /api/auth/apple/callback with invalid token returns 400/401 (NOT 500)",
            resp.status_code in [400, 401],
            f"Status: {resp.status_code} (expected 400/401, not 500)"
        )
    except Exception as e:
        log_test("POST /api/auth/apple/callback graceful error", False, str(e))
    
    # Test 2c: Email/password flow (register -> login -> /me)
    print(f"\n2c. Testing email/password flow...")
    test_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    test_password = "TestPass123!"
    test_username = f"testuser_{uuid.uuid4().hex[:6]}"
    
    # Register
    try:
        register_payload = {
            "email": test_email,
            "password": test_password,
            "name": "Test User",
            "username": test_username,
            "birthdate": "1995-01-01",
            "city": "Madrid"
        }
        resp = requests.post(f"{BASE_URL}/auth/register", json=register_payload, timeout=10)
        log_test(
            "POST /api/auth/register creates user",
            resp.status_code == 200,
            f"Status: {resp.status_code}"
        )
        
        if resp.status_code == 200:
            register_data = resp.json()
            token = register_data.get("token")
            
            # Login
            login_payload = {
                "email": test_email,
                "password": test_password
            }
            resp = requests.post(f"{BASE_URL}/auth/login", json=login_payload, timeout=10)
            log_test(
                "POST /api/auth/login returns token",
                resp.status_code == 200 and "token" in resp.json(),
                f"Status: {resp.status_code}"
            )
            
            if resp.status_code == 200:
                login_token = resp.json().get("token")
                
                # GET /me
                headers = {"Authorization": f"Bearer {login_token}"}
                resp = requests.get(f"{BASE_URL}/auth/me", headers=headers, timeout=10)
                log_test(
                    "GET /api/auth/me returns user data",
                    resp.status_code == 200 and resp.json().get("email") == test_email,
                    f"Status: {resp.status_code}, Email: {resp.json().get('email') if resp.status_code == 200 else 'N/A'}"
                )
                
                # Save credentials to test_credentials.md
                if resp.status_code == 200:
                    save_test_credentials(test_email, test_password, login_token)
    
    except Exception as e:
        log_test("Email/password flow", False, str(e))

def test_general_regression():
    """Test 3: General regression (GET /api/cities, GET /api/events)"""
    print("\n" + "="*80)
    print("TEST 3: GENERAL REGRESSION")
    print("="*80)
    
    # Test 3a: GET /api/cities
    print(f"\n3a. Testing GET /api/cities...")
    try:
        resp = requests.get(f"{BASE_URL}/cities", timeout=10)
        log_test(
            "GET /api/cities returns 200 with valid JSON",
            resp.status_code == 200 and isinstance(resp.json(), dict),
            f"Status: {resp.status_code}"
        )
        
        if resp.status_code == 200:
            cities_data = resp.json()
            cities = cities_data.get("cities", [])
            log_test(
                "Cities list contains supported cities",
                len(cities) >= 5,
                f"Found {len(cities)} cities"
            )
    except Exception as e:
        log_test("GET /api/cities", False, str(e))
    
    # Test 3b: GET /api/events (with and without ?city=)
    print(f"\n3b. Testing GET /api/events...")
    try:
        resp = requests.get(f"{BASE_URL}/events", timeout=10)
        log_test(
            "GET /api/events returns 200 with valid JSON",
            resp.status_code == 200 and isinstance(resp.json(), list),
            f"Status: {resp.status_code}"
        )
    except Exception as e:
        log_test("GET /api/events", False, str(e))
    
    try:
        resp = requests.get(f"{BASE_URL}/events?city=Madrid", timeout=10)
        log_test(
            "GET /api/events?city=Madrid returns 200 with valid JSON",
            resp.status_code == 200 and isinstance(resp.json(), list),
            f"Status: {resp.status_code}"
        )
        
        if resp.status_code == 200:
            events = resp.json()
            log_test(
                "Events list contains Madrid events",
                len(events) > 0,
                f"Found {len(events)} events"
            )
    except Exception as e:
        log_test("GET /api/events?city=Madrid", False, str(e))

def save_test_credentials(email, password, token):
    """Save test credentials to /app/memory/test_credentials.md"""
    try:
        os.makedirs("/app/memory", exist_ok=True)
        with open("/app/memory/test_credentials.md", "w") as f:
            f.write("# Test Credentials for ¿Quién va?\n\n")
            f.write("## Test User (Email/Password)\n")
            f.write(f"- Email: {email}\n")
            f.write(f"- Password: {password}\n")
            f.write(f"- Token: {token}\n")
            f.write(f"- Created: {datetime.now().isoformat()}\n")
        print(f"\n💾 Saved test credentials to /app/memory/test_credentials.md")
    except Exception as e:
        print(f"⚠️  Failed to save test credentials: {e}")

def print_summary():
    """Print test summary"""
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"✅ Passed: {test_results['passed']}")
    print(f"❌ Failed: {test_results['failed']}")
    
    if test_results['errors']:
        print("\n❌ FAILED TESTS:")
        for error in test_results['errors']:
            print(f"  - {error}")
    
    print("\n" + "="*80)
    
    # Overall result
    if test_results['failed'] == 0:
        print("🎉 ALL TESTS PASSED!")
    else:
        print(f"⚠️  {test_results['failed']} TEST(S) FAILED")
    print("="*80)

def main():
    """Main test runner"""
    print("="*80)
    print("¿QUIÉN VA? BACKEND TESTING")
    print("="*80)
    print(f"Backend URL: {BASE_URL}")
    print(f"MongoDB: {MONGO_URL}/{DB_NAME}")
    print("="*80)
    
    try:
        # Run tests
        test_seo_city_pages()
        test_auth_regression()
        test_general_regression()
        
        # Print summary
        print_summary()
        
    finally:
        # Cleanup
        cleanup_test_events()
        mongo_client.close()

if __name__ == "__main__":
    main()
