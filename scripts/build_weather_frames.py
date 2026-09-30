"""Build weather frame atlases (wind + rain) for the animated map from Earth Engine.

GFS analysis winds are stitched hourly from f000-f005 of each 6-hourly cycle. Forecast cycles (every 12 h) are
kept separately, f000-f072 at 3-hourly steps, so a cutoff can only see the latest cycle issued before it.
Observed rain is IMERG V07 aggregated to hourly. Raw arrays are cached in data/raw/weather/ (git-ignored);
atlases and manifest.json go to data/processed/weather/.  Usage: python scripts/build_weather_frames.py [--refresh]
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys

import ee
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services import weather_frames as wf
from services.earth_engine import init_ee

RAW = PROJECT_ROOT / "data" / "raw" / "weather"
GFS, IMERG = "NOAA/GFS0P25", "NASA/GPM_L3/IMERG_V07"
U, V, P = "u_component_of_wind_10m_above_ground", "v_component_of_wind_10m_above_ground", "total_precipitation_surface"
GRID = {"dimensions": {"width": wf.WIDTH, "height": wf.HEIGHT}, "crsCode": "EPSG:4326",
        "affineTransform": {"scaleX": 0.25, "shearX": 0, "translateX": wf.BOUNDS["west"] - 0.125,
                            "shearY": 0, "scaleY": -0.25, "translateY": wf.BOUNDS["north"] + 0.125}}


def cached(path: Path) -> np.ndarray | None:
    """Raw array from the cache, or None when missing or built for a different grid."""
    if not path.exists():
        return None
    arr = np.load(path)
    return arr if arr.shape[-2:] == (wf.HEIGHT, wf.WIDTH) else None


def ms(t: pd.Timestamp) -> int:
    return int(pd.Timestamp(t).tz_localize("UTC").timestamp() * 1000)


def gfs(cycle: pd.Timestamp, hour: int) -> ee.Image:
    return (ee.ImageCollection(GFS).filter(ee.Filter.eq("creation_time", ms(cycle)))
            .filter(ee.Filter.eq("forecast_hours", hour)).first())


def fetch(image: ee.Image, names: list[str]) -> np.ndarray:
    """(n_bands, H, W) float array for a multi-band image."""
    raw = ee.data.computePixels({"expression": image, "fileFormat": "NUMPY_NDARRAY", "grid": GRID})
    return np.stack([np.asarray(raw[n], dtype=np.float64) for n in names])


def analysis_sources() -> list[tuple[pd.Timestamp, pd.Timestamp, int]]:
    """(valid time, cycle, forecast hour) for every hour of the window, from the 6-hourly cycle at or before it."""
    hours = pd.date_range(wf.WINDOW_START, wf.WINDOW_END, freq="1h")
    return [(t, t.floor("6h"), int((t - t.floor("6h")).total_seconds() // 3600)) for t in hours]


def wind_analysis() -> np.ndarray:
    path = RAW / "analysis_wind.npy"
    if (arr := cached(path)) is not None:
        return arr

    def one(src):
        _, cycle, hour = src
        return fetch(gfs(cycle, hour).select([U, V]), [U, V])

    with ThreadPoolExecutor(8) as pool:
        out = np.stack(list(pool.map(one, analysis_sources())))  # (n, 2, H, W)
    np.save(path, out)
    return out


def rain_rate_3h(cycle: pd.Timestamp, step: int) -> np.ndarray:
    """Mean rate (mm/h) over the 3 h ending at ``step``. GFS accumulates in 6 h buckets that restart at f000, f006, ..."""
    if step == 0:
        return np.zeros((wf.HEIGHT, wf.WIDTH))
    if step % 6 == 3:
        return fetch(gfs(cycle, step).select([P]), [P])[0] / 3
    return (fetch(gfs(cycle, step).select([P]), [P])[0] - fetch(gfs(cycle, step - 3).select([P]), [P])[0]) / 3


def forecast_cycle(cycle: pd.Timestamp) -> np.ndarray:
    path = RAW / f"forecast_{wf.cycle_id(cycle)}.npy"
    if (arr := cached(path)) is not None:
        return arr
    steps = wf.forecast_steps()
    with ThreadPoolExecutor(6) as pool:
        uv = list(pool.map(lambda s: fetch(gfs(cycle, s).select([U, V]), [U, V]), steps))
        rain = list(pool.map(lambda s: np.maximum(rain_rate_3h(cycle, s), 0), steps))
    out = np.stack([np.concatenate([uv[i], rain[i][None]]) for i in range(len(steps))])  # (n, 3, H, W)
    np.save(path, out)
    return out


def imerg_hourly() -> np.ndarray:
    path = RAW / "imerg_rain.npy"
    if (arr := cached(path)) is not None:
        return arr
    proj = ee.Projection("EPSG:4326", [0.25, 0, wf.BOUNDS["west"] - 0.125, 0, -0.25, wf.BOUNDS["north"] + 0.125])
    hours = pd.date_range(wf.WINDOW_START, wf.WINDOW_END, freq="1h")

    def one(t):
        col = (ee.ImageCollection(IMERG).filterDate(t.strftime("%Y-%m-%dT%H:%M:%S"), (t + pd.Timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S"))
               .select("precipitation"))
        img = col.mean().setDefaultProjection(col.first().projection())
        img = img.reduceResolution(ee.Reducer.mean(), maxPixels=256).reproject(proj)
        return np.nan_to_num(fetch(img, ["precipitation"])[0])

    with ThreadPoolExecutor(8) as pool:
        out = np.stack(list(pool.map(one, hours)))
    np.save(path, out)
    return out


def rgb(r: np.ndarray, g: np.ndarray | None = None, b: np.ndarray | None = None) -> np.ndarray:
    zero = np.zeros_like(r, dtype=np.uint8)
    return np.stack([r, g if g is not None else zero, b if b is not None else zero], axis=-1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="ignore the raw cache and refetch")
    args = parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    wf.WEATHER_DIR.mkdir(parents=True, exist_ok=True)
    if args.refresh:
        for f in RAW.glob("*.npy"):
            f.unlink()
    init_ee()
    hours = [wf.iso(t) for t in pd.date_range(wf.WINDOW_START, wf.WINDOW_END, freq="1h")]
    cols, rows = wf.atlas_shape(len(hours))

    print("analysis wind ...", flush=True)
    aw = wind_analysis()
    wf.pack_atlas(rgb(wf.encode_wind(aw[:, 0]), wf.encode_wind(aw[:, 1]))).save(wf.WEATHER_DIR / "analysis_wind.png", optimize=True)
    print("observed rain (IMERG) ...", flush=True)
    ir = imerg_hourly()
    wf.pack_atlas(rgb(wf.encode_rain(ir))).save(wf.WEATHER_DIR / "observed_rain.png", optimize=True)

    manifest = {
        "bounds": wf.BOUNDS, "tile": {"width": wf.WIDTH, "height": wf.HEIGHT},
        "encoding": {"wind": {"channels": "RG", "min": -wf.WIND_MAX, "max": wf.WIND_MAX, "unit": "m/s"},
                     "rain": {"channels": "R (observed) / B (forecast)", "scale": "log1p", "max": wf.RAIN_MAX, "unit": "mm/h"}},
        "window": {"start": wf.iso(wf.WINDOW_START), "end": wf.iso(wf.WINDOW_END)},
        "analysis_wind": {"file": "analysis_wind.png", "cols": cols, "rows": rows, "frames": hours,
                          "source": "NOAA GFS 0.25 analysis (f000-f005 of each 6-hourly cycle), 10 m wind"},
        "observed_rain": {"file": "observed_rain.png", "cols": cols, "rows": rows, "frames": hours,
                          "source": "NASA GPM IMERG V07, hourly mean of half-hourly precipitation"},
        "forecast": [],
    }
    for cycle in wf.cycle_times():
        print("forecast cycle", cycle, flush=True)
        arr = forecast_cycle(cycle)
        steps = wf.forecast_steps()
        name = f"forecast_{wf.cycle_id(cycle)}.png"
        wf.pack_atlas(rgb(wf.encode_wind(arr[:, 0]), wf.encode_wind(arr[:, 1]), wf.encode_rain(arr[:, 2]))).save(wf.WEATHER_DIR / name, optimize=True)
        c, r = wf.atlas_shape(len(steps))
        manifest["forecast"].append({"cycle": wf.iso(cycle), "file": name, "cols": c, "rows": r, "step_hours": wf.FORECAST_STEP_H,
                                     "frames": [wf.iso(cycle + pd.Timedelta(hours=s)) for s in steps],
                                     "source": "NOAA GFS 0.25 forecast, 10 m wind and 3 h mean precipitation rate"})
    (wf.WEATHER_DIR / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    size = sum(f.stat().st_size for f in wf.WEATHER_DIR.iterdir()) / 1e6
    print(f"wrote {len(manifest['forecast'])} forecast atlases + 2 observed atlases, {size:.1f} MB")


if __name__ == "__main__":
    main()
