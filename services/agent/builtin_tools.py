"""Tools that wrap the existing deterministic SurgeSight services (WP1.1).

Every tool returns a compact ToolResult (counts, top-N, run_id); full data goes to the
RunStore (§4.4). Gemini never receives thousands of assets.
"""

from __future__ import annotations

import math
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from services.agent.tools import error_result, ok_result, tool
from services.config import load_region
from services.store import get_store, new_run_id

TOP_N = 15
ASSET_TYPES = ("hospital", "school", "shelter", "substation")


def jsonable(value: Any) -> Any:
    """Recursively convert numpy/pandas values to plain JSON types (NaN/NaT -> None)."""
    if value is None or value is pd.NaT or value is pd.NA:
        return None
    if isinstance(value, BaseModel):
        return jsonable(value.model_dump())
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return jsonable(value.tolist())
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (str, int, bool)):
        return value
    return str(value)


def _records(frame: pd.DataFrame, columns: list[str], n: int = TOP_N) -> list[dict[str, Any]]:
    cols = [c for c in columns if c in frame.columns]
    head = frame.head(n)[cols]
    return jsonable(head.astype(object).where(pd.notna(head), None).to_dict(orient="records"))


ASSET_COLUMNS = [
    "name", "asset_type", "osm_element", "osm_id", "baseline_risk_class",
    "scenario_risk_class", "scenario_risk_score", "risk_delta", "distance_to_track_km",
    "nearest_track_wind_kmh", "elevation_m", "status",
]


def compact_scored_data(scenario_assets: pd.DataFrame, top_n: int = TOP_N) -> dict[str, Any]:
    """Counts + top-N view of a baseline-vs-scenario comparison frame."""
    high = ("HIGH", "CRITICAL")
    by_type: dict[str, dict[str, int]] = {}
    for asset_type in sorted(scenario_assets["asset_type"].unique()):
        rows = scenario_assets[scenario_assets["asset_type"] == asset_type]
        by_type[asset_type] = {
            "assets": int(len(rows)),
            "baseline_high_plus": int(rows["baseline_risk_class"].isin(high).sum()),
            "scenario_high_plus": int(rows["scenario_risk_class"].isin(high).sum()),
        }
    newly = scenario_assets[scenario_assets["status"].isin(["NEWLY_HIGH_RISK", "NEWLY_CRITICAL"])]
    ranked = scenario_assets.sort_values("scenario_risk_score", ascending=False)
    return {
        "asset_count": int(len(scenario_assets)),
        "baseline_class_counts": jsonable(scenario_assets["baseline_risk_class"].value_counts().to_dict()),
        "scenario_class_counts": jsonable(scenario_assets["scenario_risk_class"].value_counts().to_dict()),
        "by_asset_type": by_type,
        "status_counts": jsonable(scenario_assets["status"].value_counts().to_dict()),
        "top_newly_at_risk": _records(
            newly.sort_values(["risk_delta", "scenario_risk_score"], ascending=False), ASSET_COLUMNS, top_n
        ),
        "top_scenario_risk": _records(ranked, ASSET_COLUMNS, top_n),
        "label": "Screening index, not a damage probability.",
    }


# ---------------------------------------------------------------- bulletin inputs

def register_bulletin_text(text: str) -> str:
    """Store bulletin text for the agent; returns the run_id to pass as context."""
    run_id = new_run_id("bulletin_text")
    get_store().put(run_id, "bulletin_text", {"text": text})
    return run_id


def register_bulletin_file(data: bytes, mime_type: str, filename: str) -> str:
    run_id = new_run_id("bulletin_file")
    store = get_store()
    store.put(run_id, "bulletin_file", {"mime_type": mime_type, "filename": filename})
    store.put_blob(run_id, "file.bin", data)
    return run_id


class ParseBulletinArgs(BaseModel):
    source_run_id: str = Field(
        description="run_id of an uploaded bulletin (kind bulletin_text or bulletin_file) from the context."
    )


@tool("parse_bulletin", agent_scopes={"forecast"})
def parse_bulletin_tool(args: ParseBulletinArgs) -> Any:
    """Extract structured fields from an uploaded cyclone bulletin (text, PDF or image) using
    schema-constrained multimodal parsing. Returns current position, movement, wind, pressure,
    forecast points and landfall text exactly as stated in the bulletin. Null means the
    bulletin did not state it. Use first when a bulletin run_id is provided."""
    from services.bulletin_parser import parse_bulletin_file, parse_bulletin_text

    store = get_store()
    record = store.get(args.source_run_id)
    if record["kind"] == "bulletin_text":
        bulletin = parse_bulletin_text(record["payload"]["text"])
    elif record["kind"] == "bulletin_file":
        meta = record["payload"]
        bulletin = parse_bulletin_file(
            store.get_blob(args.source_run_id, "file.bin"), meta["mime_type"], meta["filename"]
        )
    else:
        return error_result("parse_bulletin", f"{args.source_run_id} is not a bulletin (kind={record['kind']})")
    run_id = new_run_id("bulletin")
    payload = jsonable(bulletin.model_dump())
    store.put(run_id, "bulletin", payload)
    return ok_result(
        "parse_bulletin", payload, source="gemini:bulletin_parser", run_id=run_id, model_version="parser-v1"
    )


