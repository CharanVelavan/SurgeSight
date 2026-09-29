"""Satellite validation: AUC maths, metric consistency on the cached observation, cached images, Gemini review."""

from __future__ import annotations

import os
from pathlib import Path
import sys

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.agent.grounding_guard import check
from services.risk_model_v2 import score_v2
from services.satellite_validation import auc, cached_review, compute_metrics, load_images, load_observed


def main() -> None:
    assert auc(np.array([1, 2, 3, 4.0]), np.array([0, 0, 1, 1])) == 1.0
    assert auc(np.array([4, 3, 2, 1.0]), np.array([0, 0, 1, 1])) == 0.0
    assert auc(np.array([1, 1, 1, 1.0]), np.array([0, 1, 0, 1])) == 0.5
    assert auc(np.array([1.0, 2.0]), np.array([0, 0])) is None

    track = pd.read_csv(PROJECT_ROOT / "data/processed/michaung_track.csv")
    assets = pd.read_csv(PROJECT_ROOT / "data/processed/scored_assets.csv")
    frame, _ = score_v2(track, assets)
    observed, meta = load_observed()
    assert len(observed) == len(assets) and set(observed["flooded"]) <= {-1, 0, 1}
    assert ((observed["observed"] == 0) == (observed["flooded"] == -1)).all(), "unobserved assets must not count as unflooded"
    metrics = compute_metrics(frame, observed, meta)
    assert metrics["sensor"] in {"sentinel1", "sentinel2"} and metrics["asset_coverage_pct"] >= 25
    assert metrics["assets_observed"] == int(observed["observed"].sum())
    for name in ("v1_high_plus", "v2_high_plus"):
        c = metrics[name]
        assert c["true_positive"] + c["false_positive"] + c["false_negative"] + c["true_negative"] == metrics["assets_observed"]
        assert c["true_positive"] + c["false_negative"] == metrics["assets_flooded"]
    assert all(v is None or 0 <= v <= 1 for v in metrics["ranking_skill_auc"].values())
    assert sum(r["observed"] for r in metrics["by_asset_type"]) == metrics["assets_observed"]

    images = load_images()
    assert set(images) == {"flood", "rain", "screening"} and all(b[:8] == b"\x89PNG\r\n\x1a\n" for b in images.values())

    if os.getenv("SURGESIGHT_OFFLINE") == "1":
        print("SKIPPED Gemini review (SURGESIGHT_OFFLINE=1)")
        return
    review, cached = cached_review(metrics, images)
    text = review.model_dump_json()
    assert review.summary.strip() and (review.missed_areas or review.over_flagged_areas)
    assert check(text, [{"data": metrics, "warnings": []}]) == [], "review contains numbers not in the metrics"
    print("review", "from cache" if cached else "generated", "-", review.summary[:160])
    print("SURGESIGHT_SATELLITE_VALIDATION_OK")


if __name__ == "__main__":
    main()
