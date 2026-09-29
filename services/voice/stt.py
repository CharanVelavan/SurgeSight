"""Speech-to-Text (WP6.1): transcribe a short push-to-talk recording with Google Cloud Speech-to-Text."""

from __future__ import annotations

from dataclasses import dataclass
import os

from dotenv import load_dotenv

LANGUAGE_CODES = {"English": "en-IN", "Tamil": "ta-IN", "Telugu": "te-IN", "Hindi": "hi-IN", "Bengali": "bn-IN"}
MAX_SYNC_SECONDS = 58  # synchronous recognition accepts up to about one minute of audio
# "latest_short" was the most accurate model on a TTS round trip in en-IN, hi-IN, ta-IN and te-IN (2026-09-29).


@dataclass(frozen=True)
class Transcript:
    text: str
    confidence: float | None
    language_code: str


def transcribe(audio_bytes: bytes, language_code: str = "en-IN", *, sample_rate_hz: int | None = None) -> Transcript:
    """Transcribe WAV or FLAC audio (the format ``st.audio_input`` records). The sample rate is read from the header."""
    from google.cloud import speech

    load_dotenv()
    if not audio_bytes:
        raise ValueError("No audio to transcribe")
    client = speech.SpeechClient()
    config = speech.RecognitionConfig(
        language_code=language_code, enable_automatic_punctuation=True, model="latest_short",
        **({"sample_rate_hertz": sample_rate_hz, "encoding": speech.RecognitionConfig.AudioEncoding.LINEAR16} if sample_rate_hz else {}),
    )
    response = client.recognize(config=config, audio=speech.RecognitionAudio(content=audio_bytes))
    parts = [r.alternatives[0] for r in response.results if r.alternatives]
    if not parts:
        return Transcript("", None, language_code)
    confidence = sum(p.confidence for p in parts) / len(parts)
    return Transcript(" ".join(p.transcript.strip() for p in parts), round(confidence, 3), language_code)
