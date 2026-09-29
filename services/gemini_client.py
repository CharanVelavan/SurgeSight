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


MODEL_NAME = "gemini-3.7-flash"
MAX_ATTEMPTS = 3
SchemaT = TypeVar("SchemaT", bound=BaseModel)


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
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                    response_mime_type="application/json",
                    response_schema=_api_compatible_schema(schema.model_json_schema()),
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
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
