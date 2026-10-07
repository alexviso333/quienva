"""Iteration 13: /api/p/{slug} splits bot vs human; /api/p/nuevo redirect flow."""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://voting-party-planner.preview.emergentagent.com").rstrip("/")
EXISTING_SLUG = "qa-organico-3251"

HUMAN_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1"
BOT_UAS = [
    "WhatsApp/2.23.14",
    "facebookexternalhit/1.1",
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Twitterbot/1.0",
]


def _get(path, ua=None, allow_redirects=False, params=None):
    headers = {}
    if ua is not None:
        headers["User-Agent"] = ua
    return requests.get(f"{BASE_URL}{path}", headers=headers, allow_redirects=allow_redirects, params=params, timeout=20)


# ---------------- Plan slug (human → 302 to /plan/{slug}) ----------------

def test_plan_slug_human_redirects_to_plan_route():
    r = _get(f"/api/p/{EXISTING_SLUG}", ua=HUMAN_UA)
    assert r.status_code == 302, r.status_code
    loc = r.headers.get("location", "")
    assert loc.endswith(f"/plan/{EXISTING_SLUG}"), f"Unexpected redirect: {loc}"


# Bots get SSR HTML with OG tags
@pytest.mark.parametrize("ua", BOT_UAS)
def test_plan_slug_bot_returns_ssr_html(ua):
    r = _get(f"/api/p/{EXISTING_SLUG}", ua=ua)
    assert r.status_code == 200, f"UA={ua} -> {r.status_code}"
    html = r.text
    assert "og:title" in html
    assert "og:description" in html
    assert "og:image" in html


# No UA treated as bot (safe default for previews)
def test_plan_slug_no_ua_returns_ssr_html():
    r = _get(f"/api/p/{EXISTING_SLUG}", ua=None)
    # requests sends default UA; explicitly pass empty
    r = requests.get(f"{BASE_URL}/api/p/{EXISTING_SLUG}", headers={"User-Agent": ""}, allow_redirects=False, timeout=20)
    assert r.status_code == 200
    assert "og:title" in r.text


# ---------------- /api/p/nuevo ----------------

def test_plan_nuevo_human_redirects_to_feed_crear():
    r = _get("/api/p/nuevo", ua=HUMAN_UA)
    assert r.status_code == 302
    loc = r.headers.get("location", "")
    assert loc.endswith("/feed?crear=1"), f"Unexpected redirect: {loc}"


def test_plan_nuevo_human_preserves_evento_param():
    r = _get("/api/p/nuevo", ua=HUMAN_UA, params={"evento": "abc123"})
    assert r.status_code == 302
    loc = r.headers.get("location", "")
    assert "/feed?crear=1" in loc
    assert "evento=abc123" in loc


def test_plan_nuevo_bot_returns_ssr_html():
    r = _get("/api/p/nuevo", ua="WhatsApp/2.23")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")


# ---------------- 404 preserved ----------------

def test_plan_slug_not_found_returns_404_for_bot():
    r = _get("/api/p/non-existent-slug-xyz-9999", ua="WhatsApp/2.23")
    assert r.status_code == 404


def test_plan_slug_not_found_for_human_still_redirects_or_404():
    # Humans with inexistent slug: current impl checks plan first for humans?
    # Actually code: for non-"nuevo", it fetches plan; if missing -> 404; else redirect.
    r = _get("/api/p/non-existent-slug-xyz-9999", ua=HUMAN_UA)
    assert r.status_code == 404
