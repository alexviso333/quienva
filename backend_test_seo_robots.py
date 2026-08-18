#!/usr/bin/env python3
"""
Backend SEO Test: robots.txt + X-Robots-Tag on past events
Testing the SEO crawl-budget fix for "¿Quién va?" app
"""

import requests
import sys
from datetime import datetime, timedelta
import re

# Backend URL (internal port)
BASE_URL = "http://localhost:8001/api"

def test_robots_txt():
    """
    Test 1: GET /api/robots.txt
    Verify:
    - HTTP 200
    - Content-Type: text/plain
    - Contains "User-agent: *"
    - Contains Disallow lines for app routes: /event/, /feed, /profile, /chats, /wrapped, /friends, /admin, /login
    - Contains Allow lines for SEO sections: /fiesta/, /discoteca/
    - Contains Sitemap line ending in /sitemap.xml
    - MUST NOT contain "Disallow: /fiesta" or "Disallow: /discoteca" or "Disallow: /fiestas/"
    """
    print("\n" + "="*80)
    print("TEST 1: GET /api/robots.txt")
    print("="*80)
    
    try:
        resp = requests.get(f"{BASE_URL}/robots.txt", timeout=10)
        print(f"Status: {resp.status_code}")
        print(f"Content-Type: {resp.headers.get('Content-Type')}")
        
        # Check status code
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        
        # Check content type
        content_type = resp.headers.get('Content-Type', '')
        assert 'text/plain' in content_type, f"Expected text/plain, got {content_type}"
        
        body = resp.text
        print(f"\nrobots.txt content ({len(body)} chars):")
        print("-" * 80)
        print(body)
        print("-" * 80)
        
        # Check required content
        assert "User-agent: *" in body, "Missing 'User-agent: *'"
        print("✓ Contains 'User-agent: *'")
        
        # Check Disallow lines for app routes
        required_disallows = ["/event/", "/feed", "/profile", "/chats", "/wrapped", "/friends", "/admin", "/login"]
        for path in required_disallows:
            assert f"Disallow: {path}" in body, f"Missing 'Disallow: {path}'"
            print(f"✓ Contains 'Disallow: {path}'")
        
        # Check Allow lines for SEO sections
        required_allows = ["/fiesta/", "/discoteca/"]
        for path in required_allows:
            assert f"Allow: {path}" in body, f"Missing 'Allow: {path}'"
            print(f"✓ Contains 'Allow: {path}'")
        
        # Check Sitemap line
        assert "Sitemap:" in body and "/sitemap.xml" in body, "Missing Sitemap line"
        print("✓ Contains Sitemap line ending in /sitemap.xml")
        
        # CRITICAL: Check that SEO pages are NOT disallowed
        # We need to check for exact lines, not substrings
        lines = body.split('\n')
        forbidden_patterns = ["Disallow: /fiesta/", "Disallow: /discoteca/", "Disallow: /fiestas/"]
        for pattern in forbidden_patterns:
            # Check if any line exactly matches the forbidden pattern (allowing for whitespace)
            found = any(line.strip() == pattern for line in lines)
            assert not found, f"CRITICAL ERROR: Found exact line '{pattern}' - SEO pages must NOT be disallowed!"
            print(f"✓ Does NOT contain exact line '{pattern}' (SEO pages remain crawlable)")
        
        print("\n✅ TEST 1 PASSED: robots.txt is correct")
        return True
        
    except AssertionError as e:
        print(f"\n❌ TEST 1 FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n❌ TEST 1 ERROR: {e}")
        return False


def create_test_event(date_str, name_suffix):
    """
    Helper: Create a test event in MongoDB
    Returns event_id or None
    """
    from pymongo import MongoClient
    import uuid
    
    try:
        client = MongoClient("mongodb://localhost:27017")
        db = client["quienva_dev"]
        events = db["events"]
        
        event_id = str(uuid.uuid4())
        event = {
            "id": event_id,
            "name": f"SEO Test Event {name_suffix}",
            "venue": "Test Venue",
            "city": "madrid",
            "date": date_str,
            "time": "23:00",
            "image_url": "https://example.com/test.jpg",
            "genre": "Electronic",
            "sale_state": "a_la_venta",
            "price": 20.0,
            "commission_url": "https://example.com/tickets",
        }
        
        events.insert_one(event)
        print(f"✓ Created test event: {event_id} (date: {date_str})")
        return event_id
        
    except Exception as e:
        print(f"✗ Failed to create test event: {e}")
        return None


