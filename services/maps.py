"""Google Maps Platform backend calls (WP8): Geocoding, Places, Routes and Weather.

Places terms: only ``place_id`` may be stored, so Places content is returned to the caller and never written to the
run store or a cache. Route exposure is a modelled screening figure, never a statement that a road is safe.
"""

from __future__ import annotations

import math
import os
import re
from typing import Any

from dotenv import load_dotenv
import numpy as np
import pandas as pd
import requests
from shapely.geometry import LineString, shape
from shapely.ops import transform

TIMEOUT = 30
COORD_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


class MapsError(RuntimeError):
    pass


def _key() -> str:
    load_dotenv()
    key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not key:
        raise MapsError("GOOGLE_MAPS_API_KEY is not set")
    return key


def _json(response: requests.Response) -> dict[str, Any]:
    if response.status_code >= 400:
        try:
            message = response.json().get("error", {}).get("message", response.text)
        except ValueError:
            message = response.text
        raise MapsError(f"HTTP {response.status_code}: {message}"[:300])
    return response.json() if response.content else {}


# ---------------------------------------------------------------- geocoding

def geocode(query: str, *, region: str = "in") -> dict[str, Any]:
    """Coordinates for a place name or address (for example a bulletin's landfall text)."""
    data = _json(requests.get("https://maps.googleapis.com/maps/api/geocode/json",
                              params={"address": query, "region": region, "key": _key()}, timeout=TIMEOUT))
    if data.get("status") != "OK":
        raise MapsError(f"Geocoding {data.get('status')}: {data.get('error_message', query)}")
    top = data["results"][0]
    return {"query": query, "lat": top["geometry"]["location"]["lat"], "lon": top["geometry"]["location"]["lng"],
            "formatted_address": top["formatted_address"], "place_id": top["place_id"],
            "location_type": top["geometry"]["location_type"]}


def resolve_point(text: str) -> dict[str, Any]:
    """'lat,lon', an exact asset name, or free text to geocode."""
    match = COORD_RE.match(text)
    if match:
        return {"query": text, "lat": float(match.group(1)), "lon": float(match.group(2)), "source": "coordinates"}
    from services.assets import load_all_assets

    assets = load_all_assets()
    hit = assets[assets["name"].fillna("").str.lower() == text.strip().lower()]
    if len(hit):
        row = hit.iloc[0]
        return {"query": text, "lat": float(row["lat"]), "lon": float(row["lon"]), "source": f"asset:{row['asset_type']}"}
    found = geocode(text)
    return {**found, "source": "geocoding"}


# ---------------------------------------------------------------- places

def nearby_places(lat: float, lon: float, place_type: str = "hospital", radius_m: float = 3000, max_results: int = 10) -> list[dict[str, Any]]:
    """Places near a point. Content is transient: do not store anything but ``place_id``."""
    body = {"includedTypes": [place_type], "maxResultCount": max_results,
            "locationRestriction": {"circle": {"center": {"latitude": lat, "longitude": lon}, "radius": float(radius_m)}}}
    mask = "places.id,places.displayName,places.formattedAddress,places.location,places.businessStatus,places.nationalPhoneNumber"
    data = _json(requests.post("https://places.googleapis.com/v1/places:searchNearby", json=body, timeout=TIMEOUT,
                               headers={"X-Goog-Api-Key": _key(), "X-Goog-FieldMask": mask}))
    return [_place(p) for p in data.get("places", [])]


def _place(p: dict[str, Any]) -> dict[str, Any]:
    return {"place_id": p.get("id"), "name": (p.get("displayName") or {}).get("text"), "address": p.get("formattedAddress"),
            "lat": (p.get("location") or {}).get("latitude"), "lon": (p.get("location") or {}).get("longitude"),
            "business_status": p.get("businessStatus"), "phone": p.get("nationalPhoneNumber")}


def enrich_asset(name: str, lat: float, lon: float) -> dict[str, Any] | None:
    """Phone, address and business status of the Place that best matches an asset (text search biased to its location)."""
    body = {"textQuery": name, "maxResultCount": 1,
            "locationBias": {"circle": {"center": {"latitude": lat, "longitude": lon}, "radius": 1000.0}}}
    mask = "places.id,places.displayName,places.formattedAddress,places.location,places.businessStatus,places.nationalPhoneNumber"
    data = _json(requests.post("https://places.googleapis.com/v1/places:searchText", json=body, timeout=TIMEOUT,
                               headers={"X-Goog-Api-Key": _key(), "X-Goog-FieldMask": mask}))
    places = data.get("places", [])
    return _place(places[0]) if places else None


# ---------------------------------------------------------------- routes

def decode_polyline(encoded: str) -> list[tuple[float, float]]:
    """Google encoded polyline to (lat, lon) pairs."""
    points, index, lat, lon = [], 0, 0, 0
    while index < len(encoded):
        for is_lon in (False, True):
            shift = result = 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if is_lon:
                lon += delta
            else:
                lat += delta
        points.append((lat / 1e5, lon / 1e5))
    return points


