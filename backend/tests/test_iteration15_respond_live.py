"""
Iteration 15 re-verification:
- POST /api/plans/{slug}/respond frictionless flow:
  (a) no-auth no-apodo -> auto 'Invitado N' excluding pending invitees
  (b) same participante_token (body OR header) -> rename not duplicate
  (c) authed no-apodo -> uses account display name, user_id NOT in public JSON,
      plan.mine populated when fetched with auth, no dup rows
- Invited pending friend who answers with his account: pendiente -> dentro, counts
  update, no duplicates.
- Live Activity: POST /api/live-activity/token (auth) upserts; GET
  /api/admin/live-activities lists it; 401 without auth; /end ok.
- Respond/close/cancel keep returning 200 with APNs unconfigured.
- Quick regression: /invitables, /invite (403, 409), /admin/plans/invite-reminders
  single notification.
"""
import os
import time
import pytest
import requests
from datetime import datetime, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://voting-party-planner.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = ("admin@quienva.app", "QuienVa2025!")
TEST = ("test@quienva.app", "Test1234!")
AMIGO = ("amigo@quienva.app", "Test1234!")


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return r.json()["token"]


def _me(token):
    r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"}, timeout=15)
    assert r.status_code == 200
    return r.json()


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def tokens():
    at = _login(*ADMIN)
    tt = _login(*TEST)
    ft = _login(*AMIGO)
    return {"admin": at, "test": tt, "amigo": ft}


@pytest.fixture(scope="module")
def user_ids(tokens):
    return {
        "admin": _me(tokens["admin"])["user_id"],
        "test": _me(tokens["test"])["user_id"],
        "amigo": _me(tokens["amigo"])["user_id"],
    }


@pytest.fixture(scope="module", autouse=True)
def _ensure_friends(tokens, user_ids):
    # make sure test <-> amigo are friends (idempotent via API)
    r = requests.get(f"{API}/friends", headers=_hdr(tokens["test"]), timeout=15)
    ids = [f["user_id"] for f in r.json()] if r.status_code == 200 else []
    if user_ids["amigo"] in ids:
        return
    rr = requests.post(f"{API}/friends/request", headers=_hdr(tokens["test"]),
                       json={"user_id": user_ids["amigo"]}, timeout=15)
    if rr.status_code == 200:
        req_id = rr.json().get("request_id")
        requests.post(f"{API}/friends/respond", headers=_hdr(tokens["amigo"]),
                      json={"request_id": req_id, "accept": True}, timeout=15)


# ---------- helpers ----------
def _create_plan(token, **extra):
    body = {
        "titulo": "TEST plan",
        "opciones": [{"texto_libre": "A"}, {"texto_libre": "B"}],
        "umbral_personas": 5,
    }
    body.update(extra)
    r = requests.post(f"{API}/plans", headers=_hdr(token), json=body, timeout=15)
    assert r.status_code == 200, f"create plan: {r.status_code} {r.text}"
    return r.json()


