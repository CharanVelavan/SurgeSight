"""Asset tables: the core corridor assets (hospitals, shelters, schools, substations) plus the department layers (WP4.2).

The core table is frozen (the v1 baseline and its tests depend on it). The extra table holds fire, police, water and
harbour assets scored with the same v1 method, and shares the per-asset hazard caches (rainfall, coast, river).
"""

from __future__ import annotations

import pandas as pd

from services.config import load_region


def load_core_assets(region_id: str | None = None) -> pd.DataFrame:
    return pd.read_csv(load_region(region_id).path("scored_assets"))


def load_extra_assets(region_id: str | None = None) -> pd.DataFrame:
    path = load_region(region_id).path("scored_assets_extra")
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def load_all_assets(region_id: str | None = None) -> pd.DataFrame:
    """Core plus department-layer assets, one row per OSM object."""
    core, extra = load_core_assets(region_id), load_extra_assets(region_id)
    if extra.empty:
        return core
    combined = pd.concat([core, extra], ignore_index=True)
    return combined.drop_duplicates(subset=["osm_element", "osm_id"], keep="first").reset_index(drop=True)
