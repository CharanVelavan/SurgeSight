"""Region config must reproduce the previously hard-coded Michaung defaults."""

from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.advisory import ASSETS_FILE, SUMMARY_FILE
from services.config import get_settings, list_regions, load_region
from services.scenario_engine import BASELINE_ASSETS_FILE, OUTPUT_CSV, TRACK_FILE
from services.wind_provider import DEFAULT_CACHE


def main() -> None:
    assert TRACK_FILE == Path("data/processed/michaung_track.csv")
    assert BASELINE_ASSETS_FILE == ASSETS_FILE == Path("data/processed/scored_assets.csv")
    assert SUMMARY_FILE == Path("data/processed/risk_summary.json")
    assert OUTPUT_CSV == Path("data/processed/scenario_assets.csv")
    assert DEFAULT_CACHE == Path("data/raw/wind/gfs_pressure_winds_michaung.npz")

    region = load_region("michaung_2023")
    assert region.bbox == {"west": 79.0, "south": 11.5, "east": 82.0, "north": 15.0}
    assert region.languages == ("English", "Tamil", "Telugu")
    assert "michaung_2023" in list_regions()
    try:
        load_region("does_not_exist")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("unknown region should raise")

    settings = get_settings()
    assert settings.dispatch_mode == "dry_run", "dispatch must default to dry_run"
    assert settings.gemini_model
    print("SURGESIGHT_CONFIG_OK")


if __name__ == "__main__":
    main()