# ---------------------------------------------------------------- scoring

class ScoreTrackArgs(BaseModel):
    track_run_id: str = Field(description="run_id of a stored track (kind 'track'), e.g. from bulletin_to_track.")


@tool("score_track", agent_scopes={"impact"})
def score_track_tool(args: ScoreTrackArgs) -> Any:
    """Score all 3,977 hospitals, schools, shelters and substations against a stored track using
    the frozen v1 screening model and compare with the historical Michaung baseline. Returns
    class counts, per-asset-type high-risk counts and the top 15 assets. Risk values are
    screening indices, not damage probabilities."""
    from services.scenario_engine import score_custom_track

    store = get_store()
    track = store.get_frame(args.track_run_id, "track")
    scored = score_custom_track(track)
    run_id = new_run_id("score")
    data = compact_scored_data(scored)
    store.put(run_id, "score", {"track_run_id": args.track_run_id, "summary": data})
    store.put_frame(run_id, "assets", scored)
    return ok_result("score_track", data, source="risk_model_v1", run_id=run_id)


class RunScenarioArgs(BaseModel):
    north_shift_km: float = Field(default=0.0, ge=-300, le=300, description="Shift the whole track north (+) or south (-), km.")
    east_shift_km: float = Field(default=0.0, ge=-300, le=300, description="Shift the whole track east (+) or west (-), km.")
    intensity_change_pct: float = Field(default=0.0, ge=-50, le=100, description="Change wind speed by this percent.")


@tool("run_scenario", agent_scopes={"impact"})
def run_scenario_tool(args: RunScenarioArgs) -> Any:
    """What-if: shift the Michaung reference track (north/east in km) and/or change wind intensity
    (percent), then rescore all assets with the frozen v1 model. Returns counts of assets that
    become newly HIGH or CRITICAL, per-asset-type high-risk counts and the top 15 newly-at-risk
    assets. Runs in well under a second."""
    from services.scenario_engine import run_scenario

    assets, shifted_track, summary = run_scenario(
        args.north_shift_km, args.east_shift_km, args.intensity_change_pct, save_outputs=False
    )
    run_id = new_run_id("scenario")
    store = get_store()
    store.put(run_id, "scenario", {"summary": jsonable(summary)})
    store.put_frame(run_id, "assets", assets)
    store.put_frame(run_id, "track", shifted_track)
    data = compact_scored_data(assets)
    data["scenario_parameters"] = summary["scenario_parameters"]
    data["runtime_seconds"] = summary["runtime_seconds"]
    for key in (
        "newly_high_risk_hospitals", "newly_critical_hospitals", "newly_high_risk_substations",
        "newly_critical_substations", "assets_risk_increased", "assets_risk_decreased",
    ):
        data[key] = summary[key]
    return ok_result("run_scenario", data, source="scenario_engine:risk_model_v1", run_id=run_id)


class ExperimentalForecastArgs(BaseModel):
    cutoff: str = Field(
        default="2023-12-03 12:00:00",
        description="Forecast issue time (UTC, 'YYYY-MM-DD HH:MM:SS'). Only fixes at or before it are used.",
    )
    include_impacts: bool = Field(default=True, description="Also score assets under the experimental tracks.")


@tool("experimental_forecast", agent_scopes={"forecast"})
def experimental_forecast_tool(args: ExperimentalForecastArgs) -> Any:
    """Run SurgeSight's experimental track forecast (position-only Kalman filter and wind-informed
    model) from a cutoff time using only earlier observations, verify it against later fixes,
    and compare infrastructure impact with the reference track. Labelled experimental: not an
    official forecast; IMD remains authoritative."""
    from services.track_forecaster import run_experimental_forecast
    from services.wind_provider import WindDataUnavailable, load_wind_grid

    track = pd.read_csv(load_region().path("track"))
    try:
        wind_grid = load_wind_grid(track, allow_download=False)
    except WindDataUnavailable:
        wind_grid = None
    result = run_experimental_forecast(
        track, pd.Timestamp(args.cutoff), wind_grid=wind_grid, include_impacts=args.include_impacts
    )
    summary = result["summary"]
    compact = {
        k: summary[k]
        for k in (
            "forecast_label", "disclaimer", "cutoff_time", "observations_used",
            "last_observation_time", "reference_positions", "wind_model_status", "runtime_seconds",
        )
        if k in summary
    }
    compact["models"] = {
        name: {
            "label": model["label"],
            "forecast": model["forecast"],
            "verification_error_km": model["verification_error_km"],
        }
        for name, model in summary["models"].items()
    }
    if "infrastructure_impact" in summary:
        compact["infrastructure_impact"] = summary["infrastructure_impact"]
    run_id = new_run_id("forecast")
    get_store().put(run_id, "forecast", {"summary": jsonable(compact)})
    return ok_result("experimental_forecast", jsonable(compact), source="track_forecaster", run_id=run_id)


