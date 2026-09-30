import { useSyncExternalStore } from 'react'

export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    fn => {
      const q = matchMedia(query)
      q.addEventListener('change', fn)
      return () => q.removeEventListener('change', fn)
    },
    () => matchMedia(query).matches,
  )
}
