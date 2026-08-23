#!/usr/bin/env python3
"""
Check actual history entry structure
"""

import requests
import json

BASE_URL = "https://fullstack-chat-app-1.preview.emergentagent.com/api"
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

# Get history
resp = requests.get(f"{BASE_URL}/admin/events/{event_id}/history", headers=admin_headers)
data = resp.json()

print(f"Event: {data['name']}")
print(f"Total history entries: {data['total']}")
print(f"\nAll fields in latest entry:")
print(json.dumps(data['entries'][0], indent=2))
