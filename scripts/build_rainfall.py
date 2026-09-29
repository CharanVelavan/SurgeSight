"""Cache per-asset rainfall (forecast + observed) into data/processed/rainfall_assets.csv (WP2.2).

Columns:
  fc_accum_mm, fc_peak_24h_mm      GFS forecast issued at or before the cutoff, window (cutoff, cutoff+72h]
  obs_accum_mm, obs_peak_24h_mm    IMERG observed over the SAME window (validation/hindcast only)
  event_accum_mm, event_peak_24h_mm  IMERG over the whole event window (for satellite validation, WP3)

Usage: python scripts/build_rainfall.py [--region michaung_2023] [--cutoff "2023-12-03 12:00"] [--hours 72]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.assets import load_all_assets
from services.config import load_region
from services.hazards.rainfall import FORECAST_NOTE, forecast_rainfall, imd_category, observed_rainfall

EVENT_WINDOW = ("2023-12-01 00:00", "2023-12-07 00:00")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default=None)
    parser.add_argument("--cutoff", default=None)
    parser.add_argument("--hours", type=int, default=72)
    args = parser.parse_args()
    region = load_region(args.region)
    cutoff = pd.Timestamp(args.cutoff or region.demo_cutoff)
    end = cutoff + pd.Timedelta(hours=args.hours)
    assets = load_all_assets(region.id)

    print(f"forecast rainfall (init {cutoff}, {args.hours} h)...")
    forecast, fc_meta = forecast_rainfall(str(cutoff), args.hours, assets, cutoff_utc=str(cutoff))
    print("observed IMERG, same window...")
    observed = observed_rainfall(str(cutoff), str(end), assets)
    print("observed IMERG, event window...")
    event = observed_rainfall(*EVENT_WINDOW, assets)

    table = assets[["osm_element", "osm_id"]].reset_index(drop=True)
    table["fc_accum_mm"], table["fc_peak_24h_mm"] = forecast["accum_mm"], forecast["peak_24h_mm"]
    table["obs_accum_mm"], table["obs_peak_24h_mm"] = observed["accum_mm"], observed["peak_24h_mm"]
    table["event_accum_mm"], table["event_peak_24h_mm"] = event["accum_mm"], event["peak_24h_mm"]
    table.to_csv(region.path("rainfall_assets"), index=False)

    valid = table.dropna(subset=["fc_accum_mm", "obs_accum_mm"])
    summary = {
        "region": region.id,
        "forecast": fc_meta,
        "observed_source": "NASA GPM IMERG V07 via Earth Engine (validation only)",
        "window_utc": [str(cutoff), str(end)],
        "event_window_utc": list(EVENT_WINDOW),
        "assets": int(len(table)),
        "assets_with_observed": int(table["obs_accum_mm"].notna().sum()),
        "forecast_vs_observed": {
            "correlation": round(float(np.corrcoef(valid["fc_accum_mm"], valid["obs_accum_mm"])[0, 1]), 3) if valid["fc_accum_mm"].std() > 0 else None,
            "mean_forecast_mm": round(float(valid["fc_accum_mm"].mean()), 1),
            "mean_observed_mm": round(float(valid["obs_accum_mm"].mean()), 1),
        },
        "imd_peak_24h_forecast_counts": table["fc_peak_24h_mm"].apply(lambda v: imd_category(v) if pd.notna(v) else "n/a").value_counts().to_dict(),
        "imd_peak_24h_observed_counts": table["obs_peak_24h_mm"].apply(lambda v: imd_category(v) if pd.notna(v) else "n/a").value_counts().to_dict(),
        "note": FORECAST_NOTE,
    }
    (region.path("rainfall_assets").parent / "rainfall_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
