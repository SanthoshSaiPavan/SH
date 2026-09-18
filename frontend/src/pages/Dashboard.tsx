import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AlertPanel from '../components/AlertPanel'
import RecoveryModal from '../components/RecoveryModal'
import ScoreGauge from '../components/ScoreGauge'
import StatsCard from '../components/StatsCard'
import { useEngineNow } from '../hooks/useEngineNow'
import { useLiveData } from '../hooks/useLiveData'
import { STRATEGY_META } from '../lib/constants'
import { hours, inr, parseUtc, pct, time, title } from '../lib/format'
import type { Recommendation } from '../lib/schemas'
import type { MapLinkState } from './MapView'

export default function Dashboard() {
  const { shipments, recommendations, activeRecoveries, progress, alerts, dashboard } = useLiveData()
  const now = useEngineNow()
  const navigate = useNavigate()
  const [selected, setSelected] = useState<string | null>(null)

  const showOnMap = (state: MapLinkState) => navigate('/map', { state })

  // Misplaced shipments open the recovery modal; anything else is shown on the map.
  const openShipment = (id: string) => {
    const s = shipments[id]
    if (!s) return
    if (s.status === 'misplaced') setSelected(id)
    else showOnMap({ shipmentId: id })
  }

  const opportunities = Object.values(recommendations)
    .filter((r) => shipments[r.shipment_id]?.status === 'misplaced')
    .sort((a, b) => b.score - a.score)
    .slice(0, 3)

  return (
    <div className="p-4">
      <div className="space-y-4">
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
          <StatsCard icon="📦" label="Active shipments" value={dashboard?.active_shipments ?? '—'} color="#3b82f6" />
          <StatsCard icon="⚠" label="Misplaced today" value={dashboard?.misplaced_today ?? '—'} hint={`${dashboard?.misplaced_now ?? 0} awaiting recovery`} color="#ef4444" />
          <StatsCard icon="🚚" label="Piggybacked now" value={dashboard?.piggybacked_now ?? '—'} color="#a855f7" />
          <StatsCard icon="✔" label="Recovery rate" value={pct(dashboard?.recovery_rate)} hint={`${dashboard?.recoveries_in_progress ?? 0} in progress`} color="#10b981" />
          <StatsCard icon="₹" label="Cost saved today" value={inr(dashboard?.cost_saved_today)} hint={`${inr(dashboard?.cost_saved_total)} total vs dedicated`} color="#64ffda" />
        </div>

        {opportunities.map((r) => <OpportunityBanner key={r.shipment_id} rec={r} onOpen={() => openShipment(r.shipment_id)} />)}

        <div className="grid lg:grid-cols-2 gap-4 h-80">
          <AlertPanel alerts={alerts} onSelect={openShipment} />
          <div className="card p-4 flex flex-col min-h-0">
            <h3 className="font-semibold mb-3">🔄 Active recoveries <span className="text-xs text-muted">({activeRecoveries.length})</span></h3>
            <div className="space-y-2 overflow-y-auto min-h-0 flex-1">
              {activeRecoveries.length === 0 && <div className="text-sm text-muted">No recoveries in progress.</div>}
              {activeRecoveries.map((a) => {
                const s = shipments[a.shipment_id]
                const prog = progress[a.shipment_id]
                const eta = (a.recovery_route as { arrival_time?: string } | null)?.arrival_time
                return (
                  <button key={a.id} className="w-full text-left p-2.5 rounded-lg bg-surface/60 hover:bg-surface" onClick={() => openShipment(a.shipment_id)}>
                    <div className="flex items-center gap-2 text-sm">
                      <span className="mono font-semibold">{a.shipment_id}</span>
                      <span style={{ color: STRATEGY_META[a.action_type].color }}>→ {a.matched_vehicle_id ?? STRATEGY_META[a.action_type].label}</span>
                      <span className="ml-auto mono text-xs">Score {a.overall_score.toFixed(0)}/100</span>
                    </div>
                    <div className="text-xs text-muted mt-1">
                      {s ? title(s.status) : ''} · ETA {eta ? `${time(eta)} (${hours((parseUtc(eta).getTime() - now.getTime()) / 3.6e6)})` : '—'} · {inr(a.additional_cost)}
                    </div>
                    <div className="h-1 bg-bg rounded mt-1.5"><div className="h-full bg-piggy rounded transition-all" style={{ width: `${prog?.percent_complete ?? 3}%` }} /></div>
                  </button>
                )
              })}
            </div>
          </div>
        </div>
      </div>
      {selected && shipments[selected] && (
        <RecoveryModal shipment={shipments[selected]} onClose={() => setSelected(null)}
          onViewRoute={(route) => showOnMap({ shipmentId: selected, route })} />
      )}
    </div>
  )
}

function OpportunityBanner({ rec, onOpen }: { rec: Recommendation; onOpen: () => void }) {
  const meta = STRATEGY_META[rec.strategy]
  const headline = rec.strategy === 'piggyback' ? 'PIGGYBACK OPPORTUNITY DETECTED' : `RECOMMENDED: ${meta.label.toUpperCase()}`
  return (
    <button onClick={onOpen} className="glass w-full p-4 flex items-center gap-4 text-left animate-slide-in hover:border-piggy"
      style={{ borderColor: rec.recovery_mode === 'escalated' ? '#ef4444' : meta.color }}>
      <ScoreGauge score={rec.score} size={58} />
      <div className="flex-1 min-w-0">
        <div className="font-bold tracking-wide" style={{ color: meta.color }}>{meta.icon} {headline}</div>
        <div className="text-sm mt-0.5"><span className="mono font-semibold">{rec.shipment_id}</span>{rec.vehicle_id && <> → <span className="mono">{rec.vehicle_id}</span></>}
          <span className="text-xs text-muted ml-2">{title(rec.recovery_mode)}</span></div>
        {rec.reason && rec.reason !== 'initial recommendation' && <div className="text-xs text-warning mt-0.5">↻ {rec.reason}</div>}
      </div>
      <div className="grid grid-cols-3 gap-x-5 gap-y-1 text-xs text-muted">
        <span>Pickup ETA<br /><b className="text-ink">{time(rec.pickup_eta)}</b></span>
        <span>Delivery ETA<br /><b className="text-ink">{time(rec.delivery_eta)}</b> {rec.deadline_met ? '✅' : '🔴'}</span>
        <span>Free capacity<br /><b className="text-ink">{rec.available_capacity !== null && rec.available_capacity !== undefined ? `${Math.round(rec.available_capacity)} kg` : '—'}</b></span>
        <span>Recovery cost<br /><b className="text-ink">{inr(rec.recovery_cost)}</b></span>
        <span>Saving vs dedicated<br /><b className="text-success">{inr(rec.cost_saving)}</b></span>
      </div>
    </button>
  )
}
