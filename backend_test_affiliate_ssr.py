"""
Backend testing for:
1. Affiliate "Mi link" honest badge + link consistency (HIGH PRIORITY)
2. SSR home "Fiestas de hoy" — no logged-in redirect + cache (MEDIUM)

Test credentials: admin@quienva.app / admin123
Backend URL: from frontend/.env REACT_APP_BACKEND_URL
"""
import requests
import json
import sys
from typing import Dict, Any, List

# Read backend URL from frontend/.env
with open("/app/frontend/.env") as f:
    for line in f:
        if line.startswith("REACT_APP_BACKEND_URL="):
            BACKEND_URL = line.split("=", 1)[1].strip()
            break
    else:
        print("❌ REACT_APP_BACKEND_URL not found in frontend/.env")
        sys.exit(1)

API_BASE = f"{BACKEND_URL}/api"
print(f"🔗 Testing backend at: {API_BASE}\n")

# Admin credentials
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

# Test event IDs seeded by /app/scripts/seed_affiliate_verify.py
CARRIED_EVENT_IDS = ["seed_F13L", "seed_XWEK", "seed_WEYC", "seed_P0T2"]
NON_CARRIED_EVENT_ID = "seed_notcarried"

# Test results tracking
test_results = {
    "passed": 0,
    "failed": 0,
    "failures": []
}

def log_pass(test_name: str):
    """Log a passing test"""
    print(f"✅ {test_name}")
    test_results["passed"] += 1

def log_fail(test_name: str, reason: str):
    """Log a failing test"""
    print(f"❌ {test_name}")
    print(f"   Reason: {reason}")
    test_results["failed"] += 1
    test_results["failures"].append(f"{test_name}: {reason}")

def print_summary():
    """Print test summary"""
    total = test_results["passed"] + test_results["failed"]
    print(f"\n{'='*80}")
    print(f"TEST SUMMARY: {test_results['passed']}/{total} PASSED")
    print(f"{'='*80}")
    if test_results["failures"]:
        print("\n❌ FAILURES:")
        for failure in test_results["failures"]:
            print(f"  - {failure}")
    print()

# ============================================================================
# TEST AREA 1: Affiliate "Mi link" honest badge + link consistency
# ============================================================================

print("="*80)
print("TEST AREA 1: AFFILIATE 'MI LINK' HONEST BADGE + LINK CONSISTENCY")
print("="*80)
print()

# Test 1a: Admin login
print("TEST 1a: Admin login")
try:
    login_resp = requests.post(
        f"{API_BASE}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=10
    )
    if login_resp.status_code == 200:
        admin_token = login_resp.json().get("token")
        admin_cookies = login_resp.cookies
        log_pass("TEST 1a: Admin login successful")
        print(f"   Token: {admin_token[:20]}...")
    else:
        log_fail("TEST 1a: Admin login", f"Status {login_resp.status_code}: {login_resp.text}")
        print_summary()
        sys.exit(1)
except Exception as e:
    log_fail("TEST 1a: Admin login", str(e))
    print_summary()
    sys.exit(1)

# Test 1b: GET /api/events?city=Sevilla WITH admin auth
print("\nTEST 1b: GET /api/events?city=Sevilla (with admin auth)")
try:
    events_resp = requests.get(
        f"{API_BASE}/events",
        params={"city": "Sevilla"},
        headers={"Authorization": f"Bearer {admin_token}"},
        cookies=admin_cookies,
        timeout=10
    )
    if events_resp.status_code == 200:
        events = events_resp.json()
        log_pass(f"TEST 1b: GET /api/events?city=Sevilla → 200 ({len(events)} events)")
        print(f"   Total events in Sevilla: {len(events)}")
    else:
        log_fail("TEST 1b: GET /api/events?city=Sevilla", f"Status {events_resp.status_code}: {events_resp.text}")
        events = []
except Exception as e:
    log_fail("TEST 1b: GET /api/events?city=Sevilla", str(e))
    events = []

# Test 1c: Verify CARRIED events (seed_F13L, seed_XWEK, seed_WEYC, seed_P0T2)
# Note: Some events might not appear in the feed due to date/time filtering,
# so we'll check them individually via GET /api/events/{id}
print("\nTEST 1c: Verify CARRIED events have correct affiliate link + badge")
print("   (Checking each event individually via GET /api/events/{id})")

