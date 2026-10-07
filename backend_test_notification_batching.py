#!/usr/bin/env python3
"""
Test script for notification batching bug fix.
Verifies that _notify_new_events_batch sends ONE notification per user per club,
not one per event (which was causing push spam).
"""
import sys
import os
import asyncio
import uuid
from datetime import datetime, timedelta

# Set PYTHONPATH to import server module
sys.path.insert(0, '/app/backend')
os.chdir('/app/backend')

import server

# Test configuration
TEST_CITY = "Madrid"
TEST_CLUB_NAME = "Club Test"
BACKEND_URL = "https://voting-party-planner.preview.emergentagent.com"

async def cleanup_test_data(user_ids):
    """Remove test users and their notifications"""
    print(f"\n🧹 Cleaning up test data for {len(user_ids)} users...")
    await server.db.users.delete_many({"user_id": {"$in": user_ids}})
    await server.db.notifications.delete_many({"user_id": {"$in": user_ids}})
    print("✅ Cleanup complete")

async def create_test_users():
    """Create 3 opted-in users and 1 opted-out user in Madrid"""
    print("\n📝 Creating test users...")
    user_ids = []
    
    # Create 3 opted-in users
    for i in range(3):
        user_id = f"tb_optin_{i}"
        user_doc = {
            "user_id": user_id,
            "email": f"optin{i}@test.com",
            "username": f"optin{i}",
            "name": f"Opted In User {i}",
            "city": TEST_CITY,
            "notif_prefs": {
                "new_event": True,
                "friend_request": True,
                "friend_accept": True,
                "event_reminder": True,
                "group_invite": True,
                "group_message": True,
                "dm": True,
            },
            "city_change_alerts": False,
            "birthdate": "1995-01-01",
            "created_at": datetime.utcnow().isoformat(),
        }
        await server.db.users.update_one(
            {"user_id": user_id},
            {"$set": user_doc},
            upsert=True
        )
        user_ids.append(user_id)
        print(f"  ✅ Created opted-in user: {user_id}")
    
    # Create 1 opted-out user
    user_id = "tb_optout"
    user_doc = {
        "user_id": user_id,
        "email": "optout@test.com",
        "username": "optout",
        "name": "Opted Out User",
        "city": TEST_CITY,
        "notif_prefs": {
            "new_event": False,  # OPTED OUT
            "friend_request": True,
            "friend_accept": True,
            "event_reminder": True,
            "group_invite": True,
            "group_message": True,
            "dm": True,
        },
        "city_change_alerts": False,
        "birthdate": "1995-01-01",
        "created_at": datetime.utcnow().isoformat(),
    }
    await server.db.users.update_one(
        {"user_id": user_id},
        {"$set": user_doc},
        upsert=True
    )
    user_ids.append(user_id)
    print(f"  ✅ Created opted-out user: {user_id}")
    
    return user_ids

async def clear_notifications(user_ids):
    """Clear all new_event notifications for test users"""
    result = await server.db.notifications.delete_many({
        "user_id": {"$in": user_ids},
        "type": "new_event"
    })
    print(f"  🗑️  Cleared {result.deleted_count} existing new_event notifications")

