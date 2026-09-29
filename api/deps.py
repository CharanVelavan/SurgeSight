"""Shared helpers for the API routers: tool calls, frame normalisation and OIDC checks for /tasks."""

from __future__ import annotations

import os
from typing import Any

from fastapi import HTTPException, Request
import pandas as pd

import services.agent  # noqa: F401  (registers tools)
from services.agent.builtin_tools import jsonable
from services.agent.tools import ToolResult, execute_tool
from services.config import get_settings, list_regions
from services.store import get_store

CLASS_COLUMNS = ("class_v2", "scenario_risk_class", "risk_class")
SCORE_COLUMNS = ("combined_v2", "scenario_risk_score", "combined_risk_score")
CLASS_RANK = {"LOW": 0, "MODERATE": 1, "HIGH": 2, "CRITICAL": 3}


def call_tool(name: str, args: dict[str, Any] | None = None) -> ToolResult:
    """Run a registry tool; a failed tool becomes a 422 with the tool's own error message."""
    result, _ = execute_tool(name, args or {})
    if not result.ok:
        raise HTTPException(status_code=422, detail=f"{name}: {result.error}")
    return result


def tool_payload(result: ToolResult) -> dict[str, Any]:
    return {"run_id": result.run_id, "data": result.data, "warnings": result.warnings, "provenance": result.provenance.model_dump()}


def require_region(region: str | None) -> str:
    known = set(list_regions())
    region = region or get_settings().region
    if region not in known:
        raise HTTPException(status_code=404, detail=f"Unknown region '{region}'. Known: {sorted(known)}")
    return region


def stored(run_id: str) -> dict[str, Any]:
    try:
        return get_store().get(run_id)
    except (KeyError, ValueError):
        raise HTTPException(status_code=404, detail=f"Unknown run_id '{run_id}'") from None


def run_frame(run_id: str, name: str = "assets") -> pd.DataFrame:
    stored(run_id)
    try:
        return get_store().get_frame(run_id, name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Run {run_id} has no '{name}' table") from None


def normalised(frame: pd.DataFrame) -> pd.DataFrame:
    """Add ``risk_class`` and ``risk_score`` columns whichever model produced the frame."""
    out = frame.copy()
    class_col = next((c for c in CLASS_COLUMNS if c in out.columns), None)
    score_col = next((c for c in SCORE_COLUMNS if c in out.columns), None)
    if class_col is None or score_col is None:
        raise HTTPException(status_code=422, detail="This run has no risk class or score columns")
    out["risk_class"], out["risk_score"] = out[class_col], out[score_col]
    return out


def geojson(frame: pd.DataFrame, columns: list[str]) -> dict[str, Any]:
    cols = [c for c in columns if c in frame.columns]
    records = frame[["lon", "lat", *cols]].astype(object).where(frame[["lon", "lat", *cols]].notna(), None).to_dict(orient="records")
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
         "properties": jsonable({c: r[c] for c in cols})} for r in records]}


def require_task_caller(request: Request) -> str:
    """Cloud Scheduler / Pub/Sub push callers must present a Google OIDC token. Local runs skip the check."""
    settings = get_settings()
    if settings.env == "local":
        return "local"
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    try:
        claims = id_token.verify_oauth2_token(header[7:], google_requests.Request(), audience=os.getenv("TASKS_AUDIENCE"))
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from None
    invoker = os.getenv("TASKS_INVOKER_EMAIL")
    if invoker and claims.get("email") != invoker:
        raise HTTPException(status_code=403, detail="Caller is not the configured invoker")
    return claims.get("email", "unknown")
