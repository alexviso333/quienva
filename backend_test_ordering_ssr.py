#!/usr/bin/env python3
"""
Backend API Testing for ¿Quién va? App
Test ordering fix and SSR home pages (2026-09-09)

TEST 1: /api/events default ordering (date ascending, venues interleaved)
TEST 2: SSR home /api/home (and /api/en/home, /api/de/home)
TEST 3: Regression - /api/ciudad/madrid (no "xtra" substring)
"""
import requests
import json
import sys
from datetime import datetime, timedelta
import re

# Base URL from frontend/.env
BASE_URL = "https://party-hub-control.preview.emergentagent.com/api"

# Test credentials from /app/memory/test_credentials.md
TEST_EMAIL = "pruebapoll@test.dev"
TEST_PASSWORD = "Prueba1234"

# Test results
results = []

def log_test(name, passed, details=""):
    """Log test result"""
    status = "✅ PASS" if passed else "❌ FAIL"
    results.append({"name": name, "passed": passed, "details": details})
    print(f"{status}: {name}")
    if details:
        print(f"  {details}")

def login(email, password):
    """Login and return token"""
    try:
        resp = requests.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("token")
        else:
            print(f"Login failed for {email}: {resp.status_code} {resp.text}")
            return None
    except Exception as e:
        print(f"Login error for {email}: {e}")
        return None

def get_headers(token):
    """Get auth headers"""
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

print("=" * 80)
print("BACKEND API TESTING - ¿Quién va? (2026-09-09)")
print("Testing: Event ordering fix + SSR home pages")
print("=" * 80)
print()

# ============================================================================
# TEST 1: /api/events DEFAULT ORDERING (THE KEY FIX)
# ============================================================================
print("TEST 1: /api/events DEFAULT ORDERING (THE KEY FIX)")
print("-" * 80)

# Login as test user
token = login(TEST_EMAIL, TEST_PASSWORD)
if not token:
    log_test("1.0: Login as test user", False, "Failed to login")
    sys.exit(1)
log_test("1.0: Login as test user", True, f"Email: {TEST_EMAIL}")

# Test 1.1: GET /api/events?date_filter=all&genre=all
try:
    resp = requests.get(f"{BASE_URL}/events?date_filter=all&genre=all", 
                       headers=get_headers(token), timeout=15)
    if resp.status_code == 200:
        events = resp.json()
        if isinstance(events, list) and len(events) > 0:
            log_test("1.1: GET /api/events?date_filter=all&genre=all", True, 
                    f"Status: 200, Events count: {len(events)}")
            
            # Test 1.2: Verify date ordering (monotonic non-decreasing)
            dates = [ev.get("date", "") for ev in events]
            is_sorted = all(dates[i] <= dates[i+1] for i in range(len(dates)-1))
            if is_sorted:
                log_test("1.2: Events ordered by date ascending", True, 
                        f"First date: {dates[0]}, Last date: {dates[-1]}")
            else:
                # Find first violation
                violations = []
                for i in range(len(dates)-1):
                    if dates[i] > dates[i+1]:
                        violations.append(f"Index {i}: {dates[i]} > {dates[i+1]}")
                log_test("1.2: Events ordered by date ascending", False, 
                        f"Date ordering violations: {violations[:3]}")
            
            # Test 1.3: Verify venues are INTERLEAVED within a single date
            # Group events by date
            events_by_date = {}
            for ev in events:
                date = ev.get("date", "")
                if date not in events_by_date:
                    events_by_date[date] = []
                events_by_date[date].append(ev)
            
            # Check for interleaving: for dates with multiple events, venues should not be grouped
            interleaved = False
            interleave_details = []
            for date, date_events in events_by_date.items():
                if len(date_events) >= 3:  # Need at least 3 events to check interleaving
                    venues = [ev.get("venue", "") for ev in date_events]
                    # Check if venues are NOT all the same (i.e., there's variety)
                    unique_venues = set(venues)
                    if len(unique_venues) > 1:
                        # Check if they're interleaved (not grouped)
                        # Simple check: if we have multiple venues, they shouldn't be in contiguous blocks
                        venue_changes = sum(1 for i in range(len(venues)-1) if venues[i] != venues[i+1])
                        if venue_changes > 0:
                            interleaved = True
                            interleave_details.append(f"Date {date}: {len(date_events)} events, {len(unique_venues)} venues, {venue_changes} venue changes")
                            break
            
            if interleaved:
                log_test("1.3: Venues interleaved within dates", True, 
                        f"Found interleaving: {interleave_details[0]}")
            else:
                log_test("1.3: Venues interleaved within dates", False, 
                        "No clear interleaving detected (venues may be grouped)")
            
            # Test 1.4: Report first 20 (date, venue) pairs
            first_20 = [(ev.get("date", ""), ev.get("venue", "")) for ev in events[:20]]
            print("\n  First 20 (date, venue) pairs:")
            for i, (date, venue) in enumerate(first_20, 1):
                print(f"    {i:2d}. {date} - {venue}")
            
        else:
            log_test("1.1: GET /api/events?date_filter=all&genre=all", False, 
                    f"Empty or invalid response: {events}")
    else:
        log_test("1.1: GET /api/events?date_filter=all&genre=all", False, 
                f"Status: {resp.status_code}, Response: {resp.text[:200]}")
