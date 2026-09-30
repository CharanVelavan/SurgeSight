import { WifiOff } from 'lucide-react'
import { useT } from '@/i18n'
import { formatIST } from '@/lib/format'
import { useNet, useOnline } from '@/lib/net'

/** Says when the numbers on screen are a saved copy, or that the connection is gone. */
export function SavedNotice({ compact = false, className = '' }: { compact?: boolean; className?: string }) {
  const t = useT()
  const { savedAt, mapFailed } = useNet()
  const online = useOnline()
  if (online && savedAt === null && !mapFailed) return null
  const text = savedAt !== null ? t('net.saved', { time: formatIST(savedAt) }) : !online ? t('net.offline') : t('net.mapFailed')
  if (compact)
    return (
      <span role="status" title={text} className={`flex h-8 items-center gap-1.5 rounded-md bg-warn-bg px-2.5 text-[12px] font-medium text-warn ${className}`}>
        <WifiOff className="size-4 shrink-0" aria-hidden />
        <span className="max-w-56 truncate max-sm:sr-only">{text}</span>
      </span>
    )
  return (
    <div role="status" className={`flex items-center gap-2 rounded-lg border border-warn/30 bg-warn-bg px-3 py-2 text-[13px] text-warn ${className}`}>
      <WifiOff className="size-4 shrink-0" aria-hidden />
      <span>{text}</span>
    </div>
  )
}
