"""Smoke-check every Google service SurgeSight depends on.

Prints PASS/FAIL per service. Never prints key values. Uses REST so no extra
client libraries are needed; cloud APIs use the gcloud access token.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "")
SERVER_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
BROWSER_KEY = os.getenv("VITE_GOOGLE_MAPS_API_KEY", "")
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
CHENNAI = {"latitude": 13.0827, "longitude": 80.2707}
TIMEOUT = 30

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  - {detail}" if detail else ""), flush=True)


def check(name: str):
    def wrap(fn):
        try:
            detail = fn() or ""
            record(name, True, detail)
        except Exception as exc:  # noqa: BLE001
            record(name, False, str(exc)[:200].replace(SERVER_KEY or "\0", "***"))
        return fn
    return wrap


def token() -> str:
    return subprocess.check_output(
        ["gcloud", "auth", "print-access-token"], text=True, stderr=subprocess.DEVNULL
    ).strip()


def bearer() -> dict[str, str]:
    return {"Authorization": f"Bearer {token()}", "x-goog-user-project": PROJECT}


def ok_json(resp: requests.Response) -> dict:
    if resp.status_code >= 400:
        try:
            msg = resp.json().get("error", {}).get("message", resp.text)
        except ValueError:
            msg = resp.text
        raise RuntimeError(f"HTTP {resp.status_code}: {msg}")
    return resp.json() if resp.content else {}


@check("env: keys present and distinct")
def _env():
    missing = [n for n, v in [("GEMINI_API_KEY", GEMINI_KEY), ("GOOGLE_MAPS_API_KEY", SERVER_KEY),
                              ("VITE_GOOGLE_MAPS_API_KEY", BROWSER_KEY), ("GOOGLE_CLOUD_PROJECT", PROJECT)] if not v]
    if missing:
        raise RuntimeError(f"missing {missing}")
    if SERVER_KEY == BROWSER_KEY:
        raise RuntimeError("server and browser keys are identical")


@check("Gemini API (gemini-3.7-flash)")
def _gemini():
    from services.gemini_client import MODEL_NAME, create_client
    client = create_client()
    resp = client.models.generate_content(model=MODEL_NAME, contents="Reply with the single word: ok")
    return f"replied {resp.text.strip()[:20]!r}"


@check("Earth Engine (GFS forecast dataset)")
def _ee():
    import ee
    ee.Initialize(project=PROJECT)
    n = ee.ImageCollection("NOAA/GFS0P25").filterDate("2023-12-03", "2023-12-04").size().getInfo()
    if not n:
        raise RuntimeError("NOAA/GFS0P25 returned no images")
    return f"{n} GFS images on 2023-12-03"


@check("Maps Weather API (server key)")
def _weather():
    r = requests.get("https://weather.googleapis.com/v1/currentConditions:lookup",
                     params={"key": SERVER_KEY, "location.latitude": CHENNAI["latitude"],
                             "location.longitude": CHENNAI["longitude"]}, timeout=TIMEOUT)
    d = ok_json(r)
    return f"Chennai {d.get('temperature', {}).get('degrees')} C"


@check("Weather API: hourly forecast")
def _weather_forecast():
    r = requests.get("https://weather.googleapis.com/v1/forecast/hours:lookup",
                     params={"key": SERVER_KEY, "location.latitude": CHENNAI["latitude"],
                             "location.longitude": CHENNAI["longitude"], "hours": 24}, timeout=TIMEOUT)
    d = ok_json(r)
    return f"{len(d.get('forecastHours', []))} hourly rows"


@check("Geocoding API")
def _geocode():
    d = ok_json(requests.get("https://maps.googleapis.com/maps/api/geocode/json",
                             params={"address": "Chennai, India", "key": SERVER_KEY}, timeout=TIMEOUT))
    if d.get("status") != "OK":
        raise RuntimeError(f"{d.get('status')}: {d.get('error_message', '')}")
    return d["results"][0]["formatted_address"]


@check("Places API (New)")
def _places():
    r = requests.post("https://places.googleapis.com/v1/places:searchText",
                      headers={"X-Goog-Api-Key": SERVER_KEY, "X-Goog-FieldMask": "places.displayName"},
                      json={"textQuery": "hospital in Chennai", "maxResultCount": 3}, timeout=TIMEOUT)
    return f"{len(ok_json(r).get('places', []))} places"


@check("Routes API")
def _routes():
    r = requests.post("https://routes.googleapis.com/directions/v2:computeRoutes",
                      headers={"X-Goog-Api-Key": SERVER_KEY,
                               "X-Goog-FieldMask": "routes.duration,routes.distanceMeters"},
                      json={"origin": {"location": {"latLng": {"latitude": 13.0827, "longitude": 80.2707}}},
                            "destination": {"location": {"latLng": {"latitude": 13.0418, "longitude": 80.2341}}},
                            "travelMode": "DRIVE"}, timeout=TIMEOUT)
    route = ok_json(r)["routes"][0]
    return f"{route['distanceMeters']} m"


@check("Maps JavaScript API (browser key restriction)")
def _maps_js():
    out = subprocess.check_output(
        ["gcloud", "services", "api-keys", "list", "--filter=displayName=surgesight-browser",
         "--format=value(restrictions.apiTargets[].service)"], text=True, stderr=subprocess.DEVNULL).strip()
    if "maps-backend.googleapis.com" not in out:
        raise RuntimeError(f"browser key not restricted to Maps JavaScript API: {out!r}")
    return "key exists, limited to maps-backend (JS API loads in-browser only)"


@check("Text-to-Speech (Tamil)")
def _tts():
    r = requests.post("https://texttospeech.googleapis.com/v1/text:synthesize", headers=bearer(),
                      json={"input": {"text": "வணக்கம்"}, "voice": {"languageCode": "ta-IN"},
                            "audioConfig": {"audioEncoding": "MP3"}}, timeout=TIMEOUT)
    return f"{len(ok_json(r).get('audioContent', ''))} b64 chars"


@check("Speech-to-Text API enabled")
def _stt():
    r = requests.post("https://speech.googleapis.com/v1/speech:recognize", headers=bearer(),
                      json={"config": {"languageCode": "en-IN", "encoding": "LINEAR16", "sampleRateHertz": 16000},
                            "audio": {"content": ""}}, timeout=TIMEOUT)
    if r.status_code in (400,):  # reachable; empty audio is rejected
        return "reachable (empty audio rejected as expected)"
    ok_json(r)


@check("Firestore write / read / delete")
def _firestore():
    doc = f"check-{uuid.uuid4().hex[:8]}"
    base = f"https://firestore.googleapis.com/v1/projects/{PROJECT}/databases/(default)/documents/_healthcheck"
    h = bearer()
    ok_json(requests.patch(f"{base}/{doc}", headers=h, json={"fields": {"ok": {"booleanValue": True}}}, timeout=TIMEOUT))
    got = ok_json(requests.get(f"{base}/{doc}", headers=h, timeout=TIMEOUT))
    ok_json(requests.delete(f"{base}/{doc}", headers=h, timeout=TIMEOUT))
    if not got["fields"]["ok"]["booleanValue"]:
        raise RuntimeError("read-back mismatch")


@check("BigQuery query")
def _bq():
    r = requests.post(f"https://bigquery.googleapis.com/bigquery/v2/projects/{PROJECT}/queries", headers=bearer(),
                      json={"query": "SELECT ST_DISTANCE(ST_GEOGPOINT(80.27,13.08), ST_GEOGPOINT(80.23,13.04)) AS m",
                            "useLegacySql": False}, timeout=TIMEOUT)
    return f"GIS distance {float(ok_json(r)['rows'][0]['f'][0]['v']):.0f} m"


@check("Vertex AI (Gemini via aiplatform)")
def _vertex():
    url = (f"https://us-central1-aiplatform.googleapis.com/v1/projects/{PROJECT}/locations/us-central1/"
           "publishers/google/models/gemini-2.5-flash:generateContent")
    r = requests.post(url, headers=bearer(), timeout=TIMEOUT,
                      json={"contents": [{"role": "user", "parts": [{"text": "Say ok"}]}]})
    ok_json(r)


@check("Secret Manager API")
def _secrets():
    ok_json(requests.get(f"https://secretmanager.googleapis.com/v1/projects/{PROJECT}/secrets",
                         headers=bearer(), timeout=TIMEOUT))


@check("Cloud Scheduler API")
def _scheduler():
    ok_json(requests.get(f"https://cloudscheduler.googleapis.com/v1/projects/{PROJECT}/locations/asia-south1/jobs",
                         headers=bearer(), timeout=TIMEOUT))


@check("Pub/Sub API")
def _pubsub():
    ok_json(requests.get(f"https://pubsub.googleapis.com/v1/projects/{PROJECT}/topics",
                         headers=bearer(), timeout=TIMEOUT))


@check("Cloud Storage API")
def _gcs():
    ok_json(requests.get("https://storage.googleapis.com/storage/v1/b", params={"project": PROJECT},
                         headers=bearer(), timeout=TIMEOUT))


failed = [n for n, ok, _ in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} passed")
if failed:
    print("Failed:", ", ".join(failed))
sys.exit(1 if failed else 0)
