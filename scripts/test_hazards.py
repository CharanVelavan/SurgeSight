"""Rainfall, surge and risk-v2 tests (offline except one optional Earth Engine check)."""

from __future__ import annotations

import math
import os
from pathlib import Path
import sys

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.hazards.coast import find_landfall
from services.hazards.rainfall import (
    RAIN_REF_MM,
    FutureRainfallAccessError,
    forecast_rainfall,
    imd_category,
    load_rainfall_assets,
    rain_flood_score,
    rain_inputs,
    rain_score,
)
from services.hazards.surge import SURGE_CONSTANTS, peak_surge, shelf_factor, surge_scores
from services.hazards.wind_field import holland_kmh, max_wind_kmh, rmw_km
from services.risk_model_v2 import CLASS_ORDER, HAZARD_WEIGHTS, score_v2
from services.scenario_engine import shift_track_unbounded

TRACK = pd.read_csv(PROJECT_ROOT / "data/processed/michaung_track.csv")
ASSETS = pd.read_csv(PROJECT_ROOT / "data/processed/scored_assets.csv")


def test_rainfall() -> None:
    assert RAIN_REF_MM == 300.0
    assert list(rain_score(np.array([0, 150, 300, 900]))) == [0.0, 0.5, 1.0, 1.0]
    assert np.isclose(rain_flood_score(150, 0.0), 0.25) and np.isclose(rain_flood_score(150, 1.0), 0.5)
    assert [imd_category(v) for v in (10, 64.5, 115.6, 204.5)] == ["below heavy", "heavy", "very heavy", "extremely heavy"]

    # leakage guards: observed rain cannot feed a prediction; a run issued after the cutoff is refused
    try:
        rain_inputs("observed")
    except FutureRainfallAccessError:
        pass
    else:
        raise AssertionError("observed rainfall must need hindcast=True")
    observed, meta = rain_inputs("observed", hindcast=True)
    assert meta["validation_only"] is True
    forecast, meta = rain_inputs("forecast")
    assert meta["validation_only"] is False
    try:
        forecast_rainfall("2023-12-03 18:00", 72, ASSETS.head(2), cutoff_utc="2023-12-03 12:00")
    except FutureRainfallAccessError:
        pass
    else:
        raise AssertionError("a run issued after the cutoff must be refused")

    table = load_rainfall_assets()
    covered = ASSETS[["osm_element", "osm_id"]].merge(table, on=["osm_element", "osm_id"], how="left")
    assert len(table) >= len(ASSETS) and len(covered) == len(ASSETS)  # the cache also covers the department layers (WP4.2)
    assert covered[["fc_accum_mm", "fc_peak_24h_mm", "obs_accum_mm"]].notna().all().all()
    both = table.dropna(subset=["fc_accum_mm", "obs_accum_mm"])
    assert np.corrcoef(both["fc_accum_mm"], both["obs_accum_mm"])[0, 1] > 0.5, "forecast should track observed pattern"
    assert (table["fc_peak_24h_mm"] <= table["fc_accum_mm"] + 0.01).all()

    if os.getenv("SURGESIGHT_OFFLINE") != "1":  # cache agrees with a fresh Earth Engine read
        sample = ASSETS.iloc[[0, 1500, 3000]]
        fresh, _ = forecast_rainfall("2023-12-03 12:00", 72, sample, cutoff_utc="2023-12-03 12:00")
        cached = table.set_index(["osm_element", "osm_id"]).loc[list(zip(sample["osm_element"], sample["osm_id"])), "fc_accum_mm"]
        assert np.allclose(fresh["accum_mm"].to_numpy(), cached.to_numpy(), atol=0.05), (fresh["accum_mm"].tolist(), cached.tolist())
    print("SURGESIGHT_RAINFALL_OK")


def test_surge() -> None:
    assert math.isclose(shelf_factor(20), 1.5) and math.isclose(shelf_factor(200), 0.7)
    assert shelf_factor(5) == 1.5 and shelf_factor(5000) == 0.7 and 0.7 < shelf_factor(60) < 1.5

    landfall = find_landfall(TRACK)
    assert landfall is not None and 15.0 < landfall["lat"] < 16.0 and 79.8 < landfall["lon"] < 80.5, landfall
    info = peak_surge(TRACK)
    ib = 0.01 * (1010 - landfall["pressure_hpa"])
    assert math.isclose(info["inverse_barometer_m"], ib, abs_tol=1e-3)
    setup = SURGE_CONSTANTS["K_WS"] * (landfall["wind_kmh"] / 3.6 / 50) ** 2 * info["shelf_factor"]
    assert math.isclose(info["wind_setup_m"], setup, abs_tol=1e-3)
    assert math.isclose(info["peak_surge_m"], ib + setup, abs_tol=2e-3)
    expected_rmw = 46.4 * math.exp(-0.0155 * landfall["wind_kmh"] / 3.6 + 0.0169 * landfall["lat"])
    assert math.isclose(info["rmw_km"], expected_rmw, abs_tol=0.1)

    stronger = TRACK.copy()
    stronger["WIND_KMH"] *= 1.2
    stronger["PRESSURE_HPA"] -= 20
    assert peak_surge(stronger)["peak_surge_m"] > info["peak_surge_m"]

    offshore = shift_track_unbounded(TRACK, 0, 400, 0)  # 400 km east: never reaches the coast
    frame, off_info = surge_scores(offshore, ASSETS)
    assert off_info["landfall"] is None and (frame["surge_score"] == 0).all()

    frame, _ = surge_scores(TRACK, ASSETS)
    merged = ASSETS.merge(frame, on=["osm_element", "osm_id"])
    assert ((frame["surge_score"] >= 0) & (frame["surge_score"] <= 1)).all()
    hit = merged[merged["surge_score"] > 0]
    assert len(hit) > 0 and (hit["elevation_m"] < hit["surge_m"]).all(), "surge only reaches assets below the water level"
    assert (merged.loc[merged["elevation_m"] >= info["peak_surge_m"], "surge_score"] == 0).all()
    coast = pd.read_csv(PROJECT_ROOT / "data/processed/coast_assets.csv").merge(ASSETS, on=["osm_element", "osm_id"])
    assert (coast.loc[coast["coast_dist_km"] > 10].merge(frame, on=["osm_element", "osm_id"])["surge_score"] == 0).all()
    sides = set(frame.loc[frame["surge_m"] > 0, "coast_side"])
    assert sides <= {"right_of_track", "left_of_track"}
    print("SURGESIGHT_SURGE_OK")


