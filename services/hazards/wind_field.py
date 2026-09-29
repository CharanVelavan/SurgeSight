"""Parametric cyclone wind field: Holland (1980) profile with a translation asymmetry (WP2.4).

    V(r) = Vmax * [ (Rmax/r)^B * exp(1 - (Rmax/r)^B) ]^0.5,  B = 1.5
    asymmetry = +0.5 * Vt * sin(alpha)  (alpha = clockwise angle from the motion direction to the point;
                                         right of track in the Northern Hemisphere is stronger)
    Rmax from Willoughby et al. (2006): 46.4 * exp(-0.0155 * Vmax[m/s] + 0.0169 * |lat|) km

Screening use only: no gradient-to-surface conversion, gust factor or land friction.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from services.hazards.coast import bearing_matrix_deg, densify_track, haversine_matrix_km

HOLLAND_B = 1.5
ASYMMETRY_FACTOR = 0.5
MIN_R_KM = 1.0


def rmw_km(vmax_ms: np.ndarray | float, lat: np.ndarray | float) -> np.ndarray:
    return 46.4 * np.exp(-0.0155 * np.asarray(vmax_ms, float) + 0.0169 * np.abs(np.asarray(lat, float)))


def holland_kmh(r_km: np.ndarray, vmax_kmh: np.ndarray, rmax_km: np.ndarray, b: float = HOLLAND_B) -> np.ndarray:
    x = (np.asarray(rmax_km) / np.maximum(r_km, MIN_R_KM)) ** b
    return np.asarray(vmax_kmh) * np.sqrt(x * np.exp(1.0 - x))


def max_wind_kmh(track: pd.DataFrame, asset_lat: np.ndarray, asset_lon: np.ndarray, step_km: float = 5.0) -> np.ndarray:
    """Highest modelled wind (km/h) each asset sees anywhere along the track."""
    dense = densify_track(track, step_km)
    vmax = dense["WIND_KMH"].to_numpy(float)
    rmax = rmw_km(vmax / 3.6, dense["LAT"].to_numpy(float))
    lat_c, lon_c = dense["LAT"].to_numpy(float), dense["LON"].to_numpy(float)
    r = haversine_matrix_km(lat_c, lon_c, np.asarray(asset_lat, float), np.asarray(asset_lon, float))
    wind = holland_kmh(r, vmax[:, None], rmax[:, None])
    translation = dense["TRANSLATION_KMH"].to_numpy(float)
    if np.isfinite(translation).any():
        heading = dense["HEADING_DEG"].to_numpy(float)
        bearing = bearing_matrix_deg(lat_c, lon_c, np.asarray(asset_lat, float), np.asarray(asset_lon, float))
        alpha = np.radians(bearing - heading[:, None])
        asym = ASYMMETRY_FACTOR * np.nan_to_num(translation, nan=0.0)[:, None] * np.sin(alpha)
        wind = np.maximum(wind + asym, 0.0)
    return wind.max(axis=0)
