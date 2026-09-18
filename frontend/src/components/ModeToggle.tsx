import { useState } from 'react'
import { api } from '../lib/api'
import { SimStatusSchema } from '../lib/schemas'
import { useLiveData } from '../hooks/useLiveData'

/** LIVE GPS | DEMO SIMULATION toggle (same control as the Simulation page). */
export default function ModeToggle() {
  const { sim, refreshSim } = useLiveData()
  const [busy, setBusy] = useState(false)
  const set = async (mode: 'live' | 'demo') => {
    setBusy(true)
    try {
      await api.post('/api/simulation/mode', { mode }, SimStatusSchema)
      if (mode === 'demo') await api.post('/api/simulation/start', {}, SimStatusSchema)
      await refreshSim()
    } finally { setBusy(false) }
  }
  const mode = sim?.mode ?? 'demo'
  return (
    <div className="flex rounded-lg overflow-hidden border border-[var(--border-subtle)] text-[11px] font-semibold">
      {(['live', 'demo'] as const).map((m) => (
        <button key={m} disabled={busy} onClick={() => set(m)}
          className={`px-2.5 py-1 transition ${mode === m ? (m === 'live' ? 'bg-success text-bg' : 'bg-piggy text-white') : 'text-muted hover:text-ink'}`}>
          {m === 'live' ? 'LIVE GPS' : `DEMO SIMULATION${mode === 'demo' && sim && !sim.running ? ' (paused)' : ''}`}
        </button>
      ))}
    </div>
  )
}
