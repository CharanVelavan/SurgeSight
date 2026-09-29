"""Probabilistic exposure: score many perturbed tracks and rank assets by chance of HIGH+ (WP2.1).

Each member is a rigid geodesic shift ``(dn, de) ~ N(center, sigma)`` of the reference track plus an
intensity change ``~ N(center, sigma_intensity)``, scored with the unchanged v1 engine. Assets are
ranked by ``priority = p_high_plus x criticality_weight(asset_type)``.

Honest labelling: this is a scenario ensemble built from measured track-forecast error, not a
numerical-weather-prediction ensemble; probabilities are of the screening class, not of damage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import math
import time
import tomllib
from typing import Any

import numpy as np
import pandas as pd

from services.config import PROJECT_ROOT, load_region
from services.risk_model import attach_nearest_track, score_assets_from_terrain
from services.scenario_engine import load_scenario_inputs, shift_track_unbounded

MODEL_VERSION = "ensemble-v1(risk_model=v1)"
HIGH_CLASSES = ("HIGH", "CRITICAL")
FALLBACK_RMSE_KM = 51.5  # Kalman 12 h RMSE from the Michaung backtest, used only if the file is missing
DEFAULT_LEAD_HOURS = 12
DEPARTMENTS_FILE = PROJECT_ROOT / "config" / "departments.toml"
TOP_N = 15
CALIBRATION_NOTE = "calibrated in-sample on one storm (Michaung 2023); not validated out of sample"


def criticality_weights() -> dict[str, float]:
    data = tomllib.loads(DEPARTMENTS_FILE.read_text(encoding="utf-8"))
    return {k: float(v) for k, v in data["criticality_weights"].items()}


def _backtest() -> dict[str, Any] | None:
    path = load_region().path("track_backtest")
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def default_sigma_km(lead_hours: int = DEFAULT_LEAD_HOURS) -> float:
    """Per-axis (north or east) 1-sigma track error, from the Kalman backtest RMSE at a lead time.

    The backtest RMSE is a radial error, ``rmse = sqrt(sigma_n^2 + sigma_e^2)``, so per axis
    ``sigma = rmse / sqrt(2)``.
    """
    backtest = _backtest()
    rmse = FALLBACK_RMSE_KM
    if backtest:
        rmse = backtest["summary"]["position_only_kalman"][f"{lead_hours}h"]["rmse_km"]
    return round(float(rmse) / math.sqrt(2), 2)


def calibrated_ellipse_scale(coverage: float = 0.9) -> dict[str, Any]:
    """Scale factor for the experimental forecast's 90% ellipse so observed coverage ~ nominal (K9).

    ``scale_h = quantile(error_km / uncertainty_radius_km, coverage)`` over the backtest cases at each
    lead. A scale below 1 means the nominal ellipse is wider than the observed errors need.
    """
    backtest = _backtest()
    if not backtest:
        return {"available": False}
    cases = pd.DataFrame(backtest["cases"])
    cases = cases[cases["model"] == "position_only_kalman"]
    ratio = cases["error_km"] / cases["uncertainty_radius_km"]
    scales = {
        f"{lead}h": round(float(ratio[cases["lead_hours"] == lead].quantile(coverage)), 3)
        for lead in sorted(cases["lead_hours"].unique())
    }
    return {
        "available": True,
        "nominal_coverage": coverage,
        "observed_coverage_pct_uncalibrated": round(float(cases["inside_90pct_ellipse"].mean()) * 100, 1),
        "ellipse_scale_by_lead": scales,
        "note": CALIBRATION_NOTE,
    }


@dataclass
class EnsembleResult:
    assets: pd.DataFrame
    parameters: dict[str, Any]
    summary: dict[str, Any]
    spaghetti_geojson: dict[str, Any]
    top_by_type: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


def _score_member(baseline: pd.DataFrame, track: pd.DataFrame) -> pd.DataFrame:
    """The same two calls compare_scenario makes, minus the per-row status labelling."""
    result = attach_nearest_track(baseline.copy(), track, filter_to_corridor=False)
    return score_assets_from_terrain(result)


def _line(track: pd.DataFrame) -> list[list[float]]:
    return [[round(float(lon), 4), round(float(lat), 4)] for lat, lon in zip(track["LAT"], track["LON"])]


def run_ensemble(
    members: int = 100,
    seed: int = 42,
    center_shift_n_km: float = 0.0,
    center_shift_e_km: float = 0.0,
    center_intensity_pct: float = 0.0,
    sigma_km: float | None = None,
    sigma_intensity_pct: float = 8.0,
    *,
    lead_hours: int = DEFAULT_LEAD_HOURS,
    top_n: int = TOP_N,
    spaghetti_members: int = 20,
) -> EnsembleResult:
    if not 2 <= members <= 1000:
        raise ValueError("members must be between 2 and 1000")
    started = time.perf_counter()
    sigma_source = "argument"
    if sigma_km is None:
        sigma_km, sigma_source = default_sigma_km(lead_hours), f"kalman_backtest_rmse_{lead_hours}h/sqrt(2)"
    track, baseline = load_scenario_inputs()
    weights = criticality_weights()

    rng = np.random.default_rng(seed)
    d_north = rng.normal(center_shift_n_km, sigma_km, members)
    d_east = rng.normal(center_shift_e_km, sigma_km, members)
    d_intensity = rng.normal(center_intensity_pct, sigma_intensity_pct, members)

    scores = np.empty((members, len(baseline)), dtype=np.float32)
    high = np.zeros((members, len(baseline)), dtype=bool)
    critical = np.zeros((members, len(baseline)), dtype=bool)
    lines = []
    for i in range(members):
        member_track = shift_track_unbounded(track, d_north[i], d_east[i], d_intensity[i])
        scored = _score_member(baseline, member_track)
        scores[i] = scored["combined_risk_score"].to_numpy(dtype=np.float32)
        classes = scored["risk_class"].to_numpy()
        high[i] = np.isin(classes, HIGH_CLASSES)
        critical[i] = classes == "CRITICAL"
        if i < spaghetti_members:
            lines.append((i, member_track))

    keep = [c for c in (
        "name", "asset_type", "osm_element", "osm_id", "lat", "lon", "facility_quality",
        "risk_class", "combined_risk_score",
    ) if c in baseline.columns]
    assets = baseline[keep].rename(
        columns={"risk_class": "baseline_risk_class", "combined_risk_score": "baseline_risk_score"}
    ).copy()
    assets["members_high_plus"] = high.sum(axis=0).astype(int)
    assets["p_high_plus"] = high.mean(axis=0).round(4)
    assets["p_critical"] = critical.mean(axis=0).round(4)
    scores64 = scores.astype(np.float64)
    assets["score_mean"] = scores64.mean(axis=0).round(3)
    assets["score_p10"] = np.percentile(scores64, 10, axis=0).round(3)
    assets["score_p90"] = np.percentile(scores64, 90, axis=0).round(3)
    assets["criticality_weight"] = assets["asset_type"].map(weights).fillna(weights.get("default", 0.5))
    assets["priority"] = (assets["p_high_plus"] * assets["criticality_weight"]).round(4)
    assets["high_in_text"] = (
        "HIGH or worse in " + assets["members_high_plus"].astype(str) + f"/{members} members"
    )

    ranking = assets
    if "facility_quality" in assets.columns:  # real hospitals only in the ranked hospital list
        ranking = assets[assets["facility_quality"].isin(["hospital", "not_applicable"])]
    top_by_type = {}
    for asset_type, group in ranking.groupby("asset_type"):
        best = group.sort_values(["priority", "score_mean"], ascending=False).head(top_n)
        top_by_type[str(asset_type)] = [
            {
                "name": r["name"], "osm_element": r["osm_element"], "osm_id": int(r["osm_id"]),
                "p_high_plus": float(r["p_high_plus"]), "p_critical": float(r["p_critical"]),
                "score_mean": float(r["score_mean"]), "priority": float(r["priority"]),
                "high_in_text": r["high_in_text"],
            }
            for _, r in best.iterrows()
        ]

    features = [
        {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": _line(track)},
            "properties": {"role": "reference_center", "member": None},
        }
    ]
    for i, member_track in lines:
        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": _line(member_track)},
            "properties": {
                "role": "member", "member": i, "north_shift_km": round(float(d_north[i]), 1),
                "east_shift_km": round(float(d_east[i]), 1), "intensity_pct": round(float(d_intensity[i]), 1),
            },
        })

    runtime = round(time.perf_counter() - started, 3)
    parameters = {
        "members": members, "seed": seed,
        "center_shift_n_km": center_shift_n_km, "center_shift_e_km": center_shift_e_km,
        "center_intensity_pct": center_intensity_pct,
        "sigma_km_per_axis": sigma_km, "sigma_source": sigma_source,
        "sigma_intensity_pct": sigma_intensity_pct, "lead_hours": lead_hours,
        "model_version": MODEL_VERSION, "computed_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    counts = {}
    for asset_type, group in assets.groupby("asset_type"):
        counts[str(asset_type)] = {
            "assets": int(len(group)),
            "expected_high_plus": round(float(group["p_high_plus"].sum()), 1),
            "assets_high_plus_in_majority_of_members": int((group["p_high_plus"] >= 0.5).sum()),
            "assets_high_plus_in_any_member": int((group["members_high_plus"] > 0).sum()),
        }
    summary = {
        "runtime_seconds": runtime,
        "by_asset_type": counts,
        "uncertainty_calibration": calibrated_ellipse_scale(),
        "label": "Scenario ensemble from measured track error; probabilities are of the screening class, not of damage.",
    }
    return EnsembleResult(
        assets=assets, parameters=parameters, summary=summary,
        spaghetti_geojson={"type": "FeatureCollection", "features": features}, top_by_type=top_by_type,
    )