# ========================================================
# RESPOND: frictionless
# ========================================================
class TestRespondFrictionless:
    def test_no_auth_no_apodo_invitado_N_excludes_pending(self, tokens, user_ids):
        # plan with invited friend (pending). N must NOT count pending invitees.
        plan = _create_plan(tokens["test"], titulo="TEST invitado-N",
                            invitar_user_ids=[user_ids["amigo"]])
        slug = plan["slug"]

        # Confirm there is 1 pending participant and total=0
        g = requests.get(f"{API}/plans/{slug}", timeout=15).json()
        assert g["counts"]["pendiente"] == 1, g["counts"]
        assert g["counts"]["total"] == 0

        # (a) respond with ONLY {intencion:'dentro'} no auth
        r = requests.post(f"{API}/plans/{slug}/respond",
                          json={"intencion": "dentro"}, timeout=15)
        assert r.status_code == 200, r.text
        pt = r.json()["participante_token"]
        assert pt

        # Fetch plan: new row must be 'Invitado 1' (not 2, pending excluded)
        g = requests.get(f"{API}/plans/{slug}", timeout=15).json()
        apodos = [p["apodo"] for p in g["participants"] if p.get("intencion") != "pendiente"]
        assert "Invitado 1" in apodos, f"expected 'Invitado 1', got {apodos}"

    def test_rename_not_duplicate_token_in_body(self, tokens):
        plan = _create_plan(tokens["test"], titulo="TEST rename-body")
        slug = plan["slug"]
        r = requests.post(f"{API}/plans/{slug}/respond",
                          json={"intencion": "dentro"}, timeout=15)
        assert r.status_code == 200
        pt = r.json()["participante_token"]

        # Second call with token in BODY and new apodo
        r2 = requests.post(f"{API}/plans/{slug}/respond",
                           json={"intencion": "dentro", "apodo": "Marta",
                                 "participante_token": pt}, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["participante_token"] == pt  # same token

        g = requests.get(f"{API}/plans/{slug}", timeout=15).json()
        answered = [p for p in g["participants"] if p.get("intencion") != "pendiente"]
        assert len(answered) == 1, f"should not duplicate; got {len(answered)}"
        assert answered[0]["apodo"] == "Marta"

    def test_rename_not_duplicate_token_in_header(self, tokens):
        plan = _create_plan(tokens["test"], titulo="TEST rename-header")
        slug = plan["slug"]
        r = requests.post(f"{API}/plans/{slug}/respond",
                          json={"intencion": "dentro"}, timeout=15)
        pt = r.json()["participante_token"]

        r2 = requests.post(f"{API}/plans/{slug}/respond",
                           headers={"x-participante-token": pt},
                           json={"intencion": "dentro", "apodo": "Luis"}, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["participante_token"] == pt

        g = requests.get(f"{API}/plans/{slug}", timeout=15).json()
        answered = [p for p in g["participants"] if p.get("intencion") != "pendiente"]
        assert len(answered) == 1
        assert answered[0]["apodo"] == "Luis"

    def test_authed_no_apodo_uses_display_name_and_privacy(self, tokens, user_ids):
        """Authed response w/o apodo: uses account name; user_id NOT in public JSON;
        plan.mine populated when authed GET; no duplicate rows."""
        plan = _create_plan(tokens["test"], titulo="TEST authed-noapodo")
        slug = plan["slug"]
        amigo_me = _me(tokens["amigo"])
        expected_name = amigo_me.get("display_name") or amigo_me.get("name") or amigo_me.get("username")

        r = requests.post(f"{API}/plans/{slug}/respond",
                          headers=_hdr(tokens["amigo"]),
                          json={"intencion": "dentro"}, timeout=15)
        assert r.status_code == 200, r.text

        # Public GET (no auth) must NOT expose user_id in participants
        pub = requests.get(f"{API}/plans/{slug}", timeout=15).json()
        answered = [p for p in pub["participants"] if p.get("intencion") != "pendiente"]
        assert len(answered) == 1, f"duplicate rows: {answered}"
        row = answered[0]
        # user_id is intentionally hidden for privacy on public JSON
        assert "user_id" not in row or row.get("user_id") in (None, ""), f"privacy leak: {row}"
        # Apodo should be their account display name (not Invitado N)
        assert row["apodo"] and not row["apodo"].startswith("Invitado "), row["apodo"]

        # Authed GET as the same user: plan.mine must be populated
        authed = requests.get(f"{API}/plans/{slug}", headers=_hdr(tokens["amigo"]), timeout=15).json()
        mine = authed.get("mine")
        assert mine, f"plan.mine should be populated when authed, got {authed.keys()}"
        # Second response with same account should NOT duplicate
        r2 = requests.post(f"{API}/plans/{slug}/respond",
                           headers=_hdr(tokens["amigo"]),
                           json={"intencion": "paso"}, timeout=15)
        assert r2.status_code == 200
        pub2 = requests.get(f"{API}/plans/{slug}", timeout=15).json()
        answered2 = [p for p in pub2["participants"] if p.get("intencion") != "pendiente"]
        assert len(answered2) == 1


# ========================================================
# Invited pending friend answering with his account
# ========================================================
class TestInvitedFriendAnswers:
    def test_pending_to_dentro_no_duplicate(self, tokens, user_ids):
        plan = _create_plan(tokens["test"], titulo="TEST invited-answers",
                            invitar_user_ids=[user_ids["amigo"]])
        slug = plan["slug"]
        g0 = requests.get(f"{API}/plans/{slug}", timeout=15).json()
        assert g0["counts"]["pendiente"] == 1
        assert g0["counts"]["total"] == 0

        r = requests.post(f"{API}/plans/{slug}/respond",
                          headers=_hdr(tokens["amigo"]),
                          json={"intencion": "dentro"}, timeout=15)
        assert r.status_code == 200

        g1 = requests.get(f"{API}/plans/{slug}", timeout=15).json()
        assert g1["counts"]["pendiente"] == 0, g1["counts"]
        assert g1["counts"]["total"] == 1, g1["counts"]
        rows = g1["participants"]
        assert len(rows) == 1, f"should update not duplicate: {rows}"
        assert rows[0]["intencion"] == "dentro"


# ========================================================
# Live Activity endpoints
# ========================================================
class TestLiveActivity:
    def test_token_upsert_and_admin_listing(self, tokens):
        plan = _create_plan(tokens["test"], titulo="TEST live-activity")
        slug = plan["slug"]
        activity_id = f"plan:{slug}"
        tok = "a" * 64

        # No auth -> 401
        r_noauth = requests.post(f"{API}/live-activity/token",
                                 json={"activity_id": activity_id, "token": tok,
                                       "plan_slug": slug}, timeout=15)
        assert r_noauth.status_code == 401, r_noauth.status_code

        # Auth -> 200 with plan_id
        r = requests.post(f"{API}/live-activity/token",
                          headers=_hdr(tokens["test"]),
                          json={"activity_id": activity_id, "token": tok,
                                "plan_slug": slug}, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert body.get("plan_id"), body

        # Repeat -> upsert (still 200, same plan_id)
        r2 = requests.post(f"{API}/live-activity/token",
                           headers=_hdr(tokens["test"]),
                           json={"activity_id": activity_id, "token": tok + "b"[:0],
                                 "plan_slug": slug}, timeout=15)
        assert r2.status_code == 200
        assert r2.json().get("plan_id") == body["plan_id"]

        # Admin list contains it (no dup)
        la = requests.get(f"{API}/admin/live-activities",
                          headers=_hdr(tokens["admin"]), timeout=15)
        assert la.status_code == 200, la.text
        payload = la.json()
        items = payload if isinstance(payload, list) else payload.get("items") or payload.get("activities") or []
        matching = [x for x in items if x.get("activity_id") == activity_id]
        assert len(matching) == 1, f"expected 1 match, got {len(matching)}: {matching}"

        # End
        r_end = requests.post(f"{API}/live-activity/end",
                              headers=_hdr(tokens["test"]),
                              json={"activity_id": activity_id}, timeout=15)
        assert r_end.status_code == 200
        assert r_end.json().get("ok") is True


# ========================================================
# APNs unconfigured must not break respond/close/cancel
# ========================================================
class TestNoApnsDoesNotBreakVoting:
    def test_respond_close_cancel_still_200(self, tokens):
        plan = _create_plan(tokens["test"], titulo="TEST no-apns",
                            umbral_personas=2)
        slug = plan["slug"]
        creator_tok = plan["creador_token"]

        # Register a fake Live Activity token so push code paths run
        requests.post(f"{API}/live-activity/token",
                      headers=_hdr(tokens["test"]),
                      json={"activity_id": f"plan:{slug}", "token": "f" * 64,
                            "plan_slug": slug}, timeout=15)

        # respond twice -> threshold reached -> auto close
        r1 = requests.post(f"{API}/plans/{slug}/respond",
                           json={"intencion": "dentro", "apodo": "P1"}, timeout=15)
        assert r1.status_code == 200
        r2 = requests.post(f"{API}/plans/{slug}/respond",
                           json={"intencion": "dentro", "apodo": "P2"}, timeout=15)
        assert r2.status_code == 200

        # close idempotent
        rc = requests.post(f"{API}/plans/{slug}/close",
                           headers={"x-participante-token": creator_tok}, timeout=15)
        assert rc.status_code in (200, 409)  # may already be closed

        # cancel on a fresh plan
        plan2 = _create_plan(tokens["test"], titulo="TEST no-apns-cancel")
        rcn = requests.post(f"{API}/plans/{plan2['slug']}/cancel",
                            headers={"x-participante-token": plan2["creador_token"]}, timeout=15)
        assert rcn.status_code == 200


# ========================================================
# Regression: invitables / invite / invite-reminders
# ========================================================
class TestInviteRegression:
    def test_invitables_and_invite_flows(self, tokens, user_ids):
        plan = _create_plan(tokens["test"], titulo="TEST invite-reg",
                            invitar_user_ids=[user_ids["amigo"]])
        slug = plan["slug"]

        # invitables as creator
        inv = requests.get(f"{API}/plans/{slug}/invitables",
                           headers=_hdr(tokens["test"]), timeout=15)
        assert inv.status_code == 200
        data = inv.json()
        assert data.get("puede_invitar") is True

        # Admin is not a participant -> 403 trying to invite
        r403 = requests.post(f"{API}/plans/{slug}/invite",
                             headers=_hdr(tokens["admin"]),
                             json={"user_ids": [user_ids["amigo"]]}, timeout=15)
        assert r403.status_code == 403, r403.status_code

        # Close plan then invite -> 409
        rc = requests.post(f"{API}/plans/{slug}/close",
                           headers={"x-participante-token": plan["creador_token"]}, timeout=15)
        assert rc.status_code == 200
        r409 = requests.post(f"{API}/plans/{slug}/invite",
                             headers=_hdr(tokens["test"]),
                             json={"user_ids": [user_ids["admin"]]}, timeout=15)
        assert r409.status_code == 409, r409.status_code

    def test_invite_reminders_single(self, tokens, user_ids):
        # Create plan with hora_limite in ~60min and invited friend
        hora = (datetime.utcnow() + timedelta(minutes=55)).isoformat() + "Z"
        plan = _create_plan(tokens["test"], titulo="TEST reminder",
                            hora_limite=hora,
                            invitar_user_ids=[user_ids["amigo"]])
        slug = plan["slug"]

        # Trigger reminders twice
        r1 = requests.post(f"{API}/admin/plans/invite-reminders",
                           headers=_hdr(tokens["admin"]), timeout=20)
        assert r1.status_code == 200, r1.text
        time.sleep(1)
        r2 = requests.post(f"{API}/admin/plans/invite-reminders",
                           headers=_hdr(tokens["admin"]), timeout=20)
        assert r2.status_code == 200

        # Count plan_invite_reminder for this slug
        notifs = requests.get(f"{API}/notifications",
                              headers=_hdr(tokens["amigo"]), timeout=15).json()
        matching = [n for n in notifs
                    if n.get("type") == "plan_invite_reminder" and slug in str(n)]
        assert len(matching) == 1, f"expected exactly 1 reminder, got {len(matching)}"