def test_risk_v2() -> None:
    # Holland profile: peak at Rmax, decays outward; asymmetry favours the right of the track
    assert math.isclose(float(holland_kmh(np.array([40.0]), 100.0, 40.0)[0]), 100.0, rel_tol=1e-9)
    profile = holland_kmh(np.array([40.0, 80.0, 160.0, 320.0]), 100.0, 40.0)
    assert (np.diff(profile) < 0).all()
    assert math.isclose(float(rmw_km(28.0, 14.0)), 46.4 * math.exp(-0.0155 * 28 + 0.0169 * 14), rel_tol=1e-9)
    moving_north = pd.DataFrame({
        "LAT": [10.0, 10.5, 11.0], "LON": [80.0, 80.0, 80.0], "WIND_KMH": [100.0] * 3,
        "PRESSURE_HPA": [990.0] * 3, "ISO_TIME": ["2023-12-01 00:00", "2023-12-01 06:00", "2023-12-01 12:00"],
    })
    east, west = max_wind_kmh(moving_north, np.array([10.5, 10.5]), np.array([80.5, 79.5]))
    assert east > west, "right of a north-moving track (east) should be stronger"

    v2, meta = score_v2(TRACK, ASSETS)
    assert meta["model_version"] == "v2.0" and meta["rain"]["validation_only"] is False
    assert len(v2) == len(ASSETS) and set(v2["class_v2"]) <= set(CLASS_ORDER)
    terms = np.vstack([
        HAZARD_WEIGHTS["wind"] * v2["wind_v2"], HAZARD_WEIGHTS["surge"] * v2["surge_score"],
        HAZARD_WEIGHTS["rain_flood"] * v2["rain_flood_score"],
    ])
    assert np.allclose(v2["combined_v2"], 1 - np.prod(1 - terms, axis=0), atol=1e-3)
    assert (v2["combined_v2"] >= terms.max(axis=0) - 1e-3).all(), "combining hazards never lowers the score"
    names = ["wind", "surge", "rain_flood"]
    reported = np.array([names.index(h) for h in v2["dominant_hazard"]])
    chosen_term = terms[reported, np.arange(len(v2))]
    assert (chosen_term >= terms.max(axis=0) - 2e-4).all(), "dominant hazard must be the largest term (within rounding)"
    assert {"wind_v2", "surge_score", "rain_flood_score", "terrain_flood_score"} <= set(v2.columns)
    assert set(v2["triage_tier"]) == {1, 2, 3, 4} and v2["triage_tier"].eq(1).sum() >= 0.09 * len(v2)
    assert (v2.loc[v2["triage_tier"] == 1, "combined_v2"].min() >= v2.loc[v2["triage_tier"] == 4, "combined_v2"].max())

    # weaker storm scores lower; observed rain is refused for prediction
    weak = TRACK.copy()
    weak["WIND_KMH"] *= 0.6
    v2_weak, _ = score_v2(weak, ASSETS)
    assert v2_weak["combined_v2"].mean() < v2["combined_v2"].mean()
    try:
        score_v2(TRACK, ASSETS, rain_mode="observed")
    except FutureRainfallAccessError:
        pass
    else:
        raise AssertionError("observed rain must be refused without hindcast")
    hind, hind_meta = score_v2(TRACK, ASSETS, rain_mode="observed", hindcast=True)
    assert hind_meta["rain"]["validation_only"] is True

    # v1 frozen: unchanged distribution
    assert ASSETS["risk_class"].value_counts().to_dict() == {"MODERATE": 2228, "HIGH": 1737, "CRITICAL": 8, "LOW": 4}
    print("v2 classes:", v2["class_v2"].value_counts().to_dict(), "| v1:", ASSETS["risk_class"].value_counts().to_dict())
    print("SURGESIGHT_RISK_V2_OK")


def main() -> None:
    test_rainfall()
    test_surge()
    test_risk_v2()


if __name__ == "__main__":
    main()
