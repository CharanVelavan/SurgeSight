"""Gemini orchestrator: tool registry, tools and the function-calling loop."""

from services.agent import builtin_tools, hazard_tools  # noqa: F401  (registers tools on import)
