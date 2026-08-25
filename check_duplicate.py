import requests

BACKEND_URL = "https://production-deploy-26.preview.emergentagent.com"
API_BASE = f"{BACKEND_URL}/api"

# Login as admin
response = requests.post(
    f"{API_BASE}/auth/login",
    json={"email": "admin@quienva.app", "password": "admin123"},
    timeout=10
)

token = response.json().get("token")
headers = {"Authorization": f"Bearer {token}"}

# Update city to Ibiza
requests.put(
    f"{API_BASE}/auth/profile",
    headers=headers,
    json={"city": "Ibiza"},
    timeout=10
)

# Get events
response = requests.get(
    f"{API_BASE}/events",
    headers=headers,
    params={"city": "Ibiza"},
    timeout=10
)

events = response.json()

# Find the duplicate
shine_events = [e for e in events if e.get("name") == "SHINE Ibiza" and e.get("venue") == "528 Ibiza" and e.get("date") == "2026-09-24"]

print(f"Found {len(shine_events)} SHINE Ibiza events on 2026-09-24 at 528 Ibiza:")
for i, event in enumerate(shine_events, 1):
    print(f"\n{i}. Event ID: {event.get('id')}")
    print(f"   Name: {event.get('name')}")
    print(f"   Venue: {event.get('venue')}")
    print(f"   Date: {event.get('date')}")
    print(f"   Time: {event.get('time')}")
    print(f"   Commission URL: {event.get('commission_url')}")
    print(f"   Scraper Venue ID: {event.get('scraper_venue_id')}")
    print(f"   External ID: {event.get('external_id')}")
