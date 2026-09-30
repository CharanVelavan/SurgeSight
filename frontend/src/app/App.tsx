import { useEffect } from 'react'
import { MapCanvas } from '@/map/MapCanvas'
import { PerfOverlay } from '@/panels/PerfOverlay'
import { loadWeather } from '@/weather/atlas'

const showPerf = new URLSearchParams(location.search).has('perf')

export default function App() {
  useEffect(() => {
    void loadWeather()
  }, [])
  return (
    <div className="relative h-full w-full overflow-hidden bg-background">
      <MapCanvas />
      {showPerf && <PerfOverlay />}
    </div>
  )
}
