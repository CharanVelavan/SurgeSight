// Weak-network check on the production build: visit online, go offline, and the saved app and data still show.
// node e2e/offline.mjs <previewUrl>
import { chromium } from 'playwright'

const base = process.argv[2]
const failures = []
const check = (ok, msg) => { if (!ok) failures.push(msg) }

const browser = await chromium.launch({ channel: 'chrome', headless: false, args: ['--ignore-gpu-blocklist'] })
const context = await browser.newContext({ viewport: { width: 1440, height: 860 } })
const page = await context.newPage()
await page.addInitScript(() => sessionStorage.setItem('surgesight.intro', '1'))

// online: register the worker, then fill the saved copies by opening the landing page and a storm
await page.goto(base)
await page.getByRole('link', { name: /Cyclone Michaung/ }).waitFor({ timeout: 15000 })
await page.evaluate(() => navigator.serviceWorker.ready)
await page.reload()
await page.waitForFunction(() => !!navigator.serviceWorker.controller, null, { timeout: 10000 })
await page.getByRole('link', { name: /Cyclone Michaung/ }).click()
await page.waitForFunction(() => window.location.pathname.startsWith('/storm/'))
await page.getByText('AT RISK', { exact: false }).first().waitFor({ timeout: 30000 })
await page.waitForTimeout(6000)

// offline: the landing page and the at-risk list come from the saved copies
await context.setOffline(true)
await page.goto(`${base}/`)
await page.getByRole('link', { name: /Cyclone Michaung/ }).waitFor({ timeout: 15000 })
check(await page.getByRole('status').filter({ hasText: /offline|Weak connection/ }).first().isVisible(), 'landing page shows no saved-data notice offline')
await page.getByRole('link', { name: /Cyclone Michaung/ }).click()
await page.getByText('AT RISK', { exact: false }).first().waitFor({ timeout: 20000 })
check(await page.getByRole('status').filter({ hasText: /offline|Weak connection|could not load/ }).first().isVisible(), 'storm page shows no saved-data notice offline')

await context.setOffline(false)
console.log(JSON.stringify({ ok: failures.length === 0, failures }))
await browser.close()
process.exit(failures.length ? 1 : 0)
