// End-to-end check of the running app (dev server + API). Prints one JSON line; exit 1 on failure.
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
const ONBOARDED = JSON.stringify({ state: { onboarded: true, role: 'health', theme: 'light', stormWind: true, stormRain: true, lite: false }, version: 2 })

const browser = await chromium.launch({ channel: 'chrome', headless: false, args: ['--ignore-gpu-blocklist'] })
const context = await browser.newContext({ viewport: { width: 1440, height: 860 } })
const page = await context.newPage()
const errors = []
page.on('console', (m) => m.type() === 'error' && !m.text().includes('maps.googleapis.com') && errors.push(m.text().slice(0, 200)))
page.on('pageerror', (e) => errors.push(`pageerror: ${e.message.slice(0, 200)}`))
const axeCheck = async (where) => {
  let r
  for (let i = 0; i < 3; i++) {
    try {
      r = await new AxeBuilder({ page }).analyze()
      break
    } catch (e) {
      if (i === 2 || !e.message.includes('Execution context was destroyed')) throw e
      await page.waitForTimeout(500)
    }
  }
  const bad = r.violations.filter((v) => ['serious', 'critical'].includes(v.impact))
  check(bad.length === 0, `axe (${where}): ${bad.map((v) => `${v.id}(${v.nodes.length})`).join(', ')}`)
}
const shot = async (name) => { if (shots) await page.screenshot({ path: `${shots}/${name}.png` }) }

// 1. first visit: the welcome flow, role and theme, then Home
await page.goto(base)
await page.waitForURL('**/welcome**')
await page.getByRole('heading', { name: 'Welcome to SurgeSight' }).waitFor({ timeout: 15000 })
check(page.url().includes('/welcome'), `first visit did not open the welcome screens: ${page.url()}`)
await axeCheck('welcome')
await shot('welcome-1440')
await page.getByRole('button', { name: 'Continue' }).click()
await page.getByRole('radio', { name: /Health Department/ }).click()
await page.getByRole('button', { name: 'Continue' }).click()
await page.getByRole('radio', { name: 'Dark' }).click()
check(await page.evaluate(() => document.documentElement.classList.contains('dark')), 'dark theme not applied')
await page.getByRole('radio', { name: 'Light' }).click()
check(!(await page.evaluate(() => document.documentElement.classList.contains('dark'))), 'light theme not applied')
await page.getByRole('button', { name: 'Open SurgeSight' }).click()
await page.getByRole('heading', { name: 'What would you like to look at?' }).waitFor({ timeout: 10000 })
check(new URL(page.url()).pathname === '/', `welcome did not return to Home: ${page.url()}`)
check(await page.getByText('Set up for Health Department.').isVisible(), 'Home does not name the chosen role')
for (const name of ['Cyclone Fani', 'Cyclone Biparjoy', 'Cyclone Amphan']) {
  check((await page.getByText(name).count()) === 0, `${name} should be hidden on Home`)
}
check(await page.getByText(/not an official warning/).first().isVisible(), 'Home lacks the not-official notice')
await axeCheck('home')
await shot('home-1440')

// 2. language: Tamil renders, html lang follows, and it switches back
await page.getByRole('combobox', { name: 'Language' }).selectOption('ta')
await page.getByRole('heading', { name: 'எதைப் பார்க்க விரும்புகிறீர்கள்?' }).waitFor({ timeout: 5000 })
check((await page.evaluate(() => document.documentElement.lang)) === 'ta', 'html lang did not follow the language')
await shot('home-ta-1440')
await page.getByRole('combobox', { name: 'மொழி' }).selectOption('en')
await page.getByRole('heading', { name: 'What would you like to look at?' }).waitFor({ timeout: 5000 })

// 3. storm overview: status, role priorities, affected areas
await page.getByRole('main').getByRole('link', { name: /Cyclone Michaung/ }).click()
await page.waitForURL('**/storm/michaung_2023')
await page.getByRole('heading', { name: 'Your priorities' }).waitFor({ timeout: 15000 })
await page.getByText('Cyclonic Storm').first().waitFor({ timeout: 15000 })
await page.locator('#areas').waitFor()
await page.waitForFunction(() => document.querySelectorAll('[aria-labelledby="areas"] li').length >= 3, null, { timeout: 30000 })
check((await page.locator('[aria-labelledby="prio"] li').count()) >= 5, 'fewer than 5 priority facilities')
await page.getByRole('heading', { name: 'Insurance payout triggers' }).waitFor()
await page.waitForFunction(() => document.querySelectorAll('[aria-labelledby="param"] ul li').length >= 4, null, { timeout: 30000 })
await axeCheck('overview')
await shot('overview-1440')

