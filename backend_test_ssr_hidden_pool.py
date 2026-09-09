#!/usr/bin/env python3
"""
SSR Home Regression Test - Hidden Pool Feature
Tests home page rendering with visible vs hidden event cards (xtra pool)
"""

import requests
import re
from typing import Dict, List, Tuple

BASE_URL = "http://localhost:8001/api"

def count_visible_cards(html: str) -> int:
    """Count visible event cards with class 'card glow-card reveal' (NOT xtra)"""
    # Match: <a ... class="card glow-card reveal" ... > (no xtra, no style="display:none")
    # Must NOT have 'xtra' in the class attribute
    pattern = r'<a[^>]*class="card glow-card reveal"(?![^>]*xtra)[^>]*>'
    matches = re.findall(pattern, html)
    return len(matches)

def count_hidden_cards(html: str) -> int:
    """Count hidden event cards with class 'card glow-card reveal xtra' and style="display:none" """
    # Match: <a ... class="card glow-card reveal xtra" ... style="display:none" ... >
    pattern = r'<a[^>]*class="card glow-card reveal xtra"[^>]*style="display:none"[^>]*>'
    matches = re.findall(pattern, html)
    return len(matches)

def check_events_section_header(html: str, expected_count: int) -> Tuple[bool, str]:
    """Check events section header shows correct count"""
    # Match: <div class="sech"><h2>Próximas fiestas en España</h2><span>15</span>
    pattern = r'<div class="sech"><h2>[^<]+</h2><span>(\d+)</span>'
    match = re.search(pattern, html)
    if not match:
        return False, "Events section header not found"
    
    count = int(match.group(1))
    if count != expected_count:
        return False, f"Count mismatch: expected {expected_count}, got {count}"
    
    return True, f"Count correct: {count}"

def check_qvbtn_position(html: str) -> Tuple[bool, str]:
    """Check qvbtn button appears AFTER the events grid"""
    # Find position of <ul class="grid">...</ul>
    grid_pattern = r'<ul class="grid">'
    grid_match = re.search(grid_pattern, html)
    if not grid_match:
        return False, "Events grid <ul class=\"grid\"> not found"
    
    grid_pos = grid_match.start()
    
    # Find position of <a id="qvsug" class="qvbtn"
    qvbtn_pattern = r'<a id="qvsug" class="qvbtn"'
    qvbtn_match = re.search(qvbtn_pattern, html)
    if not qvbtn_match:
        return False, "qvbtn button not found"
    
    qvbtn_pos = qvbtn_match.start()
    
    if qvbtn_pos > grid_pos:
        return True, f"qvbtn appears AFTER grid (grid at {grid_pos}, qvbtn at {qvbtn_pos})"
    else:
        return False, f"qvbtn appears BEFORE grid (grid at {grid_pos}, qvbtn at {qvbtn_pos})"

def check_city_data_attribute(html: str) -> Tuple[bool, str]:
    """Check at least one event card has data-s attribute with city keyword"""
    # Match: <a ... class="card glow-card reveal" ... data-s="..." ... > and extract data-s value
    pattern = r'<a[^>]*class="card glow-card reveal"[^>]*data-s="([^"]*)"'
    matches = re.findall(pattern, html)
    
    if not matches:
        return False, "No event cards with data-s attribute found"
    
    # Check if any data-s contains a city keyword (case-insensitive)
    city_keywords = ['madrid', 'barcelona', 'ibiza', 'palma', 'marbella']
    for data_s in matches:
        data_s_lower = data_s.lower()
        for city in city_keywords:
            if city in data_s_lower:
                return True, f"Found data-s with city keyword '{city}': {data_s[:100]}"
    
    return False, f"No data-s attributes contain city keywords. Sample: {matches[0][:100] if matches else 'N/A'}"

