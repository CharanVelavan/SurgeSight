"""Reliable, restartable OSM extraction for the Michaung demo corridor.

Uses 0.5-degree tiles and one Overpass request per category. Successful raw
responses are cached. The 140 km corridor is a prototype screening distance,
not an official cyclone wind-radius estimate.
"""

from __future__ import annotations

import csv
import json
import math
import random
import re
import time
from pathlib import Path
from typing import Any

import pandas as pd
import pyogrio
import requests

TRACK_FILE = Path("data/processed/michaung_track.csv")
CACHE_DIR = Path("data/raw/osm_cache")
OUTPUT_DIR = Path("data/processed/osm")
MAX_TRACK_DISTANCE_KM = 140.0
GRID = {"south": 12.5, "north": 16.5, "west": 79.5, "east": 81.0, "step": 0.5}

OVERPASS_ENDPOINTS = [
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.nchc.org.tw/api/interpreter",
]
REQUEST_TIMEOUT_SECONDS = (5, 15)
RETRIES_PER_ENDPOINT = 1
SUCCESS_DELAY_SECONDS = 0.8
RETRYABLE_HTTP_CODES = {429, 502, 503, 504}
HEADERS = {
    "User-Agent": "SurgeSight-Hackathon/1.0 (cyclone-risk research prototype)",
    "Accept": "application/json",
}

# Compact state extracts are the same real OSM data and are a practical
# same-day fallback when public Overpass capacity is unavailable. Together
# they are about 220 MB, rather than a multi-gigabyte India-wide extract.
PBF_SOURCES = {
    "tamil_nadu": "https://download.openstreetmap.fr/extracts/asia/india/tamil_nadu-latest.osm.pbf",
    "andhra_pradesh": "https://download.openstreetmap.fr/extracts/asia/india/andhra_pradesh-latest.osm.pbf",
}
MAX_CONSECUTIVE_OVERPASS_FAILURES = 1
OVERPASS_PROBE_QUERY_BUDGET = 3

CATEGORIES = {
    "hospitals": ("amenity", "hospital", "hospital"),
    "shelters": ("amenity", "shelter", "shelter"),
    "schools": ("amenity", "school", "school"),
    "substations": ("power", "substation", "substation"),
    "arterial_roads": ("highway", "^(motorway|trunk|primary)$", "arterial_road"),
}

BASE_COLUMNS = [
    "asset_type", "name", "osm_element", "osm_id", "lat", "lon",
    "distance_to_track_km", "operator", "ref", "source_tile", "amenity",
    "power", "highway", "emergency", "healthcare", "voltage", "website", "phone",
]


def load_track() -> pd.DataFrame:
    if not TRACK_FILE.exists():
        raise FileNotFoundError(f"Missing Michaung track: {TRACK_FILE}")
    track = pd.read_csv(TRACK_FILE)
    missing = {"LAT", "LON"} - set(track.columns)
    if missing:
        raise ValueError(f"Track is missing columns: {sorted(missing)}")
    track[["LAT", "LON"]] = track[["LAT", "LON"]].apply(pd.to_numeric, errors="coerce")
    track = track.dropna(subset=["LAT", "LON"])
    if track.empty:
        raise ValueError("Michaung track has no valid coordinates")
    return track


def build_tiles() -> list[dict[str, float | str]]:
    tiles: list[dict[str, float | str]] = []
    row, south = 1, GRID["south"]
    while south < GRID["north"] - 1e-9:
        col, west = 1, GRID["west"]
        while west < GRID["east"] - 1e-9:
            tiles.append({
                "name": f"corridor_r{row:02d}_c{col:02d}",
                "south": round(south, 4), "west": round(west, 4),
                "north": round(min(south + GRID["step"], GRID["north"]), 4),
                "east": round(min(west + GRID["step"], GRID["east"]), 4),
            })
            col, west = col + 1, west + GRID["step"]
        row, south = row + 1, south + GRID["step"]
    return tiles


