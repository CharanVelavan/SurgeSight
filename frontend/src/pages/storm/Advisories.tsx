import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Bot, CheckCircle2, FileCode2, FileSearch, Inbox, Loader2, Radar, RefreshCw, Send, Volume2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Page } from '@/components/shell/AppShell'
import { usePrefs, type RoleId } from '@/app/prefs'
import { ROLES, roleById } from '@/data/roles'
import { currentApiLanguage, useLang, useT, type Key } from '@/i18n'
import { api, type Advisory } from '@/lib/api'
import { formatIST } from '@/lib/format'

function List({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null
  return (
    <section className="mt-5">
      <h3 className="eyebrow mb-2">{title}</h3>
      <ul className="flex flex-col gap-2 text-[14px] leading-relaxed">
        {items.map((x, i) => (
          <li key={i} className="flex gap-2.5">
            <span className="num mt-0.5 grid size-5 shrink-0 place-items-center rounded-full bg-accent text-[11px] font-semibold text-primary">{i + 1}</span>
            {x}
          </li>
        ))}
      </ul>
    </section>
  )
}

function AdvisoryCard({ runId, adv }: { runId: string; adv: Advisory }) {
  const t = useT()
  const [audio, setAudio] = useState<string | null>(null)
  const [speaking, setSpeaking] = useState(false)
  const [speechError, setSpeechError] = useState(false)
  const lang = currentApiLanguage()
  useEffect(() => () => { if (audio) URL.revokeObjectURL(audio) }, [audio])
  const listen = async () => {
    setSpeaking(true)
    setSpeechError(false)
    try {
      setAudio(await api.speech(runId, lang))
    } catch {
      setSpeechError(true)
    } finally {
      setSpeaking(false)
    }
  }
  return (
    <article className="rounded-xl border border-border bg-card p-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-md bg-warn-bg px-2 py-0.5 text-[12px] font-semibold text-warn">{adv.severity}</span>
        <span className="text-[12.5px] text-muted-foreground">{adv.audience}</span>
      </div>
      {adv.headline && <h2 className="mt-3 text-[19px] leading-snug font-semibold tracking-tight">{adv.headline}</h2>}
      <p className="mt-2 text-[14px] leading-relaxed">{adv.situation_summary}</p>
      {adv.instruction && <p className="mt-3 rounded-lg bg-accent/60 p-3 text-[14px] leading-relaxed font-medium">{adv.instruction}</p>}
      <List title={t('adv.actions')} items={adv.priority_actions} />
      {adv.critical_assets.length > 0 && (
        <section className="mt-5">
          <h3 className="eyebrow mb-2">{t('adv.assets')}</h3>
          <ul className="flex flex-wrap gap-1.5 text-[12.5px]">
            {adv.critical_assets.slice(0, 12).map((a, i) => (
              <li key={i} className="rounded-md border border-border px-2 py-1">{a.name}</li>
            ))}
          </ul>
        </section>
      )}
      <List title={t('adv.monitor')} items={adv.monitoring_priorities} />
      <div className="mt-6 flex flex-wrap items-center gap-2 border-t border-border pt-4">
        {lang !== 'Odia' && (
          <Button variant="outline" onClick={listen} disabled={speaking}>
            {speaking ? <Loader2 className="size-4 animate-spin" /> : <Volume2 className="size-4" />} {t('adv.listen')}
          </Button>
        )}
        <Button variant="outline" asChild>
          <a href={api.capUrl(runId)} download={`surgesight-${runId}.cap.xml`}><FileCode2 className="size-4" /> {t('adv.cap')}</a>
        </Button>
        {audio && <audio controls autoPlay src={audio} className="h-9 max-w-full" aria-label={t('adv.listen')} />}
        {speechError && <span role="alert" className="text-[13px] text-warn">{t('adv.speechError')}</span>}
      </div>
      <p className="mt-4 text-[12px] leading-relaxed text-muted-foreground">{t('adv.grounded')} {adv.disclaimer}</p>
    </article>
  )
}

const PIPELINE: { icon: typeof Radar; key: Key }[] = [
  { icon: Radar, key: 'adv.p1' },
  { icon: FileSearch, key: 'adv.p2' },
  { icon: Bot, key: 'adv.p3' },
  { icon: Inbox, key: 'adv.p4' },
  { icon: Send, key: 'adv.p5' },
]

/** Advisories: Gemini drafts one per department from the ranked facts, with audio and a CAP alert; below, how warnings go out automatically and what is in the queue. */
export function Advisories() {
  const t = useT()
  const lang = useLang()
  const mine = usePrefs(s => s.role)
  const [roleId, setRoleId] = useState<RoleId>(mine)
  const role = roleById(roleId)
  const advisory = useQuery({
    queryKey: ['advisory', role.department, lang],
    queryFn: () => api.advisory(role.department, currentApiLanguage()),
    staleTime: 30 * 60_000,
    retry: 0,
  })
  const queue = useQuery({ queryKey: ['dispatches'], queryFn: api.dispatches, staleTime: 30_000, retry: 0 })
  return (
    <Page>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
        <div className="flex-1">
          <h2 className="text-[20px] font-semibold tracking-tight">{t('adv.title')}</h2>
          <p className="mt-1 max-w-2xl text-[13.5px] leading-relaxed text-muted-foreground">{t('adv.lead')}</p>
        </div>
        <Select value={roleId} onValueChange={v => setRoleId(v as RoleId)}>
          <SelectTrigger aria-label={t('adv.department')} className="h-10 sm:w-72"><SelectValue /></SelectTrigger>
          <SelectContent>
            {ROLES.map(r => <SelectItem key={r.id} value={r.id}>{t(`role.${r.id}.name` as Key)}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div>
          {advisory.isPending && (
            <div className="rounded-xl border border-border bg-card p-5" aria-busy="true">
              <p className="flex items-center gap-2 text-[13.5px] text-muted-foreground"><Loader2 className="size-4 animate-spin" aria-hidden />{t('adv.drafting')}</p>
              <Skeleton className="mt-4 h-6 w-3/4" />
              <Skeleton className="mt-3 h-16" />
              <Skeleton className="mt-3 h-24" />
            </div>
          )}
          {advisory.isError && (
            <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-warn/30 bg-warn-bg p-4 text-[14px] text-warn">
              {t('adv.error')}
              <Button variant="outline" size="sm" onClick={() => advisory.refetch()}><RefreshCw className="size-4" /> {t('landing.retry')}</Button>
            </div>
          )}
          {advisory.data && <AdvisoryCard runId={advisory.data.run_id} adv={advisory.data.advisory} />}
        </div>

        <aside className="flex flex-col gap-5">
          <section aria-labelledby="pipe" className="rounded-xl border border-border bg-card p-4">
            <h2 id="pipe" className="text-[15px] font-semibold">{t('adv.how')}</h2>
            <ol className="mt-3 flex flex-col gap-3">
              {PIPELINE.map(({ icon: Icon, key }) => (
                <li key={key} className="flex gap-3 text-[13px] leading-snug">
                  <span className="grid size-7 shrink-0 place-items-center rounded-md bg-accent text-primary"><Icon className="size-4" aria-hidden /></span>
                  {t(key)}
                </li>
              ))}
            </ol>
            <p className="mt-3 rounded-md bg-muted px-3 py-2 text-[12px] leading-snug text-muted-foreground">{t('adv.dryRun')}</p>
          </section>

          <section aria-labelledby="queue" className="rounded-xl border border-border bg-card">
            <h2 id="queue" className="border-b border-border p-4 text-[15px] font-semibold">{t('adv.queue')}</h2>
            {queue.isPending ? (
              <div className="space-y-2 p-4">{[0, 1].map(i => <Skeleton key={i} className="h-10" />)}</div>
            ) : !queue.data?.length ? (
              <p className="p-4 text-[13px] text-muted-foreground">{t('adv.queueEmpty')}</p>
            ) : (
              <ul className="divide-y divide-border">
                {queue.data.slice(0, 8).map(d => (
                  <li key={d.id} className="px-4 py-2.5 text-[13px]">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate font-medium">{d.department}</span>
                      <span className="flex shrink-0 items-center gap-1 text-[12px] text-muted-foreground">
                        {d.status === 'sent' && <CheckCircle2 className="size-3.5 text-ok" aria-hidden />}
                        {t(`adv.status.${d.status}` as Key)}
                      </span>
                    </div>
                    <div className="mt-0.5 text-[12px] text-muted-foreground">{d.channel} · {formatIST(Date.parse(d.created_at_utc))}</div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </aside>
      </div>
    </Page>
  )
}
