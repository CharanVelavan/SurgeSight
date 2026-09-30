import { Languages } from 'lucide-react'
import { LANGS, setLang, useLang, useT, type Lang } from '@/i18n'

/** Native <select>: works with every keyboard and screen reader. Map labels follow the language after a reload. */
export function LanguageMenu({ className = '' }: { className?: string }) {
  const lang = useLang()
  const t = useT()
  return (
    <label className={`panel pointer-events-auto flex h-9 items-center gap-1.5 px-2.5 text-[12px] ${className}`}>
      <Languages className="size-4 text-muted-foreground" aria-hidden />
      <span className="sr-only">{t('lang.label')}</span>
      <select
        value={lang}
        onChange={e => {
          const next = e.target.value as Lang
          // the Google map loads its labels once, so it is reloaded in the new language
          void setLang(next).then(() => {
            if (location.pathname !== '/') location.reload()
          })
        }}
        className="cursor-pointer bg-transparent text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring/60"
      >
        {LANGS.map(l => (
          <option key={l.code} value={l.code} className="bg-[#101318]">
            {l.native}
          </option>
        ))}
      </select>
    </label>
  )
}
