"""Rate limiting for the expensive (LLM-backed) endpoints.

Buckets are keyed per authenticated user so one account can't exhaust the
shared Anthropic budget, with the client IP as a fallback for anonymous/
unauthenticated calls. The key is read from the JWT *without* verifying the
signature — verification still happens in the auth dependency, so this can't be
used to bypass auth; it only decides which bucket a request counts against.

Storage is in-memory (per process). That's correct for a single-instance
deploy like Render free tier; for multiple instances point slowapi at Redis via
RATELIMIT_STORAGE_URI.
"""

import os

import jwt
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def user_or_ip(request: Request) -> str:
    """Limiter key: the JWT subject if present, else the remote address."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1]
        try:
            sub = jwt.decode(token, options={"verify_signature": False}).get("sub")
            if sub:
                return f"user:{sub}"
        except jwt.InvalidTokenError:
            pass
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(
    key_func=user_or_ip,
    storage_uri=os.environ.get("RATELIMIT_STORAGE_URI", "memory://"),
    # Disable entirely in local dev/tests so the suite isn't throttled.
    enabled=os.environ.get("RATELIMIT_DISABLED") != "1",
)

# Per-endpoint budgets for the LLM routes. Generous enough for real use, low
# enough to cap runaway cost. Tunable here in one place.
LLM_LIMIT = "30/minute"