def test_home_page(lang_path: str, lang_name: str, expected_visible: int = 15) -> Tuple[bool, List[str]]:
    """Test home page for visible/hidden cards and other requirements"""
    issues = []
    
    print(f"\n{'='*80}")
    print(f"Testing {lang_name} Home Page: {lang_path}")
    print('='*80)
    
    url = f"{BASE_URL}{lang_path}"
    try:
        resp = requests.get(url, timeout=10)
        print(f"✓ GET {lang_path} → {resp.status_code}")
        
        if resp.status_code != 200:
            issues.append(f"Expected 200, got {resp.status_code}")
            return False, issues
        
        html = resp.text
        
        # 1. Count visible cards
        visible_count = count_visible_cards(html)
        print(f"\n1. VISIBLE EVENT CARDS (class='card glow-card reveal', NO xtra):")
        print(f"   Count: {visible_count}")
        if visible_count == expected_visible:
            print(f"   ✓ PASS: Expected {expected_visible}, got {visible_count}")
        else:
            issues.append(f"Visible cards: expected {expected_visible}, got {visible_count}")
            print(f"   ✗ FAIL: Expected {expected_visible}, got {visible_count}")
        
        # 2. Count hidden cards
        hidden_count = count_hidden_cards(html)
        print(f"\n2. HIDDEN EVENT CARDS (class='card glow-card reveal xtra', style='display:none'):")
        print(f"   Count: {hidden_count}")
        if hidden_count > 0:
            print(f"   ✓ PASS: Found {hidden_count} hidden cards (expected several, roughly 35)")
        else:
            issues.append(f"Hidden cards: expected several (roughly 35), got {hidden_count}")
            print(f"   ✗ FAIL: Expected several hidden cards, got {hidden_count}")
        
        # 3. Check events section header
        print(f"\n3. EVENTS SECTION HEADER:")
        header_ok, header_msg = check_events_section_header(html, expected_visible)
        print(f"   {header_msg}")
        if header_ok:
            print(f"   ✓ PASS")
        else:
            issues.append(f"Events section header: {header_msg}")
            print(f"   ✗ FAIL")
        
        # 4. Check qvbtn position
        print(f"\n4. QVBTN BUTTON POSITION:")
        qvbtn_ok, qvbtn_msg = check_qvbtn_position(html)
        print(f"   {qvbtn_msg}")
        if qvbtn_ok:
            print(f"   ✓ PASS")
        else:
            issues.append(f"qvbtn position: {qvbtn_msg}")
            print(f"   ✗ FAIL")
        
        # 5. Check data-s attribute
        print(f"\n5. DATA-S ATTRIBUTE WITH CITY KEYWORD:")
        data_s_ok, data_s_msg = check_city_data_attribute(html)
        print(f"   {data_s_msg}")
        if data_s_ok:
            print(f"   ✓ PASS")
        else:
            issues.append(f"data-s attribute: {data_s_msg}")
            print(f"   ✗ FAIL")
        
        return len(issues) == 0, issues
        
    except Exception as e:
        issues.append(f"Request failed: {e}")
        print(f"✗ Request failed: {e}")
        return False, issues

def test_city_page_no_xtra(city_slug: str) -> Tuple[bool, List[str]]:
    """Test city page has NO xtra substring (hidden pool must not leak)"""
    issues = []
    
    print(f"\n{'='*80}")
    print(f"Testing City Page: /ciudad/{city_slug}")
    print('='*80)
    
    url = f"{BASE_URL}/ciudad/{city_slug}"
    try:
        resp = requests.get(url, timeout=10)
        print(f"✓ GET /ciudad/{city_slug} → {resp.status_code}")
        
        if resp.status_code != 200:
            issues.append(f"Expected 200, got {resp.status_code}")
            return False, issues
        
        html = resp.text
        
        # 1. Check for normal event cards
        normal_cards_pattern = r'<a[^>]*class="card glow-card reveal"[^>]*>'
        normal_cards = re.findall(normal_cards_pattern, html)
        print(f"\n1. NORMAL EVENT CARDS (class='card glow-card reveal'):")
        print(f"   Count: {len(normal_cards)}")
        if len(normal_cards) > 0:
            print(f"   ✓ PASS: Found {len(normal_cards)} normal event cards")
        else:
            issues.append(f"No normal event cards found")
            print(f"   ✗ FAIL: No normal event cards found")
        
        # 2. Check for xtra substring (should be ZERO)
        xtra_count = html.count('xtra')
        print(f"\n2. XTRA SUBSTRING COUNT:")
        print(f"   Count: {xtra_count}")
        if xtra_count == 0:
            print(f"   ✓ PASS: NO 'xtra' substring found (hidden pool not leaked)")
        else:
            issues.append(f"Found {xtra_count} occurrences of 'xtra' substring (hidden pool leaked)")
            print(f"   ✗ FAIL: Found {xtra_count} occurrences of 'xtra' substring")
            
            # Show first few occurrences for debugging
            xtra_pattern = r'.{0,50}xtra.{0,50}'
            xtra_matches = re.findall(xtra_pattern, html, re.IGNORECASE)
            print(f"   First few occurrences:")
            for i, match in enumerate(xtra_matches[:3], 1):
                print(f"     {i}. ...{match}...")
        
        return len(issues) == 0, issues
        
    except Exception as e:
        issues.append(f"Request failed: {e}")
        print(f"✗ Request failed: {e}")
        return False, issues

