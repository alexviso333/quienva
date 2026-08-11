#!/usr/bin/env python3
"""
Backend API Testing Script for ¿Quién va? - EN/DE Evergreen Guides + Momentos Highlight Fallback
Tests multilingual blog posts and authenticated stories endpoint
"""

import requests
import sys
import json
from typing import Dict, Any

# Base URL for backend API
BASE_URL = "http://localhost:8001"

# Required headers for PUBLIC requests (blog/city/sitemap)
PUBLIC_HEADERS = {
    "x-forwarded-host": "www.quienva.me",
    "x-forwarded-proto": "https"
}

# Auth token for Momentos test (from /app/memory/test_credentials.md)
AUTH_TOKEN = "qvtest_8546d7e84b6d4428b99f039104181221"

def test_en_blog_best_parties_ibiza():
    """Test A1: GET /api/en/blog/best-parties-ibiza-summer"""
    print("\n" + "="*80)
    print("TEST A1: EN blog - Best parties in Ibiza this summer")
    print("="*80)
    
    url = f"{BASE_URL}/api/en/blog/best-parties-ibiza-summer"
    print(f"\n→ Testing GET {url}")
    
    try:
        response = requests.get(url, headers=PUBLIC_HEADERS, timeout=10)
        
        if response.status_code != 200:
            print(f"  ❌ FAIL: Expected 200, got {response.status_code}")
            return False
        
        html = response.text
        
        # Check title
        expected_title = "Best parties in Ibiza this summer: complete 2025 guide | ¿Quién va?"
        if expected_title not in html:
            print(f"  ❌ FAIL: Expected title '{expected_title}' not found")
            # Try to find what title is present
            import re
            title_match = re.search(r'<title>([^<]+)</title>', html)
            if title_match:
                print(f"     Found title: {title_match.group(1)}")
            return False
        
        # Check for 4 hreflang alternates (es, en, de, x-default)
        hreflang_langs = ['es', 'en', 'de', 'x-default']
        missing_hreflang = []
        for lang in hreflang_langs:
            if f'hreflang="{lang}"' not in html and f"hreflang='{lang}'" not in html:
                missing_hreflang.append(lang)
        
        if missing_hreflang:
            print(f"  ❌ FAIL: Missing hreflang alternates: {', '.join(missing_hreflang)}")
            return False
        
        # Check for BlogPosting JSON-LD with inLanguage "en"
        if 'application/ld+json' not in html:
            print(f"  ❌ FAIL: No application/ld+json found")
            return False
        
        has_blog_posting = ('"@type":"BlogPosting"' in html or '"@type": "BlogPosting"' in html)
        if not has_blog_posting:
            print(f"  ❌ FAIL: BlogPosting JSON-LD not found")
            return False
        
        has_in_language_en = ('"inLanguage":"en"' in html or '"inLanguage": "en"' in html)
        if not has_in_language_en:
            print(f"  ❌ FAIL: inLanguage 'en' not found in JSON-LD")
            return False
        
        print(f"  ✅ PASS: 200, correct title, 4 hreflang alternates, BlogPosting JSON-LD with inLanguage 'en'")
        return True
        
    except Exception as e:
        print(f"  ❌ FAIL: Exception - {e}")
        return False


def test_de_blog_guenstige_disco_tickets():
    """Test A2: GET /api/de/blog/guenstige-disco-tickets"""
    print("\n" + "="*80)
    print("TEST A2: DE blog - Günstige Disco-Tickets")
    print("="*80)
    
    url = f"{BASE_URL}/api/de/blog/guenstige-disco-tickets"
    print(f"\n→ Testing GET {url}")
    
    try:
        response = requests.get(url, headers=PUBLIC_HEADERS, timeout=10)
        
        if response.status_code != 200:
            print(f"  ❌ FAIL: Expected 200, got {response.status_code}")
            return False
        
        html = response.text
        
        # Check title starts with "So bekommst du günstige"
        import re
        title_match = re.search(r'<title>([^<]+)</title>', html)
        if not title_match:
            print(f"  ❌ FAIL: No <title> tag found")
            return False
        
        title = title_match.group(1)
        if not title.startswith("So bekommst du günstige"):
            print(f"  ❌ FAIL: Title does not start with 'So bekommst du günstige'")
            print(f"     Found title: {title}")
            return False
        
        print(f"  ✅ PASS: 200, German title starts with 'So bekommst du günstige'")
        print(f"     Full title: {title}")
        return True
        
    except Exception as e:
        print(f"  ❌ FAIL: Exception - {e}")
        return False


