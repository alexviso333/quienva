#!/usr/bin/env python3
"""
SEO Regression Test for server-rendered endpoints
Tests HTML-head/image rendering changes in /app/backend/server.py
"""

import requests
from bs4 import BeautifulSoup
import re

BASE_URL = "http://localhost:8001/api"
TEST_EVENT_ID = "test-ev-0"

def test_home_pages():
    """Test 1: Home pages return 200 valid HTML with proper SEO tags"""
    print("\n" + "="*80)
    print("TEST 1: HOME PAGES (/, /en/home, /de/home)")
    print("="*80)
    
    pages = [
        ("/home", "es"),
        ("/en/home", "en"),
        ("/de/home", "de")
    ]
    
    all_passed = True
    
    for path, lang in pages:
        print(f"\n--- Testing {path} (lang={lang}) ---")
        url = f"{BASE_URL}{path}"
        resp = requests.get(url)
        
        # Check status code
        if resp.status_code != 200:
            print(f"❌ FAIL: Expected 200, got {resp.status_code}")
            all_passed = False
            continue
        print(f"✅ Status: {resp.status_code}")
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Check <title>
        title = soup.find('title')
        if not title:
            print("❌ FAIL: No <title> tag found")
            all_passed = False
        else:
            print(f"✅ Title: {title.string[:60]}...")
        
        # Check self-referencing canonical
        canonical = soup.find('link', rel='canonical')
        if not canonical:
            print("❌ FAIL: No canonical link found")
            all_passed = False
        else:
            canonical_href = canonical.get('href', '')
            print(f"✅ Canonical: {canonical_href}")
            # Verify it's self-referencing (contains the path)
            if path.replace('/home', '') not in canonical_href and canonical_href.endswith(('/', '/home')):
                print(f"   ✅ Self-referencing confirmed")
            else:
                print(f"   ⚠️  Warning: May not be self-referencing")
        
        # Check hreflang links (es, en, de, x-default)
        hreflangs = soup.find_all('link', rel='alternate', hreflang=True)
        hreflang_langs = [link.get('hreflang') for link in hreflangs]
        expected_langs = ['es', 'en', 'de', 'x-default']
        
        if all(lang in hreflang_langs for lang in expected_langs):
            print(f"✅ Hreflang: Found all required ({', '.join(expected_langs)})")
        else:
            print(f"❌ FAIL: Missing hreflang. Found: {hreflang_langs}")
            all_passed = False
        
        # Check Google Fonts NON-render-blocking
        # Must have: <link rel="stylesheet" ... media="print" onload="this.media='all'">
        # Must NOT have: plain render-blocking <link rel="stylesheet" href="...fonts.googleapis.com/css2..."> OUTSIDE noscript
        
        # Remove all noscript tags first to avoid false positives
        for noscript in soup.find_all('noscript'):
            noscript.decompose()
        
        font_links = soup.find_all('link', rel='stylesheet', href=re.compile(r'fonts\.googleapis\.com/css2'))
        
        non_blocking_found = False
        blocking_found = False
        
        for link in font_links:
            href = link.get('href', '')
            media = link.get('media', '')
            onload = link.get('onload', '')
            
            if 'fonts.googleapis.com/css2' in href:
                if media == 'print' and 'this.media' in onload:
                    non_blocking_found = True
                    print(f"✅ Google Fonts NON-blocking: media=print onload=\"{onload[:30]}...\"")
                elif media != 'print':
                    blocking_found = True
                    print(f"❌ FAIL: Found BLOCKING Google Fonts link OUTSIDE noscript (no media=print)")
        
        # Check for noscript fallback (re-parse to get original)
        soup_original = BeautifulSoup(resp.text, 'html.parser')
        noscript_fonts = soup_original.find_all('noscript')
        noscript_has_fonts = any('fonts.googleapis.com' in str(ns) for ns in noscript_fonts)
        if noscript_has_fonts:
            print(f"✅ Google Fonts <noscript> fallback found")
        else:
            print(f"⚠️  Warning: No <noscript> fallback for Google Fonts")
        
        if blocking_found:
            print(f"❌ FAIL: Found render-blocking Google Fonts link OUTSIDE noscript")
            all_passed = False
        elif not non_blocking_found:
            print(f"❌ FAIL: No non-blocking Google Fonts link found")
            all_passed = False
        
        # Check Cloudinary preconnect
        preconnects = soup.find_all('link', rel='preconnect')
        cloudinary_preconnect = any('res.cloudinary.com' in link.get('href', '') for link in preconnects)
        
        if cloudinary_preconnect:
            print(f"✅ Cloudinary preconnect: <link rel=\"preconnect\" href=\"https://res.cloudinary.com\">")
        else:
            print(f"❌ FAIL: No Cloudinary preconnect found")
            all_passed = False
    
    return all_passed


