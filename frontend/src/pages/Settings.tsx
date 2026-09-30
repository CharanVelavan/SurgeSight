import { useEffect, useState } from 'react'
import { Check } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { RoleChoice } from '@/components/RoleChoice'
import { ThemeChoice } from '@/components/ThemeChoice'
import { AppShell, Page } from '@/components/shell/AppShell'
import { navigate } from '@/app/router'
import { usePrefs } from '@/app/prefs'
import { useT } from '@/i18n'
import { LanguageMenu } from '@/panels/LanguageMenu'

function Group({ id, title, lead, children }: { id: string; title: string; lead?: string; children: React.ReactNode }) {
  return (
    <section aria-labelledby={`${id}-h`} id={id} className="scroll-mt-4 border-b border-border py-8 first:pt-0 last:border-0">
      <div className="grid gap-4 md:grid-cols-[14rem_1fr] md:gap-8">
        <div>
          <h2 id={`${id}-h`} className="text-[15px] font-semibold">{title}</h2>
          {lead && <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">{lead}</p>}
        </div>
        <div>{children}</div>
      </div>
    </section>
  )
}

function Toggle({ id, title, hint, checked, onChange }: { id: string; title: string; hint?: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label htmlFor={id} className="flex cursor-pointer items-start justify-between gap-6 border-b border-border py-3 first:pt-0 last:border-0">
      <span>
        <span className="block text-[14px] font-medium">{title}</span>
        {hint && <span className="mt-0.5 block text-[13px] leading-snug text-muted-foreground">{hint}</span>}
      </span>
      <Switch id={id} checked={checked} onCheckedChange={onChange} />
    </label>
  )
}

export function Settings() {
  const t = useT()
  const prefs = usePrefs()
  const [cleared, setCleared] = useState(false)
  useEffect(() => {
    if (location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView()
  }, [])
  const clearSaved = async () => {
    try {
      for (const key of await caches.keys()) await caches.delete(key)
    } catch {
      /* no cache storage in this browser */
    }
    setCleared(true)
  }
  return (
    <AppShell title={t('nav.settings')}>
      <Page className="max-w-4xl">
        <Group id="role" title={t('settings.role')} lead={t('settings.roleLead')}>
          <RoleChoice />
        </Group>
        <Group id="appearance" title={t('settings.appearance')}>
          <ThemeChoice />
        </Group>
        <Group id="language" title={t('settings.language')} lead={t('settings.languageLead')}>
          <LanguageMenu full className="w-full sm:w-72" />
        </Group>
        <Group id="map" title={t('settings.map')}>
          <Toggle id="s-wind" title={t('settings.wind')} checked={prefs.stormWind} onChange={v => prefs.set({ stormWind: v })} />
          <Toggle id="s-rain" title={t('settings.rain')} checked={prefs.stormRain} onChange={v => prefs.set({ stormRain: v })} />
          <Toggle id="s-lite" title={t('settings.lite')} hint={t('settings.liteHint')} checked={prefs.lite} onChange={v => prefs.set({ lite: v })} />
        </Group>
        <Group id="data" title={t('settings.data')} lead={t('settings.dataLead')}>
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="outline" onClick={clearSaved}>{t('settings.clear')}</Button>
            {cleared && <span role="status" className="flex items-center gap-1.5 text-[13px] text-ok"><Check className="size-4" aria-hidden />{t('settings.cleared')}</span>}
          </div>
        </Group>
        <Group id="about" title={t('settings.about')}>
          <p className="text-[13.5px] leading-relaxed text-muted-foreground">{t('settings.aboutText')}</p>
          <Button variant="outline" className="mt-4" onClick={() => { prefs.set({ onboarded: false }); navigate('/welcome') }}>
            {t('settings.welcome')}
          </Button>
        </Group>
      </Page>
    </AppShell>
  )
}
