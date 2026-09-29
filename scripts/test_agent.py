"""Live orchestrator test: 3 canned questions, each must use tools, ground its numbers, and not error."""

from __future__ import annotations

import os
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.agent.builtin_tools import register_bulletin_text
from services.agent.orchestrator import run_agent

SAMPLE = PROJECT_ROOT / "data/raw/sample_michaung_bulletin.txt"


def main() -> None:
    if os.getenv("SURGESIGHT_OFFLINE") == "1":
        print("SKIPPED live agent test (SURGESIGHT_OFFLINE=1)")
        return
    bulletin_id = register_bulletin_text(SAMPLE.read_text(encoding="utf-8"))
    cases = [
        ("If Michaung shifts 30 km north, which hospitals become newly high risk? Top 5 only.", None, "English", {"run_scenario"}),
        ("How well would the experimental track forecast issued at 2023-12-03 12:00 have done, and does it change hospital impact?", None, "English", {"experimental_forecast"}),
        ("Track uncertainty is real. Around a 30 km northward shift, which 5 hospitals are most likely to be HIGH or worse across many possible tracks?", None, "English", {"run_ensemble"}),
        ("Using the multi-hazard v2 model, which hazard dominates for the highest-priority assets, and how many hospitals fall in triage tier 1?", None, "English", {"risk_v2"}),
        ("Score the attached bulletin and tell Health what to prepare, in Tamil.", [bulletin_id], "Tamil", {"parse_bulletin", "bulletin_to_track", "score_track", "draft_advisory"}),
    ]
    for question, run_ids, language, expected_tools in cases:
        answer, trace = run_agent(question, context_run_ids=run_ids, language=language)
        used = {step.tool for step in trace}
        print(f"\nQ: {question}\n  tools: {[s.tool for s in trace]}\n  grounded={answer.grounded} ungrounded={answer.ungrounded_numbers}")
        assert any(s.tool != "submit_answer" for s in trace), "no tool call"
        assert expected_tools <= used, f"expected {expected_tools}, used {used}"
        assert not [s for s in trace if not s.ok], [s for s in trace if not s.ok]
        assert answer.grounded, answer.ungrounded_numbers
        assert answer.answer_markdown.strip() and answer.run_ids
    print("\nSURGESIGHT_AGENT_OK")


if __name__ == "__main__":
    main()