def test_es_blog_mejores_fiestas_ibiza_hreflang():
    """Test A3: GET /api/blog/mejores-fiestas-ibiza-verano - now has 4 hreflang alternates"""
    print("\n" + "="*80)
    print("TEST A3: ES blog - Mejores fiestas Ibiza verano (hreflang cross-links)")
    print("="*80)
    
    url = f"{BASE_URL}/api/blog/mejores-fiestas-ibiza-verano"
    print(f"\n→ Testing GET {url}")
    
    try:
        response = requests.get(url, headers=PUBLIC_HEADERS, timeout=10)
        
        if response.status_code != 200:
            print(f"  ❌ FAIL: Expected 200, got {response.status_code}")
            return False
        
        html = response.text
        
        # Check for 4 hreflang alternates (es, en, de, x-default)
        hreflang_langs = ['es', 'en', 'de', 'x-default']
        missing_hreflang = []
        for lang in hreflang_langs:
            if f'hreflang="{lang}"' not in html and f"hreflang='{lang}'" not in html:
                missing_hreflang.append(lang)
        
        if missing_hreflang:
            print(f"  ❌ FAIL: Missing hreflang alternates: {', '.join(missing_hreflang)}")
            return False
        
        print(f"  ✅ PASS: 200, contains 4 hreflang alternate links (cross-linked to EN/DE versions)")
        return True
        
    except Exception as e:
        print(f"  ❌ FAIL: Exception - {e}")
        return False


def test_en_blog_index():
    """Test A4: GET /api/en/blog - lists both EN evergreen guides"""
    print("\n" + "="*80)
    print("TEST A4: EN blog index - lists evergreen guides")
    print("="*80)
    
    url = f"{BASE_URL}/api/en/blog"
    print(f"\n→ Testing GET {url}")
    
    try:
        response = requests.get(url, headers=PUBLIC_HEADERS, timeout=10)
        
        if response.status_code != 200:
            print(f"  ❌ FAIL: Expected 200, got {response.status_code}")
            return False
        
        html = response.text
        
        # Check for both EN evergreen guide slugs
        required_slugs = [
            "best-parties-ibiza-summer",
            "cheap-nightclub-tickets"
        ]
        
        missing_slugs = []
        for slug in required_slugs:
            if slug not in html:
                missing_slugs.append(slug)
        
        if missing_slugs:
            print(f"  ❌ FAIL: Missing slugs: {', '.join(missing_slugs)}")
            return False
        
        print(f"  ✅ PASS: Lists both 'best-parties-ibiza-summer' and 'cheap-nightclub-tickets'")
        return True
        
    except Exception as e:
        print(f"  ❌ FAIL: Exception - {e}")
        return False


def test_de_blog_index():
    """Test A5: GET /api/de/blog - lists both DE evergreen guides"""
    print("\n" + "="*80)
    print("TEST A5: DE blog index - lists evergreen guides")
    print("="*80)
    
    url = f"{BASE_URL}/api/de/blog"
    print(f"\n→ Testing GET {url}")
    
    try:
        response = requests.get(url, headers=PUBLIC_HEADERS, timeout=10)
        
        if response.status_code != 200:
            print(f"  ❌ FAIL: Expected 200, got {response.status_code}")
            return False
        
        html = response.text
        
        # Check for both DE evergreen guide slugs
        required_slugs = [
            "beste-partys-ibiza-sommer",
            "guenstige-disco-tickets"
        ]
        
        missing_slugs = []
        for slug in required_slugs:
            if slug not in html:
                missing_slugs.append(slug)
        
        if missing_slugs:
            print(f"  ❌ FAIL: Missing slugs: {', '.join(missing_slugs)}")
            return False
        
        print(f"  ✅ PASS: Lists both 'beste-partys-ibiza-sommer' and 'guenstige-disco-tickets'")
        return True
        
    except Exception as e:
        print(f"  ❌ FAIL: Exception - {e}")
        return False


def test_sitemap_blog_translated_guides():
    """Test A6: GET /api/sitemap-blog.xml - contains all 4 translated guide slugs"""
    print("\n" + "="*80)
    print("TEST A6: Blog sitemap - contains all 4 translated guide slugs")
    print("="*80)
    
    url = f"{BASE_URL}/api/sitemap-blog.xml"
    print(f"\n→ Testing GET {url}")
    
    try:
        response = requests.get(url, headers=PUBLIC_HEADERS, timeout=10)
        
        if response.status_code != 200:
            print(f"  ❌ FAIL: Expected 200, got {response.status_code}")
            return False
        
        xml = response.text
        
        # Check for all 4 translated guide slugs
        required_slugs = [
            "best-parties-ibiza-summer",
            "cheap-nightclub-tickets",
            "beste-partys-ibiza-sommer",
            "guenstige-disco-tickets"
        ]
        
        missing_slugs = []
        for slug in required_slugs:
            if slug not in xml:
                missing_slugs.append(slug)
        
        if missing_slugs:
            print(f"  ❌ FAIL: Missing slugs: {', '.join(missing_slugs)}")
            return False
        
        print(f"  ✅ PASS: Contains all 4 translated guide slugs")
        return True
        
    except Exception as e:
        print(f"  ❌ FAIL: Exception - {e}")
        return False


