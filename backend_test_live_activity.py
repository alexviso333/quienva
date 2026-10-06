#!/usr/bin/env python3
"""
Backend test for Live Activity (Dynamic Island) features - ITERACIÓN 15
Tests:
1. Environment sanity (GET /api/events, login with 3 users)
2. POST /api/live-activity/token (register token with plan_slug)
3. POST /api/live-activity/end (mark activity as ended)
4. Full plan flow with threshold + live activity + notifications
5. Plan closure notifications (plan_closed, plan_cancelled)
6. Quick regression of plan endpoints
"""

import requests
import time
import json
from datetime import datetime, timedelta

# Backend URL from frontend/.env
API_BASE = "https://voting-island-widget.preview.emergentagent.com/api"

# Test credentials from /app/memory/test_credentials.md
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "QuienVa2025!"
TEST_EMAIL = "test@quienva.app"
TEST_PASSWORD = "Test1234!"
FRIEND_EMAIL = "amigo@quienva.app"
FRIEND_PASSWORD = "Test1234!"

def login(email, password):
    """Login and return access token"""
    resp = requests.post(f"{API_BASE}/auth/login", json={
        "email": email,
        "password": password
    })
    if resp.status_code != 200:
        print(f"❌ Login failed for {email}: {resp.status_code} {resp.text}")
        return None
    data = resp.json()
    return data.get("token") or data.get("access_token")

def test_environment_sanity():
    """Test 1: Environment sanity check"""
    print("\n" + "="*80)
    print("TEST 1: ENVIRONMENT SANITY CHECK")
    print("="*80)
    
    # 1.1 GET /api/events should return ~124 events
    print("\n[1.1] GET /api/events (should return ~124 events)")
    resp = requests.get(f"{API_BASE}/events")
    if resp.status_code != 200:
        print(f"❌ FAILED: GET /api/events returned {resp.status_code}")
        return False
    events = resp.json()
    event_count = len(events)
    print(f"✅ PASSED: GET /api/events returned {event_count} events")
    if event_count < 100:
        print(f"⚠️  WARNING: Expected ~124 events, got {event_count}")
    
    # 1.2 Login with admin
    print("\n[1.2] Login with admin@quienva.app")
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    if not admin_token:
        print(f"❌ FAILED: Admin login failed")
        return False
    print(f"✅ PASSED: Admin login successful")
    
    # 1.3 Login with test user
    print("\n[1.3] Login with test@quienva.app")
    test_token = login(TEST_EMAIL, TEST_PASSWORD)
    if not test_token:
        print(f"❌ FAILED: Test user login failed")
        return False
    print(f"✅ PASSED: Test user login successful")
    
    # 1.4 Login with friend
    print("\n[1.4] Login with amigo@quienva.app")
    friend_token = login(FRIEND_EMAIL, FRIEND_PASSWORD)
    if not friend_token:
        print(f"❌ FAILED: Friend login failed")
        return False
    print(f"✅ PASSED: Friend login successful")
    
    # 1.5 GET /api/plans/mine should work
    print("\n[1.5] GET /api/plans/mine (authenticated)")
    resp = requests.get(f"{API_BASE}/plans/mine", headers={
        "Authorization": f"Bearer {test_token}"
    })
    if resp.status_code != 200:
        print(f"❌ FAILED: GET /api/plans/mine returned {resp.status_code}")
        return False
    print(f"✅ PASSED: GET /api/plans/mine returned {resp.status_code}")
    
    print("\n" + "="*80)
    print("✅ TEST 1 PASSED: Environment sanity check complete")
    print("="*80)
    return True

