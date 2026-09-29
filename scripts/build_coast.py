"""Cache the land polygon, per-asset coast distance and nearshore bathymetry (WP2.3 inputs).

Earth Engine is only needed here; runtime reads the cached files.
Usage: python scripts/build_coast.py [--region michaung_2023]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import ee

from services.config import load_region
from services.earth_engine import country_geometry, init_ee

UTM = "EPSG:32644"  # UTM 44N covers the Bay of Bengal east coast
SAMPLE_SPACING_KM = 10.0
SHELF_RADIUS_M = 50_000
MARGIN_DEG = 1.5


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default=None)
    region = load_region(parser.parse_args().region)
    bbox = region.bbox
    init_ee()

    # 1. land polygon (country ∩ generous rectangle), simplified
    rect = ee.Geometry.Rectangle([bbox["west"] - 5, bbox["south"] - 5, bbox["east"] + 5, bbox["north"] + 5])
    land = country_geometry(region.country).intersection(rect, 1000).simplify(500).getInfo()
    parts = shape(land)
    polygons = [g for g in getattr(parts, "geoms", [parts]) if g.geom_type in ("Polygon", "MultiPolygon")]
    geometry = shapely.union_all(polygons)  # drop stray lines/points from the intersection
    region.path("land_polygon").write_text(json.dumps(shapely.geometry.mapping(geometry)), encoding="utf-8")
    print(f"land polygon: {geometry.geom_type}, area {geometry.area:.2f} deg2")

    to_utm = Transformer.from_crs("EPSG:4326", UTM, always_xy=True).transform
    to_ll = Transformer.from_crs(UTM, "EPSG:4326", always_xy=True).transform
    land_utm = transform(to_utm, geometry)
    boundary = land_utm.boundary

    # 2. per-asset distance to (and nearest point on) the coast
    assets = pd.read_csv(region.path("scored_assets"))
    x, y = to_utm(assets["lon"].to_numpy(), assets["lat"].to_numpy())
    points = shapely.points(x, y)
    lines = shapely.shortest_line(points, boundary)
    coords = shapely.get_coordinates(lines).reshape(-1, 2, 2)  # [asset][point0=asset, point1=boundary]
    near_x, near_y = coords[:, 1, 0], coords[:, 1, 1]
    near_lon, near_lat = to_ll(near_x, near_y)
    on_land = shapely.contains_xy(geometry, assets["lon"].to_numpy(), assets["lat"].to_numpy())
    out = assets[["osm_element", "osm_id"]].copy()
    out["on_land"] = on_land
    out["coast_dist_km"] = (shapely.distance(points, boundary) / 1000).round(3)
    out["coast_lat"], out["coast_lon"] = np.round(near_lat, 5), np.round(near_lon, 5)
    out.to_csv(region.path("coast_assets"), index=False)
    print(f"assets on land: {int(on_land.sum())}/{len(out)}; within 10 km of coast: {int(((out.coast_dist_km <= 10) & out.on_land).sum())}")

    # 3. coast sample points every 10 km inside the region (+margin), with mean nearshore depth
    window = shapely.box(bbox["west"] - MARGIN_DEG, bbox["south"] - MARGIN_DEG, bbox["east"] + MARGIN_DEG, bbox["north"] + MARGIN_DEG)
    coast = shapely.intersection(boundary, transform(to_utm, window))
    samples = []
    for line in getattr(coast, "geoms", [coast]):
        if line.length == 0:
            continue
        for d in np.arange(0, line.length, SAMPLE_SPACING_KM * 1000):
            p = line.interpolate(d)
            lon, lat = to_ll(p.x, p.y)
            samples.append((lat, lon))
    print(f"coast samples: {len(samples)}")
    depth = ee.Image("NOAA/NGDC/ETOPO1").select("bedrock")
    sea_depth = depth.multiply(-1).updateMask(depth.lt(0)).rename("depth_m")
    features = [ee.Feature(ee.Geometry.Point([lon, lat]).buffer(SHELF_RADIUS_M), {"i": i}) for i, (lat, lon) in enumerate(samples)]
    reduced = sea_depth.reduceRegions(ee.FeatureCollection(features), ee.Reducer.mean(), 1855).getInfo()
    depths = {f["properties"]["i"]: f["properties"].get("mean") for f in reduced["features"]}
    table = pd.DataFrame(
        [{"lat": round(lat, 5), "lon": round(lon, 5), "mean_depth_50km_m": depths.get(i)} for i, (lat, lon) in enumerate(samples)]
    )
    table.to_csv(region.path("coast_shelf"), index=False)
    print(table["mean_depth_50km_m"].describe().round(1).to_dict())


if __name__ == "__main__":
    main()
