"""Precompute a 0.05-degree exposure grid: population, buildings and district per cell (WP2.5).

Earth Engine is only needed here. Runtime footprints are intersected with this cached grid.
  population : WorldPop 100 m (latest year, India)   -> sum per cell
  buildings  : Google Open Buildings v3 polygons, confidence >= 0.75 -> count per cell (a building is counted in each cell it touches)
  districts  : FAO GAUL 2025 level 2 (boundaries saved to districts.geojson)

Resumable: per-tile building counts are cached under data/raw/exposure/.
Usage: python scripts/build_exposure_grid.py [--region michaung_2023] [--workers 8]
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import math
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import ee

from services.config import load_region
from services.earth_engine import init_ee

STEP = 0.05
TILE_CELLS = 5  # buildings are counted in 0.25 degree tiles
MIN_CONFIDENCE = 0.75
CACHE = PROJECT_ROOT / "data" / "raw" / "exposure"


def count_tile(tx: int, ty: int, west: float, south: float, nx: int) -> dict[int, int]:
    file = CACHE / f"buildings_{tx}_{ty}.json"
    if file.exists():
        return {int(k): v for k, v in json.loads(file.read_text()).items()}
    x0, y0 = west + tx * TILE_CELLS * STEP, south + ty * TILE_CELLS * STEP
    buildings = (
        ee.FeatureCollection("GOOGLE/Research/open-buildings/v3/polygons")
        .filter(ee.Filter.gte("confidence", MIN_CONFIDENCE))
    )
    # A building is counted in every cell it touches (overcount is far below 1 %).
    cells = ee.FeatureCollection([
        ee.Feature(
            ee.Geometry.Rectangle([x0 + i * STEP, y0 + j * STEP, x0 + (i + 1) * STEP, y0 + (j + 1) * STEP]),
            {"cell": (ty * TILE_CELLS + j) * nx + tx * TILE_CELLS + i},
        )
        for j in range(TILE_CELLS) for i in range(TILE_CELLS)
    ])
    counted = cells.map(lambda c: c.set("n", buildings.filterBounds(c.geometry()).size()))

    for attempt in range(4):
        try:
            rows = counted.getInfo()["features"]
            hist = {int(r["properties"]["cell"]): int(r["properties"]["n"]) for r in rows}
            break
        except Exception as exc:  # transient EE errors / timeouts
            if attempt == 3:
                raise
            print(f"  tile {tx},{ty} retry after: {str(exc)[:80]}", flush=True)
            time.sleep(10 * (attempt + 1))
    CACHE.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(hist))
    return {int(k): int(v) for k, v in hist.items()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default=None)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    region = load_region(args.region)
    ext = region.extent
    west, south = ext["west"], ext["south"]
    nx = int(math.ceil((ext["east"] - west) / STEP / TILE_CELLS) * TILE_CELLS)
    ny = int(math.ceil((ext["north"] - south) / STEP / TILE_CELLS) * TILE_CELLS)
    init_ee()
    print(f"grid {nx} x {ny} cells of {STEP} deg", flush=True)

    ix, iy = np.meshgrid(np.arange(nx), np.arange(ny))
    grid = pd.DataFrame({"ix": ix.ravel(), "iy": iy.ravel()})
    grid["cell_id"] = grid["iy"] * nx + grid["ix"]
    grid["lat"] = (south + (grid["iy"] + 0.5) * STEP).round(4)
    grid["lon"] = (west + (grid["ix"] + 0.5) * STEP).round(4)

    # districts: GAUL 2025, rasterised, sampled at cell centres
    extent_rect = ee.Geometry.Rectangle([west, south, west + nx * STEP, south + ny * STEP])
    districts = ee.FeatureCollection("FAO/GAUL/2025/level2").filter(ee.Filter.eq("ISO3_CODE", "IND")).filterBounds(extent_rect)
    info = districts.getInfo()["features"]
    names = {f["properties"]["GAUL2_CODE"]: (f["properties"]["GAUL2_NAME"], f["properties"]["GAUL1_NAME"]) for f in info}
    region.path("districts").write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": f["geometry"], "properties": {"code": f["properties"]["GAUL2_CODE"], "district": f["properties"]["GAUL2_NAME"], "state": f["properties"]["GAUL1_NAME"]}}
            for f in districts.map(lambda f: f.setGeometry(f.geometry().simplify(300))).getInfo()["features"]
        ],
    }), encoding="utf-8")
    # Assign districts to cell centres locally (point-in-polygon on the saved boundaries); sea cells stay empty.
    from services.exposure import assign_districts, load_districts

    load_districts.cache_clear()
    assigned = assign_districts(grid, args.region, nearest_fallback=False)
    grid["district"], grid["state"] = assigned["district"], assigned["state"]
    print("districts:", sorted({d for d in grid["district"].dropna()}), flush=True)

    # population: WorldPop sum per cell
    pop_collection = ee.ImageCollection("WorldPop/GP/100m/pop").filter(ee.Filter.eq("country", "IND"))
    year = max(int(y) for y in pop_collection.aggregate_array("year").getInfo())
    population = pop_collection.filter(ee.Filter.eq("year", year)).select("population").mosaic()
    pop_values: list[float | None] = []
    for start in range(0, len(grid), 600):
        chunk = grid.iloc[start : start + 600]
        cells = ee.FeatureCollection([
            ee.Feature(ee.Geometry.Rectangle([r.lon - STEP / 2, r.lat - STEP / 2, r.lon + STEP / 2, r.lat + STEP / 2]), {"i": int(k)})
            for k, r in zip(chunk.index, chunk.itertuples())
        ])
        reduced = population.reduceRegions(cells, ee.Reducer.sum(), 100).getInfo()["features"]
        by_index = {f["properties"]["i"]: f["properties"].get("sum") for f in reduced}
        pop_values.extend(by_index.get(int(k)) for k in chunk.index)
        print(f"  population {min(start + 600, len(grid))}/{len(grid)}", flush=True)
    grid["population"] = pd.Series(pop_values, index=grid.index).fillna(0).round(1)

    # buildings: per-tile histograms in parallel
    tiles = [(tx, ty) for ty in range(ny // TILE_CELLS) for tx in range(nx // TILE_CELLS)]
    counts = np.zeros(nx * ny, dtype=np.int64)
    started = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(count_tile, tx, ty, west, south, nx): (tx, ty) for tx, ty in tiles}
        for done, future in enumerate(as_completed(futures), 1):
            for cell, n in future.result().items():
                if 0 <= cell < len(counts):
                    counts[cell] += n
            if done % 10 == 0 or done == len(tiles):
                print(f"  buildings tiles {done}/{len(tiles)} ({time.time() - started:.0f}s)", flush=True)
    grid["buildings"] = counts[grid["cell_id"].to_numpy()]
    grid["worldpop_year"] = year
    grid.to_csv(region.path("exposure_grid"), index=False)
    print(f"population total {grid.population.sum():,.0f}; buildings total {grid.buildings.sum():,}; cells with district: {grid.district.notna().sum()}", flush=True)


if __name__ == "__main__":
    main()
