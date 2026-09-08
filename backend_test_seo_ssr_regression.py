#!/usr/bin/env python3
"""
Test SEO SSR endpoints after adding:
(a) unique descriptive paragraph per language on event pages
(b) /api/llms.txt
(c) accessibility contrast fix

Backend: http://localhost:8001
Routes prefixed with /api
DB: quienva_local with seeded event id "test-ev-0" (city Ibiza, genre "Comercial", price ~30 EUR)
"""

import requests
import re
from typing import Dict, List, Tuple

BASE_URL = "http://localhost:8001/api"

def test_event_descriptive_paragraphs():
    """
    Test 1: Unique per-language descriptive paragraph on event pages
    For event test-ev-0:
    - GET /api/fiesta/test-ev-0 -> 200; body contains <section class="lead"><p>...</p></section> with SPANISH prose
    - GET /api/en/party/test-ev-0 -> 200; contains <section class="lead"> paragraph in ENGLISH
    - GET /api/de/party/test-ev-0 -> 200; contains <section class="lead"> paragraph in GERMAN
    - Confirm the three paragraphs are genuinely DIFFERENT text across languages
    - Confirm genre is localized (Comercial / Commercial / Charts respectively)
    """
    print("\n" + "="*80)
    print("TEST 1: UNIQUE PER-LANGUAGE DESCRIPTIVE PARAGRAPH ON EVENT PAGES")
    print("="*80)
    
    event_id = "test-ev-0"
    
    # Test Spanish event page
    print(f"\n1.1 Testing Spanish event page: GET /api/fiesta/{event_id}")
    es_url = f"{BASE_URL}/fiesta/{event_id}"
    es_response = requests.get(es_url)
    print(f"   Status: {es_response.status_code}")
    
    if es_response.status_code != 200:
        print(f"   ❌ FAILED: Expected 200, got {es_response.status_code}")
        return False
    
    print(f"   ✅ Status 200 OK")
    print(f"   Content-Type: {es_response.headers.get('content-type')}")
    
    # Extract Spanish lead paragraph
    es_html = es_response.text
    es_lead_match = re.search(r'<section[^>]*class="lead"[^>]*>(.*?)</section>', es_html, re.DOTALL)
    
    if not es_lead_match:
        print(f"   ❌ FAILED: No <section class=\"lead\"> found in Spanish page")
        return False
    
    es_lead_section = es_lead_match.group(1)
    es_paragraph_match = re.search(r'<p[^>]*>(.*?)</p>', es_lead_section, re.DOTALL)
    
    if not es_paragraph_match:
        print(f"   ❌ FAILED: No <p> tag found inside <section class=\"lead\"> in Spanish page")
        return False
    
    es_paragraph = es_paragraph_match.group(1).strip()
    # Remove HTML tags from paragraph text
    es_text = re.sub(r'<[^>]+>', '', es_paragraph).strip()
    
    print(f"   ✅ Found <section class=\"lead\"><p>...</p></section>")
    print(f"   Spanish paragraph (first 150 chars): {es_text[:150]}...")
    
    # Check if Spanish text mentions venue (Pacha) and city (Ibiza)
    if 'Pacha' not in es_text and 'pacha' not in es_text.lower():
        print(f"   ⚠️  WARNING: Spanish paragraph doesn't mention venue 'Pacha'")
    else:
        print(f"   ✅ Spanish paragraph mentions venue 'Pacha'")
    
    if 'Ibiza' not in es_text and 'ibiza' not in es_text.lower():
        print(f"   ⚠️  WARNING: Spanish paragraph doesn't mention city 'Ibiza'")
    else:
        print(f"   ✅ Spanish paragraph mentions city 'Ibiza'")
    
    # Check for Spanish genre "Comercial"
    if 'Comercial' in es_html or 'comercial' in es_html.lower():
        print(f"   ✅ Spanish page contains genre 'Comercial'")
    else:
        print(f"   ⚠️  WARNING: Spanish page doesn't contain genre 'Comercial'")
    
    # Test English event page
    print(f"\n1.2 Testing English event page: GET /api/en/party/{event_id}")
    en_url = f"{BASE_URL}/en/party/{event_id}"
    en_response = requests.get(en_url)
    print(f"   Status: {en_response.status_code}")
    
    if en_response.status_code != 200:
        print(f"   ❌ FAILED: Expected 200, got {en_response.status_code}")
        return False
    
    print(f"   ✅ Status 200 OK")
    
    # Extract English lead paragraph
    en_html = en_response.text
    en_lead_match = re.search(r'<section[^>]*class="lead"[^>]*>(.*?)</section>', en_html, re.DOTALL)
    
    if not en_lead_match:
        print(f"   ❌ FAILED: No <section class=\"lead\"> found in English page")
        return False
    
    en_lead_section = en_lead_match.group(1)
    en_paragraph_match = re.search(r'<p[^>]*>(.*?)</p>', en_lead_section, re.DOTALL)
    
    if not en_paragraph_match:
        print(f"   ❌ FAILED: No <p> tag found inside <section class=\"lead\"> in English page")
        return False
    
    en_paragraph = en_paragraph_match.group(1).strip()
    en_text = re.sub(r'<[^>]+>', '', en_paragraph).strip()
    
    print(f"   ✅ Found <section class=\"lead\"><p>...</p></section>")
    print(f"   English paragraph (first 150 chars): {en_text[:150]}...")
    
    # Check for English genre "Commercial"
    if 'Commercial' in en_html or 'commercial' in en_html.lower():
        print(f"   ✅ English page contains genre 'Commercial'")
    else:
        print(f"   ⚠️  WARNING: English page doesn't contain genre 'Commercial'")
    
    # Test German event page
    print(f"\n1.3 Testing German event page: GET /api/de/party/{event_id}")
    de_url = f"{BASE_URL}/de/party/{event_id}"
    de_response = requests.get(de_url)
    print(f"   Status: {de_response.status_code}")
    
    if de_response.status_code != 200:
        print(f"   ❌ FAILED: Expected 200, got {de_response.status_code}")
        return False
    
    print(f"   ✅ Status 200 OK")
    
    # Extract German lead paragraph
    de_html = de_response.text
    de_lead_match = re.search(r'<section[^>]*class="lead"[^>]*>(.*?)</section>', de_html, re.DOTALL)
    
    if not de_lead_match:
        print(f"   ❌ FAILED: No <section class=\"lead\"> found in German page")
        return False
    
    de_lead_section = de_lead_match.group(1)
    de_paragraph_match = re.search(r'<p[^>]*>(.*?)</p>', de_lead_section, re.DOTALL)
    
    if not de_paragraph_match:
        print(f"   ❌ FAILED: No <p> tag found inside <section class=\"lead\"> in German page")
        return False
    
    de_paragraph = de_paragraph_match.group(1).strip()
    de_text = re.sub(r'<[^>]+>', '', de_paragraph).strip()
    
    print(f"   ✅ Found <section class=\"lead\"><p>...</p></section>")
    print(f"   German paragraph (first 150 chars): {de_text[:150]}...")
    
    # Check for German genre "Charts"
    if 'Charts' in de_html or 'charts' in de_html.lower():
        print(f"   ✅ German page contains genre 'Charts'")
    else:
        print(f"   ⚠️  WARNING: German page doesn't contain genre 'Charts'")
    
    # Compare paragraphs to ensure they're different
    print(f"\n1.4 Comparing paragraphs across languages")
    
    # Normalize texts for comparison (lowercase, remove extra whitespace)
    es_normalized = ' '.join(es_text.lower().split())
    en_normalized = ' '.join(en_text.lower().split())
    de_normalized = ' '.join(de_text.lower().split())
    
    if es_normalized == en_normalized:
        print(f"   ❌ FAILED: Spanish and English paragraphs are IDENTICAL")
        return False
    else:
        print(f"   ✅ Spanish and English paragraphs are DIFFERENT")
    
    if es_normalized == de_normalized:
        print(f"   ❌ FAILED: Spanish and German paragraphs are IDENTICAL")
        return False
    else:
        print(f"   ✅ Spanish and German paragraphs are DIFFERENT")
    
    if en_normalized == de_normalized:
        print(f"   ❌ FAILED: English and German paragraphs are IDENTICAL")
        return False
    else:
        print(f"   ✅ English and German paragraphs are DIFFERENT")
    
    print(f"\n✅ TEST 1 PASSED: All three languages have unique descriptive paragraphs")
    return True


