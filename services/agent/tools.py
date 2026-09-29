"""Tool registry and ToolResult contract (§6.1–6.2).

A tool is a typed function ``fn(args: ArgsModel) -> ToolResult``. Its docstring is the
description Gemini sees, and its Pydantic args model is the parameter schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import time
import typing
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from services.config import load_region


class Provenance(BaseModel):
    source: str
    model_version: str
    data_version: str
    computed_at_utc: str


class ToolResult(BaseModel):
    ok: bool
    tool: str
    run_id: str | None = None
    data: dict[str, Any] = {}
    warnings: list[str] = []
    provenance: Provenance
    error: str | None = None


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args_model: type[BaseModel]
    fn: Callable[[Any], ToolResult]
    agent_scopes: frozenset[str]
    side_effect: bool = False


TOOLS: dict[str, ToolSpec] = {}


def data_version() -> str:
    """Identify the baseline data the tools computed against."""
    region = load_region()
    assets = region.path("scored_assets")
    stamp = (
        datetime.fromtimestamp(assets.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d")
        if assets.exists()
        else "missing"
    )
    return f"{region.id}@{stamp}"


def provenance(source: str, model_version: str = "v1") -> Provenance:
    return Provenance(
        source=source,
        model_version=model_version,
        data_version=data_version(),
        computed_at_utc=datetime.now(timezone.utc).isoformat(),
    )


def ok_result(
    tool_name: str,
    data: dict[str, Any],
    *,
    source: str,
    run_id: str | None = None,
    warnings: list[str] | None = None,
    model_version: str = "v1",
) -> ToolResult:
    return ToolResult(
        ok=True,
        tool=tool_name,
        run_id=run_id,
        data=data,
        warnings=warnings or [],
        provenance=provenance(source, model_version),
    )


def error_result(tool_name: str, message: str) -> ToolResult:
    return ToolResult(
        ok=False, tool=tool_name, error=message, provenance=provenance("error")
    )


def tool(
    name: str,
    *,
    agent_scopes: set[str],
    side_effect: bool = False,
) -> Callable[[Callable[[Any], ToolResult]], Callable[[Any], ToolResult]]:
    """Register a function as a Gemini tool.

    The function's single parameter must be annotated with a Pydantic model; its
    docstring becomes the tool description. ``side_effect=True`` tools may only queue
    actions for human approval (§4.8).
    """

    def decorator(fn: Callable[[Any], ToolResult]) -> Callable[[Any], ToolResult]:
        hints = typing.get_type_hints(fn)
        hints.pop("return", None)
        if len(hints) != 1:
            raise TypeError(f"Tool '{name}' must take exactly one Pydantic args model")
        args_model = next(iter(hints.values()))
        if not (isinstance(args_model, type) and issubclass(args_model, BaseModel)):
            raise TypeError(f"Tool '{name}' args must be a Pydantic model")
        if not (fn.__doc__ or "").strip():
            raise TypeError(f"Tool '{name}' needs a docstring (Gemini reads it)")
        if name in TOOLS:
            raise ValueError(f"Duplicate tool name: {name}")
        TOOLS[name] = ToolSpec(
            name=name,
            description=" ".join((fn.__doc__ or "").split()),
            args_model=args_model,
            fn=fn,
            agent_scopes=frozenset(agent_scopes),
            side_effect=side_effect,
        )
        return fn

    return decorator


def _clean_schema(value: Any) -> Any:
    """Drop JSON-Schema keywords the Gemini function-declaration schema rejects."""
    if isinstance(value, dict):
        return {
            k: _clean_schema(v)
            for k, v in value.items()
            if k not in {"additionalProperties", "title"}
        }
    if isinstance(value, list):
        return [_clean_schema(v) for v in value]
    return value


def declarations(scope: str | None = None) -> list[dict[str, Any]]:
    """Function declarations (name, description, JSON schema) for the model."""
    out = []
    for spec in TOOLS.values():
        if scope is not None and scope not in spec.agent_scopes:
            continue
        out.append(
            {
                "name": spec.name,
                "description": spec.description,
                "parameters_json_schema": _clean_schema(spec.args_model.model_json_schema()),
            }
        )
    return out


def execute_tool(name: str, raw_args: dict[str, Any] | None) -> tuple[ToolResult, int]:
    """Validate arguments and run a tool. Never raises; returns (result, duration_ms)."""
    started = time.perf_counter()
    spec = TOOLS.get(name)
    if spec is None:
        result = error_result(name, f"Unknown tool '{name}'. Available: {sorted(TOOLS)}")
    else:
        try:
            args = spec.args_model.model_validate(raw_args or {})
            result = spec.fn(args)
        except ValidationError as exc:
            problems = "; ".join(
                f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
            )
            result = error_result(name, f"Invalid arguments: {problems}")
        except Exception as exc:  # tool errors go back to Gemini, not up the stack
            result = error_result(name, f"{type(exc).__name__}: {exc}")
    return result, int((time.perf_counter() - started) * 1000)
