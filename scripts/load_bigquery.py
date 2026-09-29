"""Load SurgeSight tables into BigQuery (WP5.5): assets (with GEOGRAPHY), scenario_runs, ensemble_results,
advisories and dispatch_log.

Usage: python scripts/load_bigquery.py [--dataset surgesight] [--location asia-south1]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from google.cloud import bigquery  # noqa: E402

from services.config import get_settings  # noqa: E402
from services.store import get_store  # noqa: E402
from services.store.bigquery_store import build_assets_table  # noqa: E402


def load(client: bigquery.Client, dataset: str, name: str, frame: pd.DataFrame, geography: bool = False) -> None:
    table_id = f"{client.project}.{dataset}.{name}"
    target = table_id + "_raw" if geography else table_id
    client.load_table_from_dataframe(frame, target, job_config=bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")).result()
    if geography:
        client.query(f"CREATE OR REPLACE TABLE `{table_id}` CLUSTER BY geog AS SELECT *, ST_GEOGPOINT(lon, lat) AS geog FROM `{target}`").result()
        client.delete_table(target)
    print(f"loaded {name}: {len(frame)} rows")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default=None)
    parser.add_argument("--location", default="asia-south1")
    args = parser.parse_args()
    settings = get_settings()
    dataset = args.dataset or settings.bq_dataset
    client = bigquery.Client(project=settings.cloud_project)
    ref = bigquery.Dataset(f"{client.project}.{dataset}")
    ref.location = args.location
    try:
        existing = client.get_dataset(ref.reference)
        if existing.location.lower() != args.location.lower():
            raise SystemExit(f"Dataset {dataset} exists in {existing.location}; delete it or pass --location {existing.location}")
        ds = existing
    except Exception as exc:
        if isinstance(exc, SystemExit):
            raise
        ds = client.create_dataset(ref)
    print(f"dataset {ds.dataset_id} in {ds.location}")

    keep = ["name", "asset_type", "osm_element", "osm_id", "lat", "lon", "district", "facility_quality", "class_v2", "class_rank", "combined_v2",
            "triage_tier", "dominant_hazard", "wind_kmh_v2", "surge_m", "rain_mm", "elevation_m", "distance_to_track_km"]
    assets = build_assets_table()[keep].copy()
    assets["osm_id"] = assets["osm_id"].astype("int64")
    load(client, dataset, "assets", assets, geography=True)

    store = get_store()
    def runs(kind: str) -> list[dict]:
        return [store.get(r["run_id"]) for r in store.list(kind, 200)]

    scenarios = pd.DataFrame([{"run_id": r["run_id"], "created_at_utc": r["created_at_utc"], "summary_json": json.dumps(r["payload"].get("summary", {}), default=str)}
                              for r in runs("scenario")] or [{"run_id": "none", "created_at_utc": "", "summary_json": "{}"}])
    load(client, dataset, "scenario_runs", scenarios)

    from services.ensemble import run_ensemble
    ens = run_ensemble(members=100, seed=42).assets[["osm_element", "osm_id", "name", "asset_type", "p_high_plus", "p_critical", "score_mean", "priority"]].copy()
    ens.insert(0, "run_id", "baseline-ensemble-seed42")
    ens["osm_id"] = ens["osm_id"].astype("int64")
    load(client, dataset, "ensemble_results", ens)

    advisories = pd.DataFrame([{"run_id": r["run_id"], "created_at_utc": r["created_at_utc"], "audience": r["payload"].get("audience"),
                                "severity": r["payload"].get("severity"), "language": r["payload"].get("language"), "headline": r["payload"].get("headline")}
                               for r in runs("advisory")] or [{"run_id": "none", "created_at_utc": "", "audience": None, "severity": None, "language": None, "headline": None}])
    load(client, dataset, "advisories", advisories)

    log = pd.DataFrame([{"dispatch_id": r["run_id"], "created_at_utc": r["created_at_utc"], **{k: str(r["payload"].get(k)) for k in ("department", "channel", "status", "mode", "decided_by")}}
                        for r in runs("dispatch")] or [{"dispatch_id": "none", "created_at_utc": "", "department": None, "channel": None, "status": None, "mode": None, "decided_by": None}])
    load(client, dataset, "dispatch_log", log)
    print("SURGESIGHT_BIGQUERY_LOADED")


if __name__ == "__main__":
    main()
