#!/usr/bin/env python3
"""
Test for admin users endpoint friends count bug fix.

BUG: GET /api/admin/users returned _stats.friends = 0 for ALL users because it counted
friendships using non-existent fields (from_user_id/to_user_id). The friendships collection
actually uses requester_id and addressee_id with status: "accepted".

FIX: Changed the count to:
friends = await db.friendships.count_documents({
    "status": "accepted",
    "$or": [{"requester_id": u["user_id"]}, {"addressee_id": u["user_id"]}],
})

TEST PLAN:
1. Login as admin
2. Create 2-3 test users
3. Establish an ACCEPTED friendship between two users
4. Call GET /api/admin/users and verify _stats.friends >= 1 for the two friends
5. Verify other _stats fields still work (going, attended, groups, referred, invites_sent)
6. Verify admin auth is required (401/403 without admin token)
"""

import requests
import time
import random

# Backend URL from frontend/.env
BACKEND_URL = "https://full-stack-nights.preview.emergentagent.com/api"

# Admin credentials from /app/memory/test_credentials.md
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

def log(msg):
    print(f"[TEST] {msg}")

def test_admin_users_friends_count():
    """Test that _stats.friends correctly counts accepted friendships"""
    
    log("=" * 80)
    log("TEST: Admin Users Endpoint - Friends Count Bug Fix")
    log("=" * 80)
    
    # Generate unique test data
    timestamp = int(time.time())
    test_user1_email = f"testuser1_{timestamp}@test.com"
    test_user2_email = f"testuser2_{timestamp}@test.com"
    test_user3_email = f"testuser3_{timestamp}@test.com"
    
    # =========================================================================
    # STEP 1: Login as admin
    # =========================================================================
    log("\n[STEP 1] Login as admin...")
    resp = requests.post(f"{BACKEND_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.status_code} {resp.text}"
    admin_token = resp.cookies.get("session_token")
    assert admin_token, "No session_token cookie returned for admin"
    log(f"✅ Admin login successful, token: {admin_token[:20]}...")
    
    admin_headers = {"Cookie": f"session_token={admin_token}"}
    
    # =========================================================================
    # STEP 2: Create 3 test users
    # =========================================================================
    log("\n[STEP 2] Creating 3 test users...")
    
    # User 1
    user1_data = {
        "email": test_user1_email,
        "password": "TestPass123!",
        "name": f"Test User One {timestamp}",
        "username": f"testuser1_{timestamp}",
        "city": "Ibiza",
        "birthdate": "1995-01-15"  # Adult user
    }
    resp = requests.post(f"{BACKEND_URL}/auth/register", json=user1_data)
    assert resp.status_code == 200, f"User 1 registration failed: {resp.status_code} {resp.text}"
    user1_token = resp.cookies.get("session_token")
    assert user1_token, "No session_token cookie for user 1"
    user1_id = resp.json().get("user", {}).get("user_id")
    assert user1_id, "No user_id returned for user 1"
    log(f"✅ User 1 created: {user1_id} ({test_user1_email})")
    
    # User 2
    user2_data = {
        "email": test_user2_email,
        "password": "TestPass123!",
        "name": f"Test User Two {timestamp}",
        "username": f"testuser2_{timestamp}",
        "city": "Ibiza",
        "birthdate": "1992-06-20"  # Adult user
    }
    resp = requests.post(f"{BACKEND_URL}/auth/register", json=user2_data)
    assert resp.status_code == 200, f"User 2 registration failed: {resp.status_code} {resp.text}"
    user2_token = resp.cookies.get("session_token")
    assert user2_token, "No session_token cookie for user 2"
    user2_id = resp.json().get("user", {}).get("user_id")
    assert user2_id, "No user_id returned for user 2"
    log(f"✅ User 2 created: {user2_id} ({test_user2_email})")
    
    # User 3 (will not have friends)
    user3_data = {
        "email": test_user3_email,
        "password": "TestPass123!",
        "name": f"Test User Three {timestamp}",
        "username": f"testuser3_{timestamp}",
        "city": "Madrid",
        "birthdate": "1998-03-10"  # Adult user
    }
    resp = requests.post(f"{BACKEND_URL}/auth/register", json=user3_data)
    assert resp.status_code == 200, f"User 3 registration failed: {resp.status_code} {resp.text}"
    user3_token = resp.cookies.get("session_token")
    assert user3_token, "No session_token cookie for user 3"
    user3_id = resp.json().get("user", {}).get("user_id")
    assert user3_id, "No user_id returned for user 3"
    log(f"✅ User 3 created: {user3_id} ({test_user3_email})")
    
    user1_headers = {"Cookie": f"session_token={user1_token}"}
    user2_headers = {"Cookie": f"session_token={user2_token}"}
    user3_headers = {"Cookie": f"session_token={user3_token}"}
    
    # =========================================================================
    # STEP 3: Establish an ACCEPTED friendship between User 1 and User 2
    # =========================================================================
    log("\n[STEP 3] Establishing friendship between User 1 and User 2...")
    
    # User 1 sends friend request to User 2
    log("  → User 1 sends friend request to User 2...")
    resp = requests.post(f"{BACKEND_URL}/friends/request", 
                        json={"user_id": user2_id},
                        headers=user1_headers)
    assert resp.status_code == 200, f"Friend request failed: {resp.status_code} {resp.text}"
    request_data = resp.json()
    assert request_data.get("status") in ["pending", "accepted"], f"Unexpected status: {request_data}"
    request_id = request_data.get("request_id")
    log(f"  ✅ Friend request sent, status: {request_data.get('status')}, request_id: {request_id}")
    
    # User 2 accepts the friend request
    if request_data.get("status") == "pending":
        log("  → User 2 accepts the friend request...")
        resp = requests.post(f"{BACKEND_URL}/friends/respond",
                            json={"request_id": request_id, "accept": True},
                            headers=user2_headers)
        assert resp.status_code == 200, f"Friend accept failed: {resp.status_code} {resp.text}"
        accept_data = resp.json()
        assert accept_data.get("status") == "accepted", f"Expected 'accepted', got: {accept_data}"
        log(f"  ✅ Friend request accepted, status: {accept_data.get('status')}")
    else:
        log("  ✅ Friendship already accepted (auto-accepted)")
    
    # =========================================================================
    # STEP 4: Call GET /api/admin/users and verify _stats.friends
    # =========================================================================
    log("\n[STEP 4] Calling GET /api/admin/users to verify _stats.friends...")
    
    resp = requests.get(f"{BACKEND_URL}/admin/users", headers=admin_headers)
    assert resp.status_code == 200, f"Admin users endpoint failed: {resp.status_code} {resp.text}"
    users = resp.json()
    assert isinstance(users, list), f"Expected list, got: {type(users)}"
    log(f"✅ GET /api/admin/users returned {len(users)} users")
    
    # Find our test users in the response
    user1_data_response = None
    user2_data_response = None
    user3_data_response = None
    
    for u in users:
        if u.get("user_id") == user1_id:
            user1_data_response = u
        elif u.get("user_id") == user2_id:
            user2_data_response = u
        elif u.get("user_id") == user3_id:
            user3_data_response = u
    
    assert user1_data_response, f"User 1 ({user1_id}) not found in admin/users response"
    assert user2_data_response, f"User 2 ({user2_id}) not found in admin/users response"
    assert user3_data_response, f"User 3 ({user3_id}) not found in admin/users response"
    
    log("\n  Checking _stats for User 1 (should have 1 friend):")
    user1_stats = user1_data_response.get("_stats", {})
    log(f"    _stats: {user1_stats}")
    assert "_stats" in user1_data_response, "User 1 missing _stats field"
    assert "friends" in user1_stats, "User 1 _stats missing 'friends' field"
    assert user1_stats["friends"] >= 1, f"❌ BUG NOT FIXED: User 1 _stats.friends = {user1_stats['friends']}, expected >= 1"
    log(f"  ✅ User 1 _stats.friends = {user1_stats['friends']} (CORRECT, >= 1)")
    
    log("\n  Checking _stats for User 2 (should have 1 friend):")
    user2_stats = user2_data_response.get("_stats", {})
    log(f"    _stats: {user2_stats}")
    assert "_stats" in user2_data_response, "User 2 missing _stats field"
    assert "friends" in user2_stats, "User 2 _stats missing 'friends' field"
    assert user2_stats["friends"] >= 1, f"❌ BUG NOT FIXED: User 2 _stats.friends = {user2_stats['friends']}, expected >= 1"
    log(f"  ✅ User 2 _stats.friends = {user2_stats['friends']} (CORRECT, >= 1)")
    
    log("\n  Checking _stats for User 3 (should have 0 friends):")
    user3_stats = user3_data_response.get("_stats", {})
    log(f"    _stats: {user3_stats}")
    assert "_stats" in user3_data_response, "User 3 missing _stats field"
    assert "friends" in user3_stats, "User 3 _stats missing 'friends' field"
    assert user3_stats["friends"] == 0, f"User 3 should have 0 friends, got: {user3_stats['friends']}"
    log(f"  ✅ User 3 _stats.friends = {user3_stats['friends']} (CORRECT, = 0)")
    
    # =========================================================================
    # STEP 5: Verify other _stats fields are present and valid
    # =========================================================================
    log("\n[STEP 5] Verifying other _stats fields...")
    
    required_stats_fields = ["going", "attended", "groups", "referred", "invites_sent"]
    
    for field in required_stats_fields:
        assert field in user1_stats, f"User 1 _stats missing '{field}' field"
        assert isinstance(user1_stats[field], int), f"User 1 _stats.{field} is not an int: {type(user1_stats[field])}"
        log(f"  ✅ User 1 _stats.{field} = {user1_stats[field]} (present and valid)")
    
    for field in required_stats_fields:
        assert field in user2_stats, f"User 2 _stats missing '{field}' field"
        assert isinstance(user2_stats[field], int), f"User 2 _stats.{field} is not an int: {type(user2_stats[field])}"
        log(f"  ✅ User 2 _stats.{field} = {user2_stats[field]} (present and valid)")
    
    # =========================================================================
    # STEP 6: Verify admin auth is required
    # =========================================================================
    log("\n[STEP 6] Verifying admin authorization...")
    
    # Test without auth (should be 401)
    log("  → Testing GET /api/admin/users without auth...")
    resp = requests.get(f"{BACKEND_URL}/admin/users")
    assert resp.status_code == 401, f"Expected 401 without auth, got: {resp.status_code}"
    log(f"  ✅ Without auth: {resp.status_code} (CORRECT)")
    
    # Test with non-admin user (should be 403)
    log("  → Testing GET /api/admin/users as non-admin user...")
    resp = requests.get(f"{BACKEND_URL}/admin/users", headers=user1_headers)
    assert resp.status_code == 403, f"Expected 403 for non-admin, got: {resp.status_code}"
    log(f"  ✅ As non-admin user: {resp.status_code} (CORRECT)")
    
    # =========================================================================
    # CLEANUP: Delete test users (optional, but good practice)
    # =========================================================================
    log("\n[CLEANUP] Cleaning up test users...")
    
    # Note: There's no DELETE /api/users/{id} endpoint in the API, so we'll leave
    # the test users in the database. In a real scenario, you'd want to clean up.
    # For now, we'll just log that cleanup is skipped.
    log("  ⚠️  No user deletion endpoint available, test users will remain in DB")
    log(f"  Test users created: {user1_id}, {user2_id}, {user3_id}")
    
    # =========================================================================
    # FINAL SUMMARY
    # =========================================================================
    log("\n" + "=" * 80)
    log("🎉 ALL TESTS PASSED - BUG FIX VERIFIED")
    log("=" * 80)
    log("\nSUMMARY:")
    log("✅ Admin login successful")
    log("✅ Created 3 test users")
    log("✅ Established accepted friendship between User 1 and User 2")
    log("✅ GET /api/admin/users returns correct _stats.friends count:")
    log(f"   - User 1: {user1_stats['friends']} friend(s) (expected >= 1) ✓")
    log(f"   - User 2: {user2_stats['friends']} friend(s) (expected >= 1) ✓")
    log(f"   - User 3: {user3_stats['friends']} friend(s) (expected = 0) ✓")
    log("✅ All other _stats fields present and valid (going, attended, groups, referred, invites_sent)")
    log("✅ Admin authorization working (401 without auth, 403 for non-admin)")
    log("\nCONCLUSION:")
    log("The bug fix is working correctly. The admin users endpoint now properly counts")
    log("accepted friendships using the correct fields (requester_id/addressee_id with")
    log("status='accepted') instead of the non-existent from_user_id/to_user_id fields.")
    log("=" * 80)

if __name__ == "__main__":
    try:
        test_admin_users_friends_count()
    except AssertionError as e:
        log(f"\n❌ TEST FAILED: {e}")
        exit(1)
    except Exception as e:
        log(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
