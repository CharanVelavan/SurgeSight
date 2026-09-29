"""Latest bulletins and news through Gemini's built-in Google Search grounding (WP1.4).

This is a separate Gemini call: the built-in ``google_search`` tool is not combined with our custom
function declarations. Citations come from the grounding metadata, never from the model's text.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from google.genai import types

from services.gemini_client import generate_with_retry

SEARCH_NOTE = (
    "Web results found through Google Search grounding. They are reports, not SurgeSight outputs, "
    "and are not verified by SurgeSight. Official warnings come from IMD."
)


def _query(cyclone_name: str | None, region: str) -> str:
    subject = f"cyclone {cyclone_name}" if cyclone_name else "the active tropical cyclone"
    return (
        f"Latest official bulletin and news for {subject} affecting {region}. "
        "Give the most recent position, intensity, forecast track, landfall expectation and warnings "
        "from IMD or other official sources, with the time each was issued. "
        "If no active cyclone is found, say so plainly."
    )


def search_latest_bulletins(cyclone_name: str | None = None, region: str = "Andhra Pradesh and Tamil Nadu coast, India") -> dict[str, Any]:
    response = generate_with_retry(
        contents=_query(cyclone_name, region),
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.0,
            max_output_tokens=1500,
            system_instruction=(
                "You summarise cyclone bulletins for an emergency operations officer. Be factual and concise. "
                "Only report what the sources say. Never invent numbers."
            ),
        ),
    )
    candidate = response.candidates[0] if response.candidates else None
    metadata = getattr(candidate, "grounding_metadata", None)
    items: list[dict[str, str | None]] = []
    seen: set[str] = set()
    for chunk in (getattr(metadata, "grounding_chunks", None) or []):
        web = getattr(chunk, "web", None)
        if web is None or not web.uri or web.uri in seen:
            continue
        seen.add(web.uri)
        items.append({"title": web.title, "uri": web.uri, "domain": getattr(web, "domain", None)})
    return {
        "cyclone_name": cyclone_name,
        "region": region,
        "answer_text": (response.text or "").strip(),
        "items": items,
        "search_queries": list(getattr(metadata, "web_search_queries", None) or []),
        "grounded": bool(items),
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "label": SEARCH_NOTE,
    }
