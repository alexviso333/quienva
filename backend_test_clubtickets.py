#!/usr/bin/env python3
"""
ClubTickets Full Coverage Testing
Tests the ClubTickets affiliate integration for 15 Ibiza clubs
"""

import requests
import json
import sys
from typing import Dict, Any, List

# Configuration
BACKEND_URL = "https://performance-analyzer-24.preview.emergentagent.com"
API_BASE = f"{BACKEND_URL}/api"

# Admin credentials from /app/memory/test_credentials.md
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

# Expected 15 discoteca clubs in Ibiza
EXPECTED_CLUBS = [
    "Lío Ibiza",
    "Eden Ibiza",
    "Es Paradis Ibiza",
    "Chinois Ibiza",
    "Swag Ibiza",
    "Ibiza Rocks",
    "[UNVRS]",
    "O Beach Ibiza",
    "528 Ibiza",
    "Baloo Ibiza",
    "Bambuku Ibiza",
    "Playa Soleil",
    "Teatro Pereyra",
    "Ushuaïa Ibiza",
    "Hï Ibiza"
]

class TestRunner:
    def __init__(self):
        self.admin_token = None
        self.admin_user = None
        self.passed = 0
        self.failed = 0
        self.results = []
        
    def log(self, message: str, level: str = "INFO"):
        """Log a message"""
        prefix = {
            "INFO": "ℹ️",
            "SUCCESS": "✅",
            "FAIL": "❌",
            "WARN": "⚠️"
        }.get(level, "•")
        print(f"{prefix} {message}")
        
    def test(self, name: str, condition: bool, details: str = ""):
        """Record a test result"""
        if condition:
            self.passed += 1
            self.log(f"PASS: {name}", "SUCCESS")
            if details:
                print(f"   {details}")
            self.results.append({"name": name, "passed": True, "details": details})
        else:
            self.failed += 1
            self.log(f"FAIL: {name}", "FAIL")
            if details:
                print(f"   {details}")
            self.results.append({"name": name, "passed": False, "details": details})
    
    def login_admin(self) -> bool:
        """Login as admin and store token"""
        self.log("Logging in as admin...")
        try:
            response = requests.post(
                f"{API_BASE}/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                self.admin_token = data.get("token")
                self.admin_user = data.get("user")
                self.log(f"Admin login successful. User ID: {self.admin_user.get('id')}", "SUCCESS")
                return True
            else:
                self.log(f"Admin login failed: {response.status_code} - {response.text}", "FAIL")
                return False
        except Exception as e:
            self.log(f"Admin login error: {str(e)}", "FAIL")
            return False
    
    def get_headers(self) -> Dict[str, str]:
        """Get headers with admin token"""
        return {
            "Authorization": f"Bearer {self.admin_token}",
            "Content-Type": "application/json"
        }
    
    def update_admin_city(self, city: str) -> bool:
        """Update admin user's city"""
        self.log(f"Updating admin city to: {city}")
        
        # Try PUT /api/auth/profile first
        try:
            response = requests.put(
                f"{API_BASE}/auth/profile",
                headers=self.get_headers(),
                json={"city": city},
                timeout=10
            )
            
            if response.status_code == 200:
                self.log(f"Admin city updated to {city} via /auth/profile", "SUCCESS")
                return True
        except Exception as e:
            self.log(f"PUT /auth/profile failed: {str(e)}", "WARN")
        
        # Try PUT /api/me
        try:
            response = requests.put(
                f"{API_BASE}/me",
                headers=self.get_headers(),
                json={"city": city},
                timeout=10
            )
            
            if response.status_code == 200:
                self.log(f"Admin city updated to {city} via /me", "SUCCESS")
                return True
        except Exception as e:
            self.log(f"PUT /me failed: {str(e)}", "WARN")
        
        # Try PATCH /api/auth/me
        try:
            response = requests.patch(
                f"{API_BASE}/auth/me",
                headers=self.get_headers(),
                json={"city": city},
                timeout=10
            )
            
            if response.status_code == 200:
                self.log(f"Admin city updated to {city} via PATCH /auth/me", "SUCCESS")
                return True
        except Exception as e:
            self.log(f"PATCH /auth/me failed: {str(e)}", "WARN")
        
        self.log(f"Failed to update admin city to {city}", "FAIL")
        return False
    
    def test_a_directory_no_duplicates(self):
        """
        A) DIRECTORY (no duplicates): GET /api/venues?type=discoteca (as admin with city=Ibiza).
        Confirm ALL 15 discoteca tiles exist and [UNVRS] appears EXACTLY ONCE.
        """
        self.log("\n" + "="*80)
        self.log("TEST A: DIRECTORY (no duplicates)")
        self.log("="*80)
        
        # First, update admin city to Ibiza
        if not self.update_admin_city("Ibiza"):
            self.test("A) Update admin city to Ibiza", False, "Failed to update city")
            return
        
        self.test("A) Update admin city to Ibiza", True, "City updated successfully")
        
        # Get venues with type=discoteca
        try:
            response = requests.get(
                f"{API_BASE}/venues",
                headers=self.get_headers(),
                params={"type": "discoteca"},
                timeout=10
            )
            
            self.test(
                "A) GET /api/venues?type=discoteca returns 200",
                response.status_code == 200,
                f"Status: {response.status_code}"
            )
            
            if response.status_code != 200:
                self.log(f"Response: {response.text}", "FAIL")
                return
            
            venues = response.json()
            venue_names = [v.get("name", "") for v in venues]
            
            self.log(f"Found {len(venues)} discoteca venues")
            self.log(f"Venue names: {venue_names}")
            
            # Check all 15 expected clubs exist
            missing_clubs = []
            for club in EXPECTED_CLUBS:
                if club not in venue_names:
                    missing_clubs.append(club)
            
            self.test(
                "A) All 15 expected clubs exist",
                len(missing_clubs) == 0,
                f"Missing clubs: {missing_clubs}" if missing_clubs else "All 15 clubs found"
            )
            
            # Check [UNVRS] appears exactly once
            unvrs_count = venue_names.count("[UNVRS]")
            self.test(
                "A) [UNVRS] appears EXACTLY ONCE (no duplicate)",
                unvrs_count == 1,
                f"[UNVRS] count: {unvrs_count}"
            )
            
            # List all venues for debugging
            self.log("\nAll discoteca venues found:")
            for i, venue in enumerate(venues, 1):
                self.log(f"  {i}. {venue.get('name')} (id: {venue.get('id')}, slug: {venue.get('slug')})")
            
        except Exception as e:
            self.test("A) GET /api/venues?type=discoteca", False, f"Error: {str(e)}")
    
    def test_b_scraper_runs(self):
        """
        B) SCRAPER RUNS: As admin, list scraper venues and run scrapers for:
           - Lío Ibiza (slug lio-ibiza): expect ok=true, events>0
           - [UNVRS] (slug unvrs-ibiza): expect ok=true, events>0
        """
        self.log("\n" + "="*80)
        self.log("TEST B: SCRAPER RUNS")
        self.log("="*80)
        
        # Get all scrapers
        try:
            response = requests.get(
                f"{API_BASE}/admin/scrapers",
                headers=self.get_headers(),
                timeout=10
            )
            
            self.test(
                "B) GET /api/admin/scrapers returns 200",
                response.status_code == 200,
                f"Status: {response.status_code}"
            )
            
            if response.status_code != 200:
                self.log(f"Response: {response.text}", "FAIL")
                return
            
            scrapers = response.json()
            self.log(f"Found {len(scrapers)} total scrapers")
            
            # Find Lío Ibiza scraper
            lio_scraper = None
            for scraper in scrapers:
                if scraper.get("slug") == "lio-ibiza" or "Lío" in scraper.get("name", ""):
                    lio_scraper = scraper
                    break
            
            if lio_scraper:
                self.log(f"Found Lío Ibiza scraper: {lio_scraper.get('name')} (id: {lio_scraper.get('id')})")
                
                # Run Lío Ibiza scraper
                try:
                    run_response = requests.post(
                        f"{API_BASE}/admin/scrapers/{lio_scraper['id']}/run",
                        headers=self.get_headers(),
                        timeout=60
                    )
                    
                    self.test(
                        "B) POST /api/admin/scrapers/{lio_id}/run returns 200",
                        run_response.status_code == 200,
                        f"Status: {run_response.status_code}"
                    )
                    
                    if run_response.status_code == 200:
                        run_data = run_response.json()
                        ok = run_data.get("ok", False)
                        events = run_data.get("events", 0)
                        
                        self.test(
                            "B) Lío Ibiza scraper: ok=true",
                            ok == True,
                            f"ok: {ok}"
                        )
                        
                        self.test(
                            "B) Lío Ibiza scraper: events>0",
                            events > 0,
                            f"events: {events}"
                        )
                        
                        # Check if ClubTickets fallback was used
                        source = run_data.get("summary", {}).get("source", "")
                        if "clubtickets" in source.lower() or "fallback" in source.lower():
                            self.log(f"ClubTickets fallback used: {source}", "INFO")
                        
                        self.log(f"Lío Ibiza scraper result: {json.dumps(run_data, indent=2)}")
                    else:
                        self.log(f"Lío Ibiza scraper run failed: {run_response.text}", "FAIL")
                        
                except Exception as e:
                    self.test("B) Run Lío Ibiza scraper", False, f"Error: {str(e)}")
            else:
                self.test("B) Find Lío Ibiza scraper", False, "Scraper not found")
            
            # Find [UNVRS] scraper
            unvrs_scraper = None
            for scraper in scrapers:
                if scraper.get("slug") == "unvrs-ibiza" or "[UNVRS]" in scraper.get("name", ""):
                    unvrs_scraper = scraper
                    break
            
            if unvrs_scraper:
                self.log(f"Found [UNVRS] scraper: {unvrs_scraper.get('name')} (id: {unvrs_scraper.get('id')})")
                
                # Run [UNVRS] scraper
                try:
                    run_response = requests.post(
                        f"{API_BASE}/admin/scrapers/{unvrs_scraper['id']}/run",
                        headers=self.get_headers(),
                        timeout=60
                    )
                    
                    self.test(
                        "B) POST /api/admin/scrapers/{unvrs_id}/run returns 200",
                        run_response.status_code == 200,
                        f"Status: {run_response.status_code}"
                    )
                    
                    if run_response.status_code == 200:
                        run_data = run_response.json()
                        ok = run_data.get("ok", False)
                        events = run_data.get("events", 0)
                        
                        self.test(
                            "B) [UNVRS] scraper: ok=true",
                            ok == True,
                            f"ok: {ok}"
                        )
                        
                        self.test(
                            "B) [UNVRS] scraper: events>0",
                            events > 0,
                            f"events: {events}"
                        )
                        
                        self.log(f"[UNVRS] scraper result: {json.dumps(run_data, indent=2)}")
                    else:
                        self.log(f"[UNVRS] scraper run failed: {run_response.text}", "FAIL")
                        
                except Exception as e:
                    self.test("B) Run [UNVRS] scraper", False, f"Error: {str(e)}")
            else:
                self.test("B) Find [UNVRS] scraper", False, "Scraper not found")
                
        except Exception as e:
            self.test("B) GET /api/admin/scrapers", False, f"Error: {str(e)}")
    
    def test_c_events_affiliate_tag(self):
        """
        C) EVENTS + AFFILIATE TAG: GET /api/events?city=Ibiza (as admin city=Ibiza).
        For every event with clubtickets.com, confirm it contains "aff=CT226" and NO duplicate aff params.
        Confirm ClubTickets-affiliate events appear FIRST.
        """
        self.log("\n" + "="*80)
        self.log("TEST C: EVENTS + AFFILIATE TAG")
        self.log("="*80)
        
        # Ensure admin city is Ibiza
        if not self.update_admin_city("Ibiza"):
            self.test("C) Ensure admin city is Ibiza", False, "Failed to update city")
            return
        
        try:
            response = requests.get(
                f"{API_BASE}/events",
                headers=self.get_headers(),
                params={"city": "Ibiza"},
                timeout=10
            )
            
            self.test(
                "C) GET /api/events?city=Ibiza returns 200",
                response.status_code == 200,
                f"Status: {response.status_code}"
            )
            
            if response.status_code != 200:
                self.log(f"Response: {response.text}", "FAIL")
                return
            
            events = response.json()
            self.log(f"Found {len(events)} total events in Ibiza")
            
            # Find all clubtickets.com events
            clubtickets_events = []
            non_clubtickets_events = []
            
            for event in events:
                commission_url = event.get("commission_url", "")
                if "clubtickets.com" in commission_url:
                    clubtickets_events.append(event)
                else:
                    non_clubtickets_events.append(event)
            
            self.log(f"Found {len(clubtickets_events)} clubtickets.com events")
            self.log(f"Found {len(non_clubtickets_events)} non-clubtickets events")
            
            # Check all clubtickets events have aff=CT226
            events_without_aff = []
            events_with_duplicate_aff = []
            
            for event in clubtickets_events:
                commission_url = event.get("commission_url", "")
                
                # Check for aff=CT226
                if "aff=CT226" not in commission_url:
                    events_without_aff.append(event.get("name", "Unknown"))
                
                # Check for duplicate aff params
                aff_count = commission_url.count("aff=")
                if aff_count > 1:
                    events_with_duplicate_aff.append(event.get("name", "Unknown"))
            
            self.test(
                "C) All clubtickets.com events contain 'aff=CT226'",
                len(events_without_aff) == 0,
                f"Events without aff: {events_without_aff}" if events_without_aff else f"All {len(clubtickets_events)} events have aff=CT226"
            )
            
            self.test(
                "C) No clubtickets.com events have duplicate aff params",
                len(events_with_duplicate_aff) == 0,
                f"Events with duplicate aff: {events_with_duplicate_aff}" if events_with_duplicate_aff else "No duplicate aff params found"
            )
            
            # Check ClubTickets events appear FIRST
            if len(clubtickets_events) > 0 and len(non_clubtickets_events) > 0:
                # Find first clubtickets event index
                first_clubtickets_idx = None
                for i, event in enumerate(events):
                    if "clubtickets.com" in event.get("commission_url", ""):
                        first_clubtickets_idx = i
                        break
                
                # Find first non-clubtickets event index
                first_non_clubtickets_idx = None
                for i, event in enumerate(events):
                    if "clubtickets.com" not in event.get("commission_url", ""):
                        first_non_clubtickets_idx = i
                        break
                
                if first_clubtickets_idx is not None and first_non_clubtickets_idx is not None:
                    clubtickets_first = first_clubtickets_idx < first_non_clubtickets_idx
                    self.test(
                        "C) ClubTickets-affiliate events appear FIRST in feed",
                        clubtickets_first,
                        f"First clubtickets event at index {first_clubtickets_idx}, first non-clubtickets at {first_non_clubtickets_idx}"
                    )
                else:
                    self.log("Could not determine event ordering", "WARN")
            
            # Sample a few clubtickets events
            self.log("\nSample clubtickets.com events:")
            for i, event in enumerate(clubtickets_events[:3], 1):
                self.log(f"  {i}. {event.get('name')} at {event.get('venue')}")
                self.log(f"     URL: {event.get('commission_url')}")
            
        except Exception as e:
            self.test("C) GET /api/events?city=Ibiza", False, f"Error: {str(e)}")
    
    def test_d_venue_detail(self):
        """
        D) VENUE DETAIL: GET /api/venues/{id} for Lío Ibiza and [UNVRS];
        confirm upcoming_events > 0 and events list is non-empty.
        """
        self.log("\n" + "="*80)
        self.log("TEST D: VENUE DETAIL")
        self.log("="*80)
        
        # Get venues to find Lío Ibiza and [UNVRS]
        try:
            response = requests.get(
                f"{API_BASE}/venues",
                headers=self.get_headers(),
                params={"type": "discoteca"},
                timeout=10
            )
            
            if response.status_code != 200:
                self.test("D) GET /api/venues", False, f"Status: {response.status_code}")
                return
            
            venues = response.json()
            
            # Find Lío Ibiza
            lio_venue = None
            for venue in venues:
                if venue.get("name") == "Lío Ibiza":
                    lio_venue = venue
                    break
            
            if lio_venue:
                self.log(f"Found Lío Ibiza venue: {lio_venue.get('id')}")
                
                # Get venue detail
                try:
                    detail_response = requests.get(
                        f"{API_BASE}/venues/{lio_venue['id']}",
                        headers=self.get_headers(),
                        timeout=10
                    )
                    
                    self.test(
                        "D) GET /api/venues/{lio_id} returns 200",
                        detail_response.status_code == 200,
                        f"Status: {detail_response.status_code}"
                    )
                    
                    if detail_response.status_code == 200:
                        detail = detail_response.json()
                        upcoming_events = detail.get("upcoming_events", 0)
                        events_list = detail.get("events", [])
                        
                        self.test(
                            "D) Lío Ibiza: upcoming_events > 0",
                            upcoming_events > 0,
                            f"upcoming_events: {upcoming_events}"
                        )
                        
                        self.test(
                            "D) Lío Ibiza: events list is non-empty",
                            len(events_list) > 0,
                            f"events count: {len(events_list)}"
                        )
                    else:
                        self.log(f"Lío Ibiza detail failed: {detail_response.text}", "FAIL")
                        
                except Exception as e:
                    self.test("D) GET Lío Ibiza detail", False, f"Error: {str(e)}")
            else:
                self.test("D) Find Lío Ibiza venue", False, "Venue not found")
            
            # Find [UNVRS]
            unvrs_venue = None
            for venue in venues:
                if venue.get("name") == "[UNVRS]":
                    unvrs_venue = venue
                    break
            
            if unvrs_venue:
                self.log(f"Found [UNVRS] venue: {unvrs_venue.get('id')}")
                
                # Get venue detail
                try:
                    detail_response = requests.get(
                        f"{API_BASE}/venues/{unvrs_venue['id']}",
                        headers=self.get_headers(),
                        timeout=10
                    )
                    
                    self.test(
                        "D) GET /api/venues/{unvrs_id} returns 200",
                        detail_response.status_code == 200,
                        f"Status: {detail_response.status_code}"
                    )
                    
                    if detail_response.status_code == 200:
                        detail = detail_response.json()
                        upcoming_events = detail.get("upcoming_events", 0)
                        events_list = detail.get("events", [])
                        
                        self.test(
                            "D) [UNVRS]: upcoming_events > 0",
                            upcoming_events > 0,
                            f"upcoming_events: {upcoming_events}"
                        )
                        
                        self.test(
                            "D) [UNVRS]: events list is non-empty",
                            len(events_list) > 0,
                            f"events count: {len(events_list)}"
                        )
                    else:
                        self.log(f"[UNVRS] detail failed: {detail_response.text}", "FAIL")
                        
                except Exception as e:
                    self.test("D) GET [UNVRS] detail", False, f"Error: {str(e)}")
            else:
                self.test("D) Find [UNVRS] venue", False, "Venue not found")
                
        except Exception as e:
            self.test("D) GET /api/venues", False, f"Error: {str(e)}")
    
    def test_e_regression(self):
        """
        E) REGRESSION: Set admin city to "Palma de Mallorca" and GET /api/events —
        should still return events and non-clubtickets links unchanged (no aff=CT226 injected).
        Confirm no duplicated events in Ibiza feed.
        """
        self.log("\n" + "="*80)
        self.log("TEST E: REGRESSION")
        self.log("="*80)
        
        # Update admin city to Palma de Mallorca
        if not self.update_admin_city("Palma de Mallorca"):
            self.test("E) Update admin city to Palma de Mallorca", False, "Failed to update city")
            return
        
        self.test("E) Update admin city to Palma de Mallorca", True, "City updated successfully")
        
        # Get Palma events
        try:
            response = requests.get(
                f"{API_BASE}/events",
                headers=self.get_headers(),
                timeout=10
            )
            
            self.test(
                "E) GET /api/events (Palma) returns 200",
                response.status_code == 200,
                f"Status: {response.status_code}"
            )
            
            if response.status_code != 200:
                self.log(f"Response: {response.text}", "FAIL")
                return
            
            events = response.json()
            self.log(f"Found {len(events)} events in Palma de Mallorca")
            
            self.test(
                "E) Palma de Mallorca still returns events",
                len(events) > 0,
                f"Events count: {len(events)}"
            )
            
            # Check non-clubtickets URLs don't have aff=CT226
            non_clubtickets_with_aff = []
            
            for event in events:
                commission_url = event.get("commission_url", "")
                if commission_url and "clubtickets.com" not in commission_url and "aff=CT226" in commission_url:
                    non_clubtickets_with_aff.append(event.get("name", "Unknown"))
            
            self.test(
                "E) Non-clubtickets URLs unchanged (no aff=CT226 injected)",
                len(non_clubtickets_with_aff) == 0,
                f"Non-clubtickets events with aff: {non_clubtickets_with_aff}" if non_clubtickets_with_aff else "No aff=CT226 in non-clubtickets URLs"
            )
            
        except Exception as e:
            self.test("E) GET /api/events (Palma)", False, f"Error: {str(e)}")
        
        # Check for duplicated events in Ibiza feed
        self.log("\nChecking for duplicated events in Ibiza feed...")
        
        # Update admin city back to Ibiza
        if not self.update_admin_city("Ibiza"):
            self.test("E) Update admin city back to Ibiza", False, "Failed to update city")
            return
        
        try:
            response = requests.get(
                f"{API_BASE}/events",
                headers=self.get_headers(),
                params={"city": "Ibiza"},
                timeout=10
            )
            
            if response.status_code != 200:
                self.test("E) GET /api/events?city=Ibiza", False, f"Status: {response.status_code}")
                return
            
            events = response.json()
            
            # Check for duplicates (same venue + same date + same name)
            seen = set()
            duplicates = []
            
            for event in events:
                key = (
                    event.get("venue", ""),
                    event.get("date", ""),
                    event.get("name", "")
                )
                
                if key in seen:
                    duplicates.append(f"{event.get('name')} at {event.get('venue')} on {event.get('date')}")
                else:
                    seen.add(key)
            
            self.test(
                "E) No duplicated events in Ibiza feed",
                len(duplicates) == 0,
                f"Duplicates: {duplicates}" if duplicates else f"No duplicates found in {len(events)} events"
            )
            
        except Exception as e:
            self.test("E) Check Ibiza duplicates", False, f"Error: {str(e)}")
    
    def run_all_tests(self):
        """Run all tests"""
        self.log("\n" + "="*80)
        self.log("CLUBTICKETS FULL COVERAGE TESTING")
        self.log("="*80)
        
        # Login as admin
        if not self.login_admin():
            self.log("Failed to login as admin. Aborting tests.", "FAIL")
            return False
        
        # Run all test sections
        self.test_a_directory_no_duplicates()
        self.test_b_scraper_runs()
        self.test_c_events_affiliate_tag()
        self.test_d_venue_detail()
        self.test_e_regression()
        
        # Print summary
        self.log("\n" + "="*80)
        self.log("TEST SUMMARY")
        self.log("="*80)
        self.log(f"Total tests: {self.passed + self.failed}")
        self.log(f"Passed: {self.passed}", "SUCCESS")
        self.log(f"Failed: {self.failed}", "FAIL" if self.failed > 0 else "SUCCESS")
        
        if self.failed > 0:
            self.log("\nFailed tests:")
            for result in self.results:
                if not result["passed"]:
                    self.log(f"  - {result['name']}", "FAIL")
                    if result["details"]:
                        self.log(f"    {result['details']}")
        
        return self.failed == 0

if __name__ == "__main__":
    runner = TestRunner()
    success = runner.run_all_tests()
    sys.exit(0 if success else 1)
