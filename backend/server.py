from dotenv import load_dotenv
from pathlib import Path
import os
import time

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, UploadFile, File, Form, Query, Header
from starlette.middleware.cors import CORSMiddleware
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
import json
import asyncio
from datetime import datetime, timezone, timedelta, date, time as dtime
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pywebpush import webpush, WebPushException

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

VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:hola@quienva.app")

# In-memory TTL cache for expensive user-stats computation
_STATS_CACHE = {}

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


class FriendActionInput(BaseModel):
    user_id: str


class FriendRespondInput(BaseModel):
    request_id: str
    accept: bool


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
    }


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
# Auth endpoints
# ---------------------------------------------------------------------------
@api_router.post("/auth/register")
async def register(inp: RegisterInput, response: Response):
    email = inp.email.lower().strip()
    username = inp.username.lower().strip().replace(" ", "")
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
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(user)
    token = await create_session(user["user_id"])
    set_session_cookie(response, token)
    return {"user": public_user(user), "token": token}


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
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.users.insert_one(user)

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
    if updates:
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": updates})
        user.update(updates)
    return public_user(user)


# ---------------------------------------------------------------------------
# Friends
# ---------------------------------------------------------------------------
async def accepted_friend_ids(user_id: str) -> List[str]:
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
            {"name": {"$regex": q, "$options": "i"}},
        ],
    }, {"_id": 0}).limit(20)
    fmap = await friendship_status_map(user["user_id"])
    my_friends = await accepted_friend_ids(user["user_id"])
    out = []
    async for u in cursor:
        pu = public_user(u)
        rel = fmap.get(u["user_id"])
        pu["relationship"] = rel or {"status": "none"}
        pu["mutual_count"] = await mutual_friends_count(my_friends, u["user_id"])
        out.append(pu)
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
                                      f"{user['name']} aceptó tu solicitud de amistad",
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
                              f"{user['name']} te ha enviado una solicitud de amistad",
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
                                  f"{user['name']} aceptó tu solicitud de amistad",
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
        out.append(public_user(u))
    return out


@api_router.get("/friends/requests")
async def list_requests(user: dict = Depends(get_current_user)):
    incoming = []
    my_friends = await accepted_friend_ids(user["user_id"])
    async for f in db.friendships.find({"addressee_id": user["user_id"], "status": "pending"}):
        requester = await db.users.find_one({"user_id": f["requester_id"]}, {"_id": 0})
        if requester:
            pu = public_user(requester)
            pu["mutual_count"] = await mutual_friends_count(my_friends, requester["user_id"])
            incoming.append({"request_id": f["id"], "user": pu})
    return incoming


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


async def serialize_event(ev: dict, user: dict, friend_ids: List[str], users_map: dict | None = None) -> dict:
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
            fu = users_map.get(it["user_id"])
            if fu:
                entry = {"user_id": fu["user_id"], "name": fu["name"], "picture": fu.get("picture", "")}
                if it["status"] == "voy":
                    friends_going.append(entry)
                elif it["status"] == "me_interesa":
                    friends_interested.append(entry)
                elif it["status"] == "estuve":
                    friends_attended.append(entry)

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
        "commission_url": ev.get("commission_url", ""),
        "more_info_url": ev.get("more_info_url", ""),
        "my_status": my_status,
        "friends_going": friends_going,
        "friends_interested": friends_interested,
        "friends_attended": friends_attended,
        "total_going": sum(1 for it in interests if it["status"] == "voy"),
        "total_interested": sum(1 for it in interests if it["status"] == "me_interesa"),
        "total_attended": sum(1 for it in interests if it["status"] == "estuve"),
    }