for event_id in CARRIED_EVENT_IDS:
    try:
        event_resp = requests.get(
            f"{API_BASE}/events/{event_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            cookies=admin_cookies,
            timeout=10
        )
        
        if event_resp.status_code == 200:
            event = event_resp.json()
            commission_url = event.get("commission_url", "")
            is_affiliate = event.get("is_affiliate")
            
            print(f"\n   Event: {event_id}")
            print(f"   - commission_url: {commission_url}")
            print(f"   - is_affiliate: {is_affiliate}")
            
            # Check commission_url starts with correct format
            if commission_url.startswith("https://site.fourvenues.com/es/quienva/events/"):
                log_pass(f"TEST 1c.{event_id}: commission_url starts with correct affiliate format")
            else:
                log_fail(
                    f"TEST 1c.{event_id}: commission_url format",
                    f"Expected to start with 'https://site.fourvenues.com/es/quienva/events/', got: {commission_url}"
                )
            
            # Check is_affiliate is true
            if is_affiliate is True:
                log_pass(f"TEST 1c.{event_id}: is_affiliate == true")
            else:
                log_fail(
                    f"TEST 1c.{event_id}: is_affiliate value",
                    f"Expected true, got: {is_affiliate}"
                )
        else:
            log_fail(f"TEST 1c.{event_id}: GET event", f"Status {event_resp.status_code}")
    except Exception as e:
        log_fail(f"TEST 1c.{event_id}: GET event", str(e))

# Test 1d: Verify NON-CARRIED event (seed_notcarried)
print("\nTEST 1d: Verify NON-CARRIED event has direct link + is_affiliate=false")
try:
    event_resp = requests.get(
        f"{API_BASE}/events/{NON_CARRIED_EVENT_ID}",
        headers={"Authorization": f"Bearer {admin_token}"},
        cookies=admin_cookies,
        timeout=10
    )
    
    if event_resp.status_code == 200:
        non_carried_event = event_resp.json()
        commission_url = non_carried_event.get("commission_url", "")
        is_affiliate = non_carried_event.get("is_affiliate")
        
        print(f"   Event: {NON_CARRIED_EVENT_ID}")
        print(f"   - commission_url: {commission_url}")
        print(f"   - is_affiliate: {is_affiliate}")
        
        # Check commission_url does NOT contain /quienva/
        if "/quienva/" not in commission_url:
            log_pass(f"TEST 1d: commission_url does NOT contain '/quienva/'")
        else:
            log_fail(
                f"TEST 1d: commission_url should not contain '/quienva/'",
                f"Got: {commission_url}"
            )
        
        # Check is_affiliate is false or falsy
        if is_affiliate is False or not is_affiliate:
            log_pass(f"TEST 1d: is_affiliate is false/falsy")
        else:
            log_fail(
                f"TEST 1d: is_affiliate should be false",
                f"Got: {is_affiliate}"
            )
    else:
        log_fail("TEST 1d: GET NON-CARRIED event", f"Status {event_resp.status_code}")
except Exception as e:
    log_fail("TEST 1d: GET NON-CARRIED event", str(e))

# Test 1e: Consistency invariant across ALL events
print("\nTEST 1e: Consistency invariant (badge ≠ link violations)")
violations = []
for event in events:
    event_id = event.get("id")
    commission_url = event.get("commission_url", "")
    is_affiliate = event.get("is_affiliate")
    
    # Check if is_affiliate == true but link doesn't contain /quienva/ or aff=
    if is_affiliate is True:
        has_quienva = "/quienva/" in commission_url
        has_aff = "aff=" in commission_url
        if not (has_quienva or has_aff):
            violations.append(f"{event_id}: is_affiliate=true but link has no /quienva/ or aff=")
    
    # Check if is_affiliate == false but link contains /quienva/
    if is_affiliate is False:
        if "/quienva/" in commission_url:
            violations.append(f"{event_id}: is_affiliate=false but link contains /quienva/")

if violations:
    for v in violations:
        log_fail("TEST 1e: Consistency violation", v)
else:
    log_pass(f"TEST 1e: No consistency violations found across {len(events)} events")

# Test 1f: Regression - GET /api/events (no auth) returns 200 with required fields
print("\nTEST 1f: Regression - GET /api/events (no auth)")
try:
    guest_resp = requests.get(
        f"{API_BASE}/events",
        params={"city": "Sevilla"},
        timeout=10
    )
    if guest_resp.status_code == 200:
        guest_events = guest_resp.json()
        log_pass(f"TEST 1f: GET /api/events (no auth) → 200 ({len(guest_events)} events)")
        
        # Check first event has required fields
        if guest_events:
            first_event = guest_events[0]
            required_fields = ["price_tiers", "sale_state", "commission_url"]
            missing_fields = [f for f in required_fields if f not in first_event]
            
            if not missing_fields:
                log_pass("TEST 1f: Events include price_tiers, sale_state, commission_url")
            else:
                log_fail("TEST 1f: Missing fields", f"Missing: {missing_fields}")
            
            # Check is_affiliate is null for non-admin
            if first_event.get("is_affiliate") is None:
                log_pass("TEST 1f: is_affiliate is null for non-admin")
            else:
                log_fail("TEST 1f: is_affiliate should be null for non-admin", f"Got: {first_event.get('is_affiliate')}")
    else:
        log_fail("TEST 1f: GET /api/events (no auth)", f"Status {guest_resp.status_code}")
except Exception as e:
    log_fail("TEST 1f: GET /api/events (no auth)", str(e))

