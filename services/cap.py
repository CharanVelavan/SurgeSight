"""Common Alerting Protocol 1.2 alerts from department advisories (WP5.1).

Alerts are always ``status=Exercise`` and ``scope=Restricted``: SurgeSight is a decision-support prototype, not a
public warning source. The integration target for real use is SACHET, India's CAP-based alerting platform run by
NDMA. Output is validated against the OASIS CAP 1.2 XSD in ``config/cap/CAP-v1.2.xsd``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from typing import Any
from xml.sax.saxutils import escape

from lxml import etree
import pandas as pd
from shapely.geometry import shape

from services.advisory import RoleAdvisory
from services.config import PROJECT_ROOT, load_region
from services.departments import department_mask, get_department, score_all_assets
from services.exposure import exposure_summary

NAMESPACE = "urn:oasis:names:tc:emergency:cap:1.2"
XSD_FILE = PROJECT_ROOT / "config" / "cap" / "CAP-v1.2.xsd"
SENDER = "surgesight-exercise@surgesight.invalid"
SEVERITY = {"CRITICAL": "Extreme", "HIGH": "Severe", "MODERATE": "Moderate", "LOW": "Minor"}
LANGUAGE_TAGS = {"English": "en-IN", "Tamil": "ta-IN", "Telugu": "te-IN", "Hindi": "hi-IN", "Odia": "or-IN", "Bengali": "bn-IN"}
MAX_POLYGONS = 3
WEB = "https://surgesight.invalid/exercise"


class CapValidationError(ValueError):
    pass


@lru_cache(maxsize=1)
def _schema() -> etree.XMLSchema:
    return etree.XMLSchema(etree.parse(str(XSD_FILE)))


def validate_cap(xml: str) -> None:
    """Raise CapValidationError unless ``xml`` is well-formed CAP 1.2."""
    try:
        document = etree.fromstring(xml.encode("utf-8"))
    except etree.XMLSyntaxError as exc:
        raise CapValidationError(f"not well-formed XML: {exc}") from exc
    if not _schema().validate(document):
        raise CapValidationError("; ".join(str(e) for e in _schema().error_log)[:600])


def _polygons(footprint: dict[str, Any] | None) -> list[str]:
    if not footprint:
        return []
    geometry = shape(footprint)
    parts = sorted(getattr(geometry, "geoms", [geometry]), key=lambda g: g.area, reverse=True)[:MAX_POLYGONS]
    rings = []
    for part in parts:
        coords = list(part.exterior.coords)
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        rings.append(" ".join(f"{lat:.4f},{lon:.4f}" for lon, lat in coords))
    return rings


def _footprint(department: str, frame: pd.DataFrame | None) -> tuple[list[str], dict[str, Any] | None]:
    dept = get_department(department)
    frame = score_all_assets() if frame is None else frame
    mine = frame[department_mask(dept, frame)]
    summary = exposure_summary(mine, rule="class_high_plus", include_footprint=True)
    districts = [d["district"] for d in summary["by_district"] if d["population"] > 0][:8]
    return districts, summary.get("footprint_geojson")


def _text(tag: str, value: str) -> str:
    return f"<{tag}>{escape(value)}</{tag}>"


def build_cap_alert(
    advisory: RoleAdvisory | dict[str, Any],
    language: str = "English",
    *,
    frame: pd.DataFrame | None = None,
    previous: str | None = None,
    sent: datetime | None = None,
    sequence: int = 1,
) -> str:
    """CAP 1.2 XML for one department advisory. ``previous`` (an earlier identifier) turns it into an Update."""
    adv = advisory if isinstance(advisory, RoleAdvisory) else RoleAdvisory.model_validate(advisory)
    if language not in LANGUAGE_TAGS:
        raise ValueError(f"Unsupported CAP language: {language}")
    dept = get_department(adv.audience)
    sent = (sent or datetime.now(timezone.utc)).astimezone(timezone.utc)
    stamp = sent.strftime("%Y%m%dT%H%M%SZ")
    identifier = f"SURGESIGHT-{load_region().id}-{dept.id}-{stamp}-{sequence}"
    districts, footprint = _footprint(adv.audience, frame)
    severity = SEVERITY.get(adv.severity, "Unknown")
    description = adv.situation_summary
    if adv.priority_actions:
        description += "\n" + "\n".join(f"- {a}" for a in adv.priority_actions)
    description += "\n" + adv.disclaimer
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<alert xmlns="{NAMESPACE}">',
        _text("identifier", identifier), _text("sender", SENDER), _text("sent", sent.strftime("%Y-%m-%dT%H:%M:%S+00:00")),
        _text("status", "Exercise"), _text("msgType", "Update" if previous else "Alert"), _text("source", "SurgeSight"),
        _text("scope", "Restricted"), _text("restriction", "SurgeSight exercise. Test recipients only. Not an official warning."),
    ]
    if previous:
        lines.append(_text("references", f"{SENDER},{previous},{sent.strftime('%Y-%m-%dT%H:%M:%S+00:00')}"))
    lines += [
        "<info>", _text("language", LANGUAGE_TAGS[language]), _text("category", "Met"),
        _text("event", f"{load_region().display_name} screening impact ({dept.short_name})"),
        _text("responseType", "Prepare"), _text("urgency", "Expected"), _text("severity", severity), _text("certainty", "Possible"),
        _text("senderName", "SurgeSight decision support (exercise)"),
        _text("headline", adv.headline or f"{load_region().display_name}: {dept.short_name} advisory"),
        _text("description", description), _text("instruction", adv.instruction or "; ".join(adv.priority_actions[:2])),
        _text("web", WEB), "<area>", _text("areaDesc", ", ".join(districts) or load_region().display_name),
    ]
    lines += [_text("polygon", ring) for ring in _polygons(footprint)]
    lines += ["</area>", "</info>", "</alert>"]
    xml = "\n".join(lines)
    validate_cap(xml)
    return xml


def build_cap_from_run(run_id: str, **kwargs: Any) -> str:
    """CAP XML for a stored advisory run (kind 'advisory', as created by the draft_advisory tool)."""
    from services.store import get_store

    record = get_store().get(run_id)
    if record["kind"] != "advisory":
        raise ValueError(f"{run_id} is not an advisory run")
    payload = dict(record["payload"])
    language = payload.pop("language", "English")
    return build_cap_alert(payload, language, **kwargs)