// 4. the map: layers, boundary, impact view
await page.getByRole('navigation', { name: 'Storm sections' }).getByRole('link', { name: 'Map' }).click()
await page.waitForURL('**/storm/michaung_2023/map')
await page.waitForFunction(() => window.__overlay?._deck?.layerManager?.getLayers().some((l) => l.id === 'alert-zones'), null, { timeout: 30000 })
await page.waitForTimeout(2500)
const mapState = async () => {
  await page.waitForFunction(() => window.__overlay?._map?.getCenter(), null, { timeout: 10000 })
  return page.evaluate(() => { const m = window.__overlay._map; const c = m.getCenter(); return { zoom: m.getZoom(), lat: c.lat(), lng: c.lng(), gesture: m.get('gestureHandling'), rt: document.documentElement.dataset.renderingType } })
}
const layerIds = () => page.evaluate(() => window.__overlay._deck.layerManager.getLayers().map((l) => l.id))
const a = await mapState()
check(await page.getByRole('button', { name: 'Expand menu' }).isVisible(), 'the side rail should be collapsed on the map')
check(a.rt === 'vector-interleaved', `rendering type ${a.rt}`)
let ids = await layerIds()
for (const need of ['alert-zones', 'rain', 'track-observed', 'forecast-wind']) check(ids.includes(need), `layer ${need} missing`)
check(ids.includes('wind'), 'wind particles should be on by default')
check(!ids.some((i) => i.startsWith('assets-')), 'facilities should be hidden in the national view')
await page.getByRole('switch', { name: 'Wind' }).click()
await page.waitForTimeout(500)
check(!(await layerIds()).includes('wind'), 'wind switch did not remove the wind layer')
await page.getByRole('switch', { name: 'Wind' }).click()
await page.waitForTimeout(500)

check(a.gesture === 'greedy', `national gesture ${a.gesture}`)
const mx = 600, my = 420
await page.mouse.move(mx, my); await page.mouse.down(); await page.mouse.move(mx - 250, my - 150, { steps: 8 }); await page.mouse.up()
await page.waitForTimeout(400)
const b0 = await mapState()
check(Math.abs(b0.zoom - a.zoom) < 1e-3 && b0.lng >= 46 && b0.lng <= 118 && b0.lat >= -2 && b0.lat <= 40.5, `panned outside the boundary at frame zoom: ${JSON.stringify(a)} -> ${JSON.stringify(b0)}`)
for (let i = 0; i < 4; i++) { await page.mouse.move(mx, my); await page.mouse.wheel(0, -400); await page.waitForTimeout(150) }
await page.waitForTimeout(600)
check((await mapState()).zoom > a.zoom + 0.5, 'wheel did not zoom the national view')
for (let i = 0; i < 8; i++) { await page.mouse.wheel(0, 600); await page.waitForTimeout(100) }
await page.waitForTimeout(600)
check((await mapState()).zoom >= a.zoom - 1e-6, 'zoomed out past the national frame')

await page.getByRole('radio', { name: 'Impact area' }).click()
await page.waitForTimeout(2500)
const c = await mapState()
check(c.zoom > a.zoom + 2, `impact view zoom ${c.zoom}`)
check((await layerIds()).some((i) => i.startsWith('assets-icon-hospital')), 'hospital markers missing in the impact view')
check((await layerIds()).includes('surge'), 'surge layer missing in the impact view')
await shot('map-impact-1440')
await page.getByRole('radio', { name: 'India' }).click()
await page.waitForTimeout(2500)
check(Math.abs((await mapState()).zoom - a.zoom) < 1e-3, 'India view did not return to the national frame')

// 5. moving the cutoff re-issues the forecast, and the panel names the cycle issued at the cutoff
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
await page.evaluate(() => window.__clock.setState({ time: Date.UTC(2023, 11, 4, 6) }))
await page.waitForTimeout(700)
const panel = await page.getByRole('complementary', { name: 'Layers' }).innerText()
check(/GFS forecast issued 04 Dec 00Z/.test(panel), `layers panel: ${panel.replace(/\n/g, ' | ').slice(0, 200)}`)

// 6. frame rate over 5 s of 8x playback across the cutoff (wind on)
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
await axeCheck('map')
await page.evaluate(() => window.__clock.setState({ cutoff: Date.UTC(2023, 11, 3, 12), time: Date.UTC(2023, 11, 3, 12), playing: false }))
await page.waitForTimeout(800)
await shot('map-1440')

