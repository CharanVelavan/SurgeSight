import { useState } from 'react'
import { ArrowLeft, ArrowRight, Building2, Info, Route as RouteIcon, ShieldAlert } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Logo } from '@/components/shell/Logo'
import { RoleChoice } from '@/components/RoleChoice'
import { ThemeChoice } from '@/components/ThemeChoice'
import { navigate } from '@/app/router'
import { usePrefs } from '@/app/prefs'
import { useT } from '@/i18n'
import { LanguageMenu } from '@/panels/LanguageMenu'

const STEPS = 3

function Feature({ icon, title, text }: { icon: React.ReactNode; title: string; text: string }) {
  return (
    <li className="flex gap-3.5">
      <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-accent text-primary">{icon}</span>
      <span>
        <span className="block text-[15px] font-medium">{title}</span>
        <span className="mt-0.5 block text-[14px] leading-relaxed text-muted-foreground">{text}</span>
      </span>
    </li>
  )
}

/** First visit: what SurgeSight is, who you are, and how it should look. Returns to the page that was asked for. */
export function Welcome() {
  const t = useT()
  const [step, setStep] = useState(1)
  const lite = usePrefs(s => s.lite)
  const set = usePrefs(s => s.set)
  const finish = () => {
    set({ onboarded: true })
    const next = new URLSearchParams(location.search).get('next')
    navigate(next && next.startsWith('/') && !next.startsWith('//') && !next.startsWith('/welcome') ? next : '/', true)
  }
  return (
    <div className="flex h-full flex-col overflow-y-auto bg-background">
      <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col px-5 pt-6 pb-8 sm:pt-10">
        <div className="flex items-center gap-2.5">
          <Logo className="size-7" />
          <span className="text-[15px] font-semibold tracking-tight">SurgeSight</span>
          <LanguageMenu className="ml-auto" />
        </div>

        <div className="mt-10 flex items-center gap-3" aria-hidden>
          {Array.from({ length: STEPS }, (_, i) => (
            <span key={i} className={`h-1 flex-1 rounded-full ${i < step ? 'bg-primary' : 'bg-muted'}`} />
          ))}
        </div>
        <p className="num mt-2 text-[12px] text-muted-foreground">{t('welcome.step', { n: step })}</p>

        <section className="mt-6 flex-1" aria-live="polite">
          {step === 1 && (
            <>
              <h1 className="text-[28px] leading-tight font-semibold tracking-tight text-balance sm:text-[34px]">{t('welcome.title')}</h1>
              <p className="mt-3 text-[15px] leading-relaxed text-muted-foreground">{t('welcome.lead')}</p>
              <ul className="mt-8 flex flex-col gap-5">
                <Feature icon={<RouteIcon className="size-5" />} title={t('welcome.f1.title')} text={t('welcome.f1.text')} />
                <Feature icon={<ShieldAlert className="size-5" />} title={t('welcome.f2.title')} text={t('welcome.f2.text')} />
                <Feature icon={<Building2 className="size-5" />} title={t('welcome.f3.title')} text={t('welcome.f3.text')} />
              </ul>
              <div className="mt-8 flex gap-3 rounded-lg border border-border bg-card p-4 text-[13px] leading-relaxed text-muted-foreground">
                <Info className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
                {t('landing.notice')}
              </div>
            </>
          )}
          {step === 2 && (
            <>
              <h1 className="text-[26px] font-semibold tracking-tight">{t('welcome.roleTitle')}</h1>
              <p className="mt-2 mb-6 text-[15px] text-muted-foreground">{t('welcome.roleLead')}</p>
              <RoleChoice />
            </>
          )}
          {step === 3 && (
            <>
              <h1 className="text-[26px] font-semibold tracking-tight">{t('welcome.prefsTitle')}</h1>
              <p className="mt-2 mb-6 text-[15px] text-muted-foreground">{t('welcome.prefsLead')}</p>
              <h2 className="eyebrow mb-2.5">{t('settings.theme')}</h2>
              <ThemeChoice />
              <h2 className="eyebrow mt-7 mb-2.5">{t('settings.language')}</h2>
              <LanguageMenu full className="w-full sm:w-72" />
              <label htmlFor="lite" className="mt-7 flex cursor-pointer items-start justify-between gap-6 rounded-lg border border-border bg-card p-4">
                <span>
                  <span className="block text-[14px] font-medium">{t('settings.lite')}</span>
                  <span className="mt-0.5 block text-[13px] leading-snug text-muted-foreground">{t('settings.liteHint')}</span>
                </span>
                <Switch id="lite" checked={lite} onCheckedChange={v => set({ lite: v })} />
              </label>
            </>
          )}
        </section>

        <div className="mt-10 flex items-center gap-3 border-t border-border pt-5">
          {step > 1 ? (
            <Button variant="ghost" onClick={() => setStep(s => s - 1)}>
              <ArrowLeft className="size-4" /> {t('welcome.back')}
            </Button>
          ) : (
            <Button variant="ghost" onClick={finish}>{t('welcome.skip')}</Button>
          )}
          <Button className="ml-auto" size="lg" onClick={() => (step < STEPS ? setStep(s => s + 1) : finish())}>
            {step === 1 ? t('welcome.start') : step < STEPS ? t('welcome.next') : t('welcome.finish')}
            <ArrowRight className="size-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}
