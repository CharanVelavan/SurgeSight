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


# ---------------------------------------------------------------- satellite validation

class SatelliteValidationArgs(BaseModel):
    run_id: str | None = Field(default=None, description="A risk_v2 run_id to validate. Omit to validate the historical Michaung baseline.")
    include_review: bool = Field(default=True, description="Include the cached Gemini multimodal review of the maps, if one exists.")


@tool("satellite_validation", agent_scopes={"impact"})
def satellite_validation_tool(args: SatelliteValidationArgs) -> Any:
    """Validate the screening against satellite observation of Cyclone Michaung (hindcast): share of
    assets with an observed flood signal, how well each risk score ranks flooded above unflooded assets
    (AUC: 0.5 = no skill), HIGH+ hit and false-alarm rates for v1 and v2, and rates by asset type and
    district. Uses Sentinel-2 water mapping because Sentinel-1 did not image the area. It is a proxy for
    flooding on the scene dates with cloud gaps; unobserved assets are excluded."""
    import pandas as pd

    from services.config import load_region
    from services.risk_model_v2 import score_v2
    from services.satellite_validation import REVIEW_FILE, compute_metrics, load_observed

    observed, meta = load_observed()
    store = get_store()
    if args.run_id:
        record = store.get(args.run_id)
        if record["kind"] != "riskv2":
            return error_result("satellite_validation", f"{args.run_id} is a '{record['kind']}' run; pass a risk_v2 run or omit run_id")
        frame = store.get_frame(args.run_id, "assets")
    else:
        region = load_region()
        frame, _ = score_v2(pd.read_csv(region.path("track")), pd.read_csv(region.path("scored_assets")))
    metrics = compute_metrics(frame, observed, meta)
    data: dict[str, Any] = {"metrics": metrics}
    if args.include_review and REVIEW_FILE.exists():
        import json

        data["gemini_review"] = json.loads(REVIEW_FILE.read_text(encoding="utf-8"))["review"]
    run_id = new_run_id("satval")
    store.put(run_id, "satellite_validation", jsonable(data))
    warnings = ["Observed flood flag is a remote-sensing proxy; Sentinel-1 had no usable coverage."] if meta["sensor"] == "sentinel2" else []
    return ok_result("satellite_validation", jsonable(data), source=f"{meta['sensor']}:flood_flag", run_id=run_id, warnings=warnings, model_version="satval-v1")


# ---------------------------------------------------------------- live search

class SearchBulletinsArgs(BaseModel):
    cyclone_name: str | None = Field(default=None, description="Cyclone name, for example 'Michaung'. Omit to look for any active cyclone.")
    region: str = Field(default="Andhra Pradesh and Tamil Nadu coast, India", description="Area of interest in words.")


@tool("search_latest_bulletins", agent_scopes={"forecast", "comms"})
def search_latest_bulletins_tool(args: SearchBulletinsArgs) -> Any:
    """Find the latest published cyclone bulletins and news with Google Search grounding, with cited
    sources. Use it in live mode or when the officer asks what the official sources are saying now.
    Returns a summary and a list of source links. Web reports are not verified by SurgeSight; they
    do not feed the risk model unless the officer pastes a bulletin to parse."""
    from services.search_grounding import search_latest_bulletins

    result = search_latest_bulletins(args.cyclone_name, args.region)
    warnings = [] if result["grounded"] else ["No cited sources were returned; treat the summary as unverified."]
    return ok_result("search_latest_bulletins", jsonable(result), source="gemini:google_search", warnings=warnings)


# ---------------------------------------------------------------- independent NWP

class NwpComparisonArgs(BaseModel):
    cutoff: str | None = Field(default=None, description="Forecast issue time, UTC, for example '2023-12-03 12:00'. Omit for the demo cutoff.")


