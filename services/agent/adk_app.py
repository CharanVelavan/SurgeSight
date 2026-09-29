"""ADK multi-agent orchestrator (WP1.5): Incident Commander with specialist sub-agents.

The same tool functions as the single orchestrator are reused: each registry tool is wrapped as an ADK
tool and given to the sub-agent whose scope it belongs to (``agent_scopes``). The numbers-from-tools rule
is enforced the same way: the final text goes through ``grounding_guard`` against every tool result.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Callable

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.adk.tools import BaseTool
from google.genai import types

import services.agent  # noqa: F401  (registers tools)
from services.agent import grounding_guard, prompts
from services.agent.orchestrator import AgentAnswer, SubmitAnswerArgs, TraceStep, _context_note, _finalise, _summarise
from services.agent.tools import TOOLS, ToolResult, execute_tool
import time

from services import gemini_client

APP_NAME = "surgesight"
SUB_AGENTS = {
    "forecast_agent": ("forecast", "Track and NWP questions: experimental track forecast, GFS comparison, ensemble of possible tracks, latest bulletins."),
    "impact_agent": ("impact", "Impact questions: what-if scenarios, multi-hazard v2 scoring, surge, rainfall, river flood, exposed population, satellite validation, asset details."),
    "department_agent": ("department", "Advisories for the seven departments (Collector, Health, Fire & Rescue, Electricity, Police, Water, Fisheries) in English, Tamil, Telugu, Hindi, Odia or Bengali."),
    "finance_agent": ("finance", "Finance: illustrative parametric insurance triggers, probabilities, expected payouts and the liquidity brief."),
    "comms_agent": ("comms", "Public communication: audio of an advisory, bulletin parsing and search for the latest official bulletins."),
}
SUB_INSTRUCTION = (
    "You are a specialist of the SurgeSight Incident Commander team. Use your tools to answer the part of the "
    "question in your area. Never calculate or invent numbers: every number must be copied from a tool result. "
    "Risk values are screening indices, not damage probabilities. Experimental forecasts are not official; IMD is "
    "authoritative. Report results plainly with the exact figures and asset names the tools returned, then hand "
    "back to the Incident Commander."
)


class RegistryTool(BaseTool):
    """A SurgeSight registry tool exposed to ADK. Results are also collected for the grounding check."""

    def __init__(self, name: str, sink: list[ToolResult], on_call: Callable[[str, dict, ToolResult, int], None]):
        spec = TOOLS[name]
        super().__init__(name=name, description=spec.description)
        self._spec, self._sink, self._on_call = spec, sink, on_call

    def _get_declaration(self) -> types.FunctionDeclaration:
        from services.agent.tools import _clean_schema

        return types.FunctionDeclaration(
            name=self.name, description=self.description,
            parameters_json_schema=_clean_schema(self._spec.args_model.model_json_schema()),
        )

    async def run_async(self, *, args: dict[str, Any], tool_context: Any) -> Any:
        result, ms = await asyncio.to_thread(execute_tool, self.name, dict(args))
        self._sink.append(result)
        self._on_call(self.name, dict(args), result, ms)
        return {"result": result.model_dump(mode="json")}


def build_agents(sink: list[ToolResult], on_call: Callable[[str, dict, ToolResult, int], None], model: str | None = None) -> LlmAgent:
    model = model or gemini_client.MODEL_NAME
    subs = []
    for agent_name, (scope, description) in SUB_AGENTS.items():
        tools = [RegistryTool(name, sink, on_call) for name, spec in TOOLS.items() if scope in spec.agent_scopes]
        subs.append(LlmAgent(name=agent_name, model=model, description=description, instruction=SUB_INSTRUCTION, tools=tools))
    return LlmAgent(
        name="incident_commander", model=model,
        description="Coordinates the cyclone impact workflow across specialist agents.",
        instruction=prompts.INCIDENT_COMMANDER.replace(
            "You run the workflow by calling tools.",
            "You run the workflow by delegating to your specialist agents (forecast_agent, impact_agent, department_agent, finance_agent, comms_agent), "
            "which own the tools. Delegate, then write the final answer yourself from what they report.",
        ).replace("Finish by calling submit_answer exactly once with answer_markdown, recommended_actions (short imperative items) and uncertainty_notes (what the numbers do not tell the officer).",
                  "Write the final answer in plain Markdown: the finding first, then priority assets, then short recommended actions, then what the numbers do not tell the officer."),
        sub_agents=subs,
    )


async def _run(question: str, context_run_ids: list[str] | None, language: str, on_step: Callable[[TraceStep], None] | None, model: str):
    if not os.getenv("GOOGLE_API_KEY") and os.getenv("GEMINI_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]
    results: list[ToolResult] = []
    trace: list[TraceStep] = []

    def on_call(name: str, args: dict, result: ToolResult, ms: int) -> None:
        step = TraceStep(step=len(trace) + 1, agent=next((a for a, (s, _) in SUB_AGENTS.items() if s in TOOLS[name].agent_scopes), "adk"),
                         tool=name, args=args, ok=result.ok, duration_ms=ms, summary=_summarise(result))
        trace.append(step)
        if on_step:
            on_step(step)

    root = build_agents(results, on_call, model)
    runner = InMemoryRunner(agent=root, app_name=APP_NAME)
    session = await runner.session_service.create_session(app_name=APP_NAME, user_id="officer")
    message = types.Content(role="user", parts=[types.Part(
        text=f"{_context_note(context_run_ids)}Answer language: {language}\n\nOfficer question: {question}")])
    async def turn(new_message: types.Content) -> str:
        final = ""
        async for event in runner.run_async(user_id="officer", session_id=session.id, new_message=new_message):
            if event.is_final_response() and event.content and event.content.parts:
                text = "".join(p.text or "" for p in event.content.parts if getattr(p, "text", None))
                if text.strip():
                    final = text  # the last final response wins (the root agent answers last)
        return final

    final = await turn(message)
    problems = grounding_guard.check(final, results, question=question)
    if problems:  # one rewrite, as in the single orchestrator; anything still unsupported is redacted afterwards
        retry = types.Content(role="user", parts=[types.Part(text=prompts.GROUNDING_RETRY.format(numbers=", ".join(problems)))])
        final = await turn(retry) or final
    return final, results, trace


def run_adk_agent(
    question: str,
    *,
    context_run_ids: list[str] | None = None,
    language: str = "English",
    on_step: Callable[[TraceStep], None] | None = None,
) -> tuple[AgentAnswer, list[TraceStep]]:
    """Same contract as ``run_agent``, executed by the ADK multi-agent team."""
    last: Exception | None = None
    for model in gemini_client.model_chain():  # free-tier models run out of daily quota one at a time
        try:
            final, results, trace = asyncio.run(_run(question, context_run_ids, language, on_step, model))
            break
        except Exception as exc:
            if "RESOURCE_EXHAUSTED" not in str(exc) and "429" not in str(exc):
                raise
            gemini_client._exhausted[model] = time.time()
            last = exc
    else:
        raise last  # type: ignore[misc]
    submitted = SubmitAnswerArgs(answer_markdown=final or "The agent team could not produce an answer from the tool results.")
    return _finalise(submitted, final, results, question, trace)