def test_event_pages():
    """Test 2: Event pages return 200 for test-ev-0 with proper canonical and hreflang"""
    print("\n" + "="*80)
    print(f"TEST 2: EVENT PAGES FOR {TEST_EVENT_ID}")
    print("="*80)
    
    pages = [
        (f"/fiesta/{TEST_EVENT_ID}", "es", "/fiesta/"),
        (f"/en/party/{TEST_EVENT_ID}", "en", "/en/party/"),
        (f"/de/party/{TEST_EVENT_ID}", "de", "/de/party/")
    ]
    
    all_passed = True
    
    for path, lang, expected_canonical_path in pages:
        print(f"\n--- Testing {path} (lang={lang}) ---")
        url = f"{BASE_URL}{path}"
        resp = requests.get(url)
        
        # Check status code
        if resp.status_code != 200:
            print(f"❌ FAIL: Expected 200, got {resp.status_code}")
            all_passed = False
            continue
        print(f"✅ Status: {resp.status_code}")
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Check canonical is self-referencing (points to same language path)
        canonical = soup.find('link', rel='canonical')
        if not canonical:
            print("❌ FAIL: No canonical link found")
            all_passed = False
        else:
            canonical_href = canonical.get('href', '')
            print(f"✅ Canonical: {canonical_href}")
            
            # Verify it's self-referencing (contains the expected path)
            if expected_canonical_path in canonical_href:
                print(f"   ✅ Self-referencing confirmed (contains '{expected_canonical_path}')")
            else:
                print(f"   ❌ FAIL: Not self-referencing. Expected path '{expected_canonical_path}' not in canonical")
                all_passed = False
        
        # Check hreflang alternates (es, en, de, x-default)
        hreflangs = soup.find_all('link', rel='alternate', hreflang=True)
        hreflang_langs = [link.get('hreflang') for link in hreflangs]
        expected_langs = ['es', 'en', 'de', 'x-default']
        
        if all(lang in hreflang_langs for lang in expected_langs):
            print(f"✅ Hreflang: Found all required ({', '.join(expected_langs)})")
        else:
            print(f"❌ FAIL: Missing hreflang. Found: {hreflang_langs}")
            all_passed = False
        
        # Check hero <img> has fetchpriority="high"
        hero_img = soup.find('img', fetchpriority='high')
        if hero_img:
            print(f"✅ Hero image has fetchpriority=\"high\"")
            
            # Check if image_url is Cloudinary and has transforms
            img_src = hero_img.get('src', '')
            if 'res.cloudinary.com' in img_src:
                if 'f_auto' in img_src and 'q_auto' in img_src and 'w_' in img_src:
                    print(f"   ✅ Cloudinary transforms present: f_auto,q_auto,w_")
                    print(f"   Image src: {img_src[:80]}...")
                else:
                    print(f"   ❌ FAIL: Cloudinary URL missing transforms (f_auto,q_auto,w_)")
                    print(f"   Image src: {img_src}")
                    all_passed = False
            else:
                print(f"   ℹ️  Image is not from Cloudinary: {img_src[:60]}...")
        else:
            print(f"❌ FAIL: No hero image with fetchpriority=\"high\" found")
            all_passed = False
    
    return all_passed


