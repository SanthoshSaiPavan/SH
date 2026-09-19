import { useState } from 'react'
import { api } from '../lib/api'
import { SimStatusSchema } from '../lib/schemas'
import { useLiveData } from './useLiveData'

export type SimMode = 'live' | 'demo'

/** The backend's LIVE GPS / DEMO SIMULATION mode, shared by every control that switches it. */
export function useSimMode() {
  const { sim, refreshSim } = useLiveData()
  const [busy, setBusy] = useState(false)
  const mode: SimMode = sim?.mode ?? 'demo'
  const setMode = async (next: SimMode) => {
    if (next === mode && (next === 'live' || sim?.running)) return
    setBusy(true)
    try {
      await api.post('/api/simulation/mode', { mode: next }, SimStatusSchema)
      if (next === 'demo') await api.post('/api/simulation/start', {}, SimStatusSchema)
      await refreshSim()
    } finally { setBusy(false) }
  }
  return { mode, setMode, busy, paused: mode === 'demo' && !!sim && !sim.running }
}
