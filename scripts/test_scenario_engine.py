"""Validate scenario baseline equivalence and the +30 km north demo preset."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.scenario_engine import BASELINE_ASSETS_FILE, run_scenario


def main() -> None:
    baseline = pd.read_csv(BASELINE_ASSETS_FILE)
    zero_assets, _, zero_summary = run_scenario(0, 0, 0, save_outputs=False)
    numeric_pairs = {
        "distance_to_track_km": "distance_to_track_km",
        "nearest_track_wind_kmh": "nearest_track_wind_kmh",
        "wind_score": "wind_score",
        "combined_risk_score": "combined_risk_score",
        "terrain_flood_score": "terrain_flood_score",
    }
    for scenario_column, baseline_column in numeric_pairs.items():
        if not zero_assets[scenario_column].equals(baseline[baseline_column]):
            mismatch = int(
                zero_assets[scenario_column].ne(baseline[baseline_column]).sum()
            )
            raise AssertionError(f"Baseline mismatch in {scenario_column}: {mismatch} rows")
    if not zero_assets["risk_class"].equals(baseline["risk_class"]):
        raise AssertionError("Baseline risk classes do not match")
    if zero_summary["assets_risk_increased"] or zero_summary["assets_risk_decreased"]:
        raise AssertionError("Zero-change scenario contains risk changes")
    print("SURGESIGHT_SCENARIO_BASELINE_MATCH_OK")

    _, _, summary = run_scenario(30, 0, 0, save_outputs=True)
    print("SURGESIGHT_SCENARIO_30KM_OK")
    print(f"Baseline critical assets: {summary['baseline_critical_assets']}")
    print(f"Scenario critical assets: {summary['scenario_critical_assets']}")
    print(
        "Baseline high + critical assets: "
        f"{summary['baseline_high_or_critical_assets']}"
    )
    print(
        "Scenario high + critical assets: "
        f"{summary['scenario_high_or_critical_assets']}"
    )
    print(f"Newly high-risk hospitals: {summary['newly_high_risk_hospitals']}")
    print(f"Newly critical hospitals: {summary['newly_critical_hospitals']}")
    print(f"Newly high-risk substations: {summary['newly_high_risk_substations']}")
    print(f"Newly critical substations: {summary['newly_critical_substations']}")
    print(f"Assets with increased risk: {summary['assets_risk_increased']}")
    print(f"Assets with decreased risk: {summary['assets_risk_decreased']}")
    print(f"Runtime: {summary['runtime_seconds']:.4f} seconds")


if __name__ == "__main__":
    main()
