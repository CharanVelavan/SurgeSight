"""CAP 1.2 alerts (WP5.1) and illustrative parametric triggers (WP5.2). Offline except the Gemini brief."""

from __future__ import annotations

import os
from pathlib import Path
import re
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lxml import etree

from services.advisory import AdvisoryAsset, DISCLAIMERS, RoleAdvisory
from services.cap import CapValidationError, NAMESPACE, build_cap_alert, validate_cap
from services.parametric import evaluate, payout_pct, with_crore


def advisory(audience: str, severity: str = "CRITICAL") -> RoleAdvisory:
    return RoleAdvisory(
        audience=audience, severity=severity, headline="Test headline", situation_summary="Situation.", instruction="Do this first.",
        priority_actions=["Act one", "Act two"], critical_assets=[AdvisoryAsset(name="X", asset_type="hospital", risk_class="HIGH", combined_risk_score=0.5, distance_to_track_km=3.0)],
        monitoring_priorities=["Watch"], disclaimer=DISCLAIMERS["English"],
    )


def test_cap() -> None:
    ns = {"c": NAMESPACE}
    for name, expected in (("Health Department", "Extreme"), ("Fisheries Department", "Extreme")):
        xml = build_cap_alert(advisory(name), "English")
        validate_cap(xml)
        doc = etree.fromstring(xml.encode())
        assert doc.findtext("c:status", namespaces=ns) == "Exercise" and doc.findtext("c:scope", namespaces=ns) == "Restricted"
        assert doc.findtext("c:msgType", namespaces=ns) == "Alert"
        assert doc.findtext("c:info/c:severity", namespaces=ns) == expected
        assert doc.findtext("c:info/c:headline", namespaces=ns) == "Test headline"
        assert doc.findtext("c:info/c:area/c:areaDesc", namespaces=ns)
        polygon = doc.findtext("c:info/c:area/c:polygon", namespaces=ns)
        points = polygon.split()
        assert points and points[0] == points[-1] and len(points) >= 4, "polygon must be a closed ring"
    for severity, cap_value in (("HIGH", "Severe"), ("MODERATE", "Moderate"), ("LOW", "Minor")):
        assert f"<severity>{cap_value}</severity>" in build_cap_alert(advisory("Electricity Board", severity), "English")
    first = build_cap_alert(advisory("Police / Traffic"), "Hindi")
    identifier = re.search(r"<identifier>(.*?)</identifier>", first).group(1)
    update = build_cap_alert(advisory("Police / Traffic"), "Hindi", previous=identifier, sequence=2)
    assert "<msgType>Update</msgType>" in update and identifier in update and "<language>hi-IN</language>" in update
    for bad in ("<alert>", build_cap_alert(advisory("Health Department")).replace("<status>Exercise</status>", "<status>Bogus</status>")):
        try:
            validate_cap(bad)
            raise AssertionError("invalid CAP accepted")
        except CapValidationError:
            pass
    print("cap ok")


def test_parametric() -> None:
    tiers = [{"at": 10, "payout_pct": 25}, {"at": 20, "payout_pct": 50}]
    assert payout_pct(5, tiers) == 0 and payout_pct(10, tiers) == 25 and payout_pct(99, tiers) == 50
    result = evaluate(members=30)
    assert result["illustrative"] and "ILLUSTRATIVE" in result["label"] and len(result["portfolios"]) == 4
    for p in result["portfolios"]:
        assert 0 <= p["payout_pct"] <= 100 and p["payout_inr"] <= p["sum_insured_inr"]
        assert {t["id"] for t in p["triggers"]} == {"wind", "rain_24h", "surge"}
        assert all(0 <= t["probability"] <= 1 for t in p["triggers"])
        assert p["payout_p10_inr"] <= p["expected_payout_inr"] <= p["payout_p90_inr"] * 1.0001 or p["payout_p10_inr"] <= p["payout_p90_inr"]
    assert evaluate(members=30)["ensemble"]["expected_total_payout_inr"] == result["ensemble"]["expected_total_payout_inr"], "seeded, so repeatable"
    weak = pd.read_csv(PROJECT_ROOT / "data/processed/michaung_track.csv").assign(WIND_KMH=20.0, LAT=lambda d: d["LAT"] - 8.0)
    calm = evaluate(weak)
    assert calm["total_payout_inr"] < result["total_payout_inr"], "a weak distant track must pay less"
    crore = with_crore(result)
    assert "total_payout_inr" not in crore and abs(crore["total_payout_crore"] * 1e7 - result["total_payout_inr"]) < 1e6
    print("parametric ok", crore["total_payout_crore"], "crore on the reference track")


def test_brief() -> None:
    if os.getenv("SURGESIGHT_OFFLINE") == "1":
        print("SKIPPED live liquidity brief (SURGESIGHT_OFFLINE=1)")
        return
    import services.agent  # noqa: F401
    from services.agent import grounding_guard
    from services.agent.tools import execute_tool

    result, _ = execute_tool("parametric_triggers", {"members": 20})
    assert result.ok, result.error
    brief = result.data["liquidity_brief"]
    text = brief["headline"] + " " + brief["summary"] + " " + " ".join(brief["liquidity_actions"] + brief["caveats"])
    assert "llustrative" in text, "the brief must call the figures illustrative"
    problems = grounding_guard.check(text, [result])
    assert not problems, f"ungrounded numbers in the liquidity brief: {problems}"
    print("brief ok")


if __name__ == "__main__":
    test_cap()
    print("SURGESIGHT_CAP_OK")
    test_parametric()
    test_brief()
    print("SURGESIGHT_PARAMETRIC_OK")
