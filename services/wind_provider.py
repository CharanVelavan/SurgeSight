"""Real upper-air environmental winds for the SurgeSight experimental track model.

Source: Open-Meteo Historical Forecast API serving archived NOAA GFS 0.25 degree
(``gfs_global``) pressure-level winds. Values at a valid time come from the
operational GFS run initialised at or shortly before that time, so a wind field
valid at or before a forecast cutoff contains no information from after it.

The downloaded grid is cached locally so historical replays run offline. Every
steering request is checked against ``available_until`` to prevent future-data
leakage during backtesting.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests
from pyproj import Geod


API_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
MODEL = "gfs_global"
SOURCE_DESCRIPTION = (
    "Open-Meteo Historical Forecast API — archived NOAA GFS 0.25° (gfs_global) "
    "pressure-level u/v winds"
)
LEVELS = (850, 500, 200)
# Experimental deep-layer steering weights, chosen a priori (shallower layers weighted
# more for a sub-severe system) and NOT tuned against Michaung.
STEERING_WEIGHTS = {850: 0.45, 500: 0.35, 200: 0.20}
# Annulus average removes the storm's own symmetric circulation from the environment.
ANNULUS_RADII_KM = (300.0, 450.0, 600.0)
ANNULUS_AZIMUTHS = 16
TRAILING_WINDOW_HOURS = 6
DEFAULT_CACHE = Path("data/raw/wind/gfs_pressure_winds_michaung.npz")
GRID_LATS = np.arange(0.0, 27.0, 1.0)
GRID_LONS = np.arange(72.0, 97.0, 1.0)
BATCH_SIZE = 100
BATCH_PAUSE_SECONDS = 12.0
MAX_ATTEMPTS = 5
WGS84 = Geod(ellps="WGS84")


class WindDataUnavailable(RuntimeError):
    """Raised when real wind data cannot be loaded or downloaded."""


class FutureWindAccessError(RuntimeError):
    """Raised when a caller requests wind data valid after its information cutoff."""


@dataclass(frozen=True)
class SteeringVector:
    u_ms: float
    v_ms: float
    level_winds_ms: dict[int, tuple[float, float]]
    valid_time: pd.Timestamp
    window_start: pd.Timestamp
    samples: int

    @property
    def speed_ms(self) -> float:
        return math.hypot(self.u_ms, self.v_ms)

    @property
    def toward_bearing_deg(self) -> float:
        return math.degrees(math.atan2(self.u_ms, self.v_ms)) % 360.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "u_ms": round(self.u_ms, 3),
            "v_ms": round(self.v_ms, 3),
            "speed_ms": round(self.speed_ms, 3),
            "toward_bearing_deg": round(self.toward_bearing_deg, 1),
            "levels": {
                f"{level}hPa": {"u_ms": round(u, 3), "v_ms": round(v, 3)}
                for level, (u, v) in self.level_winds_ms.items()
            },
            "valid_time": self.valid_time.isoformat(),
            "window_start": self.window_start.isoformat(),
            "samples": self.samples,
        }


@dataclass(frozen=True)
class WindGrid:
    times: np.ndarray
    lats: np.ndarray
    lons: np.ndarray
    u: dict[int, np.ndarray]
    v: dict[int, np.ndarray]
    metadata: dict[str, Any] = field(default_factory=dict)
    available_until: pd.Timestamp | None = None

    @property
    def last_time(self) -> pd.Timestamp:
        return pd.Timestamp(self.times[-1])

    def until(self, cutoff: pd.Timestamp | str) -> "WindGrid":
        """Return a copy that physically contains only data valid at or before cutoff."""

        cutoff = pd.Timestamp(cutoff)
        mask = self.times <= np.datetime64(cutoff.to_datetime64(), "s")
        if not mask.any():
            raise WindDataUnavailable(f"No wind data valid at or before {cutoff}")
        return WindGrid(
            times=self.times[mask],
            lats=self.lats,
            lons=self.lons,
            u={level: values[mask] for level, values in self.u.items()},
            v={level: values[mask] for level, values in self.v.items()},
            metadata=self.metadata,
            available_until=cutoff,
        )

    def _bilinear(self, field_values: np.ndarray, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
        lat_step = float(self.lats[1] - self.lats[0])
        lon_step = float(self.lons[1] - self.lons[0])
        row = np.clip((lats - self.lats[0]) / lat_step, 0, len(self.lats) - 1.000001)
        col = np.clip((lons - self.lons[0]) / lon_step, 0, len(self.lons) - 1.000001)
        r0, c0 = np.floor(row).astype(int), np.floor(col).astype(int)
        fr, fc = row - r0, col - c0
        return (
            field_values[..., r0, c0] * (1 - fr) * (1 - fc)
            + field_values[..., r0 + 1, c0] * fr * (1 - fc)
            + field_values[..., r0, c0 + 1] * (1 - fr) * fc
            + field_values[..., r0 + 1, c0 + 1] * fr * fc
        )

    def steering_vector(
        self, lat: float, lon: float, valid_time: pd.Timestamp | str
    ) -> SteeringVector:
        """Annulus-mean, trailing-window, layer-weighted steering flow at a position."""

        valid_time = pd.Timestamp(valid_time)
        if self.available_until is not None and valid_time > self.available_until:
            raise FutureWindAccessError(
                f"Wind requested for {valid_time} but data cutoff is {self.available_until}"
            )
        window_start = valid_time - pd.Timedelta(hours=TRAILING_WINDOW_HOURS)
        end = np.datetime64(valid_time.to_datetime64(), "s")
        start = np.datetime64(window_start.to_datetime64(), "s")
        indices = np.flatnonzero((self.times >= start) & (self.times <= end))
        if indices.size == 0:
            raise WindDataUnavailable(f"No wind data in window {window_start} → {valid_time}")

        radii = np.repeat(np.asarray(ANNULUS_RADII_KM) * 1000.0, ANNULUS_AZIMUTHS)
        azimuths = np.tile(np.linspace(0.0, 360.0, ANNULUS_AZIMUTHS, endpoint=False), len(ANNULUS_RADII_KM))
        ring_lon, ring_lat, _ = WGS84.fwd(
            np.full(radii.size, lon), np.full(radii.size, lat), azimuths, radii
        )
        level_winds: dict[int, tuple[float, float]] = {}
        for level in LEVELS:
            u_samples = self._bilinear(self.u[level][indices], ring_lat, ring_lon)
            v_samples = self._bilinear(self.v[level][indices], ring_lat, ring_lon)
            if np.isnan(u_samples).mean() > 0.25 or np.isnan(v_samples).mean() > 0.25:
                raise WindDataUnavailable(f"Too many missing {level} hPa wind samples")
            level_winds[level] = (float(np.nanmean(u_samples)), float(np.nanmean(v_samples)))
        steer_u = sum(STEERING_WEIGHTS[level] * level_winds[level][0] for level in LEVELS)
        steer_v = sum(STEERING_WEIGHTS[level] * level_winds[level][1] for level in LEVELS)
        return SteeringVector(
            u_ms=float(steer_u),
            v_ms=float(steer_v),
            level_winds_ms=level_winds,
            valid_time=valid_time,
            window_start=window_start,
            samples=int(indices.size),
        )


def _hourly_variables() -> list[str]:
    return [
        f"{kind}_{level}hPa" for level in LEVELS for kind in ("wind_speed", "wind_direction")
    ]


def _speed_direction_to_uv(speed: np.ndarray, direction_deg: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    # Meteorological direction is where the wind blows FROM.
    radians = np.radians(direction_deg)
    return -speed * np.sin(radians), -speed * np.cos(radians)


def _request_batch(
    session: requests.Session,
    points: list[tuple[float, float]],
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    params = {
        "latitude": ",".join(f"{lat:.2f}" for lat, _ in points),
        "longitude": ",".join(f"{lon:.2f}" for _, lon in points),
        "hourly": ",".join(_hourly_variables()),
        "wind_speed_unit": "ms",
        "timezone": "GMT",
        "models": MODEL,
        "start_date": start_date,
        "end_date": end_date,
    }
    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = session.get(API_URL, params=params, timeout=120)
            if response.status_code == 429 or response.status_code >= 500:
                raise requests.HTTPError(f"HTTP {response.status_code}: {response.text[:200]}")
            response.raise_for_status()
            payload = response.json()
            payload = payload if isinstance(payload, list) else [payload]
            if len(payload) != len(points):
                raise WindDataUnavailable("Open-Meteo returned an unexpected number of locations")
            return payload
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt < MAX_ATTEMPTS:
                time.sleep(min(60.0, 5.0 * 2 ** (attempt - 1)))
    raise WindDataUnavailable(f"Open-Meteo wind download failed: {last_error}") from last_error


def fetch_wind_grid(
    start_date: str,
    end_date: str,
    *,
    lats: np.ndarray = GRID_LATS,
    lons: np.ndarray = GRID_LONS,
    progress: bool = True,
) -> WindGrid:
    points = [(float(lat), float(lon)) for lat in lats for lon in lons]
    session = requests.Session()
    times: np.ndarray | None = None
    arrays: dict[str, np.ndarray] = {}
    for offset in range(0, len(points), BATCH_SIZE):
        batch = points[offset:offset + BATCH_SIZE]
        if progress:
            print(f"  Downloading GFS winds: points {offset + 1}-{offset + len(batch)} of {len(points)}")
        payload = _request_batch(session, batch, start_date, end_date)
        for local_index, location in enumerate(payload):
            hourly = location["hourly"]
            if times is None:
                times = pd.to_datetime(hourly["time"]).to_numpy(dtype="datetime64[s]")
                for variable in _hourly_variables():
                    arrays[variable] = np.full((len(times), len(points)), np.nan)
            for variable in _hourly_variables():
                values = np.array(
                    [np.nan if value is None else value for value in hourly[variable]], dtype=float
                )
                arrays[variable][:, offset + local_index] = values
        if offset + BATCH_SIZE < len(points):
            time.sleep(BATCH_PAUSE_SECONDS)
    if times is None:
        raise WindDataUnavailable("No wind data returned")

    shape = (len(times), len(lats), len(lons))
    u_fields: dict[int, np.ndarray] = {}
    v_fields: dict[int, np.ndarray] = {}
    for level in LEVELS:
        u_values, v_values = _speed_direction_to_uv(
            arrays[f"wind_speed_{level}hPa"], arrays[f"wind_direction_{level}hPa"]
        )
        u_fields[level] = u_values.reshape(shape)
        v_fields[level] = v_values.reshape(shape)
        missing = float(np.isnan(u_fields[level]).mean())
        if missing > 0.05:
            raise WindDataUnavailable(f"{level} hPa wind grid is {missing:.0%} missing")
    metadata = {
        "source": SOURCE_DESCRIPTION,
        "api_url": API_URL,
        "model": MODEL,
        "levels_hpa": list(LEVELS),
        "start_date": start_date,
        "end_date": end_date,
        "grid_lat_range": [float(lats[0]), float(lats[-1])],
        "grid_lon_range": [float(lons[0]), float(lons[-1])],
        "grid_spacing_deg": float(lats[1] - lats[0]),
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    return WindGrid(times=times, lats=np.asarray(lats), lons=np.asarray(lons),
                    u=u_fields, v=v_fields, metadata=metadata)


def save_wind_grid(grid: WindGrid, path: Path = DEFAULT_CACHE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    arrays = {
        "times": grid.times.astype("datetime64[s]").astype("int64"),
        "lats": grid.lats,
        "lons": grid.lons,
        "metadata": np.array(json.dumps(grid.metadata)),
    }
    for level in LEVELS:
        arrays[f"u{level}"] = grid.u[level].astype("float32")
        arrays[f"v{level}"] = grid.v[level].astype("float32")
    temporary = path.with_name(path.stem + ".tmp.npz")
    np.savez_compressed(temporary, **arrays)
    temporary.replace(path)


def read_wind_grid(path: Path = DEFAULT_CACHE) -> WindGrid:
    with np.load(path, allow_pickle=False) as data:
        return WindGrid(
            times=data["times"].astype("datetime64[s]"),
            lats=data["lats"].astype(float),
            lons=data["lons"].astype(float),
            u={level: data[f"u{level}"].astype(float) for level in LEVELS},
            v={level: data[f"v{level}"].astype(float) for level in LEVELS},
            metadata=json.loads(str(data["metadata"])),
        )


def wind_date_range(track: pd.DataFrame) -> tuple[str, str]:
    times = pd.to_datetime(track["ISO_TIME"])
    start = (times.min() - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    end = (times.max() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    return start, end


def load_wind_grid(
    track: pd.DataFrame,
    *,
    cache_path: Path = DEFAULT_CACHE,
    allow_download: bool = True,
) -> WindGrid:
    """Load cached GFS winds covering the track period, downloading once if needed."""

    start_date, end_date = wind_date_range(track)
    if cache_path.exists():
        grid = read_wind_grid(cache_path)
        covers = (
            pd.Timestamp(grid.times[0]) <= pd.Timestamp(start_date)
            and pd.Timestamp(grid.times[-1]) >= pd.Timestamp(end_date)
        )
        if covers:
            return grid
    if not allow_download:
        raise WindDataUnavailable(
            f"Wind cache {cache_path} missing or incomplete; run "
            "scripts/backtest_track_forecast.py once with network access"
        )
    grid = fetch_wind_grid(start_date, end_date)
    save_wind_grid(grid, cache_path)
    return grid
