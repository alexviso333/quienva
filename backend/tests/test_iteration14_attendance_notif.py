"""
Iteration 14: Attendance gate + notif-mode filtering + past-events/calendar regression.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://full-stack-nightlife.preview.emergentagent.com").rstrip("/")

ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "QuienVa2025!"
TEST_EMAIL = "test@quienva.app"
TEST_PASSWORD = "Test1234!"


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text[:300]}"
    data = r.json()
    return data["token"], data["user"]


@pytest.fixture(scope="module")
def admin():
    tok, user = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    return {"token": tok, "user": user, "headers": {"Authorization": f"Bearer {tok}"}}


@pytest.fixture(scope="module")
def tester():
    # Re-seed attendance pending for this user
    import subprocess
    subprocess.run(["python", "/app/scripts/seed_attendance_test.py"], check=False, capture_output=True)
    tok, user = _login(TEST_EMAIL, TEST_PASSWORD)
    return {"token": tok, "user": user, "headers": {"Authorization": f"Bearer {tok}"}}


# ---------- attendance-pending ----------
class TestAttendancePending:
    def test_pending_lists_two(self, tester):
        r = requests.get(f"{BASE_URL}/api/me/attendance-pending", headers=tester["headers"], timeout=30)
        assert r.status_code == 200
        data = r.json()
        # Could be dict or list
        items = data if isinstance(data, list) else data.get("events") or data.get("items") or []
        assert len(items) >= 2, f"expected >=2 pending, got {len(items)}: {str(data)[:300]}"

    def test_confirm_went_true(self, tester):
        r = requests.get(f"{BASE_URL}/api/me/attendance-pending", headers=tester["headers"], timeout=30)
        items = r.json() if isinstance(r.json(), list) else r.json().get("events") or r.json().get("items") or []
        assert items, "need at least one pending to confirm"
        ev_id = items[0].get("id") or items[0].get("_id") or items[0].get("event_id")
        r2 = requests.post(f"{BASE_URL}/api/events/{ev_id}/attendance", json={"went": True}, headers=tester["headers"], timeout=30)
        assert r2.status_code == 200, r2.text[:300]
        # Should appear in past-events
        r3 = requests.get(f"{BASE_URL}/api/me/past-events", headers=tester["headers"], timeout=30)
        assert r3.status_code == 200
        past = r3.json() if isinstance(r3.json(), list) else r3.json().get("events") or r3.json().get("items") or []
        past_ids = [str(p.get("id") or p.get("_id") or p.get("event_id")) for p in past]
        assert str(ev_id) in past_ids, f"confirmed event {ev_id} not in past-events; got {past_ids[:5]}"

    def test_confirm_went_false(self, tester):
        r = requests.get(f"{BASE_URL}/api/me/attendance-pending", headers=tester["headers"], timeout=30)
        items = r.json() if isinstance(r.json(), list) else r.json().get("events") or r.json().get("items") or []
        if not items:
            pytest.skip("no more pending after first confirm")
        ev_id = items[0].get("id") or items[0].get("_id") or items[0].get("event_id")
        r2 = requests.post(f"{BASE_URL}/api/events/{ev_id}/attendance", json={"went": False}, headers=tester["headers"], timeout=30)
        assert r2.status_code == 200
        # Should NOT be in past-events
        r3 = requests.get(f"{BASE_URL}/api/me/past-events", headers=tester["headers"], timeout=30)
        past = r3.json() if isinstance(r3.json(), list) else r3.json().get("events") or r3.json().get("items") or []
        past_ids = [str(p.get("id") or p.get("_id") or p.get("event_id")) for p in past]
        assert str(ev_id) not in past_ids, "went=false should not add to past-events"
        # Should NOT re-appear in pending
        r4 = requests.get(f"{BASE_URL}/api/me/attendance-pending", headers=tester["headers"], timeout=30)
        pend = r4.json() if isinstance(r4.json(), list) else r4.json().get("events") or r4.json().get("items") or []
        pend_ids = [str(p.get("id") or p.get("_id") or p.get("event_id")) for p in pend]
        assert str(ev_id) not in pend_ids, "went=false should not stay in pending"

    def test_confirm_404_no_interest(self, tester):
        r = requests.post(f"{BASE_URL}/api/events/doesnotexist123/attendance", json={"went": True}, headers=tester["headers"], timeout=30)
        assert r.status_code in (404, 400), f"expected 404 got {r.status_code}"


# ---------- notif-prefs ----------
class TestNotifPrefs:
    def test_get_prefs(self, tester):
        r = requests.get(f"{BASE_URL}/api/me/notif-prefs", headers=tester["headers"], timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "mode" in data
        assert data["mode"] in ("esenciales", "todo")
        assert "extra_types" in data

    def test_set_mode_valid(self, tester):
        for mode in ("todo", "esenciales"):
            r = requests.put(f"{BASE_URL}/api/me/notif-mode", json={"mode": mode}, headers=tester["headers"], timeout=30)
            assert r.status_code == 200, r.text[:300]
            r2 = requests.get(f"{BASE_URL}/api/me/notif-prefs", headers=tester["headers"], timeout=30)
            assert r2.json()["mode"] == mode

    def test_set_mode_invalid(self, tester):
        r = requests.put(f"{BASE_URL}/api/me/notif-mode", json={"mode": "banana"}, headers=tester["headers"], timeout=30)
        assert r.status_code == 400


# ---------- notification filtering by mode ----------
def _get_notifs(headers):
    r = requests.get(f"{BASE_URL}/api/notifications", headers=headers, timeout=30)
    if r.status_code != 200:
        return []
    data = r.json()
    return data if isinstance(data, list) else data.get("notifications") or data.get("items") or []


def _create_event(admin_headers, city, title):
    import datetime
    d = datetime.datetime.utcnow() + datetime.timedelta(days=5)
    payload = {
        "name": title,
        "city": city,
        "venue": "TEST Venue",
        "date": d.strftime("%Y-%m-%d"),
        "time": "22:00",
        "genre": "test",
    }
    r = requests.post(f"{BASE_URL}/api/admin/events", json=payload, headers=admin_headers, timeout=30)
    return r


class TestNotifFiltering:
    def test_esenciales_blocks_new_event(self, admin, tester):
        # Set user to esenciales
        requests.put(f"{BASE_URL}/api/me/notif-mode", json={"mode": "esenciales"}, headers=tester["headers"], timeout=30)
        before = _get_notifs(tester["headers"])
        before_ne = [n for n in before if (n.get("type") or n.get("notif_type")) == "new_event"]
        # Create event in user's city
        city = tester["user"].get("city") or "Palma de Mallorca"
        r = _create_event(admin["headers"], city, "TEST_notif_esenciales_evt")
        assert r.status_code in (200, 201), r.text[:300]
        import time; time.sleep(1.5)
        after = _get_notifs(tester["headers"])
        after_ne = [n for n in after if (n.get("type") or n.get("notif_type")) == "new_event"]
        assert len(after_ne) == len(before_ne), f"new_event leaked in esenciales mode: before={len(before_ne)} after={len(after_ne)}"

    def test_todo_allows_new_event(self, admin, tester):
        requests.put(f"{BASE_URL}/api/me/notif-mode", json={"mode": "todo"}, headers=tester["headers"], timeout=30)
        before = _get_notifs(tester["headers"])
        before_ne = [n for n in before if (n.get("type") or n.get("notif_type")) == "new_event"]
        city = tester["user"].get("city") or "Palma de Mallorca"
        r = _create_event(admin["headers"], city, "TEST_notif_todo_evt")
        assert r.status_code in (200, 201)
        import time; time.sleep(1.5)
        after = _get_notifs(tester["headers"])
        after_ne = [n for n in after if (n.get("type") or n.get("notif_type")) == "new_event"]
        assert len(after_ne) > len(before_ne), f"new_event should arrive in todo mode: before={len(before_ne)} after={len(after_ne)}"
        # Restore
        requests.put(f"{BASE_URL}/api/me/notif-mode", json={"mode": "esenciales"}, headers=tester["headers"], timeout=30)

    def test_admin_always_receives(self, admin):
        notifs = _get_notifs(admin["headers"])
        ne = [n for n in notifs if (n.get("type") or n.get("notif_type")) == "new_event"]
        assert len(ne) > 0, "admin should have new_event notifs"


# ---------- regression ----------
class TestRegression:
    def test_events_list(self, tester):
        r = requests.get(f"{BASE_URL}/api/events", headers=tester["headers"], timeout=30)
        assert r.status_code == 200
        data = r.json()
        items = data if isinstance(data, list) else data.get("events") or data.get("items") or []
        assert len(items) > 0

    def test_stories_list(self, tester):
        r = requests.get(f"{BASE_URL}/api/stories", headers=tester["headers"], timeout=30)
        assert r.status_code == 200

    def test_plans_list(self, tester):
        r = requests.get(f"{BASE_URL}/api/plans/mine", headers=tester["headers"], timeout=30)
        assert r.status_code == 200

    def test_interest_endpoint(self, tester):
        # Pick any event
        r = requests.get(f"{BASE_URL}/api/events", headers=tester["headers"], timeout=30)
        items = r.json() if isinstance(r.json(), list) else r.json().get("events") or r.json().get("items") or []
        assert items
        ev_id = items[0].get("id") or items[0].get("_id")
        for s in ("me_interesa", "voy", "none"):
            r2 = requests.post(f"{BASE_URL}/api/events/{ev_id}/interest", json={"status": s}, headers=tester["headers"], timeout=30)
            assert r2.status_code in (200, 201), f"interest {s} -> {r2.status_code} {r2.text[:200]}"

    def test_calendar_no_unconfirmed_past(self, tester):
        # Re-seed to produce pending past 'voy'
        import subprocess
        subprocess.run(["python", "/app/scripts/seed_attendance_test.py"], check=False, capture_output=True)
        r = requests.get(f"{BASE_URL}/api/me/calendar", headers=tester["headers"], timeout=30)
        assert r.status_code == 200
        data = r.json()
        items = data if isinstance(data, list) else data.get("events") or data.get("items") or []
        import datetime
        now = datetime.datetime.utcnow()
        for it in items:
            st = it.get("start_time") or it.get("date")
            if not st:
                continue
            try:
                dt = datetime.datetime.fromisoformat(str(st).replace("Z", ""))
            except Exception:
                continue
            if dt < now:
                # must be confirmed
                status = (it.get("my_status") or it.get("status") or "").lower()
                assert status == "estuve" or it.get("has_my_photos"), f"past event not confirmed in calendar: {it.get('id')} status={status}"

    def test_past_events_no_unconfirmed(self, tester):
        r = requests.get(f"{BASE_URL}/api/me/past-events", headers=tester["headers"], timeout=30)
        assert r.status_code == 200
        data = r.json()
        items = data if isinstance(data, list) else data.get("events") or data.get("items") or []
        for it in items:
            status = (it.get("my_status") or it.get("status") or "").lower()
            # Must be 'estuve' or have own photos
            assert status == "estuve" or it.get("has_my_photos") or it.get("my_photos"), \
                f"past-events contains unconfirmed: {it.get('id')} status={status}"
