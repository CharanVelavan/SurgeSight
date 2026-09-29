"""Cache MERIT Hydro height-above-drainage and upstream area per asset (WP2.7).

Usage: python scripts/build_river_flood.py [--region michaung_2023]
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.assets import load_all_assets
from services.config import load_region
from services.hazards.river_flood import sample_merit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default=None)
    args = parser.parse_args()
    region = load_region(args.region)
    table = sample_merit(load_all_assets(region.id))
    table.to_csv(region.path("river_assets"), index=False)
    print(table.describe().round(2))
    print(f"missing HAND: {int(table['hand_m'].isna().sum())} of {len(table)}")


if __name__ == "__main__":
    main()
