import { Monitor, Moon, Sun } from 'lucide-react'
import { usePrefs, type Theme } from '@/app/prefs'
import { useT } from '@/i18n'
import { ChoiceCards } from './ChoiceCards'

export function ThemeChoice() {
  const t = useT()
  const theme = usePrefs(s => s.theme)
  const set = usePrefs(s => s.set)
  return (
    <ChoiceCards<Theme>
      label={t('settings.theme')}
      value={theme}
      onChange={v => set({ theme: v })}
      columns={3}
      choices={[
        { value: 'light', title: t('theme.light'), icon: <Sun className="size-[18px]" /> },
        { value: 'dark', title: t('theme.dark'), icon: <Moon className="size-[18px]" /> },
        { value: 'system', title: t('theme.system'), icon: <Monitor className="size-[18px]" /> },
      ]}
    />
  )
}
