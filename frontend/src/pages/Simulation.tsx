import { useState } from 'react'
import { z } from 'zod'
import { useLiveData } from '../hooks/useLiveData'
import { api } from '../lib/api'
import { CONNECTION_COLORS } from '../lib/constants'
import { title } from '../lib/format'
import { SimStatusSchema } from '../lib/schemas'

const MisplaceResult = z.object({ shipment_id: z.string(), type: z.string(), detail: z.string() })
const MisplaceForm = z.object({
  shipment_id: z.string().max(64).optional(),
  type: z.enum(['wrong_hub', 'wrong_vehicle', 'stuck']).optional(),
})

export default function Simulation() {
  const { sim, refreshSim, vehicles, shipments, hubs } = useLiveData()
  const [msg, setMsg] = useState<string | null>(null)
  const [misplace, setMisplace] = useState<{ shipment_id: string; type: string }>({ shipment_id: '', type: '' })
  const [edits, setEdits] = useState<Record<string, { speed: string; route: string }>>({})

  const run = async (fn: () => Promise<unknown>, ok?: string) => {
    try { await fn(); await refreshSim(); if (ok) setMsg(ok) } catch (e) { setMsg(e instanceof Error ? e.message : String(e)) }
  }
  const post = (path: string, body: unknown = {}) => api.post(path, body, SimStatusSchema)

  const triggerMisplacement = () => run(async () => {
    const form = MisplaceForm.parse({ shipment_id: misplace.shipment_id || undefined, type: misplace.type || undefined })
    const res = await api.post('/api/simulation/trigger-misplacement', form, MisplaceResult)
    setMsg(`${res.shipment_id}: ${title(res.type)} (${res.detail})`)
  })

  const controlVehicle = (id: string) => run(async () => {
    const e = edits[id]
    const body: Record<string, unknown> = {}
    if (e?.speed) body.speed_kmh = Number(e.speed)
    if (e?.route) body.remaining_route = [e.route]
    await api.patch(`/api/simulation/vehicles/${id}`, body, z.unknown())
  }, `${id} updated`)

  const inTransit = Object.values(shipments).filter((s) => s.status === 'in_transit' && !s.recovery_strategy)
  const demoTrucks = Object.values(vehicles).sort((a, b) => Number(b.id.startsWith('TRUCK')) - Number(a.id.startsWith('TRUCK')) || a.id.localeCompare(b.id))

  return (
    <div className="p-4 space-y-4 max-w-6xl">
      <h1 className="text-xl font-bold">Simulation control</h1>
      <div className="grid md:grid-cols-3 gap-4">
        <div className="card p-4 space-y-3">
          <h3 className="font-semibold">Mode</h3>
          <div className="flex gap-2">
            <button className={`btn ${sim?.mode === 'live' ? 'btn-success' : ''}`} onClick={() => run(() => post('/api/simulation/mode', { mode: 'live' }))}>LIVE GPS</button>
            <button className={`btn ${sim?.mode === 'demo' ? 'btn-primary' : ''}`} onClick={() => run(() => post('/api/simulation/mode', { mode: 'demo' }))}>DEMO SIMULATION</button>
          </div>
          <p className="text-xs text-muted">LIVE GPS accepts positions from drivers' phones (/driver). DEMO SIMULATION moves every vehicle on a compressed clock (2 sim-min per 2 s tick at 1×).</p>
        </div>
        <div className="card p-4 space-y-3">
          <h3 className="font-semibold">Engine</h3>
          <div className="flex gap-2">
            <button className="btn btn-success" disabled={sim?.mode !== 'demo' || sim.running} onClick={() => run(() => post('/api/simulation/start'))}>▶ Start</button>
            <button className="btn btn-danger" disabled={!sim?.running} onClick={() => run(() => post('/api/simulation/stop'))}>■ Stop</button>
          </div>
          <div className="flex gap-1">
            {(sim?.available_speeds ?? [1, 2, 5, 10]).map((s) => (
              <button key={s} className={`btn ${sim?.speed === s ? 'btn-primary' : ''}`} onClick={() => run(() => post('/api/simulation/speed', { speed: s }))}>{s}×</button>
            ))}
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={sim?.auto_recovery ?? false} onChange={(e) => run(() => post('/api/simulation/auto-recovery', { enabled: e.target.checked }))} />
            Auto-recovery (auto-approve pending recommendations)
          </label>
          <div className="text-xs text-muted mono">tick {sim?.tick_number ?? 0} · {sim?.running ? 'running' : 'paused'}</div>
        </div>
        <div className="card p-4 space-y-3">
          <h3 className="font-semibold">Trigger misplacement</h3>
          <select className="input w-full" value={misplace.shipment_id} onChange={(e) => setMisplace({ ...misplace, shipment_id: e.target.value })}>
            <option value="">Random in-transit shipment</option>
            {inTransit.map((s) => <option key={s.id} value={s.id}>{s.id} ({s.priority})</option>)}
          </select>
          <select className="input w-full" value={misplace.type} onChange={(e) => setMisplace({ ...misplace, type: e.target.value })}>
            <option value="">Random type (30/40/30)</option>
            <option value="wrong_hub">Wrong hub</option>
            <option value="wrong_vehicle">Wrong vehicle</option>
            <option value="stuck">Stuck</option>
          </select>
          <button className="btn btn-danger w-full justify-center" onClick={triggerMisplacement}>⚠ Misplace</button>
        </div>
      </div>
      {msg && <div className="text-sm text-accent">{msg}</div>}

      <div className="card p-4">
        <h3 className="font-semibold mb-1">Vehicles</h3>
        <p className="text-xs text-muted mb-3">Slow a truck down or reroute it to a different next stop to see the recommendation switch (e.g. reroute TRUCK-104, the current pick for SHP-501).</p>
        <table className="w-full text-sm">
          <thead className="text-xs text-muted text-left"><tr><th className="py-1">Vehicle</th><th>Status</th><th>Route (next ▸)</th><th>Load</th><th>Speed km/h</th><th>New next stop</th><th /></tr></thead>
          <tbody>
            {demoTrucks.map((v) => {
              const conn = v.live?.connection ?? 'offline'
              return (
                <tr key={v.id} className="border-t border-[var(--border-subtle)]">
                  <td className="py-1.5 mono"><span style={{ color: CONNECTION_COLORS[conn] }}>●</span> {v.id}</td>
                  <td className="text-xs">{title(v.status)}</td>
                  <td className="text-xs">{v.planned_route.map((h, i) => <span key={`${h}-${i}`} className={i === v.current_stop_index ? 'text-accent font-semibold' : i < v.current_stop_index ? 'text-muted/50' : 'text-muted'}>{i === v.current_stop_index ? '▸' : ''}{h.replace('HUB-', '')} </span>)}</td>
                  <td className="text-xs">{Math.round((v.used_capacity_kg / v.total_capacity_kg) * 100)}%</td>
                  <td><input className="input w-20" placeholder={String(Math.round(v.speed_kmh))} value={edits[v.id]?.speed ?? ''}
                    onChange={(e) => setEdits({ ...edits, [v.id]: { speed: e.target.value.replace(/[^0-9.]/g, ''), route: edits[v.id]?.route ?? '' } })} /></td>
                  <td><select className="input" value={edits[v.id]?.route ?? ''} onChange={(e) => setEdits({ ...edits, [v.id]: { speed: edits[v.id]?.speed ?? '', route: e.target.value } })}>
                    <option value="">(keep route)</option>
                    {Object.values(hubs).map((h) => <option key={h.id} value={h.id}>{h.city}</option>)}
                  </select></td>
                  <td><button className="btn" onClick={() => controlVehicle(v.id)}>Apply</button></td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
