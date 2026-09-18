import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, RotateCcw } from 'lucide-react'
import AlertPanel from '../components/AlertPanel'
import RecoveryModal from '../components/RecoveryModal'
import ScoreGauge from '../components/ScoreGauge'
import StatsCard from '../components/StatsCard'
import { useEngineNow } from '../hooks/useEngineNow'
import { useLiveData } from '../hooks/useLiveData'
import { hours, inr, parseUtc, pct, time, title } from '../lib/format'
import type { Recommendation } from '../lib/schemas'
import type { MapLinkState } from './MapView'

export default function Dashboard() {
  const { shipments, recommendations, activeRecoveries, progress, dashboard, alerts } = useLiveData()
  const now = useEngineNow()
  const navigate = useNavigate()
  const [selected, setSelected] = useState<string | null>(null)

  const showOnMap = (state: MapLinkState) => navigate('/map', { state })

  const openShipment = (id: string) => {
    const s = shipments[id]
    if (!s) return
    if (s.status === 'misplaced') setSelected(id)
    else showOnMap({ shipmentId: id })
  }

  const opportunities = Object.values(recommendations)
    .filter((r) => shipments[r.shipment_id]?.status === 'misplaced')
    .sort((a, b) => b.score - a.score)
    .slice(0, 2)

  return (
    <div style={{ padding: '32px', maxWidth: '1440px', margin: '0 auto' }}>

      {/* Bento-box Layout */}
      <div style={{ display: 'flex', gap: '24px', alignItems: 'flex-start' }}>

        {/* Left Column: KPIs (White cards on light gray background) */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', width: '320px', flexShrink: 0 }}>
          <div style={{ marginBottom: '8px' }}>
            <h1 style={{ fontSize: '24px', fontWeight: 600, letterSpacing: '-0.03em', margin: 0, color: 'var(--foreground)' }}>
              Fleet performance overview
            </h1>
          </div>

          <StatsCard label="Active Shipments" value={dashboard?.active_shipments ?? '—'} color="default" />
          <StatsCard label="Misplaced Today" value={dashboard?.misplaced_today ?? '—'} hint={`${dashboard?.misplaced_now ?? 0} awaiting recovery`} color="danger" />
          <StatsCard label="Piggybacked" value={dashboard?.piggybacked_now ?? '—'} color="accent" />
          <StatsCard label="Recovery Rate" value={pct(dashboard?.recovery_rate)} hint={`${dashboard?.recoveries_in_progress ?? 0} in progress`} color="success" />
          <StatsCard label="Cost Saved Today" value={inr(dashboard?.cost_saved_today)} hint={`${inr(dashboard?.cost_saved_total)} total`} color="success" />
          
          <div style={{ marginTop: '16px' }}>
            <AlertPanel alerts={alerts} onSelect={openShipment} />
          </div>
        </div>

        {/* Right Column: Dark Panel (The main bento box) */}
        <div className="dark-panel" style={{ flex: 1, padding: '32px', minHeight: '600px' }}>
          
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '32px' }}>
            <h2 style={{ fontSize: '20px', fontWeight: 500, letterSpacing: '-0.02em', margin: 0, color: 'var(--dark-foreground)' }}>
              Intelligent Recovery Center
            </h2>
          </div>

          {/* Opportunities Section */}
          {opportunities.length > 0 && (
            <div style={{ marginBottom: '40px' }}>
              <div style={{ fontSize: '13px', color: 'var(--dark-subtle)', marginBottom: '16px', fontWeight: 500 }}>
                High-Impact Opportunities
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(380px, 1fr))', gap: '16px' }}>
                {opportunities.map((r) => (
                  <OpportunityBanner key={r.shipment_id} rec={r} onOpen={() => openShipment(r.shipment_id)} />
                ))}
              </div>
            </div>
          )}

          {/* Active Recoveries List */}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', color: 'var(--dark-subtle)', marginBottom: '16px', fontWeight: 500 }}>
              <RotateCcw size={14} />
              Active Recoveries in Progress
            </div>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {activeRecoveries.length === 0 && (
                <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--dark-subtle)' }}>
                  No active recoveries
                </div>
              )}
              {activeRecoveries.map((a) => {
                const s = shipments[a.shipment_id]
                const prog = progress[a.shipment_id]
                const eta = (a.recovery_route as { arrival_time?: string } | null)?.arrival_time
                const p = prog?.percent_complete ?? 3
                return (
                  <button
                    key={a.id}
                    onClick={() => openShipment(a.shipment_id)}
                    style={{
                      width: '100%', textAlign: 'left',
                      padding: '16px 20px',
                      background: 'var(--dark-surface-2)',
                      border: '1px solid var(--dark-border)',
                      borderRadius: 'var(--radius-lg)',
                      cursor: 'pointer',
                      transition: 'all 150ms',
                    }}
                    onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = '#2A2A2E'}
                    onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = 'var(--dark-surface-2)'}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '14px', fontWeight: 600, color: 'var(--dark-foreground)' }}>
                        {a.shipment_id}
                      </span>
                      <ArrowRight size={14} style={{ color: 'var(--dark-subtle)' }} />
                      <span style={{ fontSize: '13px', color: 'var(--accent)' }}>
                        {a.matched_vehicle_id ?? title(a.action_type)}
                      </span>
                      <span style={{ marginLeft: 'auto', fontSize: '12px', color: 'var(--dark-subtle)' }}>
                        Score: <b style={{ color: 'var(--dark-foreground)' }}>{a.overall_score.toFixed(0)}/100</b>
                      </span>
                    </div>
                    
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: 'var(--dark-muted)', marginBottom: '12px' }}>
                      <span>
                        {s ? title(s.status) : ''}
                        {eta ? ` · ETA ${time(eta)} (${hours((parseUtc(eta).getTime() - now.getTime()) / 3.6e6)})` : ''}
                      </span>
                      <span style={{ fontFamily: 'var(--font-mono)' }}>Cost: {inr(a.additional_cost ?? 0)}</span>
                    </div>

                    <div style={{ height: '4px', background: 'var(--dark-border)', borderRadius: '9999px', overflow: 'hidden' }}>
                      <div style={{ height: '100%', background: 'var(--accent)', borderRadius: '9999px', width: `${p}%` }} />
                    </div>
                  </button>
                )
              })}
            </div>
          </div>
        </div>
      </div>

      {selected && shipments[selected] && (
        <RecoveryModal
          shipment={shipments[selected]}
          onClose={() => setSelected(null)}
          onViewRoutes={(routes) => showOnMap({ shipmentId: selected, route: routes[0]?.hubs })}
        />
      )}
    </div>
  )
}

