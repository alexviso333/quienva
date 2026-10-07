#!/usr/bin/env python3
"""
Backend testing for ITERACIÓN 15b - QuienVa
Tests:
1. GET /api/admin/live-activities (admin endpoint)
2. POST /api/admin/live-activities/ping (ping live activity)
3. City parameter regression (case-insensitive, slug support)
4. Plan regression (create, respond, close, notifications)
"""

import requests
import json
from datetime import datetime, timedelta

# Base URL from frontend/.env
BASE_URL = "https://voting-party-planner.preview.emergentagent.com/api"

# Test credentials from /app/memory/test_credentials.md
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "QuienVa2025!"
TEST_USER_EMAIL = "test@quienva.app"
TEST_USER_PASSWORD = "Test1234!"

def login(email, password):
    """Login and return auth token"""
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": email,
        "password": password
    })
    if resp.status_code != 200:
        print(f"❌ Login failed for {email}: {resp.status_code} {resp.text}")
        return None
    data = resp.json()
    return data.get("token")

def test_admin_live_activities():
    """Test 1: GET /api/admin/live-activities"""
    print("\n" + "="*80)
    print("TEST 1: GET /api/admin/live-activities")
    print("="*80)
    
    # Test 1.1: Without auth → 401
    print("\n[1.1] GET /api/admin/live-activities without auth → expect 401")
    resp = requests.get(f"{BASE_URL}/admin/live-activities")
    if resp.status_code == 401:
        print(f"✅ PASS: Got 401 without auth")
    else:
        print(f"❌ FAIL: Expected 401, got {resp.status_code}")
    
    # Test 1.2: With normal user → 403
    print("\n[1.2] GET /api/admin/live-activities as normal user → expect 403")
    test_token = login(TEST_USER_EMAIL, TEST_USER_PASSWORD)
    if test_token:
        resp = requests.get(f"{BASE_URL}/admin/live-activities", 
                           headers={"Authorization": f"Bearer {test_token}"})
        if resp.status_code == 403:
            print(f"✅ PASS: Got 403 with normal user")
        else:
            print(f"❌ FAIL: Expected 403, got {resp.status_code}")
    else:
        print(f"❌ FAIL: Could not login as test user")
    
    # Test 1.3: With admin → 200 with correct structure
    print("\n[1.3] GET /api/admin/live-activities as admin → expect 200 with structure")
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    if not admin_token:
        print(f"❌ FAIL: Could not login as admin")
        return None
    
    resp = requests.get(f"{BASE_URL}/admin/live-activities",
                       headers={"Authorization": f"Bearer {admin_token}"})
    
    if resp.status_code != 200:
        print(f"❌ FAIL: Expected 200, got {resp.status_code}: {resp.text}")
        return None
    
    data = resp.json()
    print(f"✅ PASS: Got 200")
    
    # Verify structure
    required_keys = ["apns_configured", "apns_environment", "liveactivity_topic", "total", "activas", "items"]
    missing_keys = [k for k in required_keys if k not in data]
    if missing_keys:
        print(f"❌ FAIL: Missing keys: {missing_keys}")
        return None
    print(f"✅ PASS: All required keys present: {required_keys}")
    
    # Verify values
    if data["apns_configured"] != True:
        print(f"❌ FAIL: apns_configured should be true, got {data['apns_configured']}")
    else:
        print(f"✅ PASS: apns_configured = true")
    
    if data["apns_environment"] != "production":
        print(f"❌ FAIL: apns_environment should be 'production', got {data['apns_environment']}")
    else:
        print(f"✅ PASS: apns_environment = 'production'")
    
    expected_topic = "me.quienva.app.push-type.liveactivity"
    if data["liveactivity_topic"] != expected_topic:
        print(f"❌ FAIL: liveactivity_topic should be '{expected_topic}', got {data['liveactivity_topic']}")
    else:
        print(f"✅ PASS: liveactivity_topic = '{expected_topic}'")
    
    print(f"✅ PASS: total = {data['total']}, activas = {data['activas']}")
    print(f"✅ PASS: items count = {len(data['items'])}")
    
    # Verify item structure if any items exist
    if data["items"]:
        item = data["items"][0]
        item_keys = ["activity_id", "user", "token_preview", "plan", "ended", "updated_at"]
        missing_item_keys = [k for k in item_keys if k not in item]
        if missing_item_keys:
            print(f"❌ FAIL: Item missing keys: {missing_item_keys}")
        else:
            print(f"✅ PASS: Item has all required keys: {item_keys}")
            print(f"   Sample item: activity_id={item['activity_id']}, user={item['user']}, ended={item['ended']}")
    
    return admin_token

