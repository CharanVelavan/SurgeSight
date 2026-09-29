"""Satellite validation tab: observed flood vs screening, metrics and the Gemini review."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from services.config import load_region
from services.risk_model_v2 import score_v2
from services.satellite_validation import (
    FLOOD_ASSETS_FILE, cached_review, compute_metrics, load_images, load_observed,
)


@st.cache_data(show_spinner="Scoring assets…")
def _metrics() -> dict:
    region = load_region()
    frame, _ = score_v2(pd.read_csv(region.path("track")), pd.read_csv(region.path("scored_assets")))
    observed, meta = load_observed()
    return compute_metrics(frame, observed, meta)


def render() -> None:
    st.subheader("Satellite validation")
    if not FLOOD_ASSETS_FILE.exists():
        st.info("Run `python scripts/build_satellite_validation.py` once to cache the satellite inputs.")
        return
    metrics = _metrics()
    st.caption(metrics["note"])
    st.warning(
        f"Sentinel-1 radar did not image this area after landfall, so the observed flood signal comes from "
        f"{metrics['sensor'].replace('sentinel', 'Sentinel-')} optical water mapping. {metrics['method']}.",
        icon=":material/satellite_alt:",
    )
    images = load_images()
    with st.container(horizontal=True):
        for key, caption in (("flood", "Observed flood signal"), ("rain", "Observed rainfall"), ("screening", "Screening result")):
            if key in images:
                st.image(images[key], caption=caption, width=300)
    with st.container(horizontal=True):
        st.metric("Assets observed", f"{metrics['assets_observed']:,}", f"{metrics['asset_coverage_pct']}% of assets", border=True)
        st.metric("With flood signal", f"{metrics['flooded_share_of_observed']:.1%}", border=True)
        st.metric("v1 HIGH+ hit rate", metrics["v1_high_plus"]["hit_rate"], border=True)
        st.metric("v2 HIGH+ hit rate", metrics["v2_high_plus"]["hit_rate"], border=True)
    st.markdown("**How well each score ranks flooded assets above unflooded ones** (AUC: 0.5 = no skill)")
    skill = pd.Series(metrics["ranking_skill_auc"], name="AUC").sort_values(ascending=False)
    st.bar_chart(skill, horizontal=True)
    st.markdown("**HIGH-or-above versus observed flooding**")
    st.dataframe(pd.DataFrame({"v1": metrics["v1_high_plus"], "v2": metrics["v2_high_plus"]}), width="stretch")
    with st.expander("By asset type and district"):
        st.dataframe(pd.DataFrame(metrics["by_asset_type"]), hide_index=True, width="stretch")
        st.dataframe(pd.DataFrame(metrics["by_district"]), hide_index=True, width="stretch")

    st.markdown("**Gemini review: where did the screening miss?**")
    if st.button("Review the maps with Gemini", icon=":material/auto_awesome:", key="sat_review"):
        try:
            with st.spinner("Gemini is comparing the maps and metrics…"):
                review, cached = cached_review(metrics, images)
            st.session_state["sat_review"] = review.model_dump()
            st.caption("Loaded from cache." if cached else "Fresh review generated.")
        except Exception as exc:
            st.error(f"Review failed: {exc}")
    review = st.session_state.get("sat_review")
    if review:
        st.markdown(review["summary"])
        for title, key in (("Missed areas", "missed_areas"), ("Over-flagged areas", "over_flagged_areas"),
                           ("Likely causes", "likely_causes"), ("Model improvements", "model_improvements"),
                           ("Data limitations", "data_limitations")):
            if review.get(key):
                with st.expander(title, expanded=key in {"missed_areas", "over_flagged_areas"}):
                    for item in review[key]:
                        st.markdown(f"- {item}")
