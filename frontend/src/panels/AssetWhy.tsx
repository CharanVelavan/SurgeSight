import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Loader2, X } from 'lucide-react'
import { useStore } from 'zustand'
import { ASSET_TYPES, assetsStore, type AssetType } from '@/data/assets'
import { api, type AssetFacts } from '@/lib/api'
import { RISK, type RiskClass } from '@/lib/colors'
import { formatIST } from '@/lib/format'
import { useUi } from '@/state/ui'
import { cutoffParam } from '@/app/queries'
import { clock } from '@/timeline/clock'

const isCritical = (cls: string) => cls === 'CRITICAL' || cls === 'HIGH'
const fmt = (v: number | null | undefined, unit: string) => (v === null || v === undefined ? 'not available' : `${v} ${unit}`)

function Row({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-white/5 py-1.5 text-[12px] last:border-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="num text-right">
        {value}
        {note && <span className="block text-[10px] font-sans text-muted-foreground">{note}</span>}
      </dd>
    </div>
  )
}

function FactTable({ f, askedAt }: { f: AssetFacts; askedAt: number }) {
  const d = f.distance
  return (
    <dl>
      <Row label="Elevation" value={fmt(f.elevation_m, 'm above sea level')} />
      <Row label="Waterlogging" value={f.waterlogging.level} note={`${fmt(f.waterlogging.rain_forecast_mm, 'mm')} forecast rain, terrain score ${f.waterlogging.terrain_flood_score ?? '—'}`} />
      <Row label="Peak wind" value={fmt(f.wind_peak_kmh, 'km/h')} />
      <Row label="Storm surge" value={fmt(f.surge_m, 'm')} />
      <Row label="Closest approach" value={`${d.closest_approach_km} km`} note={`at ${d.closest_approach_time_utc.replace('T', ' ').replace('Z', ' UTC')}`} />
      <Row label={`Distance at ${formatIST(askedAt)}`} value={d.distance_at_time_km === null ? 'not shown' : `${d.distance_at_time_km} km`} note={d.distance_at_time_note} />
      <Row
        label="What drives the score"
        value={Object.entries(f.hazard_contributions).map(([k, v]) => `${k} ${v}`).join(' · ')}
        note="wind, surge and rain flooding, weighted"
      />
    </dl>
  )
}

/** Opens when a marker is clicked. The button fetches the facts behind the ranking, then a short text written from them. */
export function AssetWhy() {
  const i = useUi(s => s.selectedAsset)
  const set = useUi(s => s.set)
  const data = useStore(assetsStore, s => s.data)
  const [asked, setAsked] = useState<{ time: number; cutoff: number } | null>(null)
  useEffect(() => setAsked(null), [i])
  const key = data && i !== null ? [data.osmElement[i], data.osmId[i]] : null
  const args = asked && key ? { time: cutoffParam(asked.time), cutoff: cutoffParam(asked.cutoff) } : null
  const facts = useQuery({
    queryKey: ['why', key, args, false],
    queryFn: () => api.explain(String(key![0]), Number(key![1]), args!.time, args!.cutoff, false),
    enabled: !!args && !!key,
    staleTime: Infinity,
    retry: 0,
  })
  const text = useQuery({
    queryKey: ['why', key, args, true],
    queryFn: () => api.explain(String(key![0]), Number(key![1]), args!.time, args!.cutoff, true),
    enabled: !!args && !!key && facts.isSuccess,
    staleTime: Infinity,
    retry: 0,
  })
  if (i === null || !data) return null
  const cls = (data.riskClass[i] in RISK ? data.riskClass[i] : 'LOW') as RiskClass
  const type = ASSET_TYPES[data.type[i] as AssetType]?.label.replace(/s$/, '') ?? data.type[i]
  const critical = isCritical(cls)
  return (
    <section aria-label="Why this ranking" className="panel pointer-events-auto absolute top-28 right-3 z-20 flex max-h-[calc(100dvh-14rem)] w-80 flex-col overflow-y-auto p-3 max-md:fixed max-md:inset-x-3 max-md:top-auto max-md:bottom-3 max-md:max-h-[65dvh] max-md:w-auto">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-[13px] font-medium">{data.name[i] || 'Unnamed'}</div>
          <div className="text-[11px] text-muted-foreground">{type}</div>
        </div>
        <button type="button" onClick={() => set({ selectedAsset: null })} aria-label="Close details" className="grid size-8 shrink-0 place-items-center rounded-lg text-muted-foreground hover:bg-accent">
          <X className="size-4" />
        </button>
      </div>
      <div className="mt-1.5 flex items-center gap-1.5 text-[12px]">
        <span style={{ color: RISK[cls].color }} aria-hidden>{RISK[cls].symbol}</span>
        {RISK[cls].label} risk
        <span className="num ml-auto text-muted-foreground">{data.riskScore[i].toFixed(2)}</span>
      </div>

      {!asked && (
        <button
          type="button"
          onClick={() => setAsked({ time: clock.getState().time, cutoff: clock.getState().cutoff })}
          className="mt-3 rounded-lg bg-primary/15 px-3 py-2 text-[13px] font-medium text-primary hover:bg-primary/25"
        >
          {critical ? 'Why is this critical?' : 'Why is this not critical?'}
        </button>
      )}

      {asked && (
        <div className="mt-3">
          {facts.isPending && <div className="flex items-center gap-2 text-[12px] text-muted-foreground"><Loader2 className="size-4 animate-spin" aria-hidden />Working out the numbers…</div>}
          {facts.isError && <div role="alert" className="text-[12px] text-[#E0B34A]">The numbers could not be loaded. Check the connection and try again.</div>}
          {facts.data && (
            <>
              <div className="mb-1 text-[10px] font-medium tracking-[0.14em] text-muted-foreground uppercase">The numbers</div>
              <FactTable f={facts.data.facts} askedAt={asked.time} />
              <div className="mt-3 mb-1 text-[10px] font-medium tracking-[0.14em] text-muted-foreground uppercase">In words</div>
              {text.isPending && <div className="flex items-center gap-2 text-[12px] text-muted-foreground"><Loader2 className="size-4 animate-spin" aria-hidden />Writing a short explanation…</div>}
              {text.isError && <div className="text-[12px] text-muted-foreground">The written summary is unavailable. The numbers above are complete.</div>}
              {text.data?.text && (
                <div className="text-[12px] leading-relaxed">
                  <p>{text.data.text.summary}</p>
                  {text.data.text.reasons.length > 0 && (
                    <ul className="mt-1.5 list-disc pl-4 text-muted-foreground">
                      {text.data.text.reasons.map((r, n) => <li key={n}>{r}</li>)}
                    </ul>
                  )}
                  <p className="mt-2 text-[10px] text-muted-foreground">
                    {text.data.text_source === 'gemini' ? 'Written by Gemini from these numbers only; numbers checked against the table.' : 'Standard wording over the numbers above.'}
                  </p>
                </div>
              )}
              <p className="mt-2 text-[10px] leading-snug text-muted-foreground">{facts.data.facts.disclaimer}</p>
            </>
          )}
        </div>
      )}
    </section>
  )
}
