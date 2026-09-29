"""Tools for probabilistic exposure and (later) rainfall, surge and v2 hazards."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from services.agent.builtin_tools import jsonable
from services.agent.tools import ok_result, tool
from services.store import get_store, new_run_id


class RunEnsembleArgs(BaseModel):
    members: int = Field(default=100, ge=10, le=500, description="Number of perturbed tracks.")
    seed: int = Field(default=42, description="Random seed; the same seed gives the same result.")
    center_shift_n_km: float = Field(default=0.0, ge=-50, le=50, description="Centre of the ensemble: shift north (+) / south (-), km.")
    center_shift_e_km: float = Field(default=0.0, ge=-50, le=50, description="Centre of the ensemble: shift east (+) / west (-), km.")
    center_intensity_pct: float = Field(default=0.0, ge=-20, le=20, description="Centre of the ensemble: wind change, percent.")
    sigma_km: float | None = Field(default=None, ge=0, le=150, description="Per-axis track spread in km. Omit to use the measured 12-hour forecast error.")


@tool("run_ensemble", agent_scopes={"forecast", "impact"})
def run_ensemble_tool(args: RunEnsembleArgs) -> Any:
    """Probabilistic exposure: score many perturbed tracks (spread taken from the measured
    track-forecast error) and rank assets by the share of members in which they reach HIGH or
    CRITICAL, weighted by criticality. Use it when the officer asks which assets are most likely
    at risk, or how uncertainty in the track changes priorities. Returns the top 15 assets per
    type with 'HIGH or worse in k/N members' and a run_id. Probabilities describe the screening
    class under track uncertainty, not damage."""
    from services.ensemble import run_ensemble

    result = run_ensemble(
        members=args.members, seed=args.seed, center_shift_n_km=args.center_shift_n_km,
        center_shift_e_km=args.center_shift_e_km, center_intensity_pct=args.center_intensity_pct,
        sigma_km=args.sigma_km,
    )
    run_id = new_run_id("ensemble")
    store = get_store()
    store.put(run_id, "ensemble", jsonable({
        "parameters": result.parameters, "summary": result.summary,
        "top_by_type": result.top_by_type, "spaghetti_geojson": result.spaghetti_geojson,
    }))
    store.put_frame(run_id, "assets", result.assets)
    data = jsonable({
        "parameters": result.parameters,
        "by_asset_type": result.summary["by_asset_type"],
        "top_by_type": result.top_by_type,
        "uncertainty_calibration": result.summary["uncertainty_calibration"],
        "label": result.summary["label"],
        "hospital_note": "Hospital ranking excludes OSM records that are clinics, dental or eye-care sites.",
    })
    return ok_result("run_ensemble", data, source="ensemble:risk_model_v1", run_id=run_id, model_version=result.parameters["model_version"])
