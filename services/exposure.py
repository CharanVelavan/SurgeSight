"""Exposed population and buildings inside a hazard footprint, per district (WP2.5).

Replaces the misleading "population in analysis region". The footprint is the union of the
neighbourhoods (default 5 km) of every asset that meets a rule (v2 class HIGH or above, triage
tier 1-2, or ensemble probability >= 0.5). Population and buildings come from the cached 0.05 degree
grid built by ``scripts/build_exposure_grid.py`` (WorldPop, Google Open Buildings v3, FAO GAUL 2025).

"Exposed" means inside the footprint. It is not a casualty or damage estimate.
"""

from __future__ import annotations

from functools import lru_cache
import json
from typing import Any

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union

from services.config import load_region
from services.hazards.coast import haversine_matrix_km

STEP = 0.05
DEFAULT_RADIUS_KM = 5.0
HIGH_CLASSES = ("HIGH", "CRITICAL")
RULES = ("class_high_plus", "triage_tier_1_2", "ensemble_p50")
LABEL = (
    "Exposed = people and buildings inside the footprint of assets meeting the rule. "
    "A hazard footprint, not a casualty or damage estimate."
)
SOURCES = "WorldPop 100 m (population), Google Open Buildings v3 (buildings, confidence >= 0.75), FAO GAUL 2025 (districts)"


@lru_cache(maxsize=None)
def load_grid(region_id: str | None = None) -> pd.DataFrame:
    path = load_region(region_id).path("exposure_grid")
    if not path.exists():
        raise FileNotFoundError(f"{path} missing; run scripts/build_exposure_grid.py")
    return pd.read_csv(path)


@lru_cache(maxsize=None)
def load_districts(region_id: str | None = None) -> list[tuple[Any, str, str]]:
    data = json.loads(load_region(region_id).path("districts").read_text(encoding="utf-8"))
    return [
        (shape(f["geometry"]), f["properties"]["district"], f["properties"]["state"])
        for f in data["features"]
    ]


def assign_districts(
    assets: pd.DataFrame, region_id: str | None = None, *, nearest_fallback: bool = True
) -> pd.DataFrame:
    """District and state of each asset by point-in-polygon (nearest polygon if none contains it)."""
    lon, lat = assets["lon"].to_numpy(float), assets["lat"].to_numpy(float)
    district = np.full(len(assets), None, dtype=object)
    state = np.full(len(assets), None, dtype=object)
    for geometry, name, st in load_districts(region_id):
        inside = shapely.contains_xy(geometry, lon, lat) & (district == None)  # noqa: E711
        district[inside], state[inside] = name, st
    missing = np.flatnonzero(district == None)  # noqa: E711
    if missing.size and nearest_fallback:
        points = shapely.points(lon[missing], lat[missing])
        polygons = load_districts(region_id)
        distances = np.vstack([shapely.distance(g, points) for g, _, _ in polygons])
        nearest = distances.argmin(axis=0)
        district[missing] = [polygons[i][1] for i in nearest]
        state[missing] = [polygons[i][2] for i in nearest]
    return pd.DataFrame({"district": district, "state": state}, index=assets.index)


def qualifying_mask(frame: pd.DataFrame, rule: str) -> np.ndarray:
    if rule == "class_high_plus":
        for column in ("class_v2", "scenario_risk_class", "risk_class"):
            if column in frame.columns:
                return frame[column].isin(HIGH_CLASSES).to_numpy()
        raise ValueError("Run has no risk class column for rule class_high_plus")
    if rule == "triage_tier_1_2":
        if "triage_tier" not in frame.columns:
            raise ValueError("Rule triage_tier_1_2 needs a risk_v2 run")
        return (frame["triage_tier"] <= 2).to_numpy()
    if rule == "ensemble_p50":
        if "p_high_plus" not in frame.columns:
            raise ValueError("Rule ensemble_p50 needs an ensemble run")
        return (frame["p_high_plus"] >= 0.5).to_numpy()
    raise ValueError(f"rule must be one of {RULES}")


def footprint_cells(
    assets: pd.DataFrame, qualifying: np.ndarray, grid: pd.DataFrame, radius_km: float = DEFAULT_RADIUS_KM
) -> np.ndarray:
    """Boolean per grid cell: is the cell centre within radius_km of any qualifying asset?"""
    inside = np.zeros(len(grid), dtype=bool)
    if not qualifying.any():
        return inside
    a_lat, a_lon = assets["lat"].to_numpy(float)[qualifying], assets["lon"].to_numpy(float)[qualifying]
    lat, lon = grid["lat"].to_numpy(float), grid["lon"].to_numpy(float)
    for start in range(0, len(grid), 400):
        block = slice(start, start + 400)
        inside[block] = (haversine_matrix_km(lat[block], lon[block], a_lat, a_lon) <= radius_km).any(axis=1)
    return inside


def footprint_geometry(grid: pd.DataFrame, cells: np.ndarray, simplify_deg: float = 0.01) -> dict[str, Any] | None:
    """GeoJSON polygon of the footprint (union of its grid cells), simplified for CAP / maps."""
    chosen = grid[cells]
    if chosen.empty:
        return None
    half = STEP / 2
    union = unary_union([box(r.lon - half, r.lat - half, r.lon + half, r.lat + half) for r in chosen.itertuples()])
    return mapping(union.simplify(simplify_deg))


def exposure_summary(
    frame: pd.DataFrame,
    *,
    rule: str = "class_high_plus",
    radius_km: float = DEFAULT_RADIUS_KM,
    region_id: str | None = None,
    include_footprint: bool = False,
) -> dict[str, Any]:
    """Exposed population and buildings, overall and per district, for a scored asset frame.

    ``frame`` needs ``lat``, ``lon`` and the columns required by the rule.
    """
    grid = load_grid(region_id)
    qualifying = qualifying_mask(frame, rule)
    cells = footprint_cells(frame, qualifying, grid, radius_km)
    exposed = grid[cells]
    districts = assign_districts(frame, region_id)
    by_district = []
    for name, group in exposed.groupby("district", dropna=False):
        label = name if isinstance(name, str) else "Outside district boundaries"
        in_district = (districts["district"] == name).to_numpy() & qualifying
        types = frame.loc[in_district, "asset_type"].value_counts().to_dict() if "asset_type" in frame else {}
        by_district.append({
            "district": label,
            "state": group["state"].dropna().iloc[0] if group["state"].notna().any() else None,
            "cells": int(len(group)),
            "population": int(round(group["population"].sum())),
            "buildings": int(group["buildings"].sum()),
            "qualifying_assets_by_type": {str(k): int(v) for k, v in types.items()},
        })
    by_district.sort(key=lambda d: d["population"], reverse=True)
    total_pop, total_buildings = grid["population"].sum(), grid["buildings"].sum()
    summary = {
        "rule": rule,
        "radius_km": radius_km,
        "qualifying_assets": int(qualifying.sum()),
        "footprint_cells": int(cells.sum()),
        "exposed_population": int(round(exposed["population"].sum())),
        "exposed_buildings": int(exposed["buildings"].sum()),
        "grid_population": int(round(total_pop)),
        "grid_buildings": int(total_buildings),
        "exposed_population_share_pct": round(float(exposed["population"].sum() / total_pop * 100), 1) if total_pop else 0.0,
        "by_district": by_district,
        "population_year": int(grid["worldpop_year"].iloc[0]) if "worldpop_year" in grid else None,
        "sources": SOURCES,
        "label": LABEL,
    }
    if include_footprint:
        summary["footprint_geojson"] = footprint_geometry(grid, cells)
    return summary
