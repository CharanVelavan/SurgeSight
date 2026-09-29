"""Hazard layers tab: river flood susceptibility (MERIT Hydro) and the GFS comparison (WP2.6, WP2.7)."""

from __future__ import annotations

import json

import pandas as pd
import pydeck as pdk
import streamlit as st

from services.config import load_region
from services.hazards.rainfall import rain_inputs
from services.hazards.river_flood import LABEL as RIVER_LABEL, river_flood_frame, summarise
from services.nwp_comparison import LABEL as NWP_LABEL


@st.cache_data(show_spinner="Scoring river flood susceptibility…")
def _river() -> pd.DataFrame:
    region = load_region()
    rain, _ = rain_inputs("forecast")
    return river_flood_frame(rain, pd.read_csv(region.path("scored_assets")))


def _river_section() -> None:
    st.markdown("### River flood susceptibility")
    st.caption(RIVER_LABEL)
    region = load_region()
    if not region.path("river_assets").exists():
        st.info("Run `python scripts/build_river_flood.py` once to cache the MERIT Hydro inputs.")
        return
    frame = _river()
    summary = summarise(frame)
    with st.container(horizontal=True):
        st.metric("Assets within 2 m of a drainage line", f"{summary['near_drainage_hand_lt_2m']:,}", border=True)
        st.metric("River flood index 0.5 or more", f"{summary['index_at_least_0_5']:,}", border=True)
        for kind, count in summary["by_asset_type_index_at_least_0_5"].items():
            st.metric(kind.title(), f"{count:,}", border=True)
    shown = frame.dropna(subset=["lat", "lon"]).copy()
    shown["fill"] = shown["river_flood_index"].map(lambda v: [int(255 * v), int(120 * (1 - v)), int(220 * (1 - v)), 200])
    shown["map_title"] = shown["name"].fillna("Unnamed infrastructure")
    shown["map_line1"] = shown["asset_type"].str.title()
    shown["map_line2"] = shown.apply(lambda r: f"River flood index {r['river_flood_index']:.2f}", axis=1)
    shown["map_line3"] = shown.apply(lambda r: f"Height above drainage {r['hand_m']:.1f} m; rain {r['rain_mm']:.0f} mm", axis=1)
    st.pydeck_chart(pdk.Deck(
        layers=[pdk.Layer("ScatterplotLayer", data=shown, get_position="[lon, lat]", get_fill_color="fill",
                          get_radius=2500, radius_min_pixels=3, radius_max_pixels=8, pickable=True)],
        initial_view_state=pdk.ViewState(latitude=float(shown["lat"].mean()), longitude=float(shown["lon"].mean()), zoom=6.2),
        tooltip={"html": "<b>{map_title}</b><br/>{map_line1}<br/>{map_line2}<br/>{map_line3}",
                 "style": {"backgroundColor": "#152238", "color": "white"}},
        map_style=None,
    ), width="stretch", height=480)
    st.caption("Blue: low susceptibility · Red: high river flood index (heavy forecast rain on land beside a drainage line).")
    metrics = region.path("terrain_summary").parent / "satellite" / "metrics.json"
    if metrics.exists():
        auc = json.loads(metrics.read_text(encoding="utf-8"))["ranking_skill_auc"]
        if "river_flood_index" in auc:
            st.caption(
                f"Against the satellite flood flag: river flood index AUC {auc['river_flood_index']}, "
                f"river susceptibility alone {auc.get('river_susceptibility')}, forecast rain alone {auc['forecast_rain_mm']}, "
                f"terrain flood score {auc['terrain_flood_score']} (0.5 = no skill)."
            )


def _nwp_section() -> None:
    st.markdown("### Independent forecast comparison (NOAA GFS)")
    st.caption(NWP_LABEL)
    path = load_region().path("nwp_comparison")
    if not path.exists():
        st.info("Run `python scripts/build_nwp_comparison.py` once to cache the GFS comparison.")
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for row in data["rows"]:
        gfs = row.get("gfs") or {}
        rows.append({
            "Lead (h)": row["lead_hours"],
            "GFS centre": f"{gfs['lat']:.2f}N {gfs['lon']:.2f}E" if gfs else "not found",
            "GFS peak wind (km/h)": gfs.get("max_wind_kmh"),
            "Kalman centre": f"{row['kalman']['lat']:.2f}N {row['kalman']['lon']:.2f}E" if row.get("kalman") else "",
            "GFS vs Kalman (km)": row.get("gfs_vs_kalman_km"),
            "GFS error vs observed (km)": row.get("gfs_error_km"),
            "Kalman error vs observed (km)": row.get("kalman_error_km"),
            "Observed wind (km/h)": (row.get("observed_validation_only") or {}).get("wind_kmh"),
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption(
        f"Forecast issued {data['cutoff_utc']}. Observed columns are validation only, taken from the later IBTrACS fixes. "
        f"Ensemble per-axis spread at 12 h: {data['ensemble_sigma_km_12h']} km. Kalman covers 24 h."
    )


def render() -> None:
    st.subheader("Hazard layers")
    _river_section()
    st.divider()
    _nwp_section()
