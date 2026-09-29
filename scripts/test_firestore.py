"""Live Firestore RunStore test: round trip of payload (with nested arrays), large payload, frame and blob (WP5.4)."""

from __future__ import annotations

import os
from pathlib import Path
import sys

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> None:
    if os.getenv("SURGESIGHT_OFFLINE") == "1":
        print("SKIPPED live Firestore test (SURGESIGHT_OFFLINE=1)")
        return
    from services.store.base import new_run_id
    from services.store.firestore_store import FirestoreStore

    store = FirestoreStore()
    run_id = new_run_id("fstest")
    try:
        payload = {"geo": {"type": "LineString", "coordinates": [[80.1, 13.0], [80.2, 13.1]]}, "text": "தமிழ்" * 200,
                   "big": ["x" * 100] * 20000}  # about 2 MB, more than one chunk
        store.put(run_id, "test", payload)
        record = store.get(run_id)
        assert record["payload"] == payload and record["kind"] == "test"
        frame = pd.DataFrame({"a": np.arange(5), "b": list("vwxyz")})
        store.put_frame(run_id, "assets", frame)
        assert store.get_frame(run_id, "assets").equals(frame)
        store.put_blob(run_id, "audio.mp3", b"\x00\x01" * 500_000)
        assert store.get_blob(run_id, "audio.mp3") == b"\x00\x01" * 500_000
        assert any(r["run_id"] == run_id for r in store.list("test"))
        key = "fstest-" + run_id
        assert store.mark_seen(key, {"t": 1}) and not store.mark_seen(key)
        store.db.collection("bulletins_seen").document(key).delete()
        try:
            store.get("nope-000")
            raise AssertionError("missing run must raise")
        except KeyError:
            pass
        print("firestore round trip ok")
    finally:
        store.delete_run(run_id)
    print("SURGESIGHT_FIRESTORE_OK")


if __name__ == "__main__":
    main()