async def test_batch_notification():
    """Test 1: Batch notification with 9 events"""
    print("\n" + "="*80)
    print("TEST 1: BATCH NOTIFICATION (9 events)")
    print("="*80)
    
    user_ids = await create_test_users()
    
    try:
        # Clear any existing notifications
        await clear_notifications(user_ids)
        
        # Build venue
        venue = {
            "name": TEST_CLUB_NAME,
            "city": TEST_CITY
        }
        
        # Build 9 fake events
        events = []
        base_date = datetime.now() + timedelta(days=7)
        for i in range(9):
            event_date = base_date + timedelta(days=i)
            event = {
                "id": str(uuid.uuid4()),
                "name": f"Fiesta {i+1}",
                "venue": TEST_CLUB_NAME,
                "city": TEST_CITY,
                "date": event_date.strftime("%Y-%m-%d"),
            }
            events.append(event)
        
        print(f"\n📅 Created {len(events)} fake events for {TEST_CLUB_NAME}")
        
        # Call the batch notification function
        print(f"\n🔔 Calling _notify_new_events_batch with {len(events)} events...")
        count = await server._notify_new_events_batch(venue, events)
        print(f"  ✅ Function returned count: {count}")
        
        # Verify notifications
        print("\n🔍 Verifying notifications...")
        
        # Check opted-in users (should have EXACTLY 1 notification each)
        for i in range(3):
            user_id = f"tb_optin_{i}"
            notif_count = await server.db.notifications.count_documents({
                "user_id": user_id,
                "type": "new_event"
            })
            
            if notif_count == 1:
                print(f"  ✅ User {user_id}: {notif_count} notification (PASS)")
                
                # Check the message content
                notif = await server.db.notifications.find_one({
                    "user_id": user_id,
                    "type": "new_event"
                })
                message = notif.get("message", "")
                
                if "9 fiestas nuevas" in message and TEST_CLUB_NAME in message:
                    print(f"     ✅ Message contains '9 fiestas nuevas' and club name: '{message}'")
                else:
                    print(f"     ❌ Message MISSING expected content: '{message}'")
                    return False
            else:
                print(f"  ❌ User {user_id}: {notif_count} notifications (EXPECTED 1, FAIL)")
                return False
        
        # Check opted-out user (should have 0 notifications)
        user_id = "tb_optout"
        notif_count = await server.db.notifications.count_documents({
            "user_id": user_id,
            "type": "new_event"
        })
        
        if notif_count == 0:
            print(f"  ✅ User {user_id}: {notif_count} notifications (PASS)")
        else:
            print(f"  ❌ User {user_id}: {notif_count} notifications (EXPECTED 0, FAIL)")
            return False
        
        print("\n✅ TEST 1 PASSED: Batch notification working correctly")
        return True
        
    finally:
        await cleanup_test_data(user_ids)

async def test_single_event_notification():
    """Test 2: Single event notification (should use single-event path)"""
    print("\n" + "="*80)
    print("TEST 2: SINGLE EVENT NOTIFICATION (1 event)")
    print("="*80)
    
    user_ids = await create_test_users()
    
    try:
        # Clear any existing notifications
        await clear_notifications(user_ids)
        
        # Build venue
        venue = {
            "name": TEST_CLUB_NAME,
            "city": TEST_CITY
        }
        
        # Build 1 fake event
        event_date = datetime.now() + timedelta(days=7)
        events = [{
            "id": str(uuid.uuid4()),
            "name": "Fiesta Única",
            "venue": TEST_CLUB_NAME,
            "city": TEST_CITY,
            "date": event_date.strftime("%Y-%m-%d"),
        }]
        
        print(f"\n📅 Created 1 fake event for {TEST_CLUB_NAME}")
        
        # Call the batch notification function (should delegate to single-event path)
        print(f"\n🔔 Calling _notify_new_events_batch with 1 event...")
        count = await server._notify_new_events_batch(venue, events)
        print(f"  ✅ Function returned count: {count}")
        
        # Verify notifications
        print("\n🔍 Verifying notifications...")
        
        # Check opted-in users (should have EXACTLY 1 notification each)
        for i in range(3):
            user_id = f"tb_optin_{i}"
            notif_count = await server.db.notifications.count_documents({
                "user_id": user_id,
                "type": "new_event"
            })
            
            if notif_count == 1:
                print(f"  ✅ User {user_id}: {notif_count} notification (PASS)")
                
                # Check the message content (should start with "🆕 Nueva fiesta:")
                notif = await server.db.notifications.find_one({
                    "user_id": user_id,
                    "type": "new_event"
                })
                message = notif.get("message", "")
                
                if message.startswith("🆕 Nueva fiesta:"):
                    print(f"     ✅ Message starts with '🆕 Nueva fiesta:': '{message}'")
                else:
                    print(f"     ❌ Message does NOT start with '🆕 Nueva fiesta:': '{message}'")
                    return False
            else:
                print(f"  ❌ User {user_id}: {notif_count} notifications (EXPECTED 1, FAIL)")
                return False
        
        # Check opted-out user (should have 0 notifications)
        user_id = "tb_optout"
        notif_count = await server.db.notifications.count_documents({
            "user_id": user_id,
            "type": "new_event"
        })
        
        if notif_count == 0:
            print(f"  ✅ User {user_id}: {notif_count} notifications (PASS)")
        else:
            print(f"  ❌ User {user_id}: {notif_count} notifications (EXPECTED 0, FAIL)")
            return False
        
        print("\n✅ TEST 2 PASSED: Single event notification working correctly")
        return True
        
    finally:
        await cleanup_test_data(user_ids)

