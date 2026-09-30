// Record every scene of the demo from the local app (and cards.html) as work/video/<id>.mp4, timed to the narration.
// Needs: the API and `npm run dev` running (see scenes.json "base"), work/durations.json from voice.py, ffmpeg.
// Run from the repo root:  node docs/pitch/video/record.mjs [s08 s09 ...]   (no ids = all scenes)
import fs from 'node:fs'
import path from 'node:path'
import { execFileSync } from 'node:child_process'
import { createRequire } from 'node:module'
import { fileURLToPath, pathToFileURL } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const require = createRequire(path.join(HERE, '../../../frontend/package.json'))
const { chromium } = require('playwright')

const cfg = JSON.parse(fs.readFileSync(path.join(HERE, 'scenes.json'), 'utf8'))
const dur = JSON.parse(fs.readFileSync(path.join(HERE, 'work/durations.json'), 'utf8'))
const only = process.argv.slice(2)
const BASE = cfg.base
export const LEAD = 0.5, TAIL = 0.9
const MIN = { s01: 5.5, s04: 12, s05: 11, s07: 11, s08: 20, s09: 20, s10: 12, s11: 8, s12: 19, s13: 9, s16: 9 }
export const sceneLen = id => Math.max(MIN[id] ?? 0, (dur[id] ?? 0) + LEAD + TAIL)
const OUT = path.join(HERE, 'work/video')
fs.mkdirSync(OUT, { recursive: true })
const sleep = ms => new Promise(r => setTimeout(r, ms))

// Subtitles: sentences (long ones split at a comma) spread over the narration by length.
function subtitles(text, seconds) {
  const parts = []
  for (const s of text.match(/[^.!?]+[.!?]+/g) ?? [text]) {
    const t = s.trim()
    if (t.length > 95 && t.includes(', ')) {
      const i = t.indexOf(', ', Math.floor(t.length / 2) - 20)
      if (i > 0) { parts.push(t.slice(0, i + 1), t.slice(i + 2)); continue }
    }
    parts.push(t)
  }
  const total = parts.reduce((a, p) => a + p.length, 0)
  let t = LEAD
  return parts.map(p => { const d = (seconds * p.length) / total; const s = { t0: t, t1: t + d, text: p }; t += d; return s })
}

// Smooth, eased mouse moves (the overlay draws a cursor that follows the mouse).
let mx = 800, my = 450
async function moveTo(page, x, y, ms = 700) {
  const x0 = mx, y0 = my, n = Math.max(8, Math.round(ms / 16))
  for (let i = 1; i <= n; i++) {
    const p = i / n, e = p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2
    mx = x0 + (x - x0) * e; my = y0 + (y - y0) * e
    await page.mouse.move(mx, my)
    await sleep(16)
  }
}
async function hover(page, loc, ms) {
  const b = await loc.boundingBox()
  if (!b) throw new Error('element not visible')
  await moveTo(page, b.x + b.width / 2, b.y + b.height / 2, ms)
}
async function click(page, loc, ms = 650) {
  await hover(page, loc, ms)
  await sleep(180)
  await page.mouse.down(); await sleep(70); await page.mouse.up()
}
async function scroll(page, dy, ms = 900) {
  const n = Math.round(ms / 30)
  for (let i = 0; i < n; i++) { await page.mouse.wheel(0, dy / n); await sleep(30) }
}

async function capture(page, scene, n, len, actions) {
  const cdp = await page.context().newCDPSession(page)
  const frames = []
  cdp.on('Page.screencastFrame', f => {
    frames.push({ t: f.metadata.timestamp, d: f.data })
    cdp.send('Page.screencastFrameAck', { sessionId: f.sessionId }).catch(() => {})
  })
  const subs = subtitles(scene.text, dur[scene.id] ?? len - LEAD - TAIL)
  await page.evaluate(o => window.__ss.start(o), { chapter: scene.chapter, n, subs })
  const t0 = Date.now() / 1000
  await cdp.send('Page.startScreencast', { format: 'jpeg', quality: 90, maxWidth: 1920, maxHeight: 1080, everyNthFrame: 1 })
  const at = async s => { const w = (t0 + s) * 1000 - Date.now(); if (w > 0) await sleep(w) }
  try { await actions(at) } catch (e) { console.warn(`  ${scene.id}: action failed: ${e.message.split('\n')[0]}`) }
  await at(len)
  await cdp.send('Page.stopScreencast')
  await cdp.detach()
  encode(scene.id, frames, t0, t0 + len)
}

