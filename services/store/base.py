"""RunStore interface: full tool results live here, Gemini only sees compact summaries (§4.4)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
import uuid

import pandas as pd


def new_run_id(kind: str) -> str:
    return f"{kind}-{uuid.uuid4().hex[:10]}"


class RunStore(ABC):
    @abstractmethod
    def put(self, run_id: str, kind: str, payload: dict[str, Any]) -> None: ...

    @abstractmethod
    def get(self, run_id: str) -> dict[str, Any]:
        """Return the stored record: ``{"run_id", "kind", "created_at_utc", "payload"}``."""

    @abstractmethod
    def list(self, kind: str | None = None, limit: int = 50) -> list[dict[str, Any]]: ...

    @abstractmethod
    def put_frame(self, run_id: str, name: str, frame: pd.DataFrame) -> None: ...

    @abstractmethod
    def get_frame(self, run_id: str, name: str) -> pd.DataFrame: ...

    @abstractmethod
    def put_blob(self, run_id: str, name: str, data: bytes) -> None: ...

    @abstractmethod
    def get_blob(self, run_id: str, name: str) -> bytes: ...

    def payload(self, run_id: str) -> dict[str, Any]:
        return self.get(run_id)["payload"]

    def log_event(self, collection: str, doc_id: str, data: dict[str, Any]) -> None:
        """Append-only audit record (approvals). Stores that have no such collection may ignore it."""

    def mark_seen(self, key: str, info: dict[str, Any] | None = None) -> bool:
        """Remember a fingerprint (bulletin hash); True if it had not been seen before."""
        seen = self.get_seen()
        if key in seen:
            return False
        seen[key] = info or {}
        self.put("_bulletins_seen", "bulletins_seen", {"seen": seen})
        return True

    def get_seen(self) -> dict[str, Any]:
        try:
            return dict(self.get("_bulletins_seen")["payload"]["seen"])
        except KeyError:
            return {}


_store: RunStore | None = None


def get_store() -> RunStore:
    """Return the configured store (``SURGESIGHT_STORE=local|firestore``)."""
    global _store
    if _store is None:
        from services.config import get_settings

        backend = get_settings().store
        if backend == "local":
            from services.store.local_store import LocalStore

            _store = LocalStore()
        elif backend == "firestore":
            from services.store.firestore_store import FirestoreStore

            _store = FirestoreStore()
        else:
            raise ValueError(f"Unknown SURGESIGHT_STORE '{backend}' (use local or firestore)")
    return _store


def set_store(store: RunStore | None) -> None:
    """Override the store (tests)."""
    global _store
    _store = store