@tool("nwp_comparison", agent_scopes={"forecast"})
def nwp_comparison_tool(args: NwpComparisonArgs) -> Any:
    """Compare SurgeSight's experimental (Kalman) track forecast with an independent numerical
    weather prediction: the NOAA GFS forecast run issued at the cutoff, analysed in Google Earth
    Engine. Returns, per lead time, the GFS storm centre and peak 10 m wind, the Kalman position, the
    distance between them, and (validation only) the error of each against the observed track. Use it
    to say whether an independent model agrees with the statistical track. Not an official forecast."""
    import json

    import pandas as pd

    from services.config import load_region
    from services.nwp_comparison import nwp_comparison

    region = load_region()
    cutoff = args.cutoff or region.demo_cutoff
    cache = region.path("nwp_comparison")
    result = None
    if cache.exists():
        cached = json.loads(cache.read_text(encoding="utf-8"))
        if pd.Timestamp(cached["cutoff_utc"]).tz_localize(None) == pd.Timestamp(cutoff).tz_localize(None):
            result = cached
    if result is None:
        result = nwp_comparison(pd.read_csv(region.path("track")), cutoff)
    run_id = new_run_id("nwp")
    get_store().put(run_id, "nwp_comparison", jsonable(result))
    return ok_result("nwp_comparison", jsonable(result), source="noaa_gfs:earth_engine", run_id=run_id, model_version="gfs-vortex-v1")


# ---------------------------------------------------------------- river flood

class RiverFloodArgs(BaseModel):
    top_n: int = Field(default=15, ge=1, le=15, description="How many assets to list per asset type.")


@tool("river_flood", agent_scopes={"impact", "forecast"})
def river_flood_tool(args: RiverFloodArgs) -> Any:
    """River flood screening: which assets sit low beside a drainage line (MERIT Hydro height above
    nearest drainage, analysed in Google Earth Engine) and are under heavy forecast rain. Use it for
    questions about river or inland flooding, as opposed to wind or coastal surge. Returns counts and
    the top assets by river flood index (0 to 1). It is a screening index, not a river-level forecast;
    live river-level forecasts are not available."""
    import pandas as pd

    from services.config import load_region
    from services.hazards.rainfall import rain_inputs
    from services.hazards.river_flood import LABEL, river_flood_frame, summarise

    assets = pd.read_csv(load_region().path("scored_assets"))
    rain, rain_meta = rain_inputs("forecast")
    frame = river_flood_frame(rain, assets)
    if "facility_quality" in assets.columns:
        frame = frame.merge(assets[["osm_element", "osm_id", "facility_quality"]], on=["osm_element", "osm_id"], how="left")
    cols = ["name", "asset_type", "osm_element", "osm_id", "hand_m", "upstream_km2", "rain_mm", "river_flood_index"]
    ranking = frame[frame["facility_quality"].isin(["hospital", "not_applicable"])] if "facility_quality" in frame else frame
    top = {
        str(kind): jsonable(group.sort_values("river_flood_index", ascending=False).head(args.top_n)[cols].to_dict(orient="records"))
        for kind, group in ranking.groupby("asset_type")
    }
    run_id = new_run_id("river")
    store = get_store()
    store.put(run_id, "river_flood", jsonable({"summary": summarise(frame), "top_by_type": top}))
    store.put_frame(run_id, "assets", frame)
    data = jsonable({"summary": summarise(frame), "top_by_type": top, "rain_source": rain_meta.get("source", "GFS forecast"), "label": LABEL,
                     "hospital_note": "Hospital ranking excludes OSM records that are clinics, dental or eye-care sites."})
    return ok_result("river_flood", data, source="merit_hydro+gfs:earth_engine", run_id=run_id, model_version="river-v1")


# ---------------------------------------------------------------- departments

class DepartmentPriorityArgs(BaseModel):
    department: Literal[
        "District Collector / Disaster Management", "Health Department", "Fire & Rescue Services", "Electricity Board",
        "Police / Traffic", "Water & Sewage Board", "Fisheries Department",
    ] = Field(description="Department whose asset view to rank.")
    top_n: int = Field(default=10, ge=1, le=15, description="How many top assets to list.")


@tool("department_priority", agent_scopes={"department", "impact"})
def department_priority_tool(args: DepartmentPriorityArgs) -> Any:
    """Rank one department's own assets (hospitals for Health, fire stations for Fire & Rescue, substations
    for Electricity, police stations, water facilities, fishing harbours, or all types for the Collector) by
    the v2 multi-hazard screening score. Returns class counts, triage tier 1 count, dominant hazards and the
    top assets. Screening indices, not damage probabilities. Roads are not scored."""
    from services.departments import department_priority

    result = department_priority(args.department, n=args.top_n)
    run_id = new_run_id("dept")
    get_store().put(run_id, "department_priority", jsonable(result))
    return ok_result("department_priority", jsonable(result), source="departments:risk_v2", run_id=run_id, model_version="v2")