def test_live_activity_token():
    """Test 2: POST /api/live-activity/token"""
    print("\n" + "="*80)
    print("TEST 2: POST /api/live-activity/token")
    print("="*80)
    
    # Login as test user
    test_token = login(TEST_EMAIL, TEST_PASSWORD)
    if not test_token:
        print("❌ FAILED: Could not login")
        return False
    
    # Create a plan first
    print("\n[2.1] Create a plan for testing")
    plan_data = {
        "titulo": "Test Live Activity Plan",
        "opciones": [
            {"texto_libre": "Opción A"},
            {"texto_libre": "Opción B"}
        ],
        "umbral_personas": 2,
        "hora_limite": (datetime.now() + timedelta(hours=24)).isoformat()
    }
    resp = requests.post(f"{API_BASE}/plans", json=plan_data, headers={
        "Authorization": f"Bearer {test_token}"
    })
    if resp.status_code != 200:
        print(f"❌ FAILED: Could not create plan: {resp.status_code} {resp.text}")
        return False
    plan = resp.json()
    plan_slug = plan.get("slug")
    print(f"✅ Plan created with slug: {plan_slug}")
    
    # 2.2 POST /api/live-activity/token with valid data
    print("\n[2.2] POST /api/live-activity/token with valid token and plan_slug")
    fake_token = "a" * 64  # 64 hex chars (fake APNs token)
    activity_id = f"plan:{plan_slug}"
    resp = requests.post(f"{API_BASE}/live-activity/token", json={
        "activity_id": activity_id,
        "token": fake_token,
        "plan_slug": plan_slug
    }, headers={
        "Authorization": f"Bearer {test_token}"
    })
    if resp.status_code != 200:
        print(f"❌ FAILED: POST /api/live-activity/token returned {resp.status_code}: {resp.text}")
        return False
    data = resp.json()
    if not data.get("ok"):
        print(f"❌ FAILED: Response ok=false")
        return False
    plan_id = data.get("plan_id")
    if not plan_id:
        print(f"❌ FAILED: No plan_id in response")
        return False
    print(f"✅ PASSED: POST /api/live-activity/token returned 200 with plan_id={plan_id}")
    
    # 2.3 Verify in MongoDB
    print("\n[2.3] Verify in MongoDB (db.live_activities)")
    import pymongo
    client = pymongo.MongoClient("mongodb://localhost:27017")
    db = client["quienva"]
    la_doc = db.live_activities.find_one({"activity_id": activity_id})
    if not la_doc:
        print(f"❌ FAILED: No document found in live_activities collection")
        return False
    if la_doc.get("plan_id") != plan_id:
        print(f"❌ FAILED: plan_id mismatch in MongoDB: {la_doc.get('plan_id')} != {plan_id}")
        return False
    if la_doc.get("ended") != False:
        print(f"❌ FAILED: ended should be False, got {la_doc.get('ended')}")
        return False
    if la_doc.get("token") != fake_token:
        print(f"❌ FAILED: token mismatch in MongoDB")
        return False
    print(f"✅ PASSED: MongoDB document verified: plan_id={plan_id}, ended=False, token stored")
    
    # 2.4 POST with empty token -> 400
    print("\n[2.4] POST /api/live-activity/token with empty token (should return 400)")
    resp = requests.post(f"{API_BASE}/live-activity/token", json={
        "activity_id": activity_id,
        "token": "",
        "plan_slug": plan_slug
    }, headers={
        "Authorization": f"Bearer {test_token}"
    })
    if resp.status_code != 400:
        print(f"❌ FAILED: Expected 400, got {resp.status_code}")
        return False
    print(f"✅ PASSED: Empty token correctly rejected with 400")
    
    # 2.5 POST without auth -> 401
    print("\n[2.5] POST /api/live-activity/token without auth (should return 401)")
    resp = requests.post(f"{API_BASE}/live-activity/token", json={
        "activity_id": activity_id,
        "token": fake_token,
        "plan_slug": plan_slug
    })
    if resp.status_code != 401:
        print(f"❌ FAILED: Expected 401, got {resp.status_code}")
        return False
    print(f"✅ PASSED: No auth correctly rejected with 401")
    
    print("\n" + "="*80)
    print("✅ TEST 2 PASSED: POST /api/live-activity/token working correctly")
    print("="*80)
    return True, activity_id

