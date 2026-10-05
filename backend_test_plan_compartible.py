#!/usr/bin/env python3
"""
Backend testing for Plan compartible feature (/p/{slug})
Tests all endpoints and behaviors as specified in the review request.
"""
import requests
import json
import time
from datetime import datetime, timedelta

# Base URL from frontend/.env REACT_APP_BACKEND_URL with /api prefix
BASE_URL = "https://night-preview-1.preview.emergentagent.com/api"

def log(msg):
    print(f"[TEST] {msg}")

def test_create_plan_success():
    """TEST 1: POST /api/plans - create plan with valid options"""
    log("TEST 1: Create plan with 2 free-text options")
    
    body = {
        "titulo": "Test Jueves",
        "mensaje_creador": "vamos?",
        "ciudad": "Madrid",
        "umbral_personas": 3,
        "creador_apodo": "Alex",
        "opciones": [
            {
                "texto_libre": "Fitz",
                "venue_nombre": "Fitz",
                "hora": "23:30",
                "precio_desde": 12
            },
            {
                "texto_libre": "LuLa Club",
                "venue_nombre": "LuLa Club",
                "hora": "00:00"
            }
        ]
    }
    
    resp = requests.post(f"{BASE_URL}/plans", json=body)
    log(f"  Status: {resp.status_code}")
    
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    
    data = resp.json()
    assert "slug" in data, "Response missing 'slug'"
    assert "creador_token" in data, "Response missing 'creador_token'"
    assert "plan" in data, "Response missing 'plan'"
    
    plan = data["plan"]
    assert "opciones" in plan, "Plan missing 'opciones'"
    assert len(plan["opciones"]) == 2, f"Expected 2 options, got {len(plan['opciones'])}"
    
    # Verify each option has opt_id (UUID)
    for opt in plan["opciones"]:
        assert "opt_id" in opt, "Option missing 'opt_id'"
        assert len(opt["opt_id"]) > 0, "opt_id is empty"
        log(f"  Option: {opt['venue_nombre']} (opt_id: {opt['opt_id']})")
    
    # Verify no Mongo ObjectId leaks (all IDs should be UUID strings)
    plan_json = json.dumps(plan)
    assert "ObjectId" not in plan_json, "Mongo ObjectId leaked in response"
    
    log(f"  ✅ Plan created: slug={data['slug']}")
    return data["slug"], data["creador_token"], plan["opciones"][0]["opt_id"]

def test_create_plan_empty_options():
    """TEST 2: POST /api/plans - must return 400 with empty opciones"""
    log("TEST 2: Create plan with empty opciones (should fail)")
    
    body = {
        "titulo": "Test Empty",
        "ciudad": "Madrid",
        "creador_apodo": "Test",
        "opciones": []
    }
    
    resp = requests.post(f"{BASE_URL}/plans", json=body)
    log(f"  Status: {resp.status_code}")
    
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    log("  ✅ Correctly rejected empty opciones with 400")

def test_get_plan_public(slug):
    """TEST 3: GET /api/plans/{slug} - returns public plan"""
    log(f"TEST 3: Get public plan: {slug}")
    
    resp = requests.get(f"{BASE_URL}/plans/{slug}")
    log(f"  Status: {resp.status_code}")
    
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    
    plan = resp.json()
    assert "slug" in plan, "Plan missing 'slug'"
    assert "counts" in plan, "Plan missing 'counts'"
    assert "participants" in plan, "Plan missing 'participants'"
    assert "opciones" in plan, "Plan missing 'opciones'"
    assert "estado" in plan, "Plan missing 'estado'"
    assert plan["estado"] == "abierto", f"Expected estado 'abierto', got {plan['estado']}"
    
    log(f"  ✅ Plan retrieved: estado={plan['estado']}, counts={plan['counts']}")
    return plan

def test_get_plan_not_found():
    """TEST 4: GET /api/plans/{slug} - 404 for unknown slug"""
    log("TEST 4: Get non-existent plan (should return 404)")
    
    resp = requests.get(f"{BASE_URL}/plans/nonexistent-slug-12345")
    log(f"  Status: {resp.status_code}")
    
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
    log("  ✅ Correctly returned 404 for unknown slug")