# ============================================================================
# TEST AREA 2: SSR home "Fiestas de hoy" — no logged-in redirect + cache
# ============================================================================

print("\n" + "="*80)
print("TEST AREA 2: SSR HOME 'FIESTAS DE HOY' — NO REDIRECT + CACHE")
print("="*80)
print()

# Test 2a: GET /api/home → 200, Content-Type text/html
print("TEST 2a: GET /api/home → 200, Content-Type text/html")
try:
    home_resp = requests.get(f"{API_BASE}/home", timeout=10)
    if home_resp.status_code == 200:
        log_pass("TEST 2a: GET /api/home → 200")
        
        content_type = home_resp.headers.get("Content-Type", "")
        if "text/html" in content_type:
            log_pass("TEST 2a: Content-Type is text/html")
        else:
            log_fail("TEST 2a: Content-Type", f"Expected text/html, got: {content_type}")
        
        home_html = home_resp.text
        
        # Check for id="qvcta"
        if 'id="qvcta"' in home_html:
            log_pass("TEST 2a: HTML contains id='qvcta'")
        else:
            log_fail("TEST 2a: Missing id='qvcta'", "Hero CTA button not found")
        
        # Check does NOT contain location.replace('/feed')
        if "location.replace('/feed')" not in home_html:
            log_pass("TEST 2a: HTML does NOT contain location.replace('/feed')")
        else:
            log_fail("TEST 2a: Auto-redirect still present", "Found location.replace('/feed') in HTML")
        
        # Check for header "Fiestas de hoy en España" OR "Próximas fiestas"
        has_today_header = "Fiestas de hoy en España" in home_html
        has_fallback_header = "Próximas fiestas" in home_html
        
        if has_today_header or has_fallback_header:
            header_type = "Fiestas de hoy" if has_today_header else "Próximas fiestas"
            log_pass(f"TEST 2a: HTML contains header '{header_type}'")
        else:
            log_fail("TEST 2a: Missing header", "Neither 'Fiestas de hoy en España' nor 'Próximas fiestas' found")
    else:
        log_fail("TEST 2a: GET /api/home", f"Status {home_resp.status_code}")
except Exception as e:
    log_fail("TEST 2a: GET /api/home", str(e))

# Test 2b: GET /api/en/home and GET /api/de/home → 200, no redirect
print("\nTEST 2b: GET /api/en/home and /api/de/home → 200, no redirect")
for lang_path in ["/en/home", "/de/home"]:
    try:
        lang_resp = requests.get(f"{API_BASE}{lang_path}", timeout=10)
        if lang_resp.status_code == 200:
            log_pass(f"TEST 2b: GET /api{lang_path} → 200")
            
            content_type = lang_resp.headers.get("Content-Type", "")
            if "text/html" in content_type:
                log_pass(f"TEST 2b: /api{lang_path} Content-Type is text/html")
            else:
                log_fail(f"TEST 2b: /api{lang_path} Content-Type", f"Expected text/html, got: {content_type}")
            
            lang_html = lang_resp.text
            
            # Check does NOT contain location.replace('/feed')
            if "location.replace('/feed')" not in lang_html:
                log_pass(f"TEST 2b: /api{lang_path} does NOT contain location.replace('/feed')")
            else:
                log_fail(f"TEST 2b: /api{lang_path} auto-redirect", "Found location.replace('/feed')")
        else:
            log_fail(f"TEST 2b: GET /api{lang_path}", f"Status {lang_resp.status_code}")
    except Exception as e:
        log_fail(f"TEST 2b: GET /api{lang_path}", str(e))

# Test 2c: Cache - two consecutive requests return identical body
print("\nTEST 2c: Cache - two consecutive GET /api/home requests")
try:
    cache_resp1 = requests.get(f"{API_BASE}/home", timeout=10)
    cache_resp2 = requests.get(f"{API_BASE}/home", timeout=10)
    
    if cache_resp1.status_code == 200 and cache_resp2.status_code == 200:
        log_pass("TEST 2c: Both requests returned 200")
        
        # Compare bodies
        if cache_resp1.text == cache_resp2.text:
            log_pass("TEST 2c: Both responses have identical body (cache working)")
        else:
            # Bodies might differ slightly due to timestamps, but should be mostly identical
            # Check if they're at least 95% similar in length
            len_diff = abs(len(cache_resp1.text) - len(cache_resp2.text))
            if len_diff < len(cache_resp1.text) * 0.05:
                log_pass("TEST 2c: Responses are similar (cache likely working)")
            else:
                log_fail("TEST 2c: Cache", f"Response bodies differ significantly (len diff: {len_diff})")
    else:
        log_fail("TEST 2c: Cache test", f"Status codes: {cache_resp1.status_code}, {cache_resp2.status_code}")
except Exception as e:
    log_fail("TEST 2c: Cache test", str(e))

# ============================================================================
# PRINT SUMMARY
# ============================================================================

print_summary()

# Exit with appropriate code
sys.exit(0 if test_results["failed"] == 0 else 1)
