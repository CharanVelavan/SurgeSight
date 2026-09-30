import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bot, CheckCircle2, FileCode2, FileSearch, Inbox, Loader2, Radar, RefreshCw, Send, Volume2, Users, AlertTriangle, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { Page } from '@/components/shell/AppShell'
import { usePrefs, type RoleId } from '@/app/prefs'
import { ROLES, roleById } from '@/data/roles'
import { currentApiLanguage, useLang, useT, type Key } from '@/i18n'
import { api, type Advisory, type DispatchItem } from '@/lib/api'
import { formatIST } from '@/lib/format'
import { useStore } from 'zustand'
import { assetsStore } from '@/data/assets'
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

function AdvisoryCard({ runId, adv, role }: { runId: string; adv: Advisory; role: any }) {
  const t = useT()
  const queryClient = useQueryClient()
  const [audio, setAudio] = useState<string | null>(null)
  const [speaking, setSpeaking] = useState(false)
  const [speechError, setSpeechError] = useState(false)
  const [dialogOpen, setDialogOpen] = useState(false)
  const lang = currentApiLanguage()
  
  const modeQuery = useQuery({ queryKey: ['dispatchMode'], queryFn: api.dispatchMode, staleTime: 300000 })
  const mode = modeQuery.data?.mode
  
  const dispatchMut = useMutation({
    mutationFn: () => api.queueDispatch(runId, 'email'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dispatches'] })
      setDialogOpen(false)
    }
  })

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
        <div className="flex flex-col gap-1 items-start">
          <Button variant="outline" asChild>
            <a href={api.capUrl(runId)} download={`surgesight-${runId}.cap.xml`}><FileCode2 className="size-4 mr-2" /> {t('adv.cap')}</a>
          </Button>
          <span className="text-[11px] text-muted-foreground">{t('adv.capDesc' as Key)}</span>
        </div>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button variant="default"><Send className="size-4 mr-2" /> {t('adv.sendAlert')}</Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>{t('adv.sendAlert')}</DialogTitle>
              <DialogDescription>
                {t('adv.confirmSend')} for {role.name}.
              </DialogDescription>
            </DialogHeader>
            <div className="py-4 space-y-4">
              <div className="rounded-md bg-accent p-3 text-[13px]">
                <strong>{adv.headline}</strong>
                <p className="mt-1 line-clamp-2 text-muted-foreground">{adv.situation_summary}</p>
              </div>
              <div className="flex items-center gap-2">
                <Badge variant={mode === 'live' ? 'destructive' : 'secondary'}>
                  {mode === 'live' ? t('adv.mode.live') : t('adv.mode.dryRun')}
                </Badge>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
              <Button onClick={() => dispatchMut.mutate()} disabled={dispatchMut.isPending}>
                {dispatchMut.isPending ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4 mr-2" />}
                {t('adv.sendAlert')}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
        {audio && <audio controls autoPlay src={audio} className="h-9 max-w-full" aria-label={t('adv.listen')} />}
        {speechError && <span role="alert" className="text-[13px] text-warn">{t('adv.speechError')}</span>}
      </div>
      <p className="mt-4 text-[12px] leading-relaxed text-muted-foreground">{t('adv.grounded')} {adv.disclaimer}</p>
    </article>
  )
}

