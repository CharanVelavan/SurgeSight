"""Live test: Google Search grounding returns a summary with cited sources (WP1.4)."""

from __future__ import annotations

import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.search_grounding import search_latest_bulletins


def main() -> None:
    if os.getenv("SURGESIGHT_OFFLINE") == "1":
        print("SKIPPED live search grounding test (SURGESIGHT_OFFLINE=1)")
        return
    result = search_latest_bulletins("Michaung")
    print(result["answer_text"][:500])
    print(f"sources={len(result['items'])} queries={result['search_queries']}")
    for item in result["items"][:5]:
        print(" -", item["title"], item["uri"][:80])
    assert result["answer_text"], "empty summary"
    assert result["grounded"] and all(i["uri"].startswith("http") for i in result["items"]), "no cited sources"
    print("SURGESIGHT_SEARCH_GROUNDING_OK")


if __name__ == "__main__":
    main()
