#!/usr/bin/env python3
"""
Backend API Testing Script for ¿Quién va? Multilingual Blog + City Guides
Tests multilingual blog endpoints (ES/EN/DE) with hreflang and city guides block
"""

import requests
import sys
import re
from typing import Dict, Any, List

# Base URL for backend API
BASE_URL = "http://localhost:8001"

# Required headers for all requests (CRITICAL: must be sent on EVERY request)
HEADERS = {
    "x-forwarded-host": "www.quienva.me",
    "x-forwarded-proto": "https"
}

# Expected agenda slugs per language
AGENDA_SLUGS = {
    "es": [
        "agenda-fiestas-finde-madrid",
        "agenda-fiestas-finde-barcelona",
        "agenda-fiestas-finde-ibiza",
        "agenda-fiestas-finde-palma",
        "agenda-fiestas-finde-marbella"
    ],
    "en": [
        "weekend-parties-madrid",
        "weekend-parties-barcelona",
        "weekend-parties-ibiza",
        "weekend-parties-palma",
        "weekend-parties-marbella"
    ],
    "de": [
        "wochenend-partys-madrid",
        "wochenend-partys-barcelona",
        "wochenend-partys-ibiza",
        "wochenend-partys-palma",
        "wochenend-partys-marbella"
    ]
}

def check_hreflang_links(html: str, expected_langs: List[str] = ["es", "en", "de", "x-default"]) -> bool:
    """Check if HTML contains all expected hreflang alternate links"""
    found_langs = []
    for lang in expected_langs:
        pattern = f'<link[^>]+rel=["\']alternate["\'][^>]+hreflang=["\']({lang})["\']'
        if re.search(pattern, html, re.IGNORECASE):
            found_langs.append(lang)
    
    return set(found_langs) == set(expected_langs)

def check_jsonld_schema(html: str, expected_type: str, expected_lang: str = None) -> bool:
    """Check if HTML contains JSON-LD schema with expected @type and optionally inLanguage"""
    # Find all JSON-LD script tags
    jsonld_pattern = r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>'
    matches = re.findall(jsonld_pattern, html, re.DOTALL | re.IGNORECASE)
    
    for match in matches:
        if f'"@type":"{expected_type}"' in match or f'"@type": "{expected_type}"' in match:
            if expected_lang:
                if f'"inLanguage":"{expected_lang}"' in match or f'"inLanguage": "{expected_lang}"' in match:
                    return True
            else:
                return True
    
    return False

def test_blog_index_es():
    """Test 1: GET /api/blog (ES) - must list all 5 agenda slugs + at least one ES static guide"""
    print("\n" + "="*80)
    print("TEST 1: Blog index ES (/api/blog)")
    print("="*80)
    
    url = f"{BASE_URL}/api/blog"
    print(f"\n→ Testing GET {url}")
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        
        if response.status_code != 200:
            print(f"  ❌ FAIL: Expected 200, got {response.status_code}")
            return False
        
        html = response.text
        
        # Check for all 5 ES agenda slugs
        missing_slugs = []
        for slug in AGENDA_SLUGS["es"]:
            if slug not in html:
                missing_slugs.append(slug)
        
        if missing_slugs:
            print(f"  ❌ FAIL: Missing ES agenda slugs: {missing_slugs}")
            return False
        
        print(f"  ✅ All 5 ES agenda slugs found: {AGENDA_SLUGS['es']}")
        
        # Check for at least one ES static guide slug (e.g., mejores-discotecas-madrid)
        static_guide_patterns = [
            "mejores-discotecas-madrid",
            "mejores-discotecas-barcelona",
            "mejores-discotecas-ibiza",
            "donde-salir-esta-noche"
        ]
        
        found_static = False
        found_guide = None
        for guide in static_guide_patterns:
            if guide in html:
                found_static = True
                found_guide = guide
                break
        
        if not found_static:
            print(f"  ❌ FAIL: No ES static guide slug found (expected at least one of: {static_guide_patterns})")
            return False
        
        print(f"  ✅ ES static guide found: {found_guide}")
        print(f"  ✅ PASS: Blog index ES lists all agenda slugs + static guides")
        return True
        
    except Exception as e:
        print(f"  ❌ FAIL: Exception - {e}")
        return False

