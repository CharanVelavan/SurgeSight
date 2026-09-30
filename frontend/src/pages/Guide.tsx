import { Clock, Database, Info, MapPinned, Route as RouteIcon, ShieldAlert } from 'lucide-react'
import { ZONE_HEX } from '@/alerts/field'
import { FacilityIcon } from '@/components/badges'
import { AppShell, Page } from '@/components/shell/AppShell'
import { usePrefs } from '@/app/prefs'
import { ASSET_ICON } from '@/data/assetIcon'
import { ROLES } from '@/data/roles'
import { useT, type Key } from '@/i18n'
import { cn } from '@/lib/utils'

function H2({ children, id }: { children: React.ReactNode; id: string }) {
  return <h2 id={id} className="scroll-mt-4 text-[18px] font-semibold tracking-tight">{children}</h2>
}

/** Who uses which screen, how to read the map, and where the numbers come from. */
export function Guide() {
  const t = useT()
  const mine = usePrefs(s => s.role)
  return (
    <AppShell title={t('nav.guide')}>
      <Page className="max-w-4xl">
        <p className="text-[15px] leading-relaxed text-muted-foreground">{t('guide.lead')}</p>

        <nav aria-label={t('guide.contents')} className="mt-5 flex flex-wrap gap-2 text-[13px]">
          {(['who', 'screens', 'read', 'sources', 'limits'] as const).map(s => (
            <a key={s} href={`#${s}`} className="rounded-full border border-border bg-card px-3 py-1 font-medium hover:border-primary/50">{t(`guide.${s}` as Key)}</a>
          ))}
        </nav>

        <section aria-labelledby="who" className="mt-10">
          <H2 id="who">{t('guide.who')}</H2>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {ROLES.map(r => (
              <article key={r.id} className={cn('rounded-xl border border-border bg-card p-4', r.id === mine && 'border-primary ring-1 ring-primary/30')}>
                <div className="flex items-center gap-3">
                  <span className="grid size-9 shrink-0 place-items-center rounded-md bg-accent text-primary"><r.icon className="size-[18px]" aria-hidden /></span>
                  <div className="min-w-0">
                    <h3 className="text-[14.5px] font-semibold">{t(`role.${r.id}.name` as Key)}</h3>
                    {r.id === mine && <p className="text-[12px] font-medium text-primary">{t('guide.you')}</p>}
                  </div>
                </div>
                <p className="mt-3 text-[13px] text-muted-foreground">{t(`role.${r.id}.focus` as Key)}</p>
                <dl className="mt-3 flex flex-col gap-2 text-[13px]">
                  <div>
                    <dt className="eyebrow">{t('guide.firstOpen')}</dt>
                    <dd className="mt-0.5">{t(r.id === 'collector' ? 'guide.start.collector' : 'guide.start.dept')}</dd>
                  </div>
                  <div>
                    <dt className="eyebrow">{t('guide.lookFor')}</dt>
                    <dd className="mt-0.5">{t(`role.${r.id}.q1` as Key)}</dd>
                  </div>
                  <div>
                    <dt className="eyebrow">{t('guide.facilities')}</dt>
                    <dd className="mt-1 flex flex-wrap gap-1.5">
                      {r.types.map(a => {
                        const Icon = ASSET_ICON[a]
                        return (
                          <span key={a} className="flex items-center gap-1 rounded-md bg-muted px-1.5 py-0.5 text-[12px]">
                            <Icon className="size-3" aria-hidden /> {t(`asset.${a}` as Key)}
                          </span>
                        )
                      })}
                    </dd>
                  </div>
                </dl>
              </article>
            ))}
          </div>
        </section>

        <section aria-labelledby="screens" className="mt-12">
          <H2 id="screens">{t('guide.screens')}</H2>
          <ol className="mt-4 flex flex-col gap-3">
            {(['home', 'overview', 'map', 'facilities', 'areas'] as const).map((s, i) => (
              <li key={s} className="flex gap-3 text-[14px] leading-relaxed">
                <span className="num grid size-6 shrink-0 place-items-center rounded-full bg-primary text-[12px] font-semibold text-primary-foreground">{i + 1}</span>
                {t(`guide.s.${s}` as Key)}
              </li>
            ))}
          </ol>
        </section>

        <section aria-labelledby="read" className="mt-12">
          <H2 id="read">{t('guide.read')}</H2>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <div className="rounded-xl border border-border bg-card p-4">
              <h3 className="flex items-center gap-2 text-[14px] font-semibold"><ShieldAlert className="size-4 text-primary" aria-hidden />{t('layers.zones')}</h3>
              <div className="mt-3 flex gap-3">
                {[1, 2, 3].map(l => <span key={l} className="h-6 flex-1 rounded border-2" style={{ borderColor: ZONE_HEX[l], background: `${ZONE_HEX[l]}40` }} aria-hidden />)}
              </div>
              <p className="mt-3 text-[13px] leading-relaxed text-muted-foreground">{t('guide.r.zones')}</p>
            </div>
            <div className="rounded-xl border border-border bg-card p-4">
              <h3 className="flex items-center gap-2 text-[14px] font-semibold"><RouteIcon className="size-4 text-primary" aria-hidden />{t('map.track')}</h3>
              <svg viewBox="0 0 200 28" className="mt-3 h-7 w-full" aria-hidden>
                <path d="M4 22 L90 14" stroke="var(--primary)" strokeWidth="3" fill="none" strokeLinecap="round" />
                <path d="M90 14 L196 6" stroke="#D99A1E" strokeWidth="3" fill="none" strokeDasharray="6 4" />
                <circle cx="150" cy="10" r="9" fill="#D99A1E" fillOpacity=".15" stroke="#D99A1E" />
              </svg>
              <p className="mt-3 text-[13px] leading-relaxed text-muted-foreground">{t('guide.r.track')}</p>
            </div>
            <div className="rounded-xl border border-border bg-card p-4">
              <h3 className="flex items-center gap-2 text-[14px] font-semibold"><MapPinned className="size-4 text-primary" aria-hidden />{t('tab.facilities')}</h3>
              <div className="mt-3 flex flex-wrap gap-2">
                {(Object.keys(ASSET_ICON) as (keyof typeof ASSET_ICON)[]).map((a, i) => (
                  <FacilityIcon key={a} type={a} cls={(['CRITICAL', 'HIGH', 'MODERATE', 'LOW'] as const)[i % 4]} size="sm" />
                ))}
              </div>
              <p className="mt-3 text-[13px] leading-relaxed text-muted-foreground">{t('guide.r.markers')}</p>
            </div>
            <div className="rounded-xl border border-border bg-card p-4">
              <h3 className="flex items-center gap-2 text-[14px] font-semibold"><Clock className="size-4 text-primary" aria-hidden />{t('timeline.aria')}</h3>
              <div className="relative mt-3 h-7" aria-hidden>
                <div className="absolute top-3 left-0 h-1.5 w-1/2 rounded-l-full bg-primary/60" />
                <div className="absolute top-3 left-1/2 h-1.5 w-1/2" style={{ background: 'repeating-linear-gradient(90deg, color-mix(in srgb, var(--primary) 55%, transparent) 0 6px, transparent 6px 10px)' }} />
                <div className="absolute top-0 left-1/2 h-7 w-px bg-foreground" />
              </div>
              <p className="mt-3 text-[13px] leading-relaxed text-muted-foreground">{t('guide.r.time')}</p>
            </div>
          </div>
        </section>

        <section aria-labelledby="sources" className="mt-12">
          <H2 id="sources">{t('guide.sources')}</H2>
          <ul className="mt-4 divide-y divide-border rounded-xl border border-border bg-card text-[13.5px]">
            {(['track', 'weather', 'rain', 'facilities', 'risk'] as const).map(k => (
              <li key={k} className="flex gap-3 p-3.5">
                <Database className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
                {t(`guide.src.${k}` as Key)}
              </li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="limits" className="mt-12 mb-4">
          <H2 id="limits">{t('guide.limits')}</H2>
          <div className="mt-4 flex gap-3 rounded-xl border border-warn/30 bg-warn-bg p-4 text-[14px] leading-relaxed">
            <Info className="mt-0.5 size-4 shrink-0 text-warn" aria-hidden />
            <div>
              <p>{t('landing.notice')}</p>
              <p className="mt-2 text-muted-foreground">{t('guide.limitsMore')}</p>
            </div>
          </div>
        </section>
      </Page>
    </AppShell>
  )
}