class ExplainScenarioArgs(BaseModel):
    run_id: str = Field(description="run_id returned by run_scenario.")


@tool("explain_scenario", agent_scopes={"impact"})
def explain_scenario_tool(args: ExplainScenarioArgs) -> Any:
    """Produce a grounded plain-language operational explanation of a run_scenario result
    (headline, implications, affected assets). Numbers in it come from that run only."""
    from services.scenario_explainer import explain_scenario

    store = get_store()
    record = store.get(args.run_id)
    if record["kind"] != "scenario":
        return error_result("explain_scenario", f"{args.run_id} is not a scenario run")
    explanation = explain_scenario(store.get_frame(args.run_id, "assets"), record["payload"]["summary"])
    payload = jsonable(explanation.model_dump())
    run_id = new_run_id("explanation")
    store.put(run_id, "explanation", payload)
    return ok_result("explain_scenario", payload, source="gemini:scenario_explainer", run_id=run_id)


# ---------------------------------------------------------------- communication

class DraftAdvisoryArgs(BaseModel):
    audience: Literal[
        "District Collector / Disaster Management", "Electricity Board", "Health Department"
    ] = Field(description="Which department the advisory is for.")
    language: Literal["English", "Tamil", "Telugu"] = "English"


@tool("draft_advisory", agent_scopes={"department"})
def draft_advisory_tool(args: DraftAdvisoryArgs) -> Any:
    """Draft a role-specific advisory (severity, situation summary, priority actions, critical
    assets, disclaimer) for a department in English, Tamil or Telugu from the deterministic
    baseline risk data. Severity, asset list and disclaimer are set from data, not by the model."""
    from services.advisory import generate_role_advisory

    advisory = generate_role_advisory(args.audience, args.language)
    payload = jsonable(advisory.model_dump())
    payload["language"] = args.language
    run_id = new_run_id("advisory")
    get_store().put(run_id, "advisory", payload)
    return ok_result("draft_advisory", payload, source="advisory", run_id=run_id)


class SynthesizeSpeechArgs(BaseModel):
    advisory_run_id: str = Field(description="run_id returned by draft_advisory.")
    language: Literal["English", "Tamil", "Telugu"] = "English"


@tool("synthesize_speech", agent_scopes={"comms"})
def synthesize_speech_tool(args: SynthesizeSpeechArgs) -> Any:
    """Turn a drafted advisory into spoken MP3 audio (Google Cloud Text-to-Speech) in English,
    Tamil or Telugu. Returns an audio run_id the UI can play; audio is not sent to Gemini."""
    from services.advisory import RoleAdvisory
    from services.tts import synthesize_advisory

    store = get_store()
    record = store.get(args.advisory_run_id)
    if record["kind"] != "advisory":
        return error_result("synthesize_speech", f"{args.advisory_run_id} is not an advisory run")
    payload = {k: v for k, v in record["payload"].items() if k != "language"}
    audio = synthesize_advisory(RoleAdvisory.model_validate(payload), args.language)
    run_id = new_run_id("audio")
    store.put(run_id, "audio", {"language": args.language, "bytes": len(audio), "advisory_run_id": args.advisory_run_id})
    store.put_blob(run_id, "audio.mp3", audio)
    return ok_result(
        "synthesize_speech",
        {"language": args.language, "audio_bytes": len(audio)},
        source="google_cloud_tts",
        run_id=run_id,
    )


# ---------------------------------------------------------------- lookup

class GetAssetDetailsArgs(BaseModel):
    osm_element: Literal["node", "way", "relation"]
    osm_id: int
    run_id: str | None = Field(default=None, description="Optional scenario/score run_id to include scenario values.")


@tool("get_asset_details", agent_scopes={"impact", "department"})
def get_asset_details_tool(args: GetAssetDetailsArgs) -> Any:
    """Look up one asset's full deterministic fields (location, elevation, wind, scores, class) by
    OSM element type and id, optionally with its values from a scenario or score run."""
    baseline = pd.read_csv(load_region().path("scored_assets"))
    row = baseline[(baseline["osm_element"] == args.osm_element) & (baseline["osm_id"] == args.osm_id)]
    if row.empty:
        return error_result("get_asset_details", f"No asset {args.osm_element}/{args.osm_id}")
    data: dict[str, Any] = {"baseline": jsonable(row.iloc[0].dropna().to_dict())}
    if args.run_id:
        frame = get_store().get_frame(args.run_id, "assets")
        match = frame[(frame["osm_element"] == args.osm_element) & (frame["osm_id"] == args.osm_id)]
        if not match.empty:
            data["run"] = jsonable(match.iloc[0].dropna().to_dict())
    return ok_result("get_asset_details", data, source="scored_assets", run_id=args.run_id)
