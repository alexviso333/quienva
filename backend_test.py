#!/usr/bin/env python3
"""
Backend test for two bug fixes:
1. Notification bell (follow) persistence on single event
2. City-wide change alerts ON by default
"""

import requests
import json
import time
from datetime import datetime, timedelta

# Base URL from frontend/.env
BASE_URL = "https://204b173e-f0b3-4059-a373-e97cae5b5cd7.preview.emergentagent.com/api"

# Admin credentials from test_credentials.md
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

def log(msg):
    print(f"[TEST] {msg}")

def test_fix_1_notification_bell_persistence():
    """
    FIX #1: Notification bell (follow) on a single event must persist
    Bug: bell "unselected itself" because is_following returned null
    Fix: is_following now returns true/false correctly
    """
    log("=" * 80)
    log("FIX #1: Testing notification bell persistence")
    log("=" * 80)
    
    # Step 1: Login as admin
    log("Step 1: Login as admin")
    admin_login_resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert admin_login_resp.status_code == 200, f"Admin login failed: {admin_login_resp.status_code} {admin_login_resp.text}"
    admin_token = admin_login_resp.json()["token"]
    log(f"✓ Admin logged in successfully")
    
    # Step 2: Create an event via POST /api/admin/events
    log("Step 2: Create a test event")
    future_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    event_data = {
        "name": "Test Event for Bell Persistence",
        "venue": "Test Venue",
        "date": future_date,
        "time": "23:00",
        "city": "Palma de Mallorca",
        "genre": "Electrónica",
        "image_url": "https://example.com/test.jpg",
        "price_tiers": [{"name": "General", "price": 20.0}],
        "sale_state": "a_la_venta"
    }
    create_event_resp = requests.post(
        f"{BASE_URL}/admin/events",
        json=event_data,
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert create_event_resp.status_code == 200, f"Create event failed: {create_event_resp.status_code} {create_event_resp.text}"
    event_id = create_event_resp.json()["id"]
    log(f"✓ Event created with id: {event_id}")
    
    # Step 3: Register a normal user
    log("Step 3: Register a normal user")
    timestamp = int(time.time())
    user_email = f"testuser{timestamp}@test.com"
    user_password = "testpass123"
    register_resp = requests.post(f"{BASE_URL}/auth/register", json={
        "email": user_email,
        "password": user_password,
        "username": f"testuser{timestamp}",
        "name": f"Test User {timestamp}",
        "birthdate": "1995-01-01",
        "city": "Palma de Mallorca"
    })
    assert register_resp.status_code == 200, f"Register failed: {register_resp.status_code} {register_resp.text}"
    log(f"✓ User registered: {user_email}")
    
    # Step 4: Login as the normal user
    log("Step 4: Login as normal user")
    user_login_resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": user_email,
        "password": user_password
    })
    assert user_login_resp.status_code == 200, f"User login failed: {user_login_resp.status_code} {user_login_resp.text}"
    user_token = user_login_resp.json()["token"]
    log(f"✓ User logged in successfully")
    
    # Step 5: GET /api/events/{id} -> is_following must be false (NOT null)
    log("Step 5: GET event - is_following should be false (not null)")
    get_event_resp = requests.get(
        f"{BASE_URL}/events/{event_id}",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert get_event_resp.status_code == 200, f"Get event failed: {get_event_resp.status_code} {get_event_resp.text}"
    event_data = get_event_resp.json()
    assert "is_following" in event_data, "is_following field missing"
    assert event_data["is_following"] is False, f"Expected is_following=false, got {event_data['is_following']}"
    log(f"✓ is_following = {event_data['is_following']} (correct: false, not null)")
    
    # Step 6: POST /api/events/{id}/follow -> expect {following:true}
    log("Step 6: Follow the event")
    follow_resp = requests.post(
        f"{BASE_URL}/events/{event_id}/follow",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert follow_resp.status_code == 200, f"Follow failed: {follow_resp.status_code} {follow_resp.text}"
    follow_data = follow_resp.json()
    assert follow_data.get("following") is True, f"Expected following=true, got {follow_data}"
    log(f"✓ Follow successful: {follow_data}")
    
    # Step 7: GET /api/events/{id} AGAIN -> is_following MUST be true (CORE FIX)
    log("Step 7: GET event again - is_following MUST be true (CORE FIX)")
    get_event_resp2 = requests.get(
        f"{BASE_URL}/events/{event_id}",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert get_event_resp2.status_code == 200, f"Get event failed: {get_event_resp2.status_code} {get_event_resp2.text}"
    event_data2 = get_event_resp2.json()
    assert "is_following" in event_data2, "is_following field missing"
    assert event_data2["is_following"] is True, f"CORE BUG: Expected is_following=true after follow, got {event_data2['is_following']}"
    log(f"✓✓✓ CORE FIX VERIFIED: is_following = {event_data2['is_following']} (persists correctly!)")
    
    # Step 8: DELETE /api/events/{id}/follow -> then GET -> is_following must be false
    log("Step 8: Unfollow the event")
    unfollow_resp = requests.delete(
        f"{BASE_URL}/events/{event_id}/follow",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert unfollow_resp.status_code == 200, f"Unfollow failed: {unfollow_resp.status_code} {unfollow_resp.text}"
    log(f"✓ Unfollow successful")
    
    log("Step 9: GET event after unfollow - is_following should be false")
    get_event_resp3 = requests.get(
        f"{BASE_URL}/events/{event_id}",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert get_event_resp3.status_code == 200, f"Get event failed: {get_event_resp3.status_code}"
    event_data3 = get_event_resp3.json()
    assert event_data3["is_following"] is False, f"Expected is_following=false after unfollow, got {event_data3['is_following']}"
    log(f"✓ is_following = {event_data3['is_following']} (correct after unfollow)")
    
    # Step 10: Call GET /api/events/{id} multiple times to confirm stability (idempotent)
    log("Step 10: Test idempotency - call GET multiple times")
    for i in range(5):
        get_event_resp_test = requests.get(
            f"{BASE_URL}/events/{event_id}",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert get_event_resp_test.status_code == 200
        event_data_test = get_event_resp_test.json()
        assert event_data_test["is_following"] is False, f"Iteration {i+1}: is_following not stable, got {event_data_test['is_following']}"
    log(f"✓ is_following value is STABLE across 5 calls (idempotent)")
    
    log("=" * 80)
    log("✅ FIX #1 PASSED: Notification bell persistence working correctly!")
    log("=" * 80)
    return True

def test_fix_2_city_alerts_default_on():
    """
    FIX #2: City-wide change alerts ON by default
    Previously: city_change_alerts defaulted to false
    Fix: Now defaults to true for new users
    """
    log("\n" + "=" * 80)
    log("FIX #2: Testing city-wide change alerts default ON")
    log("=" * 80)
    
    # Step 1: Register a brand-new user
    log("Step 1: Register a brand-new user")
    timestamp = int(time.time())
    user_email = f"newuser{timestamp}@test.com"
    user_password = "testpass123"
    register_resp = requests.post(f"{BASE_URL}/auth/register", json={
        "email": user_email,
        "password": user_password,
        "username": f"newuser{timestamp}",
        "name": f"New User {timestamp}",
        "birthdate": "1995-01-01",
        "city": "Palma de Mallorca"
    })
    assert register_resp.status_code == 200, f"Register failed: {register_resp.status_code} {register_resp.text}"
    user_token = register_resp.json()["token"]
    log(f"✓ New user registered: {user_email}")
    
    # Step 2: GET /api/auth/me -> city_change_alerts MUST be true (CORE FIX)
    log("Step 2: GET /auth/me - city_change_alerts MUST be true (CORE FIX)")
    me_resp = requests.get(
        f"{BASE_URL}/auth/me",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert me_resp.status_code == 200, f"Get /auth/me failed: {me_resp.status_code} {me_resp.text}"
    me_data = me_resp.json()
    assert "city_change_alerts" in me_data, "city_change_alerts field missing"
    assert me_data["city_change_alerts"] is True, f"CORE BUG: Expected city_change_alerts=true by default, got {me_data['city_change_alerts']}"
    log(f"✓✓✓ CORE FIX VERIFIED: city_change_alerts = {me_data['city_change_alerts']} (default is TRUE!)")
    
    # Step 3: PUT /api/me/city-alerts {enabled:false} -> {city_change_alerts:false}
    log("Step 3: Toggle OFF - PUT /me/city-alerts {enabled:false}")
    toggle_off_resp = requests.put(
        f"{BASE_URL}/me/city-alerts",
        json={"enabled": False},
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert toggle_off_resp.status_code == 200, f"Toggle OFF failed: {toggle_off_resp.status_code} {toggle_off_resp.text}"
    toggle_off_data = toggle_off_resp.json()
    assert toggle_off_data.get("city_change_alerts") is False, f"Expected city_change_alerts=false, got {toggle_off_data}"
    log(f"✓ Toggle OFF successful: {toggle_off_data}")
    
    # Step 4: GET /api/auth/me -> verify it reflects false
    log("Step 4: GET /auth/me - verify city_change_alerts is false")
    me_resp2 = requests.get(
        f"{BASE_URL}/auth/me",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert me_resp2.status_code == 200
    me_data2 = me_resp2.json()
    assert me_data2["city_change_alerts"] is False, f"Expected city_change_alerts=false, got {me_data2['city_change_alerts']}"
    log(f"✓ city_change_alerts = {me_data2['city_change_alerts']} (persisted correctly)")
    
    # Step 5: PUT /api/me/city-alerts {enabled:true} -> {city_change_alerts:true}
    log("Step 5: Toggle ON - PUT /me/city-alerts {enabled:true}")
    toggle_on_resp = requests.put(
        f"{BASE_URL}/me/city-alerts",
        json={"enabled": True},
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert toggle_on_resp.status_code == 200, f"Toggle ON failed: {toggle_on_resp.status_code} {toggle_on_resp.text}"
    toggle_on_data = toggle_on_resp.json()
    assert toggle_on_data.get("city_change_alerts") is True, f"Expected city_change_alerts=true, got {toggle_on_data}"
    log(f"✓ Toggle ON successful: {toggle_on_data}")
    
    # Step 6: GET /api/auth/me -> verify it reflects true
    log("Step 6: GET /auth/me - verify city_change_alerts is true")
    me_resp3 = requests.get(
        f"{BASE_URL}/auth/me",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert me_resp3.status_code == 200
    me_data3 = me_resp3.json()
    assert me_data3["city_change_alerts"] is True, f"Expected city_change_alerts=true, got {me_data3['city_change_alerts']}"
    log(f"✓ city_change_alerts = {me_data3['city_change_alerts']} (toggle works both ways)")
    
    log("=" * 80)
    log("✅ FIX #2 PASSED: City-wide change alerts default ON working correctly!")
    log("=" * 80)
    return True

def main():
    log("Starting backend tests for 2 bug fixes")
    log(f"Base URL: {BASE_URL}")
    log(f"Admin: {ADMIN_EMAIL}")
    
    try:
        # Test FIX #1
        fix1_passed = test_fix_1_notification_bell_persistence()
        
        # Test FIX #2
        fix2_passed = test_fix_2_city_alerts_default_on()
        
        # Summary
        log("\n" + "=" * 80)
        log("FINAL SUMMARY")
        log("=" * 80)
        log(f"FIX #1 (Notification bell persistence): {'✅ PASS' if fix1_passed else '❌ FAIL'}")
        log(f"FIX #2 (City alerts default ON): {'✅ PASS' if fix2_passed else '❌ FAIL'}")
        
        if fix1_passed and fix2_passed:
            log("\n🎉 ALL TESTS PASSED! Both fixes working correctly.")
            return 0
        else:
            log("\n❌ SOME TESTS FAILED")
            return 1
            
    except Exception as e:
        log(f"\n❌ TEST FAILED WITH EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())