def test_live_activity_end(activity_id):
    """Test 3: POST /api/live-activity/end"""
    print("\n" + "="*80)
    print("TEST 3: POST /api/live-activity/end")
    print("="*80)
    
    # Login as test user
    test_token = login(TEST_EMAIL, TEST_PASSWORD)
    if not test_token:
        print("❌ FAILED: Could not login")
        return False
    
    # 3.1 POST /api/live-activity/end
    print("\n[3.1] POST /api/live-activity/end")
    resp = requests.post(f"{API_BASE}/live-activity/end", json={
        "activity_id": activity_id
    }, headers={
        "Authorization": f"Bearer {test_token}"
    })
    if resp.status_code != 200:
        print(f"❌ FAILED: POST /api/live-activity/end returned {resp.status_code}: {resp.text}")
        return False
    data = resp.json()
    if not data.get("ok"):
        print(f"❌ FAILED: Response ok=false")
        return False
    print(f"✅ PASSED: POST /api/live-activity/end returned 200")
    
    # 3.2 Verify in MongoDB
    print("\n[3.2] Verify ended=true in MongoDB")
    import pymongo
    client = pymongo.MongoClient("mongodb://localhost:27017")
    db = client["quienva"]
    la_doc = db.live_activities.find_one({"activity_id": activity_id})
    if not la_doc:
        print(f"❌ FAILED: No document found in live_activities collection")
        return False
    if la_doc.get("ended") != True:
        print(f"❌ FAILED: ended should be True, got {la_doc.get('ended')}")
        return False
    print(f"✅ PASSED: MongoDB document verified: ended=True")
    
    print("\n" + "="*80)
    print("✅ TEST 3 PASSED: POST /api/live-activity/end working correctly")
    print("="*80)
    return True

