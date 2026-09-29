"""Extra department asset layers from the cached OSM regional extracts (WP4.2).

Fire stations, police stations, water works / pumping / wastewater plants and harbours (best effort
for fishing harbours). Uses the same corridor, dedupe and track-distance filter as the core layers.
Usage: python scripts/fetch_extra_assets.py
"""

from __future__ import annotations

from pathlib import Path
import re
import sys
from typing import Any

import pandas as pd
import pyogrio

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import fetch_osm_infrastructure as osm  # noqa: E402
from services.config import load_region  # noqa: E402

FISHING = re.compile(r"fish|harbou?r|jetty|kuppam|port\b|marina", re.I)


def classify(tags: dict[str, str]) -> str | None:
    if tags.get("amenity") == "fire_station":
        return "fire_station"
    if tags.get("amenity") == "police":
        return "police_station"
    if tags.get("man_made") in {"water_works", "pumping_station", "wastewater_plant"}:
        return "water_facility"
    if (tags.get("landuse") == "harbour" or tags.get("harbour") == "yes" or tags.get("industrial") == "port"
            or tags.get("leisure") == "marina" or tags.get("seamark:type") in {"harbour", "small_craft_facility"}):
        return "fishing_harbour"
    return None


def parse(path: Path, source: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    bbox = (osm.GRID["west"], osm.GRID["south"], osm.GRID["east"], osm.GRID["north"])
    element = {"points": "node", "lines": "way", "multipolygons": "relation"}
    for layer in ("points", "multipolygons"):
        print(f"Reading {source} / {layer}...", flush=True)
        frame = pyogrio.read_dataframe(path, layer=layer, bbox=bbox)
        for _, row in frame.iterrows():
            tags = osm.row_tags(row)
            for key in ("man_made", "landuse", "harbour", "industrial", "leisure", "seamark:type"):
                if tags.get(key) is None and row.get(key) is not None and not pd.isna(row.get(key)):
                    tags[key] = str(row.get(key))
            kind = classify(tags)
            geometry = row.get("geometry")
            if kind is None or geometry is None or geometry.is_empty:
                continue
            name = next((tags[k] for k in ("name", "official_name", "short_name", "operator", "ref") if tags.get(k)), f"Unnamed {kind.replace('_', ' ')}")
            if kind == "fishing_harbour" and not FISHING.search(name):
                continue  # keep harbours that look like fishing / port facilities
            point = geometry if geometry.geom_type == "Point" else geometry.representative_point()
            elem, raw = element[layer], row.get("osm_id")
            if layer == "multipolygons" and row.get("osm_way_id") is not None and not pd.isna(row.get("osm_way_id")):
                elem, raw = "way", row.get("osm_way_id")
            try:
                osm_id = abs(int(raw))
            except (TypeError, ValueError):
                continue
            out.append({
                "asset_type": kind, "name": name, "osm_element": elem, "osm_id": osm_id,
                "lat": float(point.y), "lon": float(point.x), "operator": tags.get("operator"), "ref": tags.get("ref"),
                "source_tile": osm.tile_name_for(float(point.y), float(point.x)), "amenity": tags.get("amenity"),
                "website": tags.get("website"), "phone": tags.get("phone") or tags.get("contact:phone"),
            })
    return out


def main() -> None:
    region = load_region()
    track = osm.load_track()
    points = list(zip(track["LAT"].astype(float), track["LON"].astype(float)))
    records: list[dict[str, Any]] = []
    for name in osm.PBF_SOURCES:
        path = osm.CACHE_DIR / f"{name}-latest.osm.pbf"
        if not path.exists():
            raise FileNotFoundError(f"{path} missing; run scripts/fetch_osm_infrastructure.py first")
        records.extend(parse(path, name))
    kept = osm.deduplicate_and_filter(records, points)
    target = region.path("extra_assets_raw")
    target.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(kept).to_csv(target, index=False)
    counts = pd.DataFrame(kept)["asset_type"].value_counts().to_dict()
    print(f"SURGESIGHT_EXTRA_ASSETS_FETCHED {counts}")


if __name__ == "__main__":
    main()
