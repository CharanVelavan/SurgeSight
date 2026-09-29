"""Maps & access tab: route exposure between assets, live district weather, place lookups (WP8)."""

from __future__ import annotations

import pandas as pd
import pydeck as pdk
import streamlit as st

from services import maps
from services.agent.maps_tools import ROUTE_LABEL
from services.assets import load_all_assets

ROUTE_COLORS = [[20, 160, 110, 230], [240, 140, 0, 230], [200, 40, 40, 230]]


@st.cache_data(show_spinner=False)
def _names(asset_type: str) -> list[str]:
    assets = load_all_assets()
    return sorted(assets.loc[assets["asset_type"] == asset_type, "name"].dropna().unique().tolist())


def _route_section() -> None:
    st.markdown("### Route access")
    st.caption(ROUTE_LABEL)
    with st.form("route_form"):
        with st.container(horizontal=True):
            origin_type = st.selectbox("From (asset type)", ["fire_station", "police_station", "substation", "shelter", "hospital"], key="route_from_type")
            destination_type = st.selectbox("To (asset type)", ["hospital", "shelter", "substation", "fire_station"], key="route_to_type")
        origin = st.selectbox("Origin", _names(origin_type), key="route_origin")
        destination = st.selectbox("Destination", _names(destination_type), key="route_destination")
        go = st.form_submit_button("Compare routes", type="primary", icon=":material/route:")
    if go:
        try:
            with st.spinner("Asking Google Routes and intersecting with the risk footprint…"):
                o, d = maps.resolve_point(origin), maps.resolve_point(destination)
                routes = maps.compute_routes(o, d, maps.high_risk_footprint())
            st.session_state["route_result"] = (origin, destination, routes)
        except Exception as exc:
            st.error(f"Route lookup failed: {exc}")
    result = st.session_state.get("route_result")
    if not result:
        return
    origin, destination, routes = result
    st.markdown(f"**{origin} → {destination}**")
    st.dataframe(pd.DataFrame([{k: v for k, v in r.items() if k != "polyline"} for r in routes]), hide_index=True, width="stretch")
    layers = [pdk.Layer("PathLayer", data=[{"path": [[lon, lat] for lat, lon in r["polyline"]]}], get_path="path",
                        get_color=ROUTE_COLORS[i % 3], width_min_pixels=5) for i, r in enumerate(routes)]
    first = routes[0]["polyline"][0]
    st.pydeck_chart(pdk.Deck(layers=layers, initial_view_state=pdk.ViewState(latitude=first[0], longitude=first[1], zoom=10), map_style=None),
                    width="stretch", height=420)
    st.caption("Green: lowest modelled exposure · orange and red: more exposure.")


def _weather_section() -> None:
    st.markdown("### District weather now")
    st.caption("Google Weather API at each district centroid. These are today's live conditions, not the 2023 Michaung event.")
    if st.button("Refresh district weather", icon=":material/cloud:", key="weather_go"):
        try:
            from concurrent.futures import ThreadPoolExecutor

            centroids = maps.district_centroids()
            with st.spinner("Reading conditions…"), ThreadPoolExecutor(max_workers=6) as pool:
                weather = list(pool.map(lambda r: maps.current_conditions(r.lat, r.lon), centroids.itertuples()))
            st.session_state["weather"] = pd.DataFrame([{"district": c.district, "state": c.state, **w} for c, w in zip(centroids.itertuples(), weather)])
        except Exception as exc:
            st.error(f"Weather lookup failed: {exc}")
    if (table := st.session_state.get("weather")) is not None:
        st.dataframe(table.drop(columns=["time"]), hide_index=True, width="stretch")


def _geocode_section() -> None:
    st.markdown("### Geocode a place")
    text = st.text_input("Place or landfall text", "Bapatla, Andhra Pradesh", key="geocode_text")
    if st.button("Find coordinates", icon=":material/pin_drop:", key="geocode_go"):
        try:
            found = maps.geocode(text)
            st.success(f"{found['formatted_address']}: {found['lat']:.4f}, {found['lon']:.4f} ({found['location_type'].lower()})")
        except Exception as exc:
            st.error(f"Geocoding failed: {exc}")


def render() -> None:
    st.subheader("Maps & access")
    _route_section()
    st.divider()
    _weather_section()
    st.divider()
    _geocode_section()