def test_events_api() -> Tuple[bool, List[str]]:
    """Test /api/events?date_filter=all returns non-empty JSON list"""
    issues = []
    
    print(f"\n{'='*80}")
    print(f"Testing Events API: /events?date_filter=all")
    print('='*80)
    
    url = f"{BASE_URL}/events?date_filter=all"
    try:
        resp = requests.get(url, timeout=10)
        print(f"✓ GET /events?date_filter=all → {resp.status_code}")
        
        if resp.status_code != 200:
            issues.append(f"Expected 200, got {resp.status_code}")
            return False, issues
        
        # Check content-type is JSON
        content_type = resp.headers.get('content-type', '').lower()
        if 'application/json' not in content_type:
            issues.append(f"Expected JSON content-type, got {content_type}")
            print(f"✗ Content-Type: {content_type} (expected application/json)")
            return False, issues
        
        print(f"✓ Content-Type: {content_type}")
        
        # Parse JSON
        try:
            data = resp.json()
        except Exception as e:
            issues.append(f"Failed to parse JSON: {e}")
            print(f"✗ Failed to parse JSON: {e}")
            return False, issues
        
        # Check it's a list
        if not isinstance(data, list):
            issues.append(f"Expected list, got {type(data).__name__}")
            print(f"✗ Expected list, got {type(data).__name__}")
            return False, issues
        
        print(f"✓ Response is a list")
        
        # Check it's non-empty
        if len(data) == 0:
            issues.append("Expected non-empty list, got empty list")
            print(f"✗ List is empty")
            return False, issues
        
        print(f"✓ List is non-empty: {len(data)} events")
        
        return len(issues) == 0, issues
        
    except Exception as e:
        issues.append(f"Request failed: {e}")
        print(f"✗ Request failed: {e}")
        return False, issues

def test_canonical_hreflang(lang_path: str, lang_name: str) -> Tuple[bool, List[str]]:
    """Test canonical and hreflang links are present"""
    issues = []
    
    print(f"\n{'='*80}")
    print(f"Testing Canonical & Hreflang: {lang_name}")
    print('='*80)
    
    url = f"{BASE_URL}{lang_path}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            issues.append(f"GET {lang_path} returned {resp.status_code}")
            return False, issues
        
        html = resp.text
        
        # Check canonical
        canonical_pattern = r'<link\s+rel="canonical"\s+href="([^"]+)"'
        canonical_match = re.search(canonical_pattern, html)
        if not canonical_match:
            issues.append("Missing canonical link")
            print(f"✗ Canonical link: NOT FOUND")
        else:
            canonical_url = canonical_match.group(1)
            print(f"✓ Canonical link: {canonical_url}")
        
        # Check hreflang alternates
        hreflang_pattern = r'<link\s+rel="alternate"\s+hreflang="([^"]+)"\s+href="([^"]+)"'
        hreflang_matches = re.findall(hreflang_pattern, html)
        
        if len(hreflang_matches) < 4:
            issues.append(f"Expected at least 4 hreflang alternates, found {len(hreflang_matches)}")
            print(f"✗ Hreflang alternates: found {len(hreflang_matches)}, expected at least 4")
        else:
            print(f"✓ Hreflang alternates: found {len(hreflang_matches)}")
            for lang, url in hreflang_matches:
                print(f"  - {lang}: {url}")
        
        return len(issues) == 0, issues
        
    except Exception as e:
        issues.append(f"Request failed: {e}")
        print(f"✗ Request failed: {e}")
        return False, issues

