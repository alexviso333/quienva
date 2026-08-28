"""Backend HTTP tests for event link stability fix.

Tests:
1. GET /api/events/nonexistent-id-123 must return HTTP 404 (not 500)
2. GET /api/events?city=Madrid&date_filter=all must return HTTP 200 with JSON list
"""
import requests
import sys

# Use local backend for testing
BASE_URL = "http://localhost:8001"

def test_nonexistent_event_404():
    """Test that a nonexistent event ID returns 404, not 500."""
    print("\n✅ TEST 1: GET /api/events/nonexistent-id-123 (expect 404)")
    url = f"{BASE_URL}/api/events/nonexistent-id-123"
    response = requests.get(url)
    
    print(f"   Status code: {response.status_code}")
    
    if response.status_code == 404:
        print("   ✅ PASS: Returns 404 as expected for nonexistent event")
        return True
    elif response.status_code == 500:
        print(f"   ❌ FAIL: Returns 500 (should be 404)")
        print(f"   Response: {response.text[:200]}")
        return False
    else:
        print(f"   ❌ FAIL: Unexpected status code {response.status_code}")
        print(f"   Response: {response.text[:200]}")
        return False

def test_madrid_events_regression():
    """Test that Madrid events endpoint still works (regression test)."""
    print("\n✅ TEST 2: GET /api/events?city=Madrid&date_filter=all (expect 200 with JSON list)")
    url = f"{BASE_URL}/api/events"
    params = {"city": "Madrid", "date_filter": "all"}
    response = requests.get(url, params=params)
    
    print(f"   Status code: {response.status_code}")
    
    if response.status_code != 200:
        print(f"   ❌ FAIL: Expected 200, got {response.status_code}")
        print(f"   Response: {response.text[:200]}")
        return False
    
    try:
        data = response.json()
        if not isinstance(data, list):
            print(f"   ❌ FAIL: Response is not a JSON list (type: {type(data)})")
            return False
        
        print(f"   ✅ PASS: Returns 200 with JSON list ({len(data)} events)")
        return True
    except Exception as e:
        print(f"   ❌ FAIL: Could not parse JSON response: {e}")
        print(f"   Response: {response.text[:200]}")
        return False

def main():
    print("=" * 70)
    print("BACKEND HTTP TESTS: Event Link Stability Fix")
    print("=" * 70)
    
    results = []
    
    # Test 1: Nonexistent event returns 404
    results.append(test_nonexistent_event_404())
    
    # Test 2: Madrid events regression
    results.append(test_madrid_events_regression())
    
    # Summary
    print("\n" + "=" * 70)
    passed = sum(results)
    total = len(results)
    print(f"SUMMARY: {passed}/{total} tests passed")
    
    if passed == total:
        print("✅ ALL HTTP TESTS PASSED")
        print("=" * 70)
        return 0
    else:
        print(f"❌ {total - passed} test(s) failed")
        print("=" * 70)
        return 1

if __name__ == "__main__":
    sys.exit(main())
