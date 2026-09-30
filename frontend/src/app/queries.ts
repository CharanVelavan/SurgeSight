import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

export const useTimeline = () => useQuery({ queryKey: ['timeline'], queryFn: api.timeline, staleTime: Infinity })

/** UTC cutoff as the API expects it: "YYYY-MM-DD HH:MM:SS". */
export const cutoffParam = (ms: number) => new Date(ms).toISOString().slice(0, 19).replace('T', ' ')

/** Experimental forecast issued at the cutoff. Cached per cutoff; a failure (too little track) just hides it. */
export const useForecast = (cutoffMs: number) =>
  useQuery({ queryKey: ['forecast', cutoffMs], queryFn: () => api.forecast(cutoffParam(cutoffMs)), staleTime: Infinity, retry: 0, placeholderData: keep => keep })
