"""Run every SurgeSight test script and print a summary table.

Default: offline (live tests are SKIPPED). Pass --live to also call the Google APIs, which uses Gemini quota or credit.

A test passes only if it exits 0 and prints every expected marker. Scripts that call live
Google APIs are reported SKIPPED (never OK) when SURGESIGHT_OFFLINE=1.
Generated scenario outputs are restored afterwards so a test run leaves the repo clean.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable

# script -> markers it must print. live=True means it needs Google APIs.
TESTS: list[tuple[str, list[str], bool]] = [
    ("scripts/test_config.py", ["SURGESIGHT_CONFIG_OK"], False),
    ("scripts/test_weather_frames.py", ["SURGESIGHT_WEATHER_FRAMES_OK"], False),
    ("scripts/test_gemini_fallback.py", ["SURGESIGHT_GEMINI_FALLBACK_OK"], False),
    ("scripts/test_scenario_engine.py", ["SURGESIGHT_SCENARIO_BASELINE_MATCH_OK", "SURGESIGHT_SCENARIO_30KM_OK"], False),
    ("scripts/test_track_forecaster.py", ["SURGESIGHT_TRACK_FORECASTER_OK"], False),
    ("scripts/test_facility_quality.py", ["SURGESIGHT_FACILITY_QUALITY_OK"], False),
    ("scripts/test_ensemble.py", ["SURGESIGHT_ENSEMBLE_OK"], False),
    ("scripts/test_hazards.py", ["SURGESIGHT_RAINFALL_OK", "SURGESIGHT_SURGE_OK", "SURGESIGHT_RISK_V2_OK"], False),
    ("scripts/test_exposure.py", ["SURGESIGHT_EXPOSURE_OK"], False),
    ("scripts/test_satellite_validation.py", ["SURGESIGHT_SATELLITE_VALIDATION_OK"], True),
    ("scripts/test_grounding_guard.py", ["SURGESIGHT_GROUNDING_GUARD_OK"], False),
    ("scripts/test_tts.py", ["SURGESIGHT_TTS_MULTILINGUAL_OK"], True),
    ("scripts/test_terrain_landmask.py", ["SURGESIGHT_TERRAIN_LANDMASK_OK"], True),
    ("scripts/test_bulletin_parser.py", ["SURGESIGHT_BULLETIN_PARSER_OK"], True),
    ("scripts/test_bulletin_to_risk.py", ["SURGESIGHT_BULLETIN_TO_RISK_OK"], True),
    ("scripts/test_cap_parametric.py", ["SURGESIGHT_CAP_OK", "SURGESIGHT_PARAMETRIC_OK"], True),
    ("scripts/test_dispatch_monitor.py", ["SURGESIGHT_DISPATCH_DRYRUN_OK", "SURGESIGHT_MONITOR_OK"], True),
    ("scripts/test_firestore.py", ["SURGESIGHT_FIRESTORE_OK"], True),
    ("scripts/test_bigquery.py", ["SURGESIGHT_BIGQUERY_OK"], True),
    ("scripts/test_departments.py", ["SURGESIGHT_DEPARTMENTS_OK"], True),
    ("scripts/test_river_nwp.py", ["SURGESIGHT_RIVER_FLOOD_OK", "SURGESIGHT_NWP_COMPARISON_OK"], False),
    ("scripts/test_search_grounding.py", ["SURGESIGHT_SEARCH_GROUNDING_OK"], True),
    ("scripts/test_maps_tools.py", ["SURGESIGHT_MAPS_TOOLS_OK"], True),
    ("scripts/test_api.py", ["SURGESIGHT_API_OK"], True),
    ("scripts/test_web.py", ["SURGESIGHT_WEB_OK"], True),
    ("scripts/test_stt.py", ["SURGESIGHT_STT_OK"], True),
    ("scripts/test_live.py", ["SURGESIGHT_LIVE_OK"], True),
    ("scripts/test_agent.py", ["SURGESIGHT_AGENT_OK"], True),
    ("scripts/test_adk.py", ["SURGESIGHT_ADK_OK"], True),
]
GENERATED = [
    "data/processed/scenario_assets.csv",
    "data/processed/scenario_assets.geojson",
    "data/processed/scenario_summary.json",
]


def main() -> int:
    # Live tests call paid or quota-limited Google APIs (Gemini, TTS, Live, Maps). They run only with --live.
    args = [a for a in sys.argv[1:] if a != "--live"]
    offline = os.getenv("SURGESIGHT_OFFLINE") == "1" or "--live" not in sys.argv[1:]
    if offline:
        os.environ["SURGESIGHT_OFFLINE"] = "1"
    only = args
    backup = Path(tempfile.mkdtemp())
    for rel in GENERATED:
        if (ROOT / rel).exists():
            shutil.copy2(ROOT / rel, backup / Path(rel).name)
    rows = []
    try:
        for script, markers, live in TESTS:
            if only and not any(o in script for o in only):
                continue
            started = time.perf_counter()
            proc = subprocess.run(
                [PYTHON, script], cwd=ROOT, capture_output=True, text=True, env=os.environ.copy()
            )
            elapsed = time.perf_counter() - started
            out = proc.stdout + proc.stderr
            missing = [m for m in markers if m not in out]
            if proc.returncode != 0 or (missing and not (offline and live and "SKIPPED" in out)):
                status = "FAIL"
            elif missing:
                status = "SKIPPED"
            else:
                status = "OK"
            rows.append((script, status, elapsed, out if status == "FAIL" else ""))
    finally:
        for rel in GENERATED:
            saved = backup / Path(rel).name
            if saved.exists():
                shutil.copy2(saved, ROOT / rel)
        shutil.rmtree(backup, ignore_errors=True)

    print(f"{'test':45} {'status':8} {'seconds':>8}")
    for script, status, seconds, _ in rows:
        print(f"{script:45} {status:8} {seconds:8.1f}")
    failures = [r for r in rows if r[1] == "FAIL"]
    for script, _, _, out in failures:
        print(f"\n--- {script} ---\n{out[-2000:]}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
