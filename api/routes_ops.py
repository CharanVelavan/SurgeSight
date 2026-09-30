"""Advisories, speech, CAP, parametric, dispatch, the streaming agent and the Cloud Scheduler task endpoints."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Literal

import re
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from api.auth import LOCAL_PRINCIPAL, Principal, require_approver, get_principal, _serializer
from api.deps import call_tool, require_task_caller, run_frame, stored, tool_payload
from services.agent.builtin_tools import jsonable
from services.store import get_store, new_run_id

router = APIRouter()
Department = Literal["District Collector / Disaster Management", "Health Department", "Fire & Rescue Services", "Electricity Board",
                     "Police / Traffic", "Water & Sewage Board", "Fisheries Department"]
Language = Literal["English", "Tamil", "Telugu", "Hindi", "Odia", "Bengali"]

EMAIL_REGEX = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class AdvisoryBody(BaseModel):
    department: Department
    language: Language = "English"
    run_id: str | None = Field(default=None, description="A risk_v2 run whose scores the advisory should use; omit for the baseline.")


@router.post("/api/advisory")
def advisory(body: AdvisoryBody) -> dict[str, Any]:
    from services.advisory import generate_role_advisory

    frame = None
    if body.run_id:
        if stored(body.run_id)["kind"] != "riskv2":
            raise HTTPException(status_code=422, detail="Advisories need a risk_v2 run_id")
        frame = run_frame(body.run_id)
        
        # Check cache
        cache_key = f"advisory-cache-{body.department}-{body.language}-{body.run_id}"
        try:
            cached = get_store().get(cache_key)
            if cached["kind"] == "advisory_cache":
                return cached["payload"]
        except KeyError:
            pass

    try:
        result = generate_role_advisory(body.department, body.language, frame)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Advisory generation failed: {exc}") from None
    
    payload = jsonable(result.model_dump()) | {"language": body.language}
    run_id = new_run_id("advisory")
    get_store().put(run_id, "advisory", payload)
    
    res = {"run_id": run_id, "advisory": payload}
    
    if body.run_id:
        cache_key = f"advisory-cache-{body.department}-{body.language}-{body.run_id}"
        get_store().put(cache_key, "advisory_cache", res)
        
    return res


class TtsBody(BaseModel):
    advisory_run_id: str | None = None
    text: str | None = Field(default=None, max_length=4000)
    language: Literal["English", "Tamil", "Telugu", "Hindi", "Bengali"] = "English"


@router.post("/api/tts", response_class=Response, responses={200: {"content": {"audio/mpeg": {}}}})
def tts(body: TtsBody) -> Response:
    from services.advisory import RoleAdvisory
    from services.tts import synthesize_advisory, synthesize_text

    if (body.advisory_run_id is None) == (body.text is None):
        raise HTTPException(status_code=422, detail="Send exactly one of advisory_run_id or text")
    try:
        if body.advisory_run_id:
            record = stored(body.advisory_run_id)
            if record["kind"] != "advisory":
                raise HTTPException(status_code=422, detail="Not an advisory run")
            audio = synthesize_advisory(RoleAdvisory.model_validate({k: v for k, v in record["payload"].items() if k != "language"}), body.language)
        else:
            audio = synthesize_text(body.text or "", body.language)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Text-to-speech failed: {exc}") from None
    return Response(content=audio, media_type="audio/mpeg")


@router.get("/api/cap/{item_id}", response_class=Response, responses={200: {"content": {"application/xml": {}}}})
def cap(item_id: str) -> Response:
    """CAP 1.2 XML for a dispatch (its attachment) or for an advisory run (built on the fly)."""
    record = stored(item_id)
    if record["kind"] == "dispatch":
        for attachment in record["payload"].get("attachments", []):
            if attachment["name"].endswith(".cap.xml"):
                return Response(content=attachment["text"], media_type="application/xml")
        raise HTTPException(status_code=404, detail="This dispatch has no CAP attachment")
    if record["kind"] == "advisory":
        from services.cap import build_cap_from_run

        return Response(content=build_cap_from_run(item_id), media_type="application/xml")
    raise HTTPException(status_code=422, detail=f"{item_id} is a '{record['kind']}' run; give a dispatch or advisory id")


class ParametricBody(BaseModel):
    members: int = Field(default=60, ge=0, le=200)
    liquidity_brief: bool = False


@router.post("/api/parametric/{run_id}")
def parametric(run_id: str, body: ParametricBody) -> dict[str, Any]:
    """ILLUSTRATIVE parametric evaluation for the reference track ('baseline') or a stored track/bulletin-score run."""
    from services.parametric import evaluate, liquidity_brief, with_crore

    track = None
    if run_id != "baseline":
        record = stored(run_id)
        track_run = run_id if record["kind"] == "track" else record["payload"].get("track_run_id")
        if not track_run:
            raise HTTPException(status_code=422, detail="Give 'baseline' or a run that holds a track (bulletin_to_track or score_track)")
        track = run_frame(track_run, "track")
    result = with_crore(evaluate(track, members=body.members))
    if body.liquidity_brief:
        result["liquidity_brief"] = liquidity_brief(result).model_dump()
    out_id = new_run_id("parametric")
    get_store().put(out_id, "parametric", jsonable(result))
    return {"run_id": out_id, "data": jsonable(result)}


class DispatchBody(BaseModel):
    advisory_run_id: str
    channel: Literal["chat", "email", "push"] = "chat"
    include_cap: bool = True


class DecisionBody(BaseModel):
    by: str = "officer"


def _dispatch(dispatch_id: str):
    from services.dispatch import router as dispatcher

    record = stored(dispatch_id)
    if record["kind"] != "dispatch":
        raise HTTPException(status_code=404, detail=f"{dispatch_id} is not a dispatch")
    return dispatcher


@router.get("/api/dispatch")
def dispatch_list(status: str | None = None) -> list[dict[str, Any]]:
    from services.dispatch import router as dispatcher

    return [d.model_dump(exclude={"attachments"}) | {"attachment_names": [a["name"] for a in d.attachments]} for d in dispatcher.list_dispatches(status)]


@router.get("/api/dispatch/mode")
def dispatch_mode() -> dict[str, Any]:
    from services.config import get_settings
    import os
    provider = os.getenv("EMAIL_PROVIDER", "gmail")
    return {"mode": get_settings().dispatch_mode, "provider_configured": provider}


class RecipientBody(BaseModel):
    department: str
    email: str

@router.get("/api/recipients")
def get_recipients(department: str) -> list[str]:
    from services.dispatch.router import get_department_recipients
    return get_department_recipients(department)

@router.post("/api/recipients")
def add_recipient(body: RecipientBody, principal: Principal = Depends(require_approver)) -> list[str]:
    from services.dispatch.router import get_department_recipients, save_department_recipients
    email = body.email.strip().lower()
    if not EMAIL_REGEX.match(email):
        raise HTTPException(status_code=422, detail="Invalid email address format")
    current = get_department_recipients(body.department)
    if email not in current:
        if len(current) >= 20:
            raise HTTPException(status_code=400, detail="Maximum of 20 recipients per department reached")
        current.append(email)
        save_department_recipients(body.department, current)
    return current

@router.delete("/api/recipients")
def remove_recipient(department: str, email: str, principal: Principal = Depends(require_approver)) -> list[str]:
    from services.dispatch.router import get_department_recipients, save_department_recipients
    email = email.strip().lower()
    current = get_department_recipients(department)
    if email in current:
        current.remove(email)
        save_department_recipients(department, current)
    return current


@router.post("/api/dispatch")
def dispatch_queue(body: DispatchBody) -> dict[str, Any]:
    """Queue only. The message waits for a human to approve it."""
    return tool_payload(call_tool("queue_dispatch", body.model_dump()))


def _decider(body: DecisionBody, principal: Principal) -> str:
    """The signed-in email when auth is on; the request's own ``by`` in local mode."""
    return body.by if principal is LOCAL_PRINCIPAL else (principal.email or principal.uid)


