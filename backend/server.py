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
import secrets
import requests
import re
import unicodedata
import json
import asyncio
from datetime import datetime, timezone, timedelta, date, time as dtime
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pywebpush import webpush, WebPushException
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


def _event_is_mine(ev: dict) -> bool:
    """True only if this event is one WE carry in our promoter profile (exact or
    venue-alias). Only those get our affiliate link; everything else keeps its
    normal link so checkout never breaks."""
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


def _fv_event_code(url: str) -> str:
    """The trailing FourVenues event code (e.g. .../events/127U -> '127U')."""
    if not url:
        return ""
    m = _FV_CODE_RE.search(url.split("?")[0].rstrip("/"))
    return m.group(1) if m else ""


def _commission_url_for(ev: dict) -> str:
    """The ticket link served to buyers: OUR affiliate link ONLY for events we
    carry; otherwise the original untouched link. We use the canonical code-based
    microsite URL (site.fourvenues.com/es/<affiliate>/events/<code>) — the exact
    format the affiliate microsite itself links to, so it resolves INSTANTLY. (The
    pretty name-date-code URL is SSR-generated on demand and 404s for ~1 min until
    FourVenues caches it.)"""
    m = _affiliate_match(ev)
    if m:
        # Prefer the code from the event's own (already-working) scraped ticket
        # link; fall back to the code captured from the affiliate feed.
        code = _fv_event_code(ev.get("commission_url", "")) or (m[0] or "")
        if code:
            return f"https://site.fourvenues.com/es/{AFFILIATE_SLUG}/events/{code}"
    return ev.get("commission_url", "") or ""


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
        "city_change_alerts": bool(u.get("city_change_alerts", True)),
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
    return {"cities": SUPPORTED_CITIES}


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
                    "puerto-banus": "Marbella", "eivissa": "Ibiza"})


def _price_line(ev: dict) -> str:
    tiers = ev.get("price_tiers") or []
    prices = [t.get("price") for t in tiers if isinstance(t, dict) and t.get("price")]
    if ev.get("sale_state") == "agotado":
        return "Agotado"
    if prices:
        return f"desde {int(min(prices))}\u20ac"
    return ""


