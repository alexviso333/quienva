#!/usr/bin/env python3
"""
Backend test for SEO routes HEAD request bug fix
Testing sitemap/robots/SEO routes to ensure they accept both GET and HEAD requests
"""
import requests
import sys
import os
from typing import Dict, Tuple

# Base URL from frontend/.env
BASE_URL = "https://multilang-feed-core.preview.emergentagent.com"
API_BASE = f"{BASE_URL}/api"

# Required headers for all requests
HEADERS = {
    "x-forwarded-host": "quienva.me",
    "x-forwarded-proto": "https"
}

# Admin credentials
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

# Test results storage
test_results = []

def log_test(test_name: str, passed: bool, details: str = ""):
    """Log test result"""
    status = "✅ PASS" if passed else "❌ FAIL"
    result = f"{status}: {test_name}"
    if details:
        result += f" - {details}"
    print(result)
    test_results.append({
        "name": test_name,
        "passed": passed,
        "details": details
    })

def test_endpoint(path: str, method: str, expected_status: int, expected_content_type: str) -> Tuple[bool, str]:
    """
    Test an endpoint with specified method
    Returns (passed, details)
    """
    url = f"{API_BASE}{path}"
    try:
        if method == "GET":
            response = requests.get(url, headers=HEADERS, timeout=10)
        elif method == "HEAD":
            response = requests.head(url, headers=HEADERS, timeout=10)
        else:
            return False, f"Invalid method: {method}"
        
        status_ok = response.status_code == expected_status
        content_type = response.headers.get("Content-Type", "")
        content_type_ok = expected_content_type.lower() in content_type.lower()
        
        if status_ok and content_type_ok:
            return True, f"{method} {path} → {response.status_code} {content_type}"
        else:
            details = f"{method} {path} → {response.status_code} {content_type} (expected {expected_status} {expected_content_type})"
            return False, details
            
    except Exception as e:
        return False, f"{method} {path} → ERROR: {str(e)}"

def get_admin_token() -> str:
    """Login as admin and get token"""
    try:
        response = requests.post(
            f"{API_BASE}/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers=HEADERS,
            timeout=10
        )
        if response.status_code == 200:
            return response.json().get("token", "")
        return ""
    except Exception:
        return ""

def get_valid_event_id(token: str) -> str:
    """Get a valid upcoming event ID"""
    try:
        # Try to get events-min (admin endpoint)
        response = requests.get(
            f"{API_BASE}/admin/events-min",
            headers={**HEADERS, "Authorization": f"Bearer {token}"},
            timeout=10
        )
        if response.status_code == 200:
            events = response.json().get("events", [])
            if events:
                return events[0]["id"]
        
        # Fallback: try to get from sitemap
        response = requests.get(
            f"{API_BASE}/sitemap-events-ibiza.xml",
            headers=HEADERS,
            timeout=10
        )
        if response.status_code == 200:
            # Extract first event ID from sitemap
            import re
            match = re.search(r'/fiesta/([a-f0-9-]+)', response.text)
            if match:
                return match.group(1)
        
        return ""
    except Exception:
        return ""

def test_content_sanity(path: str, checks: list) -> Tuple[bool, str]:
    """Test GET response content"""
    url = f"{API_BASE}{path}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            return False, f"GET {path} returned {response.status_code}"
        
        content = response.text
        failed_checks = []
        
        for check in checks:
            if check["type"] == "contains":
                if check["value"] not in content:
                    failed_checks.append(f"Missing: {check['value']}")
            elif check["type"] == "not_contains":
                if check["value"] in content:
                    failed_checks.append(f"Should not contain: {check['value']}")
            elif check["type"] == "starts_with":
                if not content.startswith(check["value"]):
                    failed_checks.append(f"Should start with: {check['value']}")
        
        if failed_checks:
            return False, "; ".join(failed_checks)
        return True, f"Content checks passed for {path}"
        
    except Exception as e:
        return False, f"ERROR: {str(e)}"

