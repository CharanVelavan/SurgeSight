"""Tests for the SurgeSight Experimental Track Forecast."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.scenario_engine import BASELINE_ASSETS_FILE, score_custom_track  # noqa: E402
from services.track_forecaster import (  # noqa: E402
    DEFAULT_DEMO_CUTOFF,
    HORIZONS_HOURS,
    MODEL_KALMAN,
    MODEL_WIND,
    InsufficientObservationsError,
    compare_track_impacts,
    covariance_is_valid,
    forecast_scenario_track,
    forecast_track,
    observations_until,
    reference_track_window,
)
from services.track_forecast_explainer import (  # noqa: E402
    TrackForecastExplanation,
    ungrounded_numbers,
)
from services.wind_provider import FutureWindAccessError, WindGrid, load_wind_grid  # noqa: E402


TRACK_FILE = Path("data/processed/michaung_track.csv")
MODELS = (MODEL_KALMAN, MODEL_WIND)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"  ok  {message}")


def synthetic_track(lat_step: float, lon_step: float, count: int = 8) -> pd.DataFrame:
    times = pd.date_range("2023-12-01 00:00", periods=count, freq="6h")
    return pd.DataFrame({
        "ISO_TIME": times,
        "LAT": 12.0 + lat_step * np.arange(count),
        "LON": 82.0 + lon_step * np.arange(count),
        "WIND_KMH": 80.0,
    })


def calm_wind_grid(track: pd.DataFrame) -> WindGrid:
    times = pd.date_range(
        pd.Timestamp(track["ISO_TIME"].min()) - pd.Timedelta(hours=12),
        pd.Timestamp(track["ISO_TIME"].max()) + pd.Timedelta(hours=30), freq="1h",
    ).to_numpy(dtype="datetime64[s]")
    lats, lons = np.arange(0.0, 27.0, 1.0), np.arange(72.0, 97.0, 1.0)
    zeros = np.zeros((len(times), len(lats), len(lons)))
    return WindGrid(times=times, lats=lats, lons=lons,
                    u={lvl: zeros for lvl in (850, 500, 200)},
                    v={lvl: zeros for lvl in (850, 500, 200)})


def main() -> None:
    track = pd.read_csv(TRACK_FILE)
    wind_grid = load_wind_grid(track, allow_download=False)
    cutoff = DEFAULT_DEMO_CUTOFF

    print("Chronological ordering")
    shuffled = track.sample(frac=1.0, random_state=7)
    for model in MODELS:
        ordered = forecast_track(track, cutoff, model, wind_grid=wind_grid)
        unordered = forecast_track(shuffled, cutoff, model, wind_grid=wind_grid)
        check(np.allclose(ordered.points[["lat", "lon"]], unordered.points[["lat", "lon"]]),
              f"{model}: shuffled input gives identical forecast")
    used = observations_until(shuffled, cutoff)
    check(used["ISO_TIME"].is_monotonic_increasing, "observations are sorted by time")

    print("No future observation leakage")
    for model in MODELS:
        base = forecast_track(track, cutoff, model, wind_grid=wind_grid)
        tampered = track.copy()
        future = pd.to_datetime(tampered["ISO_TIME"]) > cutoff
        tampered.loc[future, "LAT"] += 5.0
        tampered.loc[future, "LON"] -= 5.0
        altered = forecast_track(tampered, cutoff, model, wind_grid=wind_grid)
        check(np.allclose(base.points[["lat", "lon"]], altered.points[["lat", "lon"]]),
              f"{model}: altering future fixes does not change the forecast")
        check(base.last_observation_time <= cutoff, f"{model}: last fix used <= cutoff")
    interpolated_cutoff = cutoff + pd.Timedelta(hours=3)
    check(observations_until(track, interpolated_cutoff)["ISO_TIME"].max() == cutoff,
          "IBTrACS-interpolated rows (03/09/15/21 UTC) are never assimilated")
    visible = wind_grid.until(cutoff)
    check(pd.Timestamp(visible.times[-1]) <= cutoff, "wind grid sliced to cutoff")
    try:
        visible.steering_vector(12.0, 82.0, cutoff + pd.Timedelta(hours=1))
        raise AssertionError("future wind access was allowed")
    except FutureWindAccessError:
        print("  ok  future wind access raises FutureWindAccessError")
    try:
        forecast_track(track, "2023-11-30 06:00", MODEL_KALMAN)
        raise AssertionError("single-fix forecast was allowed")
    except InsufficientObservationsError:
        print("  ok  too few fixes raises InsufficientObservationsError")

    print("Zero / near-zero displacement sanity")
    stationary = synthetic_track(0.0, 0.0)
    stationary_cutoff = pd.Timestamp(stationary["ISO_TIME"].iloc[-1])
    result = forecast_track(stationary, stationary_cutoff, MODEL_KALMAN)
    drift = max(abs(result.points["lat"] - 12.0).max(), abs(result.points["lon"] - 82.0).max())
    check(drift < 1e-6, f"stationary storm stays put (max drift {drift:.2e} deg)")
    creeping = synthetic_track(0.001, 0.0)
    result = forecast_track(creeping, pd.Timestamp(creeping["ISO_TIME"].iloc[-1]), MODEL_KALMAN)
    moved = result.at_lead(24)["lat"] - creeping["LAT"].iloc[-1]
    check(0.0 < moved < 0.01, f"near-zero northward motion extrapolates slightly north ({moved:.4f} deg)")
    calm = forecast_track(stationary, stationary_cutoff, MODEL_WIND, wind_grid=calm_wind_grid(stationary))
    calm_move = calm.at_lead(24)
    check(calm_move["lat"] > 12.0 and calm_move["lon"] < 82.0,
          "calm environment + beta drift moves wind model north-west only")
    straight = synthetic_track(0.25, -0.25)
    straight_cutoff = pd.Timestamp(straight["ISO_TIME"].iloc[-1])
    result = forecast_track(straight, straight_cutoff, MODEL_KALMAN)
    expected = (straight["LAT"].iloc[-1] + 0.25 * 4, straight["LON"].iloc[-1] - 0.25 * 4)
    got = result.at_lead(24)
    check(abs(got["lat"] - expected[0]) < 0.1 and abs(got["lon"] - expected[1]) < 0.1,
          "constant-velocity track extrapolated linearly")

    print("6/12/24 h predictions, valid lat/lon, valid covariance")
    for model in MODELS:
        forecast = forecast_track(track, cutoff, model, wind_grid=wind_grid)
        horizons = forecast.horizons()
        check(list(horizons["lead_hours"]) == list(HORIZONS_HOURS), f"{model}: +6/+12/+24 h present")
        check(list(horizons["valid_time"]) == [cutoff + pd.Timedelta(hours=h) for h in HORIZONS_HOURS],
              f"{model}: valid times correct")
        check(horizons["lat"].between(-90, 90).all() and horizons["lon"].between(-180, 180).all()
              and np.isfinite(horizons[["lat", "lon"]]).all().all(), f"{model}: lat/lon finite and in range")
        check(all(covariance_is_valid(cov) for cov in forecast.points["_cov"]),
              f"{model}: every covariance symmetric positive definite")
        radii = forecast.points["uncertainty_radius_km"].to_numpy()
        check(bool(np.all(np.diff(radii) > 0)), f"{model}: uncertainty grows with lead time")
        check(bool((forecast.points["forecast_label"] == "SurgeSight Experimental Track Forecast").all()),
              f"{model}: every row carries the experimental label")

    print("Scenario risk engine accepts experimental track")
    baseline = pd.read_csv(BASELINE_ASSETS_FILE)
    full_scored = score_custom_track(track, baseline)
    check(full_scored["scenario_risk_class"].equals(baseline["risk_class"]),
          "full observed track through score_custom_track reproduces baseline classes")
    forecasts = {m: forecast_track(track, cutoff, m, wind_grid=wind_grid) for m in MODELS}
    scenario_track = forecast_scenario_track(track, forecasts[MODEL_WIND])
    check(scenario_track["ISO_TIME"].is_monotonic_increasing, "scenario track is chronological")
    reference = reference_track_window(track, cutoff)
    check(list(scenario_track["ISO_TIME"]) == list(reference["ISO_TIME"]),
          "experimental and reference tracks share identical valid times")
    impacts = compare_track_impacts(track, forecasts, baseline_assets=baseline)
    for name in ("reference", MODEL_KALMAN, MODEL_WIND):
        entry = impacts["tracks"][name]
        check(all(isinstance(entry[k], int) for k in
                  ("high_plus_assets", "critical_assets", "high_plus_hospitals", "high_plus_substations")),
              f"{name}: integer impact counts")
    delta = impacts["tracks"][MODEL_KALMAN]["delta_vs_reference"]["high_plus_assets"]
    check(delta == impacts["tracks"][MODEL_KALMAN]["high_plus_assets"]
          - impacts["tracks"]["reference"]["high_plus_assets"], "delta vs reference is consistent")
    identical = forecasts[MODEL_KALMAN]
    identical.points = identical.points.copy()
    ref_by_time = reference.set_index("ISO_TIME")
    identical.points["lat"] = ref_by_time.loc[identical.points["valid_time"], "LAT"].to_numpy()
    identical.points["lon"] = ref_by_time.loc[identical.points["valid_time"], "LON"].to_numpy()
    same = compare_track_impacts(track, {MODEL_KALMAN: identical}, baseline_assets=baseline)
    check(same["tracks"][MODEL_KALMAN]["delta_vs_reference"]["high_plus_assets"] == 0,
          "a forecast equal to the reference track yields zero impact delta")

    print("Explanation grounding guard")
    context = {"lat": 13.27, "error": 43.4, "count": 1295}
    grounded = TrackForecastExplanation(
        headline="13.27 and 43.4 km", forecast_difference="1,295 assets", impact_difference="",
        uncertainty_note="24-hour", caveats=[], backtest_verdict="", disclaimer="")
    check(not ungrounded_numbers(grounded, context), "numbers present in inputs are accepted")
    invented = grounded.model_copy(update={"forecast_difference": "landfall at 14.9N"})
    check(ungrounded_numbers(invented, context) == ["14.9"], "invented coordinates are rejected")

    print("SURGESIGHT_TRACK_FORECASTER_OK")


if __name__ == "__main__":
    main()
