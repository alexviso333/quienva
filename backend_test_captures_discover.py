#!/usr/bin/env python3
"""
Backend API tests for ¿Quién va? app
Testing iteration: Capture likes + Discover enhancements
"""

import requests
import time
import random
import string
import io
from datetime import datetime, timedelta
from PIL import Image

# Base URL from frontend/.env
BASE_URL = "https://event-scraper-hub-1.preview.emergentagent.com/api"

# Admin credentials
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

# Test results
tests_passed = 0
tests_failed = 0
failed_tests = []

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def random_string(length=8):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def register_user(name=None, email=None, password="testpass123", city="Palma de Mallorca", birthdate="1998-05-05", username=None):
    """Register a new user and return token"""
    if not name:
        name = f"Test User {random_string(4)}"
    if not email:
        email = f"test_{random_string(8)}@test.com"
    if not username:
        username = f"user_{random_string(6)}"
    
    resp = requests.post(f"{BASE_URL}/auth/register", json={
        "name": name,
        "email": email,
        "password": password,
        "city": city,
        "birthdate": birthdate,
        "username": username
    })
    if resp.status_code != 200:
        log(f"❌ Failed to register user: {resp.status_code} - {resp.text}")
        return None, None, None
    data = resp.json()
    return data["token"], data["user"]["user_id"], email

def login(email, password):
    """Login and return token"""
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": email,
        "password": password
    })
    if resp.status_code != 200:
        return None
    return resp.json()["token"]

def create_test_image():
    """Create a small test JPEG image in memory"""
    img = Image.new('RGB', (100, 100), color='red')
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='JPEG')
    img_bytes.seek(0)
    return img_bytes

