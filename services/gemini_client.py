"""Small, retrying Google GenAI client used by SurgeSight services."""

from __future__ import annotations

import os
import time
from typing import TypeVar

from dotenv import load_dotenv
from google import genai
from google.genai import errors
from google.genai import types
from pydantic import BaseModel


load_dotenv()
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.7-flash")
# On the free tier every model has its own small daily allowance, so when one is used up the next one is tried.
FALLBACK_MODELS = tuple(
    m.strip() for m in os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3.6-flash,gemini-3.5-flash-lite,gemini-3.1-flash-lite").split(",") if m.strip()
)
EXHAUSTED_COOLDOWN_S = 3600
MAX_ATTEMPTS = 3
SchemaT = TypeVar("SchemaT", bound=BaseModel)


_exhausted: dict[str, float] = {}
last_model_used: str | None = None


def is_quota_error(exc: Exception) -> bool:
    return isinstance(exc, errors.ClientError) and exc.code == 429 and "RESOURCE_EXHAUSTED" in str(exc)


def model_chain() -> list[str]:
    """Models to try in order, skipping ones recently found out of quota (all of them if none is left)."""
    now = time.time()
    chain = [MODEL_NAME, *[m for m in FALLBACK_MODELS if m != MODEL_NAME]]
    ready = [m for m in chain if now - _exhausted.get(m, 0.0) > EXHAUSTED_COOLDOWN_S]
    return ready or chain


def _call_with_fallback(call) -> object:
    """Run ``call(model)`` on each model in turn, moving on only when a model's quota is exhausted."""
    global last_model_used
    last: Exception | None = None
    for model in model_chain():
        try:
            result = call(model)
            last_model_used = model
            return result
        except Exception as exc:
            if not is_quota_error(exc):
                raise
            _exhausted[model] = time.time()
            last = exc
    raise last if last else RuntimeError("No Gemini model available")


class GeminiConfigurationError(RuntimeError):
    """Raised when Gemini credentials are not configured."""


def _api_compatible_schema(value: object) -> object:
    """Remove JSON Schema keywords unsupported by GenerateContent schema mode."""

    if isinstance(value, dict):
        return {
            key: _api_compatible_schema(item)
            for key, item in value.items()
            if key != "additionalProperties"
        }
    if isinstance(value, list):
        return [_api_compatible_schema(item) for item in value]
    return value


def create_client() -> genai.Client:
    load_dotenv()
    if os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "false").strip().lower() in {"1", "true", "yes"}:
        return genai.Client(
            vertexai=True,
            project=os.getenv("GOOGLE_CLOUD_PROJECT"),
            location=os.getenv("GOOGLE_CLOUD_LOCATION", "asia-south1"),
        )
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise GeminiConfigurationError(
            "GEMINI_API_KEY is not available. Add it to the environment or local .env file."
        )
    return genai.Client(api_key=api_key)


def generate_structured(
    *,
    contents: object,
    schema: type[SchemaT],
    system_instruction: str,
    temperature: float = 0.0,
    max_output_tokens: int = 4096,
) -> SchemaT:
    """Generate and validate a schema-constrained Gemini response."""

    client = create_client()
    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            structured_config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                response_mime_type="application/json",
                response_schema=_api_compatible_schema(schema.model_json_schema()),
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            )
            response = _call_with_fallback(
                lambda model: client.models.generate_content(model=model, contents=contents, config=structured_config)
            )
            if isinstance(response.parsed, schema):
                return response.parsed
            if response.text:
                return schema.model_validate_json(response.text)
            raise RuntimeError("Gemini returned no structured response")
        except Exception as exc:
            last_error = exc
            if isinstance(exc, errors.ClientError) and exc.code < 500:
                break
            if attempt == MAX_ATTEMPTS:
                break
            time.sleep(2 ** (attempt - 1))
    raise RuntimeError(
        f"Gemini structured generation failed after {MAX_ATTEMPTS} attempts: {last_error}"
    ) from last_error


def generate_with_retry(
    *,
    contents: object,
    config: types.GenerateContentConfig,
    client: genai.Client | None = None,
) -> types.GenerateContentResponse:
    """Raw ``generate_content`` with the same retry policy (used by the agent loop)."""

    client = client or create_client()
    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return _call_with_fallback(
                lambda model: client.models.generate_content(model=model, contents=contents, config=config)
            )
        except Exception as exc:
            last_error = exc
            retryable = not (isinstance(exc, errors.ClientError) and exc.code < 500 and exc.code != 429)
            if not retryable or attempt == MAX_ATTEMPTS:
                break
            time.sleep(2 ** (attempt - 1))
    raise RuntimeError(f"Gemini call failed after {MAX_ATTEMPTS} attempts: {last_error}") from last_error
