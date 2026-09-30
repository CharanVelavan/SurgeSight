import { useQuery } from '@tanstack/react-query'
import { CloudSun, History } from 'lucide-react'
import { api, type CatalogTile } from '@/lib/api'
import { useT, type Key } from '@/i18n'
import { LanguageMenu } from '@/panels/LanguageMenu'
import { SavedNotice } from '@/panels/SavedNotice'
import { onLinkClick, pathFor } from './router'

function Tile({ tile }: { tile: CatalogTile }) {
  const t = useT()
  const name = t(`tile.${tile.id}.name` as Key)
  const blurb = t(`tile.${tile.id}.blurb` as Key)
  const live = tile.kind === 'live'
  const ready = tile.status === 'available'
  const path = pathFor(live ? { name: 'live' } : { name: 'storm', id: tile.id })
  const Icon = live ? CloudSun : History
  const body = (
    <>
      <div className="flex items-center justify-between">
        <Icon className="size-5 text-primary" aria-hidden />
        <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium tracking-[0.12em] uppercase ${ready ? 'bg-primary/15 text-primary' : 'bg-white/5 text-muted-foreground'}`}>
          {!ready ? t('tile.soon') : live ? t('tile.live') : t('tile.replay')}
        </span>
      </div>
      <h2 className="mt-6 text-lg font-semibold tracking-tight">
        {name}
        {tile.year && <span className="num ml-2 text-sm font-normal text-muted-foreground">{tile.year}</span>}
      </h2>
      <p className="mt-1.5 text-[13px] leading-relaxed text-muted-foreground">{blurb}</p>
    </>
  )
  const cls = 'panel flex min-h-44 flex-col p-5 text-left transition-colors'
  return ready ? (
    <a href={path} onClick={e => onLinkClick(e, path)} className={`${cls} hover:bg-white/[0.06] focus-visible:outline-2 focus-visible:outline-primary`}>
      {body}
    </a>
  ) : (
    <div className={`${cls} opacity-60`} aria-disabled="true">
      {body}
    </div>
  )
}

export function Landing() {
  const t = useT()
  const { data, isError, refetch } = useQuery({ queryKey: ['catalog'], queryFn: api.catalog, staleTime: 60_000 })
  const live = data?.tiles.filter(t => t.kind === 'live') ?? []
  const storms = data?.tiles.filter(t => t.kind === 'storm') ?? []
  return (
    <main className="min-h-full overflow-y-auto bg-background px-4 pt-[max(2rem,env(safe-area-inset-top))] pb-10">
      <div className="mx-auto max-w-4xl">
        <div className="flex items-center gap-2">
          <svg viewBox="0 0 32 32" className="size-6" aria-hidden>
            <path d="M6 19c4-6 8-6 10-2s6 4 10-2" fill="none" stroke="var(--primary)" strokeWidth="2.5" strokeLinecap="round" />
            <path d="M6 24c4-4 8-4 10-1s6 3 10-1" fill="none" stroke="var(--primary)" strokeOpacity=".5" strokeWidth="2" strokeLinecap="round" />
          </svg>
          <span className="text-base font-semibold tracking-tight">SurgeSight</span>
          <LanguageMenu className="ml-auto" />
        </div>
        <SavedNotice className="mt-6 w-fit" />
        <h1 className="mt-10 text-3xl font-semibold tracking-tight max-sm:text-2xl">{t('landing.tagline')}</h1>
        <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-muted-foreground">
          {t('landing.intro')}
        </p>

        {isError && (
          <div role="alert" className="panel mt-8 flex items-center justify-between gap-4 p-4 text-sm text-[#E0B34A]">
            {t('landing.loadError')}
            <button type="button" onClick={() => refetch()} className="rounded-lg px-3 py-1.5 text-foreground ring-1 ring-white/15 hover:bg-white/5">
              {t('landing.retry')}
            </button>
          </div>
        )}

        {live.length > 0 && (
          <section aria-label={t('landing.now')} className="mt-10">
            <h2 className="mb-3 text-[10px] font-medium tracking-[0.14em] text-muted-foreground uppercase">{t('landing.now')}</h2>
            <div className="grid gap-4 sm:grid-cols-2">{live.map(t => <Tile key={t.id} tile={t} />)}</div>
          </section>
        )}
        {storms.length > 0 && (
          <section aria-label={t('landing.past')} className="mt-10">
            <h2 className="mb-3 text-[10px] font-medium tracking-[0.14em] text-muted-foreground uppercase">{t('landing.past')}</h2>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{storms.map(t => <Tile key={t.id} tile={t} />)}</div>
          </section>
        )}

        <p className="mt-12 max-w-2xl border-t border-white/10 pt-4 text-[12px] leading-relaxed text-muted-foreground">
          {t('landing.notice')}
        </p>
      </div>
    </main>
  )
}
