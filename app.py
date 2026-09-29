"""SurgeSight Michaung impact and infrastructure vulnerability dashboard."""

import json
import mimetypes
from pathlib import Path

import pandas as pd
import pydeck as pdk
import streamlit as st

from services.advisory import AUDIENCES, LANGUAGES, RoleAdvisory, generate_role_advisory
from services.config import load_region
from ui.agent_console import render as render_agent_console
from ui.hazard_layers import render as render_hazard_layers
from ui.satellite_validation import render as render_satellite_validation
from ui.bulletin_scoring import render as render_bulletin_scoring
from services.bulletin_parser import parse_bulletin_file, parse_bulletin_text
from services.scenario_engine import run_scenario
from services.scenario_explainer import explain_scenario
from services.tts import TEXT_ONLY_LANGUAGES, audio_supported, synthesize_advisory
from services.track_forecast_explainer import explain_forecast_difference
from services.track_forecaster import (
    DEFAULT_DEMO_CUTOFF,
    DISCLAIMER as TRACK_DISCLAIMER,
    FORECAST_LABEL,
    HORIZONS_HOURS,
    MODEL_KALMAN,
    MODEL_LABELS,
    MODEL_WIND,
    SCIENTIFIC_NOTES,
    ellipse_polygon,
    forecast_cutoffs,
    observations_until,
    public_points,
    reference_track_window,
    run_experimental_forecast,
)
from services.wind_provider import WindDataUnavailable, load_wind_grid


st.set_page_config(page_title="SurgeSight", page_icon="🌀", layout="wide")

_REGION = load_region()
TRACK_FILE = _REGION.path("track")
SCORED_ASSETS_FILE = _REGION.path("scored_assets")
RISK_SUMMARY_FILE = _REGION.path("risk_summary")

RISK_COLORS = {
    "LOW": [46, 160, 67, 190],
    "MODERATE": [245, 180, 0, 210],
    "HIGH": [239, 108, 0, 220],
    "CRITICAL": [198, 40, 40, 235],
}
ASSET_RADII = {"hospital": 5000, "shelter": 4200, "school": 3000, "substation": 3800}
TRACK_BACKTEST_FILE = _REGION.path("track_backtest")
TRACK_STYLE = {
    "reference": {"color": [40, 110, 220, 235], "width": 6, "pattern": None},
    MODEL_KALMAN: {"color": [240, 140, 0, 240], "width": 5, "pattern": (3, 2)},
    MODEL_WIND: {"color": [20, 160, 110, 240], "width": 5, "pattern": (1, 2)},
}


