"""Model fallback on free-tier quota errors (offline): a 429 moves to the next model, other errors do not."""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from google.genai import errors

from services import gemini_client as g


def quota_error() -> errors.ClientError:
    return errors.ClientError(429, {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}})


def main() -> None:
    g._exhausted.clear()
    chain = g.model_chain()
    assert chain[0] == g.MODEL_NAME and len(chain) == len(set(chain)) >= 2
    calls = []

    def flaky(model):
        calls.append(model)
        if model == chain[0]:
            raise quota_error()
        return f"answer from {model}"

    assert g._call_with_fallback(flaky) == f"answer from {chain[1]}" and calls == [chain[0], chain[1]]
    assert g.last_model_used == chain[1] and g.model_chain()[0] == chain[1], "an exhausted model is skipped next time"
    calls.clear()
    assert g._call_with_fallback(flaky) == f"answer from {chain[1]}" and calls == [chain[1]], "no retry of the exhausted model"

    def broken(model):
        raise errors.ClientError(400, {"error": {"code": 400, "message": "bad request", "status": "INVALID_ARGUMENT"}})

    try:
        g._call_with_fallback(broken)
        raise AssertionError("a non-quota error must not be hidden by fallback")
    except errors.ClientError as exc:
        assert exc.code == 400
    def always_out(model):
        raise quota_error()

    try:
        g._call_with_fallback(always_out)
        raise AssertionError("all models exhausted must raise")
    except errors.ClientError as exc:
        assert exc.code == 429
    assert set(g.model_chain()) == set(chain), "when every model is exhausted the full chain is offered again"
    g._exhausted.clear()
    print("SURGESIGHT_GEMINI_FALLBACK_OK")


if __name__ == "__main__":
    main()
