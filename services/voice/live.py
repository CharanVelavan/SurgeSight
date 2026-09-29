"""Gemini Live API voice session with the orchestrator's tools (WP6.2).

A push-to-talk exchange over a bidirectional audio session: send 16 kHz PCM audio (or text), let the model call the
same registry tools, and collect the spoken answer (24 kHz PCM) plus transcripts. Streamlit cannot stream audio
well, so this is exercised by ``scripts/test_live.py`` now and becomes a live microphone in the React UI (WP10).

The model id was checked against ``client.models.list()`` (supported action ``bidiGenerateContent``).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import io
import os
from typing import Any
import wave

from google.genai import types

import services.agent  # noqa: F401  (registers tools)
from services.agent import grounding_guard, prompts
from services.agent.tools import TOOLS, ToolResult, declarations, execute_tool
from services.gemini_client import create_client

LIVE_MODEL = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.8-live")
INPUT_RATE, OUTPUT_RATE = 16000, 24000
CHUNK_BYTES = 3200
LIVE_TOOLS = ("risk_v2", "run_scenario", "department_priority", "run_ensemble", "exposure_summary", "river_flood", "nwp_comparison", "assets_within")
MAX_TOOL_ROUNDS = 6
TIMEOUT_S = 120
VOICE_RULES = (
    "\n\nYou are speaking aloud to an officer. Keep the spoken answer under 60 seconds: lead with the finding, then at most three "
    "priorities. Say numbers exactly as the tool returned them. Do not read out run ids."
)


@dataclass
class LiveResult:
    heard: str = ""
    spoken_text: str = ""
    audio_pcm: bytes = b""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    ungrounded_numbers: list[str] = field(default_factory=list)
    model: str = LIVE_MODEL

    @property
    def grounded(self) -> bool:
        return not self.ungrounded_numbers

    def wav(self) -> bytes:
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(OUTPUT_RATE)
            out.writeframes(self.audio_pcm)
        return buffer.getvalue()


def _config(language: str) -> types.LiveConnectConfig:
    specs = [d for d in declarations() if d["name"] in LIVE_TOOLS]
    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=prompts.INCIDENT_COMMANDER + f"\nSpeak in {language}." + VOICE_RULES,
        tools=[types.Tool(function_declarations=[types.FunctionDeclaration(**d) for d in specs])],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
    )


def pcm_from_wav(wav_bytes: bytes) -> bytes:
    """Raw 16-bit mono PCM from a WAV recording (what ``st.audio_input`` returns)."""
    with wave.open(io.BytesIO(wav_bytes)) as source:
        if source.getsampwidth() != 2 or source.getnchannels() != 1 or source.getframerate() != INPUT_RATE:
            raise ValueError(f"Live input must be 16-bit mono {INPUT_RATE} Hz WAV, got {source.getframerate()} Hz x{source.getnchannels()}")
        return source.readframes(source.getnframes())


async def ask_live(*, audio_pcm: bytes | None = None, text: str | None = None, language: str = "English") -> LiveResult:
    """One push-to-talk exchange. Provide 16 kHz PCM audio, or text for a text-in/voice-out check."""
    if (audio_pcm is None) == (text is None):
        raise ValueError("Give exactly one of audio_pcm or text")
    client = create_client()
    result, tool_results = LiveResult(), []
    async with client.aio.live.connect(model=LIVE_MODEL, config=_config(language)) as session:
        if audio_pcm is not None:
            # A single large blob is not picked up by voice-activity detection: stream 100 ms chunks, then 1 s of silence.
            padded = audio_pcm + b"\x00" * (INPUT_RATE * 2)
            for start in range(0, len(padded), CHUNK_BYTES):
                await session.send_realtime_input(audio=types.Blob(data=padded[start : start + CHUNK_BYTES], mime_type=f"audio/pcm;rate={INPUT_RATE}"))
                await asyncio.sleep(0.02)
            await session.send_realtime_input(audio_stream_end=True)
        else:
            await session.send_realtime_input(text=text)
        rounds, done = 0, False
        while not done:  # a tool call ends the model's first turn; the spoken answer comes in a later turn
            async for message in session.receive():
                content = message.server_content
                if content is not None:
                    if content.input_transcription and content.input_transcription.text:
                        result.heard += content.input_transcription.text
                    if content.output_transcription and content.output_transcription.text:
                        result.spoken_text += content.output_transcription.text
                    for part in (content.model_turn.parts if content.model_turn else []) or []:
                        if part.inline_data and part.inline_data.data:
                            result.audio_pcm += part.inline_data.data
                    if content.turn_complete and result.audio_pcm:
                        done = True
                        break
                if message.tool_call:
                    rounds += 1
                    replies = []
                    for call in message.tool_call.function_calls:
                        if rounds > MAX_TOOL_ROUNDS or call.name not in LIVE_TOOLS:
                            outcome = {"error": "tool not available or budget used"}
                        else:
                            tool_result, ms = await asyncio.to_thread(execute_tool, call.name, dict(call.args or {}))
                            tool_results.append(tool_result)
                            result.tool_calls.append({"tool": call.name, "args": dict(call.args or {}), "ok": tool_result.ok, "ms": ms, "run_id": tool_result.run_id})
                            outcome = {"result": tool_result.model_dump(mode="json")}
                        replies.append(types.FunctionResponse(id=call.id, name=call.name, response=outcome))
                    result.audio_pcm, result.spoken_text = b"", ""  # drop any 'let me check' chatter said before the tool result
                    await session.send_tool_response(function_responses=replies)
    half = len(result.spoken_text) // 2
    if half and result.spoken_text[:half].strip().lower() == result.spoken_text[half:].strip().lower():  # the model sometimes repeats itself
        result.spoken_text = result.spoken_text[:half].strip()
    result.ungrounded_numbers = grounding_guard.check(result.spoken_text, tool_results, question=result.heard or text or "")
    return result


def ask_live_sync(**kwargs: Any) -> LiveResult:
    return asyncio.run(asyncio.wait_for(ask_live(**kwargs), TIMEOUT_S))
