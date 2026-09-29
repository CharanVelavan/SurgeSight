"""Incident Commander: a manual Gemini function-calling loop with a per-step trace.

We do not use SDK automatic function calling: we need every step visible (trace), arguments
validated, the tool budget enforced, and the grounding guard applied to the final answer.
"""

from __future__ import annotations

from typing import Any, Callable

from google.genai import types
from pydantic import BaseModel, Field

import services.agent  # noqa: F401  (registers built-in tools)
from services.agent import grounding_guard, prompts
from services.agent.tools import TOOLS, ToolResult, declarations, error_result, execute_tool
from services.gemini_client import generate_with_retry
from services.store import get_store

MAX_TOOL_STEPS = 12
SUBMIT = "submit_answer"


class TraceStep(BaseModel):
    step: int
    agent: str = "incident_commander"
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    ok: bool
    duration_ms: int
    summary: str


class AgentAnswer(BaseModel):
    answer_markdown: str
    run_ids: list[str] = Field(default_factory=list)
    numbers_cited: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list)
    requires_approval: list[str] = Field(default_factory=list)
    ungrounded_numbers: list[str] = Field(default_factory=list)
    grounded: bool = True


class SubmitAnswerArgs(BaseModel):
    answer_markdown: str = Field(description="The answer for the officer, in Markdown.")
    recommended_actions: list[str] = Field(default_factory=list, description="Short imperative actions.")
    uncertainty_notes: list[str] = Field(default_factory=list, description="Limits of the numbers or tools.")


