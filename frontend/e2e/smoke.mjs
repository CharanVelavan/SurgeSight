// End-to-end check of the running dashboard (dev server + API). Prints one JSON line; exit 1 on failure.
// node e2e/smoke.mjs <baseUrl> [--screenshots <dir>] [--min-fps 55] [--no-fps]
import { chromium } from 'playwright'
import AxeBuilder from '@axe-core/playwright'

const args = process.argv.slice(2)
const flag = (k, d) => (args.includes(k) ? args[args.indexOf(k) + 1] : d)
const base = args[0]
const shots = flag('--screenshots', null)
const minFps = Number(flag('--min-fps', 55))
const skipFps = args.includes('--no-fps')
const failures = []
const check = (ok, msg) => { if (!ok) failures.push(msg) }

const browser = await chromium.launch({ channel: 'chrome', headless: false, args: ['--ignore-gpu-blocklist'] })
const context = await browser.newContext({ viewport: { width: 1440, height: 860 } })
const page = await context.newPage()
const errors = []
page.on('console', (m) => m.type() === 'error' && errors.push(m.text().slice(0, 200)))
page.on('pageerror', (e) => errors.push(`pageerror: ${e.message.slice(0, 200)}`))
await page.addInitScript(() => sessionStorage.setItem('surgesight.intro', '1'))
// landing page: tiles, a working storm link, and the not-official notice
await page.goto(base)
await page.getByRole('link', { name: /Cyclone Michaung/ }).waitFor({ timeout: 15000 })
check((await page.getByText('Coming soon').count()) >= 3, 'coming soon tiles missing on the landing page')
check(await page.getByText(/not an official warning/).isVisible(), 'landing page lacks the not-official notice')
{
  const landing = await new AxeBuilder({ page }).disableRules(['color-contrast']).analyze()
  const bad = landing.violations.filter((v) => ['serious', 'critical'].includes(v.impact))
  check(bad.length === 0, `axe (landing): ${bad.map((v) => v.id).join(', ')}`)
  if (shots) await page.screenshot({ path: `${shots}/landing-1440.png` })
}
await page.getByRole('link', { name: /Cyclone Michaung/ }).click()
await page.waitForURL('**/storm/michaung_2023')
await page.waitForFunction(() => window.__overlay?._deck?.layerManager?.getLayers().some((l) => l.id === 'wind'), null, { timeout: 30000 })
await page.waitForTimeout(3000)

const mapState = () => page.evaluate(() => { const m = window.__overlay._map; const c = m.getCenter(); return { zoom: m.getZoom(), lat: c.lat(), lng: c.lng(), gesture: m.get('gestureHandling'), rt: document.documentElement.dataset.renderingType } })
const layerIds = () => page.evaluate(() => window.__overlay._deck.layerManager.getLayers().map((l) => l.id))

// 1. interleaved vector map, weather and assets present
const a = await mapState()
check(a.rt === 'vector-interleaved', `rendering type ${a.rt}`)
const ids = await layerIds()
for (const need of ['alert-zones', 'rain', 'wind', 'track-observed', 'forecast-wind']) check(ids.includes(need), `layer ${need} missing`)
check(!ids.some((i) => i.startsWith('assets-')), 'infrastructure should be hidden in the national view')

