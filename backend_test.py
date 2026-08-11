#!/usr/bin/env python3
"""
Backend API Testing Script for ¿Quién va? SEO Endpoints
Tests new server-rendered SEO endpoints with required headers
"""

import requests
import sys
from typing import Dict, Any

# Base URL for backend API
BASE_URL = "http://localhost:8001"

# Required headers for all requests
HEADERS = {
    "x-forwarded-host": "www.quienva.me",
    "x-forwarded-proto": "https"
}

def test_dynamic_og_images():
    """Test 1: Dynamic OG images for cities"""
    print("\n" + "="*80)
    print("TEST 1: Dynamic OG images (/api/og-city/{slug}.jpg)")
    print("="*80)
    
    cities = ["madrid", "palma", "ibiza"]
    all_passed = True
    
    for city in cities:
        url = f"{BASE_URL}/api/og-city/{city}.jpg"
        print(f"\n→ Testing GET {url}")
        
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            
            # Check status code
            if response.status_code != 200:
                print(f"  ❌ FAIL: Expected 200, got {response.status_code}")
                all_passed = False
                continue
            
            # Check content-type
            content_type = response.headers.get("content-type", "")
            if "image/jpeg" not in content_type:
                print(f"  ❌ FAIL: Expected content-type image/jpeg, got {content_type}")
                all_passed = False
                continue
            
            # Check body size (>10KB)
            body_size = len(response.content)
            if body_size <= 10240:  # 10KB = 10240 bytes
                print(f"  ❌ FAIL: Expected body >10KB, got {body_size} bytes")
                all_passed = False
                continue
            
            print(f"  ✅ PASS: 200, content-type={content_type}, size={body_size} bytes (>{body_size/1024:.1f}KB)")
            
        except Exception as e:
            print(f"  ❌ FAIL: Exception - {e}")
            all_passed = False
    
    # Test unknown city (should NOT be 500)
    print(f"\n→ Testing GET {BASE_URL}/api/og-city/noexiste.jpg (unknown city)")
    try:
        response = requests.get(f"{BASE_URL}/api/og-city/noexiste.jpg", headers=HEADERS, timeout=10)
        
        if response.status_code == 500:
            print(f"  ❌ FAIL: Got 500 (should be 200 jpeg OR 302 redirect)")
            all_passed = False
        elif response.status_code == 200:
            content_type = response.headers.get("content-type", "")
            if "image/jpeg" in content_type:
                print(f"  ✅ PASS: 200 with image/jpeg (gradient fallback)")
            else:
                print(f"  ⚠️  WARNING: 200 but content-type is {content_type} (expected image/jpeg)")
        elif response.status_code == 302:
            print(f"  ✅ PASS: 302 redirect (acceptable)")
        else:
            print(f"  ⚠️  WARNING: Got {response.status_code} (expected 200 jpeg OR 302)")
            
    except Exception as e:
        print(f"  ❌ FAIL: Exception - {e}")
        all_passed = False
    
    return all_passed


def test_ciudad_og_meta():
    """Test 2: GET /api/ciudad/madrid og:image meta"""
    print("\n" + "="*80)
    print("TEST 2: City page og:image meta (/api/ciudad/madrid)")
    print("="*80)
    
    url = f"{BASE_URL}/api/ciudad/madrid"
    print(f"\n→ Testing GET {url}")
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        
        if response.status_code != 200:
            print(f"  ❌ FAIL: Expected 200, got {response.status_code}")
            return False
        
        html = response.text
        
        # Check og:image meta points to /og-city/madrid.jpg
        if 'og:image' not in html:
            print(f"  ❌ FAIL: No og:image meta tag found")
            return False
        
        if '/og-city/madrid.jpg' not in html:
            print(f"  ❌ FAIL: og:image does not point to /og-city/madrid.jpg")
            # Try to extract what it points to
            import re
            og_image_match = re.search(r'<meta[^>]*property="og:image"[^>]*content="([^"]*)"', html)
            if og_image_match:
                print(f"     Found og:image: {og_image_match.group(1)}")
            return False
        
        # Check og:image:width=1200
        if 'og:image:width' not in html or '1200' not in html:
            print(f"  ❌ FAIL: og:image:width=1200 not found")
            return False
        
        # Check og:image:height=630
        if 'og:image:height' not in html or '630' not in html:
            print(f"  ❌ FAIL: og:image:height=630 not found")
            return False
        
        print(f"  ✅ PASS: og:image points to /og-city/madrid.jpg with width=1200 and height=630")
        return True
        
    except Exception as e:
        print(f"  ❌ FAIL: Exception - {e}")
        return False