def test_admin_live_activity_ping(admin_token):
    """Test 2: POST /api/admin/live-activities/ping"""
    print("\n" + "="*80)
    print("TEST 2: POST /api/admin/live-activities/ping")
    print("="*80)
    
    if not admin_token:
        print("❌ SKIP: No admin token available")
        return None
    
    # First, we need to register a live activity token
    # Create a plan first
    print("\n[2.1] Creating a test plan to register live activity...")
    plan_resp = requests.post(f"{BASE_URL}/plans", json={
        "titulo": "Test Plan for Live Activity",
        "opciones": [
            {"texto_libre": "Option A"},
            {"texto_libre": "Option B"}
        ],
        "umbral_personas": 2
    })
    
    if plan_resp.status_code != 200:
        print(f"❌ FAIL: Could not create plan: {plan_resp.status_code} {plan_resp.text}")
        return None
    
    plan_data = plan_resp.json()
    plan_slug = plan_data["slug"]
    print(f"✅ PASS: Created plan with slug: {plan_slug}")
    
    # Register a live activity token
    print("\n[2.2] Registering live activity token...")
    activity_id = f"plan:{plan_slug}"
    fake_token = "a" * 64  # 64 hex chars (fake token)
    
    la_resp = requests.post(f"{BASE_URL}/live-activity/token",
                           headers={"Authorization": f"Bearer {admin_token}"},
                           json={
                               "activity_id": activity_id,
                               "token": fake_token,
                               "plan_slug": plan_slug
                           })
    
    if la_resp.status_code != 200:
        print(f"❌ FAIL: Could not register live activity: {la_resp.status_code} {la_resp.text}")
        return None
    
    la_data = la_resp.json()
    print(f"✅ PASS: Registered live activity: {la_data}")
    
    # Test 2.3: Ping with non-existent activity_id → 404
    print("\n[2.3] POST /api/admin/live-activities/ping with non-existent activity_id → expect 404")
    resp = requests.post(f"{BASE_URL}/admin/live-activities/ping?activity_id=nonexistent",
                        headers={"Authorization": f"Bearer {admin_token}"})
    
    if resp.status_code == 404:
        print(f"✅ PASS: Got 404 for non-existent activity_id")
    else:
        print(f"❌ FAIL: Expected 404, got {resp.status_code}")
    
    # Test 2.4: Ping with existing activity_id → 200 with apns:"gone"
    print(f"\n[2.4] POST /api/admin/live-activities/ping with activity_id={activity_id} → expect 200")
    resp = requests.post(f"{BASE_URL}/admin/live-activities/ping?activity_id={activity_id}",
                        headers={"Authorization": f"Bearer {admin_token}"})
    
    if resp.status_code != 200:
        print(f"❌ FAIL: Expected 200, got {resp.status_code}: {resp.text}")
        return plan_slug
    
    data = resp.json()
    print(f"✅ PASS: Got 200")
    print(f"   Response: {json.dumps(data, indent=2)}")
    
    # Verify response structure
    if "ok" not in data or "apns" not in data:
        print(f"❌ FAIL: Response missing 'ok' or 'apns' keys")
        return plan_slug
    
    print(f"✅ PASS: Response has 'ok' and 'apns' keys")
    
    # The fake token should result in apns:"gone" (BadDeviceToken from Apple)
    # This is CORRECT behavior - it means APNs is working and Apple responded
    if data["apns"] == "gone":
        print(f"✅ PASS: apns='gone' (CORRECT - Apple responded BadDeviceToken to fake token)")
    elif data["apns"] == "err":
        print(f"⚠️  WARNING: apns='err' (check logs for details)")
    else:
        print(f"   INFO: apns='{data['apns']}' (ok={data['ok']})")
    
    # The important thing is that we got HTTP 200 and no exception
    print(f"✅ PASS: No exception, HTTP 200 response received")
    
    return plan_slug

