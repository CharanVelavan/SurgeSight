"""Dispatch & CAP tab: draft an alert, queue it, approve or reject, send (dry run by default) (WP5.3)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from services.advisory import AUDIENCES, LANGUAGES, generate_role_advisory
from services.cap import build_cap_alert
from services.config import get_settings
from services.dispatch import router


def _draft_section() -> None:
    st.markdown("### Draft an alert")
    with st.form("dispatch_draft_form"):
        with st.container(horizontal=True):
            audience = st.selectbox("Department", AUDIENCES, key="dispatch_audience")
            language = st.selectbox("Language", list(LANGUAGES), key="dispatch_language")
            channel = st.segmented_control("Channel", ["chat", "email", "push"], default="chat", key="dispatch_channel")
        submitted = st.form_submit_button("Draft advisory and CAP alert", type="primary", icon=":material/edit_note:")
    if submitted:
        try:
            with st.spinner("Drafting the advisory and building the CAP alert…"):
                advisory = generate_role_advisory(audience, language)
                cap_xml = build_cap_alert(advisory, language)
            st.session_state["dispatch_draft"] = {"advisory": advisory.model_dump(), "cap": cap_xml, "channel": channel, "language": language}
        except Exception as exc:
            st.error(f"Drafting failed: {exc}")
    draft = st.session_state.get("dispatch_draft")
    if not draft:
        return
    adv = draft["advisory"]
    st.markdown(f"**{adv['headline']}**")
    st.markdown(adv["situation_summary"])
    if adv.get("instruction"):
        st.markdown(f"**Instruction:** {adv['instruction']}")
    with st.expander("CAP 1.2 alert (status: Exercise, validated against the OASIS schema)"):
        st.code(draft["cap"], language="xml")
    if st.button("Queue for approval", icon=":material/outbox:", key="dispatch_queue"):
        body = "\n\n".join(p for p in (adv["situation_summary"], adv.get("instruction", ""),
                                       "\n".join(f"- {a}" for a in adv["priority_actions"]), adv["disclaimer"]) if p)
        item = router.queue_dispatch(adv["audience"], draft["channel"], adv["headline"] or adv["audience"], body,
                                     attachments=[{"name": "alert.cap.xml", "mime": "application/xml", "text": draft["cap"]}])
        st.success(f"Queued {item.id}. It will not be sent until approved.")
        st.session_state.pop("dispatch_draft", None)
        st.rerun()


def _queue_section() -> None:
    st.markdown("### Queue and log")
    items = router.list_dispatches()
    if not items:
        st.caption("No dispatches yet.")
        return
    st.dataframe(pd.DataFrame([{
        "id": d.id, "status": d.status, "department": d.department, "channel": d.channel, "subject": d.subject,
        "recipients": ", ".join(d.recipients) or "(test space)", "created": d.created_at_utc[:19],
    } for d in items]), hide_index=True, width="stretch")
    pending = [d for d in items if d.status in {"pending_approval", "approved"}]
    for d in pending[:10]:
        with st.container(border=True):
            st.markdown(f"**{d.subject}** · {d.department} · {d.channel} · `{d.status}`")
            st.caption(d.body[:400])
            with st.container(horizontal=True):
                if d.status == "pending_approval":
                    if st.button("Approve", key=f"ok_{d.id}", icon=":material/check:"):
                        router.approve(d.id, "officer"); st.rerun()
                    if st.button("Reject", key=f"no_{d.id}", icon=":material/close:"):
                        router.reject(d.id, "officer"); st.rerun()
                else:
                    label = "Send (dry run)" if get_settings().dispatch_mode != "live" else "Send to test recipients"
                    if st.button(label, key=f"send_{d.id}", icon=":material/send:"):
                        result = router.send(d.id)
                        st.toast(f"{result.status}: {result.detail}")
                        st.rerun()


def _monitor_section() -> None:
    from pathlib import Path

    from services.config import load_region
    from services.monitor import poll_once, process

    st.markdown("### Bulletin monitor")
    st.caption("Looks for a new bulletin (Google Search grounding, or the demo bulletin), and if it is new drafts every department's advisory and CAP alert and queues them for approval.")
    with st.container(horizontal=True):
        use_sample = st.toggle("Use the demo bulletin instead of searching", value=True, key="monitor_sample")
        st.caption("Each distinct bulletin is processed once (content hash).")
    if st.button("Check for new bulletin now", icon=":material/notifications_active:", key="monitor_check"):
        try:
            with st.spinner("Checking for a new bulletin…"):
                text = load_region().path("sample_bulletin").read_text(encoding="utf-8") if use_sample else None
                found = poll_once(text=text)
            if not found["new"]:
                st.info(f"No new bulletin ({found.get('reason') or 'already processed'}).")
            else:
                with st.spinner("New bulletin: scoring assets and drafting department alerts (about a minute)…"):
                    result = process(found["bulletin_ref"])
                st.session_state["monitor_result"] = result
                st.success(f"Processed. {len(result['dispatch_ids'])} drafts are waiting for approval below.")
                st.rerun()
        except Exception as exc:
            st.error(f"Monitor failed: {exc}")
    result = st.session_state.get("monitor_result")
    if result:
        st.caption(f"Last run {result['run_id']}: {result['cyclone']}, {result['class_counts']}. {result['label']}")
        if result.get("diff_vs_previous"):
            d = result["diff_vs_previous"]
            st.caption(f"Since the previous bulletin: {d['newly_high_or_critical']} assets became HIGH or CRITICAL, {d['no_longer_high']} no longer are.")


def render() -> None:
    settings = get_settings()
    st.subheader("Dispatch & CAP")
    if settings.dispatch_mode == "live":
        st.warning(f"LIVE mode: approved messages go to the test allow-list ({', '.join(settings.dispatch_allowlist) or 'none'}) and the Chat test space only.", icon=":material/warning:")
    else:
        st.info("Dry-run mode: approving and sending only logs the message. Nothing is sent to anyone.", icon=":material/shield:")
    st.caption("Every alert is a CAP 1.2 Exercise alert. The real-world integration target is SACHET (NDMA's CAP platform). Agents can queue, never send.")
    _monitor_section()
    st.divider()
    _draft_section()
    st.divider()
    _queue_section()
