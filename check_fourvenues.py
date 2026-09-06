#!/usr/bin/env python3
"""Check what's actually in the FourVenues API for REGGAETON event."""

import requests
import json
import unicodedata
import re
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

BASE_URL = "https://poll-integration-dev.preview.emergentagent.com/api"
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

# Get the FourVenues token from backend
admin_token = login_admin()
headers_api = {"Authorization": f"Bearer {admin_token}"}

# Get the token
print("Getting FourVenues token...")
resp = requests.get(f"{BASE_URL}/admin/scrapers/fourvenues-token", headers=headers_api)
token_data = resp.json()
print(f"Token configured: {token_data.get('configured')}")
print(f"Token valid: {token_data.get('valid')}")

# We can't get the actual token from the API (it's masked), so let's check the backend .env
print("\nChecking backend .env for token...")
with open("/app/backend/.env", "r") as f:
    for line in f:
        if line.startswith("FOURVENUES_GUEST_TOKEN"):
            token = line.split("=", 1)[1].strip()
            print(f"Found token (first 50 chars): {token[:50]}...")
            break

# Now query the FourVenues API directly
print("\nQuerying FourVenues API for 'quienva' slug...")
now = datetime.now(timezone.utc)
start = int((now - timedelta(days=1)).timestamp())
end = int((now + timedelta(days=200)).timestamp())

headers_fv = {
    "Authorization": f"Bearer {token}",
    "Origin": "https://site.fourvenues.com",
    "Referer": "https://site.fourvenues.com/",
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
}

resp = requests.get(
    "https://cli-api-service.fourvenues.com/api/events",
    params={
        "startDate": start,
        "endDate": end,
        "slug": "quienva",
        "pageSize": 200,
        "page": 1,
        "orderBy": "startDate",
        "orderType": "asc"
    },
    headers=headers_fv
)

print(f"Response status: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    items = data.get("data", []) if isinstance(data, dict) else data
    print(f"Total events: {len(items)}")
    
    # Find REGGAETON events
    print("\nSearching for REGGAETON events...")
    mad = ZoneInfo("Europe/Madrid")
    for item in items:
        name = str(item.get("name") or "").strip()
        if "REGGAETON" in name.upper():
            dates = item.get("dates") or {}
            ts = dates.get("start") or dates.get("date")
            date_str = datetime.fromtimestamp(int(ts), tz=mad).strftime("%Y-%m-%d") if ts else "?"
            org = item.get("organization") or {}
            venue = str(org.get("name") or "").strip()
            slug = str(item.get("slug") or item.get("code") or "").strip()
            
            print(f"\nFound REGGAETON event:")
            print(f"  Name: {name}")
            print(f"  Venue: {venue}")
            print(f"  Date: {date_str}")
            print(f"  Slug: {slug}")
            print(f"  Normalized venue: {_norm_name(venue)}")
            print(f"  Normalized name: {_norm_name(name)}")
            print(f"  Key: ({_norm_name(venue)}, {date_str}, {_norm_name(name)})")
else:
    print(f"Error: {resp.text}")
