#!/usr/bin/env python3
"""
Backend test for Annual Wrapped endpoint + Monthly Wrapped regression
Review request: Verify NEW ANNUAL wrapped endpoint GET /api/me/wrapped/year
and confirm monthly one still works after refactor.
"""

import requests
import json
import time
from datetime import datetime
import io

# Backend URL from frontend/.env
BASE_URL = "https://reciprocal-landing.preview.emergentagent.com/api"

# Test credentials
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

# Test counters
tests_passed = 0
tests_failed = 0

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def assert_equal(actual, expected, field_name):
    global tests_passed, tests_failed
    if actual == expected:
        log(f"  ✅ {field_name}: {actual}")
        tests_passed += 1
        return True
    else:
        log(f"  ❌ {field_name}: expected {expected}, got {actual}")
        tests_failed += 1
        return False

def assert_true(condition, message):
    global tests_passed, tests_failed
    if condition:
        log(f"  ✅ {message}")
        tests_passed += 1
        return True
    else:
        log(f"  ❌ {message}")
        tests_failed += 1
        return False

def assert_in(item, container, message):
    global tests_passed, tests_failed
    if item in container:
        log(f"  ✅ {message}")
        tests_passed += 1
        return True
    else:
        log(f"  ❌ {message} - {item} not in {container}")
        tests_failed += 1
        return False

# ============================================================
# STEP 1: Admin Login
# ============================================================
log("\n" + "="*60)
log("STEP 1: Admin Login")
log("="*60)

response = requests.post(f"{BASE_URL}/auth/login", json={
    "email": ADMIN_EMAIL,
    "password": ADMIN_PASSWORD
})

assert_equal(response.status_code, 200, "Admin login status")
admin_data = response.json()
admin_token = admin_data.get("token")
assert_true(admin_token is not None, "Admin token received")

admin_headers = {"Authorization": f"Bearer {admin_token}"}

# ============================================================
# STEP 2: Create 3 Events
# ============================================================
log("\n" + "="*60)
log("STEP 2: Create 3 Events")
log("="*60)

# Event A: 2026-05-10, Sala X, Reggaeton
log("\nCreating Event A (2026-05-10, Sala X, Reggaeton)...")
event_a_data = {
    "name": "Fiesta Reggaeton A",
    "venue": "Sala X",
    "date": "2026-05-10",
    "time": "23:00",
    "genre": "Reggaeton",
    "city": "Palma de Mallorca",
    "description": "Test event A",
    "image_url": "https://example.com/a.jpg"
}
response = requests.post(f"{BASE_URL}/admin/events", json=event_a_data, headers=admin_headers)
assert_equal(response.status_code, 200, "Event A creation status")
event_a = response.json()
event_a_id = event_a.get("id")
log(f"  Event A ID: {event_a_id}")

# Event B: 2026-05-20, Sala X, Reggaeton
log("\nCreating Event B (2026-05-20, Sala X, Reggaeton)...")
event_b_data = {
    "name": "Fiesta Reggaeton B",
    "venue": "Sala X",
    "date": "2026-05-20",
    "time": "23:00",
    "genre": "Reggaeton",
    "city": "Palma de Mallorca",
    "description": "Test event B",
    "image_url": "https://example.com/b.jpg"
}
response = requests.post(f"{BASE_URL}/admin/events", json=event_b_data, headers=admin_headers)
assert_equal(response.status_code, 200, "Event B creation status")
event_b = response.json()
event_b_id = event_b.get("id")
log(f"  Event B ID: {event_b_id}")

# Event C: 2026-03-15, Sala Y, Techno
log("\nCreating Event C (2026-03-15, Sala Y, Techno)...")
event_c_data = {
    "name": "Fiesta Techno C",
    "venue": "Sala Y",
    "date": "2026-03-15",
    "time": "23:00",
    "genre": "Techno",
    "city": "Palma de Mallorca",
    "description": "Test event C",
    "image_url": "https://example.com/c.jpg"
}
response = requests.post(f"{BASE_URL}/admin/events", json=event_c_data, headers=admin_headers)
assert_equal(response.status_code, 200, "Event C creation status")
event_c = response.json()
event_c_id = event_c.get("id")
log(f"  Event C ID: {event_c_id}")

# ============================================================
# STEP 3: Register User U1
# ============================================================
log("\n" + "="*60)
log("STEP 3: Register User U1")
log("="*60)

timestamp = int(time.time())
u1_username = f"u1_{timestamp}"
u1_email = f"u1_{timestamp}@test.com"
u1_password = "password123"

u1_data = {
    "email": u1_email,
    "username": u1_username,
    "password": u1_password,
    "name": "User One",
    "birthdate": "1995-01-01",
    "city": "Palma de Mallorca"
}

response = requests.post(f"{BASE_URL}/auth/register", json=u1_data)
assert_equal(response.status_code, 200, "U1 registration status")
u1_response = response.json()
u1_token = u1_response.get("token")
assert_true(u1_token is not None, "U1 token received")

u1_headers = {"Authorization": f"Bearer {u1_token}"}

# ============================================================
# STEP 4: U1 marks "estuve" on all 3 events
# ============================================================
log("\n" + "="*60)
log("STEP 4: U1 marks 'estuve' on all 3 events")
log("="*60)

for event_id, event_name in [(event_a_id, "Event A"), (event_b_id, "Event B"), (event_c_id, "Event C")]:
    log(f"\nMarking 'estuve' on {event_name}...")
    response = requests.post(
        f"{BASE_URL}/events/{event_id}/interest",
        json={"status": "estuve"},
        headers=u1_headers
    )
    assert_equal(response.status_code, 200, f"{event_name} interest status")

