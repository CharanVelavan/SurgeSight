# Disaster-use hardening checklist (W9)

The dashboard is read-only and used by officials during an event, so wrong or stale numbers matter more than missing features. Status as of 2026-09-30.

| Area | What is in place | Where it is checked |
|---|---|---|
| Not an official warning | Landing page notice; the map key ends with "Screening tool, not an official warning. Follow IMD and NDMA."; alert zones are labelled "Not an IMD warning"; the Why panel repeats it; six languages | `scripts/test_web.py` (landing), `src/__tests__/i18n.test.ts` |
| Source and time on numbers | Every weather scale names its source (GFS analysis, GFS forecast issued *cycle*, IMERG observed / validation only); live view shows model run, age and forecast-not-observation; Why panel shows the valid time, closest approach time and the model version | e2e checks banner and panel text |
| No hindsight | Forecast frames come only from the latest cycle at or before the cutoff; after the cutoff the storm position is our forecast, and no distance to it is shown | `test_weather_frames.py`, `test_asset_explain.py`, vitest |
| Stale data | Live cycle older than 12 h shows an amber warning telling users not to rely on it; saved copies from the service worker are labelled with the time they were saved | `test_api.py` (stale flag), `e2e/offline.mjs` |
| Failure states | Catalog down: message and "Try again"; assets down: message in the At-risk panel; weather frames down: message; explanation fails: message, and the fact table is kept apart from the written text; map fails to load: notice that lists still work | `e2e/smoke.mjs` failure-mode step |
| Gemini text | Facts first; the text is checked with the grounding guard and replaced by a fixed template if it contains a number not in the facts, or if Gemini fails | `test_asset_explain.py` |
| Cost control | Model routes (advisory, tts, agent, voice, bulletin, scenario, dispatch) limited to 10–20 calls a minute per client; the Why button 20 a minute; 429 with Retry-After | `test_api.py` (rate limit) |
| Accessibility | axe (including colour contrast) has no serious or critical issues on the landing page and the dashboard; keyboard control of the timeline; text alternatives for every button; markers use shape as well as colour | `e2e/smoke.mjs` |
| Weak network | Service worker keeps the app and last data; offline page still lists views and at-risk assets | `e2e/offline.mjs` |
| Secrets | `.env`, tokens and keys are git-ignored; the browser only receives `VITE_` keys | review before every commit |

## Still to do by the owner

1. **Restrict the Google Maps browser key** in the Cloud console: HTTP referrers `https://surgesight-221627601364.asia-south1.run.app/*` and `http://localhost:5173/*`, and only the Maps JavaScript API.
2. **Review the alert thresholds** (`config/alert_thresholds.json`, `needs_expert_review` is still true) with a meteorologist or disaster official.
3. **Have the five translations reviewed** by native speakers (they are drafts written without a translation service).
4. **Walk through the app with a real responder** and note where wording or layout slows them down.
5. **Shared rate limit.** The limit is per server process. With several Cloud Run instances the real ceiling is higher; if that matters, use Firestore or Redis for the counts.
6. **Approve the Vertex/Gemini calls** the Why button makes (a few tenths of a cent each).