def test_respond_plan_missing_apodo(slug):
    """TEST 5: POST /api/plans/{slug}/respond - 400 if apodo missing"""
    log(f"TEST 5: Respond without apodo (should fail)")
    
    body = {
        "intencion": "dentro"
    }
    
    resp = requests.post(f"{BASE_URL}/plans/{slug}/respond", json=body)
    log(f"  Status: {resp.status_code}")
    
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    log("  ✅ Correctly rejected missing apodo with 400")

def test_respond_plan_invalid_intencion(slug):
    """TEST 6: POST /api/plans/{slug}/respond - 400 if intencion invalid"""
    log(f"TEST 6: Respond with invalid intencion (should fail)")
    
    body = {
        "apodo": "Test",
        "intencion": "invalid_intent"
    }
    
    resp = requests.post(f"{BASE_URL}/plans/{slug}/respond", json=body)
    log(f"  Status: {resp.status_code}")
    
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    log("  ✅ Correctly rejected invalid intencion with 400")

def test_respond_plan_first_time(slug, opt_id):
    """TEST 7: POST /api/plans/{slug}/respond - first response returns token"""
    log(f"TEST 7: First response (dentro) - should return participante_token")
    
    body = {
        "apodo": "Marta",
        "intencion": "dentro",
        "opcion_preferida": opt_id
    }
    
    resp = requests.post(f"{BASE_URL}/plans/{slug}/respond", json=body)
    log(f"  Status: {resp.status_code}")
    
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    
    data = resp.json()
    assert "participante_token" in data, "Response missing 'participante_token'"
    assert "plan" in data, "Response missing 'plan'"
    
    token = data["participante_token"]
    plan = data["plan"]
    
    assert "counts" in plan, "Plan missing 'counts'"
    assert plan["counts"]["dentro"] >= 1, f"Expected dentro count >= 1, got {plan['counts']['dentro']}"
    
    log(f"  ✅ Response recorded: token={token[:10]}..., dentro count={plan['counts']['dentro']}")
    return token

def test_respond_plan_update_same_token(slug, token, opt_id):
    """TEST 8: POST /api/plans/{slug}/respond - update with same token (no duplicate)"""
    log(f"TEST 8: Update response with same token (should update, not duplicate)")
    
    # Get initial participant count
    plan_before = requests.get(f"{BASE_URL}/plans/{slug}").json()
    count_before = plan_before["counts"]["total"]
    dentro_before = plan_before["counts"]["dentro"]
    
    log(f"  Before: total={count_before}, dentro={dentro_before}")
    
    # Update to different intencion
    body = {
        "apodo": "Marta Updated",
        "intencion": "depende",
        "opcion_preferida": opt_id,
        "participante_token": token
    }
    
    resp = requests.post(f"{BASE_URL}/plans/{slug}/respond", json=body)
    log(f"  Status: {resp.status_code}")
    
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    
    plan_after = resp.json()["plan"]
    count_after = plan_after["counts"]["total"]
    dentro_after = plan_after["counts"]["dentro"]
    depende_after = plan_after["counts"]["depende"]
    
    log(f"  After: total={count_after}, dentro={dentro_after}, depende={depende_after}")
    
    # Total should stay the same (updated, not duplicated)
    assert count_after == count_before, f"Participant duplicated! Before: {count_before}, After: {count_after}"
    
    # dentro should decrease, depende should increase
    assert dentro_after == dentro_before - 1, f"Expected dentro to decrease by 1"
    assert depende_after >= 1, f"Expected depende >= 1"
    
    log("  ✅ Response updated correctly (no duplication)")

