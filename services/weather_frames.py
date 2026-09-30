"""Weather frame atlases for the animated map: byte encoding, atlas packing and the leakage rule.

Wind u,v are stored in the R,G bytes over +-WIND_MAX m/s; rain (mm/h) in a byte on a log scale.
Everything here is pure numpy/Pillow so the build script, the API and the tests share one definition.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from PIL import Image

WEATHER_DIR = Path(__file__).resolve().parents[1] / "data" / "processed" / "weather"
WIND_MAX = 40.0
RAIN_MAX = 200.0
# All of India plus the Arabian Sea from Oman, north past Jammu & Kashmir, east to Myanmar.
BOUNDS = {"west": 50.0, "east": 100.0, "south": 0.0, "north": 38.0, "step": 0.25}
WIDTH = round((BOUNDS["east"] - BOUNDS["west"]) / BOUNDS["step"]) + 1
HEIGHT = round((BOUNDS["north"] - BOUNDS["south"]) / BOUNDS["step"]) + 1
WINDOW_START, WINDOW_END = pd.Timestamp("2023-11-30 00:00"), pd.Timestamp("2023-12-07 00:00")
CYCLE_EVERY_H, FORECAST_STEP_H, FORECAST_LEAD_H = 12, 3, 72


def encode_wind(x: np.ndarray) -> np.ndarray:
    return np.clip(np.rint((np.nan_to_num(x) + WIND_MAX) / (2 * WIND_MAX) * 255), 0, 255).astype(np.uint8)


def decode_wind(b: np.ndarray) -> np.ndarray:
    return b.astype(np.float64) / 255 * (2 * WIND_MAX) - WIND_MAX


def encode_rain(x: np.ndarray) -> np.ndarray:
    r = np.clip(np.nan_to_num(x), 0, RAIN_MAX)
    return np.clip(np.rint(np.log1p(r) / math.log1p(RAIN_MAX) * 255), 0, 255).astype(np.uint8)


def decode_rain(b: np.ndarray) -> np.ndarray:
    return np.expm1(b.astype(np.float64) / 255 * math.log1p(RAIN_MAX))


def atlas_shape(n_frames: int) -> tuple[int, int]:
    cols = math.ceil(math.sqrt(n_frames))
    return cols, math.ceil(n_frames / cols)


def pack_atlas(frames: np.ndarray) -> Image.Image:
    """frames: (n, H, W, 3) uint8 -> one RGB atlas, row-major tiles."""
    n, h, w, _ = frames.shape
    cols, rows = atlas_shape(n)
    atlas = np.zeros((rows * h, cols * w, 3), dtype=np.uint8)
    for i in range(n):
        r, c = divmod(i, cols)
        atlas[r * h:(r + 1) * h, c * w:(c + 1) * w] = frames[i]
    return Image.fromarray(atlas, "RGB")


def unpack_atlas(image: Image.Image | Path, n_frames: int, h: int = HEIGHT, w: int = WIDTH) -> np.ndarray:
    if not isinstance(image, Image.Image):
        image = Image.open(image)
    arr = np.asarray(image.convert("RGB"))
    cols, _ = atlas_shape(n_frames)
    out = np.zeros((n_frames, h, w, 3), dtype=np.uint8)
    for i in range(n_frames):
        r, c = divmod(i, cols)
        out[i] = arr[r * h:(r + 1) * h, c * w:(c + 1) * w]
    return out


def iso(t: pd.Timestamp) -> str:
    return pd.Timestamp(t).strftime("%Y-%m-%dT%H:%M:%SZ")


def naive_utc(t: str | pd.Timestamp) -> pd.Timestamp:
    ts = pd.Timestamp(t)
    return ts.tz_convert("UTC").tz_localize(None) if ts.tzinfo is not None else ts


def cycle_times() -> list[pd.Timestamp]:
    return list(pd.date_range(WINDOW_START, WINDOW_END, freq=f"{CYCLE_EVERY_H}h"))


def forecast_steps() -> list[int]:
    return list(range(0, FORECAST_LEAD_H + 1, FORECAST_STEP_H))


def cycle_id(t: pd.Timestamp) -> str:
    return pd.Timestamp(t).strftime("%Y%m%d%H")


def load_manifest(directory: Path = WEATHER_DIR) -> dict[str, Any]:
    path = directory / "manifest.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing; run scripts/build_weather_frames.py")
    return json.loads(path.read_text(encoding="utf-8"))


def frames_for_cutoff(manifest: dict[str, Any], cutoff: str | pd.Timestamp, validation: bool = False) -> dict[str, Any]:
    """The catalogue a client may use for a cutoff C (UTC).

    Leakage rule: forecast frames come only from the latest cycle issued at or before C; analysis-wind and
    IMERG frames are cut at C. IMERG after C is returned only when ``validation`` is true, labelled as such.
    """
    c = naive_utc(cutoff)
    issued = [x for x in manifest["forecast"] if naive_utc(x["cycle"]) <= c]
    latest = max(issued, key=lambda x: x["cycle"]) if issued else None

    def cut(entry: dict[str, Any], keep_after: bool) -> dict[str, Any]:
        keep = [i for i, t in enumerate(entry["frames"]) if keep_after or naive_utc(t) <= c]
        return {**entry, "frames": [entry["frames"][i] for i in keep], "frame_indices": keep}

    return {
        "cutoff": iso(c), "validation": validation, "forecast": latest,
        "analysis_wind": cut(manifest["analysis_wind"], False),
        "observed_rain": {**cut(manifest["observed_rain"], validation), "validation_only_after_cutoff": True},
    }
