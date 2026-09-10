#!/usr/bin/env python3
"""
Test notification behavior change: new-party alerts (notif_prefs.new_event) are now
ON by default for EVERYONE (opt-out), while STILL being batched per club.

This script imports the backend module (SAFE — importing does NOT start uvicorn/scheduler).
Use PYTHONPATH=/app/backend, run from /app/backend, MongoDB is local (server.db).

Assertions:
1) OPT-OUT DEFAULT (single event): Users without notif_prefs field and users with
   notif_prefs.new_event=True get notifications, while users with notif_prefs.new_event=False do NOT
2) BATCH still works with opt-out audience: Batching still works correctly with the opt-out model
3) API default: POST /api/auth/register creates users with new_event=true by default
"""
import sys
import os
import asyncio
import uuid
from datetime import datetime, timezone

# Set up Python path to import server module
sys.path.insert(0, '/app/backend')
os.chdir('/app/backend')

# Import server module (does NOT start uvicorn/scheduler)
import server

# Test results
results = []

def log_result(test_name: str, passed: bool, message: str):
    """Log a test result"""
    status = "✅ PASS" if passed else "❌ FAIL"
    results.append({"test": test_name, "passed": passed, "message": message})
    print(f"{status}: {test_name}")
    print(f"  {message}")
    print()

async def cleanup_test_data(user_ids: list, event_ids: list):
    """Clean up test data"""
    try:
        if user_ids:
            await server.db.users.delete_many({"user_id": {"$in": user_ids}})
            await server.db.notifications.delete_many({"user_id": {"$in": user_ids}})
        if event_ids:
            await server.db.events.delete_many({"id": {"$in": event_ids}})
        print(f"Cleaned up {len(user_ids)} test users and {len(event_ids)} test events")
    except Exception as e:
        print(f"Cleanup warning: {e}")

