# SurgeSight demo video (Team Echo)

`SurgeSight_TeamEcho_demo_v2.mp4` is 1080p, about 3 minutes, and is made entirely from the local app.

| File | What it does |
|---|---|
| `scenes.json` | The 16 scenes: narration text, chapter titles, and which card or app page each scene shows |
| `voice.py` | One narration clip per scene. Uses your own recording when there is one, otherwise Cloud Text-to-Speech (`en-IN-Chirp3-HD-Charon`) |
| `record.mjs` | Opens Chrome, clicks through the app in time with the narration, and records each scene at 1920×1080 |
| `overlay.js` | Cursor, click ripples, chapter titles and subtitles drawn on top of the app while recording |
| `cards.html` | The animated title, problem, solution, case study, Google, future and closing cards |
| `assemble.py` | Joins the scenes with crossfades and mixes in the narration |

## Rebuild

The API (port 8002) and the web app (`npm run dev`, port 5174) must be running. A Chrome window opens while
recording; leave it alone until the recording finishes.

```bash
.venv/bin/python docs/pitch/video/voice.py        # narration clips and their lengths
node docs/pitch/video/record.mjs                  # all scenes (or: node docs/pitch/video/record.mjs s08 s09)
.venv/bin/python docs/pitch/video/assemble.py     # final MP4
```

## Recording your own voice

The video uses one voice. Pick **one of you** to narrate the whole thing, so the voice stays consistent.
If you want both of you in it, one of you can read s01 to s08 and the other s09 to s16. That splits at a
natural point (from the map to the "why was it alerted" feature), but one narrator usually sounds better.

1. **Equipment.** A phone is enough. Use Voice Memos (iPhone) or Recorder (Android), or QuickTime on the Mac
   (File, New Audio Recording). Wired earphones with a mic are better than the laptop microphone.
2. **Room.** A small room with soft things (curtains, bed, sofa). Close windows, switch off the fan and AC.
3. **Distance.** Hold the phone about a hand's width (15 to 20 cm) from your mouth, slightly to the side so
   your breath does not hit it.
4. **One file per scene.** Read the `text` of each scene in `scenes.json`, exactly as written. Leave a second of
   silence before and after; the script trims it. Re-record any take with a mistake; don't try to fix it.
5. **Pace.** Speak a little slower than normal, and smile slightly. It makes the voice sound warmer.
6. **Name the files by scene** and put them in `docs/pitch/video/own/`:
   `s01.m4a`, `s02.m4a`, … `s16.m4a` (`.wav`, `.mp3` and `.aiff` also work).
7. **Rebuild** with the three commands above. `voice.py` prints `own recording` for every scene it found.
   The recording adapts: if you speak longer, that scene simply lasts longer.

You can mix: any scene without a file in `own/` keeps the Cloud TTS voice.

## Notes

- The local app shows a red "Live mode" banner on Advisories because dispatch is set to live on this machine.
  `overlay.js` hides it in the video, which shows the same dry-run flow the public deployment uses.
- The live weather screen shows its real "forecast is N h old" warning when the newest GFS run is stale.
  Run `python scripts/build_live_weather.py` before recording for a fresh one.
- `work/` holds the per-scene clips and audio (about 120 MB). It can be deleted; the three commands recreate it.
