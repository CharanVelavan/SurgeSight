"""Deterministic what-if track and intensity simulator for SurgeSight."""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pyproj import Geod

from services.config import load_region
from services.risk_model import attach_nearest_track, score_assets_from_terrain


_REGION = load_region()
TRACK_FILE = _REGION.path("track")
BASELINE_ASSETS_FILE = _REGION.path("scored_assets")
OUTPUT_CSV = _REGION.path("scenario_assets_csv")
OUTPUT_GEOJSON = _REGION.path("scenario_assets_geojson")
OUTPUT_SUMMARY = _REGION.path("scenario_summary")
WGS84 = Geod(ellps="WGS84")
HIGH_RISK_CLASSES = {"HIGH", "CRITICAL"}
RISK_ORDER = {"LOW": 0, "MODERATE": 1, "HIGH": 2, "CRITICAL": 3}


def atomic_json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def load_scenario_inputs(
    track_file: Path = TRACK_FILE,
    assets_file: Path = BASELINE_ASSETS_FILE,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not track_file.exists() or not assets_file.exists():
        raise FileNotFoundError("Run the Michaung track and infrastructure scoring pipelines first")
    track = pd.read_csv(track_file)
    assets = pd.read_csv(assets_file)
    required_track = {"LAT", "LON", "WIND_KMH"}
    required_assets = {
        "lat", "lon", "asset_type", "name", "osm_element", "osm_id",
        "distance_to_track_km", "nearest_track_wind_kmh", "elevation_m",
        "water_occurrence_pct", "wind_score", "terrain_flood_score",
        "combined_risk_score", "risk_class",
    }
    if missing := required_track - set(track.columns):
        raise ValueError(f"Track missing columns: {sorted(missing)}")
    if missing := required_assets - set(assets.columns):
        raise ValueError(f"Baseline assets missing columns: {sorted(missing)}")
    return track, assets


def shift_track_geodesically(
    track: pd.DataFrame,
    north_shift_km: float,
    east_shift_km: float,
    intensity_change_pct: float,
) -> pd.DataFrame:
    """Translate every track point using a WGS84 geodesic displacement."""

    if not -50 <= north_shift_km <= 50:
        raise ValueError("North/south shift must be between -50 and +50 km")
    if not -50 <= east_shift_km <= 50:
        raise ValueError("East/west shift must be between -50 and +50 km")
    if not -20 <= intensity_change_pct <= 20:
        raise ValueError("Intensity change must be between -20% and +20%")

    shifted = track.copy()
    distance_km = math.hypot(north_shift_km, east_shift_km)
    if distance_km:
        azimuth_degrees = math.degrees(math.atan2(east_shift_km, north_shift_km))
        azimuths = np.full(len(shifted), azimuth_degrees)
        distances_m = np.full(len(shifted), distance_km * 1000.0)
        new_lon, new_lat, _ = WGS84.fwd(
            shifted["LON"].to_numpy(dtype=float),
            shifted["LAT"].to_numpy(dtype=float),
            azimuths,
            distances_m,
        )
        shifted["LAT"] = new_lat
        shifted["LON"] = new_lon
    shifted["BASELINE_WIND_KMH"] = pd.to_numeric(shifted["WIND_KMH"], errors="coerce")
    shifted["WIND_KMH"] = (
        shifted["BASELINE_WIND_KMH"] * (1.0 + intensity_change_pct / 100.0)
    ).round(3)
    return shifted


def _status_for_row(row: pd.Series) -> str:
    baseline_class = str(row["baseline_risk_class"])
    scenario_class = str(row["scenario_risk_class"])
    if scenario_class == "CRITICAL" and baseline_class != "CRITICAL":
        return "NEWLY_CRITICAL"
    if baseline_class not in HIGH_RISK_CLASSES and scenario_class in HIGH_RISK_CLASSES:
        return "NEWLY_HIGH_RISK"
    if baseline_class in HIGH_RISK_CLASSES and scenario_class not in HIGH_RISK_CLASSES:
        return "NO_LONGER_HIGH_RISK"
    if row["risk_delta"] > 0:
        return "INCREASED"
    if row["risk_delta"] < 0:
        return "DECREASED"
    return "UNCHANGED"


def compare_scenario(
    baseline: pd.DataFrame,
    shifted_track: pd.DataFrame,
) -> pd.DataFrame:
    result = baseline.copy()
    result["baseline_distance_to_track_km"] = result["distance_to_track_km"]
    result["baseline_nearest_track_wind_kmh"] = result["nearest_track_wind_kmh"]
    result["baseline_wind_score"] = result["wind_score"]
    result["baseline_risk_score"] = result["combined_risk_score"]
    result["baseline_risk_class"] = result["risk_class"]

    result = attach_nearest_track(result, shifted_track, filter_to_corridor=False)
    baseline_terrain = result["terrain_flood_score"].copy()
    result = score_assets_from_terrain(result)
    if not result["terrain_flood_score"].equals(baseline_terrain):
        raise RuntimeError("Scenario changed a fixed terrain-flood score")

    result["scenario_risk_score"] = result["combined_risk_score"]
    result["scenario_risk_class"] = result["risk_class"]
    result["risk_delta"] = (
        result["scenario_risk_score"] - result["baseline_risk_score"]
    ).round(3)
    result["status"] = result.apply(_status_for_row, axis=1)
    return result


def score_custom_track(
    custom_track: pd.DataFrame,
    baseline: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Score baseline assets against a caller-supplied track with the unchanged engine."""

    if missing := {"LAT", "LON", "WIND_KMH"} - set(custom_track.columns):
        raise ValueError(f"Custom track missing columns: {sorted(missing)}")
    if custom_track.empty:
        raise ValueError("Custom track is empty")
    values = custom_track[["LAT", "LON", "WIND_KMH"]].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(values.to_numpy(dtype=float)).all():
        raise ValueError("Custom track contains non-finite LAT/LON/WIND_KMH values")
    if not values["LAT"].between(-90, 90).all() or not values["LON"].between(-180, 180).all():
        raise ValueError("Custom track contains invalid coordinates")
    if baseline is None:
        _, baseline = load_scenario_inputs()
    return compare_scenario(baseline, custom_track)


def _count_high(frame: pd.DataFrame, class_column: str, asset_type: str | None = None) -> int:
    mask = frame[class_column].isin(HIGH_RISK_CLASSES)
    if asset_type is not None:
        mask &= frame["asset_type"].eq(asset_type)
    return int(mask.sum())


def _crossed_high_threshold(frame: pd.DataFrame, asset_type: str) -> pd.Series:
    return (
        frame["asset_type"].eq(asset_type)
        & ~frame["baseline_risk_class"].isin(HIGH_RISK_CLASSES)
        & frame["scenario_risk_class"].isin(HIGH_RISK_CLASSES)
    )


def _newly_critical(frame: pd.DataFrame, asset_type: str) -> pd.Series:
    return (
        frame["asset_type"].eq(asset_type)
        & frame["baseline_risk_class"].ne("CRITICAL")
        & frame["scenario_risk_class"].eq("CRITICAL")
    )


def _asset_summary_records(frame: pd.DataFrame, limit: int = 20) -> list[dict[str, Any]]:
    columns = [
        "name", "asset_type", "osm_element", "osm_id", "baseline_risk_score",
        "scenario_risk_score", "risk_delta", "baseline_risk_class",
        "scenario_risk_class", "distance_to_track_km", "nearest_track_wind_kmh",
        "elevation_m", "water_occurrence_pct", "status",
    ]
    output = (
        frame.sort_values(["risk_delta", "scenario_risk_score"], ascending=[False, False])
        .head(limit)[columns]
    )
    return output.astype(object).where(pd.notna(output), None).to_dict(orient="records")


def build_scenario_summary(
    scenario_assets: pd.DataFrame,
    *,
    north_shift_km: float,
    east_shift_km: float,
    intensity_change_pct: float,
    runtime_seconds: float,
) -> dict[str, Any]:
    baseline_critical = int(scenario_assets["baseline_risk_class"].eq("CRITICAL").sum())
    scenario_critical = int(scenario_assets["scenario_risk_class"].eq("CRITICAL").sum())
    newly_at_risk = scenario_assets[
        scenario_assets["status"].isin(["NEWLY_HIGH_RISK", "NEWLY_CRITICAL"])
    ]
    return {
        "scenario_parameters": {
            "north_shift_km": float(north_shift_km),
            "east_shift_km": float(east_shift_km),
            "intensity_change_pct": float(intensity_change_pct),
        },
        "asset_count": int(len(scenario_assets)),
        "runtime_seconds": round(float(runtime_seconds), 4),
        "baseline_critical_assets": baseline_critical,
        "scenario_critical_assets": scenario_critical,
        "baseline_high_or_critical_assets": _count_high(
            scenario_assets, "baseline_risk_class"
        ),
        "scenario_high_or_critical_assets": _count_high(
            scenario_assets, "scenario_risk_class"
        ),
        "baseline_high_or_critical_hospitals": _count_high(
            scenario_assets, "baseline_risk_class", "hospital"
        ),
        "scenario_high_or_critical_hospitals": _count_high(
            scenario_assets, "scenario_risk_class", "hospital"
        ),
        "baseline_high_or_critical_substations": _count_high(
            scenario_assets, "baseline_risk_class", "substation"
        ),
        "scenario_high_or_critical_substations": _count_high(
            scenario_assets, "scenario_risk_class", "substation"
        ),
        "newly_high_risk_hospitals": int(
            _crossed_high_threshold(scenario_assets, "hospital").sum()
        ),
        "newly_critical_hospitals": int(_newly_critical(scenario_assets, "hospital").sum()),
        "newly_high_risk_substations": int(
            _crossed_high_threshold(scenario_assets, "substation").sum()
        ),
        "newly_critical_substations": int(
            _newly_critical(scenario_assets, "substation").sum()
        ),
        "assets_risk_decreased": int(scenario_assets["risk_delta"].lt(0).sum()),
        "assets_risk_increased": int(scenario_assets["risk_delta"].gt(0).sum()),
        "status_counts": {
            str(key): int(value)
            for key, value in scenario_assets["status"].value_counts().items()
        },
        "top_newly_at_risk": _asset_summary_records(newly_at_risk),
        "warning": (
            "Deterministic prototype what-if screening only; not an official forecast or "
            "physics-based cyclone damage model."
        ),
    }


def dataframe_geojson(frame: pd.DataFrame) -> dict[str, Any]:
    records = frame.astype(object).where(pd.notna(frame), None).to_dict(orient="records")
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
                "properties": {
                    key: value for key, value in row.items() if key not in {"lat", "lon"}
                },
            }
            for row in records
        ],
    }


def run_scenario(
    north_shift_km: float = 0.0,
    east_shift_km: float = 0.0,
    intensity_change_pct: float = 0.0,
    *,
    save_outputs: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    started = time.perf_counter()
    track, baseline = load_scenario_inputs()
    shifted_track = shift_track_geodesically(
        track, north_shift_km, east_shift_km, intensity_change_pct
    )
    scenario_assets = compare_scenario(baseline, shifted_track)
    runtime = time.perf_counter() - started
    summary = build_scenario_summary(
        scenario_assets,
        north_shift_km=north_shift_km,
        east_shift_km=east_shift_km,
        intensity_change_pct=intensity_change_pct,
        runtime_seconds=runtime,
    )
    if save_outputs:
        OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
        scenario_assets.to_csv(OUTPUT_CSV, index=False)
        atomic_json_write(OUTPUT_GEOJSON, dataframe_geojson(scenario_assets))
        atomic_json_write(OUTPUT_SUMMARY, summary)
    return scenario_assets, shifted_track, summary
