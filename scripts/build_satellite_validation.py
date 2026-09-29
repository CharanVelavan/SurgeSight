"""Build the cached satellite-validation inputs (WP3): observed flood flag per asset + map images.

Earth Engine runs here only; the app and tools read the cached files.
Usage: python scripts/build_satellite_validation.py [--region michaung_2023]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.config import load_region
from services.risk_model_v2 import score_v2
from services.satellite_images import earth_engine_maps, screening_png
from services.satellite_validation import (
    FLOOD_ASSETS_FILE, IMAGE_FILES, META_FILE, SATELLITE_DIR, build_observed_flood, compute_metrics,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default=None)
    args = parser.parse_args()
    region = load_region(args.region)
    assets = pd.read_csv(region.path("scored_assets"))
    track = pd.read_csv(region.path("track"))
    SATELLITE_DIR.mkdir(parents=True, exist_ok=True)

    print("observed flood flag per asset...", flush=True)
    table, observed = build_observed_flood(assets, args.region)
    table.to_csv(FLOOD_ASSETS_FILE, index=False)
    META_FILE.write_text(json.dumps(observed.meta, indent=2), encoding="utf-8")
    print(json.dumps(observed.meta["attempts"], indent=2), flush=True)

    print("map images...", flush=True)
    frame, _ = score_v2(track, assets)
    images = earth_engine_maps(observed, args.region)
    images["screening"] = screening_png(frame, table, args.region)
    for key, data in images.items():
        (SATELLITE_DIR / IMAGE_FILES[key]).write_bytes(data)

    metrics = compute_metrics(frame, table, observed.meta)
    (SATELLITE_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps({k: metrics[k] for k in ("sensor", "assets_observed", "asset_coverage_pct", "flooded_share_of_observed", "ranking_skill_auc", "v1_high_plus", "v2_high_plus")}, indent=2))


if __name__ == "__main__":
    main()