// 2. the national frame: free zoom and pan, but never outside the boundary or further out than the frame
check(a.gesture === 'greedy', `national gesture ${a.gesture}`)
await page.mouse.move(700, 400); await page.mouse.down(); await page.mouse.move(400, 250, { steps: 8 }); await page.mouse.up()
await page.waitForTimeout(400)
const b0 = await mapState()
check(Math.abs(b0.zoom - a.zoom) < 1e-3 && b0.lng >= 46 && b0.lng <= 118 && b0.lat >= -2 && b0.lat <= 40.5, `panned outside the boundary at frame zoom: ${JSON.stringify(a)} -> ${JSON.stringify(b0)}`)
for (let i = 0; i < 4; i++) { await page.mouse.move(700, 400); await page.mouse.wheel(0, -400); await page.waitForTimeout(150) }
await page.waitForTimeout(600)
const b1 = await mapState()
check(b1.zoom > a.zoom + 0.5, `wheel did not zoom the national view (${a.zoom} -> ${b1.zoom})`)
await page.mouse.move(700, 400); await page.mouse.down(); await page.mouse.move(1300, 700, { steps: 10 }); await page.mouse.up()
await page.mouse.move(700, 400); await page.mouse.down(); await page.mouse.move(1300, 700, { steps: 10 }); await page.mouse.up()
await page.waitForTimeout(400)
const b2 = await mapState()
check(b2.lng >= 46 && b2.lng <= 118 && b2.lat >= -2 && b2.lat <= 40.5, `centre left the boundary: ${b2.lat}, ${b2.lng}`)
for (let i = 0; i < 8; i++) { await page.mouse.wheel(0, 600); await page.waitForTimeout(100) }
await page.waitForTimeout(600)
check((await mapState()).zoom >= a.zoom - 1e-6, 'zoomed out past the national frame')

// 3. impact area zooms in and allows panning
await page.getByRole('radio', { name: 'Impact area' }).click()
await page.waitForTimeout(2500)
const c = await mapState()
check(c.zoom > a.zoom + 2 && c.gesture === 'greedy', `impact view zoom ${c.zoom} gesture ${c.gesture}`)
check((await layerIds()).some((i) => i.startsWith('assets-icon-')), 'glyph markers missing in impact view')
// 3b. the Why button: pick a top asset from the summary, ask, and get numbers plus a written text
await page.getByRole('button', { name: /Chennai|NCPS|Hospital|Harbour|Unnamed/ }).first().click()
const why = page.getByRole('button', { name: /Why is this (not )?critical\?/ })
await why.waitFor({ timeout: 5000 })
await why.click()
await page.getByText('The numbers').waitFor({ timeout: 10000 })
await page.getByText('Closest approach').first().waitFor({ timeout: 5000 })
await page.getByText('Elevation').first().waitFor({ timeout: 5000 })
await page.getByText('Waterlogging').first().waitFor({ timeout: 5000 })
await page.getByText('In words').waitFor({ timeout: 10000 })
await page.getByText(/Standard wording|Written by Gemini/).waitFor({ timeout: 15000 })
await page.getByRole('button', { name: 'Close details' }).click()
await page.getByRole('radio', { name: 'India' }).click()
await page.waitForTimeout(2500)
check(Math.abs((await mapState()).zoom - a.zoom) < 1e-3, `india view did not return to the national frame: ${JSON.stringify(await mapState())} vs ${a.zoom}`)

// 4. moving the cutoff re-issues the forecast
const t0 = Date.now()
const req = page.waitForResponse((r) => r.url().includes('/api/forecast/experimental') && r.status() === 200, { timeout: 5000 }).catch(() => null)
await page.evaluate(() => window.__clock.setState({ cutoff: Date.UTC(2023, 11, 4, 0), time: Date.UTC(2023, 11, 4, 0) }))
const resp = await req
let forecastMs = null
if (resp) {
  await page.waitForFunction(() => window.__overlay._deck.layerManager.getLayers().some((l) => l.id === 'forecast-wind'), null, { timeout: 5000 })
  forecastMs = Date.now() - t0
}
check(resp !== null, 'no forecast request after moving the cutoff')
check(forecastMs !== null && forecastMs < 1500, `forecast took ${forecastMs} ms`)

// 5. leakage: with the forecast rain source the legend names the cycle issued at the cutoff
await page.evaluate(() => window.__clock.setState({ time: Date.UTC(2023, 11, 4, 6) }))
await page.waitForTimeout(700)
const legend = await page.locator('section[aria-label="What am I seeing?"]').innerText()
check(/GFS forecast issued 04 Dec 00Z/.test(legend), `legend: ${legend.replace(/\n/g, ' | ').slice(0, 160)}`)

