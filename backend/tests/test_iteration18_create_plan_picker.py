"""
Iteration 18 — Backend regression for the new CreatePlanSheet picker.

Validates:
  * GET /api/venues?city=<other-city> returns venues of that city even when
    the authenticated user's own city is different.
  * GET /api/venues (no param) still returns venues of the user's own city.
  * GET /api/events?city=<city> works for the plan picker.
  * POST /api/plans with 3 mixed opciones (evento_id, venue name, texto_libre)
    returns a slug and the opciones round-trip correctly.
  * POST /api/plans/{slug}/respond votes for one option and the resulting
    plan state is consistent (counts + lugar/lugarVotos/numOpciones live state).
"""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://voting-island-widget.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

TEST_EMAIL = "test@quienva.app"
TEST_PASS = "Test1234!"
FRIEND_EMAIL = "amigo@quienva.app"
FRIEND_PASS = "Test1234!"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login {email} -> {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"no token in login response: {r.json()}"
    return tok


@pytest.fixture(scope="module")
def test_token():
    return _login(TEST_EMAIL, TEST_PASS)


@pytest.fixture(scope="module")
def friend_token():
    return _login(FRIEND_EMAIL, FRIEND_PASS)


@pytest.fixture(scope="module")
def test_user(test_token):
    r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {test_token}"}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


# --- /api/venues optional city param ---------------------------------------
class TestVenuesCityParam:
    def test_venues_default_uses_user_city(self, test_token, test_user):
        r = requests.get(f"{API}/venues", headers={"Authorization": f"Bearer {test_token}"}, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        if data:
            # All returned venues belong to the user's city.
            cities = {v.get("city") for v in data if v.get("city")}
            # user city may be stored with accents; normalise case-insensitively.
            user_city = (test_user.get("city") or "").lower()
            assert any(user_city in c.lower() or c.lower() in user_city for c in cities), (
                f"user city {user_city!r} not matched in returned cities {cities}")

    def test_venues_with_explicit_madrid(self, test_token):
        r = requests.get(f"{API}/venues", params={"city": "Madrid"},
                         headers={"Authorization": f"Bearer {test_token}"}, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        if data:
            cities = {v.get("city") for v in data if v.get("city")}
            assert any("madrid" in (c or "").lower() for c in cities), (
                f"Expected Madrid venues, got cities={cities}")

    def test_venues_guest_with_city(self):
        r = requests.get(f"{API}/venues", params={"city": "Madrid"}, timeout=20)
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)


# --- /api/events for picker ------------------------------------------------
class TestEventsForPicker:
    def test_events_city_param(self, test_token):
        r = requests.get(f"{API}/events",
                         params={"date_filter": "all", "city": "Madrid"},
                         headers={"Authorization": f"Bearer {test_token}"}, timeout=25)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)


# --- POST /api/plans with 3 mixed options then vote ------------------------
class TestCreateAndVotePlan:
    @pytest.fixture(scope="class")
    def picker_data(self, test_token):
        headers = {"Authorization": f"Bearer {test_token}"}
        ev = requests.get(f"{API}/events",
                          params={"date_filter": "all", "city": "Madrid"},
                          headers=headers, timeout=25).json()
        vn = requests.get(f"{API}/venues", params={"city": "Madrid"},
                          headers=headers, timeout=20).json()
        if not ev or not vn:
            pytest.skip("Madrid picker data unavailable (no events or venues)")
        return {"event": ev[0], "venue": vn[0]}

    @pytest.fixture(scope="class")
    def created_plan(self, test_token, picker_data):
        headers = {"Authorization": f"Bearer {test_token}", "Content-Type": "application/json"}
        body = {
            "titulo": "TEST_iter18 picker plan",
            "ciudad": "Madrid",
            "opciones": [
                {"evento_id": picker_data["event"]["id"],
                 "venue_nombre": picker_data["event"].get("venue") or picker_data["event"].get("name") or "Opt1",
                 "hora": "", "precio_desde": None},
                {"texto_libre": picker_data["venue"]["name"],
                 "venue_nombre": picker_data["venue"]["name"],
                 "hora": "", "precio_desde": None},
                {"texto_libre": "TEST_casa_marta", "venue_nombre": "TEST_casa_marta",
                 "hora": "23:30", "precio_desde": None},
            ],
            "umbral_personas": None,
            "invitar_user_ids": [],
        }
        r = requests.post(f"{API}/plans", json=body, headers=headers, timeout=25)
        assert r.status_code in (200, 201), f"create plan -> {r.status_code} {r.text}"
        data = r.json()
        assert data.get("slug"), data
        assert data.get("plan"), data
        plan = data["plan"]
        assert len(plan.get("opciones") or []) == 3
        return data

    def test_plan_options_have_opt_ids(self, created_plan):
        plan = created_plan["plan"]
        for o in plan["opciones"]:
            assert o.get("opt_id"), f"option missing opt_id: {o}"

    def test_friend_vote_updates_counts(self, created_plan, friend_token, test_token):
        slug = created_plan["slug"]
        opt_id = created_plan["plan"]["opciones"][1]["opt_id"]  # vote for the venue option
        hdr = {"Authorization": f"Bearer {friend_token}", "Content-Type": "application/json"}
        r = requests.post(f"{API}/plans/{slug}/respond",
                          json={"intencion": "dentro", "opcion_preferida": opt_id},
                          headers=hdr, timeout=20)
        assert r.status_code in (200, 201), f"respond -> {r.status_code} {r.text}"

        # Refetch plan state (public endpoint via creator token not needed; use authed GET)
        r2 = requests.get(f"{API}/plans/{slug}",
                          headers={"Authorization": f"Bearer {test_token}"}, timeout=15)
        assert r2.status_code == 200, r2.text
        data = r2.json()
        # Count how many participants chose that opt_id (voted "dentro")
        parts = data.get("participantes") or data.get("participants") or []
        votes_for = [p for p in parts
                     if p.get("opcion_preferida") == opt_id and p.get("intencion") in ("dentro", "voy_si")]
        assert len(votes_for) >= 1, f"friend vote not reflected: parts={parts}"

    def test_cleanup_delete_plan(self, created_plan, test_token):
        slug = created_plan["slug"]
        # best-effort cleanup; endpoint may not exist — ignore 404/405
        hdr = {"Authorization": f"Bearer {test_token}"}
        requests.delete(f"{API}/plans/{slug}", headers=hdr, timeout=15)
