"""Phase B (Fundador badge, group_going alert) and Phase C (group polls) tests."""
import os
import time
import uuid
import pytest
import requests

def _load_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        try:
            with open("/app/frontend/.env") as f:
                for ln in f:
                    if ln.startswith("REACT_APP_BACKEND_URL="):
                        v = ln.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
    return v.rstrip("/")

BASE_URL = _load_url()
API = f"{BASE_URL}/api"


def _reg(suffix, delay=16):
    time.sleep(delay)  # avoid rate-limit
    u = f"TEST_pbc_{suffix}_{uuid.uuid4().hex[:6]}"
    payload = {
        "email": f"{u}@example.com",
        "password": "Testpass123!",
        "name": f"Test {suffix}",
        "username": u.lower(),
        "city": "Palma de Mallorca",
        "birthdate": "2000-01-01",
    }
    r = requests.post(f"{API}/auth/register", json=payload, timeout=30)
    assert r.status_code == 200, f"register {suffix}: {r.status_code} {r.text}"
    d = r.json()
    return d["token"], d["user"]


def _h(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def users():
    ta, ua = _reg("A", delay=0)
    tb, ub = _reg("B")
    return {"a": (ta, ua), "b": (tb, ub)}


@pytest.fixture(scope="module")
def group_and_invite(users):
    ta, _ = users["a"]
    tb, _ = users["b"]
    r = requests.post(f"{API}/groups", json={"name": "TEST_PBC_Group", "member_ids": []}, headers=_h(ta), timeout=20)
    assert r.status_code == 200, r.text
    gid = r.json()["id"]
    r2 = requests.get(f"{API}/groups/{gid}/invite", headers=_h(ta), timeout=20)
    assert r2.status_code == 200
    code = r2.json()["code"]
    # B joins
    r3 = requests.post(f"{API}/me/claim-group-invite", json={"code": code}, headers=_h(tb), timeout=20)
    assert r3.status_code == 200, r3.text
    return gid


# --- Phase B: Founder badge ---
def test_founder_badge_awarded_to_A(users, group_and_invite):
    ta, _ = users["a"]
    r = requests.get(f"{API}/me/badges", headers=_h(ta), timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    earned = data.get("earned") or data.get("badges") or []
    ids = [b.get("id") if isinstance(b, dict) else b for b in earned]
    assert "founder" in ids, f"founder not in {ids}; full: {data}"


# --- Phase B: group_going alert on "voy" ---
def test_group_notified_when_member_going(users, group_and_invite):
    ta, _ = users["a"]
    tb, _ = users["b"]
    r = requests.get(f"{API}/events", params={"date_filter": "all", "genre": "all"}, headers=_h(ta), timeout=20)
    assert r.status_code == 200
    events = r.json()
    lst = events if isinstance(events, list) else events.get("items") or events.get("events") or []
    assert lst, "no events available"
    eid = lst[0]["id"]
    r2 = requests.post(f"{API}/events/{eid}/interest", json={"status": "voy"}, headers=_h(tb), timeout=20)
    assert r2.status_code == 200, r2.text
    time.sleep(1.5)
    r3 = requests.get(f"{API}/notifications", headers=_h(ta), timeout=20)
    assert r3.status_code == 200
    notifs = r3.json()
    items = notifs if isinstance(notifs, list) else notifs.get("items") or []
    texts = " || ".join([str(n.get("text") or n.get("message") or n.get("body") or n) for n in items])
    assert "TEST_PBC_Group" in texts or "grupo" in texts.lower(), f"no group alert found in: {texts[:500]}"


# --- Phase C: Polls ---
@pytest.fixture(scope="module")
def poll_ctx(users, group_and_invite):
    ta, _ = users["a"]
    payload = {"title": "¿Dónde vamos?", "options": [{"label": "A"}, {"label": "B"}, {"label": "C"}]}
    r = requests.post(f"{API}/groups/{group_and_invite}/polls", json=payload, headers=_h(ta), timeout=20)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p.get("status") == "open"
    assert len(p["options"]) == 3
    return {"gid": group_and_invite, "pid": p["id"], "opts": p["options"]}


def test_poll_vote_and_change(users, poll_ctx):
    tb, _ = users["b"]
    gid, pid, opts = poll_ctx["gid"], poll_ctx["pid"], poll_ctx["opts"]
    # First vote
    r = requests.post(f"{API}/groups/{gid}/polls/{pid}/vote", json={"option_id": opts[0]["id"]}, headers=_h(tb), timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("my_vote") == opts[0]["id"]
    total1 = d.get("total_votes")
    # Change vote (same user)
    r2 = requests.post(f"{API}/groups/{gid}/polls/{pid}/vote", json={"option_id": opts[1]["id"]}, headers=_h(tb), timeout=20)
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2.get("my_vote") == opts[1]["id"]
    assert d2.get("total_votes") == total1, f"total_votes changed {total1}->{d2.get('total_votes')}"


def test_list_polls_shows_my_vote(users, poll_ctx):
    tb, _ = users["b"]
    r = requests.get(f"{API}/groups/{poll_ctx['gid']}/polls", headers=_h(tb), timeout=20)
    assert r.status_code == 200
    polls = r.json()
    mine = next((p for p in polls if p["id"] == poll_ctx["pid"]), None)
    assert mine and mine.get("my_vote") == poll_ctx["opts"][1]["id"]


def test_close_by_non_creator_forbidden(users, poll_ctx):
    tb, _ = users["b"]
    r = requests.post(f"{API}/groups/{poll_ctx['gid']}/polls/{poll_ctx['pid']}/close", headers=_h(tb), timeout=20)
    assert r.status_code == 403, f"expected 403 got {r.status_code}: {r.text}"


def test_close_by_creator_and_vote_after_close(users, poll_ctx):
    ta, _ = users["a"]
    tb, _ = users["b"]
    r = requests.post(f"{API}/groups/{poll_ctx['gid']}/polls/{poll_ctx['pid']}/close", headers=_h(ta), timeout=20)
    assert r.status_code == 200, r.text
    assert r.json().get("status") == "closed"
    # vote after close
    r2 = requests.post(f"{API}/groups/{poll_ctx['gid']}/polls/{poll_ctx['pid']}/vote",
                       json={"option_id": poll_ctx["opts"][2]["id"]}, headers=_h(tb), timeout=20)
    assert r2.status_code == 400, f"expected 400 got {r2.status_code}: {r2.text}"
