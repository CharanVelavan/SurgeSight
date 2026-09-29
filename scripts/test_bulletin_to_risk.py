"""Bulletin -> track -> v1 risk (K1). Deterministic rules offline; live parse if allowed."""

from __future__ import annotations

import os
from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.bulletin_parser import CycloneBulletin, ForecastPoint, Position
from services.bulletin_track import (
    InsufficientForecastPointsError,
    bulletin_to_track,
    parse_bulletin_time,
)
from services.scenario_engine import score_custom_track

SAMPLE = PROJECT_ROOT / "data/raw/sample_michaung_bulletin.txt"


def deterministic_rules() -> None:
    assert parse_bulletin_time("1200 UTC, 04 December 2023") == pd.Timestamp("2023-12-04 12:00")
    assert parse_bulletin_time("0000 UTC, 05 December 2023") == pd.Timestamp("2023-12-05 00:00")
    assert parse_bulletin_time("1730 IST 4 December 2023") == pd.Timestamp("2023-12-04 12:00")
    assert parse_bulletin_time("2023-12-04T15:00:00Z") == pd.Timestamp("2023-12-04 15:00")
    assert parse_bulletin_time("soon") is None

    bulletin = CycloneBulletin(
        cyclone_name="Test",
        bulletin_time="1200 UTC, 04 December 2023",
        current_position=Position(lat=14.0, lon=80.6),
        maximum_sustained_wind_kmph=100.0,
        forecast_track=[
            ForecastPoint(timestamp="1800 UTC, 04 December 2023", lat=14.4, lon=80.3, wind_kmph=None),
            ForecastPoint(timestamp="1500 UTC, 04 December 2023", lat=14.2, lon=80.4, wind_kmph=90.0),
            ForecastPoint(timestamp="2100 UTC, 04 December 2023", lat=None, lon=80.2, wind_kmph=80.0),
        ],
    )
    built = bulletin_to_track(bulletin)
    frame = built.track_df
    assert list(frame["SOURCE"]) == ["current", "forecast", "forecast"]
    assert list(frame["LAT"]) == [14.0, 14.2, 14.4], "current first, forecast time-ordered"
    assert list(frame["WIND_KMH"]) == [100.0, 90.0, 90.0], "missing wind carried forward"
    assert "wind_carried_forward:1" in built.flags
    assert "dropped_points_missing_position:1" in built.flags

    try:
        bulletin_to_track(CycloneBulletin(current_position=Position(lat=14.0, lon=80.6), maximum_sustained_wind_kmph=90))
    except InsufficientForecastPointsError as exc:
        assert "insufficient forecast points" in str(exc)
    else:
        raise AssertionError("a single point must be rejected")

    scored = score_custom_track(frame)
    assert len(scored) == 3977 and "scenario_risk_class" in scored.columns
    print("deterministic bulletin rules passed")


def live_sample() -> None:
    from services.bulletin_parser import parse_bulletin_text

    bulletin = parse_bulletin_text(SAMPLE.read_text(encoding="utf-8"))
    built = bulletin_to_track(bulletin)
    assert len(built.track_df) == 4, built.track_df
    scored = score_custom_track(built.track_df)
    counts = scored["scenario_risk_class"].value_counts().to_dict()
    assert sum(counts.values()) == 3977 and counts.get("HIGH", 0) + counts.get("CRITICAL", 0) > 0, counts
    print("sample bulletin scored:", counts)


def main() -> None:
    deterministic_rules()
    if os.getenv("SURGESIGHT_OFFLINE") == "1":
        print("SKIPPED live bulletin parse (SURGESIGHT_OFFLINE=1)")
        return
    live_sample()
    print("SURGESIGHT_BULLETIN_TO_RISK_OK")


if __name__ == "__main__":
    main()
