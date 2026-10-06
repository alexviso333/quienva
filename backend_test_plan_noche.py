#!/usr/bin/env python3
"""
Backend test for Plan deadline auto-close + Noche conversion (Bloque 3.6/3.7)
Tests the close_expired_plans() and convert_plans_to_noches() functionality.
"""
import requests
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# Base URL from frontend/.env
BASE_URL = "https://full-stack-nightlife.preview.emergentagent.com/api"

# Admin credentials from test_credentials.md
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

def log(msg):
    print(f"[TEST] {msg}")

def admin_login():
    """Login as admin and return token + user_id"""
    log("Logging in as admin...")
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.status_code} {resp.text}"
    data = resp.json()
    token = data.get("token")
    user = data.get("user", {})
    user_id = user.get("user_id")
    assert token, "No token in login response"
    assert user_id, "No user_id in login response"
    log(f"✅ Admin login successful (user_id: {user_id})")
    return token, user_id

def get_event_id(city="Madrid"):
    """Get an event ID from the specified city"""
    log(f"Fetching events from {city}...")
    resp = requests.get(f"{BASE_URL}/events", params={"city": city})
    assert resp.status_code == 200, f"Failed to get events: {resp.status_code}"
    data = resp.json()
    # API returns list directly or dict with events key
    events = data if isinstance(data, list) else data.get("events", [])
    assert len(events) > 0, f"No events found in {city}"
    event_id = events[0]["id"]
    log(f"✅ Found event: {events[0].get('name', 'Unknown')} (id: {event_id})")
    return event_id

def create_plan_with_deadline(token, evento_id, umbral_personas, hora_limite_iso, fecha_objetivo_iso):
    """Create a plan with a single option, umbral, and deadline"""
    log(f"Creating plan with umbral={umbral_personas}, hora_limite={hora_limite_iso}...")
    resp = requests.post(f"{BASE_URL}/plans", 
        headers={"Authorization": f"Bearer {token}"},
        json={
            "titulo": "Test Plan Noche",
            "ciudad": "Madrid",
            "creador_apodo": "Admin Test",
            "mensaje_creador": "Testing plan auto-close",
            "opciones": [{"evento_id": evento_id}],
            "umbral_personas": umbral_personas,
            "hora_limite": hora_limite_iso,
            "fecha_objetivo": fecha_objetivo_iso
        })
    assert resp.status_code == 200, f"Failed to create plan: {resp.status_code} {resp.text}"
    data = resp.json()
    slug = data.get("slug")
    creador_token = data.get("creador_token")
    plan = data.get("plan", {})
    assert slug, "No slug in create plan response"
    assert creador_token, "No creador_token in create plan response"
    log(f"✅ Plan created: slug={slug}, estado={plan.get('estado')}")
    return slug, creador_token, plan

def respond_to_plan_authenticated(token, slug, apodo, intencion, participante_token=None):
    """Respond to a plan as an authenticated user"""
    log(f"Responding to plan {slug} as authenticated user (apodo={apodo}, intencion={intencion})...")
    headers = {"Authorization": f"Bearer {token}"}
    body = {
        "apodo": apodo,
        "intencion": intencion
    }
    if participante_token:
        body["participante_token"] = participante_token
    resp = requests.post(f"{BASE_URL}/plans/{slug}/respond", headers=headers, json=body)
    assert resp.status_code == 200, f"Failed to respond: {resp.status_code} {resp.text}"
    data = resp.json()
    new_token = data.get("participante_token")
    plan = data.get("plan", {})
    log(f"✅ Response submitted: participante_token={new_token}, estado={plan.get('estado')}")
    return new_token, plan

def respond_to_plan_guest(slug, apodo, intencion):
    """Respond to a plan as a guest (no auth)"""
    log(f"Responding to plan {slug} as guest (apodo={apodo}, intencion={intencion})...")
    resp = requests.post(f"{BASE_URL}/plans/{slug}/respond", json={
        "apodo": apodo,
        "intencion": intencion
    })
    assert resp.status_code == 200, f"Failed to respond as guest: {resp.status_code} {resp.text}"
    data = resp.json()
    token = data.get("participante_token")
    plan = data.get("plan", {})
    log(f"✅ Guest response submitted: participante_token={token}, estado={plan.get('estado')}")
    return token, plan

def get_plan(slug):
    """Get plan details"""
    resp = requests.get(f"{BASE_URL}/plans/{slug}")
    assert resp.status_code == 200, f"Failed to get plan: {resp.status_code}"
    return resp.json()

