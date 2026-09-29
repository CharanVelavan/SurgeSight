"""Google Cloud Text-to-Speech helper without stored service-account keys."""

from __future__ import annotations

import base64
import os
import subprocess

import google.auth
from google.auth.transport.requests import Request
from google.cloud import texttospeech
import requests
from dotenv import load_dotenv

from services.advisory import RoleAdvisory


LANGUAGE_CODES = {"English": "en-IN", "Tamil": "ta-IN", "Telugu": "te-IN"}
MAX_TTS_BYTES = 4800  # Cloud TTS limit is 5,000 bytes of input text
_SENTENCE_ENDINGS = ".!?।॥"


def _truncate_utf8(text: str, max_bytes: int = MAX_TTS_BYTES) -> str:
    """Trim text to at most max_bytes of UTF-8, preferring a sentence boundary.

    Never splits a multibyte character.
    """
    if len(text.encode("utf-8")) <= max_bytes:
        return text
    clipped = text.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")
    boundary = max(clipped.rfind(mark) for mark in _SENTENCE_ENDINGS)
    if boundary >= len(clipped) // 2:
        return clipped[: boundary + 1].strip()
    return clipped.strip()


def advisory_to_speech_text(advisory: RoleAdvisory) -> str:
    actions = " ".join(
        f"{index}. {action}" for index, action in enumerate(advisory.priority_actions, start=1)
    )
    return " ".join(
        part for part in (
            advisory.situation_summary,
            actions,
            advisory.disclaimer,
        ) if part
    )


def _adc_synthesize(text: str, language_code: str) -> bytes:
    client = texttospeech.TextToSpeechClient()
    response = client.synthesize_speech(
        request={
            "input": texttospeech.SynthesisInput(text=text),
            "voice": texttospeech.VoiceSelectionParams(
                language_code=language_code,
                ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL,
            ),
            "audio_config": texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=0.95,
            ),
        }
    )
    return response.audio_content


def _access_token() -> tuple[str, str | None]:
    load_dotenv()
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    try:
        credentials, detected_project = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        credentials.refresh(Request())
        return str(credentials.token), project or detected_project
    except Exception:
        # The gcloud CLI only exists on developer machines, never on Cloud Run.
        if os.getenv("SURGESIGHT_ENV", "local") != "local":
            raise
        token = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return token, project


def _rest_synthesize(text: str, language_code: str) -> bytes:
    token, project = _access_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if project:
        headers["x-goog-user-project"] = project
    response = requests.post(
        "https://texttospeech.googleapis.com/v1/text:synthesize",
        headers=headers,
        json={
            "input": {"text": text},
            "voice": {"languageCode": language_code},
            "audioConfig": {"audioEncoding": "MP3", "speakingRate": 0.95},
        },
        timeout=60,
    )
    response.raise_for_status()
    return base64.b64decode(response.json()["audioContent"])


def synthesize_advisory(advisory: RoleAdvisory, language: str) -> bytes:
    if language not in LANGUAGE_CODES:
        raise ValueError(f"Unsupported TTS language: {language}")
    text = advisory_to_speech_text(advisory).strip()
    if not text:
        raise ValueError("Advisory has no text to synthesize")
    text = _truncate_utf8(text)
    try:
        return _adc_synthesize(text, LANGUAGE_CODES[language])
    except Exception:
        return _rest_synthesize(text, LANGUAGE_CODES[language])
