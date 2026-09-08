#!/usr/bin/env python3
"""
SSR Home Regression Test - Smart City Search Feature
Tests home page rendering in all 3 languages with new search wiring + regression tests
"""

import requests
import re
import json
from typing import Dict, List, Tuple

BASE_URL = "http://localhost:8001/api"

def test_home_language(lang_path: str, expected_qvsp: str, lang_name: str) -> Tuple[bool, List[str]]:
    """Test home page for a specific language"""
    issues = []
    
    print(f"\n{'='*80}")
    print(f"Testing {lang_name} Home Page: {lang_path}")
    print('='*80)
    
    # 1. GET request
    url = f"{BASE_URL}{lang_path}"
    try:
        resp = requests.get(url, timeout=10)
        print(f"✓ GET {lang_path} → {resp.status_code}")
        
        if resp.status_code != 200:
            issues.append(f"Expected 200, got {resp.status_code}")
            return False, issues
            
        html = resp.text
        
        # 2. Check for <form class="finder" ... onsubmit="return qvGo(event)">
        form_pattern = r'<form[^>]*class="[^"]*finder[^"]*"[^>]*onsubmit="return qvGo\(event\)"'
        if not re.search(form_pattern, html):
            issues.append("Missing <form class=\"finder\" ... onsubmit=\"return qvGo(event)\">")
            print(f"✗ Form with finder class and qvGo onsubmit: NOT FOUND")
        else:
            print(f"✓ Form with finder class and qvGo onsubmit: FOUND")
        
        # 3. Check for <input id="qvf" ...>
        input_pattern = r'<input[^>]*id="qvf"'
        if not re.search(input_pattern, html):
            issues.append("Missing <input id=\"qvf\" ...>")
            print(f"✗ Input with id=\"qvf\": NOT FOUND")
        else:
            print(f"✓ Input with id=\"qvf\": FOUND")
        
        # 4. Check for <a id="qvsug" ...>
        link_pattern = r'<a[^>]*id="qvsug"'
        if not re.search(link_pattern, html):
            issues.append("Missing <a id=\"qvsug\" ...>")
            print(f"✗ Link with id=\"qvsug\": NOT FOUND")
        else:
            print(f"✓ Link with id=\"qvsug\": FOUND")
        
        # 5. Check for inline script with "var QVNAV=["
        qvnav_pattern = r'var\s+QVNAV\s*=\s*\['
        qvnav_match = re.search(qvnav_pattern, html)
        if not qvnav_match:
            issues.append("Missing inline script with 'var QVNAV=['")
            print(f"✗ Inline script with 'var QVNAV=[': NOT FOUND")
        else:
            print(f"✓ Inline script with 'var QVNAV=[': FOUND")
            
            # Extract QVNAV array
            qvnav_full_pattern = r'var\s+QVNAV\s*=\s*(\[[^\]]+\]);'
            qvnav_full_match = re.search(qvnav_full_pattern, html)
            if qvnav_full_match:
                try:
                    qvnav_str = qvnav_full_match.group(1)
                    qvnav_array = json.loads(qvnav_str)
                    print(f"  QVNAV array length: {len(qvnav_array)}")
                    
                    if len(qvnav_array) != 5:
                        issues.append(f"QVNAV array should have 5 cities, found {len(qvnav_array)}")
                        print(f"  ✗ Expected 5 cities, found {len(qvnav_array)}")
                    else:
                        print(f"  ✓ QVNAV has 5 cities")
                    
                    # Check each city has keys k, u, l
                    for i, city in enumerate(qvnav_array):
                        if not all(key in city for key in ['k', 'u', 'l']):
                            issues.append(f"QVNAV city {i} missing required keys (k/u/l)")
                            print(f"  ✗ City {i}: missing keys - has {list(city.keys())}")
                        else:
                            print(f"  ✓ City {i}: {city.get('l', 'N/A')} - u={city.get('u', 'N/A')[:50]}...")
                            
                            # Check URL format (should point to city listing)
                            url_val = city.get('u', '')
                            expected_cities = ['madrid', 'ibiza', 'barcelona', 'palma', 'marbella']
                            if not any(f'/fiestas/{c}' in url_val or f'/parties/{c}' in url_val or f'/partys/{c}' in url_val for c in expected_cities):
                                issues.append(f"QVNAV city {i} URL doesn't match expected pattern: {url_val}")
                                print(f"    ✗ URL doesn't match expected city listing pattern")
                            
                            # Check keywords array
                            keywords = city.get('k', [])
                            if not isinstance(keywords, list) or len(keywords) == 0:
                                issues.append(f"QVNAV city {i} has no keywords array")
                                print(f"    ✗ No keywords array")
                            else:
                                print(f"    ✓ Keywords: {keywords}")
                    
                    # Print all entries
                    print(f"\n  Full QVNAV array:")
                    for i, city in enumerate(qvnav_array):
                        print(f"    [{i}] {city.get('l', 'N/A')}")
                        print(f"        URL: {city.get('u', 'N/A')}")
                        print(f"        Keywords: {city.get('k', [])}")
                        
                except json.JSONDecodeError as e:
                    issues.append(f"QVNAV array is not valid JSON: {e}")
                    print(f"  ✗ QVNAV array is not valid JSON: {e}")
        
        # 6. Check for "var QVSP="
        qvsp_pattern = r'var\s+QVSP\s*=\s*["\']([^"\']+)["\']'
        qvsp_match = re.search(qvsp_pattern, html)
        if not qvsp_match:
            issues.append("Missing inline script with 'var QVSP='")
            print(f"✗ Inline script with 'var QVSP=': NOT FOUND")
        else:
            qvsp_value = qvsp_match.group(1)
            print(f"✓ Inline script with 'var QVSP=': FOUND")
            print(f"  QVSP value: \"{qvsp_value}\"")
            
            if qvsp_value != expected_qvsp:
                issues.append(f"QVSP value mismatch: expected \"{expected_qvsp}\", got \"{qvsp_value}\"")
                print(f"  ✗ Expected: \"{expected_qvsp}\"")
            else:
                print(f"  ✓ QVSP value matches expected: \"{expected_qvsp}\"")
        
        return len(issues) == 0, issues
        
    except Exception as e:
        issues.append(f"Request failed: {e}")
        print(f"✗ Request failed: {e}")
        return False, issues


