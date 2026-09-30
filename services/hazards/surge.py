"""Screening storm-surge index (WP2.3). NOT a hydrodynamic model (not SLOSH/ADCIRC).

    peak_surge_m   = inverse_barometer + wind_setup
    inverse_barometer = 0.01 * (1010 - Pc_hPa)
    wind_setup     = K_WS * (V_landfall[m/s] / 50)^2 * shelf_factor
    shelf_factor   = 1.5 for shallow (<= 20 m mean depth within 50 km offshore) down to 0.7 for deep (>= 200 m)
    alongshore     = 1.0 right of track / 0.4 left, times exp(-d / (3 * RMW)), d = distance from landfall
    asset surge_score = clip((surge_m - elevation_m) / surge_m, 0, 1) * exp(-coast_dist_km / 5)
                        for land assets within MAX_INLAND_KM of the coast, else 0

All constants are prototype values, listed in SURGE_CONSTANTS and echoed in every output.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from services.hazards.coast import coast_assets, coast_shelf, find_landfall, haversine_matrix_km
from services.hazards.wind_field import rmw_km

SURGE_CONSTANTS = {
    "K_WS": 2.0,
    "IB_REFERENCE_HPA": 1010.0,
    "SHELF_SHALLOW_M": 20.0,
    "SHELF_DEEP_M": 200.0,
    "SHELF_FACTOR_MAX": 1.5,
    "SHELF_FACTOR_MIN": 0.7,
    "RIGHT_OF_TRACK_MULTIPLIER": 1.0,
    "LEFT_OF_TRACK_MULTIPLIER": 0.4,
    "ALONGSHORE_DECAY_RMW_MULTIPLE": 3.0,
    "MAX_INLAND_KM": 10.0,
    "INLAND_DECAY_KM": 5.0,
    "REFERENCE_WIND_MS": 50.0,
}
LABEL = "Screening surge index, not a hydrodynamic storm-surge model."
DEFAULT_PRESSURE_HPA = 1000.0


def shelf_factor(mean_depth_m: float) -> float:
    c = SURGE_CONSTANTS
    span = math.log10(c["SHELF_DEEP_M"]) - math.log10(c["SHELF_SHALLOW_M"])
    t = (math.log10(max(mean_depth_m, 1.0)) - math.log10(c["SHELF_SHALLOW_M"])) / span
    t = min(max(t, 0.0), 1.0)
    return c["SHELF_FACTOR_MAX"] - (c["SHELF_FACTOR_MAX"] - c["SHELF_FACTOR_MIN"]) * t


def peak_surge(track: pd.DataFrame, region_id: str | None = None) -> dict:
    """Peak surge at the landfall point, or ``{"landfall": None}`` if the track never crosses the coast."""
    landfall = find_landfall(track, region_id)
    if landfall is None:
        return {
            "landfall": None, "peak_surge_m": 0.0,
            "warnings": ["Track does not make landfall; no surge modelled."],
            "constants": SURGE_CONSTANTS, "label": LABEL,
        }
    c = SURGE_CONSTANTS
    warnings = []
    pressure = landfall["pressure_hpa"]
    if pressure is None or not math.isfinite(pressure):
        pressure = DEFAULT_PRESSURE_HPA
        warnings.append(
            f"No pressure on the track; assumed {DEFAULT_PRESSURE_HPA:.0f} hPa "
            f"(inverse barometer {0.01 * (c['IB_REFERENCE_HPA'] - pressure):.2f} m)."
        )
    shelf = coast_shelf(region_id)
    d = haversine_matrix_km(
        np.array([landfall["lat"]]), np.array([landfall["lon"]]),
        shelf["lat"].to_numpy(), shelf["lon"].to_numpy(),
    )[0]
    nearest = int(np.argmin(d))
    depth = float(shelf.iloc[nearest]["mean_depth_50km_m"])
    factor = shelf_factor(depth)
    v_ms = landfall["wind_kmh"] / 3.6
    ib = max(0.01 * (c["IB_REFERENCE_HPA"] - pressure), 0.0)
    setup = c["K_WS"] * (v_ms / c["REFERENCE_WIND_MS"]) ** 2 * factor
    return {
        "landfall": landfall,
        "inverse_barometer_m": round(ib, 3),
        "wind_setup_m": round(setup, 3),
        "peak_surge_m": round(ib + setup, 3),
        "shelf_mean_depth_m": round(depth, 1),
        "shelf_factor": round(factor, 3),
        "rmw_km": round(float(rmw_km(v_ms, landfall["lat"])), 1),
        "warnings": warnings,
        "constants": SURGE_CONSTANTS,
        "label": LABEL,
    }


def surge_scores(
    track: pd.DataFrame, assets: pd.DataFrame, region_id: str | None = None
) -> tuple[pd.DataFrame, dict]:
    """Per-asset surge at the asset's coast point and the surge score, plus the landfall summary."""
    info = peak_surge(track, region_id)
    coast = coast_assets(region_id)
    merged = assets[["osm_element", "osm_id", "elevation_m"]].merge(
        coast, on=["osm_element", "osm_id"], how="left"
    )
    out = pd.DataFrame({"osm_element": merged["osm_element"], "osm_id": merged["osm_id"]})
    points = surge_at_points(info, merged)
    out["surge_m"], out["surge_score"], out["coast_side"] = points["surge_m"], points["surge_score"], points["coast_side"]
    return out, info