def test_respond_plan_invalid_opt_id(slug):
    """TEST 9: POST /api/plans/{slug}/respond - invalid opt_id should be ignored (stored as null)"""
    log(f"TEST 9: Respond with invalid opcion_preferida (should be ignored)")
    
    body = {
        "apodo": "Carlos",
        "intencion": "dentro",
        "opcion_preferida": "invalid-opt-id-12345"
    }
    
    resp = requests.post(f"{BASE_URL}/plans/{slug}/respond", json=body)
    log(f"  Status: {resp.status_code}")
    
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    
    plan = resp.json()["plan"]
    # Find the participant we just created
    mine = plan.get("mine")
    if mine:
        # opcion_preferida should be None (invalid opt_id ignored)
        assert mine.get("opcion_preferida") is None, f"Expected opcion_preferida to be None, got {mine.get('opcion_preferida')}"
        log("  ✅ Invalid opt_id correctly ignored (stored as null)")
    else:
        log("  ⚠️  Could not verify (mine not in response)")

def test_autocierre_by_quorum():
    """TEST 10: AUTOCIERRE - plan closes when quorum reached"""
    log("TEST 10: AUTOCIERRE by quorum (umbral_personas=2)")
    
    # Create plan with umbral_personas=2 and no hora_limite
    body = {
        "titulo": "Test Autocierre",
        "ciudad": "Madrid",
        "umbral_personas": 2,
        "creador_apodo": "Creator",
        "opciones": [
            {
                "texto_libre": "Bar A",
                "venue_nombre": "Bar A",
                "hora": "22:00"
            },
            {
                "texto_libre": "Bar B",
                "venue_nombre": "Bar B",
                "hora": "23:00"
            }
        ]
    }
    
    resp = requests.post(f"{BASE_URL}/plans", json=body)
    assert resp.status_code == 200
    
    slug = resp.json()["slug"]
    opt_id = resp.json()["plan"]["opciones"][0]["opt_id"]
    log(f"  Created plan: {slug}")
    
    # First "dentro" response
    resp1 = requests.post(f"{BASE_URL}/plans/{slug}/respond", json={
        "apodo": "Person1",
        "intencion": "dentro",
        "opcion_preferida": opt_id
    })
    assert resp1.status_code == 200
    plan1 = resp1.json()["plan"]
    log(f"  After 1st response: estado={plan1['estado']}, dentro={plan1['counts']['dentro']}")
    assert plan1["estado"] == "abierto", "Plan should still be open after 1st response"
    
    # Second "dentro" response (should trigger autocierre)
    resp2 = requests.post(f"{BASE_URL}/plans/{slug}/respond", json={
        "apodo": "Person2",
        "intencion": "dentro",
        "opcion_preferida": opt_id
    })
    assert resp2.status_code == 200
    plan2 = resp2.json()["plan"]
    log(f"  After 2nd response: estado={plan2['estado']}, dentro={plan2['counts']['dentro']}")
    
    # Plan should now be closed
    assert plan2["estado"] == "cerrado", f"Expected estado 'cerrado', got {plan2['estado']}"
    assert plan2.get("opcion_ganadora") is not None, "opcion_ganadora should be set"
    log(f"  ✅ Plan autoclosed: opcion_ganadora={plan2['opcion_ganadora']}")
    
    # Try to respond again (should return 409)
    resp3 = requests.post(f"{BASE_URL}/plans/{slug}/respond", json={
        "apodo": "Person3",
        "intencion": "dentro"
    })
    log(f"  Try to respond to closed plan: {resp3.status_code}")
    assert resp3.status_code == 409, f"Expected 409 for closed plan, got {resp3.status_code}"
    log("  ✅ Correctly rejected response to closed plan with 409")
    
    return slug

