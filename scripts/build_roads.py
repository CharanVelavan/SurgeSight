"""Build the road exposure layer: sections, hazards, levels, facility access, validation and the web payload.

Reads the cached OSM state extracts (scripts/fetch_osm_infrastructure.py). Earth Engine is needed for the terrain
and Sentinel-2 samples, which are cached in data/raw/road_samples.csv, so a rerun (for example after changing the
level cut-offs in services/roads.py) only redoes the fast steps.

Usage: python scripts/build_roads.py [--region michaung_2023] [--resample]
"""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd
import pyogrio
import shapely
from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import fetch_osm_infrastructure as osm  # noqa: E402
from services import roads  # noqa: E402
from services.assets import load_all_assets  # noqa: E402
from services.config import load_region  # noqa: E402
from services.hazards.coast import land_geometry  # noqa: E402
from services.hazards.rainfall import forecast_rainfall  # noqa: E402
from services.hazards.surge import peak_surge, surge_at_points  # noqa: E402
from services.hazards.wind_field import max_wind_kmh  # noqa: E402
from services.satellite_validation import auc  # noqa: E402

UTM = "EPSG:32644"
EE_BATCH = 1500
SAVE_EVERY = 6000  # sections sampled between saves of the cache
EE_RETRIES = 3
RAIN_CELL_DEG = 0.1
WEB_SIMPLIFY_DEG = 0.0002  # about 20 m
TOP_ROADS = 12


def read_ways(extent: dict[str, float]) -> list[roads.Way]:
    bbox = (extent["west"], extent["south"], extent["east"], extent["north"])
    seen: set[int] = set()
    ways: list[roads.Way] = []
    for source in osm.PBF_SOURCES:
        path = osm.CACHE_DIR / f"{source}-latest.osm.pbf"
        if not path.exists():
            raise FileNotFoundError(f"{path} missing; run scripts/fetch_osm_infrastructure.py first")
        print(f"reading {source} lines...", flush=True)
        frame = pyogrio.read_dataframe(path, layer="lines", bbox=bbox, columns=["osm_id", "name", "highway", "other_tags"])
        frame = frame[frame["highway"].notna()]
        for row in frame.itertuples(index=False):
            cls = roads.highway_class(str(row.highway))
            if cls is None or row.geometry is None or row.geometry.is_empty:
                continue
            way_id = abs(int(row.osm_id))
            if way_id in seen:
                continue
            seen.add(way_id)
            ref = osm.parse_other_tags(row.other_tags).get("ref")
            name = row.name if isinstance(row.name, str) else None
            for part in getattr(row.geometry, "geoms", [row.geometry]):
                ways.append(roads.Way(way_id, cls, name, ref, np.asarray(part.coords)[:, :2]))
    return ways


def ee_line(coords: np.ndarray):
    import ee

    if len(coords) < 2 or np.allclose(coords[0], coords[-1]) and len(coords) == 2:
        return ee.Geometry.Point([float(coords[0, 0]), float(coords[0, 1])])
    return ee.Geometry.LineString([[float(x), float(y)] for x, y in coords])


def reduce_lines(image, sections: pd.DataFrame, reducer, scale: float, label: str) -> pd.DataFrame:
    """reduceRegions over each section's line, in batches, with retries."""
    import ee

    rows: list[dict] = []
    for start in range(0, len(sections), EE_BATCH):
        batch = sections.iloc[start : start + EE_BATCH]
        features = ee.FeatureCollection([ee.Feature(ee_line(c), {"sid": sid}) for sid, c in zip(batch["section_id"], batch["coords"])])
        for attempt in range(1, EE_RETRIES + 1):
            try:
                result = image.reduceRegions(collection=features, reducer=reducer, scale=scale).getInfo()
                rows.extend(f["properties"] for f in result["features"])
                break
            except Exception as exc:  # Earth Engine raises several exception types
                if attempt == EE_RETRIES:
                    raise
                print(f"  {label} retry {attempt}: {exc}", flush=True)
                time.sleep(2 ** attempt)
        print(f"  {label}: {min(start + EE_BATCH, len(sections))}/{len(sections)}", flush=True)
    return pd.DataFrame(rows)