def test_blog_index_en():
    """Test 2: GET /api/en/blog - title must contain "party & nightclub guides", list all 5 EN agenda slugs"""
    print("\n" + "="*80)
    print("TEST 2: Blog index EN (/api/en/blog)")
    print("="*80)
    
    url = f"{BASE_URL}/api/en/blog"
    print(f"\n→ Testing GET {url}")
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        
        if response.status_code != 200:
            print(f"  ❌ FAIL: Expected 200, got {response.status_code}")
            return False
        
        html = response.text
        
        # Check title contains "party & nightclub guides" (case insensitive)
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        if not title_match:
            print(f"  ❌ FAIL: No <title> tag found")
            return False
        
        title = title_match.group(1).lower()
        if "party" not in title or "nightclub" not in title or "guide" not in title:
            print(f"  ❌ FAIL: Title does not contain 'party & nightclub guides'. Found: {title_match.group(1)}")
            return False
        
        print(f"  ✅ Title contains 'party & nightclub guides': {title_match.group(1)}")
        
        # Check for all 5 EN agenda slugs
        missing_slugs = []
        for slug in AGENDA_SLUGS["en"]:
            if slug not in html:
                missing_slugs.append(slug)
        
        if missing_slugs:
            print(f"  ❌ FAIL: Missing EN agenda slugs: {missing_slugs}")
            return False
        
        print(f"  ✅ All 5 EN agenda slugs found: {AGENDA_SLUGS['en']}")
        print(f"  ✅ PASS: Blog index EN has correct title and lists all agenda slugs")
        return True
        
    except Exception as e:
        print(f"  ❌ FAIL: Exception - {e}")
        return False

def test_blog_index_de():
    """Test 3: GET /api/de/blog - title must contain "Party- & Club-Guides", list all 5 DE agenda slugs"""
    print("\n" + "="*80)
    print("TEST 3: Blog index DE (/api/de/blog)")
    print("="*80)
    
    url = f"{BASE_URL}/api/de/blog"
    print(f"\n→ Testing GET {url}")
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        
        if response.status_code != 200:
            print(f"  ❌ FAIL: Expected 200, got {response.status_code}")
            return False
        
        html = response.text
        
        # Check title contains "Party- & Club-Guides" (case insensitive)
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        if not title_match:
            print(f"  ❌ FAIL: No <title> tag found")
            return False
        
        title = title_match.group(1)
        # Check for "Party" and "Club" and "Guide" (German uses "Guides")
        if not (("party" in title.lower() or "partys" in title.lower()) and 
                "club" in title.lower() and "guide" in title.lower()):
            print(f"  ❌ FAIL: Title does not contain 'Party- & Club-Guides'. Found: {title}")
            return False
        
        print(f"  ✅ Title contains 'Party- & Club-Guides': {title}")
        
        # Check for all 5 DE agenda slugs
        missing_slugs = []
        for slug in AGENDA_SLUGS["de"]:
            if slug not in html:
                missing_slugs.append(slug)
        
        if missing_slugs:
            print(f"  ❌ FAIL: Missing DE agenda slugs: {missing_slugs}")
            return False
        
        print(f"  ✅ All 5 DE agenda slugs found: {AGENDA_SLUGS['de']}")
        print(f"  ✅ PASS: Blog index DE has correct title and lists all agenda slugs")
        return True
        
    except Exception as e:
        print(f"  ❌ FAIL: Exception - {e}")
        return False

