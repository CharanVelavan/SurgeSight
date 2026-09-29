"""Live Gemini parser test using the explicitly synthetic Michaung bulletin."""

from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.bulletin_parser import parse_bulletin_text


SAMPLE_FILE = Path("data/raw/sample_michaung_bulletin.txt")


def main() -> None:
    if not SAMPLE_FILE.exists():
        raise FileNotFoundError(f"Missing parser test bulletin: {SAMPLE_FILE}")
    bulletin = parse_bulletin_text(SAMPLE_FILE.read_text(encoding="utf-8"))
    print("SURGESIGHT_BULLETIN_PARSER_OK")
    print(bulletin.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