// 7. facilities: search, the Why panel with numbers and words, and Show on map
await page.getByRole('navigation', { name: 'Storm sections' }).getByRole('link', { name: 'Facilities' }).click()
await page.getByRole('button', { name: 'Why?' }).first().waitFor({ timeout: 15000 })
await page.getByRole('textbox', { name: 'Search by name' }).fill('government')
await page.waitForTimeout(400)
const firstName = await page.locator('li button span.block.truncate').first().innerText()
check(/government/i.test(firstName), `search did not filter: ${firstName}`)
await page.getByRole('button', { name: 'Why?' }).first().click()
await page.getByRole('button', { name: /Why is this (not )?critical\?/ }).click()
await page.getByText('The numbers').waitFor({ timeout: 10000 })
for (const label of ['Elevation', 'Waterlogging', 'Closest approach']) await page.getByText(label).first().waitFor({ timeout: 5000 })
await page.getByText(/Standard wording|Written by Gemini/).waitFor({ timeout: 20000 })
await axeCheck('facility details')
await shot('why-1440')
await page.getByRole('button', { name: 'Show on map' }).click()
await page.waitForURL('**/storm/michaung_2023/map')
await page.getByRole('complementary', { name: 'Why this ranking' }).waitFor({ timeout: 10000 })

// 8. affected areas, guide and settings
await page.getByRole('navigation', { name: 'Storm sections' }).getByRole('link', { name: 'Affected areas' }).click()
await page.waitForFunction(() => document.querySelectorAll('tbody tr th').length >= 5, null, { timeout: 30000 })
await axeCheck('areas')
await shot('areas-1440')

// 8a. roads: page, layer switch and a picked road's details
await page.getByRole('navigation', { name: 'Storm sections' }).getByRole('link', { name: 'Roads' }).click()
await page.waitForURL('**/storm/michaung_2023/roads')
await page.getByRole('heading', { name: 'Road exposure' }).waitFor({ timeout: 15000 })
await page.getByRole('region', { name: 'Road kilometres by screening level' }).waitFor({ timeout: 15000 })
await axeCheck('roads')
await page.getByRole('button', { name: 'Show on map' }).first().click()
await page.waitForURL('**/storm/michaung_2023/map')
await page.getByRole('complementary', { name: 'Road details' }).waitFor({ timeout: 15000 })
await page.getByRole('button', { name: 'Close details' }).click()
await page.getByRole('switch', { name: 'Road exposure' }).click()
await page.waitForTimeout(400)
check(!(await layerIds()).includes('roads'), 'roads switch did not remove the roads layer')
await page.getByRole('switch', { name: 'Road exposure' }).click()
await page.waitForFunction(() => window.__overlay._deck.layerManager.getLayers().some((l) => l.id === 'roads'), null, { timeout: 10000 })
await page.evaluate(() => window.__overlay._deck.layerManager.getLayers().find((l) => l.id === 'roads').props.onClick({ index: 0 }))
await page.getByRole('complementary', { name: 'Road details' }).waitFor({ timeout: 5000 })
await axeCheck('road details')

await page.getByRole('navigation', { name: 'Storm sections' }).getByRole('link', { name: 'Advisories' }).click()
await page.getByRole('heading', { name: 'How warnings go out' }).waitFor({ timeout: 10000 })
await page.getByText(/Priority actions|could not be drafted/).first().waitFor({ timeout: 90000 })

// dispatch flow
const recipInput = page.getByPlaceholder('Add email...')
await recipInput.fill('e2e-test@example.com')
await page.getByRole('button', { name: 'Add' }).click()
await page.getByText('e2e-test@example.com').waitFor({ timeout: 5000 })

await page.getByRole('button', { name: 'Send alert' }).first().click()
await page.getByRole('dialog').getByRole('button', { name: 'Send alert' }).click()
await page.getByText('Waiting for approval').first().waitFor({ timeout: 10000 })

await page.getByRole('button', { name: 'Approve' }).first().click()
await page.getByText('Approved').first().waitFor({ timeout: 10000 })

await page.getByRole('button', { name: /^Send$/ }).first().click()
await page.getByText(/Prepared \(dry run\)|Blocked/).first().waitFor({ timeout: 10000 })

await page.getByRole('button', { name: 'Remove' }).first().click()
await page.waitForFunction(() => !document.body.innerText.includes('e2e-test@example.com'), null, { timeout: 5000 })

