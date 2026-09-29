"""Score the extra department layers with v1 (same method as the core assets) (WP4.2).

Usage: python scripts/score_extra_assets.py   then rebuild the hazard caches:
  python scripts/build_coast.py && python scripts/build_rainfall.py && python scripts/build_river_flood.py
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import score_infrastructure_risk as core  # noqa: E402
from services.config import load_region  # noqa: E402
from services.facility_quality import add_facility_quality  # noqa: E402
from services.risk_model import attach_nearest_track  # noqa: E402


def main() -> None:
    region = load_region()
    track = pd.read_csv(region.path("track"))
    assets = pd.read_csv(region.path("extra_assets_raw"))
    for column in ('healthcare', 'emergency', 'power', 'highway', 'voltage'):  # columns the core layers carry
        assets[column] = assets.get(column)
    assets = attach_nearest_track(assets, track)
    samples, failures = core.sample_earth_engine(assets, "")
    scored = add_facility_quality(core.score_assets(assets, samples))
    scored.to_csv(region.path("scored_assets_extra"), index=False)
    print(scored["asset_type"].value_counts().to_dict(), "failures:", failures)
    print(scored.groupby("asset_type")["risk_class"].value_counts().unstack(fill_value=0))
    print("SURGESIGHT_EXTRA_ASSETS_SCORED")


if __name__ == "__main__":
    main()
