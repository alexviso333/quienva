"""In-process tests for Sign in with Apple backend logic (/auth/apple/callback).

We cannot use a REAL Apple identity token here, so we generate our own RSA
keypair, monkeypatch server._APPLE_JWK_CLIENT to return our public key, and mint
tokens with the exact claims Apple sends. This verifies: signature/claims
verification, audience + issuer + expiry rejection, user creation, returning-user
de-duplication (by 'sub'), private-relay email, and missing email.

Run:  python3 apple_signin_test.py
Requires backend/.env (local Mongo).
"""
import asyncio
import time
import sys

from cryptography.hazmat.primitives.asymmetric import rsa
import jwt as pyjwt
from fastapi import Response, HTTPException

sys.path.insert(0, "/app/backend")
import server  # noqa: E402

# --- generate a throwaway RSA key and point the JWKS client at its public key ---
_priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_pub = _priv.public_key()


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


server._APPLE_JWK_CLIENT.get_signing_key_from_jwt = lambda token: _FakeSigningKey(_pub)  # type: ignore


def make_token(*, sub, aud="me.quienva.app", iss="https://appleid.apple.com",
               email=None, email_verified="true", exp_delta=3600):
    now = int(time.time())
    payload = {"iss": iss, "aud": aud, "sub": sub, "iat": now, "exp": now + exp_delta}
    if email is not None:
        payload["email"] = email
        payload["email_verified"] = email_verified
    return pyjwt.encode(payload, _priv, algorithm="RS256", headers={"kid": "testkid"})


async def call(**kw):
    inp = server.AppleCallbackInput(**kw)
    return await server.apple_callback(inp, Response())


async def main():
    passed, failed = [], []

    def check(name, cond):
        (passed if cond else failed).append(name)
        print(("PASS" if cond else "FAIL"), "-", name)

    SUB = "000999.apple_test_sub.0001"
    # cleanup any prior run
    await server.db.users.delete_many({"apple_sub": {"$regex": "^000999"}})

    # 1) Happy path: valid token with private-relay email -> creates user + session
    r = await call(identity_token=make_token(sub=SUB, email="abc@privaterelay.appleid.com"),
                   name="Juan Pérez")
    check("happy path returns token", bool(r.get("token")))
    check("happy path returns user", bool(r.get("user")))
    uid = r["user"]["user_id"]
    dbu = await server.db.users.find_one({"user_id": uid})
    check("user stored with apple_sub", dbu and dbu.get("apple_sub") == SUB)
    check("auth_provider == apple", dbu and dbu.get("auth_provider") == "apple")
    check("name captured from first auth", dbu and dbu.get("name") == "Juan Pérez")
    check("session created", bool(await server.db.sessions.find_one({"session_token": r["token"]})))

    # 2) Returning user: same sub, no name -> SAME user, no duplicate, name preserved
    r2 = await call(identity_token=make_token(sub=SUB, email="abc@privaterelay.appleid.com"))
    check("returning user -> same user_id", r2["user"]["user_id"] == uid)
    cnt = await server.db.users.count_documents({"apple_sub": SUB})
    check("no duplicate user for same sub", cnt == 1)
    dbu2 = await server.db.users.find_one({"user_id": uid})
    check("name preserved on returning login", dbu2 and dbu2.get("name") == "Juan Pérez")

    # 3) Missing email token still works (sub is the identity key)
    SUB2 = "000999.apple_test_sub.0002"
    r3 = await call(identity_token=make_token(sub=SUB2, email=None), name="Sin Email")
    check("login works without email", bool(r3.get("token")))

    # 4) Wrong audience -> 401
    try:
        await call(identity_token=make_token(sub="x", aud="com.other.app"))
        check("wrong audience rejected", False)
    except HTTPException as e:
        check("wrong audience rejected (401)", e.status_code == 401)

    # 5) Wrong issuer -> 401
    try:
        await call(identity_token=make_token(sub="x", iss="https://evil.example.com"))
        check("wrong issuer rejected", False)
    except HTTPException as e:
        check("wrong issuer rejected (401)", e.status_code == 401)

    # 6) Expired token -> 401
    try:
        await call(identity_token=make_token(sub="x", exp_delta=-30))
        check("expired token rejected", False)
    except HTTPException as e:
        check("expired token rejected (401)", e.status_code == 401)

    # 7) Garbage token -> 401
    try:
        await call(identity_token="garbage.token.value")
        check("garbage token rejected", False)
    except HTTPException as e:
        check("garbage token rejected (401)", e.status_code == 401)

    # cleanup
    await server.db.users.delete_many({"apple_sub": {"$regex": "^000999"}})

    print(f"\nRESULT: {len(passed)} passed, {len(failed)} failed")
    if failed:
        print("FAILED:", failed)
        sys.exit(1)
    print("ALL APPLE SIGN-IN BACKEND TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
