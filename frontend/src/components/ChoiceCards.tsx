import { Check } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface Choice<T extends string> {
  value: T
  title: string
  text?: string
  icon?: React.ReactNode
}

/** A radio group drawn as cards: arrow keys move between them, the chosen one carries a tick. */
export function ChoiceCards<T extends string>({ label, value, onChange, choices, columns = 2 }: { label: string; value: T; onChange: (v: T) => void; choices: Choice<T>[]; columns?: 1 | 2 | 3 }) {
  const move = (e: React.KeyboardEvent, i: number) => {
    const d = e.key === 'ArrowDown' || e.key === 'ArrowRight' ? 1 : e.key === 'ArrowUp' || e.key === 'ArrowLeft' ? -1 : 0
    if (!d) return
    e.preventDefault()
    const next = choices[(i + d + choices.length) % choices.length]
    onChange(next.value)
    ;(e.currentTarget.parentElement?.children[(i + d + choices.length) % choices.length] as HTMLElement | undefined)?.focus()
  }
  return (
    <div role="radiogroup" aria-label={label} className={cn('grid gap-2.5', columns === 2 && 'sm:grid-cols-2', columns === 3 && 'sm:grid-cols-3')}>
      {choices.map((c, i) => {
        const on = c.value === value
        return (
          <button
            key={c.value}
            type="button"
            role="radio"
            aria-checked={on}
            tabIndex={on ? 0 : -1}
            onClick={() => onChange(c.value)}
            onKeyDown={e => move(e, i)}
            className={cn(
              'relative flex items-start gap-3 rounded-lg border border-border bg-card p-3.5 text-left transition-colors hover:border-primary/50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring',
              on && 'border-primary bg-accent',
            )}
          >
            {c.icon && <span className={cn('grid size-9 shrink-0 place-items-center rounded-md bg-muted text-muted-foreground', on && 'bg-primary text-primary-foreground')}>{c.icon}</span>}
            <span className="min-w-0 flex-1 pr-5">
              <span className="block text-[14px] font-medium">{c.title}</span>
              {c.text && <span className="mt-0.5 block text-[12.5px] leading-snug text-muted-foreground">{c.text}</span>}
            </span>
            {on && <Check className="absolute top-3 right-3 size-4 text-primary" aria-hidden />}
          </button>
        )
      })}
    </div>
  )
}
