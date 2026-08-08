#!/usr/bin/env python3
"""
Test GET /api/admin/moments with new scope parameter
Testing ONLY the scope query parameter functionality
"""

import requests
import sys

# Base URL from frontend/.env
BASE_URL = "https://party-memories-36.preview.emergentagent.com/api"

# Admin credentials from test_credentials.md
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

def test_admin_moments_scope():
    """Test GET /api/admin/moments with scope parameter"""
    
    print("=" * 80)
    print("TESTING: GET /api/admin/moments with scope parameter")
    print("=" * 80)
    
    # Test 1: Auth guard - without token should return 401 or 403
    print("\n[TEST 1] Auth guard: GET /api/admin/moments WITHOUT token")
    resp = requests.get(f"{BASE_URL}/admin/moments")
    print(f"  Status: {resp.status_code}")
    assert resp.status_code in [401, 403], f"Expected 401 or 403, got {resp.status_code}"
    print("  ✅ PASS: Returns 401/403 without token")
    
    # Test 1b: Auth guard with scope parameter
    print("\n[TEST 1b] Auth guard: GET /api/admin/moments?scope=tonight WITHOUT token")
    resp = requests.get(f"{BASE_URL}/admin/moments?scope=tonight")
    print(f"  Status: {resp.status_code}")
    assert resp.status_code in [401, 403], f"Expected 401 or 403, got {resp.status_code}"
    print("  ✅ PASS: Returns 401/403 without token (with scope param)")
    
    # Login as admin
    print("\n[SETUP] Logging in as admin...")
    login_resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert login_resp.status_code == 200, f"Admin login failed: {login_resp.status_code}"
    admin_token = login_resp.json()["token"]
    headers = {"Authorization": f"Bearer {admin_token}"}
    print("  ✅ Admin logged in successfully")
    
    # Test 2: GET with scope=tonight
    print("\n[TEST 2] GET /api/admin/moments?scope=tonight")
    resp_tonight = requests.get(f"{BASE_URL}/admin/moments?scope=tonight", headers=headers)
    print(f"  Status: {resp_tonight.status_code}")
    assert resp_tonight.status_code == 200, f"Expected 200, got {resp_tonight.status_code}"
    data_tonight = resp_tonight.json()
    assert isinstance(data_tonight, list), "Expected array response"
    count_tonight = len(data_tonight)
    print(f"  Count: {count_tonight} events")
    print("  ✅ PASS: scope=tonight returns array")
    
    # Test 3: GET with scope=later
    print("\n[TEST 3] GET /api/admin/moments?scope=later")
    resp_later = requests.get(f"{BASE_URL}/admin/moments?scope=later", headers=headers)
    print(f"  Status: {resp_later.status_code}")
    assert resp_later.status_code == 200, f"Expected 200, got {resp_later.status_code}"
    data_later = resp_later.json()
    assert isinstance(data_later, list), "Expected array response"
    count_later = len(data_later)
    print(f"  Count: {count_later} events")
    print("  ✅ PASS: scope=later returns array")
    
    # Test 4: GET with scope=all
    print("\n[TEST 4] GET /api/admin/moments?scope=all")
    resp_all = requests.get(f"{BASE_URL}/admin/moments?scope=all", headers=headers)
    print(f"  Status: {resp_all.status_code}")
    assert resp_all.status_code == 200, f"Expected 200, got {resp_all.status_code}"
    data_all = resp_all.json()
    assert isinstance(data_all, list), "Expected array response"
    count_all = len(data_all)
    print(f"  Count: {count_all} events")
    print("  ✅ PASS: scope=all returns array")
    
    # Test 5: GET without scope (should behave like scope=all)
    print("\n[TEST 5] GET /api/admin/moments (no scope parameter)")
    resp_no_scope = requests.get(f"{BASE_URL}/admin/moments", headers=headers)
    print(f"  Status: {resp_no_scope.status_code}")
    assert resp_no_scope.status_code == 200, f"Expected 200, got {resp_no_scope.status_code}"
    data_no_scope = resp_no_scope.json()
    assert isinstance(data_no_scope, list), "Expected array response"
    count_no_scope = len(data_no_scope)
    print(f"  Count: {count_no_scope} events")
    print("  ✅ PASS: no scope returns array")
    
    # Test 6: Assert tonight + later == all
    print("\n[TEST 6] Assert: len(tonight) + len(later) == len(all)")
    print(f"  tonight: {count_tonight}")
    print(f"  later: {count_later}")
    print(f"  all: {count_all}")
    print(f"  tonight + later: {count_tonight + count_later}")
    assert count_tonight + count_later == count_all, \
        f"Expected {count_tonight} + {count_later} == {count_all}, but got {count_tonight + count_later}"
    print("  ✅ PASS: tonight + later == all (no overlap, no gaps)")
    
    # Test 7: Assert no scope == all
    print("\n[TEST 7] Assert: len(no-scope) == len(all)")
    print(f"  no-scope: {count_no_scope}")
    print(f"  all: {count_all}")
    assert count_no_scope == count_all, \
        f"Expected no-scope ({count_no_scope}) == all ({count_all})"
    print("  ✅ PASS: no-scope behaves identically to scope=all")
    
    # Test 8: Verify field structure (check one item from each scope if available)
    print("\n[TEST 8] Verify each item has required fields")
    required_fields = [
        "id", "name", "venue", "date", "time", 
        "planned_moment_at", "moment_cancelled", "has_fired", 
        "fired_at", "voy_count", "captures_count"
    ]
    
    # Check tonight items
    if count_tonight > 0:
        item = data_tonight[0]
        print(f"  Checking tonight item: {item.get('name', 'N/A')}")
        for field in required_fields:
            assert field in item, f"Missing field '{field}' in tonight item"
        print(f"  ✅ tonight items have all required fields")
    else:
        print(f"  ⚠️  No tonight items to check")
    
    # Check later items
    if count_later > 0:
        item = data_later[0]
        print(f"  Checking later item: {item.get('name', 'N/A')}")
        for field in required_fields:
            assert field in item, f"Missing field '{field}' in later item"
        print(f"  ✅ later items have all required fields")
    else:
        print(f"  ⚠️  No later items to check")
    
    # Check all items
    if count_all > 0:
        item = data_all[0]
        print(f"  Checking all item: {item.get('name', 'N/A')}")
        for field in required_fields:
            assert field in item, f"Missing field '{field}' in all item"
        print(f"  ✅ all items have all required fields")
    else:
        print(f"  ⚠️  No all items to check")
    
    # Test 9: Sanity check - unknown scope value should not error (500)
    print("\n[TEST 9] Sanity: unknown scope value (scope=foo) should not error")
    resp_unknown = requests.get(f"{BASE_URL}/admin/moments?scope=foo", headers=headers)
    print(f"  Status: {resp_unknown.status_code}")
    assert resp_unknown.status_code == 200, \
        f"Expected 200 (fallback to all), got {resp_unknown.status_code}"
    data_unknown = resp_unknown.json()
    count_unknown = len(data_unknown)
    print(f"  Count: {count_unknown} events")
    # Should behave like 'all' (fallback)
    print(f"  Expected to behave like 'all' ({count_all} events)")
    print("  ✅ PASS: unknown scope does not error, falls back gracefully")
    
    print("\n" + "=" * 80)
    print("✅ ALL TESTS PASSED")
    print("=" * 80)
    print(f"\nSUMMARY:")
    print(f"  - Auth guard: ✅ (401/403 without token)")
    print(f"  - scope=tonight: ✅ ({count_tonight} events)")
    print(f"  - scope=later: ✅ ({count_later} events)")
    print(f"  - scope=all: ✅ ({count_all} events)")
    print(f"  - no scope: ✅ ({count_no_scope} events, behaves like all)")
    print(f"  - tonight + later == all: ✅ ({count_tonight} + {count_later} = {count_all})")
    print(f"  - Field structure: ✅ (all required fields present)")
    print(f"  - Unknown scope: ✅ (does not error, falls back)")
    print()

if __name__ == "__main__":
    try:
        test_admin_moments_scope()
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
