# SurgeSight Command UI — implementation plan (WP10, revised)

Replaces the WP10 outline in `IMPLEMENTATION_PLAN.md`. Decisions were agreed with the owner on 2026-09-30. Streamlit stays as an internal dev harness; this React app becomes the product and the demo.

## 1. Agreed decisions

| # | Topic | Decision |
|---|---|---|
| U1 | Look | **Windy-style minimal, professional.** The weather is the hero; chrome is small, translucent and quiet. No neon, no glow. |
| U2 | Layout | **Map-first, floating.** Full-bleed map; layer card top-left; agent dock right; mode dock + timeline at the bottom. |
| U3 | Map engine | **Google Maps JS (vector, Map IDs) + deck.gl** via `GoogleMapsOverlay` in interleaved mode (one WebGL context). |
| U4 | Data mode | **Replay + live-ready.** Michaung 2023 replays hour by hour; a LIVE mode lights up when the monitor ingests a new bulletin. |
| U5 | Weather layers | Wind particles (hero), rain radar, track + uncertainty cone + ensemble, impact overlays (surge, river flood, assets by tier, district exposure). |
| U6 | Features | **Contextual drawers** from a bottom mode dock: Impact, What-if, Departments, Alerts, Validation. The map reacts to every drawer. |
| U7 | Motion | **Restrained.** React Bits only where motion carries meaning (counters, text reveal, list entry, intro background). The map itself stays calm. |
| U8 | Stack | Vite + React 19 + TypeScript, Tailwind v4, shadcn/ui, React Bits (shadcn registry `@react-bits`), deck.gl 9, `@vis.gl/react-google-maps`, TanStack Query, Zustand, Motion, cmdk, vaul, react-i18next, Firebase JS SDK. |
| U9 | Agent | **Collapsible right dock**: pill → translucent panel with chat, live tool trace and voice. Mentions of assets and districts fly the map. |
| U10 | Basemap | **Switchable**: muted dark grey (default), satellite, terrain. |
| U11 | Devices | **Fully responsive.** Desktop 60 fps (120 fps on ProMotion); tablet; phone with bottom sheets and fewer particles. |
| U12 | Rain source | **Toggle**: GFS forecast as issued at the cutoff (default, leakage-honest) vs IMERG observed (labelled "validation only"). |
| U13 | Timeline | **Now-line split.** One valid-time scrubber; a draggable cutoff marker separates observed past (solid) from forecast future (dashed, cone, ensemble). Moving it re-issues the experimental forecast. |
| U14 | Type | **Geist + Geist Mono** (mono for numbers, coordinates, times). Noto Sans Indic families loaded per locale. |
| U15 | Colours | **Perceptual and colour-blind safe** ramps; risk tiers also carry shape cues. |
| U16 | Auth | **Firebase Auth now**: department accounts with a `department` custom claim; a one-click demo (viewer) account for judges. |
| U17 | Opening | **Short fly-in** (~2.5 s, skippable, once per session) while data loads. |
| U18 | UI language | **Full i18n**: English, Tamil, Telugu, Hindi, Odia, Bengali for the whole interface. |
| U19 | Sequencing | **Vertical slices**, each demoable and committed. |

## 2. Screen anatomy

```
┌───────────────────────────────────────────────────────────────────────────┐
│ ◉ SurgeSight   MICHAUNG · Severe Cyclonic Storm · 04 Dec 14:00 IST  REPLAY │ ⌘K  அ ▾  Collector ▾  ◯
│ ┌──────────┐                                                   ┌────────┐ │
│ │ Layers   │          ~ ~ ~ wind particles ~ ~ ~              │ Ask ◖🎙│ │  ← agent pill
│ │ ◉ Wind   │                ╭────╮  cone                       └────────┘ │     expands to a
│ │ ◉ Rain ▾ │      ●────●────●┄┄┄◎┄┄┄  track / ensemble                     │     400 px panel
│ │ ○ Surge  │         rain radar loop                                      │
│ │ ◉ Assets │                               ┌ 13.08N 80.27E ─────┐          │  ← cursor readout
│ │ Map ▾    │                               │ 62 km/h NE · 18 mm/h│          │
│ └──────────┘                               └─────────────────────┘          │
│ ▭▭▭ legend                                                                  │
│      [ Impact ] [ What-if ] [ Departments ] [ Alerts ] [ Validation ]       │  ← mode dock
│ ▶ ▮▮  1× 2× 4× 8×  ├──30 Nov──1 Dec──2 Dec──3 Dec─┃NOW┃┄┄4 Dec┄┄5 Dec┄┄┤    │  ← timeline
└───────────────────────────────────────────────────────────────────────────┘
```

