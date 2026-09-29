"""Bulletin monitor (WP5.6): poll for a new bulletin, run the whole flow, queue drafts for approval.

``poll_once`` finds bulletin text (pasted/test text, a configured URL, or Google Search grounding) and dedupes it
by content hash in the run store. ``process`` parses it, builds a track, scores all assets with v2, runs the
parametric evaluation and, for each department, drafts an advisory and a CAP alert and queues a dispatch for human
approval. Nothing is sent. ``diff_runs`` reports what changed between two processed bulletins.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
import re
from typing import Any

import pandas as pd
import requests

from services.departments import department_mask, get_department, load_departments
from services.store import get_store, new_run_id

KIND = "monitor_run"
HIGH_RANK = {"HIGH", "CRITICAL"}
MIN_TEXT_CHARS = 200


def fingerprint(text: str) -> str:
    """Hash of the bulletin content, insensitive to case and whitespace."""
    return hashlib.sha256(re.sub(r"\s+", " ", text).strip().lower().encode("utf-8")).hexdigest()[:24]


def _fetch(url: str) -> str:
    response = requests.get(url, timeout=30, headers={"User-Agent": "SurgeSight-Monitor/1.0"})
    response.raise_for_status()
    return re.sub(r"<[^>]+>", " ", response.text)


def poll_once(region_id: str | None = None, *, text: str | None = None, url: str | None = None) -> dict[str, Any]:
    """Look for a bulletin and report whether it is new. Source order: given text, given/env URL, Search grounding."""
    from services.agent.builtin_tools import register_bulletin_text
    from services.config import load_region

    region = load_region(region_id)
    url = url or os.getenv("MONITOR_BULLETIN_URL")
    if text:
        source = "text"
    elif url:
        text, source = _fetch(url), f"url:{url}"
    else:
        from services.search_grounding import search_latest_bulletins

        found = search_latest_bulletins(region.cyclone_name.title(), region.display_name)
        text, source = found["answer_text"], "google_search_grounding"
        if not found["grounded"]:
            return {"new": False, "bulletin_ref": None, "source": source, "reason": "search returned no cited sources"}
    if len(text.strip()) < MIN_TEXT_CHARS:
        return {"new": False, "bulletin_ref": None, "source": source, "reason": "no bulletin text found"}
    key = fingerprint(text)
    is_new = get_store().mark_seen(key, {"source": source, "region": region.id})
    return {"new": is_new, "bulletin_ref": register_bulletin_text(text) if is_new else None, "fingerprint": key, "source": source}


def _bulletin_track(bulletin_ref: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    import services.agent  # noqa: F401
    from services.agent.tools import execute_tool
    from services.bulletin_parser import CycloneBulletin
    from services.bulletin_track import bulletin_to_track

    parsed, _ = execute_tool("parse_bulletin", {"source_run_id": bulletin_ref})
    if not parsed.ok:
        raise RuntimeError(f"parse_bulletin failed: {parsed.error}")
    built = bulletin_to_track(CycloneBulletin.model_validate(parsed.data))
    return built.track_df, {"parsed": parsed.data, "flags": list(built.flags)}


def _department_draft(name: str, language: str, frame: pd.DataFrame) -> dict[str, Any]:
    from services.advisory import generate_role_advisory
    from services.cap import build_cap_alert
    from services.dispatch.router import queue_dispatch

    dept = get_department(name)
    advisory = generate_role_advisory(dept.display_name, language, frame)
    cap = build_cap_alert(advisory, language, frame=frame)
    body = "\n\n".join(p for p in (advisory.situation_summary, advisory.instruction, "\n".join(f"- {a}" for a in advisory.priority_actions), advisory.disclaimer) if p)
    channel = dept.default_channels[0] if dept.default_channels else "chat"
    dispatch = queue_dispatch(dept.display_name, channel, advisory.headline or dept.display_name, body,
                              attachments=[{"name": "alert.cap.xml", "mime": "application/xml", "text": cap}])
    return {"department": dept.display_name, "severity": advisory.severity, "headline": advisory.headline, "dispatch_id": dispatch.id}


def process(bulletin_ref: str, *, languages: dict[str, str] | None = None, departments: list[str] | None = None,
            members: int = 40, draft_workers: int = 4) -> dict[str, Any]:
    """Run the whole flow for a bulletin. ``languages`` maps department id to language (default English)."""
    from services.departments import score_all_assets
    from services.parametric import evaluate, with_crore

    store = get_store()
    track, info = _bulletin_track(bulletin_ref)
    frame = score_all_assets(track)
    previous = next(iter(store.list(KIND, 1)), None)
    run_id = new_run_id("monitor")
    store.put_frame(run_id, "assets", frame)
    names = departments or [d.display_name for d in load_departments().values()]
    languages = languages or {}
    with ThreadPoolExecutor(max_workers=draft_workers) as pool:
        drafts = list(pool.map(lambda n: _department_draft(n, languages.get(get_department(n).id, "English"), frame), names))
    parametric = with_crore(evaluate(track, members=members))
    summary = {
        "bulletin_ref": bulletin_ref, "cyclone": info["parsed"].get("cyclone_name"), "track_flags": info["flags"],
        "track_points": int(len(track)),
        "class_counts": {str(k): int(v) for k, v in frame["class_v2"].value_counts().items()},
        "drafts": drafts, "dispatch_ids": [d["dispatch_id"] for d in drafts],
        "parametric_total_payout_crore": parametric["total_payout_crore"],
        "parametric_expected_payout_crore": parametric.get("ensemble", {}).get("expected_total_payout_crore"),
        "label": "Drafts are queued for human approval. Nothing has been sent. Parametric figures are illustrative.",
    }
    if previous:
        summary["diff_vs_previous"] = diff_runs(previous["run_id"], run_id, _new_frame=frame)
    store.put(run_id, KIND, summary)
    return {"run_id": run_id, **summary}


def diff_runs(prev_run_id: str, new_run_id_: str, *, _new_frame: pd.DataFrame | None = None) -> dict[str, Any]:
    """Assets that became HIGH or CRITICAL, stopped being HIGH or CRITICAL, per department and overall."""
    store = get_store()
    prev = store.get_frame(prev_run_id, "assets")
    new = _new_frame if _new_frame is not None else store.get_frame(new_run_id_, "assets")
    key = ["osm_element", "osm_id"]
    both = new[key + ["name", "asset_type", "class_v2"]].merge(prev[key + ["class_v2"]], on=key, how="inner", suffixes=("", "_prev"))
    now_high, was_high = both["class_v2"].isin(HIGH_RANK), both["class_v2_prev"].isin(HIGH_RANK)
    newly, cleared = both[now_high & ~was_high], both[~now_high & was_high]

    def rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
        return frame[["name", "asset_type", "class_v2_prev", "class_v2"]].head(15).to_dict(orient="records")

    by_department = {}
    for dept in load_departments().values():
        n_new, n_cleared = int(department_mask(dept, newly).sum()), int(department_mask(dept, cleared).sum())
        by_department[dept.display_name] = {"newly_high_or_critical": n_new, "no_longer_high": n_cleared}
    return {"compared_assets": int(len(both)), "newly_high_or_critical": int(len(newly)), "no_longer_high": int(len(cleared)),
            "by_department": by_department, "examples_newly_high": rows(newly), "examples_no_longer_high": rows(cleared)}
