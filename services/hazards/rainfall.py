"""Rainfall pathway (WP2.2): forecast rainfall for prediction, observed IMERG for validation only.

Leakage rule (§4.6): observed rainfall after the cutoff must never be a pre-landfall input.
``rain_inputs`` refuses ``mode="observed"`` unless the caller states it is a hindcast.

Forecast rainfall is the NOAA GFS 0.25 degree run issued at the cutoff time, read from the Earth
Engine archive (NOAA/GFS0P25) by selecting the images whose ``creation_time`` equals the issue time,
so nothing issued later can enter. GFS precipitation is a cumulative total that resets every 6 hours,
so the value at forecast hour 6, 12, 18, ... is that 6-hour bucket. (Open-Meteo's Previous Runs API
was tried first; it has no data before 2024.)
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from services.config import load_region

RAIN_REF_MM = 300.0
IMD_HEAVY_MM, IMD_VERY_HEAVY_MM, IMD_EXTREME_MM = 64.5, 115.6, 204.5
IMERG_ID = "NASA/GPM_L3/IMERG_V07"
IMERG_SCALE_M = 11132
GFS_ID = "NOAA/GFS0P25"
GFS_SCALE_M = 27830
BUCKET_HOURS = 6
MAX_FORECAST_HOURS = 120
FORECAST_NOTE = (
    "NOAA GFS 0.25 degree forecast run issued at the cutoff time (Earth Engine archive); "
    "6-hour accumulation buckets. Rainfall is not shifted when a what-if moves the track."
)


class FutureRainfallAccessError(RuntimeError):
    """Raised when observed rainfall would be used as a pre-landfall input."""


def imd_category(mm_24h: float) -> str:
    if mm_24h >= IMD_EXTREME_MM:
        return "extremely heavy"
    if mm_24h >= IMD_VERY_HEAVY_MM:
        return "very heavy"
    if mm_24h >= IMD_HEAVY_MM:
        return "heavy"
    return "below heavy"


def rain_score(accum_mm: np.ndarray | float) -> np.ndarray:
    return np.clip(np.asarray(accum_mm, float) / RAIN_REF_MM, 0.0, 1.0)


def rain_flood_score(accum_mm: np.ndarray | float, terrain_flood_score: np.ndarray | float) -> np.ndarray:
    """Rain that falls on flood-prone terrain matters more: score x (0.5 + 0.5 x terrain flood score)."""
    return rain_score(accum_mm) * (0.5 + 0.5 * np.asarray(terrain_flood_score, float))


# ---------------------------------------------------------------- observed (validation only)

def observed_rainfall(start_utc: str, end_utc: str, assets: pd.DataFrame) -> pd.DataFrame:
    """IMERG V07 accumulation (mm) and peak 24 h block at each asset. Needs Earth Engine.

    24 h blocks start at ``start_utc`` (not IMD 03 UTC day boundaries).
    """
    import ee

    from services.earth_engine import init_ee, sample_points

    init_ee()
    start, end = pd.Timestamp(start_utc), pd.Timestamp(end_utc)
    collection = ee.ImageCollection(IMERG_ID).select("precipitation")

    def window_sum(a: pd.Timestamp, b: pd.Timestamp) -> "ee.Image":
        # half-hourly rates in mm/h -> mm
        return collection.filterDate(a.isoformat(), b.isoformat()).sum().multiply(0.5)

    blocks = []
    cursor = start
    while cursor + pd.Timedelta(hours=24) <= end:
        blocks.append(window_sum(cursor, cursor + pd.Timedelta(hours=24)))
        cursor += pd.Timedelta(hours=24)
    accum = window_sum(start, end).rename("accum_mm")
    image = accum
    if blocks:
        image = accum.addBands(ee.ImageCollection.fromImages(blocks).max().rename("peak_24h_mm"))
    samples = sample_points(image, list(zip(assets["lat"], assets["lon"])), IMERG_SCALE_M)
    frame = pd.DataFrame(samples)
    out = assets[["osm_element", "osm_id"]].reset_index(drop=True).join(frame)
    if "peak_24h_mm" not in out:
        out["peak_24h_mm"] = out["accum_mm"]
    return out.round(2)


# ---------------------------------------------------------------- forecast (prediction input)

class ForecastRunUnavailable(RuntimeError):
    """Raised when no GFS run exists for the requested issue time."""


def forecast_rainfall(
    init_utc: str, hours: int, assets: pd.DataFrame, *, cutoff_utc: str | None = None
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Forecast accumulation (mm) and peak 24 h block per asset for (init, init + hours]. Needs Earth Engine.

    ``cutoff_utc`` (default: the issue time) is the information cutoff; a run issued after it is refused.
    """
    import ee

    from services.earth_engine import init_ee, sample_points

    if hours % BUCKET_HOURS or not BUCKET_HOURS <= hours <= MAX_FORECAST_HOURS:
        raise ValueError(f"hours must be a multiple of {BUCKET_HOURS} up to {MAX_FORECAST_HOURS}")
    init = pd.Timestamp(init_utc)
    init = init.tz_localize("UTC") if init.tzinfo is None else init.tz_convert("UTC")
    cutoff = pd.Timestamp(cutoff_utc) if cutoff_utc else init
    cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
    if init > cutoff:
        raise FutureRainfallAccessError(f"GFS run issued {init} is after the information cutoff {cutoff}")

    init_ee()
    run = ee.ImageCollection(GFS_ID).filter(ee.Filter.eq("creation_time", int(init.timestamp() * 1000)))
    if run.size().getInfo() == 0:
        raise ForecastRunUnavailable(f"No GFS run issued at {init} in {GFS_ID}")
    buckets = [
        run.filter(ee.Filter.eq("forecast_hours", h)).select("total_precipitation_surface").first()
        for h in range(BUCKET_HOURS, hours + 1, BUCKET_HOURS)
    ]

    def total(images: list) -> "ee.Image":
        return ee.ImageCollection.fromImages(images).sum()

    per_day = 24 // BUCKET_HOURS
    blocks = [total(buckets[i : i + per_day]) for i in range(0, len(buckets) - per_day + 1, per_day)]
    image = total(buckets).rename("accum_mm")
    image = image.addBands((ee.ImageCollection.fromImages(blocks).max() if blocks else total(buckets)).rename("peak_24h_mm"))
    samples = sample_points(image, list(zip(assets["lat"], assets["lon"])), GFS_SCALE_M)
    out = assets[["osm_element", "osm_id"]].reset_index(drop=True).join(pd.DataFrame(samples))
    meta = {
        "source": f"{GFS_ID} (NOAA GFS via Earth Engine)",
        "init_utc": init.isoformat(), "information_cutoff_utc": cutoff.isoformat(), "hours": hours,
        "bucket_hours": BUCKET_HOURS, "note": FORECAST_NOTE,
    }
    return out.round(2), meta


