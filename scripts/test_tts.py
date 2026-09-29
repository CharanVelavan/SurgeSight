"""TTS tests: byte-safe truncation (offline) and live multilingual synthesis."""

from __future__ import annotations

import os
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.advisory import RoleAdvisory
from services.tts import MAX_TTS_BYTES, _truncate_utf8, synthesize_advisory


SAMPLES = {
    "English": "Cyclone impact is expected along the coast. Move patients to upper floors.",
    "Tamil": "புயல் கடலோரப் பகுதிகளைத் தாக்கும் என எதிர்பார்க்கப்படுகிறது. நோயாளிகளை மேல் தளங்களுக்கு மாற்றவும்.",
    "Telugu": "తుఫాను తీర ప్రాంతాలను తాకే అవకాశం ఉంది. రోగులను పై అంతస్తులకు తరలించండి.",
}


def test_truncation() -> None:
    for language, sentence in SAMPLES.items():
        long_text = " ".join([sentence] * 200)
        assert len(long_text.encode("utf-8")) > MAX_TTS_BYTES, language
        clipped = _truncate_utf8(long_text)
        assert len(clipped.encode("utf-8")) <= MAX_TTS_BYTES, language
        assert clipped.endswith((".", "।")), f"{language}: not cut at a sentence"
    short = "Short text."
    assert _truncate_utf8(short) == short
    # No sentence boundary at all: must still be valid UTF-8 within the limit.
    blob = "த" * 5000
    clipped = _truncate_utf8(blob)
    assert len(clipped.encode("utf-8")) <= MAX_TTS_BYTES
    clipped.encode("utf-8")


def make_advisory(language: str) -> RoleAdvisory:
    sentence = SAMPLES[language]
    return RoleAdvisory(
        audience="Health",
        severity="HIGH",
        situation_summary=" ".join([sentence] * 120),  # deliberately over the limit
        priority_actions=[sentence],
        disclaimer=sentence,
    )


def main() -> None:
    test_truncation()
    print("truncation tests passed")
    if os.getenv("SURGESIGHT_OFFLINE") == "1":
        print("SKIPPED live synthesis (SURGESIGHT_OFFLINE=1)")
        return
    for language in SAMPLES:
        audio = synthesize_advisory(make_advisory(language), language)
        assert len(audio) > 1000, f"{language}: audio too small"
        print(f"{language}: {len(audio)} bytes of MP3")
    print("SURGESIGHT_TTS_MULTILINGUAL_OK")


if __name__ == "__main__":
    main()
