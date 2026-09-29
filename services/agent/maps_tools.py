"""Google Maps Platform tools (WP8). Places content is transient: results carry place_id, and nothing is stored."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from pydantic import BaseModel, Field

from services import maps
from services.agent.builtin_tools import jsonable
from services.agent.tools import error_result, ok_result, tool
from services.store import get_store, new_run_id

ROUTE_LABEL = (
    "Modelled exposure only: kilometres of each route inside the footprint of the highest-priority assets "
    "(triage tiers 1 and 2, 3 km around each asset). 'Lower modelled exposure' does not mean safe or open; "
    "roads are not scored and live traffic or closures are not considered for this ranking."
)


class GeocodeArgs(BaseModel):
    query: str = Field(description="Place name or address, for example the landfall text from a bulletin: 'near Bapatla, Andhra Pradesh'.")


@tool("geocode_place", agent_scopes={"forecast", "comms", "impact"})
def geocode_tool(args: GeocodeArgs) -> Any:
    """Turn a place name or address (such as a bulletin's landfall location or a district) into coordinates with
    Google Geocoding. 'APPROXIMATE' location_type means a town or area centre, not a precise point."""
    return ok_result("geocode_place", jsonable(maps.geocode(args.query)), source="google_maps:geocoding")


class NearbyPlacesArgs(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    place_type: str = Field(default="hospital", description="Google place type, for example hospital, pharmacy, fire_station, police, school, gas_station.")
    radius_m: float = Field(default=3000, gt=0, le=20000)


@tool("nearby_places", agent_scopes={"impact", "department"})
def nearby_places_tool(args: NearbyPlacesArgs) -> Any:
    """Find real-world places (Google Places) of a type near a point: name, address, phone, business status. Use it
    to check what exists around an asset or to find alternatives. Results are transient Google content."""
    places = maps.nearby_places(args.lat, args.lon, args.place_type, args.radius_m)
    return ok_result("nearby_places", jsonable({"count": len(places), "places": places, "note": "Google Places content is shown, not stored."}),
                     source="google_maps:places")


class EnrichAssetArgs(BaseModel):
    name: str = Field(description="Exact asset name from a tool result, for example a hospital name.")


@tool("enrich_asset", agent_scopes={"impact", "department"})
def enrich_asset_tool(args: EnrichAssetArgs) -> Any:
    """Look up a scored asset in Google Places for its phone number, address and business status (for example
    whether a hospital is operational). Only assets whose exact name is in the scored data are accepted."""
    from services.assets import load_all_assets

    assets = load_all_assets()
    hit = assets[assets["name"].fillna("").str.lower() == args.name.strip().lower()]
    if hit.empty:
        return error_result("enrich_asset", f"No scored asset is named '{args.name}'. Use a name from a tool result.")
    row = hit.iloc[0]
    place = maps.enrich_asset(row["name"], float(row["lat"]), float(row["lon"]))
    data = {"asset": row["name"], "asset_type": row["asset_type"], "osm_element": row["osm_element"], "osm_id": int(row["osm_id"]),
            "place": place, "note": "Matched by name near the asset; verify before relying on the phone number."}
    return ok_result("enrich_asset", jsonable(data), source="google_maps:places")


class RouteAccessArgs(BaseModel):
    origin: str = Field(description="Where the route starts: an exact asset name (for example a fire station), 'lat,lon', or a place name.")
    destination: str = Field(description="Where the route ends: an exact asset name (for example a hospital), 'lat,lon', or a place name.")


@tool("route_access", agent_scopes={"impact", "department"})
def route_access_tool(args: RouteAccessArgs) -> Any:
    """Compare driving routes (with alternatives) between two points by how many kilometres of each lie inside the
    modelled high-risk footprint. Use it for questions such as fire station to hospital access or a depot to a
    substation. Reports 'lower modelled exposure', never 'safe'; roads are not scored and live closures are unknown."""
    origin, destination = maps.resolve_point(args.origin), maps.resolve_point(args.destination)
    routes = maps.compute_routes(origin, destination, maps.high_risk_footprint())
    if not routes:
        return error_result("route_access", "Google Routes returned no driving route between these points.")
    slim = [{k: v for k, v in r.items() if k != "polyline"} for r in routes]
    data = {"origin": {k: origin[k] for k in ("query", "lat", "lon", "source")}, "destination": {k: destination[k] for k in ("query", "lat", "lon", "source")},
            "routes": slim, "lowest_modelled_exposure_route": slim[0]["route"], "label": ROUTE_LABEL}
    return ok_result("route_access", jsonable(data), source="google_maps:routes+risk_v2")


class DistrictWeatherArgs(BaseModel):
    district: str | None = Field(default=None, description="One district name, or omit for every district in the corridor.")


@tool("district_weather", agent_scopes={"forecast", "impact"})
def district_weather_tool(args: DistrictWeatherArgs) -> Any:
    """Current weather (Google Weather API) at each district centroid: condition, temperature, rain probability
    and wind. These are conditions RIGHT NOW, not the 2023 Michaung event, so use them for a live-mode overview only."""
    centroids = maps.district_centroids()
    if args.district:
        centroids = centroids[centroids["district"].str.lower() == args.district.lower()]
        if centroids.empty:
            return error_result("district_weather", f"Unknown district '{args.district}'.")
    with ThreadPoolExecutor(max_workers=6) as pool:
        weather = list(pool.map(lambda r: maps.current_conditions(r.lat, r.lon), centroids.itertuples()))
    rows = [{"district": c.district, "state": c.state, **w} for c, w in zip(centroids.itertuples(), weather)]
    return ok_result("district_weather", jsonable({"districts": rows, "note": "Live conditions now, not the 2023 Michaung event."}), source="google_maps:weather")