def test_regression_canonical_hreflang(lang_path: str, lang_name: str) -> Tuple[bool, List[str]]:
    """Test regression: canonical and hreflang tags"""
    issues = []
    
    print(f"\n{'='*80}")
    print(f"Testing Regression - Canonical & Hreflang: {lang_name}")
    print('='*80)
    
    url = f"{BASE_URL}{lang_path}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            issues.append(f"GET {lang_path} returned {resp.status_code}")
            return False, issues
        
        html = resp.text
        
        # Check self-referencing canonical
        canonical_pattern = r'<link\s+rel="canonical"\s+href="([^"]+)"'
        canonical_match = re.search(canonical_pattern, html)
        if not canonical_match:
            issues.append("Missing canonical link")
            print(f"✗ Canonical link: NOT FOUND")
        else:
            canonical_url = canonical_match.group(1)
            print(f"✓ Canonical link: {canonical_url}")
            
            # Check it's self-referencing (should be the home page for that language)
            # Home pages have canonical URLs like: / (es), /en (en), /de (de)
            # This is correct - they're the root pages for each language
            if lang_path == '/home':
                expected_canonical = '/'
            elif lang_path == '/en/home':
                expected_canonical = '/en'
            elif lang_path == '/de/home':
                expected_canonical = '/de'
            else:
                expected_canonical = None
            
            if expected_canonical and not canonical_url.endswith(expected_canonical):
                issues.append(f"Canonical URL doesn't match expected: {canonical_url} (expected to end with {expected_canonical})")
                print(f"  ⚠ Expected to end with: {expected_canonical}")
            else:
                print(f"  ✓ Canonical is self-referencing home page")
        
        # Check hreflang alternates (es, en, de, x-default)
        hreflang_pattern = r'<link\s+rel="alternate"\s+hreflang="([^"]+)"\s+href="([^"]+)"'
        hreflang_matches = re.findall(hreflang_pattern, html)
        
        if len(hreflang_matches) < 4:
            issues.append(f"Expected at least 4 hreflang alternates (es/en/de/x-default), found {len(hreflang_matches)}")
            print(f"✗ Hreflang alternates: found {len(hreflang_matches)}, expected at least 4")
        else:
            print(f"✓ Hreflang alternates: found {len(hreflang_matches)}")
            
        hreflang_langs = [lang for lang, url in hreflang_matches]
        expected_langs = ['es', 'en', 'de', 'x-default']
        for expected_lang in expected_langs:
            if expected_lang in hreflang_langs:
                print(f"  ✓ hreflang=\"{expected_lang}\" present")
            else:
                issues.append(f"Missing hreflang=\"{expected_lang}\"")
                print(f"  ✗ hreflang=\"{expected_lang}\" missing")
        
        # Check non-render-blocking font link (media="print" onload)
        font_pattern = r'<link[^>]*rel="stylesheet"[^>]*media="print"[^>]*onload='
        if not re.search(font_pattern, html):
            issues.append("Missing non-render-blocking font link (media=\"print\" onload)")
            print(f"✗ Non-render-blocking font link: NOT FOUND")
        else:
            print(f"✓ Non-render-blocking font link: FOUND")
        
        return len(issues) == 0, issues
        
    except Exception as e:
        issues.append(f"Request failed: {e}")
        print(f"✗ Request failed: {e}")
        return False, issues


