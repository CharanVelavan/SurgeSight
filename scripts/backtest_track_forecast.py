"""Leakage-free historical backtest of the SurgeSight Experimental Track Forecast.

For each synoptic cutoff T on Cyclone Michaung, each model sees only original
IBTrACS fixes at or before T (and GFS winds valid at or before T), then predicts
T+6/12/24 h. Predictions are verified against later original IBTrACS fixes.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.track_forecaster import (  # noqa: E402
    CHI2_2DOF_90,
    DISCLAIMER,
    FORECAST_LABEL,
    HORIZONS_HOURS,
    MIN_OBSERVATIONS,
    MODEL_KALMAN,
    MODEL_LABELS,
    MODEL_WIND,
    SCIENTIFIC_NOTES,
    forecast_cutoffs,
    forecast_track,
    is_original_observation,
    mahalanobis_squared,
    position_error_km,
    prepare_track,
)
from services.wind_provider import (  # noqa: E402
    ANNULUS_RADII_KM,
    STEERING_WEIGHTS,
    TRAILING_WINDOW_HOURS,
    load_wind_grid,
)


TRACK_FILE = Path("data/processed/michaung_track.csv")
RAW_IBTRACS = Path("data/raw/ibtracs.csv")
OUTPUT_JSON = Path("data/processed/track_backtest.json")
OUTPUT_CSV = Path("data/processed/track_backtest.csv")
MODELS = (MODEL_KALMAN, MODEL_WIND)


def verify_observation_rule(track: pd.DataFrame) -> dict[str, object]:
    """Check the synoptic-hour rule against raw IBTrACS IFLAG where available."""

    if not RAW_IBTRACS.exists():
        return {"checked": False, "reason": "raw IBTrACS not available"}
    sid = str(track["SID"].iloc[0])
    raw = pd.read_csv(
        RAW_IBTRACS, skiprows=[1], low_memory=False,
        usecols=["SID", "ISO_TIME", "IFLAG"],
    )
    raw = raw[raw["SID"].eq(sid)].copy()
    raw["ISO_TIME"] = pd.to_datetime(raw["ISO_TIME"])
    merged = track.merge(raw[["ISO_TIME", "IFLAG"]], on="ISO_TIME", how="left")
    by_iflag = merged["IFLAG"].astype(str).str[0].eq("O")
    by_rule = is_original_observation(track)
    agree = bool(by_iflag.equals(by_rule))
    if not agree:
        raise AssertionError("Synoptic-hour rule disagrees with IBTrACS IFLAG")
    return {
        "checked": True,
        "agrees_with_iflag": agree,
        "original_fixes": int(by_iflag.sum()),
        "interpolated_rows_excluded": int((~by_iflag).sum()),
    }


def _summarise(errors: pd.Series) -> dict[str, float | int]:
    values = errors.to_numpy(dtype=float)
    return {
        "cases": int(values.size),
        "mean_km": round(float(values.mean()), 1),
        "median_km": round(float(np.median(values)), 1),
        "rmse_km": round(float(np.sqrt(np.mean(values**2))), 1),
        "p90_km": round(float(np.percentile(values, 90)), 1),
        "max_km": round(float(values.max()), 1),
    }


def run_backtest() -> dict[str, object]:
    started = time.perf_counter()
    raw_track = pd.read_csv(TRACK_FILE)
    track = prepare_track(raw_track)
    observation_check = verify_observation_rule(track)
    wind_grid = load_wind_grid(track)

    fixes = track[is_original_observation(track)].set_index("ISO_TIME")
    cutoffs = forecast_cutoffs(track, require_lead_hours=min(HORIZONS_HOURS))
    leakage_checks = 0
    rows: list[dict[str, object]] = []
    for cutoff in cutoffs:
        # Belt and braces: the forecaster also truncates internally.
        visible = raw_track[pd.to_datetime(raw_track["ISO_TIME"]).le(cutoff)]
        for model in MODELS:
            forecast = forecast_track(visible, cutoff, model, wind_grid=wind_grid)
            if forecast.last_observation_time > cutoff:
                raise AssertionError(f"Observation leakage at cutoff {cutoff}")
            if forecast.wind_data_valid_until is not None and forecast.wind_data_valid_until > cutoff:
                raise AssertionError(f"Wind-data leakage at cutoff {cutoff}")
            # Supplying the full track must give an identical forecast.
            full = forecast_track(raw_track, cutoff, model, wind_grid=wind_grid)
            if not np.allclose(full.points[["lat", "lon"]], forecast.points[["lat", "lon"]]):
                raise AssertionError(f"Forecast changed when future data was present ({cutoff})")
            leakage_checks += 1
            for lead in HORIZONS_HOURS:
                valid = cutoff + pd.Timedelta(hours=lead)
                if valid not in fixes.index:
                    continue
                truth = fixes.loc[valid]
                predicted = forecast.at_lead(lead)
                d2 = mahalanobis_squared(forecast, lead, float(truth["LAT"]), float(truth["LON"]))
                rows.append({
                    "cutoff_time": cutoff.isoformat(),
                    "model": model,
                    "model_label": MODEL_LABELS[model],
                    "lead_hours": lead,
                    "valid_time": valid.isoformat(),
                    "observations_used": forecast.observations_used,
                    "last_observation_time": forecast.last_observation_time.isoformat(),
                    "wind_data_valid_until": (
                        forecast.wind_data_valid_until.isoformat()
                        if forecast.wind_data_valid_until is not None else None
                    ),
                    "predicted_lat": round(float(predicted["lat"]), 4),
                    "predicted_lon": round(float(predicted["lon"]), 4),
                    "observed_lat": float(truth["LAT"]),
                    "observed_lon": float(truth["LON"]),
                    "error_km": round(position_error_km(predicted, float(truth["LAT"]), float(truth["LON"])), 2),
                    "uncertainty_radius_km": round(float(predicted["uncertainty_radius_km"]), 2),
                    "inside_90pct_ellipse": bool(d2 <= CHI2_2DOF_90),
                })
    cases = pd.DataFrame(rows)

    summary: dict[str, dict[str, object]] = {}
    for model in MODELS:
        summary[model] = {"label": MODEL_LABELS[model]}
        for lead in HORIZONS_HOURS:
            subset = cases[cases["model"].eq(model) & cases["lead_hours"].eq(lead)]
            stats = _summarise(subset["error_km"])
            stats["inside_90pct_ellipse_pct"] = round(100.0 * float(subset["inside_90pct_ellipse"].mean()), 1)
            stats["mean_uncertainty_radius_km"] = round(float(subset["uncertainty_radius_km"].mean()), 1)
            summary[model][f"{lead}h"] = stats

    comparison: dict[str, object] = {}
    for lead in HORIZONS_HOURS:
        paired = cases[cases["lead_hours"].eq(lead)].pivot(
            index="cutoff_time", columns="model", values="error_km"
        ).dropna()
        difference = paired[MODEL_WIND] - paired[MODEL_KALMAN]
        comparison[f"{lead}h"] = {
            "paired_cases": int(len(paired)),
            "mean_error_difference_km_wind_minus_kalman": round(float(difference.mean()), 1),
            "median_error_difference_km_wind_minus_kalman": round(float(difference.median()), 1),
            "wind_better_cases": int(difference.lt(0).sum()),
            "kalman_better_cases": int(difference.gt(0).sum()),
            "verdict": (
                "wind-informed lower mean error" if difference.mean() < 0
                else "wind-informed higher mean error" if difference.mean() > 0
                else "no difference"
            ),
        }

    case_counts = {
        f"{lead}h": int(cases[cases["model"].eq(MODEL_KALMAN) & cases["lead_hours"].eq(lead)].shape[0])
        for lead in HORIZONS_HOURS
    }
    runtime = time.perf_counter() - started
    return {
        "label": FORECAST_LABEL,
        "disclaimer": DISCLAIMER,
        "scientific_notes": SCIENTIFIC_NOTES,
        "storm": f"{track['NAME'].iloc[0]} ({track['SID'].iloc[0]})",
        "track_source": "NOAA IBTrACS (original fixes only, IFLAG 'O')",
        "wind_source": wind_grid.metadata,
        "method": {
            "min_observations": MIN_OBSERVATIONS,
            "horizons_hours": list(HORIZONS_HOURS),
            "error_metric": "great-circle (haversine) distance, km",
            "uncertainty": "90% bivariate-normal ellipse from the propagated position covariance",
            "steering_weights": {f"{level}hPa": weight for level, weight in STEERING_WEIGHTS.items()},
            "steering_annulus_km": list(ANNULUS_RADII_KM),
            "steering_trailing_window_hours": TRAILING_WINDOW_HOURS,
            "parameters_tuned_on_michaung": False,
        },
        "validation": {
            "observation_rule": observation_check,
            "cutoffs_evaluated": len(cutoffs),
            "leakage_checks_passed": leakage_checks,
            "all_forecasts_used_only_data_at_or_before_cutoff": True,
            "models_evaluated_on_identical_cases": True,
        },
        "valid_forecast_cases": case_counts,
        "summary": summary,
        "comparison": comparison,
        "runtime_seconds": round(runtime, 3),
        "cases": rows,
    }


def print_table(result: dict[str, object]) -> None:
    summary = result["summary"]
    for metric in ("mean_km", "median_km", "rmse_km", "p90_km", "inside_90pct_ellipse_pct"):
        print(f"\n{metric}")
        print(f"{'':<28}" + "".join(f"{f'{lead}h':>10}" for lead in HORIZONS_HOURS))
        for model in MODELS:
            values = "".join(f"{summary[model][f'{lead}h'][metric]:>10}" for lead in HORIZONS_HOURS)
            print(f"{MODEL_LABELS[model]:<28}{values}")


def main() -> None:
    result = run_backtest()
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT_JSON.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, indent=2), encoding="utf-8")
    temporary.replace(OUTPUT_JSON)
    pd.DataFrame(result["cases"]).to_csv(OUTPUT_CSV, index=False)

    print(FORECAST_LABEL + " — historical backtest")
    print(DISCLAIMER)
    print(f"Storm: {result['storm']}")
    print(f"Wind source: {result['wind_source']['source']}")
    print(f"Valid forecast cases: {result['valid_forecast_cases']}")
    print(f"Leakage checks passed: {result['validation']['leakage_checks_passed']}")
    print_table(result)
    print("\nWind-informed vs Kalman (paired):")
    for lead, item in result["comparison"].items():
        print(
            f"  {lead}: mean diff {item['mean_error_difference_km_wind_minus_kalman']:+.1f} km, "
            f"wind better {item['wind_better_cases']}/{item['paired_cases']} — {item['verdict']}"
        )
    print(f"\nRuntime: {result['runtime_seconds']:.2f} s")
    print(f"Saved: {OUTPUT_JSON}, {OUTPUT_CSV}")
    print("SURGESIGHT_TRACK_BACKTEST_OK")


if __name__ == "__main__":
    main()