async def test_assertion_1_opt_out_default():
    """
    ASSERTION 1: OPT-OUT DEFAULT (single event)
    
    In server.db.users upsert 3 users in city "Barcelona":
    - user "vb_noprefs" with NO notif_prefs field (make sure to $unset notif_prefs)
    - user "vb_off" with notif_prefs = {"new_event": False}
    - user "vb_on" with notif_prefs = {"new_event": True}
    
    Build a fake event dict {id, name, venue, city:"Barcelona", date}.
    Delete existing type=="new_event" notifications for these 3, then
    `await server._notify_new_event_city(event)`.
    
    ASSERT: vb_noprefs has 1 notification, vb_on has 1 notification, vb_off has 0.
    (i.e. ON by default; only explicit False is excluded.)
    """
    print("=" * 80)
    print("ASSERTION 1: OPT-OUT DEFAULT (single event)")
    print("=" * 80)
    
    user_ids = []
    event_ids = []
    
    try:
        # Create 3 test users in Barcelona
        uid_noprefs = f"vb_noprefs_{uuid.uuid4().hex[:8]}"
        uid_off = f"vb_off_{uuid.uuid4().hex[:8]}"
        uid_on = f"vb_on_{uuid.uuid4().hex[:8]}"
        user_ids = [uid_noprefs, uid_off, uid_on]
        
        # User 1: NO notif_prefs field (use $unset to ensure it's removed)
        await server.db.users.update_one(
            {"user_id": uid_noprefs},
            {
                "$set": {
                    "user_id": uid_noprefs,
                    "email": f"{uid_noprefs}@test.com",
                    "name": "User No Prefs",
                    "username": uid_noprefs,
                    "city": "Barcelona",
                    "role": "user",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                "$unset": {"notif_prefs": ""}  # Explicitly remove notif_prefs
            },
            upsert=True
        )
        
        # User 2: notif_prefs.new_event = False (opted out)
        await server.db.users.update_one(
            {"user_id": uid_off},
            {
                "$set": {
                    "user_id": uid_off,
                    "email": f"{uid_off}@test.com",
                    "name": "User Off",
                    "username": uid_off,
                    "city": "Barcelona",
                    "role": "user",
                    "notif_prefs": {"new_event": False},
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            },
            upsert=True
        )
        
        # User 3: notif_prefs.new_event = True (explicitly opted in)
        await server.db.users.update_one(
            {"user_id": uid_on},
            {
                "$set": {
                    "user_id": uid_on,
                    "email": f"{uid_on}@test.com",
                    "name": "User On",
                    "username": uid_on,
                    "city": "Barcelona",
                    "role": "user",
                    "notif_prefs": {"new_event": True},
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            },
            upsert=True
        )
        
        # Verify users were created correctly
        u_noprefs = await server.db.users.find_one({"user_id": uid_noprefs}, {"_id": 0})
        u_off = await server.db.users.find_one({"user_id": uid_off}, {"_id": 0})
        u_on = await server.db.users.find_one({"user_id": uid_on}, {"_id": 0})
        
        assert "notif_prefs" not in u_noprefs, "vb_noprefs should NOT have notif_prefs field"
        assert u_off.get("notif_prefs", {}).get("new_event") is False, "vb_off should have new_event=False"
        assert u_on.get("notif_prefs", {}).get("new_event") is True, "vb_on should have new_event=True"
        
        print(f"✓ Created 3 test users in Barcelona:")
        print(f"  - {uid_noprefs}: NO notif_prefs field")
        print(f"  - {uid_off}: notif_prefs.new_event = False")
        print(f"  - {uid_on}: notif_prefs.new_event = True")
        print()
        
        # Create a fake event in Barcelona
        event_id = f"test_event_{uuid.uuid4().hex[:8]}"
        event_ids.append(event_id)
        event = {
            "id": event_id,
            "name": "Test Party Barcelona",
            "venue": "Test Venue BCN",
            "city": "Barcelona",
            "date": "2026-12-31"
        }
        
        # Delete existing new_event notifications for these users
        await server.db.notifications.delete_many({
            "user_id": {"$in": user_ids},
            "type": "new_event"
        })
        print(f"✓ Deleted existing new_event notifications for test users")
        print()
        
        # Call _notify_new_event_city
        print(f"Calling _notify_new_event_city(event)...")
        count = await server._notify_new_event_city(event)
        print(f"✓ _notify_new_event_city returned count={count}")
        print()
        
        # Count notifications for each user
        count_noprefs = await server.db.notifications.count_documents({
            "user_id": uid_noprefs,
            "type": "new_event"
        })
        count_off = await server.db.notifications.count_documents({
            "user_id": uid_off,
            "type": "new_event"
        })
        count_on = await server.db.notifications.count_documents({
            "user_id": uid_on,
            "type": "new_event"
        })
        
        print(f"Notification counts:")
        print(f"  - vb_noprefs: {count_noprefs} (expected: 1)")
        print(f"  - vb_off: {count_off} (expected: 0)")
        print(f"  - vb_on: {count_on} (expected: 1)")
        print()
        
        # Assertions
        passed = True
        messages = []
        
        if count_noprefs == 1:
            messages.append("✓ vb_noprefs has 1 notification (ON by default)")
        else:
            messages.append(f"✗ vb_noprefs has {count_noprefs} notifications (expected 1)")
            passed = False
        
        if count_on == 1:
            messages.append("✓ vb_on has 1 notification (explicitly ON)")
        else:
            messages.append(f"✗ vb_on has {count_on} notifications (expected 1)")
            passed = False
        
        if count_off == 0:
            messages.append("✓ vb_off has 0 notifications (explicitly OFF)")
        else:
            messages.append(f"✗ vb_off has {count_off} notifications (expected 0)")
            passed = False
        
        log_result(
            "ASSERTION 1: OPT-OUT DEFAULT (single event)",
            passed,
            "\n".join(messages)
        )
        
    except Exception as e:
        log_result(
            "ASSERTION 1: OPT-OUT DEFAULT (single event)",
            False,
            f"Exception: {e}"
        )
        import traceback
        traceback.print_exc()
    finally:
        await cleanup_test_data(user_ids, event_ids)

async def test_assertion_2_batch_opt_out():
    """
    ASSERTION 2: BATCH still works with opt-out audience
    
    Clear the 3 users' new_event notifications, then
    `await server._notify_new_events_batch({"name":"Club B","city":"Barcelona"}, events)`
    with a list of 9 fake events (Barcelona).
    
    ASSERT: vb_noprefs and vb_on each have EXACTLY 1 notification (NOT 9) whose message
    contains "9 fiestas nuevas"; vb_off has 0.
    """
    print("=" * 80)
    print("ASSERTION 2: BATCH still works with opt-out audience")
    print("=" * 80)
    
    user_ids = []
    event_ids = []
    
    try:
        # Create 3 test users in Barcelona
        uid_noprefs = f"vb_noprefs_{uuid.uuid4().hex[:8]}"
        uid_off = f"vb_off_{uuid.uuid4().hex[:8]}"
        uid_on = f"vb_on_{uuid.uuid4().hex[:8]}"
        user_ids = [uid_noprefs, uid_off, uid_on]
        
        # User 1: NO notif_prefs field
        await server.db.users.update_one(
            {"user_id": uid_noprefs},
            {
                "$set": {
                    "user_id": uid_noprefs,
                    "email": f"{uid_noprefs}@test.com",
                    "name": "User No Prefs",
                    "username": uid_noprefs,
                    "city": "Barcelona",
                    "role": "user",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                "$unset": {"notif_prefs": ""}
            },
            upsert=True
        )
        
        # User 2: notif_prefs.new_event = False
        await server.db.users.update_one(
            {"user_id": uid_off},
            {
                "$set": {
                    "user_id": uid_off,
                    "email": f"{uid_off}@test.com",
                    "name": "User Off",
                    "username": uid_off,
                    "city": "Barcelona",
                    "role": "user",
                    "notif_prefs": {"new_event": False},
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            },
            upsert=True
        )
        
        # User 3: notif_prefs.new_event = True
        await server.db.users.update_one(
            {"user_id": uid_on},
            {
                "$set": {
                    "user_id": uid_on,
                    "email": f"{uid_on}@test.com",
                    "name": "User On",
                    "username": uid_on,
                    "city": "Barcelona",
                    "role": "user",
                    "notif_prefs": {"new_event": True},
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            },
            upsert=True
        )
        
        print(f"✓ Created 3 test users in Barcelona")
        print()
        
        # Delete existing new_event notifications for these users
        await server.db.notifications.delete_many({
            "user_id": {"$in": user_ids},
            "type": "new_event"
        })
        print(f"✓ Cleared existing new_event notifications for test users")
        print()
        
        # Create 9 fake events in Barcelona
        events = []
        for i in range(9):
            event_id = f"test_event_{uuid.uuid4().hex[:8]}"
            event_ids.append(event_id)
            events.append({
                "id": event_id,
                "name": f"Test Party {i+1}",
                "venue": "Club B",
                "city": "Barcelona",
                "date": "2026-12-31"
            })
        
        print(f"✓ Created 9 fake events in Barcelona")
        print()
        
        # Call _notify_new_events_batch
        venue = {"name": "Club B", "city": "Barcelona"}
        print(f"Calling _notify_new_events_batch(venue, events)...")
        count = await server._notify_new_events_batch(venue, events)
        print(f"✓ _notify_new_events_batch returned count={count}")
        print()
        
        # Count notifications for each user
        count_noprefs = await server.db.notifications.count_documents({
            "user_id": uid_noprefs,
            "type": "new_event"
        })
        count_off = await server.db.notifications.count_documents({
            "user_id": uid_off,
            "type": "new_event"
        })
        count_on = await server.db.notifications.count_documents({
            "user_id": uid_on,
            "type": "new_event"
        })
        
        # Get notification messages
        notif_noprefs = await server.db.notifications.find_one({
            "user_id": uid_noprefs,
            "type": "new_event"
        }, {"_id": 0, "message": 1})
        notif_on = await server.db.notifications.find_one({
            "user_id": uid_on,
            "type": "new_event"
        }, {"_id": 0, "message": 1})
        
        msg_noprefs = notif_noprefs.get("message", "") if notif_noprefs else ""
        msg_on = notif_on.get("message", "") if notif_on else ""
        
        print(f"Notification counts:")
        print(f"  - vb_noprefs: {count_noprefs} (expected: 1)")
        print(f"    Message: {msg_noprefs}")
        print(f"  - vb_off: {count_off} (expected: 0)")
        print(f"  - vb_on: {count_on} (expected: 1)")
        print(f"    Message: {msg_on}")
        print()
        
        # Assertions
        passed = True
        messages = []
        
        if count_noprefs == 1:
            messages.append("✓ vb_noprefs has EXACTLY 1 notification (batched)")
        else:
            messages.append(f"✗ vb_noprefs has {count_noprefs} notifications (expected 1)")
            passed = False
        
        if "9 fiestas nuevas" in msg_noprefs:
            messages.append("✓ vb_noprefs message contains '9 fiestas nuevas'")
        else:
            messages.append(f"✗ vb_noprefs message does NOT contain '9 fiestas nuevas': {msg_noprefs}")
            passed = False
        
        if count_on == 1:
            messages.append("✓ vb_on has EXACTLY 1 notification (batched)")
        else:
            messages.append(f"✗ vb_on has {count_on} notifications (expected 1)")
            passed = False
        
        if "9 fiestas nuevas" in msg_on:
            messages.append("✓ vb_on message contains '9 fiestas nuevas'")
        else:
            messages.append(f"✗ vb_on message does NOT contain '9 fiestas nuevas': {msg_on}")
            passed = False
        
        if count_off == 0:
            messages.append("✓ vb_off has 0 notifications (opted out)")
        else:
            messages.append(f"✗ vb_off has {count_off} notifications (expected 0)")
            passed = False
        
        log_result(
            "ASSERTION 2: BATCH still works with opt-out audience",
            passed,
            "\n".join(messages)
        )
        
    except Exception as e:
        log_result(
            "ASSERTION 2: BATCH still works with opt-out audience",
            False,
            f"Exception: {e}"
        )
        import traceback
        traceback.print_exc()
    finally:
        await cleanup_test_data(user_ids, event_ids)

async def test_assertion_3_api_default():
    """
    ASSERTION 3: API default
    
    POST /api/auth/register a fresh unique adult user (city "Barcelona"),
    grab the token, then GET /api/me/notif-prefs and ASSERT prefs.new_event == true
    (ON by default).
    """
    print("=" * 80)
    print("ASSERTION 3: API default")
    print("=" * 80)
    
    user_ids = []
    
    try:
        import httpx
        
        # Get backend URL from environment
        backend_url = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001")
        if not backend_url.endswith("/api"):
            backend_url = f"{backend_url}/api"
        
        print(f"Using backend URL: {backend_url}")
        print()
        
        # Create a unique test user
        unique_id = uuid.uuid4().hex[:8]
        email = f"test_user_{unique_id}@test.com"
        password = "TestPass123!"
        username = f"testuser_{unique_id}"
        
        # Register the user
        async with httpx.AsyncClient() as client:
            register_data = {
                "email": email,
                "password": password,
                "name": "Test User",
                "username": username,
                "city": "Barcelona",
                "birthdate": "1990-01-01"  # Adult user
            }
            
            print(f"Registering user: {email}")
            resp = await client.post(f"{backend_url}/auth/register", json=register_data)
            
            if resp.status_code != 200:
                raise Exception(f"Registration failed: {resp.status_code} {resp.text}")
            
            data = resp.json()
            token = data.get("token")
            user_id = data.get("user", {}).get("user_id")
            user_ids.append(user_id)
            
            print(f"✓ User registered successfully: {user_id}")
            print(f"✓ Token received: {token[:20]}...")
            print()
            
            # Get notification preferences
            print(f"Getting notification preferences...")
            resp = await client.get(
                f"{backend_url}/me/notif-prefs",
                headers={"Authorization": f"Bearer {token}"}
            )
            
            if resp.status_code != 200:
                raise Exception(f"Get notif-prefs failed: {resp.status_code} {resp.text}")
            
            data = resp.json()
            prefs = data.get("prefs", {})
            new_event_pref = prefs.get("new_event")
            
            print(f"✓ Notification preferences retrieved:")
            print(f"  prefs.new_event = {new_event_pref}")
            print()
            
            # Assertion
            passed = new_event_pref is True
            
            if passed:
                message = "✓ prefs.new_event == true (ON by default)"
            else:
                message = f"✗ prefs.new_event == {new_event_pref} (expected true)"
            
            log_result(
                "ASSERTION 3: API default",
                passed,
                message
            )
        
    except Exception as e:
        log_result(
            "ASSERTION 3: API default",
            False,
            f"Exception: {e}"
        )
        import traceback
        traceback.print_exc()
    finally:
        await cleanup_test_data(user_ids, [])

async def main():
    """Run all tests"""
    print("\n" + "=" * 80)
    print("NOTIFICATION OPT-OUT BEHAVIOR VERIFICATION")
    print("=" * 80)
    print()
    
    # Run all assertions
    await test_assertion_1_opt_out_default()
    await test_assertion_2_batch_opt_out()
    await test_assertion_3_api_default()
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed
    
    print(f"\nTotal tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print()
    
    for r in results:
        status = "✅ PASS" if r["passed"] else "❌ FAIL"
        print(f"{status}: {r['test']}")
    
    print()
    
    if failed == 0:
        print("🎉 ALL TESTS PASSED! 🎉")
        return 0
    else:
        print(f"⚠️  {failed} TEST(S) FAILED")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