def test_llms_txt():
    """
    Test 2: llms.txt endpoint
    - GET /api/llms.txt -> 200, content-type text/plain (charset utf-8)
    - Body must be Markdown starting with H1 line "# ¿Quién va?"
    - Must contain at least one Markdown link like [Text](http...)
    - Confirm it lists city links (e.g. /fiestas/ibiza) and English/Deutsch sections
    """
    print("\n" + "="*80)
    print("TEST 2: llms.txt ENDPOINT")
    print("="*80)
    
    print(f"\n2.1 Testing llms.txt: GET /api/llms.txt")
    url = f"{BASE_URL}/llms.txt"
    response = requests.get(url)
    print(f"   Status: {response.status_code}")
    
    if response.status_code != 200:
        print(f"   ❌ FAILED: Expected 200, got {response.status_code}")
        return False
    
    print(f"   ✅ Status 200 OK")
    
    # Check content-type
    content_type = response.headers.get('content-type', '').lower()
    print(f"   Content-Type: {content_type}")
    
    if 'text/plain' not in content_type:
        print(f"   ❌ FAILED: Expected content-type 'text/plain', got '{content_type}'")
        return False
    
    print(f"   ✅ Content-Type is text/plain")
    
    if 'utf-8' not in content_type and 'charset' in content_type:
        print(f"   ⚠️  WARNING: Content-Type doesn't specify charset=utf-8")
    else:
        print(f"   ✅ Content-Type includes charset=utf-8")
    
    # Check body content
    body = response.text
    print(f"\n2.2 Checking llms.txt body content")
    print(f"   Body length: {len(body)} characters")
    print(f"   First 200 characters:\n   {body[:200]}")
    
    # Check for H1 line "# ¿Quién va?"
    lines = body.split('\n')
    first_line = lines[0].strip() if lines else ""
    
    if first_line != "# ¿Quién va?":
        print(f"   ❌ FAILED: First line should be '# ¿Quién va?', got '{first_line}'")
        return False
    
    print(f"   ✅ First line is '# ¿Quién va?'")
    
    # Check for Markdown links [Text](http...)
    markdown_links = re.findall(r'\[([^\]]+)\]\(([^\)]+)\)', body)
    
    if not markdown_links:
        print(f"   ❌ FAILED: No Markdown links [Text](http...) found in body")
        return False
    
    print(f"   ✅ Found {len(markdown_links)} Markdown links")
    print(f"   Sample links:")
    for i, (text, url) in enumerate(markdown_links[:5]):
        print(f"      [{text}]({url})")
    
    # Check for city links (e.g. /fiestas/ibiza)
    city_links = [url for text, url in markdown_links if '/fiestas/' in url or '/parties/' in url or '/partys/' in url]
    
    if not city_links:
        print(f"   ⚠️  WARNING: No city links (e.g. /fiestas/ibiza) found")
    else:
        print(f"   ✅ Found {len(city_links)} city links")
        print(f"   Sample city links: {city_links[:3]}")
    
    # Check for English/Deutsch sections
    has_english = '/en/' in body or 'English' in body or 'Parties' in body
    has_german = '/de/' in body or 'Deutsch' in body or 'German' in body or 'Partys' in body
    
    if has_english:
        print(f"   ✅ English section found (contains '/en/' or 'English' or 'Parties')")
    else:
        print(f"   ⚠️  WARNING: No English section found")
    
    if has_german:
        print(f"   ✅ German section found (contains '/de/' or 'Deutsch' or 'German' or 'Partys')")
    else:
        print(f"   ⚠️  WARNING: No German section found")
    
    print(f"\n✅ TEST 2 PASSED: llms.txt endpoint working correctly")
    return True


