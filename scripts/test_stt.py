"""Speech round trip: Cloud TTS speaks a question, Cloud Speech-to-Text hears it (WP6.1)."""

from __future__ import annotations

import os
from pathlib import Path
import re
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.tts import plain_speech_text

CASES = {
    "en-IN": ("Which hospitals are at risk if the cyclone shifts thirty kilometres north?", {"hospitals", "risk", "cyclone", "north"}),
    "hi-IN": ("चक्रवात के उत्तर की ओर खिसकने पर कौन से अस्पताल खतरे में हैं", {"चक्रवात", "उत्तर", "अस्पताल"}),
    "ta-IN": ("புயல் வடக்கே நகர்ந்தால் எந்த மருத்துவமனைகள் ஆபத்தில் உள்ளன", {"புயல்", "வடக்கே", "மருத்துவமனைகள்"}),
    "te-IN": ("తుఫాను ఉత్తరం వైపు కదిలితే ఏ ఆసుపత్రులు ప్రమాదంలో ఉన్నాయి", {"తుఫాను", "ఉత్తరం", "ఆసుపత్రులు"}),
}


def test_plain_text() -> None:
    text = plain_speech_text("## Finding\n* **118 hospitals** are in tier 1 ([source](http://x)).\n1. Act now `run-1`")
    assert "#" not in text and "*" not in text and "http" not in text and "118 hospitals" in text and "Act now run-1" in text
    print("plain text ok")


def test_round_trip() -> None:
    if os.getenv("SURGESIGHT_OFFLINE") == "1":
        print("SKIPPED live speech test (SURGESIGHT_OFFLINE=1)")
        return
    from google.cloud import texttospeech

    from services.voice.stt import transcribe

    client = texttospeech.TextToSpeechClient()
    for code, (sentence, keywords) in CASES.items():
        audio = client.synthesize_speech(
            input=texttospeech.SynthesisInput(text=sentence), voice=texttospeech.VoiceSelectionParams(language_code=code),
            audio_config=texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.LINEAR16, sample_rate_hertz=16000),
        ).audio_content
        heard = transcribe(audio, code)
        words = {w.strip(".,?!।") for w in heard.text.lower().split()}  # split on spaces: \w breaks Indic combining marks
        hits = {k for k in keywords if k in words}
        print(f"{code}: {heard.text!r} confidence={heard.confidence} keywords {len(hits)}/{len(keywords)}")
        assert len(hits) >= len(keywords) - 1, f"{code}: heard {heard.text!r}"
    try:
        transcribe(b"", "en-IN")
        raise AssertionError("empty audio must be rejected")
    except ValueError:
        pass


if __name__ == "__main__":
    test_plain_text()
    test_round_trip()
    print("SURGESIGHT_STT_OK")
