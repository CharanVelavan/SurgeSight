// Measures frame times over N seconds of 8x playback across the cutoff. node e2e/fps.mjs [seconds] [impact]
import { chromium } from 'playwright'

const seconds = Number(process.argv[2] ?? 5)
const browser = await chromium.launch({ channel: 'chrome', headless: false, args: ['--ignore-gpu-blocklist'] })
const page = await browser.newPage({ viewport: { width: 1440, height: 860 } })
await page.addInitScript(() => sessionStorage.setItem('surgesight.intro', '1'))
await page.goto('http://localhost:5173/')
await page.waitForTimeout(6000)
if (process.argv.includes('impact')) {
  await page.getByRole('radio', { name: 'Impact area' }).click()
  await page.waitForTimeout(3000)
}
const r = await page.evaluate(async (secs) => {
  const c = window.__clock
  c.setState({ time: Date.UTC(2023, 11, 3, 6), speed: 8, playing: true })
  const dts = []
  let last = performance.now()
  const t0 = last
  await new Promise((res) => {
    const f = (now) => { dts.push(now - last); last = now; now - t0 < secs * 1000 ? requestAnimationFrame(f) : res() }
    requestAnimationFrame(f)
  })
  c.setState({ playing: false })
  dts.shift()
  dts.sort((a, b) => a - b)
  const mean = dts.reduce((a, b) => a + b, 0) / dts.length
  return { frames: dts.length, fps: +(1000 / mean).toFixed(1), p95ms: +dts[Math.floor(dts.length * 0.95)].toFixed(1), maxms: +dts.at(-1).toFixed(1), over25ms: dts.filter((d) => d > 25).length }
}, seconds)
console.log(JSON.stringify(r))
await browser.close()