def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("SSR HOME REGRESSION TEST - HIDDEN POOL FEATURE")
    print("="*80)
    print("\nTesting focused backend regression on SSR pages:")
    print("- Visible vs hidden event cards (xtra pool)")
    print("- Events section header with count")
    print("- qvbtn button position")
    print("- data-s attribute with city keywords")
    print("- NO xtra substring in city pages")
    print("="*80)
    
    all_passed = True
    all_issues = []
    
    # Test 1: Spanish home page
    print("\n" + "█"*80)
    print("█ TEST 1: GET /api/home (Spanish home)")
    print("█"*80)
    
    passed, issues = test_home_page('/home', 'Spanish (ES)', expected_visible=15)
    if not passed:
        all_passed = False
        all_issues.extend([f"Spanish home: {issue}" for issue in issues])
    
    # Test 2: English home page
    print("\n" + "█"*80)
    print("█ TEST 2: GET /api/en/home (English home)")
    print("█"*80)
    
    passed, issues = test_home_page('/en/home', 'English (EN)', expected_visible=15)
    if not passed:
        all_passed = False
        all_issues.extend([f"English home: {issue}" for issue in issues])
    
    # Test 3: German home page
    print("\n" + "█"*80)
    print("█ TEST 3: GET /api/de/home (German home)")
    print("█"*80)
    
    passed, issues = test_home_page('/de/home', 'German (DE)', expected_visible=15)
    if not passed:
        all_passed = False
        all_issues.extend([f"German home: {issue}" for issue in issues])
    
    # Test 4: City page (Madrid) - NO xtra
    print("\n" + "█"*80)
    print("█ TEST 4: GET /api/ciudad/madrid (NO xtra substring)")
    print("█"*80)
    
    passed, issues = test_city_page_no_xtra('madrid')
    if not passed:
        all_passed = False
        all_issues.extend([f"Madrid city page: {issue}" for issue in issues])
    
    # Test 5: Events API
    print("\n" + "█"*80)
    print("█ TEST 5: GET /api/events?date_filter=all (JSON list)")
    print("█"*80)
    
    passed, issues = test_events_api()
    if not passed:
        all_passed = False
        all_issues.extend([f"Events API: {issue}" for issue in issues])
    
    # Test 6: Canonical & hreflang for EN and DE
    print("\n" + "█"*80)
    print("█ TEST 6: Canonical & Hreflang (EN and DE)")
    print("█"*80)
    
    for lang_path, lang_name in [('/en/home', 'English'), ('/de/home', 'German')]:
        passed, issues = test_canonical_hreflang(lang_path, lang_name)
        if not passed:
            all_passed = False
            all_issues.extend([f"{lang_name} canonical/hreflang: {issue}" for issue in issues])
    
    # Final summary
    print("\n" + "="*80)
    print("FINAL SUMMARY")
    print("="*80)
    
    if all_passed:
        print("\n✅ ALL TESTS PASSED ✅")
        print("\nAll SSR home page requirements verified:")
        print("  ✓ 15 visible event cards on each home page")
        print("  ✓ Hidden pool cards (xtra) present with display:none")
        print("  ✓ Events section header shows correct count")
        print("  ✓ qvbtn button appears AFTER events grid")
        print("  ✓ Event cards have data-s attribute with city keywords")
        print("  ✓ City pages have NO xtra substring (hidden pool not leaked)")
        print("  ✓ Events API returns non-empty JSON list")
        print("  ✓ Canonical and hreflang links present")
    else:
        print(f"\n❌ TESTS FAILED: {len(all_issues)} issues found ❌")
        print("\nIssues:")
        for i, issue in enumerate(all_issues, 1):
            print(f"  {i}. {issue}")
    
    print("\n" + "="*80)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit(main())