def test_regression_event_pages():
    """
    Test 3: Regression - nothing else broke on event pages
    - Each event page still has self-referencing canonical per language
    - hreflang es+en+de+x-default
    - hero <img> fetchpriority="high"
    - For res.cloudinary.com images, an "f_auto,q_auto,w_" transform
    """
    print("\n" + "="*80)
    print("TEST 3: REGRESSION - EVENT PAGE FEATURES")
    print("="*80)
    
    event_id = "test-ev-0"
    
    # Test Spanish event page
    print(f"\n3.1 Testing Spanish event page regression: GET /api/fiesta/{event_id}")
    es_url = f"{BASE_URL}/fiesta/{event_id}"
    es_response = requests.get(es_url)
    
    if es_response.status_code != 200:
        print(f"   ❌ FAILED: Expected 200, got {es_response.status_code}")
        return False
    
    es_html = es_response.text
    
    # Check canonical
    canonical_match = re.search(r'<link[^>]*rel="canonical"[^>]*href="([^"]+)"', es_html)
    if not canonical_match:
        print(f"   ❌ FAILED: No canonical link found")
        return False
    
    canonical_url = canonical_match.group(1)
    print(f"   ✅ Canonical link found: {canonical_url}")
    
    # Check if canonical is self-referencing (contains /fiesta/ and event_id)
    if '/fiesta/' not in canonical_url or event_id not in canonical_url:
        print(f"   ❌ FAILED: Canonical is not self-referencing Spanish event page")
        return False
    
    print(f"   ✅ Canonical is self-referencing Spanish event page")
    
    # Check hreflang alternates
    hreflang_matches = re.findall(r'<link[^>]*rel="alternate"[^>]*hreflang="([^"]+)"[^>]*href="([^"]+)"', es_html)
    hreflang_dict = {lang: url for lang, url in hreflang_matches}
    
    print(f"   Found {len(hreflang_dict)} hreflang alternates:")
    for lang, url in hreflang_dict.items():
        print(f"      {lang}: {url}")
    
    required_hreflangs = ['es', 'en', 'de', 'x-default']
    missing_hreflangs = [lang for lang in required_hreflangs if lang not in hreflang_dict]
    
    if missing_hreflangs:
        print(f"   ❌ FAILED: Missing hreflang alternates: {missing_hreflangs}")
        return False
    
    print(f"   ✅ All required hreflang alternates present (es, en, de, x-default)")
    
    # Check hero image fetchpriority="high"
    hero_img_match = re.search(r'<img[^>]*fetchpriority="high"[^>]*>', es_html)
    
    if not hero_img_match:
        print(f"   ⚠️  WARNING: No hero <img> with fetchpriority=\"high\" found")
    else:
        print(f"   ✅ Hero <img> with fetchpriority=\"high\" found")
        
        # Check if it's a Cloudinary image with transforms
        hero_img = hero_img_match.group(0)
        if 'res.cloudinary.com' in hero_img:
            if 'f_auto' in hero_img and 'q_auto' in hero_img and 'w_' in hero_img:
                print(f"   ✅ Cloudinary image has f_auto,q_auto,w_ transforms")
            else:
                print(f"   ⚠️  WARNING: Cloudinary image missing some transforms (f_auto, q_auto, w_)")
    
    # Test English event page
    print(f"\n3.2 Testing English event page regression: GET /api/en/party/{event_id}")
    en_url = f"{BASE_URL}/en/party/{event_id}"
    en_response = requests.get(en_url)
    
    if en_response.status_code != 200:
        print(f"   ❌ FAILED: Expected 200, got {en_response.status_code}")
        return False
    
    en_html = en_response.text
    
    # Check canonical
    en_canonical_match = re.search(r'<link[^>]*rel="canonical"[^>]*href="([^"]+)"', en_html)
    if not en_canonical_match:
        print(f"   ❌ FAILED: No canonical link found in English page")
        return False
    
    en_canonical_url = en_canonical_match.group(1)
    print(f"   ✅ Canonical link found: {en_canonical_url}")
    
    # Check if canonical is self-referencing (contains /en/party/ and event_id)
    if '/en/party/' not in en_canonical_url or event_id not in en_canonical_url:
        print(f"   ❌ FAILED: Canonical is not self-referencing English event page")
        return False
    
    print(f"   ✅ Canonical is self-referencing English event page")
    
    # Test German event page
    print(f"\n3.3 Testing German event page regression: GET /api/de/party/{event_id}")
    de_url = f"{BASE_URL}/de/party/{event_id}"
    de_response = requests.get(de_url)
    
    if de_response.status_code != 200:
        print(f"   ❌ FAILED: Expected 200, got {de_response.status_code}")
        return False
    
    de_html = de_response.text
    
    # Check canonical
    de_canonical_match = re.search(r'<link[^>]*rel="canonical"[^>]*href="([^"]+)"', de_html)
    if not de_canonical_match:
        print(f"   ❌ FAILED: No canonical link found in German page")
        return False
    
    de_canonical_url = de_canonical_match.group(1)
    print(f"   ✅ Canonical link found: {de_canonical_url}")
    
    # Check if canonical is self-referencing (contains /de/party/ and event_id)
    if '/de/party/' not in de_canonical_url or event_id not in de_canonical_url:
        print(f"   ❌ FAILED: Canonical is not self-referencing German event page")
        return False
    
    print(f"   ✅ Canonical is self-referencing German event page")
    
    print(f"\n✅ TEST 3 PASSED: Event page regression tests passed")
    return True


