"""Web dashboard test (UI S8): production build, Vitest, then a Playwright run against the dev server and API.

The browser run needs the Google Maps JavaScript API online and real Chrome with a GPU, so it is reported
SKIPPED when SURGESIGHT_OFFLINE=1. It checks the interleaved vector map, the locked national frame, the
impact zoom, the forecast re-issued for a moved cutoff, the leakage label, playback frame rate (>= 55 fps),
axe accessibility and refreshes the README screenshots.  Usage: python scripts/test_web.py [--no-shots] [--no-fps]
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND = PROJECT_ROOT / "frontend"
API, WEB = "http://127.0.0.1:8000", "http://127.0.0.1:5199"


def up(url: str) -> bool:
    try:
        return urllib.request.urlopen(url, timeout=2).status == 200
    except OSError:
        return False


def wait_for(url: str, seconds: int = 60) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if up(url):
            return
        time.sleep(0.5)
    raise TimeoutError(f"{url} did not come up in {seconds}s")


def run(cmd: list[str], cwd: Path, label: str) -> str:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(f"{label} failed:\n{(proc.stdout + proc.stderr)[-2500:]}")
    return proc.stdout


def main() -> int:
    if os.getenv("SURGESIGHT_OFFLINE") == "1":
        print("SKIPPED: the browser test needs the Google Maps JS API online")
        return 0
    if not (FRONTEND / "node_modules").exists():
        print("SKIPPED: run `npm install` in frontend/ first")
        return 0

    run(["npm", "run", "build"], FRONTEND, "npm run build")
    print("build ok")
    out = run(["npx", "vitest", "run"], FRONTEND, "vitest")
    print("vitest ok:", [ln.strip() for ln in out.splitlines() if "Tests" in ln][-1])

    started: list[subprocess.Popen] = []
    try:
        if not up(f"{API}/api/weather/manifest"):
            env = {**os.environ, "SURGESIGHT_OFFLINE": "1"}
            started.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "api.main:app", "--port", "8000"],
                                            cwd=PROJECT_ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            wait_for(f"{API}/api/weather/manifest")
        started.append(subprocess.Popen(["npx", "vite", "--port", "5199", "--strictPort", "--host", "127.0.0.1"],
                                        cwd=FRONTEND, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        wait_for(WEB)

        cmd = ["node", "e2e/smoke.mjs", WEB]
        if "--no-shots" not in sys.argv:
            (PROJECT_ROOT / "docs" / "screenshots").mkdir(parents=True, exist_ok=True)
            cmd += ["--screenshots", str(PROJECT_ROOT / "docs" / "screenshots")]
        if "--no-fps" in sys.argv:
            cmd.append("--no-fps")
        proc = subprocess.run(cmd, cwd=FRONTEND, capture_output=True, text=True, timeout=300)
        lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("{")]
        if not lines:
            raise AssertionError(f"e2e produced no result:\n{(proc.stdout + proc.stderr)[-2500:]}")
        result = json.loads(lines[-1])
        assert result["ok"], f"e2e failures: {result['failures']}"
        print(f"e2e ok: fps={result['fps']} forecast={result["forecastMs"]} ms zones={result["zoneMs"]} ms zoom={result['zoom']}")
    finally:
        for proc in started:
            proc.terminate()
        for proc in started:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
    print("SURGESIGHT_WEB_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
