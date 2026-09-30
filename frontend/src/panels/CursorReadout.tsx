import { formatLatLon, windFrom } from '@/lib/format'
import { useUi } from '@/state/ui'
import { useClock } from '@/timeline/clock'
import { sampleRain, sampleWind } from '@/weather/atlas'
import { rainField, windField } from '@/weather/field'
import { useWeather } from '@/weather/useWeather'

/** Wind and rain under the pointer for the frame on screen (bilinear sample of the CPU copy). */
export function CursorReadout() {
  const cursor = useUi(s => s.cursor)
  const { wind: showWind, rain: showRain, rainSource } = useUi()
  const manifest = useWeather(s => s.manifest)
  const loaded = useWeather(s => s.loaded)
  const { time, cutoff } = useClock(s => ({ time: s.time, cutoff: s.cutoff }), 100)
  if (!cursor || !manifest || !loaded) return null

  const wp = showWind ? windField(manifest, time, cutoff) : null
  const rp = showRain ? rainField(manifest, time, cutoff, rainSource) : null
  const w = wp && sampleWind(wp, manifest, cursor.lon, cursor.lat)
  const r = rp && sampleRain(rp, manifest, cursor.lon, cursor.lat)
  if (!w && r == null) return null
  const speed = w ? Math.hypot(w.u, w.v) : 0

  const left = Math.min(cursor.x + 16, innerWidth - 190)
  const top = Math.min(cursor.y + 16, innerHeight - 90)
  return (
    <div className="panel num pointer-events-none fixed z-30 px-2.5 py-1.5 text-[11px] leading-[18px]" style={{ left, top }}>
      <div className="text-muted-foreground">{formatLatLon(cursor.lat, cursor.lon)}</div>
      {w && (
        <div>
          <span className="text-foreground">{(speed * 3.6).toFixed(0)} km/h</span>
          <span className="text-muted-foreground"> {windFrom(w.u, w.v)} · {speed.toFixed(1)} m/s</span>
        </div>
      )}
      {r != null && (
        <div>
          <span className="text-foreground">{r < 0.1 ? '0' : r.toFixed(r < 10 ? 1 : 0)} mm/h</span>
          <span className="text-muted-foreground"> rain{rp?.kind === 'validation' ? ' · validation' : ''}</span>
        </div>
      )}
    </div>
  )
}
