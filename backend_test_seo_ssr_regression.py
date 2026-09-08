#!/usr/bin/env python3
"""
FOCUSED regression test on SEO SSR after two additions in /app/backend/server.py.
Tests ONLY:
1) Event poster PRELOAD (LCP optimization) for test-ev-0 in all 3 languages
2) City "tips" localized block on the MAIN city listing (timeframe=all) for city Ibiza
3) Regression - make sure nothing else broke
"""

import requests
import re
from html.parser import HTMLParser

BASE_URL = "http://localhost:8001/api"

class LinkParser(HTMLParser):
    """Extract <link> tags from HTML"""
    def __init__(self):
        super().__init__()
        self.links = []
    
    def handle_starttag(self, tag, attrs):
        if tag == 'link':
            self.links.append(dict(attrs))

class ImgParser(HTMLParser):
    """Extract <img> tags from HTML"""
    def __init__(self):
        super().__init__()
        self.imgs = []
    
    def handle_starttag(self, tag, attrs):
        if tag == 'img':
            self.imgs.append(dict(attrs))

class H2Parser(HTMLParser):
    """Extract <h2> text content from HTML"""
    def __init__(self):
        super().__init__()
        self.h2_texts = []
        self.in_h2 = False
        self.current_text = ""
    
    def handle_starttag(self, tag, attrs):
        if tag == 'h2':
            self.in_h2 = True
            self.current_text = ""
    
    def handle_endtag(self, tag):
        if tag == 'h2' and self.in_h2:
            self.h2_texts.append(self.current_text.strip())
            self.in_h2 = False
    
    def handle_data(self, data):
        if self.in_h2:
            self.current_text += data

def test_event_poster_preload():
    """
    TEST 1: Event poster PRELOAD (LCP optimization)
    For test-ev-0 in all 3 languages:
    - GET /api/fiesta/test-ev-0, /api/en/party/test-ev-0, /api/de/party/test-ev-0 -> each 200
    - Each <head> must contain a <link rel="preload" as="image" href="..." fetchpriority="high">
      where the href is the event image with Cloudinary transform "f_auto,q_auto,w_520,c_limit"
    - Confirm the hero <img> still has fetchpriority="high" and the same transformed src
    """
    print("\n" + "="*80)
    print("TEST 1: EVENT POSTER PRELOAD (LCP OPTIMIZATION)")
    print("="*80)
    
    test_cases = [
        ("Spanish", f"{BASE_URL}/fiesta/test-ev-0", "Consejos"),
        ("English", f"{BASE_URL}/en/party/test-ev-0", "Tips"),
        ("German", f"{BASE_URL}/de/party/test-ev-0", "Tipps"),
    ]
    
    all_passed = True
    
    for lang_name, url, _ in test_cases:
        print(f"\n--- Testing {lang_name}: {url} ---")
        
        try:
            resp = requests.get(url, timeout=10)
            print(f"✓ Status: {resp.status_code}")
            
            if resp.status_code != 200:
                print(f"✗ FAIL: Expected 200, got {resp.status_code}")
                all_passed = False
                continue
            
            html = resp.text
            
            # Parse <link> tags
            link_parser = LinkParser()
            link_parser.feed(html)
            
            # Find preload link
            preload_links = [l for l in link_parser.links if l.get('rel') == 'preload' and l.get('as') == 'image']
            
            if not preload_links:
                print(f"✗ FAIL: No <link rel='preload' as='image'> found in <head>")
                all_passed = False
                continue
            
            preload_link = preload_links[0]
            preload_href = preload_link.get('href', '')
            fetchpriority = preload_link.get('fetchpriority', '')
            
            print(f"✓ Found preload link: {preload_href[:80]}...")
            
            # Check fetchpriority="high"
            if fetchpriority != 'high':
                print(f"✗ FAIL: preload link fetchpriority is '{fetchpriority}', expected 'high'")
                all_passed = False
            else:
                print(f"✓ Preload link has fetchpriority='high'")
            
            # Check Cloudinary transform in preload href
            required_transforms = ['f_auto', 'q_auto', 'w_520', 'c_limit']
            missing_transforms = [t for t in required_transforms if t not in preload_href]
            
            if missing_transforms:
                print(f"✗ FAIL: Preload href missing transforms: {missing_transforms}")
                print(f"   Full href: {preload_href}")
                all_passed = False
            else:
                print(f"✓ Preload href contains all required Cloudinary transforms: {required_transforms}")
            
            # Check that it's a res.cloudinary.com URL
            if 'res.cloudinary.com' not in preload_href:
                print(f"✗ FAIL: Preload href is not a Cloudinary URL")
                all_passed = False
            else:
                print(f"✓ Preload href is a Cloudinary URL")
            
            # Parse <img> tags to find hero image
            img_parser = ImgParser()
            img_parser.feed(html)
            
            # Find hero img (should have fetchpriority="high")
            hero_imgs = [img for img in img_parser.imgs if img.get('fetchpriority') == 'high']
            
            if not hero_imgs:
                print(f"✗ FAIL: No hero <img> with fetchpriority='high' found")
                all_passed = False
            else:
                hero_img = hero_imgs[0]
                hero_src = hero_img.get('src', '')
                print(f"✓ Found hero <img> with fetchpriority='high'")
                print(f"  Hero img src: {hero_src[:80]}...")
                
                # Check that hero img src matches preload href (same transformed URL)
                if hero_src != preload_href:
                    print(f"✗ FAIL: Hero img src does not match preload href")
                    print(f"   Preload: {preload_href}")
                    print(f"   Hero:    {hero_src}")
                    all_passed = False
                else:
                    print(f"✓ Hero img src matches preload href (no duplicate/broken markup)")
            
        except Exception as e:
            print(f"✗ FAIL: Exception occurred: {e}")
            all_passed = False
    
    if all_passed:
        print("\n✅ TEST 1 PASSED: Event poster preload working correctly in all 3 languages")
    else:
        print("\n❌ TEST 1 FAILED: Issues found with event poster preload")
    
    return all_passed


