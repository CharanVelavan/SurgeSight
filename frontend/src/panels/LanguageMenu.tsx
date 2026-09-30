import { Languages } from 'lucide-react'
import { LANGS, setLang, useLang, useT, type Lang } from '@/i18n'

/** Native <select> so it works with every keyboard and screen reader. The map reloads to relabel itself. */
export function LanguageMenu({ className = '', full = false }: { className?: string; full?: boolean }) {
  const lang = useLang()
  const t = useT()
  return (
    <label
      className={`flex h-9 cursor-pointer items-center gap-1.5 rounded-md px-2 text-[13px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground ${full ? 'border border-input bg-card px-3 text-foreground' : ''} ${className}`}
    >
      <Languages className="size-[18px] shrink-0" aria-hidden />
      <span className="sr-only">{t('lang.label')}</span>
      <select
        value={lang}
        onChange={e => {
          const next = e.target.value as Lang
          void setLang(next).then(() => {
            if (document.querySelector('[data-map-root]')) location.reload()
          })
        }}
        className={`cursor-pointer appearance-none bg-transparent font-medium text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring/60 ${full ? 'flex-1' : 'max-sm:w-8 max-sm:text-transparent'}`}
      >
        {LANGS.map(l => (
          <option key={l.code} value={l.code} className="bg-popover text-popover-foreground">
            {l.native}
          </option>
        ))}
      </select>
    </label>
  )
}