def surge_at_points(info: dict, merged: pd.DataFrame) -> pd.DataFrame:
    """Surge and surge score for any places with ``coast_lat, coast_lon, coast_dist_km, on_land, elevation_m``.

    ``info`` is a ``peak_surge`` result. Used for assets and for road sections alike.
    """
    out = pd.DataFrame(index=merged.index)
    out["surge_m"] = 0.0
    out["surge_score"] = 0.0
    out["coast_side"] = "n/a"
    if info["landfall"] is None or info["peak_surge_m"] <= 0:
        return out
    c = SURGE_CONSTANTS
    lf = info["landfall"]
    lat0, lon0 = lf["lat"], lf["lon"]
    # side of track: planar cross product of the heading and the landfall -> coast-point vector
    heading = math.radians(lf["heading_deg"])
    h_e, h_n = math.sin(heading), math.cos(heading)
    cos_lat = math.cos(math.radians(lat0))
    v_e = (merged["coast_lon"].to_numpy(float) - lon0) * cos_lat
    v_n = merged["coast_lat"].to_numpy(float) - lat0
    right = (h_e * v_n - h_n * v_e) < 0  # clockwise of the heading = right of track
    along_km = haversine_matrix_km(
        np.array([lat0]), np.array([lon0]),
        merged["coast_lat"].to_numpy(float), merged["coast_lon"].to_numpy(float),
    )[0]
    decay = np.exp(-along_km / (c["ALONGSHORE_DECAY_RMW_MULTIPLE"] * info["rmw_km"]))
    side = np.where(right, c["RIGHT_OF_TRACK_MULTIPLIER"], c["LEFT_OF_TRACK_MULTIPLIER"])
    surge_m = info["peak_surge_m"] * side * decay
    elevation = merged["elevation_m"].to_numpy(float)
    coast_km = merged["coast_dist_km"].to_numpy(float)
    eligible = merged["on_land"].fillna(False).to_numpy(bool) & (coast_km <= c["MAX_INLAND_KM"])
    with np.errstate(divide="ignore", invalid="ignore"):
        depth_ratio = np.clip(np.where(surge_m > 0, (surge_m - elevation) / surge_m, 0.0), 0.0, 1.0)
    score = np.where(eligible, depth_ratio * np.exp(-coast_km / c["INLAND_DECAY_KM"]), 0.0)
    out["surge_m"] = np.round(np.where(eligible, surge_m, 0.0), 3)
    out["surge_score"] = np.round(np.nan_to_num(score), 4)
    out["coast_side"] = np.where(eligible, np.where(right, "right_of_track", "left_of_track"), "n/a")
    return out
