"""Live ADK multi-agent test: the team delegates to specialists, uses tools and stays grounded (WP1.5)."""

from __future__ import annotations

import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> None:
    if os.getenv("SURGESIGHT_OFFLINE") == "1":
        print("SKIPPED live ADK test (SURGESIGHT_OFFLINE=1)")
        return
    from services.agent.adk_app import SUB_AGENTS, build_agents, run_adk_agent
    from services.agent.tools import TOOLS

    root = build_agents([], lambda *a: None)
    assert {a.name for a in root.sub_agents} == set(SUB_AGENTS)
    covered = {t.name for a in root.sub_agents for t in a.tools}
    assert covered == set(TOOLS) - {n for n, s in TOOLS.items() if not s.agent_scopes & {"forecast", "impact", "department", "comms"}}, covered ^ set(TOOLS)

    answer, trace = run_adk_agent("Using the multi-hazard v2 model, which hazard dominates for the highest-priority assets, and how many hospitals are in triage tier 1?")
    print("tools:", [(s.agent, s.tool) for s in trace])
    print(answer.answer_markdown[:600])
    print(f"grounded={answer.grounded} ungrounded={answer.ungrounded_numbers}")
    assert any(s.tool == "risk_v2" and s.ok for s in trace), "risk_v2 not used"
    assert answer.answer_markdown.strip() and answer.run_ids
    assert answer.grounded, answer.ungrounded_numbers
    print("SURGESIGHT_ADK_OK")


if __name__ == "__main__":
    main()
