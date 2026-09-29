"""Land/coast geometry shared by the surge and wind models (cached files only, no network)."""

from __future__ import annotations

from functools import lru_cache
import json
import math

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape

from services.config import load_region

EARTH_RADIUS_KM = 6371.0088


def haversine_matrix_km(lat1: np.ndarray, lon1: np.ndarray, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    """Great-circle distances (km) between every (lat1, lon1) and every (lat2, lon2): shape (n1, n2)."""
    p1, p2 = np.radians(lat1)[:, None], np.radians(lat2)[None, :]
    dphi = p2 - p1
    dlmb = np.radians(lon2)[None, :] - np.radians(lon1)[:, None]
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def bearing_matrix_deg(lat1: np.ndarray, lon1: np.ndarray, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    """Initial bearing (degrees clockwise from north) from each point 1 to each point 2."""
    p1, p2 = np.radians(lat1)[:, None], np.radians(lat2)[None, :]
    dlmb = np.radians(lon2)[None, :] - np.radians(lon1)[:, None]
    y = np.sin(dlmb) * np.cos(p2)
    x = np.cos(p1) * np.sin(p2) - np.sin(p1) * np.cos(p2) * np.cos(dlmb)
    return (np.degrees(np.arctan2(y, x)) + 360.0) % 360.0


@lru_cache(maxsize=None)
def land_geometry(region_id: str | None = None):
    region = load_region(region_id)
    return shape(json.loads(region.path("land_polygon").read_text(encoding="utf-8")))


def is_land(lon: np.ndarray, lat: np.ndarray, region_id: str | None = None) -> np.ndarray:
    return shapely.contains_xy(land_geometry(region_id), np.asarray(lon, float), np.asarray(lat, float))


@lru_cache(maxsize=None)
def coast_assets(region_id: str | None = None) -> pd.DataFrame:
    return pd.read_csv(load_region(region_id).path("coast_assets"))


@lru_cache(maxsize=None)
def coast_shelf(region_id: str | None = None) -> pd.DataFrame:
    return pd.read_csv(load_region(region_id).path("coast_shelf")).dropna(subset=["mean_depth_50km_m"])


def densify_track(track: pd.DataFrame, step_km: float = 5.0) -> pd.DataFrame:
    """Linearly interpolate a track to ~step_km spacing; adds translation speed and heading.

    Columns out: LAT, LON, WIND_KMH, PRESSURE_HPA (NaN if absent), HEADING_DEG, TRANSLATION_KMH
    (NaN when timestamps are unavailable), HOURS and ISO_TIME (when timestamps are available).
    """
    lat = track["LAT"].to_numpy(float)
    lon = track["LON"].to_numpy(float)
    wind = track["WIND_KMH"].to_numpy(float)
    pressure = (
        pd.to_numeric(track["PRESSURE_HPA"], errors="coerce").to_numpy(float)
        if "PRESSURE_HPA" in track else np.full(len(track), np.nan)
    )
    times = pd.to_datetime(track["ISO_TIME"], errors="coerce") if "ISO_TIME" in track else None
    has_times = times is not None and bool(times.notna().all())
    hours = (times - times.iloc[0]).dt.total_seconds().to_numpy() / 3600.0 if has_times else None
    rows = []
    for i in range(len(lat) - 1):
        seg_km = float(haversine_matrix_km(lat[i : i + 1], lon[i : i + 1], lat[i + 1 : i + 2], lon[i + 1 : i + 2])[0, 0])
        heading = float(bearing_matrix_deg(lat[i : i + 1], lon[i : i + 1], lat[i + 1 : i + 2], lon[i + 1 : i + 2])[0, 0])
        dt_h = float(hours[i + 1] - hours[i]) if hours is not None else None
        speed = seg_km / dt_h if dt_h and dt_h > 0 else math.nan
        steps = max(1, int(math.ceil(seg_km / step_km)))
        for k in range(steps):
            f = k / steps
            rows.append((
                lat[i] + f * (lat[i + 1] - lat[i]), lon[i] + f * (lon[i + 1] - lon[i]),
                wind[i] + f * (wind[i + 1] - wind[i]), pressure[i] + f * (pressure[i + 1] - pressure[i]),
                heading, speed, (hours[i] + f * dt_h) if dt_h is not None else math.nan,
            ))
    rows.append((
        lat[-1], lon[-1], wind[-1], pressure[-1],
        rows[-1][4] if rows else math.nan, rows[-1][5] if rows else math.nan,
        float(hours[-1]) if hours is not None else math.nan,
    ))
    out = pd.DataFrame(rows, columns=["LAT", "LON", "WIND_KMH", "PRESSURE_HPA", "HEADING_DEG", "TRANSLATION_KMH", "HOURS"])
    if has_times:
        out["ISO_TIME"] = times.iloc[0] + pd.to_timedelta(out["HOURS"], unit="h")
    return out


def find_landfall(track: pd.DataFrame, region_id: str | None = None, step_km: float = 2.0) -> dict | None:
    """First point where the track moves from sea onto land, or None (stays at sea / starts on land)."""
    dense = densify_track(track, step_km)
    land = is_land(dense["LON"].to_numpy(), dense["LAT"].to_numpy(), region_id)
    for i in range(1, len(dense)):
        if land[i] and not land[i - 1]:
            row = dense.iloc[i]
            stamp = row["ISO_TIME"] if "ISO_TIME" in dense.columns else None
            return {
                "lat": float(row["LAT"]), "lon": float(row["LON"]),
                "wind_kmh": float(row["WIND_KMH"]),
                "pressure_hpa": None if pd.isna(row["PRESSURE_HPA"]) else float(row["PRESSURE_HPA"]),
                "heading_deg": float(row["HEADING_DEG"]),
                "time": stamp.isoformat() if stamp is not None and pd.notna(stamp) else None,
            }
    return None
