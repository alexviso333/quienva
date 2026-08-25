#!/usr/bin/env python3
"""
Test suite for GET /api/events/top-weekend performance fix.

This tests the N+1 query optimization that reduced response time from ~19s to milliseconds.
The endpoint now uses bulk loading of interests instead of per-event queries.
"""

import requests
import time
import sys

# LOCAL backend (NOT production)
BASE_URL = "http://localhost:8001/api"

# Seeded session token for user "me-uid" with 40 friends in Madrid
AUTH_TOKEN = "perftest-session-token-me"
AUTH_HEADER = {"Authorization": f"Bearer {AUTH_TOKEN}"}

def test_correctness_authenticated():
    """
    TEST 1: CORRECTNESS (authenticated with query param ?city=Madrid)
    
    Expected:
    - HTTP 200
    - Single event object with id="ev-42" and name="Fiesta 42"
    - len(friends_going) == 40
    - total_going == 40
    """
    print("\n" + "="*80)
    print("TEST 1: CORRECTNESS (authenticated)")
    print("="*80)
    
    url = f"{BASE_URL}/events/top-weekend?city=Madrid"
    response = requests.get(url, headers=AUTH_HEADER)
    
    print(f"URL: {url}")
    print(f"Status: {response.status_code}")
    
    if response.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {response.status_code}")
        print(f"Response: {response.text}")
        return False
    
    data = response.json()
    
    # Check if response is None (no events)
    if data is None:
        print(f"❌ FAILED: Response is None (no events found)")
        return False
    
    print(f"Event ID: {data.get('id')}")
    print(f"Event Name: {data.get('name')}")
    
    # Check event ID
    if data.get('id') != 'ev-42':
        print(f"❌ FAILED: Expected event id='ev-42', got '{data.get('id')}'")
        return False
    
    # Check event name
    if data.get('name') != 'Fiesta 42':
        print(f"❌ FAILED: Expected event name='Fiesta 42', got '{data.get('name')}'")
        return False
    
    # Check friends_going count
    friends_going = data.get('friends_going', [])
    friends_count = len(friends_going)
    print(f"Friends going: {friends_count}")
    
    if friends_count != 40:
        print(f"❌ FAILED: Expected 40 friends going, got {friends_count}")
        return False
    
    # Check total_going
    total_going = data.get('total_going', 0)
    print(f"Total going: {total_going}")
    
    if total_going != 40:
        print(f"❌ FAILED: Expected total_going=40, got {total_going}")
        return False
    
    print("✅ PASSED: Correctness check successful")
    print(f"   - Event ID: ev-42 ✓")
    print(f"   - Event Name: Fiesta 42 ✓")
    print(f"   - Friends going: 40 ✓")
    print(f"   - Total going: 40 ✓")
    return True


def test_performance():
    """
    TEST 2: PERFORMANCE
    
    Expected:
    - Response time well under 2 seconds (locally should be milliseconds)
    - Must NOT take ~19 seconds (which would indicate N+1 problem still present)
    
    Context: 160 events and 358 interests seeded. If it takes several seconds,
    it indicates the N+1 problem is still present.
    """
    print("\n" + "="*80)
    print("TEST 2: PERFORMANCE")
    print("="*80)
    
    url = f"{BASE_URL}/events/top-weekend?city=Madrid"
    
    # Warm-up request (in case there's any cold-start overhead)
    requests.get(url, headers=AUTH_HEADER)
    
    # Measure actual performance
    start_time = time.time()
    response = requests.get(url, headers=AUTH_HEADER)
    elapsed_time = time.time() - start_time
    
    print(f"URL: {url}")
    print(f"Status: {response.status_code}")
    print(f"Response time: {elapsed_time:.3f} seconds ({elapsed_time*1000:.1f} ms)")
    
    if response.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {response.status_code}")
        return False
    
    # Performance threshold: must be under 2 seconds
    if elapsed_time >= 2.0:
        print(f"❌ FAILED: Response time {elapsed_time:.3f}s is >= 2 seconds")
        print("   This indicates the N+1 query problem may still be present")
        return False
    
    # Warning if it's slower than expected (but still under 2s)
    if elapsed_time > 0.5:
        print(f"⚠️  WARNING: Response time {elapsed_time:.3f}s is slower than expected")
        print("   (locally should be < 500ms, but still under 2s threshold)")
    
    print(f"✅ PASSED: Performance check successful")
    print(f"   - Response time: {elapsed_time:.3f}s (well under 2s threshold) ✓")
    print(f"   - N+1 query optimization working ✓")
    return True