- **Top bar (48 px, translucent):** mark, storm chip (name, IMD class, valid time in IST), REPLAY/LIVE pill, ⌘K, language, "Viewing as" role, account.
- **Layer card:** grouped toggles (Weather, Tracks, Impact) plus the basemap switcher. Collapses to an icon rail on tablet.
- **Legend:** bottom-left, auto-built from the active layers, units shown.
- **Cursor readout:** wind speed and direction plus rain rate at the cursor for the current frame (bilinear sample of the CPU copy of the grid). On touch devices, long-press.
- **Asset popover:** name, type, tier (colour + shape), hazard bars (wind, surge, rain flood), district, source on hover.
- **Provenance:** every KPI and number shows its tool and run id on hover (the grounding story, made visible).

### Drawers (desktop: 380 px left panel replacing the layer card; phone: vaul bottom sheet with snap points)

| Drawer | Content | Map reaction | Backing API |
|---|---|---|---|
| Impact | Tier counts and exposed people (animated counters), dominant-hazard filter, virtualised priority list | Assets filter; list click flies to asset | `/api/risk_v2`, `/api/exposure/{run}`, `/api/assets` |
| What-if | N/S, E/W and intensity sliders; "+30 km north" preset; baseline vs scenario; "Run ensemble" → P(HIGH+) ranking | Ghost track moves live; newly HIGH assets pulse once | `/api/scenario` (≈0.04 s, debounced 120 ms), `/api/ensemble` |
| Departments | Seven tabs; priority assets; route access; advisory in the chosen language; audio player; CAP preview | Department's assets and exposure polygon highlighted | `/api/advisory`, `/api/tts`, `/api/cap/{id}` |
| Alerts | Approval queue (approve / reject / send, role-gated), CAP XML viewer and download, sent log, parametric panel (ILLUSTRATIVE badge), push subscribe | CAP polygon outlined | `/api/dispatch*`, `/api/parametric/{run}`, `/api/push/*` |
| Validation | Sentinel-2 flood flag vs screening, AUC bars, Gemini map review, GFS vs Kalman error chart | Flooded / not-flooded assets shown | `/api/validation/satellite/{run}`, `nwp_comparison` |

### Agent dock

- Pill "Ask SurgeSight" with a mic. It expands into the panel (spring). On phone it is a full-height sheet.
- Streams `POST /api/agent` (SSE; `step`, `answer`, `error`). Each tool call enters the trace as a row (React Bits `AnimatedList`): tool, agent, duration, ok. The answer text reveals once (not token-by-token theatre).
- Grounded badge; if numbers were redacted, a visible note says so. Engine toggle: single orchestrator / ADK team.
- Asset and district names in the answer become chips; clicking one flies the map there.
- Voice: push-to-talk → `/api/voice/ask` (new; STT → agent → TTS answer). Gemini Live over WebSocket is an optional stretch (S5b).

## 3. Design system

**Surfaces (dark UI over every basemap):** `--bg #0B0D10`, `--panel rgba(16,19,24,0.72)` with `backdrop-filter: blur(16px) saturate(140%)`, `--border rgba(255,255,255,0.08)`, `--text #E6E8EB`, `--muted #8B939D`, one accent `--accent #7FA7D9` (steel blue). Radius 12 px panels, 8 px controls. Shadows soft and low. No gradients on chrome.

**Ramps (perceptual, colour-blind safe; final values tuned in S2 against the dark and satellite basemaps):**

| Scale | Stops |
|---|---|
| Wind (m/s, 0→40) | `#2B4A6F` → `#3F8FA6` → `#7CC4B0` → `#E6D3A3` → `#E08A6A` → `#B8434A` |
| Rain (mm/h, log, 0.2→50) | transparent → `#4F7CC0` → `#6B5FC4` → `#A34FB0` → `#D24A8C` → `#F4D6E4` |
| Risk class | LOW `#9AA5B1` ○ · MODERATE `#E0B34A` □ · HIGH `#E07B39` △ · CRITICAL `#B8322A` ◆ |
| Triage tier | Tier 1–4 as the same ordered hues, with a label, never colour alone |

**Type:** Geist 13/14/16/20/28; Geist Mono with tabular numerals for every figure. Indian number grouping (`Intl.NumberFormat('en-IN')`, lakh/crore) in every locale.

**Motion tokens:** drawer spring (stiffness 420, damping 40); fades 160–220 ms; layer toggles crossfade 300 ms; camera eases with a custom cubic over `map.moveCamera` per frame. `prefers-reduced-motion`: particles freeze into static arrows, no fly-in, no counters.