def test_blog_post_en_madrid():
    """Test 4: GET /api/en/blog/weekend-parties-madrid - specific title, 4 hreflang, FAQ, BlogPosting JSON-LD with inLanguage "en" """
    print("\n" + "="*80)
    print("TEST 4: Blog post EN Madrid (/api/en/blog/weekend-parties-madrid)")
    print("="*80)
    
    url = f"{BASE_URL}/api/en/blog/weekend-parties-madrid"
    print(f"\n→ Testing GET {url}")
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        
        if response.status_code != 200:
            print(f"  ❌ FAIL: Expected 200, got {response.status_code}")
            return False
        
        html = response.text
        
        # Check title == "Parties this weekend in Madrid: live agenda | ¿Quién va?"
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        if not title_match:
            print(f"  ❌ FAIL: No <title> tag found")
            return False
        
        title = title_match.group(1)
        expected_title_parts = ["Parties this weekend in Madrid", "live agenda", "¿Quién va?"]
        title_ok = all(part.lower() in title.lower() for part in expected_title_parts)
        
        if not title_ok:
            print(f"  ❌ FAIL: Title does not match expected. Found: {title}")
            print(f"         Expected parts: {expected_title_parts}")
            return False
        
        print(f"  ✅ Title correct: {title}")
        
        # Check for 4 hreflang alternate links (es, en, de, x-default)
        if not check_hreflang_links(html, ["es", "en", "de", "x-default"]):
            print(f"  ❌ FAIL: Missing one or more hreflang links (expected: es, en, de, x-default)")
            return False
        
        print(f"  ✅ All 4 hreflang links found (es, en, de, x-default)")
        
        # Check for FAQ block
        if "faq" not in html.lower() or "question" not in html.lower():
            print(f"  ❌ FAIL: FAQ block not found in body")
            return False
        
        print(f"  ✅ FAQ block found")
        
        # Check for BlogPosting JSON-LD with inLanguage "en"
        if not check_jsonld_schema(html, "BlogPosting", "en"):
            print(f"  ❌ FAIL: BlogPosting JSON-LD with inLanguage 'en' not found")
            return False
        
        print(f"  ✅ BlogPosting JSON-LD with inLanguage 'en' found")
        print(f"  ✅ PASS: Blog post EN Madrid has all required elements")
        return True
        
    except Exception as e:
        print(f"  ❌ FAIL: Exception - {e}")
        return False

def test_blog_post_de_ibiza():
    """Test 5: GET /api/de/blog/wochenend-partys-ibiza - German title starting "Partys an diesem Wochenende in Ibiza" """
    print("\n" + "="*80)
    print("TEST 5: Blog post DE Ibiza (/api/de/blog/wochenend-partys-ibiza)")
    print("="*80)
    
    url = f"{BASE_URL}/api/de/blog/wochenend-partys-ibiza"
    print(f"\n→ Testing GET {url}")
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        
        if response.status_code != 200:
            print(f"  ❌ FAIL: Expected 200, got {response.status_code}")
            return False
        
        html = response.text
        
        # Check title starts with "Partys an diesem Wochenende in Ibiza"
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        if not title_match:
            print(f"  ❌ FAIL: No <title> tag found")
            return False
        
        title = title_match.group(1)
        expected_start = "Partys an diesem Wochenende in Ibiza"
        
        if not title.startswith(expected_start):
            print(f"  ❌ FAIL: Title does not start with '{expected_start}'. Found: {title}")
            return False
        
        print(f"  ✅ Title correct: {title}")
        print(f"  ✅ PASS: Blog post DE Ibiza has correct German title")
        return True
        
    except Exception as e:
        print(f"  ❌ FAIL: Exception - {e}")
        return False

def test_blog_post_es_madrid():
    """Test 6: GET /api/blog/agenda-fiestas-finde-madrid - still 200 (ES) and contains hreflang alternate links"""
    print("\n" + "="*80)
    print("TEST 6: Blog post ES Madrid (/api/blog/agenda-fiestas-finde-madrid)")
    print("="*80)
    
    url = f"{BASE_URL}/api/blog/agenda-fiestas-finde-madrid"
    print(f"\n→ Testing GET {url}")
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        
        if response.status_code != 200:
            print(f"  ❌ FAIL: Expected 200, got {response.status_code}")
            return False
        
        html = response.text
        
        # Check for hreflang alternate links
        if not check_hreflang_links(html, ["es", "en", "de", "x-default"]):
            print(f"  ❌ FAIL: Missing one or more hreflang links (expected: es, en, de, x-default)")
            return False
        
        print(f"  ✅ All 4 hreflang links found (es, en, de, x-default)")
        print(f"  ✅ PASS: Blog post ES Madrid returns 200 with hreflang links")
        return True
        
    except Exception as e:
        print(f"  ❌ FAIL: Exception - {e}")
        return False