def test_close_plan_authorization(slug, creador_token):
    """TEST 11: POST /api/plans/{slug}/close - only creator can close"""
    log(f"TEST 11: Close plan authorization")
    
    # Try to close with WRONG token (should fail with 403)
    headers_wrong = {"x-participante-token": "wrong-token-12345"}
    resp_wrong = requests.post(f"{BASE_URL}/plans/{slug}/close", headers=headers_wrong)
    log(f"  Close with wrong token: {resp_wrong.status_code}")
    assert resp_wrong.status_code == 403, f"Expected 403, got {resp_wrong.status_code}"
    log("  ✅ Correctly rejected wrong token with 403")
    
    # Close with correct creador_token (should succeed)
    headers_correct = {"x-participante-token": creador_token}
    resp_correct = requests.post(f"{BASE_URL}/plans/{slug}/close", headers=headers_correct)
    log(f"  Close with correct token: {resp_correct.status_code}")
    assert resp_correct.status_code == 200, f"Expected 200, got {resp_correct.status_code}"
    
    plan = resp_correct.json()
    assert plan["estado"] == "cerrado", f"Expected estado 'cerrado', got {plan['estado']}"
    log("  ✅ Plan closed successfully by creator")

def test_cancel_plan_authorization():
    """TEST 12: POST /api/plans/{slug}/cancel - only creator can cancel"""
    log(f"TEST 12: Cancel plan authorization")
    
    # Create a new plan for cancellation test
    body = {
        "titulo": "Test Cancel",
        "ciudad": "Madrid",
        "creador_apodo": "Creator",
        "opciones": [{"texto_libre": "Place A", "venue_nombre": "Place A"}]
    }
    
    resp = requests.post(f"{BASE_URL}/plans", json=body)
    assert resp.status_code == 200
    
    slug = resp.json()["slug"]
    creador_token = resp.json()["creador_token"]
    log(f"  Created plan: {slug}")
    
    # Try to cancel with WRONG token (should fail with 403)
    headers_wrong = {"x-participante-token": "wrong-token-12345"}
    resp_wrong = requests.post(f"{BASE_URL}/plans/{slug}/cancel", headers=headers_wrong)
    log(f"  Cancel with wrong token: {resp_wrong.status_code}")
    assert resp_wrong.status_code == 403, f"Expected 403, got {resp_wrong.status_code}"
    log("  ✅ Correctly rejected wrong token with 403")
    
    # Cancel with correct creador_token (should succeed)
    headers_correct = {"x-participante-token": creador_token}
    resp_correct = requests.post(f"{BASE_URL}/plans/{slug}/cancel", headers=headers_correct)
    log(f"  Cancel with correct token: {resp_correct.status_code}")
    assert resp_correct.status_code == 200, f"Expected 200, got {resp_correct.status_code}"
    
    plan = resp_correct.json()
    assert plan["estado"] == "cancelado", f"Expected estado 'cancelado', got {plan['estado']}"
    log("  ✅ Plan cancelled successfully by creator")

def test_ssr_html_page(slug):
    """TEST 13: GET /api/p/{slug} - returns HTML with OG tags and window.__PLAN__"""
    log(f"TEST 13: SSR HTML page for plan: {slug}")
    
    resp = requests.get(f"{BASE_URL}/p/{slug}")
    log(f"  Status: {resp.status_code}")
    
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    assert "text/html" in resp.headers.get("Content-Type", ""), "Expected text/html content type"
    
    html = resp.text
    
    # Verify OG tags
    assert "og:title" in html, "Missing og:title meta tag"
    assert "og:image" in html, "Missing og:image meta tag"
    assert "og:description" in html or "og:desc" in html, "Missing og:description meta tag"
    
    # Verify window.__PLAN__ is present
    assert "window.__PLAN__" in html, "Missing window.__PLAN__ in HTML"
    
    log("  ✅ HTML page contains og:title, og:image, and window.__PLAN__")

def test_ssr_html_nuevo():
    """TEST 14: GET /api/p/nuevo - returns creation HTML page"""
    log("TEST 14: SSR HTML page for /p/nuevo (creation page)")
    
    resp = requests.get(f"{BASE_URL}/p/nuevo")
    log(f"  Status: {resp.status_code}")
    
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    assert "text/html" in resp.headers.get("Content-Type", ""), "Expected text/html content type"
    
    html = resp.text
    assert "Monta tu plan" in html or "monta" in html.lower(), "Missing creation page content"
    
    log("  ✅ Creation HTML page returned successfully")