**React Bits (restrained; exact names confirmed through the shadcn MCP before install):** `CountUp` (KPIs), `SplitText` / `BlurText` (intro title, agent answer reveal), `AnimatedList` (tool trace), `ShinyText` (agent "thinking"), `FadeContent` / `AnimatedContent` (drawer content), one subtle background (`Threads` or `Silk`, desaturated slate) only on the intro and sign-in screens.

## 4. Performance architecture (the 60–120 Hz requirement)

1. **The render loop never goes through React.** A single frame clock (vanilla Zustand store + `requestAnimationFrame`) owns the playback time. deck.gl layers read it through uniforms. React re-renders the timeline label at most ~10 Hz.
2. **Wind particles on the GPU.** Port of the webgl-wind technique (ISC licence, V. Agafonkin): particle state in ping-pong float textures, advection in a fragment shader, trails by fading the previous frame. Wrapped as a custom deck.gl layer that draws into the interleaved Google Maps context. The wind field is interpolated between hourly frames in the shader (`mix(frameA, frameB, t)`), so time is continuous.
3. **Rain radar crossfade.** Both neighbouring frames are bound as textures; a colour-ramp shader mixes them. No per-frame texture uploads during playback.
4. **Everything preloaded.** The Bay domain at 0.25° is about 112 × 100 cells, so a whole cycle is a single atlas PNG of a few hundred KB. All frames for the replay are GPU textures within seconds of opening (during the fly-in).
5. **Stable layers.** Layer instances are memoised; changes go through `updateTriggers`; assets (4,214) are one `ScatterplotLayer` with binary attributes.
6. **Adaptive quality.** Particle count by device: desktop 65k, tablet 25k, phone 8k. DPR capped at 2. If the measured frame time exceeds budget for 2 s, particles and trail resolution step down.
7. **Budget:** ≤ 8 ms of JS + GPU work per frame (120 Hz headroom). Dev overlay `?perf=1` shows fps and frame time.

## 5. New backend pieces

### 5.1 Weather frames (`scripts/build_weather_frames.py`, cached, Earth Engine only at build time)

- **Domain** 0–25° N, 72–100° E; **window** 2023-11-30 00Z → 2023-12-07 00Z.
- **Analysis wind (past):** `NOAA/GFS0P25` hours f000–f005 from each 6-hourly cycle, stitched hourly: 10 m u/v, precipitation rate.
- **Forecast wind and rain (future):** for each issue cycle every 12 h in the window, hours f000–f072 at 3-hourly steps (interpolated to continuous time in the shader).
- **Observed rain:** `NASA/GPM_L3/IMERG_V07` half-hourly, aggregated to hourly.
- **Encoding:** wind u,v → R,G bytes over ±40 m/s; rain → R byte on a log scale; one atlas PNG per (variable, cycle); `manifest.json` with bounds, grid size, frame times, scales, cycle issue times and source labels. Output in `data/processed/weather/`.
- **Leakage rule (tested):** for a cutoff C, future frames come only from the latest cycle issued at or before C; IMERG frames after C are served only when the "observed (validation)" toggle is on and are labelled so.
- **Test:** `scripts/test_weather_frames.py` → `SURGESIGHT_WEATHER_FRAMES_OK` (manifest complete, value round-trip error ≤ 0.2 m/s, leakage rule holds).

### 5.2 API additions (`api/routes_web.py`)

| Route | Purpose |
|---|---|
| `GET /api/weather/manifest` | Frame catalogue |
| `GET /api/weather/{file}` | Static atlas PNGs, immutable cache headers |
| `GET /api/timeline` | Observed track with times, bulletin cutoffs, landfall time |
| `GET /api/layers/{name}` | Compact GeoJSON for surge, river flood, districts with exposure |
| `GET /api/assets?format=columnar` | 4,214 assets as columnar arrays (small, binary-friendly) |
| `POST /api/voice/ask` | Audio in → STT → agent → answer text + TTS audio |
| `GET /api/me` | Firebase-verified user and department |

Existing routes are unchanged. `/api/forecast/experimental?cutoff=` already takes the cutoff.

### 5.3 Auth (Firebase)

- Firebase Auth providers: Email/Password and Google. Test users, one per department, plus `demo` (viewer).
- `scripts/set_department_claims.py` (firebase-admin) sets `{department, role}` custom claims.
- `api/auth.py`: `AUTH_MODE=off|firebase`. In firebase mode, a dependency verifies the ID token; approve/reject/send need role `approver` (Collector) and are refused for `viewer`. The existing allow-list and dry-run default still apply.
- New dependency: `firebase-admin`.

