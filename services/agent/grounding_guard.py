"""Number-provenance guard (§4.1): every number in an answer must appear in a tool output.

Gemini may not calculate or invent numbers. A number is grounded if it matches a number
found in the tool results of the same run at the precision the answer shows (so 30.4 matches
30.432, and 1,286 matches 1286). Years, the lead hours 6/12/24, the emergency number 112 and
numbers the user typed in the question are always allowed.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from pydantic import BaseModel

NUMBER_RE = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")
LIST_MARKER_RE = re.compile(r"(?m)^\s*(?:[-*]\s*)?\d{1,2}[.)]\s")
ALWAYS_ALLOWED = {6.0, 12.0, 24.0, 112.0, 0.0, 1.0}
YEAR_RANGE = range(1990, 2101)
REDACTION = "[unverified]"


def extract_numbers(text: str) -> list[str]:
    """Numbers in free text, ignoring markdown list numbering and identifiers like 'v2'."""
    text = LIST_MARKER_RE.sub(" ", text or "")
    return NUMBER_RE.findall(text)


def _value(token: str) -> tuple[float, int]:
    cleaned = token.replace(",", "")
    decimals = len(cleaned.split(".")[1]) if "." in cleaned else 0
    return float(cleaned), decimals


def _strings_and_numbers(obj: Any) -> Iterable[str]:
    if isinstance(obj, BaseModel):
        obj = obj.model_dump()
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from _strings_and_numbers(key)
            yield from _strings_and_numbers(value)
    elif isinstance(obj, (list, tuple, set)):
        for value in obj:
            yield from _strings_and_numbers(value)
    elif isinstance(obj, bool) or obj is None:
        return
    elif isinstance(obj, (int, float)):
        yield repr(obj)
    elif isinstance(obj, str):
        yield obj


def collect_allowed(tool_results: Iterable[Any], extra_text: str = "") -> list[float]:
    allowed: set[float] = set(ALWAYS_ALLOWED)
    for result in tool_results:
        data = result.model_dump() if isinstance(result, BaseModel) else result
        if isinstance(data, dict):
            payload = {"data": data.get("data"), "warnings": data.get("warnings")}
        else:
            payload = data
        for text in _strings_and_numbers(payload):
            for token in NUMBER_RE.findall(text):
                allowed.add(_value(token)[0])
            # scientific notation from repr(), e.g. 1e-05
            for token in re.findall(r"\d+(?:\.\d+)?[eE][-+]?\d+", text):
                allowed.add(float(token))
    for token in extract_numbers(extra_text):
        allowed.add(_value(token)[0])
    return sorted(allowed)


def check(answer_text: str, tool_results: Iterable[Any], *, question: str = "") -> list[str]:
    """Return the numbers in ``answer_text`` that no tool result supports (empty = grounded)."""
    allowed = collect_allowed(tool_results, question)
    problems: list[str] = []
    for token in extract_numbers(answer_text):
        value, decimals = _value(token)
        if decimals == 0 and int(value) in YEAR_RANGE and len(token) == 4:
            continue
        tolerance = 0.5 * 10 ** (-decimals) + 1e-9
        if any(abs(value - a) <= tolerance for a in allowed):
            continue
        problems.append(token)
    return problems


def redact(text: str, ungrounded: list[str]) -> str:
    """Replace each ungrounded number with a visible marker."""
    for token in sorted(set(ungrounded), key=len, reverse=True):
        text = re.sub(rf"(?<![\w.]){re.escape(token)}(?![\d])", REDACTION, text)
    return text