def test_en_city_ibiza_guides_block():
    """Test A7: GET /api/en/city/ibiza - guides block links to best-parties-ibiza-summer"""
    print("\n" + "="*80)
    print("TEST A7: EN city Ibiza - guides block links to evergreen guide")
    print("="*80)
    
    url = f"{BASE_URL}/api/en/city/ibiza"
    print(f"\n→ Testing GET {url}")
    
    try:
        response = requests.get(url, headers=PUBLIC_HEADERS, timeout=10)
        
        if response.status_code != 200:
            print(f"  ❌ FAIL: Expected 200, got {response.status_code}")
            return False
        
        html = response.text
        
        # Check for link to best-parties-ibiza-summer
        if "best-parties-ibiza-summer" not in html:
            print(f"  ❌ FAIL: Link to 'best-parties-ibiza-summer' not found in guides block")
            return False
        
        print(f"  ✅ PASS: Page contains link to 'best-parties-ibiza-summer'")
        return True
        
    except Exception as e:
        print(f"  ❌ FAIL: Exception - {e}")
        return False


def test_momentos_highlight_fallback():
    """Test B8: GET /api/stories - authenticated, must contain old moment with is_old=true"""
    print("\n" + "="*80)
    print("TEST B8: Momentos highlight fallback (AUTHENTICATED)")
    print("="*80)
    
    url = f"{BASE_URL}/api/stories"
    headers = {
        "Authorization": f"Bearer {AUTH_TOKEN}"
    }
    print(f"\n→ Testing GET {url}")
    print(f"   Using Bearer token: {AUTH_TOKEN}")
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            print(f"  ❌ FAIL: Expected 200, got {response.status_code}")
            if response.status_code == 401:
                print(f"     Authentication failed - check token validity")
            return False
        
        # Parse JSON response
        try:
            stories = response.json()
        except json.JSONDecodeError as e:
            print(f"  ❌ FAIL: Response is not valid JSON - {e}")
            return False
        
        # Check it's an array
        if not isinstance(stories, list):
            print(f"  ❌ FAIL: Response is not a JSON array")
            print(f"     Got type: {type(stories)}")
            return False
        
        # Look for at least one moment with is_old=true
        found_old_moment = False
        for story in stories:
            if isinstance(story, dict):
                if story.get("kind") == "moment" and story.get("is_old") == True:
                    found_old_moment = True
                    print(f"  ✅ FOUND: Old moment highlight - user: {story.get('user', {}).get('name', 'unknown')}")
                    break
        
        if not found_old_moment:
            print(f"  ❌ FAIL: No moment with kind='moment' AND is_old=true found")
            print(f"     Total stories returned: {len(stories)}")
            # Show what we got
            moment_count = sum(1 for s in stories if isinstance(s, dict) and s.get("kind") == "moment")
            print(f"     Moments found: {moment_count}")
            if moment_count > 0:
                print(f"     But none have is_old=true (expected at least one old moment as highlight)")
            return False
        
        print(f"  ✅ PASS: 200, JSON array contains at least one moment with kind='moment' AND is_old=true")
        return True
        
    except Exception as e:
        print(f"  ❌ FAIL: Exception - {e}")
        return False


def test_regression_blog():
    """Test C9: Regression - GET /api/blog"""
    print("\n" + "="*80)
    print("TEST C9: Regression - /api/blog")
    print("="*80)
    
    url = f"{BASE_URL}/api/blog"
    print(f"\n→ Testing GET {url}")
    
    try:
        response = requests.get(url, headers=PUBLIC_HEADERS, timeout=10)
        
        if response.status_code != 200:
            print(f"  ❌ FAIL: Expected 200, got {response.status_code}")
            return False
        
        print(f"  ✅ PASS: 200")
        return True
        
    except Exception as e:
        print(f"  ❌ FAIL: Exception - {e}")
        return False


def test_regression_ciudad_madrid():
    """Test C10: Regression - GET /api/ciudad/madrid"""
    print("\n" + "="*80)
    print("TEST C10: Regression - /api/ciudad/madrid")
    print("="*80)
    
    url = f"{BASE_URL}/api/ciudad/madrid"
    print(f"\n→ Testing GET {url}")
    
    try:
        response = requests.get(url, headers=PUBLIC_HEADERS, timeout=10)
        
        if response.status_code != 200:
            print(f"  ❌ FAIL: Expected 200, got {response.status_code}")
            return False
        
        print(f"  ✅ PASS: 200")
        return True
        
    except Exception as e:
        print(f"  ❌ FAIL: Exception - {e}")
        return False


