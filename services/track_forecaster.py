"""SurgeSight Experimental Track Forecast.

Short-range statistical track extrapolation for historical replay and research.
This is NOT an official meteorological forecast; IMD remains authoritative.

Two models share one linear Kalman filter over the state ``[x, y, vx, vy]``
(metres and m/s in a local azimuthal-equidistant projection centred on the
last observed fix):

* Position-only Kalman — constant velocity with white-noise acceleration::

      x(k+1) = F x(k) + w,        w ~ N(0, Q)

* Wind-informed Kalman — the velocity relaxes toward the environmental
  steering flow plus a fixed beta drift, entered as a control input::

      x(k+1) = F_a x(k) + B_a u(k) + w
      u(k)   = V_steer(position, time <= cutoff) + V_beta
      a      = 1 - exp(-dt / tau)

  The steering field is frozen at the cutoff for forecast steps, so no wind
  data valid after the cutoff is used.

Only original IBTrACS fixes (IFLAG 'O', the 00/06/12/18 UTC synoptic times) are
assimilated; 3-hourly interpolated positions depend on the next fix and would
leak future information.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

import numpy as np
import pandas as pd
from pyproj import Transformer

from services.risk_model import haversine_km
from services.wind_provider import WGS84, WindGrid


FORECAST_LABEL = "SurgeSight Experimental Track Forecast"
DISCLAIMER = (
    "Experimental forecast — not an official meteorological forecast. "
    "IMD bulletins remain authoritative."
)
SCIENTIFIC_NOTES = [
    "Kalman extrapolation is a short-term statistical method; it cannot anticipate "
    "recurvature or motion changes that are not already visible in recent fixes.",
    "Environmental wind steering (weighted 850/500/200 hPa annulus-mean GFS winds plus a "
    "fixed beta drift) is experimental; weights were set a priori, not tuned.",
    "The steering field is frozen at the cutoff; the model does not use NWP forecast winds.",
    "24-hour positions carry substantially more uncertainty than 6-hour positions.",
    "This model is not a replacement for numerical weather prediction or operational "
    "cyclone forecasting. IMD remains authoritative.",
]
MODEL_KALMAN = "position_only_kalman"
MODEL_WIND = "wind_informed_kalman"
MODEL_LABELS = {
    MODEL_KALMAN: "Position-only Kalman",
    MODEL_WIND: "Wind-informed experimental",
}
HORIZONS_HOURS = (6, 12, 24)
PATH_STEP_HOURS = 3
MAX_LEAD_HOURS = 24
MIN_OBSERVATIONS = 3
SYNOPTIC_HOURS = {0, 6, 12, 18}
CHI2_2DOF_90 = -2.0 * math.log(0.10)
ELLIPSE_VERTICES = 72


class InsufficientObservationsError(ValueError):
    """Raised when too few fixes precede the cutoff for a stable filter."""


@dataclass(frozen=True)
class KalmanConfig:
    """A-priori filter settings (not tuned against Michaung)."""

    observation_sigma_km: float = 15.0
    # Continuous white-noise acceleration PSD; velocity random walk ~2.5 m/s per day.
    acceleration_psd_m2_s3: float = 7.0e-5
    initial_velocity_sigma_ms: float = 8.0
    max_step_hours: float = 3.0


@dataclass(frozen=True)
class WindModelConfig:
    """Experimental steering-relaxation settings (not tuned against Michaung)."""

    relaxation_hours: float = 24.0
    beta_drift_speed_ms: float = 1.5
    beta_drift_toward_bearing_deg: float = 315.0
    steering_sigma_ms: float = 1.5


@dataclass
class TrackForecast:
    model: str
    cutoff: pd.Timestamp
    points: pd.DataFrame
    observations_used: int
    first_observation_time: pd.Timestamp
    last_observation_time: pd.Timestamp
    wind_data_valid_until: pd.Timestamp | None = None
    cutoff_steering: dict[str, Any] | None = None
    config: dict[str, Any] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return MODEL_LABELS[self.model]

    def at_lead(self, lead_hours: int) -> pd.Series:
        match = self.points[self.points["lead_hours"].eq(lead_hours)]
        if match.empty:
            raise KeyError(f"No forecast at +{lead_hours} h")
        return match.iloc[0]

    def horizons(self) -> pd.DataFrame:
        return self.points[self.points["lead_hours"].isin(HORIZONS_HOURS)].reset_index(drop=True)


class LocalProjection:
    """Azimuthal-equidistant projection centred on one fix (metres, x east, y north)."""

    def __init__(self, lat0: float, lon0: float) -> None:
        crs = f"+proj=aeqd +lat_0={lat0} +lon_0={lon0} +datum=WGS84 +units=m +no_defs"
        self._forward = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        self._inverse = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)

    def to_xy(self, lat: Any, lon: Any) -> tuple[Any, Any]:
        return self._forward.transform(lon, lat)

    def to_latlon(self, x: Any, y: Any) -> tuple[Any, Any]:
        lon, lat = self._inverse.transform(x, y)
        return lat, lon

    def velocity_to_xy(self, lat: float, lon: float, u_ms: float, v_ms: float) -> np.ndarray:
        """Convert an east/north velocity at a point into projected m/s."""

        speed = math.hypot(u_ms, v_ms)
        if speed == 0:
            return np.zeros(2)
        seconds = 3600.0
        bearing = math.degrees(math.atan2(u_ms, v_ms))
        end_lon, end_lat, _ = WGS84.fwd(lon, lat, bearing, speed * seconds)
        x0, y0 = self.to_xy(lat, lon)
        x1, y1 = self.to_xy(end_lat, end_lon)
        return np.array([(x1 - x0) / seconds, (y1 - y0) / seconds])


def is_original_observation(track: pd.DataFrame) -> pd.Series:
    """True for original best-track fixes; False for IBTrACS-interpolated rows."""

    if "IFLAG" in track.columns:
        return track["IFLAG"].astype(str).str[0].eq("O")
    times = pd.to_datetime(track["ISO_TIME"])
    return times.dt.hour.isin(SYNOPTIC_HOURS) & times.dt.minute.eq(0)


def prepare_track(track: pd.DataFrame) -> pd.DataFrame:
    """Parse, validate, and chronologically order a track."""

    required = {"ISO_TIME", "LAT", "LON"}
    if missing := required - set(track.columns):
        raise ValueError(f"Track missing columns: {sorted(missing)}")
    frame = track.copy()
    frame["ISO_TIME"] = pd.to_datetime(frame["ISO_TIME"])
    frame["LAT"] = pd.to_numeric(frame["LAT"], errors="coerce")
    frame["LON"] = pd.to_numeric(frame["LON"], errors="coerce")
    frame = frame.dropna(subset=["ISO_TIME", "LAT", "LON"])
    frame = frame.sort_values("ISO_TIME", kind="stable")
    frame = frame.drop_duplicates(subset=["ISO_TIME"], keep="first").reset_index(drop=True)
    if not frame["LAT"].between(-90, 90).all() or not frame["LON"].between(-180, 180).all():
        raise ValueError("Track contains invalid coordinates")
    return frame


def observations_until(track: pd.DataFrame, cutoff: pd.Timestamp | str) -> pd.DataFrame:
    """Original fixes at or before the cutoff — the only data a forecast may see."""

    cutoff = pd.Timestamp(cutoff)
    frame = prepare_track(track)
    frame = frame[is_original_observation(frame) & frame["ISO_TIME"].le(cutoff)]
    return frame.reset_index(drop=True)


def forecast_cutoffs(track: pd.DataFrame, *, require_lead_hours: int = 0) -> list[pd.Timestamp]:
    """Synoptic cutoffs with enough history (and, optionally, later truth)."""

    frame = prepare_track(track)
    fixes = frame[is_original_observation(frame)].reset_index(drop=True)
    times = list(fixes["ISO_TIME"])
    last = frame["ISO_TIME"].max()
    return [
        time for index, time in enumerate(times)
        if index + 1 >= MIN_OBSERVATIONS
        and time + pd.Timedelta(hours=require_lead_hours) <= last
    ]


def covariance_is_valid(matrix: np.ndarray, *, tolerance: float = 1e-6) -> bool:
    if not np.all(np.isfinite(matrix)):
        return False
    if not np.allclose(matrix, matrix.T, rtol=1e-9, atol=tolerance):
        return False
    return bool(np.linalg.eigvalsh(matrix).min() > 0)


def _transition(dt: float, relaxation: float) -> tuple[np.ndarray, np.ndarray]:
    """State transition F and control matrix B for one step of dt seconds.

    ``relaxation`` is a = 1 - exp(-dt/tau) (0 for the position-only model).
    Position advances with the step-mean velocity (trapezoidal integration).
    """

    a = relaxation
    F = np.array([
        [1.0, 0.0, dt * (1.0 - a / 2.0), 0.0],
        [0.0, 1.0, 0.0, dt * (1.0 - a / 2.0)],
        [0.0, 0.0, 1.0 - a, 0.0],
        [0.0, 0.0, 0.0, 1.0 - a],
    ])
    B = np.array([
        [dt * a / 2.0, 0.0],
        [0.0, dt * a / 2.0],
        [a, 0.0],
        [0.0, a],
    ])
    return F, B


def _process_noise(dt: float, psd: float, extra_velocity_variance: float = 0.0) -> np.ndarray:
    block = psd * np.array([[dt**3 / 3.0, dt**2 / 2.0], [dt**2 / 2.0, dt]])
    Q = np.zeros((4, 4))
    for axis in (0, 1):
        Q[np.ix_([axis, axis + 2], [axis, axis + 2])] = block
    Q[2, 2] += extra_velocity_variance
    Q[3, 3] += extra_velocity_variance
    return Q


ControlFn = Callable[[np.ndarray, pd.Timestamp], np.ndarray]


class _Filter:
    def __init__(
        self,
        config: KalmanConfig,
        control: ControlFn | None = None,
        wind_config: WindModelConfig | None = None,
    ) -> None:
        self.config = config
        self.control = control
        self.wind_config = wind_config
        sigma_obs = config.observation_sigma_km * 1000.0
        self.R = np.eye(2) * sigma_obs**2
        self.H = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])

    def initialise(self, xy: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        state = np.array([xy[0], xy[1], 0.0, 0.0])
        sigma_v = self.config.initial_velocity_sigma_ms
        P = np.diag([self.R[0, 0], self.R[1, 1], sigma_v**2, sigma_v**2])
        return state, P

    def predict(
        self, state: np.ndarray, P: np.ndarray, start: pd.Timestamp, hours: float
    ) -> tuple[np.ndarray, np.ndarray]:
        remaining = hours
        time = start
        while remaining > 1e-9:
            step_hours = min(self.config.max_step_hours, remaining)
            dt = step_hours * 3600.0
            if self.control is None:
                F, B = _transition(dt, 0.0)
                Q = _process_noise(dt, self.config.acceleration_psd_m2_s3)
                state = F @ state
            else:
                assert self.wind_config is not None
                a = 1.0 - math.exp(-step_hours / self.wind_config.relaxation_hours)
                F, B = _transition(dt, a)
                Q = _process_noise(
                    dt,
                    self.config.acceleration_psd_m2_s3,
                    (a * self.wind_config.steering_sigma_ms) ** 2,
                )
                state = F @ state + B @ self.control(state, time)
            P = F @ P @ F.T + Q
            P = 0.5 * (P + P.T)
            remaining -= step_hours
            time = time + pd.Timedelta(hours=step_hours)
        return state, P

    def update(
        self, state: np.ndarray, P: np.ndarray, measurement: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        innovation = measurement - self.H @ state
        S = self.H @ P @ self.H.T + self.R
        K = P @ self.H.T @ np.linalg.inv(S)
        state = state + K @ innovation
        identity_minus_kh = np.eye(4) - K @ self.H
        # Joseph form keeps P symmetric positive definite.
        P = identity_minus_kh @ P @ identity_minus_kh.T + K @ self.R @ K.T
        return state, 0.5 * (P + P.T)


def _ellipse_parameters(position_covariance: np.ndarray) -> dict[str, float]:
    eigenvalues, eigenvectors = np.linalg.eigh(position_covariance)
    order = np.argsort(eigenvalues)[::-1]
    eigenvalues, eigenvectors = eigenvalues[order], eigenvectors[:, order]
    major_vector = eigenvectors[:, 0]
    bearing = math.degrees(math.atan2(major_vector[0], major_vector[1])) % 180.0
    scale = math.sqrt(CHI2_2DOF_90)
    semi_major = math.sqrt(max(eigenvalues[0], 0.0)) * scale / 1000.0
    semi_minor = math.sqrt(max(eigenvalues[1], 0.0)) * scale / 1000.0
    return {
        "sigma_major_km": math.sqrt(max(eigenvalues[0], 0.0)) / 1000.0,
        "sigma_minor_km": math.sqrt(max(eigenvalues[1], 0.0)) / 1000.0,
        "ellipse90_semi_major_km": semi_major,
        "ellipse90_semi_minor_km": semi_minor,
        "ellipse_major_bearing_deg": bearing,
        # Conservative circle that contains the 90% ellipse.
        "uncertainty_radius_km": semi_major,
    }


def forecast_track(
    track: pd.DataFrame,
    cutoff: pd.Timestamp | str,
    model: str = MODEL_KALMAN,
    *,
    wind_grid: WindGrid | None = None,
    config: KalmanConfig | None = None,
    wind_config: WindModelConfig | None = None,
    max_lead_hours: int = MAX_LEAD_HOURS,
) -> TrackForecast:
    """Forecast from original fixes at or before ``cutoff`` only."""

    if model not in MODEL_LABELS:
        raise ValueError(f"Unknown model {model!r}")
    cutoff = pd.Timestamp(cutoff)
    config = config or KalmanConfig()
    wind_config = wind_config or WindModelConfig()
    observed = observations_until(track, cutoff)
    if len(observed) < MIN_OBSERVATIONS:
        raise InsufficientObservationsError(
            f"{len(observed)} fixes at or before {cutoff}; need {MIN_OBSERVATIONS}"
        )
    last_fix = observed.iloc[-1]
    projection = LocalProjection(float(last_fix["LAT"]), float(last_fix["LON"]))
    xs, ys = projection.to_xy(observed["LAT"].to_numpy(float), observed["LON"].to_numpy(float))
    measurements = np.column_stack([xs, ys])
    times = list(observed["ISO_TIME"])

    control: ControlFn | None = None
    cutoff_steering: dict[str, Any] | None = None
    wind_valid_until: pd.Timestamp | None = None
    if model == MODEL_WIND:
        if wind_grid is None:
            raise ValueError("Wind-informed model requires a wind grid")
        # Physically remove all wind data valid after the cutoff.
        visible_winds = wind_grid.until(cutoff)
        wind_valid_until = pd.Timestamp(visible_winds.times[-1])
        beta_bearing = math.radians(wind_config.beta_drift_toward_bearing_deg)
        beta_u = wind_config.beta_drift_speed_ms * math.sin(beta_bearing)
        beta_v = wind_config.beta_drift_speed_ms * math.cos(beta_bearing)

        def control(state: np.ndarray, time: pd.Timestamp) -> np.ndarray:
            lat, lon = projection.to_latlon(state[0], state[1])
            wind_time = min(time, cutoff)
            steering = visible_winds.steering_vector(float(lat), float(lon), wind_time)
            return projection.velocity_to_xy(
                float(lat), float(lon), steering.u_ms + beta_u, steering.v_ms + beta_v
            )

        cutoff_steering = visible_winds.steering_vector(
            float(last_fix["LAT"]), float(last_fix["LON"]), cutoff
        ).as_dict()

    kalman = _Filter(config, control, wind_config if model == MODEL_WIND else None)
    state, P = kalman.initialise(measurements[0])
    for previous_time, time, measurement in zip(times[:-1], times[1:], measurements[1:]):
        hours = (time - previous_time).total_seconds() / 3600.0
        state, P = kalman.predict(state, P, previous_time, hours)
        state, P = kalman.update(state, P, measurement)
    if not covariance_is_valid(P):
        raise RuntimeError("Filter covariance became invalid")

    rows: list[dict[str, Any]] = []
    lead_time = times[-1]
    lead_hours = 0
    covariance = P
    while True:
        lat, lon = projection.to_latlon(state[0], state[1])
        speed = math.hypot(state[2], state[3])
        rows.append({
            "model": model,
            "model_label": MODEL_LABELS[model],
            "forecast_label": FORECAST_LABEL,
            "cutoff_time": cutoff,
            "lead_hours": lead_hours,
            "valid_time": lead_time,
            "lat": float(lat),
            "lon": float(lon),
            "motion_speed_ms": speed,
            "motion_toward_bearing_deg": math.degrees(math.atan2(state[2], state[3])) % 360.0,
            **_ellipse_parameters(covariance[:2, :2]),
            "covariance_valid": covariance_is_valid(covariance),
            "_x": float(state[0]),
            "_y": float(state[1]),
            "_cov": covariance[:2, :2].copy(),
        })
        if lead_hours >= max_lead_hours:
            break
        state, covariance = kalman.predict(state, covariance, lead_time, PATH_STEP_HOURS)
        lead_time = lead_time + pd.Timedelta(hours=PATH_STEP_HOURS)
        lead_hours += PATH_STEP_HOURS

    points = pd.DataFrame(rows)
    points.attrs["projection"] = projection
    return TrackForecast(
        model=model,
        cutoff=cutoff,
        points=points,
        observations_used=len(observed),
        first_observation_time=times[0],
        last_observation_time=times[-1],
        wind_data_valid_until=wind_valid_until,
        cutoff_steering=cutoff_steering,
        config={
            "kalman": asdict(config),
            **({"wind": asdict(wind_config)} if model == MODEL_WIND else {}),
        },
    )


def position_error_km(forecast_row: pd.Series, lat: float, lon: float) -> float:
    return haversine_km(float(forecast_row["lat"]), float(forecast_row["lon"]), lat, lon)


def mahalanobis_squared(forecast: TrackForecast, lead_hours: int, lat: float, lon: float) -> float:
    """Squared Mahalanobis distance of a verifying position under the forecast covariance."""

    row = forecast.at_lead(lead_hours)
    projection: LocalProjection = forecast.points.attrs["projection"]
    x, y = projection.to_xy(lat, lon)
    error = np.array([x - row["_x"], y - row["_y"]])
    return float(error @ np.linalg.solve(row["_cov"], error))


def ellipse_polygon(forecast: TrackForecast, lead_hours: int) -> list[list[float]]:
    """90% uncertainty ellipse as a closed [lon, lat] ring."""

    row = forecast.at_lead(lead_hours)
    projection: LocalProjection = forecast.points.attrs["projection"]
    eigenvalues, eigenvectors = np.linalg.eigh(row["_cov"])
    scale = math.sqrt(CHI2_2DOF_90)
    angles = np.linspace(0.0, 2.0 * math.pi, ELLIPSE_VERTICES, endpoint=False)
    unit = np.stack([np.cos(angles), np.sin(angles)])
    offsets = eigenvectors @ (np.sqrt(np.maximum(eigenvalues, 0.0))[:, None] * scale * unit)
    lat, lon = projection.to_latlon(row["_x"] + offsets[0], row["_y"] + offsets[1])
    ring = [[float(a), float(b)] for a, b in zip(lon, lat)]
    return ring + [ring[0]]


def public_points(forecast: TrackForecast) -> pd.DataFrame:
    """Forecast rows without internal projection/covariance helper columns."""

    return forecast.points.drop(columns=["_x", "_y", "_cov"])


# ---------------------------------------------------------------------------
# Infrastructure-impact comparison (reuses services.scenario_engine unchanged)
# ---------------------------------------------------------------------------

INTENSITY_MODES = ("reference", "persistence")


def reference_track_window(track: pd.DataFrame, cutoff: pd.Timestamp, lead_hours: int = MAX_LEAD_HOURS) -> pd.DataFrame:
    frame = prepare_track(track)
    end = pd.Timestamp(cutoff) + pd.Timedelta(hours=lead_hours)
    return frame[frame["ISO_TIME"].le(end)].reset_index(drop=True)


def forecast_scenario_track(
    track: pd.DataFrame,
    forecast: TrackForecast,
    *,
    intensity_mode: str = "reference",
) -> pd.DataFrame:
    """Observed history to the cutoff followed by the experimental forecast path.

    ``reference`` intensity copies the reference track's wind at each valid time so
    that impact differences isolate track position. ``persistence`` holds the last
    observed wind (no later information).
    """

    if intensity_mode not in INTENSITY_MODES:
        raise ValueError(f"intensity_mode must be one of {INTENSITY_MODES}")
    frame = prepare_track(track)
    history = frame[frame["ISO_TIME"].le(forecast.cutoff)]
    future = public_points(forecast)
    future = future[future["lead_hours"].gt(0)]
    if intensity_mode == "reference":
        winds = frame.set_index("ISO_TIME")["WIND_KMH"]
        missing = set(future["valid_time"]) - set(winds.index)
        if missing:
            raise ValueError(
                f"Reference intensity unavailable for {sorted(missing)[0]}; use persistence"
            )
        future_winds = winds.loc[future["valid_time"]].to_numpy(float)
    else:
        future_winds = np.full(len(future), float(history["WIND_KMH"].iloc[-1]))
    forecast_rows = pd.DataFrame({
        "ISO_TIME": future["valid_time"].to_numpy(),
        "LAT": future["lat"].to_numpy(float),
        "LON": future["lon"].to_numpy(float),
        "WIND_KMH": future_winds,
        "SOURCE": forecast.model,
    })
    history = history[["ISO_TIME", "LAT", "LON", "WIND_KMH"]].assign(SOURCE="observed")
    return pd.concat([history, forecast_rows], ignore_index=True)


def _impact_counts(scored: pd.DataFrame) -> dict[str, int]:
    high = scored["scenario_risk_class"].isin({"HIGH", "CRITICAL"})
    return {
        "high_plus_assets": int(high.sum()),
        "critical_assets": int(scored["scenario_risk_class"].eq("CRITICAL").sum()),
        "high_plus_hospitals": int((high & scored["asset_type"].eq("hospital")).sum()),
        "high_plus_substations": int((high & scored["asset_type"].eq("substation")).sum()),
    }


def compare_track_impacts(
    track: pd.DataFrame,
    forecasts: dict[str, TrackForecast],
    *,
    intensity_mode: str = "reference",
    baseline_assets: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Deterministic infrastructure risk under reference and experimental tracks."""

    from services.scenario_engine import score_custom_track

    if not forecasts:
        raise ValueError("At least one forecast is required")
    cutoff = next(iter(forecasts.values())).cutoff
    tracks = {"reference": reference_track_window(track, cutoff)}
    for model, forecast in forecasts.items():
        if forecast.cutoff != cutoff:
            raise ValueError("All forecasts must share one cutoff")
        tracks[model] = forecast_scenario_track(track, forecast, intensity_mode=intensity_mode)

    scored = {
        name: score_custom_track(frame, baseline_assets)
        for name, frame in tracks.items()
    }
    counts = {name: _impact_counts(frame) for name, frame in scored.items()}
    reference_class = scored["reference"]["scenario_risk_class"]
    order = {"LOW": 0, "MODERATE": 1, "HIGH": 2, "CRITICAL": 3}
    results: dict[str, Any] = {}
    for name, frame in scored.items():
        entry: dict[str, Any] = {
            "label": "Observed reference" if name == "reference" else MODEL_LABELS[name],
            **counts[name],
        }
        if name != "reference":
            entry["delta_vs_reference"] = {
                key: counts[name][key] - counts["reference"][key] for key in counts[name]
            }
            class_shift = frame["scenario_risk_class"].map(order) - reference_class.map(order)
            entry["assets_class_raised_vs_reference"] = int(class_shift.gt(0).sum())
            entry["assets_class_lowered_vs_reference"] = int(class_shift.lt(0).sum())
            entry["mean_abs_score_change_vs_reference"] = round(float(
                (frame["scenario_risk_score"] - scored["reference"]["scenario_risk_score"]).abs().mean()
            ), 4)
        results[name] = entry
    end = cutoff + pd.Timedelta(hours=MAX_LEAD_HOURS)
    return {
        "cutoff_time": cutoff.isoformat(),
        "track_window": f"storm start → {end.isoformat()} (cutoff + {MAX_LEAD_HOURS} h)",
        "intensity_mode": intensity_mode,
        "intensity_note": (
            "Forecast points use the reference track's observed wind at each valid time, "
            "so differences isolate track position."
            if intensity_mode == "reference"
            else "Forecast points hold the last observed wind (persistence)."
        ),
        "asset_count": int(len(scored["reference"])),
        "tracks": results,
        "scored_assets": scored,
        "scenario_tracks": tracks,
    }


