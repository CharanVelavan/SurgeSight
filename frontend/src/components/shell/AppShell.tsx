import { useEffect, useState } from 'react'
import { Sheet, SheetContent, SheetTitle } from '@/components/ui/sheet'
import { useT } from '@/i18n'
import { Header } from './Header'
import { Sidebar } from './Sidebar'

/**
 * Every screen after the welcome: navigation on the left (a drawer on phones), a header, and the page.
 * `fill` pages (the maps) take the whole area and scroll nothing; other pages scroll inside the main area.
 */
export function AppShell({ title, badge, fill = false, children }: { title: string; badge?: React.ReactNode; fill?: boolean; children: React.ReactNode }) {
  const t = useT()
  const [menu, setMenu] = useState(false)
  // Map screens start with the rail folded to icons so the map gets the width; the user can open it again.
  const [collapsed, setCollapsed] = useState(fill)
  useEffect(() => setCollapsed(fill), [fill])
  useEffect(() => {
    document.title = `${title} · SurgeSight`
  }, [title])
  return (
    <div className="flex h-full bg-background">
      <aside className={`hidden shrink-0 border-r border-sidebar-border bg-sidebar transition-[width] duration-200 lg:block ${collapsed ? 'w-16' : 'w-60'}`}>
        <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(c => !c)} />
      </aside>
      <Sheet open={menu} onOpenChange={setMenu}>
        <SheetContent side="left" className="w-72 bg-sidebar p-0" aria-describedby={undefined}>
          <SheetTitle className="sr-only">{t('nav.main')}</SheetTitle>
          <Sidebar onNavigate={() => setMenu(false)} />
        </SheetContent>
      </Sheet>
      <div className="flex min-w-0 flex-1 flex-col">
        <Header title={title} badge={badge} onMenu={() => setMenu(true)} />
        <main id="main" className={fill ? 'relative min-h-0 flex-1 overflow-hidden' : 'min-h-0 flex-1 overflow-y-auto'}>
          {children}
        </main>
      </div>
    </div>
  )
}

/** Width and padding shared by the reading pages. */
export function Page({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return <div className={`mx-auto w-full max-w-6xl px-4 py-6 lg:px-8 lg:py-8 ${className}`}>{children}</div>
}