### 5.4 i18n

- `react-i18next`; locales `en, ta, te, hi, or, bn` in `frontend/src/locales/*.json`.
- `scripts/translate_ui.py`: Gemini (Vertex) translates `en.json` once with a glossary (CAP, IMD, tier and hazard names kept consistent). Output is marked machine-translated, pending native review.
- Indic fonts (Noto Sans Tamil / Telugu / Devanagari / Oriya / Bengali) loaded only for the active locale.
- Google Maps labels follow the UI language (the Maps loader is re-initialised on language change).
- Agent answers and advisories use the UI language by default.

## 6. Frontend structure

```
frontend/
  index.html  vite.config.ts  components.json (registries: @react-bits)
  src/
    app/            App.tsx, providers (Query, Auth, i18n), router (/ and /sign-in)
    map/            MapCanvas.tsx (Google Map + GoogleMapsOverlay), camera.ts (eased flights)
    layers/         WindParticleLayer/ (shaders), RainLayer/, tracks.ts, assets.ts, impact.ts
    weather/        manifest.ts, atlas loader → textures, sample.ts (cursor readout)
    timeline/       clock.ts (rAF store), Timeline.tsx, NowLine.tsx
    panels/         TopBar, LayerCard, Legend, ModeDock, CursorReadout, AssetPopover
    drawers/        Impact, WhatIf, Departments, Alerts, Validation
    agent/          AgentDock, TraceList, sse.ts, VoiceButton
    intro/          FlyIn.tsx
    lib/            api.ts (typed client), format.ts (en-IN numbers), colors.ts (ramps), auth.ts
    locales/        en ta te hi or bn
    components/ui/  shadcn + React Bits components
```

Dev: Vite on :5173 proxies `/api` to FastAPI on :8000. Production (WP11): Firebase Hosting with `/api/**` rewritten to Cloud Run.

## 7. Slices (each ends demoable and committed)

| Slice | Scope | Done when | Est. |
|---|---|---|---|
| **S0 Spike** | Scaffold `frontend/`, Tailwind v4, shadcn init with `@react-bits` registry; Google vector map + interleaved deck.gl; a throwaway particle layer; check fps and whether interleaving works on the satellite basemap | ≥ 60 fps playback on the dev Mac; satellite approach decided (interleaved, or non-interleaved fallback for satellite only) | 1 h |
| **S1 Weather data** | `build_weather_frames.py`, manifest, `routes_web.py` weather + timeline routes, test | `SURGESIGHT_WEATHER_FRAMES_OK` | 2 h |
| **S2 Map, weather, timeline** | Wind particles, rain crossfade + source toggle, legend, cursor readout, layer card, basemap switcher, top bar, timeline with now-line and keyboard control | Playwright screenshot + measured ≥ 55 fps over 5 s playback (headed Chrome) | 4 h |
| **S3 Tracks and opening** | Observed track draws over time; experimental forecast re-issued on cutoff drag; ensemble spaghetti; breathing cone; assets by tier; fly-in intro | Cutoff drag updates forecast in < 300 ms; intro skippable | 2.5 h |
| **S4 Auth and i18n** | Firebase Auth + sign-in screen, claims script, `api/auth.py`, role gating, i18n infra, translated locales, Indic fonts, Maps label language | Viewer cannot approve (API returns 403); all six locales render with no missing keys | 3 h |
| **S5 Agent dock** | SSE client, trace list, grounded badge, fly-to chips, engine toggle, push-to-talk voice (`/api/voice/ask`) | Live question answered with trace; redaction note shown when triggered | 2.5 h |
| S5b (stretch) | Gemini Live over WebSocket | — | 2 h |
| **S6 Drawers** | Impact, What-if, Departments, Alerts, Validation, one commit each | Each drawer's map reaction works; approval flow end-to-end in dry run | 5 h |
| **S7 Responsive and access** | Tablet rail, phone bottom sheets, touch readout, reduced motion, keyboard and focus order, contrast check | Playwright screenshots at 390, 820, 1440 px; axe has no serious issues | 2 h |
| **S8 Verify and capture** | `scripts/test_web.py` (build + Vitest + Playwright) → `SURGESIGHT_WEB_OK` in `run_all_tests.py`; README screenshots; backup screen recording | Marker passes; README screenshots added | 1 h |

### 7.1 Model per slice and hand-off order

The owner switches models between phases. Each phase ends with a commit and a message telling the owner to switch.

