from dotenv import load_dotenv
from pathlib import Path
import os
import io
import time

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, UploadFile, File, Form, Query, Header
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import Response as StarletteResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
import logging
import uuid
import bcrypt
from urllib.parse import urlparse
import secrets
import requests
import jwt
import re
import unicodedata
import json
import asyncio
from datetime import datetime, timezone, timedelta, date, time as dtime
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pywebpush import webpush, WebPushException
import apns
import httpx
import hashlib

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI(title="¿Quién va?")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("quienva")

SESSION_DAYS = 7
EMERGENT_SESSION_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"

# Self-hosted Google OAuth (no Emergent dependency). Optional: disabled if unset.
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_ENABLED = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)

# FourVenues affiliate/RRPP: ONLY the events that belong to OUR promoter profile
# (our microsite slug) get their ticket link rewritten to go through us, so the
# sale is attributed. Events we don't carry keep their normal link (rewriting
# them would break checkout). The set of "our" events is refreshed periodically
# from the FourVenues API, so as we're added to more promoters it updates itself.
AFFILIATE_SLUG = os.environ.get("FOURVENUES_AFFILIATE_SLUG", "quienva").strip()
# ClubTickets affiliate: our tracking code is appended to EVERY clubtickets.com
# ticket link served to buyers (?aff=CTxxx), so the sale is attributed to us.
# ClubTickets is Cloudflare-protected, so we can't scrape the public site; the
# venue calendars reach us via the venues' own sites (Night League) or the
# affiliate links panel (ClubTicketsScraper). Any event whose buy link points to
# clubtickets.com is therefore "ours" (revenue) → ranked first + admin-flagged.
CLUBTICKETS_AFF = os.environ.get("CLUBTICKETS_AFF", "CT226").strip()
# Our ClubTickets affiliate "links" panel (plain HTML, NOT Cloudflare-protected).
# The ClubTicketsScraper reads it to build each carried club's event calendar.
CLUBTICKETS_LINKS_URL = os.environ.get(
    "CLUBTICKETS_AFFILIATE_LINKS_URL",
    "https://admin.clubtickets.com/api/affiliate/2ae03ffd11d66db4120c78bf6a50aab0/links",
).strip()
# Key = (normalized venue/org name, YYYY-MM-DD, normalized event name) -> OUR slug.
# We match by (venue, date, name) because FourVenues gives a DIFFERENT event id/code
# per microsite, so the venue-scraped event and our promoter event never share ids.
# (venue, date, name) is the same real occurrence across microsites and is reliable.
_AFFILIATE_MAP: dict = {}
# Fallback index for clubs we carry under a DIFFERENT org name than the one the
# app scrapes (e.g. quienva's "CHANGO CLUB MADRID" vs the scraped "CHANGO MADRID").
# Keyed by (date, normalized event name) -> list of (original venue name, our slug),
# so an event can still be matched by same night+party when the venue names are
# aliases of the same physical club.
_AFFILIATE_BY_DN: dict = {}
_AFFILIATE_VENUES: list = []    # [{venue, city, events}] breakdown (admin insight)
_AFFILIATE_TS: float = 0.0      # last successful refresh (epoch seconds)


def _city_from_address(addr: str) -> str:
    """Extract the real city from a FourVenues addressComplete string, e.g.
    'C/ Marqués de Campo, 42, 03700 Dénia, Alicante, España' -> 'Dénia'."""
    if not addr:
        return ""
    m = re.search(r"\b\d{5}\s+([^,()]+)", addr)  # postal code + city
    if m:
        return m.group(1).strip()
    parts = [p.strip() for p in addr.split(",") if p.strip()]
    if parts and parts[-1].lower() in ("españa", "spain"):
        parts = parts[:-1]
    return parts[-1] if parts else ""


def _city_in_app(city: str) -> bool:
    """Whether a parsed city already maps to one of the app's supported cities."""
    c = _norm_name(city)
    if not c:
        return False
    for sc in SUPPORTED_CITIES:
        s = _norm_name(sc.get("label") or sc.get("name") or sc.get("id") or "")
        if not s:
            continue
        if c == s or c in s or s in c or s.split()[0] == c:
            return True
    return False




def _affiliate_key(venue: str, date: str, name: str) -> tuple:
    """Match key shared by the affiliate refresh and event lookup: normalized
    (venue/org name, YYYY-MM-DD, event name). Accent/punctuation-insensitive so
    the FourVenues org name lines up with the scraped venue name."""
    return (_norm_name(venue or ""), str(date or ""), _norm_name(name or ""))


def _affiliate_match(ev: dict):
    """Return (our_event_slug, affiliate_venue_norm) if we carry this event, else
    None. (1) EXACT match on (venue, date, name). (2) Fallback for clubs we carry
    under a DIFFERENT org name than the app scrapes: same (date, party name) AND the
    two club names are aliases of the same physical venue (distinctive-token subset,
    city words ignored) — so e.g. our 'CHANGO CLUB MADRID' marks the scraped
    'CHANGO MADRID'. It NEVER matches on date+name alone (that would mislabel other
    clubs' identically-named nights). affiliate_venue_norm is the normalized name of
    OUR carried club (used for coverage stats)."""
    if not AFFILIATE_SLUG or not _AFFILIATE_MAP:
        return None
    v = _norm_name(ev.get("venue", ""))
    d = str(ev.get("date") or "")
    n = _norm_name(ev.get("name", ""))
    slug = _AFFILIATE_MAP.get((v, d, n))
    if slug:
        return (slug, v)
    if _AFFILIATE_BY_DN and n:
        ev_venue = ev.get("venue", "")
        for (aff_venue, aff_slug) in _AFFILIATE_BY_DN.get((d, n), ()):
            if _venue_alias(aff_venue, ev_venue):
                return (aff_slug, _norm_name(aff_venue))
    return None


def _affiliate_slug_for(ev: dict) -> Optional[str]:
    m = _affiliate_match(ev)
    return m[0] if m else None


def _is_clubtickets_url(url: str) -> bool:
    """True if the URL points to clubtickets.com (our ClubTickets affiliate)."""
    if not url:
        return False
    try:
        return "clubtickets.com" in urlparse(url).netloc.lower()
    except Exception:
        return "clubtickets.com/" in url


def _clubtickets_affiliate_url(url: str) -> str:
    """Append our ClubTickets affiliate code (?aff=CTxxx) to a clubtickets.com
    link so the sale is attributed to us. Idempotent (never double-adds) and
    leaves non-clubtickets links untouched, so checkout never breaks."""
    if not url or not CLUBTICKETS_AFF or not _is_clubtickets_url(url):
        return url or ""
    if re.search(r"[?&]aff=", url):
        return url  # already tagged (e.g. links panel already includes it)
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}aff={CLUBTICKETS_AFF}"


def _is_our_clubtickets_url(url: str) -> bool:
    """True ONLY for a clubtickets.com link that carries OUR affiliate code
    (?aff=<CLUBTICKETS_AFF>). A plain clubtickets.com link WITHOUT our code is
    NOT ours — it's a party we don't carry, so it never counts as commission."""
    if not _is_clubtickets_url(url) or not CLUBTICKETS_AFF:
        return False
    return bool(re.search(r"[?&]aff=" + re.escape(CLUBTICKETS_AFF) + r"(?:&|$)", url or ""))


# Words that don't help tell two party names apart (promoter boilerplate, etc.).
_CT_NAME_STOP = {
    "presents", "present", "pres", "the", "party", "closing", "opening", "ibiza",
    "night", "show", "club", "con", "de", "del", "la", "el", "los", "las", "by",
    "vs", "and", "live", "tour", "featuring", "feat", "ft", "w", "at", "en",
    "2024", "2025", "2026", "2027",
}


def _ct_name_tokens(s: str) -> set:
    s = _norm_name(s or "")
    return {t for t in re.split(r"[^a-z0-9]+", s)
            if t and len(t) > 1 and t not in _CT_NAME_STOP}


def _ct_name_match(a: str, b: str) -> bool:
    """Fuzzy party-name match between a primary-source name and an affiliate-panel
    name (accent/case/punctuation-insensitive). True on exact/substring, or when
    the distinctive tokens overlap by >=50% (e.g. 'Anyma' ↔ 'Anyma Presents ÆDEN')."""
    na, nb = _norm_name(a or ""), _norm_name(b or "")
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    ta, tb = _ct_name_tokens(a), _ct_name_tokens(b)
    if not ta or not tb:
        return False
    inter = ta & tb
    return bool(inter) and (len(inter) / min(len(ta), len(tb))) >= 0.5


def _ct_night_date(date_str: str, time_str: str) -> str:
    """The 'night-label' date used to line up a primary-source party with the
    ClubTickets affiliate panel. A party whose start time is midnight (00:00)
    really belongs to the PREVIOUS night, so its night-label date is the day
    before — exactly the same normalization `_apply_scraped_event` applies before
    storing (00:00 -> 23:59 of the prior day). ClubTickets panel dates are already
    night-labels (Bubbles = the night of Aug 13), so normalizing the primary date
    the same way is what makes the two sources line up. Without this, a FourVenues
    party that starts at midnight carries the NEXT calendar day and wrongly matches
    the next night's ClubTickets party (e.g. 'The Most Beautiful Party' grabbing
    'Bubbles')."""
    if (time_str or "").strip() in ("00:00", "0:00", "00:00:00"):
        try:
            return (date.fromisoformat(str(date_str)) - timedelta(days=1)).isoformat()
        except Exception:
            return str(date_str or "")
    return str(date_str or "")


_CT_URL_KEY_RE = re.compile(
    r"/clubbing/([a-z0-9\-]+)(?:/([a-z0-9\-]+))?(?:/(\d{4}-\d{2}-\d{2}))?")


def _ct_url_key(url: str):
    """Canonical (venue_slug, event_slug, date) key for a clubtickets.com URL,
    ignoring the query string (?aff=...). Used to line up a party stored on an
    event (commission_url) with a party in the affiliate panel — the same triple
    parse_panel produces — so the coverage panel can tell matched vs unmatched
    regardless of aff-code re-encoding. Returns None if the URL isn't a
    clubtickets party URL with all three parts."""
    if not url:
        return None
    try:
        path = urlparse(url).path
    except Exception:
        path = url.split("?")[0]
    m = _CT_URL_KEY_RE.search(path or "")
    if not m:
        return None
    vslug, eslug, d = m.group(1), m.group(2), m.group(3)
    if not vslug or not eslug or not d:
        return None
    return (vslug, eslug, d)


def _event_is_mine(ev: dict) -> bool:
    """True if this event earns us commission: either a FourVenues party we carry
    in our promoter profile, OR a party whose ticket link goes through ClubTickets
    WITH OUR affiliate code (?aff) — i.e. a party we actually carry in our panel.
    A plain clubtickets.com link WITHOUT our code (a party we don't carry) is NOT
    ours. Ours get ranked first + admin-flagged; everything else keeps its normal
    link so checkout never breaks."""
    if _is_our_clubtickets_url(ev.get("commission_url", "")):
        return True
    return _affiliate_match(ev) is not None


def _guest_going_boost(ev: dict) -> int:
    """Subtle, GUEST-ONLY social-proof baseline added to an event's "X van" count.

    Goal (owner request): most parties that visibly show "X van" to logged-out
    visitors should be the ones we carry via our affiliate link — a nudge so new
    people buy through our link — but disguised so it never looks like only those
    have a crowd. Deterministic per event (stable across feed ↔ detail, no
    flicker). NEVER shown to registered users (they always see the real numbers),
    so it can't be spotted by regulars. Purely additive display value; it does
    not affect any real data, points, sorting or notifications."""
    try:
        h = int(hashlib.md5(str(ev.get("id", "")).encode()).hexdigest()[:8], 16)
    except Exception:
        h = 0
    if _event_is_mine(ev):
        # Our carried parties should be the ones that CATCH THE EYE — a bit
        # busier (typically 2–3, up to 5) so they stand out from the rest, but
        # still realistic, never inflated. ~25% still show 0 so it looks organic.
        pool = [0, 0, 0, 1, 2, 2, 3, 2, 3, 1, 4, 5]
        return pool[h % len(pool)]
    # Everyone else: quieter (mostly 0–1, the odd 2–3) so ours draw attention —
    # but enough of them still show someone that it never looks staged.
    pool = [0, 0, 0, 0, 0, 0, 0, 1, 1, 2, 1, 3]
    return pool[h % len(pool)]


_FV_CODE_RE = re.compile(r"/events/([A-Za-z0-9]+)/?$")
# Public short-link format: (www.)fourvenues.com/<org-slug>/<CODE>. The code is a
# short alphanumeric token (no hyphens). We read it so an event's OWN live link
# supplies the CURRENT code, instead of a possibly-stale code from the affiliate
# panel feed. The panel code desyncs when the club recreates the event (FourVenues
# issues a new code) → the auto affiliate link then points at a dead code (this was
# the "Fitz 10-sep → .../quienva/events/H6LG" broken-redirect bug).
_FV_PUBLIC_CODE_RE = re.compile(
    r"^https?://(?:www\.)?fourvenues\.com/[^/]+/([A-Za-z0-9]{3,12})/?$", re.I)


def _fv_event_code(url: str) -> str:
    """The trailing FourVenues event code (e.g. .../events/127U -> '127U', or the
    public short link www.fourvenues.com/<org>/4RA8 -> '4RA8')."""
    if not url:
        return ""
    base = url.split("?")[0].rstrip("/")
    m = _FV_CODE_RE.search(base)
    if m:
        return m.group(1)
    m = _FV_PUBLIC_CODE_RE.match(base)
    return m.group(1) if m else ""


def _affiliate_map_is_fresh() -> bool:
    """True if the quienva affiliate feed was refreshed successfully recently. When
    the feed is stale (e.g. FourVenues token expired → refresh keeps the old map),
    its event codes can be out of date, so we must NOT build affiliate links from
    them; we fall back to the event's own fresh direct link instead."""
    return bool(_AFFILIATE_TS) and (time.time() - _AFFILIATE_TS) < 6 * 3600


def _auto_commission_url_for(ev: dict) -> str:
    """The AUTOMATIC ticket link (scraper/affiliate logic), ignoring any manual
    admin override.

    Rule (matches the owner's model): parties that appear in OUR quienva affiliate
    feed get the quienva RRPP link so the sale is attributed to us; everything else
    keeps its own direct link, UNTOUCHED (never inject our slug).

    Freshness: FourVenues event codes are NOT shared across microsites — each RRPP
    (quienva, the club's own site...) has its OWN code namespace, so the ONLY valid
    quienva link is built from the code OUR quienva feed reports for that party
    (m[0]). Using the club's own code under our slug points at a DIFFERENT party
    (that was the 'Jueves FITZ → Mila X Golden Room' bug). The feed is re-scraped
    every run, so m[0] tracks the current quienva code. If the feed is STALE (e.g.
    token expired → refresh keeps the old map), we do NOT risk a wrong/404 quienva
    link: we serve the event's own direct link instead (works, no commission until
    the feed is fresh again)."""
    m = _affiliate_match(ev)
    direct = ev.get("commission_url", "") or ""
    if m and m[0] and _affiliate_map_is_fresh():
        return f"https://site.fourvenues.com/es/{AFFILIATE_SLUG}/events/{m[0]}"
    # Not ours, no fresh feed code → the event's own direct link, UNTOUCHED (never
    # inject our slug into a party we don't carry, never serve a stale quienva code).
    return direct


def _commission_url_for(ev: dict) -> str:
    """The ticket link served to buyers. An admin MANUAL override (link_override)
    ALWAYS wins — set from the event edit panel when the auto link is broken; the
    scraper never touches it. Otherwise fall back to the automatic link."""
    lo = str(ev.get("link_override") or "").strip()
    if lo:
        return lo
    return _auto_commission_url_for(ev)


def _fv_embed_url(ev: dict) -> str:
    """OFFICIAL FourVenues embeddable-widget URL for THIS event, with OUR RRPP slug.

    STRICT (owner): show the iframe ONLY for events that are LITERALLY in our
    FourVenues 'quienva' feed — an EXACT (venue, date, name) match in _AFFILIATE_MAP.
    We deliberately do NOT use the fuzzy venue-alias fallback here (it over-matches
    clubs we don't actually carry on FourVenues, e.g. Lío/Pacha, via same date+name).
    Everything else gets "" → the frontend keeps its existing buy button UNCHANGED
    (ClubTickets ?aff or direct scraped link). This does NOT change how buy links are
    decided anywhere; it only decides where the FourVenues iframe appears."""
    if not AFFILIATE_SLUG or not _AFFILIATE_MAP:
        return ""
    key = (_norm_name(ev.get("venue", "")), str(ev.get("date") or ""),
           _norm_name(ev.get("name", "")))
    feed_code = _AFFILIATE_MAP.get(key)
    if not feed_code:
        return ""  # not literally in our quienva RRPP feed → no iframe
    # Use OUR quienva feed's code (codes are per-microsite, not global — the club's
    # own code would embed a DIFFERENT party under our slug).
    return f"https://www.fourvenues.com/iframe/{AFFILIATE_SLUG}/events/{feed_code}"


VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:hola@quienva.app")

# Cities the app operates in. `id` is the canonical value stored on users +
# events (feed filters by exact match), `label` is what the UI shows.
SUPPORTED_CITIES = [
    {"id": "Palma de Mallorca", "label": "Palma de Mallorca", "emoji": "\U0001F3DD\uFE0F"},
    {"id": "Ibiza", "label": "Ibiza", "emoji": "\U0001F305"},
    {"id": "Madrid", "label": "Madrid", "emoji": "\U0001F306"},
    {"id": "Barcelona", "label": "Barcelona", "emoji": "\U0001F3D9\uFE0F"},
    {"id": "Marbella", "label": "Marbella / Puerto Ban\u00fas", "emoji": "\U0001F6E5\uFE0F"},
]
CITY_IDS = {c["id"] for c in SUPPORTED_CITIES}
# Sentinel city for scraped venues/parties that are NOT yet assigned to a
# supported city (admin marked them "pendiente de añadir"). It belongs to no
# region, so events with this city are hidden from every public feed until an
# admin reassigns them to a real supported city.
PENDING_CITY = "Pendiente"

# Each app-city behaves like its own isolated app. A region groups the canonical
# city with all of its sub-zones (the `city` value stored on venues/events), so
# a user in "Palma de Mallorca" sees the WHOLE island, an Ibiza user only Ibiza,
# etc. Feed, Locales, Map and notifications all use this so cities never mix.
CITY_REGIONS = {
    "Palma de Mallorca": [
        "Palma de Mallorca", "Mallorca", "Magaluf", "Can Picafort", "Alcúdia",
        "Cala Rajada", "Calvià", "Llucmajor", "Santa Ponsa", "Santanyí",
        "Cala d'Or", "Peguera", "Portals", "Sa Coma", "El Arenal", "s'Arenal",
    ],
    "Ibiza": [
        "Ibiza", "Eivissa", "Sant Antoni", "San Antonio", "Sant Josep",
        "Sant Rafel", "Platja d'en Bossa", "Santa Eulària", "Santa Eulalia",
    ],
    "Madrid": ["Madrid"],
    "Barcelona": ["Barcelona"],
    "Marbella": ["Marbella", "Puerto Banús", "Puerto Banus", "San Pedro", "San Pedro de Alcántara"],
}


def region_cities(user_city: str) -> list:
    """The list of stored `city` values that belong to a user's app-city."""
    return CITY_REGIONS.get(user_city, [user_city])


def region_for_city(city: str) -> str:
    """Reverse map: which app-city does a stored `city` value belong to."""
    for region, members in CITY_REGIONS.items():
        if city in members:
            return region
    return city


def city_query_value(user_city: str):
    """Mongo filter value for `city` given a user's app-city (region-aware)."""
    members = region_cities(user_city)
    return {"$in": members} if len(members) > 1 else members[0]


def _effective_city(user: dict, city_param: Optional[str]) -> str:
    """City used to filter the feed. A valid ?city= override wins (lets guests —
    and anyone — peek other supported cities without changing their account);
    otherwise fall back to the user's / guest's own city."""
    if city_param and city_param in CITY_IDS:
        return city_param
    return user.get("city", GUEST_CITY)

# In-memory TTL cache for expensive user-stats computation
_STATS_CACHE = {}

# In-memory TTL cache for /events/carousels (per user, short TTL)
_CAROUSELS_CACHE = {}
_CAROUSELS_TTL = 20  # seconds

scheduler = None

# --- Scraper bandwidth schedule (env-tunable) -------------------------------
# The scrapers are the app's biggest outbound-bandwidth ("service-initiated")
# consumer on Render. A two-tier schedule keeps freshness high where it matters
# (new parties, poster/name changes, near-term ticket states) while slashing
# egress: light runs refresh only near-term ticket details; full runs (a few
# times a day) refresh everything including far-future prices.
try:
    SCRAPER_LIGHT_INTERVAL_MIN = int(os.environ.get("SCRAPER_LIGHT_INTERVAL_MIN", "45"))
except Exception:
    SCRAPER_LIGHT_INTERVAL_MIN = 45
try:
    SCRAPER_LIGHT_WINDOW_DAYS = int(os.environ.get("SCRAPER_LIGHT_WINDOW_DAYS", "16"))
except Exception:
    SCRAPER_LIGHT_WINDOW_DAYS = 16
# Comma-separated hours (Europe/Madrid) for the full sweep. Default 3x/day.
SCRAPER_FULL_HOURS = os.environ.get("SCRAPER_FULL_HOURS", "7,15,22").strip() or "7,15,22"

# ---------------------------------------------------------------------------
# Local file storage (no external dependency, free, fully portable)
# ---------------------------------------------------------------------------
import mimetypes

APP_NAME = "quienva"
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", str(ROOT_DIR / "uploads")))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def save_object(rel_path: str, data: bytes) -> str:
    full = (UPLOAD_DIR / rel_path).resolve()
    if UPLOAD_DIR.resolve() not in full.parents:
        raise HTTPException(status_code=400, detail="Ruta inválida")
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(data)
    return rel_path


# --- Cloudinary (media persistence for Render's ephemeral FS) --------------
# Free-tier friendly. If not configured, we transparently fall back to local
# disk so development keeps working without any keys.
CLOUDINARY_ON = False
try:
    import cloudinary as _cloudinary
    import cloudinary.uploader as _cloudinary_uploader
    if os.environ.get("CLOUDINARY_URL"):
        _cloudinary.config(secure=True)  # SDK reads CLOUDINARY_URL from env
        CLOUDINARY_ON = True
    elif os.environ.get("CLOUDINARY_CLOUD_NAME") and os.environ.get("CLOUDINARY_API_KEY") and os.environ.get("CLOUDINARY_API_SECRET"):
        _cloudinary.config(
            cloud_name=os.environ["CLOUDINARY_CLOUD_NAME"],
            api_key=os.environ["CLOUDINARY_API_KEY"],
            api_secret=os.environ["CLOUDINARY_API_SECRET"],
            secure=True,
        )
        CLOUDINARY_ON = True
except Exception as _e:  # pragma: no cover
    CLOUDINARY_ON = False


def store_media(rel_path: str, data: bytes, content_type: str = "") -> str:
    """Persist a media blob and return a servable URL.
    Uses Cloudinary when configured (survives Render restarts), else local disk.
    """
    if CLOUDINARY_ON:
        try:
            resource_type = "video" if (content_type or "").startswith("video/") else "image"
            public_id = rel_path.rsplit(".", 1)[0]  # Cloudinary adds its own extension
            res = _cloudinary_uploader.upload(
                io.BytesIO(data),
                public_id=public_id,
                resource_type=resource_type,
                overwrite=True,
                invalidate=True,
            )
            return res.get("secure_url") or res.get("url")
        except Exception as e:
            logger.warning(f"Cloudinary upload failed, falling back to disk: {e}")
    save_object(rel_path, data)
    return f"/api/files/{rel_path}"


def read_object(rel_path: str):
    full = (UPLOAD_DIR / rel_path).resolve()
    if UPLOAD_DIR.resolve() not in full.parents or not full.exists():
        return None
    return full.read_bytes()


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Age (+18) helpers
# ---------------------------------------------------------------------------
def compute_age(birthdate: str) -> Optional[int]:
    """Return age in years from an ISO 'YYYY-MM-DD' string, or None if invalid."""
    if not birthdate:
        return None
    try:
        b = date.fromisoformat(birthdate.strip()[:10])
    except Exception:
        return None
    today = datetime.now(ZoneInfo("Europe/Madrid")).date()
    return today.year - b.year - ((today.month, today.day) < (b.month, b.day))


def is_adult(birthdate: str) -> bool:
    age = compute_age(birthdate)
    return age is not None and age >= 18


# ---------------------------------------------------------------------------
# Phone normalisation (for contact matching) — privacy-first: we only ever
# store a one-way hash, never the raw number.
# ---------------------------------------------------------------------------
def normalize_phone(raw: str) -> Optional[str]:
    """Normalise to the Spanish 9-digit national number for matching.
    Strips spaces/symbols and a leading +34/0034/34 country code."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", str(raw))
    if not digits:
        return None
    if digits.startswith("0034"):
        digits = digits[4:]
    elif digits.startswith("34") and len(digits) > 9:
        digits = digits[2:]
    # Keep the last 9 digits (Spanish mobile/landline length)
    if len(digits) >= 9:
        digits = digits[-9:]
    else:
        return None
    return digits


def phone_hash(raw: str) -> Optional[str]:
    norm = normalize_phone(raw)
    if not norm:
        return None
    return hashlib.sha256(("qv_phone_" + norm).encode("utf-8")).hexdigest()


ATTENDANCE_PRIVACY_VALUES = ("todos", "amigos", "nadie")
# Who can see YOUR "El Momento" captures. "amigos" (default) = only friends;
# "publico" = anyone (feeds the Descubrir section so newcomers/tourists see them).
MOMENT_PRIVACY_VALUES = ("amigos", "publico")


def new_session_token() -> str:
    return secrets.token_urlsafe(48)


def set_session_cookie(response: Response, token: str):
    response.set_cookie(
        key="session_token", value=token, httponly=True, secure=True,
        samesite="none", max_age=SESSION_DAYS * 24 * 3600, path="/",
    )


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class RegisterInput(BaseModel):
    email: EmailStr
    password: str
    name: str
    username: str
    city: str = "Palma de Mallorca"
    birthdate: Optional[str] = None   # YYYY-MM-DD — required, must be 18+
    phone: Optional[str] = None       # optional, stored only as a one-way hash
    source: Optional[str] = None      # marketing attribution (e.g. "ig", "tt")


class LoginInput(BaseModel):
    email: EmailStr
    password: str


class GoogleSessionInput(BaseModel):
    session_id: str


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    city: Optional[str] = None
    picture: Optional[str] = None
    username: Optional[str] = None
    birthdate: Optional[str] = None
    phone: Optional[str] = None
    attendance_privacy: Optional[str] = None   # "todos" | "amigos" | "nadie"
    moment_privacy: Optional[str] = None       # "amigos" | "publico"


class BlockInput(BaseModel):
    user_id: str


class ReportInput(BaseModel):
    target_type: str          # "user" | "moment" | "album_photo" | "message" | "event"
    target_id: str
    reason: str = ""
    note: str = ""


class MatchContactsInput(BaseModel):
    phones: List[str] = Field(default_factory=list)


class FriendActionInput(BaseModel):
    user_id: str


class FriendRespondInput(BaseModel):
    request_id: str
    accept: bool


class PriceTier(BaseModel):
    name: str = ""              # "1a fase", "Early bird", "General"…
    price: float = 0.0          # in EUR
    sold_out: bool = False


class EventInput(BaseModel):
    name: str
    venue: str
    address: str = ""
    date: str            # YYYY-MM-DD
    time: str = ""       # HH:MM
    image_url: str = ""
    genre: str = ""
    city: str = "Palma de Mallorca"
    has_commission: bool = False
    commission_url: str = ""
    more_info_url: str = ""
    # Pricing
    price_tiers: List[PriceTier] = Field(default_factory=list)
    sale_state: str = "no_a_la_venta"   # no_a_la_venta | a_la_venta | pocas_entradas | agotado
    currency: str = "EUR"


class AdminEventEditInput(BaseModel):
    """Partial edit from the admin event panel (pencil button). All fields
    optional — only provided ones are changed. Non-link fields are NOT locked
    (the scraper may refresh them on its next run, per the owner's choice); only
    the buy-link override is sticky and always wins."""
    name: Optional[str] = None
    venue: Optional[str] = None
    address: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None
    image_url: Optional[str] = None
    genre: Optional[str] = None
    city: Optional[str] = None
    sale_state: Optional[str] = None
    price_tiers: Optional[List[PriceTier]] = None
    # Manual buy-link override (sticky). When set it ALWAYS wins over scraper +
    # affiliate logic and the scraper never overwrites it. Send clear_link_override
    # (or an empty string) to remove it and go back to the automatic link.
    link_override: Optional[str] = None
    clear_link_override: bool = False


class EventPricingInput(BaseModel):
    price_tiers: List[PriceTier] = Field(default_factory=list)
    sale_state: str
    # Optional flag: if True, don't send push notifications for these changes
    # (useful when admin is bulk-updating without wanting to spam users).
    silent: bool = False


class InterestInput(BaseModel):
    status: str          # "voy" | "me_interesa" | "none"


class UsernameInput(BaseModel):
    username: str


class PushSubscriptionInput(BaseModel):
    endpoint: str
    keys: dict
    expirationTime: Optional[int] = None


class ReactionInput(BaseModel):
    content: str


class MessageInput(BaseModel):
    text: str


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def public_user(u: dict) -> dict:
    return {
        "user_id": u["user_id"],
        "email": u.get("email"),
        "name": u.get("name"),
        "username": u.get("username"),
        "picture": u.get("picture"),
        "city": u.get("city"),
        "role": u.get("role", "user"),
        "auth_provider": u.get("auth_provider"),
        "attendance_privacy": u.get("attendance_privacy", "amigos"),
        "moment_privacy": u.get("moment_privacy", "amigos"),
        "city_change_alerts": bool(u.get("city_change_alerts", False)),
        "has_phone": bool(u.get("phone_hash")),
        "needs_birthdate": not bool(u.get("birthdate")),
    }


def display_name(u) -> str:
    """Public display name shown to OTHER users: only the @username, never the
    real personal name. Self still sees their real name via public_user()."""
    if not u:
        return "Usuario"
    un = u.get("username")
    return f"@{un}" if un else (u.get("name") or "Usuario")


def public_other_user(u: dict) -> dict:
    """Serialize a user as seen by SOMEONE ELSE: the @username replaces the real
    name and the email is stripped. Never leaks a real personal name/email to
    anyone but the account owner."""
    pu = public_user(u)
    pu["name"] = display_name(u)
    pu["email"] = None
    return pu


async def get_token_from_request(request: Request) -> Optional[str]:
    token = request.cookies.get("session_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    return token


async def get_current_user(request: Request) -> dict:
    token = await get_token_from_request(request)
    if not token:
        raise HTTPException(status_code=401, detail="No autenticado")
    session = await db.sessions.find_one({"session_token": token}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=401, detail="Sesión inválida")
    expires_at = session["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Sesión expirada")
    user = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    return user


async def require_admin(request: Request) -> dict:
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Acceso solo para administrador")
    return user


# Default city served to anonymous (guest) visitors browsing without an account.
GUEST_CITY = "Palma de Mallorca"


async def get_optional_user(request: Request) -> dict:
    """Like get_current_user but NEVER raises.

    When a valid session exists it returns the real user. Otherwise it returns a
    lightweight *guest* pseudo-user (``user_id`` is ``None``) so read-only
    endpoints can serve public content to visitors who haven't registered yet.
    Because ``user_id`` is ``None``, every social lookup (friends, interests,
    tickets, follows) naturally comes back empty — no personal data leaks and no
    code path needs special-casing."""
    try:
        return await get_current_user(request)
    except HTTPException:
        return {"user_id": None, "city": GUEST_CITY, "role": None, "guest": True}


async def create_session(user_id: str, token: Optional[str] = None) -> str:
    token = token or new_session_token()
    await db.sessions.insert_one({
        "session_token": token,
        "user_id": user_id,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return token


# ---------------------------------------------------------------------------
# Cities + social share (WhatsApp Open Graph preview)
# ---------------------------------------------------------------------------
@api_router.get("/cities")
async def list_cities(response: Response):
    """Public list of supported cities for the registration / settings selector."""
    # Static content — let the browser/CDN cache it for an hour to skip round-trips.
    response.headers["Cache-Control"] = "public, max-age=3600"
    return {"cities": SUPPORTED_CITIES, "pending_city": PENDING_CITY}


def _es_share_date(date_str: str) -> str:
    _dias = ["lunes", "martes", "mi\u00e9rcoles", "jueves", "viernes", "s\u00e1bado", "domingo"]
    _meses = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    try:
        d = date.fromisoformat(date_str)
        return f"{_dias[d.weekday()]} {d.day} {_meses[d.month - 1]}"
    except Exception:
        return date_str or ""


@api_router.get("/share/event/{event_id}")
async def share_event(event_id: str, request: Request):
    """HTML page with Open Graph tags so WhatsApp/Telegram/social show a rich,
    compact card (the specific party poster + title + venue/date). Humans are
    redirected to the SPA event page; crawlers read the meta tags."""
    import html as _html
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    base = f"{proto}://{host}"
    # The page itself is served by the BACKEND, but humans must land on the
    # FRONTEND app. In a split deploy (Vercel frontend + Render backend) set
    # FRONTEND_URL to the Vercel domain; otherwise fall back to the request
    # host (works when both share one domain, e.g. the preview/ingress).
    front = (os.environ.get("FRONTEND_URL") or "").strip().rstrip("/") or base
    app_url = f"{front}/event/{event_id}"

    if not ev:
        return StarletteResponse(
            content=f"<!doctype html><meta http-equiv=refresh content='0;url={front}/feed'>",
            media_type="text/html",
        )

    name = ev.get("name") or "Fiesta"
    venue = ev.get("venue") or ""
    parts = [p for p in [venue, _es_share_date(ev.get("date", ""))] if p]
    # price / sale-state line
    tiers = ev.get("price_tiers") or []
    prices = [t.get("price") for t in tiers if isinstance(t, dict) and t.get("price")]
    state = ev.get("sale_state")
    if state == "agotado":
        parts.append("Agotado")
    elif prices:
        parts.append(f"desde {int(min(prices))}\u20ac")
    desc = " \u00b7 ".join(parts)

    img = ev.get("image_url") or ""
    if img and not img.startswith("http"):
        img = base + img

    e = _html.escape
    title = e(f"{name} \u2013 \u00bfQui\u00e9n va?")
    og_title = e(name)
    og_desc = e(desc)
    og_img = e(img)
    html_out = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta property="og:type" content="website">
<meta property="og:site_name" content="\u00bfQui\u00e9n va?">
<meta property="og:title" content="{og_title}">
<meta property="og:description" content="{og_desc}">
<meta property="og:url" content="{e(app_url)}">
{f'<meta property="og:image" content="{og_img}"><meta property="og:image:width" content="1080"><meta property="og:image:height" content="1080">' if og_img else ''}
<meta name="twitter:card" content="{'summary_large_image' if og_img else 'summary'}">
<meta name="twitter:title" content="{og_title}">
<meta name="twitter:description" content="{og_desc}">
{f'<meta name="twitter:image" content="{og_img}">' if og_img else ''}
<meta http-equiv="refresh" content="0; url={e(app_url)}">
<script>window.location.replace({json.dumps(app_url)});</script>
</head>
<body style="background:#0a0a0b;color:#fff;font-family:system-ui,sans-serif;text-align:center;padding:40px">
<p>Abriendo {og_title} en \u00bfQui\u00e9n va?\u2026</p>
<p><a style="color:#00f0ff" href="{e(app_url)}">Toca aqu\u00ed si no se abre</a></p>
</body>
</html>"""
    return StarletteResponse(content=html_out, media_type="text/html; charset=utf-8",
                             headers={"Cache-Control": "public, max-age=600"})


# ---------------------------------------------------------------------------
# SEO: public, server-rendered city pages + sitemap (indexable by Google) and
# Instagram-Story image generator. These are the only public HTML/image routes;
# everything else is the SPA behind auth.
# ---------------------------------------------------------------------------
_ASSETS_FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts")


def _slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


# slug -> canonical app-city id (built from SUPPORTED_CITIES)
_CITY_SLUGS = {_slugify(c["id"]): c["id"] for c in SUPPORTED_CITIES}
_CITY_SLUGS.update({"palma": "Palma de Mallorca", "mallorca": "Palma de Mallorca",
                    "puerto-banus": "Marbella", "eivissa": "Ibiza",
                    "marbella": "Marbella"})

# Canonical SHORT SEO slug per city. Used in sitemap, <link rel=canonical>,
# hreflang and internal links so there is ONE canonical URL per city (the app
# and older links use these short slugs). Long forms (palma-de-mallorca,
# marbella-puerto-banus, eivissa…) still resolve but canonicalize to these.
CITY_SEO_SLUG = {
    "Palma de Mallorca": "palma",
    "Ibiza": "ibiza",
    "Madrid": "madrid",
    "Barcelona": "barcelona",
    "Marbella": "marbella",
}


def _city_slug(city_id: str) -> str:
    return CITY_SEO_SLUG.get(city_id) or _slugify(city_id)


def _price_line(ev: dict) -> str:
    tiers = ev.get("price_tiers") or []
    prices = [t.get("price") for t in tiers if isinstance(t, dict) and t.get("price")]
    if ev.get("sale_state") == "agotado":
        return "Agotado"
    if prices:
        return f"desde {int(min(prices))}\u20ac"
    return ""


# --- Freshness signal: current month/year injected into SEO titles/descriptions
# (Google favours pages that look up-to-date, and it lifts CTR for "esta semana"
# style queries). Localised month names for ES / EN / DE.
_MONTHS = {
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
           "agosto", "septiembre", "octubre", "noviembre", "diciembre"],
    "en": ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"],
    "de": ["Januar", "Februar", "M\u00e4rz", "April", "Mai", "Juni", "Juli",
           "August", "September", "Oktober", "November", "Dezember"],
}
_UPDATED_WORD = {"es": "Actualizado", "en": "Updated", "de": "Aktualisiert"}


def _seo_month(lang: str) -> str:
    now = datetime.now(ZoneInfo("Europe/Madrid"))
    months = _MONTHS.get(lang, _MONTHS["es"])
    m = months[now.month - 1]
    return f"{m[:1].upper()}{m[1:]} {now.year}"


def _title_with_month(title: str, lang: str) -> str:
    """Insert 'Month Year' right before the ' | ¿Quién va?' brand suffix."""
    fr = _seo_month(lang)
    if " | " in title:
        head, sep, tail = title.partition(" | ")
        return f"{head} \u2014 {fr}{sep}{tail}"
    return f"{title} \u2014 {fr}"


def _event_seo_title(ev: dict, lang: str) -> str:
    """Compact, truncation-safe event <title> (~55-60 chars, front-loaded):
    '{name} — {venue}[, {city}] · {day mon} | ¿Quién va?'

    Why this beats the old '{name} — {venue}, {city} | Entradas y horario |
    ¿Quién va?':
    - The old title ran ~80-95 chars, so on mobile (where 995 of our 1.3k
      impressions come from) Google truncated everything after the venue —
      'Entradas y horario' and the brand never rendered.
    - It also produced redundancy like 'Fitz Marbella, Marbella' because the
      venue name already carries the city.
    - The specific day + short month is a far stronger CTR signal for event
      queries ('gims marbella', 'aya nakamura fitz') than a generic keyword
      that got cut off anyway. The 'Entradas'/ticket keywords already live in
      the meta description and page body."""
    name = (ev.get("name") or "Fiesta").strip()
    venue = (ev.get("venue") or "").strip()
    city = (ev.get("city") or "").strip()
    place = venue
    if city and city.lower() not in venue.lower():
        place = f"{venue}, {city}" if venue else city
    when = ""
    try:
        d = date.fromisoformat(ev.get("date", ""))
        mon = _MON[lang][d.month - 1]
        when = f"{d.day}. {mon}" if lang == "de" else f"{d.day} {mon}"
    except Exception:
        when = ""
    head = f"{name} \u2014 {place}" if place else name
    if when:
        head = f"{head} \u00b7 {when}"
    return f"{head} | \u00bfQui\u00e9n va?"


# Generic, recurring "placeholder" party names that carry no real lineup yet
# (e.g. "Jueves Fitz", "Sábado Amok", "Noche de fiesta"). These get a real
# artist/party name + poster later; until then their SEO page is thin.
_GENERIC_NAME_RE = re.compile(
    r"^(jueves|viernes|s[\u00e1a]bado|domingo|lunes|martes|mi[\u00e9e]rcoles|"
    r"noche|noches|fiesta|fiestas|party|parties|weekend|finde|fin de semana|"
    r"club\s?night|especial|open|apertura|clausura|closing|opening)\b",
    re.IGNORECASE,
)


def _is_thin_event(ev: dict) -> bool:
    """A 'thin/placeholder' event has no indexable content yet: no real poster
    AND no price/ticket, or a generic recurring name with no poster (the classic
    "Jueves Fitz" that later becomes a top artist). We keep these OUT of the index
    and the sitemap until they get a real poster / price / specific name, which is
    the single biggest fix for Search Console's thousands of 'Discovered - currently
    not indexed' URLs. It never noindexes an event that already has real content."""
    img = str(ev.get("image_url") or "")
    has_poster = img.startswith("http")
    tiers = ev.get("price_tiers") or []
    has_price = bool(tiers) or bool(ev.get("commission_url")) or bool(ev.get("has_commission"))
    if has_poster or has_price:
        # Has real, indexable content -> never thin.
        # (a generic name is fine once there is a poster/price to show)
        name = (ev.get("name") or "").strip()
        if has_poster:
            return False
        # has_price but no poster: only thin if the name is also totally generic
        return bool(_GENERIC_NAME_RE.match(name)) and len(name) < 12
    # No poster AND no price -> nothing to index.
    return True



def _canonicalize_base(base: str) -> str:
    """Force the canonical www host. In production the apex `quienva.me` issues a
    308 redirect to `www.quienva.me`, so any canonical / sitemap / hreflang / og
    URL built on the apex would be a REDIRECT — which is exactly why Google
    reported 'Error de redirección' and refused to index the city pages. We
    normalise the bare apex to www so every emitted URL resolves 200 directly."""
    try:
        base = re.sub(r"^(https?://)quienva\.me\b", r"\1www.quienva.me", base)
    except Exception:
        pass
    return base


def _frontend_base(request: Request) -> str:
    override = (os.environ.get("SEO_CANONICAL_BASE") or "").strip().rstrip("/")
    if override:
        return _canonicalize_base(override)
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    base = f"{proto}://{host}"
    base = (os.environ.get("FRONTEND_URL") or "").strip().rstrip("/") or base
    return _canonicalize_base(base)


async def _upcoming_for_city(city_id: str, limit: int = 60) -> list:
    today = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
    cur = db.events.find(
        {"city": city_query_value(city_id), "date": {"$gte": today}},
        {"_id": 0, "id": 1, "name": 1, "venue": 1, "date": 1, "time": 1, "city": 1,
         "genre": 1, "address": 1, "currency": 1, "last_scraped_at": 1, "created_at": 1,
         "image_url": 1, "price_tiers": 1, "sale_state": 1, "commission_url": 1, "has_commission": 1},
    ).sort("date", 1).limit(limit)
    return [e async for e in cur]


async def _city_venues(city_id: str, limit: int = 18) -> list:
    """Nightclubs of a city (from upcoming events) with a cover image + count,
    for the 'Discotecas' grid on the city landing page."""
    today = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
    pipeline = [
        {"$match": {"city": city_query_value(city_id), "date": {"$gte": today},
                    "venue": {"$nin": ["", None]}}},
        {"$group": {"_id": "$venue", "count": {"$sum": 1}, "image": {"$max": "$image_url"}}},
        {"$sort": {"count": -1}},
        {"$limit": limit},
    ]
    out = []
    async for r in db.events.aggregate(pipeline):
        v = r.get("_id") or ""
        if not v:
            continue
        img = r.get("image") or ""
        out.append({"venue": v, "slug": _slugify(v), "count": r.get("count", 0),
                    "image": img if str(img).startswith("http") else ""})
    return out


# ---------------------------------------------------------------------------
# Multilingual SEO (ES / EN / DE) — server-rendered, crawlable landing pages.
# Served on the main domain via Vercel rewrites:
#   /fiestas/:city        -> /api/ciudad/:city        (es)
#   /en/parties/:city     -> /api/en/city/:city       (en)
#   /de/partys/:city      -> /api/de/city/:city        (de)
#   /fiesta/:id/:slug     -> /api/fiesta/:id           (es)
#   /en/party/:id/:slug   -> /api/en/party/:id         (en)
#   /de/party/:id/:slug   -> /api/de/party/:id          (de)
# These pages are only hit by crawlers / search visitors and are cached, so
# they do NOT affect the speed of the React app itself.
# ---------------------------------------------------------------------------
SEO_LANGS = ("es", "en", "de")

_SEO_CSS = """
:root{color-scheme:dark;--pink:#ff0055;--cyan:#00f0ff;--bg:#050508;--card:#0e0e12;--line:#242029;--muted:#a1a1aa}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:#fff;font-family:'Outfit',system-ui,-apple-system,Segoe UI,Roboto,sans-serif;line-height:1.5;-webkit-font-smoothing:antialiased}
a{color:inherit}
.bgfx{position:fixed;inset:0;z-index:-1;background:
  radial-gradient(900px 500px at 15% -120px,rgba(255,0,85,.20),transparent 60%),
  radial-gradient(900px 520px at 100% 0,rgba(0,240,255,.16),transparent 55%),
  #0a0a0c}
.topbar{position:sticky;top:0;z-index:20;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 16px;background:rgba(10,10,12,.72);backdrop-filter:blur(14px);border-bottom:1px solid rgba(255,255,255,.06)}
.brand{font-family:'Unbounded',system-ui,sans-serif;font-weight:900;font-size:19px;letter-spacing:-.02em;text-decoration:none;color:#fff}
.brand span{color:var(--pink)}
.open{display:inline-flex;align-items:center;gap:6px;background:#fff;color:#0a0a0c;font-weight:800;font-size:13px;padding:9px 15px;border-radius:999px;text-decoration:none;transition:transform .15s ease}
.open:active{transform:scale(.95)}
.wrap{max-width:1000px;margin:0 auto;padding:26px 16px 96px}
.bc{font-size:12px;color:#71717a;margin-bottom:14px}
.bc a{color:#a1a1aa;text-decoration:none}
.bc a:hover{color:#fff}
.hero-sec{position:relative;margin-bottom:26px}
.kicker{display:inline-block;font-size:12px;font-weight:800;letter-spacing:.18em;text-transform:uppercase;color:var(--cyan);margin-bottom:10px}
h1{font-family:'Unbounded',system-ui,sans-serif;font-weight:900;font-size:clamp(30px,6vw,48px);line-height:1.05;margin:0 0 12px;letter-spacing:-.02em}
h1 .dot{color:var(--pink)}
p.sub{color:#c9c9d1;margin:0 0 18px;font-size:16px;max-width:640px}
.stats{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 20px}
.stat{display:inline-flex;align-items:center;gap:7px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.09);border-radius:999px;padding:8px 13px;font-size:13px;font-weight:600;color:#e6e6ea}
.stat b{color:var(--cyan);font-weight:800}
.cta{display:inline-flex;align-items:center;justify-content:center;gap:8px;background:linear-gradient(90deg,var(--pink),#ff3d7f);color:#fff;font-family:'Unbounded',system-ui,sans-serif;font-weight:800;font-size:15px;padding:14px 26px;border-radius:999px;text-decoration:none;box-shadow:0 12px 34px -12px rgba(255,0,85,.7);transition:transform .15s ease,box-shadow .15s ease}
.cta:hover{transform:translateY(-2px);box-shadow:0 16px 40px -12px rgba(255,0,85,.85)}
.cta.ghost{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.15);color:#fff;box-shadow:none}
.ctarow{display:flex;flex-wrap:wrap;gap:10px;margin:22px 0}
.intro{margin:2px 0 26px;color:#c9c9d1;font-size:15.5px;line-height:1.75;max-width:780px}
.intro p{margin:0}
.sectitle{font-family:'Unbounded',system-ui,sans-serif;font-weight:800;font-size:20px;margin:38px 0 16px;letter-spacing:-.01em}
.nav-tf{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 22px}
.nav-tf a,.nav-tf b{font-size:13px;font-weight:700;padding:8px 14px;border-radius:999px;text-decoration:none}
.nav-tf a{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.09);color:#c9c9d1}
.nav-tf b{background:var(--cyan);color:#04121a}
.finder{position:relative;margin:2px 0 20px;max-width:520px}
.finder input{width:100%;padding:15px 16px 15px 46px;border-radius:16px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);color:#fff;font-size:15px;font-family:inherit;outline:none;transition:border-color .2s,box-shadow .2s}
.finder input:focus{border-color:var(--cyan);box-shadow:0 0 0 3px rgba(0,240,255,.16)}
.finder input::placeholder{color:#8b8b96}
.finder .fic{position:absolute;left:16px;top:50%;transform:translateY(-50%);opacity:.55;font-size:16px}
.sech{display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin:32px 0 14px}
.sech h2{font-family:'Unbounded',system-ui,sans-serif;font-weight:700;font-size:20px;margin:0}
.sech span{color:var(--muted);font-size:13px}
.venues{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px}
.vcard{display:flex;align-items:center;gap:11px;background:var(--card);border:1px solid var(--line);border-radius:16px;padding:10px;text-decoration:none;color:#fff;transition:transform .18s ease,border-color .18s ease}
.vcard:hover{transform:translateY(-3px);border-color:rgba(255,0,85,.5)}
.vthumb{width:46px;height:46px;border-radius:12px;flex:0 0 auto;background:linear-gradient(135deg,#2a0f42,#0d2b34);display:flex;align-items:center;justify-content:center;font-family:'Unbounded',system-ui,sans-serif;font-weight:700;font-size:17px;color:#fff;overflow:hidden}
.vthumb img{width:100%;height:100%;object-fit:cover}
.vmeta{min-width:0}
.vmeta b{display:block;font-size:13.5px;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.vmeta small{color:var(--muted);font-size:12px}
.nores{grid-column:1/-1;color:var(--muted);padding:22px;text-align:center;display:none}
.grid{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:16px}
.card{position:relative;display:flex;flex-direction:column;background:var(--card);border:1px solid var(--line);border-radius:20px;overflow:hidden;text-decoration:none;color:#fff;transition:transform .2s ease,border-color .2s ease,box-shadow .2s ease}
.card:hover{transform:translateY(-4px);border-color:rgba(0,240,255,.5);box-shadow:0 18px 40px -18px rgba(0,240,255,.45)}
.poster{position:relative;width:100%;aspect-ratio:3/4;background:#0f0d14;overflow:hidden}
.poster img{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;display:block;z-index:2;transition:transform .45s cubic-bezier(.2,.7,.2,1)}
.card:hover .poster img{transform:scale(1.045)}
.poster .blurbg{position:absolute;inset:0;background-size:cover;background-position:center;filter:blur(22px) brightness(.5) saturate(1.25);transform:scale(1.35);z-index:1}
.poster .ph{position:absolute;inset:0;z-index:0;width:100%;height:100%;background:linear-gradient(150deg,#2a0f42 0%,#48173a 45%,#0d2b34 100%);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;padding:16px 14px}
.poster .ph:before{content:"";position:absolute;top:-30%;left:-20%;width:70%;height:70%;background:radial-gradient(circle,rgba(255,0,85,.5),transparent 65%);filter:blur(22px)}
.phn{font-family:'Unbounded',system-ui,sans-serif;font-weight:700;font-size:15px;color:#fff;text-align:center;line-height:1.18;text-shadow:0 2px 14px rgba(0,0,0,.55);position:relative;z-index:1;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.phv{font-size:12px;color:rgba(255,255,255,.72);text-align:center;position:relative;z-index:1}
.phb{position:absolute;top:10px;left:11px;font-family:'Unbounded',system-ui,sans-serif;font-weight:700;font-size:10px;letter-spacing:.2px;color:rgba(255,255,255,.85);z-index:1}
.poster:after{content:"";position:absolute;inset:0;z-index:3;background:linear-gradient(180deg,transparent 55%,rgba(10,10,12,.92) 100%);pointer-events:none}
.badges{position:absolute;left:9px;bottom:9px;right:9px;display:flex;gap:6px;flex-wrap:wrap;z-index:4}
.sb{font-size:11px;font-weight:800;padding:5px 10px;border-radius:999px;backdrop-filter:blur(6px);white-space:nowrap}
.sb-on{background:rgba(16,185,129,.32);color:#a7f3d0}
.sb-few{background:rgba(249,115,22,.36);color:#fed7aa}
.sb-out{background:rgba(255,255,255,.14);color:#c9c9d1}
.sb-list{background:rgba(139,92,246,.34);color:#ddd6fe}
.sb-soon{background:rgba(255,255,255,.16);color:#d4d4d8}
.pp{font-size:11px;font-weight:900;padding:5px 10px;border-radius:999px;background:var(--cyan);color:#04121a}
.body{padding:12px 13px 14px;display:flex;flex-direction:column;gap:4px}
.n{font-family:'Unbounded',system-ui,sans-serif;font-weight:700;font-size:14.5px;line-height:1.2;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.m{color:var(--muted);font-size:12.5px}
.empty{grid-column:1/-1;color:var(--muted);padding:30px;text-align:center;background:var(--card);border:1px solid var(--line);border-radius:20px}
.benes{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:16px 0 8px}
.bene{background:var(--card);border:1px solid var(--line);border-radius:20px;padding:18px}
.bene .ic{width:44px;height:44px;border-radius:13px;display:flex;align-items:center;justify-content:center;margin-bottom:13px;background:rgba(255,0,85,.14);color:var(--pink);box-shadow:inset 0 1px 0 rgba(255,255,255,.08)}
.bene:nth-child(2) .ic{background:rgba(0,240,255,.14);color:var(--cyan)}
.bene:nth-child(3) .ic{background:rgba(139,92,246,.16);color:#b98cff}
.bene h3{font-family:'Unbounded',system-ui,sans-serif;font-weight:700;font-size:15px;margin:0 0 6px}
.bene p{color:var(--muted);font-size:13.5px;margin:0}
.joinband{margin-top:22px;background:linear-gradient(120deg,rgba(255,0,85,.16),rgba(0,240,255,.12));border:1px solid rgba(255,255,255,.1);border-radius:24px;padding:26px 22px;text-align:center}
.joinband h2{font-family:'Unbounded',system-ui,sans-serif;font-weight:800;font-size:22px;margin:0 0 8px}
.joinband p{color:#d4d4d8;margin:0 0 18px}
.hero{width:100%;max-height:420px;object-fit:cover;border-radius:22px;margin:6px 0 20px;border:1px solid var(--line)}
.ehero{position:relative;border-radius:24px;overflow:hidden;margin:8px 0 24px;border:1px solid var(--line);min-height:360px;display:flex;align-items:center;justify-content:center;padding:32px 20px}
.ehero-bg{position:absolute;inset:0;background-size:cover;background-position:center;filter:blur(40px) brightness(.42) saturate(1.35);transform:scale(1.35);z-index:0}
.ehero:after{content:"";position:absolute;inset:0;z-index:1;background:radial-gradient(140% 100% at 50% 0,transparent 40%,rgba(10,10,12,.72))}
.ehero-poster{position:relative;z-index:2;max-width:340px;width:100%;animation:eheroIn .6s cubic-bezier(.2,.7,.2,1) both}
.ehero-poster img{width:100%;height:auto;max-height:480px;object-fit:contain;border-radius:18px;border:1px solid rgba(255,255,255,.16);box-shadow:0 30px 70px -24px rgba(0,0,0,.85),0 0 0 1px rgba(0,240,255,.08)}
@keyframes eheroIn{from{opacity:0;transform:translateY(14px) scale(.97)}to{opacity:1;transform:none}}
.meta{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin:20px 0}
.meta > div{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:14px 16px}
.meta b{color:var(--cyan);font-size:11px;text-transform:uppercase;letter-spacing:.06em;display:block;margin-bottom:4px}
.stickycta{position:fixed;left:0;right:0;bottom:0;z-index:30;display:flex;align-items:center;gap:12px;padding:12px 16px calc(12px + env(safe-area-inset-bottom));background:rgba(12,10,16,.9);backdrop-filter:blur(14px);border-top:1px solid rgba(255,255,255,.08)}
.stickycta .pr{flex:0 0 auto;line-height:1.1}
.stickycta .pr small{display:block;color:var(--muted);font-size:11px}
.stickycta .pr b{font-family:'Unbounded',system-ui,sans-serif;font-size:17px}
.stickycta .cta{flex:1;padding:13px 18px}
/* App download promo (SEO) — very visual, drives App Store installs */
.appband{position:relative;overflow:hidden;margin:14px 0 26px;display:flex;align-items:center;gap:16px;background:linear-gradient(120deg,rgba(0,0,0,.55),rgba(255,0,85,.20) 60%,rgba(0,240,255,.16));border:1px solid rgba(255,255,255,.14);border-radius:24px;padding:20px 22px;box-shadow:0 18px 50px -20px rgba(255,0,85,.5)}
.appband:before{content:"";position:absolute;top:-40%;right:-10%;width:220px;height:220px;background:radial-gradient(circle,rgba(0,240,255,.35),transparent 65%);filter:blur(8px);pointer-events:none}
.appband .ico{flex:0 0 auto;width:66px;height:66px;border-radius:16px;background:linear-gradient(150deg,#141216,#000);border:1px solid rgba(255,255,255,.16);display:flex;align-items:center;justify-content:center;font-family:'Unbounded',system-ui,sans-serif;font-weight:900;font-size:15px;line-height:1;box-shadow:0 10px 26px -10px rgba(0,0,0,.8)}
.appband .ico b{color:#fff}.appband .ico i{color:var(--pink);font-style:normal}
.appband .tx{position:relative;z-index:1;flex:1;text-align:left;min-width:0}
.appband .stars{color:#ffce31;font-size:13px;letter-spacing:2px;margin-bottom:3px}
.appband .tx b{display:block;font-family:'Unbounded',system-ui,sans-serif;font-weight:800;font-size:19px;line-height:1.15}
.appband .tx small{display:block;color:#e5e5ea;font-size:13px;margin:3px 0 12px}
.appstore-badge{transition:transform .15s ease,box-shadow .15s ease}
.appstore-badge:hover{transform:translateY(-2px);box-shadow:0 14px 30px -10px rgba(0,0,0,.7)}
.appstore-badge.big{padding:14px 26px !important;font-size:16px !important}
.appsticky{position:fixed;left:0;right:0;bottom:0;z-index:30;display:flex;align-items:center;gap:12px;padding:11px 16px calc(11px + env(safe-area-inset-bottom));background:rgba(12,10,16,.94);backdrop-filter:blur(16px);border-top:1px solid rgba(255,255,255,.1)}
.appsticky .ico{flex:0 0 auto;width:42px;height:42px;border-radius:11px;background:linear-gradient(150deg,#141216,#000);border:1px solid rgba(255,255,255,.16);display:flex;align-items:center;justify-content:center;font-family:'Unbounded',system-ui,sans-serif;font-weight:900;font-size:10px}
.appsticky .ico b{color:#fff}.appsticky .ico i{color:var(--pink);font-style:normal}
.appsticky .pr{flex:1;line-height:1.15;text-align:left}
.appsticky .pr b{display:block;font-family:'Unbounded',system-ui,sans-serif;font-size:15px}
.appsticky .pr small{display:block;color:var(--muted);font-size:11px}
.appsticky .appstore-badge{flex:0 0 auto;margin-top:0 !important}
@media(max-width:640px){.appband .tx b{font-size:17px}.appband{padding:16px}.appband .ico{width:56px;height:56px;font-size:13px}}
.cities{margin-top:38px;border-top:1px solid var(--line);padding-top:20px}
.cities a{color:var(--cyan);margin-right:16px;text-decoration:none;display:inline-block;margin-bottom:8px;font-weight:600}
.cities a:hover{color:#fff}
.cities b{display:block;margin-bottom:10px;color:#fff}
.langs{margin-top:28px;font-size:13px;color:#71717a}
.langs a{color:#a1a1aa;margin-right:12px;text-decoration:none}
footer{margin-top:34px;color:#71717a;font-size:13px;border-top:1px solid var(--line);padding-top:18px}
.faq{margin-top:8px}
.faq details{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:14px 16px;margin-bottom:10px}
.faq summary{font-weight:700;cursor:pointer;list-style:none}
.faq summary::-webkit-details-marker{display:none}
.faq p{color:var(--muted);margin:10px 0 0}
@media(max-width:640px){.benes{grid-template-columns:1fr}.meta{grid-template-columns:1fr}.grid{grid-template-columns:repeat(2,1fr);gap:12px}.ehero{min-height:300px;padding:22px 14px}.ehero-poster{max-width:258px}}
/* ============ premium motion & interactivity ============ */
html{scroll-behavior:smooth}
.bgfx{background:
  radial-gradient(720px 500px at 12% -140px,rgba(255,0,85,.22),transparent 60%),
  radial-gradient(760px 540px at 100% 3%,rgba(0,240,255,.16),transparent 55%),
  radial-gradient(620px 620px at 62% 122%,rgba(122,0,255,.15),transparent 60%),
  #050508;animation:bgdrift 24s ease-in-out infinite alternate}
@keyframes bgdrift{from{background-position:0 0,0 0,0 0,0 0}to{background-position:46px -34px,-46px 24px,26px -46px,0 0}}
body:before{content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;opacity:.04;mix-blend-mode:overlay;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")}
.topbar{transition:padding .25s ease,background .25s ease,box-shadow .25s ease}
.topbar.shrink{padding:8px 16px;background:rgba(5,5,8,.92);box-shadow:0 10px 30px -18px rgba(0,0,0,.9)}
.hero-sec>*{animation:fadeUp .75s cubic-bezier(.16,1,.3,1) both}
.hero-sec .kicker{animation-delay:.02s}.hero-sec h1{animation-delay:.08s}
.hero-sec p.sub{animation-delay:.16s}.hero-sec .stats{animation-delay:.24s}
.stats .stat{animation:fadeUp .6s cubic-bezier(.16,1,.3,1) both}
.stats .stat:nth-child(2){animation-delay:.30s}.stats .stat:nth-child(3){animation-delay:.36s}
.ctarow{animation:fadeUp .75s cubic-bezier(.16,1,.3,1) .30s both}
@keyframes fadeUp{from{opacity:0;transform:translateY(26px)}to{opacity:1;transform:none}}
.stat{background:rgba(255,255,255,.04);backdrop-filter:blur(10px);box-shadow:inset 0 1px 0 rgba(255,255,255,.08);transition:transform .2s ease,border-color .2s ease,background .2s ease}
.stat:hover{transform:translateY(-2px);background:rgba(255,255,255,.07);border-color:rgba(0,240,255,.4)}
.cta:not(.ghost){transition:transform .18s ease,box-shadow .25s ease}
.cta:not(.ghost):hover{transform:translateY(-2px) scale(1.015);box-shadow:0 0 28px rgba(255,0,85,.55),0 18px 44px -12px rgba(255,0,85,.85)}
.js-on .reveal{opacity:0;transform:translateY(38px);transition:opacity .7s cubic-bezier(.16,1,.3,1),transform .7s cubic-bezier(.16,1,.3,1)}
.js-on .reveal.in{opacity:1;transform:none}
.card,.vcard{box-shadow:inset 0 1px 0 rgba(255,255,255,.06)}
.glow-card{position:relative}
.glow-card:before{content:"";position:absolute;top:var(--gy,50%);left:var(--gx,50%);width:320px;height:320px;background:radial-gradient(circle,rgba(0,240,255,.20),transparent 68%);transform:translate(-50%,-50%);opacity:0;transition:opacity .3s ease;pointer-events:none;z-index:5;border-radius:50%}
.glow-card:hover:before{opacity:1}
.sectitle,.sech{animation:fadeUp .6s cubic-bezier(.16,1,.3,1) both}
.sb-on{padding-left:19px}
.sb-on:after{content:"";position:absolute;left:7px;top:50%;transform:translateY(-50%);width:6px;height:6px;border-radius:50%;background:#00f0ff;box-shadow:0 0 0 0 rgba(0,240,255,.7);animation:pulse 1.8s infinite}
.sb{position:relative}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(0,240,255,.6)}70%{box-shadow:0 0 0 8px rgba(0,240,255,0)}100%{box-shadow:0 0 0 0 rgba(0,240,255,0)}}
.meta > div{transition:transform .2s ease,border-color .2s ease}
.meta > div:hover{transform:translateY(-2px);border-color:rgba(0,240,255,.4)}
.faq details[open] p{animation:fadeUp .35s ease both}
.finder input{transition:border-color .2s,box-shadow .2s,background .2s}
.finder input:focus{background:rgba(255,255,255,.09)}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}.js-on .reveal{opacity:1;transform:none}}
"""


# Favicon / icon links injected into EVERY server-rendered SEO page <head> so
# Googlebot always finds a valid /favicon.ico (root) — required for the site
# logo/favicon to appear in Search results & the brand knowledge panel.
_ICONS_HEAD = (
    '<link rel="icon" href="/favicon.ico" sizes="any">'
    '<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png">'
    '<link rel="icon" type="image/png" sizes="96x96" href="/favicon-96x96.png">'
    '<link rel="apple-touch-icon" href="/apple-touch-icon.png">'
    '<link rel="manifest" href="/manifest.json">'
    '<meta name="theme-color" content="#050508">'
    '<script>document.documentElement.classList.add("js-on")</script>'
    '''<script>(function(){function ready(fn){if(document.readyState!="loading")fn();else document.addEventListener("DOMContentLoaded",fn);}ready(function(){var rev=document.querySelectorAll(".reveal");if("IntersectionObserver" in window && rev.length){var io=new IntersectionObserver(function(es){es.forEach(function(en){if(en.isIntersecting){en.target.classList.add("in");io.unobserve(en.target);}});},{threshold:0.12,rootMargin:"0px 0px -40px 0px"});Array.prototype.forEach.call(rev,function(el,i){el.style.transitionDelay=((i%4)*70)+"ms";io.observe(el);});}else{Array.prototype.forEach.call(rev,function(el){el.classList.add("in");});}Array.prototype.forEach.call(document.querySelectorAll(".glow-card"),function(c){c.addEventListener("mousemove",function(e){var r=c.getBoundingClientRect();c.style.setProperty("--gx",(e.clientX-r.left)+"px");c.style.setProperty("--gy",(e.clientY-r.top)+"px");});});var tb=document.querySelector(".topbar");if(tb){var os=function(){if(window.scrollY>40)tb.classList.add("shrink");else tb.classList.remove("shrink");};os();window.addEventListener("scroll",os,{passive:true});}Array.prototype.forEach.call(document.querySelectorAll(".stat b"),function(b){var t=b.textContent.trim();var n=parseInt(t.replace(/[^0-9]/g,""),10);if(!n||n>100000)return;var d=Math.min(1200,300+n*8);var s=null;function step(ts){if(!s)s=ts;var p=Math.min((ts-s)/d,1);b.textContent=Math.floor(p*n).toLocaleString("es");if(p<1)requestAnimationFrame(step);else b.textContent=t;}requestAnimationFrame(step);});});})();</script>'''
)


APP_STORE_URL = "https://apps.apple.com/es/app/qui%C3%A9n-va-fiestas-cerca/id6804396475"


def _apple_logo(size: int = 20) -> str:
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">'
            '<path d="M16.365 1.43c0 1.14-.42 2.2-1.12 3.03-.78.94-2.06 1.66-3.16 1.57-.14-1.1.42-2.28 1.09-3.02.76-.86 2.12-1.5 3.19-1.58zM20.9 17.02c-.55 1.27-.81 1.83-1.52 2.95-.99 1.56-2.39 3.5-4.12 3.51-1.54.02-1.94-1-4.03-.99-2.09.01-2.53 1.01-4.07.99-1.73-.02-3.05-1.78-4.04-3.34C1.28 16.62.99 12.02 2.68 9.6c1.02-1.46 2.62-2.31 4.13-2.31 1.54 0 2.5 1.02 3.77 1.02 1.23 0 1.98-1.02 3.76-1.02 1.34 0 2.76.73 3.78 1.99-3.32 1.82-2.78 6.56.98 7.74z"/>'
            '</svg>')


def _app_store_badge(lang: str, big: bool = False) -> str:
    """'Download on the App Store' button (Apple logo + label)."""
    label = {"es": "Desc\u00e1rgala en la App Store",
             "en": "Download on the App Store",
             "de": "Im App Store laden"}.get(lang, "Desc\u00e1rgala en la App Store")
    cls = "appstore-badge big" if big else "appstore-badge"
    return (f'<a class="{cls}" href="{APP_STORE_URL}" target="_blank" rel="noopener" '
            f'data-testid="seo-appstore-badge" '
            f'style="display:inline-flex;align-items:center;gap:9px;margin-top:14px;padding:11px 20px;'
            f'border-radius:999px;background:#000;color:#fff;border:1px solid rgba(255,255,255,.22);'
            f'font-weight:700;text-decoration:none;font-size:14px">{_apple_logo()}<span>{label}</span></a>')


def _app_icon_tile(cls: str = "ico") -> str:
    # Mini brand tile that mimics the app icon: "¿Q va?" (white + pink).
    return f'<div class="{cls}"><b>\u00bfQ</b><i>va?</i></div>'


def _app_promo_band(lang: str) -> str:
    """Big, eye-catching 'get the app' card to maximise App Store installs.
    Shown high on SEO pages."""
    txt = {
        "es": ("Descarga <b>\u00bfQui\u00e9n va?</b> gratis", "Todas las fiestas cerca de ti \u2014 en tu bolsillo"),
        "en": ("Get <b>\u00bfQui\u00e9n va?</b> free", "Every party near you \u2014 in your pocket"),
        "de": ("Hol dir <b>\u00bfQui\u00e9n va?</b> gratis", "Alle Partys in deiner N\u00e4he \u2014 in der Tasche"),
    }.get(lang, None) or ("Descarga <b>\u00bfQui\u00e9n va?</b> gratis", "Todas las fiestas cerca de ti \u2014 en tu bolsillo")
    return (f'<a class="appband" href="{APP_STORE_URL}" target="_blank" rel="noopener" '
            f'data-testid="seo-app-promo" style="text-decoration:none;color:inherit">'
            f'{_app_icon_tile()}'
            f'<div class="tx"><div class="stars">\u2605\u2605\u2605\u2605\u2605</div>'
            f'<b>{txt[0]}</b><small>{txt[1]}</small>'
            f'<span class="appstore-badge big" style="display:inline-flex;align-items:center;gap:9px;'
            f'padding:12px 22px;border-radius:999px;background:#000;color:#fff;border:1px solid rgba(255,255,255,.22);'
            f'font-weight:700;font-size:15px;margin-top:0">{_apple_logo()}<span>App Store</span></span>'
            f'</div></a>')


def _app_sticky_bar(lang: str) -> str:
    """Fixed bottom download bar (smart-banner style) for SEO city pages."""
    t = {"es": ("\u00bfQui\u00e9n va?", "Gratis en la App Store"),
         "en": ("\u00bfQui\u00e9n va?", "Free on the App Store"),
         "de": ("\u00bfQui\u00e9n va?", "Gratis im App Store")}.get(lang, ("\u00bfQui\u00e9n va?", "Gratis en la App Store"))
    get = {"es": "Obtener", "en": "Get", "de": "Laden"}.get(lang, "Obtener")
    return (f'<div class="appsticky" data-testid="seo-app-sticky">{_app_icon_tile()}'
            f'<div class="pr"><b>{t[0]}</b><small>{t[1]}</small></div>'
            f'<a class="appstore-badge" href="{APP_STORE_URL}" target="_blank" rel="noopener" '
            f'style="display:inline-flex;align-items:center;gap:8px;padding:11px 20px;border-radius:999px;'
            f'background:#000;color:#fff;border:1px solid rgba(255,255,255,.22);font-weight:700;'
            f'text-decoration:none;font-size:14px">{_apple_logo(18)}<span>{get}</span></a></div>')


def _seo_topbar(front, lang, e):
    ui = _SEO_UI.get(lang, _SEO_UI["es"])
    getapp = {"es": "Descargar app", "en": "Get the app", "de": "App laden"}.get(lang, "Descargar app")
    return (f'<header class="topbar"><a class="brand" href="{front}/">\u00bfQui\u00e9n va?<span>.</span></a>'
            f'<span style="display:inline-flex;align-items:center;gap:10px">'
            f'<a class="appstore-badge" href="{APP_STORE_URL}" target="_blank" rel="noopener" '
            f'style="display:inline-flex;align-items:center;gap:7px;padding:8px 15px;border-radius:999px;'
            f'background:#000;color:#fff;border:1px solid rgba(255,255,255,.22);font-weight:700;'
            f'text-decoration:none;font-size:13px;margin-top:0">{_apple_logo(16)}<span>{e(getapp)}</span></a>'
            f'<a class="open" href="{front}/feed">{e(ui["open"])} \u2192</a></span></header>')


def _seo_benefits(lang, e):
    ui = _SEO_UI.get(lang, _SEO_UI["es"])
    ic_users = ('<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>')
    ic_ticket = ('<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 9a3 3 0 0 1 0 6v2a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-2a3 3 0 0 1 0-6V7a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2Z"/><path d="M13 5v2"/><path d="M13 11v2"/><path d="M13 17v2"/></svg>')
    ic_zap = ('<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>')
    return (f'<h2 class="sectitle">{e(ui["why"])}</h2><div class="benes">'
            f'<div class="bene glow-card reveal"><div class="ic">{ic_users}</div><h3>{e(ui["b1t"])}</h3><p>{e(ui["b1d"])}</p></div>'
            f'<div class="bene glow-card reveal"><div class="ic">{ic_ticket}</div><h3>{e(ui["b2t"])}</h3><p>{e(ui["b2d"])}</p></div>'
            f'<div class="bene glow-card reveal"><div class="ic">{ic_zap}</div><h3>{e(ui["b3t"])}</h3><p>{e(ui["b3d"])}</p></div>'
            f'</div>')


def _seo_joinband(front, lang, e):
    ui = _SEO_UI.get(lang, _SEO_UI["es"])
    return (f'<div class="joinband"><h2>{e(ui["join_h"])}</h2><p>{e(ui["join_p"])}</p>'
            f'<a class="cta" href="{front}/feed">{e(ui["join"])}</a>'
            f'<div style="margin-top:6px">{_app_store_badge(lang)}</div></div>')


def _org_website_jsonld(front: str) -> str:
    """Site-wide brand knowledge: Organization + WebSite (with a Sitelinks
    Searchbox action) so Google can show brand info and a search box."""
    org = {
        "@context": "https://schema.org", "@type": "Organization",
        "@id": front + "/#organization",
        "name": "\u00bfQui\u00e9n va?",
        "alternateName": ["Quien va", "quienva.me", "QuienVa"],
        "url": front + "/",
        "logo": {
            "@type": "ImageObject",
            "url": front + "/icons/icon-512.png",
            "contentUrl": front + "/icons/icon-512.png",
            "width": 512, "height": 512, "caption": "\u00bfQui\u00e9n va?",
        },
        "image": front + "/icons/icon-512.png",
        "sameAs": QV_SOCIAL,
        "description": "Descubre las fiestas y discotecas de tu ciudad, mira qu\u00e9 amigos van y consigue tus entradas.",
    }
    web = {
        "@context": "https://schema.org", "@type": "WebSite",
        "@id": front + "/#website",
        "name": "\u00bfQui\u00e9n va?", "url": front + "/",
        "inLanguage": ["es", "en", "de"],
        "publisher": {"@id": front + "/#organization"},
        "potentialAction": {
            "@type": "SearchAction",
            "target": {"@type": "EntryPoint", "urlTemplate": front + "/feed?buscar={search_term_string}"},
            "query-input": "required name=search_term_string",
        },
    }
    return (f'<script type="application/ld+json">{json.dumps(org, ensure_ascii=False)}</script>'
            f'<script type="application/ld+json">{json.dumps(web, ensure_ascii=False)}</script>')


# Per-city, keyword-rich intro copy (unique per city → helps Google understand
# and rank each landing page). Club names are universal; vibe/areas localized.
_CITY_INTRO_DATA = {
    "Palma de Mallorca": {
        "clubs": "Tito's, BCM Planet Dance, Pacha Mallorca o Social Club",
        "areas": {"es": "el Paseo Mar\u00edtimo de Palma y el ambiente sin fin de Magaluf",
                  "en": "Palma's Paseo Mar\u00edtimo and the non-stop scene in Magaluf",
                  "de": "die Uferpromenade von Palma und das endlose Treiben in Magaluf"},
        "vibe": {"es": "la capital de la noche balear", "en": "the nightlife capital of the Balearics",
                 "de": "die Ausgeh-Hauptstadt der Balearen"},
    },
    "Ibiza": {
        "clubs": "Pacha, Amnesia, H\u00ef Ibiza, Ushua\u00efa, DC10 o Eden",
        "areas": {"es": "Playa d'en Bossa, San Antonio y Dalt Vila",
                  "en": "Playa d'en Bossa, San Antonio and Dalt Vila",
                  "de": "Playa d'en Bossa, San Antonio und Dalt Vila"},
        "vibe": {"es": "la capital mundial del clubbing", "en": "the clubbing capital of the world",
                 "de": "die Welthauptstadt des Clubbings"},
    },
    "Madrid": {
        "clubs": "Fabrik, Teatro Barcel\u00f3, Kapital, Joy Eslava o Sh\u00f4ko",
        "areas": {"es": "Gran V\u00eda, Malasa\u00f1a y Chueca", "en": "Gran V\u00eda, Malasa\u00f1a and Chueca",
                  "de": "Gran V\u00eda, Malasa\u00f1a und Chueca"},
        "vibe": {"es": "una de las ciudades con m\u00e1s vida nocturna de Europa",
                 "en": "one of Europe's liveliest nightlife cities",
                 "de": "eine der lebendigsten Nachtleben-St\u00e4dte Europas"},
    },
    "Barcelona": {
        "clubs": "Opium, Pacha Barcelona, Razzmatazz, Input o Bling Bling",
        "areas": {"es": "el Port Ol\u00edmpic, la Barceloneta y el Eixample",
                  "en": "Port Ol\u00edmpic, Barceloneta and the Eixample",
                  "de": "Port Ol\u00edmpic, Barceloneta und das Eixample"},
        "vibe": {"es": "el epicentro de la fiesta mediterr\u00e1nea", "en": "the epicentre of Mediterranean partying",
                 "de": "das Epizentrum der mediterranen Party"},
    },
    "Marbella": {
        "clubs": "Olivia Valere, Nikki Beach, Ocean Club o La Suite",
        "areas": {"es": "Puerto Ban\u00fas y la Milla de Oro", "en": "Puerto Ban\u00fas and the Golden Mile",
                  "de": "Puerto Ban\u00fas und die Goldene Meile"},
        "vibe": {"es": "el lujo y los beach clubs de la Costa del Sol",
                 "en": "the luxury and beach clubs of the Costa del Sol",
                 "de": "der Luxus und die Beachclubs der Costa del Sol"},
    },
}


# Unique per-city "best zones & nights" content (durable SEO for generic
# high-volume queries like "fiestas marbella", "discotecas mallorca"). ES/EN/DE.
_CITY_GUIDE_DATA = {
    "Marbella": {
        "zones": [
            {"name": "Puerto Ban\u00fas",
             "es": "La milla del lujo: discotecas como Tibu, Olivia Valere y Aqwa Mist, yates y fiesta hasta el amanecer.",
             "en": "The luxury strip: clubs like Tibu, Olivia Valere and Aqwa Mist, yachts and partying until dawn.",
             "de": "Die Luxusmeile: Clubs wie Tibu, Olivia Valere und Aqwa Mist, Yachten und Party bis zum Morgengrauen."},
            {"name": "Milla de Oro y beach clubs",
             "es": "Beach clubs de d\u00eda como Nikki Beach y Ocean Club que se convierten en fiest\u00f3n al atardecer.",
             "en": "Daytime beach clubs like Nikki Beach and Ocean Club that turn into a party at sunset.",
             "de": "Beachclubs am Tag wie Nikki Beach und Ocean Club, die bei Sonnenuntergang zur Party werden."},
            {"name": "Casco antiguo de Marbella",
             "es": "Ambiente m\u00e1s relajado de bares y terrazas para empezar la noche antes de subir a las discotecas.",
             "en": "A more relaxed scene of bars and terraces to start the night before heading to the clubs.",
             "de": "Entspanntere Bars und Terrassen, um den Abend zu beginnen, bevor es in die Clubs geht."},
        ],
        "nights": {
            "es": "En Marbella el finde arranca el jueves. Viernes y s\u00e1bado son las noches fuertes en Puerto Ban\u00fas, con las sesiones y conciertos m\u00e1s potentes, mientras que los domingos brillan los beach clubs con sus pool parties. En pleno verano hay planazo casi cada noche.",
            "en": "In Marbella the weekend kicks off on Thursday. Friday and Saturday are the big nights in Puerto Ban\u00fas, with the strongest DJ sets and concerts, while Sundays belong to the beach clubs and their pool parties. In peak summer there's something on almost every night.",
            "de": "In Marbella beginnt das Wochenende am Donnerstag. Freitag und Samstag sind die gro\u00dfen N\u00e4chte in Puerto Ban\u00fas mit den st\u00e4rksten DJ-Sets und Konzerten, w\u00e4hrend sonntags die Beachclubs mit ihren Pool-Partys gl\u00e4nzen. Im Hochsommer ist fast jede Nacht etwas los."},
    },
    "Palma de Mallorca": {
        "zones": [
            {"name": "Paseo Mar\u00edtimo de Palma",
             "es": "El coraz\u00f3n de la noche en Palma: clubs como Tito's y Social Club junto al puerto.",
             "en": "The heart of Palma's nightlife: clubs like Tito's and Social Club by the marina.",
             "de": "Das Herz von Palmas Nachtleben: Clubs wie Tito's und Social Club am Hafen."},
            {"name": "Magaluf",
             "es": "La zona m\u00e1s salvaje de la isla, con BCM Planet Dance y la fiesta joven internacional.",
             "en": "The wildest area on the island, with BCM Planet Dance and the young international party crowd.",
             "de": "Die wildeste Gegend der Insel, mit BCM Planet Dance und der jungen internationalen Partyszene."},
            {"name": "La Lonja y centro",
             "es": "Bares de copas y buen ambiente en el casco antiguo para empezar la noche.",
             "en": "Cocktail bars and a great buzz in the old town to start the night.",
             "de": "Cocktailbars und gute Stimmung in der Altstadt f\u00fcr den Auftakt."},
        ],
        "nights": {
            "es": "En Mallorca las noches fuertes son viernes y s\u00e1bado, pero en verano Magaluf no para ni un d\u00eda. El Paseo Mar\u00edtimo de Palma funciona todo el a\u00f1o y muchas discotecas programan conciertos y sesiones especiales entre semana en temporada alta.",
            "en": "In Mallorca the big nights are Friday and Saturday, but in summer Magaluf never stops. Palma's Paseo Mar\u00edtimo runs all year and many clubs schedule midweek concerts and special sessions in high season.",
            "de": "Auf Mallorca sind Freitag und Samstag die gro\u00dfen N\u00e4chte, aber im Sommer h\u00f6rt Magaluf nie auf. Palmas Paseo Mar\u00edtimo l\u00e4uft das ganze Jahr, und viele Clubs bieten in der Hochsaison auch unter der Woche Konzerte und Specials."},
    },
    "Ibiza": {
        "zones": [
            {"name": "Playa d'en Bossa",
             "es": "El epicentro del clubbing con Ushua\u00efa y H\u00ef Ibiza, donde pinchan los DJs m\u00e1s grandes del mundo.",
             "en": "The epicentre of clubbing with Ushua\u00efa and H\u00ef Ibiza, where the world's biggest DJs play.",
             "de": "Das Epizentrum des Clubbings mit Ushua\u00efa und H\u00ef Ibiza, wo die gr\u00f6\u00dften DJs der Welt auflegen."},
            {"name": "San Antonio",
             "es": "Los atardeceres m\u00e1s famosos (Caf\u00e9 del Mar) y clubs como Eden y Es Parad\u00eds.",
             "en": "The most famous sunsets (Caf\u00e9 del Mar) and clubs like Eden and Es Parad\u00eds.",
             "de": "Die ber\u00fchmtesten Sonnenunterg\u00e4nge (Caf\u00e9 del Mar) und Clubs wie Eden und Es Parad\u00eds."},
            {"name": "Ibiza ciudad y Dalt Vila",
             "es": "Glamour y noche sofisticada con Pacha y L\u00edo junto al puerto.",
             "en": "Glamour and a sophisticated night out with Pacha and L\u00edo by the port.",
             "de": "Glamour und ein anspruchsvoller Abend mit Pacha und L\u00edo am Hafen."},
        ],
        "nights": {
            "es": "En Ibiza cada club tiene su noche residente a lo largo de la semana, as\u00ed que de mayo a octubre hay fiesta grande literalmente todos los d\u00edas. Los atardeceres en San Antonio y las pool parties de d\u00eda completan el plan.",
            "en": "In Ibiza each club has its resident night across the week, so from May to October there's a huge party literally every day. Sunsets in San Antonio and daytime pool parties round out the plan.",
            "de": "Auf Ibiza hat jeder Club seine Resident-Nacht \u00fcber die Woche verteilt, sodass von Mai bis Oktober buchst\u00e4blich jeden Tag gro\u00dfe Party ist. Sonnenunterg\u00e4nge in San Antonio und Pool-Partys am Tag runden das Ganze ab."},
    },
    "Madrid": {
        "zones": [
            {"name": "Gran V\u00eda y centro",
             "es": "Discotecas ic\u00f3nicas como Teatro Barcel\u00f3, Joy Eslava y Kapital, a un paso de Sol.",
             "en": "Iconic clubs like Teatro Barcel\u00f3, Joy Eslava and Kapital, steps from Sol.",
             "de": "Legend\u00e4re Clubs wie Teatro Barcel\u00f3, Joy Eslava und Kapital, nur wenige Schritte von Sol."},
            {"name": "Malasa\u00f1a",
             "es": "El barrio alternativo, de bares con m\u00fasica indie y electr\u00f3nica hasta tarde.",
             "en": "The alternative neighbourhood, full of bars with indie and electronic music until late.",
             "de": "Das alternative Viertel voller Bars mit Indie- und Elektromusik bis sp\u00e4t."},
            {"name": "Chueca",
             "es": "El ambiente m\u00e1s diverso y las noches LGTBI+ de la ciudad.",
             "en": "The most diverse scene and the city's LGBTQ+ nights.",
             "de": "Die vielf\u00e4ltigste Szene und die LGBTQ+-N\u00e4chte der Stadt."},
        ],
        "nights": {
            "es": "En Madrid la noche empieza tarde y termina m\u00e1s tarde a\u00fan. El jueves ya se llena de universitarios, viernes y s\u00e1bado son las grandes noches, y los domingos hay afters que enlazan con la ma\u00f1ana. Fabrik, a las afueras, es la meca del techno los fines de semana.",
            "en": "In Madrid the night starts late and ends even later. Thursday fills up with students, Friday and Saturday are the big nights, and Sundays bring afterparties that run into the morning. Fabrik, on the outskirts, is the techno mecca on weekends.",
            "de": "In Madrid beginnt die Nacht sp\u00e4t und endet noch sp\u00e4ter. Donnerstags f\u00fcllt es sich mit Studenten, Freitag und Samstag sind die gro\u00dfen N\u00e4chte, und sonntags gibt es Afterpartys bis in den Morgen. Fabrik am Stadtrand ist am Wochenende das Techno-Mekka."},
    },
    "Barcelona": {
        "zones": [
            {"name": "Port Ol\u00edmpic",
             "es": "La fiesta junto al mar con Opium, Sh\u00f4ko y Pacha Barcelona.",
             "en": "Partying by the sea with Opium, Sh\u00f4ko and Pacha Barcelona.",
             "de": "Party am Meer mit Opium, Sh\u00f4ko und Pacha Barcelona."},
            {"name": "Poblenou y Raval",
             "es": "Salas de referencia como Razzmatazz y Apolo para conciertos y electr\u00f3nica.",
             "en": "Landmark venues like Razzmatazz and Apolo for concerts and electronic music.",
             "de": "Legend\u00e4re Locations wie Razzmatazz und Apolo f\u00fcr Konzerte und Elektro."},
            {"name": "Eixample",
             "es": "C\u00f3cteles y locales con estilo para calentar antes de salir.",
             "en": "Cocktails and stylish spots to warm up before going out.",
             "de": "Cocktails und stilvolle Lokale zum Aufw\u00e4rmen vor dem Ausgehen."},
        ],
        "nights": {
            "es": "En Barcelona viernes y s\u00e1bado son las noches fuertes, con las salas del Port Ol\u00edmpic a pleno rendimiento hasta el amanecer. En verano los beach clubs y las terrazas amplían la fiesta casi cada d\u00eda, y siempre hay conciertos entre semana en Razzmatazz o Apolo.",
            "en": "In Barcelona Friday and Saturday are the big nights, with the Port Ol\u00edmpic venues in full swing until dawn. In summer the beach clubs and rooftops stretch the party across almost every day, and there are always midweek concerts at Razzmatazz or Apolo.",
            "de": "In Barcelona sind Freitag und Samstag die gro\u00dfen N\u00e4chte, wenn die Locations am Port Ol\u00edmpic bis zum Morgengrauen laufen. Im Sommer verl\u00e4ngern Beachclubs und Dachterrassen die Party auf fast jeden Tag, und unter der Woche gibt es immer Konzerte im Razzmatazz oder Apolo."},
    },
}


def _city_guide_content(city_id, label, lang, e):
    """Unique 'best zones + which night to go out' section per city. Durable,
    keyword-rich content that helps city hubs rank for generic queries."""
    d = _CITY_GUIDE_DATA.get(city_id)
    if not d:
        return ""
    titles = {
        "es": ("Las mejores zonas para salir en {l}", "\u00bfQu\u00e9 noche salir en {l}?"),
        "en": ("The best areas to go out in {l}", "Which night to go out in {l}?"),
        "de": ("Die besten Ausgehviertel in {l}", "An welchem Abend ausgehen in {l}?"),
    }
    zt, nt = titles.get(lang, titles["es"])
    rows = "".join(
        f'<div><b>{e(z["name"])}</b> {e(z.get(lang, z["es"]))}</div>' for z in d["zones"])
    nights = e(d["nights"].get(lang, d["nights"]["es"]))
    return (f'<h2 class="sectitle">{e(zt.format(l=label))}</h2>'
            f'<div class="meta">{rows}</div>'
            f'<h2 class="sectitle">{e(nt.format(l=label))}</h2>'
            f'<div class="intro"><p>{nights}</p></div>')


def _city_intro(city_id, label, n, lang, e):
    d = _CITY_INTRO_DATA.get(city_id)
    if not d:
        return ""
    clubs = d["clubs"]
    areas = d["areas"].get(lang, d["areas"]["es"])
    vibe = d["vibe"].get(lang, d["vibe"]["es"])
    if lang == "en":
        txt = (f"{label} is {vibe}. From {clubs} to countless parties around {areas}, there's something on "
               f"every night. On \u00bfQui\u00e9n va? we gather every party in {label} \u2014 {n} plans this week \u2014 with "
               f"line-ups, start times, real ticket prices and, best of all, which of your friends are going. "
               f"Browse tonight's and this weekend's parties, compare clubs and grab your tickets before they sell out.")
    elif lang == "de":
        txt = (f"{label} ist {vibe}. Von {clubs} bis zu unz\u00e4hligen Partys rund um {areas} ist jede Nacht etwas los. "
               f"Auf \u00bfQui\u00e9n va? b\u00fcndeln wir alle Partys in {label} \u2014 {n} Pl\u00e4ne diese Woche \u2014 mit Line-ups, "
               f"Startzeiten, echten Ticketpreisen und vor allem: welche Freunde hingehen. Entdecke die Partys heute "
               f"Abend und am Wochenende, vergleiche Clubs und sichere dir Tickets, bevor sie ausverkauft sind.")
    else:
        txt = (f"{label} es {vibe}. Desde {clubs} hasta un sinf\u00edn de fiestas por {areas}, cada noche hay planazo. "
               f"En \u00bfQui\u00e9n va? reunimos todas las fiestas de {label} \u2014 {n} planes esta semana \u2014 con cartel, "
               f"horarios, precios reales de entrada y, lo mejor, qu\u00e9 amigos van a cada una. Descubre las fiestas de "
               f"esta noche y este finde, compara discotecas y consigue tus entradas antes de que se agoten.")
    return f'<div class="intro"><p>{e(txt)}</p></div>'

_SEO_FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
              '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
              '<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&family=Unbounded:wght@700;800;900&display=swap" rel="stylesheet">')

# Localized micro-copy for the redesigned SEO pages (topbar CTA, benefits,
# join band). Kept separate from SEO_T so it is easy to extend.
_SEO_UI = {
    "es": {
        "open": "Abrir app",
        "why": "Por qu\u00e9 \u00bfQui\u00e9n va?",
        "b1t": "Descubre qui\u00e9n va", "b1d": "Mira qu\u00e9 amigos van a cada fiesta antes de decidir el plan.",
        "b2t": "Entradas al mejor precio", "b2d": "Precios reales y avisos cuando bajan o quedan pocas entradas.",
        "b3t": "No te pierdas nada", "b3d": "Todas las discotecas y fiestas de tu ciudad, en un solo sitio.",
        "join": "\u00danete gratis", "join_h": "Vive la noche con tus amigos",
        "join_p": "Reg\u00edstrate gratis: mira qui\u00e9n va, consigue tus entradas y no te pierdas ni una fiesta.",
    },
    "en": {
        "open": "Open app",
        "why": "Why \u00bfQui\u00e9n va?",
        "b1t": "See who's going", "b1d": "Check which friends are going to each party before you decide.",
        "b2t": "Tickets at the best price", "b2d": "Real prices and alerts when they drop or are running low.",
        "b3t": "Never miss out", "b3d": "Every club and party in your city, all in one place.",
        "join": "Join free", "join_h": "Live the night with your friends",
        "join_p": "Sign up free: see who's going, grab your tickets and never miss a party.",
    },
    "de": {
        "open": "App \u00f6ffnen",
        "why": "Warum \u00bfQui\u00e9n va?",
        "b1t": "Sieh, wer hingeht", "b1d": "Sieh, welche Freunde zu jeder Party gehen, bevor du dich entscheidest.",
        "b2t": "Tickets zum besten Preis", "b2d": "Echte Preise und Hinweise, wenn sie sinken oder knapp werden.",
        "b3t": "Verpass nichts", "b3d": "Alle Clubs und Partys deiner Stadt an einem Ort.",
        "join": "Kostenlos beitreten", "join_h": "Erlebe die Nacht mit deinen Freunden",
        "join_p": "Melde dich kostenlos an: sieh wer hingeht, hol dir Tickets und verpass keine Party.",
    },
}

SEO_T = {
    "es": {
        "html_lang": "es",
        "city_title": "Fiestas y discotecas en {label} hoy y este fin de semana | \u00bfQui\u00e9n va?",
        "city_desc": "Todas las fiestas de {label}: {n} planes con horarios, precios y qu\u00e9 amigos van. Descubre las discotecas y los pr\u00f3ximos planes en \u00bfQui\u00e9n va?",
        "city_h1": "Fiestas en {label} hoy y este fin de semana",
        "city_sub": "{n} pr\u00f3ximos planes \u00b7 horarios, precios y qu\u00e9 amigos van. Con \u00bfQui\u00e9n va?",
        "open_app": "Abrir \u00bfQui\u00e9n va?",
        "other_cities": "Otras ciudades:",
        "empty": "Pronto publicaremos las pr\u00f3ximas fiestas de esta ciudad.",
        "footer": "\u00bfQui\u00e9n va? \u2014 descubre los planes del finde y mira qu\u00e9 amigos van a cada sitio.",
        "ev_title": "{name} \u2014 {venue}, {city} | Entradas y horario | \u00bfQui\u00e9n va?",
        "ev_desc": "{name} en {venue} ({city}), {date}. {price}Mira qui\u00e9n va y consigue tu entrada en \u00bfQui\u00e9n va?",
        "ev_cta": "Ver qui\u00e9n va y entradas",
        "ev_buy": "Comprar entradas",
        "ev_seeapp": "Ver qui\u00e9n va en la app",
        "ev_ended": "Esta fiesta ya ha terminado \u2014 mira los pr\u00f3ximos planes.",
        "ev_when": "Cu\u00e1ndo", "ev_where": "D\u00f3nde", "ev_price": "Precio", "ev_genre": "M\u00fasica",
        "more_in": "M\u00e1s fiestas en {label}",
        "free": "Entrada libre", "from": "desde {p}\u20ac", "soldout": "Agotado",
        "st_on_sale": "A la venta", "st_few": "Pocas entradas", "st_sold_out": "Agotado",
        "st_list_only": "Solo lista", "st_soon": "Pr\u00f3ximamente", "free_badge": "Gratis",
        "other_langs": "Idiomas:",
        "tf_tonight_title": "Fiestas esta noche en {label} | \u00bfQui\u00e9n va?",
        "tf_tonight_desc": "\u00bfQu\u00e9 hacer esta noche en {label}? {n} fiestas y discotecas abiertas hoy con horarios y precios. M\u00edralas en \u00bfQui\u00e9n va?",
        "tf_tonight_h1": "Fiestas esta noche en {label}",
        "tf_tonight_sub": "{n} planes para hoy \u00b7 horarios, precios y qu\u00e9 amigos van.",
        "tf_tonight_empty": "Hoy no hay fiestas listadas en {label}. Mira los planes del finde.",
        "tf_weekend_title": "Fiestas este fin de semana en {label} | \u00bfQui\u00e9n va?",
        "tf_weekend_desc": "Planes para este finde en {label}: {n} fiestas y discotecas con horarios y precios. Descubre qui\u00e9n va en \u00bfQui\u00e9n va?",
        "tf_weekend_h1": "Fiestas este fin de semana en {label}",
        "tf_weekend_sub": "{n} planes para el finde \u00b7 horarios, precios y qu\u00e9 amigos van.",
        "tf_weekend_empty": "A\u00fan no hay fiestas del finde en {label}. Mira todos los pr\u00f3ximos planes.",
        "link_all": "Todos los pr\u00f3ximos", "link_tonight": "Esta noche", "link_weekend": "Este finde",
        "bc_home": "Inicio", "faq_title": "Preguntas frecuentes",
        "faq_c_q1": "\u00bfQu\u00e9 fiestas hay en {label} esta semana?",
        "faq_c_a1": "Ahora mismo hay {n} fiestas y discotecas en {label} con horarios y precios actualizados. \u00c1brelas en \u00bfQui\u00e9n va?",
        "faq_c_q2": "\u00bfCu\u00e1nto cuestan las entradas?",
        "faq_c_a2": "Depende de la sala y la fecha. En cada fiesta ver\u00e1s el precio actual y si est\u00e1 a la venta, quedan pocas o est\u00e1 agotada.",
        "faq_c_q3": "\u00bfC\u00f3mo s\u00e9 qu\u00e9 amigos van?",
        "faq_c_a3": "En \u00bfQui\u00e9n va? ves qu\u00e9 amigos van o tienen entrada para cada fiesta y te avisamos de los planes del finde.",
        "faq_e_q_when": "\u00bfCu\u00e1ndo es {name}?",
        "faq_e_q_where": "\u00bfD\u00f3nde es {name}?",
        "faq_e_q_price": "\u00bfCu\u00e1nto cuesta la entrada?",
        "faq_e_a_price_free": "Consulta el precio actualizado en \u00bfQui\u00e9n va?.",
        "faq_e_a_when": "{name} es el {when} en {venue}, {city}.",
        "faq_e_a_where": "{name} se celebra en {venue}{addr}, {city}.",
        "faq_e_a_price": "La entrada para {name} cuesta {price} (precio actualizado en \u00bfQui\u00e9n va?).",
        "faq_e_q_friends": "\u00bfQu\u00e9 amigos van a {name}?",
        "faq_e_a_friends": "En \u00bfQui\u00e9n va? ves qu\u00e9 amigos van o tienen entrada para {name} y te avisamos cuando alguien de tu grupo se apunta.",
        "faq_e_q_tickets": "\u00bfC\u00f3mo consigo la entrada para {name}?",
        "faq_e_a_tickets": "Abre {name} en \u00bfQui\u00e9n va? y pulsa en conseguir entrada para comprarla al precio actualizado.",
    },
    "en": {
        "html_lang": "en",
        "city_title": "Parties & clubs in {label} tonight and this weekend | \u00bfQui\u00e9n va?",
        "city_desc": "All the parties in {label}: {n} plans with times, prices and which friends are going. Discover this week's clubs on \u00bfQui\u00e9n va?",
        "city_h1": "Parties in {label} tonight and this weekend",
        "city_sub": "{n} upcoming plans \u00b7 times, prices and which friends are going. With \u00bfQui\u00e9n va?",
        "open_app": "Open \u00bfQui\u00e9n va?",
        "other_cities": "Other cities:",
        "empty": "We'll publish the upcoming parties for this city soon.",
        "footer": "\u00bfQui\u00e9n va? \u2014 discover the weekend plans and see which friends are going where.",
        "ev_title": "{name} \u2014 {venue}, {city} | Tickets & time | \u00bfQui\u00e9n va?",
        "ev_desc": "{name} at {venue} ({city}), {date}. {price}See who's going and get your ticket on \u00bfQui\u00e9n va?",
        "ev_cta": "See who's going & tickets",
        "ev_buy": "Buy tickets",
        "ev_seeapp": "See who's going in the app",
        "ev_ended": "This party has ended \u2014 check out the upcoming plans.",
        "ev_when": "When", "ev_where": "Where", "ev_price": "Price", "ev_genre": "Music",
        "more_in": "More parties in {label}",
        "free": "Free entry", "from": "from \u20ac{p}", "soldout": "Sold out",
        "st_on_sale": "On sale", "st_few": "Few left", "st_sold_out": "Sold out",
        "st_list_only": "Guest list", "st_soon": "Coming soon", "free_badge": "Free",
        "other_langs": "Languages:",
        "tf_tonight_title": "Parties tonight in {label} | \u00bfQui\u00e9n va?",
        "tf_tonight_desc": "What to do tonight in {label}? {n} parties and clubs open today with times and prices. See them on \u00bfQui\u00e9n va?",
        "tf_tonight_h1": "Parties tonight in {label}",
        "tf_tonight_sub": "{n} plans for tonight \u00b7 times, prices and which friends are going.",
        "tf_tonight_empty": "No parties listed tonight in {label}. Check this weekend's plans.",
        "tf_weekend_title": "Parties this weekend in {label} | \u00bfQui\u00e9n va?",
        "tf_weekend_desc": "Plans for this weekend in {label}: {n} parties and clubs with times and prices. See who's going on \u00bfQui\u00e9n va?",
        "tf_weekend_h1": "Parties this weekend in {label}",
        "tf_weekend_sub": "{n} plans for the weekend \u00b7 times, prices and which friends are going.",
        "tf_weekend_empty": "No weekend parties yet in {label}. See all upcoming plans.",
        "link_all": "All upcoming", "link_tonight": "Tonight", "link_weekend": "This weekend",
        "bc_home": "Home", "faq_title": "Frequently asked questions",
        "faq_c_q1": "What parties are on in {label} this week?",
        "faq_c_a1": "Right now there are {n} parties and clubs in {label} with up-to-date times and prices. Open them on \u00bfQui\u00e9n va?",
        "faq_c_q2": "How much are the tickets?",
        "faq_c_a2": "It depends on the venue and date. On each party you'll see the current price and whether it's on sale, few left or sold out.",
        "faq_c_q3": "How do I know which friends are going?",
        "faq_c_a3": "On \u00bfQui\u00e9n va? you can see which friends are going or have a ticket for each party, and we alert you about the weekend plans.",
        "faq_e_q_when": "When is {name}?",
        "faq_e_q_where": "Where is {name}?",
        "faq_e_q_price": "How much is the ticket?",
        "faq_e_a_price_free": "Check the up-to-date price on \u00bfQui\u00e9n va?.",
        "faq_e_a_when": "{name} takes place on {when} at {venue}, {city}.",
        "faq_e_a_where": "{name} is held at {venue}{addr}, {city}.",
        "faq_e_a_price": "Tickets for {name} start at {price} (up-to-date price on \u00bfQui\u00e9n va?).",
        "faq_e_q_friends": "Which friends are going to {name}?",
        "faq_e_a_friends": "On \u00bfQui\u00e9n va? you can see which friends are going or have a ticket for {name}, and we notify you when someone from your group joins.",
        "faq_e_q_tickets": "How do I get a ticket for {name}?",
        "faq_e_a_tickets": "Open {name} on \u00bfQui\u00e9n va? and tap get ticket to buy at the up-to-date price.",
    },
    "de": {
        "html_lang": "de",
        "city_title": "Partys & Clubs in {label} heute und dieses Wochenende | \u00bfQui\u00e9n va?",
        "city_desc": "Alle Partys in {label}: {n} Pl\u00e4ne mit Uhrzeiten, Preisen und welche Freunde hingehen. Entdecke die Clubs dieser Woche auf \u00bfQui\u00e9n va?",
        "city_h1": "Partys in {label} heute und dieses Wochenende",
        "city_sub": "{n} kommende Pl\u00e4ne \u00b7 Uhrzeiten, Preise und welche Freunde hingehen. Mit \u00bfQui\u00e9n va?",
        "open_app": "\u00bfQui\u00e9n va? \u00f6ffnen",
        "other_cities": "Weitere St\u00e4dte:",
        "empty": "Wir ver\u00f6ffentlichen die kommenden Partys dieser Stadt bald.",
        "footer": "\u00bfQui\u00e9n va? \u2014 entdecke die Wochenendpl\u00e4ne und sieh, welche Freunde wohin gehen.",
        "ev_title": "{name} \u2014 {venue}, {city} | Tickets & Uhrzeit | \u00bfQui\u00e9n va?",
        "ev_desc": "{name} im {venue} ({city}), {date}. {price}Sieh, wer hingeht, und hol dir dein Ticket auf \u00bfQui\u00e9n va?",
        "ev_cta": "Sehen, wer hingeht & Tickets",
        "ev_buy": "Tickets kaufen",
        "ev_seeapp": "Wer hingeht \u2013 in der App",
        "ev_ended": "Diese Party ist vorbei \u2014 sieh dir die kommenden Pl\u00e4ne an.",
        "ev_when": "Wann", "ev_where": "Wo", "ev_price": "Preis", "ev_genre": "Musik",
        "more_in": "Mehr Partys in {label}",
        "free": "Freier Eintritt", "from": "ab {p}\u20ac", "soldout": "Ausverkauft",
        "st_on_sale": "Im Verkauf", "st_few": "Wenige \u00fcbrig", "st_sold_out": "Ausverkauft",
        "st_list_only": "Nur G\u00e4steliste", "st_soon": "Demn\u00e4chst", "free_badge": "Gratis",
        "other_langs": "Sprachen:",
        "tf_tonight_title": "Partys heute Abend in {label} | \u00bfQui\u00e9n va?",
        "tf_tonight_desc": "Was heute Abend in {label} los ist? {n} Partys und Clubs heute ge\u00f6ffnet, mit Uhrzeiten und Preisen. Sieh sie auf \u00bfQui\u00e9n va?",
        "tf_tonight_h1": "Partys heute Abend in {label}",
        "tf_tonight_sub": "{n} Pl\u00e4ne f\u00fcr heute \u00b7 Uhrzeiten, Preise und welche Freunde hingehen.",
        "tf_tonight_empty": "Heute keine Partys in {label} gelistet. Sieh dir die Wochenendpl\u00e4ne an.",
        "tf_weekend_title": "Partys dieses Wochenende in {label} | \u00bfQui\u00e9n va?",
        "tf_weekend_desc": "Pl\u00e4ne f\u00fcrs Wochenende in {label}: {n} Partys und Clubs mit Uhrzeiten und Preisen. Sieh, wer hingeht, auf \u00bfQui\u00e9n va?",
        "tf_weekend_h1": "Partys dieses Wochenende in {label}",
        "tf_weekend_sub": "{n} Pl\u00e4ne f\u00fcrs Wochenende \u00b7 Uhrzeiten, Preise und welche Freunde hingehen.",
        "tf_weekend_empty": "Noch keine Wochenend-Partys in {label}. Sieh alle kommenden Pl\u00e4ne.",
        "link_all": "Alle kommenden", "link_tonight": "Heute Abend", "link_weekend": "Wochenende",
        "bc_home": "Start", "faq_title": "H\u00e4ufige Fragen",
        "faq_c_q1": "Welche Partys gibt es diese Woche in {label}?",
        "faq_c_a1": "Aktuell gibt es {n} Partys und Clubs in {label} mit aktuellen Uhrzeiten und Preisen. \u00d6ffne sie auf \u00bfQui\u00e9n va?",
        "faq_c_q2": "Wie viel kosten die Tickets?",
        "faq_c_a2": "Das h\u00e4ngt von Location und Datum ab. Bei jeder Party siehst du den aktuellen Preis und ob im Verkauf, wenige \u00fcbrig oder ausverkauft.",
        "faq_c_q3": "Woher wei\u00df ich, welche Freunde hingehen?",
        "faq_c_a3": "Auf \u00bfQui\u00e9n va? siehst du, welche Freunde hingehen oder ein Ticket haben, und wir informieren dich \u00fcber die Wochenendpl\u00e4ne.",
        "faq_e_q_when": "Wann ist {name}?",
        "faq_e_q_where": "Wo ist {name}?",
        "faq_e_q_price": "Wie viel kostet das Ticket?",
        "faq_e_a_price_free": "Sieh den aktuellen Preis auf \u00bfQui\u00e9n va?.",
        "faq_e_a_when": "{name} findet am {when} im {venue}, {city} statt.",
        "faq_e_a_where": "{name} findet im {venue}{addr}, {city} statt.",
        "faq_e_a_price": "Tickets f\u00fcr {name} gibt es ab {price} (aktueller Preis auf \u00bfQui\u00e9n va?).",
        "faq_e_q_friends": "Welche Freunde gehen zu {name}?",
        "faq_e_a_friends": "Auf \u00bfQui\u00e9n va? siehst du, welche Freunde zu {name} gehen oder ein Ticket haben, und wir benachrichtigen dich, wenn jemand aus deiner Gruppe dabei ist.",
        "faq_e_q_tickets": "Wie bekomme ich ein Ticket f\u00fcr {name}?",
        "faq_e_a_tickets": "\u00d6ffne {name} auf \u00bfQui\u00e9n va? und tippe auf Ticket sichern, um zum aktuellen Preis zu kaufen.",
    },
}

_DOW = {
    "es": ["lunes", "martes", "mi\u00e9rcoles", "jueves", "viernes", "s\u00e1bado", "domingo"],
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "de": ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"],
}
_MON = {
    "es": ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"],
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "de": ["Jan.", "Feb.", "M\u00e4rz", "Apr.", "Mai", "Juni", "Juli", "Aug.", "Sep.", "Okt.", "Nov.", "Dez."],
}


def _seo_date(date_str: str, lang: str, tm: str = "") -> str:
    try:
        d = date.fromisoformat(date_str)
        dow = _DOW[lang][d.weekday()]
        mon = _MON[lang][d.month - 1]
        s = f"{dow} {d.day}. {mon}" if lang == "de" else f"{dow} {d.day} {mon}"
        if tm:
            s += f" \u00b7 {tm}"
        return s
    except Exception:
        return date_str or ""


def _seo_price_line(ev: dict, lang: str) -> str:
    T = SEO_T[lang]
    if ev.get("sale_state") == "agotado":
        return T["soldout"]
    prices = [t.get("price") for t in (ev.get("price_tiers") or []) if isinstance(t, dict) and t.get("price")]
    if prices:
        return T["from"].format(p=int(min(prices)))
    return ""


def _seo_sale_badge(ev: dict, lang: str):
    """(label, css_class) for a sale-state pill matching the app. None if hidden."""
    T = SEO_T[lang]
    st = ev.get("sale_state") or "no_a_la_venta"
    mp = {
        "a_la_venta": (T["st_on_sale"], "sb-on"),
        "pocas_entradas": (T["st_few"], "sb-few"),
        "agotado": (T["st_sold_out"], "sb-out"),
        "solo_lista": (T["st_list_only"], "sb-list"),
        "no_a_la_venta": (T["st_soon"], "sb-soon"),
    }
    return mp.get(st, mp["no_a_la_venta"])


def _seo_card(ev, ev_url, lang, e, nofollow: bool = False) -> str:
    """App-style poster card for SEO listings.

    nofollow=True is used for links to PAST parties (which are noindex): it stops
    Googlebot from spending crawl budget following into pages it will drop anyway.
    """
    pl = _seo_price_line(ev, lang)
    when = _seo_date(ev.get("date", ""), lang, ev.get("time", ""))
    venue = e(ev.get("venue", ""))
    meta = " \u00b7 ".join([x for x in [venue, e(when)] if x])
    vn = e(ev.get("venue", "") or "")
    ph = (f'<div class="ph"><span class="phn">{e(ev.get("name","Fiesta"))}</span>'
          f'{f"<span class=phv>{vn}</span>" if vn else ""}'
          f'<span class="phb">\u00bfQui\u00e9n va?</span></div>')
    img = ev.get("image_url", "")
    if str(img).startswith("http"):
        poster = ph + (f'<div class="blurbg" style="background-image:url({e(img)})"></div>'
                       f'<img src="{e(img)}" alt="{e(ev.get("name",""))}" loading="lazy" '
                       f'onerror="this.style.display=&#39;none&#39;">')
    else:
        poster = ph
    blabel, bcls = _seo_sale_badge(ev, lang)
    badge = f'<span class="sb {bcls}">{e(blabel)}</span>'
    price = f'<span class="pp">{e(pl)}</span>' if pl else ''
    rel_attr = ' rel="nofollow"' if nofollow else ''
    return (
        f'<a class="card glow-card reveal" data-testid="seo-event-card" data-s="{e((str(ev.get("name","")) + " " + str(ev.get("venue","")) ).lower())}" href="{e(ev_url)}"{rel_attr}>'
        f'<div class="poster">{poster}<div class="badges">{badge}{price}</div></div>'
        f'<div class="body"><span class="n">{e(ev.get("name","Fiesta"))}</span>'
        f'<span class="m">{meta}</span></div></a>')



def _city_paths(front: str, slug: str) -> dict:
    return {"es": f"{front}/fiestas/{slug}",
            "en": f"{front}/en/parties/{slug}",
            "de": f"{front}/de/partys/{slug}"}


def _event_paths(front: str, eid: str, slug: str) -> dict:
    tail = f"{eid}/{slug}" if slug else eid
    return {"es": f"{front}/fiesta/{tail}",
            "en": f"{front}/en/party/{tail}",
            "de": f"{front}/de/party/{tail}"}


def _hreflang_links(paths: dict, e) -> str:
    out = "".join(f'<link rel="alternate" hreflang="{l}" href="{e(u)}">' for l, u in paths.items())
    out += f'<link rel="alternate" hreflang="x-default" href="{e(paths["es"])}">'
    return out


def _lang_switch(paths: dict, current: str, label: str, e) -> str:
    names = {"es": "Espa\u00f1ol", "en": "English", "de": "Deutsch"}
    links = "".join(
        (f'<b>{names[l]}</b>' if l == current else f'<a href="{e(u)}">{names[l]}</a>') + " "
        for l, u in paths.items())
    return f'<div class="langs">{label} {links}</div>'


def _event_slug(ev: dict) -> str:
    return _slugify(f"{ev.get('name','')}-{ev.get('venue','')}-{ev.get('city','')}") or "fiesta"


def _seo_end_datetime(start: str) -> str:
    """Estimate an Event endDate: club nights run into the early morning, so we
    add ~6h to the start (or end 06:00 the next day when only a date is known).
    Google recommends endDate; supplying a sensible one clears the warning."""
    try:
        if "T" in start:
            dt = datetime.fromisoformat(start)
            return (dt + timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M")
        d = date.fromisoformat(start[:10])
        return f"{(d + timedelta(days=1)).isoformat()}T06:00"
    except Exception:
        return start


def _event_description(ev: dict, lang: str = "es") -> str:
    name = ev.get("name", "") or "Fiesta"
    venue = ev.get("venue", "")
    city = ev.get("city", "")
    when = _seo_date(ev.get("date", ""), lang, ev.get("time", "")) if "_seo_date" in globals() else ev.get("date", "")
    pl = _price_line(ev)
    where = " · ".join([x for x in [venue, city] if x])
    if lang == "en":
        base = f"{name}" + (f" at {where}" if where else "") + f". {when}."
        base += f" From {pl.replace('desde ', '')}." if pl and pl != "Agotado" else (" Sold out." if pl == "Agotado" else "")
        base += " Line-up, tickets and who's going on ¿Quién va?"
    elif lang == "de":
        base = f"{name}" + (f" im {where}" if where else "") + f". {when}."
        base += f" Ab {pl.replace('desde ', '')}." if pl and pl != "Agotado" else (" Ausverkauft." if pl == "Agotado" else "")
        base += " Tickets, Zeiten und wer hingeht auf ¿Quién va?"
    else:
        base = f"{name}" + (f" en {where}" if where else "") + f". {when}."
        base += f" Entradas {pl}." if pl and pl != "Agotado" else (" Agotado." if pl == "Agotado" else "")
        base += " Horarios, entradas y quién va en ¿Quién va?"
    return base[:300]


def _event_jsonld(ev: dict, url: str, front: str, include_offers: bool = True, lang: str = "es") -> str:
    start = ev.get("date", "")
    if ev.get("time"):
        start = f"{ev.get('date','')}T{ev.get('time')}"
    avail = "https://schema.org/InStock"
    if ev.get("sale_state") == "agotado":
        avail = "https://schema.org/SoldOut"
    elif ev.get("sale_state") == "no_a_la_venta":
        avail = "https://schema.org/PreOrder"
    obj = {
        "@context": "https://schema.org", "@type": "Event",
        "name": ev.get("name", ""),
        "startDate": start,
        "endDate": _seo_end_datetime(start),
        "description": _event_description(ev, lang),
        "eventStatus": "https://schema.org/EventScheduled",
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        "location": {"@type": "Place", "name": ev.get("venue", ""),
                     "address": {"@type": "PostalAddress",
                                 "streetAddress": ev.get("address", "") or ev.get("venue", ""),
                                 "addressLocality": ev.get("city", ""),
                                 "addressCountry": "ES"}},
        "url": url,
        "organizer": {"@type": "Organization", "name": "\u00bfQui\u00e9n va?", "url": front},
        # Club nights are headlined by the party/artist name; expose it as the
        # performer so Google can render richer event results.
        "performer": {"@type": "PerformingGroup", "name": ev.get("name", "") or ev.get("venue", "")},
    }
    if str(ev.get("image_url", "")).startswith("http"):
        obj["image"] = [ev["image_url"]]
    prices = [t.get("price") for t in (ev.get("price_tiers") or []) if isinstance(t, dict) and t.get("price")]
    if include_offers:
        event_day = str(ev.get("date") or "")[:10]
        valid_from = str(ev.get("created_at") or ev.get("last_scraped_at") or "")[:10]
        if not valid_from or (event_day and valid_from > event_day):
            valid_from = event_day
        # offers.url should be the page where you can actually BUY the ticket
        # (Google's guideline for event ticket offers) — use our affiliate buy link
        # when we have one, otherwise fall back to the event page URL.
        buy_url = url
        try:
            _c = _commission_url_for(ev)
            if ev.get("has_commission") and _c:
                buy_url = _c
        except Exception:
            pass
        offer = {"@type": "Offer", "availability": avail, "url": buy_url}
        if valid_from:
            offer["validFrom"] = valid_from
        # Price is only asserted when we actually know it (scraped tiers). For
        # events without a known price we still emit the Offer (url + validFrom
        # + availability) so Google always sees an `offers` field.
        if prices:
            offer["price"] = int(min(prices))
            offer["priceCurrency"] = ev.get("currency", "EUR") or "EUR"
            if event_day:
                offer["priceValidUntil"] = event_day
        obj["offers"] = offer
    return json.dumps(obj, ensure_ascii=False)


def _ev_lastmod(ev: dict, today: str) -> str:
    """A valid <lastmod> for the sitemap: the day the event was last refreshed,
    never a future date (Google ignores future lastmod)."""
    raw = str(ev.get("last_scraped_at") or ev.get("created_at") or "")[:10]
    if len(raw) == 10 and raw <= today:
        return raw
    return today


def _breadcrumb_jsonld(items: list) -> str:
    """items: list of (name, url). Emits schema.org BreadcrumbList."""
    els = [{"@type": "ListItem", "position": i + 1, "name": nm, "item": url}
           for i, (nm, url) in enumerate(items)]
    return json.dumps({"@context": "https://schema.org", "@type": "BreadcrumbList",
                       "itemListElement": els}, ensure_ascii=False)


def _breadcrumb_html(items: list, e) -> str:
    sep = " \u203a "
    parts = []
    for i, (nm, url) in enumerate(items):
        parts.append(f'<span>{e(nm)}</span>' if i == len(items) - 1 else f'<a href="{e(url)}">{e(nm)}</a>')
    return '<nav class="bc">' + sep.join(parts) + '</nav>'


def _faq_jsonld(pairs: list) -> str:
    """pairs: list of (question, answer). Emits schema.org FAQPage."""
    els = [{"@type": "Question", "name": q,
            "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in pairs]
    return json.dumps({"@context": "https://schema.org", "@type": "FAQPage",
                       "mainEntity": els}, ensure_ascii=False)


def _faq_html(title: str, pairs: list, e) -> str:
    rows = "".join(f'<details><summary>{e(q)}</summary><p>{e(a)}</p></details>' for q, a in pairs)
    return f'<div class="faq"><h2>{e(title)}</h2>{rows}</div>'


_TF_SLUG = {
    "tonight": {"es": "esta-noche", "en": "tonight", "de": "heute"},
    "weekend": {"es": "este-finde", "en": "this-weekend", "de": "wochenende"},
}


def _city_tf_paths(front: str, slug: str, timeframe: str) -> dict:
    base = _city_paths(front, slug)
    if timeframe == "all":
        return base
    return {lang: f"{base[lang]}/{_TF_SLUG[timeframe][lang]}" for lang in SEO_LANGS}


def _weekend_range(today):
    """(start, end) ISO dates for 'this weekend' (Fri-Sun), clamped to today."""
    wd = today.weekday()  # Mon=0 .. Sun=6
    friday = today + timedelta(days=4 - wd) if wd <= 3 else today - timedelta(days=wd - 4)
    sunday = friday + timedelta(days=2)
    start = max(today, friday)
    return start.isoformat(), sunday.isoformat()


async def _events_for_timeframe(city_id: str, timeframe: str) -> list:
    if timeframe == "all":
        return await _upcoming_for_city(city_id)
    today = datetime.now(ZoneInfo("Europe/Madrid")).date()
    if timeframe == "tonight":
        start = end = today.isoformat()
    else:  # weekend
        start, end = _weekend_range(today)
    cur = db.events.find(
        {"city": city_query_value(city_id), "date": {"$gte": start, "$lte": end}},
        {"_id": 0, "id": 1, "name": 1, "venue": 1, "date": 1, "time": 1, "city": 1,
         "genre": 1, "address": 1, "currency": 1, "last_scraped_at": 1, "created_at": 1,
         "image_url": 1, "price_tiers": 1, "sale_state": 1},
    ).sort("date", 1).limit(60)
    return [ev async for ev in cur]


async def _render_city(slug: str, lang: str, request: Request, timeframe: str = "all"):
    import html as _html
    e = _html.escape
    T = SEO_T[lang]
    city_id = _CITY_SLUGS.get(slug.lower())
    front = _frontend_base(request)
    if not city_id:
        return StarletteResponse(
            content=f"<!doctype html><meta http-equiv=refresh content='0;url={front}/feed'>",
            media_type="text/html", status_code=404)
    events = await _events_for_timeframe(city_id, timeframe)
    label = next((c["label"] for c in SUPPORTED_CITIES if c["id"] == city_id), city_id)
    slug_l = _city_slug(city_id)
    paths = _city_tf_paths(front, slug_l, timeframe)
    canonical = paths[lang]
    n = len(events)
    if timeframe == "all":
        title = e(T["city_title"].format(label=label, n=n))
        desc = e(T["city_desc"].format(label=label, n=n))
        h1 = e(T["city_h1"].format(label=label))
        sub = e(T["city_sub"].format(n=n))
        empty = e(T["empty"])
    else:
        tk = "tf_tonight" if timeframe == "tonight" else "tf_weekend"
        title = e(T[f"{tk}_title"].format(label=label, n=n))
        desc = e(T[f"{tk}_desc"].format(label=label, n=n))
        h1 = e(T[f"{tk}_h1"].format(label=label))
        sub = e(T[f"{tk}_sub"].format(n=n))
        empty = e(T[f"{tk}_empty"].format(label=label))
    # Freshness signal (month + year) → better CTR & "up-to-date" ranking signal.
    title = _title_with_month(title, lang)
    _mo = _seo_month(lang)
    h1 = f"{h1} \u2014 {_mo}"
    desc = f"{desc} {_UPDATED_WORD.get(lang, 'Actualizado')} {_mo}."
    # Dynamic 1200x630 banner built from the featured event poster (falls back to
    # the static branded banner). Richer link previews on WhatsApp/Instagram/Twitter.
    og_img = f"{front}/og-city/{slug_l}.jpg"

    items_html = []
    jsonld = []
    for ev in events[:24]:
        ev_url = _event_paths(front, ev.get("id", ""), _event_slug(ev))[lang]
        items_html.append(f'<li>{_seo_card(ev, ev_url, lang, e)}</li>')
        jsonld.append(f'<script type="application/ld+json">{_event_jsonld(ev, ev_url, front, lang=lang)}</script>')
    if not items_html:
        items_html.append(f'<li class="empty">{e(empty)}</li>')

    # Internal nav between timeframes (all / tonight / weekend), same language.
    nav = []
    for tf, key in (("all", "link_all"), ("tonight", "link_tonight"), ("weekend", "link_weekend")):
        u = _city_tf_paths(front, slug_l, tf)[lang]
        lbl = e(T[key])
        nav.append(f'<b>{lbl}</b>' if tf == timeframe else f'<a href="{e(u)}">{lbl}</a>')
    nav_html = f'<div class="nav-tf">{"".join(nav)}</div>'

    # Nightclubs of this city (for the stats bar + "Discotecas" grid). The full
    # grid shows on the main landing; tonight/weekend stay lean.
    venues = await _city_venues(city_id) if timeframe == "all" else []
    n_ven = len(venues)
    _lbl = {
        "es": {"plans": "pr\u00f3ximos planes", "clubs": "discotecas", "prices": "Precios reales",
               "search": "Busca tu fiesta o discoteca\u2026", "vh": f"Discotecas en {label}",
               "vsub": "Toca una discoteca para ver todas sus fiestas", "parties": "fiestas",
               "nores": "Sin resultados para tu b\u00fasqueda"},
        "en": {"plans": "upcoming plans", "clubs": "clubs", "prices": "Real prices",
               "search": "Search a party or club\u2026", "vh": f"Nightclubs in {label}",
               "vsub": "Tap a club to see all its parties", "parties": "parties",
               "nores": "No results for your search"},
        "de": {"plans": "kommende Pl\u00e4ne", "clubs": "Clubs", "prices": "Echte Preise",
               "search": "Party oder Club suchen\u2026", "vh": f"Clubs in {label}",
               "vsub": "Tippe auf einen Club f\u00fcr alle Partys", "parties": "Partys",
               "nores": "Keine Ergebnisse"},
    }
    L2 = _lbl.get(lang, _lbl["es"])
    ven_stat = f'<span class="stat"><b>{n_ven}</b> {e(L2["clubs"])}</span>' if n_ven else ''
    stats_html = (f'<div class="stats"><span class="stat"><b>{n}</b> {e(L2["plans"])}</span>'
                  f'{ven_stat}'
                  f'<span class="stat">\U0001F3AB {e(L2["prices"])}</span></div>')
    # Hero search box (client-side filter of the cards below — progressive enhancement).
    finder_html = (f'<div class="finder"><span class="fic">\U0001F50D</span>'
                   f'<input id="qvf" type="search" autocomplete="off" placeholder="{e(L2["search"])}" '
                   f'oninput="qvFilter(this.value)" aria-label="{e(L2["search"])}"></div>')
    # "Discotecas" grid with cover/logo.
    venues_html = ""
    if venues:
        vcards = []
        for v in venues:
            thumb = (f'<span class="vthumb"><img src="{e(v["image"])}" alt="{e(v["venue"])}" loading="lazy"></span>'
                     if v["image"] else
                     f'<span class="vthumb">{e((v["venue"][:1] or "?").upper())}</span>')
            vcards.append(
                f'<a class="vcard glow-card reveal" href="{e(_venue_paths(front, v["slug"])[lang])}">{thumb}'
                f'<span class="vmeta"><b>{e(v["venue"])}</b><small>{v["count"]} {e(L2["parties"])}</small></span></a>')
        venues_html = (f'<div class="sech"><h2>{e(L2["vh"])}</h2><span>{n_ven}</span></div>'
                       f'<div style="color:var(--muted);font-size:13px;margin:-8px 0 12px">{e(L2["vsub"])}</div>'
                       f'<div class="venues">{"".join(vcards)}</div>')
    _search_js = ('<script>function qvFilter(q){q=(q||"").toLowerCase().trim();'
                  'var c=document.querySelectorAll(".grid .card"),nr=document.getElementById("qvnores"),shown=0;'
                  'c.forEach(function(el){var m=!q||(el.getAttribute("data-s")||"").indexOf(q)>=0;'
                  'el.style.display=m?"":"none";if(m)shown++;});'
                  'if(nr)nr.style.display=(shown===0&&q)?"block":"none";}</script>')
    topbar = _seo_topbar(front, lang, e)
    benefits = _seo_benefits(lang, e)
    joinband = _seo_joinband(front, lang, e)

    other_cities = "".join(
        f'<a href="{e(_city_paths(front, _city_slug(c["id"]))[lang])}">{e(c["label"])}</a>'
        for c in SUPPORTED_CITIES if c["id"] != city_id)
    hreflang = _hreflang_links(paths, e)
    langsw = _lang_switch(paths, lang, e(T["other_langs"]), e)
    ogimg_tag = (f'<meta property="og:image" content="{og_img}">'
                 '<meta property="og:image:width" content="1200">'
                 '<meta property="og:image:height" content="630">'
                 f'<meta property="og:image:alt" content="{title}">'
                 f'<meta name="twitter:image" content="{og_img}">') if og_img else ''

    # Breadcrumbs + FAQ (rich results). Static text, no extra DB cost.
    bc_items = [(T["bc_home"], f"{front}/"), (label, _city_paths(front, slug_l)[lang])]
    if timeframe != "all":
        bc_items.append((T["link_tonight"] if timeframe == "tonight" else T["link_weekend"], canonical))
    bc_html = _breadcrumb_html(bc_items, e)
    faq_pairs = [
        (T["faq_c_q1"].format(label=label), T["faq_c_a1"].format(label=label, n=n)),
        (T["faq_c_q2"], T["faq_c_a2"]),
        (T["faq_c_q3"], T["faq_c_a3"]),
    ]
    intro_html = _city_intro(city_id, label, n, lang, e) if timeframe == "all" else ""
    cityguide_html = _city_guide_content(city_id, label, lang, e) if timeframe == "all" else ""
    faq_html = _faq_html(T["faq_title"], faq_pairs, e)
    guides_html = _city_guides_block(front, slug_l, label, lang, e)
    extra_jsonld = (_org_website_jsonld(front)
                    + f'<script type="application/ld+json">{_breadcrumb_jsonld(bc_items)}</script>'
                    f'<script type="application/ld+json">{_faq_jsonld(faq_pairs)}</script>')

    html_out = f"""<!doctype html>
<html lang="{T['html_lang']}"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{e(canonical)}">{_ICONS_HEAD}
{hreflang}
<meta property="og:type" content="website"><meta property="og:site_name" content="\u00bfQui\u00e9n va?">
<meta property="og:locale" content="{ {'es':'es_ES','en':'en_US','de':'de_DE'}[lang] }">
<meta property="og:title" content="{title}"><meta property="og:description" content="{desc}">
<meta property="og:url" content="{e(canonical)}">{ogimg_tag}
<meta name="twitter:card" content="summary_large_image">
{''.join(jsonld)}{extra_jsonld}
{_SEO_FONTS}
<style>{_SEO_CSS}</style></head>
<body><div class="bgfx"></div>
{topbar}
<div class="wrap">
{bc_html}
<section class="hero-sec">
<span class="kicker">{e(label)}</span>
<h1>{h1}<span class="dot">.</span></h1>
<p class="sub">{sub}</p>
{stats_html}
<div class="ctarow"><a class="cta" href="{front}/feed">{e(T["open_app"])}</a></div>
{nav_html}
</section>
{_app_promo_band(lang)}
{intro_html}
{finder_html}
<ul class="grid">{''.join(items_html)}<li class="nores" id="qvnores">{e(L2["nores"])}</li></ul>
{venues_html}
{cityguide_html}
{benefits}
{joinband}
{guides_html}
<div class="cities"><b>{e(T["other_cities"])}</b>{other_cities}</div>
{faq_html}
{langsw}
<footer>{e(T["footer"])}</footer>
</div>{_app_sticky_bar(lang)}{_search_js}</body></html>"""
    return StarletteResponse(content=html_out, media_type="text/html; charset=utf-8",
                             headers={"Cache-Control": "public, max-age=1800"})


@api_router.api_route("/ciudad/{slug}", methods=["GET", "HEAD"])
async def seo_city_es(slug: str, request: Request):
    return await _render_city(slug, "es", request)


@api_router.api_route("/ciudad/{slug}/esta-noche", methods=["GET", "HEAD"])
async def seo_city_es_tonight(slug: str, request: Request):
    return await _render_city(slug, "es", request, "tonight")


@api_router.api_route("/ciudad/{slug}/este-finde", methods=["GET", "HEAD"])
async def seo_city_es_weekend(slug: str, request: Request):
    return await _render_city(slug, "es", request, "weekend")


@api_router.api_route("/en/city/{slug}", methods=["GET", "HEAD"])
async def seo_city_en(slug: str, request: Request):
    return await _render_city(slug, "en", request)


@api_router.api_route("/en/city/{slug}/tonight", methods=["GET", "HEAD"])
async def seo_city_en_tonight(slug: str, request: Request):
    return await _render_city(slug, "en", request, "tonight")


@api_router.api_route("/en/city/{slug}/this-weekend", methods=["GET", "HEAD"])
async def seo_city_en_weekend(slug: str, request: Request):
    return await _render_city(slug, "en", request, "weekend")


@api_router.api_route("/de/city/{slug}", methods=["GET", "HEAD"])
async def seo_city_de(slug: str, request: Request):
    return await _render_city(slug, "de", request)


@api_router.api_route("/de/city/{slug}/heute", methods=["GET", "HEAD"])
async def seo_city_de_tonight(slug: str, request: Request):
    return await _render_city(slug, "de", request, "tonight")


@api_router.api_route("/de/city/{slug}/wochenende", methods=["GET", "HEAD"])
async def seo_city_de_weekend(slug: str, request: Request):
    return await _render_city(slug, "de", request, "weekend")


async def _get_event_seo(event_id: str):
    return await db.events.find_one(
        {"id": event_id},
        {"_id": 0, "id": 1, "name": 1, "venue": 1, "date": 1, "time": 1, "city": 1,
         "genre": 1, "address": 1, "currency": 1, "last_scraped_at": 1, "created_at": 1,
         "image_url": 1, "price_tiers": 1, "sale_state": 1, "commission_url": 1,
         "has_commission": 1})


async def _render_event(event_id: str, lang: str, request: Request, slug: str = ""):
    import html as _html
    e = _html.escape
    T = SEO_T[lang]
    front = _frontend_base(request)
    ev = await _get_event_seo(event_id)
    if not ev:
        # The party was removed from the DB (past/cancelled parties get purged to
        # keep storage low). Instead of a soft-404 that Google keeps recrawling,
        # try to 301 to the party's CITY hub (city is the tail of the URL slug),
        # preserving link equity and giving the user a useful landing. If the city
        # can't be inferred, return a real 410 Gone so Google drops it fast/clean.
        city_id = None
        s = (slug or "").lower()
        if s:
            for cslug in sorted(_CITY_SLUGS.keys(), key=len, reverse=True):
                if s == cslug or s.endswith("-" + cslug):
                    city_id = _CITY_SLUGS[cslug]
                    break
        if city_id:
            seo_slug = CITY_SEO_SLUG.get(city_id, _city_slug(city_id))
            target = _city_paths(front, seo_slug)[lang]
            return StarletteResponse(status_code=301, headers={"Location": target},
                                     content=f"<!doctype html><meta http-equiv=refresh content='0;url={target}'>",
                                     media_type="text/html")
        gone_html = (f"<!doctype html><html lang='{lang}'><head><meta charset='utf-8'>"
                     f"<meta name='robots' content='noindex'>"
                     f"<title>{e(T.get('ev_ended', 'Fiesta finalizada'))}</title></head>"
                     f"<body><p>{e(T.get('ev_ended', 'Esta fiesta ya no está disponible.'))}</p>"
                     f"<p><a href='{front}/feed'>¿Quién va?</a></p></body></html>")
        return StarletteResponse(content=gone_html, media_type="text/html", status_code=410,
                                 headers={"X-Robots-Tag": "noindex"})
    slug = _event_slug(ev)
    paths = _event_paths(front, event_id, slug)
    canonical = paths[lang]
    today = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
    is_past = bool(ev.get("date", "")) and ev.get("date", "") < today
    # Upcoming but with no real content yet (placeholder/thin) -> keep out of index
    # until it gets a poster/price/specific name. Past events are handled separately.
    is_thin = (not is_past) and _is_thin_event(ev)
    city = ev.get("city", "")
    when = _seo_date(ev.get("date", ""), lang, ev.get("time", ""))
    pl = _seo_price_line(ev, lang)
    price_pref = (pl + ". ") if pl else ""
    title = e(_event_seo_title(ev, lang))
    desc = e(T["ev_desc"].format(name=ev.get("name", ""), venue=ev.get("venue", ""), city=city, date=when, price=price_pref))
    img = ev.get("image_url", "")
    if str(img).startswith("http"):
        hero = (f'<div class="ehero"><div class="ehero-bg" style="background-image:url({e(img)})"></div>'
                f'<div class="ehero-poster"><img src="{e(img)}" alt="{e(ev.get("name",""))}" '
                f'width="400" height="520" onerror="this.closest(&#39;.ehero&#39;).style.display=&#39;none&#39;"></div></div>')
    else:
        hero = ""
    ogimg_tag = f'<meta property="og:image" content="{e(img)}">' if str(img).startswith("http") else ''
    hreflang = _hreflang_links(paths, e)
    langsw = _lang_switch(paths, lang, e(T["other_langs"]), e)
    jsonld = f'<script type="application/ld+json">{_event_jsonld(ev, canonical, front, include_offers=not is_past, lang=lang)}</script>'

    # Related upcoming events in the same city (internal linking + freshness).
    city_id = None
    for c in SUPPORTED_CITIES:
        if c["id"] == city or city in CITY_REGIONS.get(c["id"], []):
            city_id = c["id"]; break
    related_html = ""
    if city_id:
        city_label = next((c["label"] for c in SUPPORTED_CITIES if c["id"] == city_id), city_id)
        rel = await _upcoming_for_city(city_id, 8)
        lis = []
        for r in rel:
            if r.get("id") == event_id:
                continue
            if _is_thin_event(r):
                continue
            ru = _event_paths(front, r.get("id", ""), _event_slug(r))[lang]
            lis.append(f'<li>{_seo_card(r, ru, lang, e)}</li>')
        if lis:
            more_url = _city_paths(front, _city_slug(city_id))[lang]
            related_html = (f'<h2 class="sectitle">{e(T["more_in"].format(label=city_label))}</h2>'
                            f'<ul class="grid">{"".join(lis[:6])}</ul>'
                            f'<div class="ctarow"><a class="cta ghost" href="{e(more_url)}">{e(T["more_in"].format(label=city_label))}</a></div>')

    genre_row = f'<div><b>{e(T["ev_genre"])}</b>{e(ev.get("genre",""))}</div>' if ev.get("genre") else ""
    addr = (", " + e(ev.get("address", ""))) if ev.get("address") else ""

    # Breadcrumbs + FAQ (rich results). Static/derived text, no extra DB cost.
    name = ev.get("name", "Fiesta")
    venue = ev.get("venue", "")
    addr_plain = (", " + ev.get("address", "")) if ev.get("address") else ""
    bc_items = [(T["bc_home"], f"{front}/")]
    if city_id:
        bc_items.append((city_label, _city_paths(front, _city_slug(city_id))[lang]))
    if venue:
        bc_items.append((venue, _venue_paths(front, _slugify(venue))[lang]))
    bc_items.append((name, canonical))
    bc_html = _breadcrumb_html(bc_items, e)
    faq_pairs = [
        (T["faq_e_q_when"].format(name=name),
         T["faq_e_a_when"].format(name=name, when=when, venue=venue, city=city)),
        (T["faq_e_q_where"].format(name=name),
         T["faq_e_a_where"].format(name=name, venue=venue, addr=addr_plain, city=city)),
    ]
    if not is_past:
        # No misleading price/ticket FAQ on past parties.
        if pl:
            faq_pairs.append((T["faq_e_q_price"], T["faq_e_a_price"].format(name=name, price=pl)))
        else:
            faq_pairs.append((T["faq_e_q_price"], T["faq_e_a_price_free"]))
        faq_pairs.append((T["faq_e_q_tickets"].format(name=name),
                          T["faq_e_a_tickets"].format(name=name)))
    faq_pairs.append((T["faq_e_q_friends"].format(name=name),
                      T["faq_e_a_friends"].format(name=name)))
    faq_html = _faq_html(T["faq_title"], faq_pairs, e)
    extra_jsonld = (_org_website_jsonld(front)
                    + f'<script type="application/ld+json">{_breadcrumb_jsonld(bc_items)}</script>'
                    f'<script type="application/ld+json">{_faq_jsonld(faq_pairs)}</script>')

    # Freshness / churn handling: past parties are noindex,follow (Google drops the
    # stale page but still follows links to upcoming events), no misleading offers,
    # and the primary CTA funnels to the city's upcoming parties instead of tickets.
    robots_meta = ('<meta name="robots" content="noindex, follow">' if (is_past or is_thin)
                   else '<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1">')
    ended_html = f'<p class="sub" style="color:#f5a524;font-weight:700">{e(T["ev_ended"])}</p>' if is_past else ''
    ui = _SEO_UI.get(lang, _SEO_UI["es"])
    topbar = _seo_topbar(front, lang, e)
    benefits = _seo_benefits(lang, e)
    joinband = _seo_joinband(front, lang, e)
    ghost_open = f'<a class="cta ghost" href="{front}/feed">{e(ui["open"])}</a>'
    if is_past and city_id:
        primary_cta = f'<a class="cta" href="{e(_city_paths(front, _city_slug(city_id))[lang])}">{e(T["more_in"].format(label=city_label))}</a>'
        ctarow_html = f'<div class="ctarow">{primary_cta}</div>'
        sticky_html = ''
    else:
        # Same logic as the app: OUR affiliate link for the clubs we carry,
        # the original ticket link for the rest. Direct "Buy tickets" button +
        # a secondary "see who's going" that opens the app.
        buy_url = _commission_url_for(ev)
        can_buy = bool(buy_url) and ev.get("sale_state") != "agotado"
        app_url = f'{front}/event/{e(event_id)}'
        if can_buy:
            buy_btn = (f'<a class="cta" href="{e(buy_url)}" target="_blank" '
                       f'rel="nofollow sponsored noopener">{e(T["ev_buy"])}</a>')
            app_btn = f'<a class="cta ghost" href="{app_url}">{e(T["ev_seeapp"])}</a>'
            ctarow_html = f'<div class="ctarow">{buy_btn}{app_btn}</div>'
            sticky_btn = buy_btn
        else:
            primary_cta = f'<a class="cta" href="{app_url}">{e(T["ev_cta"])}</a>'
            ctarow_html = f'<div class="ctarow">{primary_cta}{ghost_open}</div>'
            sticky_btn = f'<a class="cta" href="{app_url}">{e(T["ev_cta"])}</a>'
        sticky_html = (f'<div class="stickycta"><div class="pr"><small>{e(T["ev_price"])}</small>'
                       f'<b>{e(pl or T["free"])}</b></div>'
                       f'{sticky_btn}</div>')
    ogloc = {'es': 'es_ES', 'en': 'en_US', 'de': 'de_DE'}[lang]
    # Internal linking: turn the venue + city in the fact row into real links to
    # their evergreen hub pages so Google understands the site structure.
    _vn = ev.get("venue", "")
    venue_link = (f'<a href="{e(_venue_paths(front, _slugify(_vn))[lang])}">{e(_vn)}</a>' if _vn else "")
    city_link = e(city)
    if city_id:
        city_link = f'<a href="{e(_city_paths(front, _city_slug(city_id))[lang])}">{e(city)}</a>'
    html_out = f"""<!doctype html>
<html lang="{T['html_lang']}"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
{robots_meta}
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{e(canonical)}">{_ICONS_HEAD}
{hreflang}
<meta property="og:type" content="website"><meta property="og:site_name" content="\u00bfQui\u00e9n va?">
<meta property="og:locale" content="{ogloc}">
<meta property="og:title" content="{title}"><meta property="og:description" content="{desc}">
<meta property="og:url" content="{e(canonical)}">{ogimg_tag}
<meta name="twitter:card" content="summary_large_image">
{jsonld}{extra_jsonld}
{_SEO_FONTS}
<style>{_SEO_CSS}</style></head>
<body><div class="bgfx"></div>
{topbar}
<div class="wrap">
{bc_html}
{hero}
<section class="hero-sec">
<span class="kicker">{e(city)}</span>
<h1>{e(ev.get("name","Fiesta"))}<span class="dot">.</span></h1>
<p class="sub">{e(ev.get("venue",""))} \u00b7 {e(city)}</p>
{ended_html}
</section>
<div class="meta">
<div><b>{e(T["ev_when"])}</b>{e(when)}</div>
<div><b>{e(T["ev_where"])}</b>{venue_link}{addr}, {city_link}</div>
{genre_row}
<div><b>{e(T["ev_price"])}</b>{e(pl or T["free"])}</div>
</div>
{ctarow_html}
{_app_promo_band(lang)}
{related_html}
{benefits}
{joinband}
{faq_html}
{langsw}
<footer>{e(T["footer"])}</footer>
</div>
{sticky_html}
</body></html>"""
    _headers = {"Cache-Control": "public, max-age=1800"}
    if is_past or is_thin:
        # Reinforce the <meta robots> so past/placeholder parties are dropped even
        # when a crawler only reads response headers (HEAD / non-HTML fetch).
        _headers["X-Robots-Tag"] = "noindex, follow"
    return StarletteResponse(content=html_out, media_type="text/html; charset=utf-8",
                             headers=_headers)


@api_router.api_route("/fiesta/{event_id}", methods=["GET", "HEAD"])
@api_router.api_route("/fiesta/{event_id}/{slug}", methods=["GET", "HEAD"])
async def seo_event_es(event_id: str, request: Request, slug: str = ""):
    return await _render_event(event_id, "es", request, slug)


@api_router.api_route("/en/party/{event_id}", methods=["GET", "HEAD"])
@api_router.api_route("/en/party/{event_id}/{slug}", methods=["GET", "HEAD"])
async def seo_event_en(event_id: str, request: Request, slug: str = ""):
    return await _render_event(event_id, "en", request, slug)


@api_router.api_route("/de/party/{event_id}", methods=["GET", "HEAD"])
@api_router.api_route("/de/party/{event_id}/{slug}", methods=["GET", "HEAD"])
async def seo_event_de(event_id: str, request: Request, slug: str = ""):
    return await _render_event(event_id, "de", request, slug)


# ---------------------------------------------------------------------------
# SEO: server-rendered HOMEPAGE (brand + city hub) and VENUE (club) pages.
# The homepage is served on "/" via a Vercel rewrite; a tiny inline script
# sends already-logged-in users straight to the app (/feed) so their
# experience is unchanged, while new visitors + crawlers get a rich, indexable
# landing that links to every city hub (spreads authority + aids discovery).
# ---------------------------------------------------------------------------

# Brand social profiles — Organization.sameAs (knowledge panel) + footer links.
QV_SOCIAL = [
    "https://www.instagram.com/quienva.me",
    "https://www.tiktok.com/@quienva.me",
]

_HOME_EXTRA_CSS = (
    ".hgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;margin:18px 0}"
    ".hcity{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);border-radius:16px;overflow:hidden}"
    ".hcity-main{display:flex;flex-direction:column;gap:2px;padding:16px;text-decoration:none;color:#fff}"
    ".hcity-main .he{font-size:26px}.hcity-main b{font-size:17px}.hcity-main small{color:#9aa}"
    ".hcity-tf{display:flex;gap:8px;padding:0 16px 14px}"
    ".hcity-tf a{font-size:13px;color:#c9b3ff;text-decoration:none;background:rgba(160,120,255,.12);"
    "padding:5px 10px;border-radius:999px}"
    ".social{display:flex;gap:14px;justify-content:center;margin:10px 0}"
    ".social a{color:#c9b3ff;text-decoration:none;font-weight:600}"
)

_HOME_T = {
    "es": {
        "title": "\u00bfQui\u00e9n va? \u2014 Fiestas y discotecas de hoy y este finde en tu ciudad",
        "desc": "Descubre todas las fiestas y discotecas de esta semana en Marbella, Ibiza, Madrid, Barcelona y Palma. Horarios, precios reales y qu\u00e9 amigos van. Consigue tus entradas en \u00bfQui\u00e9n va?",
        "h1": "Todas las fiestas de tu ciudad, en un solo sitio",
        "sub": "Descubre qu\u00e9 discotecas y fiestas hay hoy y este finde, mira qu\u00e9 amigos van y consigue tus entradas al mejor precio.",
        "cities_h": "Elige tu ciudad",
        "n_plans": "planes esta semana",
        "tonight": "Esta noche",
        "weekend": "Este finde",
        "faq_title": "Preguntas frecuentes",
        "faq": [
            ("\u00bfQu\u00e9 es \u00bfQui\u00e9n va?",
             "\u00bfQui\u00e9n va? re\u00fane todas las fiestas y discotecas de tu ciudad con horarios, precios reales y qu\u00e9 amigos van, para que no te pierdas ning\u00fan plan y consigas tus entradas f\u00e1cil."),
            ("\u00bfEn qu\u00e9 ciudades est\u00e1 disponible?",
             "Ahora mismo en Marbella / Puerto Ban\u00fas, Ibiza, Madrid, Barcelona y Palma de Mallorca, y cada semana a\u00f1adimos m\u00e1s fiestas."),
            ("\u00bfCu\u00e1nto cuesta?",
             "Es gratis. Reg\u00edstrate, mira qu\u00e9 fiestas hay, qui\u00e9n va y consigue tus entradas al mejor precio."),
        ],
    },
    "en": {
        "title": "\u00bfQui\u00e9n va? \u2014 Parties & clubs tonight and this weekend in your city",
        "desc": "Discover every party and club this week in Marbella, Ibiza, Madrid, Barcelona and Palma. Times, real prices and which friends are going. Get your tickets on \u00bfQui\u00e9n va?",
        "h1": "Every party in your city, in one place",
        "sub": "Discover which clubs and parties are on tonight and this weekend, see which friends are going and get your tickets at the best price.",
        "cities_h": "Choose your city",
        "n_plans": "plans this week",
        "tonight": "Tonight",
        "weekend": "This weekend",
        "faq_title": "FAQ",
        "faq": [
            ("What is \u00bfQui\u00e9n va?",
             "\u00bfQui\u00e9n va? brings together every party and club in your city with times, real prices and which friends are going, so you never miss a plan and grab tickets easily."),
            ("Which cities are available?",
             "Right now Marbella / Puerto Ban\u00fas, Ibiza, Madrid, Barcelona and Palma de Mallorca \u2014 and we add more parties every week."),
            ("How much does it cost?",
             "It's free. Sign up, see what's on, who's going and get your tickets at the best price."),
        ],
    },
    "de": {
        "title": "\u00bfQui\u00e9n va? \u2014 Partys & Clubs heute und am Wochenende in deiner Stadt",
        "desc": "Entdecke alle Partys und Clubs dieser Woche in Marbella, Ibiza, Madrid, Barcelona und Palma. Zeiten, echte Preise und welche Freunde hingehen. Hol dir deine Tickets bei \u00bfQui\u00e9n va?",
        "h1": "Alle Partys deiner Stadt an einem Ort",
        "sub": "Entdecke, welche Clubs und Partys heute und am Wochenende stattfinden, sieh wer hingeht und hol dir deine Tickets zum besten Preis.",
        "cities_h": "W\u00e4hle deine Stadt",
        "n_plans": "Pl\u00e4ne diese Woche",
        "tonight": "Heute",
        "weekend": "Wochenende",
        "faq_title": "H\u00e4ufige Fragen",
        "faq": [
            ("Was ist \u00bfQui\u00e9n va?",
             "\u00bfQui\u00e9n va? b\u00fcndelt alle Partys und Clubs deiner Stadt mit Zeiten, echten Preisen und welche Freunde hingehen \u2014 damit du keinen Plan verpasst und einfach Tickets bekommst."),
            ("Welche St\u00e4dte sind verf\u00fcgbar?",
             "Aktuell Marbella / Puerto Ban\u00fas, Ibiza, Madrid, Barcelona und Palma de Mallorca \u2014 und jede Woche kommen neue Partys dazu."),
            ("Was kostet es?",
             "Es ist kostenlos. Melde dich an, sieh was l\u00e4uft, wer hingeht und hol dir deine Tickets zum besten Preis."),
        ],
    },
}

_HOME_PATHS_TAIL = {"es": "/", "en": "/en", "de": "/de"}


def _home_paths(front: str) -> dict:
    return {l: f"{front}{tail}" for l, tail in _HOME_PATHS_TAIL.items()}


async def _all_cities_match() -> list:
    return [{"city": city_query_value(c["id"])} for c in SUPPORTED_CITIES]


async def _top_events_global(limit: int = 12) -> list:
    today = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
    q = {"date": {"$gte": today}, "$or": await _all_cities_match()}
    cur = db.events.find(q, {"_id": 0}).sort("date", 1).limit(limit)
    return [ev async for ev in cur]


async def _top_venues_global(limit: int = 12) -> list:
    today = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
    pipeline = [
        {"$match": {"date": {"$gte": today}, "venue": {"$nin": ["", None]},
                    "$or": await _all_cities_match()}},
        {"$group": {"_id": "$venue", "count": {"$sum": 1}, "image": {"$max": "$image_url"}}},
        {"$sort": {"count": -1}},
        {"$limit": limit},
    ]
    out = []
    async for r in db.events.aggregate(pipeline):
        v = r.get("_id") or ""
        if not v:
            continue
        img = r.get("image") or ""
        out.append({"venue": v, "slug": _slugify(v), "count": r.get("count", 0),
                    "image": img if str(img).startswith("http") else ""})
    return out



async def _render_home(lang: str, request: Request):
    import html as _html
    e = _html.escape
    front = _frontend_base(request)
    T = _HOME_T[lang]
    ST = SEO_T[lang]
    today = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
    paths = _home_paths(front)
    canonical = paths[lang]

    city_cards, itemlist = [], []
    total = 0
    for i, c in enumerate(SUPPORTED_CITIES, start=1):
        cid = c["id"]
        slug = _city_slug(cid)
        cp = _city_paths(front, slug)[lang]
        tf_t = _city_tf_paths(front, slug, "tonight")[lang]
        tf_w = _city_tf_paths(front, slug, "weekend")[lang]
        try:
            n = await db.events.count_documents({"city": city_query_value(cid), "date": {"$gte": today}})
        except Exception:
            n = 0
        total += n
        city_cards.append(
            f'<div class="hcity"><a class="hcity-main" href="{e(cp)}">'
            f'<span class="he">{c.get("emoji","")}</span><b>{e(c["label"])}</b>'
            f'<small>{n} {e(T["n_plans"])}</small></a>'
            f'<div class="hcity-tf"><a href="{e(tf_t)}">{e(T["tonight"])}</a>'
            f'<a href="{e(tf_w)}">{e(T["weekend"])}</a></div></div>')
        itemlist.append({"@type": "ListItem", "position": i, "url": cp, "name": c["label"]})
    cities_html = "".join(city_cards)

    # Premium home sections: search + upcoming parties grid + top nightclubs grid.
    HL = {
        "es": {"search": "Busca fiesta, discoteca o ciudad\u2026", "ev_h": "Pr\u00f3ximas fiestas en Espa\u00f1a",
               "ve_h": "Discotecas destacadas", "parties": "fiestas", "nores": "Sin resultados"},
        "en": {"search": "Search a party, club or city\u2026", "ev_h": "Upcoming parties in Spain",
               "ve_h": "Top nightclubs", "parties": "parties", "nores": "No results"},
        "de": {"search": "Party, Club oder Stadt suchen\u2026", "ev_h": "Kommende Partys in Spanien",
               "ve_h": "Top-Clubs", "parties": "Partys", "nores": "Keine Ergebnisse"},
    }.get(lang, None) or {"search": "Buscar\u2026", "ev_h": "Pr\u00f3ximas fiestas", "ve_h": "Discotecas",
                          "parties": "fiestas", "nores": "Sin resultados"}
    top_events = await _top_events_global(12)
    top_venues = await _top_venues_global(12)
    ev_grid = ""
    if top_events:
        ecards = [_seo_card(ev, _event_paths(front, ev.get("id", ""), _event_slug(ev))[lang], lang, e)
                  for ev in top_events]
        ev_grid = (f'<div class="sech"><h2>{e(HL["ev_h"])}</h2><span>{len(top_events)}</span></div>'
                   f'<ul class="grid">{"".join(ecards)}<li class="nores" id="qvnores">{e(HL["nores"])}</li></ul>')
    ve_grid = ""
    if top_venues:
        vc = []
        for v in top_venues:
            thumb = (f'<span class="vthumb"><img src="{e(v["image"])}" alt="{e(v["venue"])}" loading="lazy"></span>'
                     if v["image"] else f'<span class="vthumb">{e((v["venue"][:1] or "?").upper())}</span>')
            vc.append(f'<a class="vcard glow-card reveal" data-s="{e(v["venue"].lower())}" href="{e(_venue_paths(front, v["slug"])[lang])}">'
                      f'{thumb}<span class="vmeta"><b>{e(v["venue"])}</b><small>{v["count"]} {e(HL["parties"])}</small></span></a>')
        ve_grid = f'<div class="sech"><h2>{e(HL["ve_h"])}</h2></div><div class="venues">{"".join(vc)}</div>'
    finder_html = (f'<div class="finder"><span class="fic">\U0001F50D</span>'
                   f'<input id="qvf" type="search" autocomplete="off" placeholder="{e(HL["search"])}" '
                   f'oninput="qvFilter(this.value)" aria-label="{e(HL["search"])}"></div>')
    home_search_js = ('<script>function qvFilter(q){q=(q||"").toLowerCase().trim();'
                      'var c=document.querySelectorAll(".grid .card,.venues .vcard"),'
                      'nr=document.getElementById("qvnores"),shown=0;'
                      'c.forEach(function(el){var m=!q||(el.getAttribute("data-s")||el.textContent||"").toLowerCase().indexOf(q)>=0;'
                      'el.style.display=m?"":"none";if(m&&el.classList.contains("card"))shown++;});'
                      'if(nr)nr.style.display=(shown===0&&q)?"block":"none";}</script>')

    hreflang = _hreflang_links(paths, e)
    langsw = _lang_switch(paths, lang, e(ST["other_langs"]), e)
    topbar = _seo_topbar(front, lang, e)
    benefits = _seo_benefits(lang, e)
    joinband = _seo_joinband(front, lang, e)
    faq_html = _faq_html(T["faq_title"], T["faq"], e)
    il_json = json.dumps({"@context": "https://schema.org", "@type": "ItemList",
                          "itemListElement": itemlist}, ensure_ascii=False)
    extra_jsonld = (_org_website_jsonld(front)
                    + f'<script type="application/ld+json">{_faq_jsonld(T["faq"])}</script>'
                    + f'<script type="application/ld+json">{il_json}</script>')
    social_html = ('<div class="social">'
                   + "".join(f'<a href="{e(u)}" rel="me nofollow" target="_blank">'
                             f'{"Instagram" if "instagram" in u else "TikTok"}</a>' for u in QV_SOCIAL)
                   + '</div>')
    ogloc = {'es': 'es_ES', 'en': 'en_US', 'de': 'de_DE'}[lang]
    title = e(T["title"])
    desc = e(T["desc"])
    stats_html = (f'<div class="stats"><span class="stat"><b>{total}</b> {e(T["n_plans"])}</span>'
                  f'<span class="stat">\U0001F3AB {e(ST["st_on_sale"])}</span>'
                  f'<span class="stat">\U0001F465 {e(_HOME_T[lang]["tonight"])}</span></div>')
    html_out = f"""<!doctype html>
<html lang="{ST['html_lang']}"><head>
<script>try{{if(localStorage.getItem('qv_token'))location.replace('/feed')}}catch(e){{}}</script>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{e(canonical)}">{_ICONS_HEAD}
{hreflang}
<meta property="og:type" content="website"><meta property="og:site_name" content="\u00bfQui\u00e9n va?">
<meta property="og:locale" content="{ogloc}">
<meta property="og:title" content="{title}"><meta property="og:description" content="{desc}">
<meta property="og:url" content="{e(canonical)}">
<meta property="og:image" content="{front}/og/og-default.png">
<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:image" content="{front}/og/og-default.png">
{extra_jsonld}
{_SEO_FONTS}
<style>{_SEO_CSS}{_HOME_EXTRA_CSS}</style></head>
<body><div class="bgfx"></div>
{topbar}
<div class="wrap">
<section class="hero-sec">
<span class="kicker">\u00bfQui\u00e9n va?</span>
<h1>{e(T["h1"])}<span class="dot">.</span></h1>
<p class="sub">{e(T["sub"])}</p>
{stats_html}
<div class="ctarow"><a class="cta" href="{front}/feed">{e(_SEO_UI[lang]["join"])}</a></div>
{finder_html}
</section>
{ev_grid}
{ve_grid}
<h2 class="sectitle">{e(T["cities_h"])}</h2>
<div class="hgrid">{cities_html}</div>
{benefits}
{joinband}
{faq_html}
{social_html}
{langsw}
<footer>{e(ST["footer"])}</footer>
</div>{home_search_js}</body></html>"""
    return StarletteResponse(content=html_out, media_type="text/html; charset=utf-8",
                             headers={"Cache-Control": "public, max-age=1800, s-maxage=86400"})


@api_router.api_route("/home", methods=["GET", "HEAD"])
async def seo_home_es(request: Request):
    return await _render_home("es", request)


@api_router.api_route("/en/home", methods=["GET", "HEAD"])
async def seo_home_en(request: Request):
    return await _render_home("en", request)


@api_router.api_route("/de/home", methods=["GET", "HEAD"])
async def seo_home_de(request: Request):
    return await _render_home("de", request)


# ============================================================================
# BLOG (SEO long-tail) — server-rendered articles at /blog and /blog/{slug}
# ============================================================================
# Each post is a static, hand-written article targeting long-tail search
# queries like "mejores fiestas de Ibiza este verano". Server-rendered HTML
# so Googlebot indexes the full content, with Article + BreadcrumbList + FAQ
# JSON-LD. Adds /sitemap-blog.xml and per-post canonical URLs.
_BLOG_POSTS = {
    "mejores-fiestas-ibiza-verano": {
        "title": "Mejores fiestas de Ibiza este verano: gu\u00eda completa 2025",
        "description": "Descubre las mejores fiestas y discotecas de Ibiza este verano: Pacha, Ushua\u00efa, Amnesia, H\u00ef Ibiza, [UNVRS] y DC-10 con horarios, precios y consejos.",
        "hero_image": "https://res.cloudinary.com/dh4byqvbb/image/upload/w_1200,f_auto,q_auto/v1/quienva/blog/ibiza-summer.jpg",
        "published": "2025-06-15",
        "updated": "2025-07-01",
        "city": "Ibiza",
        "city_slug": "ibiza",
        "sections": [
            ("Las discotecas m\u00e1s ic\u00f3nicas de Ibiza", "Ibiza concentra las mejores discotecas del mundo en apenas 40 km de costa. <b>Pacha Ibiza</b> lleva desde 1973 marcando la pauta del clubbing internacional y sigue siendo referencia con sus fiestas m\u00edticas. <b>Ushua\u00efa Ibiza</b>, en Playa d'en Bossa, ofrece la experiencia \u00fanica del open-air club con los DJs m\u00e1s importantes del planeta. <b>Amnesia</b> es la meca del techno con dos salas gigantes y el famoso Terrace, mientras que <b>H\u00ef Ibiza</b>, hermana de Ushua\u00efa, se llev\u00f3 el t\u00edtulo del mejor club del mundo m\u00faltiples a\u00f1os seguidos. Sumado a <b>[UNVRS]</b>, <b>DC-10</b> (culto techno underground), <b>Eden</b> y <b>Club Chinois</b>, la agenda cubre todos los g\u00e9neros."),
            ("Los DJs top del verano 2025 en Ibiza", "David Guetta contin\u00faa con su icon\u00f3nica residencia F*** Me I'm Famous en Ushua\u00efa; Solomun sigue en Pacha con su Sunday Special; Marco Carola con Music On en Amnesia; Black Coffee con su residencia en H\u00ef Ibiza; Circoloco toma DC-10 los lunes; y ANTS regresa a Ushua\u00efa los s\u00e1bados con l\u00ednea techno. Consulta la agenda semanal actualizada en <a href=\"/fiestas/ibiza\">nuestra p\u00e1gina de fiestas de Ibiza</a>."),
            ("Cu\u00e1nto cuesta ir de fiesta en Ibiza", "El precio medio de entrada en 2025 oscila entre <b>40\u20ac y 90\u20ac</b> seg\u00fan el DJ y el club. Las fechas top con headliners (David Guetta, Calvin Harris, Solomun) pueden superar los <b>120\u20ac</b>. La bebida en el club ronda los <b>18-25\u20ac</b> y una botella de mesa desde 400\u20ac. Truco: comprar la entrada online con antelaci\u00f3n suele ser 20-30% m\u00e1s barato que en taquilla, y algunas noches tienen guest-list gratis hasta cierta hora."),
            ("C\u00f3mo llegar a las discotecas de Ibiza", "El <b>Discob\u00fas</b> (l\u00ednea 9) conecta Ibiza ciudad, San Antonio y Playa d'en Bossa toda la noche por 4\u20ac. Un taxi entre zonas cuesta entre <b>20\u20ac y 40\u20ac</b>. Muchos clubs ofrecen shuttle privado gratis desde hoteles asociados. Si conduces, aparcar en Playa d'en Bossa o San Antonio suele ser gratis pero llena pronto en fin de semana."),
            ("Consejos para disfrutar la noche ibicenca", "1) Reserva la entrada online con antelaci\u00f3n para ahorrar. 2) Ve pronto (23:00-00:00) para evitar cola y pagar menos. 3) Hidr\u00e1tate: el agua embotellada en el club cuesta unos 10\u20ac pero es fundamental. 4) Combina noche en club con d\u00eda en un beach club (Blue Marlin, Nassau, Nikki Beach) para el efecto Ibiza completo. 5) En <b>\u00bfQui\u00e9n va?</b> puedes ver qu\u00e9 amigos tienen entrada para el mismo club y planificar la noche juntos."),
        ],
        "faq": [
            ("\u00bfCu\u00e1les son las 5 mejores discotecas de Ibiza?", "Las 5 mejores discotecas de Ibiza son Pacha, Ushua\u00efa, Amnesia, H\u00ef Ibiza y DC-10. Todas est\u00e1n en el top mundial del clubbing y ofrecen residencias con los DJs m\u00e1s importantes cada verano."),
            ("\u00bfCu\u00e1ndo empieza la temporada de fiestas en Ibiza?", "La temporada arranca oficialmente en mayo con las Opening Parties y termina a principios de octubre con las Closing Parties. Los meses de m\u00e1xima actividad son julio y agosto."),
            ("\u00bfCu\u00e1nto cuesta una entrada de discoteca en Ibiza?", "Entre 40\u20ac y 90\u20ac de media en 2025. Las fechas con DJs de renombre mundial (Guetta, Solomun, Black Coffee) pueden superar los 120\u20ac. Comprar online con antelaci\u00f3n es m\u00e1s barato."),
            ("\u00bfCu\u00e1l es el mejor d\u00eda para ir de fiesta a Ibiza?", "Cada d\u00eda tiene su fiesta ic\u00f3nica: lunes Circoloco en DC-10, martes ANTS en Ushua\u00efa, mi\u00e9rcoles Pyramid en Amnesia, jueves David Guetta en Ushua\u00efa, viernes Music On en Amnesia, s\u00e1bado H\u00ef Ibiza y domingo Solomun en Pacha."),
            ("\u00bfC\u00f3mo se llega a las discotecas de Ibiza sin coche?", "El Discob\u00fas (l\u00ednea 9) recorre toda la costa hasta el amanecer por 4\u20ac. Los taxis cuestan entre 20\u20ac y 40\u20ac seg\u00fan la distancia. Muchos hoteles ofrecen shuttle gratis a los clubs asociados."),
        ],
        "related_cities": ["madrid", "barcelona", "palma"],
    },
    "mejores-discotecas-madrid": {
        "title": "Las 10 mejores discotecas de Madrid para salir esta noche",
        "description": "Gu\u00eda de las 10 mejores discotecas de Madrid: Kapital, Fabrik, Teatro Barcel\u00f3, Opium, Icon, Independance Club y m\u00e1s, con precios, m\u00fasica y c\u00f3mo llegar.",
        "hero_image": "https://res.cloudinary.com/dh4byqvbb/image/upload/w_1200,f_auto,q_auto/v1/quienva/blog/madrid-night.jpg",
        "published": "2025-05-20",
        "updated": "2025-07-01",
        "city": "Madrid",
        "city_slug": "madrid",
        "sections": [
            ("Los 10 clubs imprescindibles de Madrid", "Madrid tiene una de las mejores escenas nocturnas de Europa y para todos los gustos: <b>Kapital</b> (7 plantas, cada una con m\u00fasica distinta, la m\u00e1s famosa de Madrid), <b>Fabrik</b> (macro club de techno a las afueras, referente mundial), <b>Teatro Barcel\u00f3</b> (mainstream y comercial, ambiente joven), <b>Opium Madrid</b> (top y r&b, muy internacional), <b>Icon</b> (hip hop y r&b urbano), <b>Independance Club</b> (comercial en Gran V\u00eda), <b>Sala Cool</b> (electr\u00f3nica underground), <b>Mondo Disko</b> (techno y house de culto), <b>Goya Social Club</b> (elegante en el barrio de Salamanca) y <b>Panda Club</b> (nuevo hotspot). Ver <a href=\"/fiestas/madrid\">agenda completa</a>."),
            ("Zonas de fiesta en Madrid: Gran V\u00eda, Malasa\u00f1a y Salamanca", "<b>Gran V\u00eda / Callao</b> concentra los clubs m\u00e1s grandes y mainstream. <b>Malasa\u00f1a</b> es la zona alternativa e indie con bares y pubs. <b>Chueca</b> tiene ambiente LGTBIQ+ y m\u00e1s abierto. <b>Salamanca</b> es la m\u00e1s pija con clubs elegantes tipo Goya Social Club. <b>Chamber\u00ed</b> para copas de calidad. Y las afueras (Fabrik) para macrofiestas electr\u00f3nicas."),
            ("Precios de entrada y consumiciones", "La entrada media en Madrid oscila entre <b>15\u20ac y 25\u20ac</b> con una consumici\u00f3n incluida. Los clubs premium (Kapital, Fabrik en noches especiales) pueden llegar a <b>30-40\u20ac</b>. La copa suele costar <b>10-15\u20ac</b> dentro del club. Muchos clubs tienen listas gratis hasta las 2:00 o promociones de \"chicas gratis\" entre semana."),
            ("Horarios y c\u00f3mo llegar", "La mayor\u00eda abren entre las <b>00:00 y las 6:00</b>, aunque algunos como Fabrik cierran a las 7:00 o 8:00 los s\u00e1bados. El metro cierra a las 1:30, pero hay <b>b\u00fahos</b> (autobuses nocturnos) que recorren toda la ciudad hasta las 6:00. Un Uber/Cabify medio cuesta 8-15\u20ac dentro de la M-30."),
            ("Consejos para salir en Madrid", "1) Cena tarde (22:00) y llega al club sobre las 1:00, cuando empieza a llenarse. 2) Reserva mesa si vais m\u00e1s de 6, ahorra col\u00e1s y da acceso r\u00e1pido. 3) Ll\u00e9vate DNI/pasaporte, todos piden identificaci\u00f3n. 4) En <a href=\"/fiestas/madrid\">\u00bfQui\u00e9n va?</a> puedes ver qu\u00e9 discotecas tienen ambiente cada noche y quedar con tus amigos."),
        ],
        "faq": [
            ("\u00bfCu\u00e1l es la mejor discoteca de Madrid?", "Kapital es la m\u00e1s famosa y visitada por su tama\u00f1o (7 plantas, cada una con m\u00fasica diferente) y ambiente internacional. Fabrik lidera la escena techno con el mejor sonido de Espa\u00f1a."),
            ("\u00bfCu\u00e1nto cuesta la entrada a Kapital?", "La entrada a Kapital cuesta entre 15\u20ac y 25\u20ac dependiendo del d\u00eda, con una consumici\u00f3n incluida. Comprando online suele salir 5\u20ac m\u00e1s barato."),
            ("\u00bfHasta qu\u00e9 hora est\u00e1n abiertas las discotecas en Madrid?", "La mayor\u00eda cierran a las 5:30 o 6:00. Algunos macro clubs como Fabrik amanecen y cierran a las 7:00 u 8:00 de la ma\u00f1ana los s\u00e1bados."),
            ("\u00bfQu\u00e9 discotecas ponen reggaeton en Madrid?", "Icon Madrid, Kapital (en sus plantas urbanas), Opium y Independance Club programan reggaeton, r&b urbano y hip hop las noches m\u00e1s populares."),
            ("\u00bfCu\u00e1l es el mejor d\u00eda para salir de fiesta en Madrid?", "Viernes y s\u00e1bado son los m\u00e1s ambiente, pero jueves (\"jueves universitarios\") y el s\u00e1bado noche de Fabrik tambi\u00e9n llenan. Los domingos hay after-hours en algunas salas."),
        ],
        "related_cities": ["barcelona", "ibiza", "marbella"],
    },
    "discotecas-marbella-puerto-banus": {
        "title": "Discotecas en Marbella y Puerto Ban\u00fas: gu\u00eda completa 2025",
        "description": "Las mejores discotecas de Marbella y Puerto Ban\u00fas: Olivia Valere, Pangea, Nikki Beach, Suite Club y m\u00e1s. Precios, dresscode, VIP y c\u00f3mo llegar.",
        "hero_image": "https://res.cloudinary.com/dh4byqvbb/image/upload/w_1200,f_auto,q_auto/v1/quienva/blog/marbella-luxury.jpg",
        "published": "2025-06-01",
        "updated": "2025-07-01",
        "city": "Marbella",
        "city_slug": "marbella",
        "sections": [
            ("Los clubs de lujo m\u00e1s ic\u00f3nicos de Marbella", "Marbella es la capital del <b>lujo nocturno</b> en Espa\u00f1a. <b>Olivia Valere</b> lleva d\u00e9cadas siendo el club m\u00e1s ex\u00f3tico (est\u00e9tica marroqu\u00ed, jardines, piscinas). <b>Pangea Marbella</b> es la nueva estrella con eventos temporada, celebrities y ambiente joven-premium. <b>Nikki Beach</b> combina d\u00eda y noche con su famosa sunset party. <b>Suite Club</b> en Puerto Ban\u00fas atrae al p\u00fablico m\u00e1s glam. <b>La Sala by the Sea</b> y <b>Trocadero Arena</b> completan la oferta con dinner shows premium."),
            ("Puerto Ban\u00fas: la milla de oro de la noche", "Puerto Ban\u00fas concentra la mayor densidad de ocio nocturno de Marbella. Los mega yates atracan mientras <b>Aqwa Mist</b>, <b>Tibu</b>, <b>Momento</b> y <b>Suite</b> llenan la noche. El paseo tiene decenas de bares (Sinatra Bar, Old Joys) para el pre-drink. Es habitual ver Ferraris, Lamborghinis y celebrities."),
            ("Precios en Marbella: entrada, copa y VIP", "Marbella es cara: <b>entrada 25-40\u20ac</b>, copa <b>15-20\u20ac</b>, mesa VIP desde <b>800\u20ac</b> (2 botellas) hasta 5.000\u20ac en fechas top. Nikki Beach camas de d\u00eda desde 200\u20ac. Olivia Valere en fin de semana con DJ internacional puede llegar a 60\u20ac de entrada. Pangea con headliner internacional 40-50\u20ac."),
            ("Dresscode y ambiente", "Marbella es de las pocas ciudades espa\u00f1olas con <b>dresscode estricto</b>. Hombres: pantal\u00f3n largo y camisa (Olivia Valere no admite bermudas), zapato/mocas\u00edn. Mujeres: vestido/traje elegante. Nikki Beach y Ocean Club permiten estilismo m\u00e1s de d\u00eda. Es habitual ver caras conocidas: futbolistas, influencers, aristocracia \u00e1rabe."),
            ("Consejos para la noche en Marbella", "1) Reserva mesa VIP con antelaci\u00f3n en verano, se agotan. 2) Ll\u00e9vate DNI (control estricto). 3) Combina un beach club (Nikki, Ocean Club) al atardecer y sigue en club a las 00:00. 4) Los taxis son m\u00e1s caros que en otras ciudades (25-40\u20ac una carrera media). 5) Ver <a href=\"/fiestas/marbella\">agenda actualizada de fiestas en Marbella</a> con precios y disponibilidad de entradas."),
        ],
        "faq": [
            ("\u00bfCu\u00e1l es la mejor discoteca de Marbella?", "Olivia Valere es la m\u00e1s ic\u00f3nica desde hace d\u00e9cadas, con su est\u00e9tica marroqu\u00ed y ambiente exclusivo. Pangea Marbella se ha consolidado como la m\u00e1s trendy en los \u00faltimos a\u00f1os."),
            ("\u00bfCu\u00e1nto cuesta una mesa VIP en Marbella?", "Las mesas VIP arrancan en 800\u20ac (con 2 botellas incluidas) en un club medio y pueden superar los 5.000\u20ac en Nikki Beach o Pangea en fechas top de agosto."),
            ("\u00bfHay dresscode en las discotecas de Marbella?", "S\u00ed, y es estricto. Hombres: pantal\u00f3n largo, camisa y zapato/mocas\u00edn (nada de bermudas ni chanclas). Mujeres: vestido o estilo elegante. Muchos clubs rechazan la entrada por vestimenta inadecuada."),
            ("\u00bfPuerto Ban\u00fas o Marbella centro para salir?", "Puerto Ban\u00fas concentra la mayor\u00eda de discotecas grandes (Aqwa Mist, Tibu, Suite Club). Marbella centro tiene m\u00e1s clubs de dinner show (Olivia Valere, Pangea). Depende del ambiente que busques."),
            ("\u00bfCu\u00e1ndo es la mejor temporada para ir de fiesta a Marbella?", "De junio a septiembre, con el pico absoluto en agosto (\"August in Marbella\") cuando llegan celebrities y los clubs contratan DJs internacionales."),
        ],
        "related_cities": ["ibiza", "madrid", "barcelona"],
    },
    "mejores-fiestas-barcelona": {
        "title": "Mejores fiestas y discotecas en Barcelona 2025",
        "description": "Gu\u00eda de las mejores discotecas de Barcelona: Opium, Pacha Barcelona, Sh\u00f4ko, Bling Bling, Otto Zutz y m\u00e1s. Ambientes, precios y c\u00f3mo llegar.",
        "hero_image": "https://res.cloudinary.com/dh4byqvbb/image/upload/w_1200,f_auto,q_auto/v1/quienva/blog/barcelona-night.jpg",
        "published": "2025-05-25",
        "updated": "2025-07-01",
        "city": "Barcelona",
        "city_slug": "barcelona",
        "sections": [
            ("Discotecas top de Barcelona en 2025", "La escena nocturna barcelonesa combina mar, arquitectura y m\u00fasica. En el <b>Port Ol\u00edmpic</b> se concentran <b>Opium Barcelona</b> (comercial internacional, terraza sobre el mar), <b>Pacha Barcelona</b> (m\u00e1s house y electr\u00f3nica), <b>Sh\u00f4ko</b> (fusi\u00f3n mediterr\u00e1neo-asi\u00e1tica) y <b>CDLC</b>. En la zona alta: <b>Otto Zutz</b> (leyenda de la Barcelona indie), <b>Bling Bling</b> (r&b y urban), <b>Sutton</b> (ambiente pijo). Y para techno: <b>Nitsa Club</b> en Apolo y <b>Razzmatazz</b> con sus 5 salas es imprescindible."),
            ("Razzmatazz: 5 clubs en uno", "<b>Razzmatazz</b> merece secci\u00f3n propia. En el edificio del Poblenou hay 5 salas simult\u00e1neas: Razz Club (indie/rock), The Loft (electr\u00f3nica), Lolita (pop/comercial), Pop Bar (retro) y Rex Room (hip hop). Con una sola entrada (15-20\u20ac) accedes a todas. Es el club m\u00e1s popular entre estudiantes internacionales y locales."),
            ("Precios en Barcelona: m\u00e1s barato que Ibiza", "Los precios en Barcelona son m\u00e1s asequibles que en Ibiza y Marbella. <b>Entrada media 15-25\u20ac</b> (con consumici\u00f3n), copa 10-14\u20ac dentro del club, mesa VIP desde 300\u20ac. Muchos clubs tienen listas gratuitas antes de una hora determinada. Los mi\u00e9rcoles universitarios son especialmente baratos."),
            ("Barrios de fiesta: Poblenou, Ol\u00edmpic y Eixample", "<b>Port Ol\u00edmpic</b> = clubs de playa con turistas internacionales. <b>Poblenou</b> (Razzmatazz, Nitsa) = ambiente underground/electr\u00f3nica. <b>Eixample/Ensanche</b> (Sutton, Sh\u00f4ko) = m\u00e1s pijo y elegante. <b>Gr\u00e0cia</b> tiene bares alternativos ideales para el pre-drink. <b>El Born</b> y <b>Barrio G\u00f3tico</b> son perfectos para cocktails antes de club."),
            ("Consejos para salir de fiesta en Barcelona", "1) El metro cierra a las 2:00 (los viernes hasta las 5:00) pero hay muchos autobuses nocturnos (N-lines). 2) Reserva online, es 5-10\u20ac m\u00e1s barato. 3) Ve pronto (00:30-01:30) para evitar cola en Opium y Pacha. 4) Cuidado con las carteras en Port Ol\u00edmpic, es zona con m\u00e1s hurtos. 5) Consulta <a href=\"/fiestas/barcelona\">nuestra agenda de fiestas en Barcelona</a> con precios en tiempo real."),
        ],
        "faq": [
            ("\u00bfCu\u00e1l es la mejor discoteca de Barcelona?", "Razzmatazz es la m\u00e1s popular por su tama\u00f1o (5 salas simult\u00e1neas con estilos musicales distintos) y precio asequible. Opium lidera la zona de playa con ambiente internacional."),
            ("\u00bfCu\u00e1nto cuesta la entrada a Opium Barcelona?", "Entre 20\u20ac y 30\u20ac dependiendo del d\u00eda y DJ, con una consumici\u00f3n incluida. Los d\u00edas de sesi\u00f3n especial con headliner internacional pueden subir a 40\u20ac."),
            ("\u00bfHasta qu\u00e9 hora abren las discotecas en Barcelona?", "La mayor\u00eda cierran a las 6:00 de la ma\u00f1ana. Razzmatazz, Opium y Pacha son de las que cierran m\u00e1s tarde, algunas noches hasta las 7:00."),
            ("\u00bfQu\u00e9 zona de Barcelona es mejor para salir?", "Port Ol\u00edmpic si buscas ambiente internacional y clubs con vistas al mar (Opium, Pacha, Sh\u00f4ko). Poblenou si prefieres m\u00fasica electr\u00f3nica o indie (Razzmatazz, Nitsa)."),
            ("\u00bfEs seguro salir de fiesta en Barcelona?", "S\u00ed, aunque hay que tener cuidado con carteristas en zonas tur\u00edsticas y la playa del Port Ol\u00edmpic. Recomendamos llevar solo lo justo y usar bandolera cruzada delante."),
        ],
        "related_cities": ["madrid", "ibiza", "palma"],
    },
    "vida-nocturna-palma-de-mallorca": {
        "title": "Vida nocturna en Palma de Mallorca: gu\u00eda 2025",
        "description": "Descubre la vida nocturna de Palma de Mallorca: Pacha Mallorca, Tito's, BCM Planet Dance, Fitz, Amok y m\u00e1s. Fiestas, precios, playas y ambiente.",
        "hero_image": "https://res.cloudinary.com/dh4byqvbb/image/upload/w_1200,f_auto,q_auto/v1/quienva/blog/palma-night.jpg",
        "published": "2025-06-10",
        "updated": "2025-07-01",
        "city": "Palma de Mallorca",
        "city_slug": "palma",
        "sections": [
            ("Palma y Magaluf: dos escenas muy distintas", "Mallorca tiene <b>dos escenas de noche</b> muy diferentes. <b>Palma ciudad</b> ofrece clubs elegantes junto al Paseo Mar\u00edtimo (<b>Pacha Mallorca</b>, <b>Social Club</b>, <b>Titos</b>, <b>Garito Caf\u00e9</b>). <b>Magaluf</b>, a 15 minutos, es el epicentro del ocio brit\u00e1nico con <b>BCM Planet Dance</b> (uno de los clubs m\u00e1s grandes de Europa) y una intensa vida nocturna en Punta Ballena."),
            ("Pacha Mallorca y el Paseo Mar\u00edtimo", "<b>Pacha Mallorca</b> es hermana peque\u00f1a de la ibicenca y ofrece la misma esencia con menos masificaci\u00f3n. Programa DJs internacionales de electr\u00f3nica y house. En el mismo Paseo Mar\u00edtimo est\u00e1n <b>Titos</b> (leyenda desde 1923, cinco d\u00e9cadas de fiestas), <b>Social Club Mallorca</b> (m\u00fasica underground y ambiente joven) y bares como <b>Puro Beach</b>. Ver <a href=\"/fiestas/palma\">agenda semanal de Palma</a>."),
            ("Clubs alternativos: Fitz, Amok y Over Club", "En el centro de Palma hay una escena m\u00e1s alternativa e independiente. <b>Fitz Mallorca</b> combina cocktail bar y club con DJs locales. <b>Amok</b> es referencia electr\u00f3nica underground con line-ups muy cuidados. <b>Over Club</b>, <b>Lunita</b>, <b>Mar Salada</b> y <b>Luna Palma</b> completan la oferta de nichos musicales espec\u00edficos."),
            ("BCM Planet Dance y Magaluf", "<b>BCM</b> es uno de los clubs m\u00e1s grandes del mundo (capacidad 5.000 personas) con l\u00e1seres, pantallas gigantes y DJs internacionales de EDM. Entrada 25-40\u20ac. En Punta Ballena, la calle de fiesta de Magaluf, hay decenas de pubs de tradici\u00f3n brit\u00e1nica con happy hours desde las 20:00. Ambiente m\u00e1s j\u00f3ven y \"party holidays\"."),
            ("Consejos y c\u00f3mo llegar", "1) El bus n\u00b3 4 conecta Palma con Magaluf hasta las 3:00. 2) Un taxi Palma-Magaluf ronda los 20\u20ac. 3) Ll\u00e9vate DNI, el control es exigente. 4) Reserva mesa en Pacha Mallorca en fechas top de agosto. 5) Combina noche en club con d\u00eda en <b>Nikki Beach</b> o <b>Purobeach</b>. 6) En <b>\u00bfQui\u00e9n va?</b> puedes ver qu\u00e9 amigos van a cada fiesta y quedar antes."),
        ],
        "faq": [
            ("\u00bfCu\u00e1l es la mejor discoteca de Palma de Mallorca?", "Pacha Mallorca lidera la escena por su marca internacional y line-up. Titos es la m\u00e1s hist\u00f3rica (1923) y sigue siendo referente en el Paseo Mar\u00edtimo. BCM Planet Dance en Magaluf es la m\u00e1s grande."),
            ("\u00bfCu\u00e1nto cuesta la entrada a BCM Mallorca?", "Entre 25\u20ac y 40\u20ac dependiendo del DJ y la noche, con consumici\u00f3n incluida en algunas fechas. Los headliners internacionales de EDM pueden subir el precio a 50\u20ac."),
            ("\u00bfPalma o Magaluf para salir de fiesta?", "Palma ciudad para ambiente m\u00e1s elegante y variado (electr\u00f3nica, house). Magaluf para party holidays estilo brit\u00e1nico, macro clubs y ambiente joven. Ambas escenas est\u00e1n a 15 minutos en coche."),
            ("\u00bfHasta qu\u00e9 hora abren las discotecas en Mallorca?", "En Palma la mayor\u00eda cierran entre las 5:00 y las 6:00. En Magaluf, BCM y clubs de Punta Ballena pueden cerrar a las 6:00 o 7:00 seg\u00fan la noche."),
            ("\u00bfHay ambiente todo el a\u00f1o o solo en verano?", "El pico es de mayo a octubre. En invierno, la escena se reduce pero sigue habiendo actividad los fines de semana en Palma centro (Fitz, Amok, Social Club). Magaluf pr\u00e1cticamente cierra en invierno."),
        ],
        "related_cities": ["ibiza", "barcelona", "madrid"],
    },
    "como-conseguir-entradas-discoteca-baratas": {
        "title": "C\u00f3mo conseguir entradas de discoteca baratas (o gratis) en 2025",
        "description": "Trucos y consejos para conseguir entradas de discoteca m\u00e1s baratas o gratis: listas VIP, guest-list, pre-venta online, promotores, apps y c\u00f3digos descuento.",
        "hero_image": "https://res.cloudinary.com/dh4byqvbb/image/upload/w_1200,f_auto,q_auto/v1/quienva/blog/tickets-tips.jpg",
        "published": "2025-06-05",
        "updated": "2025-07-01",
        "city": None,
        "city_slug": None,
        "sections": [
            ("1. Compra la entrada online con antelaci\u00f3n", "El truco m\u00e1s efectivo. En pr\u00e1cticamente todos los clubs de <b>Ibiza, Marbella, Madrid y Barcelona</b>, la entrada anticipada online cuesta entre un <b>20% y un 40% menos</b> que en taquilla. Adem\u00e1s te evitas la cola de compra. Muchos clubs abren pre-venta con precio reducido las primeras 100-500 entradas."),
            ("2. \u00fanete a la guest-list o lista gratis", "Casi todos los clubs tienen <b>guest-list</b> gratuita hasta cierta hora (normalmente entre las 23:00 y las 00:30). Basta con apuntarse en la web del club, en Instagram o a trav\u00e9s de un promotor. En Madrid y Barcelona es muy habitual entrar gratis hasta las 2:00 apunt\u00e1ndote con antelaci\u00f3n."),
            ("3. Contacta con promotores locales", "Cada club tiene <b>promotores independientes</b> que trabajan por comisi\u00f3n. Ellos consiguen descuentos exclusivos, entrada VIP sin cola o incluso gratis a cambio de que llenes con tu grupo. Los encuentras en Instagram (buscar por hashtags como #promoibiza, #promomadrid). \u00bfQui\u00e9n va? tiene un sistema de <a href=\"/feed\">c\u00f3digo referido</a> que ahorra dinero a ambas partes."),
            ("4. Aprovecha noches gratis y \"chicas gratis\"", "Muchas discotecas en Espa\u00f1a tienen <b>noches con entrada libre</b> entre semana (jueves universitarios) o promociones tipo <b>\"chicas gratis hasta cierta hora\"</b>. Consulta la agenda semanal para no perderte estos d\u00edas."),
            ("5. Reserva mesa entre amigos", "Si vais 6-10 personas, la <b>mesa VIP</b> puede salir m\u00e1s barata que pagar entrada + copas individualmente. Una mesa desde 400\u20ac incluye entrada, botella y acceso r\u00e1pido para todo el grupo. En clubs de Marbella y Puerto Ban\u00fas es especialmente rentable."),
            ("6. Suscr\u00edbete a newsletters y apps", "Los clubs mandan <b>c\u00f3digos descuento</b> por email y notificaciones push. Descarga <a href=\"/feed\">\u00bfQui\u00e9n va?</a> y activa las notificaciones para recibir alertas de bajadas de precio, entradas de \u00faltima hora y guest-list gratis."),
            ("7. Ve pronto y evita fechas top", "Las mismas discotecas cobran precios distintos seg\u00fan la noche. Un mi\u00e9rcoles en Amnesia puede costar 30\u20ac mientras que un s\u00e1bado con David Guetta pasa de 100\u20ac. Ve en d\u00edas laborables o fuera de fechas top (agosto en Ibiza) y ahorra hasta un 60%."),
        ],
        "faq": [
            ("\u00bfC\u00f3mo entrar gratis a una discoteca?", "Ap\u00fantate a la guest-list del club antes de las 23:00, contacta con un promotor local, o busca noches con entrada libre entre semana (jueves universitarios, promos de \"chicas gratis\")."),
            ("\u00bfCu\u00e1nto se ahorra comprando entrada online?", "Entre un 20% y un 40% respecto a la taquilla, dependiendo del club. Adem\u00e1s te evitas la cola de compra. Los precios pre-venta iniciales suelen ser los m\u00e1s baratos."),
            ("\u00bfQu\u00e9 es un promotor de discoteca?", "Un intermediario independiente que trabaja por comisi\u00f3n consiguiendo p\u00fablico. A cambio ofrece descuentos, entrada VIP o gratis. Se contactan por Instagram o apps especializadas."),
            ("\u00bfLas mesas VIP salen m\u00e1s baratas que la entrada?", "Depende del tama\u00f1o del grupo. Si vais 8-10 personas, una mesa desde 500\u20ac (con botella) puede salir m\u00e1s barata que entrada + copas individuales, y ganas comodidad y acceso r\u00e1pido."),
            ("\u00bfCu\u00e1ndo son m\u00e1s baratas las entradas de discoteca?", "Entre semana (mi\u00e9rcoles y jueves), en pre-venta anticipada, en meses de baja temporada (mayo, octubre en Ibiza) y en las primeras horas de apertura."),
        ],
        "related_cities": ["ibiza", "madrid", "barcelona", "palma", "marbella"],
    },
    "donde-salir-esta-noche-espana": {
        "title": "¿Dónde salir esta noche en España? Fiestas de hoy por ciudad",
        "description": "Guía rápida para decidir dónde salir esta noche: las mejores fiestas y discotecas abiertas hoy en Madrid, Barcelona, Ibiza, Palma y Marbella, y con qué amigos vas.",
        "published": "2026-08-08",
        "updated": "2026-08-08",
        "sections": [
            ("Cómo decidir el plan de esta noche en 2 minutos", "La clave para no quedarte en casa es ver de un vistazo <b>qué está abierto hoy</b> y <b>qué amigos van</b>. En <a href=\"/feed\">¿Quién va?</a> filtras por tu ciudad y por \"esta noche\", ves horarios y precios reales de cada discoteca y descubres a qué fiesta van tus amigos. Así el plan se decide solo: vas donde está tu gente."),
            ("Fiestas esta noche en Madrid", "Entre semana Madrid nunca duerme: Kapital, Teatro Barceló, Opium e Icon suelen tener noche todos los días, y los jueves universitarios llenan Malasaña y Gran Vía. Mira las <a href=\"/fiestas/madrid/esta-noche\">fiestas de esta noche en Madrid</a> con precios actualizados."),
            ("Fiestas esta noche en Barcelona e Ibiza", "En Barcelona, Opium, Pacha, Shôko y Razzmatazz marcan la agenda nocturna del Port Olímpic. En Ibiza (mayo-octubre) cada día tiene su fiesta icónica en Pacha, Amnesia, Hï o [UNVRS]. Consulta <a href=\"/fiestas/barcelona/esta-noche\">Barcelona esta noche</a> e <a href=\"/fiestas/ibiza/esta-noche\">Ibiza esta noche</a>."),
            ("Fiestas esta noche en Palma y Marbella", "Palma de Mallorca reparte la noche entre el Paseo Marítimo, Tito's y Magaluf, mientras Marbella y Puerto Banús ofrecen el clubbing más premium (Olivia Valere, Pangea, Nikki Beach). Revisa <a href=\"/fiestas/palma/esta-noche\">Palma esta noche</a> y <a href=\"/fiestas/marbella/esta-noche\">Marbella esta noche</a>."),
        ],
        "faq": [
            ("¿Dónde puedo ver qué fiestas hay hoy cerca de mí?", "En ¿Quién va? eliges tu ciudad y el filtro \"esta noche\" para ver todas las discotecas y fiestas abiertas hoy, con horario, precio y qué amigos van a cada una."),
            ("¿A qué hora se sale de fiesta en España?", "Lo habitual es empezar con copas entre las 23:00 y las 00:30 y entrar a la discoteca a partir de la 01:00. Muchos clubs tienen entrada más barata o guest-list gratis si llegas antes de cierta hora."),
            ("¿Cómo sé a qué fiesta van mis amigos esta noche?", "En ¿Quién va? tus amigos marcan \"Voy\" o \"Me interesa\" en cada fiesta y tú lo ves en tiempo real, así puedes decidir el plan según dónde esté tu grupo."),
            ("¿Puedo comprar la entrada desde la app?", "Sí. En cada fiesta tienes el botón para conseguir la entrada online al precio actualizado, evitando la cola de taquilla."),
        ],
        "related_cities": ["madrid", "barcelona", "ibiza", "palma", "marbella"],
    },
    "mejores-fiestas-este-finde-espana": {
        "title": "Las mejores fiestas de este fin de semana en España",
        "description": "Todos los planes del finde en un sitio: las mejores fiestas y discotecas del fin de semana en Madrid, Barcelona, Ibiza, Palma y Marbella con precios y quién va.",
        "published": "2026-08-07",
        "updated": "2026-08-07",
        "sections": [
            ("Planea tu finde antes de que se agoten las entradas", "Las mejores fiestas del fin de semana vuelan: las fechas con DJ conocido se agotan días antes. Adelántate viendo la <a href=\"/feed\">agenda del finde</a> por ciudad, compara precios y asegúrate la entrada online (suele ser un 20-30% más barata que en taquilla)."),
            ("El finde en Madrid y Barcelona", "En Madrid, viernes y sábado llenan Fabrik, Kapital y las salas de Gran Vía; los macroeventos de techno son la gran cita del finde. En Barcelona, Opium y Pacha del Port Olímpic más Razzmatazz concentran el ambiente. Mira <a href=\"/fiestas/madrid/este-finde\">Madrid este finde</a> y <a href=\"/fiestas/barcelona/este-finde\">Barcelona este finde</a>."),
            ("El finde en Ibiza, Palma y Marbella", "Ibiza vive su punto álgido de viernes a domingo con las residencias top en Amnesia, Hï y Pacha. Palma reparte fiesta por toda la isla y Marbella enciende sus clubs de lujo con headliners internacionales en verano. Consulta <a href=\"/fiestas/ibiza/este-finde\">Ibiza este finde</a>, <a href=\"/fiestas/palma/este-finde\">Palma este finde</a> y <a href=\"/fiestas/marbella/este-finde\">Marbella este finde</a>."),
            ("Sal con tu grupo, no en solitario", "El mejor finde es el que compartes. En ¿Quién va? ves a qué fiestas van tus amigos, te avisamos cuando alguien de tu grupo se apunta a un plan y podéis coordinar la noche desde la app para no perderos entre tanta oferta."),
        ],
        "faq": [
            ("¿Cuáles son las mejores fiestas de este fin de semana?", "Depende de tu ciudad. En ¿Quién va? tienes la agenda del finde de Madrid, Barcelona, Ibiza, Palma y Marbella ordenada por fecha, con precios reales y qué amigos van a cada fiesta."),
            ("¿Conviene comprar la entrada con antelación para el finde?", "Sí. Las fiestas del fin de semana con DJ conocido suelen agotarse, y comprar online anticipado es más barato que en taquilla y te evita la cola."),
            ("¿Qué ciudad tiene mejor ambiente de fiesta el fin de semana?", "En verano Ibiza y Marbella son imbatibles; durante todo el año Madrid y Barcelona tienen la escena más constante. Palma sube muchísimo en temporada alta."),
            ("¿Cómo organizo el finde con mis amigos?", "En ¿Quién va? cada uno marca las fiestas a las que va y todos lo veis en tiempo real, así elegís el plan donde esté vuestro grupo y compráis la entrada juntos."),
        ],
        "related_cities": ["ibiza", "madrid", "barcelona", "palma", "marbella"],
    },
}


# English & German translations of the top tourist-facing evergreen guides.
_BLOG_POSTS_L10N = {
    "en": {
        "best-parties-ibiza-summer": {
            "title": "Best parties in Ibiza this summer: complete 2025 guide",
            "description": "Discover the best parties and clubs in Ibiza this summer: Pacha, Ushua\u00efa, Amnesia, H\u00ef Ibiza, [UNVRS] and DC-10 with times, prices and tips.",
            "hero_image": "https://res.cloudinary.com/dh4byqvbb/image/upload/w_1200,f_auto,q_auto/v1/quienva/blog/ibiza-summer.jpg",
            "published": "2025-06-15", "updated": "2025-07-01",
            "city": "Ibiza", "city_slug": "ibiza",
            "sections": [
                ("Ibiza's most iconic nightclubs", "Ibiza packs some of the world's best clubs into barely 40 km of coastline. <b>Pacha Ibiza</b> has set the pace of international clubbing since 1973 and is still a benchmark thanks to its legendary parties. <b>Ushua\u00efa Ibiza</b>, on Playa d'en Bossa, offers the unique open-air club experience with the biggest DJs on the planet. <b>Amnesia</b> is the techno mecca with two giant rooms and the famous Terrace, while <b>H\u00ef Ibiza</b>, Ushua\u00efa's sister club, was named the world's best club several years in a row. Add <b>[UNVRS]</b>, <b>DC-10</b> (underground techno cult), <b>Eden</b> and <b>Club Chinois</b> and the line-up covers every genre."),
                ("Top DJs of summer 2025 in Ibiza", "David Guetta continues his iconic F*** Me I'm Famous residency at Ushua\u00efa; Solomun stays at Pacha with his Sunday Special; Marco Carola brings Music On to Amnesia; Black Coffee holds his residency at H\u00ef Ibiza; Circoloco takes over DC-10 on Mondays; and ANTS returns to Ushua\u00efa on Saturdays with a techno line-up. Check the updated weekly agenda on <a href=\"/en/parties/ibiza\">our Ibiza parties page</a>."),
                ("How much a night out in Ibiza costs", "The average ticket in 2025 ranges from <b>\u20ac40 to \u20ac90</b> depending on the DJ and the club. Top dates with headliners (David Guetta, Calvin Harris, Solomun) can top <b>\u20ac120</b>. Drinks inside the club are around <b>\u20ac18-25</b> and a table bottle starts at \u20ac400. Tip: buying online in advance is usually 20-30% cheaper than at the door, and some nights have free guest-list until a certain hour."),
                ("How to get to Ibiza's clubs", "The <b>Discob\u00fas</b> (line 9) connects Ibiza Town, San Antonio and Playa d'en Bossa all night for \u20ac4. A taxi between areas costs <b>\u20ac20-40</b>. Many clubs offer a free private shuttle from partner hotels. If you drive, parking in Playa d'en Bossa or San Antonio is usually free but fills up early on weekends."),
                ("Tips to enjoy the Ibiza night", "1) Book your ticket online in advance to save. 2) Arrive early (11pm-midnight) to skip the queue and pay less. 3) Stay hydrated: bottled water in the club is about \u20ac10 but essential. 4) Combine a club night with a beach-club day (Blue Marlin, Nassau, Nikki Beach) for the full Ibiza effect. 5) On <b>\u00bfQui\u00e9n va?</b> you can see which friends have a ticket for the same club and plan the night together."),
            ],
            "faq": [
                ("What are the 5 best clubs in Ibiza?", "The 5 best clubs in Ibiza are Pacha, Ushua\u00efa, Amnesia, H\u00ef Ibiza and DC-10. All rank among the world's clubbing elite and host residencies with the biggest DJs every summer."),
                ("When does the Ibiza party season start?", "The season officially kicks off in May with the Opening Parties and ends in early October with the Closing Parties. Peak months are July and August."),
                ("How much is a club ticket in Ibiza?", "Between \u20ac40 and \u20ac90 on average in 2025. Dates with world-famous DJs (Guetta, Solomun, Black Coffee) can top \u20ac120. Buying online in advance is cheaper."),
                ("Which is the best day to party in Ibiza?", "Each day has its iconic party: Monday Circoloco at DC-10, Tuesday ANTS at Ushua\u00efa, Wednesday Pyramid at Amnesia, Thursday David Guetta at Ushua\u00efa, Friday Music On at Amnesia, Saturday H\u00ef Ibiza and Sunday Solomun at Pacha."),
                ("How do I reach Ibiza's clubs without a car?", "The Discob\u00fas (line 9) runs along the whole coast until dawn for \u20ac4. Taxis cost \u20ac20-40 depending on distance. Many hotels offer a free shuttle to partner clubs."),
            ],
            "related_cities": ["madrid", "barcelona", "palma"],
        },
        "cheap-nightclub-tickets": {
            "title": "How to get cheap (or free) nightclub tickets in 2025",
            "description": "Tricks and tips to get cheaper or free nightclub tickets: VIP lists, guest-list, online pre-sale, promoters, apps and discount codes.",
            "hero_image": "https://res.cloudinary.com/dh4byqvbb/image/upload/w_1200,f_auto,q_auto/v1/quienva/blog/tickets-tips.jpg",
            "published": "2025-06-05", "updated": "2025-07-01",
            "city": None, "city_slug": None,
            "sections": [
                ("1. Buy your ticket online in advance", "The most effective trick. In almost every club in <b>Ibiza, Marbella, Madrid and Barcelona</b>, the advance online ticket costs <b>20-40% less</b> than at the door. You also skip the queue. Many clubs open a pre-sale with a reduced price for the first 100-500 tickets."),
                ("2. Join the guest-list or free list", "Almost every club has a free <b>guest-list</b> until a certain hour (usually between 11pm and 00:30). Just sign up on the club's website, on Instagram or through a promoter. In Madrid and Barcelona it's very common to get in free until 2am by signing up in advance."),
                ("3. Contact local promoters", "Every club has independent <b>promoters</b> who work on commission. They get you exclusive discounts, skip-the-line VIP entry or even free entry in exchange for filling the club with your group. Find them on Instagram (hashtags like #promoibiza, #promomadrid). \u00bfQui\u00e9n va? has a <a href=\"/feed\">referral code</a> system that saves money for both sides."),
                ("4. Take advantage of free nights and \"ladies free\"", "Many clubs in Spain have <b>free-entry nights</b> midweek (university Thursdays) or promos like <b>\"ladies free until a certain hour\"</b>. Check the weekly agenda so you don't miss these days."),
                ("5. Book a table with friends", "If you're 6-10 people, a <b>VIP table</b> can work out cheaper than paying entry + drinks individually. A table from \u20ac400 includes entry, a bottle and fast access for the whole group. In Marbella and Puerto Ban\u00fas clubs it's especially worth it."),
                ("6. Subscribe to newsletters and apps", "Clubs send <b>discount codes</b> by email and push. Download <a href=\"/feed\">\u00bfQui\u00e9n va?</a> and turn on notifications to get alerts for price drops, last-minute tickets and free guest-list."),
                ("7. Go early and avoid top dates", "The same clubs charge different prices depending on the night. A Wednesday at Amnesia can cost \u20ac30 while a Saturday with David Guetta tops \u20ac100. Go on weekdays or outside top dates (August in Ibiza) and save up to 60%."),
            ],
            "faq": [
                ("How do I get into a nightclub for free?", "Sign up for the club's guest-list before 11pm, contact a local promoter, or look for free-entry nights midweek (university Thursdays, \"ladies free\" promos)."),
                ("How much do I save buying online?", "Between 20% and 40% versus the door, depending on the club. You also skip the queue. Early pre-sale prices are usually the cheapest."),
                ("What is a club promoter?", "An independent middleman who works on commission bringing in crowds. In exchange they offer discounts, VIP or free entry. You reach them via Instagram or specialised apps."),
                ("Are VIP tables cheaper than tickets?", "It depends on group size. If you're 8-10 people, a table from \u20ac500 (with a bottle) can be cheaper than individual entry + drinks, plus you get comfort and fast access."),
                ("When are nightclub tickets cheapest?", "Midweek (Wednesday and Thursday), in early pre-sale, in low-season months (May, October in Ibiza) and in the first opening hours."),
            ],
            "related_cities": ["ibiza", "madrid", "barcelona", "palma", "marbella"],
        },
    },
    "de": {
        "beste-partys-ibiza-sommer": {
            "title": "Beste Partys auf Ibiza in diesem Sommer: kompletter Guide 2025",
            "description": "Entdecke die besten Partys und Clubs auf Ibiza in diesem Sommer: Pacha, Ushua\u00efa, Amnesia, H\u00ef Ibiza, [UNVRS] und DC-10 mit Zeiten, Preisen und Tipps.",
            "hero_image": "https://res.cloudinary.com/dh4byqvbb/image/upload/w_1200,f_auto,q_auto/v1/quienva/blog/ibiza-summer.jpg",
            "published": "2025-06-15", "updated": "2025-07-01",
            "city": "Ibiza", "city_slug": "ibiza",
            "sections": [
                ("Die ikonischsten Clubs auf Ibiza", "Ibiza vereint einige der besten Clubs der Welt auf kaum 40 km K\u00fcste. <b>Pacha Ibiza</b> gibt seit 1973 den Takt des internationalen Clubbings vor und ist dank seiner legend\u00e4ren Partys weiterhin eine Referenz. <b>Ushua\u00efa Ibiza</b> an der Playa d'en Bossa bietet das einzigartige Open-Air-Club-Erlebnis mit den gr\u00f6\u00dften DJs des Planeten. <b>Amnesia</b> ist das Techno-Mekka mit zwei riesigen S\u00e4len und der ber\u00fchmten Terrace, w\u00e4hrend <b>H\u00ef Ibiza</b>, der Schwesterclub von Ushua\u00efa, mehrere Jahre in Folge zum besten Club der Welt gek\u00fcrt wurde. Dazu <b>[UNVRS]</b>, <b>DC-10</b> (Underground-Techno-Kult), <b>Eden</b> und <b>Club Chinois</b> \u2013 das Programm deckt jedes Genre ab."),
                ("Die Top-DJs im Sommer 2025 auf Ibiza", "David Guetta setzt seine ikonische Residency F*** Me I'm Famous im Ushua\u00efa fort; Solomun bleibt mit seinem Sunday Special im Pacha; Marco Carola bringt Music On ins Amnesia; Black Coffee h\u00e4lt seine Residency im H\u00ef Ibiza; Circoloco \u00fcbernimmt montags das DC-10; und ANTS kehrt samstags mit Techno ins Ushua\u00efa zur\u00fcck. Sieh dir die aktuelle W\u00f6chenagenda auf <a href=\"/de/partys/ibiza\">unserer Ibiza-Party-Seite</a> an."),
                ("Was eine Partynacht auf Ibiza kostet", "Der durchschnittliche Eintritt liegt 2025 zwischen <b>40\u20ac und 90\u20ac</b>, je nach DJ und Club. Top-Termine mit Headlinern (David Guetta, Calvin Harris, Solomun) k\u00f6nnen <b>120\u20ac</b> \u00fcbersteigen. Getr\u00e4nke im Club kosten rund <b>18-25\u20ac</b>, eine Tischflasche ab 400\u20ac. Tipp: online im Voraus kaufen ist meist 20-30% g\u00fcnstiger als an der Abendkasse, und manche N\u00e4chte haben bis zu einer bestimmten Uhrzeit kostenlose Gästeliste."),
                ("So kommst du zu den Clubs auf Ibiza", "Der <b>Discob\u00fas</b> (Linie 9) verbindet Ibiza-Stadt, San Antonio und Playa d'en Bossa die ganze Nacht f\u00fcr 4\u20ac. Ein Taxi zwischen den Zonen kostet <b>20-40\u20ac</b>. Viele Clubs bieten einen kostenlosen Shuttle von Partnerhotels. Wer f\u00e4hrt: Parken in Playa d'en Bossa oder San Antonio ist meist gratis, aber am Wochenende schnell voll."),
                ("Tipps f\u00fcr die Nacht auf Ibiza", "1) Buche dein Ticket im Voraus online, um zu sparen. 2) Komm fr\u00fch (23:00-00:00), um die Schlange zu vermeiden und weniger zu zahlen. 3) Bleib hydriert: Wasser im Club kostet ca. 10\u20ac, ist aber wichtig. 4) Kombiniere eine Clubnacht mit einem Beachclub-Tag (Blue Marlin, Nassau, Nikki Beach) f\u00fcr das volle Ibiza-Gef\u00fchl. 5) Auf <b>\u00bfQui\u00e9n va?</b> siehst du, welche Freunde ein Ticket f\u00fcr denselben Club haben, und plant die Nacht gemeinsam."),
            ],
            "faq": [
                ("Was sind die 5 besten Clubs auf Ibiza?", "Die 5 besten Clubs auf Ibiza sind Pacha, Ushua\u00efa, Amnesia, H\u00ef Ibiza und DC-10. Alle geh\u00f6ren zur Weltspitze des Clubbings und bieten jeden Sommer Residencies mit den gr\u00f6\u00dften DJs."),
                ("Wann beginnt die Party-Saison auf Ibiza?", "Die Saison startet offiziell im Mai mit den Opening Parties und endet Anfang Oktober mit den Closing Parties. Hauptmonate sind Juli und August."),
                ("Wie viel kostet ein Club-Ticket auf Ibiza?", "Im Schnitt zwischen 40\u20ac und 90\u20ac im Jahr 2025. Termine mit weltbekannten DJs (Guetta, Solomun, Black Coffee) k\u00f6nnen 120\u20ac \u00fcbersteigen. Online im Voraus ist g\u00fcnstiger."),
                ("Welcher ist der beste Tag zum Feiern auf Ibiza?", "Jeder Tag hat seine ikonische Party: Montag Circoloco im DC-10, Dienstag ANTS im Ushua\u00efa, Mittwoch Pyramid im Amnesia, Donnerstag David Guetta im Ushua\u00efa, Freitag Music On im Amnesia, Samstag H\u00ef Ibiza und Sonntag Solomun im Pacha."),
                ("Wie komme ich ohne Auto zu den Clubs auf Ibiza?", "Der Discob\u00fas (Linie 9) f\u00e4hrt die ganze K\u00fcste entlang bis zum Morgengrauen f\u00fcr 4\u20ac. Taxis kosten je nach Entfernung 20-40\u20ac. Viele Hotels bieten einen kostenlosen Shuttle zu Partnerclubs."),
            ],
            "related_cities": ["madrid", "barcelona", "palma"],
        },
        "guenstige-disco-tickets": {
            "title": "So bekommst du g\u00fcnstige (oder kostenlose) Disco-Tickets 2025",
            "description": "Tricks und Tipps f\u00fcr g\u00fcnstigere oder kostenlose Disco-Tickets: VIP-Listen, G\u00e4steliste, Online-Vorverkauf, Promoter, Apps und Rabattcodes.",
            "hero_image": "https://res.cloudinary.com/dh4byqvbb/image/upload/w_1200,f_auto,q_auto/v1/quienva/blog/tickets-tips.jpg",
            "published": "2025-06-05", "updated": "2025-07-01",
            "city": None, "city_slug": None,
            "sections": [
                ("1. Kauf dein Ticket im Voraus online", "Der wirksamste Trick. In fast jedem Club in <b>Ibiza, Marbella, Madrid und Barcelona</b> kostet das Online-Ticket im Voraus <b>20-40% weniger</b> als an der Abendkasse. Au\u00dferdem sparst du dir die Schlange. Viele Clubs starten einen Vorverkauf mit reduziertem Preis f\u00fcr die ersten 100-500 Tickets."),
                ("2. Trag dich in die G\u00e4steliste ein", "Fast jeder Club hat bis zu einer bestimmten Uhrzeit (meist zwischen 23:00 und 00:30) eine kostenlose <b>G\u00e4steliste</b>. Einfach auf der Website des Clubs, auf Instagram oder \u00fcber einen Promoter anmelden. In Madrid und Barcelona kommt man mit Voranmeldung oft bis 2:00 gratis rein."),
                ("3. Kontaktiere lokale Promoter", "Jeder Club hat unabh\u00e4ngige <b>Promoter</b>, die auf Provision arbeiten. Sie besorgen exklusive Rabatte, VIP-Eintritt ohne Schlange oder sogar Gratis-Eintritt, wenn du mit deiner Gruppe f\u00fcllst. Du findest sie auf Instagram (Hashtags wie #promoibiza, #promomadrid). \u00bfQui\u00e9n va? hat ein <a href=\"/feed\">Empfehlungscode</a>-System, das beiden Seiten Geld spart."),
                ("4. Nutze Gratis-N\u00e4chte und \"Ladies free\"", "Viele Clubs in Spanien haben unter der Woche <b>N\u00e4chte mit freiem Eintritt</b> (Uni-Donnerstage) oder Aktionen wie <b>\"Ladies free bis zu einer bestimmten Uhrzeit\"</b>. Schau in die W\u00f6chenagenda, um diese Tage nicht zu verpassen."),
                ("5. Reserviere einen Tisch mit Freunden", "Wenn ihr 6-10 Personen seid, kann ein <b>VIP-Tisch</b> g\u00fcnstiger sein als Eintritt + Getr\u00e4nke einzeln. Ein Tisch ab 400\u20ac umfasst Eintritt, eine Flasche und schnellen Zugang f\u00fcr die ganze Gruppe. In Clubs in Marbella und Puerto Ban\u00fas lohnt es sich besonders."),
                ("6. Abonniere Newsletter und Apps", "Clubs verschicken <b>Rabattcodes</b> per E-Mail und Push. Lade <a href=\"/feed\">\u00bfQui\u00e9n va?</a> herunter und aktiviere Benachrichtigungen f\u00fcr Preissenkungen, Last-Minute-Tickets und kostenlose G\u00e4steliste."),
                ("7. Komm fr\u00fch und meide Top-Termine", "Dieselben Clubs verlangen je nach Nacht unterschiedliche Preise. Ein Mittwoch im Amnesia kann 30\u20ac kosten, ein Samstag mit David Guetta \u00fcber 100\u20ac. Geh an Wochentagen oder au\u00dferhalb der Top-Termine (August auf Ibiza) und spare bis zu 60%."),
            ],
            "faq": [
                ("Wie komme ich gratis in eine Disco?", "Trag dich vor 23:00 in die G\u00e4steliste des Clubs ein, kontaktiere einen lokalen Promoter oder such nach N\u00e4chten mit freiem Eintritt unter der Woche (Uni-Donnerstage, \"Ladies free\"-Aktionen)."),
                ("Wie viel spare ich beim Online-Kauf?", "Zwischen 20% und 40% gegen\u00fcber der Abendkasse, je nach Club. Au\u00dferdem sparst du dir die Schlange. Die ersten Vorverkaufspreise sind meist am g\u00fcnstigsten."),
                ("Was ist ein Club-Promoter?", "Ein unabh\u00e4ngiger Vermittler, der auf Provision Publikum bringt. Daf\u00fcr bietet er Rabatte, VIP- oder Gratis-Eintritt. Man erreicht sie \u00fcber Instagram oder spezialisierte Apps."),
                ("Sind VIP-Tische g\u00fcnstiger als Tickets?", "Kommt auf die Gruppengr\u00f6\u00dfe an. Bei 8-10 Personen kann ein Tisch ab 500\u20ac (mit Flasche) g\u00fcnstiger sein als Eintritt + Getr\u00e4nke einzeln \u2013 plus Komfort und schneller Zugang."),
                ("Wann sind Disco-Tickets am g\u00fcnstigsten?", "Unter der Woche (Mittwoch und Donnerstag), im fr\u00fchen Vorverkauf, in Nebensaison-Monaten (Mai, Oktober auf Ibiza) und in den ersten \u00d6ffnungsstunden."),
            ],
            "related_cities": ["ibiza", "madrid", "barcelona", "palma", "marbella"],
        },
    },
}

# (es_slug, en_slug, de_slug) for the translated evergreen guides.
_GUIDE_L10N_MAP = [
    ("mejores-fiestas-ibiza-verano", "best-parties-ibiza-summer", "beste-partys-ibiza-sommer"),
    ("como-conseguir-entradas-discoteca-baratas", "cheap-nightclub-tickets", "guenstige-disco-tickets"),
]
_GUIDE_SLUG2ES = {}
for _es, _en, _de in _GUIDE_L10N_MAP:
    _GUIDE_SLUG2ES[("es", _es)] = _es
    _GUIDE_SLUG2ES[("en", _en)] = _es
    _GUIDE_SLUG2ES[("de", _de)] = _es


def _guide_hreflang(front: str, es_slug: str):
    for _es, _en, _de in _GUIDE_L10N_MAP:
        if _es == es_slug:
            return {"es": _blog_url(front, _es, "es"),
                    "en": _blog_url(front, _en, "en"),
                    "de": _blog_url(front, _de, "de")}
    return None



def _blog_url(front: str, slug: str = "", lang: str = "es") -> str:
    base = {"es": f"{front}/blog", "en": f"{front}/en/blog", "de": f"{front}/de/blog"}.get(lang, f"{front}/blog")
    if not slug:
        return base
    return f"{base}/{slug}"


def _blog_article_jsonld(post: dict, canonical: str, front: str, lang: str = "es") -> str:
    """Article + BlogPosting JSON-LD (Google-friendly)."""
    obj = {
        "@context": "https://schema.org",
        "@type": "BlogPosting",
        "headline": post["title"],
        "description": post["description"],
        "image": post.get("hero_image") or f"{front}/icons/icon-512.png",
        "datePublished": post["published"],
        "dateModified": post.get("updated") or post["published"],
        "inLanguage": lang,
        "url": canonical,
        "mainEntityOfPage": {"@type": "WebPage", "@id": canonical},
        "author": {"@type": "Organization", "name": "\u00bfQui\u00e9n va?", "url": front + "/"},
        "publisher": {
            "@type": "Organization", "name": "\u00bfQui\u00e9n va?", "url": front + "/",
            "logo": {"@type": "ImageObject", "url": front + "/icons/icon-512.png", "width": 512, "height": 512},
        },
    }
    return json.dumps(obj, ensure_ascii=False)


def _blog_common_css() -> str:
    return (
        ".blogwrap{max-width:820px;margin:0 auto;padding:0 20px}"
        ".blogtitle{font-size:36px;line-height:1.15;margin:28px 0 12px;color:#fff;font-weight:800;letter-spacing:-0.5px}"
        ".blogmeta{color:#9aa;font-size:13px;margin-bottom:24px}"
        ".blogmeta a{color:#c9b3ff;text-decoration:none}"
        ".bloghero{width:100%;height:auto;border-radius:16px;margin:0 0 28px;display:block;object-fit:cover;max-height:420px}"
        ".blogsec h2{font-size:24px;margin:34px 0 12px;color:#fff;font-weight:700}"
        ".blogsec p{color:#d8dde3;line-height:1.65;font-size:16.5px;margin:0 0 14px}"
        ".blogsec a{color:#c9b3ff;text-decoration:underline}"
        ".blogsec b{color:#fff;font-weight:600}"
        ".bloglist{list-style:none;padding:0;margin:12px 0 28px;display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px}"
        ".blogcard{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);border-radius:16px;overflow:hidden}"
        ".blogcard a{display:block;padding:18px;color:#fff;text-decoration:none}"
        ".blogcard b{display:block;font-size:16px;margin-bottom:6px;line-height:1.3}"
        ".blogcard small{color:#9aa;font-size:12.5px;line-height:1.4;display:block}"
        ".blogfaq{margin:36px 0}"
        ".blogfaq h2{font-size:24px;margin:0 0 12px;color:#fff}"
        ".blogfaq details{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.08);border-radius:12px;padding:14px 16px;margin-bottom:8px}"
        ".blogfaq summary{color:#fff;font-weight:600;cursor:pointer;font-size:15.5px}"
        ".blogfaq details[open] summary{margin-bottom:8px}"
        ".blogfaq p{color:#d8dde3;margin:0;font-size:15px;line-height:1.55}"
        ".relband{margin:36px 0;padding:20px;background:rgba(160,120,255,.08);border:1px solid rgba(160,120,255,.2);border-radius:16px}"
        ".relband b{color:#fff;display:block;margin-bottom:10px}"
        ".relband a{display:inline-block;margin:4px 8px 4px 0;padding:6px 12px;background:rgba(255,255,255,.06);border-radius:20px;color:#fff;text-decoration:none;font-size:14px}"
    )


# ---------------------------------------------------------------------------
# AUTO BLOG — a self-updating "agenda del finde" post per city. Content is built
# live from this weekend's events, so it stays fresh every week with zero manual
# work. Indexed like a normal blog post (Article + FAQ + Breadcrumb).
# ---------------------------------------------------------------------------
_AGENDA_L10N = {
    "es": {
        "slug": "agenda-fiestas-finde-{cs}",
        "title": "Fiestas de este fin de semana en {label}: agenda actualizada",
        "desc": "Agenda actualizada de las mejores fiestas y discotecas de este fin de semana en {label}: horarios, precios y qu\u00e9 amigos van. Con \u00bfQui\u00e9n va?",
        "sec1": "Las mejores fiestas de este fin de semana en {label}",
        "intro": "Estas son las fiestas destacadas de este fin de semana en {label}, ordenadas por fecha. Toca cualquiera para ver horario, precio y qu\u00e9 amigos van:",
        "empty": 'A\u00fan no hay fiestas confirmadas para este finde en {label}. Consulta la <a href="{city}">agenda completa de {label}</a> o vuelve en unas horas: la actualizamos constantemente.',
        "sec2": "Sal con tu grupo, no en solitario",
        "sec2_body": 'En <b>\u00bfQui\u00e9n va?</b> no solo ves qu\u00e9 fiestas hay este fin de semana en {label}: ves a cu\u00e1les van tus amigos, recibes un aviso cuando alguien de tu grupo se apunta y compras la entrada online al precio actualizado. As\u00ed el finde se organiza solo. Mira la <a href="{wk}">agenda del finde en {label}</a> y <a href="{tn}">las fiestas de esta noche</a>.',
        "faq": [
            ("\u00bfQu\u00e9 fiestas hay este fin de semana en {label}?", "Ahora mismo hay {n} planes en {label} para este finde con horarios y precios actualizados. \u00c1brelos en \u00bfQui\u00e9n va? para ver a qu\u00e9 va cada uno de tus amigos."),
            ("\u00bfCon qu\u00e9 antelaci\u00f3n conviene comprar la entrada?", "Las fiestas del finde con DJ conocido suelen agotarse; comprar online anticipado suele ser m\u00e1s barato que en taquilla y te evita la cola."),
            ("\u00bfC\u00f3mo veo a qu\u00e9 fiesta van mis amigos?", "En \u00bfQui\u00e9n va? cada amigo marca \u201cVoy\u201d o \u201cMe interesa\u201d y t\u00fa lo ves en tiempo real, as\u00ed eliges el plan donde est\u00e9 tu grupo."),
        ],
    },
    "en": {
        "slug": "weekend-parties-{cs}",
        "title": "Parties this weekend in {label}: live agenda",
        "desc": "The updated agenda of the best parties and clubs this weekend in {label}: times, real prices and which friends are going. On \u00bfQui\u00e9n va?",
        "sec1": "The best parties this weekend in {label}",
        "intro": "These are the top parties this weekend in {label}, sorted by date. Tap any of them to see the time, price and which friends are going:",
        "empty": 'No parties confirmed yet for this weekend in {label}. Check the <a href="{city}">full {label} agenda</a> or come back in a few hours: we update it constantly.',
        "sec2": "Go out with your crew, not alone",
        "sec2_body": 'On <b>\u00bfQui\u00e9n va?</b> you don\u2019t just see which parties are on this weekend in {label}: you see which ones your friends are going to, get a heads-up when someone from your group joins a plan, and buy your ticket online at the up-to-date price. Check the <a href="{wk}">{label} weekend agenda</a> and <a href="{tn}">tonight\u2019s parties</a>.',
        "faq": [
            ("What parties are on this weekend in {label}?", "Right now there are {n} plans in {label} for this weekend with up-to-date times and prices. Open them on \u00bfQui\u00e9n va? to see which of your friends are going."),
            ("How far in advance should I buy tickets?", "Weekend parties with a well-known DJ tend to sell out; buying online in advance is usually cheaper than at the door and saves you the queue."),
            ("How do I see which party my friends are going to?", "On \u00bfQui\u00e9n va? each friend marks \u201cGoing\u201d or \u201cInterested\u201d and you see it in real time, so you pick the plan where your crew is."),
        ],
    },
    "de": {
        "slug": "wochenend-partys-{cs}",
        "title": "Partys an diesem Wochenende in {label}: aktuelle \u00dcbersicht",
        "desc": "Die aktuelle \u00dcbersicht der besten Partys und Clubs an diesem Wochenende in {label}: Zeiten, echte Preise und welche Freunde hingehen. Auf \u00bfQui\u00e9n va?",
        "sec1": "Die besten Partys an diesem Wochenende in {label}",
        "intro": "Das sind die Top-Partys an diesem Wochenende in {label}, nach Datum sortiert. Tippe auf eine, um Uhrzeit, Preis und welche Freunde hingehen zu sehen:",
        "empty": 'Noch keine Partys f\u00fcr dieses Wochenende in {label} best\u00e4tigt. Sieh dir die <a href="{city}">komplette Agenda von {label}</a> an oder komm in ein paar Stunden wieder: Wir aktualisieren sie st\u00e4ndig.',
        "sec2": "Geh mit deiner Crew aus, nicht allein",
        "sec2_body": 'Auf <b>\u00bfQui\u00e9n va?</b> siehst du nicht nur, welche Partys an diesem Wochenende in {label} laufen: Du siehst, zu welchen deine Freunde gehen, wirst benachrichtigt, wenn jemand aus deiner Gruppe zusagt, und kaufst dein Ticket online zum aktuellen Preis. Sieh dir die <a href="{wk}">Wochenend-Agenda von {label}</a> und <a href="{tn}">die Partys heute Abend</a> an.',
        "faq": [
            ("Welche Partys gibt es an diesem Wochenende in {label}?", "Aktuell gibt es {n} Pl\u00e4ne in {label} f\u00fcr dieses Wochenende mit aktuellen Zeiten und Preisen. \u00d6ffne sie auf \u00bfQui\u00e9n va?, um zu sehen, welche deiner Freunde hingehen."),
            ("Wie fr\u00fch sollte ich Tickets kaufen?", "Wochenend-Partys mit bekanntem DJ sind oft ausverkauft; online im Voraus zu kaufen ist meist g\u00fcnstiger als an der Abendkasse und erspart die Schlange."),
            ("Wie sehe ich, zu welcher Party meine Freunde gehen?", "Auf \u00bfQui\u00e9n va? markiert jeder Freund \u201eGehe hin\u201c oder \u201eInteressiert\u201c und du siehst es in Echtzeit, so w\u00e4hlst du den Plan, wo deine Crew ist."),
        ],
    },
}


def _agenda_meta(lang: str = "es") -> list:
    L = _AGENDA_L10N.get(lang, _AGENDA_L10N["es"])
    metas = []
    for c in SUPPORTED_CITIES:
        cs = _city_slug(c["id"])
        metas.append({
            "slug": L["slug"].format(cs=cs),
            "city_id": c["id"], "city_slug": cs, "label": c["label"], "lang": lang,
            "title": L["title"].format(label=c["label"]),
            "description": L["desc"].format(label=c["label"]),
        })
    return metas


_AGENDA_BY_SLUG: dict = {}


def _agenda_lookup(slug: str, lang: str = "es"):
    if lang not in _AGENDA_BY_SLUG:
        _AGENDA_BY_SLUG[lang] = {m["slug"]: m for m in _agenda_meta(lang)}
    return _AGENDA_BY_SLUG[lang].get(slug)


def _agenda_hreflang(front: str, city_slug: str) -> dict:
    """The 3 language URLs for a city's weekend-agenda post (for hreflang)."""
    return {l: _blog_url(front, _AGENDA_L10N[l]["slug"].format(cs=city_slug), l)
            for l in SEO_LANGS}


async def _build_agenda_post(meta: dict, front: str, lang: str = "es") -> dict:
    import html as _h
    e = _h.escape
    L = _AGENDA_L10N.get(lang, _AGENDA_L10N["es"])
    city_id, label, cs = meta["city_id"], meta["label"], meta["city_slug"]
    city_url = _city_paths(front, cs)[lang]
    wk_url = _city_tf_paths(front, cs, "weekend")[lang]
    tn_url = _city_tf_paths(front, cs, "tonight")[lang]
    events = await _events_for_timeframe(city_id, "weekend")
    if not events:
        events = await _upcoming_for_city(city_id, 12)
    rows = []
    for ev in events[:10]:
        u = _event_paths(front, ev.get("id", ""), _event_slug(ev))[lang]
        d = _es_share_date(ev.get("date", "")) if lang == "es" else (ev.get("date", "") or "")
        pl = _price_line(ev)
        pls = f" \u00b7 {e(pl)}" if pl else ""
        rows.append(f'<li><a href="{e(u)}"><b>{e(ev.get("name") or "Fiesta")}</b></a> \u2014 '
                    f'{e(ev.get("venue") or "")}, {e(d)}{pls}</li>')
    n = len(events)
    if rows:
        list_html = f'<p>{e(L["intro"].format(label=label))}</p><ul>' + "".join(rows) + "</ul>"
    else:
        list_html = "<p>" + L["empty"].format(label=e(label), city=e(city_url)) + "</p>"
    s2 = L["sec2_body"].format(label=e(label), wk=e(wk_url), tn=e(tn_url))
    sections = [(L["sec1"].format(label=label), list_html), (L["sec2"], s2)]
    faq = [(q.format(label=label), a.format(label=label, n=n)) for q, a in L["faq"]]
    now = datetime.now(ZoneInfo("Europe/Madrid")).date()
    monday = now - timedelta(days=now.weekday())
    return {
        "title": meta["title"], "description": meta["description"],
        "hero_image": f"{front}/og-city/{cs}.jpg",
        "published": monday.isoformat(), "updated": now.isoformat(),
        "city": label, "city_slug": cs, "lang": lang,
        "hreflang": _agenda_hreflang(front, cs),
        "sections": sections, "faq": faq,
        "related_cities": [x for x in ["madrid", "barcelona", "ibiza", "palma", "marbella"] if x != cs][:4],
    }



def _city_guides_block(front: str, slug_l: str, label: str, lang: str, e) -> str:
    """Internal-links block on each city page: weekend agenda (localised) + the
    Spanish evergreen guides for that city + the blog index. Boosts crawl depth
    and gives users more to explore."""
    links = []
    ag_slug = _AGENDA_L10N[lang]["slug"].format(cs=slug_l)
    ag_title = _AGENDA_L10N[lang]["title"].format(label=label)
    links.append(f'<a href="{e(_blog_url(front, ag_slug, lang))}">{e(ag_title)}</a>')
    if lang == "es":
        for slug, p in _BLOG_POSTS.items():
            if p.get("city_slug") == slug_l:
                links.append(f'<a href="{e(_blog_url(front, slug))}">{e(p["title"])}</a>')
    else:
        for slug, p in _BLOG_POSTS_L10N.get(lang, {}).items():
            if p.get("city_slug") == slug_l:
                links.append(f'<a href="{e(_blog_url(front, slug, lang))}">{e(p["title"])}</a>')
    idx_label = {"es": "Todas las gu\u00edas del blog", "en": "All blog guides",
                 "de": "Alle Blog-Guides"}.get(lang, "Blog")
    links.append(f'<a href="{e(_blog_url(front, lang=lang))}">{e(idx_label)}</a>')
    heading = {"es": f"Gu\u00edas y agenda de {label}",
               "en": f"{label} guides & weekend agenda",
               "de": f"{label}: Guides & Wochenend-Agenda"}.get(lang, label)
    return f'<div class="cities"><b>{e(heading)}</b>{"".join(links)}</div>'



_BLOG_UI = {
    "es": {"home": "Inicio", "blog": "Blog", "faq": "Preguntas frecuentes", "pub": "Publicado el",
           "upd": "Actualizado el", "explore": "Sigue explorando", "parties_in": "Fiestas en", "open": "Abrir \u00bfQui\u00e9n va?"},
    "en": {"home": "Home", "blog": "Blog", "faq": "FAQ", "pub": "Published", "upd": "Updated",
           "explore": "Keep exploring", "parties_in": "Parties in", "open": "Open \u00bfQui\u00e9n va?"},
    "de": {"home": "Start", "blog": "Blog", "faq": "H\u00e4ufige Fragen", "pub": "Ver\u00f6ffentlicht am",
           "upd": "Aktualisiert am", "explore": "Weiter st\u00f6bern", "parties_in": "Partys in", "open": "\u00bfQui\u00e9n va? \u00f6ffnen"},
}
_BLOG_IDX = {
    "es": {"title": "Blog: gu\u00edas de fiestas y discotecas en Espa\u00f1a | \u00bfQui\u00e9n va?",
           "desc": "Gu\u00edas y consejos para salir de fiesta: mejores discotecas de Ibiza, Madrid, Barcelona, Palma y Marbella; entradas baratas y agenda del finde por ciudad.",
           "h1": "Blog: gu\u00edas de fiestas por ciudad",
           "sub": "Aprende a moverte por la noche espa\u00f1ola: gu\u00edas por ciudad, precios reales, trucos de entradas y la agenda actualizada del finde.",
           "il": "Art\u00edculos del blog", "html_lang": "es"},
    "en": {"title": "Blog: party & nightclub guides in Spain | \u00bfQui\u00e9n va?",
           "desc": "Guides and tips to go out in Spain: the best clubs in Ibiza, Madrid, Barcelona, Palma and Marbella, plus this weekend's party agenda by city.",
           "h1": "Blog: weekend party agendas by city",
           "sub": "The updated weekend party agenda for every city in Spain, plus tips to make the most of the night.",
           "il": "Blog articles", "html_lang": "en"},
    "de": {"title": "Blog: Party- & Club-Guides in Spanien | \u00bfQui\u00e9n va?",
           "desc": "Guides und Tipps zum Ausgehen in Spanien: die besten Clubs in Ibiza, Madrid, Barcelona, Palma und Marbella, plus die Wochenend-Agenda pro Stadt.",
           "h1": "Blog: Wochenend-Party-Agenda pro Stadt",
           "sub": "Die aktuelle Wochenend-Party-Agenda f\u00fcr jede Stadt in Spanien und Tipps, um die Nacht optimal zu nutzen.",
           "il": "Blog-Artikel", "html_lang": "de"},
}


async def _render_blog_index(request: Request, lang: str = "es"):
    import html as _html
    e = _html.escape
    front = _frontend_base(request)
    UI = _BLOG_UI.get(lang, _BLOG_UI["es"])
    IDX = _BLOG_IDX.get(lang, _BLOG_IDX["es"])
    canonical = _blog_url(front, lang=lang)

    cards = []
    itemlist = []
    pos = 1
    # Auto-updating weekly "agenda del finde" posts first (freshest content).
    for m in _agenda_meta(lang):
        url = _blog_url(front, m["slug"], lang)
        cards.append(
            f'<li class="blogcard"><a href="{e(url)}"><b>{e(m["title"])}</b>'
            f'<small>{e(m["description"])}</small></a></li>'
        )
        itemlist.append({"@type": "ListItem", "position": pos, "url": url, "name": m["title"]})
        pos += 1
    # Hand-written evergreen guides: Spanish originals + EN/DE translations.
    static_src = _BLOG_POSTS if lang == "es" else _BLOG_POSTS_L10N.get(lang, {})
    for (slug, p) in sorted(static_src.items(), key=lambda kv: kv[1]["published"], reverse=True):
        url = _blog_url(front, slug, lang)
        cards.append(
            f'<li class="blogcard"><a href="{e(url)}"><b>{e(p["title"])}</b>'
            f'<small>{e(p["description"])}</small></a></li>'
        )
        itemlist.append({"@type": "ListItem", "position": pos, "url": url, "name": p["title"]})
        pos += 1

    idx_paths = {l: _blog_url(front, lang=l) for l in SEO_LANGS}
    hreflang = _hreflang_links(idx_paths, e)
    bc_items = [(UI["home"], f"{front}/"), (UI["blog"], canonical)]
    bc_html = _breadcrumb_html(bc_items, e)
    bc_json = _breadcrumb_jsonld(bc_items)
    il_json = json.dumps({"@context": "https://schema.org", "@type": "ItemList",
                          "name": IDX["il"], "itemListElement": itemlist}, ensure_ascii=False)
    org_ld = _org_website_jsonld(front)
    title, desc = IDX["title"], IDX["desc"]
    css = _SEO_CSS + _blog_common_css()

    html_out = f"""<!doctype html>
<html lang="{IDX['html_lang']}"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{e(canonical)}">{_ICONS_HEAD}
{hreflang}
<meta property="og:type" content="website"><meta property="og:site_name" content="\u00bfQui\u00e9n va?">
<meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(canonical)}">
<meta property="og:image" content="{front}/og/og-default.png">
<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:image" content="{front}/og/og-default.png">
{org_ld}
<script type="application/ld+json">{bc_json}</script>
<script type="application/ld+json">{il_json}</script>
{_SEO_FONTS}
<style>{css}</style></head>
<body><div class="bgfx"></div>
{_seo_topbar(front, lang, e)}
<div class="wrap"><div class="blogwrap">
{bc_html}
<h1 class="blogtitle">{e(IDX["h1"])}</h1>
<p class="blogmeta">{e(IDX["sub"])}</p>
<ul class="bloglist">{''.join(cards)}</ul>
</div></div></body></html>"""
    return StarletteResponse(content=html_out, media_type="text/html; charset=utf-8",
                             headers={"Cache-Control": "public, max-age=3600, s-maxage=86400"})


async def _render_blog_post(slug: str, request: Request, lang: str = "es"):
    import html as _html
    e = _html.escape
    front = _frontend_base(request)
    UI = _BLOG_UI.get(lang, _BLOG_UI["es"])
    post = _BLOG_POSTS.get(slug) if lang == "es" else _BLOG_POSTS_L10N.get(lang, {}).get(slug)
    if not post:
        _am = _agenda_lookup(slug, lang)
        if _am:
            post = await _build_agenda_post(_am, front, lang)
    if not post:
        # Soft 404: redirect to the (localised) blog index
        bidx = _blog_url(front, lang=lang)
        html_out = f'<!doctype html><meta http-equiv="refresh" content="0;url={bidx}"><script>location.replace("{bidx}")</script>'
        return StarletteResponse(content=html_out, status_code=404, media_type="text/html; charset=utf-8")

    # Cross-language hreflang for the translated evergreen guides.
    if not post.get("hreflang"):
        _essrc = _GUIDE_SLUG2ES.get((lang, slug))
        if _essrc:
            post = {**post, "hreflang": _guide_hreflang(front, _essrc)}

    canonical = _blog_url(front, slug, lang)
    hreflang = _hreflang_links(post["hreflang"], e) if post.get("hreflang") else ""
    hero = post.get("hero_image") or f"{front}/icons/icon-512.png"

    # Build sections HTML
    secs_html = []
    for (h2, body) in post["sections"]:
        secs_html.append(f'<section class="blogsec"><h2>{e(h2)}</h2><p>{body}</p></section>')
    sections_html = "".join(secs_html)

    # FAQ HTML + JSON-LD
    faq_html = ""
    faq_json = ""
    if post.get("faq"):
        details = "".join(
            f'<details><summary>{e(q)}</summary><p>{e(a)}</p></details>'
            for q, a in post["faq"]
        )
        faq_html = f'<div class="blogfaq"><h2>{e(UI["faq"])}</h2>{details}</div>'
        faq_json = f'<script type="application/ld+json">{_faq_jsonld(post["faq"])}</script>'

    # Related cities band
    rel_html = ""
    if post.get("related_cities"):
        chips = []
        for cs in post["related_cities"]:
            for c in SUPPORTED_CITIES:
                if _city_slug(c["id"]) == cs:
                    chips.append(f'<a href="{e(_city_paths(front, cs)[lang])}">{c.get("emoji","")} {e(UI["parties_in"])} {e(c["label"])}</a>')
                    break
        if chips:
            rel_html = f'<div class="relband"><b>{e(UI["explore"])}</b>{"".join(chips)}</div>'

    # Breadcrumb + Article JSON-LD
    bc_items = [(UI["home"], f"{front}/"), (UI["blog"], _blog_url(front, lang=lang)), (post["title"], canonical)]
    bc_html = _breadcrumb_html(bc_items, e)
    bc_json = _breadcrumb_jsonld(bc_items)
    article_json = _blog_article_jsonld(post, canonical, front, lang)
    org_ld = _org_website_jsonld(front)

    css = _SEO_CSS + _blog_common_css()
    published_h = post["published"]
    updated_h = post.get("updated") or published_h
    city_link = ""
    if post.get("city_slug"):
        city_link = f' \u00b7 <a href="{e(_city_paths(front, post["city_slug"])[lang])}">{e(UI["parties_in"])} {e(post.get("city") or post["city_slug"])}</a>'

    html_out = f"""<!doctype html>
<html lang="{lang}"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1">
<title>{e(post["title"])} | \u00bfQui\u00e9n va?</title>
<meta name="description" content="{e(post["description"])}">
<link rel="canonical" href="{e(canonical)}">{_ICONS_HEAD}
{hreflang}
<meta property="og:type" content="article"><meta property="og:site_name" content="\u00bfQui\u00e9n va?">
<meta property="og:title" content="{e(post['title'])}"><meta property="og:description" content="{e(post['description'])}">
<meta property="og:url" content="{e(canonical)}">
<meta property="og:image" content="{e(hero)}">
<meta property="article:published_time" content="{e(published_h)}">
<meta property="article:modified_time" content="{e(updated_h)}">
<meta name="twitter:card" content="summary_large_image">
{org_ld}
<script type="application/ld+json">{article_json}</script>
<script type="application/ld+json">{bc_json}</script>
{faq_json}
{_SEO_FONTS}
<style>{css}</style></head>
<body><div class="bgfx"></div>
{_seo_topbar(front, lang, e)}
<div class="wrap"><div class="blogwrap">
{bc_html}
<h1 class="blogtitle">{e(post["title"])}</h1>
<p class="blogmeta">{e(UI["pub"])} {e(published_h)} \u00b7 {e(UI["upd"])} {e(updated_h)}{city_link}</p>
<img class="bloghero" src="{e(hero)}" alt="{e(post['title'])}" loading="eager" fetchpriority="high" />
{sections_html}
{faq_html}
{rel_html}
</div></div></body></html>"""
    return StarletteResponse(content=html_out, media_type="text/html; charset=utf-8",
                             headers={"Cache-Control": "public, max-age=3600, s-maxage=86400"})


@api_router.api_route("/blog", methods=["GET", "HEAD"])
async def seo_blog_index(request: Request):
    return await _render_blog_index(request, "es")


@api_router.api_route("/blog/{slug}", methods=["GET", "HEAD"])
async def seo_blog_post(slug: str, request: Request):
    return await _render_blog_post(slug, request, "es")


@api_router.api_route("/en/blog", methods=["GET", "HEAD"])
async def seo_blog_index_en(request: Request):
    return await _render_blog_index(request, "en")


@api_router.api_route("/en/blog/{slug}", methods=["GET", "HEAD"])
async def seo_blog_post_en(slug: str, request: Request):
    return await _render_blog_post(slug, request, "en")


@api_router.api_route("/de/blog", methods=["GET", "HEAD"])
async def seo_blog_index_de(request: Request):
    return await _render_blog_index(request, "de")


@api_router.api_route("/de/blog/{slug}", methods=["GET", "HEAD"])
async def seo_blog_post_de(slug: str, request: Request):
    return await _render_blog_post(slug, request, "de")


async def _sitemap_blog_xml(front: str, today: str) -> str:
    parts = [f"<url><loc>{_blog_url(front)}</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq></url>"]
    parts.append(f"<url><loc>{_blog_url(front, lang='en')}</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq></url>")
    parts.append(f"<url><loc>{_blog_url(front, lang='de')}</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq></url>")
    for slug, p in _BLOG_POSTS.items():
        lm = (p.get("updated") or p.get("published") or today)
        img = p.get("hero_image") or ""
        img_xml = ""
        if img.startswith("http"):
            img_xml = f'<image:image><image:loc>{img.replace("&", "&amp;")}</image:loc></image:image>'
        parts.append(
            f'<url><loc>{_blog_url(front, slug)}</loc><lastmod>{lm}</lastmod>'
            f'<changefreq>monthly</changefreq>{img_xml}</url>'
        )
    # EN/DE translated evergreen guides.
    for lg in ("en", "de"):
        for slug, p in _BLOG_POSTS_L10N.get(lg, {}).items():
            lm = (p.get("updated") or p.get("published") or today)
            img = p.get("hero_image") or ""
            img_xml = ""
            if img.startswith("http"):
                img_xml = f'<image:image><image:loc>{img.replace("&", "&amp;")}</image:loc></image:image>'
            parts.append(
                f'<url><loc>{_blog_url(front, slug, lg)}</loc><lastmod>{lm}</lastmod>'
                f'<changefreq>monthly</changefreq>{img_xml}</url>'
            )
    # Auto weekly agenda posts in every language (fresh daily → changefreq daily).
    for lg in SEO_LANGS:
        for m in _agenda_meta(lg):
            img = f"{front}/og-city/{m['city_slug']}.jpg"
            img_xml = f'<image:image><image:loc>{img.replace("&", "&amp;")}</image:loc></image:image>'
            parts.append(
                f'<url><loc>{_blog_url(front, m["slug"], lg)}</loc><lastmod>{today}</lastmod>'
                f'<changefreq>daily</changefreq>{img_xml}</url>'
            )
    return _sitemap_urlset(parts)


@api_router.api_route("/sitemap-blog.xml", methods=["GET", "HEAD"])
async def seo_sitemap_blog(request: Request):
    front = _frontend_base(request)
    today = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
    return _sitemap_response(await _sitemap_blog_xml(front, today))




# --- Venue (club) pages -----------------------------------------------------
_VENUE_T = {
    "es": {
        "title": "{venue} ({city}): pr\u00f3ximas fiestas y entradas | \u00bfQui\u00e9n va?",
        "desc": "Agenda de {venue} en {city}: {n} fiestas con horarios, precios reales y qu\u00e9 amigos van. Consigue tus entradas en \u00bfQui\u00e9n va?",
        "desc_past": "Agenda de {venue} en {city}: fiestas, horarios y precios reales. Descubre las pr\u00f3ximas fiestas y qui\u00e9n va en \u00bfQui\u00e9n va?",
        "h1": "Fiestas en {venue}",
        "sub": "Pr\u00f3ximas fiestas, horarios, precios y qui\u00e9n va \u00b7 {city}",
        "empty": "Pronto publicaremos las pr\u00f3ximas fiestas de esta discoteca.",
        "more_city": "M\u00e1s fiestas en {label}",
        "faq_title": "Preguntas frecuentes",
        "past_h": "\u00daltimas fiestas en {venue}",
        "past_note": "Ahora mismo no hay fiestas anunciadas en {venue}. Te avisamos en cuanto se publiquen \u2014 mientras, mira m\u00e1s planes en {city}.",
        "upcoming_h": "Pr\u00f3ximas fiestas",
        "other_h": "Otras discotecas en {label}",
        "where": "D\u00f3nde",
        "genres": "Estilos",
    },
    "en": {
        "title": "{venue} ({city}): upcoming parties & tickets | \u00bfQui\u00e9n va?",
        "desc": "{venue} in {city} agenda: {n} parties with times, real prices and which friends are going. Get your tickets on \u00bfQui\u00e9n va?",
        "desc_past": "{venue} in {city} agenda: parties, times and real prices. Discover the upcoming parties and who's going on \u00bfQui\u00e9n va?",
        "h1": "Parties at {venue}",
        "sub": "Upcoming parties, times, prices and who's going \u00b7 {city}",
        "empty": "We'll publish this club's upcoming parties soon.",
        "more_city": "More parties in {label}",
        "faq_title": "FAQ",
        "past_h": "Latest parties at {venue}",
        "past_note": "There are no announced parties at {venue} right now. We'll let you know as soon as they're published \u2014 meanwhile, see more plans in {city}.",
        "upcoming_h": "Upcoming parties",
        "other_h": "Other clubs in {label}",
        "where": "Where",
        "genres": "Styles",
    },
    "de": {
        "title": "{venue} ({city}): kommende Partys & Tickets | \u00bfQui\u00e9n va?",
        "desc": "{venue} in {city} Programm: {n} Partys mit Zeiten, echten Preisen und welche Freunde hingehen. Hol dir deine Tickets bei \u00bfQui\u00e9n va?",
        "desc_past": "{venue} in {city} Programm: Partys, Zeiten und echte Preise. Entdecke die kommenden Partys und wer hingeht bei \u00bfQui\u00e9n va?",
        "h1": "Partys im {venue}",
        "sub": "Kommende Partys, Zeiten, Preise und wer hingeht \u00b7 {city}",
        "empty": "Wir ver\u00f6ffentlichen bald die kommenden Partys dieses Clubs.",
        "more_city": "Mehr Partys in {label}",
        "faq_title": "H\u00e4ufige Fragen",
        "past_h": "Letzte Partys im {venue}",
        "past_note": "Aktuell sind keine Partys im {venue} angek\u00fcndigt. Wir sagen Bescheid, sobald sie ver\u00f6ffentlicht werden \u2014 sieh dir in der Zwischenzeit mehr Pl\u00e4ne in {city} an.",
        "upcoming_h": "Kommende Partys",
        "other_h": "Andere Clubs in {label}",
        "where": "Wo",
        "genres": "Stile",
    },
}


def _venue_paths(front: str, slug: str) -> dict:
    return {"es": f"{front}/discoteca/{slug}",
            "en": f"{front}/en/club/{slug}",
            "de": f"{front}/de/club/{slug}"}


def _seo_city_id_for(city: str):
    for c in SUPPORTED_CITIES:
        if c["id"] == city or city in CITY_REGIONS.get(c["id"], []):
            return c["id"]
    return None


async def _upcoming_venues_agg(limit: int = 3000) -> list:
    today = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
    pipeline = [
        {"$match": {"date": {"$gte": today}, "venue": {"$nin": ["", None]}}},
        {"$group": {"_id": "$venue", "city": {"$first": "$city"},
                    "count": {"$sum": 1}, "lastmod": {"$max": "$last_scraped_at"}}},
        {"$sort": {"count": -1}},
        {"$limit": limit},
    ]
    out = []
    async for r in db.events.aggregate(pipeline):
        v = r.get("_id") or ""
        if v:
            out.append({"venue": v, "city": r.get("city", ""),
                        "count": r.get("count", 0), "lastmod": r.get("lastmod")})
    return out


async def _all_venues_agg(limit: int = 6000) -> list:
    """Every venue we've ever had an event for (upcoming OR past). Used so a
    club's hub page stays alive (indexable, not a 404) even when all its parties
    have already happened — the club is an evergreen entity that will get new
    events. `city` is taken from its most recent event."""
    pipeline = [
        {"$match": {"venue": {"$nin": ["", None]}}},
        {"$sort": {"date": -1}},
        {"$group": {"_id": "$venue", "city": {"$first": "$city"},
                    "count": {"$sum": 1}, "lastmod": {"$max": "$last_scraped_at"}}},
        {"$sort": {"count": -1}},
        {"$limit": limit},
    ]
    out = []
    async for r in db.events.aggregate(pipeline):
        v = r.get("_id") or ""
        if v:
            out.append({"venue": v, "city": r.get("city", ""),
                        "count": r.get("count", 0), "lastmod": r.get("lastmod")})
    return out


async def _venue_lookup(slug: str):
    slug = (slug or "").lower()
    best = None
    for r in await _upcoming_venues_agg():
        if _slugify(r["venue"]) == slug and (best is None or r["count"] > best["count"]):
            best = r
    if best:
        return best
    # No upcoming parties -> fall back to any historical event so the hub page
    # never 404s (evergreen SEO entity).
    for r in await _all_venues_agg():
        if _slugify(r["venue"]) == slug and (best is None or r["count"] > best["count"]):
            best = r
    return best


async def _venue_events(venue: str, limit: int = 60) -> list:
    today = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
    cur = db.events.find(
        {"venue": venue, "date": {"$gte": today}},
        {"_id": 0, "id": 1, "name": 1, "venue": 1, "date": 1, "time": 1, "city": 1,
         "genre": 1, "address": 1, "currency": 1, "last_scraped_at": 1, "created_at": 1,
         "image_url": 1, "price_tiers": 1, "sale_state": 1},
    ).sort("date", 1).limit(limit)
    return [ev async for ev in cur]


async def _venue_past_events(venue: str, limit: int = 12) -> list:
    """Most recent PAST parties for a club, shown when it has nothing upcoming
    so the hub page keeps real content instead of going empty."""
    today = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
    cur = db.events.find(
        {"venue": venue, "date": {"$lt": today}},
        {"_id": 0, "id": 1, "name": 1, "venue": 1, "date": 1, "time": 1, "city": 1,
         "genre": 1, "address": 1, "currency": 1, "last_scraped_at": 1, "created_at": 1,
         "image_url": 1, "price_tiers": 1, "sale_state": 1},
    ).sort("date", -1).limit(limit)
    return [ev async for ev in cur]


async def _venue_genres(venue: str) -> list:
    """Top music genres for a club (for unique intro copy + keywords)."""
    pipeline = [
        {"$match": {"venue": venue, "genre": {"$nin": ["", None]}}},
        {"$group": {"_id": "$genre", "c": {"$sum": 1}}},
        {"$sort": {"c": -1}},
        {"$limit": 4},
    ]
    out = []
    async for r in db.events.aggregate(pipeline):
        if r.get("_id"):
            out.append(r["_id"])
    return out


def _venue_intro_text(venue: str, city: str, genres: list, lang: str) -> str:
    """Unique, dynamic descriptive paragraph per club (thin-content fix)."""
    g = ""
    if genres:
        gl = ", ".join(genres[:3])
        g = {"es": f" Aqu\u00ed suena sobre todo {gl}.",
             "en": f" Expect mostly {gl}.",
             "de": f" Musikalisch vor allem {gl}."}[lang]
    if lang == "en":
        return (f"{venue} is one of the go-to nightclubs in {city}. On \u00bfQui\u00e9n va? you'll find its "
                f"full agenda \u2014 upcoming parties, line-ups, start times, real ticket prices and which of "
                f"your friends are going.{g} Check what's on at {venue} tonight and this weekend and grab your "
                f"tickets before they sell out.")
    if lang == "de":
        return (f"{venue} geh\u00f6rt zu den angesagtesten Clubs in {city}. Auf \u00bfQui\u00e9n va? findest du das "
                f"komplette Programm \u2014 kommende Partys, Line-ups, Startzeiten, echte Ticketpreise und welche "
                f"Freunde hingehen.{g} Sieh, was heute Abend und am Wochenende im {venue} l\u00e4uft, und sichere dir "
                f"Tickets, bevor sie ausverkauft sind.")
    return (f"{venue} es una de las discotecas de referencia en {city}. En \u00bfQui\u00e9n va? encuentras su agenda "
            f"completa \u2014 pr\u00f3ximas fiestas, cartel, horarios, precios reales de entrada y qu\u00e9 amigos van.{g} "
            f"Mira qu\u00e9 hay en {venue} esta noche y este finde y consigue tus entradas antes de que se agoten.")


async def _render_venue(slug: str, lang: str, request: Request):
    import html as _html
    e = _html.escape
    front = _frontend_base(request)
    T = _VENUE_T[lang]
    ST = SEO_T[lang]
    look = await _venue_lookup(slug)
    if not look:
        return StarletteResponse(
            content=f"<!doctype html><meta http-equiv=refresh content='0;url={front}/feed'>",
            media_type="text/html", status_code=404)
    venue = look["venue"]
    city = look.get("city", "")
    events = await _venue_events(venue)
    only_past = False
    if not events:
        # Evergreen hub: keep the page alive with recent past parties instead of
        # letting it go empty / 404 when everything has already happened.
        events = await _venue_past_events(venue)
        only_past = True
    vpaths = _venue_paths(front, slug)
    canonical = vpaths[lang]
    n = 0 if only_past else len(events)
    title = e(T["title"].format(venue=venue, city=city))
    desc = e((T["desc_past"] if only_past else T["desc"]).format(venue=venue, city=city, n=n))

    og_img = ""
    items_html, jsonld = [], []
    for ev in events[:24]:
        eu = _event_paths(front, ev.get("id", ""), _event_slug(ev))[lang]
        items_html.append(f'<li>{_seo_card(ev, eu, lang, e, nofollow=only_past)}</li>')
        # Only advertise structured Event/offers for upcoming parties.
        if not only_past:
            jsonld.append(f'<script type="application/ld+json">{_event_jsonld(ev, eu, front, lang=lang)}</script>')
        if not og_img and str(ev.get("image_url", "")).startswith("http"):
            og_img = e(ev["image_url"])
    if not items_html:
        items_html.append(f'<li class="empty">{e(T["empty"])}</li>')

    city_id = _seo_city_id_for(city)
    clabel = city
    cp = ""
    bc_items = [(ST["bc_home"], f"{front}/")]
    city_cta = ""
    if city_id:
        clabel = next((c["label"] for c in SUPPORTED_CITIES if c["id"] == city_id), city)
        cp = _city_paths(front, _city_slug(city_id))[lang]
        bc_items.append((clabel, cp))
        city_cta = f'<div class="ctarow"><a class="cta ghost" href="{e(cp)}">{e(T["more_city"].format(label=clabel))}</a></div>'
    bc_items.append((venue, canonical))
    bc_html = _breadcrumb_html(bc_items, e)

    # Unique intro paragraph (thin-content fix) + music styles from real events.
    genres = await _venue_genres(venue)
    intro_html = f'<div class="intro"><p>{e(_venue_intro_text(venue, clabel or city, genres, lang))}</p></div>'

    # Address / location + styles chips (unique on-page facts).
    addr0 = next((ev.get("address") for ev in events if ev.get("address")), "")
    facts = []
    if addr0:
        facts.append(f'<div><b>{e(T["where"])}</b> {e(addr0)}</div>')
    if genres:
        facts.append(f'<div><b>{e(T["genres"])}</b> {e(", ".join(genres[:3]))}</div>')
    facts_html = f'<div class="meta">{"".join(facts)}</div>' if facts else ""

    # "No upcoming right now" note when we only have past parties.
    past_note_html = (f'<p class="sub" style="color:#f5a524;font-weight:600">'
                      f'{e(T["past_note"].format(venue=venue, city=clabel or city))}</p>') if only_past else ""
    list_h = e((T["past_h"] if only_past else T["upcoming_h"]).format(venue=venue))
    list_head = f'<h2 class="sectitle">{list_h}</h2>'

    # Internal linking: sibling clubs in the same city (keeps the hub rich and
    # spreads crawl/authority across venue pages).
    other_html = ""
    if city_id:
        siblings = [v for v in await _city_venues(city_id) if v["slug"] != slug][:8]
        if siblings:
            cards = []
            for v in siblings:
                thumb = (f'<span class="vthumb"><img src="{e(v["image"])}" alt="{e(v["venue"])}" loading="lazy"></span>'
                         if v["image"] else f'<span class="vthumb">{e((v["venue"][:1] or "?").upper())}</span>')
                cards.append(
                    f'<a class="vcard glow-card reveal" href="{e(_venue_paths(front, v["slug"])[lang])}">{thumb}'
                    f'<span class="vmeta"><b>{e(v["venue"])}</b></span></a>')
            other_html = (f'<div class="sech"><h2>{e(T["other_h"].format(label=clabel or city))}</h2></div>'
                          f'<div class="venues">{"".join(cards)}</div>')

    nc = {"@context": "https://schema.org", "@type": "NightClub",
          "name": venue, "url": canonical}
    addr = {"@type": "PostalAddress", "addressCountry": "ES"}
    if city:
        addr["addressLocality"] = city
    if addr0:
        addr["streetAddress"] = addr0
    nc["address"] = addr
    if og_img:
        nc["image"] = og_img

    # 3 FAQs (was 1) — richer FAQ rich-result + on-page content.
    q_when = (f"\u00bfQu\u00e9 fiestas hay en {venue}?" if lang == "es" else
              (f"What parties are on at {venue}?" if lang == "en" else f"Welche Partys gibt es im {venue}?"))
    if only_past:
        a_when = (f"En este momento no hay fiestas anunciadas en {venue} ({city}). Publicamos su agenda en cuanto se confirma \u2014 mira las \u00faltimas fiestas y m\u00e1s planes en {clabel or city} en \u00bfQui\u00e9n va?" if lang == "es" else
                  (f"There are no announced parties at {venue} ({city}) right now. We publish its agenda as soon as it's confirmed \u2014 see the latest parties and more plans in {clabel or city} on \u00bfQui\u00e9n va?" if lang == "en" else
                   f"Aktuell sind keine Partys im {venue} ({city}) angek\u00fcndigt. Wir ver\u00f6ffentlichen das Programm, sobald es best\u00e4tigt ist \u2014 sieh die letzten Partys und mehr Pl\u00e4ne in {clabel or city} bei \u00bfQui\u00e9n va?"))
    else:
        a_when = (f"Ahora mismo {n} pr\u00f3ximas fiestas en {venue} ({city}). Mira horarios, precios reales y qui\u00e9n va en \u00bfQui\u00e9n va?" if lang == "es" else
                  (f"Right now {n} upcoming parties at {venue} ({city}). See times, real prices and who's going on \u00bfQui\u00e9n va?" if lang == "en" else
                   f"Aktuell {n} kommende Partys im {venue} ({city}). Sieh Zeiten, echte Preise und wer hingeht bei \u00bfQui\u00e9n va?"))
    q_where = (f"\u00bfD\u00f3nde est\u00e1 {venue}?" if lang == "es" else
               (f"Where is {venue}?" if lang == "en" else f"Wo ist {venue}?"))
    loc = addr0 or city
    a_where = (f"{venue} est\u00e1 en {loc}. En \u00bfQui\u00e9n va? tienes la ubicaci\u00f3n, los horarios y c\u00f3mo llegar a cada fiesta." if lang == "es" else
               (f"{venue} is in {loc}. On \u00bfQui\u00e9n va? you get the location, times and how to get to each party." if lang == "en" else
                f"{venue} befindet sich in {loc}. Auf \u00bfQui\u00e9n va? findest du Standort, Zeiten und Anfahrt zu jeder Party."))
    q_tix = (f"\u00bfC\u00f3mo consigo entradas para {venue}?" if lang == "es" else
             (f"How do I get tickets for {venue}?" if lang == "en" else f"Wie bekomme ich Tickets f\u00fcr {venue}?"))
    a_tix = (f"Abre la fiesta que te interese de {venue} en \u00bfQui\u00e9n va? y toca en conseguir entrada para comprar al precio actual, sin sorpresas." if lang == "es" else
             (f"Open the party you want at {venue} on \u00bfQui\u00e9n va? and tap get ticket to buy at the current price, no surprises." if lang == "en" else
              f"\u00d6ffne die gew\u00fcnschte Party im {venue} auf \u00bfQui\u00e9n va? und tippe auf Ticket sichern, um zum aktuellen Preis zu kaufen."))
    faq_pairs = [(q_when, a_when), (q_where, a_where), (q_tix, a_tix)]

    hreflang = _hreflang_links(vpaths, e)
    langsw = _lang_switch(vpaths, lang, e(ST["other_langs"]), e)
    topbar = _seo_topbar(front, lang, e)
    benefits = _seo_benefits(lang, e)
    joinband = _seo_joinband(front, lang, e)
    faq_html = _faq_html(T["faq_title"], faq_pairs, e)
    extra_jsonld = (_org_website_jsonld(front)
                    + f'<script type="application/ld+json">{json.dumps(nc, ensure_ascii=False)}</script>'
                    + f'<script type="application/ld+json">{_breadcrumb_jsonld(bc_items)}</script>'
                    + f'<script type="application/ld+json">{_faq_jsonld(faq_pairs)}</script>')
    ogimg_tag = f'<meta property="og:image" content="{og_img}">' if og_img else ''
    ogloc = {'es': 'es_ES', 'en': 'en_US', 'de': 'de_DE'}[lang]
    stats_html = (f'<div class="stats"><span class="stat"><b>{n}</b> '
                  f'{e(_HOME_T[lang]["n_plans"])}</span></div>') if not only_past else ""
    html_out = f"""<!doctype html>
<html lang="{ST['html_lang']}"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{e(canonical)}">{_ICONS_HEAD}
{hreflang}
<meta property="og:type" content="website"><meta property="og:site_name" content="\u00bfQui\u00e9n va?">
<meta property="og:locale" content="{ogloc}">
<meta property="og:title" content="{title}"><meta property="og:description" content="{desc}">
<meta property="og:url" content="{e(canonical)}">{ogimg_tag}
<meta name="twitter:card" content="summary_large_image">
{''.join(jsonld)}{extra_jsonld}
{_SEO_FONTS}
<style>{_SEO_CSS}</style></head>
<body><div class="bgfx"></div>
{topbar}
<div class="wrap">
{bc_html}
<section class="hero-sec">
<span class="kicker">{e(city)}</span>
<h1>{e(T["h1"].format(venue=venue))}<span class="dot">.</span></h1>
<p class="sub">{e(T["sub"].format(city=city))}</p>
{stats_html}
{past_note_html}
<div class="ctarow"><a class="cta" href="{front}/feed">{e(_SEO_UI[lang]["open"])}</a></div>
</section>
{intro_html}
{facts_html}
{list_head}
<ul class="grid">{''.join(items_html)}</ul>
{city_cta}
{other_html}
{benefits}
{joinband}
{faq_html}
{langsw}
<footer>{e(ST["footer"])}</footer>
</div></body></html>"""
    return StarletteResponse(content=html_out, media_type="text/html; charset=utf-8",
                             headers={"Cache-Control": "public, max-age=1800"})


@api_router.api_route("/discoteca/{slug}", methods=["GET", "HEAD"])
async def seo_venue_es(slug: str, request: Request):
    return await _render_venue(slug, "es", request)


@api_router.api_route("/en/club/{slug}", methods=["GET", "HEAD"])
async def seo_venue_en(slug: str, request: Request):
    return await _render_venue(slug, "en", request)


@api_router.api_route("/de/club/{slug}", methods=["GET", "HEAD"])
async def seo_venue_de(slug: str, request: Request):
    return await _render_venue(slug, "de", request)



@api_router.api_route("/sitemap.xml", methods=["GET", "HEAD"])
async def seo_sitemap(request: Request, scope: str = "", city: str = ""):
    """Sitemap INDEX by default; child sitemaps via clean paths
    (/sitemap-cities.xml, /sitemap-events-<city>.xml). Path-based children
    (not query strings) so Vercel rewrites always proxy them to XML instead
    of falling through to the React SPA (which returned HTML to Google).
    Legacy ?scope= query params still work for backward compatibility."""
    front = _frontend_base(request)
    today = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
    if scope == "cities":
        return _sitemap_response(await _sitemap_cities_xml(front, today))
    if scope == "events":
        return _sitemap_response(await _sitemap_events_xml(front, today, city))
    return _sitemap_response(await _sitemap_index_xml(front, today))


@api_router.api_route("/sitemap-cities.xml", methods=["GET", "HEAD"])
async def seo_sitemap_cities(request: Request):
    front = _frontend_base(request)
    today = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
    return _sitemap_response(await _sitemap_cities_xml(front, today))


@api_router.api_route("/sitemap-events-{city}.xml", methods=["GET", "HEAD"])
async def seo_sitemap_events(city: str, request: Request):
    front = _frontend_base(request)
    today = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
    return _sitemap_response(await _sitemap_events_xml(front, today, city))


@api_router.api_route("/sitemap-venues.xml", methods=["GET", "HEAD"])
async def seo_sitemap_venues(request: Request):
    front = _frontend_base(request)
    today = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
    return _sitemap_response(await _sitemap_venues_xml(front, today))


# ===========================================================================
# Artist / DJ SEO hub pages (programmatic, CURATED whitelist -> no junk pages).
# Captures high-volume searches lastnight.es doesn't cover well, e.g.
# "david guetta ibiza entradas", "carl cox fechas". Native SSR, same shell/CSS,
# hreflang es/en/de, Event JSON-LD (rich results with price), sitemap.
# ===========================================================================
_ARTISTS = [
    ("david-guetta", "David Guetta", ["david guetta"]),
    ("carl-cox", "Carl Cox", ["carl cox"]),
    ("tiesto", "Ti\u00ebsto", ["tiesto", "ti\u00ebsto"]),
    ("calvin-harris", "Calvin Harris", ["calvin harris"]),
    ("solomun", "Solomun", ["solomun"]),
    ("black-coffee", "Black Coffee", ["black coffee"]),
    ("marco-carola", "Marco Carola", ["marco carola"]),
    ("dom-dolla", "Dom Dolla", ["dom dolla"]),
    ("fisher", "FISHER", ["fisher"]),
    ("peggy-gou", "Peggy Gou", ["peggy gou"]),
    ("camelphat", "CamelPhat", ["camelphat"]),
    ("adam-beyer", "Adam Beyer", ["adam beyer"]),
    ("charlotte-de-witte", "Charlotte de Witte", ["charlotte de witte"]),
    ("amelie-lens", "Amelie Lens", ["amelie lens"]),
    ("boris-brejcha", "Boris Brejcha", ["boris brejcha"]),
    ("martin-garrix", "Martin Garrix", ["martin garrix"]),
    ("john-summit", "John Summit", ["john summit"]),
    ("anyma", "Anyma", ["anyma"]),
    ("bizarrap", "Bizarrap", ["bizarrap", "bzrp"]),
    ("keinemusik", "Keinemusik", ["keinemusik"]),
    ("vintage-culture", "Vintage Culture", ["vintage culture"]),
    ("hot-since-82", "Hot Since 82", ["hot since 82"]),
    ("loco-dice", "Loco Dice", ["loco dice"]),
    ("michael-bibi", "Michael Bibi", ["michael bibi"]),
    ("jamie-jones", "Jamie Jones", ["jamie jones"]),
    ("paco-osuna", "Paco Osuna", ["paco osuna"]),
    ("chris-stussy", "Chris Stussy", ["chris stussy"]),
    ("sven-vath", "Sven V\u00e4th", ["sven vath", "sven v\u00e4th"]),
    ("luciano", "Luciano", ["luciano"]),
    ("the-martinez-brothers", "The Martinez Brothers", ["martinez brothers"]),
]
_ARTIST_BY_SLUG = {a[0]: a for a in _ARTISTS}


def _artist_paths(front: str, slug: str) -> dict:
    return {"es": f"{front}/artista/{slug}", "en": f"{front}/en/artist/{slug}",
            "de": f"{front}/de/artist/{slug}"}


async def _artist_events(aliases: list) -> list:
    import re
    today = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
    pat = "|".join(re.escape(x) for x in aliases)
    cur = db.events.find(
        {"name": {"$regex": pat, "$options": "i"}, "date": {"$gte": today}},
        {"_id": 0}).sort("date", 1).limit(60)
    return [ev async for ev in cur]


async def _render_artist(slug: str, lang: str, request: Request) -> StarletteResponse:
    import html as _htmlmod
    e = _htmlmod.escape
    front = _frontend_base(request)
    a = _ARTIST_BY_SLUG.get(slug)
    if not a:
        return StarletteResponse(
            content=f"<!doctype html><meta http-equiv=refresh content='0;url={front}/feed'>",
            media_type="text/html; charset=utf-8", status_code=404)
    _slug, name, aliases = a
    evs = await _artist_events(aliases)
    if not evs:
        return StarletteResponse(
            content=f"<!doctype html><meta http-equiv=refresh content='0;url={front}/feed'>",
            media_type="text/html; charset=utf-8", status_code=404)

    paths = _artist_paths(front, _slug)
    canonical = paths[lang]
    hl = {"es": "es", "en": "en", "de": "de"}[lang]
    open_app = {"es": "Abrir la app", "en": "Open the app", "de": "App \u00f6ffnen"}[lang]
    kicker = {"es": "DJ / Artista", "en": "DJ / Artist", "de": "DJ / K\u00fcnstler"}[lang]
    n = len(evs)
    title = {
        "es": f"{name}: pr\u00f3ximas fiestas y entradas | \u00bfQui\u00e9n va?",
        "en": f"{name}: upcoming parties & tickets | \u00bfQui\u00e9n va?",
        "de": f"{name}: kommende Partys & Tickets | \u00bfQui\u00e9n va?",
    }[lang]
    desc = {
        "es": f"Todas las fechas de {name}: {n} fiestas con club, precio y entradas oficiales. Descubre d\u00f3nde pincha {name} y compra tus entradas.",
        "en": f"All {name} dates: {n} parties with venue, price and official tickets. Find where {name} plays next and buy tickets.",
        "de": f"Alle {name}-Termine: {n} Partys mit Club, Preis und offiziellen Tickets.",
    }[lang]
    intro = {
        "es": f"Consulta las pr\u00f3ximas fiestas de <b>{e(name)}</b>: fecha, club, precio y enlace oficial de entradas. Actualizado a diario.",
        "en": f"Upcoming parties of <b>{e(name)}</b>: date, venue, price and official ticket link. Updated daily.",
        "de": f"Kommende Partys von <b>{e(name)}</b>: Datum, Club, Preis und offizieller Ticket-Link.",
    }[lang]

    more_djs = {"es": "M\u00e1s DJs", "en": "More DJs", "de": "Mehr DJs"}[lang]
    tagline = {"es": "Tu gu\u00eda de fiestas", "en": "Your party guide", "de": "Dein Party-Guide"}[lang]

    ecards = "".join(
        f'<li>{_seo_card(ev, _event_paths(front, ev.get("id", ""), _event_slug(ev))[lang], lang, e)}</li>'
        for ev in evs)

    # Related artists (internal linking)
    import random as _r
    others = [x for x in _ARTISTS if x[0] != _slug]
    _r.shuffle(others)
    related = "".join(
        f'<a class="chip" href="{e(_artist_paths(front, o[0])[lang])}">{e(o[1])}</a>'
        for o in others[:8])

    hreflang = _hreflang_links(paths, e)
    topbar = _seo_topbar(front, lang, e)

    # JSON-LD: breadcrumb + org + Event for each listed party (rich results)
    bc = ('{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":['
          f'{{"@type":"ListItem","position":1,"name":"{e(name)}","item":"{e(canonical)}"}}]}}')
    events_ld = "".join(
        f'<script type="application/ld+json">{_event_jsonld(ev, _event_paths(front, ev.get("id", ""), _event_slug(ev))[lang], front, True, lang)}</script>'
        for ev in evs[:20])
    extra_ld = (_org_website_jsonld(front)
                + f'<script type="application/ld+json">{bc}</script>' + events_ld)

    html_out = f"""<!doctype html>
<html lang="{hl}"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{e(canonical)}">{_ICONS_HEAD}
{hreflang}
<meta property="og:type" content="website"><meta property="og:site_name" content="\u00bfQui\u00e9n va?">
<meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(canonical)}">
<meta name="twitter:card" content="summary_large_image">
{extra_ld}
{_SEO_FONTS}
<style>{_SEO_CSS}</style></head>
<body><div class="bgfx"></div>
{topbar}
<div class="wrap">
<section class="hero-sec">
<span class="kicker">{e(kicker)}</span>
<h1>{e(name)}<span class="dot">.</span></h1>
<p class="sub">{intro}</p>
<div class="ctarow"><a class="cta" href="{front}/feed">{e(open_app)}</a></div>
</section>
<ul class="grid">{ecards}<li class="nores" id="qvnores"></li></ul>
<div class="cities"><b>{e(more_djs)}</b>{related}</div>
<footer>\u00a9 \u00bfQui\u00e9n va? \u2014 {e(tagline)}</footer>
</div></body></html>"""
    return StarletteResponse(content=html_out, media_type="text/html; charset=utf-8",
                             headers={"Cache-Control": "public, max-age=1800"})


@api_router.api_route("/artista/{slug}", methods=["GET", "HEAD"])
async def seo_artist_es(slug: str, request: Request):
    return await _render_artist(slug, "es", request)


@api_router.api_route("/en/artist/{slug}", methods=["GET", "HEAD"])
async def seo_artist_en(slug: str, request: Request):
    return await _render_artist(slug, "en", request)


@api_router.api_route("/de/artist/{slug}", methods=["GET", "HEAD"])
async def seo_artist_de(slug: str, request: Request):
    return await _render_artist(slug, "de", request)


async def _sitemap_artists_xml(front: str, today: str) -> str:
    import re
    names = []
    async for ev in db.events.find({"date": {"$gte": today}}, {"_id": 0, "name": 1}):
        names.append((ev.get("name") or "").lower())
    parts = []
    for _slug, _name, aliases in _ARTISTS:
        pat = re.compile("|".join(re.escape(x.lower()) for x in aliases))
        if any(pat.search(nm) for nm in names):
            parts.append(_sitemap_url(_artist_paths(front, _slug), "es", today, "daily"))
    return _sitemap_urlset(parts)


@api_router.api_route("/sitemap-artists.xml", methods=["GET", "HEAD"])
async def seo_sitemap_artists(request: Request):
    front = _frontend_base(request)
    today = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
    return _sitemap_response(await _sitemap_artists_xml(front, today))




def _sitemap_response(xml: str) -> StarletteResponse:
    return StarletteResponse(content=xml, media_type="application/xml",
                             headers={"Cache-Control": "public, max-age=3600"})


def _sitemap_url(paths: dict, lang: str, lastmod: str, freq: str, image: str = "") -> str:
    alts = "".join(f'<xhtml:link rel="alternate" hreflang="{l}" href="{u}"/>' for l, u in paths.items())
    alts += f'<xhtml:link rel="alternate" hreflang="x-default" href="{paths["es"]}"/>'
    img = ""
    if image and str(image).startswith("http"):
        img = f'<image:image><image:loc>{str(image).replace("&", "&amp;")}</image:loc></image:image>'
    return (f"<url><loc>{paths[lang]}</loc><lastmod>{lastmod}</lastmod>"
            f"<changefreq>{freq}</changefreq>{alts}{img}</url>")


def _sitemap_urlset(parts: list) -> str:
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
            'xmlns:xhtml="http://www.w3.org/1999/xhtml" '
            'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">'
            + "".join(parts) + "</urlset>")


async def _city_lastmods(today: str) -> dict:
    """Freshest real content date per city (max last_scraped_at of its events,
    never in the future). Honest <lastmod> for the city pages so Google trusts
    the recency signal instead of seeing 'today' on every URL every day."""
    out = {}
    for c in SUPPORTED_CITIES:
        lm = today
        try:
            doc = await db.events.find_one(
                {"city": city_query_value(c["id"])},
                {"_id": 0, "last_scraped_at": 1},
                sort=[("last_scraped_at", -1)])
            raw = str((doc or {}).get("last_scraped_at") or "")[:10]
            if len(raw) == 10 and raw <= today:
                lm = raw
        except Exception:
            pass
        out[c["id"]] = lm
    return out


async def _sitemap_cities_xml(front: str, today: str) -> str:
    lastmods = await _city_lastmods(today)
    parts = [f"<url><loc>{front}/</loc><lastmod>{today}</lastmod><changefreq>daily</changefreq></url>"]
    for c in SUPPORTED_CITIES:
        lm = lastmods.get(c["id"], today)
        for tf in ("all", "tonight", "weekend"):
            cp = _city_tf_paths(front, _city_slug(c["id"]), tf)
            for lang in SEO_LANGS:
                parts.append(_sitemap_url(cp, lang, lm, "daily"))
    return _sitemap_urlset(parts)


async def _sitemap_events_xml(front: str, today: str, city: str) -> str:
    city_id = _CITY_SLUGS.get((city or "").lower())
    parts = []
    if city_id:
        for ev in await _upcoming_for_city(city_id, 500):
            eid = ev.get("id")
            if not eid:
                continue
            # Skip thin/placeholder parties (no poster/price/real name yet): keeping
            # them out of the sitemap concentrates crawl budget on indexable pages.
            if _is_thin_event(ev):
                continue
            ep = _event_paths(front, eid, _event_slug(ev))
            lm = _ev_lastmod(ev, today)
            img = ev.get("image_url", "")
            for lang in SEO_LANGS:
                parts.append(_sitemap_url(ep, lang, lm, "hourly", image=img))
    return _sitemap_urlset(parts)


async def _seo_venues_agg(limit: int = 3000) -> list:
    """Venues for the SITEMAP: not just those with an upcoming party but any club
    with activity in the last ~6 months. The /discoteca/{slug} pages are EVERGREEN
    (they stay alive with recent past parties), so keeping these permanent hubs in
    the sitemap year-round — instead of dropping them the moment they have no future
    event — protects their crawling/indexing and long-term ranking."""
    today = datetime.now(ZoneInfo("Europe/Madrid")).date()
    since = (today - timedelta(days=180)).isoformat()
    pipeline = [
        {"$match": {"date": {"$gte": since}, "venue": {"$nin": ["", None]}}},
        {"$group": {"_id": "$venue", "city": {"$first": "$city"},
                    "count": {"$sum": 1}, "lastmod": {"$max": "$last_scraped_at"}}},
        {"$sort": {"count": -1}},
        {"$limit": limit},
    ]
    out = []
    async for r in db.events.aggregate(pipeline):
        v = r.get("_id") or ""
        if v:
            out.append({"venue": v, "city": r.get("city", ""),
                        "count": r.get("count", 0), "lastmod": r.get("lastmod")})
    return out


async def _sitemap_venues_xml(front: str, today: str) -> str:
    parts, seen = [], set()
    for r in await _seo_venues_agg():
        slug = _slugify(r["venue"])
        if not slug or slug in seen:
            continue
        seen.add(slug)
        vp = _venue_paths(front, slug)
        lm = (str(r.get("lastmod") or "")[:10]) or today
        for lang in SEO_LANGS:
            parts.append(_sitemap_url(vp, lang, lm, "daily"))
    return _sitemap_urlset(parts)


async def _sitemap_index_xml(front: str, today: str) -> str:
    # Recency signal: child sitemaps carry the freshest content date so Google
    # re-fetches them soon after new parties are scraped (crawl sooner).
    fresh = today
    try:
        doc = await db.events.find_one({}, {"_id": 0, "last_scraped_at": 1},
                                       sort=[("last_scraped_at", -1)])
        raw = str((doc or {}).get("last_scraped_at") or "")[:10]
        if len(raw) == 10:
            # Honest lastmod: the real freshest scrape date, never in the future.
            fresh = raw if raw <= today else today
    except Exception:
        pass
    static_lm = {
        f"{front}/sitemap-cities.xml": today,
        f"{front}/sitemap-venues.xml": fresh,
        f"{front}/sitemap-artists.xml": fresh,
        f"{front}/sitemap-blog.xml": today,
    }
    children = list(static_lm.keys())
    children += [f"{front}/sitemap-events-{_city_slug(c['id'])}.xml" for c in SUPPORTED_CITIES]
    body = "".join(
        f"<sitemap><loc>{u}</loc><lastmod>{static_lm.get(u, fresh)}</lastmod></sitemap>"
        for u in children)
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + body + "</sitemapindex>")


# App/SPA routes that serve the generic React shell (no unique SEO content).
# Letting Googlebot crawl them wastes crawl budget and creates thin/duplicate
# pages -> the root cause of thousands of "Discovered - currently not indexed"
# URLs. We block them so Google focuses its budget on our server-rendered,
# evergreen pages (/fiesta/, /discoteca/, /fiestas/<city>, /blog/).
_ROBOTS_DISALLOW = [
    "/event/",          # in-app event detail (SSR SEO version lives at /fiesta/)
    "/feed", "/friends", "/notifications", "/novedades",
    "/profile", "/users/", "/chats", "/top",
    "/recuerdos", "/memories", "/fiestas-pasadas",
    "/ajustes", "/momento", "/momentos", "/descubrir", "/wrapped",
    "/admin", "/onboarding", "/login", "/auth/",
    "/r/", "/ig", "/tt", "/mapa", "/locales",
]
# Server-rendered, indexable sections — spelled out for clarity (they are
# already allowed by default, but this documents intent for anyone reading it).
_ROBOTS_ALLOW = ["/fiesta/", "/fiestas/", "/discoteca/", "/blog", "/en/", "/de/"]


@api_router.api_route("/robots.txt", methods=["GET", "HEAD"])
async def seo_robots(request: Request):
    front = _frontend_base(request)
    lines = ["User-agent: *", "Allow: /"]
    lines += [f"Disallow: {p}" for p in _ROBOTS_DISALLOW]
    lines += [f"Allow: {p}" for p in _ROBOTS_ALLOW]
    lines += ["", f"Sitemap: {front}/sitemap.xml", ""]
    txt = "\n".join(lines)
    return StarletteResponse(content=txt, media_type="text/plain",
                             headers={"Cache-Control": "public, max-age=3600"})


# ---------------------------------------------------------------------------
# Brand icons / favicon / manifest served BY THE BACKEND too.
# The SSR pages that Googlebot crawls are served by this backend, and the code
# promises "Googlebot always finds a valid /favicon.ico" — but the backend used
# to 404 these, so if the icon requests ever hit the backend host the site
# logo/favicon could not be picked up by Google. We now serve them from
# backend/static at BOTH the root paths (favicon.ico, /icons/…) and their /api
# equivalents, with long cache + correct content types.
# ---------------------------------------------------------------------------
_STATIC_DIR = ROOT_DIR / "static"
_ICON_FILES = {
    "favicon.ico": "image/x-icon",
    "favicon-16x16.png": "image/png",
    "favicon-32x32.png": "image/png",
    "favicon-96x96.png": "image/png",
    "apple-touch-icon.png": "image/png",
    "manifest.json": "application/manifest+json",
    "icons/icon-192.png": "image/png",
    "icons/icon-512.png": "image/png",
}


def _serve_static_icon(rel: str) -> StarletteResponse:
    media = _ICON_FILES.get(rel)
    fp = (_STATIC_DIR / rel)
    if not media or not fp.is_file():
        return StarletteResponse(content="not found", status_code=404, media_type="text/plain")
    try:
        data = fp.read_bytes()
    except Exception:
        return StarletteResponse(content="error", status_code=500, media_type="text/plain")
    return StarletteResponse(
        content=data, media_type=media,
        headers={"Cache-Control": "public, max-age=604800, immutable"},
    )


def _register_icon_routes():
    for rel in _ICON_FILES:
        def _make(_rel):
            async def _handler(request: Request):
                return _serve_static_icon(_rel)
            return _handler
        h = _make(rel)
        # Root path (production host may serve these directly) + /api mirror.
        app.add_api_route(f"/{rel}", h, methods=["GET", "HEAD"], include_in_schema=False)
        api_router.add_api_route(f"/{rel}", h, methods=["GET", "HEAD"], include_in_schema=False)


_register_icon_routes()



@api_router.get("/story-image/{event_id}")
async def story_image(event_id: str, request: Request):
    """A ready-to-post 1080x1920 Instagram-Story image for a party: blurred poster
    background + the poster card + name/venue/date/price + branding."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        return StarletteResponse(content="not found", status_code=404, media_type="text/plain")
    W, H = 1080, 1920

    def font(kind, size, weight=None):
        # kind: 'title' -> Unbounded (brand display), 'body' -> Outfit
        fname = "Unbounded.ttf" if kind == "title" else "Outfit.ttf"
        f = ImageFont.truetype(os.path.join(_ASSETS_FONTS, fname), size)
        if weight is not None:
            try:
                f.set_variation_by_axes([weight])
            except Exception:
                pass
        return f

    # Fetch the poster (server-side, avoids browser CORS/tainted-canvas issues).
    poster = None
    img_url = ev.get("image_url") or ""
    if img_url.startswith("http"):
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                r = await c.get(img_url)
                if r.status_code == 200:
                    poster = Image.open(io.BytesIO(r.content)).convert("RGB")
        except Exception:
            poster = None

    # Single unified "¿Quién va?" story style: blurred poster background with
    # clean white typography. (The 3-style selector was removed for performance.)
    style = "neon"        # blurred-poster background
    neon_accents = False  # white brand + white poster border (minimal look)
    CYAN, MAGENTA, LIME = (0, 240, 255), (168, 85, 247), (190, 242, 60)

    def _cover(im):
        bw, bh = im.size
        s = max(W / bw, H / bh)
        r = im.resize((int(bw * s) + 1, int(bh * s) + 1))
        bx = (r.width - W) // 2; by = (r.height - H) // 2
        return r.crop((bx, by, bx + W, by + H))

    # ---- Background per style ----
    if style == "full" and poster is not None:
        bg = _cover(poster)
        ramp = Image.new("L", (1, H), 0)
        for y in range(H):
            top = int(175 * (1 - y / (H * 0.30))) if y < H * 0.30 else 0
            bot = int(238 * ((y - H * 0.48) / (H * 0.52))) if y > H * 0.48 else 0
            ramp.putpixel((0, y), min(255, max(top, bot)))
        bg = Image.composite(Image.new("RGB", (W, H), (6, 6, 10)), bg, ramp.resize((W, H)))
    elif style == "minimal":
        bg = Image.new("RGB", (W, H))
        for y in range(H):
            t = y / H
            bg.paste((int(15 + 7 * t), int(15 + 6 * t), int(22 + 14 * t)), (0, y, W, y + 1))
        if poster is not None:
            bg = Image.blend(bg, _cover(poster).filter(ImageFilter.GaussianBlur(60)), 0.13)
    else:  # neon
        if poster is not None:
            bg = _cover(poster).filter(ImageFilter.GaussianBlur(46))
        else:
            bg = Image.new("RGB", (W, H))
            for y in range(H):
                t = y / H
                bg.paste((int(24 + 90 * t), int(8 + 20 * t), int(48 + 130 * (1 - t))), (0, y, W, y + 1))
        bg = Image.blend(bg, Image.new("RGB", (W, H), (8, 8, 12)), 0.5)
        ramp = Image.new("L", (1, H), 0)
        for y in range(H):
            ramp.putpixel((0, y), 0 if y < H * 0.42 else int(215 * ((y - H * 0.42) / (H * 0.58))))
        bg = Image.composite(Image.new("RGB", (W, H), (5, 5, 9)), bg, ramp.resize((W, H)))
    img = bg
    draw = ImageDraw.Draw(img)

    def gtext(y, text, f, c1, c2):
        """Centered horizontal-gradient text with a soft drop shadow (for the brand)."""
        tw = int(draw.textlength(text, font=f)); th = int(f.size * 1.7)
        x0 = int((W - tw) / 2) - 6
        mask = Image.new("L", (tw + 12, th), 0)
        ImageDraw.Draw(mask).text((6, 0), text, font=f, fill=255)
        sh = Image.new("L", (tw + 12, th), 0)
        ImageDraw.Draw(sh).text((6, 0), text, font=f, fill=190)
        sh = sh.filter(ImageFilter.GaussianBlur(9))
        img.paste(Image.new("RGB", (tw + 12, th), (0, 0, 0)), (x0, int(y) + 5), sh)
        grad = Image.new("RGB", (tw + 12, th))
        for x in range(tw + 12):
            t = x / max(1, tw + 11)
            grad.paste(tuple(int(a + (b - a) * t) for a, b in zip(c1, c2)), (x, 0, x + 1, th))
        img.paste(grad, (x0, int(y)), mask)

    def ctext(y, text, f, fill=(255, 255, 255), shadow=True):
        x = (W - draw.textlength(text, font=f)) / 2
        if shadow:
            draw.text((x + 2, y + 3), text, font=f, fill=(0, 0, 0))
        draw.text((x, y), text, font=f, fill=fill)

    def wrap(text, f, max_w):
        out, cur = [], ""
        for w in text.split():
            t = (cur + " " + w).strip()
            if draw.textlength(t, font=f) <= max_w or not cur:
                cur = t
            else:
                out.append(cur); cur = w
        if cur:
            out.append(cur)
        return out[:3]

    # ---- Brand header ----
    brand = "\u00bfQUI\u00c9N VA?"
    bsize = 60
    fb = font("title", bsize, 900)
    while draw.textlength(brand, font=fb) > W - 150 and bsize > 30:
        bsize -= 2; fb = font("title", bsize, 900)
    if neon_accents:
        gtext(92, brand, fb, CYAN, MAGENTA)
    else:
        ctext(92, brand, fb, fill=(255, 255, 255), shadow=True)
    fs = font("body", 26, 500)
    ctext(96 + int(bsize * 1.35), "L O S   P L A N E S   D E L   F I N D E", fs,
          fill=(205, 210, 224), shadow=(style != "minimal"))

    # ---- Prepare event texts ----
    name = re.sub(r"[\s*_~|]+$", "", (ev.get("name") or "Fiesta").strip()) or "Fiesta"
    nsize = 60
    fn = font("title", nsize, 800)
    lines = wrap(name, fn, W - 150)
    if len(lines) >= 3:
        nsize = 50; fn = font("title", nsize, 800); lines = wrap(name, fn, W - 140)
    line2 = "  \u00b7  ".join([x for x in [ev.get("venue", ""), _es_share_date(ev.get("date", ""))] if x])
    pl = _price_line(ev)
    block_h = len(lines) * int(nsize * 1.24) + (66 if line2 else 0) + (104 if pl else 0)

    # ---- Poster card (neon/minimal) ----
    card_top = 320
    if style != "full" and poster is not None:
        pw = 840
        full_h = int(poster.height * (pw / poster.width))
        ph = min(full_h, 1020)
        pc = poster.resize((pw, full_h)).crop((0, 0, pw, ph))
        radius = 48
        mask = Image.new("L", (pw, ph), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, pw, ph), radius=radius, fill=255)
        px = (W - pw) // 2
        shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle((px, card_top, px + pw, card_top + ph), radius=radius,
                                                 fill=(0, 0, 0, 170 if neon_accents else 120))
        shadow = shadow.filter(ImageFilter.GaussianBlur(28))
        img = Image.alpha_composite(img.convert("RGBA"), shadow).convert("RGB")
        img.paste(pc, (px, card_top), mask)
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle((px, card_top, px + pw, card_top + ph), radius=radius,
                               outline=(CYAN if neon_accents else (255, 255, 255)),
                               width=4 if neon_accents else 3)
        text_y = card_top + ph + 60
    elif style == "full":
        text_y = max(560, (H - 170) - block_h)  # bottom-anchored, over the poster
    else:
        text_y = 660

    # ---- Event name + venue/date + price ----
    for ln in lines:
        ctext(text_y, ln, fn)
        text_y += int(nsize * 1.24)
    text_y += 6
    if line2:
        ctext(text_y, line2, font("body", 40, 500), fill=(214, 216, 226))
        text_y += 66
    if pl:
        f3 = font("body", 40, 700)
        tw = draw.textlength(pl, font=f3)
        px0 = (W - tw) / 2 - 36
        draw.rounded_rectangle((px0, text_y + 10, px0 + tw + 72, text_y + 84), radius=37, fill=LIME)
        draw.text(((W - tw) / 2, text_y + 22), pl, font=f3, fill=(10, 12, 8))
        text_y += 104

    # ---- Footer CTA pill ----
    foot = "M\u00edralo en \u00bfQui\u00e9n va?"
    ff = font("body", 34, 600)
    fw = draw.textlength(foot, font=ff)
    fx = (W - fw) / 2
    draw.rounded_rectangle((fx - 40, H - 132, fx + fw + 40, H - 56), radius=40, fill=(18, 20, 30))
    draw.rounded_rectangle((fx - 40, H - 132, fx + fw + 40, H - 56), radius=40, outline=(0, 240, 255), width=3)
    draw.text((fx, H - 118), foot, font=ff, fill=(0, 240, 255))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    buf.seek(0)
    return StarletteResponse(content=buf.getvalue(), media_type="image/jpeg",
                             headers={"Cache-Control": "public, max-age=3600",
                                      "Content-Disposition": f'inline; filename="quienva-{event_id}.jpg"'})


@api_router.get("/og-city/{slug}.jpg")
async def og_city_image(slug: str, request: Request):
    """Dynamic 1200x630 social/OG banner for a city, built from the poster of the
    featured upcoming event (blurred cover background + poster card + city name +
    live plan count). Falls back to a clean brand gradient when there is no poster.
    Served via Vercel rewrite /og-city/:slug.jpg -> /api/og-city/:slug.jpg."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    W, H = 1200, 630
    front = _frontend_base(request)
    city_id = _CITY_SLUGS.get(slug.lower())
    label = next((c["label"] for c in SUPPORTED_CITIES if c["id"] == city_id), (city_id or slug.title()))
    short = label.split(" / ")[0].split(" de ")[0].strip()

    def _font(kind, size):
        fname = "Unbounded.ttf" if kind == "title" else "Outfit.ttf"
        return ImageFont.truetype(os.path.join(_ASSETS_FONTS, fname), size)

    try:
        poster, n = None, 0
        if city_id:
            events = await _upcoming_for_city(city_id, limit=30)
            n = len(events)
            for ev in events:
                u = ev.get("image_url") or ""
                if u.startswith("http"):
                    try:
                        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                            r = await c.get(u)
                        if r.status_code == 200:
                            poster = Image.open(io.BytesIO(r.content)).convert("RGB")
                            break
                    except Exception:
                        poster = None

        def _cover(im, w, h):
            bw, bh = im.size
            s = max(w / bw, h / bh)
            rr = im.resize((int(bw * s) + 1, int(bh * s) + 1))
            bx = (rr.width - w) // 2
            by = (rr.height - h) // 2
            return rr.crop((bx, by, bx + w, by + h))

        if poster is not None:
            bg = _cover(poster, W, H).filter(ImageFilter.GaussianBlur(30))
            bg = Image.blend(bg, Image.new("RGB", (W, H), (8, 8, 12)), 0.5)
        else:
            bg = Image.new("RGB", (W, H), (10, 10, 12))
            for y in range(H):
                t = y / H
                bg.paste((int(20 + 60 * (1 - t)), int(6 + 10 * t), int(36 + 70 * t)), (0, y, W, y + 1))
        # Left-to-right dark ramp so the text column stays legible over any poster.
        ramp = Image.new("L", (W, 1), 0)
        for x in range(W):
            ramp.putpixel((x, 0), int(215 * (1 - min(1.0, x / (W * 0.62)))))
        ramp = ramp.resize((W, H))
        img = Image.composite(Image.new("RGB", (W, H), (5, 5, 9)), bg, ramp)
        draw = ImageDraw.Draw(img)

        # Featured poster as a rounded card on the right.
        if poster is not None:
            pw = 300
            full_h = int(poster.height * (pw / poster.width))
            ph = min(full_h, 486)
            pc = poster.resize((pw, full_h)).crop((0, 0, pw, ph))
            px = W - pw - 72
            py = (H - ph) // 2
            mask = Image.new("L", (pw, ph), 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, pw, ph), 26, fill=255)
            img.paste(pc, (px, py), mask)
            draw.rounded_rectangle((px, py, px + pw, py + ph), 26, outline=(255, 255, 255), width=3)

        # Brand + accent + city name + tagline + live plan count.
        draw.text((70, 60), "\u00bfQui\u00e9n va?", font=_font("title", 42), fill=(255, 255, 255))
        draw.rounded_rectangle((72, 150, 192, 162), 6, fill=(255, 0, 85))
        fcity = _font("title", 104 if len(short) <= 9 else 74)
        draw.text((68, 188), short, font=fcity, fill=(255, 255, 255))
        ty = 188 + int(fcity.size * 1.12)
        draw.text((72, ty), "Fiestas y discotecas \u00b7 qui\u00e9n va con tus amigos",
                  font=_font("body", 33), fill=(206, 209, 221))
        if n:
            draw.text((72, ty + 50), f"{n} planes esta semana", font=_font("body", 30), fill=(0, 240, 255))

        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=85)
        buf.seek(0)
        return StarletteResponse(content=buf.getvalue(), media_type="image/jpeg",
                                 headers={"Cache-Control": "public, max-age=3600, s-maxage=21600",
                                          "Content-Disposition": f'inline; filename="quienva-{slug}.jpg"'})
    except Exception as _e:
        logger.warning(f"og_city_image failed for {slug}: {_e}")
        # Fall back to the static branded banner shipped in the frontend.
        return StarletteResponse(status_code=302, content="",
                                 headers={"Location": f"{front}/og/og-{slug.lower()}.png"})




# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------
async def _notify_admins_new_signup(new_user: dict):
    """Notify every admin that a new user just registered. Global, opt-out via
    app_settings key 'admin_signup_alerts' (ON by default). Never blocks signup."""
    try:
        s = await db.app_settings.find_one({"key": "admin_signup_alerts"}, {"_id": 0})
        if s is not None and s.get("value") is False:
            return  # disabled by admin
        uname = new_user.get("username", "")
        name = new_user.get("name", "")
        city = new_user.get("city", "")
        provider = new_user.get("auth_provider", "email")
        msg = f"🆕 Nuevo registro: @{uname}" + (f" ({name})" if name else "")
        if city:
            msg += f" · {city}"
        async for a in db.users.find({"role": "admin"}, {"_id": 0, "user_id": 1}):
            if a["user_id"] == new_user.get("user_id"):
                continue
            await create_notification(a["user_id"], "admin_new_signup", msg,
                                      {"type": "admin_new_signup",
                                       "new_user_id": new_user.get("user_id"),
                                       "username": uname, "provider": provider,
                                       "url": "/admin"})
    except Exception as e:
        logger.warning(f"[signup-alert] failed: {e}")


@api_router.post("/auth/register")
async def register(inp: RegisterInput, response: Response):
    email = inp.email.lower().strip()
    username = inp.username.lower().strip().replace(" ", "")
    # +18 gate — birthdate is required and must be an adult
    if not inp.birthdate or not is_adult(inp.birthdate):
        raise HTTPException(status_code=400, detail="Debes ser mayor de 18 años para usar ¿Quién va?")
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Ese email ya está registrado")
    if await db.users.find_one({"username": username}):
        raise HTTPException(status_code=400, detail="Ese nombre de usuario ya existe")
    user = {
        "user_id": f"user_{uuid.uuid4().hex[:12]}",
        "email": email,
        "username": username,
        "name": inp.name.strip(),
        "picture": "",
        "city": inp.city,
        "role": "user",
        "auth_provider": "email",
        "password_hash": hash_password(inp.password),
        "birthdate": inp.birthdate.strip()[:10],
        "attendance_privacy": "amigos",
        "moment_privacy": "amigos",
        "blocked_users": [],
        "city_change_alerts": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    ph = phone_hash(inp.phone) if inp.phone else None
    if ph:
        user["phone_hash"] = ph
    if inp.source:
        user["source"] = inp.source.strip().lower()[:40]
    await db.users.insert_one(user)
    await _notify_admins_new_signup(user)
    token = await create_session(user["user_id"])
    set_session_cookie(response, token)
    return {"user": public_user(user), "token": token}


class TrackClickInput(BaseModel):
    source: str


@api_router.post("/track/click")
async def track_click(inp: TrackClickInput):
    """Log a bio-link click by source (e.g. 'ig', 'tt'). Public, fire-and-forget."""
    src = (inp.source or "").strip().lower()[:40] or "unknown"
    try:
        await db.link_clicks.insert_one({
            "source": src,
            "ts": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        logger.warning(f"[track] click insert failed: {e}")
    return {"ok": True}


@api_router.get("/track/stats")
async def track_stats(user: dict = Depends(require_admin)):
    """Admin: clicks and signups grouped by marketing source (ig / tt / ...)."""
    clicks = {}
    async for row in db.link_clicks.aggregate([
        {"$group": {"_id": "$source", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}},
    ]):
        clicks[row["_id"] or "unknown"] = row["n"]
    signups = {}
    async for row in db.users.aggregate([
        {"$match": {"source": {"$exists": True, "$ne": None}}},
        {"$group": {"_id": "$source", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}},
    ]):
        signups[row["_id"] or "unknown"] = row["n"]
    return {"clicks": clicks, "signups": signups}


@api_router.post("/auth/login")
async def login(inp: LoginInput, response: Response):
    email = inp.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user or not user.get("password_hash") or not verify_password(inp.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Email o contraseña incorrectos")
    token = await create_session(user["user_id"])
    set_session_cookie(response, token)
    return {"user": public_user(user), "token": token}


class GoogleCallbackInput(BaseModel):
    code: str
    redirect_uri: str


@api_router.get("/auth/google/config")
async def google_config():
    return {"enabled": GOOGLE_ENABLED, "client_id": GOOGLE_CLIENT_ID}


@api_router.post("/auth/google/callback")
async def google_callback(inp: GoogleCallbackInput, response: Response):
    # REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    if not GOOGLE_ENABLED:
        raise HTTPException(status_code=400, detail="Google login no está configurado")
    try:
        token_res = requests.post("https://oauth2.googleapis.com/token", data={
            "code": inp.code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": inp.redirect_uri,
            "grant_type": "authorization_code",
        }, timeout=30)
        token_res.raise_for_status()
        access_token = token_res.json()["access_token"]
        info = requests.get("https://www.googleapis.com/oauth2/v3/userinfo",
                            headers={"Authorization": f"Bearer {access_token}"}, timeout=30)
        info.raise_for_status()
        data = info.json()
    except Exception as e:
        logger.error(f"Google OAuth error: {e}")
        raise HTTPException(status_code=401, detail="No se pudo validar el login de Google")

    email = (data.get("email") or "").lower().strip()
    if not email:
        raise HTTPException(status_code=401, detail="Google no devolvió email")
    existing = await db.users.find_one({"email": email})
    if existing:
        user = existing
        if not user.get("picture") and data.get("picture"):
            await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"picture": data["picture"]}})
            user["picture"] = data["picture"]
    else:
        base_username = (email.split("@")[0] if email else "user").lower().replace(".", "")
        username = base_username
        while await db.users.find_one({"username": username}):
            username = f"{base_username}{secrets.randbelow(9999)}"
        user = {
            "user_id": f"user_{uuid.uuid4().hex[:12]}",
            "email": email,
            "username": username,
            "name": data.get("name", "Usuario"),
            "picture": data.get("picture", ""),
            "city": "Palma de Mallorca",
            "role": "user",
            "auth_provider": "google",
            "attendance_privacy": "amigos",
            "moment_privacy": "amigos",
            "blocked_users": [],
            "city_change_alerts": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.users.insert_one(user)
        await _notify_admins_new_signup(user)

    token = await create_session(user["user_id"])
    set_session_cookie(response, token)
    return {"user": public_user(user), "token": token}


class AppleCallbackInput(BaseModel):
    identity_token: str
    code: Optional[str] = None
    # Apple only sends the name on the FIRST authorization; it is a hint, never
    # proof of identity (the verified JWT claims are authoritative).
    name: Optional[str] = None
    email: Optional[str] = None


APPLE_BUNDLE_ID = os.environ.get("APPLE_BUNDLE_ID", "me.quienva.app")
APPLE_ISSUER = "https://appleid.apple.com"
# PyJWKClient fetches + caches Apple's rotating public keys and selects the right
# one by the JWT 'kid' header automatically.
_APPLE_JWK_CLIENT = jwt.PyJWKClient("https://appleid.apple.com/auth/keys")


@api_router.post("/auth/apple/callback")
async def apple_callback(inp: AppleCallbackInput, response: Response):
    """Native 'Sign in with Apple' (iOS). Verifies the identity token (JWT)
    against Apple's public keys, validates audience (our bundle id) + issuer,
    then creates/logs in a user and issues our own session token — same
    response shape as the Google callback."""
    try:
        signing_key = _APPLE_JWK_CLIENT.get_signing_key_from_jwt(inp.identity_token)
        claims = jwt.decode(
            inp.identity_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=APPLE_BUNDLE_ID,
            issuer=APPLE_ISSUER,
            options={"require": ["iss", "aud", "sub", "exp", "iat"]},
        )
    except Exception as e:
        logger.error(f"Apple Sign In verify error: {e}")
        raise HTTPException(status_code=401, detail="No se pudo validar el login de Apple")

    apple_sub = claims.get("sub")
    if not apple_sub:
        raise HTTPException(status_code=401, detail="Apple no devolvió identificador")
    # Apple's email can be a private relay address (…@privaterelay.appleid.com) or
    # absent on later logins; tolerate both. Client-supplied email is only a hint.
    token_email = (claims.get("email") or inp.email or "").lower().strip()
    email_verified = str(claims.get("email_verified")).lower() == "true"

    # 1) Returning Apple user — identified by the stable 'sub' (the durable key).
    user = await db.users.find_one({"apple_sub": apple_sub})
    # 2) Else link to an existing account by VERIFIED email.
    if not user and token_email and email_verified:
        existing = await db.users.find_one({"email": token_email})
        if existing:
            await db.users.update_one({"user_id": existing["user_id"]}, {"$set": {"apple_sub": apple_sub}})
            existing["apple_sub"] = apple_sub
            user = existing
    # 3) Else create a new account (mirrors the Google flow; birthdate is asked
    #    later via the profile, same as Google users).
    if not user:
        name = (inp.name or "").strip() or (token_email.split("@")[0] if token_email else "Usuario")
        base_username = ((token_email.split("@")[0] if token_email else f"apple{secrets.randbelow(999999)}")
                         .lower().replace(".", "").replace("+", ""))[:20] or "user"
        username = base_username
        while await db.users.find_one({"username": username}):
            username = f"{base_username}{secrets.randbelow(9999)}"
        user = {
            "user_id": f"user_{uuid.uuid4().hex[:12]}",
            "email": token_email or None,
            "username": username,
            "name": name,
            "picture": "",
            "city": "Palma de Mallorca",
            "role": "user",
            "auth_provider": "apple",
            "apple_sub": apple_sub,
            "attendance_privacy": "amigos",
            "moment_privacy": "amigos",
            "blocked_users": [],
            "city_change_alerts": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.users.insert_one(user)
        await _notify_admins_new_signup(user)

    token = await create_session(user["user_id"])
    set_session_cookie(response, token)
    return {"user": public_user(user), "token": token}


@api_router.post("/auth/logout")
async def logout(request: Request, response: Response):
    token = await get_token_from_request(request)
    if token:
        await db.sessions.delete_one({"session_token": token})
    response.delete_cookie("session_token", path="/")
    return {"ok": True}


@api_router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return public_user(user)


@api_router.put("/auth/profile")
async def update_profile(inp: ProfileUpdate, user: dict = Depends(get_current_user)):
    updates = {}
    if inp.name is not None:
        updates["name"] = inp.name.strip()
    if inp.city is not None:
        updates["city"] = inp.city
    if inp.picture is not None:
        updates["picture"] = inp.picture
    if inp.username is not None:
        uname = inp.username.lower().strip().replace(" ", "")
        clash = await db.users.find_one({"username": uname, "user_id": {"$ne": user["user_id"]}})
        if clash:
            raise HTTPException(status_code=400, detail="Ese nombre de usuario ya existe")
        updates["username"] = uname
    if inp.birthdate is not None:
        if not is_adult(inp.birthdate):
            raise HTTPException(status_code=400, detail="Debes ser mayor de 18 años para usar ¿Quién va?")
        updates["birthdate"] = inp.birthdate.strip()[:10]
    if inp.phone is not None:
        ph = phone_hash(inp.phone)
        if ph:
            updates["phone_hash"] = ph
    if inp.attendance_privacy is not None:
        if inp.attendance_privacy not in ATTENDANCE_PRIVACY_VALUES:
            raise HTTPException(status_code=400, detail="Valor de privacidad inválido")
        updates["attendance_privacy"] = inp.attendance_privacy
        # Denormalise onto the user's interests so event reads stay fast.
        await db.interests.update_many(
            {"user_id": user["user_id"]},
            {"$set": {"privacy": inp.attendance_privacy}},
        )
    if inp.moment_privacy is not None:
        if inp.moment_privacy not in MOMENT_PRIVACY_VALUES:
            raise HTTPException(status_code=400, detail="Valor de privacidad inválido")
        updates["moment_privacy"] = inp.moment_privacy
    if updates:
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": updates})
        user.update(updates)
    return public_user(user)


# ---------------------------------------------------------------------------
# Friends
# ---------------------------------------------------------------------------
async def accepted_friend_ids(user_id: str | None) -> List[str]:
    if user_id is None:
        return []
    ids = set()
    async for f in db.friendships.find({"status": "accepted",
                                        "$or": [{"requester_id": user_id}, {"addressee_id": user_id}]}):
        ids.add(f["addressee_id"] if f["requester_id"] == user_id else f["requester_id"])
    return list(ids)


async def friendship_status_map(user_id: str) -> dict:
    """Map other_user_id -> {'status': ..., 'direction': 'in'|'out', 'request_id': ...}"""
    result = {}
    async for f in db.friendships.find({"$or": [{"requester_id": user_id}, {"addressee_id": user_id}]}):
        other = f["addressee_id"] if f["requester_id"] == user_id else f["requester_id"]
        result[other] = {
            "status": f["status"],
            "direction": "out" if f["requester_id"] == user_id else "in",
            "request_id": f["id"],
        }
    return result


async def mutual_friends_count(my_friend_ids: List[str], other_id: str) -> int:
    if not my_friend_ids:
        return 0
    other_ids = set(await accepted_friend_ids(other_id))
    return len(other_ids.intersection(my_friend_ids))


@api_router.get("/users/search")
async def search_users(q: str, user: dict = Depends(get_current_user)):
    q = q.strip().lower()
    if not q:
        return []
    cursor = db.users.find({
        "user_id": {"$ne": user["user_id"]},
        "$or": [
            {"username": {"$regex": q, "$options": "i"}},
        ],
    }, {"_id": 0}).limit(30)
    fmap = await friendship_status_map(user["user_id"])
    my_friends = await accepted_friend_ids(user["user_id"])
    blocked = await blocked_relation_ids(user["user_id"])
    out = []
    async for u in cursor:
        if u["user_id"] in blocked:
            continue
        pu = public_user(u)
        pu["name"] = display_name(u)
        pu.pop("email", None)
        rel = fmap.get(u["user_id"])
        pu["relationship"] = rel or {"status": "none"}
        pu["mutual_count"] = await mutual_friends_count(my_friends, u["user_id"])
        out.append(pu)
        if len(out) >= 20:
            break
    return out


@api_router.get("/users/by-username/{username}")
async def get_by_username(username: str, user: dict = Depends(get_current_user)):
    u = await db.users.find_one({"username": username.lower().strip()}, {"_id": 0})
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    pu = public_user(u)
    fmap = await friendship_status_map(user["user_id"])
    pu["relationship"] = fmap.get(u["user_id"]) or {"status": "none"}
    my_friends = await accepted_friend_ids(user["user_id"])
    pu["mutual_count"] = await mutual_friends_count(my_friends, u["user_id"])
    pu["name"] = display_name(u)
    pu.pop("email", None)
    return pu


async def do_friend_request(user: dict, target: str) -> dict:
    if target == user["user_id"]:
        raise HTTPException(status_code=400, detail="No puedes añadirte a ti mismo")
    if not await db.users.find_one({"user_id": target}):
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    existing = await db.friendships.find_one({
        "$or": [
            {"requester_id": user["user_id"], "addressee_id": target},
            {"requester_id": target, "addressee_id": user["user_id"]},
        ]
    })
    if existing:
        if existing["status"] == "accepted":
            return {"status": "accepted"}
        # If the other person already sent a request, accept it
        if existing["requester_id"] == target and existing["status"] == "pending":
            await db.friendships.update_one({"id": existing["id"]}, {"$set": {"status": "accepted"}})
            await create_notification(target, "friend_accept",
                                      f"{display_name(user)} aceptó tu solicitud de amistad",
                                      {"user_id": user["user_id"]})
            return {"status": "accepted"}
        return {"status": "pending", "request_id": existing["id"]}
    fr = {
        "id": str(uuid.uuid4()),
        "requester_id": user["user_id"],
        "addressee_id": target,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.friendships.insert_one(fr)
    await create_notification(target, "friend_request",
                              f"{display_name(user)} te ha enviado una solicitud de amistad",
                              {"user_id": user["user_id"], "request_id": fr["id"]})
    return {"status": "pending", "request_id": fr["id"]}


@api_router.post("/friends/request")
async def send_friend_request(inp: FriendActionInput, user: dict = Depends(get_current_user)):
    return await do_friend_request(user, inp.user_id)


@api_router.post("/friends/request-by-username")
async def send_friend_request_by_username(inp: UsernameInput, user: dict = Depends(get_current_user)):
    target = await db.users.find_one({"username": inp.username.lower().strip()}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    result = await do_friend_request(user, target["user_id"])
    result["user"] = public_user(target)
    result["user"]["name"] = display_name(target)
    result["user"].pop("email", None)
    return result


@api_router.post("/friends/respond")
async def respond_friend(inp: FriendRespondInput, user: dict = Depends(get_current_user)):
    fr = await db.friendships.find_one({"id": inp.request_id})
    if not fr or fr["addressee_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if inp.accept:
        await db.friendships.update_one({"id": fr["id"]}, {"$set": {"status": "accepted"}})
        _invalidate_stats_cache(fr["requester_id"])
        _invalidate_stats_cache(user["user_id"])
        await create_notification(fr["requester_id"], "friend_accept",
                                  f"{display_name(user)} aceptó tu solicitud de amistad",
                                  {"user_id": user["user_id"]})
        return {"status": "accepted"}
    await db.friendships.delete_one({"id": fr["id"]})
    return {"status": "rejected"}


@api_router.delete("/friends/{friend_id}")
async def remove_friend(friend_id: str, user: dict = Depends(get_current_user)):
    await db.friendships.delete_one({
        "$or": [
            {"requester_id": user["user_id"], "addressee_id": friend_id},
            {"requester_id": friend_id, "addressee_id": user["user_id"]},
        ]
    })
    return {"ok": True}


@api_router.get("/friends")
async def list_friends(user: dict = Depends(get_current_user)):
    ids = await accepted_friend_ids(user["user_id"])
    out = []
    async for u in db.users.find({"user_id": {"$in": ids}}, {"_id": 0}):
        pu = public_user(u)
        pu["name"] = display_name(u)
        pu.pop("email", None)
        out.append(pu)
    return out


@api_router.get("/friends/requests")
async def list_requests(user: dict = Depends(get_current_user)):
    incoming = []
    my_friends = await accepted_friend_ids(user["user_id"])
    async for f in db.friendships.find({"addressee_id": user["user_id"], "status": "pending"}):
        requester = await db.users.find_one({"user_id": f["requester_id"]}, {"_id": 0})
        if requester:
            pu = public_user(requester)
            pu["name"] = display_name(requester)
            pu.pop("email", None)
            pu["mutual_count"] = await mutual_friends_count(my_friends, requester["user_id"])
            incoming.append({"request_id": f["id"], "user": pu})
    return incoming


# ---------------------------------------------------------------------------
# Block & Report (trust & safety)
# ---------------------------------------------------------------------------
async def blocked_by_me(user_id: str) -> set:
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "blocked_users": 1})
    return set((u or {}).get("blocked_users", []))


async def blocked_relation_ids(user_id: str) -> set:
    """Everyone the user can't interact with: people they blocked + people who
    blocked them (visibility is mutual)."""
    ids = await blocked_by_me(user_id)
    async for u in db.users.find({"blocked_users": user_id}, {"_id": 0, "user_id": 1}):
        ids.add(u["user_id"])
    return ids


@api_router.post("/me/block")
async def block_user(inp: BlockInput, user: dict = Depends(get_current_user)):
    target = inp.user_id
    if target == user["user_id"]:
        raise HTTPException(status_code=400, detail="No puedes bloquearte a ti mismo")
    if not await db.users.find_one({"user_id": target}):
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    # Add to block list, drop any friendship / pending requests both ways.
    await db.users.update_one({"user_id": user["user_id"]},
                              {"$addToSet": {"blocked_users": target}})
    await db.friendships.delete_many({
        "$or": [
            {"requester_id": user["user_id"], "addressee_id": target},
            {"requester_id": target, "addressee_id": user["user_id"]},
        ]
    })
    _invalidate_stats_cache(user["user_id"])
    _invalidate_stats_cache(target)
    return {"ok": True, "blocked": target}


@api_router.post("/me/unblock")
async def unblock_user(inp: BlockInput, user: dict = Depends(get_current_user)):
    await db.users.update_one({"user_id": user["user_id"]},
                              {"$pull": {"blocked_users": inp.user_id}})
    return {"ok": True, "unblocked": inp.user_id}


@api_router.get("/me/blocked")
async def list_blocked(user: dict = Depends(get_current_user)):
    ids = list(await blocked_by_me(user["user_id"]))
    out = []
    async for u in db.users.find({"user_id": {"$in": ids}}, {"_id": 0}):
        out.append(public_other_user(u))
    return out


@api_router.post("/reports")
async def create_report(inp: ReportInput, user: dict = Depends(get_current_user)):
    valid_types = {"user", "moment", "album_photo", "message", "event"}
    if inp.target_type not in valid_types:
        raise HTTPException(status_code=400, detail="Tipo de reporte inválido")
    report = {
        "id": str(uuid.uuid4()),
        "reporter_id": user["user_id"],
        "target_type": inp.target_type,
        "target_id": inp.target_id,
        "reason": (inp.reason or "").strip()[:200],
        "note": (inp.note or "").strip()[:1000],
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.reports.insert_one(report)
    return {"ok": True, "id": report["id"]}


@api_router.get("/admin/reports")
async def admin_list_reports(admin: dict = Depends(require_admin), status: str = Query("open")):
    q = {} if status == "all" else {"status": status}
    out = []
    async for r in db.reports.find(q, {"_id": 0}).sort("created_at", -1).limit(200):
        reporter = await db.users.find_one({"user_id": r["reporter_id"]}, {"_id": 0})
        r["reporter"] = public_user(reporter) if reporter else None
        if r["target_type"] == "user":
            tu = await db.users.find_one({"user_id": r["target_id"]}, {"_id": 0})
            r["target_user"] = public_user(tu) if tu else None
        out.append(r)
    return out


@api_router.post("/admin/reports/{report_id}/resolve")
async def admin_resolve_report(report_id: str, admin: dict = Depends(require_admin)):
    await db.reports.update_one({"id": report_id}, {"$set": {"status": "resolved"}})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Contact matching (cold-start: find friends already on the app by phone)
# ---------------------------------------------------------------------------
@api_router.post("/me/match-contacts")
async def match_contacts(inp: MatchContactsInput, user: dict = Depends(get_current_user)):
    """Given a list of raw phone numbers from the device, return the users who
    are already on ¿Quién va?. We hash numbers and never store the raw list."""
    hashes = set()
    phone_by_hash = {}
    for raw in inp.phones[:2000]:
        h = phone_hash(raw)
        if h:
            hashes.add(h)
            phone_by_hash.setdefault(h, raw)  # remember which raw phone gave this hash
    if not hashes:
        return []
    fmap = await friendship_status_map(user["user_id"])
    my_friends = await accepted_friend_ids(user["user_id"])
    blocked = await blocked_relation_ids(user["user_id"])
    out = []
    async for u in db.users.find({"phone_hash": {"$in": list(hashes)}}, {"_id": 0}).limit(200):
        if u["user_id"] == user["user_id"] or u["user_id"] in blocked:
            continue
        rel = fmap.get(u["user_id"])
        pu = public_other_user(u)
        pu["relationship"] = rel or {"status": "none"}
        pu["mutual_count"] = await mutual_friends_count(my_friends, u["user_id"])
        # Echo back the caller's own contact phone that matched, so the app can
        # line each contact up with its status. It's the user's own contact.
        pu["matched_phone"] = phone_by_hash.get(u.get("phone_hash"))
        out.append(pu)
    return out



@api_router.delete("/me")
async def delete_my_account(user: dict = Depends(get_current_user)):
    """Permanently delete the signed-in user's account and personal data.
    Required by App Store Guideline 5.1.1(v): account deletion from within the app."""
    uid = user["user_id"]

    async def _wipe(coll, q):
        try:
            await coll.delete_many(q)
        except Exception as e:
            logger.warning(f"[delete-account] {coll.name}: {e}")

    # The user's own records across collections (best-effort; missing ones no-op).
    await _wipe(db.sessions, {"user_id": uid})
    await _wipe(db.interests, {"user_id": uid})
    await _wipe(db.push_subscriptions, {"user_id": uid})
    await _wipe(db.notifications, {"user_id": uid})
    await _wipe(db.moments, {"user_id": uid})
    await _wipe(db.tickets, {"user_id": uid})
    await _wipe(db.messages, {"sender_id": uid})
    await _wipe(db.reports, {"reporter_id": uid})
    await _wipe(db.friend_requests, {"$or": [{"from_user_id": uid}, {"to_user_id": uid},
                                             {"from_user": uid}, {"to_user": uid},
                                             {"requester_id": uid}, {"target_id": uid},
                                             {"user_id": uid}]})
    await _wipe(db.friendships, {"$or": [{"user_a": uid}, {"user_b": uid},
                                         {"user_id": uid}, {"friend_id": uid}]})
    # Remove me from anyone else's blocked / friends arrays.
    for field in ("blocked_users", "friends"):
        try:
            await db.users.update_many({field: uid}, {"$pull": {field: uid}})
        except Exception as e:
            logger.warning(f"[delete-account] pull {field}: {e}")
    # Finally, the account itself.
    await _wipe(db.users, {"user_id": uid})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------
def date_in_filter(event_date_str: str, flt: str) -> bool:
    try:
        d = date.fromisoformat(event_date_str)
    except Exception:
        return True
    today = datetime.now(ZoneInfo("Europe/Madrid")).date()
    if flt == "hoy":
        return d == today
    if flt == "finde":
        # upcoming Friday, Saturday, Sunday within the next 7 days
        days_until_fri = (4 - today.weekday()) % 7
        fri = today + timedelta(days=days_until_fri)
        sun = fri + timedelta(days=2)
        return fri <= d <= sun
    if flt == "semana":
        return today <= d <= today + timedelta(days=7)
    if flt == "pasados":
        return d < today
    # "all" (default) = upcoming events (today and future)
    return d >= today


async def serialize_event(ev: dict, user: dict, friend_ids: List[str], users_map: dict | None = None,
                          interests_by_event: dict | None = None,
                          follows_set: set | None = None,
                          my_ticket_ids: set | None = None) -> dict:
    if interests_by_event is not None:
        interests = interests_by_event.get(ev["id"], [])
    else:
        interests = []
        async for it in db.interests.find({"event_id": ev["id"]}):
            interests.append(it)

    # Batch-load friend users if not provided
    if users_map is None:
        needed = list({it["user_id"] for it in interests if it["user_id"] in friend_ids})
        users_map = {}
        if needed:
            async for u in db.users.find({"user_id": {"$in": needed}}, {"_id": 0}):
                users_map[u["user_id"]] = u

    my_status = None
    friends_going = []
    friends_interested = []
    friends_attended = []
    for it in interests:
        if it["user_id"] == user["user_id"]:
            my_status = it["status"]
        elif it["user_id"] in friend_ids:
            # Respect attendance privacy: "nadie" (ghost) hides the person from
            # everyone's lists. "todos"/"amigos" are both visible to friends.
            if it.get("privacy", "todos") == "nadie":
                continue
            fu = users_map.get(it["user_id"])
            if fu:
                entry = {"user_id": fu["user_id"], "name": display_name(fu), "picture": fu.get("picture", "")}
                if it["status"] == "voy":
                    friends_going.append(entry)
                elif it["status"] == "me_interesa":
                    friends_interested.append(entry)
                elif it["status"] == "estuve":
                    friends_attended.append(entry)

    # Ticket ownership (social proof + conversion). Cheap in bulk via my_ticket_ids;
    # full counts only when serializing a single event (event detail).
    if my_ticket_ids is not None:
        my_has_ticket = ev["id"] in my_ticket_ids
        total_tickets = None
        friends_with_ticket = []
    else:
        tks = [t async for t in db.tickets.find({"event_id": ev["id"]}, {"_id": 0})]
        my_has_ticket = any(t["user_id"] == user["user_id"] for t in tks)
        total_tickets = len(tks)
        friends_with_ticket = []
        for t in tks:
            if t["user_id"] in friend_ids and t["user_id"] != user["user_id"]:
                fu = users_map.get(t["user_id"]) if users_map else None
                if not fu:
                    fu = await db.users.find_one({"user_id": t["user_id"]}, {"_id": 0})
                if fu:
                    friends_with_ticket.append({"user_id": fu["user_id"], "name": display_name(fu), "picture": fu.get("picture", "")})

    return {
        "id": ev["id"],
        "name": ev["name"],
        "venue": ev["venue"],
        "address": ev.get("address", ""),
        "date": ev["date"],
        "time": ev.get("time", ""),
        "image_url": ev.get("image_url", ""),
        "genre": ev.get("genre", ""),
        "city": ev.get("city", ""),
        "has_commission": ev.get("has_commission", False),
        "commission_url": _commission_url_for(ev),
        # Official FourVenues embeddable widget (with our RRPP slug) for events we
        # carry on FourVenues; "" for ClubTickets-only parties. Frontend embeds it
        # to build trust, always keeping the "Comprar en FourVenues ↗" button too.
        "fv_embed_url": _fv_embed_url(ev),
        # Admin-only flag so the owner can spot their affiliate events in the feed.
        # Sent as null to everyone else → no marker, no info leak.
        "is_affiliate": (_event_is_mine(ev) if (user or {}).get("role") == "admin" else None),
        # Admin-only: the manual link override (if any) + what the automatic link
        # WOULD be, so the event edit panel can prefill / show "back to automatic".
        "link_override": (str(ev.get("link_override") or "") if (user or {}).get("role") == "admin" else None),
        "auto_commission_url": (_auto_commission_url_for(ev) if (user or {}).get("role") == "admin" else None),
        "more_info_url": ev.get("more_info_url", ""),
        "featured": bool(ev.get("featured", False)),
        # Pricing
        "price_tiers": ev.get("price_tiers", []),
        "sale_state": ev.get("sale_state", "no_a_la_venta"),
        "currency": ev.get("currency", "EUR"),
        "current_price": _current_price(ev),
        # Social
        "my_status": my_status,
        "is_following": (ev["id"] in follows_set) if follows_set is not None else None,
        "friends_going": friends_going,
        "friends_interested": friends_interested,
        "friends_attended": friends_attended,
        "total_going": (
            sum(1 for it in interests if it["status"] == "voy" and it.get("privacy", "todos") != "nadie")
            + (_guest_going_boost(ev) if (user or {}).get("user_id") is None else 0)
        ),
        "total_interested": sum(1 for it in interests if it["status"] == "me_interesa" and it.get("privacy", "todos") != "nadie"),
        "total_attended": sum(1 for it in interests if it["status"] == "estuve" and it.get("privacy", "todos") != "nadie"),
        # Tickets
        "my_has_ticket": my_has_ticket,
        "total_tickets": total_tickets,
        "friends_with_ticket": friends_with_ticket,
    }


def _current_price(ev: dict) -> Optional[float]:
    """The 'active' price shown on the event card. If no tiers, return None.
    Picks the first non-sold-out tier; if all tiers are sold out, returns the
    price of the last tier (so users can still see the last known price)."""
    tiers = ev.get("price_tiers") or []
    if not tiers:
        return None
    for t in tiers:
        if not t.get("sold_out"):
            return float(t.get("price", 0))
    # All sold out — show the last one
    return float(tiers[-1].get("price", 0))


async def _venue_priority_maps(city):
    """Admin-curated club importance for ordering the feed.

    Returns (order_by_scraper_venue_id, order_by_norm_venue_name) for a city,
    both mapping to `venues.order` (lower = more important). The admin controls
    this order from the "Prioridad de discotecas" panel. Used only to REORDER
    the feed; nothing is added, removed or marked."""
    order_by_name: dict = {}
    slug_to_order: dict = {}
    async for v in db.venues.find(
        {"city": city}, {"_id": 0, "name": 1, "order": 1, "scraper_slug": 1}
    ):
        o = v.get("order", 10_000)
        nm = _norm_name(v.get("name", ""))
        if nm:
            order_by_name[nm] = o
        sl = v.get("scraper_slug") or ""
        if sl:
            slug_to_order[sl] = o
    order_by_sid: dict = {}
    if slug_to_order:
        async for s in db.scraped_venues.find(
            {"slug": {"$in": list(slug_to_order.keys())}}, {"_id": 0, "slug": 1, "id": 1}
        ):
            if s.get("id"):
                order_by_sid[s["id"]] = slug_to_order.get(s.get("slug"), 10_000)
    return order_by_sid, order_by_name


@api_router.get("/events")
async def list_events(user: dict = Depends(get_optional_user),
                      date_filter: str = Query("all"),
                      genre: str = Query("all"),
                      q: str = Query(None),
                      city: str = Query(None)):
    friend_ids = await accepted_friend_ids(user["user_id"])
    query = {"city": city_query_value(_effective_city(user, city))}
    sort_dir = -1 if date_filter == "pasados" else 1

    # Push the date window straight into the Mongo query so we never load
    # irrelevant events (past ones for the default/upcoming feed) into memory.
    # This is the single biggest win when switching to a city with hundreds of
    # events: the DB uses the (city, date) index and returns only what's shown.
    _today_iso = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
    if date_filter == "pasados":
        query["date"] = {"$lt": _today_iso}
    else:
        # "all"/"hoy"/"finde"/"semana" are all upcoming (today and future).
        query["date"] = {"$gte": _today_iso}

    # Preload friend users once (avoid N+1 lookups inside serialize_event)
    users_map: dict = {}
    if friend_ids:
        async for u in db.users.find({"user_id": {"$in": list(friend_ids)}}, {"_id": 0}):
            users_map[u["user_id"]] = u

    # First pass: load & filter events
    _q_tokens = [t for t in (_norm_name(w) for w in (q or "").split()) if t]
    filtered_events = []
    async for ev in db.events.find(query, {"_id": 0}).sort("date", sort_dir):
        if not date_in_filter(ev["date"], date_filter):
            continue
        if genre != "all" and ev.get("genre") != genre:
            continue
        # Free-text search across party name, venue/club and genre (accent- and
        # case-insensitive via _norm_name). ALL typed terms must match. Powers the
        # feed search bar.
        if _q_tokens:
            _hay = "".join([
                _norm_name(ev.get("name", "")),
                _norm_name(ev.get("venue", "")),
                _norm_name(ev.get("genre", "")),
                _norm_name(ev.get("address", "")),
            ])
            if not all(t in _hay for t in _q_tokens):
                continue
        filtered_events.append(ev)

    # Merge cross-provider duplicates: the SAME night can arrive from two ticket
    # sources (e.g. a 528/Es Paradís party via both ClubTickets and Xceed). Collapse
    # events that share (venue, date, name) into ONE, preferring OUR affiliate
    # (ClubTickets) copy so the buy link earns commission; otherwise keep the copy
    # that carries a price. Events without a name are never merged (too ambiguous).
    if filtered_events:
        _merged: dict = {}
        _passthrough = []
        for ev in filtered_events:
            nm = _norm_name(ev.get("name", ""))
            if not nm:
                _passthrough.append(ev)
                continue
            key = (_norm_name(ev.get("venue", "")), ev.get("date", ""), nm)
            cur = _merged.get(key)
            if cur is None:
                _merged[key] = ev
                continue
            _mine_new, _mine_cur = _event_is_mine(ev), _event_is_mine(cur)
            if _mine_new and not _mine_cur:
                _merged[key] = ev
            elif _mine_new == _mine_cur and _current_price(cur) is None and _current_price(ev) is not None:
                _merged[key] = ev
        filtered_events = list(_merged.values()) + _passthrough

    # BULK LOAD all interests for these events in ONE query (avoid N+1). Loaded
    # BEFORE sorting so the feed can rank by real engagement (popularity).
    event_ids = [ev["id"] for ev in filtered_events]
    interests_by_event: dict = {eid: [] for eid in event_ids}
    if event_ids:
        async for it in db.interests.find({"event_id": {"$in": event_ids}}):
            interests_by_event.setdefault(it["event_id"], []).append(it)

    # Feed ordering (never in the "pasados" view, which stays newest-first by date).
    # This only REORDERS events — nothing is added, removed or visually marked, so
    # regular users can't tell it's intentional. Priority, top to bottom:
    #   1) OUR affiliate events (slug quienva) — always first (revenue lever).
    #   2) club importance — the admin-curated venue order (lower = higher).
    #   3) featured events within the same club-importance tier.
    #   4) popularity — real user activity (voy/me interesa) blended with how close
    #      the event is to selling (pocas entradas > a la venta > próximamente > agotado).
    #   5) date — keeps each tier chronological.
    if date_filter != "pasados":
        order_by_sid, order_by_name = await _venue_priority_maps(query["city"])

        def _venue_rank(e):
            sid = e.get("scraper_venue_id")
            if sid and sid in order_by_sid:
                return order_by_sid[sid]
            return order_by_name.get(_norm_name(e.get("venue", "")), 10_000)

        _SALE_URGENCY = {"pocas_entradas": 3, "a_la_venta": 2, "no_a_la_venta": 1, "agotado": 0}

        def _popularity(e):
            its = interests_by_event.get(e["id"], [])
            going = sum(1 for it in its if it.get("status") == "voy")
            interested = sum(1 for it in its if it.get("status") == "me_interesa")
            activity = going * 2 + interested
            urgency = _SALE_URGENCY.get(e.get("sale_state", "no_a_la_venta"), 1)
            return activity + urgency

        def _price_for_sort(e):
            p = _current_price(e)
            try:
                return float(p) if p is not None else 0.0
            except Exception:
                return 0.0

        # Two-tier ordering. The FIRST key (mine=0 / others=1) guarantees our
        # affiliate events always come first, so a "mine" club can never fall below
        # a non-affiliate one. WITHIN each tier the admin-curated club order
        # (_venue_rank, lower = higher) is the primary key, so "Prioridad de
        # discotecas" now works for OUR clubs too (e.g. Fitz above Amok), not only
        # for the rest.
        #   • OUR events (tier 0): club order → most EXPENSIVE first (≈ better
        #     commission) → soonest date.
        #   • Everyone else (tier 1): club order → featured → popularity → date.
        def _feed_sort_key(e):
            if _event_is_mine(e):
                return (0, _venue_rank(e), -_price_for_sort(e), e.get("date", ""), 0.0)
            return (1, _venue_rank(e), 0 if e.get("featured") else 1,
                    -_popularity(e), e.get("date", ""))

        filtered_events.sort(key=_feed_sort_key)

    # Load user's followed events (for is_following flag)
    # For guests (user_id=None), follows_set should be None so is_following=null
    if user["user_id"] is None:
        follows_set = None
    else:
        follows_set: set = set()
        if event_ids:
            async for f in db.event_follows.find(
                {"user_id": user["user_id"], "event_id": {"$in": event_ids}},
                {"_id": 0, "event_id": 1},
            ):
                follows_set.add(f["event_id"])

    my_ticket_ids = set(await db.tickets.distinct("event_id", {"user_id": user["user_id"]})) if user["user_id"] is not None else set()
    events = []
    for ev in filtered_events:
        events.append(await serialize_event(ev, user, friend_ids, users_map, interests_by_event, follows_set, my_ticket_ids))
    return events


@api_router.get("/events/genres")
async def list_genres(user: dict = Depends(get_optional_user), city: str = Query(None)):
    genres = await db.events.distinct("genre", {"city": city_query_value(_effective_city(user, city))})
    return [g for g in genres if g]


@api_router.get("/events/top-weekend")
async def top_weekend(user: dict = Depends(get_optional_user), city: str = Query(None)):
    """The upcoming event (next 7 days) where the most of your friends are going.

    Perf: dates are stored as ISO 'YYYY-MM-DD' strings, so we can filter the
    weekend window straight in the query (instead of scanning every event in the
    city). Interests are loaded in ONE bulk query (no per-event N+1), the ranking
    is done in memory, and only the winning event is serialized. This turns what
    used to be hundreds of sequential DB round-trips (~19s) into a couple.
    """
    friend_ids = await accepted_friend_ids(user["user_id"])
    # No friends → there is no "friends going" ranking to compute.
    if not friend_ids:
        return None

    today = datetime.now(ZoneInfo("Europe/Madrid")).date()
    week_end = today + timedelta(days=7)
    city_val = city_query_value(_effective_city(user, city))

    # Query only events inside the weekend window. Widen the upper bound by one day
    # so events stored with a time suffix on week_end are not missed; the exact
    # window is re-checked in Python below.
    weekend_events = []
    async for ev in db.events.find(
        {
            "city": city_val,
            "date": {"$gte": today.isoformat(), "$lte": (week_end + timedelta(days=1)).isoformat()},
        },
        {"_id": 0},
    ).sort("date", 1):
        try:
            d = date.fromisoformat(str(ev.get("date", ""))[:10])
        except Exception:
            continue
        if today <= d <= week_end:
            weekend_events.append(ev)

    if not weekend_events:
        return None

    event_ids = [ev["id"] for ev in weekend_events]

    # BULK: load every interest for these events in a single query (avoids N+1).
    interests_by_event: dict = {eid: [] for eid in event_ids}
    async for it in db.interests.find({"event_id": {"$in": event_ids}}):
        interests_by_event.setdefault(it["event_id"], []).append(it)

    # Rank in memory: pick the event with the most friends going ("voy"),
    # respecting ghost ("nadie") attendance privacy.
    best_ev = None
    best_count = 0
    for ev in weekend_events:
        cnt = 0
        for it in interests_by_event.get(ev["id"], []):
            if (
                it.get("user_id") in friend_ids
                and it.get("status") == "voy"
                and it.get("privacy", "todos") != "nadie"
            ):
                cnt += 1
        if cnt > best_count:
            best_count = cnt
            best_ev = ev

    if best_ev is None:
        return None

    # Serialize ONLY the winner. interests_by_event + users_map avoid extra queries;
    # tickets for a single event are cheap (one query), preserving the exact shape.
    needed = list(
        {
            it["user_id"]
            for it in interests_by_event.get(best_ev["id"], [])
            if it.get("user_id") in friend_ids
        }
    )
    users_map: dict = {}
    if needed:
        async for u in db.users.find({"user_id": {"$in": needed}}, {"_id": 0}):
            users_map[u["user_id"]] = u

    return await serialize_event(
        best_ev, user, friend_ids, users_map=users_map, interests_by_event=interests_by_event
    )


@api_router.get("/events/carousels")
async def event_carousels(user: dict = Depends(get_optional_user), city: str = Query(None)):
    """Home-page carousels: top del finde (list), lo que va tu grupo, descubrir géneros."""
    eff_city = _effective_city(user, city)
    # TTL cache (per user+city, 20s) — carousels are heavy but data doesn't change every second.
    _cache_key = (user["user_id"], eff_city)
    try:
        entry = _CAROUSELS_CACHE.get(_cache_key)
        if entry and (time.time() - entry[0]) < _CAROUSELS_TTL:
            return entry[1]
    except Exception:
        pass

    friend_ids = await accepted_friend_ids(user["user_id"])
    today = datetime.now(ZoneInfo("Europe/Madrid")).date()
    city = eff_city

    # Preload friend users once for the whole endpoint
    users_map: dict = {}
    if friend_ids:
        async for u in db.users.find({"user_id": {"$in": list(friend_ids)}}, {"_id": 0}):
            users_map[u["user_id"]] = u

    # Preload upcoming events for this city (single query, reused by all three carousels)
    all_upcoming = []
    async for ev in db.events.find({"city": city}, {"_id": 0}).sort("date", 1):
        try:
            d = date.fromisoformat(ev["date"])
        except Exception:
            continue
        if d < today:
            continue
        all_upcoming.append((d, ev))

    # BULK LOAD all interests for these events in ONE query (avoid N+1 per serialize_event)
    upcoming_ids = [ev["id"] for _, ev in all_upcoming]
    interests_by_event: dict = {eid: [] for eid in upcoming_ids}
    if upcoming_ids:
        async for it in db.interests.find({"event_id": {"$in": upcoming_ids}}):
            interests_by_event.setdefault(it["event_id"], []).append(it)

    # Load user's followed events (for is_following flag)
    # For guests (user_id=None), follows_set should be None so is_following=null
    if user["user_id"] is None:
        follows_set = None
    else:
        follows_set: set = set()
        if upcoming_ids:
            async for f in db.event_follows.find(
                {"user_id": user["user_id"], "event_id": {"$in": upcoming_ids}},
                {"_id": 0, "event_id": 1},
            ):
                follows_set.add(f["event_id"])

    # BULK LOAD user's own interests once (for discover_new "my_genres")
    my_interests = []
    if user["user_id"] is not None:
        async for it in db.interests.find({"user_id": user["user_id"]}):
            my_interests.append(it)
    my_event_ids = list({it["event_id"] for it in my_interests})
    my_events_map = {}
    if my_event_ids:
        async for ev in db.events.find({"id": {"$in": my_event_ids}}, {"_id": 0, "id": 1, "genre": 1}):
            my_events_map[ev["id"]] = ev

    my_ticket_ids = set(await db.tickets.distinct("event_id", {"user_id": user["user_id"]})) if user["user_id"] is not None else set()

    # ---- Top del finde: upcoming Fri-Sun (or next 7 days) sorted by attendance ----
    week_end = today + timedelta(days=7)
    weekend_serialized = [
        await serialize_event(ev, user, friend_ids, users_map, interests_by_event, follows_set, my_ticket_ids)
        for d, ev in all_upcoming if d <= week_end
    ]
    top_weekend_list = sorted(
        weekend_serialized,
        key=lambda e: (-(e["total_going"] + e["total_interested"]), e["date"]),
    )[:6]

    # ---- Lo que va tu grupo: upcoming events with at least one friend going/interested ----
    friends_going_list = []
    if friend_ids:
        for d, ev in all_upcoming:
            se = await serialize_event(ev, user, friend_ids, users_map, interests_by_event, follows_set, my_ticket_ids)
            if (len(se["friends_going"]) + len(se["friends_interested"])) > 0:
                friends_going_list.append(se)
        friends_going_list = sorted(
            friends_going_list,
            key=lambda e: (-(len(e["friends_going"]) * 2 + len(e["friends_interested"])), e["date"]),
        )[:8]

    # ---- Descubre géneros nuevos: upcoming events in genres the user has NOT interacted with ----
    my_genres = set()
    for it in my_interests:
        ev_g = my_events_map.get(it["event_id"])
        if ev_g and ev_g.get("genre"):
            my_genres.add(ev_g["genre"])
    discover_new = []
    for d, ev in all_upcoming:
        g = ev.get("genre")
        if not g or g in my_genres:
            continue
        discover_new.append(await serialize_event(ev, user, friend_ids, users_map, interests_by_event, follows_set, my_ticket_ids))
        if len(discover_new) >= 8:
            break

    result = {
        "top_weekend": top_weekend_list,
        "friends_going": friends_going_list,
        "discover_new": discover_new,
    }
    try:
        _CAROUSELS_CACHE[_cache_key] = (time.time(), result)
        if len(_CAROUSELS_CACHE) > 500:
            items = sorted(_CAROUSELS_CACHE.items(), key=lambda kv: kv[1][0])
            for k, _ in items[:250]:
                _CAROUSELS_CACHE.pop(k, None)
    except Exception:
        pass
    return result


@api_router.get("/me/streak")
async def my_streak(user: dict = Depends(get_current_user)):
    """Consecutive weeks the user went out (voy/estuve on an event that week)."""
    mondays = set()
    async for it in db.interests.find({"user_id": user["user_id"], "status": {"$in": ["voy", "estuve"]}}):
        ev = await db.events.find_one({"id": it["event_id"]}, {"_id": 0})
        if not ev:
            continue
        try:
            d = date.fromisoformat(ev["date"])
        except Exception:
            continue
        mondays.add(d - timedelta(days=d.weekday()))
    today = datetime.now(ZoneInfo("Europe/Madrid")).date()
    this_monday = today - timedelta(days=today.weekday())
    anchor = this_monday if this_monday in mondays else this_monday - timedelta(days=7)
    streak = 0
    while anchor in mondays:
        streak += 1
        anchor -= timedelta(days=7)
    return {"streak": streak}


# =========================
# BADGES / ACHIEVEMENTS
# =========================

BADGES_CATALOG = [
    # ===== ASISTENCIA =====
    {"id": "first_step", "name": "Primer paso", "desc": "Te apuntaste a tu primera fiesta", "emoji": "🎉", "tier": "bronze", "cat": "asistencia", "points": 10},
    {"id": "attended_1", "name": "Debut", "desc": "Marcaste 'estuve' en tu primera fiesta", "emoji": "🎊", "tier": "bronze", "cat": "asistencia", "points": 15},
    {"id": "night_owl", "name": "Búho nocturno", "desc": "Estuviste en 5 fiestas", "emoji": "🌙", "tier": "silver", "cat": "asistencia", "points": 30},
    {"id": "party_pro", "name": "Habitual", "desc": "Estuviste en 10 fiestas", "emoji": "🍻", "tier": "silver", "cat": "asistencia", "points": 50},
    {"id": "party_veteran", "name": "Veterano", "desc": "Estuviste en 20 fiestas", "emoji": "🏆", "tier": "gold", "cat": "asistencia", "points": 100},
    {"id": "party_master", "name": "Maestro de la noche", "desc": "Estuviste en 35 fiestas", "emoji": "🎭", "tier": "gold", "cat": "asistencia", "points": 175},
    {"id": "legend", "name": "Leyenda", "desc": "Estuviste en 50 fiestas", "emoji": "👑", "tier": "platinum", "cat": "asistencia", "points": 300},
    {"id": "immortal", "name": "Inmortal", "desc": "Estuviste en 100 fiestas", "emoji": "💎", "tier": "platinum", "cat": "asistencia", "points": 600},

    # ===== RACHAS DE DÍAS SEGUIDOS =====
    {"id": "day_streak_2", "name": "Dos noches", "desc": "2 días seguidos saliendo", "emoji": "🌗", "tier": "bronze", "cat": "racha", "points": 15},
    {"id": "day_streak_3", "name": "Finde entero", "desc": "3 días seguidos saliendo", "emoji": "🌈", "tier": "bronze", "cat": "racha", "points": 25},
    {"id": "day_streak_5", "name": "Cinco a fondo", "desc": "5 días seguidos saliendo", "emoji": "🔥", "tier": "silver", "cat": "racha", "points": 60},
    {"id": "day_streak_7", "name": "Semana intensa", "desc": "7 días seguidos saliendo", "emoji": "💫", "tier": "gold", "cat": "racha", "points": 120},
    {"id": "day_streak_10", "name": "Sin freno", "desc": "10 días seguidos saliendo", "emoji": "⚡", "tier": "gold", "cat": "racha", "points": 200},
    {"id": "day_streak_15", "name": "Modo bestia", "desc": "15 días seguidos saliendo", "emoji": "🦁", "tier": "platinum", "cat": "racha", "points": 350},

    # ===== RACHAS DE SEMANAS =====
    {"id": "week_streak_2", "name": "Racha en marcha", "desc": "2 semanas seguidas de salir", "emoji": "🔥", "tier": "bronze", "cat": "racha", "points": 20},
    {"id": "week_streak_4", "name": "Un mes al pie del cañón", "desc": "4 semanas seguidas saliendo", "emoji": "🌟", "tier": "silver", "cat": "racha", "points": 60},
    {"id": "week_streak_8", "name": "Imparable", "desc": "8 semanas seguidas saliendo", "emoji": "🚀", "tier": "silver", "cat": "racha", "points": 120},
    {"id": "week_streak_12", "name": "Máquina", "desc": "12 semanas seguidas saliendo", "emoji": "🤖", "tier": "gold", "cat": "racha", "points": 200},
    {"id": "week_streak_26", "name": "Medio año fiestero", "desc": "26 semanas seguidas", "emoji": "🏅", "tier": "platinum", "cat": "racha", "points": 500},

    # ===== ENTRE SEMANA =====
    {"id": "weekday_1", "name": "Miércoles rebelde", "desc": "1 fiesta entre semana", "emoji": "🗡️", "tier": "bronze", "cat": "temporal", "points": 15},
    {"id": "weekday_warrior", "name": "Guerrero entre semana", "desc": "3 fiestas de lunes a jueves", "emoji": "⚔️", "tier": "silver", "cat": "temporal", "points": 40},
    {"id": "weekday_boss", "name": "Jefe entre semana", "desc": "10 fiestas de lunes a jueves", "emoji": "🛡️", "tier": "gold", "cat": "temporal", "points": 100},
    {"id": "sunday_survivor", "name": "Sobrevivir domingo", "desc": "Saliste un domingo", "emoji": "☀️", "tier": "bronze", "cat": "temporal", "points": 15},
    {"id": "sunday_lover", "name": "Enamorado del domingo", "desc": "3 domingos de fiesta", "emoji": "🌞", "tier": "silver", "cat": "temporal", "points": 50},
    {"id": "monday_king", "name": "Rey del lunes", "desc": "Saliste un lunes", "emoji": "🎩", "tier": "silver", "cat": "temporal", "points": 40},

    # ===== SOCIAL =====
    {"id": "social_1", "name": "Primer amigo", "desc": "Aceptaste tu primera amistad", "emoji": "👋", "tier": "bronze", "cat": "social", "points": 10},
    {"id": "social_5", "name": "Con amigos", "desc": "5 amigos aceptados", "emoji": "🤝", "tier": "bronze", "cat": "social", "points": 20},
    {"id": "social_10", "name": "Grupito", "desc": "10 amigos aceptados", "emoji": "👯", "tier": "silver", "cat": "social", "points": 40},
    {"id": "social_20", "name": "Círculo grande", "desc": "20 amigos aceptados", "emoji": "🌍", "tier": "silver", "cat": "social", "points": 80},
    {"id": "social_50", "name": "Rey/Reina social", "desc": "50 amigos aceptados", "emoji": "👑", "tier": "gold", "cat": "social", "points": 200},
    {"id": "social_100", "name": "Influencer", "desc": "100 amigos aceptados", "emoji": "📣", "tier": "platinum", "cat": "social", "points": 500},
    {"id": "trendsetter", "name": "Marcaste el rumbo", "desc": "3 amigos fueron a un evento después que tú", "emoji": "💡", "tier": "gold", "cat": "social", "points": 80},
    {"id": "party_starter", "name": "Iniciador", "desc": "Fuiste el primero en apuntarte a 5 eventos", "emoji": "🎬", "tier": "silver", "cat": "social", "points": 60},

    # ===== REFERIDOS =====
    {"id": "referral_1", "name": "Trajiste a alguien", "desc": "Invitaste a 1 amigo/a que se registró", "emoji": "🎁", "tier": "bronze", "cat": "referido", "points": 100},
    {"id": "referral_3", "name": "Reclutador", "desc": "3 amigos se registraron con tu link", "emoji": "📣", "tier": "silver", "cat": "referido", "points": 250},
    {"id": "referral_5", "name": "Embajador", "desc": "5 amigos se registraron con tu link", "emoji": "🌟", "tier": "gold", "cat": "referido", "points": 500},
    {"id": "referral_10", "name": "Embajador dorado", "desc": "10 amigos se registraron con tu link", "emoji": "🏆", "tier": "platinum", "cat": "referido", "points": 1200},

    # ===== ENTRADAS COMPRADAS =====
    {"id": "ticket_1", "name": "Primera entrada", "desc": "Compraste 1 entrada desde la app", "emoji": "🎟️", "tier": "bronze", "cat": "entrada", "points": 50},
    {"id": "ticket_5", "name": "VIP", "desc": "Compraste 5 entradas desde la app", "emoji": "🎫", "tier": "silver", "cat": "entrada", "points": 250},
    {"id": "ticket_15", "name": "Super VIP", "desc": "Compraste 15 entradas desde la app", "emoji": "💳", "tier": "gold", "cat": "entrada", "points": 750},

    # ===== EXPLORADOR (GÉNEROS / LOCALES) =====
    {"id": "explorer_3", "name": "Curioso", "desc": "Fuiste a 3 géneros distintos", "emoji": "🔍", "tier": "bronze", "cat": "exploracion", "points": 20},
    {"id": "explorer", "name": "Explorador", "desc": "Fuiste a 5 géneros distintos", "emoji": "🧭", "tier": "silver", "cat": "exploracion", "points": 50},
    {"id": "explorer_10", "name": "Aventurero", "desc": "Fuiste a 10 géneros distintos", "emoji": "🗺️", "tier": "gold", "cat": "exploracion", "points": 150},
    {"id": "loyal_venue", "name": "Cliente fiel", "desc": "3 fiestas en el mismo local", "emoji": "🏛️", "tier": "silver", "cat": "exploracion", "points": 40},
    {"id": "super_fan", "name": "Super fan", "desc": "10 fiestas en el mismo local", "emoji": "💖", "tier": "gold", "cat": "exploracion", "points": 150},
    {"id": "venue_hopper", "name": "Trotalocales", "desc": "Fuiste a 5 locales diferentes", "emoji": "🏃", "tier": "silver", "cat": "exploracion", "points": 60},

    # ===== CAPTURAS (fotos del momento) =====
    {"id": "capture_1", "name": "Primera captura", "desc": "Subiste tu primera captura", "emoji": "📸", "tier": "bronze", "cat": "captura", "points": 15},
    {"id": "capture_ontime", "name": "A tiempo", "desc": "Subiste una captura a tiempo (dentro del rango)", "emoji": "⏱️", "tier": "bronze", "cat": "captura", "points": 30},
    {"id": "capture_5", "name": "Reportero", "desc": "5 capturas subidas", "emoji": "📷", "tier": "silver", "cat": "captura", "points": 60},
    {"id": "capture_ontime_5", "name": "Puntual", "desc": "5 capturas a tiempo", "emoji": "⏰", "tier": "silver", "cat": "captura", "points": 120},
    {"id": "capture_20", "name": "Fotógrafo/a oficial", "desc": "20 capturas subidas", "emoji": "🎥", "tier": "gold", "cat": "captura", "points": 200},
    {"id": "storyteller", "name": "Cuentacuentos", "desc": "Subiste 3 historias", "emoji": "🎙️", "tier": "bronze", "cat": "captura", "points": 20},
    {"id": "storyteller_10", "name": "Narrador", "desc": "Subiste 10 historias", "emoji": "🎞️", "tier": "silver", "cat": "captura", "points": 60},
    {"id": "story_star", "name": "Estrella de las stories", "desc": "Subiste 30 historias", "emoji": "🌠", "tier": "gold", "cat": "captura", "points": 200},

    # ===== ÁLBUMES (multimedia por evento) =====
    {"id": "album_contributor", "name": "Colaborador de álbum", "desc": "Subiste 1 foto/vídeo a un álbum", "emoji": "🖼️", "tier": "bronze", "cat": "album", "points": 10},
    {"id": "album_pro", "name": "Editor del álbum", "desc": "10 archivos subidos a álbumes", "emoji": "📀", "tier": "silver", "cat": "album", "points": 80},
    {"id": "album_master", "name": "Maestro del álbum", "desc": "50 archivos subidos a álbumes", "emoji": "💽", "tier": "gold", "cat": "album", "points": 300},

    # ===== VARIOS =====
    {"id": "early_bird", "name": "Madrugador", "desc": "Te apuntaste a un evento con >1 semana de antelación", "emoji": "🐦", "tier": "bronze", "cat": "otros", "points": 15},
    {"id": "night_marathon", "name": "Maratón nocturno", "desc": "2 eventos en el mismo día", "emoji": "🏁", "tier": "gold", "cat": "otros", "points": 80},
    {"id": "solo_traveler", "name": "En solitario", "desc": "Fuiste a un evento donde no había amigos apuntados", "emoji": "🧍", "tier": "silver", "cat": "otros", "points": 30},
    {"id": "group_leader", "name": "Líder de grupo", "desc": "5+ amigos coincidieron contigo en un evento", "emoji": "👥", "tier": "gold", "cat": "otros", "points": 100},
    {"id": "profile_complete", "name": "Perfil top", "desc": "Perfil con foto y bio completos", "emoji": "✅", "tier": "bronze", "cat": "otros", "points": 10},
    {"id": "og", "name": "OG", "desc": "Fue de los primeros 100 usuarios", "emoji": "🥇", "tier": "platinum", "cat": "otros", "points": 200},
]

BADGES_BY_ID = {b["id"]: b for b in BADGES_CATALOG}

# Points awarded per action (in addition to badge points)
ACTION_POINTS = {
    "voy": 5,
    "estuve": 10,
    "friend_accepted": 2,
    "story_upload": 3,
    "album_upload": 5,
    "capture_ontime": 30,       # extra points for uploading the "moment" on time
    "capture_late": 5,          # small points for late captures
    "referral_signup": 100,     # both referrer and referred get this
    "ticket_purchase": 50,      # confirmed ticket purchase in-app
}


async def _compute_user_stats(user_id: str) -> dict:
    """Aggregate counts and stats for badges/profile. Cached 60s per user in memory."""
    # In-memory TTL cache to speed up rankings and repeated calls in the same session
    global _STATS_CACHE
    try:
        entry = _STATS_CACHE.get(user_id)
        if entry and (time.time() - entry[0]) < 60:
            return entry[1]
    except NameError:
        _STATS_CACHE = {}

    attended = 0
    going = 0
    interested = 0
    genres_seen = set()
    venue_counts = {}
    weekday_count = 0
    sunday_count = 0
    monday_count = 0
    dates = set()
    dates_list = []  # to detect same-day multiple events
    early_bird = False

    # Load ALL interests + events in bulk (avoid N+1: previous code did a
    # find_one on events for every single interest).
    interests_list = []
    async for it in db.interests.find({"user_id": user_id}):
        interests_list.append(it)
    event_ids_needed = list({it["event_id"] for it in interests_list})
    events_map = {}
    if event_ids_needed:
        async for ev in db.events.find({"id": {"$in": event_ids_needed}}, {"_id": 0}):
            events_map[ev["id"]] = ev

    for it in interests_list:
        if it["status"] == "voy":
            going += 1
        if it["status"] == "me_interesa":
            interested += 1
        if it["status"] == "estuve":
            attended += 1
        ev = events_map.get(it["event_id"])
        if not ev:
            continue
        if it["status"] in ("voy", "estuve") and ev.get("genre"):
            genres_seen.add(ev["genre"])
        if it["status"] in ("voy", "estuve") and ev.get("venue"):
            venue_counts[ev["venue"]] = venue_counts.get(ev["venue"], 0) + 1
        try:
            d = date.fromisoformat(ev["date"])
            if it["status"] in ("voy", "estuve"):
                dates.add(d)
                dates_list.append(d)
                if d.weekday() < 4:  # Mon-Thu
                    weekday_count += 1
                if d.weekday() == 6:  # Sunday
                    sunday_count += 1
                if d.weekday() == 0:  # Monday
                    monday_count += 1
                # Early bird: signed up voy more than 7 days before event
                if it["status"] == "voy" and it.get("created_at"):
                    try:
                        created = datetime.fromisoformat(it["created_at"]).date()
                        if (d - created).days > 7:
                            early_bird = True
                    except Exception:
                        pass
        except Exception:
            continue

    # Day streak: consecutive dates
    day_streak = 0
    today = datetime.now(ZoneInfo("Europe/Madrid")).date()
    cursor = today
    while cursor in dates:
        day_streak += 1
        cursor -= timedelta(days=1)
    # If not going today, check from yesterday
    if day_streak == 0:
        cursor = today - timedelta(days=1)
        while cursor in dates:
            day_streak += 1
            cursor -= timedelta(days=1)

    # Best day streak (longest consecutive run ever)
    best_day_streak = 0
    if dates:
        sorted_dates = sorted(dates)
        run = 1
        for i in range(1, len(sorted_dates)):
            if (sorted_dates[i] - sorted_dates[i - 1]).days == 1:
                run += 1
                best_day_streak = max(best_day_streak, run)
            else:
                run = 1
        best_day_streak = max(best_day_streak, run)

    # Week streak (reuse logic)
    mondays = {d - timedelta(days=d.weekday()) for d in dates}
    this_monday = today - timedelta(days=today.weekday())
    anchor = this_monday if this_monday in mondays else this_monday - timedelta(days=7)
    week_streak = 0
    while anchor in mondays:
        week_streak += 1
        anchor -= timedelta(days=7)

    # Best week streak ever
    best_week_streak = 0
    if mondays:
        sorted_mondays = sorted(mondays)
        run = 1
        for i in range(1, len(sorted_mondays)):
            if (sorted_mondays[i] - sorted_mondays[i - 1]).days == 7:
                run += 1
                best_week_streak = max(best_week_streak, run)
            else:
                run = 1
        best_week_streak = max(best_week_streak, run)

    # Same-day multiple events (night marathon)
    from collections import Counter
    date_counts = Counter(dates_list)
    night_marathon = any(c >= 2 for c in date_counts.values())

    # Friends count (accepted)
    friend_ids = await accepted_friend_ids(user_id)
    friends_count = len(friend_ids)

    # Stories count
    stories_count = await db.stories.count_documents({"user_id": user_id})

    # Album uploads (captures) count
    captures_count = await db.captures.count_documents({"user_id": user_id})
    captures_ontime = await db.captures.count_documents({"user_id": user_id, "on_time": True})
    album_uploads = await db.album_uploads.count_documents({"user_id": user_id})

    # Referrals: how many people signed up with your code
    referrals_count = await db.users.count_documents({"referred_by": user_id})

    # Tickets purchased (confirmed)
    tickets_count = await db.ticket_purchases.count_documents({"user_id": user_id, "confirmed": True})

    # Trendsetter + party_starter: for any voy event, did N+ friends join AFTER user?
    trendsetter = False
    party_starter_count = 0
    async for it in db.interests.find({"user_id": user_id, "status": {"$in": ["voy", "estuve"]}}):
        my_time = it.get("created_at", "")
        cnt = 0
        was_first = True
        async for other in db.interests.find({"event_id": it["event_id"], "status": {"$in": ["voy", "estuve"]}}):
            if other["user_id"] == user_id:
                continue
            if other.get("created_at", "") > my_time:
                if other["user_id"] in friend_ids:
                    cnt += 1
            else:
                was_first = False
        if cnt >= 3:
            trendsetter = True
        if was_first:
            party_starter_count += 1

    # Solo traveler: attended an event with 0 friends
    solo_traveler = False
    async for it in db.interests.find({"user_id": user_id, "status": "estuve"}):
        friends_at_event = await db.interests.count_documents({
            "event_id": it["event_id"],
            "status": {"$in": ["voy", "estuve"]},
            "user_id": {"$in": list(friend_ids)},
        })
        if friends_at_event == 0:
            solo_traveler = True
            break

    # Group leader: at least one event with 5+ friends
    group_leader = False
    async for it in db.interests.find({"user_id": user_id, "status": {"$in": ["voy", "estuve"]}}):
        friends_at_event = await db.interests.count_documents({
            "event_id": it["event_id"],
            "status": {"$in": ["voy", "estuve"]},
            "user_id": {"$in": list(friend_ids)},
        })
        if friends_at_event >= 5:
            group_leader = True
            break

    # Profile complete
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    profile_complete = bool(u and u.get("picture") and u.get("bio"))

    # OG: was in the first 100 registered users
    is_og = False
    if u and u.get("created_at"):
        earlier = await db.users.count_documents({"created_at": {"$lt": u["created_at"]}})
        is_og = earlier < 100

    top_venue = max(venue_counts.values()) if venue_counts else 0
    top_venue_name = max(venue_counts, key=venue_counts.get) if venue_counts else ""
    venues_count = len(venue_counts)

    result = {
        "attended": attended,
        "going": going,
        "interested": interested,
        "total_events": attended + going,
        "week_streak": week_streak,
        "day_streak": day_streak,
        "best_week_streak": best_week_streak,
        "best_day_streak": best_day_streak,
        "genres_count": len(genres_seen),
        "genres": sorted(genres_seen),
        "friends_count": friends_count,
        "weekday_count": weekday_count,
        "sunday_count": sunday_count,
        "monday_count": monday_count,
        "stories_count": stories_count,
        "captures_count": captures_count,
        "captures_ontime": captures_ontime,
        "album_uploads": album_uploads,
        "referrals_count": referrals_count,
        "tickets_count": tickets_count,
        "early_bird": early_bird,
        "trendsetter": trendsetter,
        "party_starter_count": party_starter_count,
        "night_marathon": night_marathon,
        "solo_traveler": solo_traveler,
        "group_leader": group_leader,
        "profile_complete": profile_complete,
        "is_og": is_og,
        "top_venue": top_venue_name,
        "top_venue_count": top_venue,
        "venues_count": venues_count,
    }
    try:
        _STATS_CACHE[user_id] = (time.time(), result)
        # Prevent unbounded growth
        if len(_STATS_CACHE) > 500:
            # Drop oldest half
            items = sorted(_STATS_CACHE.items(), key=lambda kv: kv[1][0])
            for k, _ in items[:250]:
                _STATS_CACHE.pop(k, None)
    except Exception:
        pass
    return result


def _invalidate_stats_cache(user_id: str = None):
    """Call whenever activity changes (interest, friend, story, etc.). If user_id
    is None, wipe everything."""
    try:
        global _STATS_CACHE, _CAROUSELS_CACHE
        if user_id is None:
            _STATS_CACHE.clear()
            _CAROUSELS_CACHE.clear()
        else:
            _STATS_CACHE.pop(user_id, None)
            # Interests/friends affect carousels for the user AND their friends.
            # Simpler and safe: clear whole carousels cache (it's short-lived, 20s).
            _CAROUSELS_CACHE.clear()
    except Exception:
        pass


def _award_badges(stats: dict) -> list:
    """Given user stats, return list of earned badge ids."""
    earned = []
    total = stats["attended"] + stats["going"]
    # asistencia
    if total >= 1: earned.append("first_step")
    if stats["attended"] >= 1: earned.append("attended_1")
    if stats["attended"] >= 5 or stats["going"] >= 5: earned.append("night_owl")
    if total >= 10: earned.append("party_pro")
    if total >= 20: earned.append("party_veteran")
    if total >= 35: earned.append("party_master")
    if total >= 50: earned.append("legend")
    if total >= 100: earned.append("immortal")
    # rachas día
    if stats["best_day_streak"] >= 2 or stats["day_streak"] >= 2: earned.append("day_streak_2")
    if stats["best_day_streak"] >= 3 or stats["day_streak"] >= 3: earned.append("day_streak_3")
    if stats["best_day_streak"] >= 5 or stats["day_streak"] >= 5: earned.append("day_streak_5")
    if stats["best_day_streak"] >= 7 or stats["day_streak"] >= 7: earned.append("day_streak_7")
    if stats["best_day_streak"] >= 10 or stats["day_streak"] >= 10: earned.append("day_streak_10")
    if stats["best_day_streak"] >= 15 or stats["day_streak"] >= 15: earned.append("day_streak_15")
    # rachas semana
    if stats["best_week_streak"] >= 2 or stats["week_streak"] >= 2: earned.append("week_streak_2")
    if stats["best_week_streak"] >= 4 or stats["week_streak"] >= 4: earned.append("week_streak_4")
    if stats["best_week_streak"] >= 8 or stats["week_streak"] >= 8: earned.append("week_streak_8")
    if stats["best_week_streak"] >= 12 or stats["week_streak"] >= 12: earned.append("week_streak_12")
    if stats["best_week_streak"] >= 26 or stats["week_streak"] >= 26: earned.append("week_streak_26")
    # temporal
    if stats["weekday_count"] >= 1: earned.append("weekday_1")
    if stats["weekday_count"] >= 3: earned.append("weekday_warrior")
    if stats["weekday_count"] >= 10: earned.append("weekday_boss")
    if stats["sunday_count"] >= 1: earned.append("sunday_survivor")
    if stats["sunday_count"] >= 3: earned.append("sunday_lover")
    if stats["monday_count"] >= 1: earned.append("monday_king")
    # social
    if stats["friends_count"] >= 1: earned.append("social_1")
    if stats["friends_count"] >= 5: earned.append("social_5")
    if stats["friends_count"] >= 10: earned.append("social_10")
    if stats["friends_count"] >= 20: earned.append("social_20")
    if stats["friends_count"] >= 50: earned.append("social_50")
    if stats["friends_count"] >= 100: earned.append("social_100")
    if stats["trendsetter"]: earned.append("trendsetter")
    if stats["party_starter_count"] >= 5: earned.append("party_starter")
    # referidos
    if stats["referrals_count"] >= 1: earned.append("referral_1")
    if stats["referrals_count"] >= 3: earned.append("referral_3")
    if stats["referrals_count"] >= 5: earned.append("referral_5")
    if stats["referrals_count"] >= 10: earned.append("referral_10")
    # entradas
    if stats["tickets_count"] >= 1: earned.append("ticket_1")
    if stats["tickets_count"] >= 5: earned.append("ticket_5")
    if stats["tickets_count"] >= 15: earned.append("ticket_15")
    # exploración
    if stats["genres_count"] >= 3: earned.append("explorer_3")
    if stats["genres_count"] >= 5: earned.append("explorer")
    if stats["genres_count"] >= 10: earned.append("explorer_10")
    if stats["top_venue_count"] >= 3: earned.append("loyal_venue")
    if stats["top_venue_count"] >= 10: earned.append("super_fan")
    if stats["venues_count"] >= 5: earned.append("venue_hopper")
    # capturas
    if stats["captures_count"] >= 1: earned.append("capture_1")
    if stats["captures_ontime"] >= 1: earned.append("capture_ontime")
    if stats["captures_count"] >= 5: earned.append("capture_5")
    if stats["captures_ontime"] >= 5: earned.append("capture_ontime_5")
    if stats["captures_count"] >= 20: earned.append("capture_20")
    if stats["stories_count"] >= 3: earned.append("storyteller")
    if stats["stories_count"] >= 10: earned.append("storyteller_10")
    if stats["stories_count"] >= 30: earned.append("story_star")
    # álbum
    if stats["album_uploads"] >= 1: earned.append("album_contributor")
    if stats["album_uploads"] >= 10: earned.append("album_pro")
    if stats["album_uploads"] >= 50: earned.append("album_master")
    # varios
    if stats["early_bird"]: earned.append("early_bird")
    if stats["night_marathon"]: earned.append("night_marathon")
    if stats["solo_traveler"]: earned.append("solo_traveler")
    if stats["group_leader"]: earned.append("group_leader")
    if stats["profile_complete"]: earned.append("profile_complete")
    if stats["is_og"]: earned.append("og")
    return earned


def _compute_points(stats: dict, earned_ids: list) -> dict:
    """Compute total points: badge points + action points."""
    badge_points = sum(BADGES_BY_ID[bid]["points"] for bid in earned_ids if bid in BADGES_BY_ID)
    action_points = (
        stats["going"] * ACTION_POINTS["voy"]
        + stats["attended"] * ACTION_POINTS["estuve"]
        + stats["friends_count"] * ACTION_POINTS["friend_accepted"]
        + stats["stories_count"] * ACTION_POINTS["story_upload"]
        + stats["album_uploads"] * ACTION_POINTS["album_upload"]
        + stats["captures_ontime"] * ACTION_POINTS["capture_ontime"]
        + max(0, stats["captures_count"] - stats["captures_ontime"]) * ACTION_POINTS["capture_late"]
        + stats["referrals_count"] * ACTION_POINTS["referral_signup"]
        + stats["tickets_count"] * ACTION_POINTS["ticket_purchase"]
    )
    return {
        "badge_points": badge_points,
        "action_points": action_points,
        "total": badge_points + action_points,
    }


@api_router.get("/badges/catalog")
async def badges_catalog():
    return BADGES_CATALOG


@api_router.get("/me/badges")
async def my_badges(user: dict = Depends(get_current_user)):
    stats = await _compute_user_stats(user["user_id"])
    earned_ids = _award_badges(stats)
    points = _compute_points(stats, earned_ids)
    return {
        "stats": stats,
        "points": points,
        "earned": [BADGES_BY_ID[b] for b in earned_ids if b in BADGES_BY_ID],
        "locked": [b for b in BADGES_CATALOG if b["id"] not in earned_ids],
    }


@api_router.get("/users/{user_id}/badges")
async def user_badges(user_id: str, viewer: dict = Depends(get_current_user)):
    """View another user's badges + public stats. Anyone can see basic public info;
    friends see the full stats. Non-friends see limited data + is_friend=false so
    the UI can offer 'Add friend'."""
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    is_self = user_id == viewer["user_id"]
    is_friend = False
    friend_status = "none"
    if not is_self:
        friend_ids = await accepted_friend_ids(viewer["user_id"])
        is_friend = user_id in friend_ids
        if not is_friend:
            # Check pending request either way
            req = await db.friendships.find_one({
                "$or": [
                    {"requester_id": viewer["user_id"], "addressee_id": user_id, "status": "pending"},
                    {"requester_id": user_id, "addressee_id": viewer["user_id"], "status": "pending"},
                ],
            })
            if req:
                friend_status = "pending_out" if req.get("requester_id") == viewer["user_id"] else "pending_in"
        else:
            friend_status = "friends"
    else:
        friend_status = "self"

    stats = await _compute_user_stats(user_id)
    earned_ids = _award_badges(stats)
    points = _compute_points(stats, earned_ids)

    if is_self or is_friend:
        return {
            "user": {"user_id": target["user_id"], "name": target["name"] if is_self else display_name(target),
                     "picture": target.get("picture", ""), "username": target.get("username", ""),
                     "city": target.get("city", ""), "bio": target.get("bio", "")},
            "stats": stats,
            "points": points,
            "earned": [BADGES_BY_ID[b] for b in earned_ids if b in BADGES_BY_ID],
            "locked": [b for b in BADGES_CATALOG if b["id"] not in earned_ids],
            "is_friend": is_friend,
            "is_self": is_self,
            "friend_status": friend_status,
        }
    # Public view for non-friends: limited stats, only earned badges
    public_stats = {
        "total_events": stats.get("total_events", 0),
        "friends_count": stats.get("friends_count", 0),
        "genres_count": stats.get("genres_count", 0),
        "week_streak": stats.get("week_streak", 0),
        "day_streak": stats.get("day_streak", 0),
    }
    return {
        "user": {"user_id": target["user_id"], "name": display_name(target),
                 "picture": target.get("picture", ""), "username": target.get("username", ""),
                 "city": target.get("city", ""), "bio": target.get("bio", "")},
        "stats": public_stats,
        "points": {"total": points["total"], "badge_points": points["badge_points"], "action_points": 0},
        "earned": [BADGES_BY_ID[b] for b in earned_ids if b in BADGES_BY_ID],
        "locked": [],
        "is_friend": False,
        "is_self": False,
        "friend_status": friend_status,
    }


# =========================
# RANKINGS
# =========================
async def _points_for_user(user_id: str) -> int:
    stats = await _compute_user_stats(user_id)
    earned_ids = _award_badges(stats)
    return _compute_points(stats, earned_ids)["total"]


async def _build_ranking(candidate_user_ids: list, limit: int = 100) -> list:
    """Given a list of user_ids, compute their points and return sorted ranking.
    Parallelized: fetches users in one query and computes stats concurrently."""
    if not candidate_user_ids:
        return []
    users = []
    async for u in db.users.find({"user_id": {"$in": candidate_user_ids}}, {"_id": 0}):
        users.append(u)
    # Compute points in parallel (cached to 60s so this is fast on repeat calls)
    points_list = await asyncio.gather(*[_points_for_user(u["user_id"]) for u in users])
    entries = [
        {
            "user_id": u["user_id"],
            "name": display_name(u),
            "username": u.get("username", ""),
            "picture": u.get("picture", ""),
            "city": u.get("city", ""),
            "points": pts,
        }
        for u, pts in zip(users, points_list)
    ]
    entries.sort(key=lambda e: -e["points"])
    for i, e in enumerate(entries[:limit]):
        e["rank"] = i + 1
    return entries[:limit]


@api_router.get("/rankings/friends")
async def ranking_friends(user: dict = Depends(get_current_user)):
    friend_ids = await accepted_friend_ids(user["user_id"])
    ids = friend_ids + [user["user_id"]]
    return await _build_ranking(ids, limit=100)


@api_router.get("/rankings/city")
async def ranking_city(user: dict = Depends(get_current_user), city: str = Query("")):
    target_city = city or user.get("city", "Palma de Mallorca")
    ids = []
    async for u in db.users.find({"city": target_city}, {"_id": 0, "user_id": 1}):
        ids.append(u["user_id"])
    return await _build_ranking(ids, limit=100)


@api_router.get("/rankings/world")
async def ranking_world(user: dict = Depends(get_current_user)):
    ids = []
    async for u in db.users.find({}, {"_id": 0, "user_id": 1}):
        ids.append(u["user_id"])
    return await _build_ranking(ids, limit=100)


# =========================
# STREAK — full data for the feed banner
# =========================
@api_router.get("/me/streak-full")
async def my_streak_full(user: dict = Depends(get_current_user)):
    """Full streak info: current day + week streaks, best, and next milestone."""
    stats = await _compute_user_stats(user["user_id"])
    milestones_day = [2, 3, 5, 7, 10, 15, 30]
    milestones_week = [2, 4, 8, 12, 26, 52]
    next_day = next((m for m in milestones_day if m > stats["day_streak"]), None)
    next_week = next((m for m in milestones_week if m > stats["week_streak"]), None)
    return {
        "day_streak": stats["day_streak"],
        "week_streak": stats["week_streak"],
        "best_day_streak": stats["best_day_streak"],
        "best_week_streak": stats["best_week_streak"],
        "next_day_milestone": next_day,
        "next_week_milestone": next_week,
        "total_events": stats["total_events"],
    }


# =========================
# REFERIDOS
# =========================
def _make_referral_code(username: str) -> str:
    base = re.sub(r"[^a-z0-9]", "", (username or "user").lower())[:10]
    suffix = secrets.token_hex(3).upper()
    return f"{base}-{suffix}" if base else suffix


@api_router.get("/me/referral")
async def my_referral(user: dict = Depends(get_current_user)):
    """Return current user's referral code + link + stats. Creates one if missing."""
    u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    code = u.get("referral_code")
    if not code:
        code = _make_referral_code(u.get("username", ""))
        # Ensure uniqueness
        while await db.users.find_one({"referral_code": code}):
            code = _make_referral_code(u.get("username", ""))
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"referral_code": code}})
    referred_count = await db.users.count_documents({"referred_by": user["user_id"]})
    return {
        "code": code,
        "share_url_hint": f"?ref={code}",
        "referred_count": referred_count,
        "points_per_referral": ACTION_POINTS["referral_signup"],
    }


class ClaimReferralInput(BaseModel):
    code: str


@api_router.post("/me/claim-referral")
async def claim_referral(inp: ClaimReferralInput, user: dict = Depends(get_current_user)):
    """Called right after signup to link the new user to whoever invited them.
    Only works if the current user was created within the last 24h and hasn't already claimed."""
    u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if u.get("referred_by"):
        raise HTTPException(status_code=400, detail="Ya usaste un código")
    # Ensure account is recent (<24h) to prevent abuse
    try:
        created = datetime.fromisoformat(u["created_at"])
        if (datetime.now(timezone.utc) - created).total_seconds() > 24 * 3600:
            raise HTTPException(status_code=400, detail="Solo puedes usar un código en las primeras 24h")
    except Exception:
        pass
    code = inp.code.strip()
    referrer = await db.users.find_one({"referral_code": code}, {"_id": 0})
    if not referrer:
        raise HTTPException(status_code=404, detail="Código no válido")
    if referrer["user_id"] == user["user_id"]:
        raise HTTPException(status_code=400, detail="No puedes usarte a ti mismo")
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"referred_by": referrer["user_id"]}})
    await create_notification(
        referrer["user_id"], "referral",
        f"¡{display_name(u)} se registró con tu código! +{ACTION_POINTS['referral_signup']} puntos 🎁",
        {"user_id": user["user_id"]},
    )
    return {"ok": True, "points": ACTION_POINTS["referral_signup"]}


@api_router.get("/events/{event_id}")
async def get_event(event_id: str, user: dict = Depends(get_optional_user)):
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    # Track a view for the conversion funnel (fire-and-forget, deduped per open).
    try:
        await db.event_metrics.update_one(
            {"event_id": event_id}, {"$inc": {"views": 1}}, upsert=True)
    except Exception:
        pass
    friend_ids = await accepted_friend_ids(user["user_id"])
    # Load follow state so is_following is accurate on the detail page (fixes the
    # notification bell "unselecting itself" after refetch).
    # For guests (user_id=None), follows_set should be None so is_following=null
    if user["user_id"] is None:
        follows_set = None
    else:
        follows_set: set = set()
        _f = await db.event_follows.find_one(
            {"user_id": user["user_id"], "event_id": event_id}, {"_id": 0, "event_id": 1})
        if _f:
            follows_set.add(event_id)
    return await serialize_event(ev, user, friend_ids, follows_set=follows_set)


@api_router.post("/events/{event_id}/interest")
async def set_interest(event_id: str, inp: InterestInput, user: dict = Depends(get_current_user)):
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    if inp.status not in ("voy", "me_interesa", "estuve", "none"):
        raise HTTPException(status_code=400, detail="Estado inválido")

    existing = await db.interests.find_one({"user_id": user["user_id"], "event_id": event_id})
    prev_status = existing["status"] if existing else None
    my_privacy = user.get("attendance_privacy", "amigos")

    if inp.status == "none":
        await db.interests.delete_one({"user_id": user["user_id"], "event_id": event_id})
    elif existing:
        await db.interests.update_one({"_id": existing["_id"]},
                                      {"$set": {"status": inp.status,
                                                "privacy": my_privacy,
                                                "updated_at": datetime.now(timezone.utc).isoformat()}})
    else:
        await db.interests.insert_one({
            "id": str(uuid.uuid4()),
            "user_id": user["user_id"],
            "event_id": event_id,
            "status": inp.status,
            "privacy": my_privacy,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    _invalidate_stats_cache(user["user_id"])

    # Notify friends when marking "voy" (only on transition to voy). Users who
    # chose a non-public privacy ("amigos"/"nadie") are not broadcast.
    if inp.status == "voy" and prev_status != "voy" and my_privacy == "todos":
        friend_ids = await accepted_friend_ids(user["user_id"])
        for fid in friend_ids:
            await create_notification(
                fid, "friend_going",
                f"{display_name(user)} va a {ev['name']}",
                {"event_id": event_id, "user_id": user["user_id"]},
            )

    return {"status": inp.status}



class TicketInput(BaseModel):
    have: bool = True


@api_router.post("/events/{event_id}/ticket")
async def set_ticket(event_id: str, inp: TicketInput, user: dict = Depends(get_current_user)):
    """User marks (or unmarks) that they already have a ticket for this event.
    Powers social proof ('3 amigos ya tienen entrada') and conversion tracking."""
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    if inp.have:
        await db.tickets.update_one(
            {"user_id": user["user_id"], "event_id": event_id},
            {"$set": {"user_id": user["user_id"], "event_id": event_id,
                      "created_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )
        await db.event_metrics.update_one(
            {"event_id": event_id}, {"$inc": {"tickets": 1}}, upsert=True)
    else:
        res = await db.tickets.delete_one({"user_id": user["user_id"], "event_id": event_id})
        if res.deleted_count:
            await db.event_metrics.update_one(
                {"event_id": event_id}, {"$inc": {"tickets": -1}}, upsert=True)
    total = await db.tickets.count_documents({"event_id": event_id})
    return {"have": inp.have, "total_tickets": total}


@api_router.get("/me/activity")
async def my_activity(user: dict = Depends(get_current_user)):
    """Recent activity of the user's friends: who's going where, new tickets,
    and fresh stories. The social heartbeat that keeps people opening the app."""
    friend_ids = await accepted_friend_ids(user["user_id"])
    if not friend_ids:
        return {"items": []}
    fmap = {}
    async for u in db.users.find({"user_id": {"$in": friend_ids}}, {"_id": 0}):
        fmap[u["user_id"]] = u
    today_iso = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
    items = []
    # friends marking voy (only for FUTURE events — past parties drop off the wall)
    async for it in db.interests.find(
        {"user_id": {"$in": friend_ids}, "status": "voy"}, {"_id": 0}).sort("created_at", -1).limit(60):
        ev = await db.events.find_one({"id": it["event_id"]}, {"_id": 0})
        fu = fmap.get(it["user_id"])
        if ev and fu and ev.get("date", "") >= today_iso:
            items.append({
                "type": "going", "ts": it.get("created_at", ""),
                "user": {"user_id": fu["user_id"], "name": display_name(fu), "picture": fu.get("picture", "")},
                "event_id": ev["id"], "event_name": ev["name"], "venue": ev.get("venue", ""), "date": ev.get("date", ""),
            })
    # friends who got tickets (only for FUTURE events)
    async for tk in db.tickets.find({"user_id": {"$in": friend_ids}}, {"_id": 0}).sort("created_at", -1).limit(30):
        ev = await db.events.find_one({"id": tk["event_id"]}, {"_id": 0})
        fu = fmap.get(tk["user_id"])
        if ev and fu and ev.get("date", "") >= today_iso:
            items.append({
                "type": "ticket", "ts": tk.get("created_at", ""),
                "user": {"user_id": fu["user_id"], "name": display_name(fu), "picture": fu.get("picture", "")},
                "event_id": ev["id"], "event_name": ev["name"], "venue": ev.get("venue", ""), "date": ev.get("date", ""),
            })
    items.sort(key=lambda x: x.get("ts", ""), reverse=True)
    return {"items": items[:25]}


@api_router.get("/me/past-events")
async def my_past_events(user: dict = Depends(get_current_user)):
    """Past parties the user attended (status voy/estuve and date < today).
    Powers the 'Fiestas pasadas' page; each item is enterable → /event/:id
    where the shared + private album lives."""
    uid = user["user_id"]
    today_iso = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
    # my interests that count as "went"
    status_map = {}
    async for it in db.interests.find(
        {"user_id": uid, "status": {"$in": ["voy", "estuve"]}}, {"_id": 0}):
        status_map[it["event_id"]] = it["status"]
    if not status_map:
        return {"items": []}
    ev_ids = list(status_map.keys())
    # bulk load past events
    events = {}
    async for ev in db.events.find(
        {"id": {"$in": ev_ids}, "date": {"$lt": today_iso}}, {"_id": 0}):
        events[ev["id"]] = ev
    if not events:
        return {"items": []}
    # my album photo counts per event (single grouped query)
    photo_counts = {}
    pipeline = [
        {"$match": {"user_id": uid, "event_id": {"$in": list(events.keys())}}},
        {"$group": {"_id": "$event_id", "n": {"$sum": 1}}},
    ]
    async for row in db.album_uploads.aggregate(pipeline):
        photo_counts[row["_id"]] = row["n"]
    items = []
    for eid, ev in events.items():
        items.append({
            "id": ev["id"],
            "name": ev["name"],
            "venue": ev.get("venue", ""),
            "date": ev.get("date", ""),
            "time": ev.get("time", ""),
            "image_url": ev.get("image_url", ""),
            "genre": ev.get("genre", ""),
            "my_status": status_map.get(eid, "estuve"),
            "my_photos": photo_counts.get(eid, 0),
        })
    items.sort(key=lambda x: x.get("date", ""), reverse=True)
    return {"items": items}


_MONTHS_ES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
              "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _wrapped_title(top_genre: str, parties: int) -> str:
    """A fun Spotify-Wrapped-style label based on the user's top genre / activity."""
    g = unicodedata.normalize("NFKD", (top_genre or "").lower()).encode("ascii", "ignore").decode()
    table = [
        (("reggaeton", "regueton", "perreo", "latino", "latin"), "Rey/Reina del perreo 👑"),
        (("techno", "tekno", "tech house", "tech-house"), "Alma Techno 🖤"),
        (("house", "deep"), "House Lover 🏠"),
        (("edm", "electro", "electronica", "rave", "trance"), "Raver de pura cepa ⚡"),
        (("hip hop", "hip-hop", "rap", "trap", "drill"), "Trapper de noche 🔥"),
        (("pop", "comercial", "mainstream", "hits", "40"), "Comercial de corazón ✨"),
        (("remember", "80", "90", "disco", "funk"), "Alma retro 🕺"),
    ]
    for keys, label in table:
        if any(k in g for k in keys):
            return label
    if parties >= 8:
        return "Máquina de la noche 🌙"
    if parties >= 4:
        return "Fiestero/a nivel pro 🎉"
    if parties >= 1:
        return "De planes ✨"
    return "Modo tranqui 🌙"


async def _wrapped_core(user: dict, start_iso: str, end_excl: str) -> dict:
    """Shared Wrapped aggregation over [start_iso, end_excl) by event.date."""
    uid = user["user_id"]
    my_ev_ids = []
    async for it in db.interests.find(
        {"user_id": uid, "status": {"$in": ["voy", "estuve"]}}, {"_id": 0, "event_id": 1}):
        my_ev_ids.append(it["event_id"])
    my_ev_ids = list(set(my_ev_ids))
    events = {}
    if my_ev_ids:
        async for ev in db.events.find(
            {"id": {"$in": my_ev_ids}, "date": {"$gte": start_iso, "$lt": end_excl}}, {"_id": 0}):
            events[ev["id"]] = ev

    genre_counts, venue_counts, nights, month_tally = {}, {}, set(), {}
    poster = ""
    for ev in events.values():
        if ev.get("genre"):
            genre_counts[ev["genre"]] = genre_counts.get(ev["genre"], 0) + 1
        if ev.get("venue"):
            venue_counts[ev["venue"]] = venue_counts.get(ev["venue"], 0) + 1
        d = ev.get("date") or ""
        if d:
            nights.add(d)
            month_tally[d[:7]] = month_tally.get(d[:7], 0) + 1
        if not poster and ev.get("image_url"):
            poster = ev["image_url"]
    top_genre = max(genre_counts.items(), key=lambda kv: kv[1])[0] if genre_counts else ""
    top_venue = max(venue_counts.items(), key=lambda kv: kv[1]) if venue_counts else None

    # Photos + moments are counted/collected for the PARTIES of this period (by
    # event), so a photo uploaded a few days later still belongs to that recap.
    ev_id_list = list(events.keys())
    photos = moments = moments_ontime = 0
    gallery = []
    if ev_id_list:
        photos = await db.album_uploads.count_documents(
            {"user_id": uid, "event_id": {"$in": ev_id_list}, "media_type": {"$ne": "video"}})
        moments = await db.captures.count_documents(
            {"user_id": uid, "event_id": {"$in": ev_id_list}})
        moments_ontime = await db.captures.count_documents(
            {"user_id": uid, "event_id": {"$in": ev_id_list}, "on_time": True})
        async for a in db.album_uploads.find(
            {"user_id": uid, "event_id": {"$in": ev_id_list}, "media_type": {"$ne": "video"}},
            {"_id": 0, "media_url": 1}).sort("created_at", -1).limit(9):
            if a.get("media_url"):
                gallery.append({"url": a["media_url"], "kind": "photo"})
        async for c in db.captures.find(
            {"user_id": uid, "event_id": {"$in": ev_id_list}},
            {"_id": 0, "image_url": 1}).sort("created_at", -1).limit(9):
            if c.get("image_url"):
                gallery.append({"url": c["image_url"], "kind": "moment"})
        gallery = gallery[:12]

    top_friends, friends_coincided = [], 0
    if events:
        friend_ids = await accepted_friend_ids(uid)
        if friend_ids:
            tally = {}
            async for it in db.interests.find(
                {"event_id": {"$in": ev_id_list},
                 "user_id": {"$in": friend_ids},
                 "status": {"$in": ["voy", "estuve"]}}, {"_id": 0, "user_id": 1}):
                tally[it["user_id"]] = tally.get(it["user_id"], 0) + 1
            friends_coincided = len(tally)
            for fid, cnt in sorted(tally.items(), key=lambda kv: -kv[1])[:3]:
                fu = await db.users.find_one({"user_id": fid}, {"_id": 0})
                if fu:
                    top_friends.append({"name": display_name(fu),
                                        "picture": fu.get("picture", ""), "count": cnt})
    return {
        "parties": len(events),
        "nights_out": len(nights),
        "venues": len(venue_counts),
        "top_venue": ({"name": top_venue[0], "count": top_venue[1]} if top_venue else None),
        "top_genre": top_genre,
        "genres": [{"name": g, "count": c} for g, c in
                   sorted(genre_counts.items(), key=lambda kv: -kv[1])[:5]],
        "photos": photos,
        "moments": moments,
        "moments_ontime": moments_ontime,
        "friends_coincided": friends_coincided,
        "top_friends": top_friends,
        "gallery": gallery,
        "poster": poster,
        "month_tally": month_tally,
    }


async def _compute_wrapped(user: dict, month_str: str) -> dict:
    """Monthly 'Wrapped' aggregation for a user (Spotify-Wrapped style)."""
    try:
        y, m = int(month_str[:4]), int(month_str[5:7])
        start = date(y, m, 1)
    except Exception:
        now = datetime.now(ZoneInfo("Europe/Madrid"))
        y, m = now.year, now.month
        start = date(y, m, 1)
        month_str = f"{y:04d}-{m:02d}"
    nxt = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    core = await _wrapped_core(user, start.isoformat(), nxt.isoformat())
    core.pop("month_tally", None)
    label = f"{_MONTHS_ES[m].capitalize()} {y}"
    return {
        "month": month_str,
        "month_label": label,
        "period_label": label,
        "is_year": False,
        "city": user.get("city", ""),
        "title": _wrapped_title(core["top_genre"], core["parties"]),
        "has_data": (core["parties"] + core["photos"] + core["moments"]) > 0,
        **core,
    }


async def _compute_wrapped_year(user: dict, year_str: str) -> dict:
    """Annual 'Wrapped' aggregation — the whole year (delivered every January)."""
    try:
        y = int(str(year_str)[:4])
    except Exception:
        y = datetime.now(ZoneInfo("Europe/Madrid")).year
    core = await _wrapped_core(user, date(y, 1, 1).isoformat(), date(y + 1, 1, 1).isoformat())
    tally = core.pop("month_tally", {})
    top_month = None
    if tally:
        mk, cnt = max(tally.items(), key=lambda kv: kv[1])
        top_month = {"name": _MONTHS_ES[int(mk[5:7])].capitalize(), "count": cnt}
    return {
        "month": str(y),
        "month_label": str(y),
        "period_label": str(y),
        "is_year": True,
        "year": str(y),
        "top_month": top_month,
        "active_months": len(tally),
        "city": user.get("city", ""),
        "title": _wrapped_title(core["top_genre"], core["parties"]),
        "has_data": (core["parties"] + core["photos"] + core["moments"]) > 0,
        **core,
    }


@api_router.get("/me/wrapped")
async def my_wrapped(month: str = Query(""), user: dict = Depends(get_current_user)):
    """Monthly 'Wrapped' (Spotify-Wrapped style) for the current user. Defaults to
    the PREVIOUS month (Europe/Madrid) — the last closed month. Pass ?month=YYYY-MM
    for a specific month."""
    if not month:
        now = datetime.now(ZoneInfo("Europe/Madrid"))
        prev = now.replace(day=1) - timedelta(days=1)
        month = f"{prev.year:04d}-{prev.month:02d}"
    return await _compute_wrapped(user, month)


@api_router.get("/me/wrapped/year")
async def my_wrapped_year(year: str = Query(""), user: dict = Depends(get_current_user)):
    """Annual 'Wrapped' for the current user. Defaults to the current year
    (Europe/Madrid). Pass ?year=YYYY for a specific year."""
    if not year:
        year = str(datetime.now(ZoneInfo("Europe/Madrid")).year)
    return await _compute_wrapped_year(user, year)


async def notify_annual_wrapped():
    """On Jan 1, notify users who had activity LAST YEAR that their annual Wrapped
    is ready. Links to /wrapped?year=YYYY (the year that just ended)."""
    try:
        now = datetime.now(ZoneInfo("Europe/Madrid"))
        y = now.year - 1
        start_iso, end_excl = date(y, 1, 1).isoformat(), date(y + 1, 1, 1).isoformat()
        start_dt, end_dt = f"{start_iso}T00:00:00", f"{end_excl}T00:00:00"
        year_ev_ids = [e["id"] async for e in db.events.find(
            {"date": {"$gte": start_iso, "$lt": end_excl}}, {"_id": 0, "id": 1})]
        active = set()
        if year_ev_ids:
            async for it in db.interests.find(
                {"event_id": {"$in": year_ev_ids}, "status": {"$in": ["voy", "estuve"]}},
                {"_id": 0, "user_id": 1}):
                active.add(it["user_id"])
        async for a in db.album_uploads.find(
            {"created_at": {"$gte": start_dt, "$lt": end_dt}}, {"_id": 0, "user_id": 1}):
            active.add(a["user_id"])
        async for c in db.captures.find(
            {"created_at": {"$gte": start_dt, "$lt": end_dt}}, {"_id": 0, "user_id": 1}):
            active.add(c["user_id"])
        n = 0
        for uid in active:
            await create_notification(
                uid, "annual_wrapped",
                f"🎊 Tu Wrapped {y} ya está. ¡Mira tu año de fiesta! 👀",
                {"type": "annual_wrapped", "year": str(y), "url": f"/wrapped?year={y}"})
            n += 1
        logger.info(f"[wrapped] annual notified {n} users for {y}")
    except Exception as e:
        logger.warning(f"notify_annual_wrapped failed: {e}")


async def notify_monthly_wrapped():
    """On the 1st of each month, notify users who had activity LAST month that
    their monthly Wrapped is ready. Links to /wrapped?month=YYYY-MM (prev month).
    Only notifies active users so we never spam people who didn't go out."""
    try:
        now = datetime.now(ZoneInfo("Europe/Madrid"))
        last_prev = now.replace(day=1) - timedelta(days=1)
        y, m = last_prev.year, last_prev.month
        month_str = f"{y:04d}-{m:02d}"
        start = date(y, m, 1)
        nxt = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
        start_iso, end_excl = start.isoformat(), nxt.isoformat()
        start_dt, end_dt = f"{start_iso}T00:00:00", f"{end_excl}T00:00:00"
        label = f"{_MONTHS_ES[m].capitalize()} {y}"
        month_ev_ids = [e["id"] async for e in db.events.find(
            {"date": {"$gte": start_iso, "$lt": end_excl}}, {"_id": 0, "id": 1})]
        active = set()
        if month_ev_ids:
            async for it in db.interests.find(
                {"event_id": {"$in": month_ev_ids}, "status": {"$in": ["voy", "estuve"]}},
                {"_id": 0, "user_id": 1}):
                active.add(it["user_id"])
        async for a in db.album_uploads.find(
            {"created_at": {"$gte": start_dt, "$lt": end_dt}}, {"_id": 0, "user_id": 1}):
            active.add(a["user_id"])
        async for c in db.captures.find(
            {"created_at": {"$gte": start_dt, "$lt": end_dt}}, {"_id": 0, "user_id": 1}):
            active.add(c["user_id"])
        n = 0
        for uid in active:
            await create_notification(
                uid, "monthly_wrapped",
                f"🎉 Tu Wrapped de {label} ya está. Descubre tu mes de fiesta 👀",
                {"type": "monthly_wrapped", "month": month_str, "url": f"/wrapped?month={month_str}"})
            n += 1
        logger.info(f"[wrapped] notified {n} users for {month_str}")
    except Exception as e:
        logger.warning(f"notify_monthly_wrapped failed: {e}")


@api_router.get("/me/recap")
async def my_recap(user: dict = Depends(get_current_user)):
    """Weekly recap card: what the user did in the last 7 days. Dopamine + shareable."""
    uid = user["user_id"]
    now = datetime.now(timezone.utc)
    week_ago = (now - timedelta(days=7)).isoformat()
    went = await db.interests.count_documents(
        {"user_id": uid, "status": {"$in": ["voy", "estuve"]}, "created_at": {"$gte": week_ago}})
    photos = (
        await db.album_uploads.count_documents({"user_id": uid, "created_at": {"$gte": week_ago}})
        + await db.captures.count_documents({"user_id": uid, "created_at": {"$gte": week_ago}})
        + await db.group_photos.count_documents({"user_id": uid, "created_at": {"$gte": week_ago}})
    )
    new_friends = await db.friendships.count_documents(
        {"status": "accepted", "$or": [{"from_user_id": uid}, {"to_user_id": uid}],
         "updated_at": {"$gte": week_ago}})
    # friends' upcoming plans this coming week (FOMO)
    friend_ids = await accepted_friend_ids(uid)
    friends_plans = 0
    if friend_ids:
        friends_plans = await db.interests.count_documents(
            {"user_id": {"$in": friend_ids}, "status": "voy"})
    has_activity = (went + photos + new_friends) > 0
    return {
        "went": went, "photos": photos, "new_friends": new_friends,
        "friends_plans": friends_plans, "has_activity": has_activity,
    }


@api_router.get("/discover")
async def discover(user: dict = Depends(get_current_user)):
    """Discover section — built for newcomers (e.g. tourists with no friends yet):
    recommended people in their city + recent PUBLIC 'El Momento' captures from
    users who opted in via moment_privacy='publico'. Loaded on demand, not on the
    main feed, so it never slows down the hot path."""
    uid = user["user_id"]
    my_city = user.get("city") or "Palma de Mallorca"
    friend_ids = set(await accepted_friend_ids(uid))
    blocked = await blocked_relation_ids(uid)
    rel = await friendship_status_map(uid)  # exclude anyone with a pending/accepted relation
    exclude = set(friend_ids) | set(blocked) | set(rel.keys()) | {uid}

    # ---- Recommended people (same city) ----
    candidates = []
    async for u in db.users.find(
        {"city": my_city, "user_id": {"$nin": list(exclude)}},
        {"_id": 0, "user_id": 1, "name": 1, "username": 1, "picture": 1, "city": 1},
    ).limit(40):
        candidates.append(u)
    cand_ids = [c["user_id"] for c in candidates]
    going_counts = {}
    if cand_ids:
        pipeline = [
            {"$match": {"user_id": {"$in": cand_ids}, "status": {"$in": ["voy", "me_interesa"]}}},
            {"$group": {"_id": "$user_id", "n": {"$sum": 1}}},
        ]
        async for row in db.interests.aggregate(pipeline):
            going_counts[row["_id"]] = row["n"]
    my_fids = list(friend_ids)

    # Events THIS WEEK the viewer is going to / interested in (for "coincidís" filter)
    today = datetime.now(PALMA_TZ).date()
    week_end = today + timedelta(days=7)
    my_week_ids = set()
    async for it in db.interests.find(
        {"user_id": uid, "status": {"$in": ["voy", "me_interesa"]}},
        {"_id": 0, "event_id": 1},
    ):
        ev = await db.events.find_one({"id": it["event_id"]}, {"_id": 0, "date": 1})
        if not ev:
            continue
        try:
            d = date.fromisoformat(ev["date"])
        except Exception:
            continue
        if today <= d <= week_end:
            my_week_ids.add(it["event_id"])
    shared_counts = {}
    if cand_ids and my_week_ids:
        async for row in db.interests.aggregate([
            {"$match": {"user_id": {"$in": cand_ids},
                        "event_id": {"$in": list(my_week_ids)},
                        "status": {"$in": ["voy", "me_interesa"]}}},
            {"$group": {"_id": "$user_id", "n": {"$sum": 1}}},
        ]):
            shared_counts[row["_id"]] = row["n"]

    people = []
    for c in candidates:
        # Only compute mutual friends when the viewer actually has friends
        # (a brand-new tourist has none -> skip the extra queries entirely).
        mutual = await mutual_friends_count(my_fids, c["user_id"]) if my_fids else 0
        people.append({
            **c,
            "going_count": going_counts.get(c["user_id"], 0),
            "mutual_friends": mutual,
            "shared_events": shared_counts.get(c["user_id"], 0),
        })
    # People you coincide with this week float to the top.
    people.sort(key=lambda p: (p["shared_events"], p["mutual_friends"], p["going_count"], bool(p.get("picture"))), reverse=True)
    people = people[:24]

    # ---- Public moments feed ----
    public_ids = await db.users.distinct("user_id", {"moment_privacy": "publico"})
    public_ids = [i for i in public_ids if i not in blocked and i != uid]
    moments = []
    if public_ids:
        async for c in db.captures.find(
            {"user_id": {"$in": public_ids}}, {"_id": 0}
        ).sort("created_at", -1).limit(30):
            au = await db.users.find_one({"user_id": c["user_id"]}, {"_id": 0})
            ev = None
            if c.get("event_id"):
                ev = await db.events.find_one({"id": c["event_id"]}, {"_id": 0})
            moments.append({
                "id": c["id"],
                "image_url": c.get("image_url", ""),
                "created_at": c.get("created_at"),
                "author": _msg_author(au),
                "author_id": c["user_id"],
                "event_name": ev["name"] if ev else None,
            })
    # Attach like counts + whether the viewer already liked each moment.
    if moments:
        cap_ids = [m["id"] for m in moments]
        like_counts = {}
        async for row in db.capture_reactions.aggregate([
            {"$match": {"capture_id": {"$in": cap_ids}}},
            {"$group": {"_id": "$capture_id", "n": {"$sum": 1}}},
        ]):
            like_counts[row["_id"]] = row["n"]
        my_liked = set()
        async for r in db.capture_reactions.find(
            {"capture_id": {"$in": cap_ids}, "user_id": uid}, {"_id": 0, "capture_id": 1}
        ):
            my_liked.add(r["capture_id"])
        for m in moments:
            m["likes"] = like_counts.get(m["id"], 0)
            m["i_liked"] = m["id"] in my_liked
    return {"people": people, "moments": moments, "city": my_city}


@api_router.get("/moments/feed")
async def moments_feed(scope: str = "discover", skip: int = 0, limit: int = 8,
                       user: dict = Depends(get_current_user)):
    """Vertical, scrollable feed of 'El Momento' captures.
    scope='amigos' -> captures from accepted friends; scope='discover' -> public
    captures (moment_privacy='publico'). Paginated via skip/limit + has_more."""
    uid = user["user_id"]
    blocked = set(await blocked_relation_ids(uid))
    if scope == "amigos":
        fids = await accepted_friend_ids(uid)
        author_ids = [i for i in fids if i not in blocked]
    else:
        scope = "discover"
        pub = await db.users.distinct("user_id", {"moment_privacy": "publico"})
        author_ids = [i for i in pub if i not in blocked and i != uid]
    if not author_ids:
        return {"moments": [], "has_more": False, "scope": scope}
    limit = max(1, min(int(limit or 8), 20))
    skip = max(0, int(skip or 0))
    rows = []
    async for c in db.captures.find(
        {"user_id": {"$in": author_ids}}, {"_id": 0}
    ).sort("created_at", -1).skip(skip).limit(limit + 1):
        rows.append(c)
    has_more = len(rows) > limit
    rows = rows[:limit]
    moments = []
    for c in rows:
        au = await db.users.find_one({"user_id": c["user_id"]}, {"_id": 0})
        ev = await db.events.find_one({"id": c["event_id"]}, {"_id": 0}) if c.get("event_id") else None
        moments.append({
            "id": c["id"],
            "image_url": c.get("image_url", ""),
            "created_at": c.get("created_at"),
            "author": _msg_author(au),
            "author_id": c["user_id"],
            "event_id": c.get("event_id"),
            "event_name": ev["name"] if ev else None,
        })
    if moments:
        cap_ids = [m["id"] for m in moments]
        like_counts = {}
        async for row in db.capture_reactions.aggregate([
            {"$match": {"capture_id": {"$in": cap_ids}}},
            {"$group": {"_id": "$capture_id", "n": {"$sum": 1}}},
        ]):
            like_counts[row["_id"]] = row["n"]
        my_liked = set()
        async for r in db.capture_reactions.find(
            {"capture_id": {"$in": cap_ids}, "user_id": uid}, {"_id": 0, "capture_id": 1}
        ):
            my_liked.add(r["capture_id"])
        for m in moments:
            m["likes"] = like_counts.get(m["id"], 0)
            m["i_liked"] = m["id"] in my_liked
    return {"moments": moments, "has_more": has_more, "scope": scope}


# ---------------------------------------------------------------------------
# Admin events
# ---------------------------------------------------------------------------
@api_router.post("/admin/events")
async def create_event(inp: EventInput, admin: dict = Depends(require_admin)):
    ev = inp.model_dump()
    ev["id"] = str(uuid.uuid4())
    ev["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.events.insert_one(ev)
    ev.pop("_id", None)
    # Fire "new event" push to all users in the same city (fire-and-forget)
    try:
        asyncio.create_task(_notify_new_event_city(ev))
    except Exception as e:
        logger.warning(f"new_event notify failed: {e}")
    return ev


@api_router.put("/admin/events/{event_id}")
async def edit_event(event_id: str, inp: EventInput, admin: dict = Depends(require_admin)):
    res = await db.events.update_one({"id": event_id}, {"$set": inp.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    return ev


@api_router.put("/admin/events/{event_id}/admin-edit")
async def admin_edit_event(
    event_id: str, inp: AdminEventEditInput, admin: dict = Depends(require_admin)
):
    """Partial edit from the event panel pencil (admin only). Non-link fields are
    applied directly (the scraper may still refresh them later — owner's choice).
    The buy-link override is STICKY: once set it always wins over scraper +
    affiliate logic and the scraper never overwrites it (fixes broken auto links
    like the stale FourVenues affiliate code)."""
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    set_fields: dict = {}
    unset_fields: dict = {}
    changes: list = []  # (field, old, new) for the edit history
    for f in ("name", "venue", "address", "date", "time", "image_url",
              "genre", "city", "sale_state"):
        val = getattr(inp, f)
        if val is not None and val != ev.get(f, ""):
            set_fields[f] = val
            changes.append((f, ev.get(f, ""), val))
    if inp.price_tiers is not None:
        new_tiers = [t.model_dump() for t in inp.price_tiers]
        if new_tiers != (ev.get("price_tiers") or []):
            set_fields["price_tiers"] = new_tiers
            changes.append(("price_tiers", ev.get("price_tiers") or [], new_tiers))
    # Sticky buy-link override.
    old_override = str(ev.get("link_override") or "")
    if inp.clear_link_override:
        if old_override:
            unset_fields["link_override"] = ""
            changes.append(("link_override", old_override, ""))
    elif inp.link_override is not None:
        lo = inp.link_override.strip()
        if lo and lo != old_override:
            set_fields["link_override"] = lo
            set_fields["has_commission"] = True
            changes.append(("link_override", old_override, lo))
        elif not lo and old_override:
            unset_fields["link_override"] = ""
            changes.append(("link_override", old_override, ""))
    update: dict = {}
    if set_fields:
        update["$set"] = set_fields
    if unset_fields:
        update["$unset"] = unset_fields
    if update:
        await db.events.update_one({"id": event_id}, update)
        _invalidate_stats_cache()
        for (f, old, new) in changes:
            await _record_admin_edit(event_id, f, old, new, admin)
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    return await serialize_event(ev, admin, [])


@api_router.get("/admin/events/{event_id}/edit-history")
async def admin_event_edit_history(event_id: str, admin: dict = Depends(require_admin)):
    """The manual edit log for an event (newest first) for the 'Historial de
    ediciones' panel."""
    out = []
    async for h in db.event_admin_edits.find(
        {"event_id": event_id}, {"_id": 0}
    ).sort("created_at", -1).limit(100):
        out.append(h)
    return {"edits": out}


@api_router.post("/admin/events/{event_id}/edit-history/{edit_id}/undo")
async def admin_undo_edit(event_id: str, edit_id: str, admin: dict = Depends(require_admin)):
    """Revert a single manual edit: put the field back to the value it had BEFORE
    that change. Records the revert as a new edit entry so the trail stays honest."""
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    rec = await db.event_admin_edits.find_one({"id": edit_id, "event_id": event_id}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Cambio no encontrado")
    field = rec["field"]
    old = rec.get("old_value")
    current = ev.get(field, "")
    if field == "link_override":
        if old:
            await db.events.update_one({"id": event_id}, {"$set": {"link_override": old, "has_commission": True}})
        else:
            await db.events.update_one({"id": event_id}, {"$unset": {"link_override": ""}})
    else:
        await db.events.update_one({"id": event_id}, {"$set": {field: old}})
    await db.event_admin_edits.update_one({"id": edit_id}, {"$set": {"undone": True}})
    await _record_admin_edit(event_id, field, current, old, admin, note="undo")
    _invalidate_stats_cache()
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    return await serialize_event(ev, admin, [])


@api_router.get("/admin/link-health")
async def admin_link_health(admin: dict = Depends(require_admin),
                            days: int = Query(120), city: str = Query("")):
    """Surface upcoming events whose BUY LINK is at risk of being broken, so the
    owner can fix them (with the pencil) before anyone clicks. Detection is
    deterministic (no live HTTP — FourVenues blocks datacenter IPs via Cloudflare,
    which would give false positives):
      - 'empty': the event says it has a ticket link but the served link is empty.
      - 'affiliate_stale_risk': an affiliate (FourVenues) party whose served link
        has NO code coming from the event's OWN live link, so it falls back to the
        code from the affiliate panel feed — which desyncs when the club recreates
        the event (the exact 'Fitz → .../events/H6LG' broken-redirect class). These
        are the ones to double-check / pin a manual link.
    Events with a manual link_override are considered fixed and never flagged."""
    checked, at_risk = await _scan_broken_links(days=days, city=city)
    return {"total": len(at_risk), "checked": checked, "events": at_risk}


@api_router.post("/admin/link-health/notify")
async def admin_link_health_notify(admin: dict = Depends(require_admin)):
    """Run the at-risk buy-link scan now and push a grouped alert to admins for any
    NEW broken links (same routine the scraper runs automatically). Lets the owner
    test the alert and force an immediate check."""
    n = await _notify_admins_broken_links()
    return {"ok": True, "notified_new": n}


async def _scan_broken_links(days: int = 120, city: str = ""):
    """Shared at-risk buy-link scan (used by the admin panel endpoint AND the
    scheduled admin push alert). Returns (checked_count, at_risk_list)."""
    today = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
    end = (date.fromisoformat(today) + timedelta(days=max(1, days))).isoformat()
    q: dict = {"date": {"$gte": today, "$lte": end}}
    if city and city in CITY_IDS:
        q["city"] = city_query_value(city)
    at_risk = []
    checked = 0
    async for ev in db.events.find(q, {"_id": 0}):
        if ev.get("city") == PENDING_CITY:
            continue
        checked += 1
        override = str(ev.get("link_override") or "").strip()
        if override:
            continue  # manually fixed
        eff = _commission_url_for(ev)
        reason = None
        if not eff:
            if ev.get("has_commission"):
                reason = "empty"
        elif _affiliate_match(ev) and not _affiliate_map_is_fresh():
            # It's one of ours but the quienva feed is stale (e.g. token expired), so
            # right now we're serving its direct link and losing the commission —
            # worth flagging so the owner renews the FourVenues token.
            reason = "affiliate_stale_feed"
        if reason:
            at_risk.append({
                "event_id": ev["id"],
                "name": ev.get("name", ""),
                "venue": ev.get("venue", ""),
                "date": ev.get("date", ""),
                "time": ev.get("time", ""),
                "city": ev.get("city", ""),
                "reason": reason,
                "commission_url": eff,
                "auto_commission_url": _auto_commission_url_for(ev),
            })
    at_risk.sort(key=lambda x: (x["date"], x["venue"]))
    return checked, at_risk


async def _notify_admins_broken_links():
    """Send ONE grouped push to every admin when NEW at-risk buy links appear
    (see _scan_broken_links). Persists the set of already-alerted event ids in
    app_settings key 'admin_notified_broken_links' so the same event never
    re-alerts until it's fixed and breaks again. Opt-out via app_settings key
    'admin_broken_link_alerts' (ON by default). Never raises."""
    try:
        s = await db.app_settings.find_one({"key": "admin_broken_link_alerts"}, {"_id": 0})
        if s is not None and s.get("value") is False:
            return 0  # disabled by admin
        _checked, at_risk = await _scan_broken_links(days=120)
        current_ids = {e["event_id"] for e in at_risk}
        prev_doc = await db.app_settings.find_one({"key": "admin_notified_broken_links"}, {"_id": 0})
        prev_ids = set((prev_doc or {}).get("value") or [])
        # Keep the persisted set aligned with what's currently broken (so a fixed
        # event that breaks AGAIN later will alert again), and find the genuinely NEW ones.
        new_ids = current_ids - prev_ids
        await db.app_settings.update_one(
            {"key": "admin_notified_broken_links"},
            {"$set": {"key": "admin_notified_broken_links", "value": list(current_ids),
                      "updated_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )
        if not new_ids:
            return 0
        new_events = [e for e in at_risk if e["event_id"] in new_ids]
        n = len(new_events)
        sample = "; ".join(f"{(e.get('name') or '¿?')[:28]} ({e.get('venue') or ''})" for e in new_events[:3])
        titulo = "1 evento con enlace en riesgo" if n == 1 else f"{n} eventos con enlace en riesgo"
        msg = f"⚠️ {titulo}. Ábrelo y arréglalo con el lápiz." + (f" Ej.: {sample}" if sample else "")
        data = {"type": "admin_broken_link", "count": n,
                "event_id": new_events[0]["event_id"] if n == 1 else None,
                "url": f"/event/{new_events[0]['event_id']}" if n == 1 else "/admin"}
        async for a in db.users.find({"role": "admin"}, {"_id": 0, "user_id": 1}):
            await create_notification(a["user_id"], "admin_broken_link", msg, data)
        return n
    except Exception as e:
        logger.warning(f"[broken-link-alert] failed: {e}")
        return 0


@api_router.delete("/admin/events/{event_id}")
async def delete_event(event_id: str, admin: dict = Depends(require_admin)):
    await db.events.delete_one({"id": event_id})
    await db.interests.delete_many({"event_id": event_id})
    await db.event_messages.delete_many({"event_id": event_id})
    await db.event_follows.delete_many({"event_id": event_id})
    await db.notifications.delete_many({"data.event_id": event_id})
    return {"ok": True}


# =========================
# EVENT FOLLOWS ("avísame cuando salgan entradas")
# =========================
@api_router.post("/events/{event_id}/follow")
async def follow_event(event_id: str, user: dict = Depends(get_current_user)):
    """Follow an event to receive push notifications about ticket sales,
    price changes, low stock and sold-out. Idempotent."""
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    await db.event_follows.update_one(
        {"user_id": user["user_id"], "event_id": event_id},
        {"$set": {"user_id": user["user_id"], "event_id": event_id,
                  "created_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    _invalidate_stats_cache(user["user_id"])
    return {"ok": True, "following": True}


@api_router.delete("/events/{event_id}/follow")
async def unfollow_event(event_id: str, user: dict = Depends(get_current_user)):
    await db.event_follows.delete_one({"user_id": user["user_id"], "event_id": event_id})
    _invalidate_stats_cache(user["user_id"])
    return {"ok": True, "following": False}


@api_router.get("/events/{event_id}/follow-status")
async def follow_status(event_id: str, user: dict = Depends(get_current_user)):
    f = await db.event_follows.find_one({"user_id": user["user_id"], "event_id": event_id})
    return {"following": bool(f)}


# =========================
# EVENT PRICING (admin) + auto-notifications
# =========================
VALID_SALE_STATES = {"no_a_la_venta", "a_la_venta", "pocas_entradas", "agotado"}


async def _notify_event_audience(event_id: str, kind: str, title: str, body: str, url: str = ""):
    """Send in-app + web push notification to everyone interested in the event:
    followers + users with 'voy' or 'me_interesa' interest. De-duplicates users."""
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        return 0
    target_ids = set()
    async for f in db.event_follows.find({"event_id": event_id}, {"_id": 0, "user_id": 1}):
        target_ids.add(f["user_id"])
    async for it in db.interests.find(
        {"event_id": event_id, "status": {"$in": ["voy", "me_interesa"]}},
        {"_id": 0, "user_id": 1},
    ):
        target_ids.add(it["user_id"])
    # City-wide change opt-in: users who enabled "avisarme de cualquier cambio en
    # mi ciudad" (off by default) get price/sale-state change notifications for
    # every event in their city, even ones they don't follow.
    async for u in db.users.find(
        {"city": region_for_city(ev.get("city")), "city_change_alerts": True},
        {"_id": 0, "user_id": 1},
    ):
        target_ids.add(u["user_id"])
    for uid in target_ids:
        await create_notification(uid, kind, body, {"event_id": event_id, "type": kind})
    logger.info(f"[notify] event={event_id} kind={kind} → {len(target_ids)} users")
    return len(target_ids)


async def _notify_new_event_city(event: dict):
    """When a new event is created, notify users in the same app-city (region-aware:
    e.g. a Magaluf event notifies Palma de Mallorca users) who OPTED IN to new-party
    alerts (notif_prefs.new_event == True). This is opt-in: users who never enabled
    it get nothing, so the city is no longer auto-broadcast to everyone."""
    region = region_for_city(event.get("city") or "Palma de Mallorca")
    body = f"🆕 Nueva fiesta: {event['name']} · {event.get('venue', '')} ({event['date']})"
    count = 0
    # Only users who explicitly enabled new-party alerts for their city.
    async for u in db.users.find(
        {"city": region, "notif_prefs.new_event": True},
        {"_id": 0, "user_id": 1},
    ):
        await create_notification(
            u["user_id"], "new_event", body,
            {"event_id": event["id"], "type": "new_event"},
        )
        count += 1
    logger.info(f"[notify] new_event {event['id']} → {count} opted-in users in {region}")
    return count


def _describe_sale_transition(old: str, new: str) -> Optional[tuple]:
    """Return (kind, body_template) for a sale state transition, or None if
    the transition doesn't warrant a notification."""
    if old == new:
        return None
    if new == "a_la_venta":
        return ("tickets_on_sale", "🎟️ ¡Entradas a la venta ya para {name}!")
    if new == "pocas_entradas":
        return ("tickets_low_stock", "⚡ Quedan pocas entradas para {name}. ¡Corre!")
    if new == "agotado":
        return ("tickets_sold_out", "🔒 {name}: entradas agotadas.")
    return None


def _detect_price_increase(old_tiers: list, new_tiers: list) -> Optional[float]:
    """If a new phase with a higher price than the previous max was added,
    or a sold-out flag flipped moving the effective price up, return the new price."""
    def eff(tiers):
        for t in tiers:
            if not t.get("sold_out"):
                return float(t.get("price", 0))
        return None

    old_p = eff(old_tiers or [])
    new_p = eff(new_tiers or [])
    if old_p is not None and new_p is not None and new_p > old_p + 0.001:
        return new_p
    return None


def _detect_price_decrease(old_tiers: list, new_tiers: list) -> Optional[float]:
    """If the effective (cheapest available) price dropped between runs,
    return the new lower price. Used to fire a 'price drop' notification."""
    def eff(tiers):
        avail = [float(t.get("price", 0)) for t in (tiers or []) if not t.get("sold_out")]
        return min(avail) if avail else None

    old_p = eff(old_tiers or [])
    new_p = eff(new_tiers or [])
    if old_p is not None and new_p is not None and new_p < old_p - 0.001:
        return new_p
    return None


@api_router.put("/admin/events/{event_id}/pricing")
async def admin_set_pricing(event_id: str, inp: EventPricingInput, admin: dict = Depends(require_admin)):
    """Update price tiers and sale state. Automatically sends push notifications
    to followers + interested users on meaningful transitions:
    - sale_state → a_la_venta
    - sale_state → pocas_entradas
    - sale_state → agotado
    - effective price went up (previous phase sold out, new phase active)
    Set silent=true to update without notifying (bulk edits, corrections)."""
    if inp.sale_state not in VALID_SALE_STATES:
        raise HTTPException(status_code=400, detail=f"Estado inválido. Válidos: {', '.join(VALID_SALE_STATES)}")

    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento no encontrado")

    old_state = ev.get("sale_state", "no_a_la_venta")
    old_tiers = ev.get("price_tiers", [])
    new_tiers = [t.model_dump() for t in inp.price_tiers]

    await db.events.update_one(
        {"id": event_id},
        {"$set": {"price_tiers": new_tiers, "sale_state": inp.sale_state}},
    )
    # Invalidate caches so the feed reflects the change
    _invalidate_stats_cache()

    # Persistent history (admin manual change) — always recorded, even if silent
    def _eff_price(tiers):
        avail = [t.get("price") for t in (tiers or []) if not t.get("sold_out") and t.get("price") is not None]
        return min(avail) if avail else None
    old_price = _eff_price(old_tiers)
    new_price_hist = _eff_price(new_tiers)
    if old_state != inp.sale_state:
        await _record_event_history(event_id, "state", "admin",
                                    {"old_state": old_state, "new_state": inp.sale_state})
    if old_price != new_price_hist:
        kind_h = "price_up" if (old_price is not None and new_price_hist is not None and new_price_hist > old_price) else ("price_down" if (old_price is not None and new_price_hist is not None and new_price_hist < old_price) else "pricing_edited")
        await _record_event_history(event_id, kind_h, "admin",
                                    {"old_price": old_price, "new_price": new_price_hist})

    notifications_sent = 0
    if not inp.silent:
        # 1) State transition notification
        transition = _describe_sale_transition(old_state, inp.sale_state)
        if transition:
            kind, template = transition
            body = template.format(name=ev["name"])
            notifications_sent += await _notify_event_audience(event_id, kind, ev["name"], body)
        # 2) Price increase notification (independent of state transition)
        new_price = _detect_price_increase(old_tiers, new_tiers)
        if new_price is not None and inp.sale_state == "a_la_venta":
            body = f"📈 Nueva fase de precios en {ev['name']}: ahora {int(new_price)}€. Aprovecha antes de la siguiente subida."
            notifications_sent += await _notify_event_audience(event_id, "tickets_price_up", ev["name"], body)

    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    return {"event": ev, "notifications_sent": notifications_sent}


@api_router.post("/admin/events/{event_id}/notify-low-stock")
async def admin_notify_low_stock(event_id: str, admin: dict = Depends(require_admin)):
    """Manually fire the 'pocas entradas' notification without changing the sale
    state (useful when Forvenues shows 'few tickets left' but you don't want to
    change the state)."""
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    body = f"⚡ Quedan pocas entradas para {ev['name']}. ¡Corre!"
    count = await _notify_event_audience(event_id, "tickets_low_stock", ev["name"], body)
    return {"notified": count}


# =========================
# ADMIN — Users & Stats
# =========================

@api_router.get("/admin/users")
async def admin_list_users(
    admin: dict = Depends(require_admin),
    search: str = Query("", description="Búsqueda por nombre o email"),
    limit: int = Query(200, ge=1, le=1000),
):
    q = {}
    if search:
        rx = {"$regex": re.escape(search), "$options": "i"}
        q = {"$or": [{"name": rx}, {"email": rx}]}
    users = []
    async for u in db.users.find(q, {"_id": 0, "password": 0}).sort("created_at", -1).limit(limit):
        going = await db.interests.count_documents({"user_id": u["user_id"], "status": "voy"})
        attended = await db.interests.count_documents({"user_id": u["user_id"], "status": "estuve"})
        friends = await db.friendships.count_documents({
            "$or": [{"from_user_id": u["user_id"], "status": "accepted"},
                    {"to_user_id": u["user_id"], "status": "accepted"}]
        })
        u["_stats"] = {"going": going, "attended": attended, "friends": friends}
        users.append(u)
    return users


class UserRoleInput(BaseModel):
    role: str  # "admin" | "user"


@api_router.put("/admin/users/{user_id}/role")
async def admin_set_role(user_id: str, inp: UserRoleInput, admin: dict = Depends(require_admin)):
    if inp.role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="Rol inválido")
    res = await db.users.update_one({"user_id": user_id}, {"$set": {"role": inp.role}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return {"ok": True}


@api_router.delete("/admin/users/{user_id}")
async def admin_delete_user(user_id: str, admin: dict = Depends(require_admin)):
    if user_id == admin["user_id"]:
        raise HTTPException(status_code=400, detail="No puedes borrarte a ti mismo")
    await db.users.delete_one({"user_id": user_id})
    await db.interests.delete_many({"user_id": user_id})
    await db.friendships.delete_many({"$or": [{"from_user_id": user_id}, {"to_user_id": user_id}]})
    await db.notifications.delete_many({"user_id": user_id})
    await db.stories.delete_many({"user_id": user_id})
    return {"ok": True}


@api_router.get("/admin/stats")
async def admin_stats(admin: dict = Depends(require_admin)):
    """High-level dashboard stats for the admin panel."""
    today = datetime.now(ZoneInfo("Europe/Madrid")).date()
    week_ago = (today - timedelta(days=7)).isoformat()
    total_users = await db.users.count_documents({})
    active_week = await db.interests.distinct("user_id", {"created_at": {"$gte": week_ago}})
    total_events = await db.events.count_documents({})
    upcoming_events = await db.events.count_documents({"date": {"$gte": today.isoformat()}})
    total_going = await db.interests.count_documents({"status": "voy"})
    total_interested = await db.interests.count_documents({"status": "me_interesa"})
    total_attended = await db.interests.count_documents({"status": "estuve"})
    total_stories = await db.stories.count_documents({})
    total_friendships = await db.friendships.count_documents({"status": "accepted"})

    # Top events by attendance in the next 30 days
    horizon = (today + timedelta(days=30)).isoformat()
    top_events = []
    async for ev in db.events.find({"date": {"$gte": today.isoformat(), "$lte": horizon}}, {"_id": 0}):
        cnt = await db.interests.count_documents({"event_id": ev["id"], "status": {"$in": ["voy", "me_interesa"]}})
        if cnt > 0:
            top_events.append({"id": ev["id"], "name": ev["name"], "date": ev["date"], "venue": ev.get("venue", ""), "signups": cnt})
    top_events.sort(key=lambda e: -e["signups"])
    top_events = top_events[:8]

    # Genre popularity
    genre_counts = {}
    async for it in db.interests.find({"status": {"$in": ["voy", "estuve"]}}, {"_id": 0, "event_id": 1}):
        ev = await db.events.find_one({"id": it["event_id"]}, {"_id": 0, "genre": 1})
        if ev and ev.get("genre"):
            genre_counts[ev["genre"]] = genre_counts.get(ev["genre"], 0) + 1
    genres_ranked = sorted([{"genre": g, "count": c} for g, c in genre_counts.items()], key=lambda x: -x["count"])[:8]

    return {
        "totals": {
            "users": total_users,
            "active_week": len(active_week),
            "events": total_events,
            "upcoming": upcoming_events,
            "going": total_going,
            "interested": total_interested,
            "attended": total_attended,
            "stories": total_stories,
            "friendships": total_friendships,
        },
        "top_events": top_events,
        "genres": genres_ranked,
    }


@api_router.get("/admin/events")
async def admin_list_events(admin: dict = Depends(require_admin),
                            city: str = Query(""), scope: str = Query("all")):
    """Admin party list, filterable by app-city (region-aware) and time scope.
    Lightweight projection — the heavy per-event serialization is not needed here."""
    q = {}
    if city:
        q["city"] = city_query_value(city)
    today = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
    if scope == "upcoming":
        q["date"] = {"$gte": today}
    elif scope == "past":
        q["date"] = {"$lt": today}
    proj = {"_id": 0, "id": 1, "name": 1, "venue": 1, "date": 1, "time": 1,
            "image_url": 1, "has_commission": 1, "city": 1, "sale_state": 1,
            "featured": 1, "source": 1, "price_tiers": 1}
    sort_dir = -1 if scope == "past" else 1
    events = []
    async for ev in db.events.find(q, proj).sort("date", sort_dir):
        events.append(ev)
    return events


DEFAULT_COMMISSION_PCT = 0.10  # your cut per ticket sold via the app


def _est_commission(ev: dict, tickets: int) -> float:
    price = _current_price(ev) or 0
    pct = ev.get("commission_pct", DEFAULT_COMMISSION_PCT)
    return round(price * tickets * pct, 2)


@api_router.get("/admin/funnel")
async def admin_funnel(admin: dict = Depends(require_admin), scope: str = Query("upcoming")):
    """Money funnel per event: views → interested/going → ticket clicks → tickets → € commission.
    scope=upcoming (default) or all. Uses grouped aggregations (fast even with many events)."""
    today = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
    q = {} if scope == "all" else {"date": {"$gte": today}}
    events = [ev async for ev in db.events.find(q, {"_id": 0}).sort("date", 1)]
    ev_ids = [ev["id"] for ev in events]

    # bulk metrics (views)
    metrics = {}
    async for m in db.event_metrics.find({"event_id": {"$in": ev_ids}}, {"_id": 0}):
        metrics[m["event_id"]] = m

    # grouped interest counts by (event_id, status)
    going_map, interested_map = {}, {}
    async for row in db.interests.aggregate([
        {"$match": {"event_id": {"$in": ev_ids}, "status": {"$in": ["voy", "me_interesa"]}}},
        {"$group": {"_id": {"e": "$event_id", "s": "$status"}, "n": {"$sum": 1}}},
    ]):
        if row["_id"]["s"] == "voy":
            going_map[row["_id"]["e"]] = row["n"]
        else:
            interested_map[row["_id"]["e"]] = row["n"]

    # grouped tickets + clicks
    tickets_map = {r["_id"]: r["n"] async for r in db.tickets.aggregate([
        {"$match": {"event_id": {"$in": ev_ids}}},
        {"$group": {"_id": "$event_id", "n": {"$sum": 1}}},
    ])}
    clicks_map = {r["_id"]: r["n"] async for r in db.ticket_purchases.aggregate([
        {"$match": {"event_id": {"$in": ev_ids}}},
        {"$group": {"_id": "$event_id", "n": {"$sum": 1}}},
    ])}

    rows = []
    totals = {"views": 0, "interested": 0, "going": 0, "clicks": 0, "tickets": 0, "commission": 0.0}
    for ev in events:
        eid = ev["id"]
        going = going_map.get(eid, 0)
        interested = interested_map.get(eid, 0)
        tickets = tickets_map.get(eid, 0)
        clicks = clicks_map.get(eid, 0)
        views = metrics.get(eid, {}).get("views", 0)
        commission = _est_commission(ev, tickets)
        conv = round((tickets / clicks) * 100, 1) if clicks else 0.0
        rows.append({
            "id": eid, "name": ev["name"], "venue": ev.get("venue", ""), "date": ev.get("date", ""),
            "price": _current_price(ev), "sale_state": ev.get("sale_state", "no_a_la_venta"),
            "views": views, "interested": interested, "going": going,
            "clicks": clicks, "tickets": tickets,
            "conversion_pct": conv, "est_commission": commission,
            "has_commission": ev.get("has_commission", False),
        })
        totals["views"] += views
        totals["interested"] += interested
        totals["going"] += going
        totals["clicks"] += clicks
        totals["tickets"] += tickets
        totals["commission"] += commission
    rows.sort(key=lambda r: -r["est_commission"])
    totals["commission"] = round(totals["commission"], 2)
    return {"rows": rows, "totals": totals}


@api_router.get("/admin/venue-report")
async def admin_venue_report(admin: dict = Depends(require_admin)):
    """Aggregated reach/sales by venue — the one-pager you show a club to close a deal.
    Grouped aggregations (fast)."""
    events = [ev async for ev in db.events.find({}, {"_id": 0})]
    ev_ids = [ev["id"] for ev in events]
    metrics = {}
    async for m in db.event_metrics.find({"event_id": {"$in": ev_ids}}, {"_id": 0}):
        metrics[m["event_id"]] = m
    going_map, interested_map = {}, {}
    async for row in db.interests.aggregate([
        {"$match": {"event_id": {"$in": ev_ids}, "status": {"$in": ["voy", "me_interesa"]}}},
        {"$group": {"_id": {"e": "$event_id", "s": "$status"}, "n": {"$sum": 1}}},
    ]):
        (going_map if row["_id"]["s"] == "voy" else interested_map)[row["_id"]["e"]] = row["n"]
    tickets_map = {r["_id"]: r["n"] async for r in db.tickets.aggregate([
        {"$match": {"event_id": {"$in": ev_ids}}}, {"$group": {"_id": "$event_id", "n": {"$sum": 1}}}])}
    clicks_map = {r["_id"]: r["n"] async for r in db.ticket_purchases.aggregate([
        {"$match": {"event_id": {"$in": ev_ids}}}, {"$group": {"_id": "$event_id", "n": {"$sum": 1}}}])}
    venues = {}
    for ev in events:
        v = ev.get("venue", "Otros")
        d = venues.setdefault(v, {"venue": v, "events": 0, "views": 0, "interested": 0, "going": 0, "clicks": 0, "tickets": 0, "commission": 0.0})
        eid = ev["id"]
        tickets = tickets_map.get(eid, 0)
        d["events"] += 1
        d["views"] += metrics.get(eid, {}).get("views", 0)
        d["interested"] += interested_map.get(eid, 0)
        d["going"] += going_map.get(eid, 0)
        d["clicks"] += clicks_map.get(eid, 0)
        d["tickets"] += tickets
        d["commission"] += _est_commission(ev, tickets)
    out = list(venues.values())
    for d in out:
        d["commission"] = round(d["commission"], 2)
    out.sort(key=lambda x: -(x["going"] + x["tickets"]))
    return {"venues": out}


@api_router.get("/admin/events/{event_id}/history")
async def admin_event_history(event_id: str, admin: dict = Depends(require_admin)):
    """Persistent timeline of every price/state change for one event (scraper + admin)."""
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    entries = []
    async for h in db.event_history.find({"event_id": event_id}, {"_id": 0}).sort("created_at", -1).limit(200):
        entries.append(h)
    return {"event_id": event_id, "name": ev.get("name"), "entries": entries, "total": len(entries)}


@api_router.get("/admin/events/{event_id}/stats")
async def admin_event_stats(event_id: str, admin: dict = Depends(require_admin)):
    """FULL per-event dashboard (admin 'Gran Hermano'): funnel + who's going/interested/
    attended, tickets, clicks, views, album, captures, followers, current pricing + history."""
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    eid = event_id

    async def _people(status, limit=60):
        ids = await db.interests.distinct("user_id", {"event_id": eid, "status": status})
        people = []
        async for u in db.users.find({"user_id": {"$in": ids}}, {"_id": 0, "user_id": 1, "name": 1, "picture": 1, "city": 1}).limit(limit):
            people.append({"user_id": u["user_id"], "name": display_name(u), "picture": u.get("picture", ""), "city": u.get("city", "")})
        return people

    async def _history():
        return [h async for h in db.event_history.find({"event_id": eid}, {"_id": 0}).sort("created_at", -1).limit(100)]

    async def _metric():
        return await db.event_metrics.find_one({"event_id": eid}, {"_id": 0}) or {}

    # Run everything concurrently for speed
    (metric, going, interested, attended, tickets, clicks, followers, album_items, captures,
     ppl_going, ppl_interested, ppl_attended, history) = await asyncio.gather(
        _metric(),
        db.interests.count_documents({"event_id": eid, "status": "voy"}),
        db.interests.count_documents({"event_id": eid, "status": "me_interesa"}),
        db.interests.count_documents({"event_id": eid, "status": "estuve"}),
        db.tickets.count_documents({"event_id": eid}),
        db.ticket_purchases.count_documents({"event_id": eid}),
        db.event_follows.count_documents({"event_id": eid}),
        db.album_uploads.count_documents({"event_id": eid}),
        db.captures.count_documents({"event_id": eid}),
        _people("voy"), _people("me_interesa"), _people("estuve"),
        _history(),
    )
    views = metric.get("views", 0)
    commission = _est_commission(ev, tickets)
    conv = round((tickets / clicks) * 100, 1) if clicks else 0.0
    return {
        "event": {
            "id": ev["id"], "name": ev.get("name"), "venue": ev.get("venue", ""),
            "date": ev.get("date", ""), "time": ev.get("time", ""), "genre": ev.get("genre", ""),
            "image_url": ev.get("image_url", ""), "city": ev.get("city", ""),
            "source": ev.get("source", "manual"),
            "price_tiers": ev.get("price_tiers", []), "sale_state": ev.get("sale_state", "no_a_la_venta"),
            "current_price": _current_price(ev), "currency": ev.get("currency", "EUR"),
            "commission_url": ev.get("commission_url", ""), "has_commission": ev.get("has_commission", False),
            "featured": bool(ev.get("featured", False)),
        },
        "funnel": {
            "views": views, "interested": interested, "going": going, "attended": attended,
            "clicks": clicks, "tickets": tickets, "followers": followers,
            "album_items": album_items, "captures": captures,
            "conversion_pct": conv, "est_commission": commission,
        },
        "people": {
            "going": ppl_going,
            "interested": ppl_interested,
            "attended": ppl_attended,
        },
        "history": history,
    }


class NotifyInterestedInput(BaseModel):
    message: str = ""


@api_router.post("/admin/events/{event_id}/notify-interested")
async def admin_notify_interested(event_id: str, inp: NotifyInterestedInput, admin: dict = Depends(require_admin)):
    """Send a custom push to everyone interested/going/following an event
    (retargeting to recover ticket sales)."""
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    body = inp.message.strip() or f"🎟️ Últimas entradas para {ev['name']}. ¡No te quedes fuera!"
    count = await _notify_event_audience(event_id, "tickets_reminder", ev["name"], body)
    return {"notified": count}


# =========================================================================
# ADMIN — preset notification broadcasts (send whenever you want)
# =========================================================================
ADMIN_NOTIFY_PRESETS = [
    {"id": "on_sale", "label": "Entradas a la venta", "emoji": "🎟️", "needs_event": True,
     "title": "¡Entradas a la venta!", "body": "🎟️ ¡Ya hay entradas para {name}! Pilla la tuya antes de que vuelen."},
    {"id": "low_stock", "label": "Quedan pocas", "emoji": "⚡", "needs_event": True,
     "title": "Quedan pocas entradas", "body": "⚡ Quedan pocas entradas para {name}. ¡No te quedes fuera!"},
    {"id": "price_up_soon", "label": "El precio sube pronto", "emoji": "⏰", "needs_event": True,
     "title": "El precio sube pronto", "body": "⏰ El precio de {name} sube pronto. Aprovecha ahora que está más barato."},
    {"id": "price_down", "label": "Bajada de precio", "emoji": "📉", "needs_event": True,
     "title": "¡Bajada de precio!", "body": "📉 ¡Bajada de precio en {name}! Entradas más baratas por tiempo limitado."},
    {"id": "tonight", "label": "Es esta noche", "emoji": "🔥", "needs_event": True,
     "title": "¡Es esta noche!", "body": "🔥 {name} es HOY. ¿Vas? Marca 'Voy' y avisa a tus colegas."},
    {"id": "last_call", "label": "Última llamada", "emoji": "🚨", "needs_event": True,
     "title": "Última llamada", "body": "🚨 Última llamada para {name}. Las entradas están volando."},
    {"id": "who_goes", "label": "¿Quién va?", "emoji": "👀", "needs_event": True,
     "title": "¿Quién va?", "body": "👀 ¿Vas a {name}? Descubre qué amigos van y organizaos."},
    {"id": "album_reminder", "label": "Sube tus fotos", "emoji": "📸", "needs_event": True,
     "title": "Sube tus fotos", "body": "📸 ¿Estuviste en {name}? Sube tus fotos al álbum compartido de la fiesta."},
    {"id": "generic_new", "label": "Nuevas fiestas (a todos)", "emoji": "🆕", "needs_event": False,
     "title": "Nuevas fiestas", "body": "🆕 Hay nuevas fiestas en la app. ¡Échales un vistazo y no te pierdas nada!"},
    {"id": "generic_weekend", "label": "Planes del finde (a todos)", "emoji": "🕺", "needs_event": False,
     "title": "¿Qué hacemos este finde?", "body": "🕺 Llega el finde. Mira todos los planes y decide con tus amigos."},
]


class AdminNotifyInput(BaseModel):
    event_id: str = ""
    preset_id: str = ""
    title: str = ""
    body: str = ""
    audience: str = "event"  # "event" | "all" | "city" | "genre"
    city: str = ""
    genre: str = ""
    send_at: str = ""  # ISO datetime; if set & in the future -> scheduled


@api_router.get("/admin/notify/presets")
async def admin_notify_presets(admin: dict = Depends(require_admin)):
    return {"presets": ADMIN_NOTIFY_PRESETS}


class FeaturedInput(BaseModel):
    featured: bool = True


@api_router.put("/admin/events/{event_id}/featured")
async def admin_set_featured(event_id: str, inp: FeaturedInput, admin: dict = Depends(require_admin)):
    """Promote (or un-promote) an event so it floats to the top of the feed."""
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    await db.events.update_one({"id": event_id}, {"$set": {"featured": bool(inp.featured)}})
    _invalidate_stats_cache()
    return {"ok": True, "featured": bool(inp.featured)}


@api_router.get("/admin/events-min")
async def admin_events_min(admin: dict = Depends(require_admin), q: str = Query(""), city: str = Query("")):
    """Lightweight event list for the notification composer (id/name/venue/date/city).
    Returns UPCOMING events sorted ASC (soonest first) so the admin can find any
    party that is about to happen — the old DESC+500 cap hid most near-term
    parties when many cities were loaded. Supports an optional ?city= filter
    (region-aware) and always excludes 'pending' (unassigned) events."""
    today = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
    query = {"date": {"$gte": today}}
    if city and city in CITY_IDS:
        query["city"] = city_query_value(city)
    else:
        query["city"] = {"$ne": PENDING_CITY}
    if q:
        query["name"] = {"$regex": q, "$options": "i"}
    out = []
    async for ev in db.events.find(
        query,
        {"_id": 0, "id": 1, "name": 1, "venue": 1, "date": 1, "time": 1, "city": 1, "sale_state": 1},
    ).sort("date", 1).limit(1000):
        out.append(ev)
    return {"events": out}


async def _resolve_segment_user_ids(audience: str, city: str = "", genre: str = "") -> list:
    """Return the list of user_ids for a broadcast segment."""
    if audience == "city" and city:
        return await db.users.distinct("user_id", {"city": city})
    if audience == "genre" and genre:
        ev_ids = await db.events.distinct("id", {"genre": genre})
        if not ev_ids:
            return []
        return await db.interests.distinct("user_id", {"event_id": {"$in": ev_ids}})
    return await db.users.distinct("user_id", {})


async def _broadcast_to_users(user_ids: list, ntype: str, body: str):
    count = 0
    for uid in user_ids:
        await create_notification(uid, ntype, body, {"type": ntype, "url": "/feed"})
        count += 1
    logger.info(f"[admin_notify] broadcast → {count} users")
    return count


async def _resolve_notify_body(preset_id: str, custom_body: str, event: dict) -> str:
    preset = next((p for p in ADMIN_NOTIFY_PRESETS if p["id"] == preset_id), None)
    body = (custom_body or "").strip() or (preset["body"] if preset else "")
    if not body:
        raise HTTPException(status_code=400, detail="Escribe un mensaje o elige un preset")
    if "{name}" in body:
        if not event:
            raise HTTPException(status_code=400, detail="Este mensaje necesita que elijas una fiesta")
        body = body.replace("{name}", event["name"])
    return body


@api_router.post("/admin/notify/send")
async def admin_notify_send(inp: AdminNotifyInput, admin: dict = Depends(require_admin)):
    """Send a preset or custom notification now, or schedule it for later.
    audience: event (followers/going/interested) | all | city | genre."""
    ev = None
    if inp.event_id:
        ev = await db.events.find_one({"id": inp.event_id}, {"_id": 0})
        if not ev:
            raise HTTPException(status_code=404, detail="Evento no encontrado")
    body = await _resolve_notify_body(inp.preset_id, inp.body, ev)

    audience = inp.audience if inp.audience in ("event", "all", "city", "genre") else "event"
    if audience == "event" and not inp.event_id:
        raise HTTPException(status_code=400, detail="Elige una fiesta o cambia la audiencia")
    if audience == "city" and not inp.city:
        raise HTTPException(status_code=400, detail="Elige una ciudad")
    if audience == "genre" and not inp.genre:
        raise HTTPException(status_code=400, detail="Elige un género")

    # SCHEDULE for later?
    if inp.send_at:
        try:
            when = datetime.fromisoformat(inp.send_at.replace("Z", "+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=ZoneInfo("Europe/Madrid"))
        except Exception:
            raise HTTPException(status_code=400, detail="Fecha/hora inválida")
        if when > datetime.now(timezone.utc):
            doc = {
                "id": str(uuid.uuid4()),
                "body": body, "audience": audience,
                "event_id": inp.event_id, "event_name": ev["name"] if ev else "",
                "city": inp.city, "genre": inp.genre,
                "send_at": when.astimezone(timezone.utc).isoformat(),
                "status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.scheduled_notifications.insert_one(doc)
            doc.pop("_id", None)
            return {"ok": True, "scheduled": True, "send_at": doc["send_at"], "id": doc["id"]}

    # SEND NOW
    if audience == "event":
        count = await _notify_event_audience(inp.event_id, "admin_broadcast", ev["name"], body)
        return {"ok": True, "audience": "event", "notified": count}
    user_ids = await _resolve_segment_user_ids(audience, inp.city, inp.genre)
    asyncio.create_task(_broadcast_to_users(user_ids, "admin_broadcast", body))
    return {"ok": True, "audience": audience, "notified": len(user_ids), "queued": True}


@api_router.get("/admin/notify/scheduled")
async def admin_notify_scheduled(admin: dict = Depends(require_admin)):
    out = []
    async for s in db.scheduled_notifications.find({"status": "pending"}, {"_id": 0}).sort("send_at", 1).limit(100):
        out.append(s)
    return {"scheduled": out}


@api_router.delete("/admin/notify/scheduled/{sched_id}")
async def admin_notify_cancel(sched_id: str, admin: dict = Depends(require_admin)):
    r = await db.scheduled_notifications.update_one({"id": sched_id, "status": "pending"}, {"$set": {"status": "cancelled"}})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="No encontrado o ya enviado")
    return {"ok": True, "cancelled": True}


async def process_scheduled_notifications():
    """Scheduler job (runs every minute): send any due scheduled notifications."""
    now_iso = datetime.now(timezone.utc).isoformat()
    due = []
    async for s in db.scheduled_notifications.find({"status": "pending", "send_at": {"$lte": now_iso}}, {"_id": 0}):
        due.append(s)
    for s in due:
        try:
            if s["audience"] == "event" and s.get("event_id"):
                await _notify_event_audience(s["event_id"], "admin_broadcast", s.get("event_name", ""), s["body"])
            else:
                uids = await _resolve_segment_user_ids(s["audience"], s.get("city", ""), s.get("genre", ""))
                await _broadcast_to_users(uids, "admin_broadcast", s["body"])
            await db.scheduled_notifications.update_one({"id": s["id"]}, {"$set": {"status": "sent", "sent_at": datetime.now(timezone.utc).isoformat()}})
        except Exception as e:
            logger.warning(f"scheduled notify {s['id']} failed: {e}")





@api_router.post("/admin/upload")
async def admin_upload(file: UploadFile = File(...), admin: dict = Depends(require_admin)):
    ext = file.filename.split(".")[-1].lower() if "." in file.filename else "bin"
    path = f"{APP_NAME}/events/{uuid.uuid4().hex}.{ext}"
    data = await file.read()
    ct = file.content_type or "image/jpeg"
    _url = store_media(path, data, ct)
    await db.files.insert_one({
        "id": str(uuid.uuid4()),
        "storage_path": path,
        "content_type": ct,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"image_url": _url}


def _detect_genre(name: str) -> str:
    """Best-effort genre detection from an event name using Spanish keywords."""
    if not name:
        return ""
    n = name.lower()
    mapping = [
        (["techno", "technho", "tekno", "underground"], "Techno"),
        (["reggaeton", "reggeton", "regueton", "perreo", "latin trap"], "Reggaeton"),
        (["house ", " house", "house-", "-house", "deephouse", "deep house", "tech house"], "House"),
        (["indie", "rock ", " rock", "alternative"], "Indie"),
        (["latino", "latin ", "salsa", "bachata", "kizomba", "merengue"], "Latino"),
        (["hip hop", "hip-hop", "hiphop", "rap ", "trap"], "Hip Hop"),
        (["edm ", " edm", "electro", "electronic"], "Electrónica"),
        (["sunset", "chillout", "chill out", "lounge"], "Sunset"),
        (["reggae", "dancehall"], "Reggae"),
        (["pop ", " pop", "hits"], "Pop"),
        (["ochenta", "80s", "90s", "noventa", "retro"], "Retro"),
    ]
    padded = f" {n} "
    for keys, label in mapping:
        for k in keys:
            if k in padded:
                return label
    return ""


class ImportUrlInput(BaseModel):
    url: str


def _parse_fourvenues_url(url: str) -> dict:
    """Deterministic extraction from Fourvenues URLs (works even if the page is Cloudflare-blocked).

    Examples:
      https://site.fourvenues.com/es/discoteca-amok-mallorca@amok/events/bonitx--01-08-2026-WVUY
      https://site.fourvenues.com/es/discoteca-amok-mallorca@amok?gad_source=...
    """
    from urllib.parse import urlparse
    p = urlparse(url)
    if "fourvenues.com" not in p.netloc:
        return {}
    parts = [x for x in p.path.split("/") if x]
    # Strip locale (es, en, ca...)
    if parts and len(parts[0]) == 2:
        parts = parts[1:]
    if not parts:
        return {}

    venue_slug = parts[0]  # "discoteca-amok-mallorca@amok"
    # After "@" is the short handle, before is the descriptive slug
    venue_pretty = venue_slug.split("@")[0].replace("-", " ").strip().title()

    out = {"venue": venue_pretty, "commission_url": url, "has_commission": True}

    # Event details
    if len(parts) >= 3 and parts[1] == "events":
        event_part = parts[2]  # "bonitx--01-08-2026-WVUY"
        # Regex: <slug>--DD-MM-YYYY-<id>
        m = re.match(r"^(.+?)--(\d{2})-(\d{2})-(\d{4})(?:-([A-Za-z0-9]+))?$", event_part)
        if m:
            name_slug, dd, mm, yyyy, _id = m.groups()
            out["name"] = name_slug.replace("-", " ").strip().title()
            out["date"] = f"{yyyy}-{mm}-{dd}"
        else:
            out["name"] = event_part.replace("-", " ").strip().title()
    return out


def _fetch_html_best_effort(url: str) -> str:
    """Fetch HTML trying multiple strategies. Returns '' if everything fails.

    1) curl_cffi with Chrome fingerprint (bypasses many Cloudflare setups)
    2) plain requests with WhatsApp UA (many sites whitelist link-preview bots)
    3) plain requests with generic browser UA
    """
    strategies = [
        ("curl_cffi:chrome124", True, {"impersonate": "chrome124"}),
        ("curl_cffi:chrome110", True, {"impersonate": "chrome110"}),
        ("whatsapp", False, {"headers": {"User-Agent": "WhatsApp/2.19.81 A"}}),
        ("browser", False, {"headers": {
            "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        }}),
    ]
    for label, use_cffi, kwargs in strategies:
        try:
            if use_cffi:
                from curl_cffi import requests as cf
                r = cf.get(url, timeout=15, **kwargs)
            else:
                r = requests.get(url, timeout=15, allow_redirects=True, **kwargs)
            html = getattr(r, "text", "") or ""
            if r.status_code == 200 and "Hang on a sec" not in html and len(html) > 500:
                logger.info(f"import-url fetched via {label} ({len(html)} bytes)")
                return html
            logger.info(f"import-url {label} => status={r.status_code} blocked={'Hang on a sec' in html}")
        except Exception as e:
            logger.info(f"import-url {label} error: {e}")
    return ""


def _extract_og(html: str) -> dict:
    from bs4 import BeautifulSoup
    if not html:
        return {}
    soup = BeautifulSoup(html, "html.parser")

    def meta(*names):
        for n in names:
            tag = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
            if tag and tag.get("content"):
                return tag["content"].strip()
        return ""

    return {
        "title": meta("og:title", "twitter:title") or (
            soup.title.string.strip() if soup.title and soup.title.string else ""
        ),
        "description": meta("og:description", "twitter:description", "description"),
        "image": meta("og:image", "twitter:image", "og:image:secure_url"),
    }


def _download_image(image_url: str, page_url: str) -> str:
    """Download an image and store it locally. Returns internal /api/files/... path or ''."""
    from urllib.parse import urlparse
    if not image_url:
        return ""
    try:
        if image_url.startswith("//"):
            image_url = "https:" + image_url
        elif image_url.startswith("/"):
            base = urlparse(page_url)
            image_url = f"{base.scheme}://{base.netloc}{image_url}"
        img_res = requests.get(image_url, timeout=12,
                               headers={"User-Agent": "Mozilla/5.0 (QuienVaBot)"})
        img_res.raise_for_status()
        ct = img_res.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        if not ct.startswith("image/"):
            return ""
        ext = mimetypes.guess_extension(ct) or ".jpg"
        if ext == ".jpe":
            ext = ".jpg"
        path = f"{APP_NAME}/events/{uuid.uuid4().hex}{ext}"
        return store_media(path, img_res.content, ct)
    except Exception as e:
        logger.info(f"import-url image download failed: {e}")
        return ""


@api_router.post("/admin/import-url")
async def admin_import_url(inp: ImportUrlInput, admin: dict = Depends(require_admin)):
    """Extract event data from a URL.

    Strategy (in order):
      1) Parse deterministic patterns (e.g. Fourvenues URL structure) — works even if Cloudflare-blocked.
      2) Fetch HTML with browser fingerprint / crawler UA fallbacks.
      3) Read OpenGraph / Twitter meta tags.
      4) Download the og:image to local storage (no hotlink).
    """
    import re as _re  # local alias to avoid shadowing
    url = inp.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL inválida")

    parsed = _parse_fourvenues_url(url)
    html = _fetch_html_best_effort(url)
    og = _extract_og(html) if html else {}

    # For Fourvenues venue-only URLs, don't use OG title (it's just "Fourvenues")
    is_generic_title = og.get("title", "").strip().lower() in {"fourvenues", "xceed", "instagram", "facebook", ""}
    parsed_has_event = bool(parsed.get("name"))

    # Merge: URL parser wins for structured fields, OG wins for descriptive fields
    if parsed_has_event:
        name = parsed["name"]
    elif not is_generic_title:
        name = og.get("title", "").strip()
    else:
        name = ""
    if name:
        # Clean up common suffixes like " - Fourvenues" / " | Sitename"
        name = _re.sub(r"\s*[|\-–—]\s*(Fourvenues|Xceed|DICE|Instagram|Facebook)\s*$", "", name)[:120]

    image_url = _download_image(og.get("image", ""), url) if og.get("image") else ""

    venue = parsed.get("venue", "") or ""
    address = ""
    if venue:
        # Look up address from previously-saved events for this venue
        prev = await db.events.find_one({"venue": venue, "address": {"$ne": ""}}, {"_id": 0, "address": 1})
        if not prev:
            # Fuzzy: case-insensitive contains
            prev = await db.events.find_one(
                {"venue": {"$regex": f"^{_re.escape(venue)}$", "$options": "i"}, "address": {"$ne": ""}},
                {"_id": 0, "address": 1},
            )
        if prev and prev.get("address"):
            address = prev["address"]

    result = {
        "name": name,
        "description": (og.get("description") or "")[:280],
        "image_url": image_url,
        "more_info_url": url,
        "venue": venue,
        "address": address,
        "date": parsed.get("date", ""),
        "genre": _detect_genre(name),
        "has_commission": parsed.get("has_commission", False),
        "commission_url": parsed.get("commission_url", "") if parsed.get("has_commission") else "",
    }
    return result


@api_router.post("/upload/avatar")
async def upload_avatar(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    ext = file.filename.split(".")[-1].lower() if "." in file.filename else "bin"
    path = f"{APP_NAME}/avatars/{user['user_id']}/{uuid.uuid4().hex}.{ext}"
    data = await file.read()
    ct = file.content_type or "image/jpeg"
    _url = store_media(path, data, ct)
    await db.files.insert_one({
        "id": str(uuid.uuid4()),
        "storage_path": path,
        "content_type": ct,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    url = _url
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"picture": url}})
    return {"image_url": url}


@api_router.get("/files/{path:path}")
async def serve_file(path: str):
    data = read_object(path)
    if data is None:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    record = await db.files.find_one({"storage_path": path})
    ct = record["content_type"] if record else (mimetypes.guess_type(path)[0] or "application/octet-stream")
    return StarletteResponse(content=data, media_type=ct,
                             headers={"Cache-Control": "public, max-age=86400"})


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
_NOTIF_PREF_KEYS = [
    "new_event", "tickets_on_sale", "tickets_low_stock", "tickets_sold_out",
    "tickets_price_down", "tickets_price_up", "friend_going",
]
# Opt-IN categories: OFF by default; only delivered if the user explicitly turned
# them ON in Settings. "new_event" (new parties in your city) was previously a
# blanket auto-broadcast to everyone in the city — now it's opt-in so users only
# get city-wide new-party alerts if they choose to. Everything else stays opt-OUT
# (on by default). Ticket-state changes for events the user follows/marked are
# unaffected (they go through _notify_event_audience, not the city broadcast).
_OPT_IN_PREF_KEYS = {"new_event"}
DEFAULT_NOTIF_PREFS = {k: (k not in _OPT_IN_PREF_KEYS) for k in _NOTIF_PREF_KEYS}


async def create_notification(user_id: str, ntype: str, message: str, data: dict):
    # Respect per-user notification preferences for gated categories.
    if ntype in _NOTIF_PREF_KEYS:
        u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "notif_prefs": 1})
        prefs = (u or {}).get("notif_prefs") or {}
        val = prefs.get(ntype)
        if ntype in _OPT_IN_PREF_KEYS:
            # Opt-in: deliver ONLY when explicitly enabled (True).
            if val is not True:
                return
        elif val is False:
            # Opt-out: deliver unless explicitly disabled.
            return
    await db.notifications.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "type": ntype,
        "message": message,
        "data": data,
        "read": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    # Fire-and-forget web push (in-app notification is the fallback)
    url = "/feed"
    if ntype in ("friend_request", "friend_accept"):
        url = "/friends"
    elif ntype in ("weekly_digest", "weekend_recap"):
        url = "/notifications"
    elif ntype == "story_reaction":
        url = "/profile"
    elif ntype in ("moment_prompt", "moment", "moment_friend"):
        url = "/momento"
    elif data and data.get("event_id"):
        url = f"/event/{data['event_id']}"
    try:
        asyncio.create_task(push_to_user(user_id, "¿Quién va?", message, url))
    except RuntimeError:
        pass


def _sync_web_push(sub: dict, payload: str):
    try:
        webpush(
            subscription_info={"endpoint": sub["endpoint"], "keys": sub["keys"]},
            data=payload,
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={"sub": VAPID_SUBJECT},
        )
        return None
    except WebPushException as e:
        code = getattr(getattr(e, "response", None), "status_code", None)
        return sub["endpoint"] if code in (404, 410) else "err"
    except Exception:
        return "err"


async def push_to_user(user_id: str, title: str, body: str, url: str):
    # 1) Web Push (browser / PWA) — unchanged, powers quienva.me.
    if VAPID_PRIVATE_KEY:
        payload = json.dumps({"title": title, "body": body, "url": url})
        subs = []
        async for s in db.push_subscriptions.find({"user_id": user_id}):
            subs.append(s)
        for s in subs:
            dead = await asyncio.to_thread(_sync_web_push, s, payload)
            if dead and dead != "err":
                await db.push_subscriptions.delete_one({"endpoint": dead})
    # 2) APNs (native iOS App Store app) — separate collection & credentials.
    await _apns_to_user(user_id, title, body, url)


async def _apns_to_user(user_id: str, title: str, body: str, url: str):
    if not apns.is_configured():
        return
    try:
        devices = []
        async for d in db.apns_devices.find({"user_id": user_id, "disabled_at": None}):
            devices.append(d)
        for d in devices:
            res = await apns.send_apns(d["token"], title, body, {"url": url})
            if res == "gone":
                await db.apns_devices.update_one(
                    {"_id": d["_id"]},
                    {"$set": {"disabled_at": datetime.now(timezone.utc).isoformat()}},
                )
    except Exception as e:
        logging.warning("APNs dispatch failed for %s: %s", user_id, e)


@api_router.get("/notifications")
async def list_notifications(user: dict = Depends(get_current_user)):
    out = []
    async for n in db.notifications.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).limit(50):
        out.append(n)
    return out


@api_router.get("/notifications/unread-count")
async def unread_count(user: dict = Depends(get_current_user)):
    count = await db.notifications.count_documents({"user_id": user["user_id"], "read": False})
    return {"count": count}


@api_router.post("/notifications/{notif_id}/read")
async def mark_read(notif_id: str, user: dict = Depends(get_current_user)):
    await db.notifications.update_one({"id": notif_id, "user_id": user["user_id"]}, {"$set": {"read": True}})
    return {"ok": True}


@api_router.post("/notifications/read-all")
async def mark_all_read(user: dict = Depends(get_current_user)):
    await db.notifications.update_many({"user_id": user["user_id"]}, {"$set": {"read": True}})
    return {"ok": True}


class NotifPrefsInput(BaseModel):
    prefs: dict


@api_router.get("/me/notif-prefs")
async def get_notif_prefs(user: dict = Depends(get_current_user)):
    prefs = {**DEFAULT_NOTIF_PREFS, **(user.get("notif_prefs") or {})}
    return {"prefs": prefs, "keys": _NOTIF_PREF_KEYS}


@api_router.put("/me/notif-prefs")
async def set_notif_prefs(inp: NotifPrefsInput, user: dict = Depends(get_current_user)):
    clean = {k: bool(v) for k, v in (inp.prefs or {}).items() if k in _NOTIF_PREF_KEYS}
    merged = {**DEFAULT_NOTIF_PREFS, **(user.get("notif_prefs") or {}), **clean}
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"notif_prefs": merged}})
    return {"prefs": merged}


class CityAlertsInput(BaseModel):
    enabled: bool


@api_router.put("/me/city-alerts")
async def set_city_alerts(inp: CityAlertsInput, user: dict = Depends(get_current_user)):
    """Opt in/out of notifications for ANY change (price/sale-state) on ANY event
    in your city. Off by default."""
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"city_change_alerts": bool(inp.enabled)}},
    )
    return {"city_change_alerts": bool(inp.enabled)}


# ---------------------------------------------------------------------------
# Web Push
# ---------------------------------------------------------------------------
@api_router.get("/push/vapid-public-key")
async def vapid_public_key():
    return {"publicKey": VAPID_PUBLIC_KEY}


@api_router.post("/push/subscribe")
async def push_subscribe(inp: PushSubscriptionInput, user: dict = Depends(get_current_user)):
    await db.push_subscriptions.update_one(
        {"endpoint": inp.endpoint},
        {"$set": {
            "endpoint": inp.endpoint,
            "keys": inp.keys,
            "user_id": user["user_id"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, "$setOnInsert": {"created_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"ok": True}


@api_router.post("/push/unsubscribe")
async def push_unsubscribe(inp: PushSubscriptionInput, user: dict = Depends(get_current_user)):
    await db.push_subscriptions.delete_one({"endpoint": inp.endpoint, "user_id": user["user_id"]})
    return {"ok": True}


@api_router.get("/push/status")
async def push_status(user: dict = Depends(get_current_user)):
    count = await db.push_subscriptions.count_documents({"user_id": user["user_id"]})
    apns_count = await db.apns_devices.count_documents({"user_id": user["user_id"], "disabled_at": None})
    return {"subscribed": count > 0 or apns_count > 0}


@api_router.get("/push/diagnostics")
async def push_diagnostics(user: dict = Depends(get_current_user)):
    """Tells exactly why pushes may not arrive: is APNs configured on this server,
    how many devices are registered, and (production vs sandbox)."""
    apns_count = await db.apns_devices.count_documents({"user_id": user["user_id"], "disabled_at": None})
    web_count = await db.push_subscriptions.count_documents({"user_id": user["user_id"]})
    return {
        "apns_configured": apns.is_configured(),
        "apns_environment": "production" if apns.APNS_PRODUCTION else "sandbox",
        "apns_bundle_id": apns.APNS_BUNDLE_ID,
        "apns_devices": apns_count,
        "web_push_configured": bool(VAPID_PRIVATE_KEY),
        "web_subscriptions": web_count,
    }


@api_router.post("/push/test")
async def push_test(user: dict = Depends(get_current_user)):
    """Send a REAL test notification to the current user's registered devices and
    return a per-device result so the user can confirm delivery end-to-end."""
    # Persist an in-app notification too (bypass pref gating for the test).
    await db.notifications.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user["user_id"],
        "type": "test",
        "message": "🔔 ¡Notificaciones activadas! Esto es una prueba.",
        "data": {},
        "read": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    apns_results = []
    if apns.is_configured():
        async for d in db.apns_devices.find({"user_id": user["user_id"], "disabled_at": None}):
            res = await apns.send_apns(d["token"], "¿Quién va?", "🔔 ¡Notificaciones activadas! Esto es una prueba.", {"url": "/notifications"})
            apns_results.append(res)
            if res == "gone":
                await db.apns_devices.update_one({"_id": d["_id"]}, {"$set": {"disabled_at": datetime.now(timezone.utc).isoformat()}})
    # Web push (browser/PWA) too.
    web_sent = 0
    if VAPID_PRIVATE_KEY:
        payload = json.dumps({"title": "¿Quién va?", "body": "🔔 ¡Notificaciones activadas! Esto es una prueba.", "url": "/notifications"})
        async for s in db.push_subscriptions.find({"user_id": user["user_id"]}):
            dead = await asyncio.to_thread(_sync_web_push, s, payload)
            if dead and dead != "err":
                await db.push_subscriptions.delete_one({"endpoint": dead})
            elif not dead:
                web_sent += 1
    ok = ("ok" in apns_results) or web_sent > 0
    return {
        "ok": ok,
        "apns_configured": apns.is_configured(),
        "apns_devices": len(apns_results),
        "apns_results": apns_results,
        "web_sent": web_sent,
    }


@api_router.get("/admin/push/inspect")
async def admin_push_inspect(email: str, admin: dict = Depends(require_admin)):
    """DEBUG (admin): shows whether a given user's iPhone token is stored on THIS
    server, its APNs environment and whether it got disabled. No app update needed."""
    u = await db.users.find_one({"email": email.lower().strip()}, {"_id": 0, "user_id": 1, "email": 1, "notif_prefs": 1})
    if not u:
        raise HTTPException(status_code=404, detail="user not found")
    devices = []
    async for d in db.apns_devices.find({"user_id": u["user_id"]}, {"_id": 0}):
        devices.append({
            "token_prefix": (d.get("token") or "")[:14],
            "environment": d.get("environment"),
            "disabled_at": d.get("disabled_at"),
            "created_at": d.get("created_at"),
            "updated_at": d.get("updated_at"),
        })
    web = await db.push_subscriptions.count_documents({"user_id": u["user_id"]})
    # Recent native-app diagnostics (self-reported by the device). This reveals
    # WHY a token never arrived: permission result, APNs token arrival, and the
    # upload result/error — plus whether the DEVICE was authenticated at all.
    debug_events = []
    async for ev in db.apns_debug.find(
        {"$or": [{"email": u["email"]}, {"email": None}]}, {"_id": 0},
    ).sort("ts", -1).limit(15):
        debug_events.append(ev)
    return {
        "email": u["email"],
        "server_apns_configured": apns.is_configured(),
        "server_apns_environment": "production" if apns.APNS_PRODUCTION else "sandbox",
        "server_bundle_id": apns.APNS_BUNDLE_ID,
        "apns_devices": devices,
        "web_subscriptions": web,
        "device_debug_log": debug_events,
    }


@api_router.post("/admin/push/send")
async def admin_push_send(email: str, admin: dict = Depends(require_admin)):
    """DEBUG (admin): send a REAL push to a user's registered iPhone(s) and report
    the raw APNs result per device. Tries ALL devices (even disabled) so the exact
    failure is visible. Re-enables a device if Apple accepts it (result 'ok')."""
    u = await db.users.find_one({"email": email.lower().strip()}, {"_id": 0, "user_id": 1})
    if not u:
        raise HTTPException(status_code=404, detail="user not found")
    results = []
    async for d in db.apns_devices.find({"user_id": u["user_id"]}):
        res = await apns.send_apns(d["token"], "¿Quién va?", "🔔 Prueba de notificación", {"url": "/notifications"}, production=True)
        entry = {"token_prefix": (d.get("token") or "")[:14], "env": d.get("environment"), "was_disabled": bool(d.get("disabled_at")), "result_production": res}
        if res != "ok":
            # Probe sandbox: if THIS works, the installed app is a development/sandbox
            # build and needs a production (App Store) build to match the server.
            sandbox_res = await apns.send_apns(d["token"], "¿Quién va?", "🔔 Prueba (sandbox)", {"url": "/notifications"}, production=False)
            entry["result_sandbox"] = sandbox_res
        if res == "ok":
            await db.apns_devices.update_one({"_id": d["_id"]}, {"$set": {"disabled_at": None}})
        results.append(entry)
    if not results:
        hint = "No hay ningun token registrado para este usuario -> la app instalada no envio el token al servidor."
    elif any(r.get("result_production") == "ok" for r in results):
        hint = "OK: entregado a Apple en produccion. Debe llegar al iPhone."
    elif any(r.get("result_sandbox") == "ok" for r in results):
        hint = "ENTORNO EQUIVOCADO: el token funciona en SANDBOX, no en produccion. La app instalada es un build de desarrollo; necesita un build de App Store/TestFlight (aps-environment=production)."
    else:
        hint = "gone/err en ambos entornos -> token invalido o credenciales del servidor incorrectas."
    return {"server_apns_configured": apns.is_configured(), "sent_to": len(results), "results": results, "hint": hint}


class ApnsTokenInput(BaseModel):
    token: str


@api_router.post("/push/apns/register")
async def apns_register(inp: ApnsTokenInput, user: dict = Depends(get_current_user)):
    """Store the APNs device token for the native iOS app. One user can have
    several devices; upsert keyed by (user, token)."""
    token = (inp.token or "").strip()
    if not token or len(token) < 32:
        raise HTTPException(status_code=400, detail="Invalid APNs token")
    now = datetime.now(timezone.utc).isoformat()
    await db.apns_devices.update_one(
        {"user_id": user["user_id"], "token": token},
        {"$set": {
            "user_id": user["user_id"],
            "token": token,
            "platform": "ios",
            "provider": "apns",
            "bundle_id": apns.APNS_BUNDLE_ID,
            "environment": "production" if apns.APNS_PRODUCTION else "sandbox",
            "updated_at": now,
            "disabled_at": None,
        }, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    return {"ok": True, "configured": apns.is_configured()}


@api_router.post("/push/apns/unregister")
async def apns_unregister(inp: ApnsTokenInput, user: dict = Depends(get_current_user)):
    await db.apns_devices.delete_one({"user_id": user["user_id"], "token": (inp.token or "").strip()})
    return {"ok": True}


class ApnsDebugInput(BaseModel):
    stage: str
    detail: Optional[str] = None
    token_prefix: Optional[str] = None
    email: Optional[str] = None
    logged_in: Optional[bool] = None
    platform: Optional[str] = None


@api_router.post("/push/apns/debug")
async def apns_debug_report(inp: ApnsDebugInput, user: dict = Depends(get_optional_user)):
    """Best-effort diagnostic sink for the native app. NEVER fails so we capture
    exactly what happens on the device (permission result, APNs token arrival,
    upload success/error) EVEN when the device has no valid session — which is how
    we tell apart an APNs problem from a not-logged-in problem. Viewable by admin
    via /admin/push/inspect."""
    now = datetime.now(timezone.utc).isoformat()
    server_user_id = user.get("user_id")  # None => the DEVICE is NOT authenticated
    server_email = user.get("email")
    email = ((inp.email or server_email or "").lower().strip()) or None
    await db.apns_debug.insert_one({
        "ts": now,
        "stage": inp.stage,
        "detail": (inp.detail or "")[:500],
        "token_prefix": inp.token_prefix,
        "platform": inp.platform,
        "email": email,
        "client_says_logged_in": inp.logged_in,
        "server_authenticated": server_user_id is not None,
    })
    return {"ok": True}


# ---------------------------------------------------------------------------
# Weekly digest
# ---------------------------------------------------------------------------
async def generate_weekly_digest() -> int:
    today = datetime.now(timezone.utc).date()
    week_end = today + timedelta(days=7)
    sent = 0
    async for u in db.users.find({}, {"_id": 0}):
        fids = await accepted_friend_ids(u["user_id"])
        if not fids:
            continue
        plans = {}  # event name -> set of friend first names
        async for it in db.interests.find({"user_id": {"$in": fids},
                                           "status": {"$in": ["voy", "me_interesa"]}}):
            ev = await db.events.find_one({"id": it["event_id"]}, {"_id": 0})
            if not ev:
                continue
            try:
                d = date.fromisoformat(ev["date"])
            except Exception:
                continue
            if not (today <= d <= week_end):
                continue
            fu = await db.users.find_one({"user_id": it["user_id"]}, {"_id": 0})
            plans.setdefault(ev["name"], set())
            if fu:
                plans[ev["name"]].add(display_name(fu))
        if not plans:
            continue
        n = len(plans)
        names = list(plans.keys())[:3]
        msg = f"Tus amigos tienen {n} plan{'es' if n > 1 else ''} esta semana: " + ", ".join(names)
        if n > 3:
            msg += "…"
        await create_notification(u["user_id"], "weekly_digest", msg, {})
        sent += 1
    logger.info(f"Resumen semanal enviado a {sent} usuarios")
    return sent


@api_router.post("/admin/trigger-weekly-digest")
async def trigger_weekly_digest(admin: dict = Depends(require_admin)):
    sent = await generate_weekly_digest()
    return {"sent": sent}


# ---------------------------------------------------------------------------
# Event reminders (a few hours before an event, for those who marked "voy")
# ---------------------------------------------------------------------------
PALMA_TZ = ZoneInfo("Europe/Madrid")


async def generate_event_reminders() -> int:
    now = datetime.now(PALMA_TZ)
    today = now.date()
    horizon = now + timedelta(hours=3)
    sent = 0

    async def already(uid, eid, ntype):
        return await db.notifications.find_one({"user_id": uid, "type": ntype, "data.event_id": eid})

    async for ev in db.events.find({}, {"_id": 0}):
        try:
            ev_date = date.fromisoformat(ev["date"])
        except Exception:
            ev_date = None
        t = ev.get("time")
        start = None
        if t:
            try:
                start = datetime.fromisoformat(f"{ev['date']}T{t}:00").replace(tzinfo=PALMA_TZ)
            except Exception:
                start = None

        # 1) 'voy' — remind a few hours before it starts
        if start and now <= start <= horizon:
            async for it in db.interests.find({"event_id": ev["id"], "status": "voy"}):
                if await already(it["user_id"], ev["id"], "event_reminder"):
                    continue
                await create_notification(
                    it["user_id"], "event_reminder",
                    f"¡Tu plan empieza pronto! {ev['name']} en {ev['venue']} a las {t}",
                    {"event_id": ev["id"]},
                )
                sent += 1

        # 2) 'me_interesa' — nudge on the day of the event
        if ev_date == today:
            async for it in db.interests.find({"event_id": ev["id"], "status": "me_interesa"}):
                if await already(it["user_id"], ev["id"], "interested_reminder"):
                    continue
                await create_notification(
                    it["user_id"], "interested_reminder",
                    f"Hoy: {ev['name']} en {ev['venue']} — te interesaba, ¿te animas?",
                    {"event_id": ev["id"]},
                )
                sent += 1

    if sent:
        logger.info(f"Recordatorios enviados: {sent}")
    return sent


@api_router.post("/admin/trigger-reminders")
async def trigger_reminders(admin: dict = Depends(require_admin)):
    sent = await generate_event_reminders()
    return {"sent": sent}


# ---------------------------------------------------------------------------
# Stories (ephemeral 24h, friends-only)
# ---------------------------------------------------------------------------
STORY_TTL_HOURS = 24


@api_router.post("/stories")
async def create_story(
    file: UploadFile = File(...),
    caption: str = Form(""),
    event_id: str = Form(""),
    user: dict = Depends(get_current_user),
):
    ext = file.filename.split(".")[-1].lower() if "." in file.filename else "jpg"
    data = await file.read()
    ct = file.content_type or "image/jpeg"
    if not ct.startswith("image/"):
        raise HTTPException(status_code=400, detail="El archivo debe ser una imagen")
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="La imagen supera el máximo de 8MB")
    if event_id:
        ev = await db.events.find_one({"id": event_id})
        if not ev:
            raise HTTPException(status_code=404, detail="Evento no encontrado")
    path = f"{APP_NAME}/stories/{user['user_id']}/{uuid.uuid4().hex}.{ext}"
    _url = store_media(path, data, ct)
    await db.files.insert_one({
        "id": str(uuid.uuid4()),
        "storage_path": path,
        "content_type": ct,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    now = datetime.now(timezone.utc)
    story = {
        "id": str(uuid.uuid4()),
        "user_id": user["user_id"],
        "image_url": _url,
        "caption": caption.strip(),
        "event_id": event_id or None,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=STORY_TTL_HOURS)).isoformat(),
    }
    await db.stories.insert_one(story)
    story.pop("_id", None)
    return story


async def serialize_story(s: dict, viewer: dict) -> dict:
    author = await db.users.find_one({"user_id": s["user_id"]}, {"_id": 0})
    event_name = None
    if s.get("event_id"):
        ev = await db.events.find_one({"id": s["event_id"]}, {"_id": 0})
        event_name = ev["name"] if ev else None
    is_mine = s["user_id"] == viewer["user_id"]
    out = {
        **{k: v for k, v in s.items() if k != "_id"},
        "is_mine": is_mine,
        "kind": "story",
        "author": {
            "name": display_name(author) if author else "Usuario",
            "picture": author.get("picture", "") if author else "",
            "username": author["username"] if author else "",
        },
        "event_name": event_name,
    }
    if is_mine:
        reactions = []
        async for r in db.story_reactions.find({"story_id": s["id"]}, {"_id": 0}).sort("created_at", 1):
            ru = await db.users.find_one({"user_id": r["user_id"]}, {"_id": 0})
            reactions.append({
                "content": r["content"],
                "user": {"name": display_name(ru) if ru else "Usuario", "picture": ru.get("picture", "") if ru else ""},
            })
        out["reactions"] = reactions
    return out


@api_router.get("/stories")
async def list_stories(user: dict = Depends(get_current_user)):
    friend_ids = await accepted_friend_ids(user["user_id"])
    allowed = friend_ids + [user["user_id"]]
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=STORY_TTL_HOURS)).isoformat()
    out = []
    async for s in db.stories.find(
        {"user_id": {"$in": allowed}, "created_at": {"$gte": cutoff}}, {"_id": 0}
    ).sort("created_at", 1):
        out.append(await serialize_story(s, user))
    # Also surface friends' (and own) 'El Momento' captures from the last 24h as
    # ephemeral stories, so the top-of-feed bar shows the whole night.
    out.extend(await _moments_as_stories(allowed, cutoff, user))
    # Live content first (by time); "highlight" (old) moments go to the end.
    out.sort(key=lambda x: (bool(x.get("is_old")), x.get("created_at") or ""))
    return out


async def _moments_as_stories(allowed: list, cutoff: str, viewer: dict) -> list:
    caps = []
    async for c in db.captures.find(
        {"user_id": {"$in": allowed}, "created_at": {"$gte": cutoff}}, {"_id": 0}
    ).sort("created_at", 1):
        caps.append(c)
    is_old = False
    if not caps:
        # No captures in the last 24h → surface older "highlights" so the
        # Momentos row is never empty (like Instagram "Destacadas"). Respect the
        # viewer's own moment privacy: "amigos" → friends' (+own) past moments;
        # "publico" → also include past PUBLIC moments from opted-in users.
        is_old = True
        blocked = set(await blocked_relation_ids(viewer["user_id"]))
        author_ids = {a for a in allowed if a not in blocked}
        if viewer.get("moment_privacy", "amigos") == "publico":
            pub = await db.users.distinct("user_id", {"moment_privacy": "publico"})
            author_ids.update(p for p in pub if p not in blocked)
        author_ids = list(author_ids)
        if not author_ids:
            return []
        async for c in db.captures.find(
            {"user_id": {"$in": author_ids}, "created_at": {"$lt": cutoff}}, {"_id": 0}
        ).sort("created_at", -1).limit(12):
            caps.append(c)
        if not caps:
            return []
    cap_ids = [c["id"] for c in caps]
    like_counts = {}
    async for row in db.capture_reactions.aggregate([
        {"$match": {"capture_id": {"$in": cap_ids}}},
        {"$group": {"_id": "$capture_id", "n": {"$sum": 1}}},
    ]):
        like_counts[row["_id"]] = row["n"]
    my_liked = set()
    async for r in db.capture_reactions.find(
        {"capture_id": {"$in": cap_ids}, "user_id": viewer["user_id"]}, {"_id": 0, "capture_id": 1}
    ):
        my_liked.add(r["capture_id"])
    items = []
    for c in caps:
        au = await db.users.find_one({"user_id": c["user_id"]}, {"_id": 0})
        ev = await db.events.find_one({"id": c["event_id"]}, {"_id": 0}) if c.get("event_id") else None
        items.append({
            "id": c["id"],
            "user_id": c["user_id"],
            "image_url": c.get("image_url", ""),
            "created_at": c.get("created_at"),
            "event_id": c.get("event_id"),
            "event_name": ev["name"] if ev else None,
            "is_mine": c["user_id"] == viewer["user_id"],
            "kind": "moment",
            "is_old": is_old,
            "likes": like_counts.get(c["id"], 0),
            "i_liked": c["id"] in my_liked,
            "author": _msg_author(au),
        })
    return items


@api_router.get("/stories/archive")
async def stories_archive(user: dict = Depends(get_current_user)):
    """All of the user's own stories (including expired) — like an Instagram/BeReal archive."""
    out = []
    async for s in db.stories.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1):
        out.append(await serialize_story(s, user))
    return out


@api_router.post("/stories/{story_id}/react")
async def react_to_story(story_id: str, inp: ReactionInput, user: dict = Depends(get_current_user)):
    s = await db.stories.find_one({"id": story_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Historia no encontrada")
    if s["user_id"] != user["user_id"]:
        friends = await accepted_friend_ids(user["user_id"])
        if s["user_id"] not in friends:
            raise HTTPException(status_code=403, detail="No puedes reaccionar a esta historia")
    content = inp.content.strip()[:200]
    if not content:
        raise HTTPException(status_code=400, detail="Escribe algo")
    await db.story_reactions.insert_one({
        "id": str(uuid.uuid4()),
        "story_id": story_id,
        "user_id": user["user_id"],
        "content": content,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    if s["user_id"] != user["user_id"]:
        await create_notification(
            s["user_id"], "story_reaction",
            f"{display_name(user)} reaccionó a tu historia: {content}",
            {"story_id": story_id},
        )
    return {"ok": True}


@api_router.delete("/stories/{story_id}")
async def delete_story(story_id: str, user: dict = Depends(get_current_user)):
    res = await db.stories.delete_one({"id": story_id, "user_id": user["user_id"]})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Historia no encontrada")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Event chat
# ---------------------------------------------------------------------------
def _msg_author(u):
    return {"name": display_name(u) if u else "Usuario", "picture": u.get("picture", "") if u else "",
            "username": u["username"] if u else ""}


@api_router.get("/events/{event_id}/messages")
async def list_event_messages(event_id: str, user: dict = Depends(get_current_user)):
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    out = []
    async for m in db.event_messages.find({"event_id": event_id}, {"_id": 0}).sort("created_at", -1).limit(100):
        au = await db.users.find_one({"user_id": m["user_id"]}, {"_id": 0})
        out.append({**m, "author": _msg_author(au), "is_mine": m["user_id"] == user["user_id"]})
    out.reverse()
    return out


@api_router.post("/events/{event_id}/messages")
async def post_event_message(event_id: str, inp: MessageInput, user: dict = Depends(get_current_user)):
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    text = inp.text.strip()[:500]
    if not text:
        raise HTTPException(status_code=400, detail="Escribe un mensaje")
    msg = {
        "id": str(uuid.uuid4()),
        "event_id": event_id,
        "user_id": user["user_id"],
        "text": text,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.event_messages.insert_one(msg)
    msg.pop("_id", None)
    # notify people interested/going (except sender)
    participants = set()
    async for it in db.interests.find({"event_id": event_id, "status": {"$in": ["voy", "me_interesa"]}}):
        participants.add(it["user_id"])
    for pid in participants:
        if pid != user["user_id"]:
            await create_notification(
                pid, "event_message",
                f"{display_name(user)} en el chat de {ev['name']}: {text[:60]}",
                {"event_id": event_id},
            )
    return {**msg, "author": _msg_author(user), "is_mine": True}


# ---------------------------------------------------------------------------
# Weekend recap (Monday summary of your group's weekend)
# ---------------------------------------------------------------------------
async def generate_weekend_recap() -> int:
    today = datetime.now(PALMA_TZ).date()
    days_back = (today.weekday() + 1) % 7 or 7  # most recent past Sunday
    last_sunday = today - timedelta(days=days_back)
    last_monday = last_sunday - timedelta(days=6)  # whole past week (Mon→Sun)
    sent = 0

    def in_week(dstr):
        try:
            d = date.fromisoformat(dstr)
        except Exception:
            return False
        return last_monday <= d <= last_sunday

    async for u in db.users.find({}, {"_id": 0}):
        friend_ids = await accepted_friend_ids(u["user_id"])
        allowed = friend_ids + [u["user_id"]]

        my_plans = 0
        async for it in db.interests.find({"user_id": u["user_id"], "status": {"$in": ["voy", "estuve"]}}):
            ev = await db.events.find_one({"id": it["event_id"]}, {"_id": 0})
            if ev and in_week(ev["date"]):
                my_plans += 1

        group_events = set()
        async for it in db.interests.find({"user_id": {"$in": friend_ids}, "status": {"$in": ["voy", "estuve"]}}):
            ev = await db.events.find_one({"id": it["event_id"]}, {"_id": 0})
            if ev and in_week(ev["date"]):
                group_events.add(ev["id"])

        mon_iso = datetime.combine(last_monday, datetime.min.time()).replace(tzinfo=PALMA_TZ).isoformat()
        sun_iso = datetime.combine(last_sunday + timedelta(days=1), datetime.min.time()).replace(tzinfo=PALMA_TZ).isoformat()
        photos = await db.stories.count_documents({"user_id": {"$in": allowed}, "created_at": {"$gte": mon_iso, "$lte": sun_iso}})

        if my_plans + len(group_events) + photos == 0:
            continue
        week_key = last_monday.isoformat()
        if await db.notifications.find_one({"user_id": u["user_id"], "type": "weekend_recap", "data.week": week_key}):
            continue
        msg = (f"Recuerdo de la semana 🎉 Fuiste a {my_plans} plan{'es' if my_plans != 1 else ''}, "
               f"tu grupo se apuntó a {len(group_events)} y subisteis {photos} foto{'s' if photos != 1 else ''}.")
        await create_notification(u["user_id"], "weekend_recap", msg, {"week": week_key})
        sent += 1
    logger.info(f"Recuerdo de la semana enviado a {sent} usuarios")
    return sent


@api_router.post("/admin/trigger-weekend-recap")
async def trigger_weekend_recap(admin: dict = Depends(require_admin)):
    sent = await generate_weekend_recap()
    return {"sent": sent}


@api_router.get("/")
async def root():
    return {"message": "¿Quién va? API"}


# =========================================================================
# CHATS — DMs (1-on-1) + Group chats + Group management
# =========================================================================

class DMSendInput(BaseModel):
    to_user_id: str
    text: str = ""
    image_url: str = ""


class GroupCreateInput(BaseModel):
    name: str
    member_ids: List[str] = []
    picture: str = ""


class GroupUpdateInput(BaseModel):
    name: Optional[str] = None
    picture: Optional[str] = None


class GroupMemberInput(BaseModel):
    user_id: str


class GroupMessageInput(BaseModel):
    text: str = ""
    image_url: str = ""


def _dm_key(a: str, b: str) -> str:
    return "|".join(sorted([a, b]))


async def _dm_thread_summary(other_id: str, my_id: str) -> dict:
    other = await db.users.find_one({"user_id": other_id}, {"_id": 0})
    if not other:
        return None
    key = _dm_key(my_id, other_id)
    last = None
    async for m in db.dm_messages.find({"thread_key": key}, {"_id": 0}).sort("created_at", -1).limit(1):
        last = m
    unread = await db.dm_messages.count_documents({
        "thread_key": key, "to_user_id": my_id, "read": False,
    })
    return {
        "user": {"user_id": other["user_id"], "name": display_name(other),
                 "username": other.get("username", ""), "picture": other.get("picture", "")},
        "last_message": (last["text"] if (last and last.get("text")) else ("📷 Foto" if last else "")),
        "last_at": last["created_at"] if last else "",
        "unread": unread,
    }


@api_router.get("/dm/threads")
async def list_dm_threads(user: dict = Depends(get_current_user)):
    """List DM threads — one per friend, most recent first."""
    friend_ids = await accepted_friend_ids(user["user_id"])
    threads = []
    for fid in friend_ids:
        summary = await _dm_thread_summary(fid, user["user_id"])
        if summary:
            threads.append(summary)
    # Sort: unread first, then by last_at desc
    threads.sort(key=lambda t: (-t["unread"], t["last_at"] or "", ""), reverse=True)
    return threads


@api_router.get("/dm/{other_user_id}/messages")
async def get_dm_messages(other_user_id: str, user: dict = Depends(get_current_user)):
    """Get all messages between me and another user (must be friend)."""
    friend_ids = await accepted_friend_ids(user["user_id"])
    if other_user_id not in friend_ids and other_user_id != user["user_id"]:
        raise HTTPException(status_code=403, detail="Solo puedes hablar con amigos")
    key = _dm_key(user["user_id"], other_user_id)
    msgs = []
    async for m in db.dm_messages.find({"thread_key": key}, {"_id": 0}).sort("created_at", 1):
        m["is_mine"] = m["from_user_id"] == user["user_id"]
        msgs.append(m)
    # Mark received as read
    await db.dm_messages.update_many(
        {"thread_key": key, "to_user_id": user["user_id"], "read": False},
        {"$set": {"read": True}},
    )
    # Also clear the bell notifications for this conversation so it no longer
    # shows as pending (fixes: "entro al mensaje y sigue pendiente").
    await db.notifications.update_many(
        {"user_id": user["user_id"], "type": "dm",
         "data.user_id": other_user_id, "read": False},
        {"$set": {"read": True}},
    )
    return msgs


@api_router.post("/dm/send")
async def send_dm(inp: DMSendInput, user: dict = Depends(get_current_user)):
    friend_ids = await accepted_friend_ids(user["user_id"])
    if inp.to_user_id not in friend_ids:
        raise HTTPException(status_code=403, detail="Solo puedes hablar con amigos")
    if len(inp.text) > 1000:
        raise HTTPException(status_code=400, detail="Mensaje demasiado largo (máx 1000)")
    text = inp.text.strip()
    image_url = (inp.image_url or "").strip()
    if not text and not image_url:
        raise HTTPException(status_code=400, detail="Escribe un mensaje")
    msg = {
        "id": str(uuid.uuid4()),
        "thread_key": _dm_key(user["user_id"], inp.to_user_id),
        "from_user_id": user["user_id"],
        "to_user_id": inp.to_user_id,
        "text": text,
        "image_url": image_url,
        "read": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.dm_messages.insert_one(msg)
    msg.pop("_id", None)
    _preview = text[:60] if text else "📷 Foto"
    await create_notification(
        inp.to_user_id, "dm",
        f"{display_name(user)}: {_preview}",
        {"user_id": user["user_id"], "type": "dm"},
    )
    return {**msg, "is_mine": True}


@api_router.get("/dm/unread-count")
async def dm_unread_count(user: dict = Depends(get_current_user)):
    count = await db.dm_messages.count_documents({"to_user_id": user["user_id"], "read": False})
    return {"count": count}


# ---- GROUPS ----
async def _group_or_404(group_id: str, user_id: str) -> dict:
    g = await db.groups.find_one({"id": group_id}, {"_id": 0})
    if not g:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")
    if user_id not in g.get("member_ids", []):
        raise HTTPException(status_code=403, detail="No perteneces a este grupo")
    return g


def _serialize_group(g: dict, members_map: dict, viewer_id: str, last_msg: dict = None, unread: int = 0) -> dict:
    return {
        "id": g["id"],
        "name": g["name"],
        "picture": g.get("picture", ""),
        "member_ids": g.get("member_ids", []),
        "members": [
            {"user_id": mid, "name": display_name(members_map.get(mid)),
             "picture": members_map.get(mid, {}).get("picture", ""),
             "username": members_map.get(mid, {}).get("username", "")}
            for mid in g.get("member_ids", [])
        ],
        "created_by": g.get("created_by"),
        "created_at": g.get("created_at"),
        "last_message": last_msg["text"] if last_msg else "",
        "last_at": last_msg["created_at"] if last_msg else "",
        "unread": unread,
        "is_admin": g.get("created_by") == viewer_id,
    }


@api_router.post("/groups")
async def create_group(inp: GroupCreateInput, user: dict = Depends(get_current_user)):
    name = inp.name.strip()[:60]
    if not name:
        raise HTTPException(status_code=400, detail="Escribe un nombre")
    friend_ids = set(await accepted_friend_ids(user["user_id"]))
    invalid = [mid for mid in inp.member_ids if mid != user["user_id"] and mid not in friend_ids]
    if invalid:
        raise HTTPException(status_code=400, detail="Solo puedes añadir amigos")
    members = list(set([user["user_id"]] + list(inp.member_ids)))
    g = {
        "id": str(uuid.uuid4()),
        "name": name,
        "picture": inp.picture,
        "member_ids": members,
        "created_by": user["user_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.groups.insert_one(g)
    g.pop("_id", None)
    # Notify members
    for mid in members:
        if mid != user["user_id"]:
            await create_notification(
                mid, "group_invite",
                f"{display_name(user)} te añadió al grupo '{name}'",
                {"group_id": g["id"]},
            )
    return g


@api_router.get("/groups")
async def list_groups(user: dict = Depends(get_current_user)):
    groups = []
    async for g in db.groups.find({"member_ids": user["user_id"]}, {"_id": 0}):
        groups.append(g)
    if not groups:
        return []
    # Preload members
    all_ids = set()
    for g in groups:
        all_ids.update(g.get("member_ids", []))
    members_map = {}
    async for u in db.users.find({"user_id": {"$in": list(all_ids)}}, {"_id": 0}):
        members_map[u["user_id"]] = u
    # Preload last message + unread per group
    out = []
    for g in groups:
        last = None
        async for m in db.group_messages.find({"group_id": g["id"]}, {"_id": 0}).sort("created_at", -1).limit(1):
            last = m
        unread = await db.group_messages.count_documents({
            "group_id": g["id"],
            "read_by": {"$nin": [user["user_id"]]},
            "user_id": {"$ne": user["user_id"]},
        })
        out.append(_serialize_group(g, members_map, user["user_id"], last, unread))
    out.sort(key=lambda x: x["last_at"] or x["created_at"], reverse=True)
    return out


@api_router.get("/groups/{group_id}")
async def get_group(group_id: str, user: dict = Depends(get_current_user)):
    g = await _group_or_404(group_id, user["user_id"])
    members_map = {}
    async for u in db.users.find({"user_id": {"$in": g.get("member_ids", [])}}, {"_id": 0}):
        members_map[u["user_id"]] = u
    return _serialize_group(g, members_map, user["user_id"])


@api_router.put("/groups/{group_id}")
async def update_group(group_id: str, inp: GroupUpdateInput, user: dict = Depends(get_current_user)):
    g = await _group_or_404(group_id, user["user_id"])
    if g.get("created_by") != user["user_id"]:
        raise HTTPException(status_code=403, detail="Solo el creador puede editar el grupo")
    updates = {}
    if inp.name is not None:
        updates["name"] = inp.name.strip()[:60]
    if inp.picture is not None:
        updates["picture"] = inp.picture
    if updates:
        await db.groups.update_one({"id": group_id}, {"$set": updates})
    return {"ok": True}


@api_router.post("/groups/{group_id}/add-member")
async def add_group_member(group_id: str, inp: GroupMemberInput, user: dict = Depends(get_current_user)):
    g = await _group_or_404(group_id, user["user_id"])
    friend_ids = await accepted_friend_ids(user["user_id"])
    if inp.user_id not in friend_ids:
        raise HTTPException(status_code=400, detail="Solo puedes añadir amigos")
    if inp.user_id in g.get("member_ids", []):
        return {"ok": True}
    await db.groups.update_one({"id": group_id}, {"$addToSet": {"member_ids": inp.user_id}})
    await create_notification(
        inp.user_id, "group_invite",
        f"{display_name(user)} te añadió al grupo '{g['name']}'",
        {"group_id": group_id},
    )
    return {"ok": True}


@api_router.post("/groups/{group_id}/leave")
async def leave_group(group_id: str, user: dict = Depends(get_current_user)):
    g = await _group_or_404(group_id, user["user_id"])
    await db.groups.update_one({"id": group_id}, {"$pull": {"member_ids": user["user_id"]}})
    # If empty, delete the group
    remaining = await db.groups.find_one({"id": group_id}, {"_id": 0})
    if remaining and not remaining.get("member_ids"):
        await db.groups.delete_one({"id": group_id})
        await db.group_messages.delete_many({"group_id": group_id})
    return {"ok": True}


@api_router.delete("/groups/{group_id}/members/{member_id}")
async def kick_group_member(group_id: str, member_id: str, user: dict = Depends(get_current_user)):
    g = await _group_or_404(group_id, user["user_id"])
    if g.get("created_by") != user["user_id"]:
        raise HTTPException(status_code=403, detail="Solo el creador puede expulsar miembros")
    await db.groups.update_one({"id": group_id}, {"$pull": {"member_ids": member_id}})
    return {"ok": True}


@api_router.get("/groups/{group_id}/messages")
async def list_group_messages(group_id: str, user: dict = Depends(get_current_user)):
    await _group_or_404(group_id, user["user_id"])
    msgs = []
    async for m in db.group_messages.find({"group_id": group_id}, {"_id": 0}).sort("created_at", 1).limit(300):
        au = await db.users.find_one({"user_id": m["user_id"]}, {"_id": 0})
        m["author"] = _msg_author(au)
        m["is_mine"] = m["user_id"] == user["user_id"]
        msgs.append(m)
    # Mark as read
    await db.group_messages.update_many(
        {"group_id": group_id, "read_by": {"$nin": [user["user_id"]]}},
        {"$addToSet": {"read_by": user["user_id"]}},
    )
    return msgs


@api_router.post("/groups/{group_id}/messages")
async def send_group_message(group_id: str, inp: GroupMessageInput, user: dict = Depends(get_current_user)):
    g = await _group_or_404(group_id, user["user_id"])
    text = inp.text.strip()
    image_url = (inp.image_url or "").strip()
    if len(text) > 1000:
        raise HTTPException(status_code=400, detail="Mensaje demasiado largo (máx 1000)")
    if not text and not image_url:
        raise HTTPException(status_code=400, detail="Escribe algo")
    msg = {
        "id": str(uuid.uuid4()),
        "group_id": group_id,
        "user_id": user["user_id"],
        "text": text,
        "image_url": image_url,
        "read_by": [user["user_id"]],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.group_messages.insert_one(msg)
    msg.pop("_id", None)
    _preview = text[:60] if text else "📷 Foto"
    for mid in g.get("member_ids", []):
        if mid != user["user_id"]:
            await create_notification(
                mid, "group_message",
                f"{g['name']} · {display_name(user)}: {_preview}",
                {"group_id": group_id, "type": "group_message"},
            )
    return {**msg, "author": _msg_author(user), "is_mine": True}


# =========================================================================
# GROUP PHOTO — when 3+ members of a group are going to the same party
# =========================================================================

@api_router.get("/groups/{group_id}/photo-op")
async def group_photo_op(group_id: str, user: dict = Depends(get_current_user)):
    """Detects parties where 3+ members of this group marked 'voy'."""
    g = await _group_or_404(group_id, user["user_id"])
    member_ids = g.get("member_ids", [])
    today = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
    counts: dict = {}
    async for it in db.interests.find({"user_id": {"$in": member_ids}, "status": "voy"}):
        counts.setdefault(it["event_id"], set()).add(it["user_id"])
    ops = []
    for eid, uids in counts.items():
        if len(uids) < 3:
            continue
        ev = await db.events.find_one({"id": eid}, {"_id": 0})
        if not ev or ev.get("date", "") < today:
            continue
        members_going = []
        async for u in db.users.find({"user_id": {"$in": list(uids)}}, {"_id": 0}):
            members_going.append(_msg_author(u))
        photos_count = await db.group_photos.count_documents({"group_id": group_id, "event_id": eid})
        mine = await db.group_photos.find_one({"group_id": group_id, "event_id": eid, "user_id": user["user_id"]})
        ops.append({
            "event_id": eid,
            "event_name": ev["name"],
            "venue": ev.get("venue", ""),
            "date": ev["date"],
            "time": ev.get("time", ""),
            "count": len(uids),
            "members_going": members_going,
            "photos_count": photos_count,
            "i_uploaded": bool(mine),
        })
    ops.sort(key=lambda x: (x["date"], x.get("time", "")))
    return {"active": len(ops) > 0, "ops": ops}


@api_router.post("/groups/{group_id}/photo")
async def group_photo_upload(
    group_id: str,
    event_id: str = Form(...),
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    g = await _group_or_404(group_id, user["user_id"])
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    ct = file.content_type or "image/jpeg"
    if not ct.startswith("image/"):
        raise HTTPException(status_code=400, detail="Solo fotos")
    data = await file.read()
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Máximo 25MB")
    ext = file.filename.split(".")[-1].lower() if file.filename and "." in file.filename else "jpg"
    path = f"{APP_NAME}/group_photos/{group_id}/{uuid.uuid4().hex}.{ext}"
    _url = store_media(path, data, ct)
    await db.files.insert_one({
        "id": str(uuid.uuid4()),
        "storage_path": path,
        "content_type": ct,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    photo = {
        "id": str(uuid.uuid4()),
        "group_id": group_id,
        "event_id": event_id,
        "user_id": user["user_id"],
        "image_url": _url,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.group_photos.insert_one(photo)
    photo.pop("_id", None)
    # Post it into the group chat as an image message
    msg = {
        "id": str(uuid.uuid4()),
        "group_id": group_id,
        "user_id": user["user_id"],
        "text": f"📸 Foto de grupo en {ev['name']}",
        "image_url": photo["image_url"],
        "read_by": [user["user_id"]],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.group_messages.insert_one(msg)
    for mid in g.get("member_ids", []):
        if mid != user["user_id"]:
            await create_notification(
                mid, "group_message",
                f"📸 {display_name(user)} subió la foto de grupo de {ev['name']}",
                {"group_id": group_id, "type": "group_photo"},
            )
    return {**photo, "author": _msg_author(user)}


@api_router.get("/groups/{group_id}/photos")
async def group_photos_list(group_id: str, event_id: str = Query(None), user: dict = Depends(get_current_user)):
    await _group_or_404(group_id, user["user_id"])
    q = {"group_id": group_id}
    if event_id:
        q["event_id"] = event_id
    out = []
    async for p in db.group_photos.find(q, {"_id": 0}).sort("created_at", -1):
        u = await db.users.find_one({"user_id": p["user_id"]}, {"_id": 0})
        p["author"] = _msg_author(u)
        p["is_mine"] = p["user_id"] == user["user_id"]
        out.append(p)
    return out



# =========================================================================
# ALBUM — shared multimedia per event (photos + videos)
# =========================================================================

async def _can_access_album(event_id: str, user_id: str) -> bool:
    """User can upload to the album if they have any interest (voy, me_interesa, estuve)."""
    it = await db.interests.find_one({"event_id": event_id, "user_id": user_id})
    return it is not None


def _album_sharing_fields(a: dict) -> dict:
    return {
        "shared": bool(a.get("shared")),
        "shared_all_friends": bool(a.get("shared_all_friends")),
        "shared_with_users": a.get("shared_with_users", []) or [],
        "shared_with_groups": a.get("shared_with_groups", []) or [],
    }


async def _album_visible_to(a: dict, viewer_id: str, friend_ids: List[str], my_group_ids: List[str]) -> bool:
    """Whether a shared upload owned by someone else is visible to viewer."""
    if not a.get("shared"):
        return False
    if viewer_id in (a.get("shared_with_users") or []):
        return True
    if set(a.get("shared_with_groups") or []) & set(my_group_ids):
        return True
    if a.get("shared_all_friends") and a["user_id"] in friend_ids:
        return True
    return False


@api_router.post("/events/{event_id}/album/upload")
async def album_upload(event_id: str, files: List[UploadFile] = File(...), user: dict = Depends(get_current_user)):
    """Upload one OR many photos/videos at once to the event album (private by default)."""
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    if not await _can_access_album(event_id, user["user_id"]):
        raise HTTPException(status_code=403, detail="Solo asistentes al evento pueden subir")
    if not files:
        raise HTTPException(status_code=400, detail="No hay archivos")
    if len(files) > 30:
        raise HTTPException(status_code=400, detail="Máximo 30 archivos por subida")
    results = []
    for file in files:
        data = await file.read()
        if len(data) > 50 * 1024 * 1024:  # 50MB max
            raise HTTPException(status_code=400, detail="Máximo 50MB por archivo")
        ct = file.content_type or "application/octet-stream"
        is_video = ct.startswith("video/")
        is_image = ct.startswith("image/")
        if not (is_video or is_image):
            raise HTTPException(status_code=400, detail="Solo fotos o vídeos")
        ext = file.filename.split(".")[-1].lower() if (file.filename and "." in file.filename) else ("mp4" if is_video else "jpg")
        path = f"{APP_NAME}/albums/{event_id}/{uuid.uuid4().hex}.{ext}"
        _url = store_media(path, data, ct)
        await db.files.insert_one({
            "id": str(uuid.uuid4()),
            "storage_path": path,
            "content_type": ct,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        upload = {
            "id": str(uuid.uuid4()),
            "event_id": event_id,
            "user_id": user["user_id"],
            "media_url": _url,
            "media_type": "video" if is_video else "image",
            "created_at": datetime.now(timezone.utc).isoformat(),
            # Private by default — the owner shares explicitly afterwards.
            "shared": False,
            "shared_all_friends": False,
            "shared_with_users": [],
            "shared_with_groups": [],
        }
        await db.album_uploads.insert_one(upload)
        upload.pop("_id", None)
        results.append(upload)
    # Backwards-compatible: return the single object if only one file was sent.
    if len(results) == 1:
        return results[0]
    return {"uploads": results, "count": len(results)}


@api_router.get("/events/{event_id}/album")
async def album_list(event_id: str, user: dict = Depends(get_current_user)):
    """Returns two buckets:
    - mine: every upload of mine for this event (private album), with its sharing state.
    - shared: the combined album = uploads shared *with me* by others + my own shared ones.
    """
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    uid = user["user_id"]
    friend_ids = await accepted_friend_ids(uid)
    my_group_ids = [g["id"] async for g in db.groups.find({"member_ids": uid}, {"_id": 0, "id": 1})]

    # cache authors to avoid N+1
    author_cache: dict = {}

    async def _decorate(a):
        au = author_cache.get(a["user_id"])
        if au is None:
            au = await db.users.find_one({"user_id": a["user_id"]}, {"_id": 0})
            author_cache[a["user_id"]] = au
        a["author"] = _msg_author(au)
        a["is_mine"] = a["user_id"] == uid
        a.update(_album_sharing_fields(a))
        return a

    mine, shared = [], []
    async for a in db.album_uploads.find({"event_id": event_id}, {"_id": 0}).sort("created_at", -1):
        if a["user_id"] == uid:
            await _decorate(a)
            mine.append(a)
            if a.get("shared"):
                shared.append(a)
        elif await _album_visible_to(a, uid, friend_ids, my_group_ids):
            await _decorate(a)
            shared.append(a)
    shared.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {
        "event": {"id": ev["id"], "name": ev["name"], "date": ev["date"], "venue": ev["venue"]},
        "mine": mine,
        "shared": shared,
        "can_upload": await _can_access_album(event_id, uid),
        "total_mine": len(mine),
        "total_shared": len(shared),
    }


class AlbumShareInput(BaseModel):
    user_ids: List[str] = []
    group_ids: List[str] = []
    all_friends: bool = False


@api_router.post("/events/{event_id}/album/{upload_id}/share")
async def album_share(event_id: str, upload_id: str, inp: AlbumShareInput, user: dict = Depends(get_current_user)):
    a = await db.album_uploads.find_one({"id": upload_id, "event_id": event_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="No encontrado")
    if a["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Solo puedes compartir tus propias fotos")
    friend_ids = await accepted_friend_ids(user["user_id"])
    # sanitize: only share with actual friends
    clean_users = [u for u in inp.user_ids if u in friend_ids]
    # only groups I belong to
    valid_groups = [g["id"] async for g in db.groups.find(
        {"id": {"$in": inp.group_ids}, "member_ids": user["user_id"]}, {"_id": 0, "id": 1})]
    is_shared = bool(clean_users or valid_groups or inp.all_friends)
    prev_users = set(a.get("shared_with_users") or [])
    await db.album_uploads.update_one({"id": upload_id}, {"$set": {
        "shared": is_shared,
        "shared_all_friends": bool(inp.all_friends),
        "shared_with_users": clean_users,
        "shared_with_groups": valid_groups,
    }})
    # notify newly-added recipients
    try:
        ev = await db.events.find_one({"id": event_id}, {"_id": 0})
        recipients = set()
        if inp.all_friends:
            recipients.update(friend_ids)
        recipients.update(clean_users)
        for gid in valid_groups:
            g = await db.groups.find_one({"id": gid}, {"_id": 0, "member_ids": 1})
            if g:
                recipients.update(m for m in g.get("member_ids", []) if m != user["user_id"])
        new_recipients = recipients - prev_users - {user["user_id"]}
        for rid in list(new_recipients)[:60]:
            await create_notification(
                rid, "album_shared",
                f"📸 {display_name(user)} compartió una foto de {ev['name'] if ev else 'una fiesta'}",
                {"event_id": event_id, "type": "album_shared"},
            )
    except Exception as e:
        logger.warning(f"album share notify failed: {e}")
    a.update({"shared": is_shared, "shared_all_friends": bool(inp.all_friends),
              "shared_with_users": clean_users, "shared_with_groups": valid_groups})
    return {"ok": True, **_album_sharing_fields(a)}


@api_router.post("/events/{event_id}/album/{upload_id}/unshare")
async def album_unshare(event_id: str, upload_id: str, user: dict = Depends(get_current_user)):
    a = await db.album_uploads.find_one({"id": upload_id, "event_id": event_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="No encontrado")
    if a["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Solo puedes gestionar tus propias fotos")
    await db.album_uploads.update_one({"id": upload_id}, {"$set": {
        "shared": False, "shared_all_friends": False,
        "shared_with_users": [], "shared_with_groups": [],
    }})
    return {"ok": True, "shared": False}


class AlbumShareBatchInput(BaseModel):
    upload_ids: List[str] = []
    user_ids: List[str] = []
    group_ids: List[str] = []
    all_friends: bool = False


@api_router.post("/events/{event_id}/album/share-batch")
async def album_share_batch(event_id: str, inp: AlbumShareBatchInput, user: dict = Depends(get_current_user)):
    """Share MANY of my uploads at once with the same audience (no one-by-one)."""
    if not inp.upload_ids:
        raise HTTPException(status_code=400, detail="Selecciona al menos una foto")
    friend_ids = await accepted_friend_ids(user["user_id"])
    clean_users = [u for u in inp.user_ids if u in friend_ids]
    valid_groups = [g["id"] async for g in db.groups.find(
        {"id": {"$in": inp.group_ids}, "member_ids": user["user_id"]}, {"_id": 0, "id": 1})]
    is_shared = bool(clean_users or valid_groups or inp.all_friends)
    if not is_shared:
        raise HTTPException(status_code=400, detail="Elige con quién compartir")
    # only my own uploads for this event
    mine = [a async for a in db.album_uploads.find(
        {"id": {"$in": inp.upload_ids}, "event_id": event_id, "user_id": user["user_id"]}, {"_id": 0})]
    if not mine:
        raise HTTPException(status_code=404, detail="No se encontraron tus fotos")
    prev_recipients = set()
    for a in mine:
        prev_recipients.update(a.get("shared_with_users") or [])
    await db.album_uploads.update_many(
        {"id": {"$in": [a["id"] for a in mine]}, "user_id": user["user_id"]},
        {"$set": {
            "shared": is_shared,
            "shared_all_friends": bool(inp.all_friends),
            "shared_with_users": clean_users,
            "shared_with_groups": valid_groups,
        }},
    )
    # notify newly-added recipients ONCE (not per photo)
    try:
        ev = await db.events.find_one({"id": event_id}, {"_id": 0})
        recipients = set(clean_users)
        if inp.all_friends:
            recipients.update(friend_ids)
        for gid in valid_groups:
            g = await db.groups.find_one({"id": gid}, {"_id": 0, "member_ids": 1})
            if g:
                recipients.update(m for m in g.get("member_ids", []) if m != user["user_id"])
        new_recipients = recipients - prev_recipients - {user["user_id"]}
        n = len(mine)
        for rid in list(new_recipients)[:60]:
            await create_notification(
                rid, "album_shared",
                f"📸 {display_name(user)} compartió {n} foto{'s' if n != 1 else ''} de {ev['name'] if ev else 'una fiesta'}",
                {"event_id": event_id, "type": "album_shared"},
            )
    except Exception as e:
        logger.warning(f"album share-batch notify failed: {e}")
    return {"ok": True, "shared_count": len(mine)}


@api_router.post("/chat/upload")
async def chat_media_upload(files: List[UploadFile] = File(...), user: dict = Depends(get_current_user)):
    """Upload one or many images for use inside a DM / group chat message.
    Returns a list of {media_url, media_type}. Kept separate from the album."""
    if not files:
        raise HTTPException(status_code=400, detail="No hay archivos")
    if len(files) > 10:
        raise HTTPException(status_code=400, detail="Máximo 10 fotos por vez")
    out = []
    for file in files:
        data = await file.read()
        if len(data) > 25 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Máximo 25MB por foto")
        ct = file.content_type or "application/octet-stream"
        if not ct.startswith("image/"):
            raise HTTPException(status_code=400, detail="Solo fotos")
        ext = file.filename.split(".")[-1].lower() if (file.filename and "." in file.filename) else "jpg"
        path = f"{APP_NAME}/chat/{user['user_id']}/{uuid.uuid4().hex}.{ext}"
        _url = store_media(path, data, ct)
        out.append({"media_url": _url, "media_type": "image"})
    return {"uploads": out}


@api_router.delete("/events/{event_id}/album/{upload_id}")
async def album_delete(event_id: str, upload_id: str, user: dict = Depends(get_current_user)):
    a = await db.album_uploads.find_one({"id": upload_id, "event_id": event_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="No encontrado")
    if a["user_id"] != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Solo puedes borrar tus propias subidas")
    await db.album_uploads.delete_one({"id": upload_id})
    return {"ok": True}


# =========================================================================
# CAPTURA DEL MOMENTO (like BeReal but branded as "El Momento")
# =========================================================================
# A random 2-hour prompt window per event; users who are "going" get notified,
# and captures within 2 minutes of the prompt count as "on time" (extra points).

class MomentPromptInput(BaseModel):
    event_id: str


@api_router.get("/events/{event_id}/moment/status")
async def moment_status(event_id: str, user: dict = Depends(get_current_user)):
    """Get info about the current 'moment' prompt for an event."""
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    prompt = await db.moment_prompts.find_one({"event_id": event_id}, {"_id": 0})
    my_capture = await db.captures.find_one({"event_id": event_id, "user_id": user["user_id"]}, {"_id": 0})
    return {
        "prompt": prompt,  # {sent_at, expires_at, on_time_deadline}
        "my_capture": my_capture,
        "can_capture": bool(prompt),
    }


@api_router.get("/me/active-moment")
async def my_active_moment(user: dict = Depends(get_current_user)):
    """Returns the most relevant *pending* moment for the current user:
    an event they marked interest in, that has a non-expired prompt, and which
    they have NOT captured yet. Powers the blocking modal + home pill + /momento.
    """
    uid = user["user_id"]
    now = datetime.now(timezone.utc)
    # events the user cares about
    my_event_ids = [it["event_id"] async for it in db.interests.find(
        {"user_id": uid, "status": {"$in": ["voy", "estuve", "me_interesa"]}},
        {"_id": 0, "event_id": 1})]
    if not my_event_ids:
        return {"active": False}
    # already captured -> exclude
    captured_ids = {c["event_id"] async for c in db.captures.find(
        {"user_id": uid, "event_id": {"$in": my_event_ids}}, {"_id": 0, "event_id": 1})}
    best = None
    async for p in db.moment_prompts.find(
        {"event_id": {"$in": my_event_ids}}, {"_id": 0}).sort("sent_at", -1):
        if p["event_id"] in captured_ids:
            continue
        try:
            exp = datetime.fromisoformat(p["expires_at"].replace("Z", "+00:00"))
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if exp < now:
            continue
        best = p
        break
    if not best:
        return {"active": False}
    ev = await db.events.find_one({"id": best["event_id"]}, {"_id": 0})
    if not ev:
        return {"active": False}
    try:
        deadline = datetime.fromisoformat(best["on_time_deadline"].replace("Z", "+00:00"))
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        on_time = now <= deadline
    except Exception:
        on_time = False
    # FOMO: how many friends already captured this moment
    friend_ids = await accepted_friend_ids(uid)
    friends_captured = 0
    if friend_ids:
        friends_captured = await db.captures.count_documents(
            {"event_id": best["event_id"], "user_id": {"$in": friend_ids}})
    return {
        "active": True,
        "event_id": ev["id"],
        "event_name": ev["name"],
        "venue": ev.get("venue", ""),
        "prompt": best,
        "on_time": on_time,
        "friends_captured": friends_captured,
    }



@api_router.post("/admin/events/{event_id}/moment/trigger")
async def admin_trigger_moment(event_id: str, admin: dict = Depends(require_admin)):
    """Admin triggers the moment prompt manually. Sends push to all 'voy' users."""
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    # Un-cancel it in case it had been paused, since the admin is explicitly firing it.
    if ev.get("moment_cancelled"):
        await db.events.update_one({"id": event_id}, {"$set": {"moment_cancelled": False}})
    result = await _fire_moment(ev, triggered_by=admin["user_id"])
    return {"prompt": result["prompt"], "notified": result["notified"]}


# =========================================================================
# ADMIN: EL MOMENTO — daily scheduling controls
# =========================================================================
def _random_moment_time(event_date_iso: str) -> str:
    """Generate a random datetime (ISO) between 01:00 and 05:59 on the night
    of the event (i.e., calendar day after event_date)."""
    ed = date.fromisoformat(event_date_iso)
    party_night = ed + timedelta(days=1)
    hour = 1 + secrets.randbelow(5)
    minute = secrets.randbelow(60)
    return datetime.combine(party_night, dtime(hour, minute), tzinfo=ZoneInfo("Europe/Madrid")).isoformat()


async def _moment_event_view(ev: dict) -> dict:
    """Return a compact view of an event for the admin moment panel."""
    prompt = await db.moment_prompts.find_one({"event_id": ev["id"]}, {"_id": 0})
    voy_count = await db.interests.count_documents({"event_id": ev["id"], "status": "voy"})
    captures_count = await db.captures.count_documents({"event_id": ev["id"]})
    return {
        "id": ev["id"],
        "name": ev["name"],
        "venue": ev.get("venue", ""),
        "date": ev["date"],
        "time": ev.get("time", ""),
        "planned_moment_at": ev.get("planned_moment_at"),
        "moment_cancelled": bool(ev.get("moment_cancelled")),
        "has_fired": bool(prompt),
        "fired_at": prompt.get("sent_at") if prompt else None,
        "voy_count": voy_count,
        "captures_count": captures_count,
    }


@api_router.get("/admin/moments")
async def admin_moments_list(scope: str = Query("all"), admin: dict = Depends(require_admin)):
    """List events for the "moment window": yesterday + today + tomorrow (yesterday
    covers after-midnight parties). Ordered by planned_moment_at (unscheduled first).

    scope:
      - "tonight": only the night currently in progress (before 06:00 that is
        still the previous calendar day's night). Loads fast → shown first.
      - "later":  the remaining days in the window (the following nights).
      - "all"  :  everything (backward compatible).
    """
    now = datetime.now(ZoneInfo("Europe/Madrid"))
    today = now.date().isoformat()
    yesterday = (now.date() - timedelta(days=1)).isoformat()
    tomorrow = (now.date() + timedelta(days=1)).isoformat()
    window = [yesterday, today, tomorrow]
    tonight_date = yesterday if now.hour < 6 else today
    if scope == "tonight":
        dates = [tonight_date]
    elif scope == "later":
        dates = [d for d in window if d != tonight_date]
    else:
        dates = window
    out = []
    async for ev in db.events.find(
        {"date": {"$in": dates}}, {"_id": 0}
    ).sort("date", 1):
        out.append(await _moment_event_view(ev))
    # Sort: no time first, then earliest planned time
    out.sort(key=lambda e: (e["planned_moment_at"] or "9999"))
    return out


class MomentTimeInput(BaseModel):
    hour: int
    minute: int = 0


def _validate_moment_time(hour: int, minute: int):
    if not (1 <= hour <= 5):
        raise HTTPException(status_code=400, detail="La hora debe estar entre 01 y 05 (h)")
    if hour == 5 and minute > 59:
        raise HTTPException(status_code=400, detail="Máximo permitido: 05:59")
    if not (0 <= minute <= 59):
        raise HTTPException(status_code=400, detail="Minuto inválido")


@api_router.put("/admin/moments/{event_id}")
async def admin_moment_set_time(event_id: str, inp: MomentTimeInput, admin: dict = Depends(require_admin)):
    """Set a specific planned time for the moment. Must be 01:00-05:59."""
    _validate_moment_time(inp.hour, inp.minute)
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    party_night = date.fromisoformat(ev["date"]) + timedelta(days=1)
    planned_dt = datetime.combine(party_night, dtime(inp.hour, inp.minute), tzinfo=ZoneInfo("Europe/Madrid"))
    await db.events.update_one(
        {"id": event_id},
        {"$set": {"planned_moment_at": planned_dt.isoformat(), "moment_cancelled": False}},
    )
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    return await _moment_event_view(ev)


@api_router.post("/admin/moments/{event_id}/randomize")
async def admin_moment_randomize(event_id: str, admin: dict = Depends(require_admin)):
    """Assign a new random 01:00-05:59 time to a single event."""
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    planned = _random_moment_time(ev["date"])
    await db.events.update_one(
        {"id": event_id},
        {"$set": {"planned_moment_at": planned, "moment_cancelled": False}},
    )
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    return await _moment_event_view(ev)


@api_router.post("/admin/moments/randomize-all")
async def admin_moment_randomize_all(scope: str = Query("all"), admin: dict = Depends(require_admin)):
    """Assign a random 01:00-05:59 time to events in the current window that
    haven't fired yet.

    scope:
      - "tonight": only the night in progress (before 06:00 = previous day's night).
      - "later":   the remaining days in the window.
      - "all"  :   the whole window (yesterday, today, tomorrow). Default.
    """
    now = datetime.now(ZoneInfo("Europe/Madrid"))
    today = now.date().isoformat()
    yesterday = (now.date() - timedelta(days=1)).isoformat()
    tomorrow = (now.date() + timedelta(days=1)).isoformat()
    window = [yesterday, today, tomorrow]
    tonight_date = yesterday if now.hour < 6 else today
    if scope == "tonight":
        dates = [tonight_date]
    elif scope == "later":
        dates = [d for d in window if d != tonight_date]
    else:
        dates = window
    count = 0
    async for ev in db.events.find({"date": {"$in": dates}}, {"_id": 0}):
        # Skip if already fired
        existing = await db.moment_prompts.find_one({"event_id": ev["id"]})
        if existing:
            continue
        planned = _random_moment_time(ev["date"])
        await db.events.update_one(
            {"id": ev["id"]},
            {"$set": {"planned_moment_at": planned, "moment_cancelled": False}},
        )
        count += 1
    return {"updated": count}


@api_router.post("/admin/moments/{event_id}/cancel")
async def admin_moment_cancel(event_id: str, admin: dict = Depends(require_admin)):
    """Pause/cancel the moment for this event tonight — it won't be triggered."""
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    await db.events.update_one({"id": event_id}, {"$set": {"moment_cancelled": True}})
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    return await _moment_event_view(ev)


@api_router.post("/admin/moments/{event_id}/uncancel")
async def admin_moment_uncancel(event_id: str, admin: dict = Depends(require_admin)):
    """Undo a previous pause — the moment will be triggered at planned_moment_at."""
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    await db.events.update_one({"id": event_id}, {"$set": {"moment_cancelled": False}})
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    return await _moment_event_view(ev)


@api_router.post("/events/{event_id}/moment/upload")
async def moment_upload(event_id: str, file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    prompt = await db.moment_prompts.find_one({"event_id": event_id}, {"_id": 0})
    if not prompt:
        raise HTTPException(status_code=400, detail="No hay un momento activo para este evento")
    # Only 1 capture per user per event
    existing = await db.captures.find_one({"event_id": event_id, "user_id": user["user_id"]})
    if existing:
        raise HTTPException(status_code=400, detail="Ya subiste tu momento")
    ct = file.content_type or "image/jpeg"
    if not ct.startswith("image/"):
        raise HTTPException(status_code=400, detail="Solo fotos")
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Máximo 10MB")
    ext = file.filename.split(".")[-1].lower() if "." in file.filename else "jpg"
    path = f"{APP_NAME}/moments/{event_id}/{uuid.uuid4().hex}.{ext}"
    _url = store_media(path, data, ct)
    now = datetime.now(timezone.utc)
    deadline = datetime.fromisoformat(prompt["on_time_deadline"].replace("Z", "+00:00"))
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    on_time = now <= deadline
    capture = {
        "id": str(uuid.uuid4()),
        "event_id": event_id,
        "user_id": user["user_id"],
        "image_url": _url,
        "on_time": on_time,
        "seconds_late": max(0, int((now - deadline).total_seconds())),
        "created_at": now.isoformat(),
    }
    await db.captures.insert_one(capture)
    capture.pop("_id", None)
    # Notify friends who are also going/attended this event (or all friends if it's a live moment)
    try:
        friend_ids = await accepted_friend_ids(user["user_id"])
        if friend_ids:
            # Prefer friends who are on this same event; if none, ping all friends
            same_event_friends = []
            async for it in db.interests.find({
                "event_id": event_id,
                "user_id": {"$in": friend_ids},
                "status": {"$in": ["voy", "estuve", "me_interesa"]},
            }):
                same_event_friends.append(it["user_id"])
            targets = same_event_friends or friend_ids[:30]  # cap at 30 to avoid spam
            for fid in targets:
                await create_notification(
                    fid, "moment_friend",
                    f"⚡ {display_name(user)} subió su momento en {ev['name']}. ¡No te lo pierdas!",
                    {"event_id": event_id, "type": "moment_friend"},
                )
    except Exception as e:
        logger.warning(f"Moment friend notify failed: {e}")
    return capture


@api_router.get("/events/{event_id}/moment/gallery")
async def moment_gallery(event_id: str, user: dict = Depends(get_current_user)):
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    # Must have uploaded or be attendee
    my_capture = await db.captures.find_one({"event_id": event_id, "user_id": user["user_id"]}, {"_id": 0})
    if not my_capture:
        raise HTTPException(status_code=403, detail="Debes subir tu momento para ver los de los demás")
    # Only show friends' captures + own (excluding anyone blocked either way)
    friend_ids = await accepted_friend_ids(user["user_id"])
    blocked = await blocked_relation_ids(user["user_id"])
    allowed = [fid for fid in friend_ids if fid not in blocked] + [user["user_id"]]
    items = []
    async for c in db.captures.find({"event_id": event_id, "user_id": {"$in": allowed}}, {"_id": 0}).sort("created_at", 1):
        au = await db.users.find_one({"user_id": c["user_id"]}, {"_id": 0})
        c["author"] = _msg_author(au)
        c["is_mine"] = c["user_id"] == user["user_id"]
        items.append(c)
    return items


@api_router.post("/captures/{capture_id}/like")
async def like_capture(capture_id: str, user: dict = Depends(get_current_user)):
    """Toggle a like on an 'El Momento' capture. Used by the Descubrir feed and
    the moment gallery. Returns the new like count and whether I like it now."""
    uid = user["user_id"]
    c = await db.captures.find_one({"id": capture_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Momento no encontrado")
    existing = await db.capture_reactions.find_one({"capture_id": capture_id, "user_id": uid})
    if existing:
        await db.capture_reactions.delete_one({"capture_id": capture_id, "user_id": uid})
        liked = False
    else:
        await db.capture_reactions.insert_one({
            "id": str(uuid.uuid4()),
            "capture_id": capture_id,
            "user_id": uid,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        liked = True
        if c["user_id"] != uid:
            await create_notification(
                c["user_id"], "capture_like",
                f"A {display_name(user)} le gusta tu Momento ❤️",
                {"user_id": uid, "type": "capture_like"},
            )
    count = await db.capture_reactions.count_documents({"capture_id": capture_id})
    return {"liked": liked, "likes": count}


# =========================================================================
# CALENDAR — past events with multimedia grouped by day
# =========================================================================

@api_router.get("/me/calendar")
async def my_calendar(user: dict = Depends(get_current_user),
                      start: str = Query(""),
                      end: str = Query("")):
    """Return events grouped by day where I or my friends had activity."""
    try:
        end_d = date.fromisoformat(end) if end else datetime.now(ZoneInfo("Europe/Madrid")).date()
        start_d = date.fromisoformat(start) if start else (end_d - timedelta(days=90))
    except Exception:
        raise HTTPException(status_code=400, detail="Fechas inválidas")

    friend_ids = await accepted_friend_ids(user["user_id"])
    allowed_users = friend_ids + [user["user_id"]]

    # All interests within date range for me or friends
    days = {}  # date_iso -> {events: [], photos: [], videos: [], my_events: []}
    interests_by_event = {}
    async for it in db.interests.find({"user_id": {"$in": allowed_users},
                                        "status": {"$in": ["voy", "estuve"]}}):
        interests_by_event.setdefault(it["event_id"], []).append(it)

    for event_id, its in interests_by_event.items():
        ev = await db.events.find_one({"id": event_id}, {"_id": 0})
        if not ev:
            continue
        try:
            d = date.fromisoformat(ev["date"])
        except Exception:
            continue
        if not (start_d <= d <= end_d):
            continue
        # Album items
        album_items = []
        async for a in db.album_uploads.find({"event_id": event_id, "user_id": {"$in": allowed_users}}, {"_id": 0}):
            album_items.append(a)
        moments = []
        async for c in db.captures.find({"event_id": event_id, "user_id": {"$in": allowed_users}}, {"_id": 0}):
            moments.append(c)
        my_status = next((i["status"] for i in its if i["user_id"] == user["user_id"]), None)
        friend_names = []
        for i in its:
            if i["user_id"] == user["user_id"]:
                continue
            fu = await db.users.find_one({"user_id": i["user_id"]}, {"_id": 0, "name": 1, "picture": 1})
            if fu:
                friend_names.append({"name": display_name(fu), "picture": fu.get("picture", "")})
        key = d.isoformat()
        days.setdefault(key, {"date": key, "events": []})
        days[key]["events"].append({
            "id": ev["id"], "name": ev["name"], "venue": ev["venue"], "genre": ev.get("genre", ""),
            "image_url": ev.get("image_url", ""),
            "my_status": my_status,
            "friends": friend_names,
            "photos": [a for a in album_items if a["media_type"] == "image"],
            "videos": [a for a in album_items if a["media_type"] == "video"],
            "moments": moments,
        })

    return sorted(days.values(), key=lambda x: x["date"], reverse=True)


# =========================================================================
# TICKETS — track in-app ticket purchases (for points/badges)
# =========================================================================

class TicketPurchaseInput(BaseModel):
    event_id: str


@api_router.post("/tickets/click")
async def ticket_click(inp: TicketPurchaseInput, user: dict = Depends(get_current_user)):
    """User clicked the 'Conseguir entrada' button — record for future confirmation."""
    ev = await db.events.find_one({"id": inp.event_id}, {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    click = {
        "id": str(uuid.uuid4()),
        "user_id": user["user_id"],
        "event_id": inp.event_id,
        "confirmed": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.ticket_purchases.insert_one(click)
    return {"ok": True, "id": click["id"]}


class TicketConfirmInput(BaseModel):
    purchase_id: str
    confirmed: bool = True


@api_router.post("/admin/tickets/confirm")
async def admin_confirm_ticket(inp: TicketConfirmInput, admin: dict = Depends(require_admin)):
    """Admin confirms a ticket purchase → user gets points."""
    p = await db.ticket_purchases.find_one({"id": inp.purchase_id}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="No encontrado")
    await db.ticket_purchases.update_one(
        {"id": inp.purchase_id},
        {"$set": {
            "confirmed": inp.confirmed,
            "status": "confirmed" if inp.confirmed else "rejected",
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    if inp.confirmed:
        await create_notification(
            p["user_id"], "ticket_confirmed",
            f"¡Compra confirmada! +{ACTION_POINTS['ticket_purchase']} puntos 🎟️",
            {"event_id": p["event_id"]},
        )
    return {"ok": True}


# =========================================================================
# ADMIN — extended dashboard (activity chart + top users by points)
# =========================================================================

@api_router.get("/admin/dashboard")
async def admin_dashboard(admin: dict = Depends(require_admin)):
    """Extended admin dashboard: activity by day + top users by points."""
    today = datetime.now(ZoneInfo("Europe/Madrid")).date()
    start = today - timedelta(days=29)  # 30-day window
    activity = {d.isoformat(): {"date": d.isoformat(), "signups": 0, "voys": 0, "stories": 0, "captures": 0}
                for d in [start + timedelta(days=i) for i in range(30)]}

    async for u in db.users.find({"created_at": {"$gte": start.isoformat()}}, {"_id": 0}):
        try:
            d = datetime.fromisoformat(u["created_at"]).date().isoformat()
            if d in activity:
                activity[d]["signups"] += 1
        except Exception:
            pass

    async for it in db.interests.find({"status": "voy", "created_at": {"$gte": start.isoformat()}}, {"_id": 0}):
        try:
            d = datetime.fromisoformat(it["created_at"]).date().isoformat()
            if d in activity:
                activity[d]["voys"] += 1
        except Exception:
            pass

    async for s in db.stories.find({"created_at": {"$gte": start.isoformat()}}, {"_id": 0}):
        try:
            d = datetime.fromisoformat(s["created_at"]).date().isoformat()
            if d in activity:
                activity[d]["stories"] += 1
        except Exception:
            pass

    async for c in db.captures.find({"created_at": {"$gte": start.isoformat()}}, {"_id": 0}):
        try:
            d = datetime.fromisoformat(c["created_at"]).date().isoformat()
            if d in activity:
                activity[d]["captures"] += 1
        except Exception:
            pass

    activity_list = sorted(activity.values(), key=lambda x: x["date"])

    # Top 10 users by points (world)
    ids = []
    async for u in db.users.find({}, {"_id": 0, "user_id": 1}):
        ids.append(u["user_id"])
    top_users = await _build_ranking(ids, limit=10)

    # Groups + DMs count
    total_groups = await db.groups.count_documents({})
    total_group_msgs = await db.group_messages.count_documents({})
    total_dms = await db.dm_messages.count_documents({})
    total_album = await db.album_uploads.count_documents({})
    total_captures = await db.captures.count_documents({})
    pending_tickets = await db.ticket_purchases.count_documents({"confirmed": False})

    return {
        "activity_30d": activity_list,
        "top_users": top_users,
        "extras": {
            "groups": total_groups,
            "group_messages": total_group_msgs,
            "dms": total_dms,
            "album_items": total_album,
            "captures": total_captures,
            "pending_tickets": pending_tickets,
        },
    }


@api_router.get("/admin/tickets")
async def admin_list_tickets(admin: dict = Depends(require_admin),
                              status: str = Query("pending")):
    q = {"confirmed": False, "status": {"$ne": "rejected"}} if status == "pending" else {"confirmed": True}
    out = []
    async for p in db.ticket_purchases.find(q, {"_id": 0}).sort("created_at", -1).limit(200):
        u = await db.users.find_one({"user_id": p["user_id"]}, {"_id": 0})
        ev = await db.events.find_one({"id": p["event_id"]}, {"_id": 0})
        p["user"] = {"name": u["name"] if u else "-", "email": u.get("email", "") if u else ""}
        p["event"] = {"name": ev["name"] if ev else "-", "date": ev.get("date", "") if ev else ""}
        out.append(p)
    return out


# ---------------------------------------------------------------------------
# Startup: indexes, admin seed, sample events
# ---------------------------------------------------------------------------
async def seed_admin():
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@quienva.app")
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        await db.users.insert_one({
            "user_id": f"user_{uuid.uuid4().hex[:12]}",
            "email": admin_email,
            "username": "admin",
            "name": "Admin",
            "picture": "",
            "city": "Palma de Mallorca",
            "role": "admin",
            "auth_provider": "email",
            "password_hash": hash_password(admin_password),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("Admin creado")
    else:
        updates = {"role": "admin"}
        if not verify_password(admin_password, existing.get("password_hash", "")):
            updates["password_hash"] = hash_password(admin_password)
        await db.users.update_one({"email": admin_email}, {"$set": updates})


DEMO_EVENTS = [
    {"offset": 0, "name": "Techno Underground", "venue": "Sala Focus", "address": "C/ Bartomeu Rosselló, Palma",
     "time": "23:59", "genre": "Techno",
     "image_url": "https://images.unsplash.com/photo-1470225620780-dba8ba36b745",
     "has_commission": True, "commission_url": "https://fourvenues.com/", "more_info_url": ""},
    {"offset": 1, "name": "Reggaeton Party", "venue": "Tito's Palma", "address": "Passeig Marítim, Palma",
     "time": "00:30", "genre": "Reggaeton",
     "image_url": "https://images.unsplash.com/photo-1517983079452-bbaa6a081a6b?crop=entropy&cs=srgb&fm=jpg&q=85",
     "has_commission": True, "commission_url": "https://fourvenues.com/", "more_info_url": ""},
    {"offset": 2, "name": "Sunset Sessions", "venue": "Purobeach", "address": "Cala Estància, Palma",
     "time": "19:00", "genre": "House",
     "image_url": "https://images.unsplash.com/photo-1563784462029-e9cc28281850?crop=entropy&cs=srgb&fm=jpg&q=85",
     "has_commission": False, "commission_url": "", "more_info_url": "https://www.instagram.com/purobeach/"},
    {"offset": 4, "name": "Indie Night", "venue": "Es Gremi", "address": "Polígon Son Castelló, Palma",
     "time": "21:30", "genre": "Indie",
     "image_url": "https://images.pexels.com/photos/9534908/pexels-photo-9534908.jpeg",
     "has_commission": False, "commission_url": "", "more_info_url": "https://www.instagram.com/esgremi/"},
    {"offset": 5, "name": "Latin Fever", "venue": "Social Club", "address": "C/ dels Paraires, Palma",
     "time": "23:00", "genre": "Latino",
     "image_url": "https://images.unsplash.com/photo-1763322564752-12ce8fae2bfe?crop=entropy&cs=srgb&fm=jpg&q=85",
     "has_commission": True, "commission_url": "https://fourvenues.com/", "more_info_url": ""},
    {"offset": 8, "name": "House Marathon", "venue": "BCM Planet Dance", "address": "Magaluf, Calvià",
     "time": "23:59", "genre": "House",
     "image_url": "https://images.unsplash.com/photo-1459749411175-04bf5292ceea",
     "has_commission": True, "commission_url": "https://fourvenues.com/", "more_info_url": ""},
]


async def cleanup_demo_events():
    # Remove leftover automated-test artifacts so the feed stays clean
    await db.events.delete_many({"name": {"$regex": "^(TEST|UI5|Iteration)", "$options": "i"}})
    # Remove the previously-seeded DEMO parties (matched by their exact
    # name + venue pair) so demo data never mixes with real events — in the
    # sandbox AND in production once this deploys. Real events are untouched.
    demo_or = [{"name": d["name"], "venue": d["venue"]} for d in DEMO_EVENTS]
    if demo_or:
        res = await db.events.delete_many({"$or": demo_or})
        if res.deleted_count:
            logger.info(f"Eliminadas {res.deleted_count} fiestas demo")


async def cleanup_old_events():
    """Delete OLD parties that NOBODY engaged with (keeps the DB lean + feed fast),
    but PRESERVE every event that is someone's memory: any attendee (voy/estuve),
    a shared-album photo, or an 'El Momento' capture. Those stay FOREVER so
    'Recuerdos' / 'Fiestas pasadas' never loses a past night."""
    try:
        cutoff = (datetime.now(ZoneInfo("Europe/Madrid")).date() - timedelta(days=3)).isoformat()
        old_ids = [e["id"] async for e in db.events.find(
            {"date": {"$lt": cutoff}}, {"_id": 0, "id": 1})]
        if not old_ids:
            return {"deleted": 0, "kept": 0, "old_total": 0}
        # Events to KEEP as memories: anyone marked voy/estuve, uploaded an album
        # photo, or captured 'El Momento'. Everything else is a stale scraped event.
        keep = set()
        async for it in db.interests.find(
            {"event_id": {"$in": old_ids}, "status": {"$in": ["voy", "estuve"]}},
            {"_id": 0, "event_id": 1}):
            keep.add(it["event_id"])
        async for a in db.album_uploads.find(
            {"event_id": {"$in": old_ids}}, {"_id": 0, "event_id": 1}):
            keep.add(a["event_id"])
        async for c in db.captures.find(
            {"event_id": {"$in": old_ids}}, {"_id": 0, "event_id": 1}):
            keep.add(c["event_id"])
        to_delete = [eid for eid in old_ids if eid not in keep]
        if not to_delete:
            logger.info(f"cleanup_old_events: 0 removed (kept {len(keep)} memories)")
            return {"deleted": 0, "kept": len(keep), "old_total": len(old_ids)}
        await db.events.delete_many({"id": {"$in": to_delete}})
        for coll in (db.interests, db.tickets, db.event_follows, db.event_metrics,
                     db.event_history, db.ticket_purchases, db.album_uploads,
                     db.captures):
            try:
                await coll.delete_many({"event_id": {"$in": to_delete}})
            except Exception:
                pass
        logger.info(f"cleanup_old_events: removed {len(to_delete)} unengaged events >3 days old (kept {len(keep)} memories)")
        return {"deleted": len(to_delete), "kept": len(keep), "old_total": len(old_ids)}
    except Exception as e:
        logger.warning(f"cleanup_old_events failed: {e}")
        return {"deleted": 0, "kept": 0, "old_total": 0, "error": str(e)}


@app.on_event("startup")
async def on_startup():
    try:
        await db.users.create_index("email", unique=True)
        await db.users.create_index("username", unique=True)
        await db.users.create_index("user_id", unique=True)
        await db.users.create_index("city")
        await db.users.create_index([("city", 1), ("city_change_alerts", 1)])
        await db.users.create_index("referral_code")
        await db.users.create_index("referred_by")
        await db.users.create_index("created_at")
        await db.sessions.create_index("session_token", unique=True)
        await db.sessions.create_index("user_id")
        # Performance indices (idempotent) — speed up hot queries
        await db.interests.create_index([("user_id", 1), ("event_id", 1)])
        await db.interests.create_index([("event_id", 1), ("status", 1)])
        await db.interests.create_index("event_id")
        await db.interests.create_index("user_id")
        # CRITICAL FIX: friendships uses requester_id/addressee_id in code,
        # NOT from_user_id/to_user_id (old indexes were dead weight).
        await db.friendships.create_index([("requester_id", 1), ("addressee_id", 1)])
        await db.friendships.create_index([("addressee_id", 1), ("status", 1)])
        await db.friendships.create_index([("requester_id", 1), ("status", 1)])
        await db.friendships.create_index("id")
        await db.notifications.create_index([("user_id", 1), ("created_at", -1)])
        await db.notifications.create_index([("user_id", 1), ("read", 1)])
        await db.stories.create_index([("user_id", 1), ("created_at", -1)])
        await db.stories.create_index("expires_at")
        await db.dm_messages.create_index([("thread_key", 1), ("created_at", 1)])
        await db.dm_messages.create_index([("to_user_id", 1), ("read", 1)])
        await db.group_messages.create_index([("group_id", 1), ("created_at", 1)])
        await db.groups.create_index("member_ids")
        await db.captures.create_index([("event_id", 1), ("user_id", 1)])
        await db.captures.create_index("user_id")
        await db.capture_reactions.create_index([("capture_id", 1), ("user_id", 1)], unique=True)
        await db.capture_reactions.create_index("capture_id")
        await db.album_uploads.create_index([("event_id", 1), ("created_at", -1)])
        await db.album_uploads.create_index("user_id")
        # Compound index for the feed's main query (city + date)
        await db.events.create_index([("city", 1), ("date", 1)])
        await db.events.create_index("id", unique=True)
        await db.events.create_index("date")
        await db.moment_prompts.create_index("event_id", unique=True)
        await db.ticket_purchases.create_index([("user_id", 1), ("confirmed", 1)])
        await db.event_follows.create_index([("user_id", 1), ("event_id", 1)], unique=True)
        await db.event_follows.create_index("event_id")
        await db.scraped_venues.create_index("name")
        await db.scraped_venues.create_index("active")
        await db.scrape_changelog.create_index([("batch_id", 1), ("created_at", -1)])
        await db.event_history.create_index([("event_id", 1), ("created_at", -1)])
        await db.event_admin_edits.create_index([("event_id", 1), ("created_at", -1)])
        try:
            # auto-expire changelog after 30 days so it never bloats (also serves created_at sorts)
            await db.scrape_changelog.create_index("created_at", expireAfterSeconds=30 * 24 * 3600, name="cl_ttl")
        except Exception:
            pass
        await db.events.create_index("external_id")
        await db.events.create_index("source")
    except Exception as e:
        logger.warning(f"Index warn: {e}")
    await seed_admin()
    try:
        await seed_scraped_venues()
    except Exception as _:
        pass
    try:
        await seed_venue_directory()
    except Exception as _:
        pass
    try:
        await sync_scraper_venues_to_directory()
    except Exception as _:
        pass
    try:
        await enrich_venue_directory()
    except Exception as _:
        pass
    try:
        await sync_xceed_venues_to_directory()
    except Exception as _:
        pass
    try:
        await migrate_midnight_events()
    except Exception as _:
        pass
    try:
        await cleanup_old_events()
    except Exception as _:
        pass
    await cleanup_demo_events()
    # Seed the ClubTickets panel memory from events already stored with OUR ?aff
    # link so the same-day link-drop fix also protects parties ClubTickets has
    # ALREADY dropped from the panel today (idempotent, never raises).
    try:
        await _bootstrap_ct_memory_from_events()
    except Exception as _:
        pass
    # One-time migration: turn city-wide CHANGE alerts OFF by default for everyone
    # (owner reversed the earlier ON default — it was flooding users). New events
    # still reach EVERYONE in the city (see _notify_new_event_city, ungated); this
    # flag only affects the opt-in price/sale-state "cualquier cambio en mi ciudad"
    # alerts. Idempotent via a settings flag so it only runs once and never
    # re-flips users who later opt back in.
    try:
        _flag = await db.app_settings.find_one({"key": "city_alerts_default_off_v1"}, {"_id": 0})
        if not _flag:
            res = await db.users.update_many(
                {"city_change_alerts": {"$ne": False}},
                {"$set": {"city_change_alerts": False}},
            )
            await db.app_settings.update_one(
                {"key": "city_alerts_default_off_v1"},
                {"$set": {"key": "city_alerts_default_off_v1", "value": True,
                          "migrated": getattr(res, "modified_count", 0),
                          "at": datetime.now(timezone.utc).isoformat()}},
                upsert=True,
            )
            logger.info(f"[migration] city_change_alerts default OFF → {getattr(res,'modified_count',0)} users updated")
    except Exception as e:
        logger.warning(f"[migration] city_alerts default failed: {e}")
    global scheduler
    try:
        scheduler = AsyncIOScheduler(timezone="Europe/Madrid")
        # Friday at 12:00 (Palma time) — weekly plans digest
        scheduler.add_job(generate_weekly_digest, "cron", day_of_week="fri", hour=12, minute=0,
                          id="weekly_digest", replace_existing=True)
        scheduler.add_job(generate_event_reminders, "interval", minutes=30,
                          id="event_reminders", replace_existing=True)
        scheduler.add_job(generate_weekend_recap, "cron", day_of_week="mon", hour=12, minute=0,
                          id="weekend_recap", replace_existing=True)
        # Auto-trigger "El Momento" every 10 minutes for events happening right now
        scheduler.add_job(auto_trigger_moments, "interval", minutes=10,
                          id="auto_moments", replace_existing=True)
        # Daily randomizer for El Momento planned times — runs at 18:00 (Palma time)
        # every day, assigns 01:00-06:00 slot to today's events not yet scheduled.
        scheduler.add_job(daily_randomize_moments, "cron", hour=18, minute=0,
                          id="daily_randomize_moments", replace_existing=True)
        # Process scheduled admin notifications every minute
        scheduler.add_job(process_scheduled_notifications, "interval", minutes=1,
                          id="scheduled_notifications", replace_existing=True)
        # Monthly Wrapped: 1st of each month at 12:00 (Madrid) notify active users.
        scheduler.add_job(notify_monthly_wrapped, "cron", day=1, hour=12, minute=0,
                          id="monthly_wrapped", replace_existing=True)
        # Annual Wrapped: every Jan 1 at 12:10 notify users about last year's recap.
        scheduler.add_job(notify_annual_wrapped, "cron", month=1, day=1, hour=12, minute=10,
                          id="annual_wrapped", replace_existing=True)
        # Scrapers — bandwidth-aware two-tier schedule (keeps Render egress under
        # the free-tier cap without losing freshness):
        #   * LIGHT run every SCRAPER_LIGHT_INTERVAL_MIN: FourVenues + ClubTickets
        #     only. Full LISTING for all events (new parties + poster/name changes
        #     detected fast), but ticket DETAILS only for events within
        #     SCRAPER_LIGHT_WINDOW_DAYS. Heavy HTML adapters (xceed/nightleague)
        #     are skipped.
        #   * FULL run at SCRAPER_FULL_HOURS (a few times/day): every adapter, full
        #     ticket-detail sweep for all future events. Far-future prices refresh
        #     here. First light run 60s after startup warms the feed.
        scheduler.add_job(run_scrapers_light, "interval", minutes=SCRAPER_LIGHT_INTERVAL_MIN,
                          id="scrapers_light", replace_existing=True,
                          max_instances=1, coalesce=True, misfire_grace_time=300,
                          next_run_time=datetime.now(timezone.utc) + timedelta(seconds=60))
        scheduler.add_job(run_scrapers_full, "cron", hour=SCRAPER_FULL_HOURS, minute=15,
                          id="scrapers_full", replace_existing=True,
                          max_instances=1, coalesce=True, misfire_grace_time=600)
        scheduler.start()
        logger.info(f"Scheduler iniciado (digest viernes + recordatorios 30min + recuerdo lunes 12:00 + momentos auto cada 10min + randomizador diario 18:00 + scrapers LIGHT c/{SCRAPER_LIGHT_INTERVAL_MIN}min ventana {SCRAPER_LIGHT_WINDOW_DAYS}d + FULL a las {SCRAPER_FULL_HOURS}h)")
    except Exception as e:
        logger.error(f"Scheduler init falló: {e}")


async def auto_trigger_moments():
    """Automatically trigger 'El Momento' for events happening right now.
    The planned time is a random datetime between 01:00 and 06:00 on the NIGHT
    of the event (i.e., 01:00-06:00 of event_date + 1 day, since parties peak
    after midnight). Admin can override via /api/admin/moments/... endpoints.
    Skips events with moment_cancelled=True."""
    try:
        now = datetime.now(ZoneInfo("Europe/Madrid"))
        today = now.date().isoformat()
        yesterday = (now.date() - timedelta(days=1)).isoformat()
        candidates = []
        # Events today AND yesterday (for after-midnight parties)
        async for ev in db.events.find({"date": {"$in": [today, yesterday]}}, {"_id": 0}):
            candidates.append(ev)
        for ev in candidates:
            try:
                # Skip if cancelled by admin
                if ev.get("moment_cancelled"):
                    continue
                # If already has a prompt, skip
                existing = await db.moment_prompts.find_one({"event_id": ev["id"]})
                if existing:
                    continue
                # Only trigger if voy users exist
                voy_count = await db.interests.count_documents({"event_id": ev["id"], "status": "voy"})
                if voy_count == 0:
                    continue
                event_date = date.fromisoformat(ev["date"])
                # Check if we plan a moment time; store it in the event doc so it's deterministic
                planned = ev.get("planned_moment_at")
                if not planned:
                    # Pick a random datetime between 01:00 and 06:00 on the party NIGHT
                    # (calendar day AFTER event_date; parties peak after midnight)
                    party_night = event_date + timedelta(days=1)
                    hour = 1 + secrets.randbelow(5)  # 1, 2, 3, 4, or 5 (i.e. 01:00–05:59)
                    minute = secrets.randbelow(60)
                    planned_dt = datetime.combine(party_night, dtime(hour, minute), tzinfo=ZoneInfo("Europe/Madrid"))
                    planned = planned_dt.isoformat()
                    await db.events.update_one({"id": ev["id"]}, {"$set": {"planned_moment_at": planned}})
                planned_dt = datetime.fromisoformat(planned)
                if planned_dt.tzinfo is None:
                    planned_dt = planned_dt.replace(tzinfo=ZoneInfo("Europe/Madrid"))
                # Trigger if we've reached planned_dt and we're not more than 4h past it
                if planned_dt <= now <= planned_dt + timedelta(hours=4):
                    await _fire_moment(ev, triggered_by="auto")
                    logger.info(f"Auto moment triggered for {ev['name']}")
            except Exception as e:
                logger.warning(f"auto_moment inner failed for event {ev.get('id')}: {e}")
    except Exception as e:
        logger.error(f"auto_trigger_moments failed: {e}")


async def _fire_moment(ev: dict, triggered_by: str = "auto") -> dict:
    """Create the moment prompt for an event and notify all 'voy' users
    (both in-app and web push). Idempotent-ish (upserts the prompt)."""
    now_utc = datetime.now(timezone.utc)
    prompt = {
        "id": str(uuid.uuid4()),
        "event_id": ev["id"],
        "sent_at": now_utc.isoformat(),
        "on_time_deadline": (now_utc + timedelta(minutes=2)).isoformat(),
        "expires_at": (now_utc + timedelta(hours=6)).isoformat(),
        "triggered_by": triggered_by,
    }
    await db.moment_prompts.update_one({"event_id": ev["id"]}, {"$set": prompt}, upsert=True)
    notified = 0
    async for it in db.interests.find({"event_id": ev["id"], "status": "voy"}):
        await create_notification(
            it["user_id"], "moment_prompt",
            f"⚡ Es EL MOMENTO en {ev['name']}. ¡Sube una foto ya! (2 min para +30 puntos)",
            {"event_id": ev["id"], "type": "moment"},
        )
        notified += 1
    return {"prompt": prompt, "notified": notified}


async def daily_randomize_moments():
    """Runs once daily (18:00). Assigns random planned_moment_at (01:00-06:00
    on the night of the event) to today's events that don't have one yet and
    haven't been cancelled by admin. Idempotent — won't overwrite existing times."""
    try:
        now = datetime.now(ZoneInfo("Europe/Madrid"))
        today = now.date().isoformat()
        count = 0
        async for ev in db.events.find({"date": today}, {"_id": 0}):
            if ev.get("moment_cancelled"):
                continue
            if ev.get("planned_moment_at"):
                continue
            party_night = date.fromisoformat(ev["date"]) + timedelta(days=1)
            hour = 1 + secrets.randbelow(5)
            minute = secrets.randbelow(60)
            planned_dt = datetime.combine(party_night, dtime(hour, minute), tzinfo=ZoneInfo("Europe/Madrid"))
            await db.events.update_one(
                {"id": ev["id"]},
                {"$set": {"planned_moment_at": planned_dt.isoformat()}},
            )
            count += 1
        logger.info(f"daily_randomize_moments: assigned times to {count} events for {today}")
    except Exception as e:
        logger.error(f"daily_randomize_moments failed: {e}")


# =========================================================================
# NEXT BADGES (progress hints — for the "Insignia Diaria" nudge)
# =========================================================================

BADGE_THRESHOLDS = {
    # id -> (stat_key, threshold)
    "night_owl": ("total_events", 5),
    "party_pro": ("total_events", 10),
    "party_veteran": ("total_events", 20),
    "party_master": ("total_events", 35),
    "legend": ("total_events", 50),
    "immortal": ("total_events", 100),
    "day_streak_2": ("day_streak", 2),
    "day_streak_3": ("day_streak", 3),
    "day_streak_5": ("day_streak", 5),
    "day_streak_7": ("day_streak", 7),
    "day_streak_10": ("day_streak", 10),
    "day_streak_15": ("day_streak", 15),
    "week_streak_2": ("week_streak", 2),
    "week_streak_4": ("week_streak", 4),
    "week_streak_8": ("week_streak", 8),
    "week_streak_12": ("week_streak", 12),
    "week_streak_26": ("week_streak", 26),
    "weekday_warrior": ("weekday_count", 3),
    "weekday_boss": ("weekday_count", 10),
    "sunday_lover": ("sunday_count", 3),
    "social_5": ("friends_count", 5),
    "social_10": ("friends_count", 10),
    "social_20": ("friends_count", 20),
    "social_50": ("friends_count", 50),
    "social_100": ("friends_count", 100),
    "referral_1": ("referrals_count", 1),
    "referral_3": ("referrals_count", 3),
    "referral_5": ("referrals_count", 5),
    "referral_10": ("referrals_count", 10),
    "ticket_1": ("tickets_count", 1),
    "ticket_5": ("tickets_count", 5),
    "ticket_15": ("tickets_count", 15),
    "explorer_3": ("genres_count", 3),
    "explorer": ("genres_count", 5),
    "explorer_10": ("genres_count", 10),
    "venue_hopper": ("venues_count", 5),
    "capture_5": ("captures_count", 5),
    "capture_20": ("captures_count", 20),
    "storyteller": ("stories_count", 3),
    "storyteller_10": ("stories_count", 10),
    "story_star": ("stories_count", 30),
    "album_pro": ("album_uploads", 10),
    "album_master": ("album_uploads", 50),
}


@api_router.get("/me/next-badges")
async def next_badges(user: dict = Depends(get_current_user), limit: int = Query(3)):
    """Return the closest 'unlocked' badges (least gap between current stat and threshold).
    Used by the 'Insignia Diaria' banner on the Feed."""
    stats = await _compute_user_stats(user["user_id"])
    earned_ids = set(_award_badges(stats))
    out = []
    for bid, (key, threshold) in BADGE_THRESHOLDS.items():
        if bid in earned_ids:
            continue
        current = stats.get(key, 0)
        remaining = threshold - current
        if remaining <= 0:
            continue
        b = BADGES_BY_ID.get(bid)
        if not b:
            continue
        out.append({
            **b,
            "current": current,
            "threshold": threshold,
            "remaining": remaining,
            "stat_key": key,
            "progress": round(current / threshold * 100, 1) if threshold else 0,
        })
    out.sort(key=lambda x: (x["remaining"], -x["progress"]))
    return out[:limit]

app.include_router(api_router)


# =========================================================================
# SCRAPERS — automatic event ingestion from public club websites
# =========================================================================
from scrapers import build_scraper as _build_scraper, ScrapedEvent as _ScrapedEvent
from scrapers.base import normalize_venue_key as _norm_venue

_ALLOWED_ADAPTERS = ("fourvenues_api", "fourvenues_public_api", "nextjs_html", "nightleague", "xceed", "clubtickets")

# FourVenues guest-token: long-lived JWT shared by every microsite. Read from an
# app_settings override (editable in admin) first, then the env var. Cached briefly.
_FV_TOKEN_CACHE = {"val": None, "ts": 0.0}


async def _get_fourvenues_token() -> str:
    now = time.time()
    if _FV_TOKEN_CACHE["val"] is not None and now - _FV_TOKEN_CACHE["ts"] < 30:
        return _FV_TOKEN_CACHE["val"]
    token = ""
    try:
        s = await db.app_settings.find_one({"key": "fourvenues_guest_token"}, {"_id": 0})
        if s and s.get("value"):
            token = str(s["value"]).strip()
    except Exception:
        token = ""
    if not token:
        token = (os.environ.get("FOURVENUES_GUEST_TOKEN") or "").strip()
    _FV_TOKEN_CACHE["val"] = token
    _FV_TOKEN_CACHE["ts"] = now
    return token


async def _fourvenues_token_is_valid(token: str) -> Optional[bool]:
    """Live check against FourVenues. Returns True/False, or None if the check
    itself couldn't run (network error) so we don't false-alarm."""
    if not token:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                "https://cli-api-service.fourvenues.com/api/microsites/amok/metadata",
                headers={"Authorization": f"Bearer {token}",
                         "Origin": "https://site.fourvenues.com",
                         "User-Agent": "Mozilla/5.0"},
            )
        return r.status_code == 200
    except Exception:
        return None


# City keyword sets used to classify an affiliate club's address into one of the
# app's supported cities. Matched as WHOLE tokens against the city part extracted
# AFTER the postal code (via _city_from_address), never against the raw address —
# so street names like "Calle Barcelona" (in Benicasim) or "Las Palmas" can't
# false-match "Barcelona"/"Palma".
_CITY_KEYWORDS = {
    "Palma de Mallorca": {"palma", "mallorca", "magaluf", "calvia", "alcudia",
                          "andratx", "manacor", "santanyi", "peguera",
                          "portals", "llucmajor", "picafort", "pollensa"},
    "Ibiza": {"ibiza", "eivissa", "bossa"},
    "Madrid": {"madrid", "alcorcon", "mostoles", "getafe", "leganes"},
    "Barcelona": {"barcelona"},
    "Marbella": {"marbella", "banus", "estepona"},  # "san pedro" handled below
}


def _name_tokens(s: str) -> set:
    """Accent/case-insensitive word tokens (kept SEPARATE, unlike _norm_name which
    strips spaces). Used for city classification and duplicate-club detection."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return {t for t in re.split(r"[^a-z0-9]+", s) if t}


# City/region words that are NOT distinctive of a club (so 'Chango Madrid' and
# 'Opium Madrid' don't look like the same place just because both say 'madrid').
_CITY_TOKENS = {
    "madrid", "barcelona", "ibiza", "eivissa", "marbella", "banus", "puerto",
    "palma", "mallorca", "magaluf", "club", "the", "de", "la", "el",
}


def _venue_alias(a: str, b: str) -> bool:
    """Do two club names refer to the SAME physical venue, ignoring city/filler
    words? True when the distinctive-token set of one is a (non-empty) subset of
    the other. e.g. 'CHANGO CLUB MADRID' vs 'CHANGO MADRID' -> {chango} match."""
    ta = _name_tokens(a) - _CITY_TOKENS
    tb = _name_tokens(b) - _CITY_TOKENS
    if not ta or not tb:
        return False
    return ta <= tb or tb <= ta


def _supported_city_for(addr: str) -> Optional[str]:
    """Map a FourVenues address to one of the app's supported cities, or None.
    Uses only the city segment after the postal code to avoid street-name traps."""
    city = _city_from_address(addr)
    toks = _name_tokens(city)
    if not toks:
        return None
    if {"san", "pedro"} <= toks or {"puerto", "banus"} <= _name_tokens(addr):
        return "Marbella"
    for app_city, kws in _CITY_KEYWORDS.items():
        if toks & kws:
            return app_city
    return None


def _names_refer_same(a: str, b: str) -> bool:
    """Heuristic: do two venue names refer to the same physical club? True when
    one token set is a subset of the other (e.g. 'Chango Madrid' vs 'CHANGO CLUB
    MADRID'). Prevents auto-seeding a duplicate scraper for an already-covered club."""
    ta, tb = _name_tokens(a), _name_tokens(b)
    if not ta or not tb:
        return False
    return ta == tb or ta <= tb or tb <= ta


async def _auto_seed_affiliate_clubs(org_seed: dict, overrides: dict = None) -> int:
    """Ensure every club we carry (from our RRPP link) that sits in a SUPPORTED
    city has its own FourVenues scraper, so its events show up in the feed, get
    the 'Mi link' marker and rank first — WITHOUT us hand-adding each new club.
    Deduped by slug AND by name (so we never duplicate a club already scraped).
    org_seed: {org_slug: [org_name, {app_city: count}]}. Returns how many added.
    Respects admin overrides: a slug marked 'Pendiente' is skipped; a slug
    overridden to a supported city is seeded in THAT city."""
    if not org_seed:
        return 0
    overrides = overrides or {}
    try:
        existing_slugs = set()
        existing_names = []  # (norm-ready name)
        async for v in db.scraped_venues.find({}, {"_id": 0, "slug": 1, "name": 1}):
            if v.get("slug"):
                existing_slugs.add(v["slug"])
            if v.get("name"):
                existing_names.append(v["name"])
        added = 0
        for slug, (name, city_counts) in org_seed.items():
            if not slug or slug in existing_slugs:
                continue
            ov = overrides.get(slug)
            if ov == PENDING_CITY:
                continue  # admin marked this club as pending → do not auto-create
            if ov and ov in CITY_IDS:
                city = ov
            elif city_counts:
                city = max(city_counts.items(), key=lambda kv: kv[1])[0]
            else:
                continue
            if any(_names_refer_same(name, en) for en in existing_names):
                continue  # a scraper for this club already exists under another slug
            doc = {
                "id": str(uuid.uuid4()), "name": name, "slug": slug, "city": city,
                "adapter_type": "fourvenues_api", "active": True,
                "url": f"https://site.fourvenues.com/es/{slug}",
                "auto_affiliate": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "last_run_at": None, "last_run_ok": None, "last_run_events": 0,
                "last_run_new": 0, "last_run_updated": 0, "last_run_error": None,
            }
            await db.scraped_venues.insert_one(doc)
            existing_slugs.add(slug)
            existing_names.append(name)
            added += 1
        if added:
            logger.info(f"[affiliate] auto-seeded {added} new carried club(s) in supported cities")
        return added
    except Exception as e:
        logger.warning(f"[affiliate] auto-seed failed: {e}")
        return 0


async def _notify_new_carried_clubs(all_orgs: dict):
    """Notify admins when a club NEWLY appears in our RRPP link (a new discoteca
    added to our promoter profile). Purely additive: does NOT touch matching or
    ticket links. The FIRST run only records the current clubs as a baseline
    (no notifications), so we never spam every existing club as 'new'."""
    if not all_orgs:
        return
    try:
        doc = await db.app_settings.find_one({"key": "known_carried_clubs"}, {"_id": 0})
        current = set(all_orgs.keys())
        if not doc:
            await db.app_settings.update_one(
                {"key": "known_carried_clubs"},
                {"$set": {"key": "known_carried_clubs", "slugs": sorted(current),
                          "updated_at": datetime.now(timezone.utc).isoformat()}},
                upsert=True,
            )
            return
        known = set(doc.get("slugs", []))
        new_slugs = current - known
        if not new_slugs:
            return
        admin_ids = [a["user_id"] async for a in db.users.find({"role": "admin"}, {"_id": 0, "user_id": 1})]
        for slug in sorted(new_slugs):
            name = all_orgs.get(slug, slug)
            msg = f"🎉 Nueva discoteca en tu link RPP: {name}. Ya usa tu link de compra automáticamente."
            for uid in admin_ids:
                await create_notification(uid, "new_carried_club", msg,
                                          {"type": "new_carried_club", "slug": slug, "url": "/admin"})
        await db.app_settings.update_one(
            {"key": "known_carried_clubs"},
            {"$set": {"slugs": sorted(known | current),
                      "updated_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )
        logger.info(f"[affiliate] {len(new_slugs)} new carried club(s) → alerted {len(admin_ids)} admin(s)")
    except Exception as e:
        logger.warning(f"[affiliate] new-club notify failed: {e}")


async def refresh_affiliate_events() -> int:
    """Refresh the set of events that belong to OUR affiliate profile (our
    microsite slug). We call the same FourVenues events API used by the scraper,
    but for OUR slug, and cache the event ids/codes. Only these events get the
    affiliate link; everything else keeps its normal link. Runs on startup and
    every scraper cycle, so being added to new promoters is picked up on its own.
    Never clears the cache on a transient failure (keeps last known good)."""
    global _AFFILIATE_MAP, _AFFILIATE_BY_DN, _AFFILIATE_VENUES, _AFFILIATE_TS
    if not AFFILIATE_SLUG:
        return 0
    token = await _get_fourvenues_token()
    if not token:
        logger.info("[affiliate] no FourVenues token yet; keeping previous affiliate set")
        return len(_AFFILIATE_MAP)
    now = datetime.now(timezone.utc)
    start = int((now - timedelta(days=1)).timestamp())
    end = int((now + timedelta(days=200)).timestamp())
    headers = {
        "Authorization": f"Bearer {token}",
        "Origin": "https://site.fourvenues.com",
        "Referer": "https://site.fourvenues.com/",
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }
    mad = ZoneInfo("Europe/Madrid")
    amap: dict = {}          # (norm venue, date, norm name) -> our event slug
    by_dn: dict = {}         # (date, norm name) -> [(venue original, our slug)] alias fallback
    venue_agg: dict = {}     # (venue, city) -> count
    org_seed: dict = {}      # org_slug -> (org_name, app_city) for auto-seeding
    all_orgs: dict = {}      # org_slug -> venue name (every carried club in our RRPP)
    org_agg: dict = {}       # org key -> {slug, venue, cities:{detected_city:count}, events}
    try:
        async with httpx.AsyncClient(timeout=20, headers=headers) as client:
            page = 1
            while page <= 40:  # safety cap (paginate until an EMPTY page)
                r = await client.get(
                    "https://cli-api-service.fourvenues.com/api/events",
                    params={"startDate": start, "endDate": end, "slug": AFFILIATE_SLUG,
                            "pageSize": 200, "page": page, "orderBy": "startDate", "orderType": "asc"},
                )
                if r.status_code == 401:
                    logger.warning("[affiliate] token invalid (401); keeping previous affiliate set")
                    try:
                        await _alert_admins_token_expired()
                    except Exception:
                        pass
                    return len(_AFFILIATE_MAP)
                r.raise_for_status()
                payload = r.json()
                items = payload.get("data", []) if isinstance(payload, dict) else payload
                if not isinstance(items, list) or not items:
                    break
                for it in items:
                    name = str(it.get("name") or "").strip()
                    dates = it.get("dates") or {}
                    ts = dates.get("start") or dates.get("date")
                    if not name or not ts:
                        continue
                    # Same date formula the scraper uses (start ts, Madrid tz), THEN
                    # the SAME midnight normalization the ingestion applies: a party
                    # whose start is 00:00 really belongs to the previous night, so
                    # it is stored as 23:59 of the day before. The affiliate refresh
                    # MUST replicate this or the key is off by one day for every
                    # midnight-starting party (most clubs) → no match, no link, no
                    # badge. This was the root cause of missing "Mi link" markers.
                    _dt = datetime.fromtimestamp(int(ts), tz=mad)
                    date_str = _dt.strftime("%Y-%m-%d")
                    _time_str = _dt.strftime("%H:%M") if dates.get("start") else ""
                    if _time_str in ("00:00", "0:00", "00:00:00"):
                        try:
                            date_str = (date.fromisoformat(date_str) - timedelta(days=1)).isoformat()
                        except Exception:
                            pass
                    org = it.get("organization") or {}
                    venue = str(org.get("name") or "").strip()
                    # Store the event CODE (e.g. "127U"). The affiliate ticket link
                    # is the canonical microsite URL
                    # site.fourvenues.com/es/<affiliate>/events/<code> — the SAME
                    # code-based URL the microsite itself links to, so it resolves
                    # INSTANTLY (the pretty name-date-code URL is SSR-generated on
                    # demand and 404s for ~1 min until FourVenues caches it).
                    code = str(it.get("code") or it.get("slug") or "").strip().strip("/")
                    if not code:
                        continue
                    amap[_affiliate_key(venue, date_str, name)] = code
                    by_dn.setdefault((date_str, _norm_name(name)), []).append((venue, code))
                    # Breakdown so admin knows which venues/cities to add to the app.
                    loc = it.get("location") or {}
                    addr = str(loc.get("addressComplete") or loc.get("address") or "")
                    vcity = str(loc.get("city") or loc.get("town") or "").strip()
                    if not vcity:
                        vcity = _city_from_address(addr)
                    vk = (venue or "?", vcity)
                    venue_agg[vk] = venue_agg.get(vk, 0) + 1
                    # Auto-seed data: the CLUB microsite slug (org.slug, not the
                    # per-event slug) + a tally of the supported cities its events
                    # fall in, so a scraper can be created for every carried club
                    # (classified by its MOST COMMON supported city → robust for
                    # touring promoters) without hand-adding each one.
                    org_slug = str(org.get("slug") or "").strip()
                    _det_city = _supported_city_for(addr)
                    # Per-club aggregation (keyed by microsite slug, or venue name
                    # as fallback) that powers the affiliate panel + admin city
                    # reassignment. Records the DETECTED supported city (best guess)
                    # so the admin can confirm/correct it.
                    _okey = org_slug or _norm_name(venue or "?")
                    _orec = org_agg.setdefault(_okey, {"slug": org_slug, "venue": venue or org_slug or "?", "cities": {}, "events": 0})
                    _orec["events"] += 1
                    _dc = _det_city or ""
                    _orec["cities"][_dc] = _orec["cities"].get(_dc, 0) + 1
                    if org_slug:
                        all_orgs[org_slug] = venue or org_slug
                        # Always record the org for auto-seed (empty city map is OK);
                        # a supported detected city adds a vote for classification.
                        rec = org_seed.setdefault(org_slug, [venue or org_slug, {}])
                        if _det_city:
                            rec[1][_det_city] = rec[1].get(_det_city, 0) + 1
                # The FourVenues API returns a VARIABLE page size (~170) that is
                # SMALLER than the requested pageSize=200, so we must NOT stop on
                # "len < pageSize" (that quit after page 1 → only ~172 of ~700
                # events, i.e. just the next ~2 weeks). Keep paging until the API
                # returns an EMPTY page.
                page += 1
        if not amap:
            logger.info("[affiliate] API returned 0 events for our slug; keeping previous set")
            return len(_AFFILIATE_MAP)
        _AFFILIATE_MAP = amap
        _AFFILIATE_BY_DN = by_dn
        # Load admin city overrides (persistent manual reassignments) keyed by
        # club slug (or normalized venue name) so the panel reflects the admin's
        # choice even when auto-detection guessed a different / no city.
        overrides = {}
        async for _o in db.affiliate_city_overrides.find({}, {"_id": 0}):
            _k = _o.get("slug") or _o.get("key")
            if _k:
                overrides[_k] = _o.get("city")
        _vlist = []
        for _key, _rec in org_agg.items():
            _slug = _rec.get("slug") or ""
            _cities = {c: n for c, n in _rec.get("cities", {}).items() if c}
            _detected = max(_cities.items(), key=lambda kv: kv[1])[0] if _cities else ""
            _ov = overrides.get(_slug) or overrides.get(_key)
            _effective = _ov or _detected
            _pending = (_ov == PENDING_CITY)
            _in_app = (_effective in CITY_IDS) if _ov else _city_in_app(_detected)
            _vlist.append({
                "slug": _slug, "key": _key, "venue": _rec.get("venue") or "?",
                "city": _effective or "", "detected_city": _detected,
                "events": _rec.get("events", 0),
                "in_app": bool(_in_app) and not _pending,
                "override": bool(_ov), "pending": _pending,
            })
        _AFFILIATE_VENUES = sorted(_vlist, key=lambda x: (-x["events"], x["venue"]))
        _AFFILIATE_TS = time.time()
        logger.info(f"[affiliate] '{AFFILIATE_SLUG}' → {len(amap)} events across {len(_AFFILIATE_VENUES)} venues are mine")
        # Self-maintaining coverage: create a scraper for any carried club in a
        # supported city that we don't already scrape (deduped by slug + name).
        await _auto_seed_affiliate_clubs(org_seed, overrides)
        # Alert admins when a NEW club appears in our RRPP link (additive; does not
        # affect matching/linking). First run only records a baseline (no spam).
        await _notify_new_carried_clubs(all_orgs)
        return len(amap)
    except Exception as e:
        logger.warning(f"[affiliate] refresh failed ({e}); keeping previous affiliate set of {len(_AFFILIATE_MAP)}")
        return len(_AFFILIATE_MAP)




async def _alert_admins_token_expired():
    """Notify ONLY admin users that the FourVenues guest token has expired, so
    the scraper stopped importing new parties. Throttled to once per 12h so a
    persistent expiry doesn't spam the admin every scraper run."""
    try:
        flag = await db.app_settings.find_one({"_id": "fv_token_alert"}, {"_id": 0})
        last_at = (flag or {}).get("at")
        if last_at:
            try:
                delta = datetime.now(timezone.utc) - datetime.fromisoformat(last_at)
                if delta.total_seconds() < 12 * 3600:
                    return
            except Exception:
                pass
        msg = ("⚠️ El token de FourVenues ha caducado. El scraper NO está importando "
               "fiestas nuevas. Renueva el token en Panel → Scrapers.")
        n = 0
        async for a in db.users.find({"role": "admin"}, {"_id": 0, "user_id": 1}):
            await create_notification(a["user_id"], "admin_token_expired", msg,
                                      {"type": "admin_token_expired", "url": "/admin"})
            n += 1
        await db.app_settings.update_one(
            {"_id": "fv_token_alert"},
            {"$set": {"at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )
        logger.warning(f"[fourvenues] token expired → alerted {n} admin(s)")
    except Exception as e:
        logger.warning(f"_alert_admins_token_expired failed: {e}")

# Preseeded list of venues (Palma de Mallorca). Admin can add more via UI.
# All FourVenues-powered clubs use the universal 'fourvenues_api' adapter
# (rich data: real prices, sold-out & few-left flags). Only the club/promoter
# slug is needed (from site.fourvenues.com/es/<slug>).
_SEED_VENUES = [
    {"name": "Fitz Mallorca", "slug": "fitz-mallorca",
     "url": "https://site.fourvenues.com/es/fitz-mallorca"},
    {"name": "Amok Mallorca", "slug": "amok",
     "url": "https://site.fourvenues.com/es/amok"},
    {"name": "Over Club Mallorca", "slug": "over-club",
     "url": "https://site.fourvenues.com/es/over-club"},
    {"name": "Lunita", "slug": "lunita",
     "url": "https://site.fourvenues.com/es/lunita"},
    {"name": "Mar Salada", "slug": "mar-salada",
     "url": "https://site.fourvenues.com/es/mar-salada"},
    {"name": "Luna Palma", "slug": "luna-palma",
     "url": "https://site.fourvenues.com/es/luna-palma"},
    {"name": "Palma Events", "slug": "palma-events",
     "url": "https://site.fourvenues.com/es/palma-events"},
    {"name": "Velvet", "slug": "velvet-club",
     "url": "https://site.fourvenues.com/es/velvet-club"},
    {"name": "Boomerang", "slug": "boomerang",
     "url": "https://site.fourvenues.com/es/boomerang"},
    {"name": "BCM Planet Dance", "slug": "bcm-mallorca", "city": "Magaluf",
     "url": "https://site.fourvenues.com/es/bcm-mallorca"},
    {"name": "Tabana", "slug": "tabana-mallorca",
     "url": "https://site.fourvenues.com/es/tabana-mallorca"},
    {"name": "Danzû (Can Picafort)", "slug": "danzu", "city": "Can Picafort",
     "url": "https://site.fourvenues.com/es/danzu"},
    {"name": "Savage", "slug": "savage-mallorca",
     "url": "https://site.fourvenues.com/es/savage-mallorca"},
    {"name": "Laos", "slug": "laos-club",
     "url": "https://site.fourvenues.com/es/laos-club"},
    {"name": "Zar Society", "slug": "zar-mallorca",
     "url": "https://site.fourvenues.com/es/zar-mallorca"},
    {"name": "Galaxy", "slug": "galaxy-mallorca", "city": "Magaluf",
     "url": "https://site.fourvenues.com/es/galaxy-mallorca"},
    {"name": "Panama Jack", "slug": "panama-jack-magaluf", "city": "Magaluf",
     "url": "https://site.fourvenues.com/es/panama-jack-magaluf"},

    # ---- IBIZA (FourVenues, verified live) ----
    {"name": "Pacha Ibiza", "slug": "pacha-ibiza", "city": "Ibiza",
     "url": "https://site.fourvenues.com/es/pacha-ibiza"},
    # These Ibiza clubs use FourVenues as primary source (real per-event prices),
    # but we're ALSO ClubTickets affiliates for them (ct_slug). run_scraper_for_venue
    # ALWAYS rewrites their ticket links to our clubtickets.com link (?aff=CT226) —
    # keeping FourVenues prices when available — and falls back to the full
    # ClubTickets calendar when FourVenues returns nothing (e.g. token expired).
    {"name": "Lío Ibiza", "slug": "lio-ibiza", "city": "Ibiza",
     "url": "https://site.fourvenues.com/es/lio-ibiza", "ct_slug": "lio"},
    {"name": "Es Paradis Ibiza", "slug": "es-paradis-ibiza", "city": "Ibiza",
     "url": "https://site.fourvenues.com/es/es-paradis-ibiza", "ct_slug": "es-paradis"},
    {"name": "Eden Ibiza", "slug": "eden-ibiza", "city": "Ibiza",
     "url": "https://site.fourvenues.com/es/eden-ibiza", "ct_slug": "eden-ibiza"},
    {"name": "Pikes Ibiza", "slug": "pikes-ibiza", "city": "Ibiza",
     "url": "https://site.fourvenues.com/es/pikes-ibiza"},
    {"name": "Chinois Ibiza", "slug": "chinois-ibiza", "city": "Ibiza",
     "url": "https://site.fourvenues.com/es/chinois-ibiza", "ct_slug": "club-chinois-ibiza"},
    {"name": "Swag Ibiza", "slug": "swag-ibiza", "city": "Ibiza",
     "url": "https://site.fourvenues.com/es/swag-ibiza", "ct_slug": "swag"},
    {"name": "Ibiza Rocks", "slug": "ibiza-rocks", "city": "Ibiza",
     "url": "https://site.fourvenues.com/es/ibiza-rocks", "ct_slug": "ibiza-rocks"},
    {"name": "Bora Bora Ibiza", "slug": "bora-bora-ibiza", "city": "Ibiza",
     "url": "https://site.fourvenues.com/es/bora-bora-ibiza"},
    {"name": "Cova Santa Ibiza", "slug": "cova-santa", "city": "Ibiza",
     "url": "https://site.fourvenues.com/es/cova-santa"},

    # ---- MADRID (FourVenues, verified live) ----
    {"name": "LuLa Club", "slug": "lula-club", "city": "Madrid",
     "url": "https://site.fourvenues.com/es/lula-club"},
    {"name": "Chango Madrid", "slug": "discoteca-chango", "city": "Madrid",
     "url": "https://site.fourvenues.com/es/discoteca-chango"},
    {"name": "Deseo (Nazca)", "slug": "nazca-club", "city": "Madrid",
     "url": "https://site.fourvenues.com/es/nazca-club"},
    {"name": "Vandido", "slug": "vandido", "city": "Madrid",
     "url": "https://site.fourvenues.com/es/vandido"},
    {"name": "Green Social Club", "slug": "green", "city": "Madrid",
     "url": "https://site.fourvenues.com/es/green"},
    {"name": "Jowke Club", "slug": "jowke-club", "city": "Madrid",
     "url": "https://site.fourvenues.com/es/jowke-club"},
    {"name": "Kube Madrid", "slug": "kube", "city": "Madrid",
     "url": "https://site.fourvenues.com/es/kube"},
    {"name": "Teatro Kapital", "slug": "kapital", "city": "Madrid",
     "url": "https://site.fourvenues.com/es/kapital"},
    {"name": "Teatro Barceló", "slug": "teatro-barcelo", "city": "Madrid",
     "url": "https://site.fourvenues.com/es/teatro-barcelo"},
    {"name": "Sala Mon", "slug": "sala-mon", "city": "Madrid",
     "url": "https://site.fourvenues.com/es/sala-mon"},
    {"name": "Opium Madrid", "slug": "opium-madrid", "city": "Madrid",
     "url": "https://site.fourvenues.com/es/opium-madrid"},
    {"name": "Gabana", "slug": "gabana", "city": "Madrid",
     "url": "https://site.fourvenues.com/es/gabana"},
    {"name": "Medias Puri", "slug": "medias-puri", "city": "Madrid",
     "url": "https://site.fourvenues.com/es/medias-puri"},
    {"name": "Florida Park", "slug": "florida-park", "city": "Madrid",
     "url": "https://site.fourvenues.com/es/florida-park"},
    # Clubs carried via our RRPP link (quienva) — added so our affiliate events
    # exist in the feed, get the "Mi link" marker and rank first. Verified live.
    {"name": "Fitz Madrid", "slug": "fitz-madrid", "city": "Madrid",
     "url": "https://site.fourvenues.com/es/fitz-madrid"},
    {"name": "TIFFANY'S THE CLUB", "slug": "tiffanys-the-club1", "city": "Madrid",
     "url": "https://site.fourvenues.com/es/tiffanys-the-club1"},
    {"name": "CrisTo Social Club", "slug": "cristo-social-club", "city": "Madrid",
     "url": "https://site.fourvenues.com/es/cristo-social-club"},
    {"name": "Gunilla Club", "slug": "gunilla-club", "city": "Madrid",
     "url": "https://site.fourvenues.com/es/gunilla-club"},
    {"name": "Todos Santos", "slug": "todos-santos", "city": "Madrid",
     "url": "https://site.fourvenues.com/es/todos-santos"},
    {"name": "Teatro Magno", "slug": "teatro-magno", "city": "Madrid",
     "url": "https://site.fourvenues.com/es/teatro-magno"},
    {"name": "Shôko Madrid", "slug": "shoko-madrid", "city": "Madrid",
     "url": "https://site.fourvenues.com/es/shoko-madrid"},
    {"name": "PERRO NEGRO MADRID", "slug": "perro-negro-madrid", "city": "Madrid",
     "url": "https://site.fourvenues.com/es/perro-negro-madrid"},

    # ---- BARCELONA (FourVenues, verified live) ----
    {"name": "Opium Barcelona", "slug": "opium-barcelona", "city": "Barcelona",
     "url": "https://site.fourvenues.com/es/opium-barcelona"},
    {"name": "Bling Bling BCN", "slug": "bling-bling", "city": "Barcelona",
     "url": "https://site.fourvenues.com/es/bling-bling"},
    {"name": "Costa Este BCN", "slug": "costa-este", "city": "Barcelona",
     "url": "https://site.fourvenues.com/es/costa-este"},
    {"name": "Downtown Barcelona", "slug": "downtown-barcelona", "city": "Barcelona",
     "url": "https://site.fourvenues.com/es/downtown-barcelona"},
    {"name": "Twenties Barcelona", "slug": "twenties-barcelona", "city": "Barcelona",
     "url": "https://site.fourvenues.com/es/twenties-barcelona"},
    {"name": "Sutton Barcelona", "slug": "sutton-barcelona", "city": "Barcelona",
     "url": "https://site.fourvenues.com/es/sutton-barcelona"},
    {"name": "Otto Zutz", "slug": "otto-zutz", "city": "Barcelona",
     "url": "https://site.fourvenues.com/es/otto-zutz"},
    {"name": "City Hall Barcelona", "slug": "city-hall-barcelona", "city": "Barcelona",
     "url": "https://site.fourvenues.com/es/city-hall-barcelona"},
    {"name": "Luz de Gas", "slug": "luz-de-gas", "city": "Barcelona",
     "url": "https://site.fourvenues.com/es/luz-de-gas"},

    # ---- MARBELLA / PUERTO BANÚS (FourVenues, verified live) ----
    {"name": "Fitz Marbella", "slug": "fitz-marbella", "city": "Marbella",
     "url": "https://site.fourvenues.com/es/fitz-marbella"},
    {"name": "Mirage Marbella", "slug": "mirage-marbella", "city": "Marbella",
     "url": "https://site.fourvenues.com/es/mirage-marbella"},
    {"name": "Marina Beach Club", "slug": "marina-beach-club", "city": "Marbella",
     "url": "https://site.fourvenues.com/es/marina-beach-club"},
    {"name": "Opium Marbella", "slug": "opium-marbella", "city": "Marbella",
     "url": "https://site.fourvenues.com/es/opium-marbella"},
    {"name": "Tibu Marbella", "slug": "tibu-marbella", "city": "Marbella",
     "url": "https://site.fourvenues.com/es/tibu-marbella"},
    {"name": "Funky Buddha Puerto Banús", "slug": "funky-buddha-puerto-banus", "city": "Marbella",
     "url": "https://site.fourvenues.com/es/funky-buddha-puerto-banus"},
    {"name": "Xcess Banús", "slug": "xcess-banus", "city": "Marbella",
     "url": "https://site.fourvenues.com/es/xcess-banus"},
    # The Night League official-site scrapers (Ibiza superclubs, real prices via
    # embedded ClubTickets/JSON-LD availability — no FourVenues, no auth).
    {"name": "Ushuaïa Ibiza", "slug": "ushuaia-ibiza", "city": "Ibiza",
     "adapter_type": "nightleague",
     "url": "https://www.theushuaiaexperience.com/club/en", "ct_slug": "ushuaia-ibiza"},
    {"name": "Hï Ibiza", "slug": "hi-ibiza", "city": "Ibiza",
     "adapter_type": "nightleague",
     "url": "https://www.hiibiza.com/es", "ct_slug": "hi-ibiza"},
    # Xceed city listings — real club events with prices via schema.org JSON-LD.
    # No slug (they aggregate many real venues) so they don't create a directory
    # locale; per-event venue name is set from each event's JSON-LD location.
    {"name": "Xceed · Ibiza", "slug": "", "city": "Ibiza", "adapter_type": "xceed",
     "url": "https://xceed.me/es/ibiza/events"},
    {"name": "Xceed · Madrid", "slug": "", "city": "Madrid", "adapter_type": "xceed",
     "url": "https://xceed.me/es/madrid/events"},
    {"name": "Xceed · Barcelona", "slug": "", "city": "Barcelona", "adapter_type": "xceed",
     "url": "https://xceed.me/es/barcelona/events"},
    {"name": "Xceed · Marbella", "slug": "", "city": "Marbella", "adapter_type": "xceed",
     "url": "https://xceed.me/es/marbella/events"},
    {"name": "Xceed · Palma", "slug": "", "city": "Palma de Mallorca", "adapter_type": "xceed",
     "url": "https://xceed.me/es/palma-de-mallorca/events"},
    # ---- IBIZA · ClubTickets affiliate clubs.
    # Data comes from our affiliate links panel; ticket links carry ?aff=CT226 so
    # every sale is attributed to us. [UNVRS] uses its OWN Night League site as
    # primary (real per-event prices) + ct_slug so its buy links still go through
    # ClubTickets. The rest below are ClubTickets-only clubs (no other price source).
    {"name": "[UNVRS]", "slug": "unvrs-ibiza", "city": "Ibiza", "adapter_type": "nightleague",
     "url": "https://www.unvrs.com/", "ct_slug": "unvrs-ibiza"},
    {"name": "O Beach Ibiza", "slug": "o-beach-ibiza", "city": "Ibiza", "adapter_type": "clubtickets",
     "url": "https://www.clubtickets.com/clubbing/o-beach-ibiza"},
    {"name": "528 Ibiza", "slug": "528-ibiza", "city": "Ibiza", "adapter_type": "clubtickets",
     "url": "https://www.clubtickets.com/clubbing/528-ibiza"},
    {"name": "Baloo Ibiza", "slug": "baloo", "city": "Ibiza", "adapter_type": "clubtickets",
     "url": "https://www.clubtickets.com/clubbing/baloo"},
    {"name": "Bambuku Ibiza", "slug": "bambuku-ibiza", "city": "Ibiza", "adapter_type": "clubtickets",
     "url": "https://www.clubtickets.com/clubbing/bambuku-ibiza"},
    {"name": "Playa Soleil", "slug": "playa-soleil", "city": "Ibiza", "adapter_type": "clubtickets",
     "url": "https://www.clubtickets.com/clubbing/playa-soleil"},
    {"name": "Teatro Pereyra", "slug": "teatro-pereyra", "city": "Ibiza", "adapter_type": "clubtickets",
     "url": "https://www.clubtickets.com/clubbing/teatro-pereyra"},
]
for _v in _SEED_VENUES:
    _v.setdefault("city", "Palma de Mallorca")
    _v.setdefault("adapter_type", "fourvenues_api")
    _v.setdefault("active", True)


async def seed_scraped_venues():
    """Idempotent seed of the venues collection. Also migrates the two original
    venues (Fitz/Amok) to the universal fourvenues_api adapter + slug."""
    try:
        # Cleanup: Megasport is a gym, not a club — remove it and its events.
        _ms = await db.scraped_venues.find_one({"slug": "megasport"})
        if _ms:
            await db.events.delete_many({"scraper_venue_id": _ms["id"]})
            await db.scraped_venues.delete_one({"id": _ms["id"]})
        # Migrate legacy Fitz/Amok docs to the new universal adapter.
        _migrations = {
            "Fitz Mallorca": {"slug": "fitz-mallorca", "url": "https://site.fourvenues.com/es/fitz-mallorca"},
            "Amok Mallorca": {"slug": "amok", "url": "https://site.fourvenues.com/es/amok"},
        }
        for nm, patch in _migrations.items():
            await db.scraped_venues.update_one(
                {"name": nm},
                {"$set": {"adapter_type": "fourvenues_api", **patch}},
            )
        # Migrate [UNVRS] from the ClubTickets-only adapter to its own Night League
        # site (real per-event prices) while keeping ct_slug so buy links still go
        # through ClubTickets (?aff). Also drop the now-stale ClubTickets-sourced
        # future events so they get recreated with prices on the next run.
        _unvrs = await db.scraped_venues.find_one({"slug": "unvrs-ibiza"})
        if _unvrs and _unvrs.get("adapter_type") != "nightleague":
            await db.scraped_venues.update_one(
                {"id": _unvrs["id"]},
                {"$set": {"adapter_type": "nightleague",
                          "url": "https://www.unvrs.com/", "ct_slug": "unvrs-ibiza"}},
            )
            try:
                await db.events.delete_many({
                    "scraper_venue_id": _unvrs["id"], "source": "scraper",
                    "date": {"$gte": date.today().isoformat()},
                })
            except Exception:
                pass
        for v in _SEED_VENUES:
            existing = await db.scraped_venues.find_one({"name": v["name"]})
            if existing:
                # Backfill slug if missing (older docs).
                if not existing.get("slug") and v.get("slug"):
                    await db.scraped_venues.update_one(
                        {"id": existing.get("id")}, {"$set": {"slug": v["slug"]}})
                # Backfill the ClubTickets affiliate slug on existing docs so the
                # already-seeded clubs (Lío, Eden, Es Paradís, Chinois, Swag, Ibiza
                # Rocks, Ushuaïa, Hï) enforce our ?aff link + panel calendar without
                # a reseed. Also drop the legacy ct_fallback_slug field if present.
                if v.get("ct_slug") and existing.get("ct_slug") != v["ct_slug"]:
                    await db.scraped_venues.update_one(
                        {"id": existing.get("id")},
                        {"$set": {"ct_slug": v["ct_slug"]},
                         "$unset": {"ct_fallback_slug": ""}})
                continue
            doc = {**v, "id": str(uuid.uuid4()), "created_at": datetime.now(timezone.utc).isoformat(),
                   "last_run_at": None, "last_run_ok": None, "last_run_events": 0,
                   "last_run_new": 0, "last_run_updated": 0, "last_run_error": None}
            await db.scraped_venues.insert_one(doc)
        logger.info(f"Seeded scraped_venues: {len(_SEED_VENUES)} venues (fourvenues_api)")
        # Link curated Ibiza directory entries to their new scrapers so
        # sync_scraper_venues_to_directory dedups them (no duplicate locales).
        # Ushuaïa/Hï → Night League; [UNVRS] → ClubTickets affiliate panel.
        for nm, slug in (("Ushuaïa Ibiza", "ushuaia-ibiza"), ("Hï Ibiza", "hi-ibiza"),
                         ("[UNVRS]", "unvrs-ibiza")):
            await db.venues.update_many(
                {"name": nm, "scraper_slug": {"$in": ["", None]}},
                {"$set": {"scraper_slug": slug}})
            # Drop any auto-generated duplicate created before the link existed.
            await db.venues.delete_many(
                {"scraper_slug": slug, "auto_generated": True})
    except Exception as e:
        logger.warning(f"seed_scraped_venues failed: {e}")


async def _record_scrape_change(batch_id: str, kind: str, ev: dict, extra: dict = None):
    """Log a single change detected during a scraper run (for the admin panel)."""
    try:
        doc = {
            "id": str(uuid.uuid4()),
            "batch_id": batch_id or "",
            "kind": kind,  # new | price_up | price_down | state | sold_out | on_sale
            "event_id": ev.get("id", ""),
            "event_name": ev.get("name", ""),
            "venue": ev.get("venue", ""),
            "date": ev.get("date", ""),
            "city": ev.get("city", ""),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if extra:
            doc.update(extra)
        await db.scrape_changelog.insert_one(doc)
    except Exception as e:
        logger.warning(f"scrape changelog insert failed: {e}")


async def _record_event_history(event_id: str, kind: str, source: str = "scraper", extra: dict = None):
    """PERSISTENT per-event timeline (no TTL) — every price/state change, manual or
    automatic. Powers the admin 'Fiestas' tab history. 'Gran Hermano' mode."""
    try:
        doc = {
            "id": str(uuid.uuid4()),
            "event_id": event_id,
            "kind": kind,          # created | price_up | price_down | on_sale | low_stock | sold_out | state | edited | pricing_edited
            "source": source,      # scraper | admin
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if extra:
            doc.update(extra)
        await db.event_history.insert_one(doc)
    except Exception as e:
        logger.warning(f"event history insert failed: {e}")


async def _record_admin_edit(event_id: str, field: str, old_value, new_value, admin: dict, note: str = ""):
    """Per-field admin edit log (who/when/old/new) powering the 'Historial de
    ediciones' + undo in the event edit panel. Separate from event_history so it
    can carry the exact old value for a clean revert."""
    try:
        doc = {
            "id": str(uuid.uuid4()),
            "event_id": event_id,
            "field": field,
            "old_value": old_value,
            "new_value": new_value,
            "by_user_id": admin.get("user_id"),
            "by_email": admin.get("email"),
            "by_name": admin.get("username") or admin.get("name") or "admin",
            "note": note,
            "undone": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.event_admin_edits.insert_one(doc)
    except Exception as e:
        logger.warning(f"admin edit log failed: {e}")


def _significant_rename(old: str, new: str) -> bool:
    """True if an event's name changed meaningfully (not just accents/spacing/case).
    Used to surface Fitz-style placeholder→real-name reveals as a real 'novedad'."""
    o = _norm_name(old or "")
    n = _norm_name(new or "")
    if not n or n == o or len(n) < 3:
        return False
    return True


_CT_AFFILIATE_MAP = None


def _affiliate_ct_slug_for_name(name: str):
    """Return the ClubTickets slug for a venue NAME if it's one of our affiliate
    clubs (built once from _SEED_VENUES: ct_slug, or the slug of clubtickets-native
    venues). Lets us enforce our ?aff link on events created by ANY scraper."""
    global _CT_AFFILIATE_MAP
    if _CT_AFFILIATE_MAP is None:
        m = {}
        try:
            for v in _SEED_VENUES:
                ct = v.get("ct_slug") or (v.get("slug") if v.get("adapter_type") == "clubtickets" else None)
                if ct:
                    m[_norm_name(v.get("name", ""))] = ct
        except Exception:
            pass
        _CT_AFFILIATE_MAP = m
    return _CT_AFFILIATE_MAP.get(_norm_name(name or ""))


# ---------------------------------------------------------------------------
# ClubTickets affiliate-panel MEMORY (persistent) — fixes the "same-day link
# drop". ClubTickets REMOVES a party from OUR affiliate links panel on its own
# event day even though the party is still on sale, so our scraper used to lose
# the ?aff link for TODAY's parties (elrow@UNVRS, ANTS@Ushuaïa, Kodo@Lío ...).
# We snapshot every party the panel shows and, for parties whose date is TODAY
# (Europe/Madrid), keep serving the remembered ?aff link even after the panel
# drops them. FUTURE-dated parties that vanish are treated as genuinely removed
# (NOT resurrected), so we never keep a cancelled/dropped night alive.
# ---------------------------------------------------------------------------
_CT_MEM_TTL = 300              # re-persist the live panel at most every 5 min
_CT_MEM_LAST_WRITE = 0.0
_CT_MEM_RESURRECT_DAYS = 5     # only resurrect parties last seen within N days


async def _remember_panel(idx: dict) -> None:
    """Persist every party in the live affiliate panel (idempotent upsert with a
    fresh last_seen). Rate-limited to once per _CT_MEM_TTL so a full scraper
    cycle (thousands of events) never hammers Mongo. Never raises."""
    global _CT_MEM_LAST_WRITE
    if not idx:
        return
    now = time.time()
    if now - _CT_MEM_LAST_WRITE < _CT_MEM_TTL:
        return
    _CT_MEM_LAST_WRITE = now
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        from pymongo import UpdateOne
    except Exception:
        return
    ops = []
    for ct_slug, parties in idx.items():
        for p in (parties or []):
            eslug = p.get("event_slug") or ""
            d = p.get("date") or ""
            url = p.get("url") or ""
            if not d or not url:
                continue
            _id = f"{ct_slug}|{eslug}|{d}"
            ops.append(UpdateOne(
                {"_id": _id},
                {"$set": {"ct_slug": ct_slug, "event_slug": eslug, "date": d,
                          "name": p.get("name", ""), "url": url,
                          "last_seen": now_iso},
                 "$setOnInsert": {"first_seen": now_iso}},
                upsert=True,
            ))
    if not ops:
        return
    try:
        await db.ct_panel_memory.bulk_write(ops, ordered=False)
    except Exception as e:
        logger.warning(f"[clubtickets] panel memory write failed: {e}")


async def _merged_panel_index() -> dict:
    """Live affiliate-panel index (per ct_slug party list) MERGED with remembered
    parties whose date is TODAY (Europe/Madrid). Live entries always win. This is
    what makes a party ClubTickets drops from the panel on its own event day keep
    OUR ?aff link. Returns {} if the panel is unreachable AND memory is empty."""
    try:
        from scrapers.clubtickets import get_panel_index
        live = await get_panel_index(CLUBTICKETS_LINKS_URL)
    except Exception:
        live = {}
    live = live or {}
    # Snapshot the live panel (future days) so we can resurrect them on their day.
    try:
        await _remember_panel(live)
    except Exception:
        pass
    merged = {k: list(v) for k, v in live.items()}
    # (ct_slug, event_slug, date) already present in the live panel.
    present = {(k, (p.get("event_slug") or ""), p.get("date"))
               for k, v in merged.items() for p in (v or [])}
    today_str = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
    cutoff = (datetime.now(timezone.utc)
              - timedelta(days=_CT_MEM_RESURRECT_DAYS)).isoformat()
    try:
        cur = db.ct_panel_memory.find(
            {"date": today_str, "last_seen": {"$gte": cutoff}}, {"_id": 0})
        async for m in cur:
            key = (m.get("ct_slug"), m.get("event_slug") or "", m.get("date"))
            if key in present:
                continue
            merged.setdefault(m.get("ct_slug"), []).append({
                "name": m.get("name", ""),
                "event_slug": m.get("event_slug") or "",
                "date": m.get("date"),
                "url": m.get("url", ""),
            })
            present.add(key)
    except Exception as e:
        logger.warning(f"[clubtickets] panel memory read failed: {e}")
    return merged


async def _bootstrap_ct_memory_from_events() -> int:
    """One-time-ish seed of the panel memory from events already stored with OUR
    ClubTickets ?aff link (date >= today). Lets the same-day fix work on the very
    first run too — for parties ClubTickets has ALREADY dropped today (so the
    live panel can't teach us about them) but that are still in the DB from a
    previous scrape. Idempotent; never raises."""
    try:
        from pymongo import UpdateOne
    except Exception:
        return 0
    today_str = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
    now_iso = datetime.now(timezone.utc).isoformat()
    ops = []
    try:
        cur = db.events.find(
            {"date": {"$gte": today_str},
             "commission_url": {"$regex": "clubtickets\\.com"}},
            {"_id": 0, "name": 1, "date": 1, "commission_url": 1})
        async for ev in cur:
            url = ev.get("commission_url", "")
            if not _is_our_clubtickets_url(url):
                continue
            k = _ct_url_key(url)
            if not k:
                continue
            vslug, eslug, d = k
            _id = f"{vslug}|{eslug}|{d}"
            ops.append(UpdateOne(
                {"_id": _id},
                {"$set": {"ct_slug": vslug, "event_slug": eslug, "date": d,
                          "name": ev.get("name", ""), "url": url},
                 "$setOnInsert": {"first_seen": now_iso, "last_seen": now_iso}},
                upsert=True,
            ))
    except Exception as e:
        logger.warning(f"[clubtickets] memory bootstrap scan failed: {e}")
        return 0
    if not ops:
        return 0
    try:
        await db.ct_panel_memory.bulk_write(ops, ordered=False)
    except Exception as e:
        logger.warning(f"[clubtickets] memory bootstrap write failed: {e}")
        return 0
    logger.info(f"[clubtickets] panel memory bootstrapped from {len(ops)} stored aff events")
    return len(ops)



async def _ct_affiliate_url_for(ct_slug: str, date_str: str, name: str):
    """Return OUR ClubTickets ?aff link for a party ONLY if that exact party is in
    our affiliate panel, else None. Match is PER PARTY (never per venue): the panel
    party must be on the SAME night-label date AND its name must match (fuzzy). We
    do NOT blindly take a single same-date candidate anymore: a club can run more
    than one party a night (e.g. Lío's early 'The Halftime Show' + late 'Tiempo'),
    so a same-date-but-different-name party must NOT inherit another party's link.
    None → the caller keeps the party's normal direct link (no ?aff).

    `date_str` is expected to already be the night-label date (this is called from
    _apply_scraped_event AFTER midnight normalization); we normalize once more
    defensively so a raw midnight date still lines up with the panel."""
    if not ct_slug or not date_str:
        return None
    try:
        idx = await _merged_panel_index()
    except Exception:
        return None
    parties = idx.get(ct_slug) or []
    if not parties:
        return None
    same_date = [p for p in parties if p.get("date") == date_str]
    for p in same_date:
        if _ct_name_match(name, p.get("name", "")):
            return p.get("url") or None
    return None


async def _apply_scraped_event(venue: dict, se: _ScrapedEvent, batch_id: str = "") -> str:
    """Diff a single scraped event against the DB and apply changes:
    - CREATE if not found → fires "new event" push to city.
    - UPDATE fields if found; if sale_state transitioned or price went up,
      fires the corresponding notification (same logic as manual admin).
    Returns: 'created' | 'updated' | 'unchanged' | 'skipped'.
    """
    venue_name = venue.get("name") or ""
    city = venue.get("city") or "Palma de Mallorca"
    # Normalize midnight: a party at 00:00 really belongs to the previous night,
    # so we store it as 23:59 of the day before. This removes the "day 4 00:00 vs
    # night of 3→4" ambiguity and makes it show under the correct "hoy" day.
    if (se.time or "").strip() in ("00:00", "0:00", "00:00:00"):
        try:
            se.date = (date.fromisoformat(se.date) - timedelta(days=1)).isoformat()
            se.time = "23:59"
        except Exception:
            pass
    # Affiliate-link enforcement (source-agnostic, PER PARTY — never per venue):
    # if this exact party (venue + date + name) appears in OUR ClubTickets affiliate
    # panel, force its buy link to our ?aff link so the sale is attributed to us —
    # no matter which scraper produced it (e.g. the city-wide Xceed feed, or a
    # FourVenues party we also carry on ClubTickets). If the party is NOT in our
    # panel we leave its link exactly as the primary source gave it (FourVenues,
    # the club's own site, Xceed, ...) with NO ?aff, so the party always resolves.
    _ct_slug = _affiliate_ct_slug_for_name(se.venue or venue_name)
    if _ct_slug:
        try:
            _aff_url = await _ct_affiliate_url_for(_ct_slug, se.date, se.name)
        except Exception:
            _aff_url = None
        if _aff_url:
            se.ticket_url = _aff_url  # this party IS in our panel → our ?aff link
    # 1) Lookup by external_id (most reliable)
    existing = await db.events.find_one({"external_id": se.external_id}, {"_id": 0})
    # 2) Fallback: venue + date (user might have created it manually). Only match
    #    candidates WITHOUT an external_id — otherwise two scraped events at the same
    #    venue on the same day would cannibalize each other.
    if not existing:
        norm = _norm_venue(venue_name)
        async for c in db.events.find({"date": se.date}, {"_id": 0}):
            if c.get("external_id"):
                continue
            if _norm_venue(c.get("venue", "")) == norm:
                existing = c
                break
    # 3) Robust re-match (prevents broken links / 404): the SAME real party can come
    #    back with a DIFFERENT external_id — FourVenues issues a new code per
    #    microsite, and a club can flip between FourVenues- and ClubTickets-sourced
    #    feeds run to run. Matching ONLY by external_id would CREATE a new event
    #    (new UUID) every time, and the reconcile step below would delete the
    #    previous one -> every previously shared/opened link 404s. So also REUSE an
    #    existing SCRAPED event for the SAME venue (scraper_venue_id) + date whose
    #    NAME matches (fuzzy). This keeps the event id STABLE across runs so links
    #    never break. The name check disambiguates two different parties on the same
    #    night at the same venue (they won't fuzzy-match).
    if not existing and venue.get("id"):
        async for c in db.events.find(
            {"date": se.date, "source": "scraper", "scraper_venue_id": venue.get("id")},
            {"_id": 0},
        ):
            if _ct_name_match(se.name, c.get("name", "")):
                existing = c
                break
    now_iso = datetime.now(timezone.utc).isoformat()
    if not existing:
        # CREATE
        ev = {
            "id": str(uuid.uuid4()),
            "name": se.name,
            "venue": se.venue or venue_name,
            "address": "",
            "date": se.date,
            "time": se.time or "",
            "image_url": se.image_url,
            "genre": (se.genre or "").split(",")[0].strip()[:40],
            "city": city,
            "has_commission": bool(se.ticket_url),
            "commission_url": se.ticket_url or "",
            "more_info_url": "",
            "price_tiers": se.price_tiers or [],
            "sale_state": se.sale_state or "no_a_la_venta",
            "currency": se.currency or "EUR",
            "source": "scraper",
            "external_id": se.external_id,
            "scraper_venue_id": venue.get("id"),
            "lat": getattr(se, "lat", None),
            "lng": getattr(se, "lng", None),
            "venue_image": getattr(se, "venue_image", "") or "",
            "created_at": now_iso,
            "last_scraped_at": now_iso,
        }
        await db.events.insert_one(ev)
        _invalidate_stats_cache()
        # Fire "new event" push (fire-and-forget). Skip on the venue's FIRST
        # ever run to avoid flooding users when a new club/city is onboarded
        # (that run bulk-creates its whole calendar). Real new events on later
        # runs still notify.
        if venue.get("last_run_at"):
            try:
                asyncio.create_task(_notify_new_event_city(ev))
            except Exception:
                pass
        await _record_scrape_change(batch_id, "new", ev, {
            "current_price": ev.get("price_tiers", [{}])[0].get("price") if ev.get("price_tiers") else None,
            "sale_state": ev.get("sale_state"),
        })
        await _record_event_history(ev["id"], "created", "scraper", {
            "sale_state": ev.get("sale_state"),
            "new_price": ev.get("price_tiers", [{}])[0].get("price") if ev.get("price_tiers") else None,
        })
        return "created"

    # UPDATE — merge scraped fields but respect admin's manual overrides where
    # sensible. We DO overwrite: name, date, time, image_url (only if empty),
    # commission_url (only if empty), price_tiers, sale_state.
    old_state = existing.get("sale_state", "no_a_la_venta")
    old_tiers = existing.get("price_tiers", []) or []
    patch = {"last_scraped_at": now_iso, "external_id": se.external_id}
    if not existing.get("source"):
        patch["source"] = "scraper"
    if se.name and se.name != existing.get("name"):
        patch["name"] = se.name
    if existing.get("source") == "scraper":
        # keep real venue name + latest poster in sync for scraped events
        if se.venue and se.venue != existing.get("venue"):
            patch["venue"] = se.venue
        if se.image_url and se.image_url != existing.get("image_url"):
            patch["image_url"] = se.image_url
    if se.time and se.time != existing.get("time"):
        patch["time"] = se.time
    if se.image_url and not existing.get("image_url"):
        patch["image_url"] = se.image_url
    if getattr(se, "lat", None) is not None and existing.get("lat") is None:
        patch["lat"] = se.lat
        patch["lng"] = se.lng
    if getattr(se, "venue_image", "") and not existing.get("venue_image"):
        patch["venue_image"] = se.venue_image
    if se.ticket_url and not existing.get("commission_url"):
        patch["commission_url"] = se.ticket_url
        patch["has_commission"] = True
    # Keep scraped events' buy link in sync with the freshly computed one so any
    # stale link is corrected on the next run — CRUCIALLY this repoints a party
    # AWAY from a wrong ?aff link back to its normal direct link when we don't
    # carry it, and onto our ?aff link when we do. Manual (non-scraper) events are
    # never touched, so admin overrides stand.
    elif (existing.get("source") == "scraper" and se.ticket_url
          and se.ticket_url != existing.get("commission_url")):
        patch["commission_url"] = se.ticket_url
        patch["has_commission"] = True
    if se.genre and not existing.get("genre"):
        patch["genre"] = se.genre.split(",")[0].strip()[:40]
    # Pricing — but ONLY when this run actually fetched the ticket detail. On a
    # "light" run far-future events arrive with pricing_known=False; we must keep
    # the DB's last known price/state instead of clobbering it with empty values.
    if getattr(se, "pricing_known", True):
        if se.price_tiers != old_tiers:
            patch["price_tiers"] = se.price_tiers
        if se.sale_state and se.sale_state != old_state:
            patch["sale_state"] = se.sale_state
    if len(patch) == 2:  # only meta fields (last_scraped_at, external_id)
        await db.events.update_one({"id": existing["id"]}, {"$set": patch})
        return "unchanged"
    await db.events.update_one({"id": existing["id"]}, {"$set": patch})
    _invalidate_stats_cache()
    # Fire notifications on transitions (same rules as manual pricing endpoint)
    new_state = patch.get("sale_state", old_state)
    new_tiers = patch.get("price_tiers", old_tiers)
    transition = _describe_sale_transition(old_state, new_state)
    if transition:
        kind, tmpl = transition
        body = tmpl.format(name=existing["name"])
        await _notify_event_audience(existing["id"], kind, existing["name"], body)
        _cl_kind = {"tickets_on_sale": "on_sale", "tickets_low_stock": "state",
                    "tickets_sold_out": "sold_out"}.get(kind, "state")
        await _record_scrape_change(batch_id, _cl_kind, existing, {"old_state": old_state, "new_state": new_state})
        await _record_event_history(existing["id"], _cl_kind, "scraper", {"old_state": old_state, "new_state": new_state})
    new_price = _detect_price_increase(old_tiers, new_tiers)
    if new_price is not None and new_state == "a_la_venta":
        body = f"📈 Nueva fase de precios en {existing['name']}: ahora {int(new_price)}€."
        await _notify_event_audience(existing["id"], "tickets_price_up", existing["name"], body)
        await _record_scrape_change(batch_id, "price_up", existing, {"new_price": new_price})
        await _record_event_history(existing["id"], "price_up", "scraper", {"new_price": new_price})
    drop_price = _detect_price_decrease(old_tiers, new_tiers)
    if drop_price is not None and new_state in ("a_la_venta", "pocas_entradas"):
        body = f"📉 ¡Bajada de precio en {existing['name']}! Ahora desde {int(drop_price)}€."
        await _notify_event_audience(existing["id"], "tickets_price_down", existing["name"], body)
        await _record_scrape_change(batch_id, "price_down", existing, {"new_price": drop_price})
        await _record_event_history(existing["id"], "price_down", "scraper", {"new_price": drop_price})
    # Name change (e.g. Fitz's placeholder "Jueves Fitz" → real artist/party name).
    new_name = patch.get("name")
    if new_name and _significant_rename(existing.get("name", ""), new_name):
        old_name = existing.get("name", "")
        await _record_scrape_change(
            batch_id, "renamed", {**existing, "name": new_name},
            {"old_name": old_name, "new_name": new_name},
        )
        await _record_event_history(
            existing["id"], "renamed", "scraper",
            {"old_name": old_name, "new_name": new_name},
        )
        try:
            body = f"🎤 Ya hay cartel: {new_name}"
            await _notify_event_audience(existing["id"], "event_renamed", new_name, body)
        except Exception:
            pass
    # Affiliate-link FLIP alert: the buy link crossed the "earns us commission"
    # line since the last run — either it LOST our ClubTickets ?aff link (now a
    # plain direct link → no commission) or it GAINED it (now goes through us).
    # We only care about a genuine change on an EXISTING scraped event that
    # already had a link (not the first time it's set). Recorded in the changelog
    # + per-event history; admins get ONE grouped push per run (see
    # _notify_admins_affiliate_flips), never one-per-event, so a mass re-point
    # (e.g. after fixing the matching) can't spam.
    if "commission_url" in patch:
        _old_url = existing.get("commission_url", "") or ""
        _new_url = patch.get("commission_url", "") or ""
        if _old_url and _new_url != _old_url:
            _old_ours = _is_our_clubtickets_url(_old_url)
            _new_ours = _is_our_clubtickets_url(_new_url)
            if _old_ours != _new_ours:
                _direction = "lost" if _old_ours and not _new_ours else "gained"
                _flip_extra = {"direction": _direction,
                               "old_url": _old_url[:400], "new_url": _new_url[:400]}
                await _record_scrape_change(batch_id, "affiliate_flip", existing, _flip_extra)
                await _record_event_history(existing["id"], "affiliate_flip", "scraper", _flip_extra)
    return "updated"


async def _enforce_clubtickets_affiliate(venue: dict, primary: list) -> list:
    """For a club we carry on ClubTickets (venue['ct_slug']), attribute the sale to
    us ONLY on the exact parties we actually carry in our affiliate panel — matched
    PER PARTY (date + fuzzy name), NEVER blanket per venue.

    - A primary-source party (FourVenues / the club's own site) that MATCHES a party
      in our panel → its buy link becomes our ClubTickets ?aff link (we keep the
      primary's richer data: real prices, poster, artist name).
    - A primary party that is NOT in our panel → its link is left EXACTLY as the
      primary gave it (FourVenues / native, no ?aff), so the party always resolves
      and checkout never breaks. We never fall back to the club landing + ?aff.
    - Panel parties the primary didn't have are appended so the calendar is complete
      (these carry our ?aff, since they ARE ours).
    - If the primary produced nothing, the whole calendar comes from the panel.
    """
    ct_slug = venue.get("ct_slug")
    if not ct_slug:
        return primary
    # Build the ClubTickets calendar from the MEMORY-augmented panel index so
    # parties ClubTickets dropped from the panel on their own event day (but which
    # are still on sale) keep OUR ?aff link instead of falling back to a plain link.
    from scrapers.clubtickets import _COORDS as _CT_COORDS
    idx = await _merged_panel_index()
    parties = idx.get(ct_slug) or []
    _lat, _lng = _CT_COORDS.get(ct_slug, (None, None))
    ct_events = []
    _seen_ct: set = set()
    for p in parties:
        d = p.get("date") or ""
        eslug = p.get("event_slug") or ""
        url = p.get("url") or ""
        if not d or not url:
            continue
        ext = f"ct:{ct_slug}:{eslug}:{d}"
        if ext in _seen_ct:
            continue
        _seen_ct.add(ext)
        _name = p.get("name") or (eslug or venue.get("name", "")).replace("-", " ").title()
        ct_events.append(_ScrapedEvent(
            external_id=ext,
            name=_name[:120],
            venue=venue.get("name", ""),
            date=d,
            time="",
            image_url="",
            ticket_url=_clubtickets_affiliate_url(url),
            price_tiers=[],
            sale_state="a_la_venta",
            currency="EUR",
            lat=_lat, lng=_lng,
        ))
    if not ct_events:
        return primary          # panel unreachable + no memory → leave primary untouched
    if not primary:
        return ct_events        # primary empty → full ClubTickets affiliate calendar
    by_date: dict = {}
    for ce in ct_events:
        by_date.setdefault(ce.date, []).append(ce)
    # Group the primary events by their NIGHT-LABEL date (midnight starts belong to
    # the previous night — same rule the store uses) so both sources line up, and
    # so we know how many primary parties share a night (needed for the safe
    # single-candidate fallback below).
    prim_by_nd: dict = {}
    for pe in primary:
        nd = _ct_night_date(pe.date, getattr(pe, "time", ""))
        prim_by_nd.setdefault(nd, []).append(pe)
    matched_ext: set = set()
    for nd, pes in prim_by_nd.items():
        cands = by_date.get(nd) or []
        if not cands:
            continue  # nothing carried that night → keep every primary link as-is
        for pe in pes:
            chosen = None
            # 1) Name match FIRST — the only reliable signal when a club runs
            #    several parties a night (e.g. Lío's 'The Halftime Show' 21:00 and
            #    'Tiempo' 23:45 both on the same date, but only 'Tiempo' is ours).
            for ce in cands:
                if _ct_name_match(pe.name, ce.name):
                    chosen = ce
                    break
            # 2) Fallback: take the single carried party ONLY when it is truly
            #    unambiguous — exactly one carried party AND exactly one primary
            #    party that night — so a same-date-but-different-name sibling can
            #    never inherit another party's link.
            if chosen is None and len(cands) == 1 and len(pes) == 1:
                chosen = cands[0]
            if chosen is not None:
                pe.ticket_url = chosen.ticket_url    # our ?aff link — party is ours
                matched_ext.add(chosen.external_id)
            # else: NOT in our panel → keep pe.ticket_url (primary's own direct link)
    extra = [ce for ce in ct_events if ce.external_id not in matched_ext]
    return primary + extra



async def run_scraper_for_venue(venue: dict, batch_id: str = "",
                                detail_window_days: Optional[int] = None) -> dict:
    """Run one venue's scraper and apply diffs. Returns a summary.

    detail_window_days: when set (a "light" run), FourVenues venues only fetch
    ticket details for events starting within that many days (far events keep
    their last known price/state). None => full detail sweep."""
    _standalone = not batch_id
    if not batch_id:
        batch_id = uuid.uuid4().hex
    start = time.time()
    summary = {"venue_id": venue.get("id"), "venue_name": venue.get("name"), "ok": False,
               "events": 0, "created": 0, "updated": 0, "unchanged": 0, "error": None,
               "duration_ms": 0}
    try:
        _kwargs = dict(
            venue_name=venue.get("name", ""),
            city=venue.get("city", "Palma de Mallorca"),
        )
        if venue.get("adapter_type") == "fourvenues_api":
            _kwargs["slug"] = venue.get("slug") or ""
            _kwargs["guest_token"] = await _get_fourvenues_token()
            if detail_window_days is not None:
                _kwargs["detail_window_days"] = detail_window_days
        if venue.get("adapter_type") == "clubtickets":
            _kwargs["venue_slug"] = venue.get("slug") or ""
            _kwargs["panel_url"] = CLUBTICKETS_LINKS_URL
            _kwargs["aff_code"] = CLUBTICKETS_AFF
        scraper = _build_scraper(venue["adapter_type"], venue["url"], **_kwargs)
        # Run the primary scraper. If it raises (e.g. FourVenues guest-token expired)
        # but this club is one of our ClubTickets affiliate venues (ct_slug), don't
        # fail — we still build/repair its calendar from the affiliate panel below.
        _primary_err = None
        try:
            events = await scraper.fetch()
        except Exception as _e:
            if not venue.get("ct_slug"):
                raise
            _primary_err = _e
            events = []
        # ClubTickets affiliate enforcement: for every club we carry on ClubTickets
        # make sure EVERY ticket link is our clubtickets.com link with ?aff=<code>,
        # keeping the primary's prices/poster where available (see helper docstring).
        if venue.get("ct_slug"):
            try:
                _before = len(events)
                events = await _enforce_clubtickets_affiliate(venue, events)
                if _primary_err is not None or _before == 0:
                    summary["source"] = "clubtickets"
                elif len(events) != _before:
                    summary["source"] = "primary+clubtickets"
                else:
                    summary["source"] = "primary(clubtickets links)"
            except Exception as e:
                logger.warning(f"[scraper] {venue.get('name')} clubtickets enforce failed: {e}")
        # If the primary errored AND we still have nothing, surface the original
        # error so the admin panel flags the broken venue.
        if _primary_err is not None and not events:
            raise _primary_err
        summary["events"] = len(events)
        _seen_ext: set = set()
        for se in events:
            try:
                _seen_ext.add(se.external_id)
                r = await _apply_scraped_event(venue, se, batch_id)
                if r in summary:
                    summary[r] += 1
            except Exception as e:
                logger.warning(f"[scraper {venue.get('name')}] apply failed for {se.external_id}: {e}")
        # Reconcile: for ClubTickets-affiliate clubs, drop FUTURE scraped events of
        # this venue that were NOT in this run (e.g. old FourVenues-sourced events
        # replaced by ClubTickets, or vice-versa) so the same night never shows
        # twice from two providers. Only future, only this venue, only scraped.
        if venue.get("ct_slug") and _seen_ext:
            try:
                _today = date.today().isoformat()
                await db.events.delete_many({
                    "scraper_venue_id": venue.get("id"),
                    "source": "scraper",
                    "date": {"$gte": _today},
                    "external_id": {"$nin": list(_seen_ext)},
                })
            except Exception as e:
                logger.warning(f"[scraper {venue.get('name')}] reconcile failed: {e}")
        summary["ok"] = True
    except Exception as e:
        summary["error"] = str(e)[:400]
        logger.error(f"[scraper] {venue.get('name')} failed: {e}")
    summary["duration_ms"] = int((time.time() - start) * 1000)
    # Save summary to venue doc
    try:
        await db.scraped_venues.update_one(
            {"id": venue["id"]},
            {"$set": {
                "last_run_at": datetime.now(timezone.utc).isoformat(),
                "last_run_ok": summary["ok"],
                "last_run_events": summary["events"],
                "last_run_new": summary["created"],
                "last_run_updated": summary["updated"],
                "last_run_error": summary["error"],
                "last_run_duration_ms": summary["duration_ms"],
            }},
        )
    except Exception:
        pass
    # Standalone (single-venue admin) run: send the grouped affiliate-flip alert
    # now (a full run-all sends it once at the end instead — see run_all_scrapers).
    if _standalone:
        try:
            await _notify_admins_affiliate_flips(batch_id, venue.get("name"))
        except Exception:
            pass
    return summary


async def _notify_admins_affiliate_flips(batch_id: str, venue_name: str = None):
    """Send ONE grouped notification to every admin summarising the affiliate-link
    flips recorded in this scrape batch (parties that changed from OUR ClubTickets
    ?aff link to a plain direct link, or vice-versa). Grouped on purpose so a mass
    re-point never floods admins with one push per party. Opt-out via app_settings
    key 'admin_affiliate_flip_alerts' (ON by default). Never raises."""
    try:
        s = await db.app_settings.find_one({"key": "admin_affiliate_flip_alerts"}, {"_id": 0})
        if s is not None and s.get("value") is False:
            return  # disabled by admin
        q = {"batch_id": batch_id, "kind": "affiliate_flip"}
        if venue_name:
            q["venue"] = venue_name
        flips = []
        async for c in db.scrape_changelog.find(q, {"_id": 0}):
            flips.append(c)
        if not flips:
            return
        lost = [f for f in flips if f.get("direction") == "lost"]
        gained = [f for f in flips if f.get("direction") == "gained"]
        parts = []
        if lost:
            parts.append(f"{len(lost)} pasaron a enlace directo (sin comisión)")
        if gained:
            parts.append(f"{len(gained)} pasaron a tu enlace de afiliado")
        detail = " · ".join(parts) if parts else f"{len(flips)} cambios"
        # A couple of concrete examples so the alert is actionable at a glance.
        sample = "; ".join(
            f"{(f.get('event_name') or '¿?')[:30]} ({'→directo' if f.get('direction') == 'lost' else '→afiliado'})"
            for f in flips[:3]
        )
        msg = f"🔀 Enlaces de venta: {detail}." + (f" Ej.: {sample}" if sample else "")
        data = {"type": "admin_affiliate_flip", "batch_id": batch_id,
                "lost": len(lost), "gained": len(gained), "url": "/admin"}
        async for a in db.users.find({"role": "admin"}, {"_id": 0, "user_id": 1}):
            await create_notification(a["user_id"], "admin_affiliate_flip", msg, data)
    except Exception as e:
        logger.warning(f"[affiliate-flip-alert] failed: {e}")


async def run_all_scrapers(mode: str = "full"):
    """Run active venues with a bounded concurrency (protects Render free tier
    and avoids hammering FourVenues when many venues are configured). Called by
    scheduler + admin trigger.

    mode="full"  -> every adapter, full ticket-detail sweep (all future events).
    mode="light" -> ONLY the cheap/high-value adapters (FourVenues + ClubTickets),
                    and FourVenues fetches ticket details ONLY for events within
                    SCRAPER_LIGHT_WINDOW_DAYS. New parties + poster/name changes
                    are still picked up for ALL FourVenues events (the listing is
                    one cheap request); only far-future price/sale-state refreshes
                    are deferred to the next full run. This is the main lever that
                    keeps Render egress bandwidth well under the free-tier cap.
    """
    light = (mode == "light")
    light_window = SCRAPER_LIGHT_WINDOW_DAYS if light else None
    # Heavy HTML adapters (xceed, nightleague) fetch one page per event, so we
    # only run them on full sweeps. FourVenues + ClubTickets are cheap enough to
    # run every light cycle (fast new-party / cartel-change detection).
    _light_adapters = {"fourvenues_api", "clubtickets"}
    venues = []
    async for v in db.scraped_venues.find({"active": True}, {"_id": 0}):
        if light and v.get("adapter_type") not in _light_adapters:
            continue
        venues.append(v)
    if not venues:
        return []
    batch_id = uuid.uuid4().hex
    # Cap how many venues scrape at the same time. Each venue can fire up to
    # ~120 ticket-detail requests, so running all of them at once would spike
    # CPU/memory and risk rate-limiting. 4 at a time is a safe compromise.
    _sem = asyncio.Semaphore(4)

    async def _run_one(v):
        async with _sem:
            return await run_scraper_for_venue(v, batch_id, detail_window_days=light_window)

    results = await asyncio.gather(*(_run_one(v) for v in venues), return_exceptions=False)
    total_new = sum(r["created"] for r in results)
    total_upd = sum(r["updated"] for r in results)
    logger.info(f"[scrapers] Completed ({mode}): {len(results)} venues, {total_new} new events, {total_upd} updated")
    # If any FourVenues venue is configured, verify the guest token is still
    # valid; if it expired, alert ONLY the admin (throttled) so parties keep flowing.
    try:
        if any(v.get("adapter_type") == "fourvenues_api" for v in venues):
            _tok = await _get_fourvenues_token()
            _valid = await _fourvenues_token_is_valid(_tok)
            if _valid is False:
                await _alert_admins_token_expired()
    except Exception:
        pass
    try:
        await db.app_settings.update_one(
            {"_id": "last_scrape_batch"},
            {"$set": {
                "batch_id": batch_id,
                "at": datetime.now(timezone.utc).isoformat(),
                "venues_run": len(results),
                "total_new": total_new,
                "total_updated": total_upd,
            }},
            upsert=True,
        )
    except Exception:
        pass
    try:
        await sync_scraper_venues_to_directory()
    except Exception:
        pass
    try:
        await enrich_venue_directory()
    except Exception:
        pass
    try:
        await sync_xceed_venues_to_directory()
    except Exception:
        pass
    try:
        await cleanup_old_events()
    except Exception:
        pass
    # Refresh which events are OURS (affiliate) so their ticket links use our
    # promoter link; everything else keeps its normal link.
    try:
        await refresh_affiliate_events()
    except Exception:
        pass
    # One grouped admin alert for all affiliate-link flips detected this run.
    try:
        await _notify_admins_affiliate_flips(batch_id)
    except Exception:
        pass
    # Grouped admin push when NEW at-risk buy links appear (so the owner can fix
    # them before anyone clicks a dead link) — runs AFTER refresh_affiliate_events.
    try:
        await _notify_admins_broken_links()
    except Exception:
        pass
    return results


async def run_scrapers_light():
    """Scheduler entrypoint: frequent, low-bandwidth refresh (see run_all_scrapers)."""
    return await run_all_scrapers(mode="light")


async def run_scrapers_full():
    """Scheduler entrypoint: full refresh of every adapter, a few times per day."""
    return await run_all_scrapers(mode="full")



# ---- Admin endpoints for scraper management ----
class ScrapedVenueInput(BaseModel):
    name: str
    city: str = "Palma de Mallorca"
    adapter_type: str      # 'fourvenues_api' | 'fourvenues_public_api' | 'nextjs_html'
    url: str
    slug: str = ""
    active: bool = True


class FourVenuesTokenInput(BaseModel):
    token: str


@app.get("/api/admin/scrapers/fourvenues-token")
async def admin_get_fv_token(admin: dict = Depends(require_admin)):
    """Return whether a FourVenues guest-token is configured (masked) and a
    live validity check against the API."""
    token = await _get_fourvenues_token()
    masked = ""
    if token:
        masked = f"{token[:12]}…{token[-6:]}" if len(token) > 24 else "configurado"
    valid = None
    if token:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(
                    "https://cli-api-service.fourvenues.com/api/microsites/amok/metadata",
                    headers={"Authorization": f"Bearer {token}",
                             "Origin": "https://site.fourvenues.com",
                             "User-Agent": "Mozilla/5.0"},
                )
            valid = r.status_code == 200
        except Exception:
            valid = None
    return {"configured": bool(token), "masked": masked, "valid": valid}


@app.put("/api/admin/scrapers/fourvenues-token")
async def admin_set_fv_token(inp: FourVenuesTokenInput, admin: dict = Depends(require_admin)):
    token = (inp.token or "").strip()
    if not token or token.count(".") != 2:
        raise HTTPException(status_code=400, detail="Token JWT inválido")
    await db.app_settings.update_one(
        {"key": "fourvenues_guest_token"},
        {"$set": {"key": "fourvenues_guest_token", "value": token,
                  "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    _FV_TOKEN_CACHE["val"] = None  # bust cache
    # Validate immediately.
    valid = None
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                "https://cli-api-service.fourvenues.com/api/microsites/amok/metadata",
                headers={"Authorization": f"Bearer {token}",
                         "Origin": "https://site.fourvenues.com",
                         "User-Agent": "Mozilla/5.0"},
            )
        valid = r.status_code == 200
    except Exception:
        valid = None
    return {"ok": True, "valid": valid}


@app.get("/api/admin/scrapers")
async def admin_list_scrapers(admin: dict = Depends(require_admin)):
    out = []
    async for v in db.scraped_venues.find({}, {"_id": 0}).sort("name", 1):
        out.append(v)
    return out


@app.get("/api/admin/scrape-changelog")
async def admin_scrape_changelog(limit: int = 80, admin: dict = Depends(require_admin)):
    """Recent scraper changes: new parties, price up/down, sale-state changes and
    sold-outs. Shows the LATEST changes across recent runs (not only the last one)
    so the admin keeps context, but capped so it never grows unbounded.
    Only visible to admin. Lightweight (indexed + capped)."""
    limit = max(1, min(limit, 200))
    last = await db.app_settings.find_one({"_id": "last_scrape_batch"}, {"_id": 0})
    entries = []
    # Show the most recent changes overall (across runs), newest first, capped.
    async for c in db.scrape_changelog.find({}, {"_id": 0}).sort("created_at", -1).limit(limit):
        entries.append(c)
    counts = {"new": 0, "price_up": 0, "price_down": 0, "state": 0, "sold_out": 0, "on_sale": 0, "renamed": 0, "affiliate_flip": 0}
    last_batch_id = (last or {}).get("batch_id")
    last_run_counts = dict(counts)
    for e in entries:
        k = e.get("kind")
        if k in counts:
            counts[k] += 1
        # Also tally just the latest run, so the UI can highlight "nuevo".
        if last_batch_id and e.get("batch_id") == last_batch_id and k in last_run_counts:
            last_run_counts[k] += 1
        # Flag entries from the latest run for the frontend badge.
        e["is_last_run"] = bool(last_batch_id and e.get("batch_id") == last_batch_id)
    return {
        "last_run": last,
        "counts": counts,
        "last_run_counts": last_run_counts,
        "total": len(entries),
        "entries": entries,
    }


@app.post("/api/admin/scrapers")
async def admin_create_scraper(inp: ScrapedVenueInput, admin: dict = Depends(require_admin)):
    if inp.adapter_type not in _ALLOWED_ADAPTERS:
        raise HTTPException(status_code=400, detail="adapter_type inválido")
    if inp.adapter_type == "fourvenues_api" and not (inp.slug or "").strip():
        # Try to derive from URL; if still empty, reject.
        from scrapers.fourvenues_api import FourVenuesApiScraper as _FV
        derived = _FV._slug_from_url(inp.url)
        if not derived:
            raise HTTPException(status_code=400, detail="Falta el 'slug' de FourVenues")
    doc = {
        "id": str(uuid.uuid4()),
        **inp.model_dump(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_run_at": None, "last_run_ok": None, "last_run_events": 0,
        "last_run_new": 0, "last_run_updated": 0, "last_run_error": None,
    }
    await db.scraped_venues.insert_one(doc)
    doc.pop("_id", None)
    return doc


@app.put("/api/admin/scrapers/{venue_id}")
async def admin_update_scraper(venue_id: str, inp: ScrapedVenueInput, admin: dict = Depends(require_admin)):
    if inp.adapter_type not in _ALLOWED_ADAPTERS:
        raise HTTPException(status_code=400, detail="adapter_type inválido")
    r = await db.scraped_venues.update_one({"id": venue_id}, {"$set": inp.model_dump()})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Venue no encontrado")
    v = await db.scraped_venues.find_one({"id": venue_id}, {"_id": 0})
    return v


@app.delete("/api/admin/scrapers/{venue_id}")
async def admin_delete_scraper(venue_id: str, admin: dict = Depends(require_admin)):
    r = await db.scraped_venues.delete_one({"id": venue_id})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Venue no encontrado")
    return {"ok": True}


@app.post("/api/admin/scrapers/{venue_id}/run")
async def admin_run_scraper(venue_id: str, admin: dict = Depends(require_admin)):
    v = await db.scraped_venues.find_one({"id": venue_id}, {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Venue no encontrado")
    return await run_scraper_for_venue(v)


@app.get("/api/admin/affiliate-status")
async def admin_affiliate_status(admin: dict = Depends(require_admin)):
    """How many scraped events currently match OUR affiliate profile (our slug).
    Only these events get our affiliate ticket link; the rest keep the normal one.
    Also reports, per venue, how many UPCOMING events actually show up MARKED in
    the app right now (real coverage) vs how many we carry per the RRPP link."""
    from datetime import datetime as _dt, timezone as _tz
    # Real coverage: count upcoming events in the DB that currently match as ours,
    # grouped by normalized venue name (join key with _AFFILIATE_VENUES).
    _today = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
    matched_by_venue: dict = {}
    total_matched = 0
    async for ev in db.events.find({"date": {"$gte": _today}},
                                   {"_id": 0, "venue": 1, "date": 1, "name": 1, "city": 1}):
        m = _affiliate_match(ev)
        if m:
            total_matched += 1
            matched_by_venue[m[1]] = matched_by_venue.get(m[1], 0) + 1
    venues_out = []
    for v in _AFFILIATE_VENUES:
        vv = dict(v)
        vv["matched"] = matched_by_venue.get(_norm_name(v.get("venue", "")), 0)
        venues_out.append(vv)
    # Surface venues we carry in a supported city but that show 0 marked events
    # (coverage gaps worth a look) first, then by carried volume.
    venues_out.sort(key=lambda x: (0 if (x.get("in_app") and not x.get("matched")) else 1,
                                   -x.get("events", 0), x.get("venue", "")))
    return {
        "slug": AFFILIATE_SLUG,
        "mine_count": len(_AFFILIATE_MAP),
        "matched_count": total_matched,
        "venues": venues_out,
        "updated_at": (_dt.fromtimestamp(_AFFILIATE_TS, _tz.utc).isoformat() if _AFFILIATE_TS else None),
    }


@app.post("/api/admin/affiliate-refresh")
async def admin_affiliate_refresh(admin: dict = Depends(require_admin)):
    """Manually re-read our affiliate events from FourVenues (also runs auto every 20 min)."""
    n = await refresh_affiliate_events()
    return {"slug": AFFILIATE_SLUG, "mine_count": n}


@app.get("/api/admin/clubtickets-coverage")
async def admin_clubtickets_coverage(admin: dict = Depends(require_admin), days: int = 120):
    """Coverage of OUR ClubTickets affiliate panel: for every party we carry (per
    club, per date) tell whether it is currently LIVE in the app through our ?aff
    link (matched) or MISSING (unmatched) — so the owner can spot parties we're
    leaving on the table. Matching is by the canonical (club, party, date) key of
    the buy link, so aff-code re-encoding never breaks it. Upcoming only."""
    from scrapers.clubtickets import get_panel_index, _INDEX_CACHE
    try:
        idx = await get_panel_index(CLUBTICKETS_LINKS_URL)
    except Exception:
        idx = {}
    today = datetime.now(ZoneInfo("Europe/Madrid")).date()
    horizon = (today + timedelta(days=max(1, min(days, 400)))).isoformat()
    today_s = today.isoformat()

    # club slug -> display name (from our seed venues: ct_slug or native slug).
    slug_name: dict = {}
    try:
        for v in _SEED_VENUES:
            ct = v.get("ct_slug") or (v.get("slug") if v.get("adapter_type") == "clubtickets" else None)
            if ct:
                slug_name[ct] = v.get("name", ct)
    except Exception:
        pass

    # DB index: upcoming events whose buy link is a clubtickets party URL.
    db_idx: dict = {}
    async for ev in db.events.find(
            {"date": {"$gte": today_s}},
            {"_id": 0, "id": 1, "name": 1, "venue": 1, "date": 1,
             "commission_url": 1, "price_tiers": 1, "sale_state": 1}):
        key = _ct_url_key(ev.get("commission_url", ""))
        if key:
            db_idx[key] = ev

    venues_out = []
    tot_parties = tot_matched = tot_price = 0
    for slug, parties in idx.items():
        rows = []
        for p in parties:
            d = p.get("date") or ""
            if not d or d < today_s or d > horizon:
                continue
            ev = db_idx.get((slug, p.get("event_slug") or "", d))
            matched = ev is not None
            has_price = bool(ev and ev.get("price_tiers"))
            rows.append({
                "name": p.get("name") or (p.get("event_slug") or "").replace("-", " ").title(),
                "date": d,
                "matched": matched,
                "has_price": has_price,
                "in_app_name": (ev or {}).get("name") if matched else None,
                "event_id": (ev or {}).get("id") if matched else None,
                "sale_state": (ev or {}).get("sale_state") if matched else None,
                "url": p.get("url") or "",
            })
        if not rows:
            continue
        rows.sort(key=lambda r: (r["date"], r["name"]))
        m = sum(1 for r in rows if r["matched"])
        pr = sum(1 for r in rows if r["has_price"])
        tot_parties += len(rows); tot_matched += m; tot_price += pr
        venues_out.append({
            "slug": slug,
            "name": slug_name.get(slug, slug.replace("-", " ").title()),
            "total": len(rows), "matched": m, "unmatched": len(rows) - m,
            "with_price": pr, "parties": rows,
        })
    venues_out.sort(key=lambda v: (-v["unmatched"], v["name"]))
    ts = _INDEX_CACHE.get("ts") or 0.0
    return {
        "aff_code": CLUBTICKETS_AFF,
        "updated_at": (datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts else None),
        "totals": {"parties": tot_parties, "matched": tot_matched,
                   "unmatched": tot_parties - tot_matched, "with_price": tot_price},
        "venues": venues_out,
    }


class AffiliateFlipAlertsInput(BaseModel):
    enabled: bool


@app.get("/api/admin/settings/affiliate-flip-alerts")
async def admin_get_affiliate_flip_alerts(admin: dict = Depends(require_admin)):
    """Whether admins get a grouped alert when parties change buy link
    affiliate<->direct after a re-scrape (ON by default)."""
    s = await db.app_settings.find_one({"key": "admin_affiliate_flip_alerts"}, {"_id": 0})
    enabled = not (s is not None and s.get("value") is False)
    return {"enabled": enabled}


@app.put("/api/admin/settings/affiliate-flip-alerts")
async def admin_set_affiliate_flip_alerts(inp: AffiliateFlipAlertsInput, admin: dict = Depends(require_admin)):
    await db.app_settings.update_one(
        {"key": "admin_affiliate_flip_alerts"},
        {"$set": {"key": "admin_affiliate_flip_alerts", "value": bool(inp.enabled),
                  "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"enabled": bool(inp.enabled)}


@app.get("/api/admin/settings/broken-link-alerts")
async def admin_get_broken_link_alerts(admin: dict = Depends(require_admin)):
    """Whether admins get a grouped push when NEW at-risk buy links appear
    (ON by default)."""
    s = await db.app_settings.find_one({"key": "admin_broken_link_alerts"}, {"_id": 0})
    enabled = not (s is not None and s.get("value") is False)
    return {"enabled": enabled}


@app.put("/api/admin/settings/broken-link-alerts")
async def admin_set_broken_link_alerts(inp: AffiliateFlipAlertsInput, admin: dict = Depends(require_admin)):
    await db.app_settings.update_one(
        {"key": "admin_broken_link_alerts"},
        {"$set": {"key": "admin_broken_link_alerts", "value": bool(inp.enabled),
                  "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"enabled": bool(inp.enabled)}


async def _matching_event_venue_names(venue: str) -> list:
    """All distinct event `venue` values that refer to the same physical club as
    `venue` (accent/word-subset aware). Used to move a club's events between
    cities when the admin reassigns it from the affiliate panel."""
    if not venue:
        return []
    names = []
    for vn in await db.events.distinct("venue"):
        if vn and _names_refer_same(vn, venue):
            names.append(vn)
    return names


class AffiliateSetCityInput(BaseModel):
    slug: str = ""
    venue: str = ""
    city: str  # a supported city id OR the PENDING_CITY sentinel


@app.post("/api/admin/affiliate/set-city")
async def admin_affiliate_set_city(inp: AffiliateSetCityInput, admin: dict = Depends(require_admin)):
    """Manually (re)assign the app-city of an affiliate club/venue.

    Works for BOTH the "Pendientes de añadir" list (club whose city wasn't
    auto-detected → pick the right one so it enters the app) and the "Ya en la
    app" list (move a club to another city, or send it back to "Pendiente" so it
    disappears from the feed until re-added). Persists the choice, moves the
    club's existing events, and syncs/creates the FourVenues scraper.
    """
    city = (inp.city or "").strip()
    if city != PENDING_CITY and city not in CITY_IDS:
        raise HTTPException(status_code=400, detail="Ciudad no válida")
    slug = (inp.slug or "").strip()
    venue = (inp.venue or "").strip()
    if not slug and not venue:
        raise HTTPException(status_code=400, detail="Falta el sitio (slug o nombre)")
    key = slug or _norm_name(venue)

    # 1) Persist the override (survives the 20-min affiliate refresh).
    await db.affiliate_city_overrides.update_one(
        {"key": key},
        {"$set": {"key": key, "slug": slug, "venue": venue, "city": city,
                  "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )

    # 2) Locate an existing scraper config for this club (by slug, then by name).
    cfg = None
    if slug:
        cfg = await db.scraped_venues.find_one({"slug": slug}, {"_id": 0})
    if not cfg and venue:
        async for v in db.scraped_venues.find({}, {"_id": 0}):
            if _names_refer_same(v.get("name", ""), venue):
                cfg = v
                break

    events_updated = 0
    scraper_action = "none"
    name_matches = await _matching_event_venue_names(venue) if venue else []

    if city == PENDING_CITY:
        # Send to pending: pause the scraper and hide its events from feeds.
        if cfg:
            await db.scraped_venues.update_one(
                {"id": cfg["id"]}, {"$set": {"active": False, "city": PENDING_CITY}})
            scraper_action = "paused"
            r = await db.events.update_many(
                {"scraper_venue_id": cfg["id"]}, {"$set": {"city": PENDING_CITY}})
            events_updated += r.modified_count
        if name_matches:
            r2 = await db.events.update_many(
                {"venue": {"$in": name_matches}}, {"$set": {"city": PENDING_CITY}})
            events_updated += r2.modified_count
    else:
        # Assign to a supported city: sync/create the scraper and move events.
        if cfg:
            await db.scraped_venues.update_one(
                {"id": cfg["id"]}, {"$set": {"city": city, "active": True}})
            scraper_action = "updated"
            r = await db.events.update_many(
                {"scraper_venue_id": cfg["id"]}, {"$set": {"city": city}})
            events_updated += r.modified_count
        elif slug:
            cfg = {
                "id": str(uuid.uuid4()), "name": venue or slug, "slug": slug, "city": city,
                "adapter_type": "fourvenues_api", "active": True,
                "url": f"https://site.fourvenues.com/es/{slug}",
                "auto_affiliate": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "last_run_at": None, "last_run_ok": None, "last_run_events": 0,
                "last_run_new": 0, "last_run_updated": 0, "last_run_error": None,
            }
            await db.scraped_venues.insert_one(cfg)
            scraper_action = "created"
        if name_matches:
            r2 = await db.events.update_many(
                {"venue": {"$in": name_matches}}, {"$set": {"city": city}})
            events_updated += r2.modified_count
        # Fetch this club's calendar in the background if we just created it.
        if cfg and scraper_action == "created":
            _c = dict(cfg)
            try:
                asyncio.create_task(run_scraper_for_venue(_c))
            except Exception:
                pass

    # 3) Reflect the change instantly in the in-memory affiliate panel data.
    try:
        for e in _AFFILIATE_VENUES:
            if (slug and e.get("slug") == slug) or e.get("key") == key:
                e["city"] = city
                e["override"] = True
                e["pending"] = (city == PENDING_CITY)
                e["in_app"] = (city in CITY_IDS)
    except Exception:
        pass

    _invalidate_stats_cache()
    return {"ok": True, "slug": slug, "venue": venue, "city": city,
            "events_updated": events_updated, "scraper": scraper_action}



@app.post("/api/admin/maintenance/cleanup-old-events")
async def admin_cleanup_old_events(admin: dict = Depends(require_admin)):
    """Run the stale-event cleanup on demand. Deletes ONLY old events nobody
    engaged with; preserves every event that is a memory (attendee/album/moment)."""
    res = await cleanup_old_events()
    return res or {"deleted": 0, "kept": 0, "old_total": 0}


class SignupAlertsInput(BaseModel):
    enabled: bool


@app.get("/api/admin/settings/signup-alerts")
async def admin_get_signup_alerts(admin: dict = Depends(require_admin)):
    """Whether admins get a notification on every new user signup (ON by default)."""
    s = await db.app_settings.find_one({"key": "admin_signup_alerts"}, {"_id": 0})
    enabled = not (s is not None and s.get("value") is False)
    return {"enabled": enabled}


@app.put("/api/admin/settings/signup-alerts")
async def admin_set_signup_alerts(inp: SignupAlertsInput, admin: dict = Depends(require_admin)):
    await db.app_settings.update_one(
        {"key": "admin_signup_alerts"},
        {"$set": {"key": "admin_signup_alerts", "value": bool(inp.enabled),
                  "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"enabled": bool(inp.enabled)}



@app.post("/api/admin/scrapers/run-all")
async def admin_run_all_scrapers(admin: dict = Depends(require_admin)):
    results = await run_all_scrapers()
    return {
        "venues_run": len(results),
        "total_new": sum(r["created"] for r in results),
        "total_updated": sum(r["updated"] for r in results),
        "results": results,
    }


# =========================================================================
# VENUE DIRECTORY — "Locales de Mallorca" (discotecas/pubs, con o sin FourVenues)
# =========================================================================
# order: Palma clubs first, then pueblos. type: discoteca|pub|beach_club|promotor
# open_days: 0=Lun ... 6=Dom. scraper_slug links to a FourVenues scraper (events).
_SEED_DIRECTORY = [
    # --- Palma / Paseo Marítimo (FourVenues) ---
    {"name": "Amok", "zone": "Palma · Marítimo", "city": "Palma de Mallorca", "type": "discoteca",
     "scraper_slug": "amok", "free_entry": False, "open_days": [2, 4, 5], "instagram": "amokmallorca",
     "address": "Camí Can Capó, 4, 07199 Palma"},
    {"name": "Fitz Mallorca", "zone": "Palma · Marítimo", "city": "Palma de Mallorca", "type": "discoteca",
     "scraper_slug": "fitz-mallorca", "free_entry": False, "open_days": [3, 4, 5], "instagram": "fitzmallorca",
     "address": "Passeig Marítim, Palma"},
    {"name": "Mar Salada", "zone": "Palma · Marítimo", "city": "Palma de Mallorca", "type": "discoteca",
     "scraper_slug": "mar-salada", "free_entry": False, "open_days": [4, 5], "instagram": "marsaladaclub",
     "address": "Passeig Marítim, Palma"},
    {"name": "Tabana", "zone": "Palma · Marítimo", "city": "Palma de Mallorca", "type": "discoteca",
     "scraper_slug": "tabana-mallorca", "free_entry": False, "open_days": [4, 5], "instagram": "tabanamallorca",
     "address": "Passeig Marítim, Palma"},
    {"name": "Velvet", "zone": "Palma · Porto Pi", "city": "Palma de Mallorca", "type": "discoteca",
     "scraper_slug": "velvet-club", "free_entry": False, "open_days": [4, 5], "instagram": "velvetclubpalma",
     "address": "Carrer de Porto Pi, 4, 07015 Palma"},
    {"name": "Over Club", "zone": "Palma", "city": "Palma de Mallorca", "type": "discoteca",
     "scraper_slug": "over-club", "free_entry": False, "open_days": [4, 5], "instagram": "overclubmallorca",
     "address": "Palma de Mallorca"},
    {"name": "Lunita", "zone": "Palma", "city": "Palma de Mallorca", "type": "discoteca",
     "scraper_slug": "lunita", "free_entry": False, "open_days": [4, 5, 6], "instagram": "discolunita",
     "address": "Palma de Mallorca"},
    {"name": "Luna Palma", "zone": "Palma", "city": "Palma de Mallorca", "type": "discoteca",
     "scraper_slug": "luna-palma", "free_entry": False, "open_days": [4, 5], "instagram": "",
     "address": "Palma de Mallorca"},
    {"name": "Boomerang", "zone": "Palma", "city": "Palma de Mallorca", "type": "discoteca",
     "scraper_slug": "boomerang", "free_entry": False, "open_days": [4, 5], "instagram": "",
     "address": "Carrer Gremi Teixidors, 27, 07009 Palma"},
    {"name": "Palma Events", "zone": "Palma", "city": "Palma de Mallorca", "type": "promotor",
     "scraper_slug": "palma-events", "free_entry": False, "open_days": [], "instagram": "palmaevents",
     "address": "Palma de Mallorca"},
    # --- Palma pubs / free ---
    {"name": "Shamrock", "zone": "Palma · Marítimo", "city": "Palma de Mallorca", "type": "pub",
     "scraper_slug": "", "free_entry": True, "open_days": [0, 1, 2, 3, 4, 5, 6], "instagram": "shamrockpalma",
     "address": "Passeig Marítim, 8, Palma"},
    {"name": "Garito Café", "zone": "Palma · Dàrsena", "city": "Palma de Mallorca", "type": "pub",
     "scraper_slug": "", "free_entry": True, "open_days": [3, 4, 5, 6], "instagram": "garitocafe",
     "address": "Dàrsena de Can Barbarà, Palma"},
    {"name": "Social Club", "zone": "Palma · Marítimo", "city": "Palma de Mallorca", "type": "discoteca",
     "scraper_slug": "", "free_entry": False, "open_days": [4, 5], "instagram": "socialclubmallorca",
     "address": "Passeig Marítim, Palma"},
    {"name": "Savage", "zone": "Palma · Marítimo", "city": "Palma de Mallorca", "type": "discoteca",
     "scraper_slug": "savage-mallorca", "free_entry": False, "open_days": [4, 5], "instagram": "savagemallorca",
     "address": "Passeig Marítim, Palma"},
    {"name": "Laos", "zone": "Palma · Marítimo", "city": "Palma de Mallorca", "type": "discoteca",
     "scraper_slug": "laos-club", "free_entry": False, "open_days": [4, 5], "instagram": "laosclub",
     "address": "Passeig Marítim, Palma"},
    {"name": "Enredo", "zone": "Palma · Marítimo", "city": "Palma de Mallorca", "type": "discoteca",
     "scraper_slug": "", "free_entry": False, "open_days": [4, 5], "instagram": "enredomallorca",
     "address": "Passeig Marítim, Palma"},
    {"name": "Brassclub", "zone": "Palma · Marítimo", "city": "Palma de Mallorca", "type": "pub",
     "scraper_slug": "", "free_entry": True, "open_days": [1, 2, 3, 4, 5], "instagram": "brassclub",
     "address": "Av. Gabriel Roca, 4, Palma"},
    # --- Magaluf / Calvià ---
    {"name": "BCM Planet Dance", "zone": "Magaluf", "city": "Magaluf", "type": "discoteca",
     "scraper_slug": "bcm-mallorca", "free_entry": False, "open_days": [1, 3, 4, 5], "instagram": "bcmplanetdance",
     "address": "Avinguda de l'Olivera, 14, 07181 Calvià"},
    {"name": "Tokio Joe's", "zone": "Magaluf", "city": "Magaluf", "type": "discoteca",
     "scraper_slug": "", "free_entry": True, "open_days": [0, 1, 2, 3, 4, 5, 6], "instagram": "tokiojoesmagaluf",
     "address": "Punta Ballena, Magaluf"},
    {"name": "Carwash NightClub", "zone": "Magaluf", "city": "Magaluf", "type": "discoteca",
     "scraper_slug": "", "free_entry": True, "open_days": [3, 4, 5, 6], "instagram": "carwashmagaluf",
     "address": "Punta Ballena, Magaluf"},
    # --- Alcúdia / Port d'Alcúdia ---
    {"name": "Banana Club", "zone": "Port d'Alcúdia", "city": "Alcúdia", "type": "discoteca",
     "scraper_slug": "", "free_entry": True, "open_days": [1, 3, 4, 5], "instagram": "bananaclubmallorca",
     "address": "Port d'Alcúdia (también Magaluf y Cala Rajada)"},
    {"name": "Menta Disco", "zone": "Port d'Alcúdia", "city": "Alcúdia", "type": "discoteca",
     "scraper_slug": "", "free_entry": False, "open_days": [], "instagram": "mentadisco",
     "address": "Port d'Alcúdia · (cerrada esta temporada)"},
    # --- Can Picafort ---
    {"name": "Danzû", "zone": "Can Picafort", "city": "Can Picafort", "type": "promotor",
     "scraper_slug": "danzu", "free_entry": False, "open_days": [4, 5], "instagram": "danzu.events",
     "address": "Can Picafort"},
    {"name": "Skau", "zone": "Can Picafort", "city": "Can Picafort", "type": "discoteca",
     "scraper_slug": "", "free_entry": True, "open_days": [4, 5, 6], "instagram": "skaudisco",
     "address": "Can Picafort"},
    {"name": "Charly's", "zone": "Can Picafort", "city": "Can Picafort", "type": "pub",
     "scraper_slug": "", "free_entry": True, "open_days": [0, 1, 2, 3, 4, 5, 6], "instagram": "",
     "address": "Can Picafort"},
    # --- Cala Rajada ---
    {"name": "Keops", "zone": "Cala Rajada", "city": "Cala Rajada", "type": "discoteca",
     "scraper_slug": "", "free_entry": True, "open_days": [3, 4, 5, 6], "instagram": "keopsclub",
     "address": "Cala Rajada"},
    {"name": "Angel's", "zone": "Cala Rajada", "city": "Cala Rajada", "type": "discoteca",
     "scraper_slug": "", "free_entry": True, "open_days": [4, 5, 6], "instagram": "",
     "address": "Cala Rajada"},
    # --- Santa Ponsa ---
    {"name": "Disco Inferno", "zone": "Santa Ponsa", "city": "Santa Ponsa", "type": "discoteca",
     "scraper_slug": "", "free_entry": True, "open_days": [4, 5, 6], "instagram": "",
     "address": "Santa Ponsa"},
    # --- Otros conocidos ---
    {"name": "Club Milano", "zone": "Mallorca", "city": "Mallorca", "type": "discoteca",
     "scraper_slug": "", "free_entry": False, "open_days": [4, 5], "instagram": "clubmilano",
     "address": "Mallorca"},
    # --- Nuevas discotecas (2026): FourVenues donde existe, si no link propio ---
    {"name": "Zar Society", "zone": "Palma · Marítimo", "city": "Palma de Mallorca", "type": "discoteca",
     "scraper_slug": "zar-mallorca", "free_entry": False, "open_days": [3, 4, 5], "instagram": "zarsociety",
     "buy_url": "https://zarsociety.es/", "address": "Av. Gabriel Roca 27, Palma"},
    {"name": "Selva Club", "zone": "Palma", "city": "Palma de Mallorca", "type": "discoteca",
     "scraper_slug": "", "free_entry": False, "open_days": [4, 5], "instagram": "selva.011",
     "buy_url": "https://www.selvaclub.com/", "address": "Palma de Mallorca"},
    {"name": "Kaelum Club", "zone": "Palma", "city": "Palma de Mallorca", "type": "discoteca",
     "scraper_slug": "", "free_entry": False, "open_days": [4, 5], "instagram": "kaelumclub",
     "buy_url": "https://ticketib.com/organizers/kaelum-club", "address": "Av. de l'Argentina 3, Palma"},
    {"name": "R33 (Wave Club)", "zone": "Palma", "city": "Palma de Mallorca", "type": "discoteca",
     "scraper_slug": "", "free_entry": False, "open_days": [4, 5], "instagram": "r33mallorca",
     "buy_url": "", "address": "Carrer Poima 24, Palma"},
    {"name": "Sala Luna", "zone": "Palma", "city": "Palma de Mallorca", "type": "discoteca",
     "scraper_slug": "", "free_entry": False, "open_days": [4, 5], "instagram": "",
     "buy_url": "", "address": "Palma de Mallorca"},
    {"name": "Living Music Club", "zone": "Palma", "city": "Palma de Mallorca", "type": "discoteca",
     "scraper_slug": "", "free_entry": False, "open_days": [4, 5], "instagram": "livingmusicclub",
     "buy_url": "", "address": "Palma de Mallorca"},
    {"name": "VIP GLAM 69", "zone": "Palma", "city": "Palma de Mallorca", "type": "discoteca",
     "scraper_slug": "", "free_entry": False, "open_days": [4, 5], "instagram": "",
     "buy_url": "", "address": "Palma de Mallorca"},
    {"name": "Times Square Music Club", "zone": "Palma", "city": "Palma de Mallorca", "type": "discoteca",
     "scraper_slug": "", "free_entry": False, "open_days": [4, 5], "instagram": "",
     "buy_url": "", "address": "Palma de Mallorca"},
    {"name": "Hello The Club", "zone": "Palma", "city": "Palma de Mallorca", "type": "discoteca",
     "scraper_slug": "", "free_entry": False, "open_days": [4, 5], "instagram": "",
     "buy_url": "", "address": "Palma de Mallorca"},
    {"name": "Club NL", "zone": "Palma", "city": "Palma de Mallorca", "type": "discoteca",
     "scraper_slug": "", "free_entry": False, "open_days": [4, 5], "instagram": "",
     "buy_url": "", "address": "Palma de Mallorca"},
    {"name": "La Nit", "zone": "Palma", "city": "Palma de Mallorca", "type": "discoteca",
     "scraper_slug": "", "free_entry": False, "open_days": [4, 5], "instagram": "",
     "buy_url": "", "address": "Palma de Mallorca"},
    # --- Magaluf ---
    {"name": "Galaxy", "zone": "Magaluf", "city": "Magaluf", "type": "discoteca",
     "scraper_slug": "galaxy-mallorca", "free_entry": False, "open_days": [3, 4, 5, 6], "instagram": "galaxymagaluf",
     "buy_url": "", "address": "Carrer Punta Ballena 7, Magaluf"},
    {"name": "Panama Jack", "zone": "Magaluf", "city": "Magaluf", "type": "discoteca",
     "scraper_slug": "panama-jack-magaluf", "free_entry": False, "open_days": [3, 4, 5, 6], "instagram": "panamajackmagaluf",
     "buy_url": "", "address": "Magaluf"},
    {"name": "Stereo", "zone": "Magaluf", "city": "Magaluf", "type": "discoteca",
     "scraper_slug": "", "free_entry": False, "open_days": [3, 4, 5, 6], "instagram": "stereomallorca",
     "buy_url": "https://stereomallorca.com/", "address": "Carrer Punta Ballena 2, Magaluf"},
    {"name": "Mansion", "zone": "Magaluf", "city": "Magaluf", "type": "discoteca",
     "scraper_slug": "", "free_entry": False, "open_days": [3, 4, 5, 6], "instagram": "mansionmallorca",
     "buy_url": "https://www.eventbrite.com/o/mansion-mallorca-58079932393", "address": "Magaluf"},
    {"name": "Night Flight", "zone": "Magaluf", "city": "Magaluf", "type": "discoteca",
     "scraper_slug": "", "free_entry": True, "open_days": [3, 4, 5, 6], "instagram": "",
     "buy_url": "", "address": "Magaluf"},
    # --- Playa de Palma / El Arenal (entrada gratis) ---
    {"name": "Mega-Park", "zone": "Playa de Palma", "city": "Palma de Mallorca", "type": "discoteca",
     "scraper_slug": "", "free_entry": True, "open_days": [0, 1, 2, 3, 4, 5, 6], "instagram": "megapark_official",
     "buy_url": "https://www.megapark.tv/", "address": "Carrer de l'Illa de Formentera, S'Arenal"},
    {"name": "Oberbayern", "zone": "Playa de Palma", "city": "Palma de Mallorca", "type": "discoteca",
     "scraper_slug": "", "free_entry": True, "open_days": [0, 1, 2, 3, 4, 5, 6], "instagram": "oberbayern_official",
     "buy_url": "", "address": "Carrer Miquel Pellisa, S'Arenal"},
    # --- Cala Rajada ---
    {"name": "Bell's Disco & Club", "zone": "Cala Rajada", "city": "Cala Rajada", "type": "discoteca",
     "scraper_slug": "", "free_entry": True, "open_days": [4, 5, 6], "instagram": "",
     "buy_url": "", "address": "Cala Rajada"},
    # --- Pubs (entrada libre, mismo horario cada semana) ---
    {"name": "Why Not?", "zone": "Palma", "city": "Palma de Mallorca", "type": "pub",
     "scraper_slug": "", "free_entry": True, "open_days": [3, 4, 5], "instagram": "",
     "buy_url": "", "address": "Palma de Mallorca"},
    {"name": "After Landing", "zone": "Palma", "city": "Palma de Mallorca", "type": "pub",
     "scraper_slug": "", "free_entry": True, "open_days": [4, 5, 6], "instagram": "",
     "buy_url": "", "address": "Palma de Mallorca"},
    {"name": "The Prince of Wales", "zone": "Palma", "city": "Palma de Mallorca", "type": "pub",
     "scraper_slug": "", "free_entry": True, "open_days": [0, 1, 2, 3, 4, 5, 6], "instagram": "",
     "buy_url": "", "address": "Palma de Mallorca"},
    {"name": "Goodfellas", "zone": "Magaluf", "city": "Magaluf", "type": "pub",
     "scraper_slug": "", "free_entry": True, "open_days": [0, 1, 2, 3, 4, 5, 6], "instagram": "",
     "buy_url": "", "address": "Magaluf"},
    {"name": "Legends", "zone": "Port d'Alcúdia", "city": "Alcúdia", "type": "pub",
     "scraper_slug": "", "free_entry": True, "open_days": [0, 1, 2, 3, 4, 5, 6], "instagram": "",
     "buy_url": "", "address": "Port d'Alcúdia"},
    # --- Beach clubs (fiesta de día · categoría propia) ---
    {"name": "Purobeach Palma", "zone": "Cala Estància", "city": "Palma de Mallorca", "type": "beach_club",
     "scraper_slug": "", "free_entry": False, "open_days": [0, 1, 2, 3, 4, 5, 6], "instagram": "purobeach",
     "buy_url": "https://purobeach.com/palma/", "open_time": "11:00", "close_time": "22:00",
     "address": "Carrer Pagell 1, Cala Estància, Palma"},
    {"name": "Nikki Beach Mallorca", "zone": "Magaluf", "city": "Calvià", "type": "beach_club",
     "scraper_slug": "", "free_entry": False, "open_days": [3, 4, 5, 6], "instagram": "nikkibeachmallorca",
     "buy_url": "https://mallorca.nikkibeach.com/", "open_time": "11:00", "close_time": "19:00",
     "address": "Avinguda Notari Alemany 1, Magaluf"},
    {"name": "Beso Beach Mallorca", "zone": "Ses Illetes", "city": "Palma de Mallorca", "type": "beach_club",
     "scraper_slug": "", "free_entry": False, "open_days": [0, 1, 2, 3, 4, 5, 6], "instagram": "besobeach",
     "buy_url": "https://besobeach.com/", "open_time": "12:00", "close_time": "20:00",
     "address": "Passeig d'Illetes 7, Illetes"},
    {"name": "UM Beach House Portals", "zone": "Portals Nous", "city": "Calvià", "type": "beach_club",
     "scraper_slug": "", "free_entry": False, "open_days": [0, 1, 2, 3, 4, 5, 6], "instagram": "umbeachhouse",
     "buy_url": "", "open_time": "11:00", "close_time": "21:00", "address": "Portals Nous, Calvià"},
    {"name": "Balneario Illetas", "zone": "Ses Illetes", "city": "Palma de Mallorca", "type": "beach_club",
     "scraper_slug": "", "free_entry": False, "open_days": [4, 5, 6], "instagram": "balnearioilletas",
     "buy_url": "", "open_time": "11:00", "close_time": "20:00", "address": "Passeig d'Illetes 52, Illetes"},
    {"name": "Mhares Sea Club", "zone": "Cala Blava", "city": "Llucmajor", "type": "beach_club",
     "scraper_slug": "", "free_entry": False, "open_days": [3, 4, 5, 6], "instagram": "mharesseaclub",
     "buy_url": "https://mharesseaclub.com/", "open_time": "12:00", "close_time": "22:00",
     "address": "Carretera Cala Blava, Llucmajor"},
    {"name": "Sa Gavina", "zone": "Portals Vells", "city": "Calvià", "type": "beach_club",
     "scraper_slug": "", "free_entry": False, "open_days": [0, 1, 2, 3, 4, 5, 6], "instagram": "",
     "buy_url": "", "open_time": "11:00", "close_time": "20:00", "address": "Portals Vells, Calvià"},
    {"name": "Savage Beach Club", "zone": "Palmanova", "city": "Calvià", "type": "beach_club",
     "scraper_slug": "", "free_entry": False, "open_days": [3, 4, 5, 6], "instagram": "savagebeachclub",
     "buy_url": "", "open_time": "12:00", "close_time": "21:00", "address": "Palmanova, Calvià"},
    {"name": "NU Beach Mallorca", "zone": "Palma", "city": "Palma de Mallorca", "type": "beach_club",
     "scraper_slug": "", "free_entry": False, "open_days": [4, 5, 6], "instagram": "nu_mallorca",
     "buy_url": "", "open_time": "12:00", "close_time": "22:00", "address": "Palma de Mallorca"},
    {"name": "Cala Gran Beach Club", "zone": "Cala d'Or", "city": "Santanyí", "type": "beach_club",
     "scraper_slug": "", "free_entry": False, "open_days": [0, 1, 2, 3, 4, 5, 6], "instagram": "",
     "buy_url": "", "open_time": "11:00", "close_time": "20:00", "address": "Cala d'Or, Santanyí"},

    # ============================================================
    # OTRAS CIUDADES — superclubs que NO usan FourVenues (directorio
    # con enlace de compra propio; visibles y monetizables. Las que
    # SÍ usan FourVenues están en _SEED_VENUES y se auto-actualizan).
    # ============================================================
    # --- IBIZA ---
    {"name": "Amnesia Ibiza", "zone": "Sant Rafel", "city": "Ibiza", "type": "discoteca",
     "scraper_slug": "", "free_entry": False, "open_days": [0, 1, 2, 3, 4, 5, 6], "instagram": "amnesiaibiza",
     "buy_url": "https://www.amnesia.es/", "address": "Ctra. Ibiza a San Antonio Km 5, Sant Rafel"},
    {"name": "Hï Ibiza", "zone": "Platja d'en Bossa", "city": "Ibiza", "type": "discoteca",
     "scraper_slug": "hi-ibiza", "free_entry": False, "open_days": [0, 1, 2, 3, 4, 5, 6], "instagram": "hiibizaofficial",
     "buy_url": "https://hiibiza.com/", "address": "Platja d'en Bossa, Sant Josep"},
    {"name": "Ushuaïa Ibiza", "zone": "Platja d'en Bossa", "city": "Ibiza", "type": "discoteca",
     "scraper_slug": "ushuaia-ibiza", "free_entry": False, "open_days": [0, 1, 2, 3, 4, 5, 6], "instagram": "ushuaiaibiza",
     "buy_url": "https://www.theushuaiaexperience.com/", "address": "Platja d'en Bossa 10, Sant Josep"},
    {"name": "[UNVRS]", "zone": "Ibiza", "city": "Ibiza", "type": "discoteca",
     "scraper_slug": "unvrs-ibiza", "free_entry": False, "open_days": [0, 1, 2, 3, 4, 5, 6], "instagram": "unvrs",
     "buy_url": "https://unvrs.com/", "address": "Ctra. Sant Josep, Ibiza"},
    {"name": "DC10", "zone": "Platja d'en Bossa", "city": "Ibiza", "type": "discoteca",
     "scraper_slug": "", "free_entry": False, "open_days": [0, 1], "instagram": "dc10ibiza",
     "buy_url": "https://dc10ibiza.com/", "address": "Ctra. Aeroport Km 1, Sant Josep"},
    # --- MADRID ---
    {"name": "Fabrik", "zone": "Humanes", "city": "Madrid", "type": "discoteca",
     "scraper_slug": "", "free_entry": False, "open_days": [5, 6], "instagram": "fabrikmadrid",
     "buy_url": "https://fabrik.es/", "address": "Av. de la Industria 82, Humanes de Madrid"},
    {"name": "Uñas Chung Lee", "zone": "Centro", "city": "Madrid", "type": "discoteca",
     "scraper_slug": "", "free_entry": False, "open_days": [4, 5], "instagram": "unaschunglee",
     "buy_url": "", "address": "Madrid"},
    {"name": "Goya Social Club", "zone": "Salamanca", "city": "Madrid", "type": "discoteca",
     "scraper_slug": "", "free_entry": False, "open_days": [3, 4, 5], "instagram": "goyasocialclub",
     "buy_url": "", "address": "C/ Goya, Madrid"},
    # --- BARCELONA ---
    {"name": "Pacha Barcelona", "zone": "Vila Olímpica", "city": "Barcelona", "type": "discoteca",
     "scraper_slug": "", "free_entry": False, "open_days": [4, 5], "instagram": "pachabarcelona",
     "buy_url": "https://pachabarcelona.es/", "address": "C/ Ramon Trias Fargas 2, Barcelona"},
    {"name": "Shôko Barcelona", "zone": "Barceloneta", "city": "Barcelona", "type": "discoteca",
     "scraper_slug": "", "free_entry": False, "open_days": [3, 4, 5, 6], "instagram": "shokobarcelona",
     "buy_url": "https://shoko.biz/", "address": "Passeig Marítim de la Barceloneta 36, Barcelona"},
    {"name": "Razzmatazz", "zone": "Poblenou", "city": "Barcelona", "type": "discoteca",
     "scraper_slug": "", "free_entry": False, "open_days": [4, 5], "instagram": "salarazzmatazz",
     "buy_url": "https://www.salarazzmatazz.com/", "address": "C/ Pamplona 88, Barcelona"},
    {"name": "Sala Apolo", "zone": "Paral·lel", "city": "Barcelona", "type": "discoteca",
     "scraper_slug": "", "free_entry": False, "open_days": [0, 1, 3, 4, 5, 6], "instagram": "sala_apolo",
     "buy_url": "https://www.sala-apolo.com/", "address": "C/ Nou de la Rambla 113, Barcelona"},
    {"name": "Input High Fidelity Dance Club", "zone": "Montjuïc", "city": "Barcelona", "type": "discoteca",
     "scraper_slug": "", "free_entry": False, "open_days": [5, 6], "instagram": "input_bcn",
     "buy_url": "", "address": "Av. Francesc Ferrer i Guàrdia, Barcelona"},
    # --- MARBELLA / PUERTO BANÚS ---
    {"name": "Olivia Valère", "zone": "Marbella", "city": "Marbella", "type": "discoteca",
     "scraper_slug": "", "free_entry": False, "open_days": [3, 4, 5], "instagram": "oliviavalere",
     "buy_url": "https://oliviavalere.com/", "address": "Ctra. de Istán Km 0.8, Marbella"},
    {"name": "La Suite Marbella", "zone": "Puente Romano", "city": "Marbella", "type": "discoteca",
     "scraper_slug": "", "free_entry": False, "open_days": [3, 4, 5], "instagram": "lasuitemarbella",
     "buy_url": "", "address": "Puente Romano Resort, Marbella"},
    {"name": "Momento Puerto Banús", "zone": "Puerto Banús", "city": "Marbella", "type": "discoteca",
     "scraper_slug": "", "free_entry": False, "open_days": [4, 5, 6], "instagram": "momentomarbella",
     "buy_url": "", "address": "Puerto Banús, Marbella"},
]


async def seed_venue_directory():
    """Idempotent seed of the 'venues' directory collection."""
    try:
        await db.venues.delete_many({"name": "Megasport"})
        for i, v in enumerate(_SEED_DIRECTORY):
            existing = await db.venues.find_one({"name": v["name"], "zone": v["zone"]})
            if existing:
                continue
            doc = {
                "id": str(uuid.uuid4()),
                "order": i,
                "active": True,
                "image_url": "",
                "description": "",
                **v,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.venues.insert_one(doc)
        logger.info(f"Seeded venue directory: {len(_SEED_DIRECTORY)} locales")
    except Exception as e:
        logger.warning(f"seed_venue_directory failed: {e}")


_ZONE_COORDS = {
    "Palma · Marítimo": (39.5628, 2.6289),
    "Palma · Porto Pi": (39.5556, 2.6217),
    "Palma · Dàrsena": (39.5606, 2.6300),
    "Palma": (39.5696, 2.6502),
    "Magaluf": (39.5089, 2.5330),
    "Port d'Alcúdia": (39.8386, 3.1206),
    "Can Picafort": (39.7656, 3.1568),
    "Cala Rajada": (39.7095, 3.4630),
    "Santa Ponsa": (39.5111, 2.4790),
    "Mallorca": (39.6953, 3.0176),
    # City centres — fallback for other-city venues without a curated coord.
    "Ibiza": (38.9089, 1.4328),
    "Madrid": (40.4239, -3.6997),
    "Barcelona": (41.3888, 2.1590),
    "Marbella": (36.4930, -4.9540),
}

# Curated real-world coordinates per venue (authoritative — overrides guesses).
_VENUE_COORDS = {
    "Amok": (39.5487, 2.6885),
    "Fitz Mallorca": (39.5695, 2.6318),
    "Mar Salada": (39.5683, 2.6278),
    "Tabana": (39.5689, 2.6298),
    "Velvet": (39.5556, 2.6210),
    "Over Club": (39.5668, 2.6262),
    "Lunita": (39.5722, 2.6352),
    "Luna Palma": (39.5718, 2.6345),
    "Boomerang": (39.5990, 2.7080),
    "Palma Events": (39.5701, 2.6500),
    "Shamrock": (39.5699, 2.6338),
    "Garito Café": (39.5602, 2.6208),
    "Social Club": (39.5686, 2.6288),
    "Savage": (39.5691, 2.6305),
    "Laos": (39.5693, 2.6312),
    "Enredo": (39.5685, 2.6282),
    "Brassclub": (39.5702, 2.6345),
    "BCM Planet Dance": (39.5091, 2.5320),
    "Tokio Joe's": (39.5096, 2.5332),
    "Carwash NightClub": (39.5094, 2.5338),
    "Banana Club": (39.8392, 3.1208),
    "Menta Disco": (39.8420, 3.1180),
    "Danzû": (39.7662, 3.1572),
    "Skau": (39.7658, 3.1560),
    "Charly's": (39.7665, 3.1580),
    "Keops": (39.7098, 3.4632),
    "Angel's": (39.7102, 3.4620),
    "Disco Inferno": (39.5115, 2.4795),
    "Club Milano": (39.6953, 3.0176),
    # --- Other cities (FourVenues clubs, geocoded) ---
    "Pacha Ibiza": (38.918441, 1.443315),
    "Lío Ibiza": (38.913783, 1.443104),
    "Es Paradis Ibiza": (38.978647, 1.307947),
    "Eden Ibiza": (38.97904, 1.307781),
    "Pikes Ibiza": (38.991108, 1.320141),
    "Chinois Ibiza": (38.916492, 1.441461),
    "Swag Ibiza": (38.891337, 1.408253),
    "Ibiza Rocks": (38.982881, 1.299883),
    "Bora Bora Ibiza": (38.889474, 1.405702),
    "Cova Santa Ibiza": (38.897831, 1.331792),
    "LuLa Club": (40.421235, -3.707137),
    "Chango Madrid": (40.431683, -3.698185),
    "Deseo (Nazca)": (40.434, -3.679),
    "Vandido": (40.4266, -3.7),
    "Green Social Club": (40.4245, -3.684),
    "Jowke Club": (40.42, -3.699),
    "Kube Madrid": (40.459781, -3.6918),
    "Teatro Kapital": (40.409774, -3.693224),
    "Teatro Barceló": (40.42702, -3.699712),
    "Sala Mon": (40.435766, -3.716496),
    "Opium Madrid": (40.437935, -3.692172),
    "Gabana": (40.421771, -3.684182),
    "Medias Puri": (40.412323, -3.703456),
    "Opium Barcelona": (41.385278, 2.19671),
    "Bling Bling BCN": (41.3934, 2.1497),
    "Costa Este BCN": (41.381918, 2.157767),
    "Downtown Barcelona": (41.381261, 2.114327),
    "Twenties Barcelona": (41.393612, 2.15801),
    "Sutton Barcelona": (41.395949, 2.151744),
    "Otto Zutz": (41.400109, 2.150382),
    "City Hall Barcelona": (41.387748, 2.168255),
    "Fitz Marbella": (36.4879, -4.9527),
    "Mirage Marbella": (36.5085, -4.8858),
    "Marina Beach Club": (36.4869, -4.956),
    "Opium Marbella": (36.4874, -4.9538),
    "Tibu Marbella": (36.488057, -4.953503),
    "Florida Park": (40.4148, -3.6795),
    "Luz de Gas": (41.3936, 2.149),
    # --- Other cities (non-FourVenues superclubs, geocoded) ---
    "Amnesia Ibiza": (38.94766, 1.408229),
    "Hï Ibiza": (38.885987, 1.403855),
    "Ushuaïa Ibiza": (38.885142, 1.405109),
    "[UNVRS]": (38.957901, 1.408304),
    "DC10": (38.88024, 1.392638),
    "Fabrik": (40.265301, -3.840565),
    "Uñas Chung Lee": (40.419996, -3.699015),
    "Goya Social Club": (40.425395, -3.688824),
    "Pacha Barcelona": (41.385749, 2.197042),
    "Shôko Barcelona": (41.385499, 2.196975),
    "Razzmatazz": (41.397278, 2.191076),
    "Sala Apolo": (41.374391, 2.169561),
    "Input High Fidelity Dance Club": (41.369441, 2.146997),
    "Olivia Valère": (36.505062, -4.940957),
    "La Suite Marbella": (36.503904, -4.925198),
    "Momento Puerto Banús": (36.48746, -4.9536),
}


async def migrate_midnight_events():
    """One-off (idempotent): shift already-stored scraped events at 00:00 to
    23:59 of the previous day, matching the new normalization. Only touches
    scraped events (external_id set) so manual placeholders aren't moved."""
    try:
        moved = 0
        cur = db.events.find(
            {"time": {"$in": ["00:00", "0:00", "00:00:00"]}, "external_id": {"$nin": [None, ""]}},
            {"_id": 0, "id": 1, "date": 1},
        )
        async for e in cur:
            try:
                new_date = (date.fromisoformat(e["date"]) - timedelta(days=1)).isoformat()
            except Exception:
                continue
            await db.events.update_one({"id": e["id"]}, {"$set": {"date": new_date, "time": "23:59"}})
            moved += 1
        if moved:
            logger.info(f"migrate_midnight_events: shifted {moved} events 00:00 -> prev day 23:59")
    except Exception as e:
        logger.warning(f"migrate_midnight_events failed: {e}")


async def sync_scraper_venues_to_directory():
    """Ensure every FourVenues scraped venue has a matching directory entry so it
    appears in Locales + Map for its city. Slugs already covered by a hand-curated
    entry (e.g. all of Mallorca) are skipped and never modified."""
    try:
        manual_slugs, auto_slugs = set(), set()
        async for v in db.venues.find({"scraper_slug": {"$nin": ["", None]}},
                                      {"_id": 0, "scraper_slug": 1, "auto_generated": 1}):
            s = v.get("scraper_slug")
            if not s:
                continue
            (auto_slugs if v.get("auto_generated") else manual_slugs).add(s)
        created = 0
        async for sv in db.scraped_venues.find({}, {"_id": 0}):
            slug = sv.get("slug")
            if not slug or slug in manual_slugs or slug in auto_slugs:
                continue
            city = sv.get("city") or "Palma de Mallorca"
            await db.venues.insert_one({
                "id": str(uuid.uuid4()),
                "name": sv["name"], "zone": city, "city": city, "type": "discoteca",
                "scraper_slug": slug, "free_entry": False, "open_days": [],
                "open_days_manual": False, "instagram": "", "buy_url": sv.get("url", ""),
                "open_time": "", "close_time": "", "address": "", "image_url": "",
                "description": "", "lat": None, "lng": None,
                "active": True, "order": 100, "auto_generated": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            auto_slugs.add(slug)
            created += 1
        if created:
            logger.info(f"sync_scraper_venues_to_directory: +{created} auto directory venues")
    except Exception as e:
        logger.warning(f"sync_scraper_venues_to_directory failed: {e}")


def _norm_name(s: str) -> str:
    """Accent/punctuation-insensitive key for venue-name matching."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


async def sync_xceed_venues_to_directory():
    """Create/refresh a Locale (directory) entry for each real venue behind Xceed
    events, using the geo embedded in the events, so they appear on the Map.
    Venues already covered by a curated / FourVenues locale are skipped."""
    try:
        existing = {}
        async for v in db.venues.find({"xceed_venue": {"$ne": True}},
                                      {"_id": 0, "name": 1, "city": 1}):
            existing.setdefault(v.get("city") or "", set()).add(_norm_name(v.get("name")))
        pipeline = [
            {"$match": {"external_id": {"$regex": "^xc:"}, "lat": {"$ne": None}}},
            {"$group": {"_id": {"venue": "$venue", "city": "$city"},
                        "lat": {"$first": "$lat"}, "lng": {"$first": "$lng"},
                        "img": {"$max": "$venue_image"}, "n": {"$sum": 1}}},
        ]
        created = updated = 0
        async for r in db.events.aggregate(pipeline):
            name = (r["_id"].get("venue") or "").strip()
            city = r["_id"].get("city") or ""
            if not name or not city:
                continue
            if _norm_name(name) in existing.get(city, set()):
                continue  # already a curated / FourVenues locale
            doc_set = {
                "name": name, "city": city, "zone": city, "type": "discoteca",
                "xceed_venue": True, "scraper_slug": "",
                "lat": r["lat"], "lng": r["lng"], "active": True,
            }
            if r.get("img"):
                doc_set["image_url"] = r["img"]
            found = await db.venues.find_one(
                {"xceed_venue": True, "name": name, "city": city}, {"_id": 0, "id": 1})
            if found:
                await db.venues.update_one({"id": found["id"]}, {"$set": doc_set})
                updated += 1
            else:
                await db.venues.insert_one({
                    "id": str(uuid.uuid4()),
                    "free_entry": False, "open_days": [], "open_days_manual": False,
                    "instagram": "", "buy_url": "", "open_time": "", "close_time": "",
                    "address": "", "description": "", "order": 100,
                    "auto_generated": True,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    **doc_set,
                })
                created += 1
        if created or updated:
            logger.info(f"sync_xceed_venues_to_directory: +{created} new, {updated} updated")
    except Exception as e:
        logger.warning(f"sync_xceed_venues_to_directory failed: {e}")


async def _xceed_venue_counts() -> dict:
    """Map (normalized venue name, city) -> count of upcoming Xceed events."""
    today = date.today().isoformat()
    counts = {}
    try:
        pipeline = [
            {"$match": {"external_id": {"$regex": "^xc:"}, "date": {"$gte": today}}},
            {"$group": {"_id": {"v": "$venue", "c": "$city"}, "n": {"$sum": 1}}},
        ]
        async for r in db.events.aggregate(pipeline):
            counts[(_norm_name(r["_id"].get("v")), r["_id"].get("c"))] = r["n"]
    except Exception:
        pass
    return counts


async def enrich_venue_directory():
    """Derive coords, cover image and opening days for directory venues from
    their scraped events. open_days is only auto-set when not manually edited."""
    try:
        slug_to_id = {}
        async for s in db.scraped_venues.find({}, {"_id": 0, "slug": 1, "id": 1}):
            if s.get("slug"):
                slug_to_id[s["slug"]] = s["id"]
        today = date.today().isoformat()
        async for v in db.venues.find({}):
            patch = {}
            sid = slug_to_id.get(v.get("scraper_slug") or "")
            # Coordinates: curated table is authoritative; else zone fallback + jitter.
            curated = _VENUE_COORDS.get(v.get("name"))
            if curated:
                if (v.get("lat"), v.get("lng")) != curated:
                    patch["lat"], patch["lng"] = curated
            elif v.get("lat") is None:
                base = _ZONE_COORDS.get(v.get("zone")) or _ZONE_COORDS["Mallorca"]
                h = int(hashlib.md5((v.get("name") or v["id"]).encode()).hexdigest(), 16)
                patch["lat"] = base[0] + ((h % 100) - 50) / 12000.0
                patch["lng"] = base[1] + (((h // 100) % 100) - 50) / 12000.0
            # Cover image
            if not v.get("image_url") and sid:
                e = await db.events.find_one({"scraper_venue_id": sid, "venue_image": {"$nin": ["", None]}},
                                             {"_id": 0, "venue_image": 1})
                if e and e.get("venue_image"):
                    patch["image_url"] = e["venue_image"]
            # Auto opening days from upcoming events (unless admin edited)
            if not v.get("open_days_manual") and sid:
                days = set()
                async for e in db.events.find({"scraper_venue_id": sid, "date": {"$gte": today}},
                                              {"_id": 0, "date": 1}):
                    try:
                        days.add(datetime.strptime(e["date"], "%Y-%m-%d").weekday())
                    except Exception:
                        pass
                if days:
                    patch["open_days"] = sorted(days)
            if patch:
                await db.venues.update_one({"id": v["id"]}, {"$set": patch})
    except Exception as e:
        logger.warning(f"enrich_venue_directory failed: {e}")


class VenueInput(BaseModel):
    name: str
    zone: str = "Mallorca"
    city: str = "Mallorca"
    type: str = "discoteca"          # discoteca | pub | beach_club | promotor
    scraper_slug: str = ""
    free_entry: bool = False
    open_days: List[int] = []
    open_days_manual: bool = False
    instagram: str = ""
    buy_url: str = ""                # external ticket page (non-FourVenues venues)
    open_time: str = ""             # e.g. "23:00" — informative opening hour
    close_time: str = ""            # e.g. "06:00"
    address: str = ""
    image_url: str = ""
    description: str = ""
    lat: Optional[float] = None
    lng: Optional[float] = None
    active: bool = True
    order: int = 100


class VenueReorderInput(BaseModel):
    venue_ids: List[str]


async def _venue_event_counts() -> dict:
    """Map scraper_venue_id -> count of upcoming events (date >= today)."""
    today = date.today().isoformat()
    counts = {}
    try:
        pipeline = [
            {"$match": {"date": {"$gte": today}, "scraper_venue_id": {"$ne": None}}},
            {"$group": {"_id": "$scraper_venue_id", "n": {"$sum": 1}}},
        ]
        async for r in db.events.aggregate(pipeline):
            counts[r["_id"]] = r["n"]
    except Exception:
        pass
    return counts


@app.get("/api/venues")
async def list_venues(response: Response, zone: str = None, type: str = None, user: dict = Depends(get_optional_user)):
    q = {"active": True, "city": city_query_value(user.get("city", "Palma de Mallorca"))}
    if zone:
        q["zone"] = zone
    if type:
        q["type"] = type
    venues = []
    async for v in db.venues.find(q, {"_id": 0}).sort([("order", 1), ("name", 1)]):
        venues.append(v)
    # link fourvenues slug -> scraper venue id -> upcoming events count
    slug_to_id = {}
    async for s in db.scraped_venues.find({}, {"_id": 0, "slug": 1, "id": 1}):
        if s.get("slug"):
            slug_to_id[s["slug"]] = s["id"]
    counts = await _venue_event_counts()
    xc_counts = await _xceed_venue_counts()
    # Which venues have at least one of OUR affiliate events (for silent priority
    # ordering — no visual marker). Only scanned when we actually carry events.
    affiliate_venue_ids: set = set()
    if _AFFILIATE_MAP:
        _today = date.today().isoformat()
        async for e in db.events.find(
            {"city": q["city"], "date": {"$gte": _today}, "external_id": {"$regex": "^fv:"}},
            {"_id": 0, "venue": 1, "date": 1, "name": 1, "scraper_venue_id": 1},
        ):
            if e.get("scraper_venue_id") and _event_is_mine(e):
                affiliate_venue_ids.add(e["scraper_venue_id"])
    for v in venues:
        if v.get("xceed_venue"):
            v["upcoming_events"] = xc_counts.get((_norm_name(v.get("name")), v.get("city")), 0)
            v["has_affiliate"] = False
        else:
            vid = slug_to_id.get(v.get("scraper_slug") or "")
            v["upcoming_events"] = counts.get(vid, 0) if vid else 0
            v["has_affiliate"] = bool(vid and vid in affiliate_venue_ids)
    # Silent revenue priority: venues with our affiliate events first, then the
    # rest in their existing (order, name) order. Stable sort keeps that order.
    venues.sort(key=lambda v: 0 if v.get("has_affiliate") else 1)
    # Venue directory changes rarely; a short private cache makes the Locales/Map
    # pages feel instant on repeat opens without ever showing another user's data.
    response.headers["Cache-Control"] = "private, max-age=120"
    return venues


@app.get("/api/venues/{venue_id}")
async def get_venue(venue_id: str, user: dict = Depends(get_optional_user)):
    v = await db.venues.find_one({"id": venue_id}, {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Local no encontrado")
    events = []
    slug = v.get("scraper_slug") or ""
    if v.get("xceed_venue"):
        today = date.today().isoformat()
        async for e in db.events.find(
            {"external_id": {"$regex": "^xc:"}, "venue": v.get("name"),
             "city": v.get("city"), "date": {"$gte": today}}, {"_id": 0}
        ).sort("date", 1).limit(30):
            events.append({
                "id": e["id"], "name": e["name"], "date": e["date"], "time": e.get("time", ""),
                "image_url": e.get("image_url", ""), "sale_state": e.get("sale_state"),
                "current_price": next((t.get("price") for t in (e.get("price_tiers") or []) if not t.get("sold_out")), None),
            })
    elif slug:
        sv = await db.scraped_venues.find_one({"slug": slug}, {"_id": 0, "id": 1})
        if sv:
            today = date.today().isoformat()
            async for e in db.events.find(
                {"scraper_venue_id": sv["id"], "date": {"$gte": today}}, {"_id": 0}
            ).sort("date", 1).limit(30):
                events.append({
                    "id": e["id"], "name": e["name"], "date": e["date"], "time": e.get("time", ""),
                    "image_url": e.get("image_url", ""), "sale_state": e.get("sale_state"),
                    "current_price": next((t.get("price") for t in (e.get("price_tiers") or []) if not t.get("sold_out")), None),
                })
    v["events"] = events
    v["upcoming_events"] = len(events)
    return v


@app.get("/api/venues/meta/zones")
async def venue_zones(user: dict = Depends(get_optional_user)):
    zones = await db.venues.distinct("zone", {"active": True, "city": city_query_value(user.get("city", "Palma de Mallorca"))})
    return {"zones": sorted(zones)}


@app.post("/api/admin/venues")
async def admin_create_venue(inp: VenueInput, admin: dict = Depends(require_admin)):
    doc = {"id": str(uuid.uuid4()), **inp.model_dump(),
           "created_at": datetime.now(timezone.utc).isoformat()}
    await db.venues.insert_one(doc)
    doc.pop("_id", None)
    return doc


@app.put("/api/admin/venues/reorder")
async def admin_reorder_venues(inp: VenueReorderInput, admin: dict = Depends(require_admin)):
    """Set the club-importance priority in one shot. Receives the venue ids in the
    desired order (top = most important) and stores order = position. This is the
    "Prioridad de discotecas" list the owner can rearrange anytime; the feed uses
    it right below our own affiliate events."""
    n = 0
    for i, vid in enumerate(inp.venue_ids):
        r = await db.venues.update_one({"id": vid}, {"$set": {"order": i}})
        n += r.matched_count
    return {"ok": True, "updated": n}


@app.put("/api/admin/venues/{venue_id}")
async def admin_update_venue(venue_id: str, inp: VenueInput, admin: dict = Depends(require_admin)):
    data = inp.model_dump()
    data["open_days_manual"] = True  # admin took control of opening days
    r = await db.venues.update_one({"id": venue_id}, {"$set": data})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Local no encontrado")
    return await db.venues.find_one({"id": venue_id}, {"_id": 0})


@app.delete("/api/admin/venues/{venue_id}")
async def admin_delete_venue(venue_id: str, admin: dict = Depends(require_admin)):
    r = await db.venues.delete_one({"id": venue_id})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Local no encontrado")
    return {"ok": True}


# =========================================================================
# HEALTH CHECK — public endpoint for keep-alive pings (cron-job.org / UptimeRobot)
# Kept ultra-lightweight: no DB call, just proves the process is up.
# =========================================================================
@app.get("/api/health")
async def health():
    return {"ok": True, "ts": datetime.now(timezone.utc).isoformat()}


@app.get("/health")
async def health_root():
    return {"ok": True}


# GZip compression: shrinks JSON responses ~5-10x on the wire.
# Only compress payloads >= 500 bytes (small responses aren't worth CPU).
app.add_middleware(GZipMiddleware, minimum_size=500)


# ---------------------------------------------------------------------------
# Security: hardening headers + lightweight brute-force protection on auth.
# A public app must look and behave "serious": no clickjacking, no MIME
# sniffing, a strict referrer policy, and abuse throttling on credentials.
# ---------------------------------------------------------------------------
_RATE_BUCKET: dict = {}          # ip+path -> [timestamps]
_RATE_LIMITS = {                 # path suffix -> (max_hits, window_seconds)
    "/api/auth/login": (12, 60),
    "/api/auth/register": (8, 300),
    "/api/auth/google/callback": (20, 60),
    "/api/auth/apple/callback": (20, 60),
}


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    # --- brute-force / abuse throttle on sensitive auth endpoints ---
    path = request.url.path
    limit = _RATE_LIMITS.get(path)
    if limit and request.method == "POST":
        max_hits, window = limit
        ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
              or (request.client.host if request.client else "?"))
        key = f"{ip}:{path}"
        now = time.time()
        hits = [t for t in _RATE_BUCKET.get(key, []) if now - t < window]
        if len(hits) >= max_hits:
            return StarletteResponse(
                content=json.dumps({"detail": "Demasiados intentos. Espera un momento e inténtalo de nuevo."}),
                status_code=429,
                media_type="application/json",
            )
        hits.append(now)
        _RATE_BUCKET[key] = hits
        # keep the bucket from growing unbounded
        if len(_RATE_BUCKET) > 5000:
            _RATE_BUCKET.clear()

    response = await call_next(request)

    # --- hardening headers on every response ---
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(self), camera=(self), microphone=()"
    response.headers["X-XSS-Protection"] = "0"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


_cors_env = os.environ.get('CORS_ORIGINS', '*').strip()
# Native app shells (Capacitor iOS/Android WebView) load from these origins and
# must ALWAYS be allowed, regardless of the CORS_ORIGINS allowlist — otherwise
# the mobile app's API calls are blocked by CORS. (iosScheme "https" → https://localhost)
_NATIVE_APP_ORIGINS = ["https://localhost", "capacitor://localhost", "ionic://localhost"]
if _cors_env == '*':
    # Wildcard + credentials is invalid per spec — use regex to echo the origin back.
    app.add_middleware(
        CORSMiddleware,
        allow_credentials=True,
        allow_origin_regex=".*",
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    _origins = [o.strip() for o in _cors_env.split(',') if o.strip()] + _NATIVE_APP_ORIGINS
    app.add_middleware(
        CORSMiddleware,
        allow_credentials=True,
        allow_origins=_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
