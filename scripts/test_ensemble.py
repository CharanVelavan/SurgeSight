"""Ensemble: reproducible by seed, fast, consistent with the validated v1 engine."""

from __future__ import annotations

from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.ensemble import _score_member, calibrated_ellipse_scale, default_sigma_km, run_ensemble
from services.scenario_engine import compare_scenario, load_scenario_inputs, shift_track_unbounded


def main() -> None:
    # 1. member scoring equals the validated compare_scenario path
    track, baseline = load_scenario_inputs()
    shifted = shift_track_unbounded(track, 33.0, -41.0, 7.0)
    reference = compare_scenario(baseline, shifted)["scenario_risk_score"].to_numpy()
    member = _score_member(baseline, shifted)["combined_risk_score"].to_numpy()
    assert np.array_equal(reference, member), "ensemble member differs from compare_scenario"

    # 2. zero-uncertainty ensemble reproduces the v1 baseline classes exactly
    zero = run_ensemble(members=5, sigma_km=0.0, sigma_intensity_pct=0.0)
    high_now = baseline["risk_class"].isin(["HIGH", "CRITICAL"]).to_numpy()
    assert np.array_equal(zero.assets["p_high_plus"].to_numpy() == 1.0, high_now)
    assert set(zero.assets["p_high_plus"].unique()) <= {0.0, 1.0}

    # 3. seed reproducibility, runtime, structure
    started = time.perf_counter()
    first = run_ensemble(members=100, seed=42, center_shift_n_km=30)
    elapsed = time.perf_counter() - started
    again = run_ensemble(members=100, seed=42, center_shift_n_km=30)
    other = run_ensemble(members=100, seed=7, center_shift_n_km=30)
    pd.testing.assert_frame_equal(first.assets, again.assets)
    assert not first.assets["p_high_plus"].equals(other.assets["p_high_plus"])
    assert elapsed < 6.0, f"100 members took {elapsed:.2f}s"
    assert first.parameters["seed"] == 42 and first.parameters["sigma_km_per_axis"] == default_sigma_km()
    a = first.assets
    assert ((a["p_high_plus"] >= 0) & (a["p_high_plus"] <= 1)).all()
    assert (a["p_critical"] <= a["p_high_plus"] + 1e-9).all()
    assert (a["score_p10"] <= a["score_mean"] + 1e-3).all() and (a["score_mean"] <= a["score_p90"] + 1e-3).all()
    assert (a["priority"] == (a["p_high_plus"] * a["criticality_weight"]).round(4)).all()
    assert set(first.top_by_type) == {"hospital", "school", "shelter", "substation"}
    top = first.top_by_type["hospital"]
    assert len(top) == 15 and top == sorted(top, key=lambda r: (r["priority"], r["score_mean"]), reverse=True)
    hospitals = a[a["asset_type"] == "hospital"].set_index("osm_id")
    assert all(hospitals.loc[r["osm_id"], "facility_quality"] == "hospital" for r in top[:15] if r["osm_id"] in hospitals.index)
    assert len(first.spaghetti_geojson["features"]) == 21  # centre + 20 members

    # 4. the 12 h default sigma matches ~51.5 km RMSE / sqrt(2) and the calibration is computed
    assert abs(default_sigma_km(12) - 36.42) < 0.05
    calibration = calibrated_ellipse_scale()
    assert calibration["available"] and calibration["ellipse_scale_by_lead"]["12h"] < 1.0
    print(f"100 members in {elapsed:.2f}s; top hospital: {top[0]['name']} ({top[0]['high_in_text']})")
    print("ellipse scale:", calibration["ellipse_scale_by_lead"], "| uncalibrated coverage:", calibration["observed_coverage_pct_uncalibrated"], "%")
    print("SURGESIGHT_ENSEMBLE_OK")


if __name__ == "__main__":
    main()