def test_auto_blog_posts():
    """Test 3: Auto blog posts for weekend agenda"""
    print("\n" + "="*80)
    print("TEST 3: Auto blog posts (weekend agenda)")
    print("="*80)
    
    test_cases = [
        ("madrid", "Madrid"),
        ("ibiza", "Ibiza")
    ]
    
    all_passed = True
    
    for slug_city, display_city in test_cases:
        url = f"{BASE_URL}/api/blog/agenda-fiestas-finde-{slug_city}"
        print(f"\n→ Testing GET {url}")
        
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            
            if response.status_code != 200:
                print(f"  ❌ FAIL: Expected 200, got {response.status_code}")
                all_passed = False
                continue
            
            html = response.text
            
            # Check title
            expected_title = f"Fiestas de este fin de semana en {display_city}: agenda actualizada"
            if expected_title not in html:
                print(f"  ❌ FAIL: Expected title '{expected_title}' not found")
                all_passed = False
                continue
            
            # Check for blog section markup
            if '<article' not in html and '<section' not in html:
                print(f"  ❌ FAIL: No blog section markup found (<article> or <section>)")
                all_passed = False
                continue
            
            # Check for FAQ block
            if 'Preguntas frecuentes' not in html:
                print(f"  ❌ FAIL: 'Preguntas frecuentes' FAQ block not found")
                all_passed = False
                continue
            
            # Check for Article JSON-LD (BlogPosting is also acceptable as it's a subtype of Article)
            if 'application/ld+json' not in html:
                print(f"  ❌ FAIL: No application/ld+json found")
                all_passed = False
                continue
            
            has_article = ('"@type":"Article"' in html or '"@type": "Article"' in html or
                          '"@type":"BlogPosting"' in html or '"@type": "BlogPosting"' in html)
            if not has_article:
                print(f"  ❌ FAIL: Article/BlogPosting JSON-LD not found")
                all_passed = False
                continue
            
            print(f"  ✅ PASS: 200, correct title, blog markup, FAQ block, Article JSON-LD present")
            
        except Exception as e:
            print(f"  ❌ FAIL: Exception - {e}")
            all_passed = False
    
    return all_passed


def test_blog_index():
    """Test 4: GET /api/blog index lists all 5 agenda slugs"""
    print("\n" + "="*80)
    print("TEST 4: Blog index (/api/blog)")
    print("="*80)
    
    url = f"{BASE_URL}/api/blog"
    print(f"\n→ Testing GET {url}")
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        
        if response.status_code != 200:
            print(f"  ❌ FAIL: Expected 200, got {response.status_code}")
            return False
        
        html = response.text
        
        # Check for all 5 agenda slugs
        required_slugs = [
            "agenda-fiestas-finde-madrid",
            "agenda-fiestas-finde-barcelona",
            "agenda-fiestas-finde-ibiza",
            "agenda-fiestas-finde-palma",
            "agenda-fiestas-finde-marbella"
        ]
        
        missing_slugs = []
        for slug in required_slugs:
            if slug not in html:
                missing_slugs.append(slug)
        
        if missing_slugs:
            print(f"  ❌ FAIL: Missing slugs: {', '.join(missing_slugs)}")
            return False
        
        print(f"  ✅ PASS: All 5 agenda slugs present in blog index")
        return True
        
    except Exception as e:
        print(f"  ❌ FAIL: Exception - {e}")
        return False


