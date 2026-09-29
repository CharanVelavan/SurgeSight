"""Generate a SurgeSight Experimental Track Forecast from a historical cutoff.

Experimental forecast — not an official meteorological forecast. IMD remains
authoritative.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.track_forecaster import (  # noqa: E402
    DEFAULT_DEMO_CUTOFF,
    DISCLAIMER,
    FORECAST_LABEL,
    INTENSITY_MODES,
    MODEL_KALMAN,
    MODEL_WIND,
    forecast_cutoffs,
    forecast_geojson,
    run_experimental_forecast,
)
from services.wind_provider import WindDataUnavailable, load_wind_grid  # noqa: E402


TRACK_FILE = Path("data/processed/michaung_track.csv")
OUTPUT_DIR = Path("data/processed")
BACKTEST_FILE = OUTPUT_DIR / "track_backtest.json"


def write_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cutoff", default=str(DEFAULT_DEMO_CUTOFF),
        help="Historical cutoff (UTC synoptic time, e.g. '2023-12-03 12:00').",
    )
    parser.add_argument("--intensity-mode", choices=INTENSITY_MODES, default="reference")
    args = parser.parse_args()

    track = pd.read_csv(TRACK_FILE)
    cutoff = pd.Timestamp(args.cutoff)
    valid_cutoffs = forecast_cutoffs(track)
    if cutoff not in valid_cutoffs:
        raise SystemExit(
            f"Cutoff {cutoff} is not a usable synoptic fix. Choose one of: "
            + ", ".join(time.strftime("%Y-%m-%d %H:%M") for time in valid_cutoffs)
        )
    try:
        wind_grid = load_wind_grid(track)
    except WindDataUnavailable as exc:
        print(f"WARNING: {exc}")
        wind_grid = None

    result = run_experimental_forecast(
        track, cutoff, wind_grid=wind_grid, intensity_mode=args.intensity_mode
    )
    summary = result["summary"]
    if BACKTEST_FILE.exists():
        backtest = json.loads(BACKTEST_FILE.read_text(encoding="utf-8"))
        summary["backtest_reference"] = {
            "valid_forecast_cases": backtest["valid_forecast_cases"],
            "summary": backtest["summary"],
            "comparison": backtest["comparison"],
        }
    outputs = {
        MODEL_KALMAN: OUTPUT_DIR / "experimental_track_kalman.geojson",
        MODEL_WIND: OUTPUT_DIR / "experimental_track_wind.geojson",
    }
    for model, forecast in result["forecasts"].items():
        write_json(outputs[model], forecast_geojson(forecast, track))
    write_json(OUTPUT_DIR / "experimental_track_summary.json", summary)

    print(FORECAST_LABEL)
    print(DISCLAIMER)
    print(f"Cutoff: {summary['cutoff_time']}  (fixes used: {summary['observations_used']})")
    for model, item in summary["models"].items():
        print(f"\n{item['label']}")
        for point in item["forecast"]:
            error = item["verification_error_km"].get(f"{point['lead_hours']}h")
            print(
                f"  +{point['lead_hours']:>2}h {point['timestamp']}  "
                f"{point['lat']:.2f}N {point['lon']:.2f}E  "
                f"90% radius {point['uncertainty_radius_km']:.0f} km  "
                f"error vs IBTrACS {error if error is not None else 'n/a'} km"
            )
    impact = summary.get("infrastructure_impact")
    if impact:
        print(f"\nInfrastructure impact ({impact['track_window']}; intensity: {impact['intensity_mode']})")
        for name, item in impact["tracks"].items():
            delta = item.get("delta_vs_reference", {})
            print(
                f"  {item['label']:<28} High+ {item['high_plus_assets']:>5} "
                f"Critical {item['critical_assets']:>3} Hospitals {item['high_plus_hospitals']:>4} "
                f"Substations {item['high_plus_substations']:>4}"
                + (f"  Δ {delta}" if delta else "")
            )
    print(f"\nRuntime: {summary['runtime_seconds']:.2f} s")
    print("Saved: " + ", ".join(str(path) for path in outputs.values())
          + f", {OUTPUT_DIR / 'experimental_track_summary.json'}")


if __name__ == "__main__":
    main()
