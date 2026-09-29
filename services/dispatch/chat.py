"""Google Chat incoming-webhook messages as cards v2 (WP5.3)."""

from __future__ import annotations

import os
from typing import Any

import requests
from dotenv import load_dotenv

TIMEOUT = 20


def webhook_url() -> str | None:
    load_dotenv()
    return os.getenv("GOOGLE_CHAT_WEBHOOK_URL") or None


def build_card(subject: str, body: str, *, department: str, attachments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """A cards v2 message. Chat text is limited, so the body is trimmed and attachments are listed by name."""
    widgets: list[dict[str, Any]] = [{"textParagraph": {"text": body[:3800].replace("\n", "<br>")}}]
    if attachments:
        widgets.append({"textParagraph": {"text": "<b>Attached:</b> " + ", ".join(a["name"] for a in attachments)}})
    return {
        "cardsV2": [{
            "cardId": "surgesight-dispatch",
            "card": {
                "header": {"title": subject[:200], "subtitle": f"{department} · SurgeSight EXERCISE (not an official warning)"},
                "sections": [{"widgets": widgets}],
            },
        }]
    }


def send_card(card: dict[str, Any]) -> dict[str, Any]:
    url = webhook_url()
    if not url:
        raise RuntimeError("GOOGLE_CHAT_WEBHOOK_URL is not set")
    response = requests.post(url, json=card, timeout=TIMEOUT)
    response.raise_for_status()
    return {"message": response.json().get("name")}
