import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { z } from 'zod'
import RecoveryModal from '../components/RecoveryModal'
import ShipmentCard from '../components/ShipmentCard'
import { useEngineNow } from '../hooks/useEngineNow'
import { useLiveData } from '../hooks/useLiveData'
import { api } from '../lib/api'
import { STRATEGY_META } from '../lib/constants'
import { inr, time, title } from '../lib/format'
import { ActionSchema, type RecoveryAction } from '../lib/schemas'
import type { MapLinkState } from './MapView'

export default function Recovery() {
  const { shipments, recommendations, progress, activeRecoveries } = useLiveData()
  const navigate = useNavigate()
  const now = useEngineNow()
  const [selected, setSelected] = useState<string | null>(null)
  const [history, setHistory] = useState<RecoveryAction[]>([])

  // History is loaded on page entry and whenever the set of active recoveries changes.
  useEffect(() => {
    api.get('/api/recovery/history', z.array(ActionSchema)).then(setHistory).catch(() => undefined)
  }, [activeRecoveries.length])

  const awaiting = Object.values(shipments).filter((s) => s.status === 'misplaced')
    .sort((a, b) => (recommendations[b.id]?.score ?? 0) - (recommendations[a.id]?.score ?? 0))
  const recovering = Object.values(shipments).filter((s) => s.recovery_strategy && !['recovered', 'delivered'].includes(s.status))

  return (
    <div style={{ padding: '32px', maxWidth: '1440px', margin: '0 auto', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '24px', alignItems: 'start' }}>
      <section>
        <h2 className="font-semibold mb-3">⚠ Awaiting decision <span className="text-muted text-sm">({awaiting.length})</span></h2>
        <div className="space-y-2">
          {awaiting.length === 0 && <div className="text-sm text-muted">No misplaced shipments.</div>}
          {awaiting.map((s) => <ShipmentCard key={s.id} shipment={s} recommendation={recommendations[s.id]} now={now} onClick={() => setSelected(s.id)} />)}
        </div>
      </section>
      <section>
        <h2 className="font-semibold mb-3">🔄 In progress <span className="text-muted text-sm">({recovering.length})</span></h2>
        <div className="space-y-2">
          {recovering.length === 0 && <div className="text-sm text-muted">No active recoveries.</div>}
          {recovering.map((s) => <ShipmentCard key={s.id} shipment={s} progress={progress[s.id]} now={now} />)}
        </div>
      </section>
      <section>
        <h2 className="font-semibold mb-3">📜 History <span className="text-muted text-sm">({history.length})</span></h2>
        <div className="space-y-2">
          {history.map((a) => {
            const baseline = (a.recovery_route as { dedicated_cost?: number } | null)?.dedicated_cost ?? 0
            return (
              <div key={a.id} className="card p-3 text-xs">
                <div className="flex items-center gap-2 text-sm">
                  <span className="mono font-semibold">{a.shipment_id}</span>
                  <span style={{ color: STRATEGY_META[a.action_type].color }}>{STRATEGY_META[a.action_type].label}</span>
                  <span className={`ml-auto ${a.status === 'completed' ? 'text-success' : 'text-danger'}`}>{title(a.status)}</span>
                </div>
                <div className="text-muted mt-1">
                  {a.matched_vehicle_id ?? '—'} · score {a.overall_score.toFixed(0)} · cost {inr(a.additional_cost)}
                  {a.status === 'completed' && <> · saved <b className="text-success">{inr(baseline - (a.additional_cost ?? 0))}</b></>} · {time(a.completed_at)}
                </div>
              </div>
            )
          })}
        </div>
      </section>
      {selected && shipments[selected] && (
        <RecoveryModal shipment={shipments[selected]} onClose={() => setSelected(null)} onViewRoutes={(routes) => navigate('/map', { state: { shipmentId: selected, routes } satisfies MapLinkState })} />
      )}
    </div>
  )
}
