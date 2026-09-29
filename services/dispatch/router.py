"""Dispatch queue with human approval (WP5.3).

Nothing leaves SurgeSight without an explicit ``approve`` and a ``send``. ``DISPATCH_MODE=dry_run`` (the default)
renders and logs the message but contacts no one; ``live`` sends only to the test allow-list (email) or to the
configured Chat test-space webhook. Agents can queue a dispatch but cannot approve or send it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from services.config import get_settings
from services.departments import get_department
from services.store import get_store, new_run_id

KIND = "dispatch"
Status = Literal["pending_approval", "approved", "rejected", "sent", "dry_run", "blocked", "failed"]


class Dispatch(BaseModel):
    id: str
    department: str
    channel: Literal["chat", "email"]
    recipients: list[str] = Field(default_factory=list)
    subject: str
    body: str
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    status: Status = "pending_approval"
    created_at_utc: str
    decided_by: str | None = None
    decided_at_utc: str | None = None
    sent_at_utc: str | None = None
    mode: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def allowed_recipients(department: str) -> set[str]:
    return {r.lower() for r in get_settings().dispatch_allowlist} | {r.lower() for r in get_department(department).recipients}


def _save(dispatch: Dispatch) -> Dispatch:
    get_store().put(dispatch.id, KIND, dispatch.model_dump())
    return dispatch


def get(dispatch_id: str) -> Dispatch:
    record = get_store().get(dispatch_id)
    if record["kind"] != KIND:
        raise ValueError(f"{dispatch_id} is not a dispatch")
    return Dispatch.model_validate(record["payload"])


def list_dispatches(status: str | None = None, limit: int = 100) -> list[Dispatch]:
    store = get_store()
    items = [Dispatch.model_validate(store.get(r["run_id"])["payload"]) for r in store.list(KIND, limit)]
    return [d for d in items if status is None or d.status == status]


def queue_dispatch(
    department: str, channel: Literal["chat", "email"], subject: str, body: str, *,
    attachments: list[dict[str, Any]] | None = None, recipients: list[str] | None = None,
) -> Dispatch:
    """Queue a message for human approval. Recipients default to the department's test allow-list."""
    dept = get_department(department)
    chosen = recipients if recipients is not None else sorted(allowed_recipients(dept.display_name))
    return _save(Dispatch(
        id=new_run_id("dispatch"), department=dept.display_name, channel=channel, recipients=chosen,
        subject=subject, body=body, attachments=attachments or [], created_at_utc=_now(),
    ))


def _decide(dispatch_id: str, status: Status, by: str) -> Dispatch:
    dispatch = get(dispatch_id)
    if dispatch.status != "pending_approval":
        raise ValueError(f"{dispatch_id} is {dispatch.status}, not pending approval")
    decided = _save(dispatch.model_copy(update={"status": status, "decided_by": by, "decided_at_utc": _now()}))
    get_store().log_event("approvals", f"{dispatch_id}-{status}", {"dispatch_id": dispatch_id, "decision": status, "by": by})
    return decided


def approve(dispatch_id: str, by: str = "officer") -> Dispatch:
    return _decide(dispatch_id, "approved", by)


def reject(dispatch_id: str, by: str = "officer") -> Dispatch:
    return _decide(dispatch_id, "rejected", by)


def send(dispatch_id: str) -> Dispatch:
    """Send an approved dispatch according to DISPATCH_MODE and the allow-list."""
    from services.dispatch import chat, gmail

    dispatch = get(dispatch_id)
    if dispatch.status != "approved":
        raise PermissionError(f"{dispatch_id} is {dispatch.status}; only an approved dispatch can be sent")
    settings = get_settings()
    update: dict[str, Any] = {"mode": settings.dispatch_mode, "sent_at_utc": _now()}
    if settings.dispatch_mode != "live":
        update.update(status="dry_run", detail={"note": "dry run: nothing was sent", "would_send_to": dispatch.recipients or ["(chat test space)"]})
        return _save(dispatch.model_copy(update=update))
    try:
        if dispatch.channel == "chat":
            card = chat.build_card(dispatch.subject, dispatch.body, department=dispatch.department, attachments=dispatch.attachments)
            update.update(status="sent", detail=chat.send_card(card))
        else:
            allowed = allowed_recipients(dispatch.department)
            outside = [r for r in dispatch.recipients if r.lower() not in allowed]
            if not dispatch.recipients or outside:
                update.update(status="blocked", detail={"reason": "recipients not on the test allow-list", "recipients": outside or ["(none)"]})
            else:
                update.update(status="sent", detail=gmail.send_email(dispatch.recipients, dispatch.subject, dispatch.body, dispatch.attachments))
    except Exception as exc:
        update.update(status="failed", detail={"error": f"{type(exc).__name__}: {exc}"})
    return _save(dispatch.model_copy(update=update))
