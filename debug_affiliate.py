#!/usr/bin/env python3
"""Debug script to check affiliate matching."""

import requests
import json
import unicodedata
import re

BASE_URL = "https://url-validation-fix.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

def _norm_name(s):
    """Same normalization as backend."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())

def login_admin():
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    return resp.json()["token"]

# Login
admin_token = login_admin()
headers = {"Authorization": f"Bearer {admin_token}"}

# Get affiliate status to see what events we have
print("Fetching affiliate status...")
resp = requests.get(f"{BASE_URL}/admin/affiliate-status", headers=headers)
data = resp.json()

print(f"\nAffiliate slug: {data['slug']}")
print(f"Mine count: {data['mine_count']}")
print(f"\nVenues with REGGAETON:")
for venue in data['venues']:
    if 'REGGAETON' in venue['venue'].upper():
        print(f"  - {venue['venue']} ({venue['city']}) - {venue['events']} events")

# Test normalization
test_venue = "REGGAETON MILLENNIAL FEST"
test_name = "REGGAETON MILLENNIAL FEST 2026 - MADRID"
test_date = "2026-10-03"

print(f"\nNormalization test:")
print(f"  Venue: '{test_venue}' -> '{_norm_name(test_venue)}'")
print(f"  Name: '{test_name}' -> '{_norm_name(test_name)}'")
print(f"  Date: '{test_date}'")
print(f"  Key: ({_norm_name(test_venue)}, {test_date}, {_norm_name(test_name)})")

# Create the event
print(f"\nCreating test event...")
event_data = {
    "name": test_name,
    "venue": test_venue,
    "city": "Madrid",
    "date": test_date,
    "time": "23:00",
    "has_commission": True,
    "commission_url": "https://site.fourvenues.com/es/whatever/events/x"
}
resp = requests.post(f"{BASE_URL}/admin/events", json=event_data, headers=headers)
event = resp.json()
event_id = event["id"]

print(f"Event created: {event_id}")
print(f"  name: {event.get('name')}")
print(f"  venue: {event.get('venue')}")
print(f"  date: {event.get('date')}")

# Get the event back
print(f"\nFetching event back...")
resp = requests.get(f"{BASE_URL}/events/{event_id}", headers=headers)
event = resp.json()

print(f"Event retrieved:")
print(f"  name: {event.get('name')}")
print(f"  venue: {event.get('venue')}")
print(f"  date: {event.get('date')}")
print(f"  commission_url: {event.get('commission_url')}")
print(f"  is_affiliate: {event.get('is_affiliate')}")

# Cleanup
print(f"\nCleaning up...")
requests.delete(f"{BASE_URL}/admin/events/{event_id}", headers=headers)
print("Done")
