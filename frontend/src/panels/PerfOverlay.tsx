/** `?perf=1`: fps, frame time and particle budget, read from the frame loop without React per frame. */

import { useEffect, useState } from 'react'
import { perf, quality } from '@/map/quality'

export function PerfOverlay() {
  const [, force] = useState(0)
  useEffect(() => {
    const id = setInterval(() => force(x => x + 1), 250)
    return () => clearInterval(id)
  }, [])
  return (
    <div className="panel num pointer-events-none fixed right-3 bottom-40 z-50 px-2.5 py-1.5 text-[11px] leading-4 text-muted-foreground">
      <div><span className="text-foreground">{perf.fps.toFixed(0)}</span> fps · {perf.frameMs.toFixed(1)} ms</div>
      <div>{(quality.particles / 1000).toFixed(0)}k particles · trail {quality.trail}</div>
      <div>{document.documentElement.dataset.renderingType ?? '…'}</div>
    </div>
  )
}