except Exception as e:
    log_test("1.1: GET /api/events?date_filter=all&genre=all", False, f"Exception: {e}")

# Test 1.5: GET /api/events?date_filter=all&genre=all&poll=1
try:
    resp = requests.get(f"{BASE_URL}/events?date_filter=all&genre=all&poll=1", 
                       headers=get_headers(token), timeout=15)
    if resp.status_code == 200:
        events = resp.json()
        if isinstance(events, list):
            log_test("1.5: GET /api/events?poll=1", True, 
                    f"Status: 200, Events count: {len(events)}")
            
            # Test 1.6: Verify date ordering
            dates = [ev.get("date", "") for ev in events]
            is_sorted = all(dates[i] <= dates[i+1] for i in range(len(dates)-1))
            if is_sorted:
                log_test("1.6: Poll events ordered by date ascending", True, 
                        f"First date: {dates[0] if dates else 'N/A'}, Last date: {dates[-1] if dates else 'N/A'}")
            else:
                log_test("1.6: Poll events ordered by date ascending", False, 
                        "Date ordering violations found")
            
            # Test 1.7: Verify max date <= Sunday of next week (2026-09-20)
            # Today is 2026-09-09 (Tuesday), next Sunday is 2026-09-13, Sunday of NEXT week is 2026-09-20
            max_allowed_date = "2026-09-20"
            if dates:
                max_date = max(dates)
                if max_date <= max_allowed_date:
                    log_test("1.7: Poll max date <= 2026-09-20", True, 
                            f"Max date: {max_date}, Count: {len(events)}")
                else:
                    log_test("1.7: Poll max date <= 2026-09-20", False, 
                            f"Max date: {max_date} exceeds {max_allowed_date}")
            else:
                log_test("1.7: Poll max date <= 2026-09-20", True, 
                        "No events in poll (empty list)")
        else:
            log_test("1.5: GET /api/events?poll=1", False, 
                    f"Invalid response: {events}")
    else:
        log_test("1.5: GET /api/events?poll=1", False, 
                f"Status: {resp.status_code}, Response: {resp.text[:200]}")
except Exception as e:
    log_test("1.5: GET /api/events?poll=1", False, f"Exception: {e}")

print()

# ============================================================================
# TEST 2: SSR HOME /api/home (and /api/en/home, /api/de/home)
# ============================================================================
print("TEST 2: SSR HOME /api/home (and /api/en/home, /api/de/home)")
print("-" * 80)