def km_inside(points: list[tuple[float, float]], footprint: dict[str, Any] | None) -> float:
    """Length (km) of a polyline inside a GeoJSON footprint, measured in a local equirectangular projection."""
    if footprint is None or len(points) < 2:
        return 0.0
    lat0 = float(np.mean([p[0] for p in points]))
    kx, ky = 111.32 * math.cos(math.radians(lat0)), 110.57

    def project(x, y, z=None):
        return (np.asarray(x) * kx, np.asarray(y) * ky)

    line = transform(project, LineString([(lon, lat) for lat, lon in points]))
    area = transform(project, shape(footprint))
    return float(line.intersection(area).length)


def compute_routes(origin: dict[str, float], destination: dict[str, float], footprint: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Driving routes (with alternatives) and the km of each inside the modelled footprint, lowest exposure first."""
    body = {"origin": {"location": {"latLng": {"latitude": origin["lat"], "longitude": origin["lon"]}}},
            "destination": {"location": {"latLng": {"latitude": destination["lat"], "longitude": destination["lon"]}}},
            "travelMode": "DRIVE", "computeAlternativeRoutes": True}
    mask = "routes.duration,routes.distanceMeters,routes.polyline.encodedPolyline,routes.description"
    data = _json(requests.post("https://routes.googleapis.com/directions/v2:computeRoutes", json=body, timeout=TIMEOUT,
                               headers={"X-Goog-Api-Key": _key(), "X-Goog-FieldMask": mask}))
    from services.roads import route_exposure

    routes = []
    for i, route in enumerate(data.get("routes", []), start=1):
        points = decode_polyline(route["polyline"]["encodedPolyline"])
        distance_km = route["distanceMeters"] / 1000
        inside = km_inside(points, footprint)
        roads = route_exposure(points) or {}
        routes.append({"route": i, "via": route.get("description"), "distance_km": round(distance_km, 2),
                       "duration_min": round(int(route["duration"].rstrip("s")) / 60, 1),
                       **roads,
                       "km_in_modelled_high_risk_footprint": round(inside, 2),
                       "share_in_footprint_pct": round(100 * inside / distance_km, 1) if distance_km else 0.0,
                       "polyline": points})
    routes.sort(key=lambda r: (r.get("km_most_exposed", 0.0), r.get("km_high_exposure", 0.0),
                               r["km_in_modelled_high_risk_footprint"], r["duration_min"]))
    for rank, r in enumerate(routes, start=1):
        r["exposure_rank"] = rank
    return routes


def high_risk_footprint(rule: str = "triage_tier_1_2", radius_km: float = 3.0) -> dict[str, Any] | None:
    """GeoJSON footprint of the highest-priority assets (relative triage, since absolute v2 classes saturate)."""
    from services.departments import score_all_assets
    from services.exposure import exposure_summary

    return exposure_summary(score_all_assets(), rule=rule, radius_km=radius_km, include_footprint=True).get("footprint_geojson")


# ---------------------------------------------------------------- weather

def current_conditions(lat: float, lon: float) -> dict[str, Any]:
    d = _json(requests.get("https://weather.googleapis.com/v1/currentConditions:lookup", timeout=TIMEOUT,
                           params={"key": _key(), "location.latitude": lat, "location.longitude": lon}))
    return {"time": d.get("currentTime"), "condition": (d.get("weatherCondition") or {}).get("description", {}).get("text"),
            "temperature_c": (d.get("temperature") or {}).get("degrees"),
            "rain_probability_pct": (d.get("precipitation") or {}).get("probability", {}).get("percent"),
            "wind_kmh": (d.get("wind") or {}).get("speed", {}).get("value"),
            "gust_kmh": (d.get("wind") or {}).get("gust", {}).get("value")}


def forecast_hours(lat: float, lon: float, hours: int = 24) -> list[dict[str, Any]]:
    d = _json(requests.get("https://weather.googleapis.com/v1/forecast/hours:lookup", timeout=TIMEOUT,
                           params={"key": _key(), "location.latitude": lat, "location.longitude": lon, "hours": hours}))
    return [{"start": h.get("interval", {}).get("startTime"), "temperature_c": (h.get("temperature") or {}).get("degrees"),
             "rain_probability_pct": (h.get("precipitation") or {}).get("probability", {}).get("percent"),
             "rain_mm": (h.get("precipitation") or {}).get("qpf", {}).get("quantity"),
             "wind_kmh": (h.get("wind") or {}).get("speed", {}).get("value")} for h in d.get("forecastHours", [])]


def district_centroids() -> pd.DataFrame:
    import json

    from services.config import load_region

    data = json.loads(load_region().path("districts").read_text(encoding="utf-8"))
    rows = []
    for f in data["features"]:
        c = shape(f["geometry"]).representative_point()
        rows.append({"district": f["properties"]["district"], "state": f["properties"]["state"], "lat": c.y, "lon": c.x})
    return pd.DataFrame(rows)