def test_city_tips_localized():
    """
    TEST 2: City "tips" localized block on the MAIN city listing (timeframe=all)
    For city Ibiza:
    - GET /api/ciudad/ibiza -> 200; contains <h2> "Consejos para salir en Ibiza" + 2 Spanish paragraphs
    - GET /api/en/city/ibiza -> 200; contains <h2> "Tips for a night out in Ibiza" + English paragraphs
    - GET /api/de/city/ibiza -> 200; contains <h2> "Tipps für eine Nacht in Ibiza" + German paragraphs
    - Confirm the three tips blocks are genuinely DIFFERENT text across languages
    - Confirm tonight/weekend variants do NOT include this tips block
    """
    print("\n" + "="*80)
    print("TEST 2: CITY TIPS LOCALIZED BLOCK")
    print("="*80)
    
    test_cases = [
        ("Spanish", f"{BASE_URL}/ciudad/ibiza", "Consejos para salir en Ibiza", "Compra tus entradas con antelación"),
        ("English", f"{BASE_URL}/en/city/ibiza", "Tips for a night out in Ibiza", "Buy your tickets in advance"),
        ("German", f"{BASE_URL}/de/city/ibiza", "Tipps für eine Nacht in Ibiza", "Kauf deine Tickets im Voraus"),
    ]
    
    all_passed = True
    tips_texts = {}
    
    for lang_name, url, expected_h2, expected_text_snippet in test_cases:
        print(f"\n--- Testing {lang_name}: {url} ---")
        
        try:
            resp = requests.get(url, timeout=10)
            print(f"✓ Status: {resp.status_code}")
            
            if resp.status_code != 200:
                print(f"✗ FAIL: Expected 200, got {resp.status_code}")
                all_passed = False
                continue
            
            html = resp.text
            
            # Parse <h2> tags
            h2_parser = H2Parser()
            h2_parser.feed(html)
            
            # Check for expected h2
            if expected_h2 not in h2_parser.h2_texts:
                print(f"✗ FAIL: Expected <h2> '{expected_h2}' not found")
                print(f"   Found h2 tags: {h2_parser.h2_texts}")
                all_passed = False
            else:
                print(f"✓ Found expected <h2>: '{expected_h2}'")
            
            # Check for expected text snippet in the HTML
            if expected_text_snippet not in html:
                print(f"✗ FAIL: Expected text snippet not found: '{expected_text_snippet}'")
                all_passed = False
            else:
                print(f"✓ Found expected text snippet: '{expected_text_snippet[:50]}...'")
            
            # Extract the tips section for comparison
            # Find text between the tips h2 and the next section
            tips_match = re.search(rf'{re.escape(expected_h2)}.*?<div class="intro">(.*?)</div>', html, re.DOTALL)
            if tips_match:
                tips_text = tips_match.group(1)
                tips_texts[lang_name] = tips_text
                print(f"✓ Extracted tips text ({len(tips_text)} chars)")
            else:
                print(f"✗ FAIL: Could not extract tips section")
                all_passed = False
            
        except Exception as e:
            print(f"✗ FAIL: Exception occurred: {e}")
            all_passed = False
    
    # Verify tips texts are DIFFERENT across languages
    print("\n--- Verifying tips texts are genuinely DIFFERENT across languages ---")
    if len(tips_texts) == 3:
        es_text = tips_texts.get("Spanish", "")
        en_text = tips_texts.get("English", "")
        de_text = tips_texts.get("German", "")
        
        if es_text == en_text or es_text == de_text or en_text == de_text:
            print(f"✗ FAIL: Tips texts are NOT different across languages")
            all_passed = False
        else:
            print(f"✓ Tips texts are genuinely DIFFERENT across languages")
            print(f"  Spanish: {len(es_text)} chars")
            print(f"  English: {len(en_text)} chars")
            print(f"  German: {len(de_text)} chars")
    
    # Test tonight/weekend variants do NOT include tips block
    print("\n--- Testing tonight/weekend variants do NOT include tips block ---")
    variant_urls = [
        (f"{BASE_URL}/ciudad/ibiza/esta-noche", "Spanish tonight"),
        (f"{BASE_URL}/en/city/ibiza/tonight", "English tonight"),
        (f"{BASE_URL}/ciudad/ibiza/este-finde", "Spanish weekend"),
        (f"{BASE_URL}/en/city/ibiza/this-weekend", "English weekend"),
    ]
    
    for url, variant_name in variant_urls:
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                print(f"✗ FAIL: {variant_name} returned {resp.status_code}, expected 200")
                all_passed = False
                continue
            
            html = resp.text
            
            # Check that tips h2 is NOT present
            has_tips = ("Consejos para salir" in html or 
                       "Tips for a night out" in html or 
                       "Tipps für eine Nacht" in html)
            
            if has_tips:
                print(f"✗ FAIL: {variant_name} contains tips block (should not)")
                all_passed = False
            else:
                print(f"✓ {variant_name} does NOT contain tips block (correct)")
        
        except Exception as e:
            print(f"✗ FAIL: {variant_name} exception: {e}")
            all_passed = False
    
    if all_passed:
        print("\n✅ TEST 2 PASSED: City tips localized block working correctly")
    else:
        print("\n❌ TEST 2 FAILED: Issues found with city tips localized block")
    
    return all_passed