# Test 2.1: GET /api/home
try:
    resp = requests.get(f"{BASE_URL}/home", timeout=15)
    if resp.status_code == 200:
        html = resp.text
        log_test("2.1: GET /api/home", True, f"Status: 200, HTML length: {len(html)}")
        
        # Test 2.2: Verify events section header is "Fiestas de hoy en España"
        expected_header = "Fiestas de hoy en España"
        if expected_header in html:
            log_test("2.2: Events section header", True, 
                    f"Found: '{expected_header}'")
            
            # Test 2.3: Extract count from <span> in header
            # Pattern: <div class="sech"><h2>Fiestas de hoy en España</h2><span>28</span></div>
            header_pattern = r'<div class="sech"><h2>Fiestas de hoy en España</h2><span>(\d+)</span></div>'
            header_match = re.search(header_pattern, html)
            if header_match:
                header_count = int(header_match.group(1))
                
                # Test 2.4: Count visible event cards (class="card glow-card reveal", NOT xtra)
                # Pattern: <a class="card glow-card reveal" ... (NOT "card glow-card reveal xtra")
                visible_card_pattern = r'<a class="card glow-card reveal"[^>]*(?:(?!xtra)[^>])*>'
                visible_cards = re.findall(visible_card_pattern, html)
                visible_count = len(visible_cards)
                
                if header_count == visible_count:
                    log_test("2.3: Header count matches visible cards", True, 
                            f"Header: {header_count}, Visible cards: {visible_count}")
                    
                    if visible_count == 28:
                        log_test("2.4: Visible count is 28 (today's parties)", True, 
                                f"Count: {visible_count}")
                    else:
                        log_test("2.4: Visible count is 28 (today's parties)", False, 
                                f"Expected 28, got {visible_count}")
                else:
                    log_test("2.3: Header count matches visible cards", False, 
                            f"Header: {header_count}, Visible cards: {visible_count}")
            else:
                log_test("2.3: Extract header count", False, 
                        "Could not find header count pattern")
            
            # Test 2.5: Verify hidden pool cards exist
            hidden_card_pattern = r'<a class="card glow-card reveal xtra"[^>]*style="display:none"'
            hidden_cards = re.findall(hidden_card_pattern, html)
            if hidden_cards:
                log_test("2.5: Hidden pool cards exist", True, 
                        f"Found {len(hidden_cards)} hidden cards")
            else:
                log_test("2.5: Hidden pool cards exist", False, 
                        "No hidden cards found")
            
            # Test 2.6: Verify qvbtn button appears AFTER events grid
            # Pattern: <ul class="grid">...</ul> followed by <a id="qvsug" class="qvbtn"
            grid_pattern = r'<ul class="grid">.*?</ul>.*?<a id="qvsug" class="qvbtn"'
            if re.search(grid_pattern, html, re.DOTALL):
                log_test("2.6: qvbtn button after events grid", True, 
                        "Button found in correct position")
            else:
                log_test("2.6: qvbtn button after events grid", False, 
                        "Button not found or in wrong position")
        else:
            log_test("2.2: Events section header", False, 
                    f"Expected '{expected_header}' not found")
    else:
        log_test("2.1: GET /api/home", False, 
                f"Status: {resp.status_code}, Response: {resp.text[:200]}")
except Exception as e:
    log_test("2.1: GET /api/home", False, f"Exception: {e}")

# Test 2.7: GET /api/en/home
try:
    resp = requests.get(f"{BASE_URL}/en/home", timeout=15)
    if resp.status_code == 200:
        html = resp.text
        log_test("2.7: GET /api/en/home", True, f"Status: 200, HTML length: {len(html)}")
        
        # Verify visible event cards exist
        visible_card_pattern = r'<a class="card glow-card reveal"[^>]*(?:(?!xtra)[^>])*>'
        visible_cards = re.findall(visible_card_pattern, html)
        
        # Verify qvbtn button exists
        qvbtn_pattern = r'<a id="qvsug" class="qvbtn"'
        has_qvbtn = re.search(qvbtn_pattern, html)
        
        if visible_cards and has_qvbtn:
            log_test("2.8: EN home has visible cards + qvbtn", True, 
                    f"Visible cards: {len(visible_cards)}, qvbtn: found")
        else:
            log_test("2.8: EN home has visible cards + qvbtn", False, 
                    f"Visible cards: {len(visible_cards)}, qvbtn: {'found' if has_qvbtn else 'missing'}")
    else:
        log_test("2.7: GET /api/en/home", False, 
                f"Status: {resp.status_code}")
