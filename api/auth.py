"""Firebase Auth for the web UI: verify ID tokens and gate the dispatch decisions by role.

``AUTH_MODE=off`` (default, local dev and the Streamlit harness) treats every caller as an approver.
``AUTH_MODE=firebase`` requires ``Authorization: Bearer <Firebase ID token>``; the token's custom claims
``department`` and ``role`` (``approver`` | ``viewer``) come from scripts/set_department_claims.py.
``AUTH_MODE=passcode`` uses an ``APPROVER_PASSCODE`` checked by the server and a signed session cookie.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from typing import Any

from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyCookie
from itsdangerous import URLSafeTimedSerializer

ROLES = ("approver", "viewer")
cookie_scheme = APIKeyCookie(name="approver_session", auto_error=False)

def _serializer() -> URLSafeTimedSerializer:
    secret = os.getenv("APPROVER_PASSCODE")
    if not secret:
        raise RuntimeError("APPROVER_PASSCODE is not set")
    return URLSafeTimedSerializer(secret)


@dataclass(frozen=True)
class Principal:
    uid: str
    email: str
    department: str | None
    role: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


LOCAL_PRINCIPAL = Principal(uid="local", email="local@dev", department=None, role="approver")


def auth_mode() -> str:
    mode = os.getenv("AUTH_MODE", "off").strip().lower()
    if mode not in {"off", "firebase", "passcode"}:
        raise RuntimeError(f"AUTH_MODE must be 'off', 'firebase', or 'passcode', got '{mode}'")
    return mode


def _verify_token(token: str) -> dict[str, Any]:
    """Verify a Firebase ID token and return its claims. Tests replace this function."""
    import firebase_admin
    from firebase_admin import auth as firebase_auth

    if not firebase_admin._apps:
        firebase_admin.initialize_app(options={"projectId": os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")})
    return firebase_auth.verify_id_token(token)


def get_principal(request: Request) -> Principal:
    mode = auth_mode()
    if mode == "off":
        return LOCAL_PRINCIPAL
    if mode == "passcode":
        cookie = request.cookies.get("approver_session")
        if cookie:
            try:
                # Max age 12 hours
                uid = _serializer().loads(cookie, max_age=43200)
                return Principal(uid=uid, email=uid, department=None, role="approver")
            except Exception:
                pass
        return Principal(uid="viewer", email="viewer", department=None, role="viewer")
        
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sign in required")
    try:
        claims = _verify_token(header[7:].strip())
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid or expired sign-in: {type(exc).__name__}") from None
    role = claims.get("role") if claims.get("role") in ROLES else "viewer"
    return Principal(uid=claims.get("uid") or claims.get("sub", ""), email=claims.get("email", ""), department=claims.get("department"), role=role)


def require_approver(principal: Principal = Depends(get_principal)) -> Principal:
    """Approve, reject and send need the approver (Collector) role; viewers get 403."""
    if principal.role != "approver":
        raise HTTPException(status_code=403, detail="Your role is view-only; an approver must make this decision")
    return principal