async def test_api_registration():
    """Test 3: API registration - verify city_change_alerts is false by default"""
    print("\n" + "="*80)
    print("TEST 3: API REGISTRATION (city_change_alerts default OFF)")
    print("="*80)
    
    import httpx
    
    # Generate unique credentials
    timestamp = int(datetime.now().timestamp())
    email = f"test{timestamp}@example.com"
    username = f"testuser{timestamp}"
    password = "TestPassword123!"
    
    print(f"\n📝 Registering new user via API...")
    print(f"  Email: {email}")
    print(f"  Username: {username}")
    
    # Register via API
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{BACKEND_URL}/api/auth/register",
                json={
                    "email": email,
                    "username": username,
                    "password": password,
                    "name": "Test User",
                    "birthdate": "1995-01-01",
                    "city": "Madrid"
                },
                timeout=10.0
            )
            
            if response.status_code == 200:
                user_data = response.json()
                print(f"  ✅ Registration successful (HTTP 200)")
                print(f"  DEBUG: Full response: {user_data}")
                
                # Check city_change_alerts (should be False or None, both mean OFF)
                city_change_alerts = user_data.get("user", {}).get("city_change_alerts") if "user" in user_data else user_data.get("city_change_alerts")
                
                if city_change_alerts in (False, None):
                    print(f"  ✅ city_change_alerts = {city_change_alerts} (PASS - default OFF)")
                else:
                    print(f"  ❌ city_change_alerts = {city_change_alerts} (EXPECTED False or None, FAIL)")
                    return False
                
                # Test login
                print(f"\n🔐 Testing login...")
                login_response = await client.post(
                    f"{BACKEND_URL}/api/auth/login",
                    json={
                        "email": email,
                        "password": password
                    },
                    timeout=10.0
                )
                
                if login_response.status_code == 200:
                    print(f"  ✅ Login successful (HTTP 200)")
                else:
                    print(f"  ❌ Login failed (HTTP {login_response.status_code})")
                    return False
                
                print("\n✅ TEST 3 PASSED: API registration and login working correctly")
                return True
            else:
                print(f"  ❌ Registration failed (HTTP {response.status_code})")
                print(f"  Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"  ❌ API request failed: {e}")
            return False

async def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("NOTIFICATION BATCHING BUG FIX VERIFICATION")
    print("="*80)
    print(f"Backend URL: {BACKEND_URL}")
    print(f"Test City: {TEST_CITY}")
    print(f"Test Club: {TEST_CLUB_NAME}")
    
    results = []
    
    # Test 1: Batch notification (9 events)
    try:
        result = await test_batch_notification()
        results.append(("Batch notification (9 events)", result))
    except Exception as e:
        print(f"\n❌ TEST 1 FAILED WITH EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Batch notification (9 events)", False))
    
    # Test 2: Single event notification
    try:
        result = await test_single_event_notification()
        results.append(("Single event notification (1 event)", result))
    except Exception as e:
        print(f"\n❌ TEST 2 FAILED WITH EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Single event notification (1 event)", False))
    
    # Test 3: API registration
    try:
        result = await test_api_registration()
        results.append(("API registration (city_change_alerts default)", result))
    except Exception as e:
        print(f"\n❌ TEST 3 FAILED WITH EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        results.append(("API registration (city_change_alerts default)", False))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    all_passed = all(result for _, result in results)
    
    if all_passed:
        print("\n🎉 ALL TESTS PASSED 🎉")
        print("\n✅ CONCLUSION:")
        print("  - Batch notification sends EXACTLY 1 notification per user (not 9)")
        print("  - Message contains '9 fiestas nuevas' and club name")
        print("  - Opted-out users receive 0 notifications")
        print("  - Single event uses the single-event path ('🆕 Nueva fiesta:')")
        print("  - API registration sets city_change_alerts to False by default")
        print("  - API login works correctly")
        print("\n✅ The per-event push burst bug is FIXED!")
    else:
        print("\n❌ SOME TESTS FAILED")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
