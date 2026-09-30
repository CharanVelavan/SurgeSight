"""Make one narration clip per scene and record its length.

A recording in own/<scene id>.(wav|m4a|mp3|aiff) is used when present; otherwise Cloud Text-to-Speech reads the
scene text with the voice in scenes.json. Output: work/audio/<id>.wav and work/durations.json (seconds).

Run from the repo root:  .venv/bin/python docs/pitch/video/voice.py
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from dotenv import load_dotenv
from google.cloud import texttospeech as tts

HERE = Path(__file__).parent
OWN = HERE / "own"
WORK = HERE / "work" / "audio"


def seconds(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def to_wav(src: Path, dst: Path) -> None:
    # Trim leading/trailing silence, even out loudness, 48 kHz mono.
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-af",
                    "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
                    "silenceremove=start_periods=1:start_threshold=-45dB,areverse,loudnorm=I=-16:TP=-1.5",
                    "-ar", "48000", "-ac", "1", str(dst)], check=True)


def main() -> None:
    load_dotenv()
    cfg = json.loads((HERE / "scenes.json").read_text())
    WORK.mkdir(parents=True, exist_ok=True)
    client = None
    durations = {}
    for scene in cfg["scenes"]:
        sid, dst = scene["id"], WORK / f"{scene['id']}.wav"
        own = next((p for p in sorted(OWN.glob(f"{sid}.*")) if p.suffix.lower() in {".wav", ".m4a", ".mp3", ".aiff"}), None)
        if own:
            to_wav(own, dst)
            source = f"own recording {own.name}"
        else:
            client = client or tts.TextToSpeechClient()
            name = cfg["voice"]
            resp = client.synthesize_speech(request={
                "input": tts.SynthesisInput(text=scene["text"]),
                "voice": tts.VoiceSelectionParams(language_code=name[:5], name=name),
                "audio_config": tts.AudioConfig(audio_encoding=tts.AudioEncoding.LINEAR16, sample_rate_hertz=48000),
            })
            raw = WORK / f"{sid}.tts.wav"
            raw.write_bytes(resp.audio_content)
            to_wav(raw, dst)
            raw.unlink()
            source = f"Cloud TTS {name}"
        durations[sid] = round(seconds(dst), 2)
        print(f"{sid}  {durations[sid]:5.1f}s  {source}")
    (HERE / "work" / "durations.json").write_text(json.dumps(durations, indent=1))
    print(f"total narration {sum(durations.values()):.0f}s")


if __name__ == "__main__":
    main()