def test_sitemap_blog():
    """Test 5: GET /api/sitemap-blog.xml contains all 5 agenda slugs"""
    print("\n" + "="*80)
    print("TEST 5: Blog sitemap (/api/sitemap-blog.xml)")
    print("="*80)
    
    url = f"{BASE_URL}/api/sitemap-blog.xml"
    print(f"\n→ Testing GET {url}")
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        
        if response.status_code != 200:
            print(f"  ❌ FAIL: Expected 200, got {response.status_code}")
            return False
        
        xml = response.text
        
        # Check for all 5 agenda slugs
        required_slugs = [
            "agenda-fiestas-finde-madrid",
            "agenda-fiestas-finde-barcelona",
            "agenda-fiestas-finde-ibiza",
            "agenda-fiestas-finde-palma",
            "agenda-fiestas-finde-marbella"
        ]
        
        missing_slugs = []
        for slug in required_slugs:
            if slug not in xml:
                missing_slugs.append(slug)
        
        if missing_slugs:
            print(f"  ❌ FAIL: Missing slugs: {', '.join(missing_slugs)}")
            return False
        
        print(f"  ✅ PASS: All 5 agenda slugs present in sitemap-blog.xml")
        return True
        
    except Exception as e:
        print(f"  ❌ FAIL: Exception - {e}")
        return False


def test_sitemap_index():
    """Test 6: GET /api/sitemap.xml (index) - valid XML sitemapindex"""
    print("\n" + "="*80)
    print("TEST 6: Sitemap index (/api/sitemap.xml)")
    print("="*80)
    
    url = f"{BASE_URL}/api/sitemap.xml"
    print(f"\n→ Testing GET {url}")
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        
        if response.status_code != 200:
            print(f"  ❌ FAIL: Expected 200, got {response.status_code}")
            return False
        
        xml = response.text
        
        # Check for valid XML
        if not xml.startswith('<?xml'):
            print(f"  ❌ FAIL: Response does not start with <?xml")
            return False
        
        # Check for sitemapindex
        if '<sitemapindex' not in xml:
            print(f"  ❌ FAIL: No <sitemapindex> tag found")
            return False
        
        print(f"  ✅ PASS: 200, valid XML sitemapindex")
        return True
        
    except Exception as e:
        print(f"  ❌ FAIL: Exception - {e}")
        return False


def test_sitemap_events_changefreq():
    """Test 7: GET /api/sitemap-events-madrid.xml - URLs have changefreq=hourly"""
    print("\n" + "="*80)
    print("TEST 7: Events sitemap changefreq (/api/sitemap-events-madrid.xml)")
    print("="*80)
    
    url = f"{BASE_URL}/api/sitemap-events-madrid.xml"
    print(f"\n→ Testing GET {url}")
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        
        if response.status_code != 200:
            print(f"  ❌ FAIL: Expected 200, got {response.status_code}")
            return False
        
        xml = response.text
        
        # Check for <url> entries
        if '<url>' not in xml:
            print(f"  ❌ FAIL: No <url> entries found")
            return False
        
        # Check for changefreq=hourly
        if '<changefreq>hourly</changefreq>' not in xml:
            print(f"  ❌ FAIL: <changefreq>hourly</changefreq> not found")
            return False
        
        print(f"  ✅ PASS: <url> entries have <changefreq>hourly</changefreq>")
        return True
        
    except Exception as e:
        print(f"  ❌ FAIL: Exception - {e}")
        return False


def test_regression():
    """Test 8: Regression tests - existing endpoints still work"""
    print("\n" + "="*80)
    print("TEST 8: Regression tests")
    print("="*80)
    
    test_urls = [
        "/api/ciudad/ibiza",
        "/api/home",
        "/api/blog/donde-salir-esta-noche-espana"
    ]
    
    all_passed = True
    
    for path in test_urls:
        url = f"{BASE_URL}{path}"
        print(f"\n→ Testing GET {url}")
        
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            
            if response.status_code != 200:
                print(f"  ❌ FAIL: Expected 200, got {response.status_code}")
                all_passed = False
            else:
                print(f"  ✅ PASS: 200")
                
        except Exception as e:
            print(f"  ❌ FAIL: Exception - {e}")
            all_passed = False
    
    return all_passed


def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("BACKEND API TESTING - ¿Quién va? SEO Endpoints")
    print("="*80)
    print(f"Base URL: {BASE_URL}")
    print(f"Headers: {HEADERS}")
    
    results = {}
    
    # Run all tests
    results["Dynamic OG images"] = test_dynamic_og_images()
    results["Ciudad og:image meta"] = test_ciudad_og_meta()
    results["Auto blog posts"] = test_auto_blog_posts()
    results["Blog index"] = test_blog_index()
    results["Sitemap blog"] = test_sitemap_blog()
    results["Sitemap index"] = test_sitemap_index()
    results["Sitemap events changefreq"] = test_sitemap_events_changefreq()
    results["Regression tests"] = test_regression()
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