def test_event_pages() -> Tuple[bool, List[str]]:
    """Test regression: event pages in all languages"""
    issues = []
    
    print(f"\n{'='*80}")
    print(f"Testing Regression - Event Pages")
    print('='*80)
    
    event_id = "test-ev-0"
    paths = [
        ('/fiesta/test-ev-0', 'Spanish'),
        ('/en/party/test-ev-0', 'English'),
        ('/de/party/test-ev-0', 'German')
    ]
    
    for path, lang_name in paths:
        url = f"{BASE_URL}{path}"
        try:
            resp = requests.get(url, timeout=10)
            print(f"\n{lang_name}: GET {path} → {resp.status_code}")
            
            if resp.status_code != 200:
                issues.append(f"{lang_name} event page returned {resp.status_code}")
                print(f"  ✗ Expected 200")
                continue
            
            html = resp.text
            
            # Check self-referencing canonical
            canonical_pattern = r'<link\s+rel="canonical"\s+href="([^"]+)"'
            canonical_match = re.search(canonical_pattern, html)
            if canonical_match:
                print(f"  ✓ Canonical: {canonical_match.group(1)}")
            else:
                issues.append(f"{lang_name} event page missing canonical")
                print(f"  ✗ Canonical: NOT FOUND")
            
            # Check for unique <section class="lead"> paragraph
            lead_pattern = r'<section[^>]*class="[^"]*lead[^"]*"[^>]*>.*?</section>'
            if re.search(lead_pattern, html, re.DOTALL):
                print(f"  ✓ <section class=\"lead\"> present")
            else:
                issues.append(f"{lang_name} event page missing <section class=\"lead\">")
                print(f"  ✗ <section class=\"lead\"> NOT FOUND")
                
        except Exception as e:
            issues.append(f"{lang_name} event page request failed: {e}")
            print(f"  ✗ Request failed: {e}")
    
    return len(issues) == 0, issues


