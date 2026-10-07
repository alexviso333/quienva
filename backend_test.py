#!/usr/bin/env python3
"""
Backend testing for "el plan se decide solo" iteration (2026-10)
Testing ONLY backend at http://localhost:8001/api
"""
import requests
import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

BASE_URL = "http://localhost:8001/api"

def test_landing_ssr():
    """Test 1: Landing SSR pages (GET /api/home, /api/en/home, /api/de/home)"""
    print("\n" + "="*80)
    print("TEST 1: LANDING SSR (GET /api/home, /api/en/home, /api/de/home)")
    print("="*80)
    
    tests = [
        ("es", f"{BASE_URL}/home", "El plan se decide solo", "Crear un plan gratis", "Ver fiestas de esta noche"),
        ("en", f"{BASE_URL}/en/home", "The plan decides itself", "Create a free plan", "See parties tonight"),
        ("de", f"{BASE_URL}/de/home", "Der Plan entscheidet sich selbst", "Gratis Plan erstellen", "Partys heute Abend ansehen"),
    ]
    
    results = []
    for lang, url, h1_text, cta_text, cta_sub_text in tests:
        print(f"\n--- Testing {lang.upper()} ({url}) ---")
        try:
            resp = requests.get(url, timeout=10)
            print(f"Status: {resp.status_code}")
            
            if resp.status_code != 200:
                results.append(f"❌ {lang}: HTTP {resp.status_code}")
                continue
            
            html = resp.text
            
            # Check H1
            h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
            if h1_match and h1_text in h1_match.group(1):
                print(f"✅ H1 contains: '{h1_text}'")
            else:
                print(f"❌ H1 does NOT contain: '{h1_text}'")
                if h1_match:
                    print(f"   Found: {h1_match.group(1)[:100]}")
                results.append(f"❌ {lang}: H1 incorrect")
                continue
            
            # Check CTA primary button
            cta_match = re.search(r'<a[^>]*id="qvcta"[^>]*class="cta cta-xl"[^>]*href="[^"]*p/nuevo"[^>]*>(.*?)</a>', html, re.DOTALL)
            if not cta_match:
                cta_match = re.search(r'<a[^>]*class="cta cta-xl"[^>]*id="qvcta"[^>]*href="[^"]*p/nuevo"[^>]*>(.*?)</a>', html, re.DOTALL)
            
            if cta_match and cta_text in cta_match.group(1):
                print(f"✅ CTA primary button found with text: '{cta_text}'")
            else:
                print(f"❌ CTA primary button NOT found or text incorrect")
                results.append(f"❌ {lang}: CTA primary button missing")
                continue
            
            # Check CTA secondary link
            cta_sub_patterns = [
                r'<a[^>]*class="cta-sub"[^>]*href="[^"]*fiestas/madrid"[^>]*>(.*?)</a>',
                r'<a[^>]*class="cta-sub"[^>]*href="[^"]*parties/madrid"[^>]*>(.*?)</a>',
                r'<a[^>]*class="cta-sub"[^>]*href="[^"]*partys/madrid"[^>]*>(.*?)</a>',
            ]
            cta_sub_match = None
            for pattern in cta_sub_patterns:
                cta_sub_match = re.search(pattern, html, re.DOTALL)
                if cta_sub_match:
                    break
            
            if cta_sub_match and cta_sub_text in cta_sub_match.group(1):
                print(f"✅ CTA secondary link found with text: '{cta_sub_text}'")
            else:
                print(f"❌ CTA secondary link NOT found or text incorrect")
                if cta_sub_match:
                    print(f"   Found text: {cta_sub_match.group(1)[:100]}")
                results.append(f"❌ {lang}: CTA secondary link missing")
                continue
            
            # Check stats: no stat should be <= 50
            stat_matches = re.findall(r'<span[^>]*class="stat"[^>]*>.*?<b[^>]*>(\d+)</b>', html, re.DOTALL)
            invalid_stats = [int(s) for s in stat_matches if int(s) <= 50]
            if invalid_stats:
                print(f"❌ Found stats with value <= 50: {invalid_stats}")
                results.append(f"❌ {lang}: Stats <= 50 found")
                continue
            else:
                print(f"✅ No stats with value <= 50 (found {len(stat_matches)} stats)")
            
            # Check NO "ciudades"/"cities"/"Städte" stat
            forbidden_words = ["ciudades", "cities", "Städte"]
            has_forbidden = False
            for word in forbidden_words:
                # Check if it's in a stat context (within <span class="stat">...</span>)
                pattern = r'<span[^>]*class="stat"[^>]*>.*?' + re.escape(word) + r'.*?</span>'
                if re.search(pattern, html, re.IGNORECASE | re.DOTALL):
                    print(f"❌ Found forbidden word '{word}' in stats")
                    has_forbidden = True
            
            if not has_forbidden:
                print(f"✅ No forbidden words (ciudades/cities/Städte) in stats")
            else:
                results.append(f"❌ {lang}: Forbidden stat word found")
                continue
            
            # Check for the 3 new blocks
            blocks = [
                ("Decide con tu grupo", "Decide with your group", "Entscheide mit deiner Gruppe"),
                ("Guarda la noche", "Keep the night", "Bewahr die Nacht"),
                ("Mira quién va", "See who", "Sieh, wer"),  # Partial match to handle HTML entities
            ]
            
            missing_blocks = []
            for es, en, de in blocks:
                text = es if lang == "es" else (en if lang == "en" else de)
                if text not in html:
                    missing_blocks.append(text)
            
            if missing_blocks:
                print(f"❌ Missing blocks: {missing_blocks}")
                results.append(f"❌ {lang}: Missing blocks")
                continue
            else:
                print(f"✅ All 3 blocks found (Decide/Guarda/Mira)")
            
            # Check FAQ first answer
            faq_texts = {
                "es": "es la forma más rápida de decidir dónde salís",
                "en": "is the fastest way to decide where you're going out",
                "de": "ist der schnellste Weg zu entscheiden",  # Partial match
            }
            if faq_texts[lang] in html:
                print(f"✅ New FAQ answer found")
            else:
                print(f"❌ New FAQ answer NOT found")
                results.append(f"❌ {lang}: FAQ answer missing")
                continue
            
            # Check NO count-up animation script
            if 'toLocaleString("es")' in html or 'toLocaleString(' in html:
                print(f"❌ Count-up animation script found (should be removed)")
                results.append(f"❌ {lang}: Count-up script present")
                continue
            else:
                print(f"✅ No count-up animation script")
            
            # Check H2 "Así se monta un plan" (not duplicated)
            h2_matches = re.findall(r'<h2[^>]*>(.*?)</h2>', html, re.DOTALL)
            h2_texts = [re.sub(r'<[^>]+>', '', m).strip() for m in h2_matches]
            
            if lang == "es":
                h1_count = sum(1 for t in h2_texts if "El plan se decide solo" in t)
                demo_count = sum(1 for t in h2_texts if "Así se monta un plan" in t)
                
                if h1_count > 0:
                    print(f"❌ H2 'El plan se decide solo' found (should not be duplicated)")
                    results.append(f"❌ {lang}: H2 duplicated")
                    continue
                
                if demo_count > 0:
                    print(f"✅ H2 'Así se monta un plan' found (demo section)")
                else:
                    print(f"⚠️  H2 'Así se monta un plan' not found (may be OK)")
            
            results.append(f"✅ {lang}: ALL CHECKS PASSED")
            
        except Exception as e:
            print(f"❌ Error: {e}")
            results.append(f"❌ {lang}: Exception - {e}")
    
    print("\n" + "="*80)
    print("TEST 1 SUMMARY:")
    for r in results:
        print(r)
    print("="*80)
    
    return all("✅" in r for r in results)


