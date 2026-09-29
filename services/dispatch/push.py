"""Push notifications (WP5.3): ntfy for phones today, Firebase Cloud Messaging for the web app later.

ntfy sends to the topic in ``NTFY_TOPIC`` (a long random string is its only secret). FCM sends to the browser
registration tokens stored by ``register_token`` (the test page at ``/push-test``). Messages are always marked as an
exercise.
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
import requests

TIMEOUT = 20
NTFY_SERVER = "https://ntfy.sh"
FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
MAX_BODY = 3500
PRIORITY = {"CRITICAL": "urgent", "HIGH": "high", "MODERATE": "default", "LOW": "low"}


def ntfy_topic() -> str | None:
    load_dotenv()
    return os.getenv("NTFY_TOPIC") or None


def configured_providers() -> list[str]:
    providers = []
    if ntfy_topic():
        providers.append("ntfy")
    if list_tokens():
        providers.append("fcm")
    return providers


def ntfy_request(subject: str, body: str, *, department: str, severity: str | None = None) -> dict[str, Any]:
    """The HTTP request ntfy expects. Header values are latin-1 only, so non-Latin text goes in the body."""
    ascii_title = f"SurgeSight EXERCISE: {department}"
    text = f"{subject}\n\n{body}"[:MAX_BODY]
    return {"headers": {"Title": ascii_title, "Priority": PRIORITY.get(severity or "", "default"), "Tags": "cyclone,warning"},
            "data": text.encode("utf-8")}


def send_ntfy(subject: str, body: str, *, department: str, severity: str | None = None) -> dict[str, Any]:
    topic = ntfy_topic()
    if not topic:
        raise RuntimeError("NTFY_TOPIC is not set")
    request = ntfy_request(subject, body, department=department, severity=severity)
    response = requests.post(f"{NTFY_SERVER}/{topic}", headers=request["headers"], data=request["data"], timeout=TIMEOUT)
    response.raise_for_status()
    return {"provider": "ntfy", "message_id": response.json().get("id")}


def fcm_message(subject: str, body: str, *, department: str, token: str) -> dict[str, Any]:
    return {"message": {"token": token, "notification": {"title": f"EXERCISE · {subject}"[:200], "body": body[:1000]},
                        "data": {"department": department, "exercise": "true"}}}


def _fcm_send_one(url: str, headers: dict[str, str], payload: dict[str, Any]) -> tuple[bool, str]:
    response = requests.post(url, json=payload, headers=headers, timeout=TIMEOUT)
    if response.status_code < 400:
        return True, response.json().get("name", "validated")
    return False, f"HTTP {response.status_code}: {response.text[:160]}"


def send_fcm(subject: str, body: str, *, department: str, validate_only: bool = False) -> dict[str, Any]:
    """Send to every registered browser. Tokens FCM reports as gone (UNREGISTERED or NOT_FOUND) are dropped."""
    import google.auth
    from google.auth.transport.requests import Request

    tokens = list_tokens()
    if not tokens:
        raise RuntimeError("No browser is registered for push: open /push-test and click Enable notifications")
    credentials, project = google.auth.default(scopes=[FCM_SCOPE])
    credentials.refresh(Request())
    project = os.getenv("GOOGLE_CLOUD_PROJECT") or project
    url = f"https://fcm.googleapis.com/v1/projects/{project}/messages:send"
    headers = {"Authorization": f"Bearer {credentials.token}", "x-goog-user-project": project}
    delivered, failed, dropped = 0, [], 0
    for token in tokens:
        payload = fcm_message(subject, body, department=department, token=token)
        if validate_only:
            payload["validate_only"] = True
        ok, detail = _fcm_send_one(url, headers, payload)
        if ok:
            delivered += 1
        else:
            failed.append(detail)
            if "UNREGISTERED" in detail or "NOT_FOUND" in detail:
                remove_token(token)
                dropped += 1
    if not delivered:
        raise RuntimeError("FCM accepted no message: " + "; ".join(failed))
    return {"provider": "fcm", "delivered_to": delivered, "failed": len(failed), "dropped_tokens": dropped}


def send_push(subject: str, body: str, *, department: str, severity: str | None = None) -> dict[str, Any]:
    """Send to every configured provider; raises only if none is configured or all fail."""
    providers = configured_providers()
    if not providers:
        raise RuntimeError("No push provider configured: set NTFY_TOPIC, or register a browser at /push-test for FCM")
    results, errors = [], []
    for name in providers:
        try:
            results.append(send_ntfy(subject, body, department=department, severity=severity) if name == "ntfy"
                           else send_fcm(subject, body, department=department))
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    if not results:
        raise RuntimeError("; ".join(errors))
    return {"sent": results, "errors": errors}


# ---------------------------------------------------------------- web client registration

TOKEN_KIND = "push_token"


def _token_id(token: str) -> str:
    import hashlib

    return "pushtoken-" + hashlib.sha256(token.encode()).hexdigest()[:16]


def web_config() -> dict[str, str]:
    """The public Firebase web config (the apiKey is an identifier, not a secret) for the browser client."""
    load_dotenv()
    config = {"apiKey": os.getenv("FIREBASE_API_KEY"), "appId": os.getenv("FIREBASE_APP_ID"),
              "messagingSenderId": os.getenv("FIREBASE_MESSAGING_SENDER_ID"), "projectId": os.getenv("GOOGLE_CLOUD_PROJECT")}
    missing = [k for k, v in config.items() if not v]
    if missing:
        raise RuntimeError(f"Firebase web config incomplete, missing {missing}")
    config["authDomain"] = f"{config['projectId']}.firebaseapp.com"
    return config  # type: ignore[return-value]


def register_token(token: str) -> dict[str, Any]:
    """Remember a browser registration token (from the test page or the React app) as a push recipient."""
    from datetime import datetime, timezone

    from services.store import get_store

    if not token or len(token) < 20:
        raise ValueError("A registration token is required")
    get_store().put(_token_id(token), TOKEN_KIND, {"token": token, "registered_at_utc": datetime.now(timezone.utc).isoformat()})
    return {"registered": len(list_tokens())}


def list_tokens() -> list[str]:
    from services.store import get_store

    store = get_store()
    payloads = [store.get(r["run_id"])["payload"] for r in store.list(TOKEN_KIND, 200)]
    return [p["token"] for p in payloads if p.get("token") and not p.get("removed")]


def remove_token(token: str) -> None:
    """Mark a token as removed (the run store has no delete, so the record is blanked)."""
    from services.store import get_store

    get_store().put(_token_id(token), TOKEN_KIND, {"token": "", "removed": True})