# ---------------------------------------------------------------------------
# End-to-end experimental forecast (used by the generator script and the UI)
# ---------------------------------------------------------------------------

DEFAULT_DEMO_CUTOFF = pd.Timestamp("2023-12-03 12:00:00")


def verification_errors(track: pd.DataFrame, forecast: TrackForecast) -> dict[str, float | None]:
    """Great-circle error against later original fixes (historical replay only)."""

    frame = prepare_track(track)
    fixes = frame[is_original_observation(frame)].set_index("ISO_TIME")
    errors: dict[str, float | None] = {}
    for lead in HORIZONS_HOURS:
        valid = forecast.cutoff + pd.Timedelta(hours=lead)
        if valid in fixes.index:
            truth = fixes.loc[valid]
            errors[f"{lead}h"] = round(
                position_error_km(forecast.at_lead(lead), float(truth["LAT"]), float(truth["LON"])), 1
            )
        else:
            errors[f"{lead}h"] = None
    return errors


def forecast_geojson(forecast: TrackForecast, track: pd.DataFrame) -> dict[str, Any]:
    frame = observations_until(track, forecast.cutoff)
    points = public_points(forecast)
    base = {
        "forecast_label": FORECAST_LABEL,
        "disclaimer": DISCLAIMER,
        "model": forecast.model,
        "model_label": forecast.label,
        "cutoff_time": forecast.cutoff.isoformat(),
    }
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[float(lon), float(lat)] for lat, lon in zip(frame["LAT"], frame["LON"])],
            },
            "properties": {**base, "feature": "observed_history_used"},
        },
        {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[float(lon), float(lat)] for lat, lon in zip(points["lat"], points["lon"])],
            },
            "properties": {**base, "feature": "forecast_track"},
        },
    ]
    for _, row in points.iterrows():
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(row["lon"]), float(row["lat"])]},
            "properties": {
                **base,
                "feature": "forecast_point",
                "lead_hours": int(row["lead_hours"]),
                "timestamp": row["valid_time"].isoformat(),
                "lat": round(float(row["lat"]), 4),
                "lon": round(float(row["lon"]), 4),
                "uncertainty_radius_km": round(float(row["uncertainty_radius_km"]), 1),
                "ellipse90_semi_major_km": round(float(row["ellipse90_semi_major_km"]), 1),
                "ellipse90_semi_minor_km": round(float(row["ellipse90_semi_minor_km"]), 1),
                "ellipse_major_bearing_deg": round(float(row["ellipse_major_bearing_deg"]), 1),
            },
        })
    for lead in HORIZONS_HOURS:
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [ellipse_polygon(forecast, lead)]},
            "properties": {**base, "feature": "uncertainty_ellipse_90pct", "lead_hours": lead},
        })
    return {"type": "FeatureCollection", "features": features}


