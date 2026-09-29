"""Agent console tab: ask the Gemini orchestrator, watch its tool trace live."""

from __future__ import annotations

import mimetypes
from pathlib import Path

import streamlit as st

from services.agent.builtin_tools import register_bulletin_file, register_bulletin_text
from services.agent.orchestrator import TraceStep, run_agent
from services.store import get_store

SAMPLE_BULLETIN = Path("data/raw/sample_michaung_bulletin.txt")
LANGUAGES = ["English", "Tamil", "Telugu"]
EXAMPLES = {
    "What if it shifts 30 km north?": "If Michaung shifts 30 km north, which hospitals become newly high risk? Top 5 only.",
    "Experimental forecast check": "How well would the experimental track forecast issued at 2023-12-03 12:00 have done, and does it change hospital impact?",
    "Score the bulletin for Health": "Score the attached bulletin and tell Health what to prepare.",
}


def _step_line(step: TraceStep) -> str:
    icon = ":material/check_circle:" if step.ok else ":material/error:"
    args = ", ".join(f"{k}={v}" for k, v in step.args.items()) or "no arguments"
    return f"{icon} **{step.tool}** ({args}) · {step.duration_ms} ms  \n{step.summary}"


def _bulletin_run_id(source: str, upload, pasted: str) -> str | None:
    if source == "Sample bulletin":
        return register_bulletin_text(SAMPLE_BULLETIN.read_text(encoding="utf-8"))
    if source == "Upload" and upload is not None:
        guessed = mimetypes.guess_type(upload.name)[0]
        return register_bulletin_file(upload.getvalue(), upload.type or guessed or "application/octet-stream", upload.name)
    if source == "Paste text" and pasted.strip():
        return register_bulletin_text(pasted)
    return None


def render() -> None:
    st.subheader("Agent console")
    st.caption(
        "Gemini decides which deterministic tools to run and reads their results. It never calculates "
        "a risk number, and every number in the answer is checked against tool output. Nothing is sent "
        "to anyone from here."
    )

    example = st.pills("Examples", list(EXAMPLES), key="agent_example", label_visibility="collapsed")
    if example and st.session_state.get("agent_example_applied") != example:
        st.session_state["agent_question"] = EXAMPLES[example]
        st.session_state["agent_example_applied"] = example

    with st.form("agent_form"):
        question = st.text_area("Question for the incident commander", key="agent_question", height=100)
        with st.container(horizontal=True):
            language = st.selectbox("Answer language", LANGUAGES, key="agent_language")
            source = st.segmented_control(
                "Bulletin", ["None", "Sample bulletin", "Upload", "Paste text"],
                default="None", key="agent_bulletin_source",
            )
        upload = st.file_uploader(
            "Bulletin file", type=["txt", "pdf", "png", "jpg", "jpeg", "webp", "heic", "heif"],
            key="agent_upload",
        ) if source == "Upload" else None
        pasted = st.text_area("Bulletin text", key="agent_paste", height=140) if source == "Paste text" else ""
        submitted = st.form_submit_button("Ask", type="primary", icon=":material/smart_toy:")

    if submitted:
        if not question.strip():
            st.warning("Type a question first.")
        else:
            try:
                bulletin_id = _bulletin_run_id(source or "None", upload, pasted)
                with st.status("Incident commander working…", expanded=True) as status:
                    answer, trace = run_agent(
                        question,
                        context_run_ids=[bulletin_id] if bulletin_id else None,
                        language=language,
                        on_step=lambda step: st.markdown(_step_line(step)),
                    )
                    status.update(label=f"Done · {len(trace)} steps", state="complete", expanded=False)
                st.session_state["agent_result"] = (question, answer, trace)
            except Exception as exc:
                st.error(f"Agent failed: {exc}")

    result = st.session_state.get("agent_result")
    if not result:
        return
    question, answer, trace = result
    st.markdown(answer.answer_markdown)
    if answer.grounded:
        st.badge("All numbers found in tool output", icon=":material/verified:", color="green")
    else:
        st.badge(
            f"Removed unsupported numbers: {', '.join(answer.ungrounded_numbers)}",
            icon=":material/warning:", color="orange",
        )
    if answer.recommended_actions:
        st.markdown("**Recommended actions**")
        for action in answer.recommended_actions:
            st.markdown(f"- {action}")
    if answer.uncertainty_notes:
        with st.expander("Uncertainty and limits"):
            for note in answer.uncertainty_notes:
                st.markdown(f"- {note}")
    store = get_store()
    for run_id in answer.run_ids:
        if run_id.startswith("audio-"):
            st.audio(store.get_blob(run_id, "audio.mp3"), format="audio/mp3")
    with st.expander(f"Tool trace ({len(trace)} steps) and run ids"):
        for step in trace:
            st.markdown(_step_line(step))
        st.caption("Run ids: " + ", ".join(answer.run_ids or ["none"]))
