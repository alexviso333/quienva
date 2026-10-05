#!/usr/bin/env python3
"""
Detailed validation of Artist/DJ SEO pages JSON-LD structure
"""
import requests
import json
from bs4 import BeautifulSoup

BASE_URL = "https://night-preview-1.preview.emergentagent.com/api"
GOOGLEBOT_UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"

def validate_json_ld_structure():
    """
    Detailed validation of JSON-LD structure for carl-cox artist page
    """
    print("\n" + "="*80)
    print("DETAILED JSON-LD VALIDATION")
    print("="*80)
    
    url = f"{BASE_URL}/artista/carl-cox"
    print(f"URL: {url}\n")
    
    headers = {"User-Agent": GOOGLEBOT_UA}
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        print(f"❌ Failed to fetch page: {response.status_code}")
        return False
    
    soup = BeautifulSoup(response.text, 'html.parser')
    json_ld_scripts = soup.find_all('script', type='application/ld+json')
    
    print(f"Found {len(json_ld_scripts)} JSON-LD script tags\n")
    
    valid_events = 0
    
    for i, script in enumerate(json_ld_scripts, 1):
        try:
            data = json.loads(script.string)
            
            if data.get('@type') != 'Event':
                continue
            
            print(f"Event #{valid_events + 1}: {data.get('name', 'N/A')}")
            print("-" * 60)
            
            # Required fields
            required_fields = ['@context', '@type', 'name', 'startDate', 'location', 'offers']
            missing_fields = []
            
            for field in required_fields:
                if field not in data:
                    missing_fields.append(field)
                else:
                    if field == 'offers':
                        print(f"  ✅ {field}: {type(data[field]).__name__}")
                    elif field == 'location':
                        print(f"  ✅ {field}: {data[field].get('name', 'N/A')}")
                    else:
                        value = str(data[field])[:60]
                        print(f"  ✅ {field}: {value}")
            
            if missing_fields:
                print(f"  ❌ Missing required fields: {', '.join(missing_fields)}")
                continue
            
            # Validate offers structure
            offers = data['offers']
            print(f"\n  Offers validation:")
            
            if not isinstance(offers, dict):
                print(f"    ❌ offers is not an object (got {type(offers).__name__})")
                continue
            
            # Check @type
            if offers.get('@type') == 'Offer':
                print(f"    ✅ @type: Offer")
            else:
                print(f"    ❌ @type: {offers.get('@type', 'missing')}")
            
            # Check url
            if 'url' in offers:
                print(f"    ✅ url: {offers['url'][:60]}...")
            else:
                print(f"    ❌ url: missing")
            
            # Check price (optional but good to have)
            if 'price' in offers:
                print(f"    ✅ price: {offers['price']}")
            
            if 'priceCurrency' in offers:
                print(f"    ✅ priceCurrency: {offers['priceCurrency']}")
            
            if 'availability' in offers:
                print(f"    ✅ availability: {offers['availability']}")
            
            # Validate location structure
            location = data['location']
            print(f"\n  Location validation:")
            
            if isinstance(location, dict):
                if location.get('@type') == 'Place':
                    print(f"    ✅ @type: Place")
                else:
                    print(f"    ⚠️  @type: {location.get('@type', 'missing')}")
                
                if 'name' in location:
                    print(f"    ✅ name: {location['name']}")
                
                if 'address' in location:
                    print(f"    ✅ address: present")
            else:
                print(f"    ❌ location is not an object")
            
            valid_events += 1
            print()
            
        except json.JSONDecodeError as e:
            print(f"  ❌ Invalid JSON in script #{i}: {e}\n")
            continue
    
    print("="*80)
    print(f"Summary: {valid_events} valid Event JSON-LD structures found")
    print("="*80)
    
    return valid_events > 0


if __name__ == "__main__":
    success = validate_json_ld_structure()
    exit(0 if success else 1)
