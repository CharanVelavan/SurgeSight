"""Read and compute endpoints: regions, tracks, assets, bulletins, scenarios, ensembles, hazards, exposure."""

from __future__ import annotations

import mimetypes
from typing import Any, Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
import pandas as pd
from pydantic import BaseModel, Field

from api.deps import CLASS_RANK, call_tool, geojson, normalised, require_region, run_frame, stored, tool_payload
from services.agent.builtin_tools import jsonable, register_bulletin_file, register_bulletin_text
from services.config import list_regions, load_region

router = APIRouter()


@router.get("/api/regions")
def regions() -> list[dict[str, Any]]:
    regions = [load_region(region_id) for region_id in list_regions()]
    return [{"id": r.id, "display_name": r.display_name, "cyclone_name": r.cyclone_name, "languages": list(r.languages),
             "demo_cutoff": r.demo_cutoff, "extent": r.extent} for r in regions]


@router.get("/api/regions/{region_id}/track")
def region_track(region_id: str) -> dict[str, Any]:
    region = load_region(require_region(region_id))
    track = pd.read_csv(region.path("track"))
    return {"region": region.id, "points": jsonable(track.astype(object).where(track.notna(), None).to_dict(orient="records"))}


@router.get("/api/assets")
def assets(region: str | None = None, dept: str | None = None, min_class: Literal["LOW", "MODERATE", "HIGH", "CRITICAL"] = "LOW",
           run_id: str | None = Query(None, description="A stored run with an assets table. Omit for the v2 baseline."),
           format: Literal["geojson", "columnar"] = Query("geojson", description="columnar: parallel arrays, about a fifth of the size")) -> dict[str, Any]:
    """Assets as GeoJSON (or columnar arrays for the web map), optionally for one department and a minimum class."""
    from services.departments import department_mask, get_department, score_all_assets

    require_region(region)
    frame = normalised(run_frame(run_id) if run_id else score_all_assets())
    if dept:
        try:
            frame = frame[department_mask(get_department(dept), frame)]
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc).strip("'\"")) from None
    frame = frame[frame["risk_class"].map(CLASS_RANK).fillna(0) >= CLASS_RANK[min_class]]
    if format == "columnar":
        cols = [c for c in ("name", "asset_type", "osm_element", "osm_id", "risk_class", "risk_score", "triage_tier", "dominant_hazard", "facility_quality") if c in frame.columns]
        out = {"count": len(frame), "run_id": run_id, "class_order": list(CLASS_RANK),
               "lon": [round(float(v), 5) for v in frame["lon"]], "lat": [round(float(v), 5) for v in frame["lat"]],
               "risk_class_rank": [int(v) for v in frame["risk_class"].map(CLASS_RANK).fillna(0)]}
        out.update({c: jsonable(frame[c].astype(object).where(frame[c].notna(), None).tolist()) for c in cols})
        return out
    body = geojson(frame, ["name", "asset_type", "osm_element", "osm_id", "risk_class", "risk_score", "triage_tier", "dominant_hazard"])
    body["count"] = len(body["features"])
    body["run_id"] = run_id
    return body


@router.post("/api/bulletin/parse")
async def bulletin_parse(file: UploadFile | None = File(None), text: str | None = Form(None)) -> dict[str, Any]:
    """Parse a bulletin (upload a text/PDF/image file, or pass ``text``). Returns the structured bulletin and its run_id."""
    if (file is None) == (text is None):
        raise HTTPException(status_code=422, detail="Send exactly one of file or text")
    if file is not None:
        data = await file.read()
        mime = file.content_type or mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream"
        source = register_bulletin_file(data, mime, file.filename or "bulletin")
    else:
        source = register_bulletin_text(text or "")
    return tool_payload(call_tool("parse_bulletin", {"source_run_id": source})) | {"source_run_id": source}


class BulletinScoreBody(BaseModel):
    bulletin_run_id: str


@router.post("/api/bulletin/score")
def bulletin_score(body: BulletinScoreBody) -> dict[str, Any]:
    """Bulletin run -> track -> v1 score. Returns the track and the score run_id."""
    track = call_tool("bulletin_to_track", {"bulletin_run_id": body.bulletin_run_id})
    score = call_tool("score_track", {"track_run_id": track.run_id})
    return {"track": tool_payload(track), "score": tool_payload(score)}


