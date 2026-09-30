import { WifiOff } from 'lucide-react'
import { useT } from '@/i18n'
import { formatIST } from '@/lib/format'
import { useNet, useOnline } from '@/lib/net'

/** Says when the numbers on screen are a saved copy, or that the connection is gone. Shown on every screen. */
export function SavedNotice({ className = '' }: { className?: string }) {
  const t = useT()
  const { savedAt, mapFailed } = useNet()
  const online = useOnline()
  if (online && savedAt === null && !mapFailed) return null
  return (
    <div role="status" className={`panel pointer-events-auto z-30 flex max-w-[calc(100%-1.5rem)] items-center gap-2 px-3 py-1.5 text-[12px] text-[#E0B34A] ${className}`}>
      <WifiOff className="size-4 shrink-0" aria-hidden />
      <span>
        {savedAt !== null ? t('net.saved', { time: formatIST(savedAt) }) : !online ? t('net.offline') : t('net.mapFailed')}
      </span>
    </div>
  )
}
