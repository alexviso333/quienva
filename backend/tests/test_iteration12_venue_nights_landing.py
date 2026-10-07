"""Iteration 12: Venue nights endpoint + SSR landing sections (plan sharable, after)."""
import os
import re
import urllib.parse
from datetime import datetime
from zoneinfo import ZoneInfo
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://voting-party-planner.preview.emergentagent.com").rstrip("/")
TIFFANY_EVENT_ID = "d5d1ba48-e907-49a9-b6ed-f4d76a3dbdba"


# ---------- venue-nights endpoint ----------
class TestVenueNights:
    def test_returns_upcoming_nights_only(self):
        """Desde "el plan se decide solo" este endpoint devuelve las PRÓXIMAS
        noches del local (antes devolvía pasadas, que se leían como "fiestas a
        las que fuiste" y no era verdad)."""
        r = requests.get(f"{BASE_URL}/api/events/{TIFFANY_EVENT_ID}/venue-nights", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        nights = data.get("nights") or []
        assert data.get("count") == len(nights)
        assert len(nights) <= 8
        if not nights:
            return
        assert data.get("kind") == "upcoming"
        today = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
        dates = [n["date"] for n in nights]
        assert all(d >= today for d in dates), f"past night returned: {dates}"
        assert dates == sorted(dates), f"not ascending: {dates}"
        assert all(n["id"] != TIFFANY_EVENT_ID for n in nights)
        for n in nights:
            for k in ("id", "name", "date", "time", "image_url", "price", "sale_state"):
                assert k in n, f"night missing key {k}"
            assert "attended" not in n and "photos" not in n

    def test_non_existent_event_returns_empty(self):
        r = requests.get(f"{BASE_URL}/api/events/not-a-real-event-id/venue-nights", timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert data.get("nights") == []
        assert data.get("count") == 0

    def test_venue_without_past_nights(self):
        # Find a non-Tiffany event via listing
        r = requests.get(f"{BASE_URL}/api/events?limit=50", timeout=20)
        assert r.status_code == 200
        events = r.json() if isinstance(r.json(), list) else r.json().get("events", [])
        target = None
        for e in events:
            v = (e.get("venue") or "").lower()
            if v and "tiffany" not in v:
                target = e
                break
        if not target:
            pytest.skip("no non-Tiffany event available in list")
        enc = urllib.parse.quote(target["id"].encode("utf-8", "surrogatepass"), safe="")
        r2 = requests.get(f"{BASE_URL}/api/events/{enc}/venue-nights", timeout=20)
        assert r2.status_code == 200, r2.text
        data = r2.json()
        assert data.get("count") == 0
        assert data.get("nights") == []


# ---------- SSR landing ----------
class TestSSRLanding:
    @pytest.mark.parametrize("path,plan_badges", [
        ("/api/home", ["Recuerdos", "Wrapped", "Embajador"]),
        ("/api/en/home", ["Memories", "Wrapped", "Ambassador"]),
        ("/api/de/home", ["Erinnerungen", "Wrapped", "Botschafter"]),
    ])
    def test_home_has_plan_and_after_sections(self, path, plan_badges):
        r = requests.get(f"{BASE_URL}{path}", timeout=20)
        assert r.status_code == 200
        html = r.text
        assert 'class="plansec"' in html, f"missing plansec in {path}"
        assert 'class="pdemo"' in html, f"missing pdemo in {path}"
        assert "/p/nuevo" in html, f"missing /p/nuevo CTA in {path}"
        assert 'class="after"' in html, f"missing after section in {path}"
        for kw in plan_badges:
            assert kw in html, f"missing {kw} in {path}"

    def test_home_stats_bar_has_only_numeric_counters(self):
        html = requests.get(f"{BASE_URL}/api/home", timeout=20).text
        m = re.search(r'class="stats"[^>]*>(.*?)</div>', html, re.S)
        if not m:
            # Desde "el plan se decide solo": si no hay ningún dato > 50 la barra
            # de contadores NO se renderiza (antes salía "0 planes esta semana").
            return
        stats = m.group(1)
        # No bogus pills without numbers
        assert "A la venta" not in stats
        assert "Esta noche" not in stats
        # El contador de "ciudades" se quitó (6 nunca impresiona a nadie).
        assert "ciudades" not in stats
        # Todo lo que quede tiene que ser un número REAL y mayor que 50.
        nums = [int(n) for n in re.findall(r"<b>\s*([0-9]+)\s*</b>", stats)]
        assert nums, "stats bar rendered with no numbers"
        assert all(n > 50 for n in nums), f"stat <= 50 shown: {nums}"

    def test_city_and_sitemap_still_200(self):
        assert requests.get(f"{BASE_URL}/api/ciudad/madrid", timeout=20).status_code == 200
        r = requests.get(f"{BASE_URL}/api/sitemap.xml", timeout=20)
        assert r.status_code == 200
        assert "<sitemapindex" in r.text or "<urlset" in r.text
