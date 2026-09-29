"""Live API test: spoken question in, tool calls, spoken answer out (WP6.2)."""

from __future__ import annotations

import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SCRATCH = Path(os.getenv("SURGESIGHT_TEST_OUT", "/tmp"))


def main() -> None:
    if os.getenv("SURGESIGHT_OFFLINE") == "1":
        print("SKIPPED live Gemini Live test (SURGESIGHT_OFFLINE=1)")
        return
    from google.cloud import texttospeech

    from services.voice.live import LIVE_MODEL, ask_live_sync, pcm_from_wav

    question = "Using the multi hazard model, how many hospitals are in triage tier one, and which hazard dominates?"
    wav = texttospeech.TextToSpeechClient().synthesize_speech(
        input=texttospeech.SynthesisInput(text=question), voice=texttospeech.VoiceSelectionParams(language_code="en-IN"),
        audio_config=texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.LINEAR16, sample_rate_hertz=16000),
    ).audio_content
    result = ask_live_sync(audio_pcm=pcm_from_wav(wav), language="English")
    print(f"model={LIVE_MODEL}\nheard: {result.heard!r}\ntools: {[(c['tool'], c['ok']) for c in result.tool_calls]}\nspoken: {result.spoken_text[:400]!r}")
    print(f"audio bytes={len(result.audio_pcm)} grounded={result.grounded} ungrounded={result.ungrounded_numbers}")
    assert result.audio_pcm and len(result.audio_pcm) > 24000, "no spoken answer"
    assert result.spoken_text.strip(), "no transcript of the spoken answer"
    assert any(c["ok"] for c in result.tool_calls), "the live model answered without using a tool"
    assert result.grounded, f"spoken numbers not in tool output: {result.ungrounded_numbers}"
    (SCRATCH / "surgesight_live_reply.wav").write_bytes(result.wav())
    print("SURGESIGHT_LIVE_OK")


if __name__ == "__main__":
    main()
