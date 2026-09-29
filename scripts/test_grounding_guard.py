"""Grounding guard: catches injected numbers, accepts rounding, ignores allowed constants."""

from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.agent.grounding_guard import check, extract_numbers, redact
from services.agent.tools import ok_result


def main() -> None:
    result = ok_result(
        "run_scenario",
        {
            "newly_high_risk_hospitals": 18,
            "scenario_class_counts": {"HIGH": 1282, "CRITICAL": 4},
            "top": [{"name": "Radha Krishna Hospital", "distance_to_track_km": 30.432, "elevation_m": 8.0}],
            "window": "2023-12-04 12:00 UTC",
        },
        source="test",
    )
    results = [result]

    good = (
        "If the track shifts 30 km north, 18 hospitals become newly HIGH. 1,282 assets are HIGH and "
        "4 are CRITICAL. Radha Krishna Hospital is about 30.4 km from the track at 8 m elevation. "
        "Issued 4 December 2023. Call 112.\n1. Move patients.\n2. Fuel generators."
    )
    assert check(good, results, question="what if it shifts 30 km north?") == [], check(good, results)

    injected = good + " A further 987 shelters will flood."
    assert check(injected, results) == ["987"], check(injected, results)

    computed = "Together 1,286 assets are at HIGH or above."  # 1282 + 4: model-computed, not in a tool result
    assert check(computed, results) == ["1,286"]

    wrong_precision = "The hospital is 31.2 km away."
    assert check(wrong_precision, results) == ["31.2"]

    assert extract_numbers("Use v2 model; Gemini 3.7 is fast; 2 items") == ["3.7", "2"]
    redacted = redact(injected, ["987"])
    assert "987" not in redacted and "[unverified]" in redacted
    # 1,282 must survive redaction of a different number
    assert "1,282" in redacted
    print("SURGESIGHT_GROUNDING_GUARD_OK")


if __name__ == "__main__":
    main()