class ScenarioBody(BaseModel):
    north_shift_km: float = Field(default=0.0, ge=-50, le=50)
    east_shift_km: float = Field(default=0.0, ge=-50, le=50)
    intensity_change_pct: float = Field(default=0.0, ge=-20, le=20)


@router.post("/api/scenario")
def scenario(body: ScenarioBody) -> dict[str, Any]:
    return tool_payload(call_tool("run_scenario", body.model_dump()))


class EnsembleBody(BaseModel):
    members: int = Field(default=100, ge=10, le=500)
    seed: int = 42
    center_shift_n_km: float = Field(default=0.0, ge=-50, le=50)
    center_shift_e_km: float = Field(default=0.0, ge=-50, le=50)
    center_intensity_pct: float = Field(default=0.0, ge=-20, le=20)
    sigma_km: float | None = Field(default=None, ge=0, le=150)


@router.post("/api/ensemble")
def ensemble(body: EnsembleBody) -> dict[str, Any]:
    return tool_payload(call_tool("run_ensemble", body.model_dump(exclude_none=True)))


@router.get("/api/forecast/experimental")
def experimental_forecast(cutoff: str = "2023-12-03 12:00:00", horizon: int = Query(24, description="Lead time to highlight, hours")) -> dict[str, Any]:
    result = tool_payload(call_tool("experimental_forecast", {"cutoff": cutoff, "include_impacts": False}))
    for model in result["data"].get("models", {}).values():
        model["forecast"] = [p for p in model["forecast"] if p["lead_hours"] <= horizon]
    return result


@router.get("/api/hazards/{run_id}")
def hazards(run_id: str) -> dict[str, Any]:
    """Wind / surge / rain breakdown of a risk_v2 run."""
    record = stored(run_id)
    if record["kind"] != "riskv2":
        raise HTTPException(status_code=422, detail=f"{run_id} is a '{record['kind']}' run; hazards need a risk_v2 run")
    frame = run_frame(run_id)
    return {"run_id": run_id, "meta": record["payload"].get("meta"), "parameters": record["payload"].get("parameters"),
            "class_counts": jsonable(frame["class_v2"].value_counts().to_dict()),
            "dominant_hazard_counts": jsonable(frame["dominant_hazard"].value_counts().to_dict()),
            "triage_tier_counts": jsonable(frame["triage_tier"].value_counts().sort_index().to_dict()),
            "top_assets": jsonable(frame.sort_values("combined_v2", ascending=False).head(15)[
                ["name", "asset_type", "class_v2", "combined_v2", "dominant_hazard", "wind_kmh_v2", "surge_m", "rain_mm", "triage_tier"]].to_dict(orient="records"))}


@router.post("/api/risk_v2")
def risk_v2(body: ScenarioBody) -> dict[str, Any]:
    """Run risk model v2 (optionally after a what-if shift); the run_id feeds /api/hazards, /api/exposure, /api/advisory."""
    return tool_payload(call_tool("risk_v2", body.model_dump()))


@router.get("/api/exposure/{run_id}")
def exposure(run_id: str, rule: Literal["class_high_plus", "triage_tier_1_2", "ensemble_p50"] | None = None, radius_km: float = Query(5.0, ge=1, le=25)) -> dict[str, Any]:
    args: dict[str, Any] = {"run_id": run_id, "radius_km": radius_km}
    if rule:
        args["rule"] = rule
    stored(run_id)
    return tool_payload(call_tool("exposure_summary", args))


@router.get("/api/validation/satellite/{run_id}")
def satellite(run_id: str) -> dict[str, Any]:
    """Satellite validation of a risk_v2 run, or of the baseline when run_id is 'baseline'."""
    args = {} if run_id == "baseline" else {"run_id": run_id}
    if args:
        stored(run_id)
    return tool_payload(call_tool("satellite_validation", args))


@router.get("/runs/{run_id}")
def run(run_id: str) -> dict[str, Any]:
    record = stored(run_id)
    return jsonable(record)
