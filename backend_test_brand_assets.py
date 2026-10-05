#!/usr/bin/env python3
"""
Test script for brand icon/favicon/manifest file serving.
Verifies that the backend correctly serves all brand assets needed for Googlebot.
"""

import requests
import json
import sys

# Backend base URL from frontend/.env
BASE_URL = "https://quienva-tonight.preview.emergentagent.com"

def test_endpoint(url, expected_status, expected_content_type_prefix, expected_min_size=None, check_json=False):
    """Test a single endpoint and return results."""
    try:
        response = requests.get(url, timeout=10)
        status = response.status_code
        content_type = response.headers.get('Content-Type', '')
        content_length = len(response.content)
        
        # Check status
        status_ok = status == expected_status
        
        # Check content-type (prefix match for flexibility)
        content_type_ok = content_type.startswith(expected_content_type_prefix) if expected_content_type_prefix else True
        
        # Check size if specified
        size_ok = content_length >= expected_min_size if expected_min_size else True
        
        # Check JSON validity if specified
        json_ok = True
        json_data = None
        if check_json and status == 200:
            try:
                json_data = response.json()
                json_ok = True
            except Exception:
                json_ok = False
        
        return {
            'url': url,
            'status': status,
            'status_ok': status_ok,
            'content_type': content_type,
            'content_type_ok': content_type_ok,
            'content_length': content_length,
            'size_ok': size_ok,
            'json_ok': json_ok,
            'json_data': json_data,
            'success': status_ok and content_type_ok and size_ok and json_ok
        }
    except Exception as e:
        return {
            'url': url,
            'error': str(e),
            'success': False
        }

def main():
    print("=" * 80)
    print("TESTING BRAND ICON/FAVICON/MANIFEST FILE SERVING")
    print("=" * 80)
    print(f"Backend URL: {BASE_URL}")
    print()
    
    tests = [
        {
            'name': 'Test 1: favicon.ico',
            'url': f'{BASE_URL}/api/favicon.ico',
            'expected_status': 200,
            'expected_content_type': 'image/',  # Accept image/x-icon or image/vnd.microsoft.icon
            'expected_min_size': 5000,  # ~7KB expected
            'check_json': False
        },
        {
            'name': 'Test 2: icons/icon-512.png',
            'url': f'{BASE_URL}/api/icons/icon-512.png',
            'expected_status': 200,
            'expected_content_type': 'image/png',
            'expected_min_size': 30000,  # ~34KB expected
            'check_json': False
        },
        {
            'name': 'Test 3: icons/icon-192.png',
            'url': f'{BASE_URL}/api/icons/icon-192.png',
            'expected_status': 200,
            'expected_content_type': 'image/png',
            'expected_min_size': 1000,  # Some reasonable size
            'check_json': False
        },
        {
            'name': 'Test 4: apple-touch-icon.png',
            'url': f'{BASE_URL}/api/apple-touch-icon.png',
            'expected_status': 200,
            'expected_content_type': 'image/png',
            'expected_min_size': 1000,
            'check_json': False
        },
        {
            'name': 'Test 5: favicon-96x96.png',
            'url': f'{BASE_URL}/api/favicon-96x96.png',
            'expected_status': 200,
            'expected_content_type': 'image/png',
            'expected_min_size': 1000,
            'check_json': False
        },
        {
            'name': 'Test 6: manifest.json',
            'url': f'{BASE_URL}/api/manifest.json',
            'expected_status': 200,
            'expected_content_type': 'application/',  # Accept application/manifest+json or application/json
            'expected_min_size': 50,
            'check_json': True
        },
        {
            'name': 'Test 7: API root (regression check)',
            'url': f'{BASE_URL}/api/',
            'expected_status': 200,
            'expected_content_type': 'application/json',
            'expected_min_size': 10,
            'check_json': True
        }
    ]
    
    results = []
    all_passed = True
    
    for test in tests:
        print(f"\n{test['name']}")
        print("-" * 80)
        
        result = test_endpoint(
            test['url'],
            test['expected_status'],
            test['expected_content_type'],
            test.get('expected_min_size'),
            test.get('check_json', False)
        )
        
        results.append(result)
        
        if 'error' in result:
            print(f"❌ ERROR: {result['error']}")
            all_passed = False
        else:
            # Status
            status_icon = "✅" if result['status_ok'] else "❌"
            print(f"{status_icon} Status: {result['status']} (expected {test['expected_status']})")
            
            # Content-Type
            ct_icon = "✅" if result['content_type_ok'] else "❌"
            print(f"{ct_icon} Content-Type: {result['content_type']} (expected prefix: {test['expected_content_type']})")
            
            # Size
            if test.get('expected_min_size'):
                size_icon = "✅" if result['size_ok'] else "❌"
                print(f"{size_icon} Content-Length: {result['content_length']} bytes (expected >= {test['expected_min_size']})")
            else:
                print(f"   Content-Length: {result['content_length']} bytes")
            
            # JSON validation
            if test.get('check_json'):
                json_icon = "✅" if result['json_ok'] else "❌"
                print(f"{json_icon} JSON Valid: {result['json_ok']}")
                if result['json_data']:
                    print(f"   JSON Data: {json.dumps(result['json_data'], indent=2)}")
            
            # Overall
            if result['success']:
                print(f"✅ PASS")
            else:
                print(f"❌ FAIL")
                all_passed = False
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    passed = sum(1 for r in results if r['success'])
    total = len(results)
    
    print(f"\nTests Passed: {passed}/{total}")
    
    for i, result in enumerate(results, 1):
        icon = "✅" if result['success'] else "❌"
        test_name = tests[i-1]['name']
        print(f"{icon} {test_name}")
        if not result['success'] and 'error' not in result:
            if not result.get('status_ok'):
                print(f"   - Status: {result['status']} (expected {tests[i-1]['expected_status']})")
            if not result.get('content_type_ok'):
                print(f"   - Content-Type: {result['content_type']} (expected {tests[i-1]['expected_content_type']})")
            if not result.get('size_ok'):
                print(f"   - Size: {result['content_length']} bytes (expected >= {tests[i-1].get('expected_min_size')})")
            if not result.get('json_ok'):
                print(f"   - JSON validation failed")
    
    print("\n" + "=" * 80)
    if all_passed:
        print("✅ ALL TESTS PASSED - Brand assets are being served correctly")
        print("=" * 80)
        return 0
    else:
        print("❌ SOME TESTS FAILED - See details above")
        print("=" * 80)
        return 1

if __name__ == '__main__':
    sys.exit(main())
