import { useState } from 'react'
import RecoveryModal from '../components/RecoveryModal'
import { useEngineNow } from '../hooks/useEngineNow'
import { useLiveData, useShipments } from '../hooks/useLiveData'
import { PRIORITY_META, STATUS_COLORS } from '../lib/constants'
import { parseUtc, timeLeft, title } from '../lib/format'

const STATUSES = ['in_transit', 'misplaced', 'piggybacked', 'recovered', 'delivered', 'delayed', 'at_origin']

export default function Shipments() {
  const { shipments } = useLiveData()
  const now = useEngineNow()
  const [q, setQ] = useState('')
  const [status, setStatus] = useState<string[]>([])
  const [priority, setPriority] = useState<string[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const rows = useShipments({ q, status, priority })

  return (
    <div className="p-4 space-y-4">
      <div className="flex flex-wrap gap-3 items-center">
        <h1 className="text-xl font-bold mr-4">Shipments <span className="text-sm text-muted">({rows.length})</span></h1>
        <input className="input w-64" placeholder="Search ID or tracking number" value={q} maxLength={40} onChange={(e) => setQ(e.target.value)} />
        <select className="input" value={status[0] ?? ''} onChange={(e) => setStatus(e.target.value ? [e.target.value] : [])}>
          <option value="">All statuses</option>
          {STATUSES.map((s) => <option key={s} value={s}>{title(s)}</option>)}
        </select>
        <select className="input" value={priority[0] ?? ''} onChange={(e) => setPriority(e.target.value ? [e.target.value] : [])}>
          <option value="">All priorities</option>
          {Object.entries(PRIORITY_META).map(([k, v]) => <option key={k} value={k}>{v.emoji} {v.label}</option>)}
        </select>
      </div>
      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs text-muted text-left">
            <tr>{['ID', 'Priority', 'Status', 'Route', 'At / on', 'Weight', 'Deadline', 'Flags', 'Recovery'].map((h) => <th key={h} className="px-3 py-2">{h}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((s) => {
              const left = (parseUtc(s.deadline).getTime() - now.getTime()) / 3.6e6
              return (
                <tr key={s.id} className="border-t border-[var(--border-subtle)] hover:bg-surface/50 cursor-pointer" onClick={() => s.status === 'misplaced' && setSelected(s.id)}>
                  <td className="px-3 py-2 mono">{s.id}</td>
                  <td className="px-3">{PRIORITY_META[s.priority].emoji} {PRIORITY_META[s.priority].label}</td>
                  <td className="px-3"><span className="text-xs px-2 py-0.5 rounded-full" style={{ background: `${STATUS_COLORS[s.status]}22`, color: STATUS_COLORS[s.status] }}>{title(s.status)}</span>
                    {s.misplacement_type && <span className="text-xs text-warning ml-1">{title(s.misplacement_type)}</span>}</td>
                  <td className="px-3 text-xs">{s.expected_route.map((h) => h.replace('HUB-', '')).join(' › ')}</td>
                  <td className="px-3 text-xs mono">{s.current_hub_id ?? s.current_vehicle_id ?? '—'}</td>
                  <td className="px-3 text-xs">{s.weight_kg} kg</td>
                  <td className={`px-3 text-xs ${left < 0 ? 'text-danger' : ''}`}>{['delivered', 'recovered'].includes(s.status) ? '—' : timeLeft(left)}</td>
                  <td className="px-3 text-xs">{s.handling_flags.join(', ') || '—'}</td>
                  <td className="px-3 text-xs">{s.recovery_strategy ? `${title(s.recovery_strategy)} ${s.recovery_score?.toFixed(0) ?? ''}` : '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {selected && shipments[selected] && (
        <RecoveryModal shipment={shipments[selected]} onClose={() => setSelected(null)} onViewRoute={() => setSelected(null)} />
      )}
    </div>
  )
}