await axeCheck('advisories')
await shot('advisories-1440')
await page.getByRole('link', { name: 'Guide' }).click()
check(await page.getByRole('button', { name: 'Collapse menu' }).isVisible(), 'the side rail should be open on reading pages')
await page.getByRole('heading', { name: 'Who should use what' }).waitFor()
await axeCheck('guide')
await page.getByRole('link', { name: 'Settings' }).click()
await page.getByRole('heading', { name: 'Your role' }).waitFor()
await page.getByRole('button', { name: 'Switch between light and dark' }).click()
check(await page.evaluate(() => document.documentElement.classList.contains('dark')), 'header theme button did not switch to dark')
await page.waitForTimeout(600)
await axeCheck('settings (dark)')
await shot('settings-dark-1440')
await page.getByRole('button', { name: 'Switch between light and dark' }).click()

// 9. phone: the map with its layers sheet
await page.setViewportSize({ width: 390, height: 844 })
await page.goto(`${base}/storm/michaung_2023/map`)
await page.waitForFunction(() => window.__overlay?._deck?.layerManager?.getLayers().some((l) => l.id === 'alert-zones'), null, { timeout: 30000 })
await page.getByRole('button', { name: 'Layers' }).click()
await page.getByRole('switch', { name: 'Alert zones' }).waitFor({ timeout: 5000 })
await shot('phone-layers-390')
await page.keyboard.press('Escape')
await page.getByRole('button', { name: 'Open menu' }).click()
await page.getByRole('dialog').getByRole('link', { name: 'Guide' }).waitFor({ timeout: 5000 })
await page.keyboard.press('Escape')
await page.setViewportSize({ width: 1440, height: 860 })

// 10. failure modes: the catalog down on Home, and a failing explanation
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 860 } })
  await ctx.addInitScript((v) => localStorage.setItem('surgesight.prefs', v), ONBOARDED)
  const bad = await ctx.newPage()
  await bad.route('**/api/catalog', (r) => r.abort())
  await bad.goto(base)
  await bad.getByRole('alert').filter({ hasText: /could not be loaded/ }).waitFor({ timeout: 10000 })
  await bad.unroute('**/api/catalog')
  await bad.getByRole('button', { name: 'Try again' }).click()
  await bad.getByRole('main').getByRole('link', { name: /Cyclone Michaung/ }).waitFor({ timeout: 10000 })
  await ctx.close()

  await page.route('**/explain**', (r) => r.fulfill({ status: 500, body: 'boom' }))
  await page.goto(`${base}/storm/michaung_2023/facilities`)
  await page.getByRole('button', { name: 'Why?' }).first().click({ timeout: 30000 })
  await page.getByRole('button', { name: /Why is this (not )?critical\?/ }).click()
  await page.getByRole('alert').filter({ hasText: /numbers could not be loaded/ }).waitFor({ timeout: 10000 })
  await page.unroute('**/explain**')
  errors.splice(0, errors.length, ...errors.filter((e) => !/status of 500/.test(e)))
}

// 11. live weather (only when data/processed/live has been built)
const catalog = await (await fetch(`${base}/api/catalog`)).json()
let liveInfo = null
if (catalog.tiles.find((t) => t.id === 'live')?.status === 'available') {
  await page.goto(`${base}/live`)
  await page.waitForFunction(() => window.__overlay?._deck?.layerManager?.getLayers().some((l) => l.id === 'cloud'), null, { timeout: 30000 })
  await page.waitForTimeout(1500)
  const liveIds = await layerIds()
  for (const need of ['cloud', 'rain', 'wind', 'alert-zones']) check(liveIds.includes(need), `live layer ${need} missing`)
  check(!liveIds.some((i) => i.startsWith('track-') || i.startsWith('assets-')), 'live view must not draw storm or facility layers')
  const banner = await page.getByRole('status').filter({ hasText: /GFS model run|old/ }).first().innerText()
  await page.getByRole('radio', { name: 'Temp' }).click()
  await page.waitForTimeout(800)
  check((await layerIds()).includes('temperature') && !(await layerIds()).includes('cloud'), 'temperature layer did not replace cloud')
  await page.mouse.move(600, 450)
  await page.waitForTimeout(400)
  check(/°C/.test(await page.locator('body').innerText()), 'live cursor readout lacks temperature')
  await axeCheck('live')
  await shot('live-1440')
  liveInfo = banner.slice(0, 80)
}

check(errors.length === 0, `console errors: ${errors.slice(0, 3).join(' || ')}`)
console.log(JSON.stringify({ ok: failures.length === 0, failures, fps, forecastMs, live: liveInfo, zoom: { india: +a.zoom.toFixed(2), impact: +c.zoom.toFixed(2) } }))
await browser.close()
process.exit(failures.length ? 1 : 0)
