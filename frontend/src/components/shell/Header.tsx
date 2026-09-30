import { Menu, Moon, Sun } from 'lucide-react'
import { Link, pathFor, STORM_TABS, useRoute, type StormTab } from '@/app/router'
import { usePrefs, useResolvedTheme } from '@/app/prefs'
import { useT, type Key } from '@/i18n'
import { cn } from '@/lib/utils'
import { LanguageMenu } from '@/panels/LanguageMenu'
import { SavedNotice } from '@/panels/SavedNotice'

function StormTabs({ id, tab }: { id: string; tab: StormTab }) {
  const t = useT()
  return (
    <nav aria-label={t('nav.stormSections')} className="-mb-px flex gap-1 overflow-x-auto">
      {STORM_TABS.map(s => (
        <Link
          key={s}
          to={pathFor({ name: 'storm', id, tab: s })}
          aria-current={s === tab ? 'page' : undefined}
          className={cn(
            'relative shrink-0 border-b-2 border-transparent px-3 py-2.5 text-[13px] font-medium whitespace-nowrap text-muted-foreground transition-colors hover:text-foreground',
            s === tab && 'text-foreground',
          )}
        >
          {t(`tab.${s}` as Key)}
          {/* The underline is its own element so a page change can slide it to the new tab (see .vt-tab). */}
          {s === tab && <span className="vt-tab absolute inset-x-0 -bottom-0.5 h-0.5 rounded-full bg-primary" aria-hidden />}
        </Link>
      ))}
    </nav>
  )
}

function ThemeToggle() {
  const t = useT()
  const resolved = useResolvedTheme()
  const set = usePrefs(s => s.set)
  const next = resolved === 'dark' ? 'light' : 'dark'
  return (
    <button
      type="button"
      onClick={() => set({ theme: next })}
      aria-label={t('theme.toggle')}
      title={t(`theme.${next}` as Key)}
      className="grid size-9 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
    >
      {resolved === 'dark' ? <Sun className="size-[18px]" /> : <Moon className="size-[18px]" />}
    </button>
  )
}

/** Page title, the storm's sections as tabs, and quick theme and language switches. */
export function Header({ title, badge, onMenu }: { title: string; badge?: React.ReactNode; onMenu: () => void }) {
  const t = useT()
  const route = useRoute()
  return (
    <header className="shrink-0 border-b border-border bg-card/80 backdrop-blur">
      <div className="flex h-14 items-center gap-3 px-4 lg:px-6">
        <button type="button" onClick={onMenu} aria-label={t('nav.menu')} className="-ml-1.5 grid size-9 place-items-center rounded-md text-muted-foreground hover:bg-accent lg:hidden">
          <Menu className="size-5" />
        </button>
        <h1 className="min-w-0 truncate text-[15px] font-semibold tracking-tight">{title}</h1>
        {badge}
        <div className="ml-auto flex items-center gap-1">
          <SavedNotice compact />
          <LanguageMenu />
          <ThemeToggle />
        </div>
      </div>
      {route.name === 'storm' && (
        <div className="px-2 lg:px-4">
          <StormTabs id={route.id} tab={route.tab} />
        </div>
      )}
    </header>
  )
}