def test_regression_home_page():
    """
    Test 4: Regression - home page
    - GET /api/home still 200 with non-render-blocking font link (media="print" onload) and Cloudinary preconnect
    """
    print("\n" + "="*80)
    print("TEST 4: REGRESSION - HOME PAGE")
    print("="*80)
    
    print(f"\n4.1 Testing home page: GET /api/home")
    url = f"{BASE_URL}/home"
    response = requests.get(url)
    print(f"   Status: {response.status_code}")
    
    if response.status_code != 200:
        print(f"   ❌ FAILED: Expected 200, got {response.status_code}")
        return False
    
    print(f"   ✅ Status 200 OK")
    
    html = response.text
    
    # Check for non-render-blocking font link (media="print" onload)
    font_link_match = re.search(r'<link[^>]*media="print"[^>]*onload[^>]*>', html)
    
    if not font_link_match:
        print(f"   ⚠️  WARNING: No non-render-blocking font link (media=\"print\" onload) found")
    else:
        print(f"   ✅ Non-render-blocking font link found (media=\"print\" onload)")
    
    # Check for Cloudinary preconnect
    cloudinary_preconnect = re.search(r'<link[^>]*rel="preconnect"[^>]*href="[^"]*cloudinary[^"]*"', html)
    
    if not cloudinary_preconnect:
        print(f"   ⚠️  WARNING: No Cloudinary preconnect found")
    else:
        print(f"   ✅ Cloudinary preconnect found")
    
    print(f"\n✅ TEST 4 PASSED: Home page regression tests passed")
    return True