def _horizon_records(forecast: TrackForecast) -> list[dict[str, Any]]:
    records = []
    for _, row in forecast.horizons().iterrows():
        records.append({
            "lead_hours": int(row["lead_hours"]),
            "timestamp": row["valid_time"].isoformat(),
            "lat": round(float(row["lat"]), 4),
            "lon": round(float(row["lon"]), 4),
            "uncertainty_radius_km": round(float(row["uncertainty_radius_km"]), 1),
            "ellipse90_semi_major_km": round(float(row["ellipse90_semi_major_km"]), 1),
            "ellipse90_semi_minor_km": round(float(row["ellipse90_semi_minor_km"]), 1),
            "model": forecast.model,
        })
    return records


def run_experimental_forecast(
    track: pd.DataFrame,
    cutoff: pd.Timestamp | str = DEFAULT_DEMO_CUTOFF,
    *,
    wind_grid: WindGrid | None,
    intensity_mode: str = "reference",
    include_impacts: bool = True,
) -> dict[str, Any]:
    """Forecast both models, verify against later fixes, and compare impacts."""

    import time

    started = time.perf_counter()
    cutoff = pd.Timestamp(cutoff)
    forecasts = {MODEL_KALMAN: forecast_track(track, cutoff, MODEL_KALMAN)}
    wind_error: str | None = None
    if wind_grid is not None:
        forecasts[MODEL_WIND] = forecast_track(track, cutoff, MODEL_WIND, wind_grid=wind_grid)
    else:
        wind_error = "Wind data unavailable; wind-informed model skipped."

    frame = prepare_track(track)
    fixes = frame[is_original_observation(frame)].set_index("ISO_TIME")
    reference = []
    for lead in HORIZONS_HOURS:
        valid = cutoff + pd.Timedelta(hours=lead)
        if valid in fixes.index:
            reference.append({
                "lead_hours": lead, "timestamp": valid.isoformat(),
                "lat": float(fixes.loc[valid, "LAT"]), "lon": float(fixes.loc[valid, "LON"]),
            })

    impacts = None
    if include_impacts:
        can_use_reference = frame["ISO_TIME"].max() >= cutoff + pd.Timedelta(hours=MAX_LEAD_HOURS)
        impacts = compare_track_impacts(
            track, forecasts,
            intensity_mode=intensity_mode if can_use_reference else "persistence",
        )

    summary = {
        "forecast_label": FORECAST_LABEL,
        "disclaimer": DISCLAIMER,
        "scientific_notes": SCIENTIFIC_NOTES,
        "cutoff_time": cutoff.isoformat(),
        "observations_used": forecasts[MODEL_KALMAN].observations_used,
        "last_observation_time": forecasts[MODEL_KALMAN].last_observation_time.isoformat(),
        "reference_positions": reference,
        "models": {
            model: {
                "label": forecast.label,
                "forecast": _horizon_records(forecast),
                "verification_error_km": verification_errors(track, forecast),
                "wind_data_valid_until": (
                    forecast.wind_data_valid_until.isoformat()
                    if forecast.wind_data_valid_until is not None else None
                ),
                "cutoff_steering": forecast.cutoff_steering,
                "config": forecast.config,
            }
            for model, forecast in forecasts.items()
        },
        "wind_model_status": wind_error or "ok",
        "wind_source": wind_grid.metadata if wind_grid is not None else None,
    }
    if impacts is not None:
        summary["infrastructure_impact"] = {
            key: value for key, value in impacts.items()
            if key not in {"scored_assets", "scenario_tracks"}
        }
    summary["runtime_seconds"] = round(time.perf_counter() - started, 3)
    return {"summary": summary, "forecasts": forecasts, "impacts": impacts}
