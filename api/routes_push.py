"""Web push registration: the test page, its service worker and topic subscription (WP5.3, FCM)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from services.dispatch import push

router = APIRouter()
STATIC = Path(__file__).parent / "static"
FIREBASE_SDK = "10.14.1"


def _config() -> dict[str, str]:
    try:
        return push.web_config()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@router.get("/api/push/config")
def push_config() -> dict[str, Any]:
    return {"firebase": _config(), "sdk_version": FIREBASE_SDK}


class TokenBody(BaseModel):
    token: str = Field(min_length=20, max_length=4096)


@router.post("/api/push/subscribe")
def push_subscribe(body: TokenBody) -> dict[str, Any]:
    try:
        return {"subscribed": True, **push.register_token(body.token)}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None


@router.post("/api/push/unsubscribe")
def push_unsubscribe(body: TokenBody) -> dict[str, Any]:
    try:
        push.remove_token(body.token)
        return {"subscribed": False}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None


@router.get("/firebase-messaging-sw.js")
def service_worker() -> Response:
    """The service worker must be served from the site root to receive pushes for the whole page scope."""
    template = (STATIC / "firebase-messaging-sw.js").read_text(encoding="utf-8")
    script = template.replace("__SDK__", FIREBASE_SDK).replace("__CONFIG__", json.dumps(_config()))
    return Response(content=script, media_type="text/javascript", headers={"Service-Worker-Allowed": "/"})


@router.get("/push-test", response_class=HTMLResponse)
def push_test_page() -> str:
    return (STATIC / "push-test.html").read_text(encoding="utf-8")
