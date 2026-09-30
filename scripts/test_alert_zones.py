"""Alert level test: the shared threshold table gives the expected levels. Offline."""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.alert_zones import alert_level, level_name, thresholds


def test_table() -> None:
    t = thresholds()
    assert t["levels"] == ["green", "yellow", "orange", "red"] and t["needs_expert_review"] is True
    assert t["wind_kmh"] == sorted(t["wind_kmh"]) and t["rain_mm_h"] == sorted(t["rain_mm_h"])
    for wind, rain, expected in t["test_table"]:
        got = alert_level(wind, rain)
        assert got == expected, f"wind {wind} rain {rain}: expected {expected}, got {got}"
    assert level_name(3) == "red"
    print("alert levels ok:", len(t["test_table"]), "cases")


if __name__ == "__main__":
    test_table()
    print("SURGESIGHT_ALERT_ZONES_OK")
