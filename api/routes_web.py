"""Routes for the React command UI: weather frames, timeline, map layers, voice and the signed-in user."""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
import numpy as np
import pandas as pd

from api.auth import Principal, auth_mode, get_principal
from api.deps import require_region
from api.routes_ops import Language
from services import weather_frames as wf
from services.agent.builtin_tools import jsonable
from services.config import load_region

router = APIRouter()
IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}


@router.get("/api/weather/manifest")
def weather_manifest(cutoff: str | None = Query(None, description="UTC time; limits frames to what was knowable then"),
                     validation: bool = Query(False, description="Also list observed rain after the cutoff (validation only)")) -> dict[str, Any]:
    try:
        manifest = wf.load_manifest()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    if cutoff is None:
        return manifest
    try:
        selected = wf.frames_for_cutoff(manifest, cutoff, validation)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail=f"Unreadable cutoff '{cutoff}'") from None
    return {**{k: manifest[k] for k in ("bounds", "tile", "encoding", "window")}, **selected}


@router.get("/api/weather/{file}")
def weather_file(file: str) -> FileResponse:
    if not file.endswith(".png"):
        raise HTTPException(status_code=404, detail="Unknown weather file")
    path = wf.WEATHER_DIR / file
    if path.parent != wf.WEATHER_DIR or not path.is_file():
        raise HTTPException(status_code=404, detail="Unknown weather file")
    return FileResponse(path, media_type="image/png", headers=IMMUTABLE)


@router.get("/api/timeline")
def timeline(region: str | None = None) -> dict[str, Any]:
    """Observed track with times, candidate bulletin cutoffs and the first track point over land."""
    from shapely.geometry import Point, shape
    from shapely.prepared import prep

    reg = load_region(require_region(region))
    track = pd.read_csv(reg.path("track"))
    track["ISO_TIME"] = pd.to_datetime(track["ISO_TIME"])
    land = prep(shape(json.loads(reg.path("land_polygon").read_text(encoding="utf-8"))))
    on_land = [land.contains(Point(lon, lat)) for lat, lon in zip(track["LAT"], track["LON"])]
    landfall = track.loc[[i for i, flag in enumerate(on_land) if flag][:1]]
    cutoffs = track[track["ISO_TIME"].dt.hour.isin([0, 12]) & (track["ISO_TIME"] >= track["ISO_TIME"].min() + pd.Timedelta(hours=24))]
    return jsonable({
        "region": reg.id, "cyclone": reg.cyclone_name, "timezone": "UTC", "demo_cutoff": reg.demo_cutoff,
        "start": track["ISO_TIME"].min().strftime("%Y-%m-%dT%H:%M:%SZ"), "end": track["ISO_TIME"].max().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "track": [{"time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "lat": lat, "lon": lon, "wind_kt": w, "pressure_hpa": p}
                  for t, lat, lon, w, p in zip(track["ISO_TIME"], track["LAT"], track["LON"], track["WIND_KT"], track["PRESSURE_HPA"])],
        "cutoffs": [t.strftime("%Y-%m-%dT%H:%M:%SZ") for t in cutoffs["ISO_TIME"]],
        "first_over_land": None if landfall.empty else {"time": landfall["ISO_TIME"].iloc[0].strftime("%Y-%m-%dT%H:%M:%SZ"),
                                                           "lat": float(landfall["LAT"].iloc[0]), "lon": float(landfall["LON"].iloc[0]),
                                                           "note": "first observed track point inside the land polygon, not an official landfall time"},
    })


def _points(frame: pd.DataFrame, value_cols: list[str]) -> dict[str, Any]:
    cols = [c for c in value_cols if c in frame.columns]
    features = []
    for row in frame[["lon", "lat", *cols]].itertuples(index=False):
        r = row._asdict()
        features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(float(r["lon"]), 4), round(float(r["lat"]), 4)]},
                         "properties": {c: (None if pd.isna(r[c]) else (round(float(r[c]), 3) if isinstance(r[c], (float, np.floating)) else r[c])) for c in cols}})
    return {"type": "FeatureCollection", "features": features}


@router.get("/api/layers/{name}")
def layer(name: Literal["surge", "river", "districts"], region: str | None = None) -> dict[str, Any]:
    """Compact GeoJSON for a map layer: surge and river-flood points, or districts with exposure."""
    reg = load_region(require_region(region))
    if name == "districts":
        districts = json.loads(reg.path("districts").read_text(encoding="utf-8"))
        grid = pd.read_csv(reg.path("exposure_grid"))
        totals = grid.groupby("district")[["population", "buildings"]].sum()
        for feature in districts["features"]:
            props = feature.setdefault("properties", {})
            key = props.get("district") or props.get("name") or props.get("NAME_2")
            if key in totals.index:
                props["population"] = int(totals.loc[key, "population"])
                props["buildings"] = int(totals.loc[key, "buildings"])
        return districts
    from services.departments import score_all_assets

    frame = score_all_assets()
    if name == "surge":
        return _points(frame[frame["surge_m"].fillna(0) > 0], ["surge_m", "asset_type", "name"])
    river = pd.read_csv(reg.path("river_assets"))
    merged = frame.merge(river[["osm_element", "osm_id", "hand_m", "river_susceptibility"]], on=["osm_element", "osm_id"], how="inner")
    return _points(merged[merged["river_susceptibility"].fillna(0) > 0], ["river_susceptibility", "hand_m", "asset_type", "name"])


@router.get("/api/me")
def me(principal: Principal = Depends(get_principal)) -> dict[str, Any]:
    return {"auth_mode": auth_mode(), **principal.as_dict()}


@router.post("/api/voice/ask")
async def voice_ask(audio: UploadFile = File(..., description="WAV or FLAC push-to-talk recording"),
                    language: Language = Form("English"), engine: Literal["single", "adk"] = Form("single"),
                    speak: bool = Form(True)) -> dict[str, Any]:
    """Audio in, then speech-to-text, the grounded agent, and optionally text-to-speech of the answer."""
    from services.agent.adk_app import run_adk_agent
    from services.agent.orchestrator import run_agent
    from services.tts import synthesize_text
    from services.voice import stt

    code = stt.LANGUAGE_CODES.get(language)
    if code is None:
        raise HTTPException(status_code=422, detail=f"Speech input is not available in {language}; type the question instead")
    content = await audio.read()
    if not content:
        raise HTTPException(status_code=422, detail="Empty recording")
    loop = asyncio.get_running_loop()
    try:
        transcript = await loop.run_in_executor(None, lambda: stt.transcribe(content, code))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Speech-to-text failed: {exc}") from None
    if not transcript.text.strip():
        raise HTTPException(status_code=422, detail="No speech was recognised; try again closer to the microphone")
    runner = run_adk_agent if engine == "adk" else run_agent
    try:
        answer, trace = await loop.run_in_executor(None, lambda: runner(transcript.text, language=language))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Agent failed: {type(exc).__name__}: {exc}") from None
    body: dict[str, Any] = {"transcript": transcript.text, "confidence": transcript.confidence, "language": language,
                            "answer": answer.model_dump(), "steps": [s.model_dump() for s in trace] if trace else [], "audio_mp3_base64": None}
    if speak and language != "Odia":
        try:
            audio_bytes = await loop.run_in_executor(None, lambda: synthesize_text(answer.answer_markdown, language))
            body["audio_mp3_base64"] = base64.b64encode(audio_bytes).decode("ascii")
        except Exception as exc:
            body["tts_error"] = f"{type(exc).__name__}: {exc}"
    return jsonable(body)