def _frontend_base(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    base = f"{proto}://{host}"
    return (os.environ.get("FRONTEND_URL") or "").strip().rstrip("/") or base


async def _upcoming_for_city(city_id: str, limit: int = 60) -> list:
    today = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
    cur = db.events.find(
        {"city": city_query_value(city_id), "date": {"$gte": today}},
        {"_id": 0, "id": 1, "name": 1, "venue": 1, "date": 1, "city": 1,
         "image_url": 1, "price_tiers": 1, "sale_state": 1},
    ).sort("date", 1).limit(limit)
    return [e async for e in cur]


@api_router.get("/ciudad/{slug}")
async def seo_city_page(slug: str, request: Request):
    """Server-rendered, crawlable page: 'Fiestas en {ciudad} hoy y este finde'.
    Real HTML content (no JS needed) so Google can index it; links push users
    into the app. Meant to be served on the main domain via a Vercel rewrite
    (/fiestas/:city -> {backend}/api/ciudad/:city)."""
    import html as _html
    e = _html.escape
    city_id = _CITY_SLUGS.get(slug.lower())
    front = _frontend_base(request)
    if not city_id:
        return StarletteResponse(
            content=f"<!doctype html><meta http-equiv=refresh content='0;url={front}/feed'>",
            media_type="text/html", status_code=404)
    events = await _upcoming_for_city(city_id)
    label = next((c["label"] for c in SUPPORTED_CITIES if c["id"] == city_id), city_id)
    canonical = f"{front}/fiestas/{slug.lower()}"
    n = len(events)
    title = e(f"Fiestas y discotecas en {label} hoy y este fin de semana | \u00bfQui\u00e9n va?")
    desc = e(f"Todas las fiestas de {label}: {n} planes con horarios, precios y qu\u00e9 amigos van. "
             f"Descubre las discotecas de esta semana en \u00bfQui\u00e9n va?")
    og_img = ""
    for ev in events:
        if ev.get("image_url", "").startswith("http"):
            og_img = e(ev["image_url"]); break

    items_html = []
    for ev in events:
        pl = _price_line(ev)
        line2 = " \u00b7 ".join([x for x in [e(ev.get("venue", "")), _es_share_date(ev.get("date", "")), e(pl)] if x])
        app_url = f"{front}/event/{ev.get('id')}"
        img = ev.get("image_url", "")
        img_tag = f'<img src="{e(img)}" alt="{e(ev.get("name",""))}" loading="lazy" width="72" height="72">' if img.startswith("http") else ""
        items_html.append(
            f'<li><a href="{e(app_url)}">{img_tag}<div><span class="n">{e(ev.get("name","Fiesta"))}</span>'
            f'<span class="m">{line2}</span></div></a></li>')
    if not items_html:
        items_html.append('<li class="empty">Pronto publicaremos las pr\u00f3ximas fiestas de esta ciudad.</li>')

    other_cities = "".join(
        f'<a href="{front}/fiestas/{_slugify(c["id"])}">{e(c["label"])}</a>'
        for c in SUPPORTED_CITIES if c["id"] != city_id)

    html_out = f"""<!doctype html>
<html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{e(canonical)}">
<meta property="og:type" content="website"><meta property="og:site_name" content="\u00bfQui\u00e9n va?">
<meta property="og:title" content="{title}"><meta property="og:description" content="{desc}">
<meta property="og:url" content="{e(canonical)}">
{f'<meta property="og:image" content="{og_img}">' if og_img else ''}
<meta name="twitter:card" content="summary_large_image">
<style>
:root{{color-scheme:dark}}
body{{margin:0;background:#0a0a0c;color:#fff;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;line-height:1.5}}
.wrap{{max-width:720px;margin:0 auto;padding:24px 18px 60px}}
h1{{font-size:26px;margin:12px 0 6px}}
p.sub{{color:#a1a1aa;margin:0 0 22px}}
ul{{list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:10px}}
li a{{display:flex;gap:12px;align-items:center;background:#141417;border:1px solid #26262b;border-radius:14px;padding:10px 12px;text-decoration:none;color:#fff}}
li img{{border-radius:10px;object-fit:cover;flex:0 0 auto}}
.n{{display:block;font-weight:700}}
.m{{display:block;color:#a1a1aa;font-size:14px}}
.empty{{color:#a1a1aa;padding:20px;text-align:center}}
.cta{{display:inline-block;margin:22px 0;background:linear-gradient(90deg,#00f0ff,#7c3aed);color:#001014;font-weight:800;padding:12px 20px;border-radius:999px;text-decoration:none}}
.cities{{margin-top:34px;border-top:1px solid #26262b;padding-top:18px}}
.cities a{{color:#00f0ff;margin-right:14px;text-decoration:none;display:inline-block;margin-bottom:8px}}
footer{{margin-top:30px;color:#71717a;font-size:13px}}
</style></head>
<body><div class="wrap">
<h1>Fiestas en {e(label)} hoy y este fin de semana</h1>
<p class="sub">{n} planes esta semana \u00b7 horarios, precios y qu\u00e9 amigos van. Con \u00bfQui\u00e9n va?</p>
<a class="cta" href="{front}/feed">Abrir \u00bfQui\u00e9n va?</a>
<ul>{''.join(items_html)}</ul>
<div class="cities"><b>Otras ciudades:</b><br>{other_cities}</div>
<footer>\u00bfQui\u00e9n va? \u2014 descubre los planes del finde y mira qu\u00e9 amigos van a cada sitio.</footer>
</div></body></html>"""
    return StarletteResponse(content=html_out, media_type="text/html; charset=utf-8",
                             headers={"Cache-Control": "public, max-age=1800"})


@api_router.get("/sitemap.xml")
async def seo_sitemap(request: Request):
    front = _frontend_base(request)
    urls = [f"{front}/", f"{front}/feed"]
    urls += [f"{front}/fiestas/{_slugify(c['id'])}" for c in SUPPORTED_CITIES]
    today = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
    body = "".join(f"<url><loc>{u}</loc><lastmod>{today}</lastmod><changefreq>daily</changefreq></url>" for u in urls)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>'
    return StarletteResponse(content=xml, media_type="application/xml",
                             headers={"Cache-Control": "public, max-age=3600"})


@api_router.get("/robots.txt")
async def seo_robots(request: Request):
    front = _frontend_base(request)
    txt = f"User-agent: *\nAllow: /\nSitemap: {front}/sitemap.xml\n"
    return StarletteResponse(content=txt, media_type="text/plain",
                             headers={"Cache-Control": "public, max-age=3600"})


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
        "city_change_alerts": True,
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
            "city_change_alerts": True,
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
    for raw in inp.phones[:2000]:
        h = phone_hash(raw)
        if h:
            hashes.add(h)
    if not hashes:
        return []
    fmap = await friendship_status_map(user["user_id"])
    my_friends = await accepted_friend_ids(user["user_id"])
    blocked = await blocked_relation_ids(user["user_id"])
    out = []
    async for u in db.users.find({"phone_hash": {"$in": list(hashes)}}, {"_id": 0}).limit(100):
        if u["user_id"] == user["user_id"] or u["user_id"] in blocked:
            continue
        rel = fmap.get(u["user_id"])
        if rel and rel.get("status") == "accepted":
            continue  # already friends
        pu = public_other_user(u)
        pu["relationship"] = rel or {"status": "none"}
        pu["mutual_count"] = await mutual_friends_count(my_friends, u["user_id"])
        out.append(pu)
    return out



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
        # Admin-only flag so the owner can spot their affiliate events in the feed.
        # Sent as null to everyone else → no marker, no info leak.
        "is_affiliate": (_event_is_mine(ev) if (user or {}).get("role") == "admin" else None),
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
    filtered_events = []
    async for ev in db.events.find(query, {"_id": 0}).sort("date", sort_dir):
        if not date_in_filter(ev["date"], date_filter):
            continue
        if genre != "all" and ev.get("genre") != genre:
            continue
        filtered_events.append(ev)

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
        # affiliate events always come first, so the remaining keys are only ever
        # compared WITHIN the same tier (Python stops at the first differing key).
        #   • OUR events (tier 0): most EXPENSIVE first (higher price ≈ higher
        #     commission / better club), then soonest date. (padding keeps equal shape)
        #   • Everyone else (tier 1): club importance → featured → popularity → date.
        def _feed_sort_key(e):
            if _event_is_mine(e):
                return (0, -_price_for_sort(e), e.get("date", ""), 0, 0.0)
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
    """The upcoming event (next 7 days) where the most of your friends are going."""
    friend_ids = await accepted_friend_ids(user["user_id"])
    today = datetime.now(ZoneInfo("Europe/Madrid")).date()
    week_end = today + timedelta(days=7)
    best = None
    best_count = 0
    async for ev in db.events.find({"city": city_query_value(_effective_city(user, city))}, {"_id": 0}).sort("date", 1):
        try:
            d = date.fromisoformat(ev["date"])
        except Exception:
            continue
        if not (today <= d <= week_end):
            continue
        se = await serialize_event(ev, user, friend_ids)
        c = len(se["friends_going"])
        if c > best_count:
            best_count = c
            best = se
    return best


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
    """When a new event is created, notify all users in the same app-city
    (region-aware: e.g. a Magaluf event notifies Palma de Mallorca users)."""
    region = region_for_city(event.get("city") or "Palma de Mallorca")
    body = f"🆕 Nueva fiesta: {event['name']} · {event.get('venue', '')} ({event['date']})"
    count = 0
    async for u in db.users.find({"city": region}, {"_id": 0, "user_id": 1}):
        await create_notification(
            u["user_id"], "new_event", body,
            {"event_id": event["id"], "type": "new_event"},
        )
        count += 1
    logger.info(f"[notify] new_event {event['id']} → {count} users in {region}")
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
async def admin_events_min(admin: dict = Depends(require_admin), q: str = Query("")):
    """Lightweight event list for the notification dropdown (id/name/venue/date).
    Fast: single projected query, no per-event counts."""
    query = {}
    if q:
        query = {"name": {"$regex": q, "$options": "i"}}
    out = []
    async for ev in db.events.find(query, {"_id": 0, "id": 1, "name": 1, "venue": 1, "date": 1, "sale_state": 1}).sort("date", -1).limit(500):
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
DEFAULT_NOTIF_PREFS = {k: True for k in _NOTIF_PREF_KEYS}


async def create_notification(user_id: str, ntype: str, message: str, data: dict):
    # Respect per-user notification preferences for gated categories.
    if ntype in _NOTIF_PREF_KEYS:
        u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "notif_prefs": 1})
        prefs = (u or {}).get("notif_prefs") or {}
        if prefs.get(ntype) is False:
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
    if not VAPID_PRIVATE_KEY:
        return
    payload = json.dumps({"title": title, "body": body, "url": url})
    subs = []
    async for s in db.push_subscriptions.find({"user_id": user_id}):
        subs.append(s)
    for s in subs:
        dead = await asyncio.to_thread(_sync_web_push, s, payload)
        if dead and dead != "err":
            await db.push_subscriptions.delete_one({"endpoint": dead})


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
    return {"subscribed": count > 0}


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
    return out


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
    # One-time migration: enable city-wide change alerts by default for everyone
    # (owner requested it ON by default). Idempotent via a settings flag so it
    # only runs once and never re-flips users who later opt out.
    try:
        _flag = await db.app_settings.find_one({"key": "city_alerts_default_on_v1"}, {"_id": 0})
        if not _flag:
            res = await db.users.update_many(
                {"city_change_alerts": {"$ne": True}},
                {"$set": {"city_change_alerts": True}},
            )
            await db.app_settings.update_one(
                {"key": "city_alerts_default_on_v1"},
                {"$set": {"key": "city_alerts_default_on_v1", "value": True,
                          "migrated": getattr(res, "modified_count", 0),
                          "at": datetime.now(timezone.utc).isoformat()}},
                upsert=True,
            )
            logger.info(f"[migration] city_change_alerts default ON → {getattr(res,'modified_count',0)} users updated")
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
        # Scrapers — refresh all active venues every 30 min. First run 60s after
        # startup so a fresh deploy warms up the events feed quickly.
        scheduler.add_job(run_all_scrapers, "interval", minutes=20,
                          id="scrapers_all", replace_existing=True,
                          max_instances=1, coalesce=True, misfire_grace_time=300,
                          next_run_time=datetime.now(timezone.utc) + timedelta(seconds=60))
        scheduler.add_job(refresh_affiliate_events, "interval", minutes=20,
                          id="affiliate_refresh", replace_existing=True,
                          max_instances=1, coalesce=True, misfire_grace_time=300,
                          next_run_time=datetime.now(timezone.utc) + timedelta(seconds=25))
        scheduler.start()
        logger.info("Scheduler iniciado (digest viernes + recordatorios 30min + recuerdo lunes 12:00 + momentos auto cada 10min + randomizador diario 18:00 + scrapers cada 20min)")
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

