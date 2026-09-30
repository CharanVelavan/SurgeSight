"""Weather frame test (UI S1): manifest complete, encoding round trip, cached atlases decode, leakage rule holds. Offline."""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services import weather_frames as wf


def test_encoding_round_trip() -> None:
    rng = np.random.default_rng(7)
    wind = rng.uniform(-wf.WIND_MAX, wf.WIND_MAX, size=(4, wf.HEIGHT, wf.WIDTH))
    err = np.abs(wf.decode_wind(wf.encode_wind(wind)) - wind).max()
    assert err <= 0.2, f"wind round-trip error {err:.3f} m/s"
    rain = np.concatenate([rng.uniform(0, 5, 2000), rng.uniform(5, wf.RAIN_MAX, 2000), [0.0, wf.RAIN_MAX]])
    back = wf.decode_rain(wf.encode_rain(rain))
    assert np.all(np.abs(back - rain) <= 0.011 * (1 + rain) + 1e-9), "rain round trip outside 1.1 % of (1 + r)"
    assert wf.encode_rain(np.array([np.nan, -3.0])).tolist() == [0, 0], "missing or negative rain must encode to zero"
    frames = rng.integers(0, 256, size=(25, wf.HEIGHT, wf.WIDTH, 3), dtype=np.uint8)
    assert np.array_equal(wf.unpack_atlas(wf.pack_atlas(frames), 25), frames), "atlas pack/unpack is not lossless"
    print("encoding ok")


def test_manifest_complete() -> dict:
    manifest = wf.load_manifest()
    hours = pd.date_range(wf.WINDOW_START, wf.WINDOW_END, freq="1h")
    for key in ("analysis_wind", "observed_rain"):
        entry = manifest[key]
        assert len(entry["frames"]) == len(hours) == 169, f"{key}: {len(entry['frames'])} frames"
        assert (wf.WEATHER_DIR / entry["file"]).is_file(), entry["file"]
        assert (entry["cols"], entry["rows"]) == wf.atlas_shape(len(hours))
    assert [c["cycle"] for c in manifest["forecast"]] == [wf.iso(t) for t in wf.cycle_times()]
    for cycle in manifest["forecast"]:
        assert len(cycle["frames"]) == len(wf.forecast_steps()) == 25
        assert cycle["frames"][0] == cycle["cycle"] and cycle["step_hours"] == 3
        assert (wf.WEATHER_DIR / cycle["file"]).is_file(), cycle["file"]
    print("manifest ok:", len(manifest["forecast"]), "forecast cycles")
    return manifest


def test_atlases_decode(manifest: dict) -> None:
    wind = wf.unpack_atlas(wf.WEATHER_DIR / manifest["analysis_wind"]["file"], 169)
    speed = np.hypot(wf.decode_wind(wind[..., 0]), wf.decode_wind(wind[..., 1]))
    assert 0.5 < speed.mean() < 15 and speed.max() < 60, f"implausible analysis wind mean {speed.mean():.1f} max {speed.max():.1f} m/s"
    rain = wf.decode_rain(wf.unpack_atlas(wf.WEATHER_DIR / manifest["observed_rain"]["file"], 169)[..., 0])
    assert rain.max() > 10, "IMERG should show heavy rain during Michaung"
    cycle = next(c for c in manifest["forecast"] if c["cycle"] == "2023-12-03T00:00:00Z")
    fc = wf.unpack_atlas(wf.WEATHER_DIR / cycle["file"], 25)
    assert wf.decode_rain(fc[..., 2]).max() > 5 and np.hypot(wf.decode_wind(fc[..., 0]), wf.decode_wind(fc[..., 1])).max() > 15, "the 3 Dec cycle should forecast a strong cyclone"
    assert wf.decode_rain(fc[0, ..., 2]).max() == 0, "f000 has no accumulation, rain must be zero"
    print("atlases decode ok")


def test_leakage_rule(manifest: dict) -> None:
    cutoff = pd.Timestamp("2023-12-03 12:00")
    sel = wf.frames_for_cutoff(manifest, cutoff)
    assert sel["forecast"]["cycle"] == "2023-12-03T12:00:00Z", "the cycle issued exactly at the cutoff is allowed and is the latest"
    assert all(wf.naive_utc(c["cycle"]) <= cutoff for c in [sel["forecast"]])
    later = wf.frames_for_cutoff(manifest, "2023-12-03 11:59")
    assert later["forecast"]["cycle"] == "2023-12-03T00:00:00Z", "a cycle issued after the cutoff must never be offered"
    for key in ("analysis_wind", "observed_rain"):
        assert all(wf.naive_utc(t) <= cutoff for t in sel[key]["frames"]), f"{key} leaks frames after the cutoff"
    assert sel["observed_rain"]["frames"][-1] == "2023-12-03T12:00:00Z"
    valid = wf.frames_for_cutoff(manifest, cutoff, validation=True)
    assert len(valid["observed_rain"]["frames"]) == 169 and valid["validation"] is True
    assert len(valid["analysis_wind"]["frames"]) < 169, "analysis wind after the cutoff is never served, even for validation"
    assert wf.frames_for_cutoff(manifest, "2023-11-29 00:00")["forecast"] is None, "before the first cycle there is no forecast"
    print("leakage rule ok")


if __name__ == "__main__":
    test_encoding_round_trip()
    manifest = test_manifest_complete()
    test_atlases_decode(manifest)
    test_leakage_rule(manifest)
    print("SURGESIGHT_WEATHER_FRAMES_OK")
