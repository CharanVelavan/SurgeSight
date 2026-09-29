"""Independent NWP comparison (WP2.6): the NOAA GFS forecast beside SurgeSight's own track forecast.

A stand-in while Google WeatherNext is unavailable. GFS is real numerical weather prediction, so it is an
independent check on the statistical Kalman track, analysed in Google Earth Engine (NOAA/GFS0P25).

Method: for each lead time, take the GFS 10 m wind field from the run issued at the cutoff, compute
relative vorticity, and follow the vortex from the last observed position at the cutoff (nearest
vorticity maximum within a search radius of the previous centre). GFS at 0.25 degrees smooths the
core, so its centre is approximate (tens of kilometres).
The GFS centre is not an official forecast; IMD remains authoritative.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from services.hazards.rainfall import GFS_ID
from services.risk_model import haversine_km

STEP_DEG = 0.25
WEST, SOUTH, EAST, NORTH = 77.875, 7.875, 87.875, 17.875  # search window (GFS pixel edges)
LEADS = (6, 12, 18, 24, 36, 48)  # the Kalman forecast covers 24 h; later leads are GFS only
SEARCH_KM = 250.0
WIND_RADIUS_KM = 200.0
LABEL = (
    "NOAA GFS forecast (numerical weather prediction) analysed in Google Earth Engine, shown beside the "
    "SurgeSight experimental track. The GFS centre is found from its 10 m wind field at 0.25 degrees, so its centre is "
    "approximate (tens of kilometres). Not an official forecast; IMD remains "
    "authoritative."
)


def _fetch_uv(run, lead: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """u, v (m/s) and the pixel-centre latitude and longitude of every cell (rows run north to south)."""
    import ee

    winds = run.filter(ee.Filter.eq("forecast_hours", lead)).first().select(
        ["u_component_of_wind_10m_above_ground", "v_component_of_wind_10m_above_ground"]
    )
    image = winds.addBands(ee.Image.pixelLonLat().reproject(winds.projection()))
    props = image.sampleRectangle(ee.Geometry.Rectangle([WEST + 0.05, SOUTH + 0.05, EAST - 0.05, NORTH - 0.05]), defaultValue=0).getInfo()["properties"]
    grab = lambda name: np.array(props[name], float)  # noqa: E731
    return (grab("u_component_of_wind_10m_above_ground"), grab("v_component_of_wind_10m_above_ground"),
            grab("latitude"), grab("longitude"))


def vorticity(u: np.ndarray, v: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Relative vorticity (1/s) on the lat/lon grid; ``lat`` is the 2-D latitude of each cell, rows run north to south."""
    dy = STEP_DEG * 111_320.0
    dx = dy * np.cos(np.radians(lat))
    dv_dx = np.gradient(v, axis=1) / dx
    du_dy = np.gradient(u, axis=0) / (-dy)
    zeta = dv_dx - du_dy
    padded = np.pad(zeta, 1, mode="edge")
    return sum(padded[i : i + zeta.shape[0], j : j + zeta.shape[1]] for i in range(3) for j in range(3)) / 9.0


def track_vortex(u: np.ndarray, v: np.ndarray, grid_lat: np.ndarray, grid_lon: np.ndarray, previous: tuple[float, float]) -> dict[str, float] | None:
    """Vorticity maximum nearest the previous centre, and the maximum 10 m wind around it."""
    zeta = vorticity(u, v, grid_lat)
    distance = np.vectorize(haversine_km)(previous[0], previous[1], grid_lat, grid_lon)
    window = distance <= SEARCH_KM
    if not window.any() or zeta[window].max() <= 0:
        return None
    masked = np.where(window, zeta, -np.inf)
    i, j = np.unravel_index(np.argmax(masked), masked.shape)
    centre = (float(grid_lat[i, j]), float(grid_lon[i, j]))
    speed_kmh = np.hypot(u, v) * 3.6
    near = np.vectorize(haversine_km)(centre[0], centre[1], grid_lat, grid_lon) <= WIND_RADIUS_KM
    return {"lat": round(centre[0], 2), "lon": round(centre[1], 2), "max_wind_kmh": round(float(speed_kmh[near].max()), 1),
            "vorticity_1e5_per_s": round(float(zeta[i, j]) * 1e5, 1)}


def nwp_comparison(track: pd.DataFrame, cutoff_utc: str, *, leads: tuple[int, ...] = LEADS) -> dict[str, Any]:
    """GFS vortex centre versus the Kalman forecast (and the observed track, validation only). Needs Earth Engine."""
    import ee

    from services.earth_engine import init_ee
    from services.ensemble import default_sigma_km
    from services.hazards.rainfall import ForecastRunUnavailable
    from services.track_forecaster import MODEL_KALMAN, forecast_track, observations_until

    init_ee()
    cutoff = pd.Timestamp(cutoff_utc)
    stamp = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
    run = ee.ImageCollection(GFS_ID).filter(ee.Filter.eq("creation_time", int(stamp.timestamp() * 1000)))
    if run.size().getInfo() == 0:
        raise ForecastRunUnavailable(f"No GFS run issued at {stamp}")

    last = observations_until(track, cutoff).iloc[-1]
    kalman = {int(p.lead_hours): p for p in forecast_track(track, cutoff, MODEL_KALMAN).points.itertuples()}
    centre = (float(last["LAT"]), float(last["LON"]))
    observed = track.assign(t=pd.to_datetime(track["ISO_TIME"])).set_index("t")
    rows = []
    for lead in leads:
        u, v, grid_lat, grid_lon = _fetch_uv(run, lead)
        found = track_vortex(u, v, grid_lat, grid_lon, centre)
        row: dict[str, Any] = {"lead_hours": lead, "valid_utc": str(cutoff + pd.Timedelta(hours=lead))}
        if found is None:
            row["gfs"] = None
            rows.append(row)
            continue
        centre = (found["lat"], found["lon"])
        row["gfs"] = found
        if lead in kalman:
            k = kalman[lead]
            row["kalman"] = {"lat": round(float(k.lat), 2), "lon": round(float(k.lon), 2)}
            row["gfs_vs_kalman_km"] = round(haversine_km(found["lat"], found["lon"], k.lat, k.lon), 1)
        valid = cutoff + pd.Timedelta(hours=lead)
        if valid in observed.index:
            best = observed.loc[valid]
            row["observed_validation_only"] = {"lat": float(best["LAT"]), "lon": float(best["LON"]), "wind_kmh": round(float(best["WIND_KMH"]), 1)}
            row["gfs_error_km"] = round(haversine_km(found["lat"], found["lon"], best["LAT"], best["LON"]), 1)
            if lead in kalman:
                row["kalman_error_km"] = round(haversine_km(kalman[lead].lat, kalman[lead].lon, best["LAT"], best["LON"]), 1)
        rows.append(row)
    return {
        "cutoff_utc": str(stamp), "source": f"{GFS_ID} (NOAA GFS via Earth Engine)", "rows": rows,
        "ensemble_sigma_km_12h": default_sigma_km(12), "label": LABEL,
    }
