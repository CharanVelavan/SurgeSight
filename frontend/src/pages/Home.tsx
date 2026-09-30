import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, ArrowRight, BookOpen, CloudSun, History, MapPin, CalendarDays, Wind } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { AppShell, Page } from '@/components/shell/AppShell'
import { useCatalog } from '@/app/queries'
import { Link, pathFor } from '@/app/router'
import { usePrefs } from '@/app/prefs'
import { roleById } from '@/data/roles'
import { currentLocale, useT, type Key } from '@/i18n'
import { api, type CatalogTile, type NowCity } from '@/lib/api'
import { formatCycle } from '@/lib/format'
import type { Manifest } from '@/weather/manifest'

const visibleStormIds = new Set(['michaung_2023'])

const monthYear = (iso: string) => new Intl.DateTimeFormat(`${currentLocale()}-u-nu-latn`, { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(Date.parse(`${iso}-01T00:00:00Z`))

function CityTile({ c }: { c: NowCity }) {
  const t = useT()
  return (
    <li className="rounded-lg border border-border bg-background/40 p-3">
      <p className="text-[12.5px] font-medium text-muted-foreground">{c.city}</p>
      <p className="mt-1 text-[24px] font-semibold leading-none tracking-tight tabular-nums">
        {c.temperature_c != null ? `${Math.round(c.temperature_c)}°` : '–'}
      </p>
      <p className="mt-1.5 truncate text-[12.5px]">{c.condition ?? ''}</p>
      {c.wind_kmh != null && (
        <p className="mt-1 flex items-center gap-1 text-[12px] text-muted-foreground">
          <Wind className="size-3.5" aria-hidden />
          {t('home.wind', { n: Math.round(c.wind_kmh) })}
        </p>
      )}
    </li>
  )
}

function LiveCard({ tile }: { tile: CatalogTile }) {
  const t = useT()
  const ready = tile.status === 'available'
  const { data: live } = useQuery({
    queryKey: ['live-manifest-head'],
    queryFn: async () => ((await (await fetch('/api/live/manifest')).json()) as Manifest).live ?? null,
    enabled: ready,
    staleTime: 60_000,
  })
  const now = useQuery({ queryKey: ['live-now'], queryFn: api.liveNow, staleTime: 5 * 60_000, refetchInterval: 10 * 60_000, retry: 1 })
  return (
    <div className="rounded-xl border border-border bg-card">
      <div className="flex flex-col gap-4 p-5 sm:flex-row sm:items-start">
        <span className="grid size-12 shrink-0 place-items-center rounded-lg bg-accent text-primary">
          <CloudSun className="size-6" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[16px] font-semibold">{t('tile.live.name')}</h3>
            {ready ? <Badge className="bg-ok/15 text-ok">{t('header.live')}</Badge> : <Badge variant="secondary">{t('tile.soon')}</Badge>}
          </div>
          <p className="mt-1 text-[14px] text-muted-foreground">{t('tile.live.blurb')}</p>
        </div>
        {ready && (
          <Button asChild className="shrink-0">
            <Link to="/live">{t('home.openMap')} <ArrowRight className="size-4" aria-hidden /></Link>
          </Button>
        )}
      </div>

      <div className="border-t border-border p-5">
        <h4 className="mb-3 text-[13px] font-medium text-muted-foreground">{t('home.nowTitle')}</h4>
        {now.isPending ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-24 rounded-lg" />)}
          </div>
        ) : now.data ? (
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {now.data.cities.map(c => <CityTile key={c.city} c={c} />)}
          </ul>
        ) : (
          <p className="text-[13.5px] text-muted-foreground">{t('home.nowError')}</p>
        )}
        <p className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-muted-foreground">
          <span>{t('home.nowSource')}</span>
          {live && (
            <span className={`flex items-center gap-1.5 ${live.stale ? 'text-warn' : ''}`}>
              {live.stale && <AlertTriangle className="size-3.5" aria-hidden />}
              {t('home.liveRun', { cycle: formatCycle(Date.parse(live.cycle)), age: Math.round(live.age_hours) })}
            </span>
          )}
        </p>
        {live && <p className="mt-2 max-w-3xl text-[12px] leading-relaxed text-muted-foreground">{t('home.runNote')}</p>}
      </div>
    </div>
  )
}

function StormCard({ tile }: { tile: CatalogTile }) {
  const t = useT()
  const ready = tile.status === 'available'
  const inner = (
    <div className="grid gap-5 md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] md:gap-8">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-[18px] font-semibold">{t(`tile.${tile.id}.name` as Key)}</h3>
          {ready ? <Badge variant="secondary">{t('tile.replay')}</Badge> : <Badge variant="outline" className="text-muted-foreground">{t('tile.soon')}</Badge>}
        </div>
        {tile.category && <p className="mt-0.5 text-[13px] text-muted-foreground">{t(`imd.${tile.category}` as Key)}</p>}
        <dl className="mt-4 flex flex-col gap-1.5 text-[13px]">
          {tile.states && (
            <div className="flex items-center gap-2 text-muted-foreground">
              <MapPin className="size-3.5 shrink-0" aria-hidden />
              <dt className="sr-only">{t('home.where')}</dt>
              <dd className="text-foreground">{tile.states}</dd>
            </div>
          )}
          {tile.month && (
            <div className="flex items-center gap-2 text-muted-foreground">
              <CalendarDays className="size-3.5 shrink-0" aria-hidden />
              <dt className="sr-only">{t('home.when')}</dt>
              <dd className="text-foreground">{monthYear(tile.month)}</dd>
            </div>
          )}
        </dl>
      </div>
      <div className="flex flex-col justify-between gap-4">
        <p className="text-[14px] leading-relaxed text-muted-foreground">{t(`tile.${tile.id}.blurb` as Key)}</p>
        <div className="text-[13.5px] font-medium">
          {ready ? (
            <span className="flex items-center gap-1 text-primary">
              {t('home.openReplay')} <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" aria-hidden />
            </span>
          ) : (
            <span className="text-muted-foreground">{t('home.soonNote')}</span>
          )}
        </div>
      </div>
    </div>
  )
  const cls = 'group block rounded-xl border border-border bg-card p-5 transition-colors sm:p-6'
  return ready ? (
    <Link to={pathFor({ name: 'storm', id: tile.id, tab: 'overview' })} className={`${cls} hover:border-primary/50 hover:bg-accent/40`}>
      {inner}
    </Link>
  ) : (
    <div className={cls} aria-disabled="true">
      {inner}
    </div>
  )
}

export function Home() {
  const t = useT()
  const role = roleById(usePrefs(s => s.role))
  const { data, isError, isPending, refetch } = useCatalog()
  const live = data?.tiles.filter(x => x.kind === 'live') ?? []
  const storms = data?.tiles.filter(x => x.kind === 'storm' && visibleStormIds.has(x.id)) ?? []
  return (
    <AppShell title={t('nav.home')}>
      <Page>
        <h2 className="text-[24px] font-semibold tracking-tight">{t('home.title')}</h2>
        <p className="mt-2 inline-flex flex-wrap items-center gap-2 rounded-full border border-border bg-card py-1 pl-3 pr-3.5 text-[13px] text-muted-foreground">
          <role.icon className="size-4 text-primary" aria-hidden />
          {t('home.lead', { role: t(`role.${role.id}.name` as Key) })}
          <Link to="/settings#role" className="font-medium text-primary hover:underline">{t('nav.change')}</Link>
        </p>

        {isError && (
          <div role="alert" className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-warn/30 bg-warn-bg p-4 text-[14px] text-warn">
            {t('landing.loadError')}
            <Button variant="outline" size="sm" onClick={() => refetch()}>{t('landing.retry')}</Button>
          </div>
        )}

        <section aria-labelledby="now" className="mt-8">
          <h3 id="now" className="eyebrow mb-3">{t('landing.now')}</h3>
          {isPending ? <Skeleton className="h-64 rounded-xl" /> : live.map(tile => <LiveCard key={tile.id} tile={tile} />)}
        </section>

        <section aria-labelledby="past" className="mt-10">
          <h3 id="past" className="eyebrow flex items-center gap-2"><History className="size-3.5" aria-hidden />{t('landing.past')}</h3>
          <p className="mb-4 mt-2 max-w-3xl text-[14px] leading-relaxed text-muted-foreground">{t('landing.pastDescription')}</p>
          <div className="grid gap-4">
            {isPending ? <Skeleton className="h-44 rounded-xl" /> : storms.map(tile => <StormCard key={tile.id} tile={tile} />)}
          </div>
        </section>

        <section className="mt-8 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border pt-6">
          <BookOpen className="size-4 text-primary" aria-hidden />
          <p className="flex-1 text-[13.5px] text-muted-foreground"><span className="font-medium text-foreground">{t('home.guideTitle')}</span> {t('home.guideText')}</p>
          <Link to="/guide" className="flex items-center gap-1 text-[13.5px] font-medium text-primary hover:underline">{t('home.guideCta')} <ArrowRight className="size-4" aria-hidden /></Link>
        </section>

        <p className="mt-6 max-w-3xl text-[12.5px] leading-relaxed text-muted-foreground">{t('landing.notice')}</p>
      </Page>
    </AppShell>
  )
}
