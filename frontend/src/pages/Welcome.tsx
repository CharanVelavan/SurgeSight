import { useState } from 'react'
import { ArrowLeft, ArrowRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Logo } from '@/components/shell/Logo'
import { RoleChoice } from '@/components/RoleChoice'
import { ThemeChoice } from '@/components/ThemeChoice'
import { navigate } from '@/app/router'
import { usePrefs } from '@/app/prefs'
import { useT } from '@/i18n'
import { LanguageMenu } from '@/panels/LanguageMenu'

const STEPS = 2

/** First visit: what SurgeSight is, who you are, and how it should look. Returns to the page that was asked for. */
export function Welcome() {
  const t = useT()
  const [step, setStep] = useState(0)
  const lite = usePrefs(s => s.lite)
  const set = usePrefs(s => s.set)
  const finish = () => {
    set({ onboarded: true })
    const next = new URLSearchParams(location.search).get('next')
    navigate(next && next.startsWith('/') && !next.startsWith('//') && !next.startsWith('/welcome') ? next : '/', true)
  }
  // The animated intro plays on the first step only, and not in lite mode (see index.css for reduced motion).
  const intro = step === 0 && !lite
  const fx = (cls: string) => (intro ? cls : '')
  return (
    <div className="flex h-full flex-col overflow-x-hidden overflow-y-auto bg-background">
      <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col px-5 pt-6 pb-8 sm:pt-10">
        <div className="flex items-center justify-end">
          <LanguageMenu />
        </div>

        {step > 0 && (
          <>
            <div className="mt-6 flex items-center gap-3" aria-hidden>
              {Array.from({ length: STEPS }, (_, i) => (
                <span key={i} className={`h-1 flex-1 rounded-full ${i < step ? 'bg-primary' : 'bg-muted'}`} />
              ))}
            </div>
            <p className="num mt-2 text-[12px] text-muted-foreground">{t('welcome.step', { n: step })}</p>
          </>
        )}

        <section className="mt-6 flex flex-1 flex-col" aria-live="polite">
          {step === 0 && (
            <div className="flex min-h-[60vh] flex-1 flex-col items-center justify-center text-center">
              <Logo className={`size-28 drop-shadow-sm sm:size-32 ${fx('intro-logo')}`} />
              <h1 className={`mt-8 text-[30px] leading-tight font-semibold tracking-tight text-balance sm:text-[38px] ${fx('intro-wipe')}`}>{t('welcome.hello')}</h1>
              <p className={`mt-3 max-w-md text-[15px] leading-relaxed text-muted-foreground ${fx('intro-up')}`}>{t('welcome.lead')}</p>
              <span className="mt-7 flex gap-2" aria-hidden>
                {['#1A73E8', '#EA4335', '#FBBC04', '#34A853'].map((c, i) => (
                  <i key={c} className={`block size-2.5 rounded-full ${fx('intro-dot')}`} style={{ background: c, ['--d' as string]: `${1.7 + i * 0.1}s` }} />
                ))}
              </span>
            </div>
          )}
          {step === 1 && (
            <>
              <h1 className="text-[26px] font-semibold tracking-tight">{t('welcome.roleTitle')}</h1>
              <p className="mt-2 mb-6 text-[15px] text-muted-foreground">{t('welcome.roleLead')}</p>
              <RoleChoice />
            </>
          )}
          {step === 2 && (
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

        <div className={`mt-10 flex items-center gap-3 ${step > 0 ? 'border-t border-border pt-5' : ''} ${fx('intro-up')}`} style={intro ? { ['--d' as string]: '2s' } : undefined}>
          {step > 0 ? (
            <Button variant="ghost" onClick={() => setStep(s => s - 1)}>
              <ArrowLeft className="size-4" /> {t('welcome.back')}
            </Button>
          ) : (
            <Button variant="ghost" onClick={finish}>{t('welcome.skip')}</Button>
          )}
          <Button className="ml-auto" size="lg" onClick={() => (step < STEPS ? setStep(s => s + 1) : finish())}>
            {step < STEPS ? t('welcome.next') : t('welcome.finish')}
            <ArrowRight className="size-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}