# ---------------------------------------------------------------- cached per-asset table

def load_rainfall_assets(region_id: str | None = None) -> pd.DataFrame:
    path = load_region(region_id).path("rainfall_assets")
    if not path.exists():
        raise FileNotFoundError(f"{path} missing; run scripts/build_rainfall.py")
    return pd.read_csv(path)


def rain_inputs(mode: str, *, hindcast: bool = False, region_id: str | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Per-asset rainfall for the hazard model as columns ``accum_mm`` and ``peak_24h_mm``.

    ``mode="forecast"`` is the only pre-landfall input. ``mode="observed"`` (IMERG) is allowed only
    with ``hindcast=True`` and is labelled validation-only.
    """
    table = load_rainfall_assets(region_id)
    if mode == "forecast":
        cols = {"fc_accum_mm": "accum_mm", "fc_peak_24h_mm": "peak_24h_mm"}
        meta = {"mode": "forecast", "validation_only": False, "note": FORECAST_NOTE}
    elif mode == "observed":
        if not hindcast:
            raise FutureRainfallAccessError(
                "Observed IMERG rainfall is validation/hindcast only and cannot be a pre-landfall input"
            )
        cols = {"obs_accum_mm": "accum_mm", "obs_peak_24h_mm": "peak_24h_mm"}
        meta = {"mode": "observed", "validation_only": True, "note": "Observed IMERG after the cutoff: hindcast only."}
    else:
        raise ValueError("mode must be 'forecast' or 'observed'")
    out = table[["osm_element", "osm_id", *cols]].rename(columns=cols)
    return out, meta