def delete_test_event(event_id):
    """
    Helper: Delete a test event from MongoDB
    """
    from pymongo import MongoClient
    
    try:
        client = MongoClient("mongodb://localhost:27017")
        db = client["quienva_dev"]
        events = db["events"]
        
        result = events.delete_one({"id": event_id})
        if result.deleted_count > 0:
            print(f"✓ Deleted test event: {event_id}")
        else:
            print(f"✗ Test event not found: {event_id}")
            
    except Exception as e:
        print(f"✗ Failed to delete test event: {e}")


def test_past_event_robots_tag():
    """
    Test 2: Past event with X-Robots-Tag header
    - Create a PAST event (date < today)
    - GET /api/fiesta/{past_id}
    - Expect: HTTP 200
    - Expect: Response header "X-Robots-Tag: noindex, follow"
    - Expect: HTML contains <meta name="robots" content="noindex, follow">
    """
    print("\n" + "="*80)
    print("TEST 2: Past event with X-Robots-Tag header")
    print("="*80)
    
    # Create past event (yesterday)
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    past_event_id = create_test_event(yesterday, "PAST")
    
    if not past_event_id:
        print("❌ TEST 2 FAILED: Could not create test event")
        return False
    
    try:
        resp = requests.get(f"{BASE_URL}/fiesta/{past_event_id}", timeout=10)
        print(f"\nStatus: {resp.status_code}")
        print(f"Headers: {dict(resp.headers)}")
        
        # Check status code
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        print("✓ Status code: 200")
        
        # Check X-Robots-Tag header
        x_robots_tag = resp.headers.get('X-Robots-Tag', '')
        print(f"\nX-Robots-Tag header: '{x_robots_tag}'")
        assert x_robots_tag, "Missing X-Robots-Tag header"
        assert "noindex" in x_robots_tag.lower(), f"X-Robots-Tag should contain 'noindex', got: {x_robots_tag}"
        assert "follow" in x_robots_tag.lower(), f"X-Robots-Tag should contain 'follow', got: {x_robots_tag}"
        print("✓ X-Robots-Tag header present: 'noindex, follow'")
        
        # Check HTML meta robots tag
        body = resp.text
        meta_robots_match = re.search(r'<meta\s+name=["\']robots["\']\s+content=["\']([^"\']+)["\']', body, re.IGNORECASE)
        if meta_robots_match:
            meta_content = meta_robots_match.group(1)
            print(f"\nHTML meta robots tag: '{meta_content}'")
            assert "noindex" in meta_content.lower(), f"Meta robots should contain 'noindex', got: {meta_content}"
            assert "follow" in meta_content.lower(), f"Meta robots should contain 'follow', got: {meta_content}"
            print("✓ HTML contains <meta name='robots' content='noindex, follow'>")
        else:
            raise AssertionError("HTML does not contain <meta name='robots'> tag")
        
        print("\n✅ TEST 2 PASSED: Past event has correct X-Robots-Tag header and meta tag")
        return True
        
    except AssertionError as e:
        print(f"\n❌ TEST 2 FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n❌ TEST 2 ERROR: {e}")
        return False
    finally:
        # Clean up
        delete_test_event(past_event_id)


