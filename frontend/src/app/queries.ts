import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

export const useTimeline = () => useQuery({ queryKey: ['timeline'], queryFn: api.timeline, staleTime: Infinity })
