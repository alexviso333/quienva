"""Apple Push Notifications (APNs) — token-based (.p8) provider for the native
iOS app (App Store build, bundle id me.quienva.app).

This is completely independent from the existing Web Push / VAPID flow used by
the website (quienva.me): APNs tokens live in their own Mongo collection and are
only sent through this module. If APNs is not configured (missing Team ID / key)
every call is a safe no-op, so nothing breaks while credentials are pending.
"""
import os
import time
import logging
from uuid import uuid4

import jwt

logger = logging.getLogger("apns")

APNS_KEY_ID = os.environ.get("APNS_KEY_ID", "").strip()
APNS_TEAM_ID = os.environ.get("APNS_TEAM_ID", "").strip()
APNS_BUNDLE_ID = os.environ.get("APNS_BUNDLE_ID", "me.quienva.app").strip()
APNS_PRODUCTION = os.environ.get("APNS_PRODUCTION", "true").strip().lower() != "false"

# Private key: either inline (APNS_PRIVATE_KEY, with real or \n-escaped newlines)
# or a path to the .p8 file (APNS_PRIVATE_KEY_PATH).
_KEY_INLINE = os.environ.get("APNS_PRIVATE_KEY", "")
_KEY_PATH = os.environ.get("APNS_PRIVATE_KEY_PATH", "").strip()


def _load_private_key() -> str:
    if _KEY_INLINE:
        return _KEY_INLINE.replace("\\n", "\n")
    if _KEY_PATH and os.path.exists(_KEY_PATH):
        try:
            with open(_KEY_PATH, "r") as f:
                return f.read()
        except Exception as e:  # pragma: no cover
            logger.warning("APNs: could not read key file: %s", e)
    return ""


_PRIVATE_KEY = _load_private_key()

APNS_HOST = "https://api.push.apple.com" if APNS_PRODUCTION else "https://api.development.push.apple.com"


def is_configured() -> bool:
    return bool(APNS_KEY_ID and APNS_TEAM_ID and _PRIVATE_KEY)


_jwt_cache = {"token": None, "iat": 0}


def _provider_token() -> str:
    # APNs rejects tokens older than 1h; refresh every 50 min.
    now = int(time.time())
    if not _jwt_cache["token"] or now - _jwt_cache["iat"] > 50 * 60:
        _jwt_cache["iat"] = now
        _jwt_cache["token"] = jwt.encode(
            {"iss": APNS_TEAM_ID, "iat": now},
            _PRIVATE_KEY,
            algorithm="ES256",
            headers={"kid": APNS_KEY_ID},
        )
    return _jwt_cache["token"]


async def send_apns(device_token: str, title: str, body: str, data: dict | None = None) -> str:
    """Send one alert push. Returns:
    'ok' on success, 'gone' if the token is invalid/unregistered (caller should
    delete it), or 'err' on any other failure. Never raises.
    """
    if not is_configured():
        return "err"
    try:
        import httpx
    except Exception:  # pragma: no cover
        return "err"

    payload = {
        "aps": {"alert": {"title": title, "body": body}, "sound": "default"},
    }
    if data:
        payload.update(data)
    headers = {
        "authorization": f"bearer {_provider_token()}",
        "apns-topic": APNS_BUNDLE_ID,
        "apns-push-type": "alert",
        "apns-priority": "10",
        "apns-id": str(uuid4()),
    }
    try:
        async with httpx.AsyncClient(http2=True, timeout=15) as client:
            resp = await client.post(
                f"{APNS_HOST}/3/device/{device_token}",
                json=payload,
                headers=headers,
            )
        if resp.status_code == 200:
            return "ok"
        reason = ""
        try:
            reason = resp.json().get("reason", "")
        except Exception:
            reason = resp.text[:120]
        if resp.status_code == 410 or reason in ("Unregistered", "BadDeviceToken"):
            return "gone"
        logger.warning("APNs send failed %s: %s", resp.status_code, reason)
        return "err"
    except Exception as e:  # pragma: no cover
        logger.warning("APNs send exception: %s", e)
        return "err"