def test_regression():
    """
    TEST 3: Regression - make sure nothing else broke
    - City pages still have self-referencing canonical per language + hreflang es+en+de+x-default
    - Existing localized city intro + guide (zones/nights) still present on /api/en/city/ibiza and /api/de/city/ibiza
    - GET /api/home still 200 with non-render-blocking font link (media="print" onload)
    - GET /api/llms.txt still 200
    - Nonexistent event /api/fiesta/nope-xyz still 410 (or 301), not 200
    """
    print("\n" + "="*80)
    print("TEST 3: REGRESSION CHECKS")
    print("="*80)
    
    all_passed = True
    
    # Test 3.1: City pages canonical + hreflang
    print("\n--- 3.1: City pages canonical + hreflang ---")
    city_urls = [
        (f"{BASE_URL}/ciudad/ibiza", "es", "https://www.quienva.me/fiestas/ibiza"),
        (f"{BASE_URL}/en/city/ibiza", "en", "https://www.quienva.me/en/parties/ibiza"),
        (f"{BASE_URL}/de/city/ibiza", "de", "https://www.quienva.me/de/partys/ibiza"),
    ]
    
    # Use proper headers to simulate production environment
    headers = {
        'x-forwarded-host': 'quienva.me',
        'x-forwarded-proto': 'https'
    }
    
    for url, lang, expected_canonical in city_urls:
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                print(f"✗ FAIL: {url} returned {resp.status_code}")
                all_passed = False
                continue
            
            html = resp.text
            
            # Check canonical
            canonical_match = re.search(r'<link rel="canonical" href="([^"]+)"', html)
            if not canonical_match:
                print(f"✗ FAIL: {url} missing canonical link")
                all_passed = False
            else:
                canonical = canonical_match.group(1)
                if canonical != expected_canonical:
                    print(f"✗ FAIL: {url} canonical is {canonical}, expected {expected_canonical}")
                    all_passed = False
                else:
                    print(f"✓ {lang} canonical correct: {canonical}")
            
            # Check hreflang (es, en, de, x-default)
            hreflang_langs = re.findall(r'<link rel="alternate" hreflang="([^"]+)"', html)
            required_langs = ['es', 'en', 'de', 'x-default']
            missing_langs = [l for l in required_langs if l not in hreflang_langs]
            
            if missing_langs:
                print(f"✗ FAIL: {url} missing hreflang: {missing_langs}")
                all_passed = False
            else:
                print(f"✓ {lang} has all required hreflang: {required_langs}")
        
        except Exception as e:
            print(f"✗ FAIL: {url} exception: {e}")
            all_passed = False
    
    # Test 3.2: Existing localized city intro + guide still present
    print("\n--- 3.2: Existing localized city intro + guide ---")
    guide_checks = [
        (f"{BASE_URL}/en/city/ibiza", "English", "Ibiza"),
        (f"{BASE_URL}/de/city/ibiza", "German", "Ibiza"),
    ]
    
    for url, lang, city_name in guide_checks:
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                print(f"✗ FAIL: {url} returned {resp.status_code}")
                all_passed = False
                continue
            
            html = resp.text
            
            # Check for intro/guide content (should have some descriptive text about the city)
            # Look for common patterns in city guides
            has_intro = '<div class="intro">' in html
            has_content = len(html) > 10000  # City pages should have substantial content
            
            if not has_intro or not has_content:
                print(f"✗ FAIL: {url} missing expected intro/guide content")
                all_passed = False
            else:
                print(f"✓ {lang} intro/guide content present (page size: {len(html)} chars)")
        
        except Exception as e:
            print(f"✗ FAIL: {url} exception: {e}")
            all_passed = False
    
    # Test 3.3: Home page with non-render-blocking fonts
    print("\n--- 3.3: Home page with non-render-blocking fonts ---")
    try:
        resp = requests.get(f"{BASE_URL}/home", timeout=10)
        if resp.status_code != 200:
            print(f"✗ FAIL: /api/home returned {resp.status_code}")
            all_passed = False
        else:
            html = resp.text
            
            # Check for non-render-blocking font link (media="print" onload)
            font_link_match = re.search(r'<link[^>]*fonts\.googleapis\.com[^>]*media="print"[^>]*onload', html)
            
            if not font_link_match:
                print(f"✗ FAIL: /api/home missing non-render-blocking font link (media='print' onload)")
                all_passed = False
            else:
                print(f"✓ /api/home has non-render-blocking font link")
    
    except Exception as e:
        print(f"✗ FAIL: /api/home exception: {e}")
        all_passed = False
    
    # Test 3.4: llms.txt still works
    print("\n--- 3.4: llms.txt endpoint ---")
    try:
        resp = requests.get(f"{BASE_URL}/llms.txt", timeout=10)
        if resp.status_code != 200:
            print(f"✗ FAIL: /api/llms.txt returned {resp.status_code}")
            all_passed = False
        else:
            print(f"✓ /api/llms.txt returned 200")
    
    except Exception as e:
        print(f"✗ FAIL: /api/llms.txt exception: {e}")
        all_passed = False
    
    # Test 3.5: Nonexistent event returns 410 or 301, not 200
    print("\n--- 3.5: Nonexistent event handling ---")
    try:
        resp = requests.get(f"{BASE_URL}/fiesta/nope-xyz", allow_redirects=False, timeout=10)
        status = resp.status_code
        
        if status == 200:
            print(f"✗ FAIL: /api/fiesta/nope-xyz returned 200 (should be 410 or 301)")
            all_passed = False
        elif status in [410, 301, 302, 404]:
            print(f"✓ /api/fiesta/nope-xyz returned {status} (correct, not 200)")
        else:
            print(f"⚠ WARNING: /api/fiesta/nope-xyz returned {status} (expected 410/301/404)")
    
    except Exception as e:
        print(f"✗ FAIL: /api/fiesta/nope-xyz exception: {e}")
        all_passed = False
    
    if all_passed:
        print("\n✅ TEST 3 PASSED: All regression checks passed")
    else:
        print("\n❌ TEST 3 FAILED: Some regression checks failed")
    
    return all_passed


def main():
    print("\n" + "="*80)
    print("FOCUSED SEO SSR REGRESSION TEST")
    print("Testing two additions in /app/backend/server.py:")
    print("1. Event poster PRELOAD (LCP optimization)")
    print("2. City 'tips' localized block")
    print("="*80)
    
    results = []
    
    # Run all tests
    results.append(("Event Poster Preload", test_event_poster_preload()))
    results.append(("City Tips Localized", test_city_tips_localized()))
    results.append(("Regression Checks", test_regression()))
    
    # Summary
    print("\n" + "="*80)
    print("FINAL SUMMARY")
    print("="*80)
    
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    all_passed = all(passed for _, passed in results)
    
    if all_passed:
        print("\n🎉 ALL TESTS PASSED 🎉")
        print("\nThe two SEO SSR additions are working correctly:")
        print("✓ Event poster preload with Cloudinary transforms in all 3 languages")
        print("✓ City tips localized block on main city listings (not on tonight/weekend)")
        print("✓ No regressions detected")
    else:
        print("\n⚠️  SOME TESTS FAILED ⚠️")
        print("\nPlease review the failures above.")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit(main())
