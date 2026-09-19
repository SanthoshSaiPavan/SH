import { useSimMode } from '../hooks/useSimMode'

/** LIVE GPS | DEMO SIMULATION toggle (same control as the Simulation page). */
export default function ModeToggle() {
  const { mode, setMode, busy, paused } = useSimMode()
  return (
    <div role="radiogroup" aria-label="Data mode"
      className="flex rounded-full bg-white p-1 border border-black/5 shadow-[0_2px_10px_rgba(0,0,0,0.03)] text-[11px] font-semibold">
      {(['live', 'demo'] as const).map((m) => (
        <button key={m} role="radio" aria-checked={mode === m} disabled={busy} onClick={() => setMode(m)}
          className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 transition-colors disabled:opacity-60 ${mode === m ? 'bg-[var(--foreground)] text-white' : 'text-[var(--muted-foreground)] hover:text-[var(--foreground)]'}`}>
          <span className={`w-1.5 h-1.5 rounded-full ${m === 'live' ? 'bg-[var(--success)]' : 'bg-[var(--accent)]'}`} />
          {m === 'live' ? 'LIVE GPS' : `DEMO${paused ? ' (paused)' : ''}`}
        </button>
      ))}
    </div>
  )
}