SUBMIT_DECLARATION = {
    "name": SUBMIT,
    "description": (
        "Finish the task: submit the final answer to the officer. Call exactly once, after all "
        "needed tools have run. Every number must be copied from a tool result."
    ),
    "parameters_json_schema": {
        "type": "object",
        "properties": {
            "answer_markdown": {"type": "string", "description": "The answer, in Markdown."},
            "recommended_actions": {"type": "array", "items": {"type": "string"}},
            "uncertainty_notes": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["answer_markdown"],
    },
}


def _summarise(result: ToolResult) -> str:
    if not result.ok:
        return f"error: {result.error}"
    parts = [f"run_id={result.run_id}"] if result.run_id else []
    data = result.data
    for key in ("asset_count", "newly_high_risk_hospitals", "cutoff_time", "cyclone_name", "language"):
        if key in data:
            parts.append(f"{key}={data[key]}")
    if "scenario_class_counts" in data:
        parts.append(f"scenario_classes={data['scenario_class_counts']}")
    if "severity" in data:
        parts.append(f"severity={data['severity']}")
    return ", ".join(parts) or "ok"


def _config(scope: str | None, *, only_submit: bool = False) -> types.GenerateContentConfig:
    decls = [SUBMIT_DECLARATION] if only_submit else declarations(scope) + [SUBMIT_DECLARATION]
    function_calling = (
        types.FunctionCallingConfig(mode="ANY", allowed_function_names=[SUBMIT])
        if only_submit
        else types.FunctionCallingConfig(mode="AUTO")
    )
    return types.GenerateContentConfig(
        system_instruction=prompts.INCIDENT_COMMANDER,
        tools=[types.Tool(function_declarations=[types.FunctionDeclaration(**d) for d in decls])],
        tool_config=types.ToolConfig(function_calling_config=function_calling),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        max_output_tokens=8192,
    )


def _context_note(context_run_ids: list[str] | None) -> str:
    if not context_run_ids:
        return ""
    store = get_store()
    lines = []
    for run_id in context_run_ids:
        try:
            lines.append(f"- {run_id} (kind: {store.get(run_id)['kind']})")
        except KeyError:
            lines.append(f"- {run_id} (not found)")
    return "Available run_ids you may pass to tools:\n" + "\n".join(lines) + "\n\n"


def run_agent(
    question: str,
    *,
    context_run_ids: list[str] | None = None,
    language: str = "English",
    on_step: Callable[[TraceStep], None] | None = None,
    scope: str | None = None,
    max_steps: int = MAX_TOOL_STEPS,
) -> tuple[AgentAnswer, list[TraceStep]]:
    """Answer an officer's question by orchestrating tools. Returns (answer, trace)."""

    trace: list[TraceStep] = []
    results: list[ToolResult] = []
    contents: list[types.Content] = [
        types.Content(
            role="user",
            parts=[
                types.Part(
                    text=f"{_context_note(context_run_ids)}Answer language: {language}\n\nOfficer question: {question}"
                )
            ],
        )
    ]
    submitted: SubmitAnswerArgs | None = None
    grounding_retries = 0
    steps = 0
    fallback_text = ""

    def record(name: str, args: dict[str, Any], ok: bool, ms: int, summary: str) -> None:
        step = TraceStep(
            step=len(trace) + 1, tool=name, args=args, ok=ok, duration_ms=ms, summary=summary,
        )
        trace.append(step)
        if on_step:
            on_step(step)

    for _ in range(max_steps + 4):
        force = steps >= max_steps
        response = generate_with_retry(contents=contents, config=_config(scope, only_submit=force))
        candidate = response.candidates[0] if response.candidates else None
        if candidate is None or candidate.content is None or not candidate.content.parts:
            break
        contents.append(candidate.content)
        calls = [p.function_call for p in candidate.content.parts if p.function_call]
        if not calls:
            fallback_text = response.text or ""
            break

        reply_parts: list[types.Part] = []
        for call in calls:
            args = dict(call.args or {})
            if call.name == SUBMIT:
                try:
                    submitted = SubmitAnswerArgs.model_validate(args)
                except Exception as exc:
                    reply_parts.append(types.Part.from_function_response(
                        name=SUBMIT, response={"error": f"Invalid submit_answer arguments: {exc}"}))
                    continue
                problems = grounding_guard.check(
                    submitted.answer_markdown + " " + " ".join(submitted.recommended_actions),
                    results, question=question,
                )
                if problems and grounding_retries < 1:
                    grounding_retries += 1
                    reply_parts.append(types.Part.from_function_response(
                        name=SUBMIT,
                        response={"error": prompts.GROUNDING_RETRY.format(numbers=", ".join(problems))},
                    ))
                    submitted = None
                    continue
                record(SUBMIT, {}, True, 0, "answer submitted")
                break
            if call.name in TOOLS and steps >= max_steps:
                result, ms = error_result(call.name, "Tool budget exhausted; call submit_answer."), 0
            else:
                steps += 1 if call.name in TOOLS else 0
                result, ms = execute_tool(call.name, args)
            results.append(result)
            record(call.name, args, result.ok, ms, _summarise(result))
            reply_parts.append(types.Part.from_function_response(
                name=call.name, response={"result": result.model_dump(mode="json")}))
        if submitted is not None:
            break
        contents.append(types.Content(role="user", parts=reply_parts))

    return _finalise(submitted, fallback_text, results, question, trace)


def _finalise(
    submitted: SubmitAnswerArgs | None,
    fallback_text: str,
    results: list[ToolResult],
    question: str,
    trace: list[TraceStep],
) -> tuple[AgentAnswer, list[TraceStep]]:
    if submitted is None:
        submitted = SubmitAnswerArgs(
            answer_markdown=fallback_text or "The agent could not produce an answer from the tool results.",
            uncertainty_notes=["The model did not call submit_answer; text returned as-is."],
        )
    text = submitted.answer_markdown
    scan = text + " " + " ".join(submitted.recommended_actions)
    problems = grounding_guard.check(scan, results, question=question)
    notes = list(submitted.uncertainty_notes)
    actions = list(submitted.recommended_actions)
    if problems:
        text = grounding_guard.redact(text, problems)
        actions = [grounding_guard.redact(a, problems) for a in actions]
        notes.append(
            "Numbers removed because no tool result supports them: " + ", ".join(sorted(set(problems)))
        )
    run_ids = [r.run_id for r in results if r.run_id]
    answer = AgentAnswer(
        answer_markdown=text,
        run_ids=list(dict.fromkeys(run_ids)),
        numbers_cited=grounding_guard.extract_numbers(text),
        recommended_actions=actions,
        uncertainty_notes=notes,
        ungrounded_numbers=sorted(set(problems)),
        grounded=not problems,
    )
    return answer, trace
