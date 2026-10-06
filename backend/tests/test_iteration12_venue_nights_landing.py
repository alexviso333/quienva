"""Iteration 12: Venue nights endpoint + SSR landing sections (plan sharable, after)."""
import os
import re
import urllib.parse
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://full-stack-nights.preview.emergentagent.com").rstrip("/")
TIFFANY_EVENT_ID = "d5d1ba48-e907-49a9-b6ed-f4d76a3dbdba"


# ---------- venue-nights endpoint ----------
class TestVenueNights:
    def test_tiffany_returns_three_nights(self):
        r = requests.get(f"{BASE_URL}/api/events/{TIFFANY_EVENT_ID}/venue-nights", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("venue") == "Tiffany's"
        assert data.get("count") == 3
        nights = data.get("nights") or []
        assert len(nights) == 3
        by_name = {n["name"]: n for n in nights}
        for required in ("Reggaeton Night", "Techno Marathon", "Opening Party"):
            assert required in by_name, f"missing {required}: got {list(by_name)}"
        expected_dates = {"Reggaeton Night": "2026-09-27", "Techno Marathon": "2026-09-20", "Opening Party": "2026-09-13"}
        for name, exp in expected_dates.items():
            assert by_name[name]["date"] == exp
        for n in nights:
            for k in ("id", "name", "date", "image_url", "attended", "photos"):
                assert k in n, f"night missing key {k}"

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
        assert m, "stats bar not found"
        stats = m.group(1)
        # No bogus pills without numbers
        assert "A la venta" not in stats
        assert "Esta noche" not in stats
        # Must have the numeric stat labels
        assert "planes esta semana" in stats
        assert "ciudades" in stats
        assert "discotecas" in stats

    def test_city_and_sitemap_still_200(self):
        assert requests.get(f"{BASE_URL}/api/ciudad/madrid", timeout=20).status_code == 200
        r = requests.get(f"{BASE_URL}/api/sitemap.xml", timeout=20)
        assert r.status_code == 200
        assert "<sitemapindex" in r.text or "<urlset" in r.text