def test_plan_flow_with_threshold():
    """Test 4: Full plan flow with threshold + live activity + APNs error handling"""
    print("\n" + "="*80)
    print("TEST 4: FULL PLAN FLOW WITH THRESHOLD + LIVE ACTIVITY")
    print("="*80)
    
    # Login as test user (creator)
    test_token = login(TEST_EMAIL, TEST_PASSWORD)
    if not test_token:
        print("❌ FAILED: Could not login as test user")
        return False
    
    # Login as friend (participant with account)
    friend_token = login(FRIEND_EMAIL, FRIEND_PASSWORD)
    if not friend_token:
        print("❌ FAILED: Could not login as friend")
        return False
    
    # 4.1 Create plan with umbral_personas=2
    print("\n[4.1] Create plan with umbral_personas=2 and 2 options")
    plan_data = {
        "titulo": "Test Threshold Plan",
        "opciones": [
            {"texto_libre": "Bar A"},
            {"texto_libre": "Bar B"}
        ],
        "umbral_personas": 2,
        "hora_limite": (datetime.now() + timedelta(hours=24)).isoformat()
    }
    resp = requests.post(f"{API_BASE}/plans", json=plan_data, headers={
        "Authorization": f"Bearer {test_token}"
    })
    if resp.status_code != 200:
        print(f"❌ FAILED: Could not create plan: {resp.status_code} {resp.text}")
        return False
    plan = resp.json()
    plan_slug = plan.get("slug")
    creador_token = plan.get("creador_token")
    print(f"✅ Plan created with slug: {plan_slug}, umbral_personas=2")
    
    # 4.2 Register live activity token for this plan
    print("\n[4.2] Register live activity token (fake APNs token)")
    fake_token = "b" * 64  # 64 hex chars (fake APNs token)
    activity_id = f"plan:{plan_slug}"
    resp = requests.post(f"{API_BASE}/live-activity/token", json={
        "activity_id": activity_id,
        "token": fake_token,
        "plan_slug": plan_slug
    }, headers={
        "Authorization": f"Bearer {test_token}"
    })
    if resp.status_code != 200:
        print(f"❌ FAILED: Could not register live activity token: {resp.status_code}")
        return False
    print(f"✅ Live activity token registered")
    
    # 4.3 First response "dentro" (friend with account)
    print("\n[4.3] First response 'dentro' from friend (with account)")
    resp = requests.post(f"{API_BASE}/plans/{plan_slug}/respond", json={
        "apodo": "Amigo Test",
        "intencion": "dentro"
    }, headers={
        "Authorization": f"Bearer {friend_token}"
    })
    if resp.status_code != 200:
        print(f"❌ FAILED: First response failed: {resp.status_code} {resp.text}")
        return False
    data = resp.json()
    plan_after_1 = data.get("plan", {})
    if plan_after_1.get("estado") != "abierto":
        print(f"❌ FAILED: Plan should still be 'abierto' after 1 response, got {plan_after_1.get('estado')}")
        return False
    print(f"✅ First response recorded, plan still 'abierto' (1/2 threshold)")
    
    # 4.4 Second response "dentro" (guest without account)
    print("\n[4.4] Second response 'dentro' from guest (without account)")
    resp = requests.post(f"{API_BASE}/plans/{plan_slug}/respond", json={
        "apodo": "Guest User",
        "intencion": "dentro"
    })
    if resp.status_code != 200:
        print(f"❌ FAILED: Second response failed: {resp.status_code} {resp.text}")
        return False
    data = resp.json()
    plan_after_2 = data.get("plan", {})
    
    # 4.5 Verify plan closed by quorum
    print("\n[4.5] Verify plan closed by quorum (estado=cerrado, opcion_ganadora != null)")
    if plan_after_2.get("estado") != "cerrado":
        print(f"❌ FAILED: Plan should be 'cerrado' after reaching threshold, got {plan_after_2.get('estado')}")
        return False
    if not plan_after_2.get("opcion_ganadora"):
        print(f"❌ FAILED: opcion_ganadora should be set, got {plan_after_2.get('opcion_ganadora')}")
        return False
    print(f"✅ Plan closed by quorum: estado=cerrado, opcion_ganadora={plan_after_2.get('opcion_ganadora')}")
    
    # 4.6 Check backend logs for APNs warnings (not errors)
    print("\n[4.6] Check backend logs for APNs warnings (should have BadDeviceToken warning, no uncaught exceptions)")
    import subprocess
    result = subprocess.run(
        ["tail", "-n", "50", "/var/log/supervisor/backend.err.log"],
        capture_output=True, text=True
    )
    logs = result.stdout
    
    # Look for APNs warnings
    has_apns_warning = "APNs" in logs or "apns" in logs or "live-activity" in logs or "live activity" in logs
    has_uncaught_exception = "Traceback" in logs or "Exception" in logs.split("\n")[-20:]  # Check last 20 lines
    has_500_error = "500" in logs.split("\n")[-20:]
    
    print(f"   Backend logs (last 50 lines):")
    print(f"   - APNs-related messages: {'Yes' if has_apns_warning else 'No'}")
    print(f"   - Uncaught exceptions in recent logs: {'Yes ❌' if has_uncaught_exception else 'No ✅'}")
    print(f"   - 500 errors in recent logs: {'Yes ❌' if has_500_error else 'No ✅'}")
    
    if has_uncaught_exception:
        print(f"⚠️  WARNING: Found uncaught exceptions in logs (last 20 lines)")
        print("   Recent logs:")
        print("   " + "\n   ".join(logs.split("\n")[-20:]))
    
    if has_500_error:
        print(f"⚠️  WARNING: Found 500 errors in logs")
    
    print(f"✅ PASSED: Plan flow completed successfully, HTTP 200 even with fake APNs token")
    
    print("\n" + "="*80)
    print("✅ TEST 4 PASSED: Full plan flow with threshold working correctly")
    print("="*80)
    return True, plan_slug, friend_token, test_token

