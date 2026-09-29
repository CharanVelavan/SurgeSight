"""'Score this bulletin' panel for the Bulletin Intelligence tab (K1)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from services.bulletin_parser import CycloneBulletin
from services.bulletin_track import InsufficientForecastPointsError, bulletin_to_track
from services.scenario_engine import score_custom_track
from services.agent.builtin_tools import compact_scored_data


def render(parsed_data: dict) -> None:
    st.markdown("**Risk from this bulletin**")
    st.caption(
        "Converts the parsed bulletin into a track and scores all assets with the same v1 screening "
        "model used for the historical Michaung track. Screening indices, not damage probabilities."
    )
    if st.button("Score this bulletin", icon=":material/calculate:", key="score_bulletin"):
        try:
            built = bulletin_to_track(CycloneBulletin.model_validate(parsed_data))
            scored = score_custom_track(built.track_df)
            st.session_state["bulletin_score"] = (built, compact_scored_data(scored))
        except InsufficientForecastPointsError as exc:
            st.session_state.pop("bulletin_score", None)
            st.error(str(exc))
        except Exception as exc:
            st.session_state.pop("bulletin_score", None)
            st.error(f"Could not score the bulletin: {exc}")

    saved = st.session_state.get("bulletin_score")
    if not saved:
        return
    built, data = saved
    for flag in built.flags:
        st.warning(f"Track note: {flag}")
    counts = data["scenario_class_counts"]
    with st.container(horizontal=True):
        for label in ("CRITICAL", "HIGH", "MODERATE", "LOW"):
            st.metric(label.title(), counts.get(label, 0), border=True)
    st.dataframe(built.track_df[["ISO_TIME", "LAT", "LON", "WIND_KMH", "SOURCE"]], hide_index=True, width="stretch")
    st.markdown("**Highest-scoring assets under this bulletin**")
    st.dataframe(pd.DataFrame(data["top_scenario_risk"]), hide_index=True, width="stretch")
