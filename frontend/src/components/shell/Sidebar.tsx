import { BookOpen, CloudSun, History, House, Settings } from 'lucide-react'
import { useCatalog } from '@/app/queries'
import { Link, pathFor, useRoute, type Route } from '@/app/router'
import { usePrefs } from '@/app/prefs'
import { roleById } from '@/data/roles'
import { useT, type Key } from '@/i18n'
import { cn } from '@/lib/utils'
import { Logo } from './Logo'

function NavItem({ to, icon: Icon, label, active, sub, onNavigate }: { to: string; icon: typeof House; label: string; active: boolean; sub?: string; onNavigate?: () => void }) {
  return (
    <Link
      to={to}
      onClick={onNavigate}
      aria-current={active ? 'page' : undefined}
      className={cn(
        'flex items-center gap-3 rounded-md px-2.5 py-2 text-[13px] font-medium text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-foreground',
        active && 'bg-sidebar-accent text-foreground',
      )}
    >
      <Icon className={cn('size-[18px] shrink-0', active && 'text-primary')} aria-hidden />
      <span className="min-w-0 flex-1 truncate">{label}</span>
      {sub && <span className="num text-[11px] font-normal text-muted-foreground">{sub}</span>}
    </Link>
  )
}

const is = (r: Route, name: Route['name']) => r.name === name

/** Primary navigation: the same list as a fixed column on wide screens and inside the menu drawer on phones. */
export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const t = useT()
  const route = useRoute()
  const { data } = useCatalog()
  const role = roleById(usePrefs(s => s.role))
  const storms = data?.tiles.filter(tile => tile.kind === 'storm' && tile.status === 'available') ?? []
  return (
    <nav aria-label={t('nav.main')} className="flex h-full flex-col gap-6 px-3 py-4">
      <Link to="/" onClick={onNavigate} className="flex items-center gap-2.5 px-1.5">
        <Logo className="size-7" />
        <span className="text-[15px] font-semibold tracking-tight">SurgeSight</span>
      </Link>

      <div className="flex flex-col gap-0.5">
        <NavItem to="/" icon={House} label={t('nav.home')} active={is(route, 'home')} onNavigate={onNavigate} />
        <NavItem to="/live" icon={CloudSun} label={t('nav.live')} active={is(route, 'live')} onNavigate={onNavigate} />
      </div>

      <div className="flex flex-col gap-0.5">
        <div className="eyebrow px-2.5 pb-1.5">{t('nav.storms')}</div>
        {storms.map(s => (
          <NavItem
            key={s.id}
            to={pathFor({ name: 'storm', id: s.id, tab: 'overview' })}
            icon={History}
            label={t(`tile.${s.id}.name` as Key)}
            sub={s.year ? String(s.year) : undefined}
            active={route.name === 'storm' && route.id === s.id}
            onNavigate={onNavigate}
          />
        ))}
      </div>

      <div className="mt-auto flex flex-col gap-0.5">
        <NavItem to="/guide" icon={BookOpen} label={t('nav.guide')} active={is(route, 'guide')} onNavigate={onNavigate} />
        <NavItem to="/settings" icon={Settings} label={t('nav.settings')} active={is(route, 'settings')} onNavigate={onNavigate} />
        <Link
          to="/settings#role"
          onClick={onNavigate}
          className="mt-3 flex items-center gap-3 rounded-lg border border-border bg-card px-3 py-2.5 transition-colors hover:border-primary/40"
        >
          <span className="grid size-8 shrink-0 place-items-center rounded-md bg-accent text-primary">
            <role.icon className="size-4" aria-hidden />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-[11px] text-muted-foreground">{t('nav.yourRole')}</span>
            <span className="block truncate text-[13px] font-medium">{t(`role.${role.id}.short` as Key)}</span>
          </span>
        </Link>
      </div>
    </nav>
  )
}
