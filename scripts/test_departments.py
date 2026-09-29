"""Departments (WP4): config, asset layers, per-department ranking, advisory context, languages."""

from __future__ import annotations

import os
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import services.agent  # noqa: F401
from services.advisory import AUDIENCES, DISCLAIMERS, LANGUAGES, build_advisory_context
from services.agent.tools import execute_tool
from services.assets import load_all_assets, load_core_assets, load_extra_assets
from services.departments import department_priority, get_department, load_departments
from services.tts import LANGUAGE_CODES, TEXT_ONLY_LANGUAGES, audio_supported

NEW_TYPES = {"fire_station", "police_station", "water_facility", "fishing_harbour"}


def test_config_and_assets() -> None:
    departments = load_departments()
    assert len(departments) == 7 and len(AUDIENCES) == 7
    assert get_department("Health").id == "health" and get_department("Health Department").id == "health"
    core, extra, both = load_core_assets(), load_extra_assets(), load_all_assets()
    assert len(core) == 3977, "core baseline must stay frozen"
    assert set(extra["asset_type"]) == NEW_TYPES and len(both) == len(core) + len(extra)
    assert not both.duplicated(["osm_element", "osm_id"]).any()
    print("config ok", extra["asset_type"].value_counts().to_dict())


def test_priorities() -> None:
    for key, dept in departments_iter():
        result = department_priority(key, n=5)
        assert result["assets"] > 0, key
        assert sum(result["class_counts"].values()) == result["assets"], key
        assert result["top_assets"] and set(a["asset_type"] for a in result["top_assets"]) <= set(dept.asset_types), key
        scores = [a["combined_v2"] for a in result["top_assets"]]
        assert scores == sorted(scores, reverse=True)
    health = department_priority("health", n=5)
    assert all(a["asset_type"] == "hospital" for a in health["top_assets"])
    tool, _ = execute_tool("department_priority", {"department": "Electricity Board", "top_n": 3})
    assert tool.ok and len(tool.data["top_assets"]) == 3, tool.error
    print("priorities ok")


def departments_iter():
    return load_departments().items()


def test_advisory_context() -> None:
    for name in AUDIENCES:
        context, assets = build_advisory_context(name)
        assert context["required_severity"] in {"MODERATE", "HIGH", "CRITICAL"} and assets, name
        assert all(a.asset_type in context["department_asset_types"] for a in assets), name
    print("advisory context ok")


def test_languages() -> None:
    assert set(LANGUAGES) == set(DISCLAIMERS) == {"English", "Tamil", "Telugu", "Hindi", "Odia", "Bengali"}
    assert audio_supported("Hindi") and audio_supported("Bengali") and not audio_supported("Odia")
    assert "Odia" in TEXT_ONLY_LANGUAGES and set(LANGUAGE_CODES) | set(TEXT_ONLY_LANGUAGES) == set(LANGUAGES)
    print("languages ok")


def test_live_advisory() -> None:
    if os.getenv("SURGESIGHT_OFFLINE") == "1":
        print("SKIPPED live advisory (SURGESIGHT_OFFLINE=1)")
        return
    from services.advisory import generate_role_advisory

    for audience, language in (("Police / Traffic", "Odia"), ("Water & Sewage Board", "Bengali")):
        advisory = generate_role_advisory(audience, language)
        assert advisory.headline and advisory.instruction and advisory.priority_actions, audience
        assert advisory.disclaimer == DISCLAIMERS[language] and advisory.audience == audience
        names = {a.name for a in advisory.critical_assets}
        assert names and all(n for n in names)
    print("live advisory ok")


if __name__ == "__main__":
    test_config_and_assets()
    test_priorities()
    test_advisory_context()
    test_languages()
    test_live_advisory()
    print("SURGESIGHT_DEPARTMENTS_OK")
