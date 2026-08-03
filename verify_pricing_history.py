#!/usr/bin/env python3
"""
Additional verification for pricing history details
"""

import requests
import json

BASE_URL = "https://04ef964d-e7a3-4272-aa05-db85d0d80903.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

# Login as admin
resp = requests.post(f"{BASE_URL}/auth/login", json={
    "email": ADMIN_EMAIL,
    "password": ADMIN_PASSWORD
})
admin_token = resp.json().get("token")
admin_headers = {"Authorization": f"Bearer {admin_token}"}

# Get an event
resp = requests.get(f"{BASE_URL}/events", headers=admin_headers)
events = resp.json()
event_id = events[0]["id"]

print(f"Testing with event ID: {event_id}")

# Get current history
resp = requests.get(f"{BASE_URL}/admin/events/{event_id}/history", headers=admin_headers)
data = resp.json()
print(f"\nCurrent history total: {data['total']}")

# Make a pricing change with different price
new_pricing = {
    "price_tiers": [
        {"name": "Early Bird", "price": 15.0, "sold_out": False},
        {"name": "General", "price": 30.0, "sold_out": False}
    ],
    "sale_state": "a_la_venta",
    "silent": False
}

print(f"\nChanging pricing to: {json.dumps(new_pricing, indent=2)}")
resp = requests.put(f"{BASE_URL}/admin/events/{event_id}/pricing", 
                    headers=admin_headers,
                    json=new_pricing)
print(f"PUT response status: {resp.status_code}")

# Get history again
resp = requests.get(f"{BASE_URL}/admin/events/{event_id}/history", headers=admin_headers)
data = resp.json()
print(f"\nNew history total: {data['total']}")

# Show last 3 entries
print(f"\nLast 3 history entries:")
for i, entry in enumerate(data['entries'][:3]):
    print(f"\n{i+1}. Entry:")
    print(f"   Source: {entry.get('source')}")
    print(f"   Kind: {entry.get('kind')}")
    print(f"   Created at: {entry.get('created_at')}")
    print(f"   Details: {json.dumps(entry.get('details', {}), indent=6)}")