def main():
    print("=" * 80)
    print("SEO ROUTES HEAD REQUEST BUG FIX TEST")
    print("=" * 80)
    print(f"Base URL: {BASE_URL}")
    print(f"Headers: {HEADERS}")
    print()
    
    # Test 1: /api/sitemap.xml
    print("TEST 1: /api/sitemap.xml")
    passed, details = test_endpoint("/sitemap.xml", "GET", 200, "application/xml")
    log_test("GET /api/sitemap.xml → 200 application/xml", passed, details)
    
    passed, details = test_endpoint("/sitemap.xml", "HEAD", 200, "application/xml")
    log_test("HEAD /api/sitemap.xml → 200 application/xml (NOT 405, NOT application/json)", passed, details)
    print()
    
    # Test 2: /api/sitemap-cities.xml
    print("TEST 2: /api/sitemap-cities.xml")
    passed, details = test_endpoint("/sitemap-cities.xml", "GET", 200, "application/xml")
    log_test("GET /api/sitemap-cities.xml → 200 application/xml", passed, details)
    
    passed, details = test_endpoint("/sitemap-cities.xml", "HEAD", 200, "application/xml")
    log_test("HEAD /api/sitemap-cities.xml → 200 application/xml", passed, details)
    print()
    
    # Test 3: /api/sitemap-events-ibiza.xml
    print("TEST 3: /api/sitemap-events-ibiza.xml")
    passed, details = test_endpoint("/sitemap-events-ibiza.xml", "GET", 200, "application/xml")
    log_test("GET /api/sitemap-events-ibiza.xml → 200 application/xml", passed, details)
    
    passed, details = test_endpoint("/sitemap-events-ibiza.xml", "HEAD", 200, "application/xml")
    log_test("HEAD /api/sitemap-events-ibiza.xml → 200 application/xml", passed, details)
    print()
    
    # Test 4: /api/robots.txt
    print("TEST 4: /api/robots.txt")
    passed, details = test_endpoint("/robots.txt", "GET", 200, "text/plain")
    log_test("GET /api/robots.txt → 200 text/plain", passed, details)
    
    passed, details = test_endpoint("/robots.txt", "HEAD", 200, "text/plain")
    log_test("HEAD /api/robots.txt → 200 text/plain", passed, details)
    print()
    
    # Test 5: /api/ciudad/madrid
    print("TEST 5: /api/ciudad/madrid")
    passed, details = test_endpoint("/ciudad/madrid", "GET", 200, "text/html")
    log_test("GET /api/ciudad/madrid → 200 text/html", passed, details)
    
    passed, details = test_endpoint("/ciudad/madrid", "HEAD", 200, "text/html")
    log_test("HEAD /api/ciudad/madrid → 200 text/html", passed, details)
    print()
    
    # Test 6: /api/fiesta/{valid_id}
    print("TEST 6: /api/fiesta/{valid_id}")
    print("Getting admin token...")
    token = get_admin_token()
    if token:
        print("✓ Admin login successful")
        event_id = get_valid_event_id(token)
        if event_id:
            print(f"✓ Found valid event ID: {event_id}")
            
            passed, details = test_endpoint(f"/fiesta/{event_id}", "GET", 200, "text/html")
            log_test(f"GET /api/fiesta/{event_id} → 200 text/html", passed, details)
            
            passed, details = test_endpoint(f"/fiesta/{event_id}", "HEAD", 200, "text/html")
            log_test(f"HEAD /api/fiesta/{event_id} → 200 text/html", passed, details)
        else:
            log_test("Get valid event ID", False, "Could not retrieve event ID")
    else:
        log_test("Admin login", False, "Could not login as admin")
    print()
    
    # Test 7: Content sanity - GET /api/sitemap.xml
    print("TEST 7: Content sanity - GET /api/sitemap.xml")
    passed, details = test_content_sanity("/sitemap.xml", [
        {"type": "starts_with", "value": "<?xml"},
        {"type": "contains", "value": "<sitemapindex"},
        {"type": "contains", "value": "https://www.quienva.me/sitemap-cities.xml"},
        {"type": "not_contains", "value": "application/json"},
        {"type": "not_contains", "value": "405"}
    ])
    log_test("GET /api/sitemap.xml content: starts with <?xml, contains <sitemapindex>, uses www host", passed, details)
    print()
    
    # Test 8: Content sanity - GET /api/sitemap-cities.xml
    print("TEST 8: Content sanity - GET /api/sitemap-cities.xml")
    passed, details = test_content_sanity("/sitemap-cities.xml", [
        {"type": "contains", "value": "<url>"},
        {"type": "contains", "value": "https://www.quienva.me"},
        {"type": "contains", "value": "/fiestas/palma"},
        {"type": "contains", "value": "/fiestas/ibiza"},
        {"type": "contains", "value": "/fiestas/madrid"},
        {"type": "contains", "value": "/fiestas/barcelona"},
        {"type": "contains", "value": "/fiestas/marbella"},
        {"type": "not_contains", "value": "palma-de-mallorca"},
        {"type": "not_contains", "value": "application/json"},
        {"type": "not_contains", "value": "405"}
    ])
    log_test("GET /api/sitemap-cities.xml content: contains <url>, uses www host, uses SHORT city slugs", passed, details)
    print()
    
    # Summary
    print("=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    total = len(test_results)
    passed = sum(1 for r in test_results if r["passed"])
    failed = total - passed
    
    print(f"Total tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print()
    
    if failed > 0:
        print("FAILED TESTS:")
        for result in test_results:
            if not result["passed"]:
                print(f"  ❌ {result['name']}")
                if result["details"]:
                    print(f"     {result['details']}")
        print()
    
    # Create results table
    print("RESULTS TABLE:")
    print("-" * 80)
    print(f"{'Endpoint':<40} {'Method':<8} {'Status':<10} {'Content-Type':<20}")
    print("-" * 80)
    
    endpoints = [
        ("/api/sitemap.xml", "GET", "200", "application/xml"),
        ("/api/sitemap.xml", "HEAD", "200", "application/xml"),
        ("/api/sitemap-cities.xml", "GET", "200", "application/xml"),
        ("/api/sitemap-cities.xml", "HEAD", "200", "application/xml"),
        ("/api/sitemap-events-ibiza.xml", "GET", "200", "application/xml"),
        ("/api/sitemap-events-ibiza.xml", "HEAD", "200", "application/xml"),
        ("/api/robots.txt", "GET", "200", "text/plain"),
        ("/api/robots.txt", "HEAD", "200", "text/plain"),
        ("/api/ciudad/madrid", "GET", "200", "text/html"),
        ("/api/ciudad/madrid", "HEAD", "200", "text/html"),
        ("/api/fiesta/{id}", "GET", "200", "text/html"),
        ("/api/fiesta/{id}", "HEAD", "200", "text/html"),
    ]
    
    for endpoint, method, status, content_type in endpoints:
        # Find matching test result
        test_name = f"{method} {endpoint}"
        result = next((r for r in test_results if test_name in r["name"]), None)
        if result:
            status_icon = "✅" if result["passed"] else "❌"
            print(f"{endpoint:<40} {method:<8} {status:<10} {content_type:<20} {status_icon}")
        else:
            print(f"{endpoint:<40} {method:<8} {status:<10} {content_type:<20} ⚠️")
    
    print("-" * 80)
    print()
    
    if failed == 0:
        print("🎉 ALL TESTS PASSED! Bug fix verified successfully.")
        return 0
    else:
        print("⚠️  SOME TESTS FAILED. Bug fix needs attention.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