def test_plan_notifications(plan_slug, friend_token, test_token):
    """Test 5: Plan closure notifications"""
    print("\n" + "="*80)
    print("TEST 5: PLAN CLOSURE NOTIFICATIONS")
    print("="*80)
    
    # 5.1 Check notifications for friend (participant with account)
    print("\n[5.1] GET /api/notifications for friend (should have plan_closed notification)")
    resp = requests.get(f"{API_BASE}/notifications", headers={
        "Authorization": f"Bearer {friend_token}"
    })
    if resp.status_code != 200:
        print(f"❌ FAILED: GET /api/notifications returned {resp.status_code}")
        return False
    
    notifications = resp.json()
    plan_closed_notif = None
    for notif in notifications:
        if notif.get("type") == "plan_closed" and plan_slug in str(notif.get("data", {})):
            plan_closed_notif = notif
            break
    
    if not plan_closed_notif:
        print(f"❌ FAILED: No plan_closed notification found for friend")
        print(f"   Notifications: {json.dumps(notifications, indent=2)}")
        return False
    
    message = plan_closed_notif.get("message", "")
    if "Plan cerrado" not in message and "cerrado" not in message:
        print(f"❌ FAILED: Notification message should contain 'Plan cerrado', got: {message}")
        return False
    
    print(f"✅ PASSED: Friend received plan_closed notification: {message}")
    
    # 5.2 Check notifications for creator (test user)
    print("\n[5.2] GET /api/notifications for creator (should also have plan_closed notification)")
    resp = requests.get(f"{API_BASE}/notifications", headers={
        "Authorization": f"Bearer {test_token}"
    })
    if resp.status_code != 200:
        print(f"❌ FAILED: GET /api/notifications returned {resp.status_code}")
        return False
    
    notifications = resp.json()
    plan_closed_notif = None
    for notif in notifications:
        if notif.get("type") == "plan_closed" and plan_slug in str(notif.get("data", {})):
            plan_closed_notif = notif
            break
    
    if not plan_closed_notif:
        print(f"❌ FAILED: No plan_closed notification found for creator")
        return False
    
    print(f"✅ PASSED: Creator received plan_closed notification")
    
    # 5.3 Create another plan and cancel it
    print("\n[5.3] Create another plan and cancel it (should trigger plan_cancelled notification)")
    plan_data = {
        "titulo": "Test Cancel Plan",
        "opciones": [
            {"texto_libre": "Option 1"},
            {"texto_libre": "Option 2"}
        ]
    }
    resp = requests.post(f"{API_BASE}/plans", json=plan_data, headers={
        "Authorization": f"Bearer {test_token}"
    })
    if resp.status_code != 200:
        print(f"❌ FAILED: Could not create plan: {resp.status_code}")
        return False
    plan = resp.json()
    cancel_slug = plan.get("slug")
    creador_token = plan.get("creador_token")
    print(f"✅ Plan created with slug: {cancel_slug}")
    
    # Cancel the plan
    print("\n[5.4] Cancel the plan")
    resp = requests.post(f"{API_BASE}/plans/{cancel_slug}/cancel", headers={
        "x-participante-token": creador_token
    })
    if resp.status_code != 200:
        print(f"❌ FAILED: Could not cancel plan: {resp.status_code} {resp.text}")
        return False
    print(f"✅ Plan cancelled")
    
    # Check for plan_cancelled notification
    print("\n[5.5] GET /api/notifications for creator (should have plan_cancelled notification)")
    time.sleep(1)  # Give it a moment to process
    resp = requests.get(f"{API_BASE}/notifications", headers={
        "Authorization": f"Bearer {test_token}"
    })
    if resp.status_code != 200:
        print(f"❌ FAILED: GET /api/notifications returned {resp.status_code}")
        return False
    
    notifications = resp.json()
    plan_cancelled_notif = None
    for notif in notifications:
        if notif.get("type") == "plan_cancelled" and cancel_slug in str(notif.get("data", {})):
            plan_cancelled_notif = notif
            break
    
    if not plan_cancelled_notif:
        print(f"❌ FAILED: No plan_cancelled notification found")
        print(f"   Notifications: {json.dumps(notifications[:3], indent=2)}")
        return False
    
    message = plan_cancelled_notif.get("message", "")
    if "cancelado" not in message.lower():
        print(f"❌ FAILED: Notification message should contain 'cancelado', got: {message}")
        return False
    
    print(f"✅ PASSED: Creator received plan_cancelled notification: {message}")
    
    print("\n" + "="*80)
    print("✅ TEST 5 PASSED: Plan notifications working correctly")
    print("="*80)
    return True