@router.post("/api/dispatch/{dispatch_id}/approve")
def dispatch_approve(dispatch_id: str, body: DecisionBody = DecisionBody(), principal: Principal = Depends(require_approver)) -> dict[str, Any]:
    d = _dispatch(dispatch_id)
    try:
        return d.approve(dispatch_id, _decider(body, principal)).model_dump(exclude={"attachments"})
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.post("/api/dispatch/{dispatch_id}/reject")
def dispatch_reject(dispatch_id: str, body: DecisionBody = DecisionBody(), principal: Principal = Depends(require_approver)) -> dict[str, Any]:
    d = _dispatch(dispatch_id)
    try:
        return d.reject(dispatch_id, _decider(body, principal)).model_dump(exclude={"attachments"})
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.post("/api/dispatch/{dispatch_id}/send")
def dispatch_send(dispatch_id: str, principal: Principal = Depends(require_approver)) -> dict[str, Any]:
    """Send an approved dispatch (a dry run unless DISPATCH_MODE=live)."""
    d = _dispatch(dispatch_id)
    try:
        return d.send(dispatch_id).model_dump(exclude={"attachments"})
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None

@router.post("/api/dispatch/simulate")
def dispatch_simulate(principal: Principal = Depends(require_approver)) -> dict[str, Any]:
    from services.monitor import poll_once, process
    import os
    sample = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "raw", "sample_michaung_bulletin.txt")
    with open(sample, "r", encoding="utf-8") as f:
        text = f.read()
    polled = poll_once(text=text)
    if not polled.get("bulletin_ref"):
        raise HTTPException(status_code=400, detail="Failed to register sample bulletin")
    return jsonable(process(polled["bulletin_ref"]))