| Phase | Model | Work | Why |
|---|---|---|---|
| **A** | Sonnet 5.5, medium | **S1** complete (weather frames, manifest, leakage test). Backend of S4/S5 only: `api/routes_web.py` (all routes in 5.2), `api/auth.py` + `AUTH_MODE` + auth tests with a mocked verifier, `scripts/set_department_claims.py`, `POST /api/voice/ask`, add `firebase-admin` to requirements. **No `frontend/` work.** | Python and API work following existing repo patterns; none of it needs the front-end scaffold |
| **B** | **Opus 5.5** | **S0** spike and scaffold, then **S2** (GPU wind particles, rain crossfade shader, frame clock, timeline, layer card, legend, cursor readout) | deck.gl 9 / luma.gl 9 custom shaders and interleaved Google Maps are where the 60 fps target is won or lost |
| **C** | Sonnet 5.5, medium | **S3**, front end of **S4** (sign-in, i18n, `translate_ui.py`, fonts), **S5** agent dock, **S6** drawers, **S7**, **S8** | Component work on top of the Phase B foundation |
| (any time) | Opus 5.5 | Any frame-rate regression below 55 fps | Profiling and GPU debugging |

Phase A stop condition: `SURGESIGHT_WEATHER_FRAMES_OK` and `SURGESIGHT_API_OK` pass offline, committed; then tell the owner "Phase A done, switch to Opus 5.5 for Phase B".

### 7.2 Phase B outcome (S0 + S2, 2026-09-30)

- **Satellite decision (S0):** the hybrid satellite basemap keeps vector rendering, so deck.gl stays interleaved on dark, satellite and terrain. The non-interleaved overlay is still wired in and switches automatically if the map ever reports raster rendering.
- **deck.gl 9.4 workaround:** `GoogleMapsOverlay` could create a canvas-backed Deck before Google's GL context arrived, and then nothing drew. `frontend/src/map/overlay.ts` skips that path in interleaved mode.
- **Trails:** particle trails are a ring of past positions drawn as tapered quads, not the fade-previous-frame technique in §4.2. Fading breaks when the map redraws itself or the camera moves.
- **Budget:** 22k particles on desktop, 12k on tablet and 6k on phone, with trail 20/14. 65k reached 75 fps but looked like a solid carpet.
- **Measured on the dev Mac (headed Chrome, 1200×897 CSS px):** 113–120 fps mean over 5 s of 8× playback across the cutoff, worst frame 17 ms after atlases are pre-uploaded (one per frame).
- **Measurement method:** these numbers come from the Chrome DevTools harness. The Playwright version of this check belongs to S8.
- **Byte-exact check:** the browser decodes the atlases byte-for-byte as `services/weather_frames.py` does (same checksum).

**Total ≈ 23 h** (the original WP10 estimate of 5 h did not include animated weather, auth or full i18n).

## 8. Tests

- **Vitest:** atlas decode round-trip, clock and timeline maths, leakage selection of frames for a cutoff, en-IN formatting, i18n key parity across locales.
- **Playwright:** open app → skip intro → play 5 s → assert fps ≥ 55; drag cutoff → forecast updates; open each drawer; viewer approve → 403; screenshots at three widths (reused in README).
- **Python:** `test_weather_frames.py`, auth tests in `test_api.py` (`AUTH_MODE=firebase` with a mocked verifier).

## 9. Owner actions (I will give exact steps when we reach them)

1. **Maps:** create vector Map IDs (dark style, and one for satellite/terrain if needed) in Cloud Console → Google Maps Platform → Map Management; a browser key restricted to `localhost:5173` and later the Hosting domain.
2. **Firebase Auth:** enable Email/Password and Google providers in the Firebase console (same project).
3. **Approve** the one-off Gemini translation run (a few cents on Vertex) and native-speaker review later if possible.

## 10. Risks

| Risk | Mitigation |
|---|---|
| Interleaved deck.gl may not support the satellite basemap | S0 decides; non-interleaved overlay for satellite only |
| 120 Hz depends on the display and browser | Target 60 fps everywhere; 120 on ProMotion is a bonus, measured not promised |
| Machine-translated UI may be wrong | Glossary, "machine translated" note in the About panel, English fallback per key |
| Auth adds friction for judges | One-click demo (viewer) sign-in on the sign-in screen |
| GFS/IMERG gaps for some hours | Manifest marks missing frames; the shader holds the last good frame and the legend says so |
| Scope (≈ 23 h) | Slices are ordered so S0–S3 alone is a strong demo; S5b and parts of S7 can drop |