def test_guest_unauthenticated():
    """
    TEST 3: GUEST (no Authorization header)
    
    Expected:
    - HTTP 200
    - null/empty body (no friends → no ranking)
    """
    print("\n" + "="*80)
    print("TEST 3: GUEST (unauthenticated)")
    print("="*80)
    
    url = f"{BASE_URL}/events/top-weekend?city=Madrid"
    response = requests.get(url)  # No auth header
    
    print(f"URL: {url}")
    print(f"Status: {response.status_code}")
    
    if response.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {response.status_code}")
        print(f"Response: {response.text}")
        return False
    
    data = response.json()
    print(f"Response body: {data}")
    
    # Should be None or empty (no friends → no ranking)
    if data is not None and data != {}:
        print(f"❌ FAILED: Expected null/empty body, got {data}")
        return False
    
    print("✅ PASSED: Guest check successful")
    print(f"   - Returns null/empty body (no friends → no ranking) ✓")
    return True


def test_regression_events_list():
    """
    TEST 4a: REGRESSION - GET /api/events?city=Madrid&date_filter=all
    
    Expected:
    - HTTP 200
    - List of 160 events
    """
    print("\n" + "="*80)
    print("TEST 4a: REGRESSION - Events list")
    print("="*80)
    
    url = f"{BASE_URL}/events?city=Madrid&date_filter=all"
    response = requests.get(url, headers=AUTH_HEADER)
    
    print(f"URL: {url}")
    print(f"Status: {response.status_code}")
    
    if response.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {response.status_code}")
        print(f"Response: {response.text}")
        return False
    
    data = response.json()
    events_count = len(data)
    print(f"Events count: {events_count}")
    
    if events_count != 160:
        print(f"❌ FAILED: Expected 160 events, got {events_count}")
        return False
    
    print("✅ PASSED: Events list regression check successful")
    print(f"   - Returns 160 events ✓")
    return True


def test_regression_carousels():
    """
    TEST 4b: REGRESSION - GET /api/events/carousels?city=Madrid
    
    Expected:
    - HTTP 200
    - No error
    """
    print("\n" + "="*80)
    print("TEST 4b: REGRESSION - Carousels")
    print("="*80)
    
    url = f"{BASE_URL}/events/carousels?city=Madrid"
    response = requests.get(url, headers=AUTH_HEADER)
    
    print(f"URL: {url}")
    print(f"Status: {response.status_code}")
    
    if response.status_code != 200:
        print(f"❌ FAILED: Expected 200, got {response.status_code}")
        print(f"Response: {response.text}")
        return False
    
    data = response.json()
    print(f"Response keys: {list(data.keys())}")
    
    print("✅ PASSED: Carousels regression check successful")
    print(f"   - Returns 200 without error ✓")
    return True


def main():
    print("\n" + "="*80)
    print("BACKEND TEST: GET /api/events/top-weekend Performance Fix")
    print("="*80)
    print("\nContext:")
    print("- Testing LOCAL backend at http://localhost:8001")
    print("- Database: quienva_local_test (seeded by scripts/seed_perf_test.py)")
    print("- User: me-uid (40 friends in Madrid)")
    print("- Expected winner: ev-42 (Fiesta 42) with 40 friends going")
    print("- Performance fix: N+1 query → bulk loading (19s → milliseconds)")
    
    results = []
    
    # Run all tests
    results.append(("Correctness (authenticated)", test_correctness_authenticated()))
    results.append(("Performance", test_performance()))
    results.append(("Guest (unauthenticated)", test_guest_unauthenticated()))
    results.append(("Regression: Events list", test_regression_events_list()))
    results.append(("Regression: Carousels", test_regression_carousels()))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n❌ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
