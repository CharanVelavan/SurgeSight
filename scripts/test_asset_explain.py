"""Asset explanation test (W4): facts complete, distance rules, grounded text accepted, ungrounded text replaced. Offline."""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services import asset_explain as ax
from services.departments import score_all_assets


def sample():
    frame = score_all_assets()
    return frame.sort_values("combined_v2", ascending=False).iloc[0], frame.sort_values("combined_v2").iloc[0], ax.reference_track()


def test_facts() -> dict:
    top, bottom, track = sample()
    facts = ax.build_facts(top, track, pd.Timestamp("2023-12-04 00:00"), pd.Timestamp("2023-12-04 12:00"))
    for key in ("elevation_m", "waterlogging", "wind_peak_kmh", "surge_m", "distance", "class", "hazard_contributions", "disclaimer"):
        assert key in facts, key
    assert facts["distance"]["closest_approach_km"] > 0 and facts["distance"]["distance_at_time_km"] is not None
    after = ax.build_facts(top, track, pd.Timestamp("2023-12-05 00:00"), pd.Timestamp("2023-12-03 12:00"))
    assert after["distance"]["distance_at_time_km"] is None and "forecast" in after["distance"]["distance_at_time_note"], "no distance from a forecast position"
    low = ax.build_facts(bottom, track)
    assert low["class"] != facts["class"] or low["score"] < facts["score"]
    print("facts ok")
    return facts


def test_narrative(facts: dict) -> None:
    text, source = ax.narrate(facts, generate=lambda prompt: ax.Narrative(summary=f"{facts['name']} scores {facts['score']} and is {facts['class']}.", reasons=[]))
    assert source == "gemini", "text using only numbers from the facts must be accepted"
    text, source = ax.narrate(facts, generate=lambda prompt: ax.Narrative(summary="Expect 4,321 people affected and 17 outages.", reasons=[]))
    assert source == "template" and "4,321" not in text.summary, "invented numbers must be replaced by the template"
    def boom(prompt):
        raise RuntimeError("quota")
    assert ax.narrate(facts, generate=boom)[1] == "template", "a Gemini failure falls back to the template"
    seen: list[str] = []
    ax.narrate(facts, generate=lambda prompt: seen.append(prompt) or ax.Narrative(summary="x", reasons=[]), language="Tamil")
    assert "Write in Tamil" in seen[0] and "Latin digits" in seen[0], "the language must reach the prompt"
    template = ax.template_text(facts)
    assert not ax.grounding_guard.check(" ".join([template.summary, *template.reasons]), [{"data": facts}]), "the template itself must be grounded"
    print("narrative ok")


if __name__ == "__main__":
    f = test_facts()
    test_narrative(f)
    print("SURGESIGHT_ASSET_EXPLAIN_OK")