function encode(id, frames, t0, t1) {
  const dir = path.join(HERE, 'work/frames', id)
  fs.rmSync(dir, { recursive: true, force: true }); fs.mkdirSync(dir, { recursive: true })
  frames.sort((a, b) => a.t - b.t)
  const kept = frames.filter(f => f.t < t1)
  if (!kept.length) throw new Error(`${id}: no frames captured`)
  let list = ''
  kept.forEach((f, i) => {
    const name = `f${String(i).padStart(5, '0')}.jpg`
    fs.writeFileSync(path.join(dir, name), Buffer.from(f.d, 'base64'))
    const start = i === 0 ? t0 : f.t, end = i + 1 < kept.length ? kept[i + 1].t : t1
    list += `file '${name}'\nduration ${Math.max(0.001, end - start).toFixed(4)}\n`
  })
  list += `file 'f${String(kept.length - 1).padStart(5, '0')}.jpg'\n`
  fs.writeFileSync(path.join(dir, 'list.txt'), list)
  execFileSync('ffmpeg', ['-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', path.join(dir, 'list.txt'),
    '-vf', 'fps=30,scale=1920:1080:flags=lanczos,format=yuv420p', '-t', (t1 - t0).toFixed(3),
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '16', path.join(OUT, `${id}.mp4`)])
  fs.rmSync(dir, { recursive: true, force: true })
  console.log(`  ${id}: ${kept.length} frames, ${(t1 - t0).toFixed(1)}s`)
}

const role = (p, r, name) => p.getByRole(r, { name })
const tab = (p, name) => p.getByRole('navigation', { name: 'Storm sections' }).getByRole('link', { name })
const S = `${BASE}/storm/michaung_2023`
const PREFS = { state: { onboarded: true, role: 'health', theme: 'light', stormWind: true, stormRain: true, lite: false }, version: 2 }