@st.cache_data
def load_track(path: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame["ISO_TIME"] = pd.to_datetime(frame["ISO_TIME"])
    return frame


@st.cache_data
def load_scored_assets(path: str) -> pd.DataFrame:
    return pd.read_csv(path)


@st.cache_data
def load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


@st.cache_resource(max_entries=1, show_spinner="Loading cached GFS environmental winds…")
def load_forecast_wind_grid(path: str):
    return load_wind_grid(pd.read_csv(path), allow_download=False)


@st.cache_resource(max_entries=24, show_spinner="Running experimental track models…")
def run_track_forecast(path: str, cutoff: str) -> dict:
    frame = pd.read_csv(path)
    try:
        wind_grid = load_forecast_wind_grid(path)
    except WindDataUnavailable:
        wind_grid = None
    return run_experimental_forecast(frame, pd.Timestamp(cutoff), wind_grid=wind_grid)


def styled_path_segments(coordinates: list[list[float]], pattern: tuple[int, int] | None) -> list[dict]:
    """Split a path into dash/dot pieces (pydeck has no native dash style here)."""

    if pattern is None or len(coordinates) < 2:
        return [{"path": coordinates}]
    on, off = pattern
    pieces_per_leg = 12
    dense: list[list[float]] = []
    for start, end in zip(coordinates[:-1], coordinates[1:]):
        for step in range(pieces_per_leg):
            fraction = step / pieces_per_leg
            dense.append([start[0] + (end[0] - start[0]) * fraction,
                          start[1] + (end[1] - start[1]) * fraction])
    dense.append(coordinates[-1])
    segments = []
    for index in range(0, len(dense) - 1, on + off):
        piece = dense[index:index + on + 1]
        if len(piece) >= 2:
            segments.append({"path": piece})
    return segments


def format_position(lat: float, lon: float) -> str:
    return f"{lat:.2f}°N, {lon:.2f}°E"


def format_delta(value: int) -> str:
    return f"{value:+,}" if value else "±0"


def format_population(value: object) -> str:
    try:
        return f"{int(float(value)):,}"
    except (TypeError, ValueError):
        return "N/A"


def apply_north_demo_preset() -> None:
    st.session_state["scenario_north_shift"] = 30
    st.session_state["scenario_east_shift"] = 0
    st.session_state["scenario_intensity_change"] = 0


if not TRACK_FILE.exists():
    st.error(f"Missing track file: {TRACK_FILE}")
    st.stop()

track = load_track(str(TRACK_FILE))
assets_available = SCORED_ASSETS_FILE.exists() and RISK_SUMMARY_FILE.exists()
assets = load_scored_assets(str(SCORED_ASSETS_FILE)) if assets_available else pd.DataFrame()
risk_summary = load_json(str(RISK_SUMMARY_FILE)) if assets_available else {}

st.title("SurgeSight")
st.caption("Cyclone impact and infrastructure vulnerability forecaster")
st.subheader("Cyclone Michaung · 2023")

if assets_available:
    with st.container(horizontal=True):
        st.metric(
            "Population in analysis region",
            format_population(risk_summary.get("population_exposed_screening_region")),
            help="WorldPop estimate for the Earth Engine Michaung screening region.",
            icon=":material/groups:", border=True,
        )
        st.metric(
            "Critical assets", f"{len(assets):,}",
            help="Hospitals, mapped emergency shelters, schools, and electrical substations in the screening corridor.",
            icon=":material/domain:", border=True,
        )
        st.metric(
            "High-risk hospitals", f"{risk_summary.get('high_risk_hospitals', 0):,}",
            help="Hospitals classified HIGH or CRITICAL by the prototype screening index.",
            icon=":material/local_hospital:", border=True,
        )
        st.metric(
            "High-risk substations", f"{risk_summary.get('high_risk_substations', 0):,}",
            help="Substations classified HIGH or CRITICAL by the prototype screening index.",
            icon=":material/electric_bolt:", border=True,
        )
else:
    latest = track.iloc[-1]
    with st.container(horizontal=True):
        st.metric("Track observations", len(track), border=True)
        st.metric("Maximum wind", f"{track['WIND_KMH'].max():.0f} km/h", border=True)
        st.metric("Minimum pressure", f"{track['PRESSURE_HPA'].min():.0f} hPa", border=True)
        st.metric("Latest position", f"{latest['LAT']:.2f}, {latest['LON']:.2f}", border=True)
    st.warning(
        "Scored infrastructure outputs are not available yet. Run "
        "`python scripts/fetch_osm_infrastructure.py` and then "
        "`python scripts/score_infrastructure_risk.py`."
    )

track_map = track.copy()
track_map["map_title"] = track_map["ISO_TIME"].dt.strftime("%Y-%m-%d %H:%M UTC")
track_map["map_line1"] = "Observed cyclone track"
track_map["map_line2"] = track_map["WIND_KMH"].map(lambda value: f"Wind: {value:.1f} km/h")
track_map["map_line3"] = track_map["PRESSURE_HPA"].map(
    lambda value: f"Pressure: {value:.0f} hPa" if pd.notna(value) else "Pressure: N/A"
)

layers = [
    pdk.Layer(
        "PathLayer",
        data=[{"path": track[["LON", "LAT"]].values.tolist()}],
        get_path="path", get_color=[45, 110, 210, 210], get_width=5,
        width_min_pixels=3, pickable=False,
    ),
    pdk.Layer(
        "ScatterplotLayer", data=track_map, get_position="[LON, LAT]",
        get_fill_color=[45, 110, 210, 220], get_line_color=[255, 255, 255, 220],
        get_radius=15000, radius_min_pixels=4, radius_max_pixels=10,
        line_width_min_pixels=1, stroked=True, pickable=True,
    ),
]

if assets_available and not assets.empty:
    asset_map = assets.copy()
    asset_map["risk_color"] = asset_map["risk_class"].map(RISK_COLORS)
    asset_map["marker_radius"] = asset_map["asset_type"].map(ASSET_RADII).fillna(3000)
    asset_map["map_title"] = asset_map["name"].fillna("Unnamed infrastructure")
    asset_map["map_line1"] = asset_map["asset_type"].str.replace("_", " ").str.title()
    asset_map["map_line2"] = asset_map.apply(
        lambda row: f"Risk: {row['risk_class']} ({row['combined_risk_score']:.2f})", axis=1
    )
    asset_map["map_line3"] = asset_map["distance_to_track_km"].map(
        lambda value: f"Distance to track: {value:.1f} km"
    )
    layers.append(
        pdk.Layer(
            "ScatterplotLayer", data=asset_map, get_position="[lon, lat]",
            get_fill_color="risk_color", get_line_color=[255, 255, 255, 220],
            get_radius="marker_radius", radius_min_pixels=4, radius_max_pixels=11,
            line_width_min_pixels=1, stroked=True, pickable=True,
        )
    )

view_lat = float(pd.concat([track["LAT"], assets["lat"]]) .mean()) if assets_available else float(track["LAT"].mean())
view_lon = float(pd.concat([track["LON"], assets["lon"]]) .mean()) if assets_available else float(track["LON"].mean())
deck = pdk.Deck(
    layers=layers,
    initial_view_state=pdk.ViewState(latitude=view_lat, longitude=view_lon, zoom=5.2, pitch=0),
    tooltip={
        "html": "<b>{map_title}</b><br/>{map_line1}<br/>{map_line2}<br/>{map_line3}",
        "style": {"backgroundColor": "#152238", "color": "white"},
    },
    map_style=None,
)

st.pydeck_chart(deck, width="stretch", height=610)
if assets_available:
    st.caption(
        "Asset risk: 🟢 LOW · 🟡 MODERATE · 🟠 HIGH · 🔴 CRITICAL. "
        "Marker color shows risk class; select a marker for score and track distance."
    )

if assets_available:
    with st.expander("Infrastructure risk data"):
        display_columns = [
            "asset_type", "name", "risk_class", "combined_risk_score",
            "distance_to_track_km", "nearest_track_wind_kmh", "elevation_m",
            "water_occurrence_pct", "osm_element", "osm_id",
        ]
        st.dataframe(
            assets[display_columns], hide_index=True, width="stretch",
            column_config={
                "combined_risk_score": st.column_config.ProgressColumn(
                    "Risk score", min_value=0.0, max_value=1.0, format="%.3f"
                ),
                "distance_to_track_km": st.column_config.NumberColumn(
                    "Distance to track (km)", format="%.1f"
                ),
                "nearest_track_wind_kmh": st.column_config.NumberColumn(
                    "Nearest-track wind (km/h)", format="%.1f"
                ),
                "elevation_m": st.column_config.NumberColumn("Elevation (m)", format="%.1f"),
                "water_occurrence_pct": st.column_config.NumberColumn(
                    "Water occurrence (%)", format="%.1f"
                ),
            },
        )

with st.expander("Track data"):
    st.dataframe(
        track[["ISO_TIME", "LAT", "LON", "WIND_KMH", "PRESSURE_HPA"]],
        width="stretch", hide_index=True,
    )

st.divider()
intelligence_tab, advisory_tab, simulator_tab, track_forecast_tab, agent_tab, satellite_tab, hazard_tab = st.tabs(
    [
        "Bulletin Intelligence", "Role-specific advisories", "Forecast Simulator",
        "Experimental Track Forecast", "Agent console", "Satellite validation", "Hazard layers",
    ],
    on_change="rerun",
    key="intelligence_tabs",
)

if intelligence_tab.open:
    with intelligence_tab:
        st.subheader("Bulletin Intelligence")
        st.caption(
            "Parse a live bulletin as an additional input. This does not replace the historical "
            "IBTrACS Michaung scenario shown above."
        )
        with st.form("bulletin_parser_form"):
            bulletin_text = st.text_area(
                "Paste bulletin text",
                height=220,
                placeholder="Paste an IMD-style cyclone bulletin here…",
            )
            bulletin_upload = st.file_uploader(
                "Or upload a bulletin",
                type=["txt", "pdf", "png", "jpg", "jpeg", "webp", "heic", "heif"],
                max_upload_size=50,
                help="Text, PDF, PNG, JPEG, WebP, HEIC, or HEIF; maximum 50 MB.",
            )
            analyze_bulletin = st.form_submit_button(
                "Analyze bulletin", type="primary", icon=":material/document_search:"
            )

        if analyze_bulletin:
            try:
                with st.spinner("Extracting bulletin facts with Gemini…"):
                    if bulletin_upload is not None:
                        guessed_type = mimetypes.guess_type(bulletin_upload.name)[0]
                        parsed = parse_bulletin_file(
                            bulletin_upload.getvalue(),
                            bulletin_upload.type or guessed_type or "application/octet-stream",
                            bulletin_upload.name,
                        )
                    elif bulletin_text.strip():
                        parsed = parse_bulletin_text(bulletin_text)
                    else:
                        raise ValueError("Paste bulletin text or upload a bulletin file")
                st.session_state["parsed_bulletin"] = parsed.model_dump(mode="json")
                st.success("Bulletin parsed into validated structured data.")
            except Exception as exc:
                st.error(f"Bulletin analysis failed: {exc}")

        parsed_data = st.session_state.get("parsed_bulletin")
        if parsed_data:
            position = parsed_data.get("current_position") or {}
            movement = parsed_data.get("movement") or {}
            with st.container(horizontal=True):
                st.metric("Cyclone", parsed_data.get("cyclone_name") or "Unavailable", border=True)
                st.metric("Bulletin time", parsed_data.get("bulletin_time") or "Unavailable", border=True)
                position_text = (
                    f"{position.get('lat')}, {position.get('lon')}"
                    if position.get("lat") is not None and position.get("lon") is not None
                    else "Unavailable"
                )
                st.metric("Current position", position_text, border=True)
                wind = parsed_data.get("maximum_sustained_wind_kmph")
                st.metric("Sustained wind", f"{wind:g} km/h" if wind is not None else "Unavailable", border=True)
                pressure = parsed_data.get("central_pressure_hpa")
                st.metric("Central pressure", f"{pressure:g} hPa" if pressure is not None else "Unavailable", border=True)

            st.markdown(
                f"**Movement:** {movement.get('direction') or 'Unavailable'}"
                + (
                    f" at {movement['speed_kmph']:g} km/h"
                    if movement.get("speed_kmph") is not None else ""
                )
            )
            landfall = parsed_data.get("landfall") or {}
            st.markdown(
                "**Landfall:** "
                + " · ".join(
                    str(value) for value in (
                        landfall.get("location_text"),
                        landfall.get("expected_time"),
                        landfall.get("confidence_text"),
                    ) if value
                )
                if any(landfall.values()) else "**Landfall:** Unavailable in bulletin"
            )
            if parsed_data.get("rainfall_summary"):
                st.markdown(f"**Rainfall:** {parsed_data['rainfall_summary']}")

            forecast = parsed_data.get("forecast_track") or []
            if forecast:
                st.markdown("**Forecast track**")
                st.dataframe(pd.DataFrame(forecast), hide_index=True, width="stretch")
            st.markdown("**Warnings**")
            warnings = parsed_data.get("warnings") or []
            if warnings:
                for warning in warnings:
                    st.markdown(f"- {warning}")
            else:
                st.caption("No warnings were explicitly extracted from the bulletin.")
            with st.expander("Raw structured JSON"):
                st.json(parsed_data)
            render_bulletin_scoring(parsed_data)

if advisory_tab.open:
    with advisory_tab:
        st.subheader("Grounded role-specific advisories")
        st.caption(
            "Gemini interprets calculated scores only. It does not calculate or change risk."
        )
        with st.form("advisory_form"):
            audience = st.segmented_control(
                "Audience", AUDIENCES, default=AUDIENCES[0], required=True, width="stretch"
            )
            language = st.segmented_control(
                "Language", list(LANGUAGES), default="English", required=True
            )
            generate_advisory = st.form_submit_button(
                "Generate advisory", type="primary", icon=":material/campaign:"
            )

        if generate_advisory:
            try:
                with st.spinner("Generating grounded advisory…"):
                    result = generate_role_advisory(str(audience), str(language))
                st.session_state["role_advisory"] = result.model_dump(mode="json")
                st.session_state["role_advisory_language"] = str(language)
                st.session_state.pop("role_advisory_audio", None)
                st.success("Advisory generated from deterministic risk results.")
            except Exception as exc:
                st.error(f"Advisory generation failed: {exc}")

        advisory_data = st.session_state.get("role_advisory")
        if advisory_data:
            st.metric("Screening severity", advisory_data["severity"], border=True)
            st.markdown(f"**Audience:** {advisory_data['audience']}")
            if advisory_data.get("headline"):
                st.markdown(f"#### {advisory_data['headline']}")
            st.markdown(advisory_data["situation_summary"])
            if advisory_data.get("instruction"):
                st.markdown(f"**Instruction:** {advisory_data['instruction']}")
            st.markdown("**Priority actions**")
            for action in advisory_data.get("priority_actions", []):
                st.markdown(f"- {action}")
            st.markdown("**Critical assets supplied to the advisory**")
            st.dataframe(
                pd.DataFrame(advisory_data.get("critical_assets", [])),
                hide_index=True,
                width="stretch",
            )
            st.markdown("**Monitoring priorities**")
            for priority in advisory_data.get("monitoring_priorities", []):
                st.markdown(f"- {priority}")
            st.info(advisory_data["disclaimer"], icon=":material/info:")

            advisory_language = st.session_state.get("role_advisory_language", "English")
            if not audio_supported(advisory_language):
                st.caption(TEXT_ONLY_LANGUAGES[advisory_language])
            elif st.button("Play community alert", icon=":material/volume_up:"):
                try:
                    with st.spinner("Synthesizing community alert…"):
                        advisory_object = RoleAdvisory.model_validate(advisory_data)
                        audio = synthesize_advisory(
                            advisory_object,
                            st.session_state.get("role_advisory_language", "English"),
                        )
                    st.session_state["role_advisory_audio"] = audio
                except Exception as exc:
                    st.error(f"Text-to-speech failed: {exc}")
            if audio := st.session_state.get("role_advisory_audio"):
                st.audio(audio, format="audio/mp3")
            with st.expander("Raw advisory JSON"):
                st.json(advisory_data)

if simulator_tab.open:
    with simulator_tab:
        st.subheader("Forecast Simulator")
        st.caption(
            "Shift the observed track and adjust wind intensity. All scenario scores are "
            "recalculated deterministically; Gemini is used only for an optional explanation."
        )
        st.session_state.setdefault("scenario_north_shift", 0)
        st.session_state.setdefault("scenario_east_shift", 0)
        st.session_state.setdefault("scenario_intensity_change", 0)
        st.button(
            "30 km North",
            icon=":material/north:",
            on_click=apply_north_demo_preset,
            help="Set the hackathon preset: +30 km north, 0 km east/west, 0% intensity change.",
        )
        with st.form("scenario_form"):
            north_shift = st.slider(
                "North / South Track Shift",
                min_value=-50,
                max_value=50,
                step=1,
                format="%d km",
                key="scenario_north_shift",
                help="Negative values move the track south; positive values move it north.",
            )
            east_shift = st.slider(
                "East / West Track Shift",
                min_value=-50,
                max_value=50,
                step=1,
                format="%d km",
                key="scenario_east_shift",
                help="Negative values move the track west; positive values move it east.",
            )
            intensity_change = st.slider(
                "Cyclone Intensity",
                min_value=-20,
                max_value=20,
                step=1,
                format="%d%%",
                key="scenario_intensity_change",
            )
            simulate = st.form_submit_button(
                "SIMULATE SCENARIO", type="primary", icon=":material/model_training:"
            )

        if simulate:
            try:
                with st.spinner("Recomputing deterministic infrastructure risk…"):
                    scenario_assets, shifted_track, scenario_summary = run_scenario(
                        north_shift, east_shift, intensity_change, save_outputs=True
                    )
                st.session_state["scenario_assets"] = scenario_assets
                st.session_state["scenario_track"] = shifted_track
                st.session_state["scenario_summary"] = scenario_summary
                st.session_state.pop("scenario_explanation", None)
                st.success(
                    f"Scenario simulated in {scenario_summary['runtime_seconds']:.3f} seconds."
                )
            except Exception as exc:
                st.error(f"Scenario simulation failed: {exc}")

        scenario_assets = st.session_state.get("scenario_assets")
        shifted_track = st.session_state.get("scenario_track")
        scenario_summary = st.session_state.get("scenario_summary")
        if scenario_assets is not None and shifted_track is not None and scenario_summary:
            st.markdown("### Baseline vs scenario")
            baseline_column, scenario_column = st.columns(2)
            with baseline_column:
                with st.container(border=True):
                    st.markdown("**BASELINE**")
                    st.metric("Critical assets", scenario_summary["baseline_critical_assets"])
                    st.metric(
                        "High + Critical",
                        scenario_summary["baseline_high_or_critical_assets"],
                    )
                    st.metric(
                        "Hospitals at High+",
                        scenario_summary["baseline_high_or_critical_hospitals"],
                    )
                    st.metric(
                        "Substations at High+",
                        scenario_summary["baseline_high_or_critical_substations"],
                    )
            with scenario_column:
                with st.container(border=True):
                    st.markdown("**SCENARIO**")
                    st.metric(
                        "Critical assets",
                        scenario_summary["scenario_critical_assets"],
                        delta=(
                            scenario_summary["scenario_critical_assets"]
                            - scenario_summary["baseline_critical_assets"]
                        ),
                        delta_color="inverse",
                    )
                    st.metric(
                        "High + Critical",
                        scenario_summary["scenario_high_or_critical_assets"],
                        delta=(
                            scenario_summary["scenario_high_or_critical_assets"]
                            - scenario_summary["baseline_high_or_critical_assets"]
                        ),
                        delta_color="inverse",
                    )
                    st.metric(
                        "Hospitals at High+",
                        scenario_summary["scenario_high_or_critical_hospitals"],
                        delta=(
                            scenario_summary["scenario_high_or_critical_hospitals"]
                            - scenario_summary["baseline_high_or_critical_hospitals"]
                        ),
                        delta_color="inverse",
                    )
                    st.metric(
                        "Substations at High+",
                        scenario_summary["scenario_high_or_critical_substations"],
                        delta=(
                            scenario_summary["scenario_high_or_critical_substations"]
                            - scenario_summary["baseline_high_or_critical_substations"]
                        ),
                        delta_color="inverse",
                    )

            with st.container(horizontal=True):
                st.metric(
                    "Assets with increased risk",
                    scenario_summary["assets_risk_increased"],
                    border=True,
                )
                st.metric(
                    "Assets with decreased risk",
                    scenario_summary["assets_risk_decreased"],
                    border=True,
                )
                st.metric(
                    "Newly High+ hospitals",
                    scenario_summary["newly_high_risk_hospitals"],
                    border=True,
                )
                st.metric(
                    "Newly High+ substations",
                    scenario_summary["newly_high_risk_substations"],
                    border=True,
                )

            newly_at_risk = scenario_assets[
                scenario_assets["status"].isin(["NEWLY_HIGH_RISK", "NEWLY_CRITICAL"])
            ].sort_values(["risk_delta", "scenario_risk_score"], ascending=[False, False])
            st.markdown("### Newly at risk")
            if newly_at_risk.empty:
                st.info("No assets newly entered HIGH or CRITICAL risk in this scenario.")
            else:
                st.dataframe(
                    newly_at_risk[
                        [
                            "name", "asset_type", "baseline_risk_class",
                            "scenario_risk_class", "baseline_risk_score",
                            "scenario_risk_score", "risk_delta", "distance_to_track_km",
                        ]
                    ].head(50),
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "baseline_risk_score": st.column_config.NumberColumn(format="%.3f"),
                        "scenario_risk_score": st.column_config.NumberColumn(format="%.3f"),
                        "risk_delta": st.column_config.NumberColumn(format="%+.3f"),
                        "distance_to_track_km": st.column_config.NumberColumn(
                            "Distance to shifted track (km)", format="%.1f"
                        ),
                    },
                )

            scenario_map = scenario_assets.copy()
            scenario_map["scenario_color"] = scenario_map["scenario_risk_class"].map(RISK_COLORS)
            scenario_map["marker_radius"] = (
                scenario_map["asset_type"].map(ASSET_RADII).fillna(3000)
            )
            scenario_map["map_title"] = scenario_map["name"].fillna("Unnamed infrastructure")
            scenario_map["map_line1"] = scenario_map["asset_type"].str.replace("_", " ").str.title()
            scenario_map["map_line2"] = scenario_map.apply(
                lambda row: (
                    f"Baseline: {row['baseline_risk_class']} ({row['baseline_risk_score']:.3f})"
                ),
                axis=1,
            )
            scenario_map["map_line3"] = scenario_map.apply(
                lambda row: (
                    f"Scenario: {row['scenario_risk_class']} ({row['scenario_risk_score']:.3f})"
                ),
                axis=1,
            )
            scenario_map["map_line4"] = scenario_map.apply(
                lambda row: (
                    f"Delta: {row['risk_delta']:+.3f}; shifted-track distance: "
                    f"{row['distance_to_track_km']:.1f} km"
                ),
                axis=1,
            )
            increased_assets = scenario_map[scenario_map["risk_delta"] > 0]
            simulator_layers = [
                pdk.Layer(
                    "PathLayer",
                    data=[{"path": track[["LON", "LAT"]].values.tolist()}],
                    get_path="path", get_color=[40, 110, 220, 210], get_width=5,
                    width_min_pixels=3,
                ),
                pdk.Layer(
                    "PathLayer",
                    data=[{"path": shifted_track[["LON", "LAT"]].values.tolist()}],
                    get_path="path", get_color=[210, 35, 120, 230], get_width=7,
                    width_min_pixels=4,
                ),
                pdk.Layer(
                    "ScatterplotLayer", data=scenario_map, get_position="[lon, lat]",
                    get_fill_color="scenario_color", get_line_color=[255, 255, 255, 180],
                    get_radius="marker_radius", radius_min_pixels=3, radius_max_pixels=9,
                    line_width_min_pixels=1, stroked=True, pickable=True,
                ),
                pdk.Layer(
                    "ScatterplotLayer", data=increased_assets, get_position="[lon, lat]",
                    get_fill_color=[255, 60, 20, 230], get_line_color=[255, 235, 80, 255],
                    get_radius="marker_radius * 1.4", radius_min_pixels=6,
                    radius_max_pixels=14, line_width_min_pixels=2, stroked=True,
                    pickable=True,
                ),
            ]
            simulator_deck = pdk.Deck(
                layers=simulator_layers,
                initial_view_state=pdk.ViewState(
                    latitude=float(scenario_map["lat"].mean()),
                    longitude=float(scenario_map["lon"].mean()),
                    zoom=6.0,
                    pitch=0,
                ),
                tooltip={
                    "html": (
                        "<b>{map_title}</b><br/>{map_line1}<br/>{map_line2}<br/>"
                        "{map_line3}<br/>{map_line4}"
                    ),
                    "style": {"backgroundColor": "#152238", "color": "white"},
                },
                map_style=None,
            )
            st.markdown("### Scenario map")
            st.pydeck_chart(simulator_deck, width="stretch", height=610)
            st.caption(
                "Blue: baseline track · Magenta: shifted scenario track · "
                "Orange/yellow outline: asset risk increased."
            )

            if st.button(
                "Explain Operational Impact", icon=":material/auto_awesome:"
            ):
                try:
                    with st.spinner("Explaining deterministic scenario results…"):
                        explanation = explain_scenario(scenario_assets, scenario_summary)
                    st.session_state["scenario_explanation"] = explanation.model_dump(mode="json")
                except Exception as exc:
                    st.error(f"Scenario explanation failed: {exc}")

            explanation_data = st.session_state.get("scenario_explanation")
            if explanation_data:
                st.markdown(f"### {explanation_data['headline']}")
                st.markdown(explanation_data["operational_impact"])
                st.markdown("**Key changes**")
                for item in explanation_data.get("key_changes", []):
                    st.markdown(f"- {item}")
                st.markdown("**Operational considerations**")
                for item in explanation_data.get("operational_considerations", []):
                    st.markdown(f"- {item}")
                st.info(explanation_data["disclaimer"], icon=":material/info:")
                with st.expander("Raw scenario explanation JSON"):
                    st.json(explanation_data)