function RecipientsPanel({ department, me }: { department: string; me: any }) {
  const t = useT()
  const queryClient = useQueryClient()
  const [email, setEmail] = useState('')
  const [error, setError] = useState<string | null>(null)
  
  const req = useQuery({
    queryKey: ['recipients', department],
    queryFn: () => api.recipients(department),
  })

  const addMut = useMutation({
    mutationFn: (e: string) => api.addRecipient(department, e),
    onSuccess: () => {
      setEmail('')
      setError(null)
      queryClient.invalidateQueries({ queryKey: ['recipients', department] })
    },
    onError: (err: any) => setError(err.message)
  })

  const removeMut = useMutation({
    mutationFn: (e: string) => api.removeRecipient(department, e),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['recipients', department] })
    }
  })
  
  if (req.isPending) return <Skeleton className="h-20" />
  
  const recs = req.data || []
  
  return (
    <section className="rounded-xl border border-border bg-card">
      <h2 className="border-b border-border p-4 text-[15px] font-semibold flex items-center gap-2">
        <Users className="size-4" /> {t('adv.recipientsTitle')} <Badge variant="secondary" className="ml-auto">{recs.length}</Badge>
      </h2>
      <div className="p-4 space-y-4">
        {recs.length === 0 ? (
          <p className="text-[13px] text-muted-foreground">No recipients stored.</p>
        ) : (
          <ul className="space-y-2">
            {recs.map(r => (
              <li key={r} className="flex items-center justify-between text-[13px]">
                <span className="truncate pr-2">{r}</span>
                {me?.role === 'approver' && (
                  <Button variant="ghost" size="sm" onClick={() => removeMut.mutate(r)} disabled={removeMut.isPending} className="h-6 text-[11px] px-2 text-destructive">
                    {t('adv.removeRecipient')}
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
        
        {me?.role === 'approver' && (
          <form onSubmit={e => { e.preventDefault(); if (email) addMut.mutate(email) }} className="flex flex-col gap-2 pt-2 border-t border-border">
            <div className="flex gap-2">
              <Input type="email" placeholder="Add email..." value={email} onChange={e => setEmail(e.target.value)} required />
              <Button type="submit" size="sm" disabled={addMut.isPending || !email}>{t('adv.addRecipient')}</Button>
            </div>
            {error && <span className="text-[12px] text-destructive">{error}</span>}
          </form>
        )}
      </div>
    </section>
  )
}

function QueueItem({ d, me }: { d: DispatchItem; me: any }) {
  const t = useT()
  const queryClient = useQueryClient()
  
  const actionMut = useMutation({
    mutationFn: async ({ action }: { action: 'approve' | 'reject' | 'send' }) => {
      if (action === 'approve') return api.approveDispatch(d.id)
      if (action === 'reject') return api.rejectDispatch(d.id)
      if (action === 'send') return api.sendDispatch(d.id)
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['dispatches'] })
  })
  
  return (
    <li className="px-4 py-3 text-[13px]">
      <div className="flex items-start justify-between gap-2">
        <div className="font-medium">{d.department}</div>
        <Badge variant={d.status === 'blocked' || d.status === 'rejected' || d.status === 'failed' ? 'destructive' : d.status === 'sent' || d.status === 'approved' ? 'default' : 'secondary'} className="shrink-0">
          {d.status === 'sent' && <CheckCircle2 className="size-3 -ml-0.5 mr-1 text-primary-foreground" aria-hidden />}
          {d.status === 'blocked' && <AlertTriangle className="size-3 -ml-0.5 mr-1" aria-hidden />}
          {t(`adv.status.${d.status}` as Key)}
        </Badge>
      </div>
      <div className="mt-1 text-[12px] text-muted-foreground truncate">{d.subject}</div>
      <div className="mt-1 text-[11px] text-muted-foreground">{d.channel} · {formatIST(Date.parse(d.created_at_utc))}</div>
      {d.status === 'blocked' && d.detail?.reason && (
        <div className="mt-2 text-[12px] text-destructive bg-destructive/10 p-2 rounded">
          {d.detail.reason}
        </div>
      )}
      
      {me?.role === 'approver' && d.status === 'pending_approval' && (
        <div className="mt-3 flex gap-2">
          <Button size="sm" variant="outline" onClick={() => actionMut.mutate({ action: 'approve' })} disabled={actionMut.isPending}>{t('adv.action.approve')}</Button>
          <Button size="sm" variant="outline" onClick={() => actionMut.mutate({ action: 'reject' })} disabled={actionMut.isPending} className="text-destructive hover:text-destructive">{t('adv.action.reject')}</Button>
        </div>
      )}
      {me?.role === 'approver' && d.status === 'approved' && (
        <div className="mt-3 flex gap-2">
          <Button size="sm" onClick={() => actionMut.mutate({ action: 'send' })} disabled={actionMut.isPending}>{t('adv.action.send')}</Button>
        </div>
      )}
    </li>
  )
}

function PasscodeLogin({ onLogin }: { onLogin: () => void }) {
  const t = useT()
  const [pass, setPass] = useState('')
  const [err, setErr] = useState('')
  
  const login = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const res = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ passcode: pass })
      })
      if (!res.ok) throw new Error('Invalid passcode')
      setPass('')
      setErr('')
      onLogin()
    } catch {
      setErr('Invalid passcode')
    }
  }

  return (
    <form onSubmit={login} className="flex gap-2 items-center p-4 border border-border rounded-xl bg-card">
      <span className="text-[13px] font-medium">{t('adv.login')}</span>
      <Input type="password" value={pass} onChange={e => setPass(e.target.value)} placeholder={t('adv.passcode')} className="w-32" />
      <Button type="submit" size="sm" disabled={!pass}>Sign in</Button>
      {err && <span className="text-destructive text-[12px]">{err}</span>}
    </form>
  )
}