// What happens on screen in each app scene. `pre` loads the page (not recorded); `run` is timed with at(seconds).
const APP = {
  s04: {
    pre: async p => {
      await p.goto(BASE); await p.evaluate(() => localStorage.clear())
      await p.goto(`${BASE}/welcome`); await role(p, 'heading', 'Welcome to SurgeSight').waitFor({ timeout: 20000 })
    },
    run: async (p, at) => {
      // The welcome intro animation runs for about 2.5 s before the first click.
      await at(2.8); await click(p, role(p, 'button', 'Continue'))
      await at(4.4); await click(p, role(p, 'radio', /Health Department/))
      await at(6.0); await click(p, role(p, 'button', 'Continue'))
      await at(7.2); await click(p, role(p, 'radio', 'Dark'))
      await at(8.5); await click(p, role(p, 'radio', 'Light'))
      await at(9.8); await click(p, role(p, 'button', 'Open SurgeSight'))
    },
  },
  s05: {
    pre: async p => { await p.goto(`${BASE}/live`); await sleep(9000) },
    run: async (p, at) => {
      await at(0.8); await moveTo(p, 820, 420, 1400)
      await at(3.0); await click(p, role(p, 'radio', 'Temp'))
      await at(5.2); await moveTo(p, 960, 610, 1500)
      await at(7.8); await click(p, role(p, 'radio', 'Cloud'))
      await at(9.4); await moveTo(p, 760, 520, 1200)
    },
  },
  s07: {
    pre: async p => { await p.goto(S); await role(p, 'heading', 'Your priorities').waitFor({ timeout: 20000 }); await sleep(1500) },
    run: async (p, at) => {
      await at(1.0); await hover(p, p.getByText('Reaches the coast').first(), 900)
      await at(3.0); await hover(p, role(p, 'heading', 'Your priorities'), 900)
      await at(5.0); await scroll(p, 520, 1400)
      await at(8.0); await scroll(p, 420, 1200)
    },
  },
  s08: {
    pre: async p => { await p.goto(`${S}/map`); await sleep(9000); await role(p, 'radio', 'India').click(); await sleep(3500) },
    run: async (p, at) => {
      await at(0.9); await click(p, role(p, 'radio', 'Impact area'))
      await at(5.0); await click(p, role(p, 'button', 'Play'))
      await at(11.5); await click(p, role(p, 'button', 'Pause'))
      await at(13.0); await click(p, role(p, 'switch', 'Wind'))
      await at(14.8); await click(p, role(p, 'switch', 'Wind'))
      await at(16.5); await moveTo(p, 700, 520, 1300)
    },
  },
  s09: {
    pre: async p => {
      await p.goto(`${S}/facilities`); await role(p, 'button', 'Why?').first().waitFor({ timeout: 20000 })
      await role(p, 'button', 'All types').click(); await sleep(400) // turns every type on, schools included
      await p.getByRole('textbox', { name: 'Search by name' }).fill('KGVB'); await sleep(1200)
    },
    run: async (p, at) => {
      await at(1.0); await click(p, role(p, 'button', 'Why?').first())
      await at(3.0); await click(p, role(p, 'button', /Why is this (not )?critical\?/))
      await p.getByText(/Written by Gemini|Standard wording/).waitFor({ timeout: 25000 })
      await at(9.5); await moveTo(p, 1390, 560, 700); await scroll(p, 420, 1600)
      await at(14.0); await scroll(p, 380, 1400)
    },
  },
  s10: {
    pre: async p => { await p.goto(`${S}/roads`); await role(p, 'region', 'Road kilometres by screening level').waitFor({ timeout: 20000 }); await sleep(1200) },
    run: async (p, at) => {
      await at(1.0); await hover(p, role(p, 'region', 'Road kilometres by screening level'), 900)
      await at(3.3); await hover(p, role(p, 'heading', 'Roads to check first'), 800)
      await at(5.0); await scroll(p, 300, 1000)
      await at(7.5); await hover(p, role(p, 'heading', 'Facility access'), 800)
      await at(9.3); await click(p, role(p, 'button', 'Show on map').first())
    },
  },
  s11: {
    pre: async p => { await p.goto(`${S}/areas`); await sleep(3500) },
    run: async (p, at) => {
      await at(1.0); await moveTo(p, 760, 420, 900)
      await at(2.5); await scroll(p, 380, 1300)
      await at(5.0); await scroll(p, 380, 1300)
    },
  },
  s12: {
    pre: async p => {
      // Draft (or load) the Tamil advisory first so it appears instantly on camera, then return to English.
      await p.goto(`${S}/advisories`); await p.getByText(/Priority actions/).first().waitFor({ timeout: 120000 })
      await role(p, 'combobox', 'Language').selectOption('ta')
      await p.getByText('முன்னுரிமைச் செயல்கள்').first().waitFor({ timeout: 120000 })
      await role(p, 'combobox', 'மொழி').selectOption('en')
      await p.getByText(/Priority actions/).first().waitFor({ timeout: 120000 }); await sleep(1000)
    },
    run: async (p, at) => {
      await at(1.0); await hover(p, p.getByText(/Priority actions/).first(), 900)
      await at(3.0); await scroll(p, 260, 900)
      await at(5.5); await hover(p, role(p, 'combobox', 'Language'), 800)
      await role(p, 'combobox', 'Language').selectOption('ta')
      await p.getByText('முன்னுரிமைச் செயல்கள்').first().waitFor({ timeout: 60000 }).catch(() => {})
      await at(11.5); await hover(p, p.getByText(/Recipients/).first(), 900)
      await at(14.0); await scroll(p, 300, 1100)
    },
    post: async p => { await role(p, 'combobox', 'மொழி').selectOption('en').catch(() => {}) },
  },
  s13: {
    pre: async p => { await p.goto(`${BASE}/settings`); await role(p, 'heading', 'Your role').waitFor({ timeout: 20000 }) },
    run: async (p, at) => {
      await at(1.0); await hover(p, role(p, 'heading', 'Your role'), 800)
      await at(2.3); await click(p, role(p, 'button', 'Switch between light and dark'))
      await at(4.5); await scroll(p, 350, 1100)
      await at(7.0); await click(p, role(p, 'button', 'Switch between light and dark'))
    },
  },
}

const browser = await chromium.launch({ channel: 'chrome', headless: false, args: ['--ignore-gpu-blocklist', '--hide-scrollbars'] })
const context = await browser.newContext({ viewport: { width: 1600, height: 900 }, deviceScaleFactor: 1.2 })
await context.addInitScript({ path: path.join(HERE, 'overlay.js') })
// Every scene except the welcome flow starts as an onboarded Health officer in light theme and English.
await context.addInitScript(p => {
  if (location.origin.startsWith('http') && !location.pathname.startsWith('/welcome') && !localStorage.getItem('surgesight.prefs')) {
    localStorage.setItem('surgesight.prefs', JSON.stringify(p)); localStorage.setItem('surgesight.lang', 'en')
  }
}, PREFS)
const page = await context.newPage()
const cards = pathToFileURL(path.join(HERE, 'cards.html')).href

let n = 0
for (const scene of cfg.scenes) {
  if (scene.kind === 'app') n++
  if (only.length && !only.includes(scene.id)) continue
  const len = sceneLen(scene.id)
  console.log(`${scene.id} (${scene.kind}) ${len.toFixed(1)}s`)
  if (scene.kind === 'card') {
    await page.goto(`${cards}?c=${scene.card}`); await sleep(800)
    await capture(page, scene, '', len, async () => {})
  } else {
    const a = APP[scene.id]
    await a.pre(page)
    mx = 800; my = 450
    await capture(page, scene, String(n).padStart(2, '0'), len, at => a.run(page, at))
    if (a.post) await a.post(page)
  }
}
await browser.close()
