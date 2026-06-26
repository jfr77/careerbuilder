#!/usr/bin/env python3
"""Auth unit tests — JWT verification + ownership helper. No server, no DB.

Run:  .venv/bin/python tests/test_auth.py
Same plain-assert style as test_api.py / test_scrapers.py.
"""

import os
import sys
import time
from pathlib import Path

import jwt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# auth.py reads env at call time, not import time.
from backend import auth  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from fastapi.security import HTTPAuthorizationCredentials  # noqa: E402

SECRET = "x" * 40  # >=32 bytes, no InsecureKeyLengthWarning
PASS, FAIL = 0, 0


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


def creds(token):
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def make_token(sub="user-1", *, secret=SECRET, aud="authenticated", exp_offset=3600, **extra):
    payload = {"sub": sub, "aud": aud, "exp": int(time.time()) + exp_offset, **extra}
    return jwt.encode(payload, secret, algorithm="HS256")


def expect_401(fn, name):
    try:
        fn()
        check(name, False, "no exception raised")
    except HTTPException as e:
        check(name, e.status_code == 401, f"got {e.status_code}")


def test_owns():
    import uuid
    u = "00000000-0000-0000-0000-000000000000"
    check("owns: uuid obj == str", auth.owns(uuid.UUID(u), u))
    check("owns: str == str", auth.owns(u, u))
    check("owns: mismatch is False", not auth.owns(u, "11111111-1111-1111-1111-111111111111"))
    check("owns: None owner is nobody's", not auth.owns(None, u))


def test_current_user():
    os.environ.pop("AUTH_DISABLED", None)
    os.environ["SUPABASE_JWT_SECRET"] = SECRET

    # valid token -> sub
    uid = auth.current_user(creds(make_token("abc-123")))
    check("valid token -> sub", uid == "abc-123")

    expect_401(lambda: auth.current_user(None), "missing token -> 401")
    expect_401(lambda: auth.current_user(creds(make_token(exp_offset=-10))), "expired -> 401")
    expect_401(lambda: auth.current_user(creds(make_token(secret="wrong" * 8))), "bad signature -> 401")
    expect_401(lambda: auth.current_user(creds(make_token(aud="other"))), "wrong audience -> 401")
    expect_401(lambda: auth.current_user(creds("not.a.jwt")), "malformed -> 401")

    # token with no subject
    no_sub = jwt.encode({"aud": "authenticated", "exp": int(time.time()) + 60}, SECRET, algorithm="HS256")
    expect_401(lambda: auth.current_user(creds(no_sub)), "no sub claim -> 401")

    # misconfigured server (no secret) fails closed with 503
    os.environ.pop("SUPABASE_JWT_SECRET", None)
    try:
        auth.current_user(creds(make_token()))
        check("no secret -> 503", False, "no exception")
    except HTTPException as e:
        check("no secret -> 503 (fail closed)", e.status_code == 503, f"got {e.status_code}")

    # AUTH_DISABLED short-circuits to the dev user
    os.environ["AUTH_DISABLED"] = "1"
    check("AUTH_DISABLED -> dev user", auth.current_user(None) == auth.DEV_USER_ID)
    os.environ.pop("AUTH_DISABLED", None)


if __name__ == "__main__":
    print("test_owns")
    test_owns()
    print("test_current_user")
    test_current_user()
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)