def test_city_pages() -> Tuple[bool, List[str]]:
    """Test regression: city pages in all languages"""
    issues = []
    
    print(f"\n{'='*80}")
    print(f"Testing Regression - City Pages")
    print('='*80)
    
    paths = [
        ('/ciudad/ibiza', 'Spanish'),
        ('/en/city/ibiza', 'English'),
        ('/de/city/ibiza', 'German')
    ]
    
    for path, lang_name in paths:
        url = f"{BASE_URL}{path}"
        try:
            resp = requests.get(url, timeout=10)
            print(f"\n{lang_name}: GET {path} → {resp.status_code}")
            
            if resp.status_code != 200:
                issues.append(f"{lang_name} city page returned {resp.status_code}")
                print(f"  ✗ Expected 200")
                continue
            
            html = resp.text
            
            # Check for localized city tips block
            # Look for common patterns in city pages
            tips_patterns = [
                r'<section[^>]*class="[^"]*tips[^"]*"',
                r'<div[^>]*class="[^"]*city-info[^"]*"',
                r'<article[^>]*class="[^"]*guide[^"]*"'
            ]
            
            found_tips = False
            for pattern in tips_patterns:
                if re.search(pattern, html):
                    found_tips = True
                    break
            
            if found_tips:
                print(f"  ✓ City tips/info block present")
            else:
                # This is a soft check - just note it
                print(f"  ⚠ City tips block not clearly identified (may be present with different structure)")
            
            # Check canonical
            canonical_pattern = r'<link\s+rel="canonical"\s+href="([^"]+)"'
            canonical_match = re.search(canonical_pattern, html)
            if canonical_match:
                print(f"  ✓ Canonical: {canonical_match.group(1)}")
            else:
                issues.append(f"{lang_name} city page missing canonical")
                print(f"  ✗ Canonical: NOT FOUND")
                
        except Exception as e:
            issues.append(f"{lang_name} city page request failed: {e}")
            print(f"  ✗ Request failed: {e}")
    
    return len(issues) == 0, issues


def test_static_endpoints() -> Tuple[bool, List[str]]:
    """Test regression: robots.txt, sitemap.xml, llms.txt"""
    issues = []
    
    print(f"\n{'='*80}")
    print(f"Testing Regression - Static Endpoints")
    print('='*80)
    
    endpoints = [
        ('/robots.txt', 'text/plain'),
        ('/sitemap.xml', 'application/xml'),
        ('/llms.txt', 'text/plain')
    ]
    
    for path, expected_content_type in endpoints:
        url = f"{BASE_URL}{path}"
        try:
            resp = requests.get(url, timeout=10)
            print(f"\nGET {path} → {resp.status_code}")
            
            if resp.status_code != 200:
                issues.append(f"{path} returned {resp.status_code}")
                print(f"  ✗ Expected 200")
                continue
            
            print(f"  ✓ Status: 200")
            
            content_type = resp.headers.get('content-type', '').lower()
            if expected_content_type.lower() in content_type:
                print(f"  ✓ Content-Type: {content_type}")
            else:
                issues.append(f"{path} wrong content-type: expected {expected_content_type}, got {content_type}")
                print(f"  ✗ Content-Type: expected {expected_content_type}, got {content_type}")
            
            # Show snippet of content
            content_snippet = resp.text[:200]
            print(f"  Content snippet: {content_snippet[:100]}...")
                
        except Exception as e:
            issues.append(f"{path} request failed: {e}")
            print(f"  ✗ Request failed: {e}")
    
    return len(issues) == 0, issues


def test_nonexistent_event() -> Tuple[bool, List[str]]:
    """Test regression: nonexistent event returns 410 or 301"""
    issues = []
    
    print(f"\n{'='*80}")
    print(f"Testing Regression - Nonexistent Event")
    print('='*80)
    
    url = f"{BASE_URL}/fiesta/nope-xyz"
    try:
        resp = requests.get(url, timeout=10, allow_redirects=False)
        print(f"GET /fiesta/nope-xyz → {resp.status_code}")
        
        if resp.status_code in [410, 301]:
            print(f"  ✓ Status: {resp.status_code} (expected 410 or 301)")
        elif resp.status_code == 200:
            issues.append("Nonexistent event returned 200 (should be 410 or 301)")
            print(f"  ✗ Status: 200 (should be 410 or 301)")
        else:
            issues.append(f"Nonexistent event returned unexpected status {resp.status_code}")
            print(f"  ⚠ Status: {resp.status_code} (expected 410 or 301)")
            
    except Exception as e:
        issues.append(f"Nonexistent event request failed: {e}")
        print(f"  ✗ Request failed: {e}")
    
    return len(issues) == 0, issues


