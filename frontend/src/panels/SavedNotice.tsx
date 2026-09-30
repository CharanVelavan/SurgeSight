import { WifiOff } from 'lucide-react'
import { formatIST } from '@/lib/format'
import { useNet, useOnline } from '@/lib/net'

/** Says when the numbers on screen are a saved copy, or that the connection is gone. Shown on every screen. */
export function SavedNotice({ className = '' }: { className?: string }) {
  const { savedAt, mapFailed } = useNet()
  const online = useOnline()
  if (online && savedAt === null && !mapFailed) return null
  return (
    <div role="status" className={`panel pointer-events-auto z-30 flex max-w-[calc(100%-1.5rem)] items-center gap-2 px-3 py-1.5 text-[12px] text-[#E0B34A] ${className}`}>
      <WifiOff className="size-4 shrink-0" aria-hidden />
      <span>
        {savedAt !== null ? <>Weak connection: showing data saved at <span className="num">{formatIST(savedAt)}</span>. It may be out of date.</> : !online ? 'You are offline. Saved data is shown where available.' : 'The map could not load. Lists and numbers still work.'}
      </span>
    </div>
  )
}