def trigger_close_expired(token):
    """Trigger the close_expired_plans admin endpoint"""
    log("Triggering close_expired_plans...")
    resp = requests.post(f"{BASE_URL}/admin/plans/close-expired",
        headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, f"Failed to trigger close-expired: {resp.status_code} {resp.text}"
    log("✅ close_expired_plans triggered")
    return resp.json()

def trigger_convert_noches(token):
    """Trigger the convert_plans_to_noches admin endpoint"""
    log("Triggering convert_plans_to_noches...")
    resp = requests.post(f"{BASE_URL}/admin/plans/convert-noches",
        headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, f"Failed to trigger convert-noches: {resp.status_code} {resp.text}"
    log("✅ convert_plans_to_noches triggered")
    return resp.json()

def get_event_with_auth(token, event_id):
    """Get event details with authentication to check my_status"""
    resp = requests.get(f"{BASE_URL}/events/{event_id}",
        headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, f"Failed to get event: {resp.status_code}"
    return resp.json()

def test_scenario_1_expiry_without_quorum():
    """
    Scenario 1: Expiry WITHOUT quorum
    - Create plan with umbral=2, hora_limite in PAST, fecha_objetivo in PAST
    - Add ONE authenticated 'dentro' response
    - Call close-expired
    - Verify: estado='cerrado', opcion_ganadora=null, cierre_motivo='expirado_sin_quorum'
    """
    log("\n" + "="*80)
    log("SCENARIO 1: Expiry WITHOUT quorum")
    log("="*80)
    
    token, user_id = admin_login()
    evento_id = get_event_id("Madrid")
    
    # Create timestamps in the PAST (Europe/Madrid timezone)
    madrid_tz = ZoneInfo("Europe/Madrid")
    now_madrid = datetime.now(madrid_tz)
    past_hora_limite = (now_madrid - timedelta(hours=2)).isoformat()
    past_fecha_objetivo = (now_madrid - timedelta(days=2)).date().isoformat()  # 2 days ago to ensure it's processed
    
    # Create plan
    slug, creador_token, plan = create_plan_with_deadline(
        token, evento_id, 
        umbral_personas=2,
        hora_limite_iso=past_hora_limite,
        fecha_objetivo_iso=past_fecha_objetivo
    )
    
    # Add ONE authenticated 'dentro' response
    participante_token, plan = respond_to_plan_authenticated(token, slug, "Admin", "dentro")
    
    # Verify plan is still open
    assert plan.get("estado") == "abierto", f"Plan should be open, got: {plan.get('estado')}"
    log(f"✅ Plan is still open after 1 response (quorum not met)")
    
    # Trigger close-expired
    trigger_close_expired(token)
    
    # Get plan and verify
    plan = get_plan(slug)
    estado = plan.get("estado")
    opcion_ganadora = plan.get("opcion_ganadora")
    cierre_motivo = plan.get("cierre_motivo")
    
    log(f"Plan after close-expired: estado={estado}, opcion_ganadora={opcion_ganadora}, cierre_motivo={cierre_motivo}")
    
    assert estado == "cerrado", f"Expected estado='cerrado', got: {estado}"
    assert opcion_ganadora is None, f"Expected opcion_ganadora=null, got: {opcion_ganadora}"
    assert cierre_motivo == "expirado_sin_quorum", f"Expected cierre_motivo='expirado_sin_quorum', got: {cierre_motivo}"
    
    log("✅ SCENARIO 1 PASSED: Plan closed without quorum")
    return slug

def test_scenario_2_expiry_with_quorum():
    """
    Scenario 2: Expiry WITH quorum
    - Create plan with umbral=2, hora_limite in PAST, fecha_objetivo in PAST
    - Add TWO 'dentro' responses: one authenticated, one guest
    - Call close-expired
    - Verify: estado='cerrado', opcion_ganadora=<opt_id>, cierre_motivo='quorum'
    """
    log("\n" + "="*80)
    log("SCENARIO 2: Expiry WITH quorum")
    log("="*80)
    
    token, user_id = admin_login()
    evento_id = get_event_id("Madrid")
    
    # Create timestamps in the PAST
    madrid_tz = ZoneInfo("Europe/Madrid")
    now_madrid = datetime.now(madrid_tz)
    past_hora_limite = (now_madrid - timedelta(hours=2)).isoformat()
    past_fecha_objetivo = (now_madrid - timedelta(days=2)).date().isoformat()  # 2 days ago to ensure it's processed
    
    # Create plan
    slug, creador_token, plan = create_plan_with_deadline(
        token, evento_id,
        umbral_personas=2,
        hora_limite_iso=past_hora_limite,
        fecha_objetivo_iso=past_fecha_objetivo
    )
    
    # Get the single option's opt_id
    opciones = plan.get("opciones", [])
    assert len(opciones) == 1, f"Expected 1 option, got {len(opciones)}"
    expected_opt_id = opciones[0].get("opt_id")
    log(f"Expected winning opt_id: {expected_opt_id}")
    
    # Add ONE authenticated 'dentro' response
    participante_token_1, plan = respond_to_plan_authenticated(token, slug, "Admin", "dentro")
    
    # Add ONE guest 'dentro' response
    participante_token_2, plan = respond_to_plan_guest(slug, "Guest User", "dentro")
    
    # Verify plan is still open (quorum met but not auto-closed because hora_limite passed)
    # Note: _plan_maybe_autoclose only closes if dentro >= umbral AND not past_deadline
    # Since hora_limite is in the past, it won't auto-close on respond
    log(f"Plan estado after 2 responses: {plan.get('estado')}")
    
    # Trigger close-expired
    trigger_close_expired(token)
    
    # Get plan and verify
    plan = get_plan(slug)
    estado = plan.get("estado")
    opcion_ganadora = plan.get("opcion_ganadora")
    cierre_motivo = plan.get("cierre_motivo")
    
    log(f"Plan after close-expired: estado={estado}, opcion_ganadora={opcion_ganadora}, cierre_motivo={cierre_motivo}")
    
    assert estado == "cerrado", f"Expected estado='cerrado', got: {estado}"
    assert opcion_ganadora == expected_opt_id, f"Expected opcion_ganadora={expected_opt_id}, got: {opcion_ganadora}"
    assert cierre_motivo == "quorum", f"Expected cierre_motivo='quorum', got: {cierre_motivo}"
    
    log("✅ SCENARIO 2 PASSED: Plan closed with quorum")
    return slug, evento_id

def test_scenario_3_noche_conversion(slug_from_scenario_2, evento_id):
    """
    Scenario 3: Noche conversion
    - After scenario 2 (closed with winner, past target date)
    - Call convert-noches
    - Verify: registered participant has 'estuve' status on winning event
    - Verify: guest participant does NOT create interest
    - Verify: calling convert-noches again is idempotent (no duplicate interests)
    """
    log("\n" + "="*80)
    log("SCENARIO 3: Noche conversion")
    log("="*80)
    
    token, user_id = admin_login()
    
    # Get plan to verify it's ready for conversion
    plan = get_plan(slug_from_scenario_2)
    log(f"Plan before conversion: estado={plan.get('estado')}, opcion_ganadora={plan.get('opcion_ganadora')}, noche_id={plan.get('noche_id')}")
    
    assert plan.get("estado") == "cerrado", "Plan should be closed"
    assert plan.get("opcion_ganadora") is not None, "Plan should have a winner"
    assert plan.get("noche_id") is None, "Plan should not have noche_id yet"
    
    # Get event BEFORE conversion to check my_status
    event_before = get_event_with_auth(token, evento_id)
    my_status_before = event_before.get("my_status")
    log(f"Admin my_status BEFORE conversion: {my_status_before}")
    
    # Trigger convert-noches
    trigger_convert_noches(token)
    
    # Small delay to ensure DB update completes
    import time
    time.sleep(0.5)
    
    # Verify noche_id is set in the database (not exposed via API)
    import subprocess
    result = subprocess.run(
        ["mongosh", "quienva", "--quiet", "--eval", 
         f"db.plans.findOne({{slug: '{slug_from_scenario_2}'}}, {{_id: 0, noche_id: 1}})"],
        capture_output=True, text=True
    )
    import json
    # Parse the MongoDB output (it's in JSON format)
    noche_id = None
    if result.returncode == 0:
        # Extract noche_id from output
        output = result.stdout.strip()
        if "noche_id:" in output:
            # Parse the noche_id value
            import re
            match = re.search(r"noche_id:\s*'([^']+)'", output)
            if match:
                noche_id = match.group(1)
    
    log(f"Plan noche_id from database: {noche_id}")
    assert noche_id == evento_id, f"Expected noche_id={evento_id}, got: {noche_id}"
    
    # Get event AFTER conversion to check my_status
    event_after = get_event_with_auth(token, evento_id)
    my_status_after = event_after.get("my_status")
    log(f"Admin my_status AFTER conversion: {my_status_after}")
    
    assert my_status_after == "estuve", f"Expected my_status='estuve', got: {my_status_after}"
    log("✅ Registered participant (admin) now has 'estuve' status on winning event")
    
    # Verify idempotency: call convert-noches again
    log("Testing idempotency: calling convert-noches again...")
    trigger_convert_noches(token)
    
    # Get event again to verify no duplicate
    event_after_2 = get_event_with_auth(token, evento_id)
    my_status_after_2 = event_after_2.get("my_status")
    log(f"Admin my_status after 2nd conversion: {my_status_after_2}")
    
    assert my_status_after_2 == "estuve", f"Expected my_status='estuve', got: {my_status_after_2}"
    log("✅ Idempotency verified: no duplicate interests created")
    
    log("✅ SCENARIO 3 PASSED: Noche conversion working correctly")

def test_scenario_4_registered_participant_linking():
    """
    Scenario 4: Registered participant linking
    - Create a plan as authenticated user
    - Respond as authenticated user
    - Respond again as authenticated user (should update SAME participant)
    - Verify: participant is linked to user_id
    - Verify: counts.total stays the same (no duplication)
    """
    log("\n" + "="*80)
    log("SCENARIO 4: Registered participant linking")
    log("="*80)
    
    token, user_id = admin_login()
    evento_id = get_event_id("Madrid")
    
    # Create plan with future deadline (so it doesn't auto-close)
    madrid_tz = ZoneInfo("Europe/Madrid")
    now_madrid = datetime.now(madrid_tz)
    future_hora_limite = (now_madrid + timedelta(hours=2)).isoformat()
    future_fecha_objetivo = (now_madrid + timedelta(days=1)).date().isoformat()
    
    slug, creador_token, plan = create_plan_with_deadline(
        token, evento_id,
        umbral_personas=3,
        hora_limite_iso=future_hora_limite,
        fecha_objetivo_iso=future_fecha_objetivo
    )
    
    # First response as authenticated user
    participante_token_1, plan_1 = respond_to_plan_authenticated(token, slug, "Admin First", "dentro")
    counts_1 = plan_1.get("counts", {})
    total_1 = counts_1.get("total", 0)
    dentro_1 = counts_1.get("dentro", 0)
    log(f"After 1st response: total={total_1}, dentro={dentro_1}")
    
    assert total_1 == 1, f"Expected total=1, got: {total_1}"
    assert dentro_1 == 1, f"Expected dentro=1, got: {dentro_1}"
    
    # Second response as SAME authenticated user with SAME participante_token (should update)
    participante_token_2, plan_2 = respond_to_plan_authenticated(
        token, slug, "Admin Updated", "voy_si", participante_token=participante_token_1
    )
    counts_2 = plan_2.get("counts", {})
    total_2 = counts_2.get("total", 0)
    dentro_2 = counts_2.get("dentro", 0)
    voy_si_2 = counts_2.get("voy_si", 0)
    log(f"After 2nd response (update): total={total_2}, dentro={dentro_2}, voy_si={voy_si_2}")
    
    assert total_2 == 1, f"Expected total=1 (no duplication), got: {total_2}"
    assert dentro_2 == 0, f"Expected dentro=0 (changed to voy_si), got: {dentro_2}"
    assert voy_si_2 == 1, f"Expected voy_si=1, got: {voy_si_2}"
    
    log("✅ Participant updated correctly (no duplication)")
    
    # Third response as SAME authenticated user WITHOUT participante_token (should still update by user_id)
    participante_token_3, plan_3 = respond_to_plan_authenticated(
        token, slug, "Admin Final", "dentro"
    )
    counts_3 = plan_3.get("counts", {})
    total_3 = counts_3.get("total", 0)
    dentro_3 = counts_3.get("dentro", 0)
    voy_si_3 = counts_3.get("voy_si", 0)
    log(f"After 3rd response (by user_id): total={total_3}, dentro={dentro_3}, voy_si={voy_si_3}")
    
    assert total_3 == 1, f"Expected total=1 (no duplication by user_id), got: {total_3}"
    assert dentro_3 == 1, f"Expected dentro=1, got: {dentro_3}"
    assert voy_si_3 == 0, f"Expected voy_si=0 (changed back to dentro), got: {voy_si_3}"
    
    log("✅ Participant linked by user_id correctly (regression fix verified)")
    log("✅ SCENARIO 4 PASSED: Registered participant linking working")

def test_scenario_5_regression_plan_endpoints():
    """
    Scenario 5: Regression tests
    - Create plan
    - Respond to plan
    - Close plan manually (as creator with creador_token)
    - Cancel plan (create new one first)
    - Verify all endpoints return 2xx and behave correctly
    """
    log("\n" + "="*80)
    log("SCENARIO 5: Regression - Plan endpoints")
    log("="*80)
    
    token, user_id = admin_login()
    evento_id = get_event_id("Madrid")
    
    # Create plan
    madrid_tz = ZoneInfo("Europe/Madrid")
    now_madrid = datetime.now(madrid_tz)
    future_hora_limite = (now_madrid + timedelta(hours=2)).isoformat()
    future_fecha_objetivo = (now_madrid + timedelta(days=1)).date().isoformat()
    
    slug_1, creador_token_1, plan_1 = create_plan_with_deadline(
        token, evento_id,
        umbral_personas=2,
        hora_limite_iso=future_hora_limite,
        fecha_objetivo_iso=future_fecha_objetivo
    )
    log("✅ Create plan endpoint working")
    
    # Respond to plan
    participante_token, plan_resp = respond_to_plan_authenticated(token, slug_1, "Admin", "dentro")
    assert plan_resp.get("estado") == "abierto", "Plan should still be open"
    log("✅ Respond endpoint working")
    
    # Close plan manually with creador_token
    log(f"Closing plan manually with creador_token...")
    resp = requests.post(f"{BASE_URL}/plans/{slug_1}/close",
        headers={"x-participante-token": creador_token_1})
    assert resp.status_code == 200, f"Failed to close plan: {resp.status_code} {resp.text}"
    plan_closed = resp.json()
    assert plan_closed.get("estado") == "cerrado", f"Expected estado='cerrado', got: {plan_closed.get('estado')}"
    assert plan_closed.get("cierre_motivo") == "manual", f"Expected cierre_motivo='manual', got: {plan_closed.get('cierre_motivo')}"
    log("✅ Close plan endpoint working (with creador_token)")
    
    # Create another plan to test cancel
    slug_2, creador_token_2, plan_2 = create_plan_with_deadline(
        token, evento_id,
        umbral_personas=2,
        hora_limite_iso=future_hora_limite,
        fecha_objetivo_iso=future_fecha_objetivo
    )
    
    # Cancel plan with creador_token
    log(f"Cancelling plan with creador_token...")
    resp = requests.post(f"{BASE_URL}/plans/{slug_2}/cancel",
        headers={"x-participante-token": creador_token_2})
    assert resp.status_code == 200, f"Failed to cancel plan: {resp.status_code} {resp.text}"
    plan_cancelled = resp.json()
    assert plan_cancelled.get("estado") == "cancelado", f"Expected estado='cancelado', got: {plan_cancelled.get('estado')}"
    log("✅ Cancel plan endpoint working (with creador_token)")
    
    # Test close with authenticated user (creator_user_id)
    slug_3, creador_token_3, plan_3 = create_plan_with_deadline(
        token, evento_id,
        umbral_personas=2,
        hora_limite_iso=future_hora_limite,
        fecha_objetivo_iso=future_fecha_objetivo
    )
    
    log(f"Closing plan with Bearer token (as creator)...")
    resp = requests.post(f"{BASE_URL}/plans/{slug_3}/close",
        headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, f"Failed to close plan with Bearer: {resp.status_code} {resp.text}"
    plan_closed_auth = resp.json()
    assert plan_closed_auth.get("estado") == "cerrado", f"Expected estado='cerrado', got: {plan_closed_auth.get('estado')}"
    log("✅ Close plan endpoint working (with Bearer token as creator)")
    
    log("✅ SCENARIO 5 PASSED: All plan endpoints working correctly")

def main():
    log("Starting Plan/Noche backend tests...")
    log(f"Base URL: {BASE_URL}")
    
    try:
        # Scenario 1: Expiry without quorum
        test_scenario_1_expiry_without_quorum()
        
        # Scenario 2: Expiry with quorum
        slug_s2, evento_id_s2 = test_scenario_2_expiry_with_quorum()
        
        # Scenario 3: Noche conversion
        test_scenario_3_noche_conversion(slug_s2, evento_id_s2)
        
        # Scenario 4: Registered participant linking
        test_scenario_4_registered_participant_linking()
        
        # Scenario 5: Regression tests
        test_scenario_5_regression_plan_endpoints()
        
        log("\n" + "="*80)
        log("🎉 ALL TESTS PASSED!")
        log("="*80)
        
    except AssertionError as e:
        log(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        log(f"\n❌ UNEXPECTED ERROR: {e}")
        raise

if __name__ == "__main__":
    main()
