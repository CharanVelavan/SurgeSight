"""Offline test of the river flood layer (WP2.7) and the GFS comparison cache (WP2.6) plus their tools."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import services.agent  # noqa: F401
from services.agent.tools import execute_tool
from services.config import load_region
from services.hazards.river_flood import load_river_table, river_flood_index, susceptibility
from services.nwp_comparison import track_vortex, vorticity


def test_river() -> None:
    assert susceptibility(0) == 1.0 and susceptibility(5) < susceptibility(1) and susceptibility(60) < 0.001
    assert river_flood_index(0, 0) == 0 and river_flood_index(300, 0) == 1.0
    table = load_river_table()
    assert len(table) > 3900 and table["hand_m"].notna().mean() > 0.99
    result, _ = execute_tool("river_flood", {"top_n": 3})
    assert result.ok, result.error
    assert set(result.data["top_by_type"]) == {"hospital", "school", "shelter", "substation"}
    assert len(result.data["top_by_type"]["hospital"]) == 3 and "not a river-level forecast" in result.data["label"]
    print("river ok")


def test_vortex() -> None:
    # synthetic cyclonic vortex (counter-clockwise in the northern hemisphere) centred at 13N 81E
    lat = np.linspace(17.875, 7.875, 40)[:, None] * np.ones((1, 40))
    lon = np.ones((40, 1)) * np.linspace(77.875, 87.875, 40)[None, :]
    dy, dx = (lat - 13.0) * 111.0, (lon - 81.0) * 111.0 * np.cos(np.radians(13.0))
    r = np.hypot(dx, dy) + 1
    speed = 30 * (r / 60) * np.exp(1 - r / 60)
    u, v = -speed * dy / r, speed * dx / r
    assert vorticity(u, v, lat)[20:25, 10:30].max() > 0
    found = track_vortex(u, v, lat, lon, (12.5, 81.5))
    assert found and abs(found["lat"] - 13.0) < 0.6 and abs(found["lon"] - 81.0) < 0.6, found
    print("vortex ok")


def test_nwp_cache() -> None:
    data = json.loads(load_region().path("nwp_comparison").read_text(encoding="utf-8"))
    assert data["cutoff_utc"].startswith("2023-12-03 12:00") and len(data["rows"]) >= 4
    assert all(row["gfs"] and row["gfs_error_km"] < 150 for row in data["rows"]), "GFS centre lost the storm"
    result, _ = execute_tool("nwp_comparison", {})
    assert result.ok, result.error
    assert result.data["rows"][0]["lead_hours"] == 6 and "not an official forecast" in result.data["label"].lower()
    print("nwp ok")


if __name__ == "__main__":
    test_river()
    test_vortex()
    test_nwp_cache()
    print("SURGESIGHT_RIVER_FLOOD_OK")
    print("SURGESIGHT_NWP_COMPARISON_OK")