def test_regression_sitemap():
    """Test C11: Regression - GET /api/sitemap.xml"""
    print("\n" + "="*80)
    print("TEST C11: Regression - /api/sitemap.xml")
    print("="*80)
    
    url = f"{BASE_URL}/api/sitemap.xml"
    print(f"\n→ Testing GET {url}")
    
    try:
        response = requests.get(url, headers=PUBLIC_HEADERS, timeout=10)
        
        if response.status_code != 200:
            print(f"  ❌ FAIL: Expected 200, got {response.status_code}")
            return False
        
        print(f"  ✅ PASS: 200")
        return True
        
    except Exception as e:
        print(f"  ❌ FAIL: Exception - {e}")
        return False


def test_regression_og_city_ibiza():
    """Test C12: Regression - GET /api/og-city/ibiza.jpg (must return image/jpeg)"""
    print("\n" + "="*80)
    print("TEST C12: Regression - /api/og-city/ibiza.jpg")
    print("="*80)
    
    url = f"{BASE_URL}/api/og-city/ibiza.jpg"
    print(f"\n→ Testing GET {url}")
    
    try:
        response = requests.get(url, headers=PUBLIC_HEADERS, timeout=10)
        
        if response.status_code != 200:
            print(f"  ❌ FAIL: Expected 200, got {response.status_code}")
            return False
        
        # Check content-type
        content_type = response.headers.get("content-type", "")
        if "image/jpeg" not in content_type:
            print(f"  ❌ FAIL: Expected content-type image/jpeg, got {content_type}")
            return False
        
        print(f"  ✅ PASS: 200, content-type={content_type}")
        return True
        
    except Exception as e:
        print(f"  ❌ FAIL: Exception - {e}")
        return False


def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("BACKEND API TESTING - EN/DE Evergreen Guides + Momentos Highlight Fallback")
    print("="*80)
    print(f"Base URL: {BASE_URL}")
    print(f"Public headers: {PUBLIC_HEADERS}")
    print(f"Auth token: Bearer {AUTH_TOKEN}")
    
    results = {}
    
    # Section A: EN/DE evergreen guide translations (7 tests)
    print("\n" + "="*80)
    print("SECTION A: EN/DE EVERGREEN GUIDE TRANSLATIONS (PUBLIC, NO AUTH)")
    print("="*80)
    results["A1: EN blog best-parties-ibiza-summer"] = test_en_blog_best_parties_ibiza()
    results["A2: DE blog guenstige-disco-tickets"] = test_de_blog_guenstige_disco_tickets()
    results["A3: ES blog mejores-fiestas-ibiza-verano hreflang"] = test_es_blog_mejores_fiestas_ibiza_hreflang()
    results["A4: EN blog index"] = test_en_blog_index()
    results["A5: DE blog index"] = test_de_blog_index()
    results["A6: sitemap-blog.xml translated guides"] = test_sitemap_blog_translated_guides()
    results["A7: EN city Ibiza guides block"] = test_en_city_ibiza_guides_block()
    
    # Section B: Momentos highlight fallback (1 test)
    print("\n" + "="*80)
    print("SECTION B: MOMENTOS HIGHLIGHT FALLBACK (AUTHENTICATED)")
    print("="*80)
    results["B8: Momentos highlight fallback"] = test_momentos_highlight_fallback()
    
    # Section C: Regression tests (4 tests)
    print("\n" + "="*80)
    print("SECTION C: REGRESSION TESTS")
    print("="*80)
    results["C9: Regression /api/blog"] = test_regression_blog()
    results["C10: Regression /api/ciudad/madrid"] = test_regression_ciudad_madrid()
    results["C11: Regression /api/sitemap.xml"] = test_regression_sitemap()
    results["C12: Regression /api/og-city/ibiza.jpg"] = test_regression_og_city_ibiza()
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    # Group by section
    section_a = {k: v for k, v in results.items() if k.startswith("A")}
    section_b = {k: v for k, v in results.items() if k.startswith("B")}
    section_c = {k: v for k, v in results.items() if k.startswith("C")}
    
    print("\nSection A: EN/DE Evergreen Guide Translations")
    for test_name, result in section_a.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {test_name}")
    
    print("\nSection B: Momentos Highlight Fallback")
    for test_name, result in section_b.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {test_name}")
    
    print("\nSection C: Regression Tests")
    for test_name, result in section_c.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {test_name}")
    
    print(f"\n{'='*80}")
    print(f"TOTAL: {passed}/{total} tests passed")
    print(f"{'='*80}")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
