"""Push notifications (WP5.3): ntfy for phones today, Firebase Cloud Messaging for the web app later.

Both send to a topic you configure, which is the test target: ``NTFY_TOPIC`` (use a long random string, since the
topic name is the only secret) and ``FCM_TOPIC``. Messages are always marked as an exercise.
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


def fcm_topic() -> str | None:
    load_dotenv()
    return os.getenv("FCM_TOPIC") or None


def configured_providers() -> list[str]:
    return [name for name, topic in (("ntfy", ntfy_topic()), ("fcm", fcm_topic())) if topic]


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


def fcm_message(subject: str, body: str, *, department: str, topic: str) -> dict[str, Any]:
    return {"message": {"topic": topic, "notification": {"title": f"EXERCISE · {subject}"[:200], "body": body[:1000]},
                        "data": {"department": department, "exercise": "true"}}}


def send_fcm(subject: str, body: str, *, department: str, validate_only: bool = False) -> dict[str, Any]:
    import google.auth
    from google.auth.transport.requests import Request

    topic = fcm_topic()
    if not topic:
        raise RuntimeError("FCM_TOPIC is not set")
    credentials, project = google.auth.default(scopes=[FCM_SCOPE])
    credentials.refresh(Request())
    project = os.getenv("GOOGLE_CLOUD_PROJECT") or project
    payload = fcm_message(subject, body, department=department, topic=topic)
    if validate_only:
        payload["validate_only"] = True
    response = requests.post(f"https://fcm.googleapis.com/v1/projects/{project}/messages:send", json=payload, timeout=TIMEOUT,
                             headers={"Authorization": f"Bearer {credentials.token}", "x-goog-user-project": project})
    if response.status_code >= 400:
        raise RuntimeError(f"FCM HTTP {response.status_code}: {response.text[:200]}")
    return {"provider": "fcm", "message": response.json().get("name", "validated" if validate_only else None)}


def send_push(subject: str, body: str, *, department: str, severity: str | None = None) -> dict[str, Any]:
    """Send to every configured provider; raises only if none is configured or all fail."""
    providers = configured_providers()
    if not providers:
        raise RuntimeError("No push provider configured: set NTFY_TOPIC and/or FCM_TOPIC")
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
