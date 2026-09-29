"""Firestore RunStore (WP5.4), selected with ``SURGESIGHT_STORE=firestore``.

Layout: ``runs/{run_id}`` holds ``{kind, created_at_utc, chunks}``; the JSON payload is split into
``runs/{run_id}/parts/{n}`` documents because Firestore rejects nested arrays (GeoJSON) and documents over 1 MB.
Frames are CSV and blobs raw bytes, chunked the same way under ``runs/{run_id}/blobs/{name}/parts/{n}``.
Advisories and dispatches are mirrored into ``advisories`` and ``dispatches`` for easy listing; approvals and
bulletin fingerprints have their own collections.
"""

from __future__ import annotations

from datetime import datetime, timezone
import io
import json
from typing import Any

import pandas as pd

from services.config import get_settings
from services.store.base import RunStore

CHUNK_BYTES = 700_000
MIRRORS = {"advisory": "advisories", "dispatch": "dispatches"}


class FirestoreStore(RunStore):
    def __init__(self, project: str | None = None, database: str = "(default)") -> None:
        from google.cloud import firestore

        self.db = firestore.Client(project=project or get_settings().cloud_project, database=database)

    # -- chunked bytes
    def _write_chunks(self, ref, data: bytes) -> int:
        chunks = [data[i : i + CHUNK_BYTES] for i in range(0, len(data), CHUNK_BYTES)] or [b""]
        batch = self.db.batch()
        for n, chunk in enumerate(chunks):
            batch.set(ref.collection("parts").document(f"{n:05d}"), {"n": n, "data": chunk})
        batch.commit()
        return len(chunks)

    def _read_chunks(self, ref) -> bytes:
        parts = sorted(ref.collection("parts").stream(), key=lambda d: d.to_dict()["n"])
        return b"".join(p.to_dict()["data"] for p in parts)

    # -- RunStore
    def put(self, run_id: str, kind: str, payload: dict[str, Any]) -> None:
        ref = self.db.collection("runs").document(run_id)
        created = datetime.now(timezone.utc).isoformat()
        raw = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        chunks = self._write_chunks(ref, raw)
        ref.set({"kind": kind, "created_at_utc": created, "chunks": chunks, "bytes": len(raw)})
        mirror = MIRRORS.get(kind)
        if mirror and len(raw) < 900_000:
            self.db.collection(mirror).document(run_id).set({"kind": kind, "created_at_utc": created, "payload_json": raw.decode("utf-8")})

    def get(self, run_id: str) -> dict[str, Any]:
        ref = self.db.collection("runs").document(run_id)
        snapshot = ref.get()
        if not snapshot.exists:
            raise KeyError(f"Unknown run_id: {run_id}")
        meta = snapshot.to_dict()
        return {"run_id": run_id, "kind": meta["kind"], "created_at_utc": meta["created_at_utc"],
                "payload": json.loads(self._read_chunks(ref).decode("utf-8"))}

    def list(self, kind: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        from google.cloud.firestore_v1.base_query import FieldFilter

        query = self.db.collection("runs")
        if kind:
            query = query.where(filter=FieldFilter("kind", "==", kind))
        rows = [{"run_id": d.id, "kind": d.to_dict()["kind"], "created_at_utc": d.to_dict()["created_at_utc"]} for d in query.stream()]
        rows.sort(key=lambda r: r["created_at_utc"], reverse=True)
        return rows[:limit]

    def put_frame(self, run_id: str, name: str, frame: pd.DataFrame) -> None:
        self.put_blob(run_id, f"frame_{name}.csv", frame.to_csv(index=False).encode("utf-8"))

    def get_frame(self, run_id: str, name: str) -> pd.DataFrame:
        try:
            return pd.read_csv(io.BytesIO(self.get_blob(run_id, f"frame_{name}.csv")))
        except KeyError:
            raise KeyError(f"Run {run_id} has no frame '{name}'") from None

    def put_blob(self, run_id: str, name: str, data: bytes) -> None:
        ref = self.db.collection("runs").document(run_id).collection("blobs").document(name.replace("/", "_"))
        ref.set({"bytes": len(data), "chunks": self._write_chunks(ref, data)})

    def get_blob(self, run_id: str, name: str) -> bytes:
        ref = self.db.collection("runs").document(run_id).collection("blobs").document(name.replace("/", "_"))
        if not ref.get().exists:
            raise KeyError(f"Run {run_id} has no blob '{name}'")
        return self._read_chunks(ref)

    # -- extras used by dispatch and the monitor
    def log_event(self, collection: str, doc_id: str, data: dict[str, Any]) -> None:
        self.db.collection(collection).document(doc_id).set({**data, "logged_at_utc": datetime.now(timezone.utc).isoformat()})

    def mark_seen(self, key: str, info: dict[str, Any] | None = None) -> bool:
        """Record a bulletin fingerprint; True if it was new."""
        ref = self.db.collection("bulletins_seen").document(key)
        if ref.get().exists:
            return False
        ref.set({"first_seen_utc": datetime.now(timezone.utc).isoformat(), **(info or {})})
        return True

    def delete_run(self, run_id: str) -> None:
        """Remove a run and its parts (used by tests)."""
        ref = self.db.collection("runs").document(run_id)
        for blob in ref.collection("blobs").stream():
            for part in blob.reference.collection("parts").stream():
                part.reference.delete()
            blob.reference.delete()
        for part in ref.collection("parts").stream():
            part.reference.delete()
        ref.delete()
        for mirror in MIRRORS.values():
            self.db.collection(mirror).document(run_id).delete()