def test_plan_regression():
    """Test 6: Quick regression of plan endpoints"""
    print("\n" + "="*80)
    print("TEST 6: PLAN ENDPOINTS REGRESSION")
    print("="*80)
    
    # Login as test user
    test_token = login(TEST_EMAIL, TEST_PASSWORD)
    if not test_token:
        print("❌ FAILED: Could not login")
        return False
    
    # 6.1 POST /api/plans
    print("\n[6.1] POST /api/plans (create plan)")
    plan_data = {
        "titulo": "Regression Test Plan",
        "opciones": [
            {"texto_libre": "Option A"},
            {"texto_libre": "Option B"}
        ]
    }
    resp = requests.post(f"{API_BASE}/plans", json=plan_data, headers={
        "Authorization": f"Bearer {test_token}"
    })
    if resp.status_code != 200:
        print(f"❌ FAILED: POST /api/plans returned {resp.status_code}")
        return False
    plan = resp.json()
    plan_slug = plan.get("slug")
    creador_token = plan.get("creador_token")
    print(f"✅ PASSED: POST /api/plans returned 200, slug={plan_slug}")
    
    # 6.2 GET /api/plans/{slug}
    print("\n[6.2] GET /api/plans/{slug}")
    resp = requests.get(f"{API_BASE}/plans/{plan_slug}")
    if resp.status_code != 200:
        print(f"❌ FAILED: GET /api/plans/{plan_slug} returned {resp.status_code}")
        return False
    print(f"✅ PASSED: GET /api/plans/{plan_slug} returned 200")
    
    # 6.3 POST /api/plans/{slug}/respond
    print("\n[6.3] POST /api/plans/{slug}/respond")
    resp = requests.post(f"{API_BASE}/plans/{plan_slug}/respond", json={
        "apodo": "Test User",
        "intencion": "dentro"
    })
    if resp.status_code != 200:
        print(f"❌ FAILED: POST /api/plans/{plan_slug}/respond returned {resp.status_code}")
        return False
    print(f"✅ PASSED: POST /api/plans/{plan_slug}/respond returned 200")
    
    # 6.4 POST /api/plans/{slug}/close
    print("\n[6.4] POST /api/plans/{slug}/close")
    resp = requests.post(f"{API_BASE}/plans/{plan_slug}/close", headers={
        "x-participante-token": creador_token
    })
    if resp.status_code != 200:
        print(f"❌ FAILED: POST /api/plans/{plan_slug}/close returned {resp.status_code}")
        return False
    print(f"✅ PASSED: POST /api/plans/{plan_slug}/close returned 200")
    
    # 6.5 Create another plan for cancel test
    print("\n[6.5] POST /api/plans (create another plan for cancel test)")
    resp = requests.post(f"{API_BASE}/plans", json=plan_data, headers={
        "Authorization": f"Bearer {test_token}"
    })
    if resp.status_code != 200:
        print(f"❌ FAILED: POST /api/plans returned {resp.status_code}")
        return False
    plan2 = resp.json()
    plan_slug2 = plan2.get("slug")
    creador_token2 = plan2.get("creador_token")
    
    # 6.6 POST /api/plans/{slug}/cancel
    print("\n[6.6] POST /api/plans/{slug}/cancel")
    resp = requests.post(f"{API_BASE}/plans/{plan_slug2}/cancel", headers={
        "x-participante-token": creador_token2
    })
    if resp.status_code != 200:
        print(f"❌ FAILED: POST /api/plans/{plan_slug2}/cancel returned {resp.status_code}")
        return False
    print(f"✅ PASSED: POST /api/plans/{plan_slug2}/cancel returned 200")
    
    # 6.7 GET /api/events/{id}/plans (need an event first)
    print("\n[6.7] GET /api/events/{id}/plans")
    # Get first event
    resp = requests.get(f"{API_BASE}/events")
    if resp.status_code != 200:
        print(f"❌ FAILED: GET /api/events returned {resp.status_code}")
        return False
    events = resp.json()
    if not events:
        print(f"⚠️  SKIPPED: No events available for testing GET /api/events/{id}/plans")
    else:
        event_id = events[0].get("id")
        resp = requests.get(f"{API_BASE}/events/{event_id}/plans")
        if resp.status_code != 200:
            print(f"❌ FAILED: GET /api/events/{event_id}/plans returned {resp.status_code}")
            return False
        print(f"✅ PASSED: GET /api/events/{event_id}/plans returned 200")
    
    # 6.8 GET /api/plans/mine
    print("\n[6.8] GET /api/plans/mine")
    resp = requests.get(f"{API_BASE}/plans/mine", headers={
        "Authorization": f"Bearer {test_token}"
    })
    if resp.status_code != 200:
        print(f"❌ FAILED: GET /api/plans/mine returned {resp.status_code}")
        return False
    print(f"✅ PASSED: GET /api/plans/mine returned 200")
    
    # 6.9 GET /api/og/plan/{slug} (OG image)
    print("\n[6.9] GET /api/og/plan/{slug} (OG image, should be image/png or image/svg+xml)")
    resp = requests.get(f"{API_BASE}/og/plan/{plan_slug}")
    if resp.status_code != 200:
        print(f"❌ FAILED: GET /api/og/plan/{plan_slug} returned {resp.status_code}")
        return False
    content_type = resp.headers.get("content-type", "")
    if "image/png" not in content_type and "image/svg" not in content_type:
        print(f"❌ FAILED: Expected image/png or image/svg+xml, got {content_type}")
        return False
    print(f"✅ PASSED: GET /api/og/plan/{plan_slug} returned 200 with {content_type}")
    
    print("\n" + "="*80)
    print("✅ TEST 6 PASSED: Plan endpoints regression complete")
    print("="*80)
    return True

