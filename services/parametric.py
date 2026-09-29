"""Parametric trigger evaluation (WP5.2). ILLUSTRATIVE: portfolios, sums insured and payout tiers are invented.

The trigger index of a portfolio is the 75th percentile, over its insured sites, of the wind, the wettest-24h
rainfall or the surge screening score. The deterministic payout uses the reference track; the ensemble gives
the probability of each trigger and the expected payout by re-scoring wind and surge for perturbed tracks
(rain does not depend on the track in this model, so it is the same in every member).
"""

from __future__ import annotations

from functools import lru_cache
import tomllib
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from services.assets import load_all_assets
from services.config import PROJECT_ROOT, load_region
from services.exposure import assign_districts
from services.hazards.rainfall import load_rainfall_assets
from services.hazards.surge import surge_scores
from services.hazards.wind_field import max_wind_kmh

TRIGGERS_FILE = PROJECT_ROOT / "config" / "parametric_triggers.toml"
LABEL = (
    "ILLUSTRATIVE parametric outputs. Portfolios, sums insured, tiers and payouts are invented to show how "
    "triggers would work; they are not an insurance product, a price or a claim."
)


def load_config() -> dict[str, Any]:
    return tomllib.loads(TRIGGERS_FILE.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _sites() -> pd.DataFrame:
    """Assets with district and peak 24 h forecast rain, the fixed inputs of every evaluation."""
    assets = load_all_assets()[["osm_element", "osm_id", "asset_type", "lat", "lon", "elevation_m"]].reset_index(drop=True)
    assets["district"] = assign_districts(assets)["district"].to_numpy()
    rain = load_rainfall_assets()[["osm_element", "osm_id", "fc_peak_24h_mm"]]
    return assets.merge(rain, on=["osm_element", "osm_id"], how="left")


def payout_pct(value: float, tiers: list[dict[str, float]]) -> float:
    reached = [t["payout_pct"] for t in tiers if value >= t["at"]]
    return float(max(reached)) if reached else 0.0


def _index(values: np.ndarray, quantile: float) -> float:
    values = values[~np.isnan(values)]
    return float(np.quantile(values, quantile)) if values.size else 0.0


def _track_indices(track: pd.DataFrame, sites: pd.DataFrame, region_id: str | None) -> tuple[np.ndarray, np.ndarray]:
    wind = max_wind_kmh(track, sites["lat"].to_numpy(float), sites["lon"].to_numpy(float))
    surge, _ = surge_scores(track, sites, region_id)
    return np.asarray(wind, float), surge["surge_score"].to_numpy(float)


def _portfolio_values(cfg: dict[str, Any], sites: pd.DataFrame, wind: np.ndarray, surge: np.ndarray) -> list[dict[str, Any]]:
    q = cfg["meta"]["index_quantile"]
    out = []
    for portfolio in cfg["portfolios"]:
        mask = sites["district"].isin(portfolio["districts"]).to_numpy()
        values = {
            "wind": _index(wind[mask], q),
            "rain_24h": _index(sites["fc_peak_24h_mm"].to_numpy(float)[mask], q),
            "surge": _index(surge[mask], q),
        }
        pct = {t["id"]: payout_pct(values[t["id"]], t["tiers"]) for t in cfg["triggers"]}
        total_pct = min(100.0, sum(pct.values()))
        out.append({"id": portfolio["id"], "sites": int(mask.sum()), "values": values, "payout_pct_by_trigger": pct,
                    "payout_pct": total_pct, "payout_inr": portfolio["sum_insured_inr"] * total_pct / 100.0})
    return out


def evaluate(track: pd.DataFrame | None = None, *, members: int = 0, seed: int = 42, sigma_km: float | None = None,
             region_id: str | None = None) -> dict[str, Any]:
    """Evaluate every trigger for the reference (or given) track; with ``members`` > 0 add ensemble probabilities."""
    from services.ensemble import default_sigma_km
    from services.scenario_engine import shift_track_unbounded

    cfg, sites = load_config(), _sites()
    region = load_region(region_id)
    track = pd.read_csv(region.path("track")) if track is None else track
    wind, surge = _track_indices(track, sites, region_id)
    deterministic = _portfolio_values(cfg, sites, wind, surge)
    portfolios = []
    for spec, det in zip(cfg["portfolios"], deterministic):
        entry = {"id": det["id"], "name": spec["name"], "districts": spec["districts"], "sum_insured_inr": spec["sum_insured_inr"],
                 "insured_sites": det["sites"], "triggers": [], "payout_pct": det["payout_pct"], "payout_inr": det["payout_inr"]}
        for trig in cfg["triggers"]:
            value = det["values"][trig["id"]]
            entry["triggers"].append({"id": trig["id"], "label": trig["label"], "index_value": round(value, 3),
                                      "breached": payout_pct(value, trig["tiers"]) > 0,
                                      "payout_pct": det["payout_pct_by_trigger"][trig["id"]]})
        portfolios.append(entry)
    result: dict[str, Any] = {"illustrative": True, "currency": cfg["meta"]["currency"], "label": LABEL, "portfolios": portfolios,
                              "total_payout_inr": sum(p["payout_inr"] for p in portfolios),
                              "total_sum_insured_inr": sum(p["sum_insured_inr"] for p in portfolios)}
    if members > 0:
        sigma = sigma_km if sigma_km is not None else default_sigma_km()
        rng = np.random.default_rng(seed)
        dn, de, di = rng.normal(0, sigma, members), rng.normal(0, sigma, members), rng.normal(0, 8.0, members)
        breach = {(p["id"], t["id"]): 0 for p in cfg["portfolios"] for t in cfg["triggers"]}
        payouts = np.zeros((members, len(cfg["portfolios"])))
        for i in range(members):
            w, s = _track_indices(shift_track_unbounded(track, dn[i], de[i], di[i]), sites, region_id)
            for j, member in enumerate(_portfolio_values(cfg, sites, w, s)):
                payouts[i, j] = member["payout_inr"]
                for tid, pct in member["payout_pct_by_trigger"].items():
                    breach[(member["id"], tid)] += pct > 0
        for j, entry in enumerate(portfolios):
            entry["expected_payout_inr"] = float(payouts[:, j].mean())
            entry["payout_p10_inr"], entry["payout_p90_inr"] = float(np.percentile(payouts[:, j], 10)), float(np.percentile(payouts[:, j], 90))
            for trig in entry["triggers"]:
                trig["probability"] = round(breach[(entry["id"], trig["id"])] / members, 3)
        result["ensemble"] = {"members": members, "seed": seed, "sigma_km_per_axis": sigma,
                              "expected_total_payout_inr": float(payouts.sum(axis=1).mean())}
    return result


CRORE = 1e7


def with_crore(result: dict[str, Any]) -> dict[str, Any]:
    """Add rupee crore fields (1 crore = 10 million) so that briefs can copy figures without converting."""
    result = dict(result)
    result["total_payout_crore"] = round(result["total_payout_inr"] / CRORE, 1)
    result["total_sum_insured_crore"] = round(result["total_sum_insured_inr"] / CRORE, 1)
    if "ensemble" in result:
        result["ensemble"] = {**result["ensemble"], "expected_total_payout_crore": round(result["ensemble"]["expected_total_payout_inr"] / CRORE, 1)}
    portfolios = []
    for p in result["portfolios"]:
        p = dict(p)
        for key in ("sum_insured_inr", "payout_inr", "expected_payout_inr", "payout_p10_inr", "payout_p90_inr"):
            if key in p:
                p[key.replace("_inr", "_crore")] = round(p[key] / CRORE, 1)
                del p[key]
        portfolios.append(p)
    result["portfolios"] = portfolios
    for key in ("total_payout_inr", "total_sum_insured_inr"):
        result.pop(key, None)
    if "ensemble" in result:
        result["ensemble"].pop("expected_total_payout_inr", None)
    return result


class LiquidityBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")
    headline: str
    summary: str
    liquidity_actions: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


def liquidity_brief(result: dict[str, Any]) -> LiquidityBrief:
    """Gemini Finance agent: a short liquidity brief written only from the evaluation's own figures."""
    import json

    from services.gemini_client import generate_structured

    prompt = (
        "Write a liquidity brief for a state disaster finance officer from this illustrative parametric evaluation. "
        "Copy every figure exactly as shown (rupee figures are in crore). Do not add, convert or estimate any number. "
        "State clearly that the portfolios and payouts are illustrative, not a real insurance product.\n\n"
        f"<EVALUATION>\n{json.dumps(result, ensure_ascii=False, indent=1)}\n</EVALUATION>"
    )
    return generate_structured(
        contents=prompt, schema=LiquidityBrief, max_output_tokens=2048,
        system_instruction="You are a cautious public-finance analyst. Use only figures in the supplied JSON.",
    )