def test_ssr_html_not_found():
    """TEST 15: GET /api/p/{slug} - 404 HTML for unknown slug"""
    log("TEST 15: SSR HTML page for non-existent plan (should return 404)")
    
    resp = requests.get(f"{BASE_URL}/p/nonexistent-slug-99999")
    log(f"  Status: {resp.status_code}")
    
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
    assert "text/html" in resp.headers.get("Content-Type", ""), "Expected text/html content type"
    
    log("  ✅ Correctly returned 404 HTML for unknown slug")

def test_og_image(slug):
    """TEST 16: GET /api/og/plan/{slug} - returns PNG image"""
    log(f"TEST 16: OG image for plan: {slug}")
    
    resp = requests.get(f"{BASE_URL}/og/plan/{slug}")
    log(f"  Status: {resp.status_code}")
    
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    
    content_type = resp.headers.get("Content-Type", "")
    assert "image/png" in content_type, f"Expected image/png, got {content_type}"
    
    # Verify image has non-trivial size (should be > 10KB for 1200x630 PNG)
    image_size = len(resp.content)
    log(f"  Image size: {image_size} bytes")
    assert image_size > 10000, f"Image too small: {image_size} bytes (expected > 10KB)"
    
    log("  ✅ OG image returned successfully (PNG, non-trivial size)")

def main():
    print("=" * 80)
    print("BACKEND TESTING: Plan compartible (/p/{slug})")
    print("=" * 80)
    print()
    
    try:
        # TEST 1-2: Create plan (success and failure)
        slug, creador_token, opt_id = test_create_plan_success()
        test_create_plan_empty_options()
        
        # TEST 3-4: Get plan (success and 404)
        test_get_plan_public(slug)
        test_get_plan_not_found()
        
        # TEST 5-9: Respond to plan (validation and behavior)
        test_respond_plan_missing_apodo(slug)
        test_respond_plan_invalid_intencion(slug)
        token = test_respond_plan_first_time(slug, opt_id)
        test_respond_plan_update_same_token(slug, token, opt_id)
        test_respond_plan_invalid_opt_id(slug)
        
        # TEST 10: Autocierre by quorum
        closed_slug = test_autocierre_by_quorum()
        
        # TEST 11-12: Close/cancel authorization
        # Create a fresh plan for close test
        body = {
            "titulo": "Test Close Auth",
            "ciudad": "Madrid",
            "creador_apodo": "Creator",
            "opciones": [{"texto_libre": "Place X", "venue_nombre": "Place X"}]
        }
        resp = requests.post(f"{BASE_URL}/plans", json=body)
        close_slug = resp.json()["slug"]
        close_token = resp.json()["creador_token"]
        
        test_close_plan_authorization(close_slug, close_token)
        test_cancel_plan_authorization()
        
        # TEST 13-16: SSR HTML and OG image
        test_ssr_html_page(slug)
        test_ssr_html_nuevo()
        test_ssr_html_not_found()
        test_og_image(slug)
        
        print()
        print("=" * 80)
        print("✅ ALL TESTS PASSED (16/16)")
        print("=" * 80)
        print()
        print("SUMMARY:")
        print("  ✅ POST /api/plans - create plan with validation")
        print("  ✅ GET /api/plans/{slug} - public plan retrieval")
        print("  ✅ POST /api/plans/{slug}/respond - respond without login")
        print("  ✅ AUTOCIERRE - plan closes when quorum reached")
        print("  ✅ POST /api/plans/{slug}/close - creator authorization")
        print("  ✅ POST /api/plans/{slug}/cancel - creator authorization")
        print("  ✅ GET /api/p/{slug} - SSR HTML with OG tags")
        print("  ✅ GET /api/og/plan/{slug} - PNG image generation")
        print()
        
    except AssertionError as e:
        print()
        print("=" * 80)
        print(f"❌ TEST FAILED: {e}")
        print("=" * 80)
        raise
    except Exception as e:
        print()
        print("=" * 80)
        print(f"❌ UNEXPECTED ERROR: {e}")
        print("=" * 80)
        raise

if __name__ == "__main__":
    main()