function OpportunityBanner({ rec, onOpen }: { rec: Recommendation; onOpen: () => void }) {
  const isEscalated = rec.recovery_mode === 'escalated'
  const label = rec.strategy === 'piggyback' ? 'Piggyback opportunity' : `Recommended: ${title(rec.strategy)}`
  
  return (
    <button
      onClick={onOpen}
      className="animate-slide-in"
      style={{
        width: '100%', textAlign: 'left',
        display: 'flex', alignItems: 'center', gap: '20px',
        padding: '20px',
        background: 'var(--dark-surface-2)',
        border: '1px solid var(--dark-border)',
        borderRadius: 'var(--radius-xl)',
        cursor: 'pointer',
        transition: 'all 150ms',
      }}
      onMouseEnter={e => {
        const el = e.currentTarget as HTMLElement;
        el.style.borderColor = 'rgba(255,255,255,0.2)';
        el.style.background = '#2A2A2E';
      }}
      onMouseLeave={e => {
        const el = e.currentTarget as HTMLElement;
        el.style.borderColor = 'var(--dark-border)';
        el.style.background = 'var(--dark-surface-2)';
      }}
    >
      <ScoreGauge score={rec.score} size={64} />

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
          <span style={{ fontSize: '11px', fontWeight: 600, color: isEscalated ? 'var(--destructive)' : 'var(--accent)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            {label}
          </span>
          {isEscalated && (
            <span style={{ fontSize: '10px', fontWeight: 600, color: 'var(--destructive)', background: 'rgba(224,100,100,0.12)', padding: '2px 8px', borderRadius: '4px' }}>
              ESCALATED
            </span>
          )}
        </div>
        
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '16px', fontWeight: 600, color: 'var(--dark-foreground)' }}>
            {rec.shipment_id}
          </span>
          {rec.vehicle_id && (
            <>
              <ArrowRight size={14} style={{ color: 'var(--dark-subtle)' }} />
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '14px', color: 'var(--dark-muted)' }}>
                {rec.vehicle_id}
              </span>
            </>
          )}
        </div>
        
        <div style={{ display: 'flex', gap: '24px' }}>
          <Metric label="Delivery ETA" value={time(rec.delivery_eta)} valueColor={rec.deadline_met ? '#FFFFFF' : 'var(--destructive)'} />
          <Metric label="Saving" value={inr(rec.cost_saving)} valueColor="var(--accent)" />
        </div>
      </div>
    </button>
  )
}

function Metric({ label, value, valueColor }: { label: string; value: string; valueColor?: string }) {
  return (
    <div>
      <div style={{ fontSize: '11px', color: 'var(--dark-subtle)', marginBottom: '4px' }}>{label}</div>
      <div style={{ fontSize: '14px', fontWeight: 600, fontFamily: 'var(--font-mono)', color: valueColor ?? 'var(--dark-foreground)' }}>
        {value}
      </div>
    </div>
  )
}