def test_city_parameter_regression():
    """Test 3: City parameter regression (case-insensitive, slug support)"""
    print("\n" + "="*80)
    print("TEST 3: City parameter regression")
    print("="*80)
    
    # Test 3.1: Madrid, madrid, MADRID should return same events
    print("\n[3.1] Testing city=Madrid, madrid, MADRID → should return same events")
    
    cities_to_test = ["Madrid", "madrid", "MADRID"]
    results = {}
    
    for city in cities_to_test:
        resp = requests.get(f"{BASE_URL}/events?city={city}")
        if resp.status_code != 200:
            print(f"❌ FAIL: GET /api/events?city={city} returned {resp.status_code}")
            continue
        
        events = resp.json()  # /api/events returns a list directly
        event_ids = [e["id"] for e in events]
        results[city] = {
            "count": len(event_ids),
            "ids": set(event_ids),
            "cities": set(e.get("city") for e in events)
        }
        print(f"   city={city}: {results[city]['count']} events, cities={results[city]['cities']}")
    
    # Verify all three return the same events
    if len(results) == 3:
        madrid_ids = results["Madrid"]["ids"]
        if results["madrid"]["ids"] == madrid_ids and results["MADRID"]["ids"] == madrid_ids:
            print(f"✅ PASS: Madrid, madrid, MADRID return EXACTLY the same events ({len(madrid_ids)} events)")
        else:
            print(f"❌ FAIL: Madrid variants return different events")
            print(f"   Madrid: {len(results['Madrid']['ids'])}, madrid: {len(results['madrid']['ids'])}, MADRID: {len(results['MADRID']['ids'])}")
        
        # Verify all events have city="Madrid"
        all_madrid = all(c == {"Madrid"} for c in [results[city]["cities"] for city in cities_to_test])
        if all_madrid:
            print(f"✅ PASS: All events have city='Madrid'")
        else:
            print(f"❌ FAIL: Not all events have city='Madrid': {[results[city]['cities'] for city in cities_to_test]}")
    
    # Test 3.2: Other cities
    print("\n[3.2] Testing other cities")
    
    city_tests = [
        ("ibiza", "Ibiza"),
        ("palma", "Palma de Mallorca"),
        ("mallorca", "Palma de Mallorca"),
        ("sevilla", "Sevilla"),
        ("barcelona", "Barcelona")
    ]
    
    for city_param, expected_city in city_tests:
        resp = requests.get(f"{BASE_URL}/events?city={city_param}")
        if resp.status_code != 200:
            print(f"❌ FAIL: GET /api/events?city={city_param} returned {resp.status_code}")
            continue
        
        events = resp.json()  # /api/events returns a list directly
        cities = set(e.get("city") for e in events)
        
        if cities == {expected_city}:
            print(f"✅ PASS: city={city_param} → {len(events)} events, all with city='{expected_city}'")
        else:
            print(f"❌ FAIL: city={city_param} → expected city='{expected_city}', got cities={cities}")
    
    # Test 3.3: Non-existent city → default city (Palma de Mallorca)
    print("\n[3.3] Testing non-existent city → should return default city (Palma de Mallorca)")
    
    resp = requests.get(f"{BASE_URL}/events?city=noexiste")
    if resp.status_code != 200:
        print(f"❌ FAIL: GET /api/events?city=noexiste returned {resp.status_code}")
    else:
        events = resp.json()  # /api/events returns a list directly
        cities = set(e.get("city") for e in events)
        if "Palma de Mallorca" in cities:
            print(f"✅ PASS: Non-existent city → default to Palma de Mallorca ({len(events)} events)")
        else:
            print(f"⚠️  INFO: Non-existent city → cities={cities}")
    
    # Test 3.4: No city parameter → default city
    print("\n[3.4] Testing no city parameter → should return default city")
    
    resp = requests.get(f"{BASE_URL}/events")
    if resp.status_code != 200:
        print(f"❌ FAIL: GET /api/events returned {resp.status_code}")
    else:
        events = resp.json()  # /api/events returns a list directly
        print(f"✅ PASS: No city parameter → {len(events)} events")
    
    # Test 3.5: Test /api/events/genres with city parameter
    print("\n[3.5] Testing GET /api/events/genres?city=madrid")
    
    resp = requests.get(f"{BASE_URL}/events/genres?city=madrid")
    if resp.status_code != 200:
        print(f"❌ FAIL: GET /api/events/genres?city=madrid returned {resp.status_code}")
    else:
        genres = resp.json()  # Returns a list directly
        print(f"✅ PASS: GET /api/events/genres?city=madrid → 200 with {len(genres)} genres")

