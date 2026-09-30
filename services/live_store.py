"""Where the live weather atlases live.

Locally they are in data/processed/live. On Cloud Run the scheduled job uploads them to a Cloud Storage
bucket (LIVE_BUCKET, e.g. gs://my-bucket/live) and each service instance keeps a local copy, checking the
bucket for a newer manifest at most every few minutes. The web routes only ever read the local folder.
"""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import threading
import time

from services.config import PROJECT_ROOT

LOCAL_DIR = PROJECT_ROOT / "data" / "processed" / "live"
CHECK_EVERY_S = 300
_lock = threading.Lock()
_checked = 0.0
_generation: int | None = None


def bucket_url() -> str | None:
    return os.getenv("LIVE_BUCKET") or None


def _split(url: str) -> tuple[str, str]:
    rest = url.removeprefix("gs://")
    bucket, _, prefix = rest.partition("/")
    return bucket, prefix.strip("/")


def live_dir() -> Path:
    """Folder with manifest.json and the atlases; refreshed from the bucket when one is configured."""
    url = bucket_url()
    if not url:
        return LOCAL_DIR
    target = Path(tempfile.gettempdir()) / "surgesight-live"
    global _checked, _generation
    with _lock:
        if time.monotonic() - _checked > CHECK_EVERY_S or not (target / "manifest.json").is_file():
            _checked = time.monotonic()
            try:
                _sync(url, target)
            except Exception as exc:  # keep serving the last copy; the stale banner covers the rest
                print(f"live weather sync failed: {type(exc).__name__}: {exc}", flush=True)
    return target


def _sync(url: str, target: Path) -> None:
    from google.cloud import storage

    global _generation
    bucket_name, prefix = _split(url)
    bucket = storage.Client().bucket(bucket_name)
    manifest = bucket.blob(f"{prefix}/manifest.json" if prefix else "manifest.json")
    manifest.reload()
    if manifest.generation == _generation and (target / "manifest.json").is_file():
        return
    staging = target.with_name(target.name + ".new")
    staging.mkdir(parents=True, exist_ok=True)
    for blob in bucket.list_blobs(prefix=f"{prefix}/" if prefix else None):
        name = blob.name.removeprefix(f"{prefix}/" if prefix else "")
        if name and "/" not in name:
            blob.download_to_filename(staging / name)
    if target.exists():
        for f in target.iterdir():
            f.unlink()
        target.rmdir()
    staging.rename(target)
    _generation = manifest.generation


def upload(folder: Path, url: str) -> int:
    """Upload the atlases first and the manifest last, so a reader never sees a manifest without its files."""
    from google.cloud import storage

    bucket_name, prefix = _split(url)
    bucket = storage.Client().bucket(bucket_name)
    files = sorted(folder.iterdir(), key=lambda f: f.name == "manifest.json")
    for f in files:
        blob = bucket.blob(f"{prefix}/{f.name}" if prefix else f.name)
        blob.cache_control = "no-cache"
        blob.upload_from_filename(f)
    return len(files)
