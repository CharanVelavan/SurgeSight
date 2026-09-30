"""Offline, deterministic tests for road sectioning, scoring, access and route exposure."""

from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path
import sys
import json

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import roads


def test_split_ways() -> None:
    # Way 1 crosses the 1 km threshold; way 2 shares its middle vertex, which must also be a split point.
    a = roads.Way(1, "primary", "A", None, np.array([[80.0, 13.0], [80.006, 13.0], [80.012, 13.0], [80.018, 13.0]]))
    b = roads.Way(2, "secondary", "B", None, np.array([[80.012, 12.995], [80.012, 13.0], [80.012, 13.005]]))
    out = roads.split_ways([a, b], max_km=1.0)
    first = out[out["way_id"] == 1]
    assert len(first) == 2, first[["section_id", "length_km"]].to_dict("records")
    junction = (80.012, 13.0)
    assert sum(junction in (row.a, row.b) for row in out.itertuples()) >= 4


def test_score_sections() -> None:
    base = {"hand_min_m": 0.0, "elevation_min_m": 0.0, "water_max_pct": 0.0, "surge_score": 0.0,
            "wind_kmh": 0.0, "length_km": 1.0}
    scored = roads.score_sections(pd.DataFrame([dict(base, rain_mm=mm) for mm in range(0, 300, 15)]))
    assert scored["flood_level"].value_counts().sort_index().to_dict() == {0: 10, 1: 6, 2: 3, 3: 1}
    tied = roads.score_sections(pd.DataFrame([dict(base, rain_mm=150.0, section_id=f"tie:{i:02d}") for i in range(20)]))
    assert tied["flood_level"].value_counts().sort_index().to_dict() == {0: 10, 1: 6, 2: 3, 3: 1}
    wind_base = dict(base, hand_min_m=30.0, elevation_min_m=30.0)
    wind = roads.score_sections(pd.DataFrame([dict(wind_base, rain_mm=0.0, wind_kmh=v) for v in (61.9, 62.0, 89.0, 118.0)]))
    assert wind["wind_level"].tolist() == [0, 1, 2, 3]
    assert wind["level"].tolist() == [0, 1, 2, 3]


def test_access() -> None:
    a, b, c, d, e, f = (80.0, 13.0), (80.01, 13.0), (80.02, 13.0), (80.03, 13.0), (80.1, 13.0), (80.11, 13.0)
    sections = pd.DataFrame([
        {"a": a, "b": b, "length_km": 1.0, "level": 3},       # closing this isolates facility A
        {"a": b, "b": d, "length_km": 5.0, "level": 3},       # short bridge closes
        {"a": b, "b": c, "length_km": 20.0, "level": 0},      # longer remaining route
        {"a": c, "b": d, "length_km": 20.0, "level": 0},
        {"a": e, "b": f, "length_km": 30.0, "level": 0},       # never connected to a hospital
    ])
    facilities = pd.DataFrame([
        {"osm_element": "node", "osm_id": 1, "lat": a[1], "lon": a[0]},
        {"osm_element": "node", "osm_id": 2, "lat": b[1], "lon": b[0]},
        {"osm_element": "node", "osm_id": 3, "lat": d[1], "lon": d[0]},
        {"osm_element": "node", "osm_id": 4, "lat": e[1], "lon": e[0]},
    ])
    out = roads.access(sections, facilities, pd.Series([False, False, True, False]))
    assert out.loc[0, "road_access"] == "cut_off"
    assert out.loc[0, "hospital_km_before"] is not None and pd.isna(out.loc[0, "hospital_km_after"])
    assert out.loc[1, "road_access"] == "at_risk"
    assert out.loc[1, "hospital_km_after"] > out.loc[1, "hospital_km_before"]
    assert out.loc[3, "road_access"] == "open" and pd.isna(out.loc[3, "hospital_km_before"])


def test_highway_class() -> None:
    assert roads.highway_class("primary_link") == "primary"
    assert roads.highway_class("tertiary") == "tertiary"
    assert roads.highway_class("residential") is None


def test_route_exposure_without_layer() -> None:
    import services.config

    original = services.config.load_region
    roads._risky_sections.cache_clear()
    try:
        services.config.load_region = lambda _region=None: SimpleNamespace(paths={})
        assert roads.route_exposure([(13.0, 80.0), (13.01, 80.01)], "missing") is None
    finally:
        services.config.load_region = original
        roads._risky_sections.cache_clear()


def test_built_summary() -> None:
    path = ROOT / "data/processed/roads/roads_summary.json"
    if not path.exists():
        return
    summary = json.loads(path.read_text())
    share = summary["km_by_level"].get("most_exposed", summary["km_by_level"].get("likely_impassable", 0)) / summary["km_total"]
    assert share <= 0.25, f"most-exposed road share is {share:.1%}"


if __name__ == "__main__":
    test_split_ways()
    test_score_sections()
    test_access()
    test_highway_class()
    test_route_exposure_without_layer()
    test_built_summary()
    print("SURGESIGHT_ROADS_OK")
