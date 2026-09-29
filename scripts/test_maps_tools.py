"""Maps Platform tools (WP8): polyline maths offline, then live Geocoding, Places, Routes and Weather."""

from __future__ import annotations

import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import services.agent  # noqa: F401
from services import maps
from services.agent.tools import TOOLS, execute_tool


def test_offline() -> None:
    assert maps.decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@") == [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]
    box = {"type": "Polygon", "coordinates": [[[80.0, 13.0], [80.1, 13.0], [80.1, 13.1], [80.0, 13.1], [80.0, 13.0]]]}
    inside = maps.km_inside([(13.05, 79.9), (13.05, 80.2)], box)  # crosses the box west to east
    assert abs(inside - 0.1 * 111.32 * 0.9741) < 0.3, inside
    assert maps.km_inside([(20.0, 70.0), (20.0, 70.1)], box) == 0.0 and maps.km_inside([(13, 80)], box) == 0.0 and maps.km_inside([(13, 80), (13, 80.1)], None) == 0.0
    assert maps.resolve_point("13.08, 80.27")["source"] == "coordinates" and maps.resolve_point("Tiruvottiyur Harbour")["source"].startswith("asset:")
    for name in ("geocode_place", "nearby_places", "enrich_asset", "route_access", "district_weather"):
        assert name in TOOLS
    bad, _ = execute_tool("enrich_asset", {"name": "No Such Hospital 999"})
    assert not bad.ok and "No scored asset" in bad.error
    print("maps offline ok")


def test_live() -> None:
    if os.getenv("SURGESIGHT_OFFLINE") == "1":
        print("SKIPPED live Maps calls (SURGESIGHT_OFFLINE=1)")
        return
    geo, _ = execute_tool("geocode_place", {"query": "Bapatla, Andhra Pradesh"})
    assert geo.ok and abs(geo.data["lat"] - 15.9) < 0.3 and abs(geo.data["lon"] - 80.47) < 0.3, geo.error
    near, _ = execute_tool("nearby_places", {"lat": 13.0827, "lon": 80.2707, "place_type": "hospital", "radius_m": 2000})
    assert near.ok and near.data["count"] > 0 and near.data["places"][0]["place_id"]
    assert near.run_id is None, "Places content must not be stored"
    rich, _ = execute_tool("enrich_asset", {"name": "Punarjeevan Hospital"})
    assert rich.ok and rich.data["asset_type"] == "hospital", rich.error
    route, _ = execute_tool("route_access", {"origin": "13.0827,80.2707", "destination": "Tiruvottiyur Harbour"})
    assert route.ok, route.error
    routes = route.data["routes"]
    assert routes and all(r["distance_km"] > 0 and 0 <= r["share_in_footprint_pct"] <= 100.5 for r in routes)
    assert [r["km_in_modelled_high_risk_footprint"] for r in routes] == sorted(r["km_in_modelled_high_risk_footprint"] for r in routes)
    assert "not mean safe" in route.data["label"] and "polyline" not in routes[0]
    weather, _ = execute_tool("district_weather", {"district": "Chennai"})
    assert weather.ok and weather.data["districts"][0]["temperature_c"] is not None, weather.error
    print("maps live ok")


if __name__ == "__main__":
    test_offline()
    test_live()
    print("SURGESIGHT_MAPS_TOOLS_OK")