def test_plan_visibility():
    """Test 2: Plan visibility (todos/amigos/invitados/invalid)"""
    print("\n" + "="*80)
    print("TEST 2: PLAN VISIBILITY")
    print("="*80)
    
    results = []
    
    # Test creating plans with different visibilidad values
    test_cases = [
        ("todos", "todos"),
        ("amigos", "amigos"),
        ("invitados", "invitados"),
        ("basura", "todos"),  # Invalid should default to "todos"
    ]
    
    created_slugs = []
    
    for input_vis, expected_vis in test_cases:
        print(f"\n--- Creating plan with visibilidad='{input_vis}' ---")
        
        payload = {
            "opciones": [
                {"texto_libre": f"Test option for {input_vis}"}
            ],
            "visibilidad": input_vis
        }
        
        try:
            resp = requests.post(f"{BASE_URL}/plans", json=payload, timeout=10)
            print(f"Status: {resp.status_code}")
            
            if resp.status_code != 200:
                print(f"❌ Failed to create plan: {resp.text[:200]}")
                results.append(f"❌ Create plan with visibilidad='{input_vis}': HTTP {resp.status_code}")
                continue
            
            data = resp.json()
            slug = data.get("slug")
            creador_token = data.get("creador_token")
            plan_vis = data.get("plan", {}).get("visibilidad")
            
            print(f"Created plan: {slug}")
            print(f"Returned visibilidad: {plan_vis}")
            print(f"Expected visibilidad: {expected_vis}")
            
            if plan_vis == expected_vis:
                print(f"✅ Visibilidad correct: {plan_vis}")
                results.append(f"✅ Create plan with visibilidad='{input_vis}' -> '{expected_vis}'")
                created_slugs.append((slug, creador_token, expected_vis))
            else:
                print(f"❌ Visibilidad incorrect: expected '{expected_vis}', got '{plan_vis}'")
                results.append(f"❌ Create plan with visibilidad='{input_vis}': wrong value")
            
        except Exception as e:
            print(f"❌ Error: {e}")
            results.append(f"❌ Create plan with visibilidad='{input_vis}': Exception")
    
    # Test GET /api/plans/{slug} - should always return 200 (link is open)
    print(f"\n--- Testing GET /api/plans/{{slug}} (should always be 200) ---")
    for slug, token, vis in created_slugs:
        try:
            resp = requests.get(f"{BASE_URL}/plans/{slug}", timeout=10)
            print(f"GET /plans/{slug} (visibilidad={vis}): {resp.status_code}")
            
            if resp.status_code == 200:
                data = resp.json()
                returned_vis = data.get("visibilidad")
                if returned_vis == vis:
                    print(f"✅ Plan accessible, visibilidad field present: {returned_vis}")
                    results.append(f"✅ GET /plans/{slug}: 200 with visibilidad={vis}")
                else:
                    print(f"❌ Visibilidad field incorrect or missing")
                    results.append(f"❌ GET /plans/{slug}: visibilidad field wrong")
            else:
                print(f"❌ Plan not accessible: {resp.status_code}")
                results.append(f"❌ GET /plans/{slug}: HTTP {resp.status_code}")
        except Exception as e:
            print(f"❌ Error: {e}")
            results.append(f"❌ GET /plans/{slug}: Exception")
    
    print("\n" + "="*80)
    print("TEST 2 SUMMARY:")
    for r in results:
        print(r)
    print("="*80)
    
    return all("✅" in r for r in results)


