"""Build the live weather atlases (W5) from the newest complete NOAA GFS cycle in Earth Engine.

Same grid and encoding as the storm replays, so the map code is shared: one analysis frame (f000), one
forecast cycle to +72 h in 3-hourly steps with wind, rain and, in a second atlas, cloud cover, 2 m
temperature and relative humidity. Output goes to data/processed/live/ (git-ignored); run it every 6 hours.
Usage: python scripts/build_live_weather.py
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys

import ee
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_weather_frames import GFS, P, U, V, fetch, gfs, rain_rate_3h, rgb
from services import weather_frames as wf
from services.earth_engine import init_ee

LIVE_DIR = Path(os.getenv("LIVE_BUILD_DIR", str(PROJECT_ROOT / "data" / "processed" / "live")))
CLOUD, TEMP, RH = "total_cloud_cover_entire_atmosphere", "temperature_2m_above_ground", "relative_humidity_2m_above_ground"
TEMP_MIN, TEMP_MAX = -30.0, 50.0


def encode_percent(x: np.ndarray) -> np.ndarray:
    return np.clip(np.rint(np.nan_to_num(x) / 100 * 255), 0, 255).astype(np.uint8)


def encode_temp(x: np.ndarray) -> np.ndarray:
    return np.clip(np.rint((np.nan_to_num(x, nan=TEMP_MIN) - TEMP_MIN) / (TEMP_MAX - TEMP_MIN) * 255), 0, 255).astype(np.uint8)


def newest_complete_cycle() -> pd.Timestamp:
    """Newest cycle that already holds every forecast hour we need. A cycle still being ingested has gaps."""
    now = pd.Timestamp.now("UTC").tz_localize(None)
    fmt = "%Y-%m-%dT%H:%M:%S"
    col = ee.ImageCollection(GFS).filterDate((now - pd.Timedelta(days=4)).strftime(fmt), (now + pd.Timedelta(days=5)).strftime(fmt))
    rows = col.reduceColumns(ee.Reducer.toList(2), ["creation_time", "forecast_hours"]).get("list").getInfo()
    hours: dict[int, set[int]] = {}
    for created, hour in rows:
        hours.setdefault(int(created), set()).add(int(hour))
    need = set(wf.forecast_steps())
    complete = [created for created, have in hours.items() if need <= have]
    if not complete:
        raise RuntimeError("no complete GFS cycle found in Earth Engine")
    return pd.Timestamp(max(complete), unit="ms")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--upload", default=os.getenv("LIVE_BUCKET"), help="gs://bucket/prefix to publish to (default: LIVE_BUCKET)")
    args = parser.parse_args()
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    init_ee()
    cycle = newest_complete_cycle()
    steps = wf.forecast_steps()
    print("cycle", cycle, "steps", len(steps), flush=True)

    def fields(step: int) -> tuple[np.ndarray, np.ndarray]:
        img = gfs(cycle, step)
        uv = fetch(img.select([U, V]), [U, V])
        ext = fetch(img.select([CLOUD, TEMP, RH]), [CLOUD, TEMP, RH])
        return uv, ext

    with ThreadPoolExecutor(6) as pool:
        got = list(pool.map(fields, steps))
        rain = list(pool.map(lambda s: np.maximum(rain_rate_3h(cycle, s), 0), steps))
    uv = np.stack([g[0] for g in got])      # (n, 2, H, W)
    ext = np.stack([g[1] for g in got])     # (n, 3, H, W)
    rain_arr = np.stack(rain)               # (n, H, W)

    name, ext_name = f"forecast_{wf.cycle_id(cycle)}.png", f"forecast_ext_{wf.cycle_id(cycle)}.png"
    wf.pack_atlas(rgb(wf.encode_wind(uv[:, 0]), wf.encode_wind(uv[:, 1]), wf.encode_rain(rain_arr))).save(LIVE_DIR / name, optimize=True)
    wf.pack_atlas(rgb(encode_percent(ext[:, 0]), encode_temp(ext[:, 1]), encode_percent(ext[:, 2]))).save(LIVE_DIR / ext_name, optimize=True)
    # one analysis frame (f000) and an empty observed-rain frame keep the manifest shape the replay code expects
    wf.pack_atlas(rgb(wf.encode_wind(uv[:1, 0]), wf.encode_wind(uv[:1, 1]))).save(LIVE_DIR / "analysis_wind.png", optimize=True)
    wf.pack_atlas(rgb(wf.encode_rain(np.zeros((1, wf.HEIGHT, wf.WIDTH))))).save(LIVE_DIR / "observed_rain.png", optimize=True)

    c, r = wf.atlas_shape(len(steps))
    c1, r1 = wf.atlas_shape(1)
    first = [wf.iso(cycle)]
    manifest = {
        "base": "/api/live",
        "bounds": wf.BOUNDS, "tile": {"width": wf.WIDTH, "height": wf.HEIGHT},
        "encoding": {"wind": {"channels": "RG", "min": -wf.WIND_MAX, "max": wf.WIND_MAX, "unit": "m/s"},
                     "rain": {"channels": "B (forecast)", "scale": "log1p", "max": wf.RAIN_MAX, "unit": "mm/h"},
                     "scalar": {"cloud": {"channel": "R", "min": 0, "max": 100, "unit": "%"},
                                "temperature": {"channel": "G", "min": TEMP_MIN, "max": TEMP_MAX, "unit": "°C"},
                                "humidity": {"channel": "B", "min": 0, "max": 100, "unit": "%"}}},
        "window": {"start": wf.iso(cycle), "end": wf.iso(cycle + pd.Timedelta(hours=wf.FORECAST_LEAD_H))},
        "analysis_wind": {"file": "analysis_wind.png", "cols": c1, "rows": r1, "frames": first, "source": "NOAA GFS 0.25 analysis (f000)"},
        "observed_rain": {"file": "observed_rain.png", "cols": c1, "rows": r1, "frames": first, "source": "none in live mode"},
        "forecast": [{"cycle": wf.iso(cycle), "file": name, "ext_file": ext_name, "cols": c, "rows": r, "step_hours": wf.FORECAST_STEP_H,
                      "frames": [wf.iso(cycle + pd.Timedelta(hours=s)) for s in steps],
                      "source": "NOAA GFS 0.25 forecast: 10 m wind, 3 h mean precipitation rate, cloud cover, 2 m temperature and humidity"}],
        "live": {"cycle": wf.iso(cycle), "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "source": "NOAA GFS via Google Earth Engine"},
    }
    (LIVE_DIR / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    size = sum(f.stat().st_size for f in LIVE_DIR.iterdir()) / 1e6
    print(f"live weather written: cycle {wf.iso(cycle)}, {size:.1f} MB")
    if args.upload:
        from services.live_store import upload

        print(f"uploaded {upload(LIVE_DIR, args.upload)} files to {args.upload}")


if __name__ == "__main__":
    main()
