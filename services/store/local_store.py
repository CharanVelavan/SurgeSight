"""JSON-on-disk RunStore under ``data/runs/`` (git-ignored)."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

import pandas as pd

from services.config import PROJECT_ROOT
from services.store.base import RunStore

DEFAULT_ROOT = PROJECT_ROOT / "data" / "runs"
_SAFE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _safe(name: str) -> str:
    if not _SAFE.match(name) or name.startswith("."):
        raise ValueError(f"Unsafe identifier: {name!r}")
    return name


class LocalStore(RunStore):
    def __init__(self, root: Path = DEFAULT_ROOT) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _dir(self, run_id: str) -> Path:
        path = self.root / _safe(run_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def put(self, run_id: str, kind: str, payload: dict[str, Any]) -> None:
        record = {
            "run_id": run_id,
            "kind": kind,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        target = self._dir(run_id) / "record.json"
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(record, ensure_ascii=False, default=str), encoding="utf-8")
        tmp.replace(target)

    def get(self, run_id: str) -> dict[str, Any]:
        file = self.root / _safe(run_id) / "record.json"
        if not file.exists():
            raise KeyError(f"Unknown run_id: {run_id}")
        return json.loads(file.read_text(encoding="utf-8"))

    def list(self, kind: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        records = []
        for file in self.root.glob("*/record.json"):
            record = json.loads(file.read_text(encoding="utf-8"))
            if kind is None or record["kind"] == kind:
                records.append({k: record[k] for k in ("run_id", "kind", "created_at_utc")})
        records.sort(key=lambda r: r["created_at_utc"], reverse=True)
        return records[:limit]

    def put_frame(self, run_id: str, name: str, frame: pd.DataFrame) -> None:
        frame.to_csv(self._dir(run_id) / f"{_safe(name)}.csv", index=False)

    def get_frame(self, run_id: str, name: str) -> pd.DataFrame:
        file = self.root / _safe(run_id) / f"{_safe(name)}.csv"
        if not file.exists():
            raise KeyError(f"Run {run_id} has no frame '{name}'")
        return pd.read_csv(file)

    def put_blob(self, run_id: str, name: str, data: bytes) -> None:
        (self._dir(run_id) / _safe(name)).write_bytes(data)

    def get_blob(self, run_id: str, name: str) -> bytes:
        file = self.root / _safe(run_id) / _safe(name)
        if not file.exists():
            raise KeyError(f"Run {run_id} has no blob '{name}'")
        return file.read_bytes()
