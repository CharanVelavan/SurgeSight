"""Backfill ``facility_quality`` into the existing scored assets without rescoring (WP0.5)."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.facility_quality import add_facility_quality

CSV = PROJECT_ROOT / "data/processed/scored_assets.csv"
GEOJSON = PROJECT_ROOT / "data/processed/scored_assets.geojson"
SUMMARY = PROJECT_ROOT / "data/processed/facility_quality_summary.json"


def main() -> None:
    original = pd.read_csv(CSV)
    if "facility_quality" in original.columns:
        original = original.drop(columns="facility_quality")
    updated = add_facility_quality(original)

    # v1 outputs must not change: every original column is identical.
    pd.testing.assert_frame_equal(updated[original.columns], original)

    updated.to_csv(CSV, index=False)
    geo = json.loads(GEOJSON.read_text(encoding="utf-8"))
    assert len(geo["features"]) == len(updated)
    for feature, quality in zip(geo["features"], updated["facility_quality"]):
        feature["properties"]["facility_quality"] = quality
    GEOJSON.write_text(json.dumps(geo, indent=2), encoding="utf-8")

    hospitals = updated[updated["asset_type"] == "hospital"]
    counts = hospitals["facility_quality"].value_counts().to_dict()
    high = hospitals["risk_class"].isin(["HIGH", "CRITICAL"])
    summary = {
        "osm_hospital_tagged": int(len(hospitals)),
        "hospital": int(counts.get("hospital", 0)),
        "clinic_or_other": int(counts.get("clinic_or_other", 0)),
        "hospital_high_or_critical_v1": int(
            (high & (hospitals["facility_quality"] == "hospital")).sum()
        ),
        "all_tagged_high_or_critical_v1": int(high.sum()),
    }
    SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
