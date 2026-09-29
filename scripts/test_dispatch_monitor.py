"""Dispatch approval flow in dry-run (WP5.3) and the bulletin monitor (WP5.6). Uses a throwaway run store."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ["DISPATCH_MODE"] = "dry_run"

from services.store import set_store
from services.store.local_store import LocalStore

set_store(LocalStore(Path(tempfile.mkdtemp())))

import services.agent  # noqa: F401
from services.agent.tools import execute_tool
from services.dispatch import chat, gmail, push, router
from services.monitor import diff_runs, fingerprint, poll_once, process
from services.store import get_store


def test_dispatch() -> None:
    item = router.queue_dispatch("Health", "chat", "Subject", "Body", attachments=[{"name": "a.xml", "mime": "application/xml", "text": "<a/>"}])
    assert item.status == "pending_approval" and item.department == "Health Department"
    for action in (router.send,):
        try:
            action(item.id)
            raise AssertionError("an unapproved dispatch must not send")
        except PermissionError:
            pass
    router.approve(item.id, "tester")
    sent = router.send(item.id)
    assert sent.status == "dry_run" and sent.mode == "dry_run" and "nothing was sent" in sent.detail["note"]
    try:
        router.reject(item.id)
        raise AssertionError("cannot reject after sending")
    except ValueError:
        pass
    rejected = router.queue_dispatch("Electricity", "email", "S", "B", recipients=["nobody@example.com"])
    router.reject(rejected.id)
    try:
        router.send(rejected.id)
        raise AssertionError("a rejected dispatch must not send")
    except PermissionError:
        pass
    assert {d.status for d in router.list_dispatches()} == {"dry_run", "rejected"}
    card = chat.build_card("Subject", "Line one\nLine two", department="Health", attachments=[{"name": "a.xml"}])
    assert card["cardsV2"][0]["card"]["header"]["subtitle"].endswith("(not an official warning)") and "Line one<br>Line two" in str(card)
    message = gmail.build_message("me@example.com", ["you@example.com"], "S", "B", [{"name": "a.xml", "mime": "application/xml", "text": "<a/>"}])
    assert message["To"] == "you@example.com" and any(p.get_filename() == "a.xml" for p in message.iter_attachments())
    request = push.ntfy_request("तूफान की चेतावनी", "Body text", department="Health Department", severity="CRITICAL")
    assert request["headers"]["Priority"] == "urgent" and all(v.isascii() for v in request["headers"].values()), "ntfy headers must be ASCII"
    assert "तूफान" in request["data"].decode("utf-8")
    msg = push.fcm_message("Subject", "Body", department="Health Department", token="t" * 30)["message"]
    assert msg["token"] == "t" * 30 and msg["notification"]["title"].startswith("EXERCISE") and msg["data"]["exercise"] == "true"
    pushed = router.queue_dispatch("Fisheries", "push", "Subject", "Body")
    router.approve(pushed.id)
    assert router.send(pushed.id).status == "dry_run", "push must also be a dry run by default"
    os.environ.pop("NTFY_TOPIC", None)
    assert push.register_token("a" * 40) == {"registered": 1} and push.list_tokens() == ["a" * 40]
    push.register_token("a" * 40)
    assert len(push.list_tokens()) == 1, "registering the same token twice must not duplicate it"
    push.remove_token("a" * 40)
    assert push.list_tokens() == []
    try:
        push.send_push("s", "b", department="d")
        raise AssertionError("no provider configured must fail")
    except RuntimeError as exc:
        assert "No push provider" in str(exc)
    print("dispatch dry run ok")


def test_agent_tool_queues_only() -> None:
    if os.getenv("SURGESIGHT_OFFLINE") == "1":
        print("SKIPPED live agent queue test (SURGESIGHT_OFFLINE=1)")
        return
    drafted, _ = execute_tool("draft_advisory", {"audience": "Police / Traffic", "language": "Hindi"})
    assert drafted.ok, drafted.error
    queued, _ = execute_tool("queue_dispatch", {"advisory_run_id": drafted.run_id, "channel": "chat"})
    assert queued.ok, queued.error
    assert queued.data["status"] == "pending_approval" and queued.data["attachments"] == ["alert.cap.xml"]
    assert router.get(queued.data["dispatch_id"]).status == "pending_approval", "the agent must not approve or send"
    print("agent queue ok")


def test_monitor_offline() -> None:
    text = (PROJECT_ROOT / "data/raw/sample_michaung_bulletin.txt").read_text(encoding="utf-8")
    assert fingerprint(text) == fingerprint("  " + text.upper().replace("\n", "  ") + "\n")
    first = poll_once(text=text)
    assert first["new"] and first["bulletin_ref"]
    again = poll_once(text=text.lower())
    assert not again["new"] and again["bulletin_ref"] is None
    assert not poll_once(text="too short")["new"]

    store = get_store()
    old = pd.DataFrame({"osm_element": ["node"] * 4, "osm_id": [1, 2, 3, 4], "name": list("abcd"), "asset_type": ["hospital", "hospital", "substation", "police_station"],
                        "class_v2": ["MODERATE", "HIGH", "HIGH", "LOW"], "facility_quality": ["hospital"] * 4})
    new = old.assign(class_v2=["HIGH", "MODERATE", "CRITICAL", "HIGH"])
    store.put_frame("m-old", "assets", old)
    store.put_frame("m-new", "assets", new)
    delta = diff_runs("m-old", "m-new")
    assert delta["newly_high_or_critical"] == 2 and delta["no_longer_high"] == 1 and delta["compared_assets"] == 4
    assert delta["by_department"]["Health Department"] == {"newly_high_or_critical": 1, "no_longer_high": 1}
    assert delta["by_department"]["Police / Traffic"]["newly_high_or_critical"] == 1
    print("monitor offline ok")


def test_monitor_process() -> None:
    if os.getenv("SURGESIGHT_OFFLINE") == "1":
        print("SKIPPED live monitor process (SURGESIGHT_OFFLINE=1)")
        return
    text = (PROJECT_ROOT / "data/raw/sample_michaung_bulletin.txt").read_text(encoding="utf-8") + "\nSecond issue for the process test.\n"
    ref = poll_once(text=text)["bulletin_ref"]
    out = process(ref, departments=["Fisheries", "Water"], members=15, languages={"water": "Telugu"})
    assert out["cyclone"] and out["track_points"] >= 2 and sum(out["class_counts"].values()) > 4000
    assert len(out["dispatch_ids"]) == 2
    assert all(router.get(i).status == "pending_approval" and router.get(i).attachments for i in out["dispatch_ids"])
    assert out["parametric_total_payout_crore"] > 0 and "Nothing has been sent" in out["label"]
    again = process(ref, departments=["Fisheries"], members=10)
    diff = again["diff_vs_previous"]
    assert diff["compared_assets"] > 4000 and diff["newly_high_or_critical"] == 0 and diff["no_longer_high"] == 0, "same bulletin: nothing changes"
    print("monitor process ok")


if __name__ == "__main__":
    test_dispatch()
    test_agent_tool_queues_only()
    print("SURGESIGHT_DISPATCH_DRYRUN_OK")
    test_monitor_offline()
    test_monitor_process()
    print("SURGESIGHT_MONITOR_OK")
