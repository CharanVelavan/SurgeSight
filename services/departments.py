"""Department views (WP4.1): each department's asset types, weights, questions and ranked priority assets.

Ranking uses the v2 multi-hazard model over the core plus department-layer assets, restricted to the
department's asset types. Values are screening indices for prioritisation, not damage probabilities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import tomllib
from typing import Any

import pandas as pd

from services.assets import load_all_assets
from services.config import PROJECT_ROOT, load_region

DEPARTMENTS_FILE = PROJECT_ROOT / "config" / "departments.toml"
CLASS_ORDER = ("CRITICAL", "HIGH", "MODERATE", "LOW")


@dataclass(frozen=True)
class Department:
    id: str
    display_name: str
    short_name: str
    asset_types: tuple[str, ...]
    advisory_focus: str
    key_questions: tuple[str, ...] = ()
    default_channels: tuple[str, ...] = ()
    recipients: tuple[str, ...] = ()
    facility_quality: tuple[str, ...] = field(default=())


@lru_cache(maxsize=1)
def load_departments() -> dict[str, Department]:
    data = tomllib.loads(DEPARTMENTS_FILE.read_text(encoding="utf-8"))["departments"]
    return {
        key: Department(
            id=key, display_name=v["display_name"], short_name=v["short_name"], asset_types=tuple(v["asset_types"]),
            advisory_focus=v["advisory_focus"], key_questions=tuple(v.get("key_questions", ())),
            default_channels=tuple(v.get("default_channels", ())), recipients=tuple(v.get("recipients", ())),
            facility_quality=tuple(v.get("facility_quality", ())),
        )
        for key, v in data.items()
    }


def get_department(key_or_name: str) -> Department:
    """Look up by id, display name or short name (case-insensitive)."""
    wanted = key_or_name.strip().lower()
    for dept in load_departments().values():
        if wanted in {dept.id, dept.display_name.lower(), dept.short_name.lower()}:
            return dept
    raise KeyError(f"Unknown department '{key_or_name}'. Known: {sorted(load_departments())}")


def department_mask(dept: Department, frame: pd.DataFrame) -> pd.Series:
    mask = frame["asset_type"].isin(dept.asset_types)
    if dept.facility_quality and "facility_quality" in frame.columns:
        hospital = frame["asset_type"] == "hospital"
        mask &= ~hospital | frame["facility_quality"].isin(dept.facility_quality)
    return mask


@lru_cache(maxsize=1)
def _baseline_v2(region_id: str | None = None) -> pd.DataFrame:
    from services.risk_model_v2 import score_v2

    region = load_region(region_id)
    frame, _ = score_v2(pd.read_csv(region.path("track")), load_all_assets(region_id), region_id=region_id)
    return frame


def score_all_assets(track: pd.DataFrame | None = None, region_id: str | None = None) -> pd.DataFrame:
    """v2-scored frame for core plus department-layer assets (the Michaung reference track unless one is given)."""
    if track is None:
        return _baseline_v2(region_id).copy()
    from services.risk_model_v2 import score_v2

    frame, _ = score_v2(track, load_all_assets(region_id), region_id=region_id)
    return frame


def department_priority(dept_id: str, *, n: int = 15, frame: pd.DataFrame | None = None) -> dict[str, Any]:
    """Class counts and the top ``n`` assets by v2 score for one department."""
    dept = get_department(dept_id)
    frame = score_all_assets() if frame is None else frame
    mine = frame[department_mask(dept, frame)]
    top_cols = ["name", "asset_type", "osm_element", "osm_id", "class_v2", "combined_v2", "dominant_hazard",
                "wind_kmh_v2", "surge_m", "rain_mm", "triage_tier"]
    ranked = mine.sort_values("combined_v2", ascending=False)
    if dept.facility_quality and "facility_quality" in ranked.columns:  # real hospitals ahead of clinics
        ranked = ranked.assign(_q=(ranked["facility_quality"] != "hospital").astype(int)).sort_values(["_q", "combined_v2"], ascending=[True, False]).drop(columns="_q")
    top = ranked[[c for c in top_cols if c in ranked.columns]].head(n)
    return {
        "department": dept.display_name, "department_id": dept.id, "asset_types": list(dept.asset_types),
        "advisory_focus": dept.advisory_focus,
        "assets": int(len(mine)),
        "class_counts": {c: int((mine["class_v2"] == c).sum()) for c in CLASS_ORDER},
        "high_or_critical": int(mine["class_v2"].isin(["HIGH", "CRITICAL"]).sum()),
        "triage_tier_1": int((mine["triage_tier"] == 1).sum()) if "triage_tier" in mine else None,
        "dominant_hazard_counts": {str(k): int(v) for k, v in mine["dominant_hazard"].value_counts().items()},
        "top_assets": top.round(3).to_dict(orient="records"),
    }
