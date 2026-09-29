"""Cache the GFS-versus-Kalman comparison for the demo cutoff (WP2.6).

Usage: python scripts/build_nwp_comparison.py [--region michaung_2023] [--cutoff "2023-12-03 12:00"]
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
from services.nwp_comparison import nwp_comparison


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default=None)
    parser.add_argument("--cutoff", default=None)
    args = parser.parse_args()
    region = load_region(args.region)
    result = nwp_comparison(pd.read_csv(region.path("track")), args.cutoff or region.demo_cutoff)
    region.path("nwp_comparison").write_text(json.dumps(result, indent=2), encoding="utf-8")
    for row in result["rows"]:
        print(row["lead_hours"], row.get("gfs"), row.get("gfs_error_km"), row.get("kalman_error_km"))


if __name__ == "__main__":
    main()
