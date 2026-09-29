"""Score Michaung corridor assets with track wind and Earth Engine terrain.

This is a transparent screening model for a hackathon prototype, not an
operational or physics-based cyclone damage model.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import ee
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.risk_model import (
    REFERENCE_WIND_KMH,
    SCREENING_CORRIDOR_KM,
    WEIGHTS,
    attach_nearest_track,
    score_assets_from_terrain,
)


TRACK_FILE = Path("data/processed/michaung_track.csv")
ASSET_FILE = Path("data/processed/osm/critical_assets.csv")
TERRAIN_SUMMARY_FILE = Path("data/processed/michaung_terrain_summary.json")
EE_CACHE_FILE = Path("data/raw/ee_asset_samples.json")
OUTPUT_CSV = Path("data/processed/scored_assets.csv")
OUTPUT_GEOJSON = Path("data/processed/scored_assets.geojson")
SUMMARY_FILE = Path("data/processed/risk_summary.json")

EE_BATCH_SIZE = 300
EE_RETRIES = 3


def atomic_json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    for path in (TRACK_FILE, ASSET_FILE, TERRAIN_SUMMARY_FILE):
        if not path.exists():
            raise FileNotFoundError(f"Required input does not exist: {path}")
    track = pd.read_csv(TRACK_FILE)
    assets = pd.read_csv(ASSET_FILE)
    terrain_summary = json.loads(TERRAIN_SUMMARY_FILE.read_text(encoding="utf-8"))
    required_track = {"LAT", "LON", "WIND_KMH"}
    required_assets = {"asset_type", "osm_element", "osm_id", "lat", "lon"}
    if missing := required_track - set(track.columns):
        raise ValueError(f"Track missing columns: {sorted(missing)}")
    if missing := required_assets - set(assets.columns):
        raise ValueError(f"Assets missing columns: {sorted(missing)}")
    for column in ("LAT", "LON", "WIND_KMH"):
        track[column] = pd.to_numeric(track[column], errors="coerce")
    for column in ("lat", "lon"):
        assets[column] = pd.to_numeric(assets[column], errors="coerce")
    track = track.dropna(subset=["LAT", "LON", "WIND_KMH"]).reset_index(drop=True)
    assets = assets.dropna(subset=["lat", "lon"]).reset_index(drop=True)
    if track.empty or assets.empty:
        raise ValueError("Track or critical asset input is empty")
    return track, assets, terrain_summary


def asset_key(row: Any) -> str:
    return f"{row.osm_element}/{int(row.osm_id)}"


def load_ee_cache() -> dict[str, dict[str, float]]:
    if not EE_CACHE_FILE.exists():
        return {}
    try:
        payload = json.loads(EE_CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def sample_earth_engine(
    assets: pd.DataFrame, project: str
) -> tuple[dict[str, dict[str, float]], list[dict[str, Any]]]:
    print(f"Initializing Earth Engine project: {project}")
    ee.Initialize(project=project)
    cache = load_ee_cache()
    missing_rows = [row for row in assets.itertuples(index=False) if asset_key(row) not in cache]
    failures: list[dict[str, Any]] = []
    print(f"Earth Engine point samples: {len(cache)} cached; {len(missing_rows)} missing")

    image = (
        ee.Image("USGS/SRTMGL1_003").select("elevation").unmask(0).rename("elevation_m")
        .addBands(
            ee.Image("JRC/GSW1_4/GlobalSurfaceWater")
            .select("occurrence").unmask(0).rename("water_occurrence_pct")
        )
    )
    for start in range(0, len(missing_rows), EE_BATCH_SIZE):
        batch = missing_rows[start : start + EE_BATCH_SIZE]
        features = [
            ee.Feature(ee.Geometry.Point([float(row.lon), float(row.lat)]), {"asset_key": asset_key(row)})
            for row in batch
        ]
        last_error: Exception | None = None
        for attempt in range(1, EE_RETRIES + 1):
            try:
                sampled = image.sampleRegions(
                    collection=ee.FeatureCollection(features), scale=30, geometries=False
                ).getInfo()
                returned = 0
                for feature in sampled.get("features", []):
                    properties = feature.get("properties") or {}
                    key = properties.get("asset_key")
                    elevation = properties.get("elevation_m")
                    water = properties.get("water_occurrence_pct")
                    if key is None or elevation is None or water is None:
                        continue
                    cache[str(key)] = {
                        "elevation_m": float(elevation),
                        "water_occurrence_pct": float(water),
                    }
                    returned += 1
                atomic_json_write(EE_CACHE_FILE, cache)
                print(f"  sampled {start + 1}-{start + len(batch)}: {returned} returned")
                last_error = None
                break
            except Exception as exc:  # Earth Engine raises several API exception types.
                last_error = exc
                if attempt < EE_RETRIES:
                    wait = 2 ** attempt
                    print(f"  Earth Engine batch retry {attempt}/{EE_RETRIES} in {wait}s: {exc}")
                    time.sleep(wait)
        if last_error is not None:
            failures.append({
                "batch_start": start + 1, "batch_size": len(batch), "error": str(last_error)
            })
    return cache, failures


def score_assets(assets: pd.DataFrame, samples: dict[str, dict[str, float]]) -> pd.DataFrame:
    result = assets.copy()
    result["asset_key"] = [asset_key(row) for row in result.itertuples(index=False)]
    result["elevation_m"] = result["asset_key"].map(
        lambda key: samples.get(key, {}).get("elevation_m")
    )
    result["water_occurrence_pct"] = result["asset_key"].map(
        lambda key: samples.get(key, {}).get("water_occurrence_pct")
    )
    if result[["elevation_m", "water_occurrence_pct"]].isna().any(axis=None):
        missing = int(result[["elevation_m", "water_occurrence_pct"]].isna().any(axis=1).sum())
        raise RuntimeError(
            f"Earth Engine values are missing for {missing} assets; rerun to retry those samples"
        )

    return score_assets_from_terrain(result.drop(columns=["asset_key"]))


def dataframe_geojson(frame: pd.DataFrame) -> dict[str, Any]:
    records = frame.where(pd.notna(frame), None).to_dict(orient="records")
    return {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
            "properties": {key: value for key, value in row.items() if key not in {"lat", "lon"}},
        } for row in records],
    }


def main() -> None:
    track, assets, terrain_summary = load_inputs()
    assets = attach_nearest_track(assets, track)
    project = str(terrain_summary.get("project") or "")
    if not project:
        raise ValueError("Earth Engine project is missing from terrain summary")
    samples, ee_failures = sample_earth_engine(assets, project)
    scored = score_assets(assets, samples)

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    scored.to_csv(OUTPUT_CSV, index=False)
    atomic_json_write(OUTPUT_GEOJSON, dataframe_geojson(scored))
    risk_counts = {name: int((scored["risk_class"] == name).sum()) for name in (
        "LOW", "MODERATE", "HIGH", "CRITICAL"
    )}
    high_or_critical = scored["risk_class"].isin(["HIGH", "CRITICAL"])
    population = terrain_summary.get("summary", {}).get("population_estimate")
    summary = {
        "scenario": "Cyclone Michaung 2023",
        "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "asset_count": len(scored),
        "asset_type_counts": {str(k): int(v) for k, v in scored["asset_type"].value_counts().items()},
        "risk_class_counts": risk_counts,
        "high_risk_hospitals": int(((scored["asset_type"] == "hospital") & high_or_critical).sum()),
        "high_risk_substations": int(((scored["asset_type"] == "substation") & high_or_critical).sum()),
        "population_exposed_screening_region": population,
        "earth_engine_sample_failures": ee_failures,
        "datasets": {
            "track": "NOAA IBTrACS Michaung observations",
            "infrastructure": "OpenStreetMap contributors via Overpass API",
            "elevation": "USGS/SRTMGL1_003",
            "surface_water": "JRC/GSW1_4/GlobalSurfaceWater occurrence",
        },
        "prototype_model": {
            "weights": WEIGHTS,
            "reference_wind_kmh": REFERENCE_WIND_KMH,
            "screening_corridor_km": SCREENING_CORRIDOR_KM,
            "wind_score": (
                "Observed nearest-track wind divided by 120 km/h, capped at 1, "
                "then multiplied by a distance factor declining from 1.0 to 0.5 at 140 km."
            ),
            "terrain_flood_score": (
                "70% elevation vulnerability (1 at <=5 m, declining linearly to 0 at >=30 m) "
                "plus 30% historical surface-water occurrence."
            ),
            "combined_risk_score": "65% wind score plus 35% terrain flood score.",
            "risk_classes": {
                "LOW": "0.00 <= score < 0.25", "MODERATE": "0.25 <= score < 0.50",
                "HIGH": "0.50 <= score < 0.75", "CRITICAL": "0.75 <= score <= 1.00",
            },
            "warning": (
                "Prototype screening index only; not an operational, physics-based cyclone, "
                "flood, storm-surge, or infrastructure damage model."
            ),
        },
    }
    atomic_json_write(SUMMARY_FILE, summary)

    print("\nSURGESIGHT_RISK_SCORING_OK\n")
    print(f"Scored assets: {len(scored):,}")
    for risk_class, count in risk_counts.items():
        print(f"{risk_class}: {count:,}")
    print(f"High-risk hospitals: {summary['high_risk_hospitals']:,}")
    print(f"High-risk substations: {summary['high_risk_substations']:,}")
    print(f"Earth Engine failed batches: {len(ee_failures):,}")


if __name__ == "__main__":
    main()
