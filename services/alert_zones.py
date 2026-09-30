"""Alert levels (green, yellow, orange, red) from wind and rain, using the thresholds shared with the web UI.

The thresholds live in config/alert_thresholds.json and are read by both this module and the TypeScript
alert layer. They are our own screening thresholds, not an IMD warning, and need expert review before real use.
"""

from __future__ import annotations

from functools import lru_cache
import json
from typing import Any

from services.config import PROJECT_ROOT

PATH = PROJECT_ROOT / "config" / "alert_thresholds.json"


@lru_cache(maxsize=1)
def thresholds() -> dict[str, Any]:
    return json.loads(PATH.read_text(encoding="utf-8"))


def alert_level(wind_kmh: float, rain_mm_h: float) -> int:
    """0 green, 1 yellow, 2 orange, 3 red: the larger of the wind level and the rain level."""
    t = thresholds()
    wind = sum(wind_kmh >= x for x in t["wind_kmh"])
    rain = sum(rain_mm_h >= x for x in t["rain_mm_h"])
    return max(wind, rain)


def level_name(level: int) -> str:
    return thresholds()["levels"][level]
