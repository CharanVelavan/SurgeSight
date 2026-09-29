"""Tools for probabilistic exposure and (later) rainfall, surge and v2 hazards."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from services.agent.builtin_tools import jsonable
from services.agent.tools import error_result, ok_result, tool
from services.store import get_store, new_run_id


class RunEnsembleArgs(BaseModel):
    members: int = Field(default=100, ge=10, le=500, description="Number of perturbed tracks.")
    seed: int = Field(default=42, description="Random seed; the same seed gives the same result.")
    center_shift_n_km: float = Field(default=0.0, ge=-50, le=50, description="Centre of the ensemble: shift north (+) / south (-), km.")
    center_shift_e_km: float = Field(default=0.0, ge=-50, le=50, description="Centre of the ensemble: shift east (+) / west (-), km.")
    center_intensity_pct: float = Field(default=0.0, ge=-20, le=20, description="Centre of the ensemble: wind change, percent.")
    sigma_km: float | None = Field(default=None, ge=0, le=150, description="Per-axis track spread in km. Omit to use the measured 12-hour forecast error.")


@tool("run_ensemble", agent_scopes={"forecast", "impact"})
def run_ensemble_tool(args: RunEnsembleArgs) -> Any:
    """Probabilistic exposure: score many perturbed tracks (spread taken from the measured
    track-forecast error) and rank assets by the share of members in which they reach HIGH or
    CRITICAL, weighted by criticality. Use it when the officer asks which assets are most likely
    at risk, or how uncertainty in the track changes priorities. Returns the top 15 assets per
    type with 'HIGH or worse in k/N members' and a run_id. Probabilities describe the screening
    class under track uncertainty, not damage."""
    from services.ensemble import run_ensemble

    result = run_ensemble(
        members=args.members, seed=args.seed, center_shift_n_km=args.center_shift_n_km,
        center_shift_e_km=args.center_shift_e_km, center_intensity_pct=args.center_intensity_pct,
        sigma_km=args.sigma_km,
    )
    run_id = new_run_id("ensemble")
    store = get_store()
    store.put(run_id, "ensemble", jsonable({
        "parameters": result.parameters, "summary": result.summary,
        "top_by_type": result.top_by_type, "spaghetti_geojson": result.spaghetti_geojson,
    }))
    store.put_frame(run_id, "assets", result.assets)
    data = jsonable({
        "parameters": result.parameters,
        "by_asset_type": result.summary["by_asset_type"],
        "top_by_type": result.top_by_type,
        "uncertainty_calibration": result.summary["uncertainty_calibration"],
        "label": result.summary["label"],
        "hospital_note": "Hospital ranking excludes OSM records that are clinics, dental or eye-care sites.",
    })
    return ok_result("run_ensemble", data, source="ensemble:risk_model_v1", run_id=run_id, model_version=result.parameters["model_version"])


# ---------------------------------------------------------------- v2 hazards

class HazardScenarioArgs(BaseModel):
    north_shift_km: float = Field(default=0.0, ge=-50, le=50, description="Shift the Michaung reference track north (+) / south (-), km.")
    east_shift_km: float = Field(default=0.0, ge=-50, le=50, description="Shift the track east (+) / west (-), km.")
    intensity_change_pct: float = Field(default=0.0, ge=-20, le=20, description="Change wind speed by this percent.")


def _scenario_track(args: HazardScenarioArgs):
    import pandas as pd

    from services.config import load_region
    from services.scenario_engine import shift_track_geodesically

    track = pd.read_csv(load_region().path("track"))
    return shift_track_geodesically(track, args.north_shift_km, args.east_shift_km, args.intensity_change_pct)


def _top_v2(frame, n: int = 15) -> list[dict[str, Any]]:
    cols = ["name", "asset_type", "osm_element", "osm_id", "v1_class", "class_v2", "combined_v2",
            "dominant_hazard", "wind_kmh_v2", "surge_m", "rain_mm", "triage_tier"]
    ranked = frame.sort_values("combined_v2", ascending=False).head(n)[cols]
    return jsonable(ranked.to_dict(orient="records"))


@tool("risk_v2", agent_scopes={"impact"})
def risk_v2_tool(args: HazardScenarioArgs) -> Any:
    """Score every asset with risk model v2, which combines a modelled wind field (Holland profile),
    a screening storm-surge index and rainfall-on-terrain flooding, optionally after shifting the
    Michaung track or changing intensity. Returns v1 vs v2 class counts, the dominant hazard per
    asset, triage tiers (1 = highest relative priority) and the top 15 assets with their hazard
    breakdown. Rainfall is the pre-landfall GFS forecast, not observed. Absolute classes are high
    across this corridor because the whole corridor was hit hard; use triage tiers to rank."""
    from services.risk_model_v2 import class_distribution, score_v2
    import pandas as pd

    from services.config import load_region

    assets = pd.read_csv(load_region().path("scored_assets"))
    frame, meta = score_v2(_scenario_track(args), assets)
    run_id = new_run_id("riskv2")
    store = get_store()
    store.put(run_id, "riskv2", jsonable({"meta": meta, "parameters": args.model_dump()}))
    store.put_frame(run_id, "assets", frame)
    hospitals = frame[(frame["asset_type"] == "hospital") & (frame["facility_quality"] == "hospital")]
    data = {
        "parameters": args.model_dump(),
        "v1_class_counts": class_distribution(frame, "v1_class"),
        "v2_class_counts": class_distribution(frame, "class_v2"),
        "dominant_hazard_counts": frame["dominant_hazard"].value_counts().to_dict(),
        "triage_tier_counts": frame["triage_tier"].value_counts().sort_index().to_dict(),
        "hospitals_only": {
            "count": int(len(hospitals)),
            "v2_high_plus": int(hospitals["class_v2"].isin(["HIGH", "CRITICAL"]).sum()),
            "tier_1": int((hospitals["triage_tier"] == 1).sum()),
        },
        "top_assets": _top_v2(frame),
        "surge": {k: meta["surge"].get(k) for k in ("peak_surge_m", "inverse_barometer_m", "wind_setup_m", "shelf_mean_depth_m", "landfall")},
        "rain": meta["rain"],
        "label": meta["label"],
        "surge_label": meta["surge_label"],
        "note": "Hospital counts use real hospitals only (OSM clinics and dental sites excluded).",
    }
    return ok_result("risk_v2", jsonable(data), source="risk_model_v2", run_id=run_id, model_version=meta["model_version"])


@tool("surge_hazard", agent_scopes={"impact"})
def surge_hazard_tool(args: HazardScenarioArgs) -> Any:
    """Screening storm-surge index for the Michaung track (optionally shifted): landfall point,
    inverse-barometer and wind-setup components, peak surge in metres, and the coastal assets
    (within 10 km of the coast and below the surge level) that surge would reach. It is a
    screening index built from published formulas, not a hydrodynamic surge model."""
    import pandas as pd

    from services.config import load_region
    from services.hazards.surge import surge_scores

    assets = pd.read_csv(load_region().path("scored_assets"))
    frame, info = surge_scores(_scenario_track(args), assets)
    merged = assets[["name", "asset_type", "osm_element", "osm_id", "elevation_m"]].merge(frame, on=["osm_element", "osm_id"])
    reached = merged[merged["surge_score"] > 0].sort_values("surge_score", ascending=False)
    run_id = new_run_id("surge")
    get_store().put(run_id, "surge", jsonable({"info": {k: v for k, v in info.items() if k != "constants"}, "parameters": args.model_dump()}))
    get_store().put_frame(run_id, "assets", merged)
    data = {
        "parameters": args.model_dump(),
        "landfall": info["landfall"],
        "peak_surge_m": info["peak_surge_m"],
        "inverse_barometer_m": info.get("inverse_barometer_m"),
        "wind_setup_m": info.get("wind_setup_m"),
        "shelf_mean_depth_m": info.get("shelf_mean_depth_m"),
        "assets_reached": int(len(reached)),
        "assets_reached_by_type": reached["asset_type"].value_counts().to_dict(),
        "top_assets": jsonable(reached.head(15)[["name", "asset_type", "osm_element", "osm_id", "elevation_m", "surge_m", "surge_score", "coast_side"]].to_dict(orient="records")),
        "warnings": info["warnings"],
        "label": info["label"],
    }
    return ok_result("surge_hazard", jsonable(data), source="hazards.surge", run_id=run_id, model_version="surge-screening-v1")


class RainfallHazardArgs(BaseModel):
    mode: Literal["forecast", "observed"] = Field(
        default="forecast",
        description="'forecast' = GFS run issued at the cutoff (a valid pre-landfall input). "
        "'observed' = satellite IMERG after the fact: validation only, never a prediction input.",
    )


@tool("rainfall_hazard", agent_scopes={"impact"})
def rainfall_hazard_tool(args: RainfallHazardArgs) -> Any:
    """Rainfall across the assets: forecast (NOAA GFS run issued 2023-12-03 12:00 UTC, next 72 h)
    or observed (NASA GPM IMERG, validation only). Returns mean/peak totals, counts of assets in
    each IMD 24-hour rainfall class (heavy 64.5-115.5 mm, very heavy 115.6-204.4 mm, extremely heavy
    204.5 mm and above) and the wettest assets. In 'observed' mode the result is labelled
    validation-only; it must not be presented as a pre-landfall forecast."""
    import pandas as pd

    from services.config import load_region
    from services.hazards.rainfall import imd_category, rain_inputs

    assets = pd.read_csv(load_region().path("scored_assets"))
    rain, meta = rain_inputs(args.mode, hindcast=True)
    frame = assets[["name", "asset_type", "osm_element", "osm_id"]].merge(rain, on=["osm_element", "osm_id"])
    frame["imd_24h_class"] = frame["peak_24h_mm"].apply(lambda v: imd_category(v) if pd.notna(v) else "n/a")
    data = {
        "mode": args.mode, "validation_only": meta["validation_only"], "note": meta["note"],
        "total_mm": {"mean": round(float(frame["accum_mm"].mean()), 1), "max": round(float(frame["accum_mm"].max()), 1)},
        "peak_24h_mm": {"mean": round(float(frame["peak_24h_mm"].mean()), 1), "max": round(float(frame["peak_24h_mm"].max()), 1)},
        "imd_24h_class_counts": frame["imd_24h_class"].value_counts().to_dict(),
        "wettest_assets": jsonable(frame.sort_values("accum_mm", ascending=False).head(10)[["name", "asset_type", "osm_element", "osm_id", "accum_mm", "peak_24h_mm", "imd_24h_class"]].to_dict(orient="records")),
    }
    warnings = ["Observed rainfall is for validation only, not a pre-landfall input."] if meta["validation_only"] else []
    return ok_result("rainfall_hazard", jsonable(data), source="NOAA/GFS0P25" if args.mode == "forecast" else "NASA/GPM_L3/IMERG_V07", warnings=warnings, model_version="rain-v1")


# ---------------------------------------------------------------- exposure

class ExposureArgs(BaseModel):
    run_id: str = Field(description="run_id of a risk_v2, run_ensemble, run_scenario or score_track result.")
    rule: Literal["class_high_plus", "triage_tier_1_2", "ensemble_p50"] | None = Field(
        default=None,
        description="Which assets define the hazard footprint. class_high_plus = HIGH or CRITICAL; "
        "triage_tier_1_2 = top 30% relative priority (risk_v2 runs); ensemble_p50 = HIGH+ in at least "
        "half of the members (run_ensemble runs). Omit to pick the natural rule for the run.",
    )
    radius_km: float = Field(default=5.0, ge=1, le=25, description="Footprint radius around each qualifying asset, km.")


@tool("exposure_summary", agent_scopes={"impact"})
def exposure_summary_tool(args: ExposureArgs) -> Any:
    """Exposed people and buildings per district for a stored run: population (WorldPop) and buildings
    (Google Open Buildings) inside the footprint of the assets that meet a rule (HIGH or above, top
    triage tiers, or likely under the ensemble). Use it to answer 'how many people / buildings /
    which districts are affected'. 'Exposed' means inside the hazard footprint; it is not a casualty or
    damage estimate. Districts are listed by exposed population."""
    from services.exposure import exposure_summary

    store = get_store()
    record = store.get(args.run_id)
    kind = record["kind"]
    if kind not in {"riskv2", "ensemble", "scenario", "score", "surge"}:
        return error_result("exposure_summary", f"{args.run_id} is a '{kind}' run; use a risk_v2, run_ensemble, run_scenario or score_track run")
    frame = store.get_frame(args.run_id, "assets")
    rule = args.rule or ("ensemble_p50" if kind == "ensemble" else "class_high_plus")
    summary = exposure_summary(frame, rule=rule, radius_km=args.radius_km, include_footprint=True)
    footprint = summary.pop("footprint_geojson")
    run_id = new_run_id("exposure")
    store.put(run_id, "exposure", jsonable({"source_run_id": args.run_id, "summary": summary, "footprint_geojson": footprint}))
    compact = dict(summary)
    compact["by_district"] = summary["by_district"][:10]
    compact["districts_listed"] = f"top {len(compact['by_district'])} of {len(summary['by_district'])} by exposed population"
    return ok_result("exposure_summary", jsonable(compact), source="exposure_grid", run_id=run_id)
