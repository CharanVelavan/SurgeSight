# SurgeSight command UI

React front end for SurgeSight (plan: `../docs/UI_PLAN.md`). Vite + React 19 + TypeScript, Tailwind v4,
shadcn/ui (registry `@react-bits` in `components.json`), Google Maps JS vector map with deck.gl 9 interleaved.

```bash
npm install
npm run dev        # http://localhost:5173, proxies /api to FastAPI on :8000
npm run build
```

Environment (read from the repo-root `.env`; only `VITE_*` keys reach the browser):

- `VITE_GOOGLE_MAPS_API_KEY` — browser key, restricted to the dev and hosting origins.
- `VITE_GOOGLE_MAP_ID` — vector Map ID. Falls back to Google's `DEMO_MAP_ID` for development.

Debug: `?perf=1` shows fps, frame time and the particle budget; `?particles=N` pins the particle count.
