// Screenshot helper for the running dev server: node e2e/snap.mjs <out.png> [actions...]
// actions: impact | cutoff=<ISO> | time=<ISO> | play=<ms> | validation | width=<px> | hover=<x,y>
import { chromium } from 'playwright'

const [out = 'snap.png', ...actions] = process.argv.slice(2)
const arg = (k) => actions.find((a) => a.startsWith(k + '='))?.split('=').slice(1).join('=')
const width = Number(arg('width') ?? 1440)
const browser = await chromium.launch({ channel: 'chrome', headless: false, args: ['--ignore-gpu-blocklist'] })
const page = await browser.newPage({ viewport: { width, height: width < 700 ? 844 : 860 }, deviceScaleFactor: 1 })
const logs = []
page.on('console', (m) => ['error'].includes(m.type()) && logs.push(m.text().slice(0, 300)))
page.on('pageerror', (e) => logs.push(`pageerror: ${e.message.slice(0, 300)}`))
await page.addInitScript(() => sessionStorage.setItem('surgesight.intro', '1'))
await page.goto('http://localhost:5173/?perf=1')
await page.waitForTimeout(6000)
if (actions.includes('impact')) {
  await page.getByRole('radio', { name: 'Impact area' }).click()
  await page.waitForTimeout(3000)
}
if (actions.includes('validation')) await page.getByRole('radio', { name: /Observed/ }).click()
const clockAt = (k, v) => page.evaluate(([key, iso]) => window.__clock.setState(key === 'cutoff' ? { cutoff: Date.parse(iso) } : { time: Date.parse(iso) }), [k, v])
if (arg('cutoff')) { await clockAt('cutoff', arg('cutoff')); await page.waitForTimeout(1500) }
if (arg('time')) { await clockAt('time', arg('time')); await page.waitForTimeout(1500) }
if (arg('hover')) { const [x, y] = arg('hover').split(',').map(Number); await page.mouse.move(x, y); await page.waitForTimeout(800) }
await page.waitForTimeout(1000)
console.log(await page.evaluate(() => JSON.stringify({ fps: +window.__surgesight.perf.fps.toFixed(0), layers: window.__overlay._deck.layerManager.getLayers().map((l) => l.id) })))
await page.screenshot({ path: out })
console.log(logs.join('\n') || 'no console errors')
await browser.close()
