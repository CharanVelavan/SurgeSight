import { usePrefs, type RoleId } from '@/app/prefs'
import { ROLES } from '@/data/roles'
import { useT, type Key } from '@/i18n'
import { ChoiceCards } from './ChoiceCards'

export function RoleChoice() {
  const t = useT()
  const role = usePrefs(s => s.role)
  const set = usePrefs(s => s.set)
  return (
    <ChoiceCards<RoleId>
      label={t('nav.yourRole')}
      value={role}
      onChange={v => set({ role: v })}
      choices={ROLES.map(r => ({
        value: r.id,
        title: t(`role.${r.id}.name` as Key),
        text: t(`role.${r.id}.focus` as Key),
        icon: <r.icon className="size-[18px]" />,
      }))}
    />
  )
}
