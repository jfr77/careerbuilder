"""Supabase Auth — JWT verification for the API.

Supabase issues every signed-in user a JWT signed (HS256) with the project's
JWT secret. The frontend attaches it as `Authorization: Bearer <jwt>` on every
request; here we verify the signature + expiry and pull the user id out of the
`sub` claim. That id (a UUID) is what scopes all profile-derived data.

Config (env):
  SUPABASE_JWT_SECRET   the project's JWT secret (Supabase dashboard →
                        Project Settings → API → JWT Settings → JWT Secret).
  AUTH_DISABLED=1       dev/local escape hatch: skip verification and act as a
                        fixed dev user. NEVER set this in production.

When SUPABASE_JWT_SECRET is unset and AUTH_DISABLED is not 1, every protected
request fails closed with 503 — the API refuses to run unauthenticated rather
than silently exposing data.
"""

import os

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# Supabase signs access tokens with this audience by default.
JWT_AUDIENCE = "authenticated"

# Fixed pseudo-user used only when AUTH_DISABLED=1 (local dev). Stable UUID so
# data created while disabled stays consistent across restarts.
DEV_USER_ID = "00000000-0000-0000-0000-000000000000"


def owns(stored, user_id) -> bool:
    """True if `stored` (a row's owner_id) belongs to `user_id`.

    Compares as strings: Postgres hands uuid columns back as uuid.UUID objects
    while the JWT `sub` is a plain string, so a naive `==` would never match.
    A NULL/empty owner (legacy/unclaimed rows) belongs to nobody."""
    return stored is not None and str(stored) == str(user_id)


def _secret() -> str | None:
    return os.environ.get("SUPABASE_JWT_SECRET")


def auth_disabled() -> bool:
    return os.environ.get("AUTH_DISABLED") == "1"


# auto_error=False so we can return our own 401 with a clear message.
_bearer = HTTPBearer(auto_error=False)


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """FastAPI dependency → the authenticated user's id (UUID string).

    Raises 401 on a missing/invalid/expired token, 503 if the server has no
    JWT secret configured (so a misconfigured deploy fails loudly, not open)."""
    if auth_disabled():
        return DEV_USER_ID

    secret = _secret()
    if not secret:
        raise HTTPException(
            503,
            "auth is not configured: set SUPABASE_JWT_SECRET (or AUTH_DISABLED=1 "
            "for local dev). The API refuses to serve user data unauthenticated.",
        )

    if creds is None or not creds.credentials:
        raise HTTPException(401, "missing bearer token")

    try:
        payload = jwt.decode(
            creds.credentials,
            secret,
            algorithms=["HS256"],
            audience=JWT_AUDIENCE,
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(401, f"invalid token: {e}")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(401, "token has no subject")
    return user_id
