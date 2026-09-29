"""River flood susceptibility layer (WP2.7), built from MERIT Hydro in Earth Engine.

A static terrain-and-network screening (a stand-in while the Google Flood Forecasting API is unavailable). It is a static terrain-and-network
screening, not a river-level forecast: it says which assets sit low beside a drainage line, and
combined with forecast rain it says where heavy rain is most likely to become river flooding.

Height above nearest drainage (HAND, MERIT Hydro ``hnd``) is 0 m on the channel and grows uphill.
``susceptibility = exp(-HAND / 5 m)``: 1 on the channel, about 0.37 at 5 m, about 0.02 at 20 m.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from services.config import load_region
from services.hazards.rainfall import rain_score

MERIT_ID = "MERIT/Hydro/v1_0_1"
MERIT_SCALE_M = 90
HAND_SCALE_M = 5.0
LABEL = (
    "River flood susceptibility from MERIT Hydro (height above nearest drainage, upstream area) analysed in "
    "Google Earth Engine, combined with GFS forecast rain. A screening index for flood-prone locations, not a "
    "river-level forecast or a probability."
)


def susceptibility(hand_m: np.ndarray | float) -> np.ndarray:
    return np.exp(-np.clip(np.asarray(hand_m, float), 0.0, None) / HAND_SCALE_M)


def river_flood_index(rain_mm: np.ndarray | float, hand_m: np.ndarray | float) -> np.ndarray:
    """Heavy rain on land close to a drainage line: rain score x susceptibility (0 to 1)."""
    return rain_score(rain_mm) * susceptibility(hand_m)


def sample_merit(assets: pd.DataFrame) -> pd.DataFrame:
    """Sample MERIT Hydro at asset locations. Needs Earth Engine."""
    import ee

    from services.earth_engine import init_ee, sample_points

    init_ee()
    image = ee.Image(MERIT_ID).select(["hnd", "upa"])
    samples = pd.DataFrame(sample_points(image, list(zip(assets["lat"], assets["lon"])), MERIT_SCALE_M))
    out = assets[["osm_element", "osm_id"]].reset_index(drop=True)
    out["hand_m"] = samples["hnd"].round(2)
    out["upstream_km2"] = samples["upa"].round(2)
    out["river_susceptibility"] = np.round(susceptibility(out["hand_m"].fillna(HAND_SCALE_M * 6)), 4)
    return out


def load_river_table(region_id: str | None = None) -> pd.DataFrame:
    path = load_region(region_id).path("river_assets")
    if not path.exists():
        raise FileNotFoundError(f"{path} missing; run scripts/build_river_flood.py")
    return pd.read_csv(path)


def river_flood_frame(rain: pd.DataFrame, assets: pd.DataFrame, region_id: str | None = None) -> pd.DataFrame:
    """Per-asset river flood index for the given rain table (columns osm_element, osm_id, accum_mm)."""
    river = load_river_table(region_id)
    keyed = assets[["osm_element", "osm_id", "asset_type", "name", "lat", "lon"]].reset_index(drop=True)
    for col in ("asset_type", "name"):
        if col not in keyed:
            keyed[col] = None
    merged = keyed.merge(river, on=["osm_element", "osm_id"], how="left").merge(
        rain[["osm_element", "osm_id", "accum_mm"]], on=["osm_element", "osm_id"], how="left"
    )
    merged["rain_mm"] = merged["accum_mm"].fillna(0.0).round(1)
    merged["river_flood_index"] = np.round(river_flood_index(merged["rain_mm"], merged["hand_m"].fillna(HAND_SCALE_M * 6)), 4)
    return merged.drop(columns=["accum_mm"])


def summarise(frame: pd.DataFrame) -> dict[str, Any]:
    high = frame["river_flood_index"] >= 0.5
    return {
        "assets": int(len(frame)),
        "near_drainage_hand_lt_2m": int((frame["hand_m"] < 2).sum()),
        "index_at_least_0_5": int(high.sum()),
        "by_asset_type_index_at_least_0_5": {str(k): int(v) for k, v in frame[high].groupby("asset_type").size().items()},
        "label": LABEL,
    }
