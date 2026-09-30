"""A small in-process rate limit for the routes that call paid models (Gemini, text-to-speech, speech-to-text).

One process keeps its own counts, which is enough to stop a runaway client or a script from spending the budget;
a shared limit across Cloud Run instances would need a store (Redis or Firestore) and is not built.
"""

from __future__ import annotations

import time

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

WINDOW_S = 60
# (method, path prefix) -> calls per client per minute
RULES: dict[tuple[str, str], int] = {
    ("POST", "/api/advisory"): 10, ("POST", "/api/tts"): 10, ("POST", "/api/agent"): 10, ("POST", "/api/voice"): 10,
    ("POST", "/api/bulletin"): 10, ("POST", "/api/scenario"): 20, ("POST", "/api/dispatch"): 20,
}

_hits: dict[str, list[float]] = {}


def client_id(request: Request) -> str:
    """The caller's address; behind Cloud Run the first X-Forwarded-For entry is the real client."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "?"


def allow(who: str, bucket: str, per_minute: int, now: float | None = None) -> bool:
    now = time.monotonic() if now is None else now
    key = f"{bucket}|{who}"
    recent = [t for t in _hits.get(key, []) if now - t < WINDOW_S]
    if len(recent) >= per_minute:
        _hits[key] = recent
        return False
    _hits[key] = [*recent, now]
    return True


def check(request: Request, bucket: str, per_minute: int) -> None:
    """Raise 429 when this client used up its calls for the bucket."""
    if not allow(client_id(request), bucket, per_minute):
        raise HTTPException(status_code=429, detail="Too many requests; wait a minute and try again", headers={"Retry-After": str(WINDOW_S)})


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        for (method, prefix), limit in RULES.items():
            if request.method == method and request.url.path.startswith(prefix):
                if not allow(client_id(request), prefix, limit):
                    return JSONResponse({"detail": "Too many requests; wait a minute and try again"}, status_code=429,
                                        headers={"Retry-After": str(WINDOW_S)})
                break
        return await call_next(request)