// 6. frame rate over 5 s of 8x playback across the cutoff
let fps = null
if (!skipFps) {
  fps = await page.evaluate(async () => {
    window.__clock.setState({ cutoff: Date.UTC(2023, 11, 3, 12), time: Date.UTC(2023, 11, 3, 6), speed: 8, playing: true })
    const dts = []; let last = performance.now(); const t0 = last
    await new Promise((res) => { const f = (n) => { dts.push(n - last); last = n; n - t0 < 5000 ? requestAnimationFrame(f) : res() }; requestAnimationFrame(f) })
    window.__clock.setState({ playing: false })
    dts.shift(); dts.sort((x, y) => x - y)
    return +(1000 / (dts.reduce((s, x) => s + x, 0) / dts.length)).toFixed(1)
  })
  check(fps >= minFps, `fps ${fps} < ${minFps}`)
}

// 7. accessibility: no serious or critical violations
const axe = await new AxeBuilder({ page }).disableRules(['color-contrast']).analyze()
const bad = axe.violations.filter((v) => ['serious', 'critical'].includes(v.impact))
check(bad.length === 0, `axe: ${bad.map((v) => `${v.id}(${v.nodes.length})`).join(', ')}`)

// 8. screenshots at three widths
if (shots) {
  await page.evaluate(() => window.__clock.setState({ cutoff: Date.UTC(2023, 11, 3, 12), time: Date.UTC(2023, 11, 3, 12), playing: false }))
  for (const [w, h, name] of [[1440, 860, 'desktop'], [820, 1180, 'tablet'], [390, 844, 'phone']]) {
    await page.setViewportSize({ width: w, height: h })
    await page.waitForTimeout(2500)
    await page.screenshot({ path: `${shots}/${name}-${w}.png` })
  }
}

// 9. live weather (only when data/processed/live has been built)
const catalog = await (await fetch(`${base}/api/catalog`)).json()
let liveInfo = null
if (catalog.tiles.find((t) => t.id === 'live')?.status === 'available') {
  await page.setViewportSize({ width: 1440, height: 860 })
  await page.goto(`${base}/live`)
  await page.waitForFunction(() => window.__overlay?._deck?.layerManager?.getLayers().some((l) => l.id === 'wind'), null, { timeout: 30000 })
  await page.getByRole('status').first().waitFor({ timeout: 10000 })
  await page.waitForTimeout(2500)
  const liveIds = await layerIds()
  for (const need of ['cloud', 'wind', 'alert-zones']) check(liveIds.includes(need), `live layer ${need} missing`)
  check(!liveIds.some((i) => i.startsWith('track-') || i.startsWith('assets-')), 'live view must not draw storm or infrastructure layers')
  const banner = await page.getByRole('status').first().innerText()
  check(/GFS model run|old/.test(banner), `live banner: ${banner}`)
  await page.getByRole('radio', { name: 'Temp' }).click()
  await page.waitForTimeout(800)
  check((await layerIds()).includes('temperature') && !(await layerIds()).includes('cloud'), 'temperature layer did not replace cloud')
  await page.mouse.move(700, 450)
  await page.waitForTimeout(400)
  check(/°C/.test(await page.locator('body').innerText()), 'live cursor readout lacks temperature')
  if (shots) await page.screenshot({ path: `${shots}/live-1440.png` })
  liveInfo = banner.slice(0, 80)
}

check(errors.length === 0, `console errors: ${errors.slice(0, 3).join(' || ')}`)
const zoneMs = await page.evaluate(() => window.__zoneMs ?? null)
console.log(JSON.stringify({ ok: failures.length === 0, failures, fps, forecastMs, zoneMs, live: liveInfo, zoom: { india: +a.zoom.toFixed(2), impact: +c.zoom.toFixed(2) } }))
await browser.close()
process.exit(failures.length ? 1 : 0)
