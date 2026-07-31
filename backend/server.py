from dotenv import load_dotenv
from pathlib import Path
import os

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
import json
import asyncio
from datetime import datetime, timezone, timedelta, date
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


async def serialize_event(ev: dict, user: dict, friend_ids: List[str]) -> dict:
    interests = []
    async for it in db.interests.find({"event_id": ev["id"]}):
        interests.append(it)

    my_status = None
    friends_going = []
    friends_interested = []
    friends_attended = []
    for it in interests:
        if it["user_id"] == user["user_id"]:
            my_status = it["status"]
        elif it["user_id"] in friend_ids:
            fu = await db.users.find_one({"user_id": it["user_id"]}, {"_id": 0})
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
    events = []
    async for ev in db.events.find(query, {"_id": 0}).sort("date", sort_dir):
        if not date_in_filter(ev["date"], date_filter):
            continue
        if genre != "all" and ev.get("genre") != genre:
            continue
        events.append(await serialize_event(ev, user, friend_ids))
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
        scheduler.start()
        logger.info("Scheduler iniciado (digest viernes + recordatorios 30min + recuerdo lunes 12:00)")
    except Exception as e:
        logger.error(f"Scheduler init falló: {e}")


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