def test_city_guides_block_es():
    """Test 7: GET /api/ciudad/madrid - must contain guides block heading "Guías y agenda de Madrid" 
    and links to agenda-fiestas-finde-madrid AND mejores-discotecas-madrid AND blog index"""
    print("\n" + "="*80)
    print("TEST 7: City guides block ES (/api/ciudad/madrid)")
    print("="*80)
    
    url = f"{BASE_URL}/api/ciudad/madrid"
    print(f"\n→ Testing GET {url}")
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        
        if response.status_code != 200:
            print(f"  ❌ FAIL: Expected 200, got {response.status_code}")
            return False
        
        html = response.text
        
        # Check for guides block heading "Guías y agenda de Madrid"
        if "Guías y agenda de Madrid" not in html and "Guias y agenda de Madrid" not in html:
            print(f"  ❌ FAIL: Guides block heading 'Guías y agenda de Madrid' not found")
            return False
        
        print(f"  ✅ Guides block heading found: 'Guías y agenda de Madrid'")
        
        # Check for link to agenda-fiestas-finde-madrid
        if "agenda-fiestas-finde-madrid" not in html:
            print(f"  ❌ FAIL: Link to 'agenda-fiestas-finde-madrid' not found")
            return False
        
        print(f"  ✅ Link to 'agenda-fiestas-finde-madrid' found")
        
        # Check for link to mejores-discotecas-madrid (or similar static guide)
        static_guides = ["mejores-discotecas-madrid", "donde-salir-madrid"]
        found_static = False
        for guide in static_guides:
            if guide in html:
                found_static = True
                print(f"  ✅ Link to static guide found: '{guide}'")
                break
        
        if not found_static:
            print(f"  ❌ FAIL: No static guide link found (expected one of: {static_guides})")
            return False
        
        # Check for link to blog index (should contain /blog or similar)
        if "/blog" not in html:
            print(f"  ❌ FAIL: Link to blog index not found")
            return False
        
        print(f"  ✅ Link to blog index found")
        print(f"  ✅ PASS: City guides block ES has all required elements")
        return True
        
    except Exception as e:
        print(f"  ❌ FAIL: Exception - {e}")
        return False

def test_city_guides_block_en():
    """Test 8: GET /api/en/city/madrid - must contain guides block "Madrid guides & weekend agenda" 
    and link to weekend-parties-madrid and "All blog guides" """
    print("\n" + "="*80)
    print("TEST 8: City guides block EN (/api/en/city/madrid)")
    print("="*80)
    
    url = f"{BASE_URL}/api/en/city/madrid"
    print(f"\n→ Testing GET {url}")
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        
        if response.status_code != 200:
            print(f"  ❌ FAIL: Expected 200, got {response.status_code}")
            return False
        
        html = response.text
        
        # Check for guides block heading "Madrid guides & weekend agenda" (case insensitive)
        heading_patterns = [
            "Madrid guides & weekend agenda",
            "Madrid guides and weekend agenda",
            "Madrid guides"
        ]
        
        found_heading = False
        for pattern in heading_patterns:
            if pattern.lower() in html.lower():
                found_heading = True
                print(f"  ✅ Guides block heading found: '{pattern}'")
                break
        
        if not found_heading:
            print(f"  ❌ FAIL: Guides block heading not found (expected one of: {heading_patterns})")
            return False
        
        # Check for link to weekend-parties-madrid
        if "weekend-parties-madrid" not in html:
            print(f"  ❌ FAIL: Link to 'weekend-parties-madrid' not found")
            return False
        
        print(f"  ✅ Link to 'weekend-parties-madrid' found")
        
        # Check for "All blog guides" text (case insensitive)
        if "all blog guides" not in html.lower():
            print(f"  ❌ FAIL: 'All blog guides' text not found")
            return False
        
        print(f"  ✅ 'All blog guides' text found")
        print(f"  ✅ PASS: City guides block EN has all required elements")
        return True
        
    except Exception as e:
        print(f"  ❌ FAIL: Exception - {e}")
        return False

