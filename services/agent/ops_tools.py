"""Tools that prepare outward messages. They only queue drafts for human approval (§4.8)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from services.agent.tools import error_result, ok_result, tool
from services.store import get_store


class QueueDispatchArgs(BaseModel):
    advisory_run_id: str = Field(description="run_id returned by draft_advisory.")
    channel: Literal["chat", "email"] = Field(default="chat", description="Google Chat message or email.")
    include_cap: bool = Field(default=True, description="Attach a CAP 1.2 exercise alert built from the advisory.")


@tool("queue_dispatch", agent_scopes={"comms", "department"}, side_effect=True)
def queue_dispatch_tool(args: QueueDispatchArgs) -> Any:
    """Queue a department advisory (and a CAP 1.2 exercise alert) for HUMAN APPROVAL. This does NOT send anything:
    the officer must approve it in the Dispatch tab, and in dry-run mode nothing leaves the system even then. Tell
    the officer it is waiting for approval; never say it was sent."""
    from services.advisory import RoleAdvisory
    from services.cap import build_cap_alert
    from services.dispatch.router import queue_dispatch

    record = get_store().get(args.advisory_run_id)
    if record["kind"] != "advisory":
        return error_result("queue_dispatch", f"{args.advisory_run_id} is not an advisory run")
    payload = dict(record["payload"])
    language = payload.pop("language", "English")
    advisory = RoleAdvisory.model_validate(payload)
    attachments = []
    if args.include_cap:
        attachments.append({"name": "alert.cap.xml", "mime": "application/xml", "text": build_cap_alert(advisory, language)})
    body = "\n\n".join(part for part in (advisory.situation_summary, advisory.instruction,
                                         "\n".join(f"- {a}" for a in advisory.priority_actions), advisory.disclaimer) if part)
    dispatch = queue_dispatch(advisory.audience, args.channel, advisory.headline or f"SurgeSight advisory: {advisory.audience}", body, attachments=attachments)
    return ok_result("queue_dispatch", {
        "dispatch_id": dispatch.id, "status": dispatch.status, "department": dispatch.department, "channel": dispatch.channel,
        "subject": dispatch.subject, "recipients": dispatch.recipients, "attachments": [a["name"] for a in attachments],
        "message": "Queued for human approval. Nothing has been sent.",
    }, source="dispatch", run_id=dispatch.id)


class CheckBulletinArgs(BaseModel):
    pass


@tool("check_for_new_bulletin", agent_scopes={"forecast", "comms"})
def check_for_new_bulletin_tool(args: CheckBulletinArgs) -> Any:
    """Check whether a new cyclone bulletin has been published (Google Search grounding), deduplicated by content
    hash. Returns whether it is new and a bulletin run_id to pass to parse_bulletin. It only looks; it does not
    process or send anything."""
    from services.monitor import poll_once

    found = poll_once()
    return ok_result("check_for_new_bulletin", found, source=found.get("source", "monitor"), run_id=found.get("bulletin_ref"))
