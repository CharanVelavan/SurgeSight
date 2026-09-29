"""Facility-quality classification and v1-untouched checks."""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.facility_quality import classify_facility


def main() -> None:
    assert classify_facility("Apollo Hospital", "hospital", None) == "hospital"
    assert classify_facility("Kalabhavan Hospital", "hospital", None) == "hospital"  # 'lab' inside a word
    assert classify_facility("4 Squares Dentistry", "hospital", None) == "clinic_or_other"
    assert classify_facility("Dental Hospital", "hospital", None) == "clinic_or_other"
    assert classify_facility("Chennai Eye Care Hospital", "hospital", None) == "clinic_or_other"
    assert classify_facility("City Diagnostics", "hospital", None) == "clinic_or_other"
    assert classify_facility(float("nan"), "hospital", None) == "hospital"

    assets = pd.read_csv(PROJECT_ROOT / "data/processed/scored_assets.csv")
    hospitals = assets[assets["asset_type"] == "hospital"]
    assert set(hospitals["facility_quality"]) == {"hospital", "clinic_or_other"}
    assert (assets.loc[assets["asset_type"] != "hospital", "facility_quality"] == "not_applicable").all()
    counts = assets["risk_class"].value_counts().to_dict()
    assert counts == {"MODERATE": 2228, "HIGH": 1737, "CRITICAL": 8, "LOW": 4}, counts  # v1 unchanged
    print("SURGESIGHT_FACILITY_QUALITY_OK")


if __name__ == "__main__":
    main()
