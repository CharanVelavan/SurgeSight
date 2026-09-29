"""Shared deterministic SurgeSight infrastructure-risk mathematics.

Operation order and rounding intentionally match the original Michaung scoring
pipeline. This module performs no AI or external API calls.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


REFERENCE_WIND_KMH = 120.0
SCREENING_CORRIDOR_KM = 140.0
WEIGHTS = {
    "terrain_elevation": 0.70,
    "terrain_water_occurrence": 0.30,
    "combined_wind": 0.65,
    "combined_terrain_flood": 0.35,
}
SCORE_COLUMNS = (
    "distance_to_track_km",
    "nearest_track_wind_kmh",
    "elevation_m",
    "water_occurrence_pct",
    "wind_score",
    "terrain_flood_score",
    "combined_risk_score",
)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def classify_risk(score: float) -> str:
    if score < 0.25:
        return "LOW"
    if score < 0.50:
        return "MODERATE"
    if score < 0.75:
        return "HIGH"
    return "CRITICAL"


def attach_nearest_track(
    assets: pd.DataFrame,
    track: pd.DataFrame,
    *,
    wind_multiplier: float = 1.0,
    filter_to_corridor: bool = True,
) -> pd.DataFrame:
    """Attach nearest observed-track distance and adjusted wind to each asset."""

    required_assets = {"lat", "lon"}
    required_track = {"LAT", "LON", "WIND_KMH"}
    if missing := required_assets - set(assets.columns):
        raise ValueError(f"Assets missing columns: {sorted(missing)}")
    if missing := required_track - set(track.columns):
        raise ValueError(f"Track missing columns: {sorted(missing)}")
    if wind_multiplier < 0:
        raise ValueError("Wind multiplier cannot be negative")

    asset_lat = np.radians(assets["lat"].to_numpy(dtype=float))[:, None]
    asset_lon = np.radians(assets["lon"].to_numpy(dtype=float))[:, None]
    track_lat = np.radians(track["LAT"].to_numpy(dtype=float))[None, :]
    track_lon = np.radians(track["LON"].to_numpy(dtype=float))[None, :]
    delta_lat = track_lat - asset_lat
    delta_lon = track_lon - asset_lon
    haversine_a = (
        np.sin(delta_lat / 2.0) ** 2
        + np.cos(asset_lat) * np.cos(track_lat) * np.sin(delta_lon / 2.0) ** 2
    )
    distances = 6371.0088 * 2.0 * np.arctan2(
        np.sqrt(haversine_a), np.sqrt(np.maximum(0.0, 1.0 - haversine_a))
    )
    nearest_indices = np.argmin(distances, axis=1)
    nearest_distances = distances[np.arange(len(assets)), nearest_indices]
    track_winds = track["WIND_KMH"].to_numpy(dtype=float) * wind_multiplier
    nearest_winds = track_winds[nearest_indices]

    result = assets.copy()
    result["distance_to_track_km"] = np.round(nearest_distances, 3)
    result["nearest_track_wind_kmh"] = np.round(nearest_winds, 3)
    if filter_to_corridor:
        result = result[result["distance_to_track_km"] <= SCREENING_CORRIDOR_KM]
    return result.reset_index(drop=True)


def score_assets_from_terrain(assets: pd.DataFrame) -> pd.DataFrame:
    """Calculate scores from attached distance/wind and fixed terrain values."""

    required = {
        "distance_to_track_km",
        "nearest_track_wind_kmh",
        "elevation_m",
        "water_occurrence_pct",
    }
    if missing := required - set(assets.columns):
        raise ValueError(f"Risk input missing columns: {sorted(missing)}")
    result = assets.copy()
    intensity = (result["nearest_track_wind_kmh"] / REFERENCE_WIND_KMH).clip(0, 1)
    proximity = (
        1.0 - 0.5 * result["distance_to_track_km"] / SCREENING_CORRIDOR_KM
    ).clip(0.5, 1.0)
    result["wind_score"] = (intensity * proximity).clip(0, 1)

    elevation_score = ((30.0 - result["elevation_m"]) / 25.0).clip(0, 1)
    water_score = (result["water_occurrence_pct"] / 100.0).clip(0, 1)
    result["terrain_flood_score"] = (
        WEIGHTS["terrain_elevation"] * elevation_score
        + WEIGHTS["terrain_water_occurrence"] * water_score
    ).clip(0, 1)
    result["combined_risk_score"] = (
        WEIGHTS["combined_wind"] * result["wind_score"]
        + WEIGHTS["combined_terrain_flood"] * result["terrain_flood_score"]
    ).clip(0, 1)
    result["risk_class"] = result["combined_risk_score"].map(classify_risk)
    for column in SCORE_COLUMNS:
        result[column] = result[column].round(3)
    return result
