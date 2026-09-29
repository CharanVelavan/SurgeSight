"""Separate real hospitals from clinics, dental, eye-care, labs, etc. in OSM data (K5).

This only adds a label. Risk scores (v1) are never changed by it; v2 and the
department views filter on ``facility_quality == "hospital"``.
"""

from __future__ import annotations

import re

import pandas as pd


NON_HOSPITAL_PATTERN = re.compile(
    r"\b(dental|dentistry|dentist|clinics?|pharmacy|diagnostics?|scan|scans|labs?|"
    r"laborator(?:y|ies)|optical|opticals|eye\s*care)\b",
    re.IGNORECASE,
)
HOSPITAL = "hospital"
OTHER = "clinic_or_other"
NOT_APPLICABLE = "not_applicable"


def classify_facility(name: object, amenity: object, healthcare: object) -> str:
    """Return ``hospital`` or ``clinic_or_other`` for a hospital-tagged OSM record."""
    tagged = str(amenity).lower() == "hospital" or str(healthcare).lower() == "hospital"
    if not tagged:
        return OTHER
    if isinstance(name, str) and NON_HOSPITAL_PATTERN.search(name):
        return OTHER
    return HOSPITAL


def add_facility_quality(assets: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with a ``facility_quality`` column (hospital rows only are classified)."""
    out = assets.copy()
    is_hospital = out["asset_type"] == "hospital"
    out["facility_quality"] = NOT_APPLICABLE
    out.loc[is_hospital, "facility_quality"] = [
        classify_facility(n, a, h)
        for n, a, h in zip(
            out.loc[is_hospital, "name"],
            out.loc[is_hospital, "amenity"],
            out.loc[is_hospital, "healthcare"],
        )
    ]
    return out