def test_future_event_no_robots_tag():
    """
    Test 3: Future event WITHOUT X-Robots-Tag header
    - Create an UPCOMING event (date > today)
    - GET /api/fiesta/{future_id}
    - Expect: HTTP 200
    - Expect: NO X-Robots-Tag header
    - Expect: HTML contains <meta name="robots" content="index,follow">
    """
    print("\n" + "="*80)
    print("TEST 3: Future event WITHOUT X-Robots-Tag header")
    print("="*80)
    
    # Create future event (tomorrow)
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    future_event_id = create_test_event(tomorrow, "FUTURE")
    
    if not future_event_id:
        print("❌ TEST 3 FAILED: Could not create test event")
        return False
    
    try:
        resp = requests.get(f"{BASE_URL}/fiesta/{future_event_id}", timeout=10)
        print(f"\nStatus: {resp.status_code}")
        print(f"Headers: {dict(resp.headers)}")
        
        # Check status code
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        print("✓ Status code: 200")
        
        # Check NO X-Robots-Tag header
        x_robots_tag = resp.headers.get('X-Robots-Tag', '')
        print(f"\nX-Robots-Tag header: '{x_robots_tag}'")
        assert not x_robots_tag, f"X-Robots-Tag header should NOT be present for future events, got: {x_robots_tag}"
        print("✓ NO X-Robots-Tag header (as expected for future events)")
        
        # Check HTML meta robots tag
        body = resp.text
        meta_robots_match = re.search(r'<meta\s+name=["\']robots["\']\s+content=["\']([^"\']+)["\']', body, re.IGNORECASE)
        if meta_robots_match:
            meta_content = meta_robots_match.group(1)
            print(f"\nHTML meta robots tag: '{meta_content}'")
            assert "index" in meta_content.lower(), f"Meta robots should contain 'index', got: {meta_content}"
            assert "follow" in meta_content.lower(), f"Meta robots should contain 'follow', got: {meta_content}"
            # Should NOT contain "noindex"
            assert "noindex" not in meta_content.lower(), f"Meta robots should NOT contain 'noindex' for future events, got: {meta_content}"
            print("✓ HTML contains <meta name='robots' content='index,follow'> (no 'noindex')")
        else:
            raise AssertionError("HTML does not contain <meta name='robots'> tag")
        
        print("\n✅ TEST 3 PASSED: Future event has NO X-Robots-Tag and correct meta tag")
        return True
        
    except AssertionError as e:
        print(f"\n❌ TEST 3 FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n❌ TEST 3 ERROR: {e}")
        return False
    finally:
        # Clean up
        delete_test_event(future_event_id)


def test_regression():
    """
    Test 4: Regression tests
    - GET /api/ → 200
    - GET /api/sitemap.xml → 200 valid XML
    - GET /api/sitemap-events-madrid.xml → 200
    """
    print("\n" + "="*80)
    print("TEST 4: Regression tests")
    print("="*80)
    
    all_passed = True
    
    # Test 4a: GET /api/
    try:
        resp = requests.get(f"{BASE_URL}/", timeout=10)
        print(f"\n4a. GET /api/ → Status: {resp.status_code}")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        print("✓ GET /api/ returns 200")
    except Exception as e:
        print(f"✗ GET /api/ failed: {e}")
        all_passed = False
    
    # Test 4b: GET /api/sitemap.xml
    try:
        resp = requests.get(f"{BASE_URL}/sitemap.xml", timeout=10)
        print(f"\n4b. GET /api/sitemap.xml → Status: {resp.status_code}")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        
        # Check it's valid XML
        body = resp.text
        assert body.startswith("<?xml"), "Response should start with <?xml"
        assert "<sitemapindex" in body or "<urlset" in body, "Response should contain sitemap XML"
        print("✓ GET /api/sitemap.xml returns 200 with valid XML")
    except Exception as e:
        print(f"✗ GET /api/sitemap.xml failed: {e}")
        all_passed = False
    
    # Test 4c: GET /api/sitemap-events-madrid.xml
    try:
        resp = requests.get(f"{BASE_URL}/sitemap-events-madrid.xml", timeout=10)
        print(f"\n4c. GET /api/sitemap-events-madrid.xml → Status: {resp.status_code}")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        print("✓ GET /api/sitemap-events-madrid.xml returns 200")
    except Exception as e:
        print(f"✗ GET /api/sitemap-events-madrid.xml failed: {e}")
        all_passed = False
    
    if all_passed:
        print("\n✅ TEST 4 PASSED: All regression tests passed")
    else:
        print("\n❌ TEST 4 FAILED: Some regression tests failed")
    
    return all_passed


def main():
    print("\n" + "="*80)
    print("BACKEND SEO TEST: robots.txt + X-Robots-Tag on past events")
    print("Testing '¿Quién va?' app SEO crawl-budget fix")
    print("="*80)
    
    results = []
    
    # Run all tests
    results.append(("robots.txt content", test_robots_txt()))
    results.append(("Past event X-Robots-Tag", test_past_event_robots_tag()))
    results.append(("Future event no X-Robots-Tag", test_future_event_no_robots_tag()))
    results.append(("Regression tests", test_regression()))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed ({passed*100//total}%)")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        sys.exit(0)
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