def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("SSR HOME REGRESSION TEST - SMART CITY SEARCH FEATURE")
    print("="*80)
    
    all_passed = True
    all_issues = []
    
    # Test 1: Home renders in all 3 languages with new search wiring
    print("\n" + "█"*80)
    print("█ TEST SUITE 1: HOME PAGE RENDERING IN ALL 3 LANGUAGES")
    print("█"*80)
    
    languages = [
        ('/home', 'Ver todas las fiestas en', 'Spanish (ES)'),
        ('/en/home', 'See all parties in', 'English (EN)'),
        ('/de/home', 'Alle Partys in', 'German (DE)')
    ]
    
    for lang_path, expected_qvsp, lang_name in languages:
        passed, issues = test_home_language(lang_path, expected_qvsp, lang_name)
        if not passed:
            all_passed = False
            all_issues.extend([f"{lang_name}: {issue}" for issue in issues])
    
    # Test 2: Regression - canonical, hreflang, fonts
    print("\n" + "█"*80)
    print("█ TEST SUITE 2: REGRESSION - CANONICAL, HREFLANG, FONTS")
    print("█"*80)
    
    for lang_path, _, lang_name in languages:
        passed, issues = test_regression_canonical_hreflang(lang_path, lang_name)
        if not passed:
            all_passed = False
            all_issues.extend([f"{lang_name} regression: {issue}" for issue in issues])
    
    # Test 3: Regression - event pages
    print("\n" + "█"*80)
    print("█ TEST SUITE 3: REGRESSION - EVENT PAGES")
    print("█"*80)
    
    passed, issues = test_event_pages()
    if not passed:
        all_passed = False
        all_issues.extend([f"Event pages: {issue}" for issue in issues])
    
    # Test 4: Regression - city pages
    print("\n" + "█"*80)
    print("█ TEST SUITE 4: REGRESSION - CITY PAGES")
    print("█"*80)
    
    passed, issues = test_city_pages()
    if not passed:
        all_passed = False
        all_issues.extend([f"City pages: {issue}" for issue in issues])
    
    # Test 5: Regression - static endpoints
    print("\n" + "█"*80)
    print("█ TEST SUITE 5: REGRESSION - STATIC ENDPOINTS")
    print("█"*80)
    
    passed, issues = test_static_endpoints()
    if not passed:
        all_passed = False
        all_issues.extend([f"Static endpoints: {issue}" for issue in issues])
    
    # Test 6: Regression - nonexistent event
    print("\n" + "█"*80)
    print("█ TEST SUITE 6: REGRESSION - NONEXISTENT EVENT")
    print("█"*80)
    
    passed, issues = test_nonexistent_event()
    if not passed:
        all_passed = False
        all_issues.extend([f"Nonexistent event: {issue}" for issue in issues])
    
    # Final summary
    print("\n" + "="*80)
    print("FINAL SUMMARY")
    print("="*80)
    
    if all_passed:
        print("\n✅ ALL TESTS PASSED ✅")
        print("\nThe SSR home page with smart city-search feature is working correctly.")
        print("All regression tests passed - no existing functionality was broken.")
    else:
        print(f"\n❌ TESTS FAILED: {len(all_issues)} issues found ❌")
        print("\nIssues:")
        for i, issue in enumerate(all_issues, 1):
            print(f"  {i}. {issue}")
    
    print("\n" + "="*80)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit(main())