def test_genre_localization():
    """Test 3: Genre localization on event pages"""
    print("\n" + "="*80)
    print(f"TEST 3: GENRE LOCALIZATION FOR {TEST_EVENT_ID}")
    print("="*80)
    
    pages = [
        (f"/fiesta/{TEST_EVENT_ID}", "es", "Comercial"),
        (f"/en/party/{TEST_EVENT_ID}", "en", "Commercial / Top 40"),
        (f"/de/party/{TEST_EVENT_ID}", "de", "Charts / Kommerziell")
    ]
    
    all_passed = True
    
    for path, lang, expected_genre in pages:
        print(f"\n--- Testing {path} (lang={lang}) ---")
        url = f"{BASE_URL}{path}"
        resp = requests.get(url)
        
        if resp.status_code != 200:
            print(f"❌ FAIL: Expected 200, got {resp.status_code}")
            all_passed = False
            continue
        
        # Search for genre text in the HTML
        if expected_genre in resp.text:
            print(f"✅ Genre localization: Found \"{expected_genre}\"")
        else:
            print(f"❌ FAIL: Expected genre \"{expected_genre}\" not found in page")
            # Try to find what genre is actually shown
            soup = BeautifulSoup(resp.text, 'html.parser')
            # Look for common genre patterns
            genre_patterns = ['Comercial', 'Commercial', 'Charts', 'Kommerziell', 'Top 40']
            found_genres = [g for g in genre_patterns if g in resp.text]
            if found_genres:
                print(f"   Found instead: {', '.join(found_genres)}")
            all_passed = False
    
    return all_passed


def test_sitemaps_robots():
    """Test 4: Sitemaps and robots.txt return 200 with valid content"""
    print("\n" + "="*80)
    print("TEST 4: SITEMAPS AND ROBOTS.TXT")
    print("="*80)
    
    endpoints = [
        ("/robots.txt", "text/plain", "Sitemap:"),
        ("/sitemap.xml", "application/xml", "<?xml"),
        ("/sitemap-cities.xml", "application/xml", "<urlset"),
        ("/sitemap-events-ibiza.xml", "application/xml", "<urlset")
    ]
    
    all_passed = True
    
    for path, expected_content_type, expected_content in endpoints:
        print(f"\n--- Testing {path} ---")
        url = f"{BASE_URL}{path}"
        resp = requests.get(url)
        
        # Check status code
        if resp.status_code != 200:
            print(f"❌ FAIL: Expected 200, got {resp.status_code}")
            all_passed = False
            continue
        print(f"✅ Status: {resp.status_code}")
        
        # Check content type
        content_type = resp.headers.get('content-type', '').lower()
        if expected_content_type.lower() in content_type:
            print(f"✅ Content-Type: {content_type}")
        else:
            print(f"❌ FAIL: Expected content-type '{expected_content_type}', got '{content_type}'")
            all_passed = False
        
        # Check content
        if expected_content in resp.text:
            print(f"✅ Content: Contains '{expected_content}'")
            # Show snippet
            if path == "/robots.txt":
                lines = resp.text.split('\n')
                sitemap_line = [l for l in lines if 'Sitemap:' in l]
                if sitemap_line:
                    print(f"   {sitemap_line[0]}")
            elif "sitemap" in path:
                print(f"   First 100 chars: {resp.text[:100]}...")
        else:
            print(f"❌ FAIL: Expected content '{expected_content}' not found")
            all_passed = False
    
    return all_passed


def test_gone_removed_handling():
    """Test 5: Gone/removed handling returns 410 or 301, not 200"""
    print("\n" + "="*80)
    print("TEST 5: GONE/REMOVED HANDLING")
    print("="*80)
    
    path = f"/fiesta/does-not-exist-xyz"
    print(f"\n--- Testing {path} ---")
    url = f"{BASE_URL}{path}"
    resp = requests.get(url, allow_redirects=False)
    
    print(f"Status: {resp.status_code}")
    
    if resp.status_code == 410:
        print(f"✅ PASS: Returns 410 Gone (correct)")
        return True
    elif resp.status_code in [301, 302, 303, 307, 308]:
        print(f"✅ PASS: Returns {resp.status_code} redirect (acceptable)")
        location = resp.headers.get('location', '')
        print(f"   Redirects to: {location}")
        return True
    elif resp.status_code == 200:
        print(f"❌ FAIL: Returns 200 (soft-404, incorrect)")
        return False
    else:
        print(f"⚠️  Unexpected status: {resp.status_code}")
        return False


def main():
    print("\n" + "="*80)
    print("SEO REGRESSION TEST - SERVER-RENDERED ENDPOINTS")
    print("Testing HTML-head/image rendering changes")
    print("="*80)
    
    results = {
        "Test 1: Home pages": test_home_pages(),
        "Test 2: Event pages": test_event_pages(),
        "Test 3: Genre localization": test_genre_localization(),
        "Test 4: Sitemaps/robots": test_sitemaps_robots(),
        "Test 5: Gone/removed handling": test_gone_removed_handling()
    }
    
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    all_passed = all(results.values())
    
    print("\n" + "="*80)
    if all_passed:
        print("🎉 ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
    print("="*80)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit(main())