const PIPELINE: { icon: typeof Radar; key: Key }[] = [
  { icon: Radar, key: 'adv.p1' },
  { icon: FileSearch, key: 'adv.p2' },
  { icon: Bot, key: 'adv.p3' },
  { icon: Inbox, key: 'adv.p4' },
  { icon: Send, key: 'adv.p5' },
]

export function Advisories() {
  const t = useT()
  const lang = useLang()
  const queryClient = useQueryClient()
  const mine = usePrefs(s => s.role)
  const [roleId, setRoleId] = useState<RoleId>(mine)
  const role = roleById(roleId)
  
  const meQuery = useQuery({ queryKey: ['me'], queryFn: api.me, staleTime: 60000, retry: 0 })
  const modeQuery = useQuery({ queryKey: ['dispatchMode'], queryFn: api.dispatchMode, staleTime: 300000 })
  const mode = modeQuery.data?.mode
  
  const runId = useStore(assetsStore, s => s.data?.runId)
  const advisory = useQuery({
    queryKey: ['advisory', role.department, lang, runId || null],
    queryFn: () => api.advisory(role.department, currentApiLanguage(), runId || null),
    staleTime: Infinity,
    retry: 0,
  })
  
  const queue = useQuery({ queryKey: ['dispatches'], queryFn: api.dispatches, staleTime: 30_000, retry: 0 })
  
  return (
    <Page>
      {mode === 'live' && (
        <div className="mb-6 flex items-center gap-2 rounded-lg bg-destructive/10 p-3 text-[14px] text-destructive">
          <AlertCircle className="size-4" />
          <strong>{t('adv.mode.live')}</strong> — Dispatches will be sent to real recipients.
        </div>
      )}
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
        <div className="space-y-5">
          {meQuery.data?.auth_mode === 'passcode' && meQuery.data?.role === 'viewer' && (
            <PasscodeLogin onLogin={() => queryClient.invalidateQueries({ queryKey: ['me'] })} />
          )}
          
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
          {advisory.data && <AdvisoryCard runId={advisory.data.run_id} adv={advisory.data.advisory} role={role} />}
        </div>

        <aside className="flex flex-col gap-5">
          <RecipientsPanel department={role.department} me={meQuery.data} />
          
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
            <h2 id="queue" className="border-b border-border p-4 text-[15px] font-semibold flex items-center justify-between">
              {t('adv.queue')}
              <Button variant="ghost" size="icon-sm" aria-label="Refresh queue" onClick={() => queryClient.invalidateQueries({ queryKey: ['dispatches'] })}><RefreshCw className="size-4" /></Button>
            </h2>
            {queue.isPending ? (
              <div className="space-y-2 p-4">{[0, 1].map(i => <Skeleton key={i} className="h-10" />)}</div>
            ) : !queue.data?.length ? (
              <p className="p-4 text-[13px] text-muted-foreground">{t('adv.queueEmpty')}</p>
            ) : (
              <ul className="divide-y divide-border max-h-[500px] overflow-y-auto">
                {queue.data.slice(0, 20).map(d => (
                  <QueueItem key={d.id} d={d} me={meQuery.data} />
                ))}
              </ul>
            )}
          </section>
        </aside>
      </div>
    </Page>
  )
}