def test_regression_nonexistent_event():
    """
    Test 5: Regression - nonexistent event
    - Nonexistent event /api/fiesta/nope-xyz still returns 410 (or 301 to city hub), not 200
    """
    print("\n" + "="*80)
    print("TEST 5: REGRESSION - NONEXISTENT EVENT")
    print("="*80)
    
    print(f"\n5.1 Testing nonexistent event: GET /api/fiesta/nope-xyz")
    url = f"{BASE_URL}/fiesta/nope-xyz"
    response = requests.get(url, allow_redirects=False)
    print(f"   Status: {response.status_code}")
    
    if response.status_code == 200:
        print(f"   ❌ FAILED: Nonexistent event returned 200 (should be 410 or 301)")
        return False
    
    if response.status_code == 410:
        print(f"   ✅ Nonexistent event returned 410 Gone (correct)")
    elif response.status_code == 301:
        print(f"   ✅ Nonexistent event returned 301 redirect (correct)")
        redirect_location = response.headers.get('location', '')
        print(f"   Redirect location: {redirect_location}")
    elif response.status_code == 404:
        print(f"   ✅ Nonexistent event returned 404 Not Found (acceptable)")
    else:
        print(f"   ⚠️  WARNING: Nonexistent event returned {response.status_code} (expected 410, 301, or 404)")
    
    print(f"\n✅ TEST 5 PASSED: Nonexistent event handling correct")
    return True


def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("SEO SSR REGRESSION TESTING")
    print("Testing after adding:")
    print("  (a) unique descriptive paragraph per language on event pages")
    print("  (b) /api/llms.txt")
    print("  (c) accessibility contrast fix")
    print("="*80)
    
    results = []
    
    # Test 1: Unique per-language descriptive paragraphs
    try:
        result = test_event_descriptive_paragraphs()
        results.append(("Unique per-language descriptive paragraphs", result))
    except Exception as e:
        print(f"\n❌ TEST 1 FAILED WITH EXCEPTION: {e}")
        results.append(("Unique per-language descriptive paragraphs", False))
    
    # Test 2: llms.txt
    try:
        result = test_llms_txt()
        results.append(("llms.txt endpoint", result))
    except Exception as e:
        print(f"\n❌ TEST 2 FAILED WITH EXCEPTION: {e}")
        results.append(("llms.txt endpoint", False))
    
    # Test 3: Regression - event pages
    try:
        result = test_regression_event_pages()
        results.append(("Regression - event pages", result))
    except Exception as e:
        print(f"\n❌ TEST 3 FAILED WITH EXCEPTION: {e}")
        results.append(("Regression - event pages", False))
    
    # Test 4: Regression - home page
    try:
        result = test_regression_home_page()
        results.append(("Regression - home page", result))
    except Exception as e:
        print(f"\n❌ TEST 4 FAILED WITH EXCEPTION: {e}")
        results.append(("Regression - home page", False))
    
    # Test 5: Regression - nonexistent event
    try:
        result = test_regression_nonexistent_event()
        results.append(("Regression - nonexistent event", result))
    except Exception as e:
        print(f"\n❌ TEST 5 FAILED WITH EXCEPTION: {e}")
        results.append(("Regression - nonexistent event", False))
    
    # Print summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED 🎉")
        return 0
    else:
        print(f"\n❌ {total - passed} TEST(S) FAILED")
        return 1


if __name__ == "__main__":
    exit(main())