_ALLOWED_ADAPTERS = ("fourvenues_api", "fourvenues_public_api", "nextjs_html", "nightleague")

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


async def _auto_seed_affiliate_clubs(org_seed: dict) -> int:
    """Ensure every club we carry (from our RRPP link) that sits in a SUPPORTED
    city has its own FourVenues scraper, so its events show up in the feed, get
    the 'Mi link' marker and rank first — WITHOUT us hand-adding each new club.
    Deduped by slug AND by name (so we never duplicate a club already scraped).
    org_seed: {org_slug: [org_name, {app_city: count}]}. Returns how many added."""
    if not org_seed:
        return 0
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
            if not city_counts:
                continue
            city = max(city_counts.items(), key=lambda kv: kv[1])[0]
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
                    if org_slug:
                        all_orgs[org_slug] = venue or org_slug
                        app_city = _supported_city_for(addr)
                        if app_city:
                            rec = org_seed.setdefault(org_slug, [venue or org_slug, {}])
                            rec[1][app_city] = rec[1].get(app_city, 0) + 1
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
        _AFFILIATE_VENUES = sorted(
            [{"venue": v, "city": c, "events": n, "in_app": _city_in_app(c)}
             for (v, c), n in venue_agg.items()],
            key=lambda x: (-x["events"], x["venue"]),
        )
        _AFFILIATE_TS = time.time()
        logger.info(f"[affiliate] '{AFFILIATE_SLUG}' → {len(amap)} events across {len(_AFFILIATE_VENUES)} venues are mine")
        # Self-maintaining coverage: create a scraper for any carried club in a
        # supported city that we don't already scrape (deduped by slug + name).
        await _auto_seed_affiliate_clubs(org_seed)
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
    {"name": "Lío Ibiza", "slug": "lio-ibiza", "city": "Ibiza",
     "url": "https://site.fourvenues.com/es/lio-ibiza"},
    {"name": "Es Paradis Ibiza", "slug": "es-paradis-ibiza", "city": "Ibiza",
     "url": "https://site.fourvenues.com/es/es-paradis-ibiza"},
    {"name": "Eden Ibiza", "slug": "eden-ibiza", "city": "Ibiza",
     "url": "https://site.fourvenues.com/es/eden-ibiza"},
    {"name": "Pikes Ibiza", "slug": "pikes-ibiza", "city": "Ibiza",
     "url": "https://site.fourvenues.com/es/pikes-ibiza"},
    {"name": "Chinois Ibiza", "slug": "chinois-ibiza", "city": "Ibiza",
     "url": "https://site.fourvenues.com/es/chinois-ibiza"},
    {"name": "Swag Ibiza", "slug": "swag-ibiza", "city": "Ibiza",
     "url": "https://site.fourvenues.com/es/swag-ibiza"},
    {"name": "Ibiza Rocks", "slug": "ibiza-rocks", "city": "Ibiza",
     "url": "https://site.fourvenues.com/es/ibiza-rocks"},
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
     "url": "https://www.theushuaiaexperience.com/club/en"},
    {"name": "Hï Ibiza", "slug": "hi-ibiza", "city": "Ibiza",
     "adapter_type": "nightleague",
     "url": "https://www.hiibiza.com/es"},
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
        for v in _SEED_VENUES:
            existing = await db.scraped_venues.find_one({"name": v["name"]})
            if existing:
                # Backfill slug if missing (older docs).
                if not existing.get("slug") and v.get("slug"):
                    await db.scraped_venues.update_one(
                        {"id": existing.get("id")}, {"$set": {"slug": v["slug"]}})
                continue
            doc = {**v, "id": str(uuid.uuid4()), "created_at": datetime.now(timezone.utc).isoformat(),
                   "last_run_at": None, "last_run_ok": None, "last_run_events": 0,
                   "last_run_new": 0, "last_run_updated": 0, "last_run_error": None}
            await db.scraped_venues.insert_one(doc)
        logger.info(f"Seeded scraped_venues: {len(_SEED_VENUES)} venues (fourvenues_api)")
        # Link curated Ibiza directory entries to their new Night League scrapers
        # so sync_scraper_venues_to_directory dedups them (no duplicate locales).
        for nm, slug in (("Ushuaïa Ibiza", "ushuaia-ibiza"), ("Hï Ibiza", "hi-ibiza")):
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