class LoginBody(BaseModel):
    passcode: str

@router.post("/api/login")
def login(body: LoginBody) -> Response:
    import os
    expected = os.getenv("APPROVER_PASSCODE")
    if not expected or body.passcode != expected:
        raise HTTPException(status_code=401, detail="Invalid passcode")
    token = _serializer().dumps("approver")
    response = JSONResponse(content={"status": "ok"})
    response.set_cookie(key="approver_session", value=token, httponly=True, samesite="lax", max_age=43200)
    return response

@router.post("/api/logout")
def logout() -> Response:
    response = JSONResponse(content={"status": "ok"})
    response.delete_cookie(key="approver_session")
    return response


class AgentBody(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    language: Language = "English"
    engine: Literal["single", "adk"] = "single"
    context_run_ids: list[str] = Field(default_factory=list)


@router.post("/api/agent")
async def agent(body: AgentBody) -> EventSourceResponse:
    """Server-sent events: one ``step`` event per tool call, then ``answer`` (or ``error``)."""
    from services.agent.adk_app import run_adk_agent
    from services.agent.orchestrator import run_agent

    for rid in body.context_run_ids:
        stored(rid)
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
    runner = run_adk_agent if body.engine == "adk" else run_agent

    def work() -> None:
        try:
            answer, trace = runner(body.question, context_run_ids=body.context_run_ids or None, language=body.language,
                                   on_step=lambda step: loop.call_soon_threadsafe(queue.put_nowait, ("step", step.model_dump())))
            loop.call_soon_threadsafe(queue.put_nowait, ("answer", answer.model_dump()))
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, ("error", {"message": f"{type(exc).__name__}: {exc}"}))
        loop.call_soon_threadsafe(queue.put_nowait, ("done", {}))

    task = loop.run_in_executor(None, work)

    async def events():
        while True:
            name, data = await queue.get()
            if name == "done":
                break
            yield {"event": name, "data": json.dumps(jsonable(data), ensure_ascii=False)}
        await task

    return EventSourceResponse(events())


class PollBody(BaseModel):
    text: str | None = Field(default=None, description="Bulletin text to use instead of searching (tests, manual runs).")


@router.post("/tasks/poll")
def task_poll(body: PollBody = PollBody(), caller: str = Depends(require_task_caller)) -> dict[str, Any]:
    """Scheduler entry point: look for a new bulletin."""
    from services.monitor import poll_once

    return poll_once(text=body.text) | {"caller": caller}


class ProcessBody(BaseModel):
    bulletin_ref: str
    departments: list[str] | None = None
    members: int = Field(default=40, ge=0, le=200)


@router.post("/tasks/process")
def task_process(body: ProcessBody, caller: str = Depends(require_task_caller)) -> dict[str, Any]:
    """Pub/Sub / Scheduler entry point: run the whole flow for a bulletin and queue drafts for approval."""
    from services.monitor import process

    stored(body.bulletin_ref)
    return jsonable(process(body.bulletin_ref, departments=body.departments, members=body.members)) | {"caller": caller}
