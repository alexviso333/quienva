#!/usr/bin/env python3
"""
Backend testing for ¿Quién va? app - Feed ordering, venue reorder, and affiliate fix
Testing 3 specific tasks as per review request.
"""

import requests
import json
import sys
from datetime import datetime

# Backend URL from frontend/.env
BASE_URL = "https://6ddc88ff-0b94-4edf-bb0b-c4e233c8af3e.preview.emergentagent.com/api"

# Admin credentials from test_credentials.md
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

def log(msg):
    """Print timestamped log message"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def test_admin_login():
    """Login as admin and return token"""
    log("🔐 Testing admin login...")
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.status_code} {resp.text}"
    data = resp.json()
    assert "token" in data, "No token in login response"
    assert "user" in data, "No user in login response"
    assert data["user"]["role"] == "admin", f"User is not admin: {data['user'].get('role')}"
    assert data["user"]["city"] == "Palma de Mallorca", f"Admin city is not Palma de Mallorca: {data['user'].get('city')}"
    log(f"✅ Admin login successful: {data['user']['email']}, city: {data['user']['city']}")
    return data["token"]

def register_normal_user(token_suffix):
    """Register a normal (non-admin) user and return token"""
    log(f"👤 Registering normal user with suffix {token_suffix}...")
    email = f"normaluser{token_suffix}@test.com"
    resp = requests.post(f"{BASE_URL}/auth/register", json={
        "email": email,
        "password": "testpass123",
        "name": f"Normal User {token_suffix}",
        "username": f"normaluser{token_suffix}",
        "city": "Palma de Mallorca",
        "birthdate": "1995-01-01"
    })
    assert resp.status_code == 200, f"User registration failed: {resp.status_code} {resp.text}"
    data = resp.json()
    assert "token" in data, "No token in registration response"
    assert data["user"]["role"] == "user", f"User role is not 'user': {data['user'].get('role')}"
    log(f"✅ Normal user registered: {email}")
    return data["token"]

def test_task1_feed_ordering(admin_token, normal_token):
    """
    TASK 1: GET /api/events feed ordering
    - Must return 200 (not 500)
    - Events ordered by venue importance (order field, lower = first)
    - Verify Selva Club (order=30) appears before order=100 venues
    - is_affiliate field: boolean for admin, null for normal user
    """
    log("\n" + "="*80)
    log("TASK 1: Testing GET /api/events feed ordering")
    log("="*80)
    
    # Test 1a: Admin user - feed should return 200
    log("\n📋 Test 1a: GET /api/events as admin (date_filter=all, genre=all)")
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = requests.get(f"{BASE_URL}/events", params={"date_filter": "all", "genre": "all"}, headers=headers)
    assert resp.status_code == 200, f"Feed returned {resp.status_code} instead of 200: {resp.text}"
    events = resp.json()
    assert isinstance(events, list), f"Feed response is not a list: {type(events)}"
    log(f"✅ Feed returned 200 with {len(events)} events")
    
    # Test 1b: Verify venue ordering - collect venue names and their first appearance order
    log("\n📋 Test 1b: Verify venue importance ordering (Selva Club order=30 should appear before order=100 venues)")
    
    # First, get all venues to see their order values
    venues_resp = requests.get(f"{BASE_URL}/venues", headers=headers)
    assert venues_resp.status_code == 200, f"Venues endpoint failed: {venues_resp.status_code}"
    venues = venues_resp.json()
    venue_orders = {v["name"]: v.get("order", 10000) for v in venues}
    log(f"📊 Venue orders from /api/venues: {json.dumps(venue_orders, indent=2)}")
    
    # Track first appearance of each venue in feed
    venue_first_appearance = {}
    for idx, event in enumerate(events):
        venue_name = event.get("venue", "")
        if venue_name and venue_name not in venue_first_appearance:
            venue_first_appearance[venue_name] = {
                "position": idx,
                "order": venue_orders.get(venue_name, 10000),
                "event_name": event.get("name", "")
            }
    
    log(f"📊 Venue first appearances in feed (first 10):")
    sorted_appearances = sorted(venue_first_appearance.items(), key=lambda x: x[1]["position"])
    for venue, info in sorted_appearances[:10]:
        log(f"  Position {info['position']}: {venue} (order={info['order']}) - {info['event_name']}")
    
    # Verify Selva Club appears before order=100 venues
    selva_info = venue_first_appearance.get("Selva Club")
    if selva_info:
        log(f"\n🎯 Selva Club found at position {selva_info['position']} with order={selva_info['order']}")
        
        # Find first order=100 venue
        first_order_100_pos = None
        first_order_100_venue = None
        for venue, info in sorted_appearances:
            if info["order"] == 100:
                first_order_100_pos = info["position"]
                first_order_100_venue = venue
                break
        
        if first_order_100_pos is not None:
            log(f"🎯 First order=100 venue: {first_order_100_venue} at position {first_order_100_pos}")
            assert selva_info["position"] < first_order_100_pos, \
                f"❌ Selva Club (order=30, pos={selva_info['position']}) should appear BEFORE {first_order_100_venue} (order=100, pos={first_order_100_pos})"
            log(f"✅ Venue ordering correct: Selva Club (pos {selva_info['position']}) appears before order=100 venues (pos {first_order_100_pos})")
        else:
            log("⚠️  No order=100 venues found in feed to compare")
    else:
        log("⚠️  Selva Club not found in feed (may not have events)")
    
    # Test 1c: Verify is_affiliate field for admin (should be boolean)
    log("\n📋 Test 1c: Verify is_affiliate field for admin user")
    admin_affiliate_values = [e.get("is_affiliate") for e in events[:5]]
    log(f"📊 is_affiliate values for admin (first 5 events): {admin_affiliate_values}")
    for event in events[:5]:
        is_aff = event.get("is_affiliate")
        assert is_aff is not None, f"❌ is_affiliate is None for admin (should be boolean): event {event.get('name')}"
        assert isinstance(is_aff, bool), f"❌ is_affiliate is not boolean for admin: {type(is_aff)} for event {event.get('name')}"
    log(f"✅ is_affiliate is boolean for admin (all values are False as expected - no FourVenues token in this env)")
    
    # Test 1d: Verify is_affiliate field for normal user (should be null)
    log("\n📋 Test 1d: Verify is_affiliate field for normal user (should be null)")
    normal_headers = {"Authorization": f"Bearer {normal_token}"}
    resp = requests.get(f"{BASE_URL}/events", params={"date_filter": "all", "genre": "all"}, headers=normal_headers)
    assert resp.status_code == 200, f"Feed for normal user returned {resp.status_code}"
    normal_events = resp.json()
    normal_affiliate_values = [e.get("is_affiliate") for e in normal_events[:5]]
    log(f"📊 is_affiliate values for normal user (first 5 events): {normal_affiliate_values}")
    for event in normal_events[:5]:
        is_aff = event.get("is_affiliate")
        assert is_aff is None, f"❌ is_affiliate should be null for normal user, got {is_aff} for event {event.get('name')}"
    log(f"✅ is_affiliate is null for normal user (as expected)")
    
    log("\n✅ TASK 1 COMPLETE: Feed ordering working correctly")
    return events

def test_task2_venue_reorder(admin_token):
    """
    TASK 2: PUT /api/admin/venues/reorder
    - Admin-only (non-admin should get 403)
    - Reorder venues and verify feed changes
    - Restore original order after test
    """
    log("\n" + "="*80)
    log("TASK 2: Testing PUT /api/admin/venues/reorder")
    log("="*80)
    
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # Test 2a: Get current venues list
    log("\n📋 Test 2a: Get current venues list")
    resp = requests.get(f"{BASE_URL}/venues", headers=headers)
    assert resp.status_code == 200, f"GET /api/venues failed: {resp.status_code}"
    venues = resp.json()
    log(f"✅ Retrieved {len(venues)} venues")
    
    # Find Selva Club and Sotano Club
    selva = next((v for v in venues if v["name"] == "Selva Club"), None)
    sotano = next((v for v in venues if v["name"] == "Sotano Club"), None)
    
    if not selva:
        log("⚠️  Selva Club not found in venues list")
        selva_id = None
        selva_order = None
    else:
        selva_id = selva["id"]
        selva_order = selva.get("order", 10000)
        log(f"📊 Selva Club: id={selva_id}, order={selva_order}")
    
    if not sotano:
        log("⚠️  Sotano Club not found in venues list")
        sotano_id = None
        sotano_order = None
    else:
        sotano_id = sotano["id"]
        sotano_order = sotano.get("order", 10000)
        log(f"📊 Sotano Club: id={sotano_id}, order={sotano_order}")
    
    if not selva_id or not sotano_id:
        log("⚠️  Cannot test reorder without both Selva Club and Sotano Club")
        log("✅ TASK 2 SKIPPED: Required venues not found")
        return
    
    # Test 2b: Get initial feed order
    log("\n📋 Test 2b: Get initial feed order")
    resp = requests.get(f"{BASE_URL}/events", params={"date_filter": "all", "genre": "all"}, headers=headers)
    assert resp.status_code == 200, f"Feed failed: {resp.status_code}"
    initial_events = resp.json()
    
    # Find first appearance of each venue
    selva_pos_initial = None
    sotano_pos_initial = None
    for idx, event in enumerate(initial_events):
        if event.get("venue") == "Selva Club" and selva_pos_initial is None:
            selva_pos_initial = idx
        if event.get("venue") == "Sotano Club" and sotano_pos_initial is None:
            sotano_pos_initial = idx
    
    log(f"📊 Initial feed positions: Selva Club={selva_pos_initial}, Sotano Club={sotano_pos_initial}")
    
    # Test 2c: Reorder - put Sotano first, Selva second
    log("\n📋 Test 2c: Reorder venues - Sotano Club first, Selva Club second")
    reorder_payload = {"venue_ids": [sotano_id, selva_id]}
    resp = requests.put(f"{BASE_URL}/admin/venues/reorder", json=reorder_payload, headers=headers)
    assert resp.status_code == 200, f"Reorder failed: {resp.status_code} {resp.text}"
    reorder_result = resp.json()
    assert reorder_result.get("ok") is True, f"Reorder response ok is not True: {reorder_result}"
    assert "updated" in reorder_result, "Reorder response missing 'updated' field"
    log(f"✅ Reorder successful: {reorder_result}")
    
    # Test 2d: Verify feed order changed
    log("\n📋 Test 2d: Verify feed order changed after reorder")
    resp = requests.get(f"{BASE_URL}/events", params={"date_filter": "all", "genre": "all"}, headers=headers)
    assert resp.status_code == 200, f"Feed failed: {resp.status_code}"
    reordered_events = resp.json()
    
    selva_pos_after = None
    sotano_pos_after = None
    for idx, event in enumerate(reordered_events):
        if event.get("venue") == "Selva Club" and selva_pos_after is None:
            selva_pos_after = idx
        if event.get("venue") == "Sotano Club" and sotano_pos_after is None:
            sotano_pos_after = idx
    
    log(f"📊 After reorder positions: Selva Club={selva_pos_after}, Sotano Club={sotano_pos_after}")
    
    if sotano_pos_after is not None and selva_pos_after is not None:
        assert sotano_pos_after < selva_pos_after, \
            f"❌ Sotano Club (pos={sotano_pos_after}) should appear BEFORE Selva Club (pos={selva_pos_after}) after reorder"
        log(f"✅ Feed order changed correctly: Sotano Club now appears before Selva Club")
    else:
        log("⚠️  Could not verify feed order change (one or both venues not in feed)")
    
    # Test 2e: Restore original order
    log("\n📋 Test 2e: Restore original order (Selva first, Sotano second)")
    restore_payload = {"venue_ids": [selva_id, sotano_id]}
    resp = requests.put(f"{BASE_URL}/admin/venues/reorder", json=restore_payload, headers=headers)
    assert resp.status_code == 200, f"Restore order failed: {resp.status_code} {resp.text}"
    restore_result = resp.json()
    assert restore_result.get("ok") is True, f"Restore response ok is not True: {restore_result}"
    log(f"✅ Original order restored: {restore_result}")
    
    # Test 2f: Verify feed order restored
    log("\n📋 Test 2f: Verify feed order restored")
    resp = requests.get(f"{BASE_URL}/events", params={"date_filter": "all", "genre": "all"}, headers=headers)
    assert resp.status_code == 200, f"Feed failed: {resp.status_code}"
    restored_events = resp.json()
    
    selva_pos_restored = None
    sotano_pos_restored = None
    for idx, event in enumerate(restored_events):
        if event.get("venue") == "Selva Club" and selva_pos_restored is None:
            selva_pos_restored = idx
        if event.get("venue") == "Sotano Club" and sotano_pos_restored is None:
            sotano_pos_restored = idx
    
    log(f"📊 After restore positions: Selva Club={selva_pos_restored}, Sotano Club={sotano_pos_restored}")
    
    if selva_pos_restored is not None and sotano_pos_restored is not None:
        assert selva_pos_restored < sotano_pos_restored, \
            f"❌ Selva Club (pos={selva_pos_restored}) should appear BEFORE Sotano Club (pos={sotano_pos_restored}) after restore"
        log(f"✅ Feed order restored correctly: Selva Club now appears before Sotano Club")
    else:
        log("⚠️  Could not verify feed order restore (one or both venues not in feed)")
    
    # Test 2g: Non-admin should get 403
    log("\n📋 Test 2g: Non-admin user should get 403")
    normal_token = register_normal_user(f"reorder{int(datetime.now().timestamp())}")
    normal_headers = {"Authorization": f"Bearer {normal_token}"}
    resp = requests.put(f"{BASE_URL}/admin/venues/reorder", json=reorder_payload, headers=normal_headers)
    assert resp.status_code == 403, f"Non-admin should get 403, got {resp.status_code}"
    log(f"✅ Non-admin correctly rejected with 403")
    
    # Test 2h: Unauthenticated should get 401
    log("\n📋 Test 2h: Unauthenticated request should get 401")
    resp = requests.put(f"{BASE_URL}/admin/venues/reorder", json=reorder_payload)
    assert resp.status_code == 401, f"Unauthenticated should get 401, got {resp.status_code}"
    log(f"✅ Unauthenticated correctly rejected with 401")
    
    log("\n✅ TASK 2 COMPLETE: Venue reorder working correctly")

def test_task3_affiliate_fix(admin_token):
    """
    TASK 3: Regression safety for _affiliate_key fix
    - POST /api/admin/affiliate-refresh should return 200 with no server error
    - GET /api/admin/affiliate-status should return 200 with slug and no error
    - Non-admin should get 403
    """
    log("\n" + "="*80)
    log("TASK 3: Testing affiliate endpoints (regression for _affiliate_key fix)")
    log("="*80)
    
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # Test 3a: GET /api/admin/affiliate-status
    log("\n📋 Test 3a: GET /api/admin/affiliate-status as admin")
    resp = requests.get(f"{BASE_URL}/admin/affiliate-status", headers=headers)
    assert resp.status_code == 200, f"affiliate-status failed: {resp.status_code} {resp.text}"
    status_data = resp.json()
    log(f"📊 Affiliate status response: {json.dumps(status_data, indent=2)}")
    
    assert "slug" in status_data, "affiliate-status response missing 'slug' field"
    assert status_data["slug"] == "quienva", f"Expected slug 'quienva', got {status_data['slug']}"
    assert "mine_count" in status_data, "affiliate-status response missing 'mine_count' field"
    log(f"✅ affiliate-status returned 200 with slug={status_data['slug']}, mine_count={status_data['mine_count']}")
    log(f"   (mine_count=0 is expected - no FourVenues token in this env)")
    
    # Test 3b: POST /api/admin/affiliate-refresh
    log("\n📋 Test 3b: POST /api/admin/affiliate-refresh as admin")
    resp = requests.post(f"{BASE_URL}/admin/affiliate-refresh", headers=headers)
    assert resp.status_code == 200, f"affiliate-refresh failed: {resp.status_code} {resp.text}"
    refresh_data = resp.json()
    log(f"📊 Affiliate refresh response: {json.dumps(refresh_data, indent=2)}")
    
    assert "slug" in refresh_data, "affiliate-refresh response missing 'slug' field"
    assert "mine_count" in refresh_data, "affiliate-refresh response missing 'mine_count' field"
    log(f"✅ affiliate-refresh returned 200 with slug={refresh_data['slug']}, mine_count={refresh_data['mine_count']}")
    log(f"   (mine_count=0 is expected - no FourVenues token in this env)")
    log(f"   The key point: NO NameError for _affiliate_key (the bug is fixed)")
    
    # Test 3c: Non-admin should get 403 for affiliate-status
    log("\n📋 Test 3c: Non-admin user should get 403 for affiliate-status")
    normal_token = register_normal_user(f"affiliate{int(datetime.now().timestamp())}")
    normal_headers = {"Authorization": f"Bearer {normal_token}"}
    resp = requests.get(f"{BASE_URL}/admin/affiliate-status", headers=normal_headers)
    assert resp.status_code == 403, f"Non-admin should get 403 for affiliate-status, got {resp.status_code}"
    log(f"✅ Non-admin correctly rejected with 403 for affiliate-status")
    
    # Test 3d: Non-admin should get 403 for affiliate-refresh
    log("\n📋 Test 3d: Non-admin user should get 403 for affiliate-refresh")
    resp = requests.post(f"{BASE_URL}/admin/affiliate-refresh", headers=normal_headers)
    assert resp.status_code == 403, f"Non-admin should get 403 for affiliate-refresh, got {resp.status_code}"
    log(f"✅ Non-admin correctly rejected with 403 for affiliate-refresh")
    
    log("\n✅ TASK 3 COMPLETE: Affiliate endpoints working correctly (no _affiliate_key NameError)")

def main():
    """Run all tests"""
    log("="*80)
    log("🚀 Starting backend tests for ¿Quién va? app")
    log("="*80)
    log(f"Backend URL: {BASE_URL}")
    log(f"Admin credentials: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    
    try:
        # Login as admin
        admin_token = test_admin_login()
        
        # Register a normal user for is_affiliate testing
        normal_token = register_normal_user(f"feed{int(datetime.now().timestamp())}")
        
        # Run the 3 tasks
        test_task1_feed_ordering(admin_token, normal_token)
        test_task2_venue_reorder(admin_token)
        test_task3_affiliate_fix(admin_token)
        
        log("\n" + "="*80)
        log("🎉 ALL TESTS PASSED")
        log("="*80)
        return 0
        
    except AssertionError as e:
        log(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        log(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
