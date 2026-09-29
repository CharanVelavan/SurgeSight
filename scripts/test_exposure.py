"""Exposure grid, district assignment and footprint arithmetic."""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.exposure import (
    assign_districts, exposure_summary, footprint_cells, footprint_geometry, load_districts, load_grid, qualifying_mask,
)
from services.risk_model_v2 import score_v2

TRACK = pd.read_csv(PROJECT_ROOT / "data/processed/michaung_track.csv")
ASSETS = pd.read_csv(PROJECT_ROOT / "data/processed/scored_assets.csv")


def main() -> None:
    grid = load_grid()
    assert (grid["population"] >= 0).all() and (grid["buildings"] >= 0).all()
    assert 20e6 < grid["population"].sum() < 40e6, grid["population"].sum()
    assert 3e6 < grid["buildings"].sum() < 20e6, grid["buildings"].sum()
    names = {name for _, name, _ in load_districts()}
    assert {"Chennai", "Tiruvallur", "Potti Sriramulu Nellore"} <= names, names

    districts = assign_districts(ASSETS)
    assert districts["district"].notna().all()
    chennai_hospital = ASSETS[ASSETS["name"].fillna("").str.contains("Chennai")].head(1)
    assert districts.loc[chennai_hospital.index[0], "district"] in {"Chennai", "Chengalpattu", "Tiruvallur", "Kanchipuram"}

    v2, _ = score_v2(TRACK, ASSETS)
    everything = exposure_summary(v2, rule="class_high_plus")
    tier12 = exposure_summary(v2, rule="triage_tier_1_2")
    wide = exposure_summary(v2, rule="class_high_plus", radius_km=15)
    narrow = exposure_summary(v2, rule="class_high_plus", radius_km=2)

    assert everything["exposed_population"] == sum(d["population"] for d in everything["by_district"])
    assert everything["exposed_buildings"] == sum(d["buildings"] for d in everything["by_district"])
    assert tier12["exposed_population"] < everything["exposed_population"], "a stricter rule exposes fewer people"
    assert narrow["exposed_population"] <= everything["exposed_population"] <= wide["exposed_population"]
    assert wide["exposed_population"] <= wide["grid_population"]
    assert everything["by_district"] == sorted(everything["by_district"], key=lambda d: d["population"], reverse=True)

    none = v2.copy()
    none["class_v2"] = "LOW"
    zero = exposure_summary(none, rule="class_high_plus")
    assert zero["exposed_population"] == 0 and zero["exposed_buildings"] == 0 and zero["by_district"] == []

    mask = qualifying_mask(v2, "class_high_plus")
    cells = footprint_cells(v2, mask, grid, 5.0)
    geometry = footprint_geometry(grid, cells)
    assert geometry is not None and geometry["type"] in {"Polygon", "MultiPolygon"}
    try:
        exposure_summary(v2, rule="ensemble_p50")
    except ValueError:
        pass
    else:
        raise AssertionError("ensemble rule needs an ensemble run")
    print(f"HIGH+ footprint: {everything['exposed_population']:,} people, {everything['exposed_buildings']:,} buildings "
          f"({everything['exposed_population_share_pct']}% of grid); top districts: "
          f"{[(d['district'], d['population']) for d in everything['by_district'][:3]]}")
    print("SURGESIGHT_EXPOSURE_OK")


if __name__ == "__main__":
    main()