def sample_terrain(sections: pd.DataFrame) -> pd.DataFrame:
    """Lowest ground, lowest height above drainage and wettest surface-water history along each section."""
    import ee

    from services.earth_engine import init_ee

    init_ee()
    terrain = (
        ee.Image("USGS/SRTMGL1_003").select("elevation").unmask(0).rename("elev")
        .addBands(ee.Image("MERIT/Hydro/v1_0_1").select("hnd").rename("hand"))
        .addBands(ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").unmask(0).rename("water"))
    )
    reducer = ee.Reducer.min().combine(ee.Reducer.max(), sharedInputs=True)
    t = reduce_lines(terrain, sections, reducer, 30, "terrain")
    t = t.rename(columns={"sid": "section_id", "elev_min": "elevation_min_m", "hand_min": "hand_min_m", "water_max": "water_max_pct"})
    return t[["section_id", "elevation_min_m", "hand_min_m", "water_max_pct"]]


def sample_observed(sections: pd.DataFrame, region) -> pd.DataFrame:
    """Sentinel-2 observed-flood flag along each section (validation only, never a forecast input)."""
    import ee

    from services.earth_engine import init_ee
    from services.satellite_validation import sentinel2_flood

    init_ee()
    flood, valid = sentinel2_flood(region.id)
    observed = flood.unmask(0).rename("flooded").addBands(valid.rename("valid"))
    o = reduce_lines(observed, sections, ee.Reducer.max(), 30, "sentinel-2")
    return o.rename(columns={"sid": "section_id"})[["section_id", "flooded", "valid"]]


def sample_rain(sections: pd.DataFrame, region) -> np.ndarray:
    """GFS forecast rain issued at the cutoff, sampled once per 0.1 degree cell of the section midpoints."""
    cells = pd.DataFrame({
        "lat": (sections["mid_lat"] / RAIN_CELL_DEG).round() * RAIN_CELL_DEG,
        "lon": (sections["mid_lon"] / RAIN_CELL_DEG).round() * RAIN_CELL_DEG,
    })
    unique = cells.drop_duplicates().reset_index(drop=True)
    unique["osm_element"], unique["osm_id"] = "cell", range(len(unique))
    print(f"GFS rain for {len(unique)} cells...", flush=True)
    cutoff = str(pd.Timestamp(region.demo_cutoff))
    rain, _ = forecast_rainfall(cutoff, 72, unique, cutoff_utc=cutoff)
    unique["rain_mm"] = rain["accum_mm"].to_numpy()
    return cells.merge(unique[["lat", "lon", "rain_mm"]], on=["lat", "lon"], how="left")["rain_mm"].to_numpy()


def coast_fields(sections: pd.DataFrame, region) -> pd.DataFrame:
    land = land_geometry(region.id)
    to_utm = Transformer.from_crs("EPSG:4326", UTM, always_xy=True).transform
    to_ll = Transformer.from_crs(UTM, "EPSG:4326", always_xy=True).transform
    boundary = transform(to_utm, land).boundary
    lon, lat = sections["mid_lon"].to_numpy(), sections["mid_lat"].to_numpy()
    x, y = to_utm(lon, lat)
    points = shapely.points(x, y)
    near = shapely.get_coordinates(shapely.shortest_line(points, boundary)).reshape(-1, 2, 2)[:, 1]
    near_lon, near_lat = to_ll(near[:, 0], near[:, 1])
    return pd.DataFrame({
        "on_land": shapely.contains_xy(land, lon, lat),
        "coast_dist_km": shapely.distance(points, boundary) / 1000,
        "coast_lat": near_lat, "coast_lon": near_lon,
    }, index=sections.index)


def districts_of(sections: pd.DataFrame, region) -> list[str | None]:
    geo = json.loads(region.path("districts").read_text(encoding="utf-8"))
    lon, lat = sections["mid_lon"].to_numpy(), sections["mid_lat"].to_numpy()
    out = np.full(len(sections), None, dtype=object)
    for feature in geo["features"]:
        inside = shapely.contains_xy(shape(feature["geometry"]), lon, lat)
        out[inside & (out == None)] = feature["properties"].get("district")  # noqa: E711
    return out.tolist()


def validation(frame: pd.DataFrame) -> dict:
    seen = frame[frame["valid"] == 1]
    flooded = seen["flooded"] == 1
    out = {
        "sensor": "sentinel2",
        "sections_observed": int(len(seen)), "km_observed": round(float(seen["length_km"].sum()), 1),
        "observed_flooded_share": round(float(flooded.mean()), 3) if len(seen) else None,
        "auc_water_on_road": auc(seen["water_on_road"].to_numpy(), flooded.to_numpy()),
        "auc_wet_ground": auc(seen["wet_ground"].to_numpy(), flooded.to_numpy()),
        "auc_rain_only": auc(seen["rain_mm"].to_numpy(), flooded.to_numpy()),
        "by_flood_level": {},
        "note": "Sentinel-2 standing water after the storm (see data/processed/satellite/observation_meta.json). "
                "A proxy: clouds and urban flooding are under-detected; unobserved sections are left out.",
    }
    for level in range(4):
        part = seen[seen["flood_level"] == level]
        out["by_flood_level"][roads.LEVEL_NAMES[level]] = {
            "sections": int(len(part)),
            "observed_flooded_share": round(float((part["flooded"] == 1).mean()), 3) if len(part) else None,
        }
    return out


def web_payload(frame: pd.DataFrame, meta: dict) -> dict:
    """Compact columns for the map: sections at level 1 and above, simplified, coordinates to 4 decimals."""
    shown = frame[frame["level"] >= 1].sort_values("level")
    path: list[float] = []
    starts: list[int] = []
    for coords in shown["coords"]:
        line = shapely.simplify(shapely.linestrings(coords), WEB_SIMPLIFY_DEG)
        pts = shapely.get_coordinates(line)
        starts.append(len(path) // 2)
        path.extend(np.round(pts, 4).ravel().tolist())
    names = sorted({n for n in shown["label"].dropna()})
    index = {n: i for i, n in enumerate(names)}

    def col(name: str, digits: int = 1) -> list:
        return [None if pd.isna(v) else round(float(v), digits) for v in shown[name]]

    return {
        **meta,
        "count": int(len(shown)), "names": names,
        "path": path, "starts": starts,
        "id": shown["section_id"].tolist(),
        "name": [index.get(n, -1) if isinstance(n, str) else -1 for n in shown["label"]],
        "highway": [roads.HIGHWAY_RANK[h] for h in shown["highway"]],
        "level": shown["level"].astype(int).tolist(),
        "cause": shown["cause"].tolist(),
        "km": col("length_km", 2), "rain_mm": col("rain_mm", 0), "wind_kmh": col("wind_kmh", 0),
        "surge_m": col("surge_m", 2), "elevation_min_m": col("elevation_min_m", 0), "hand_min_m": col("hand_min_m", 1),
        "district": [None if pd.isna(v) else str(v) for v in shown["district"]],
    }


STAGES = {
    "terrain": ["elevation_min_m", "hand_min_m", "water_max_pct"],
    "rain": ["rain_mm"],
    "observed": ["flooded", "valid"],
}


def cached_samples(sections: pd.DataFrame, region, resample: bool) -> pd.DataFrame:
    """Earth Engine samples per section, one stage at a time; each stage is saved as soon as it finishes."""
    cache = region.path("road_samples")
    cache.parent.mkdir(parents=True, exist_ok=True)
    table = pd.DataFrame({"section_id": sections["section_id"]})
    if cache.exists() and not resample:
        table = table.merge(pd.read_csv(cache), on="section_id", how="left")
    # nearby sections in the same batch keep each Earth Engine request small
    order = sections.assign(_cell=(sections["mid_lat"] * 5).round() * 1000 + (sections["mid_lon"] * 5).round()).sort_values(["_cell", "mid_lat"])
    for stage, cols in STAGES.items():
        for c in cols:
            if c not in table:
                table[c] = np.nan
        todo = order[order["section_id"].isin(table.loc[table[cols[0]].isna(), "section_id"])]
        if todo.empty:
            continue
        print(f"{stage}: {len(todo):,} sections to sample", flush=True)
        chunk = len(todo) if stage == "rain" else SAVE_EVERY
        for start in range(0, len(todo), chunk):
            part = todo.iloc[start : start + chunk]
            if stage == "terrain":
                fresh = sample_terrain(part)
            elif stage == "rain":
                fresh = pd.DataFrame({"section_id": part["section_id"].to_numpy(), "rain_mm": sample_rain(part.reset_index(drop=True), region)})
            else:
                fresh = sample_observed(part, region)
            table = table.set_index("section_id")
            table.update(fresh.set_index("section_id")[cols])
            table = table.reset_index()
            table.to_csv(cache, index=False)
    return table


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default=None)
    parser.add_argument("--resample", action="store_true", help="ignore the cached Earth Engine samples")
    args = parser.parse_args()
    region = load_region(args.region)
    out_dir = region.path("road_sections").parent
    out_dir.mkdir(parents=True, exist_ok=True)

    sections = roads.split_ways(read_ways(region.extent))
    print(f"{len(sections):,} sections, {sections['length_km'].sum():,.0f} km", flush=True)

    frame = sections.merge(cached_samples(sections, region, args.resample), on="section_id", how="left")

    track = pd.read_csv(region.path("track"))
    lat, lon = frame["mid_lat"].to_numpy(), frame["mid_lon"].to_numpy()
    frame["wind_kmh"] = np.concatenate([max_wind_kmh(track, lat[i : i + 4000], lon[i : i + 4000]) for i in range(0, len(frame), 4000)]).round(1)
    coast = coast_fields(frame, region).assign(elevation_m=frame["elevation_min_m"].fillna(30.0))
    surge = surge_at_points(peak_surge(track, region.id), coast)
    frame["surge_m"], frame["surge_score"] = surge["surge_m"].to_numpy(), surge["surge_score"].to_numpy()
    frame = roads.score_sections(frame)
    flood_score_cuts = frame.attrs["flood_score_cuts"]
    frame["district"] = districts_of(frame, region)
    frame["label"] = [roads.road_label(n, r) for n, r in zip(frame["name"], frame["ref"])]

    # facility access
    assets = load_all_assets(region.id)
    hospital = (assets["asset_type"] == "hospital") & (assets.get("facility_quality", pd.Series("hospital", index=assets.index)) == "hospital")
    acc = roads.access(frame, assets, hospital)
    acc.to_csv(region.path("road_access"), index=False)

    check = validation(frame)
    by_district = (frame[frame["level"] >= 2].groupby("district")["length_km"].sum().round(1).sort_values(ascending=False))
    named = frame[(frame["level"] >= 2) & frame["label"].notna()]
    top = (named.groupby("label").agg(km=("length_km", "sum"), worst=("level", "max"), highway=("highway", lambda h: min(h, key=roads.HIGHWAY_RANK.get)))
           .assign(rank=lambda d: d["highway"].map(roads.HIGHWAY_RANK))
           .sort_values(["worst", "rank", "km"], ascending=[False, True, False]).head(TOP_ROADS))
    joined = assets[["osm_element", "osm_id", "asset_type", "name"]].merge(acc, on=["osm_element", "osm_id"])
    summary = {
        "model_version": roads.MODEL_VERSION, "label": roads.LABEL,
        "sections": int(len(frame)), "km_total": round(float(frame["length_km"].sum()), 1),
        "km_by_level": roads.km_by_level(frame),
        "km_by_cause_level2plus": {str(k): round(float(v), 1) for k, v in frame[frame["level"] >= 2].groupby("cause")["length_km"].sum().items()},
        "km_level2plus_by_district": {str(k): float(v) for k, v in by_district.items()},
        "top_roads": [{"road": k, "km": round(float(r.km), 1), "level": int(r.worst), "highway": r.highway} for k, r in top.iterrows()],
        "access_counts": {str(k): {str(s): int(n) for s, n in g["road_access"].value_counts().items()} for k, g in joined.groupby("asset_type")},
        "hospital_detour": {
            "facilities_with_longer_trip": int(((joined["hospital_km_after"] - joined["hospital_km_before"]) > 1).sum()),
            "facilities_without_hospital_after": int((joined["hospital_km_before"].notna() & joined["hospital_km_after"].isna()).sum()),
        },
        "cuts": {"flood_km_percentiles": list(roads.FLOOD_PERCENTILES), "flood_score_values": list(flood_score_cuts),
                 "wind_kmh": list(roads.WIND_CUTS_KMH)},
        "validation": check,
        "sources": {
            "roads": "OpenStreetMap contributors (motorway to tertiary and link roads)",
            "terrain": "USGS SRTM (lowest point), MERIT Hydro height above drainage (lowest), JRC surface water (highest)",
            "rain": f"NOAA GFS forecast issued {region.demo_cutoff} UTC, 72 h, via Earth Engine",
            "wind": "Holland (1980) profile along the track", "surge": "SurgeSight screening surge index",
            "validation": "Sentinel-2 flood map (validation only, never a forecast input)",
        },
    }
    region.path("roads_summary").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    keep = ["section_id", "way_id", "highway", "label", "district", "length_km", "mid_lat", "mid_lon", "elevation_min_m", "hand_min_m",
            "water_max_pct", "rain_mm", "wind_kmh", "surge_m", "surge_score", "wet_ground", "water_on_road", "flood_level", "wind_level",
            "level", "cause", "flooded", "valid"]
    frame[keep].to_csv(region.path("road_sections"), index=False)
    payload = web_payload(frame, {"model_version": roads.MODEL_VERSION, "label": roads.LABEL, "summary": {k: summary[k] for k in ("km_total", "km_by_level")}})
    with gzip.open(region.path("roads_web"), "wt", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"), ensure_ascii=False)

    print(json.dumps({k: summary[k] for k in ("km_total", "km_by_level", "km_by_cause_level2plus", "access_counts", "hospital_detour", "validation")}, indent=2))
    print(f"web payload: {payload['count']:,} sections, {region.path('roads_web').stat().st_size / 1e6:.2f} MB gzipped")
    print("SURGESIGHT_ROADS_BUILT")


if __name__ == "__main__":
    main()