@api_router.get("/events")
async def list_events(user: dict = Depends(get_current_user),
                      date_filter: str = Query("all"),
                      genre: str = Query("all")):
    friend_ids = await accepted_friend_ids(user["user_id"])
    query = {"city": user.get("city", "Palma de Mallorca")}
    sort_dir = -1 if date_filter == "pasados" else 1

    # Preload friend users once (avoid N+1 lookups inside serialize_event)
    users_map: dict = {}
    if friend_ids:
        async for u in db.users.find({"user_id": {"$in": list(friend_ids)}}, {"_id": 0}):
            users_map[u["user_id"]] = u

    events = []
    async for ev in db.events.find(query, {"_id": 0}).sort("date", sort_dir):
        if not date_in_filter(ev["date"], date_filter):
            continue
        if genre != "all" and ev.get("genre") != genre:
            continue
        events.append(await serialize_event(ev, user, friend_ids, users_map))
    return events


@api_router.get("/events/genres")
async def list_genres(user: dict = Depends(get_current_user)):
    genres = await db.events.distinct("genre", {"city": user.get("city", "Palma de Mallorca")})
    return [g for g in genres if g]


@api_router.get("/events/top-weekend")
async def top_weekend(user: dict = Depends(get_current_user)):
    """The upcoming event (next 7 days) where the most of your friends are going."""
    friend_ids = await accepted_friend_ids(user["user_id"])
    today = datetime.now(ZoneInfo("Europe/Madrid")).date()
    week_end = today + timedelta(days=7)
    best = None
    best_count = 0
    async for ev in db.events.find({"city": user.get("city", "Palma de Mallorca")}, {"_id": 0}).sort("date", 1):
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
async def event_carousels(user: dict = Depends(get_current_user)):
    """Home-page carousels: top del finde (list), lo que va tu grupo, descubrir géneros."""
    friend_ids = await accepted_friend_ids(user["user_id"])
    today = datetime.now(ZoneInfo("Europe/Madrid")).date()
    city = user.get("city", "Palma de Mallorca")

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

    # ---- Top del finde: upcoming Fri-Sun (or next 7 days) sorted by attendance ----
    week_end = today + timedelta(days=7)
    weekend_serialized = [
        await serialize_event(ev, user, friend_ids, users_map)
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
            se = await serialize_event(ev, user, friend_ids, users_map)
            if (len(se["friends_going"]) + len(se["friends_interested"])) > 0:
                friends_going_list.append(se)
        friends_going_list = sorted(
            friends_going_list,
            key=lambda e: (-(len(e["friends_going"]) * 2 + len(e["friends_interested"])), e["date"]),
        )[:8]

    # ---- Descubre géneros nuevos: upcoming events in genres the user has NOT interacted with ----
    my_genres = set()
    async for it in db.interests.find({"user_id": user["user_id"]}):
        ev = await db.events.find_one({"id": it["event_id"]}, {"_id": 0, "genre": 1})
        if ev and ev.get("genre"):
            my_genres.add(ev["genre"])
    discover_new = []
    for d, ev in all_upcoming:
        g = ev.get("genre")
        if not g or g in my_genres:
            continue
        discover_new.append(await serialize_event(ev, user, friend_ids, users_map))
        if len(discover_new) >= 8:
            break

    return {
        "top_weekend": top_weekend_list,
        "friends_going": friends_going_list,
        "discover_new": discover_new,
    }


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

    async for it in db.interests.find({"user_id": user_id}):
        if it["status"] == "voy":
            going += 1
        if it["status"] == "me_interesa":
            interested += 1
        if it["status"] == "estuve":
            attended += 1
        ev = await db.events.find_one({"id": it["event_id"]}, {"_id": 0})
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
        global _STATS_CACHE
        if user_id is None:
            _STATS_CACHE.clear()
        else:
            _STATS_CACHE.pop(user_id, None)
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
            "user": {"user_id": target["user_id"], "name": target["name"],
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
        "user": {"user_id": target["user_id"], "name": target["name"],
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
            "name": u["name"],
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
        f"¡{u['name']} se registró con tu código! +{ACTION_POINTS['referral_signup']} puntos 🎁",
        {"user_id": user["user_id"]},
    )
    return {"ok": True, "points": ACTION_POINTS["referral_signup"]}


@api_router.get("/events/discover")
async def discover_events(user: dict = Depends(get_current_user)):
    """Recommend upcoming events based on the genres the user engages with most."""
    friend_ids = await accepted_friend_ids(user["user_id"])
    genre_count = {}
    interacted = set()
    async for it in db.interests.find({"user_id": user["user_id"]}):
        interacted.add(it["event_id"])
        ev = await db.events.find_one({"id": it["event_id"]}, {"_id": 0})
        if ev and ev.get("genre"):
            genre_count[ev["genre"]] = genre_count.get(ev["genre"], 0) + 1
    ranked_genres = [g for g, _ in sorted(genre_count.items(), key=lambda x: -x[1])]
    genre_rank = {g: i for i, g in enumerate(ranked_genres)}

    today = datetime.now(ZoneInfo("Europe/Madrid")).date()
    upcoming = []
    async for ev in db.events.find({"city": user.get("city", "Palma de Mallorca")}, {"_id": 0}):
        if ev["id"] in interacted:
            continue
        try:
            d = date.fromisoformat(ev["date"])
        except Exception:
            continue
        if d < today:
            continue
        upcoming.append(ev)

    if ranked_genres:
        matched = [e for e in upcoming if e.get("genre") in genre_rank]
        others = [e for e in upcoming if e.get("genre") not in genre_rank]
        matched.sort(key=lambda e: (genre_rank.get(e.get("genre"), 999), e["date"]))
        others.sort(key=lambda e: e["date"])
        pool = matched + others
    else:
        pool = upcoming

    result = []
    for ev in pool[:12]:
        result.append(await serialize_event(ev, user, friend_ids))
    if not ranked_genres:
        result.sort(key=lambda e: -(e["total_going"] + e["total_interested"]))
    return result


@api_router.get("/events/{event_id}")
async def get_event(event_id: str, user: dict = Depends(get_current_user)):
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    friend_ids = await accepted_friend_ids(user["user_id"])
    return await serialize_event(ev, user, friend_ids)


@api_router.post("/events/{event_id}/interest")
async def set_interest(event_id: str, inp: InterestInput, user: dict = Depends(get_current_user)):
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    if inp.status not in ("voy", "me_interesa", "estuve", "none"):
        raise HTTPException(status_code=400, detail="Estado inválido")

    existing = await db.interests.find_one({"user_id": user["user_id"], "event_id": event_id})
    prev_status = existing["status"] if existing else None

    if inp.status == "none":
        await db.interests.delete_one({"user_id": user["user_id"], "event_id": event_id})
    elif existing:
        await db.interests.update_one({"_id": existing["_id"]},
                                      {"$set": {"status": inp.status,
                                                "updated_at": datetime.now(timezone.utc).isoformat()}})
    else:
        await db.interests.insert_one({
            "id": str(uuid.uuid4()),
            "user_id": user["user_id"],
            "event_id": event_id,
            "status": inp.status,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    _invalidate_stats_cache(user["user_id"])

    # Notify friends when marking "voy" (only on transition to voy)
    if inp.status == "voy" and prev_status != "voy":
        friend_ids = await accepted_friend_ids(user["user_id"])
        for fid in friend_ids:
            await create_notification(
                fid, "friend_going",
                f"{user['name']} va a {ev['name']}",
                {"event_id": event_id, "user_id": user["user_id"]},
            )

    return {"status": inp.status}


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
    await db.notifications.delete_many({"data.event_id": event_id})
    return {"ok": True}


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
async def admin_list_events(admin: dict = Depends(require_admin)):
    events = []
    async for ev in db.events.find({}, {"_id": 0}).sort("date", 1):
        events.append(ev)
    return events


@api_router.post("/admin/upload")
async def admin_upload(file: UploadFile = File(...), admin: dict = Depends(require_admin)):
    ext = file.filename.split(".")[-1].lower() if "." in file.filename else "bin"
    path = f"{APP_NAME}/events/{uuid.uuid4().hex}.{ext}"
    data = await file.read()
    ct = file.content_type or "image/jpeg"
    save_object(path, data)
    await db.files.insert_one({
        "id": str(uuid.uuid4()),
        "storage_path": path,
        "content_type": ct,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"image_url": f"/api/files/{path}"}


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
        save_object(path, img_res.content)
        return f"/api/files/{path}"
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
    save_object(path, data)
    await db.files.insert_one({
        "id": str(uuid.uuid4()),
        "storage_path": path,
        "content_type": ct,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    url = f"/api/files/{path}"
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
async def create_notification(user_id: str, ntype: str, message: str, data: dict):
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
                plans[ev["name"]].add(fu["name"].split(" ")[0])
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
    save_object(path, data)
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
        "image_url": f"/api/files/{path}",
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
            "name": author["name"] if author else "Usuario",
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
                "user": {"name": ru["name"] if ru else "Usuario", "picture": ru.get("picture", "") if ru else ""},
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
            f"{user['name']} reaccionó a tu historia: {content}",
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
    return {"name": u["name"] if u else "Usuario", "picture": u.get("picture", "") if u else "",
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
                f"{user['name']} en el chat de {ev['name']}: {text[:60]}",
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
    last_friday = last_sunday - timedelta(days=2)
    sent = 0

    def in_weekend(dstr):
        try:
            d = date.fromisoformat(dstr)
        except Exception:
            return False
        return last_friday <= d <= last_sunday

    async for u in db.users.find({}, {"_id": 0}):
        friend_ids = await accepted_friend_ids(u["user_id"])
        allowed = friend_ids + [u["user_id"]]

        my_plans = 0
        async for it in db.interests.find({"user_id": u["user_id"], "status": {"$in": ["voy", "estuve"]}}):
            ev = await db.events.find_one({"id": it["event_id"]}, {"_id": 0})
            if ev and in_weekend(ev["date"]):
                my_plans += 1

        group_events = set()
        async for it in db.interests.find({"user_id": {"$in": friend_ids}, "status": {"$in": ["voy", "estuve"]}}):
            ev = await db.events.find_one({"id": it["event_id"]}, {"_id": 0})
            if ev and in_weekend(ev["date"]):
                group_events.add(ev["id"])

        fri_iso = datetime.combine(last_friday, datetime.min.time()).replace(tzinfo=PALMA_TZ).isoformat()
        sun_iso = datetime.combine(last_sunday + timedelta(days=1), datetime.min.time()).replace(tzinfo=PALMA_TZ).isoformat()
        photos = await db.stories.count_documents({"user_id": {"$in": allowed}, "created_at": {"$gte": fri_iso, "$lte": sun_iso}})

        if my_plans + len(group_events) + photos == 0:
            continue
        week_key = last_friday.isoformat()
        if await db.notifications.find_one({"user_id": u["user_id"], "type": "weekend_recap", "data.week": week_key}):
            continue
        msg = (f"Recuerdo del finde 🎉 Fuiste a {my_plans} plan{'es' if my_plans != 1 else ''}, "
               f"tu grupo se apuntó a {len(group_events)} y subisteis {photos} foto{'s' if photos != 1 else ''}.")
        await create_notification(u["user_id"], "weekend_recap", msg, {"week": week_key})
        sent += 1
    logger.info(f"Recuerdo del finde enviado a {sent} usuarios")
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
    text: str


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
    text: str


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
        "user": {"user_id": other["user_id"], "name": other["name"],
                 "username": other.get("username", ""), "picture": other.get("picture", "")},
        "last_message": last["text"] if last else "",
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
    return msgs


@api_router.post("/dm/send")
async def send_dm(inp: DMSendInput, user: dict = Depends(get_current_user)):
    friend_ids = await accepted_friend_ids(user["user_id"])
    if inp.to_user_id not in friend_ids:
        raise HTTPException(status_code=403, detail="Solo puedes hablar con amigos")
    if len(inp.text) > 1000:
        raise HTTPException(status_code=400, detail="Mensaje demasiado largo (máx 1000)")
    text = inp.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Escribe un mensaje")
    msg = {
        "id": str(uuid.uuid4()),
        "thread_key": _dm_key(user["user_id"], inp.to_user_id),
        "from_user_id": user["user_id"],
        "to_user_id": inp.to_user_id,
        "text": text,
        "read": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.dm_messages.insert_one(msg)
    msg.pop("_id", None)
    await create_notification(
        inp.to_user_id, "dm",
        f"{user['name']}: {text[:60]}",
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
            {"user_id": mid, "name": members_map.get(mid, {}).get("name", ""),
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
                f"{user['name']} te añadió al grupo '{name}'",
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
        f"{user['name']} te añadió al grupo '{g['name']}'",
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
    if len(text) > 1000:
        raise HTTPException(status_code=400, detail="Mensaje demasiado largo (máx 1000)")
    if not text:
        raise HTTPException(status_code=400, detail="Escribe algo")
    msg = {
        "id": str(uuid.uuid4()),
        "group_id": group_id,
        "user_id": user["user_id"],
        "text": text,
        "read_by": [user["user_id"]],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.group_messages.insert_one(msg)
    msg.pop("_id", None)
    for mid in g.get("member_ids", []):
        if mid != user["user_id"]:
            await create_notification(
                mid, "group_message",
                f"{g['name']} · {user['name']}: {text[:60]}",
                {"group_id": group_id, "type": "group_message"},
            )
    return {**msg, "author": _msg_author(user), "is_mine": True}


# =========================================================================
# ALBUM — shared multimedia per event (photos + videos)
# =========================================================================

async def _can_access_album(event_id: str, user_id: str) -> bool:
    """User can upload/view album if they have any interest (voy, me_interesa, estuve)."""
    it = await db.interests.find_one({"event_id": event_id, "user_id": user_id})
    return it is not None


@api_router.post("/events/{event_id}/album/upload")
async def album_upload(event_id: str, file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    if not await _can_access_album(event_id, user["user_id"]):
        raise HTTPException(status_code=403, detail="Solo asistentes al evento pueden subir")
    data = await file.read()
    if len(data) > 50 * 1024 * 1024:  # 50MB max
        raise HTTPException(status_code=400, detail="Máximo 50MB")
    ct = file.content_type or "application/octet-stream"
    is_video = ct.startswith("video/")
    is_image = ct.startswith("image/")
    if not (is_video or is_image):
        raise HTTPException(status_code=400, detail="Solo fotos o vídeos")
    ext = file.filename.split(".")[-1].lower() if "." in file.filename else ("mp4" if is_video else "jpg")
    path = f"{APP_NAME}/albums/{event_id}/{uuid.uuid4().hex}.{ext}"
    save_object(path, data)
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
        "media_url": f"/api/files/{path}",
        "media_type": "video" if is_video else "image",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.album_uploads.insert_one(upload)
    upload.pop("_id", None)
    return upload


@api_router.get("/events/{event_id}/album")
async def album_list(event_id: str, user: dict = Depends(get_current_user)):
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    # Anyone who was interested/going/attended can view
    if not await _can_access_album(event_id, user["user_id"]):
        # But allow view if friend went
        friend_ids = await accepted_friend_ids(user["user_id"])
        has_friend = await db.interests.find_one({"event_id": event_id, "user_id": {"$in": friend_ids}})
        if not has_friend:
            raise HTTPException(status_code=403, detail="Sin acceso al álbum")
    items = []
    async for a in db.album_uploads.find({"event_id": event_id}, {"_id": 0}).sort("created_at", -1):
        au = await db.users.find_one({"user_id": a["user_id"]}, {"_id": 0})
        a["author"] = _msg_author(au)
        a["is_mine"] = a["user_id"] == user["user_id"]
        items.append(a)
    return {"event": {"id": ev["id"], "name": ev["name"], "date": ev["date"], "venue": ev["venue"]},
            "items": items, "total": len(items)}


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


@api_router.post("/admin/events/{event_id}/moment/trigger")
async def admin_trigger_moment(event_id: str, admin: dict = Depends(require_admin)):
    """Admin triggers the moment prompt manually. Sends push to all 'voy' users."""
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    now = datetime.now(timezone.utc)
    prompt = {
        "id": str(uuid.uuid4()),
        "event_id": event_id,
        "sent_at": now.isoformat(),
        "on_time_deadline": (now + timedelta(minutes=2)).isoformat(),
        "expires_at": (now + timedelta(hours=6)).isoformat(),
        "triggered_by": admin["user_id"],
    }
    await db.moment_prompts.update_one({"event_id": event_id}, {"$set": prompt}, upsert=True)
    # Notify all voy users
    sent = 0
    async for it in db.interests.find({"event_id": event_id, "status": "voy"}):
        await create_notification(
            it["user_id"], "moment_prompt",
            f"⚡ Es EL MOMENTO en {ev['name']}. ¡Sube una foto ya! (2 min para +30 puntos)",
            {"event_id": event_id, "type": "moment"},
        )
        sent += 1
    return {"prompt": prompt, "notified": sent}


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
    save_object(path, data)
    now = datetime.now(timezone.utc)
    deadline = datetime.fromisoformat(prompt["on_time_deadline"].replace("Z", "+00:00"))
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    on_time = now <= deadline
    capture = {
        "id": str(uuid.uuid4()),
        "event_id": event_id,
        "user_id": user["user_id"],
        "image_url": f"/api/files/{path}",
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
                    f"⚡ {user['name']} subió su momento en {ev['name']}. ¡No te lo pierdas!",
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
    # Only show friends' captures + own
    friend_ids = await accepted_friend_ids(user["user_id"])
    allowed = friend_ids + [user["user_id"]]
    items = []
    async for c in db.captures.find({"event_id": event_id, "user_id": {"$in": allowed}}, {"_id": 0}).sort("created_at", 1):
        au = await db.users.find_one({"user_id": c["user_id"]}, {"_id": 0})
        c["author"] = _msg_author(au)
        c["is_mine"] = c["user_id"] == user["user_id"]
        items.append(c)
    return items


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
                friend_names.append({"name": fu["name"], "picture": fu.get("picture", "")})
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
        {"$set": {"confirmed": inp.confirmed, "confirmed_at": datetime.now(timezone.utc).isoformat()}},
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
    q = {"confirmed": False} if status == "pending" else {"confirmed": True}
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


async def seed_events():
    # Remove leftover automated-test artifacts so the pilot feed stays clean
    await db.events.delete_many({"name": {"$regex": "^(TEST|UI5|Iteration)", "$options": "i"}})
    today = datetime.now(ZoneInfo("Europe/Madrid")).date()
    for d in DEMO_EVENTS:
        date_str = (today + timedelta(days=d["offset"])).isoformat()
        await db.events.update_one(
            {"name": d["name"]},
            {
                "$set": {
                    "venue": d["venue"], "address": d["address"], "date": date_str, "time": d["time"],
                    "genre": d["genre"], "image_url": d["image_url"], "has_commission": d["has_commission"],
                    "commission_url": d["commission_url"], "more_info_url": d["more_info_url"],
                    "city": "Palma de Mallorca",
                },
                "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": datetime.now(timezone.utc).isoformat()},
            },
            upsert=True,
        )
    logger.info("Eventos demo actualizados (fechas próximas)")


@app.on_event("startup")
async def on_startup():
    try:
        await db.users.create_index("email", unique=True)
        await db.users.create_index("username", unique=True)
        await db.sessions.create_index("session_token", unique=True)
        # Performance indices (idempotent) — speed up hot queries
        await db.interests.create_index([("user_id", 1), ("event_id", 1)])
        await db.interests.create_index([("event_id", 1), ("status", 1)])
        await db.interests.create_index("user_id")
        await db.friendships.create_index([("from_user_id", 1), ("to_user_id", 1)])
        await db.friendships.create_index([("to_user_id", 1), ("status", 1)])
        await db.notifications.create_index([("user_id", 1), ("created_at", -1)])
        await db.notifications.create_index([("user_id", 1), ("read", 1)])
        await db.stories.create_index([("user_id", 1), ("created_at", -1)])
        await db.dm_messages.create_index([("thread_key", 1), ("created_at", 1)])
        await db.dm_messages.create_index([("to_user_id", 1), ("read", 1)])
        await db.group_messages.create_index([("group_id", 1), ("created_at", 1)])
        await db.groups.create_index("member_ids")
        await db.captures.create_index([("event_id", 1), ("user_id", 1)])
        await db.album_uploads.create_index([("event_id", 1), ("created_at", -1)])
        await db.album_uploads.create_index("user_id")
        await db.events.create_index("date")
        await db.moment_prompts.create_index("event_id", unique=True)
    except Exception as e:
        logger.warning(f"Index warn: {e}")
    await seed_admin()
    await seed_events()
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
        scheduler.start()
        logger.info("Scheduler iniciado (digest viernes + recordatorios 30min + recuerdo lunes 12:00 + momentos auto cada 10min)")
    except Exception as e:
        logger.error(f"Scheduler init falló: {e}")


async def auto_trigger_moments():
    """Automatically trigger 'El Momento' for events happening right now.
    For each event whose time window is active (start_time to start_time+5h),
    if it has 'voy' users and no prompt yet, schedule a random moment within
    60–180 min after event start."""
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
                # If already has a prompt, skip
                existing = await db.moment_prompts.find_one({"event_id": ev["id"]})
                if existing:
                    continue
                # Only trigger if voy users exist
                voy_count = await db.interests.count_documents({"event_id": ev["id"], "status": "voy"})
                if voy_count == 0:
                    continue
                # Parse event start datetime
                start_str = ev.get("time") or "22:00"
                try:
                    hh, mm = start_str.split(":")[:2]
                    hh, mm = int(hh), int(mm)
                except Exception:
                    hh, mm = 22, 0
                event_date = date.fromisoformat(ev["date"])
                event_start = datetime.combine(event_date, dtime(hh, mm), tzinfo=ZoneInfo("Europe/Madrid"))
                # Check if we plan a moment time; store it in the event doc so it's deterministic
                planned = ev.get("planned_moment_at")
                if not planned:
                    # Pick a random offset between 60 and 180 minutes after start
                    offset_min = secrets.randbelow(121) + 60
                    planned_dt = event_start + timedelta(minutes=offset_min)
                    planned = planned_dt.isoformat()
                    await db.events.update_one({"id": ev["id"]}, {"$set": {"planned_moment_at": planned}})
                planned_dt = datetime.fromisoformat(planned)
                if planned_dt.tzinfo is None:
                    planned_dt = planned_dt.replace(tzinfo=ZoneInfo("Europe/Madrid"))
                # Trigger if we've reached planned_dt and we're not more than 4h past it
                if planned_dt <= now <= planned_dt + timedelta(hours=4):
                    now_utc = datetime.now(timezone.utc)
                    prompt = {
                        "id": str(uuid.uuid4()),
                        "event_id": ev["id"],
                        "sent_at": now_utc.isoformat(),
                        "on_time_deadline": (now_utc + timedelta(minutes=2)).isoformat(),
                        "expires_at": (now_utc + timedelta(hours=6)).isoformat(),
                        "triggered_by": "auto",
                    }
                    await db.moment_prompts.insert_one(prompt)
                    notified = 0
                    async for it in db.interests.find({"event_id": ev["id"], "status": "voy"}):
                        await create_notification(
                            it["user_id"], "moment_prompt",
                            f"⚡ Es EL MOMENTO en {ev['name']}. ¡Sube una foto ya! (2 min para +30 puntos)",
                            {"event_id": ev["id"], "type": "moment"},
                        )
                        notified += 1
                    logger.info(f"Auto moment triggered for {ev['name']} → {notified} users")
            except Exception as e:
                logger.warning(f"auto_moment inner failed for event {ev.get('id')}: {e}")
    except Exception as e:
        logger.error(f"auto_trigger_moments failed: {e}")


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