def test_event_plans_visibility():
    """Test 3: GET /api/events/{id}/plans without auth - only shows 'todos' plans"""
    print("\n" + "="*80)
    print("TEST 3: EVENT PLANS VISIBILITY (GET /api/events/{id}/plans)")
    print("="*80)
    
    event_id = "d0a5fd95-6d9e-452b-b878-7a84ae578462"  # Bubbles at Es Paradis Ibiza
    
    results = []
    
    # Create 3 plans with different visibilidad on the same event
    print(f"\n--- Creating 3 plans on event {event_id} ---")
    
    visibilidades = ["todos", "amigos", "invitados"]
    created_plans = []
    
    for vis in visibilidades:
        payload = {
            "opciones": [
                {"evento_id": event_id, "venue_nombre": "Bubbles"}
            ],
            "visibilidad": vis
        }
        
        try:
            resp = requests.post(f"{BASE_URL}/plans", json=payload, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                slug = data.get("slug")
                print(f"✅ Created plan with visibilidad='{vis}': {slug}")
                created_plans.append((slug, vis))
            else:
                print(f"❌ Failed to create plan with visibilidad='{vis}': {resp.status_code}")
                results.append(f"❌ Create plan for event: HTTP {resp.status_code}")
        except Exception as e:
            print(f"❌ Error creating plan: {e}")
            results.append(f"❌ Create plan for event: Exception")
    
    if len(created_plans) != 3:
        print(f"❌ Could not create all 3 plans (created {len(created_plans)})")
        results.append(f"❌ Setup failed: only {len(created_plans)} plans created")
        return False
    
    # Now GET /api/events/{id}/plans WITHOUT authentication
    print(f"\n--- GET /api/events/{event_id}/plans (no auth) ---")
    
    try:
        resp = requests.get(f"{BASE_URL}/events/{event_id}/plans", timeout=10)
        print(f"Status: {resp.status_code}")
        
        if resp.status_code != 200:
            print(f"❌ Failed to get event plans: {resp.status_code}")
            results.append(f"❌ GET event plans: HTTP {resp.status_code}")
            return False
        
        data = resp.json()
        plans = data.get("plans", [])
        
        print(f"Returned {len(plans)} plan(s)")
        
        # Should only return "todos" plans (not amigos/invitados)
        todos_count = 0
        other_count = 0
        
        for plan in plans:
            vis = plan.get("visibilidad", "")
            slug = plan.get("slug", "")
            print(f"  Plan {slug}: visibilidad={vis}")
            
            if vis == "todos":
                todos_count += 1
            else:
                other_count += 1
        
        if other_count == 0:
            print(f"✅ Only 'todos' plans returned ({todos_count} total, 0 amigos/invitados)")
            results.append(f"✅ GET event plans: only 'todos' visible")
        else:
            print(f"❌ Incorrect plans returned: {todos_count} 'todos', {other_count} amigos/invitados")
            results.append(f"❌ GET event plans: visibility filter broken")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        results.append(f"❌ GET event plans: Exception")
    
    print("\n" + "="*80)
    print("TEST 3 SUMMARY:")
    for r in results:
        print(r)
    print("="*80)
    
    return all("✅" in r for r in results)


def test_club_nombre_in_options():
    """Test 4: club_nombre field in plan options"""
    print("\n" + "="*80)
    print("TEST 4: CLUB_NOMBRE IN PLAN OPTIONS")
    print("="*80)
    
    event_id = "d0a5fd95-6d9e-452b-b878-7a84ae578462"  # Bubbles at Es Paradis Ibiza
    
    results = []
    
    # Test 1: venue_nombre different from club name
    print(f"\n--- Test 1: venue_nombre='Bubbles' (different from club) ---")
    payload = {
        "opciones": [
            {"evento_id": event_id, "venue_nombre": "Bubbles"}
        ]
    }
    
    try:
        resp = requests.post(f"{BASE_URL}/plans", json=payload, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            opciones = data.get("plan", {}).get("opciones", [])
            if opciones:
                club_nombre = opciones[0].get("club_nombre", "")
                print(f"club_nombre: '{club_nombre}'")
                
                if club_nombre == "Es Paradis Ibiza":
                    print(f"✅ club_nombre correct: 'Es Paradis Ibiza'")
                    results.append(f"✅ club_nombre with different venue_nombre")
                else:
                    print(f"❌ club_nombre incorrect: expected 'Es Paradis Ibiza', got '{club_nombre}'")
                    results.append(f"❌ club_nombre incorrect")
            else:
                print(f"❌ No opciones returned")
                results.append(f"❌ No opciones in response")
        else:
            print(f"❌ Failed to create plan: {resp.status_code}")
            results.append(f"❌ Create plan: HTTP {resp.status_code}")
    except Exception as e:
        print(f"❌ Error: {e}")
        results.append(f"❌ Test 1: Exception")
    
    # Test 2: venue_nombre same as club name
    print(f"\n--- Test 2: venue_nombre='Es Paradis Ibiza' (same as club) ---")
    payload = {
        "opciones": [
            {"evento_id": event_id, "venue_nombre": "Es Paradis Ibiza"}
        ]
    }
    
    try:
        resp = requests.post(f"{BASE_URL}/plans", json=payload, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            opciones = data.get("plan", {}).get("opciones", [])
            if opciones:
                club_nombre = opciones[0].get("club_nombre", "")
                print(f"club_nombre: '{club_nombre}'")
                
                if club_nombre == "":
                    print(f"✅ club_nombre empty (correct, no repetition)")
                    results.append(f"✅ club_nombre empty when same as venue")
                else:
                    print(f"❌ club_nombre should be empty, got '{club_nombre}'")
                    results.append(f"❌ club_nombre not empty")
            else:
                print(f"❌ No opciones returned")
                results.append(f"❌ No opciones in response")
        else:
            print(f"❌ Failed to create plan: {resp.status_code}")
            results.append(f"❌ Create plan: HTTP {resp.status_code}")
    except Exception as e:
        print(f"❌ Error: {e}")
        results.append(f"❌ Test 2: Exception")
    
    # Test 3: texto_libre option
    print(f"\n--- Test 3: texto_libre option ---")
    payload = {
        "opciones": [
            {"texto_libre": "Bar de la esquina"}
        ]
    }
    
    try:
        resp = requests.post(f"{BASE_URL}/plans", json=payload, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            opciones = data.get("plan", {}).get("opciones", [])
            if opciones:
                club_nombre = opciones[0].get("club_nombre", "")
                print(f"club_nombre: '{club_nombre}'")
                
                if club_nombre == "":
                    print(f"✅ club_nombre empty for texto_libre (correct)")
                    results.append(f"✅ club_nombre empty for texto_libre")
                else:
                    print(f"❌ club_nombre should be empty for texto_libre, got '{club_nombre}'")
                    results.append(f"❌ club_nombre not empty for texto_libre")
            else:
                print(f"❌ No opciones returned")
                results.append(f"❌ No opciones in response")
        else:
            print(f"❌ Failed to create plan: {resp.status_code}")
            results.append(f"❌ Create plan: HTTP {resp.status_code}")
    except Exception as e:
        print(f"❌ Error: {e}")
        results.append(f"❌ Test 3: Exception")
    
    print("\n" + "="*80)
    print("TEST 4 SUMMARY:")
    for r in results:
        print(r)
    print("="*80)
    
    return all("✅" in r for r in results)


def test_venue_nights():
    """Test 5: GET /api/events/{id}/venue-nights"""
    print("\n" + "="*80)
    print("TEST 5: VENUE-NIGHTS (GET /api/events/{id}/venue-nights)")
    print("="*80)
    
    # Test with 2-3 different Ibiza events
    test_events = [
        "d0a5fd95-6d9e-452b-b878-7a84ae578462",  # Bubbles at Es Paradis Ibiza
    ]
    
    # Get more Ibiza events
    try:
        resp = requests.get(f"{BASE_URL}/events?city=Ibiza&date_filter=all", timeout=10)
        if resp.status_code == 200:
            events = resp.json()  # API returns list directly
            if isinstance(events, list):
                # Get 2 more events
                for ev in events[:5]:
                    eid = ev.get("id")
                    if eid and eid not in test_events:
                        test_events.append(eid)
                        if len(test_events) >= 3:
                            break
    except:
        pass
    
    print(f"Testing {len(test_events)} events")
    
    results = []
    today = datetime.now(ZoneInfo("Europe/Madrid")).date()
    
    for event_id in test_events:
        print(f"\n--- Testing event {event_id} ---")
        
        try:
            resp = requests.get(f"{BASE_URL}/events/{event_id}/venue-nights", timeout=10)
            print(f"Status: {resp.status_code}")
            
            if resp.status_code != 200:
                print(f"❌ Failed: HTTP {resp.status_code}")
                results.append(f"❌ venue-nights for {event_id[:8]}: HTTP {resp.status_code}")
                continue
            
            data = resp.json()
            nights = data.get("nights", [])
            kind = data.get("kind", "")
            
            print(f"Returned {len(nights)} nights, kind='{kind}'")
            
            # Check kind
            if kind != "upcoming":
                print(f"❌ kind should be 'upcoming', got '{kind}'")
                results.append(f"❌ venue-nights: wrong kind")
                continue
            
            # Check each night
            all_ok = True
            for i, night in enumerate(nights):
                night_id = night.get("id", "")
                name = night.get("name", "")
                date_str = night.get("date", "")
                time_str = night.get("time", "")
                image_url = night.get("image_url", "")
                price = night.get("price")
                sale_state = night.get("sale_state", "")
                
                # Check required fields
                required_fields = ["id", "name", "date", "time", "image_url", "price", "sale_state"]
                missing = [f for f in required_fields if f not in night]
                if missing:
                    print(f"  Night {i}: ❌ Missing fields: {missing}")
                    all_ok = False
                    continue
                
                # Check date >= today
                try:
                    night_date = datetime.fromisoformat(date_str).date()
                    if night_date < today:
                        print(f"  Night {i}: ❌ Date {date_str} is in the past")
                        all_ok = False
                        continue
                except:
                    print(f"  Night {i}: ❌ Invalid date format: {date_str}")
                    all_ok = False
                    continue
                
                # Check NOT the same event
                if night_id == event_id:
                    print(f"  Night {i}: ❌ Includes the same event ID")
                    all_ok = False
                    continue
                
                # Check NO attended or photos fields
                if "attended" in night or "photos" in night:
                    print(f"  Night {i}: ❌ Has 'attended' or 'photos' field (should be removed)")
                    all_ok = False
                    continue
                
                print(f"  Night {i}: ✅ {name} on {date_str}")
            
            # Check ordering (dates should be ascending)
            dates = []
            for night in nights:
                try:
                    dates.append(datetime.fromisoformat(night.get("date", "")).date())
                except:
                    pass
            
            if dates and dates != sorted(dates):
                print(f"❌ Dates not in ascending order")
                all_ok = False
            else:
                print(f"✅ Dates in ascending order")
            
            # Check max 8
            if len(nights) > 8:
                print(f"❌ More than 8 nights returned: {len(nights)}")
                all_ok = False
            else:
                print(f"✅ Max 8 nights (returned {len(nights)})")
            
            if all_ok:
                results.append(f"✅ venue-nights for {event_id[:8]}: ALL CHECKS PASSED")
            else:
                results.append(f"❌ venue-nights for {event_id[:8]}: SOME CHECKS FAILED")
            
        except Exception as e:
            print(f"❌ Error: {e}")
            results.append(f"❌ venue-nights for {event_id[:8]}: Exception")
    
    print("\n" + "="*80)
    print("TEST 5 SUMMARY:")
    for r in results:
        print(r)
    print("="*80)
    
    return all("✅" in r for r in results)


def test_events_ibiza():
    """Test 6: GET /api/events?city=Ibiza&date_filter=all"""
    print("\n" + "="*80)
    print("TEST 6: EVENTS IBIZA (GET /api/events?city=Ibiza&date_filter=all)")
    print("="*80)
    
    results = []
    
    try:
        resp = requests.get(f"{BASE_URL}/events?city=Ibiza&date_filter=all", timeout=10)
        print(f"Status: {resp.status_code}")
        
        if resp.status_code != 200:
            print(f"❌ Failed: HTTP {resp.status_code}")
            results.append(f"❌ GET events: HTTP {resp.status_code}")
            return False
        
        # API returns a list directly, not a dict
        events = resp.json()
        if not isinstance(events, list):
            print(f"❌ Response is not a list")
            results.append(f"❌ GET events: wrong response type")
            return False
        
        print(f"Returned {len(events)} events")
        
        # Check nights_at_venue = 0 (no photos in album_uploads)
        all_ok = True
        for i, ev in enumerate(events[:10]):  # Check first 10
            nights = ev.get("nights_at_venue", -1)
            if nights != 0:
                print(f"  Event {i}: ❌ nights_at_venue={nights} (should be 0)")
                all_ok = False
            
            # Check open_plans_count doesn't count amigos/invitados
            # (we can't verify this directly without creating plans, but we can check the field exists)
            if "open_plans_count" not in ev:
                print(f"  Event {i}: ❌ Missing open_plans_count field")
                all_ok = False
        
        if all_ok:
            print(f"✅ All events have nights_at_venue=0")
            print(f"✅ All events have open_plans_count field")
            results.append(f"✅ GET events Ibiza: ALL CHECKS PASSED")
        else:
            results.append(f"❌ GET events Ibiza: SOME CHECKS FAILED")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        results.append(f"❌ GET events Ibiza: Exception")
    
    print("\n" + "="*80)
    print("TEST 6 SUMMARY:")
    for r in results:
        print(r)
    print("="*80)
    
    return all("✅" in r for r in results)


def test_regression():
    """Test 7: Regression tests"""
    print("\n" + "="*80)
    print("TEST 7: REGRESSION TESTS")
    print("="*80)
    
    results = []
    
    # Create a test plan first
    print(f"\n--- Creating test plan for regression ---")
    payload = {
        "opciones": [
            {"texto_libre": "Test regression"}
        ]
    }
    
    try:
        resp = requests.post(f"{BASE_URL}/plans", json=payload, timeout=10)
        if resp.status_code != 200:
            print(f"❌ Failed to create test plan: {resp.status_code}")
            results.append(f"❌ Setup: create plan failed")
            return False
        
        data = resp.json()
        slug = data.get("slug")
        creador_token = data.get("creador_token")
        
        print(f"✅ Created test plan: {slug}")
        
        # Test respond
        print(f"\n--- POST /api/plans/{slug}/respond ---")
        respond_payload = {
            "intencion": "dentro",
            "apodo": "Test User"
        }
        resp = requests.post(f"{BASE_URL}/plans/{slug}/respond", json=respond_payload, timeout=10)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            print(f"✅ respond endpoint working")
            results.append(f"✅ POST respond: 200")
        else:
            print(f"❌ respond failed: {resp.status_code}")
            results.append(f"❌ POST respond: HTTP {resp.status_code}")
        
        # Test close
        print(f"\n--- POST /api/plans/{slug}/close ---")
        headers = {"x-participante-token": creador_token}
        resp = requests.post(f"{BASE_URL}/plans/{slug}/close", headers=headers, timeout=10)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            print(f"✅ close endpoint working")
            results.append(f"✅ POST close: 200")
        else:
            print(f"❌ close failed: {resp.status_code}")
            results.append(f"❌ POST close: HTTP {resp.status_code}")
        
        # Create another plan for cancel test
        resp = requests.post(f"{BASE_URL}/plans", json=payload, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            slug2 = data.get("slug")
            creador_token2 = data.get("creador_token")
            
            # Test cancel
            print(f"\n--- POST /api/plans/{slug2}/cancel ---")
            headers = {"x-participante-token": creador_token2}
            resp = requests.post(f"{BASE_URL}/plans/{slug2}/cancel", headers=headers, timeout=10)
            print(f"Status: {resp.status_code}")
            if resp.status_code == 200:
                print(f"✅ cancel endpoint working")
                results.append(f"✅ POST cancel: 200")
            else:
                print(f"❌ cancel failed: {resp.status_code}")
                results.append(f"❌ POST cancel: HTTP {resp.status_code}")
        
        # Test GET /api/plans/mine
        print(f"\n--- GET /api/plans/mine?slugs={slug} ---")
        resp = requests.get(f"{BASE_URL}/plans/mine?slugs={slug}", timeout=10)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            print(f"✅ plans/mine endpoint working")
            results.append(f"✅ GET plans/mine: 200")
        else:
            print(f"❌ plans/mine failed: {resp.status_code}")
            results.append(f"❌ GET plans/mine: HTTP {resp.status_code}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        results.append(f"❌ Regression: Exception")
    
    # Test SSR pages
    ssr_pages = [
        ("/ciudad/madrid", "Madrid"),
        ("/p/nuevo", "nuevo"),
    ]
    
    for path, keyword in ssr_pages:
        print(f"\n--- GET /api{path} ---")
        try:
            resp = requests.get(f"{BASE_URL}{path}", timeout=10)
            print(f"Status: {resp.status_code}")
            if resp.status_code == 200 and "text/html" in resp.headers.get("content-type", ""):
                print(f"✅ SSR page working")
                results.append(f"✅ GET {path}: 200 HTML")
            else:
                print(f"❌ SSR page failed: {resp.status_code}")
                results.append(f"❌ GET {path}: HTTP {resp.status_code}")
        except Exception as e:
            print(f"❌ Error: {e}")
            results.append(f"❌ GET {path}: Exception")
    
    print("\n" + "="*80)
    print("TEST 7 SUMMARY:")
    for r in results:
        print(r)
    print("="*80)
    
    return all("✅" in r for r in results)


def main():
    print("\n" + "="*80)
    print("BACKEND TESTING: 'El plan se decide solo' iteration")
    print("Base URL: http://localhost:8001/api")
    print("="*80)
    
    all_results = []
    
    # Run all tests
    test1 = test_landing_ssr()
    all_results.append(("Landing SSR", test1))
    
    test2 = test_plan_visibility()
    all_results.append(("Plan Visibility", test2))
    
    test3 = test_event_plans_visibility()
    all_results.append(("Event Plans Visibility", test3))
    
    test4 = test_club_nombre_in_options()
    all_results.append(("Club Nombre in Options", test4))
    
    test5 = test_venue_nights()
    all_results.append(("Venue Nights", test5))
    
    test6 = test_events_ibiza()
    all_results.append(("Events Ibiza", test6))
    
    test7 = test_regression()
    all_results.append(("Regression", test7))
    
    # Final summary
    print("\n" + "="*80)
    print("FINAL SUMMARY")
    print("="*80)
    
    for name, passed in all_results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{name}: {status}")
    
    total = len(all_results)
    passed = sum(1 for _, p in all_results if p)
    
    print(f"\nTotal: {passed}/{total} test suites passed")
    print("="*80)
    
    return all(p for _, p in all_results)


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
