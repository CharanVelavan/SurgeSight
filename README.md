# SurgeSight

**From cyclone forecast to infrastructure consequence.** SurgeSight turns a cyclone bulletin into a ranked list of the hospitals, substations, shelters, fire and police stations, water works and harbours most likely to be hit. It lets an officer test "what if the track shifts 30 km north?", drafts a grounded advisory for each department in six languages, and queues alerts for human approval.

*Google Cloud × hack2skill · Build with AI: Code for Communities 2.0 · Problem Statement 05: Track-Based Cyclone Impact & Infrastructure Vulnerability Forecaster.*
*Demonstrated on Cyclone Michaung (December 2023, Tamil Nadu and Andhra Pradesh).*

> **Screening, not forecasting.** SurgeSight does not replace IMD. Every score is a screening index for prioritising attention, not a probability of damage. Experimental tracks are not official forecasts. Every alert is a CAP `Exercise` message and needs a human to approve it.

**Status:** working prototype, run locally. Not deployed yet (no live URL). See [Limitations](#limitations).

## What it does

| Step | What happens |
|---|---|
| 1. Read | Gemini parses an IMD-style bulletin (text, PDF or image) into a structured track. |
| 2. Score | 4,214 assets are scored by a multi-hazard model: modelled wind field, screening storm surge, and rainfall on terrain. |
| 3. Test | A what-if simulator shifts the track or intensity. A 100-member ensemble, with spread taken from a measured track-error backtest, ranks assets by how often they reach HIGH or worse. |
| 4. Check | Results are compared with an independent NOAA GFS forecast, and validated against Sentinel-2 flood observations of the real event. |
| 5. Explain | A Gemini agent picks and runs the tools. A guard checks that **every number in its answer appears in a tool result**, and redacts any that do not. |
| 6. Act | Seven department views produce advisories (English, Tamil, Telugu, Hindi, Odia, Bengali) with audio, CAP 1.2 alerts, and illustrative parametric-insurance triggers. |
| 7. Approve | Nothing is sent without a person approving it. Delivery works by Gmail and by Firebase push. |

## Architecture

```mermaid
flowchart LR
    B[Bulletin<br/>text · PDF · image] --> P[Gemini parser]
    P --> T[Track]
    T --> R[Risk model v2<br/>wind · surge · rain]
    A[(Assets · OSM<br/>4,214)] --> R
    EE[Earth Engine<br/>terrain · GFS · IMERG<br/>Sentinel · WorldPop] --> R
    R --> E[Ensemble · exposure<br/>river flood · parametric]
    E --> AG{{Gemini agent<br/>single or ADK team}}
    AG -->|tools| E
    AG --> G[Grounding guard]
    G --> D[Department advisories<br/>6 languages · TTS · CAP]
    D --> Q[Approval queue]
    Q -->|approved| S[Gmail · Firebase push]
    API[FastAPI] --- AG
    UI[Streamlit dashboard] --- API
    ST[(Firestore · BigQuery GIS)] --- E
```

A fuller description, with design decisions, is in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Google technologies used

| Service | Job | State |
|---|---|---|
| **Gemini 3.7 Flash** (Vertex AI) | Orchestrator, bulletin parsing, advisories, translation, satellite-map review | Built |
| **Gemini Live API** (`gemini-3.8-live`) | Spoken question in, tool calls, spoken answer out | Built; tested with synthetic speech |
| **Agent Development Kit** | Incident Commander with forecast, impact, department, finance and comms agents | Built; not on Agent Engine |
| **Google Search grounding** | Latest bulletins and news with cited sources | Built |
| **Earth Engine** | Terrain, GFS forecast rain and winds, IMERG, Sentinel-1/2, WorldPop, Open Buildings, MERIT Hydro | Built |
| **Maps Platform** | Geocoding, Places, Routes (route exposure), Weather | Built |
| **Cloud Text-to-Speech / Speech-to-Text** | Spoken advisories and voice questions | Built (no Odia voice exists) |
| **Firestore** | Run store (`SURGESIGHT_STORE=firestore`) | Built |
| **BigQuery GIS** | Parameterised spatial asset queries | Built |
| **Gmail API** | Approved email dispatch with CAP attachment | Built, sent live |
| **Firebase Cloud Messaging** | Approved web push | Built, delivered live |
| Cloud Run, Pub/Sub, Scheduler, Secret Manager, Firebase Hosting, Looker Studio | Deployment and automation | **Not built yet** |

Google Chat webhooks are coded but could not be tested: they are unavailable on personal accounts.

## Key results (Cyclone Michaung, one storm)

| Result | Value |
|---|---|
| Assets scored | 4,214 (3,977 core plus 237 department-layer assets) |
| Track forecast error (Kalman, backtest) | 27.6 km mean at 6 h, 48.2 km at 12 h |
| GFS vortex centre error vs observed | 44–80 km at +6 to +48 h; better than Kalman from +18 h |
| Satellite flood ranking, AUC (0.5 = no skill) | forecast rain 0.626 · v2 rain-flood 0.622 · river flood index 0.618 · v2 combined 0.554 · v2 wind **0.394** |
| Satellite coverage | Sentinel-2 saw 48.7% of assets; 11.5% of those showed flooding |
| Exposed people, top-priority footprint | 10.5 million (38.1% of the grid), triage tiers 1–2 |
| Parametric (illustrative) | 287.5 crore payout on the reference track of 490.0 crore insured |

**Honest reading.** Rainfall predicts flooding best; wind ranks flooded assets *below chance*. The v2 HIGH-or-worse class flags almost everything (hit rate 0.977, false-alarm rate 0.983) because the whole corridor was hit hard, so v2 also reports **relative triage tiers**. The model probably needs more rain weight and less wind and surge for flood impact. That change is not made yet.

## Quickstart

Requires Python 3.14, a Google Cloud project with Application Default Credentials (`gcloud auth application-default login`), and a `.env` (see below).

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py                 # dashboard on http://localhost:8501
uvicorn api.main:app --port 8000     # API; docs at /docs, push test page at /push-test
python scripts/run_all_tests.py      # offline tests
python scripts/run_all_tests.py --live   # also calls Google APIs (uses quota or credit)
```

`.env` (never committed): `GOOGLE_CLOUD_PROJECT`, `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_LOCATION=global`, `GEMINI_API_KEY` (optional fallback), `GOOGLE_MAPS_API_KEY`, `DISPATCH_MODE=dry_run` (default; `live` sends only to `DISPATCH_ALLOWLIST`), and the `FIREBASE_*` web settings.

## Project layout

```
services/   models and integrations (risk, ensemble, hazards, agent, dispatch, cap, voice, maps)
api/        FastAPI wrappers over the services, including the streaming agent
ui/ app.py  Streamlit dashboard (a development harness that a React app is meant to replace)
config/     regions, departments, parametric triggers, CAP schema
scripts/    data builds and the test suite (27 scripts, each printing a SURGESIGHT_*_OK marker)
docs/       architecture, the implementation plan and the original vision document
```

## Responsible use and limitations

- **Screening indices only.** No damage, casualty or outage predictions. Roads are not scored, so route results say "lower modelled exposure", never "safe".
- **One storm.** Calibration, the backtest and the validation all use Michaung. Nothing is validated out of sample. A second region (Fani 2019, Odisha) is planned but not built.
- **Satellite proxy.** Sentinel-1 radar did not image the area after landfall, so the flood flag comes from Sentinel-2 optical water mapping, which misses cloud-covered and urban flooding.
- **Data gaps.** OSM coverage of fire stations, water works and fishing harbours is thin. Live Google Weather shows today's conditions, not the 2023 event.
- **Parametric outputs are illustrative.** Portfolios, sums insured and payouts are invented.
- **Human in the loop.** Agents can queue a dispatch but never approve or send it. The default mode is a dry run.
- **Not built yet:** cloud deployment and automation, the React command UI, Agent Engine, Looker Studio.

## Data sources

NOAA IBTrACS and GFS, NASA GPM IMERG, Copernicus Sentinel-1/2, JRC Global Surface Water, USGS SRTM, WorldPop, Google Open Buildings, MERIT Hydro, FAO GAUL, OpenStreetMap contributors (ODbL), and Google Maps Platform. Places content is shown but never stored.
