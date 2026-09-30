import { useEffect } from 'react'
import { trackStore } from '@/data/track'
import { useClock } from '@/timeline/clock'
import { useForecast, useTimeline } from './queries'

/** Feeds the timeline and the forecast for the current cutoff into the store read by the map's frame loop. */
export function TrackSync() {
  const { data: timeline } = useTimeline()
  const cutoff = useClock(s => s.cutoff, 50)
  const { data: forecast, isError } = useForecast(cutoff)

  useEffect(() => {
    trackStore.setState({ timeline: timeline ?? null })
  }, [timeline])
  useEffect(() => {
    trackStore.setState({ forecast: isError ? null : (forecast?.data ?? null) })
  }, [forecast, isError])
  return null
}