def build_query(tile: dict[str, Any], category: str) -> str:
    key, value, _ = CATEGORIES[category]
    bbox = ",".join(str(tile[k]) for k in ("south", "west", "north", "east"))
    if category == "arterial_roads":
        selectors = f'  way["{key}"~"{value}"]({bbox});'
    else:
        selectors = "\n".join(
            f'  {kind}["{key}"="{value}"]({bbox});'
            for kind in ("node", "way", "relation")
        )
    return f"[out:json][timeout:35];\n(\n{selectors}\n);\nout center qt;"


def atomic_json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def valid_payload(payload: Any) -> bool:
    return isinstance(payload, dict) and isinstance(payload.get("elements"), list)


def load_cache(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if valid_payload(payload) else None


def fetch_query(
    session: requests.Session,
    query: str,
    cache_path: Path,
    endpoint_offset: int,
) -> tuple[dict[str, Any] | None, str | None, bool]:
    cached = load_cache(cache_path)
    if cached is not None:
        return cached, None, True

    endpoints = OVERPASS_ENDPOINTS[endpoint_offset:] + OVERPASS_ENDPOINTS[:endpoint_offset]
    errors: list[str] = []
    for endpoint in endpoints:
        for attempt in range(1, RETRIES_PER_ENDPOINT + 1):
            try:
                response = session.post(
                    endpoint, data={"data": query}, headers=HEADERS,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                if response.status_code == 200:
                    payload = response.json()
                    if not valid_payload(payload):
                        raise ValueError("response has no Overpass elements array")
                    atomic_json_write(cache_path, payload)
                    time.sleep(SUCCESS_DELAY_SECONDS)
                    return payload, None, False

                message = f"{endpoint} HTTP {response.status_code}"
                errors.append(message)
                if response.status_code not in RETRYABLE_HTTP_CODES:
                    break
                retry_after = response.headers.get("Retry-After")
                try:
                    wait = min(float(retry_after), 30.0) if retry_after else 0.0
                except ValueError:
                    wait = 0.0
                wait = max(wait, min(2 ** attempt + random.random(), 12.0))
                print(f"    {message}; retrying in {wait:.1f}s")
                time.sleep(wait)
            except (requests.RequestException, ValueError) as exc:
                message = f"{endpoint} {type(exc).__name__}: {exc}"
                errors.append(message)
                if attempt < RETRIES_PER_ENDPOINT:
                    wait = min(2 ** attempt + random.random(), 12.0)
                    print(f"    {message}; retrying in {wait:.1f}s")
                    time.sleep(wait)
    return None, " | ".join(errors[-6:]), False


def download_pbf(session: requests.Session, name: str, url: str) -> Path:
    path = CACHE_DIR / f"{name}-latest.osm.pbf"
    if path.exists() and path.stat().st_size > 1_000_000:
        print(f"Using cached regional extract: {path.name}")
        return path
    part = path.with_suffix(path.suffix + ".part")
    for attempt in range(1, 4):
        existing = part.stat().st_size if part.exists() else 0
        headers = dict(HEADERS)
        if existing:
            headers["Range"] = f"bytes={existing}-"
        try:
            with session.get(url, stream=True, timeout=(10, 60), headers=headers) as response:
                response.raise_for_status()
                append = existing > 0 and response.status_code == 206
                mode = "ab" if append else "wb"
                with part.open(mode) as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            handle.write(chunk)
            part.replace(path)
            print(f"Downloaded {path.name}: {path.stat().st_size / 1_000_000:.1f} MB")
            return path
        except requests.RequestException as exc:
            if attempt == 3:
                raise RuntimeError(f"Could not download fallback {url}: {exc}") from exc
            wait = 2 ** attempt
            print(f"Fallback download retry {attempt}/3 in {wait}s: {exc}")
            time.sleep(wait)
    raise AssertionError("unreachable")


HSTORE_PAIR = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"=>"([^"\\]*(?:\\.[^"\\]*)*)"')


def parse_other_tags(value: Any) -> dict[str, str]:
    if value is None or pd.isna(value):
        return {}
    return {
        key.replace('\\"', '"'): item.replace('\\"', '"')
        for key, item in HSTORE_PAIR.findall(str(value))
    }


def row_tags(row: pd.Series) -> dict[str, str]:
    tags = parse_other_tags(row.get("other_tags"))
    for key in (
        "name", "official_name", "short_name", "operator", "ref", "amenity",
        "power", "highway", "emergency", "healthcare", "voltage", "website", "phone",
    ):
        value = row.get(key)
        if value is not None and not pd.isna(value):
            tags[key] = str(value)
    return tags


def tile_name_for(lat: float, lon: float) -> str:
    row = min(int((lat - GRID["south"]) // GRID["step"]) + 1, 8)
    col = min(int((lon - GRID["west"]) // GRID["step"]) + 1, 3)
    return f"corridor_r{max(row, 1):02d}_c{max(col, 1):02d}"


def parse_pbf_extract(path: Path, source_name: str) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = {name: [] for name in CATEGORIES}
    bbox = (GRID["west"], GRID["south"], GRID["east"], GRID["north"])
    layer_element = {"points": "node", "lines": "way", "multipolygons": "relation"}
    for layer in ("points", "lines", "multipolygons"):
        print(f"Reading {source_name} / {layer} in corridor bbox...")
        frame = pyogrio.read_dataframe(path, layer=layer, bbox=bbox)
        for _, row in frame.iterrows():
            tags = row_tags(row)
            category = None
            if tags.get("amenity") == "hospital":
                category = "hospitals"
            elif tags.get("amenity") == "shelter":
                category = "shelters"
            elif tags.get("amenity") == "school":
                category = "schools"
            elif tags.get("power") == "substation":
                category = "substations"
            elif layer == "lines" and tags.get("highway") in {"motorway", "trunk", "primary"}:
                category = "arterial_roads"
            if category is None:
                continue
            geometry = row.get("geometry")
            if geometry is None or geometry.is_empty:
                continue
            point = geometry if geometry.geom_type == "Point" else geometry.representative_point()
            lat, lon = float(point.y), float(point.x)
            osm_element = layer_element[layer]
            raw_id = row.get("osm_id")
            if layer == "multipolygons" and row.get("osm_way_id") is not None and not pd.isna(row.get("osm_way_id")):
                osm_element, raw_id = "way", row.get("osm_way_id")
            try:
                osm_id = abs(int(raw_id))
            except (TypeError, ValueError):
                continue
            asset_type = CATEGORIES[category][2]
            name = next((tags.get(key) for key in (
                "name", "official_name", "short_name", "operator", "ref"
            ) if tags.get(key)), f"Unnamed {asset_type.replace('_', ' ')}")
            output[category].append({
                "asset_type": asset_type, "name": name, "osm_element": osm_element,
                "osm_id": osm_id, "lat": lat, "lon": lon,
                "operator": tags.get("operator"), "ref": tags.get("ref"),
                "source_tile": tile_name_for(lat, lon), "amenity": tags.get("amenity"),
                "power": tags.get("power"), "highway": tags.get("highway"),
                "emergency": tags.get("emergency"), "healthcare": tags.get("healthcare"),
                "voltage": tags.get("voltage"),
                "website": tags.get("website") or tags.get("contact:website"),
                "phone": tags.get("phone") or tags.get("contact:phone"),
            })
        del frame
    return output


def fetch_pbf_fallback(session: requests.Session) -> dict[str, list[dict[str, Any]]]:
    combined: dict[str, list[dict[str, Any]]] = {name: [] for name in CATEGORIES}
    for name, url in PBF_SOURCES.items():
        path = download_pbf(session, name, url)
        extracted = parse_pbf_extract(path, name)
        for category, records in extracted.items():
            combined[category].extend(records)
    return combined


def coordinates(element: dict[str, Any]) -> tuple[float | None, float | None]:
    if element.get("lat") is not None and element.get("lon") is not None:
        return float(element["lat"]), float(element["lon"])
    center = element.get("center") or {}
    if center.get("lat") is not None and center.get("lon") is not None:
        return float(center["lat"]), float(center["lon"])
    return None, None


def text_value(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).strip() or None


def parse_elements(payload: dict[str, Any], category: str, tile_name: str) -> list[dict[str, Any]]:
    _, _, asset_type = CATEGORIES[category]
    records: list[dict[str, Any]] = []
    for element in payload.get("elements", []):
        lat, lon = coordinates(element)
        if lat is None or lon is None:
            continue
        tags = element.get("tags") or {}
        candidates = [text_value(tags.get(field)) for field in (
            "name", "official_name", "short_name", "operator", "ref"
        )]
        name = next((candidate for candidate in candidates if candidate), None)
        records.append({
            "asset_type": asset_type,
            "name": name or f"Unnamed {asset_type.replace('_', ' ')}",
            "osm_element": text_value(element.get("type")), "osm_id": element.get("id"),
            "lat": lat, "lon": lon, "operator": text_value(tags.get("operator")),
            "ref": text_value(tags.get("ref")), "source_tile": tile_name,
            "amenity": text_value(tags.get("amenity")), "power": text_value(tags.get("power")),
            "highway": text_value(tags.get("highway")), "emergency": text_value(tags.get("emergency")),
            "healthcare": text_value(tags.get("healthcare")), "voltage": text_value(tags.get("voltage")),
            "website": text_value(tags.get("website") or tags.get("contact:website")),
            "phone": text_value(tags.get("phone") or tags.get("contact:phone")),
        })
    return records


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def deduplicate_and_filter(
    records: list[dict[str, Any]], track_points: list[tuple[float, float]]
) -> list[dict[str, Any]]:
    unique: dict[tuple[Any, Any], dict[str, Any]] = {}
    for record in records:
        key = (record["osm_element"], record["osm_id"])
        if key in unique:
            tiles = set(str(unique[key]["source_tile"]).split(";")) | {str(record["source_tile"])}
            unique[key]["source_tile"] = ";".join(sorted(tiles))
        else:
            unique[key] = record
    kept: list[dict[str, Any]] = []
    for record in unique.values():
        distance = min(
            haversine_km(record["lat"], record["lon"], track_lat, track_lon)
            for track_lat, track_lon in track_points
        )
        if distance <= MAX_TRACK_DISTANCE_KM:
            record["distance_to_track_km"] = round(distance, 3)
            kept.append(record)
    return sorted(kept, key=lambda row: (row["asset_type"], row["name"], row["osm_id"]))


def to_geojson(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
            "properties": {key: value for key, value in row.items() if key not in {"lat", "lon"}},
        } for row in records],
    }


def save_records(name: str, records: list[dict[str, Any]]) -> None:
    columns = BASE_COLUMNS + sorted({key for row in records for key in row} - set(BASE_COLUMNS))
    with (OUTPUT_DIR / f"{name}.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    atomic_json_write(OUTPUT_DIR / f"{name}.geojson", to_geojson(records))


def main() -> None:
    print("SURGESIGHT OSM EXTRACTION")
    print(
        f"Prototype corridor: <= {MAX_TRACK_DISTANCE_KM:.0f} km from the observed track "
        "(not an official wind-radius estimate)"
    )
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    track = load_track()
    track_points = list(zip(track["LAT"].astype(float), track["LON"].astype(float)))
    tiles = build_tiles()
    print(f"Track observations: {len(track_points)}; 0.5-degree tiles: {len(tiles)}")

    raw: dict[str, list[dict[str, Any]]] = {name: [] for name in CATEGORIES}
    failures: list[dict[str, str]] = []
    cache_hits = downloads = 0
    fallback_used = False
    consecutive_failures = 0
    with requests.Session() as session:
        query_number = 0
        for tile in tiles:
            for category in CATEGORIES:
                query_number += 1
                cache_path = CACHE_DIR / f"{tile['name']}_{category}.json"
                print(f"[{query_number:03d}/{len(tiles) * len(CATEGORIES)}] {tile['name']} / {category}")
                payload, error, cached = fetch_query(
                    session, build_query(tile, category), cache_path,
                    endpoint_offset=(query_number - 1) % len(OVERPASS_ENDPOINTS),
                )
                if payload is None:
                    failures.append({
                        "tile": str(tile["name"]), "category": category,
                        "error": error or "unknown error",
                    })
                    print("    FAILED; continuing")
                    consecutive_failures += 1
                    if consecutive_failures >= MAX_CONSECUTIVE_OVERPASS_FAILURES:
                        print("Public Overpass is persistently unavailable; switching to regional PBF fallback.")
                        fallback_used = True
                        break
                    continue
                consecutive_failures = 0
                cache_hits += int(cached)
                downloads += int(not cached)
                parsed = parse_elements(payload, category, str(tile["name"]))
                raw[category].extend(parsed)
                print(f"    {'cache' if cached else 'downloaded'}: {len(parsed)} records")
                if query_number >= OVERPASS_PROBE_QUERY_BUDGET:
                    print(
                        "Public Overpass is responding too slowly for the hackathon time budget; "
                        "switching to compact regional PBF extracts."
                    )
                    fallback_used = True
                    break
            if fallback_used:
                break

        if fallback_used or failures:
            fallback_used = True
            fallback_records = fetch_pbf_fallback(session)
            for category, records in fallback_records.items():
                raw[category].extend(records)

    final = {name: deduplicate_and_filter(records, track_points) for name, records in raw.items()}
    for name, records in final.items():
        save_records(name, records)
    critical_assets = [
        row for name in ("hospitals", "shelters", "schools", "substations") for row in final[name]
    ]
    critical_assets = deduplicate_and_filter(critical_assets, track_points)
    save_records("critical_assets", critical_assets)

    counts = {name: len(records) for name, records in final.items()}
    summary = {
        "scenario": "Cyclone Michaung 2023",
        "source": "OpenStreetMap contributors via Overpass API and regional OSM PBF extracts",
        "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "screening_track_distance_km": MAX_TRACK_DISTANCE_KM,
        "screening_warning": "Prototype screening distance; not an official wind-radius estimate.",
        "overpass_endpoints": OVERPASS_ENDPOINTS,
        "fallback_used": fallback_used,
        "fallback_reason": (
            "Public Overpass latency exceeded the hackathon time budget during validation."
            if fallback_used else None
        ),
        "fallback_sources": PBF_SOURCES if fallback_used else {},
        "grid": GRID, "tile_count": len(tiles),
        "query_count_planned": len(tiles) * len(CATEGORIES),
        "overpass_queries_processed": query_number,
        "cache_hits": cache_hits, "downloads": downloads,
        "counts": {**counts, "critical_assets": len(critical_assets),
                   "major_road_elements": counts["arterial_roads"]},
        "failed_query_count": len(failures), "failures": failures,
        "notes": [
            "OSM is community-maintained and coverage varies.",
            "Schools remain schools and are not treated as official cyclone shelters.",
            "Road ways use Overpass center points for reliability.",
            "Objects are deduplicated by OSM element type plus OSM id.",
        ],
    }
    atomic_json_write(OUTPUT_DIR / "osm_summary.json", summary)

    print("\nSURGESIGHT_OSM_OK\n")
    print(f"Hospitals: {counts['hospitals']:,}")
    print(f"Emergency shelters: {counts['shelters']:,}")
    print(f"Schools: {counts['schools']:,}")
    print(f"Substations: {counts['substations']:,}")
    print(f"Critical assets: {len(critical_assets):,}")
    print(f"Major road elements: {counts['arterial_roads']:,}")
    print(f"Failed tile/category queries: {len(failures):,}")
    print(f"Cache hits: {cache_hits:,}; new downloads: {downloads:,}")
    if failures:
        print("\nFailed queries (rerun retries only these):")
        for failure in failures:
            print(f"- {failure['tile']} / {failure['category']}: {failure['error']}")


if __name__ == "__main__":
    main()