def _significant_rename(old: str, new: str) -> bool:
    """True if an event's name changed meaningfully (not just accents/spacing/case).
    Used to surface Fitz-style placeholder→real-name reveals as a real 'novedad'."""
    o = _norm_name(old or "")
    n = _norm_name(new or "")
    if not n or n == o or len(n) < 3:
        return False
    return True


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
    if se.genre and not existing.get("genre"):
        patch["genre"] = se.genre.split(",")[0].strip()[:40]
    # Pricing
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
    return "updated"


async def run_scraper_for_venue(venue: dict, batch_id: str = "") -> dict:
    """Run one venue's scraper and apply diffs. Returns a summary."""
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
        scraper = _build_scraper(venue["adapter_type"], venue["url"], **_kwargs)
        events = await scraper.fetch()
        summary["events"] = len(events)
        for se in events:
            try:
                r = await _apply_scraped_event(venue, se, batch_id)
                if r in summary:
                    summary[r] += 1
            except Exception as e:
                logger.warning(f"[scraper {venue.get('name')}] apply failed for {se.external_id}: {e}")
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
    return summary


async def run_all_scrapers():
    """Run active venues with a bounded concurrency (protects Render free tier
    and avoids hammering FourVenues when many venues are configured). Called by
    scheduler + admin trigger."""
    venues = []
    async for v in db.scraped_venues.find({"active": True}, {"_id": 0}):
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
            return await run_scraper_for_venue(v, batch_id)

    results = await asyncio.gather(*(_run_one(v) for v in venues), return_exceptions=False)
    total_new = sum(r["created"] for r in results)
    total_upd = sum(r["updated"] for r in results)
    logger.info(f"[scrapers] Completed: {len(results)} venues, {total_new} new events, {total_upd} updated")
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
    return results


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
    counts = {"new": 0, "price_up": 0, "price_down": 0, "state": 0, "sold_out": 0, "on_sale": 0, "renamed": 0}
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
     "scraper_slug": "", "free_entry": False, "open_days": [0, 1, 2, 3, 4, 5, 6], "instagram": "unvrs",
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
    app.add_middleware(
        CORSMiddleware,
        allow_credentials=True,
        allow_origins=[o.strip() for o in _cors_env.split(',') if o.strip()],
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