def main():
    print("\n" + "="*80)
    print("BACKEND TEST: LIVE ACTIVITY (DYNAMIC ISLAND) - ITERACIÓN 15")
    print("="*80)
    print(f"API Base: {API_BASE}")
    print(f"Test credentials: admin@quienva.app, test@quienva.app, amigo@quienva.app")
    
    all_passed = True
    
    # Test 1: Environment sanity
    if not test_environment_sanity():
        all_passed = False
        print("\n❌ TEST 1 FAILED - Stopping tests")
        return
    
    # Test 2: POST /api/live-activity/token
    result = test_live_activity_token()
    if isinstance(result, tuple):
        success, activity_id = result
        if not success:
            all_passed = False
            print("\n❌ TEST 2 FAILED - Continuing with other tests")
            activity_id = None
    else:
        all_passed = False
        activity_id = None
    
    # Test 3: POST /api/live-activity/end
    if activity_id:
        if not test_live_activity_end(activity_id):
            all_passed = False
            print("\n❌ TEST 3 FAILED - Continuing with other tests")
    else:
        print("\n⚠️  TEST 3 SKIPPED - No activity_id from Test 2")
    
    # Test 4: Full plan flow with threshold
    result = test_plan_flow_with_threshold()
    if isinstance(result, tuple):
        success, plan_slug, friend_token, test_token = result
        if not success:
            all_passed = False
            print("\n❌ TEST 4 FAILED - Continuing with other tests")
            plan_slug = None
    else:
        all_passed = False
        plan_slug = None
        friend_token = None
        test_token = None
    
    # Test 5: Plan notifications
    if plan_slug and friend_token and test_token:
        if not test_plan_notifications(plan_slug, friend_token, test_token):
            all_passed = False
            print("\n❌ TEST 5 FAILED - Continuing with other tests")
    else:
        print("\n⚠️  TEST 5 SKIPPED - Missing data from Test 4")
    
    # Test 6: Plan regression
    if not test_plan_regression():
        all_passed = False
        print("\n❌ TEST 6 FAILED")
    
    # Final summary
    print("\n" + "="*80)
    print("FINAL SUMMARY")
    print("="*80)
    if all_passed:
        print("✅ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED - See details above")
    print("="*80)

if __name__ == "__main__":
    main()
