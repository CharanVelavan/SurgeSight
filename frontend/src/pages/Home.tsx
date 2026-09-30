import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, ArrowRight, BookOpen, CloudSun, History, MapPin, CalendarDays } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { AppShell, Page } from '@/components/shell/AppShell'
import { useCatalog } from '@/app/queries'
import { Link, pathFor } from '@/app/router'
import { usePrefs } from '@/app/prefs'
import { roleById } from '@/data/roles'
import { currentLocale, useT, type Key } from '@/i18n'
import type { CatalogTile } from '@/lib/api'
import { formatCycle } from '@/lib/format'
import type { Manifest } from '@/weather/manifest'

const monthYear = (iso: string) => new Intl.DateTimeFormat(`${currentLocale()}-u-nu-latn`, { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(Date.parse(`${iso}-01T00:00:00Z`))

function LiveCard({ tile }: { tile: CatalogTile }) {
  const t = useT()
  const ready = tile.status === 'available'
  const { data: live } = useQuery({
    queryKey: ['live-manifest-head'],
    queryFn: async () => ((await (await fetch('/api/live/manifest')).json()) as Manifest).live ?? null,
    enabled: ready,
    staleTime: 60_000,
  })
  const body = (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
      <span className="grid size-12 shrink-0 place-items-center rounded-lg bg-accent text-primary">
        <CloudSun className="size-6" aria-hidden />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-[16px] font-semibold">{t('tile.live.name')}</h3>
          {ready ? <Badge className="bg-ok/15 text-ok">{t('header.live')}</Badge> : <Badge variant="secondary">{t('tile.soon')}</Badge>}
        </div>
        <p className="mt-1 text-[14px] text-muted-foreground">{t('tile.live.blurb')}</p>
        {live && (
          <p className={`mt-2 flex items-center gap-1.5 text-[12.5px] ${live.stale ? 'text-warn' : 'text-muted-foreground'}`}>
            {live.stale && <AlertTriangle className="size-3.5" aria-hidden />}
            {t('home.liveRun', { cycle: formatCycle(Date.parse(live.cycle)), age: Math.round(live.age_hours) })}
          </p>
        )}
      </div>
      {ready && (
        <span className="flex items-center gap-1 text-[13px] font-medium text-primary">
          {t('home.open')} <ArrowRight className="size-4" aria-hidden />
        </span>
      )}
    </div>
  )
  const cls = 'block rounded-xl border border-border bg-card p-5 transition-colors'
  return ready ? (
    <Link to="/live" className={`${cls} hover:border-primary/50 hover:bg-accent/40`}>{body}</Link>
  ) : (
    <div className={`${cls} opacity-70`}>{body}</div>
  )
}

function StormCard({ tile }: { tile: CatalogTile }) {
  const t = useT()
  const ready = tile.status === 'available'
  const inner = (
    <>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-[16px] font-semibold">{t(`tile.${tile.id}.name` as Key)}</h3>
          {tile.category && <p className="mt-0.5 text-[12.5px] text-muted-foreground">{t(`imd.${tile.category}` as Key)}</p>}
        </div>
        {ready ? <Badge variant="secondary">{t('tile.replay')}</Badge> : <Badge variant="outline" className="text-muted-foreground">{t('tile.soon')}</Badge>}
      </div>
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
      <p className="mt-3 flex-1 text-[13px] leading-relaxed text-muted-foreground">{t(`tile.${tile.id}.blurb` as Key)}</p>
      <div className="mt-4 border-t border-border pt-3 text-[13px] font-medium">
        {ready ? (
          <span className="flex items-center gap-1 text-primary">
            {t('home.openReplay')} <ArrowRight className="size-4" aria-hidden />
          </span>
        ) : (
          <span className="text-muted-foreground">{t('home.soonNote')}</span>
        )}
      </div>
    </>
  )
  const cls = 'flex flex-col rounded-xl border border-border bg-card p-5 transition-colors'
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
  const storms = [...(data?.tiles.filter(x => x.kind === 'storm') ?? [])].sort((a, b) => Number(b.status === 'available') - Number(a.status === 'available'))
  return (
    <AppShell title={t('nav.home')}>
      <Page>
        <h2 className="text-[24px] font-semibold tracking-tight">{t('home.title')}</h2>
        <p className="mt-1.5 flex items-center gap-2 text-[14px] text-muted-foreground">
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
          {isPending ? <Skeleton className="h-28 rounded-xl" /> : live.map(tile => <LiveCard key={tile.id} tile={tile} />)}
        </section>

        <section aria-labelledby="past" className="mt-10">
          <h3 id="past" className="eyebrow mb-3 flex items-center gap-2"><History className="size-3.5" aria-hidden />{t('landing.past')}</h3>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {isPending ? [0, 1, 2, 3].map(i => <Skeleton key={i} className="h-60 rounded-xl" />) : storms.map(tile => <StormCard key={tile.id} tile={tile} />)}
          </div>
        </section>

        <section className="mt-10 flex flex-col gap-4 rounded-xl border border-border bg-card p-5 sm:flex-row sm:items-center">
          <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-accent text-primary"><BookOpen className="size-5" aria-hidden /></span>
          <div className="flex-1">
            <h3 className="text-[15px] font-semibold">{t('home.guideTitle')}</h3>
            <p className="mt-0.5 text-[13.5px] text-muted-foreground">{t('home.guideText')}</p>
          </div>
          <Button variant="outline" asChild><Link to="/guide">{t('home.guideCta')}</Link></Button>
        </section>

        <p className="mt-10 max-w-3xl text-[12.5px] leading-relaxed text-muted-foreground">{t('landing.notice')}</p>
      </Page>
    </AppShell>
  )
}