def test_sitemap_blog():
    """Test 9: GET /api/sitemap-blog.xml - must contain all 15 agenda slugs across 3 languages + /en/blog and /de/blog index URLs"""
    print("\n" + "="*80)
    print("TEST 9: Blog sitemap (/api/sitemap-blog.xml)")
    print("="*80)
    
    url = f"{BASE_URL}/api/sitemap-blog.xml"
    print(f"\n→ Testing GET {url}")
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        
        if response.status_code != 200:
            print(f"  ❌ FAIL: Expected 200, got {response.status_code}")
            return False
        
        xml = response.text
        
        # Check all 15 agenda slugs (5 per language)
        all_slugs = AGENDA_SLUGS["es"] + AGENDA_SLUGS["en"] + AGENDA_SLUGS["de"]
        missing_slugs = []
        
        for slug in all_slugs:
            if slug not in xml:
                missing_slugs.append(slug)
        
        if missing_slugs:
            print(f"  ❌ FAIL: Missing agenda slugs in sitemap: {missing_slugs}")
            return False
        
        print(f"  ✅ All 15 agenda slugs found across 3 languages")
        
        # Check for /en/blog index URL
        if "/en/blog" not in xml:
            print(f"  ❌ FAIL: /en/blog index URL not found in sitemap")
            return False
        
        print(f"  ✅ /en/blog index URL found")
        
        # Check for /de/blog index URL
        if "/de/blog" not in xml:
            print(f"  ❌ FAIL: /de/blog index URL not found in sitemap")
            return False
        
        print(f"  ✅ /de/blog index URL found")
        print(f"  ✅ PASS: Blog sitemap contains all required URLs")
        return True
        
    except Exception as e:
        print(f"  ❌ FAIL: Exception - {e}")
        return False

def test_regression():
    """Test 10: Regression tests - /api/home, /api/ciudad/ibiza, /api/de/city/madrid, /api/sitemap.xml, /api/og-city/madrid.jpg"""
    print("\n" + "="*80)
    print("TEST 10: Regression tests")
    print("="*80)
    
    tests = [
        ("/api/home", "text/html", "Home page"),
        ("/api/ciudad/ibiza", "text/html", "City page Ibiza ES"),
        ("/api/de/city/madrid", "text/html", "City page Madrid DE"),
        ("/api/sitemap.xml", "application/xml", "Sitemap index"),
        ("/api/og-city/madrid.jpg", "image/jpeg", "OG image Madrid")
    ]
    
    all_passed = True
    
    for path, expected_content_type, description in tests:
        url = f"{BASE_URL}{path}"
        print(f"\n→ Testing GET {url} ({description})")
        
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            
            if response.status_code != 200:
                print(f"  ❌ FAIL: Expected 200, got {response.status_code}")
                all_passed = False
                continue
            
            content_type = response.headers.get("content-type", "")
            if expected_content_type not in content_type:
                print(f"  ❌ FAIL: Expected content-type {expected_content_type}, got {content_type}")
                all_passed = False
                continue
            
            print(f"  ✅ PASS: 200, content-type={content_type}")
            
        except Exception as e:
            print(f"  ❌ FAIL: Exception - {e}")
            all_passed = False
    
    if all_passed:
        print(f"\n  ✅ PASS: All regression tests passed")
    
    return all_passed

def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("MULTILINGUAL BLOG + CITY GUIDES TESTING")
    print("Testing backend at:", BASE_URL)
    print("Headers:", HEADERS)
    print("="*80)
    
    results = {}
    
    # Run all tests
    results["1. Blog index ES"] = test_blog_index_es()
    results["2. Blog index EN"] = test_blog_index_en()
    results["3. Blog index DE"] = test_blog_index_de()
    results["4. Blog post EN Madrid"] = test_blog_post_en_madrid()
    results["5. Blog post DE Ibiza"] = test_blog_post_de_ibiza()
    results["6. Blog post ES Madrid"] = test_blog_post_es_madrid()
    results["7. City guides block ES"] = test_city_guides_block_es()
    results["8. City guides block EN"] = test_city_guides_block_en()
    results["9. Blog sitemap"] = test_sitemap_blog()
    results["10. Regression tests"] = test_regression()
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print("\n" + "="*80)
    print(f"TOTAL: {passed}/{total} tests passed ({passed*100//total}%)")
    print("="*80)
    
    # Exit with appropriate code
    sys.exit(0 if passed == total else 1)

if __name__ == "__main__":
    main()
