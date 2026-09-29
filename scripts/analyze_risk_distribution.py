"""Describe SurgeSight's deterministic risk-score distribution.

This script is diagnostic only. It does not alter model weights or scores.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


INPUT_FILE = Path("data/processed/scored_assets.csv")
OUTPUT_FILE = Path("data/processed/risk_diagnostics.json")
FIELDS = [
    "combined_risk_score",
    "wind_score",
    "terrain_flood_score",
    "distance_to_track_km",
    "elevation_m",
    "water_occurrence_pct",
]
PERCENTILES = {
    "p10": 0.10,
    "p25": 0.25,
    "p50": 0.50,
    "p75": 0.75,
    "p90": 0.90,
    "p95": 0.95,
    "p99": 0.99,
}


def field_statistics(series: pd.Series) -> dict[str, int | float | None]:
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return {
            "count": 0,
            "mean": None,
            "min": None,
            "max": None,
            **{name: None for name in PERCENTILES},
        }
    return {
        "count": int(numeric.count()),
        "mean": float(numeric.mean()),
        "min": float(numeric.min()),
        "max": float(numeric.max()),
        **{name: float(numeric.quantile(value)) for name, value in PERCENTILES.items()},
    }


def atomic_json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Missing scored assets: {INPUT_FILE}")
    assets = pd.read_csv(INPUT_FILE)
    missing = set(FIELDS + ["risk_class", "asset_type"]) - set(assets.columns)
    if missing:
        raise ValueError(f"Scored assets missing columns: {sorted(missing)}")

    statistics = {field: field_statistics(assets[field]) for field in FIELDS}
    risk_counts = {
        str(key): int(value)
        for key, value in assets["risk_class"].value_counts(dropna=False).items()
    }
    cross_counts = (
        assets.groupby(["asset_type", "risk_class"], dropna=False)
        .size()
        .rename("count")
        .reset_index()
    )
    by_asset_and_risk = [
        {
            "asset_type": str(row.asset_type),
            "risk_class": str(row.risk_class),
            "count": int(row.count),
        }
        for row in cross_counts.itertuples(index=False)
    ]
    output = {
        "source": str(INPUT_FILE),
        "asset_count": int(len(assets)),
        "statistics": statistics,
        "risk_class_counts": risk_counts,
        "counts_by_asset_type_and_risk_class": by_asset_and_risk,
        "note": "Diagnostics only; model weights and deterministic scores are unchanged.",
    }
    atomic_json_write(OUTPUT_FILE, output)

    print("SURGESIGHT RISK DISTRIBUTION DIAGNOSTICS")
    for field, values in statistics.items():
        print(f"\n{field}")
        for name in ("count", "mean", "min", "max", *PERCENTILES):
            value = values[name]
            display = f"{value:.6f}" if isinstance(value, float) else value
            print(f"  {name}: {display}")
    print("\nRisk-class counts")
    for risk_class, count in risk_counts.items():
        print(f"  {risk_class}: {count}")
    print("\nCounts by asset type + risk class")
    for row in by_asset_and_risk:
        print(f"  {row['asset_type']} / {row['risk_class']}: {row['count']}")
    print(f"\nSaved: {OUTPUT_FILE}")
    print("SURGESIGHT_RISK_DIAGNOSTICS_OK")


if __name__ == "__main__":
    main()
