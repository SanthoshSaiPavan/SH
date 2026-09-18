import { useMemo } from 'react'
import { parseUtc } from '../lib/format'
import { useLiveData } from './useLiveData'

/** The engine clock: simulated time in DEMO mode, wall time in LIVE mode. */
export function useEngineNow(): Date {
  const { sim } = useLiveData()
  return useMemo(() => (sim ? parseUtc(sim.sim_time) : new Date()), [sim])
}