def test_capture_like_endpoint():
    """Test POST /api/captures/{capture_id}/like endpoint"""
    global tests_passed, tests_failed, failed_tests
    
    log("\n" + "="*80)
    log("TEST 1: CAPTURE LIKE ENDPOINT")
    log("="*80)
    
    # Step 1: Login as admin
    log("\n1. Login as admin...")
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    if not admin_token:
        log("❌ Failed to login as admin")
        tests_failed += 1
        failed_tests.append("Capture Like - Admin login failed")
        return
    log("✅ Admin logged in")
    tests_passed += 1
    
    # Step 2: Create an event
    log("\n2. Create test event...")
    today = datetime.now().strftime("%Y-%m-%d")
    event_data = {
        "name": "Test Fiesta",
        "venue": "Test Club",
        "date": today,
        "time": "23:00",
        "city": "Palma de Mallorca",
        "genre": "techno"
    }
    resp = requests.post(
        f"{BASE_URL}/admin/events",
        json=event_data,
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    if resp.status_code != 200:
        log(f"❌ Failed to create event: {resp.status_code} - {resp.text}")
        tests_failed += 1
        failed_tests.append("Capture Like - Event creation failed")
        return
    event_id = resp.json()["id"]
    log(f"✅ Event created with id: {event_id}")
    tests_passed += 1
    
    # Step 3: Register normal user U
    log("\n3. Register normal user U...")
    token_u, user_id_u, email_u = register_user(name="User U", birthdate="1995-03-15")
    if not token_u:
        log("❌ Failed to register user U")
        tests_failed += 1
        failed_tests.append("Capture Like - User U registration failed")
        return
    log(f"✅ User U registered: {user_id_u}")
    tests_passed += 1
    
    # Step 4: User U marks 'voy' on event
    log("\n4. User U marks 'voy' on event...")
    resp = requests.post(
        f"{BASE_URL}/events/{event_id}/interest",
        json={"status": "voy"},
        headers={"Authorization": f"Bearer {token_u}"}
    )
    if resp.status_code != 200:
        log(f"❌ Failed to mark interest: {resp.status_code} - {resp.text}")
        tests_failed += 1
        failed_tests.append("Capture Like - Mark interest failed")
        return
    log("✅ User U marked 'voy'")
    tests_passed += 1
    
    # Step 5: Admin triggers moment
    log("\n5. Admin triggers moment...")
    resp = requests.post(
        f"{BASE_URL}/admin/events/{event_id}/moment/trigger",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    if resp.status_code != 200:
        log(f"❌ Failed to trigger moment: {resp.status_code} - {resp.text}")
        tests_failed += 1
        failed_tests.append("Capture Like - Trigger moment failed")
        return
    log("✅ Moment triggered")
    tests_passed += 1
    
    # Step 6: User U uploads moment capture
    log("\n6. User U uploads moment capture...")
    img_bytes = create_test_image()
    files = {'file': ('test.jpg', img_bytes, 'image/jpeg')}
    resp = requests.post(
        f"{BASE_URL}/events/{event_id}/moment/upload",
        files=files,
        headers={"Authorization": f"Bearer {token_u}"}
    )
    if resp.status_code != 200:
        log(f"❌ Failed to upload capture: {resp.status_code} - {resp.text}")
        tests_failed += 1
        failed_tests.append("Capture Like - Upload capture failed")
        return
    log("✅ Capture uploaded")
    tests_passed += 1
    
    # Step 7: Get capture ID from gallery
    log("\n7. Get capture ID from gallery...")
    resp = requests.get(
        f"{BASE_URL}/events/{event_id}/moment/gallery",
        headers={"Authorization": f"Bearer {token_u}"}
    )
    if resp.status_code != 200:
        log(f"❌ Failed to get gallery: {resp.status_code} - {resp.text}")
        tests_failed += 1
        failed_tests.append("Capture Like - Get gallery failed")
        return
    gallery = resp.json()
    if not gallery or len(gallery) == 0:
        log("❌ No captures in gallery")
        tests_failed += 1
        failed_tests.append("Capture Like - No captures in gallery")
        return
    capture_id = gallery[0]["id"]
    log(f"✅ Capture ID retrieved: {capture_id}")
    tests_passed += 1
    
    # Step 8: Register another user V
    log("\n8. Register user V...")
    token_v, user_id_v, email_v = register_user(name="User V", birthdate="1996-07-20")
    if not token_v:
        log("❌ Failed to register user V")
        tests_failed += 1
        failed_tests.append("Capture Like - User V registration failed")
        return
    log(f"✅ User V registered: {user_id_v}")
    tests_passed += 1
    
    # Step 9: User V likes the capture (first time)
    log("\n9. User V likes the capture (first time)...")
    resp = requests.post(
        f"{BASE_URL}/captures/{capture_id}/like",
        headers={"Authorization": f"Bearer {token_v}"}
    )
    if resp.status_code != 200:
        log(f"❌ Failed to like capture: {resp.status_code} - {resp.text}")
        tests_failed += 1
        failed_tests.append("Capture Like - First like failed")
        return
    data = resp.json()
    if data.get("liked") != True or data.get("likes") != 1:
        log(f"❌ Expected liked=True, likes=1, got: {data}")
        tests_failed += 1
        failed_tests.append("Capture Like - First like response incorrect")
        return
    log(f"✅ First like successful: {data}")
    tests_passed += 1
    
    # Step 10: User V likes the capture again (toggle/unlike)
    log("\n10. User V likes the capture again (toggle/unlike)...")
    resp = requests.post(
        f"{BASE_URL}/captures/{capture_id}/like",
        headers={"Authorization": f"Bearer {token_v}"}
    )
    if resp.status_code != 200:
        log(f"❌ Failed to unlike capture: {resp.status_code} - {resp.text}")
        tests_failed += 1
        failed_tests.append("Capture Like - Unlike failed")
        return
    data = resp.json()
    if data.get("liked") != False or data.get("likes") != 0:
        log(f"❌ Expected liked=False, likes=0, got: {data}")
        tests_failed += 1
        failed_tests.append("Capture Like - Unlike response incorrect")
        return
    log(f"✅ Unlike successful (toggle working): {data}")
    tests_passed += 1
    
    # Step 11: Test non-existent capture
    log("\n11. Test non-existent capture...")
    resp = requests.post(
        f"{BASE_URL}/captures/nonexistent-id/like",
        headers={"Authorization": f"Bearer {token_v}"}
    )
    if resp.status_code != 404:
        log(f"❌ Expected 404 for non-existent capture, got: {resp.status_code}")
        tests_failed += 1
        failed_tests.append("Capture Like - Non-existent capture should return 404")
        return
    log("✅ Non-existent capture returns 404")
    tests_passed += 1
    
    # Step 12: Test unauthenticated request
    log("\n12. Test unauthenticated request...")
    resp = requests.post(f"{BASE_URL}/captures/{capture_id}/like")
    if resp.status_code != 401:
        log(f"❌ Expected 401 for unauthenticated request, got: {resp.status_code}")
        tests_failed += 1
        failed_tests.append("Capture Like - Unauthenticated should return 401")
        return
    log("✅ Unauthenticated request returns 401")
    tests_passed += 1
    
    log("\n" + "="*80)
    log("✅ ALL CAPTURE LIKE TESTS PASSED")
    log("="*80)

def test_discover_enhancements():
    """Test GET /api/discover with new fields"""
    global tests_passed, tests_failed, failed_tests
    
    log("\n" + "="*80)
    log("TEST 2: DISCOVER ENHANCEMENTS")
    log("="*80)
    
    # Step 1: Register a test user
    log("\n1. Register test user...")
    token_u, user_id_u, email_u = register_user(name="Discover User", birthdate="1997-08-10")
    if not token_u:
        log("❌ Failed to register user")
        tests_failed += 1
        failed_tests.append("Discover - User registration failed")
        return
    log(f"✅ User registered: {user_id_u}")
    tests_passed += 1
    
    # Step 2: Call GET /api/discover
    log("\n2. Call GET /api/discover...")
    resp = requests.get(
        f"{BASE_URL}/discover",
        headers={"Authorization": f"Bearer {token_u}"}
    )
    if resp.status_code != 200:
        log(f"❌ Failed to get discover: {resp.status_code} - {resp.text}")
        tests_failed += 1
        failed_tests.append("Discover - GET /discover failed")
        return
    data = resp.json()
    log(f"✅ Discover endpoint returned 200")
    tests_passed += 1
    
    # Step 3: Verify structure
    log("\n3. Verify response structure...")
    if "people" not in data or "moments" not in data:
        log(f"❌ Missing required fields in response: {data.keys()}")
        tests_failed += 1
        failed_tests.append("Discover - Missing people or moments field")
        return
    if not isinstance(data["people"], list):
        log(f"❌ 'people' should be a list, got: {type(data['people'])}")
        tests_failed += 1
        failed_tests.append("Discover - people is not a list")
        return
    if not isinstance(data["moments"], list):
        log(f"❌ 'moments' should be a list, got: {type(data['moments'])}")
        tests_failed += 1
        failed_tests.append("Discover - moments is not a list")
        return
    log(f"✅ Response structure correct: people={len(data['people'])}, moments={len(data['moments'])}")
    tests_passed += 1
    
    # Step 4: Verify people have shared_events field
    log("\n4. Verify people have 'shared_events' field...")
    if len(data["people"]) > 0:
        person = data["people"][0]
        if "shared_events" not in person:
            log(f"❌ Person missing 'shared_events' field: {person.keys()}")
            tests_failed += 1
            failed_tests.append("Discover - Person missing shared_events field")
            return
        if not isinstance(person["shared_events"], int):
            log(f"❌ 'shared_events' should be int, got: {type(person['shared_events'])}")
            tests_failed += 1
            failed_tests.append("Discover - shared_events is not an integer")
            return
        log(f"✅ People have 'shared_events' field (integer): {person['shared_events']}")
        tests_passed += 1
    else:
        log("⚠️  No people in response, skipping shared_events check")
        tests_passed += 1
    
    # Step 5: Verify people never includes requesting user
    log("\n5. Verify people never includes requesting user...")
    people_ids = [p["user_id"] for p in data["people"]]
    if user_id_u in people_ids:
        log(f"❌ Requesting user {user_id_u} found in people list!")
        tests_failed += 1
        failed_tests.append("Discover - Requesting user should not be in people list")
        return
    log(f"✅ Requesting user NOT in people list (correct)")
    tests_passed += 1
    
    # Step 6: Verify moments have likes and i_liked fields
    log("\n6. Verify moments have 'likes' and 'i_liked' fields...")
    if len(data["moments"]) > 0:
        moment = data["moments"][0]
        if "likes" not in moment:
            log(f"❌ Moment missing 'likes' field: {moment.keys()}")
            tests_failed += 1
            failed_tests.append("Discover - Moment missing likes field")
            return
        if "i_liked" not in moment:
            log(f"❌ Moment missing 'i_liked' field: {moment.keys()}")
            tests_failed += 1
            failed_tests.append("Discover - Moment missing i_liked field")
            return
        if not isinstance(moment["likes"], int):
            log(f"❌ 'likes' should be int, got: {type(moment['likes'])}")
            tests_failed += 1
            failed_tests.append("Discover - likes is not an integer")
            return
        if not isinstance(moment["i_liked"], bool):
            log(f"❌ 'i_liked' should be bool, got: {type(moment['i_liked'])}")
            tests_failed += 1
            failed_tests.append("Discover - i_liked is not a boolean")
            return
        log(f"✅ Moments have 'likes' (int) and 'i_liked' (bool): likes={moment['likes']}, i_liked={moment['i_liked']}")
        tests_passed += 1
    else:
        log("⚠️  No moments in response, skipping likes/i_liked check")
        tests_passed += 1
    
    log("\n" + "="*80)
    log("✅ ALL DISCOVER ENHANCEMENT TESTS PASSED")
    log("="*80)

def test_regression():
    """Test regression - existing endpoints still work"""
    global tests_passed, tests_failed, failed_tests
    
    log("\n" + "="*80)
    log("TEST 3: REGRESSION TESTS")
    log("="*80)
    
    # Step 1: Register user
    log("\n1. Register user for regression tests...")
    token, user_id, email = register_user(name="Regression User")
    if not token:
        log("❌ Failed to register user")
        tests_failed += 1
        failed_tests.append("Regression - User registration failed")
        return
    log(f"✅ User registered")
    tests_passed += 1
    
    # Step 2: Test GET /api/discover still returns 200
    log("\n2. Test GET /api/discover returns 200...")
    resp = requests.get(
        f"{BASE_URL}/discover",
        headers={"Authorization": f"Bearer {token}"}
    )
    if resp.status_code != 200:
        log(f"❌ GET /discover failed: {resp.status_code}")
        tests_failed += 1
        failed_tests.append("Regression - GET /discover failed")
        return
    log("✅ GET /discover returns 200")
    tests_passed += 1
    
    # Step 3: Test PUT /api/auth/profile with moment_privacy
    log("\n3. Test PUT /api/auth/profile with moment_privacy='publico'...")
    resp = requests.put(
        f"{BASE_URL}/auth/profile",
        json={"moment_privacy": "publico"},
        headers={"Authorization": f"Bearer {token}"}
    )
    if resp.status_code != 200:
        log(f"❌ PUT /auth/profile failed: {resp.status_code} - {resp.text}")
        tests_failed += 1
        failed_tests.append("Regression - PUT /auth/profile failed")
        return
    log("✅ PUT /auth/profile with moment_privacy='publico' returns 200")
    tests_passed += 1
    
    log("\n" + "="*80)
    log("✅ ALL REGRESSION TESTS PASSED")
    log("="*80)

def main():
    log("="*80)
    log("STARTING BACKEND TESTS - Capture Likes + Discover Enhancements")
    log("="*80)
    log(f"Base URL: {BASE_URL}")
    log(f"Admin: {ADMIN_EMAIL}")
    
    try:
        # Test 1: Capture like endpoint
        test_capture_like_endpoint()
        
        # Test 2: Discover enhancements
        test_discover_enhancements()
        
        # Test 3: Regression
        test_regression()
        
    except Exception as e:
        log(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        global tests_failed
        tests_failed += 1
    
    # Summary
    log("\n" + "="*80)
    log("TEST SUMMARY")
    log("="*80)
    log(f"✅ Tests passed: {tests_passed}")
    log(f"❌ Tests failed: {tests_failed}")
    if failed_tests:
        log("\nFailed tests:")
        for test in failed_tests:
            log(f"  - {test}")
    log("="*80)
    
    return tests_failed == 0

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
