"""Risk model v2 (WP2.4): Holland wind field + screening surge + rainfall-on-terrain.

    wind_v2       = clip(V(r) / 120 km/h, 0, 1)                 (Holland 1980 profile, max over the track)
    combined_v2   = 1 - (1 - 0.8*wind_v2)(1 - 0.9*surge)(1 - 0.8*rain_flood)
    rain_flood    = clip(rain_mm / 300, 0, 1) * (0.5 + 0.5*terrain_flood_score)
    dominant      = the largest of the three weighted terms

v1 (services/risk_model.py) is frozen and stays the baseline; the UI shows both. Scores are
screening indices for prioritisation, not damage probabilities. Rainfall is always a forecast
input; observed IMERG needs ``hindcast=True`` (§4.6).

Calibration finding (Michaung, 2026-09-29): with these constants nearly every corridor asset is
HIGH or CRITICAL, because the whole corridor received IMD "very heavy" to "extremely heavy" rain
(true also for observed IMERG). Absolute classes therefore do not discriminate here; use
``v2_percentile`` / ``triage_tier`` (relative rank) and the per-hazard breakdown. Recalibrate
against Sentinel-1 flood extent in WP3 rather than tuning to a target distribution.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from services.hazards.rainfall import FutureRainfallAccessError, rain_flood_score, rain_inputs, rain_score
from services.hazards.surge import LABEL as SURGE_LABEL
from services.hazards.surge import surge_scores
from services.hazards.wind_field import max_wind_kmh

MODEL_VERSION = "v2.0"
REFERENCE_WIND_KMH = 120.0
HAZARD_WEIGHTS = {"wind": 0.8, "surge": 0.9, "rain_flood": 0.8}
CLASS_THRESHOLDS = (0.25, 0.50, 0.75)  # same as v1: LOW / MODERATE / HIGH / CRITICAL
HAZARD_NAMES = ("wind", "surge", "rain_flood")
TIER_CUTS = (90.0, 70.0, 40.0)  # percentile cut-offs for triage tiers 1 (highest), 2, 3; the rest are tier 4
CLASS_ORDER = ["LOW", "MODERATE", "HIGH", "CRITICAL"]


def classify_v2(score: np.ndarray) -> np.ndarray:
    return np.select(
        [score < CLASS_THRESHOLDS[0], score < CLASS_THRESHOLDS[1], score < CLASS_THRESHOLDS[2]],
        CLASS_ORDER[:3], default=CLASS_ORDER[3],
    )


def score_v2(
    track: pd.DataFrame,
    assets: pd.DataFrame,
    *,
    rain_mode: str = "forecast",
    hindcast: bool = False,
    rain: pd.DataFrame | None = None,
    region_id: str | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Score assets under ``track`` with v2. ``assets`` needs the v1 baseline columns.

    ``rain`` may supply custom ``osm_element, osm_id, accum_mm`` values; otherwise the cached
    forecast (or, for hindcast only, observed) table is used.
    """
    if rain is None:
        rain, rain_meta = rain_inputs(rain_mode, hindcast=hindcast, region_id=region_id)
    else:
        rain_meta = {"mode": "custom", "validation_only": False}
    keyed = assets.reset_index(drop=True)
    merged = keyed[["osm_element", "osm_id"]].merge(
        rain[["osm_element", "osm_id", "accum_mm"]], on=["osm_element", "osm_id"], how="left"
    )
    rain_missing = int(merged["accum_mm"].isna().sum())
    rain_mm = merged["accum_mm"].fillna(0.0).to_numpy()

    wind_kmh = max_wind_kmh(track, keyed["lat"].to_numpy(), keyed["lon"].to_numpy())
    wind = np.clip(wind_kmh / REFERENCE_WIND_KMH, 0.0, 1.0)
    surge_frame, surge_info = surge_scores(track, keyed, region_id)
    surge = surge_frame["surge_score"].to_numpy()
    terrain = keyed["terrain_flood_score"].to_numpy(float)
    rain_flood = rain_flood_score(rain_mm, terrain)

    terms = np.vstack([
        HAZARD_WEIGHTS["wind"] * wind, HAZARD_WEIGHTS["surge"] * surge, HAZARD_WEIGHTS["rain_flood"] * rain_flood,
    ])
    combined = 1.0 - np.prod(1.0 - terms, axis=0)
    dominant = np.where(terms.max(axis=0) <= 0, "none", np.array(HAZARD_NAMES)[terms.argmax(axis=0)])

    out = keyed[[c for c in (
        "name", "asset_type", "osm_element", "osm_id", "lat", "lon", "facility_quality", "elevation_m",
        "risk_class", "combined_risk_score",
    ) if c in keyed.columns]].rename(columns={"risk_class": "v1_class", "combined_risk_score": "v1_score"})
    out["wind_kmh_v2"] = np.round(wind_kmh, 1)
    out["wind_v2"] = np.round(wind, 4)
    out["surge_m"] = surge_frame["surge_m"].to_numpy()
    out["surge_score"] = np.round(surge, 4)
    out["rain_mm"] = np.round(rain_mm, 1)
    out["rain_score"] = np.round(rain_score(rain_mm), 4)
    out["rain_flood_score"] = np.round(rain_flood, 4)
    out["terrain_flood_score"] = np.round(terrain, 4)
    out["combined_v2"] = np.round(combined, 4)
    out["class_v2"] = classify_v2(combined)
    out["dominant_hazard"] = dominant
    out["class_changed_vs_v1"] = out["class_v2"] != out["v1_class"]
    # Relative triage inside this event: absolute classes saturate when a whole corridor is hit hard.
    out["v2_percentile"] = np.round(out["combined_v2"].rank(pct=True) * 100, 1)
    out["triage_tier"] = np.select(
        [out["v2_percentile"] >= TIER_CUTS[0], out["v2_percentile"] >= TIER_CUTS[1], out["v2_percentile"] >= TIER_CUTS[2]],
        [1, 2, 3], default=4,
    )

    meta = {
        "model_version": MODEL_VERSION,
        "computed_at_utc": datetime.now(timezone.utc).isoformat(),
        "hazard_weights": HAZARD_WEIGHTS,
        "reference_wind_kmh": REFERENCE_WIND_KMH,
        "rain": {**rain_meta, "assets_without_rain_value": rain_missing},
        "surge": {k: v for k, v in surge_info.items() if k != "constants"},
        "surge_label": SURGE_LABEL,
        "label": "Screening index, not a damage probability.",
    }
    return out, meta


def class_distribution(frame: pd.DataFrame, column: str) -> dict[str, int]:
    counts = frame[column].value_counts()
    return {name: int(counts.get(name, 0)) for name in CLASS_ORDER}


__all__ = ["score_v2", "class_distribution", "classify_v2", "MODEL_VERSION", "FutureRainfallAccessError"]