if track_forecast_tab.open:
    with track_forecast_tab:
        st.subheader(FORECAST_LABEL)
        st.warning(
            "**Experimental forecast — not an official meteorological forecast.** "
            "IMD bulletins remain authoritative. This historical replay uses only IBTrACS "
            "fixes and GFS winds available at or before the selected cutoff.",
            icon=":material/science:",
        )
        tf_cutoffs = forecast_cutoffs(track, require_lead_hours=max(HORIZONS_HOURS))
        tf_default = DEFAULT_DEMO_CUTOFF if DEFAULT_DEMO_CUTOFF in tf_cutoffs else tf_cutoffs[-1]
        with st.container(horizontal=True, vertical_alignment="bottom"):
            tf_cutoff = st.selectbox(
                "Forecast cutoff (UTC)",
                tf_cutoffs,
                index=tf_cutoffs.index(tf_default),
                format_func=lambda value: value.strftime("%Y-%m-%d %H:%M"),
                key="track_forecast_cutoff",
                help="Only original IBTrACS fixes at or before this time are used.",
            )
            tf_horizon = st.segmented_control(
                "Forecast horizon",
                list(HORIZONS_HOURS),
                default=24,
                required=True,
                format_func=lambda value: f"{value}h",
                key="track_forecast_horizon",
            )

        try:
            tf_result = run_track_forecast(str(TRACK_FILE), tf_cutoff.isoformat())
        except Exception as exc:
            st.error(f"Experimental track forecast failed: {exc}")
            tf_result = None

        if tf_result is not None:
            tf_summary = tf_result["summary"]
            tf_forecasts = tf_result["forecasts"]
            tf_impacts = tf_result["impacts"]
            if tf_summary["wind_model_status"] != "ok":
                st.info(tf_summary["wind_model_status"], icon=":material/air:")
            tf_reference = {item["lead_hours"]: item for item in tf_summary["reference_positions"]}

            st.markdown("### Track model")
            with st.container(horizontal=True):
                tf_ref_point = tf_reference.get(tf_horizon)
                with st.container(border=True):
                    st.markdown(":blue[**Observed reference (IBTrACS)**]")
                    st.metric(
                        f"Position at +{tf_horizon}h",
                        format_position(tf_ref_point["lat"], tf_ref_point["lon"]) if tf_ref_point else "N/A",
                    )
                    st.caption(f"Valid {tf_ref_point['timestamp'] if tf_ref_point else 'N/A'} UTC")
                for tf_model, tf_color in ((MODEL_KALMAN, "orange"), (MODEL_WIND, "green")):
                    if tf_model not in tf_summary["models"]:
                        continue
                    tf_model_summary = tf_summary["models"][tf_model]
                    tf_point = next(
                        item for item in tf_model_summary["forecast"]
                        if item["lead_hours"] == tf_horizon
                    )
                    tf_error = tf_model_summary["verification_error_km"].get(f"{tf_horizon}h")
                    with st.container(border=True):
                        st.markdown(f":{tf_color}[**{MODEL_LABELS[tf_model]}**]")
                        st.metric(
                            f"Predicted position at +{tf_horizon}h",
                            format_position(tf_point["lat"], tf_point["lon"]),
                        )
                        st.metric(
                            "90% uncertainty radius", f"{tf_point['uncertainty_radius_km']:.0f} km"
                        )
                        st.metric(
                            "Track error in replay",
                            f"{tf_error:.1f} km" if tf_error is not None else "N/A",
                            help="Great-circle distance to the later IBTrACS fix.",
                        )

            tf_layers = []
            tf_full_reference = track[["LON", "LAT"]].values.tolist()
            tf_layers.append(pdk.Layer(
                "PathLayer", data=[{"path": tf_full_reference}], get_path="path",
                get_color=[40, 110, 220, 70], get_width=3, width_min_pixels=2,
            ))
            tf_window = reference_track_window(track, tf_cutoff)
            tf_layers.append(pdk.Layer(
                "PathLayer", data=[{"path": tf_window[["LON", "LAT"]].values.tolist()}],
                get_path="path", get_color=TRACK_STYLE["reference"]["color"],
                get_width=TRACK_STYLE["reference"]["width"], width_min_pixels=4,
            ))
            tf_history = observations_until(track, tf_cutoff)
            tf_layers.append(pdk.Layer(
                "ScatterplotLayer", data=tf_history, get_position="[LON, LAT]",
                get_fill_color=[40, 110, 220, 230], get_radius=9000, radius_min_pixels=3,
            ))
            tf_markers = []
            if tf_ref_point:
                tf_markers.append({
                    "lon": tf_ref_point["lon"], "lat": tf_ref_point["lat"],
                    "color": TRACK_STYLE["reference"]["color"],
                    "map_title": f"Observed IBTrACS fix +{tf_horizon}h",
                    "map_line1": format_position(tf_ref_point["lat"], tf_ref_point["lon"]),
                    "map_line2": tf_ref_point["timestamp"],
                })
            for tf_model, tf_forecast in tf_forecasts.items():
                tf_style = TRACK_STYLE[tf_model]
                tf_points = public_points(tf_forecast)
                tf_layers.append(pdk.Layer(
                    "PolygonLayer",
                    data=[{"polygon": ellipse_polygon(tf_forecast, tf_horizon)}],
                    get_polygon="polygon",
                    get_fill_color=tf_style["color"][:3] + [35],
                    get_line_color=tf_style["color"][:3] + [200],
                    line_width_min_pixels=1, stroked=True, filled=True,
                ))
                tf_path = tf_points[tf_points["lead_hours"] <= tf_horizon][["lon", "lat"]].values.tolist()
                tf_layers.append(pdk.Layer(
                    "PathLayer", data=styled_path_segments(tf_path, tf_style["pattern"]),
                    get_path="path", get_color=tf_style["color"], get_width=tf_style["width"],
                    width_min_pixels=3, cap_rounded=True,
                ))
                tf_row = tf_forecast.at_lead(tf_horizon)
                tf_markers.append({
                    "lon": float(tf_row["lon"]), "lat": float(tf_row["lat"]),
                    "color": tf_style["color"],
                    "map_title": f"{MODEL_LABELS[tf_model]} +{tf_horizon}h (experimental)",
                    "map_line1": format_position(float(tf_row["lat"]), float(tf_row["lon"])),
                    "map_line2": f"90% radius {tf_row['uncertainty_radius_km']:.0f} km",
                })
            tf_layers.append(pdk.Layer(
                "ScatterplotLayer", data=pd.DataFrame(tf_markers), get_position="[lon, lat]",
                get_fill_color="color", get_line_color=[255, 255, 255, 255], get_radius=12000,
                radius_min_pixels=6, radius_max_pixels=12, line_width_min_pixels=2,
                stroked=True, pickable=True,
            ))
            tf_center = tf_history.iloc[-1]
            st.pydeck_chart(
                pdk.Deck(
                    layers=tf_layers,
                    initial_view_state=pdk.ViewState(
                        latitude=float(tf_center["LAT"]) + 0.8,
                        longitude=float(tf_center["LON"]) - 0.5,
                        zoom=6.0, pitch=0,
                    ),
                    tooltip={
                        "html": "<b>{map_title}</b><br/>{map_line1}<br/>{map_line2}",
                        "style": {"backgroundColor": "#152238", "color": "white"},
                    },
                    map_style=None,
                ),
                width="stretch", height=560,
            )
            st.caption(
                "Blue solid: observed IBTrACS reference (bold to cutoff + 24h; dots = fixes used) · "
                "Orange dashed: position-only Kalman · Green dotted: wind-informed experimental · "
                f"Shaded ellipses: 90% uncertainty at +{tf_horizon}h."
            )

            st.markdown("### Backtest error")
            if TRACK_BACKTEST_FILE.exists():
                tf_backtest = load_json(str(TRACK_BACKTEST_FILE))
                tf_metric = st.segmented_control(
                    "Error statistic",
                    ["mean_km", "median_km", "rmse_km", "p90_km"],
                    default="mean_km", required=True,
                    format_func=lambda value: {
                        "mean_km": "Mean", "median_km": "Median",
                        "rmse_km": "RMSE", "p90_km": "90th percentile",
                    }[value],
                    key="track_backtest_metric",
                )
                tf_table = pd.DataFrame({
                    f"{lead}h": [
                        tf_backtest["summary"][model][f"{lead}h"][tf_metric]
                        for model in (MODEL_KALMAN, MODEL_WIND)
                    ]
                    for lead in HORIZONS_HOURS
                }, index=[MODEL_LABELS[MODEL_KALMAN], MODEL_LABELS[MODEL_WIND]])
                st.dataframe(
                    tf_table, width="stretch",
                    column_config={
                        f"{lead}h": st.column_config.NumberColumn(f"{lead}h (km)", format="%.1f")
                        for lead in HORIZONS_HOURS
                    },
                )
                tf_cases = tf_backtest["valid_forecast_cases"]
                tf_verdicts = "; ".join(
                    f"{lead}: wind-informed {item['mean_error_difference_km_wind_minus_kalman']:+.1f} km "
                    f"vs Kalman (better in {item['wind_better_cases']}/{item['paired_cases']} cases)"
                    for lead, item in tf_backtest["comparison"].items()
                )
                st.caption(
                    f"Leakage-free replay on Cyclone Michaung: {tf_cases['6h']}/{tf_cases['12h']}/"
                    f"{tf_cases['24h']} cases at 6/12/24h. Mean-error difference — {tf_verdicts}. "
                    "Single-storm sample; not a general skill estimate."
                )
            else:
                tf_backtest = None
                st.info(
                    "Run `python scripts/backtest_track_forecast.py` to compute backtest errors.",
                    icon=":material/info:",
                )

            st.markdown("### Impact comparison")
            if tf_impacts:
                tf_track_items = tf_impacts["tracks"]
                tf_rows = {
                    "high_plus_assets": "High+ assets",
                    "critical_assets": "Critical assets",
                    "high_plus_hospitals": "High+ hospitals",
                    "high_plus_substations": "High+ substations",
                }
                tf_impact_table = pd.DataFrame({
                    item["label"]: [
                        f"{item[key]:,}" + (
                            f" ({format_delta(item['delta_vs_reference'][key])})"
                            if "delta_vs_reference" in item else ""
                        )
                        for key in tf_rows
                    ]
                    for item in tf_track_items.values()
                }, index=list(tf_rows.values()))
                st.table(tf_impact_table)
                st.caption(
                    f"Deterministic SurgeSight risk engine, unchanged weights. Track window: "
                    f"{tf_impacts['track_window']}. {tf_impacts['intensity_note']} "
                    "Deltas are relative to the observed reference. Many assets sit near the "
                    "HIGH threshold, so class counts are sensitive to track position."
                )

            with st.expander("Method and limitations", icon=":material/menu_book:"):
                for note in SCIENTIFIC_NOTES:
                    st.markdown(f"- {note}")
                if MODEL_WIND in tf_summary["models"]:
                    tf_steer = tf_summary["models"][MODEL_WIND]["cutoff_steering"]
                    st.markdown(
                        f"- Steering flow at cutoff: {tf_steer['speed_ms']:.1f} m/s toward "
                        f"{tf_steer['toward_bearing_deg']:.0f}° (GFS, valid ≤ cutoff)."
                    )
                if tf_summary.get("wind_source"):
                    st.caption(f"Wind data: {tf_summary['wind_source']['source']}")

            if tf_backtest is not None and MODEL_WIND in tf_summary["models"]:
                if st.button("Explain Forecast Difference", icon=":material/auto_awesome:"):
                    try:
                        with st.spinner("Explaining deterministic forecast differences…"):
                            tf_explanation = explain_forecast_difference(
                                tf_summary, tf_backtest, int(tf_horizon)
                            )
                        st.session_state["track_forecast_explanation"] = {
                            "key": (tf_cutoff.isoformat(), int(tf_horizon)),
                            "data": tf_explanation.model_dump(mode="json"),
                        }
                    except Exception as exc:
                        st.error(f"Forecast explanation failed: {exc}")
                tf_saved = st.session_state.get("track_forecast_explanation")
                if tf_saved and tf_saved["key"] == (tf_cutoff.isoformat(), int(tf_horizon)):
                    tf_data = tf_saved["data"]
                    with st.container(border=True):
                        st.markdown(f"**{tf_data['headline']}**")
                        st.markdown(tf_data["forecast_difference"])
                        st.markdown(tf_data["impact_difference"])
                        st.markdown(tf_data["uncertainty_note"])
                        for item in tf_data.get("caveats", []):
                            st.markdown(f"- {item}")
                        st.markdown(f"**Measured backtest:** {tf_data['backtest_verdict']}")
                        st.info(tf_data["disclaimer"], icon=":material/info:")

            st.caption(TRACK_DISCLAIMER)

st.caption(
    "Sources: NOAA IBTrACS, OpenStreetMap contributors, USGS SRTM, JRC Global Surface Water, "
    "WorldPop, and NOAA GFS via Open-Meteo. Screening prototype only—not an operational cyclone damage model."
)

if agent_tab.open:
    with agent_tab:
        render_agent_console()

if satellite_tab.open:
    with satellite_tab:
        render_satellite_validation()

if hazard_tab.open:
    with hazard_tab:
        render_hazard_layers()
