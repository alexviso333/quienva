"""Iteration 8: SEO sitemap (path-based children) + Momentos feed backend tests."""
import os
import re
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"


# ---------- Sitemap ----------

def test_sitemap_index_content_type_and_children():
    r = requests.get(f"{API}/sitemap.xml", timeout=30)
    assert r.status_code == 200
    ct = r.headers.get("content-type", "")
    assert "xml" in ct, f"content-type not xml: {ct}"
    body = r.text
    assert "<sitemapindex" in body
    # children must be path-based, not query-string
    assert "sitemap-cities.xml" in body
    assert "sitemap-events-ibiza.xml" in body
    assert "?scope=" not in body, "child sitemap URLs must be path-based, not query-string"
    # extract child locs
    locs = re.findall(r"<loc>([^<]+)</loc>", body)
    assert any(l.endswith("/sitemap-cities.xml") for l in locs)
    assert any("/sitemap-events-" in l for l in locs)


def test_sitemap_cities():
    r = requests.get(f"{API}/sitemap-cities.xml", timeout=30)
    assert r.status_code == 200
    assert "xml" in r.headers.get("content-type", "")
    assert "<urlset" in r.text
    assert "/ciudad/" in r.text or "ibiza" in r.text.lower()


@pytest.mark.parametrize("city", ["ibiza", "madrid"])
def test_sitemap_events_city(city):
    r = requests.get(f"{API}/sitemap-events-{city}.xml", timeout=30)
    assert r.status_code == 200
    assert "xml" in r.headers.get("content-type", "")
    assert "<urlset" in r.text


def test_robots_txt():
    r = requests.get(f"{API}/robots.txt", timeout=15)
    assert r.status_code == 200
    assert "text/plain" in r.headers.get("content-type", "")
    assert re.search(r"(?im)^\s*Sitemap:", r.text)


# ---------- Regression: SEO city + event page ----------

def test_seo_city_ibiza_html():
    r = requests.get(f"{API}/ciudad/ibiza", timeout=30)
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    assert 'class="card"' in r.text
    # breadcrumb + faq indicators
    assert "BreadcrumbList" in r.text
    assert "FAQPage" in r.text


def test_seo_event_html():
    # find an event id from moments feed or a sitemap-events file
    r = requests.get(f"{API}/sitemap-events-ibiza.xml", timeout=30)
    m = re.search(r"/fiesta/([a-f0-9-]{36})", r.text)
    if not m:
        pytest.skip("no event URL in ibiza sitemap")
    eid = m.group(1)
    r2 = requests.get(f"{API}/fiesta/{eid}", timeout=30)
    assert r2.status_code == 200
    assert "text/html" in r2.headers.get("content-type", "")
    assert "FAQPage" in r2.text
    assert "BreadcrumbList" in r2.text


# ---------- Auth helpers ----------

@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login",
                      json={"email": "admin@quienva.app", "password": "admin123"},
                      timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---------- Momentos feed ----------

def test_moments_feed_amigos_only_friends(admin_headers):
    r = requests.get(f"{API}/moments/feed", params={"scope": "amigos", "limit": 20},
                     headers=admin_headers, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["scope"] == "amigos"
    assert "has_more" in data
    moments = data["moments"]
    assert isinstance(moments, list) and len(moments) > 0
    # All authors must be lucia or marc
    authors = {m["author"].get("username") for m in moments}
    assert authors.issubset({"lucia", "marc"}), f"unexpected authors in amigos: {authors}"
    for m in moments:
        assert "image_url" in m
        assert "likes" in m and "i_liked" in m
        assert "event_name" in m  # may be None


def test_moments_feed_discover_only_public_excludes_self(admin_headers):
    r = requests.get(f"{API}/moments/feed", params={"scope": "discover", "limit": 20},
                     headers=admin_headers, timeout=20)
    assert r.status_code == 200
    data = r.json()
    assert data["scope"] == "discover"
    moments = data["moments"]
    assert len(moments) > 0
    authors = {m["author"].get("username") for m in moments}
    assert authors.issubset({"sara", "tourist"}), f"discover leaked authors: {authors}"
    assert "admin" not in authors


def test_moments_feed_pagination(admin_headers):
    p1 = requests.get(f"{API}/moments/feed",
                      params={"scope": "discover", "skip": 0, "limit": 2},
                      headers=admin_headers, timeout=20).json()
    assert len(p1["moments"]) == 2
    assert p1["has_more"] is True
    p2 = requests.get(f"{API}/moments/feed",
                      params={"scope": "discover", "skip": 2, "limit": 2},
                      headers=admin_headers, timeout=20).json()
    ids1 = {m["id"] for m in p1["moments"]}
    ids2 = {m["id"] for m in p2["moments"]}
    assert ids1.isdisjoint(ids2), "pagination pages overlap"


def test_moments_like_toggle_reflects_in_feed(admin_headers):
    feed = requests.get(f"{API}/moments/feed",
                        params={"scope": "amigos", "limit": 1},
                        headers=admin_headers, timeout=20).json()
    assert feed["moments"], "no moments to like"
    m = feed["moments"][0]
    cid = m["id"]
    before_liked = bool(m["i_liked"])
    before_count = int(m["likes"])
    # toggle
    r = requests.post(f"{API}/captures/{cid}/like", headers=admin_headers, timeout=15)
    assert r.status_code == 200, r.text
    feed2 = requests.get(f"{API}/moments/feed",
                         params={"scope": "amigos", "limit": 20},
                         headers=admin_headers, timeout=20).json()
    m2 = next(x for x in feed2["moments"] if x["id"] == cid)
    assert m2["i_liked"] != before_liked, "i_liked did not toggle"
    if before_liked:
        assert m2["likes"] == before_count - 1
    else:
        assert m2["likes"] == before_count + 1
    # toggle back to leave state clean
    requests.post(f"{API}/captures/{cid}/like", headers=admin_headers, timeout=15)
