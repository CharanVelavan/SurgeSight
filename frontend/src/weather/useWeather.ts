import { useStore } from 'zustand'
import { weatherStore } from './atlas'

export const useWeather = <T,>(select: Parameters<typeof useStore<typeof weatherStore, T>>[1]) => useStore(weatherStore, select)
