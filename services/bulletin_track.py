"""Convert a parsed cyclone bulletin into a track the v1 risk engine can score (WP1.2, K1).

Deterministic: no AI. Rules (IMPLEMENTATION_PLAN §WP1.2):
- the current position is the first bulletin point; forecast points follow in time order;
- points without lat/lon are dropped and flagged;
- a missing wind carries the last known wind forward and is flagged;
- fewer than 2 usable points is an error.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import re

import pandas as pd
from dateutil import parser as date_parser

from services.bulletin_parser import CycloneBulletin

KT_PER_KMH = 1 / 1.852
TRACK_COLUMNS = ["SID", "NAME", "ISO_TIME", "LAT", "LON", "WIND_KT", "PRESSURE_HPA", "BASIN", "WIND_KMH", "SOURCE"]
_HHMM_TZ = re.compile(r"\b([01]\d|2[0-3])([0-5]\d)\s*(UTC|GMT|Z|IST)\b", re.IGNORECASE)


class InsufficientForecastPointsError(ValueError):
    """Raised when a bulletin has fewer than 2 usable track points."""


@dataclass
class TrackBuildResult:
    track_df: pd.DataFrame
    flags: list[str] = field(default_factory=list)


def parse_bulletin_time(text: str | None) -> pd.Timestamp | None:
    """Parse bulletin timestamps such as '1200 UTC, 04 December 2023' or ISO strings, to naive UTC."""
    if not text or not text.strip():
        return None
    try:
        match = _HHMM_TZ.search(text)
        if match:
            hour, minute, zone = int(match.group(1)), int(match.group(2)), match.group(3).upper()
            rest = _HHMM_TZ.sub(" ", text, count=1)
            day = date_parser.parse(rest, fuzzy=True, default=datetime(1, 1, 1))
            if day.year < 1990:
                return None
            moment = datetime(day.year, day.month, day.day, hour, minute)
            if zone == "IST":
                moment -= timedelta(hours=5, minutes=30)
            return pd.Timestamp(moment)
        parsed = date_parser.parse(text, fuzzy=True, default=datetime(1, 1, 1))
        if parsed.year < 1990:
            return None
        stamp = pd.Timestamp(parsed)
        return stamp.tz_convert("UTC").tz_localize(None) if stamp.tzinfo else stamp
    except (ValueError, OverflowError):
        return None


def bulletin_to_track(
    bulletin: CycloneBulletin,
    *,
    previous_track: pd.DataFrame | None = None,
) -> TrackBuildResult:
    """Build a scorable track from a parsed bulletin.

    ``previous_track`` (optional) supplies earlier observed fixes, which are kept only if
    they are older than the bulletin time.
    """
    flags: list[str] = []
    name = (bulletin.cyclone_name or "UNKNOWN").upper()
    issue_time = parse_bulletin_time(bulletin.bulletin_time)

    raw: list[dict] = []
    current = bulletin.current_position
    if current.lat is not None and current.lon is not None:
        raw.append({
            "time": issue_time, "lat": current.lat, "lon": current.lon,
            "wind": bulletin.maximum_sustained_wind_kmph,
            "pressure": bulletin.central_pressure_hpa, "source": "current",
        })
    else:
        flags.append("current_position_missing")

    dropped = 0
    forecast = []
    for point in bulletin.forecast_track:
        if point.lat is None or point.lon is None:
            dropped += 1
            continue
        forecast.append({
            "time": parse_bulletin_time(point.timestamp), "lat": point.lat, "lon": point.lon,
            "wind": point.wind_kmph, "pressure": point.pressure_hpa, "source": "forecast",
        })
    if dropped:
        flags.append(f"dropped_points_missing_position:{dropped}")

    if forecast and all(p["time"] is not None for p in forecast):
        forecast.sort(key=lambda p: p["time"])
    elif forecast:
        flags.append("forecast_timestamps_unparsed_kept_in_bulletin_order")
    raw.extend(forecast)

    if len(raw) < 2:
        raise InsufficientForecastPointsError(
            f"insufficient forecast points: {len(raw)} usable point(s) in the bulletin; need at least 2"
        )

    carried = 0
    last_wind: float | None = None
    first_known = next((p["wind"] for p in raw if p["wind"] is not None), None)
    if first_known is None:
        raise ValueError("Bulletin states no wind speed for any usable point; cannot score it")
    for point in raw:
        if point["wind"] is None:
            point["wind"] = last_wind if last_wind is not None else first_known
            carried += 1
        last_wind = point["wind"]
    if carried:
        flags.append(f"wind_carried_forward:{carried}")

    rows = [
        {
            "SID": "BULLETIN", "NAME": name,
            "ISO_TIME": p["time"].strftime("%Y-%m-%d %H:%M:%S") if p["time"] is not None else None,
            "LAT": float(p["lat"]), "LON": float(p["lon"]),
            "WIND_KT": round(float(p["wind"]) * KT_PER_KMH, 3),
            "PRESSURE_HPA": p["pressure"], "BASIN": "NI",
            "WIND_KMH": float(p["wind"]), "SOURCE": p["source"],
        }
        for p in raw
    ]
    frame = pd.DataFrame(rows, columns=TRACK_COLUMNS)

    if previous_track is not None and issue_time is not None and not previous_track.empty:
        history = previous_track.copy()
        history["ISO_TIME"] = pd.to_datetime(history["ISO_TIME"])
        history = history[history["ISO_TIME"] < issue_time]
        if not history.empty:
            history["ISO_TIME"] = history["ISO_TIME"].dt.strftime("%Y-%m-%d %H:%M:%S")
            history["SOURCE"] = "history"
            frame = pd.concat([history[TRACK_COLUMNS], frame], ignore_index=True)
            flags.append(f"history_prepended:{len(history)}")

    if issue_time is None:
        flags.append("bulletin_time_unparsed")
    return TrackBuildResult(track_df=frame, flags=flags)
