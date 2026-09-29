"""FastAPI layer test with TestClient: every route in the plan (WP9). Uses a throwaway run store."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ["DISPATCH_MODE"] = "dry_run"
os.environ["SURGESIGHT_ENV"] = "local"

from fastapi.testclient import TestClient

from services.store import set_store
from services.store.local_store import LocalStore

set_store(LocalStore(Path(tempfile.mkdtemp())))

from api.main import app

client = TestClient(app)
LIVE = os.getenv("SURGESIGHT_OFFLINE") != "1"
SAMPLE = (PROJECT_ROOT / "data/raw/sample_michaung_bulletin.txt").read_text(encoding="utf-8")
EXPECTED = {
    "/api/regions", "/api/regions/{region_id}/track", "/api/assets", "/api/bulletin/parse", "/api/bulletin/score", "/api/scenario",
    "/api/ensemble", "/api/forecast/experimental", "/api/hazards/{run_id}", "/api/exposure/{run_id}", "/api/validation/satellite/{run_id}",
    "/api/advisory", "/api/tts", "/api/cap/{item_id}", "/api/parametric/{run_id}", "/api/dispatch", "/api/dispatch/{dispatch_id}/approve",
    "/api/dispatch/{dispatch_id}/reject", "/api/agent", "/tasks/poll", "/tasks/process", "/runs/{run_id}", "/healthz",
}


def ok(response, code=200):
    assert response.status_code == code, f"{response.request.method} {response.request.url.path}: {response.status_code} {response.text[:300]}"
    return response


def test_routes_and_basics() -> None:
    paths = set(client.get("/openapi.json").json()["paths"])
    assert EXPECTED <= paths, EXPECTED - paths
    assert ok(client.get("/healthz")).json()["status"] == "ok"
    regions = ok(client.get("/api/regions")).json()
    assert regions and regions[0]["id"] == "michaung_2023"
    track = ok(client.get("/api/regions/michaung_2023/track")).json()
    assert track["points"] and "LAT" in track["points"][0]
    assert client.get("/api/regions/atlantis/track").status_code == 404
    cors = client.options("/api/regions", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert cors.headers.get("access-control-allow-origin") == "http://localhost:5173"
    print("basics ok")


def test_assets() -> None:
    body = ok(client.get("/api/assets", params={"dept": "Health Department", "min_class": "HIGH"})).json()
    assert body["type"] == "FeatureCollection" and body["count"] > 100
    props = body["features"][0]["properties"]
    assert props["asset_type"] == "hospital" and props["risk_class"] in {"HIGH", "CRITICAL"}
    assert ok(client.get("/api/assets", params={"dept": "Fisheries"})).json()["count"] == 9
    assert client.get("/api/assets", params={"dept": "Nonexistent"}).status_code == 404
    assert client.get("/api/assets", params={"run_id": "nope-000"}).status_code == 404
    assert client.get("/api/assets", params={"min_class": "SEVERE"}).status_code == 422
    print("assets ok")


def test_scenario_flow() -> str:
    scenario = ok(client.post("/api/scenario", json={"north_shift_km": 30})).json()
    assert scenario["run_id"] and scenario["data"]["scenario_parameters"]["north_shift_km"] == 30
    assert client.post("/api/scenario", json={"north_shift_km": 900}).status_code == 422
    in_run = ok(client.get("/api/assets", params={"run_id": scenario["run_id"], "min_class": "CRITICAL"})).json()
    assert in_run["run_id"] == scenario["run_id"]
    ensemble = ok(client.post("/api/ensemble", json={"members": 20})).json()
    assert ensemble["data"]["top_by_type"]["hospital"]
    risk = ok(client.post("/api/risk_v2", json={"north_shift_km": 10})).json()
    rid = risk["run_id"]
    hazards = ok(client.get(f"/api/hazards/{rid}")).json()
    assert sum(hazards["class_counts"].values()) == 4214 and hazards["top_assets"]
    assert client.get(f"/api/hazards/{scenario['run_id']}").status_code == 422
    exposure = ok(client.get(f"/api/exposure/{rid}", params={"rule": "triage_tier_1_2"})).json()
    assert exposure["data"]["exposed_population"] > 0
    assert client.get("/api/exposure/nope-000").status_code == 404
    sat = ok(client.get(f"/api/validation/satellite/{rid}")).json()
    assert "ranking_skill_auc" in sat["data"]["metrics"]
    assert ok(client.get(f"/runs/{rid}")).json()["kind"] == "riskv2" and client.get("/runs/zzz-1").status_code == 404
    forecast = ok(client.get("/api/forecast/experimental", params={"horizon": 12})).json()
    assert all(p["lead_hours"] <= 12 for m in forecast["data"]["models"].values() for p in m["forecast"])
    print("scenario flow ok")
    return rid


def test_bulletin_and_parametric() -> None:
    parsed = ok(client.post("/api/bulletin/parse", data={"text": SAMPLE})).json()
    assert parsed["data"]["cyclone_name"], parsed
    assert client.post("/api/bulletin/parse").status_code == 422
    scored = ok(client.post("/api/bulletin/score", json={"bulletin_run_id": parsed["run_id"]})).json()
    assert scored["score"]["run_id"] and scored["track"]["data"]["point_count"] >= 2
    with_file = ok(client.post("/api/bulletin/parse", files={"file": ("b.txt", SAMPLE.encode(), "text/plain")})).json()
    assert with_file["data"]["cyclone_name"]
    base = ok(client.post("/api/parametric/baseline", json={"members": 10})).json()["data"]
    assert base["illustrative"] and base["total_payout_crore"] > 0
    from_bulletin = ok(client.post(f"/api/parametric/{scored['score']['run_id']}", json={"members": 0})).json()["data"]
    assert from_bulletin["portfolios"]
    assert client.post(f"/api/parametric/{parsed['run_id']}", json={}).status_code == 422
    print("bulletin and parametric ok")


def test_advisory_dispatch(risk_run: str) -> None:
    advisory = ok(client.post("/api/advisory", json={"department": "Fisheries Department", "language": "Bengali", "run_id": risk_run})).json()
    assert advisory["advisory"]["headline"] and advisory["advisory"]["audience"] == "Fisheries Department"
    assert client.post("/api/advisory", json={"department": "Navy", "language": "English"}).status_code == 422
    audio = ok(client.post("/api/tts", json={"advisory_run_id": advisory["run_id"], "language": "Bengali"}))
    assert audio.headers["content-type"] == "audio/mpeg" and len(audio.content) > 5000
    assert client.post("/api/tts", json={"language": "English"}).status_code == 422
    xml = ok(client.get(f"/api/cap/{advisory['run_id']}"))
    assert xml.headers["content-type"].startswith("application/xml") and "<status>Exercise</status>" in xml.text
    queued = ok(client.post("/api/dispatch", json={"advisory_run_id": advisory["run_id"], "channel": "chat"})).json()
    did = queued["data"]["dispatch_id"]
    assert queued["data"]["status"] == "pending_approval"
    assert client.post(f"/api/dispatch/{did}/send").status_code == 409, "an unapproved dispatch must not send"
    assert ok(client.get(f"/api/cap/{did}")).text == xml.text.replace(xml.text, ok(client.get(f"/api/cap/{did}")).text)
    assert any(d["id"] == did and d["status"] == "pending_approval" for d in ok(client.get("/api/dispatch")).json())
    assert ok(client.post(f"/api/dispatch/{did}/approve", json={"by": "tester"})).json()["status"] == "approved"
    assert client.post(f"/api/dispatch/{did}/reject").status_code == 409
    sent = ok(client.post(f"/api/dispatch/{did}/send")).json()
    assert sent["status"] == "dry_run" and sent["mode"] == "dry_run"
    other = ok(client.post("/api/dispatch", json={"advisory_run_id": advisory["run_id"], "channel": "email", "include_cap": False})).json()["data"]["dispatch_id"]
    assert ok(client.post(f"/api/dispatch/{other}/reject")).json()["status"] == "rejected"
    assert client.post("/api/dispatch/nope-1/approve").status_code == 404
    print("advisory and dispatch ok")


def test_agent_stream() -> None:
    with client.stream("POST", "/api/agent", json={"question": "Which hazard dominates for the highest-priority assets, and how many hospitals are in triage tier 1?"}) as response:
        assert response.status_code == 200 and response.headers["content-type"].startswith("text/event-stream")
        events, name = [], None
        for line in response.iter_lines():
            if line.startswith("event:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("data:") and name:
                events.append((name, json.loads(line.split(":", 1)[1])))
                name = None
    kinds = [n for n, _ in events]
    assert "step" in kinds and kinds[-1] == "answer", kinds
    answer = events[-1][1]
    assert answer["grounded"] and answer["answer_markdown"].strip()
    assert client.post("/api/agent", json={"question": "hi"}).status_code == 422
    print("agent stream ok")


def test_push_routes() -> None:
    cfg = ok(client.get("/api/push/config")).json()
    assert cfg["firebase"]["appId"] and cfg["firebase"]["projectId"] and cfg["sdk_version"]
    sw = ok(client.get("/firebase-messaging-sw.js"))
    assert sw.headers["content-type"].startswith("text/javascript") and "__CONFIG__" not in sw.text and cfg["firebase"]["appId"] in sw.text
    assert sw.headers["service-worker-allowed"] == "/"
    page = ok(client.get("/push-test"))
    assert "Enable notifications" in page.text and "not an official" in page.text.lower() or "exercise" in page.text.lower()
    assert client.post("/api/push/subscribe", json={"token": "short"}).status_code == 422
    token = "t" * 60
    assert ok(client.post("/api/push/subscribe", json={"token": token})).json() == {"subscribed": True, "registered": 1}
    assert ok(client.post("/api/push/subscribe", json={"token": token})).json()["registered"] == 1, "same token must not duplicate"
    assert ok(client.post("/api/push/unsubscribe", json={"token": token})).json() == {"subscribed": False}
    from services.dispatch import push
    assert push.list_tokens() == []
    print("push routes ok")


def test_tasks() -> None:
    polled = ok(client.post("/tasks/poll", json={"text": SAMPLE + "\nAPI task test issue."})).json()
    assert polled["new"] and polled["bulletin_ref"] and polled["caller"] == "local"
    assert not ok(client.post("/tasks/poll", json={"text": SAMPLE + "\nAPI task test issue."})).json()["new"]
    if LIVE:
        done = ok(client.post("/tasks/process", json={"bulletin_ref": polled["bulletin_ref"], "departments": ["Fisheries"], "members": 5})).json()
        assert len(done["dispatch_ids"]) == 1 and "Nothing has been sent" in done["label"]
    assert client.post("/tasks/process", json={"bulletin_ref": "nope-1"}).status_code == 404
    # cloud mode: the OIDC check must reject callers without a valid Google token
    from services import config

    original = config.get_settings
    try:
        import api.deps as deps

        deps.get_settings = lambda: config.Settings(env="cloud")
        assert client.post("/tasks/poll", json={}).status_code == 401
        assert client.post("/tasks/poll", json={}, headers={"Authorization": "Bearer not-a-token"}).status_code == 401
        assert client.post("/api/scenario", json={}).status_code == 200, "only /tasks/* is token protected"
    finally:
        deps.get_settings = original
    print("tasks ok")


if __name__ == "__main__":
    test_routes_and_basics()
    test_assets()
    if not LIVE:
        print("SKIPPED live-model routes (SURGESIGHT_OFFLINE=1)")
        test_push_routes()
        test_tasks()
    else:
        rid = test_scenario_flow()
        test_bulletin_and_parametric()
        test_advisory_dispatch(rid)
        test_agent_stream()
        test_push_routes()
        test_tasks()
    print("SURGESIGHT_API_OK")