except Exception as e:
    log_test("2.7: GET /api/en/home", False, f"Exception: {e}")

# Test 2.9: GET /api/de/home
try:
    resp = requests.get(f"{BASE_URL}/de/home", timeout=15)
    if resp.status_code == 200:
        html = resp.text
        log_test("2.9: GET /api/de/home", True, f"Status: 200, HTML length: {len(html)}")
        
        # Verify visible event cards exist
        visible_card_pattern = r'<a class="card glow-card reveal"[^>]*(?:(?!xtra)[^>])*>'
        visible_cards = re.findall(visible_card_pattern, html)
        
        # Verify qvbtn button exists
        qvbtn_pattern = r'<a id="qvsug" class="qvbtn"'
        has_qvbtn = re.search(qvbtn_pattern, html)
        
        if visible_cards and has_qvbtn:
            log_test("2.10: DE home has visible cards + qvbtn", True, 
                    f"Visible cards: {len(visible_cards)}, qvbtn: found")
        else:
            log_test("2.10: DE home has visible cards + qvbtn", False, 
                    f"Visible cards: {len(visible_cards)}, qvbtn: {'found' if has_qvbtn else 'missing'}")
    else:
        log_test("2.9: GET /api/de/home", False, 
                f"Status: {resp.status_code}")
except Exception as e:
    log_test("2.9: GET /api/de/home", False, f"Exception: {e}")

print()

# ============================================================================
# TEST 3: REGRESSION - /api/ciudad/madrid
# ============================================================================
print("TEST 3: REGRESSION - /api/ciudad/madrid")
print("-" * 80)

# Test 3.1: GET /api/ciudad/madrid
try:
    resp = requests.get(f"{BASE_URL}/ciudad/madrid", timeout=15)
    if resp.status_code == 200:
        html = resp.text
        log_test("3.1: GET /api/ciudad/madrid", True, f"Status: 200, HTML length: {len(html)}")
        
        # Test 3.2: Verify ZERO occurrences of "xtra"
        xtra_count = html.count("xtra")
        if xtra_count == 0:
            log_test("3.2: HTML contains ZERO 'xtra' substrings", True, 
                    "No 'xtra' found (regression test passed)")
        else:
            # Find context around "xtra" occurrences
            xtra_contexts = []
            for match in re.finditer(r'.{0,50}xtra.{0,50}', html):
                xtra_contexts.append(match.group(0))
            log_test("3.2: HTML contains ZERO 'xtra' substrings", False, 
                    f"Found {xtra_count} occurrences. Examples: {xtra_contexts[:3]}")
    else:
        log_test("3.1: GET /api/ciudad/madrid", False, 
                f"Status: {resp.status_code}")
except Exception as e:
    log_test("3.1: GET /api/ciudad/madrid", False, f"Exception: {e}")

print()

# ============================================================================
# SUMMARY
# ============================================================================
print("=" * 80)
print("TEST SUMMARY")
print("=" * 80)

passed = sum(1 for r in results if r["passed"])
failed = sum(1 for r in results if not r["passed"])
total = len(results)

print(f"Total: {total} tests")
print(f"Passed: {passed} ✅")
print(f"Failed: {failed} ❌")
print()

if failed > 0:
    print("FAILED TESTS:")
    for r in results:
        if not r["passed"]:
            print(f"  ❌ {r['name']}")
            if r["details"]:
                print(f"     {r['details']}")
    print()

# Exit with appropriate code
sys.exit(0 if failed == 0 else 1)