# ============================================================
# STEP 5: VERIFY ANNUAL - GET /api/me/wrapped/year?year=2026
# ============================================================
log("\n" + "="*60)
log("STEP 5: VERIFY ANNUAL - GET /api/me/wrapped/year?year=2026")
log("="*60)

response = requests.get(f"{BASE_URL}/me/wrapped/year?year=2026", headers=u1_headers)
assert_equal(response.status_code, 200, "Annual wrapped status")

annual_data = response.json()
log(f"\nAnnual Wrapped Response: {json.dumps(annual_data, indent=2)}")

# Verify all required fields
assert_equal(annual_data.get("is_year"), True, "is_year")
assert_equal(annual_data.get("has_data"), True, "has_data")
assert_equal(annual_data.get("parties"), 3, "parties")
assert_equal(annual_data.get("venues"), 2, "venues (Sala X and Sala Y)")
assert_equal(annual_data.get("top_genre"), "Reggaeton", "top_genre")

# Check top_month
top_month = annual_data.get("top_month")
assert_true(top_month is not None, "top_month exists")
if top_month:
    assert_equal(top_month.get("name"), "Mayo", "top_month.name")
    assert_equal(top_month.get("count"), 2, "top_month.count")

assert_equal(annual_data.get("active_months"), 2, "active_months (March and May)")
assert_equal(annual_data.get("month"), "2026", "month")
assert_equal(annual_data.get("month_label"), "2026", "month_label")

title = annual_data.get("title")
assert_true(title is not None and len(title) > 0, f"title is non-empty string: '{title}'")

# ============================================================
# STEP 6: DEFAULT ANNUAL - GET /api/me/wrapped/year (no year param)
# ============================================================
log("\n" + "="*60)
log("STEP 6: DEFAULT ANNUAL - GET /api/me/wrapped/year (no year param)")
log("="*60)

response = requests.get(f"{BASE_URL}/me/wrapped/year", headers=u1_headers)
assert_equal(response.status_code, 200, "Default annual wrapped status")

default_annual = response.json()
log(f"\nDefault Annual Wrapped Response: {json.dumps(default_annual, indent=2)}")

assert_equal(default_annual.get("month"), "2026", "month (current year)")
assert_equal(default_annual.get("is_year"), True, "is_year")

# ============================================================
# STEP 7: EMPTY YEAR - GET /api/me/wrapped/year?year=2019
# ============================================================
log("\n" + "="*60)
log("STEP 7: EMPTY YEAR - GET /api/me/wrapped/year?year=2019")
log("="*60)

response = requests.get(f"{BASE_URL}/me/wrapped/year?year=2019", headers=u1_headers)
assert_equal(response.status_code, 200, "Empty year wrapped status")

empty_year = response.json()
log(f"\nEmpty Year Wrapped Response: {json.dumps(empty_year, indent=2)}")

assert_equal(empty_year.get("has_data"), False, "has_data")
assert_equal(empty_year.get("parties"), 0, "parties")
assert_equal(empty_year.get("is_year"), True, "is_year")
assert_equal(empty_year.get("month"), "2019", "month")

# ============================================================
# STEP 8: REGRESSION MONTHLY - GET /api/me/wrapped?month=2026-05
# ============================================================
log("\n" + "="*60)
log("STEP 8: REGRESSION MONTHLY - GET /api/me/wrapped?month=2026-05")
log("="*60)

response = requests.get(f"{BASE_URL}/me/wrapped?month=2026-05", headers=u1_headers)
assert_equal(response.status_code, 200, "Monthly wrapped status")

monthly_may = response.json()
log(f"\nMonthly Wrapped (May) Response: {json.dumps(monthly_may, indent=2)}")

assert_equal(monthly_may.get("parties"), 2, "parties (only May events A+B)")
assert_equal(monthly_may.get("is_year"), False, "is_year")
assert_equal(monthly_may.get("venues"), 1, "venues (only Sala X)")
assert_equal(monthly_may.get("top_genre"), "Reggaeton", "top_genre")

# ============================================================
# STEP 9: REGRESSION MONTHLY - GET /api/me/wrapped?month=2026-03
# ============================================================
log("\n" + "="*60)
log("STEP 9: REGRESSION MONTHLY - GET /api/me/wrapped?month=2026-03")
log("="*60)

response = requests.get(f"{BASE_URL}/me/wrapped?month=2026-03", headers=u1_headers)
assert_equal(response.status_code, 200, "Monthly wrapped (March) status")

monthly_march = response.json()
log(f"\nMonthly Wrapped (March) Response: {json.dumps(monthly_march, indent=2)}")

assert_equal(monthly_march.get("parties"), 1, "parties (only March event C)")
assert_equal(monthly_march.get("is_year"), False, "is_year")
assert_equal(monthly_march.get("top_genre"), "Techno", "top_genre")

# ============================================================
# FINAL SUMMARY
# ============================================================
log("\n" + "="*60)
log("FINAL SUMMARY")
log("="*60)
log(f"✅ Tests Passed: {tests_passed}")
log(f"❌ Tests Failed: {tests_failed}")
log(f"📊 Total Tests: {tests_passed + tests_failed}")

if tests_failed == 0:
    log("\n🎉 ALL TESTS PASSED!")
    exit(0)
else:
    log(f"\n⚠️  {tests_failed} TEST(S) FAILED")
    exit(1)