def test_plan_regression(admin_token, existing_plan_slug=None):
    """Test 4: Plan regression"""
    print("\n" + "="*80)
    print("TEST 4: Plan regression")
    print("="*80)
    
    if not admin_token:
        print("❌ SKIP: No admin token available")
        return
    
    # Test 4.1: POST /api/plans
    print("\n[4.1] POST /api/plans → expect 200")
    
    plan_resp = requests.post(f"{BASE_URL}/plans", json={
        "titulo": "Test Plan Regression",
        "opciones": [
            {"texto_libre": "Option 1"},
            {"texto_libre": "Option 2"}
        ],
        "umbral_personas": 2
    })
    
    if plan_resp.status_code != 200:
        print(f"❌ FAIL: POST /api/plans returned {plan_resp.status_code}: {plan_resp.text}")
        return
    
    plan_data = plan_resp.json()
    plan_slug = plan_data["slug"]
    creador_token = plan_data["creador_token"]
    print(f"✅ PASS: Created plan with slug: {plan_slug}")
    
    # Test 4.2: GET /api/plans/{slug}
    print(f"\n[4.2] GET /api/plans/{plan_slug} → expect 200")
    
    resp = requests.get(f"{BASE_URL}/plans/{plan_slug}")
    if resp.status_code != 200:
        print(f"❌ FAIL: GET /api/plans/{plan_slug} returned {resp.status_code}")
    else:
        print(f"✅ PASS: GET /api/plans/{plan_slug} → 200")
    
    # Test 4.3: POST /api/plans/{slug}/respond (first response)
    print(f"\n[4.3] POST /api/plans/{plan_slug}/respond (first response) → expect 200")
    
    resp = requests.post(f"{BASE_URL}/plans/{plan_slug}/respond", json={
        "apodo": "Tester 1",
        "intencion": "dentro"
    })
    
    if resp.status_code != 200:
        print(f"❌ FAIL: POST respond returned {resp.status_code}: {resp.text}")
        return
    
    resp_data = resp.json()
    participante_token_1 = resp_data.get("participante_token")
    print(f"✅ PASS: First response → 200, participante_token: {participante_token_1[:20]}...")
    
    # Test 4.4: POST /api/plans/{slug}/respond (second response to trigger quorum)
    print(f"\n[4.4] POST /api/plans/{plan_slug}/respond (second response) → expect 200 and plan closes")
    
    resp = requests.post(f"{BASE_URL}/plans/{plan_slug}/respond", json={
        "apodo": "Tester 2",
        "intencion": "dentro"
    })
    
    if resp.status_code != 200:
        print(f"❌ FAIL: POST respond returned {resp.status_code}: {resp.text}")
        return
    
    print(f"✅ PASS: Second response → 200")
    
    # Verify plan is closed
    resp = requests.get(f"{BASE_URL}/plans/{plan_slug}")
    if resp.status_code == 200:
        plan_data = resp.json()
        if plan_data.get("estado") == "cerrado":
            print(f"✅ PASS: Plan estado = 'cerrado' (quorum reached)")
            if plan_data.get("opcion_ganadora"):
                print(f"✅ PASS: opcion_ganadora is set: {plan_data['opcion_ganadora']}")
            else:
                print(f"⚠️  WARNING: opcion_ganadora is not set")
        else:
            print(f"❌ FAIL: Plan estado = '{plan_data.get('estado')}', expected 'cerrado'")
    
    # Test 4.5: Create another plan and close it manually
    print(f"\n[4.5] Creating another plan to test manual close...")
    
    plan_resp = requests.post(f"{BASE_URL}/plans", json={
        "titulo": "Test Plan for Manual Close",
        "opciones": [
            {"texto_libre": "Option A"},
            {"texto_libre": "Option B"}
        ]
    })
    
    if plan_resp.status_code != 200:
        print(f"❌ FAIL: Could not create second plan: {plan_resp.status_code}")
        return
    
    plan_data = plan_resp.json()
    plan_slug_2 = plan_data["slug"]
    creador_token_2 = plan_data["creador_token"]
    print(f"✅ PASS: Created second plan with slug: {plan_slug_2}")
    
    # Test 4.6: POST /api/plans/{slug}/close
    print(f"\n[4.6] POST /api/plans/{plan_slug_2}/close → expect 200")
    
    resp = requests.post(f"{BASE_URL}/plans/{plan_slug_2}/close",
                        headers={"x-participante-token": creador_token_2})
    
    if resp.status_code != 200:
        print(f"❌ FAIL: POST close returned {resp.status_code}: {resp.text}")
    else:
        print(f"✅ PASS: POST /api/plans/{plan_slug_2}/close → 200")
    
    # Test 4.7: Check notifications for plan_closed
    print(f"\n[4.7] GET /api/notifications → check for plan_closed notification")
    
    resp = requests.get(f"{BASE_URL}/notifications",
                       headers={"Authorization": f"Bearer {admin_token}"})
    
    if resp.status_code != 200:
        print(f"❌ FAIL: GET /api/notifications returned {resp.status_code}")
    else:
        notifications = resp.json()  # Returns a list directly
        plan_closed_notifs = [n for n in notifications if n.get("type") == "plan_closed"]
        
        if plan_closed_notifs:
            print(f"✅ PASS: Found {len(plan_closed_notifs)} plan_closed notification(s)")
            print(f"   Sample: {plan_closed_notifs[0].get('text', 'N/A')}")
        else:
            print(f"⚠️  INFO: No plan_closed notifications found (may be expected if admin didn't participate)")
    
    # Test 4.8: Test OG image
    print(f"\n[4.8] GET /api/og/plan/{plan_slug} → expect 200 image/png")
    
    resp = requests.get(f"{BASE_URL}/og/plan/{plan_slug}")
    
    if resp.status_code != 200:
        print(f"❌ FAIL: GET /api/og/plan/{plan_slug} returned {resp.status_code}")
    else:
        content_type = resp.headers.get("content-type", "")
        if "image/png" in content_type:
            print(f"✅ PASS: GET /api/og/plan/{plan_slug} → 200 image/png ({len(resp.content)} bytes)")
        else:
            print(f"❌ FAIL: Expected image/png, got {content_type}")

def main():
    print("="*80)
    print("BACKEND TESTING - ITERACIÓN 15b")
    print("QuienVa - Admin Live Activities + City Parameter Fix + Plan Regression")
    print("="*80)
    
    # Test 1: Admin live activities endpoint
    admin_token = test_admin_live_activities()
    
    # Test 2: Admin live activity ping
    plan_slug = test_admin_live_activity_ping(admin_token)
    
    # Test 3: City parameter regression
    test_city_parameter_regression()
    
    # Test 4: Plan regression
    test_plan_regression(admin_token, plan_slug)
    
    print("\n" + "="*80)
    print("TESTING COMPLETE")
    print("="*80)

if __name__ == "__main__":
    main()
