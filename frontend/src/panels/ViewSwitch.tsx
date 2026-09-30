import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useT } from '@/i18n'
import { useUi, type View } from '@/state/ui'

export function ViewSwitch() {
  const t = useT()
  const view = useUi(s => s.view)
  const set = useUi(s => s.set)
  return (
    <div className="panel pointer-events-auto absolute top-16 right-3 z-10 p-1">
      <ToggleGroup type="single" size="sm" spacing={0} value={view} onValueChange={v => v && set({ view: v as View, hoverAsset: null })} aria-label={t('view.aria')}>
        <ToggleGroupItem value="india" className="px-3 text-[11px] data-[state=on]:bg-accent">{t('view.india')}</ToggleGroupItem>
        <ToggleGroupItem value="impact" className="px-3 text-[11px] data-[state=on]:bg-accent" title={t('view.impactTip')}>
          {t('view.impact')}
        </ToggleGroupItem>
      </ToggleGroup>
    </div>
  )
}
