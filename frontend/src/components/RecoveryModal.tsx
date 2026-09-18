import { useCallback, useEffect, useState } from 'react'
import { z } from 'zod'
import { api, ApiError } from '../lib/api'
import { PRIORITY_META, STRATEGY_META } from '../lib/constants'
import { hours, inr, parseUtc, pct, time, timeLeft, title } from '../lib/format'
import { EvaluationSchema, type Evaluation, type Shipment, type Strategy } from '../lib/schemas'
import { useAuth } from '../hooks/useAuth'
import { useEngineNow } from '../hooks/useEngineNow'
import { useSocket, useSocketEvent } from '../hooks/useSocket'
import { X, Brain, ScrollText, Send, AlertTriangle, CheckCircle2, ChevronRight, Scale3D } from 'lucide-react'
import ScoreGauge, { ScoreBar } from './ScoreGauge'
import CounterfactualSimulator from './CounterfactualSimulator'

import type { RouteOverlay } from './LiveMap'

type Props = { shipment: Shipment; onClose: () => void; onViewRoutes: (routes: RouteOverlay[]) => void }

const ExplainSchema = z.object({
  explanation: z.string(), grounded_summary: z.string(), source: z.string(),
  model: z.string().nullable(),
  risk: z.object({ deadline_risk: z.boolean(), capacity_risk: z.boolean(), route_risk: z.boolean(), cost_delta: z.number().nullable(), notes: z.array(z.string()) }),
})
const AnswerSchema = z.object({ answer: z.string(), source: z.string() })
const WhatIfSchema = z.object({
  delta: z.object({ score: z.number(), cost: z.number(), buffer_hours: z.number() }),
  hypothetical_meets_deadline: z.boolean(),
}).loose()
const AuditSchema = z.array(z.object({
  id: z.string(), explanation: z.string(), operator_query: z.string().nullable(),
  operator_decision: z.string().nullable(), confidence_score: z.number().nullable(), created_at: z.string().nullable(),
}))
const ExecuteSchema = z.object({ ok: z.boolean(), action_id: z.string().optional() })

const MODE_LABEL: Record<string, { color: string; bg: string; label: string }> = {
  auto_executed:    { color: 'var(--success)',     bg: 'rgba(139,207,114,0.10)', label: 'Auto-executed' },
  pending_approval: { color: 'var(--accent)',      bg: 'rgba(184,217,106,0.10)', label: 'Pending Approval' },
  escalated:        { color: 'var(--destructive)', bg: 'rgba(224,100,100,0.10)', label: 'Escalated' },
}

export default function RecoveryModal({ shipment, onClose, onViewRoutes }: Props) {
  const { isOperator } = useAuth()
  const now = useEngineNow()
  const { joinRoom, leaveRoom } = useSocket()
  const [ev, setEv] = useState<Evaluation | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [explain, setExplain] = useState<z.infer<typeof ExplainSchema> | null>(null)
  const [explaining, setExplaining] = useState(false)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<string | null>(null)
  const [whatIf, setWhatIf] = useState<Record<string, z.infer<typeof WhatIfSchema>>>({})
  const [audit, setAudit] = useState<z.infer<typeof AuditSchema> | null>(null)
  const [rejectReason, setRejectReason] = useState('')
  const [tab, setTab] = useState<'strategies' | 'simulator' | 'agent' | 'audit'>('strategies')

  const load = useCallback(async () => {
    try {
      setEv(await api.get(`/api/recovery/options/${shipment.id}`, EvaluationSchema))
      setError(null)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e))
    }
  }, [shipment.id])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    const room = `shipment:${shipment.id}`
    joinRoom(room)
    return () => leaveRoom(room)
  }, [shipment.id, joinRoom, leaveRoom])
  useSocketEvent<{ shipment_id: string }>('piggyback:recommendation', (d) => { if (d.shipment_id === shipment.id) load() })
  useSocketEvent<{ shipment_id: string }>('recovery:started', (d) => { if (d.shipment_id === shipment.id) onClose() })

  const approve = async (strategy: Strategy) => {
    setBusy(true)
    try {
      await api.post('/api/recovery/execute', { shipment_id: shipment.id, strategy_id: strategy.id }, ExecuteSchema)
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally { setBusy(false) }
  }

  const reject = async () => {
    setBusy(true)
    try {
      await api.post('/api/recovery/reject', { shipment_id: shipment.id, reason: rejectReason }, z.unknown())
      await load()
    } finally { setBusy(false) }
  }

  const runExplain = async () => {
    setExplaining(true)
    try { setExplain(await api.get(`/api/agent/explain/${shipment.id}`, ExplainSchema)) }
    catch (e) { setError(e instanceof Error ? e.message : String(e)) }
    finally { setExplaining(false) }
  }

  const ask = async () => {
    if (question.trim().length < 3) return
    setAnswer('…')
    const res = await api.post('/api/agent/query', { question, shipment_id: shipment.id }, AnswerSchema)
    setAnswer(`${res.answer}${res.source === 'template' ? ' (grounded template)' : ''}`)
  }

  const runWhatIf = async (type: string) => {
    const res = await api.post('/api/agent/what-if', { shipment_id: shipment.id, hypothetical_strategy: type }, WhatIfSchema)
    setWhatIf((w) => ({ ...w, [type]: res }))
  }

  const loadAudit = async () => setAudit(await api.get(`/api/agent/audit-trail/${shipment.id}`, AuditSchema))

  const p = PRIORITY_META[shipment.priority]
  const left = (parseUtc(shipment.deadline).getTime() - now.getTime()) / 3.6e6
  const mode = ev ? MODE_LABEL[ev.recovery_mode] : null
  const recommendedId = ev?.recommended?.id

  const TABS = [
    { id: 'strategies' as const, label: 'Recovery Options' },
    { id: 'simulator' as const, label: 'Scenario Simulator' },
    { id: 'agent' as const, label: 'Decision Agent' },
    { id: 'audit' as const, label: 'Audit Trail' },
  ]

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 100,
        background: 'rgba(0,0,0,0.65)',
        backdropFilter: 'blur(6px)',
        display: 'grid', placeItems: 'center', padding: '24px',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-xl)',
          boxShadow: 'var(--shadow-modal)',
          width: '100%', maxWidth: '960px',
          maxHeight: '90vh', overflow: 'hidden',
          display: 'flex', flexDirection: 'column',
        }}
      >
        {/* Header */}
        <div style={{
          padding: '20px 24px 0',
          borderBottom: '1px solid var(--border)',
          flexShrink: 0,
        }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '16px', marginBottom: '16px' }}>
            {/* Left: info */}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: '11px', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--subtle-foreground)', marginBottom: '6px' }}>
                Recovery Console
              </div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '12px', flexWrap: 'wrap' }}>
                <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 600, letterSpacing: '-0.025em', fontFamily: 'var(--font-mono)', color: 'var(--foreground)' }}>
                  {shipment.id}
                </h2>
                <span style={{ fontSize: '12px', fontWeight: 600, color: p.color }}>{p.label.toUpperCase()}</span>
                <span style={{ fontSize: '12px', color: left < 2 ? 'var(--destructive)' : 'var(--muted-foreground)' }}>
                  Deadline {timeLeft(left)}
                </span>
                <span style={{ fontSize: '12px', color: 'var(--subtle-foreground)' }}>
                  {shipment.weight_kg} kg · {shipment.volume_cbm} m³
                </span>
                {shipment.misplacement_type && (
                  <span style={{ fontSize: '12px', color: 'var(--warning)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <AlertTriangle size={12} />
                    {title(shipment.misplacement_type)}
                    {shipment.current_hub_id
                      ? ` at ${shipment.current_hub_id}`
                      : shipment.current_vehicle_id ? ` on ${shipment.current_vehicle_id}` : ''}
                  </span>
                )}
                <ChevronRight size={14} style={{ color: 'var(--subtle-foreground)' }} />
                <span style={{ fontSize: '12px', color: 'var(--muted-foreground)', fontFamily: 'var(--font-mono)' }}>
                  {shipment.destination_hub_id}
                </span>
              </div>
            </div>

            {/* Mode badge */}
            {mode && (
              <span style={{
                fontSize: '11px', fontWeight: 600, letterSpacing: '0.04em',
                color: mode.color, background: mode.bg,
                border: `1px solid ${mode.color}33`,
                borderRadius: '6px', padding: '3px 10px',
                flexShrink: 0,
              }}>
                {mode.label}
              </span>
            )}

            {/* Close */}
            <button
              onClick={onClose}
              style={{
                width: '32px', height: '32px', flexShrink: 0,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: 'transparent', border: '1px solid var(--border)',
                borderRadius: '7px', color: 'var(--muted-foreground)',
                cursor: 'pointer', transition: 'all 150ms',
              }}
              onMouseEnter={e => { const el = e.currentTarget as HTMLElement; el.style.background = 'var(--surface-secondary)'; el.style.color = 'var(--foreground)'; }}
              onMouseLeave={e => { const el = e.currentTarget as HTMLElement; el.style.background = 'transparent'; el.style.color = 'var(--muted-foreground)'; }}
            >
              <X size={15} />
            </button>
          </div>

          {/* Tabs */}
          <div style={{ display: 'flex', gap: '0' }}>
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                style={{
                  padding: '12px 16px',
                  fontSize: '13px', fontWeight: tab === t.id ? 500 : 400,
                  color: tab === t.id ? 'var(--foreground)' : 'var(--muted-foreground)',
                  background: 'transparent',
                  border: 'none',
                  borderBottom: tab === t.id ? '2px solid var(--foreground)' : '2px solid transparent',
                  cursor: 'pointer',
                  transition: 'color 150ms',
                  marginBottom: '-1px',
                }}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
          {error && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: '8px',
              padding: '10px 14px', marginBottom: '16px',
              background: 'var(--destructive-bg)',
              border: '1px solid rgba(224,100,100,0.25)',
              borderRadius: '8px',
              fontSize: '13px', color: 'var(--destructive)',
            }}>
              <AlertTriangle size={14} />
              {error}
            </div>
          )}

          {!ev && !error && (
            <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--subtle-foreground)', fontSize: '13px' }}>
              Evaluating recovery strategies…
            </div>
          )}

          {ev && (
            <>
              {/* ── Tab: Strategies ─────────────────────────────────── */}
              {tab === 'strategies' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {ev.recommendation_reason && (
                    <div style={{ fontSize: '12px', color: 'var(--subtle-foreground)', marginBottom: '8px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <span>{ev.recommendation_reason}</span>
                      <button className="btn btn-accent" style={{ flexShrink: 0, height: '28px', fontSize: '12px' }} onClick={() => {
                        const routes = ev.strategies.filter(s => s.feasible).map(s => ({
                          id: s.id,
                          hubs: s.hubs,
                          color: STRATEGY_META[s.type].color,
                        }))
                        onViewRoutes(routes)
                      }}>
                        View all options on map
                      </button>
                    </div>
                  )}
                  {ev.strategies.map((s) => (
                    <StrategyRow
                      key={s.id} s={s} ev={ev}
                      recommended={s.id === recommendedId}
                      canApprove={isOperator && !busy}
                      onApprove={() => approve(s)}
                      onView={() => onViewRoutes([{ id: s.id, hubs: s.hubs, color: STRATEGY_META[s.type].color }])}
                      onWhatIf={() => runWhatIf(s.type)}
                      whatIf={whatIf[s.type]}
                    />
                  ))}

                  {/* Reject bar */}
                  {isOperator && ev.recovery_mode !== 'escalated' && (
                    <div style={{ display: 'flex', gap: '8px', marginTop: '8px', alignItems: 'center' }}>
                      <input
                        className="input" style={{ flex: 1 }}
                        placeholder="Reason for rejection (optional)"
                        value={rejectReason} maxLength={500}
                        onChange={(e) => setRejectReason(e.target.value)}
                      />
                      <button className="btn btn-danger" disabled={busy} onClick={reject}>
                        Reject & escalate
                      </button>
                    </div>
                  )}

                  {/* Candidates table */}
                  {ev.piggyback_candidates.length > 0 && (
                    <div style={{ marginTop: '16px' }}>
                      <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--muted-foreground)', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                        Piggyback Candidates
                      </div>
                      <table className="data-table" style={{ fontSize: '12px' }}>
                        <thead>
                          <tr>
                            <th>Vehicle(s)</th><th>Path</th><th>Pickup</th><th>Arrive</th>
                            <th>Detour</th><th>Cost</th>
                            {Object.keys(ev.piggyback_weights).map((k) => <th key={k}>{title(k)}</th>)}
                            <th>Score</th>
                          </tr>
                        </thead>
                        <tbody>
                          {ev.piggyback_candidates.map((c) => (
                            <tr key={c.vehicle_id}>
                              <td className="primary mono">{c.vehicles.join(' → ')}</td>
                              <td>{c.hubs.map((h) => h.replace('HUB-', '')).join('›')}</td>
                              <td>{time(c.pickup_time)}</td>
                              <td>{time(c.arrival_time)}</td>
                              <td>{c.detour_km.toFixed(0)} km</td>
                              <td>{inr(c.cost)}</td>
                              {['proximity', 'capacity', 'deadline', 'overlap', 'cost_savings'].map((k) => (
                                <td key={k} style={{ fontFamily: 'var(--font-mono)' }}>{(c.scores[k] ?? 0).toFixed(2)}</td>
                              ))}
                              <td className="primary mono" style={{ color: 'var(--foreground)', fontWeight: 600 }}>{c.score.toFixed(1)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}

              {/* ── Tab: Simulator ───────────────────────────────────── */}
              {tab === 'simulator' && (
                <CounterfactualSimulator
                  shipment={shipment}
                  strategies={ev.strategies}
                  now={now}
                  dedicatedCostBaseline={ev.dedicated_cost}
                />
              )}

              {/* ── Tab: Agent ───────────────────────────────────────── */}
              {tab === 'agent' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', maxWidth: '680px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Brain size={15} style={{ color: 'var(--accent)' }} />
                    <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--foreground)' }}>Decision Agent</span>
                    <button className="btn" style={{ marginLeft: 'auto' }} disabled={explaining} onClick={runExplain}>
                      {explaining ? 'Thinking…' : 'Explain recommendation'}
                    </button>
                  </div>

                  {explain && (
                    <div style={{ padding: '16px', background: 'var(--surface-secondary)', border: '1px solid var(--border)', borderRadius: '10px' }}>
                      <p style={{ margin: '0 0 12px', fontSize: '13px', lineHeight: 1.6, color: 'var(--foreground)' }}>
                        {explain.explanation}
                      </p>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '10px' }}>
                        {(['deadline_risk', 'capacity_risk', 'route_risk'] as const).map((k) => (
                          <span key={k} style={{
                            display: 'inline-flex', alignItems: 'center', gap: '4px',
                            fontSize: '11px', fontWeight: 500,
                            padding: '3px 8px', borderRadius: '6px',
                            color: explain.risk[k] ? 'var(--destructive)' : 'var(--success)',
                            background: explain.risk[k] ? 'rgba(224,100,100,0.10)' : 'rgba(139,207,114,0.10)',
                            border: `1px solid ${explain.risk[k] ? 'rgba(224,100,100,0.20)' : 'rgba(139,207,114,0.20)'}`,
                          }}>
                            {title(k)}: {explain.risk[k] ? 'Yes' : 'No'}
                          </span>
                        ))}
                        {explain.risk.cost_delta !== null && (
                          <span style={{ fontSize: '11px', color: 'var(--muted-foreground)', padding: '3px 8px', background: 'var(--surface-tertiary)', borderRadius: '6px', border: '1px solid var(--border)' }}>
                            vs dedicated: {inr(explain.risk.cost_delta)}
                          </span>
                        )}
                      </div>
                      {explain.risk.notes.map((n) => (
                        <div key={n} style={{ display: 'flex', alignItems: 'flex-start', gap: '6px', fontSize: '12px', color: 'var(--warning)', marginTop: '4px' }}>
                          <AlertTriangle size={12} style={{ flexShrink: 0, marginTop: '1px' }} />
                          {n}
                        </div>
                      ))}
                    </div>
                  )}

                  {answer && (
                    <div style={{ padding: '12px 14px', background: 'var(--surface-secondary)', border: '1px solid var(--border)', borderRadius: '8px', fontSize: '13px', color: 'var(--foreground)' }}>
                      {answer}
                    </div>
                  )}

                  <div style={{ display: 'flex', gap: '8px' }}>
                    <input
                      className="input" style={{ flex: 1 }}
                      placeholder="Ask the agent a question…"
                      value={question} maxLength={1000}
                      onChange={(e) => setQuestion(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && ask()}
                    />
                    <button className="btn" onClick={ask}>
                      <Send size={13} /> Ask
                    </button>
                  </div>
                </div>
              )}

              {/* ── Tab: Audit ───────────────────────────────────────── */}
              {tab === 'audit' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                    <ScrollText size={15} style={{ color: 'var(--muted-foreground)' }} />
                    <span style={{ fontSize: '13px', fontWeight: 600 }}>Decision Audit Trail</span>
                    <button className="btn" style={{ marginLeft: 'auto' }} onClick={loadAudit}>Load</button>
                  </div>
                  {!audit && (
                    <div style={{ fontSize: '13px', color: 'var(--subtle-foreground)', padding: '20px 0' }}>
                      Click "Load" to view all logged decisions for this shipment.
                    </div>
                  )}
                  {audit?.length === 0 && (
                    <div style={{ fontSize: '13px', color: 'var(--subtle-foreground)' }}>No decisions logged yet.</div>
                  )}
                  {audit?.map((a) => (
                    <div key={a.id} style={{
                      padding: '12px 14px',
                      background: 'var(--surface-secondary)',
                      border: '1px solid var(--border)',
                      borderRadius: '8px',
                    }}>
                      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', fontSize: '11px', color: 'var(--subtle-foreground)', marginBottom: '6px', fontFamily: 'var(--font-mono)' }}>
                        <span>{time(a.created_at)}</span>
                        {a.operator_decision && <span style={{ color: 'var(--accent)', fontWeight: 600 }}>{a.operator_decision}</span>}
                        {a.confidence_score !== null && <span>Confidence {(a.confidence_score * 100).toFixed(0)}%</span>}
                      </div>
                      {a.operator_query && <div style={{ fontSize: '12px', color: 'var(--muted-foreground)', fontStyle: 'italic', marginBottom: '4px' }}>Q: "{a.operator_query}"</div>}
                      <div style={{ fontSize: '13px', color: 'var(--foreground)', lineHeight: 1.5 }}>{a.explanation}</div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

type RowProps = {
  s: Strategy; ev: Evaluation; recommended: boolean; canApprove: boolean
  onApprove: () => void; onView: () => void; onWhatIf: () => void; whatIf?: z.infer<typeof WhatIfSchema>
}

function StrategyRow({ s, ev, recommended, canApprove, onApprove, onView, onWhatIf, whatIf }: RowProps) {
  const meta = STRATEGY_META[s.type]
  const saving = ev.dedicated_cost > 0 ? 1 - s.cost / ev.dedicated_cost : 0
  const deadlineLabel = !s.feasible ? '—' : s.deadline_met ? (s.buffer_hours < 2 ? 'Tight' : 'Safe') : 'WILL MISS'
  const deadlineColor = !s.feasible ? 'var(--subtle-foreground)' : s.deadline_met ? (s.buffer_hours < 2 ? 'var(--warning)' : 'var(--success)') : 'var(--destructive)'
  const d = s.details as Record<string, unknown>

  return (
    <div style={{
      padding: '20px',
      background: recommended ? 'var(--accent-dim)' : 'var(--surface-secondary)',
      border: `1px solid ${recommended ? 'var(--accent)' : 'var(--border)'}`,
      borderRadius: 'var(--radius-lg)',
      opacity: s.feasible ? 1 : 0.45,
    }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '16px' }}>
        <ScoreGauge score={s.score} size={64} />

        <div style={{ flex: 1, minWidth: 0 }}>
          {/* Strategy label */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px', flexWrap: 'wrap' }}>
            {recommended && (
              <span style={{
                fontSize: '10px', fontWeight: 600, letterSpacing: '0.05em',
                color: '#000',
                background: 'var(--accent)',
                borderRadius: '999px', padding: '2px 8px',
              }}>RECOMMENDED</span>
            )}
            <span style={{ fontSize: '13px', fontWeight: 600, color: meta.color }}>
              {title(s.type)}
            </span>
            {s.vehicle_id && (
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--muted-foreground)' }}>
                → {s.vehicle_id}
              </span>
            )}
            {s.type === 'reroute' && s.hubs.length > 2 && (
              <span style={{ fontSize: '12px', color: 'var(--subtle-foreground)' }}>
                via {s.hubs.slice(1, -1).join(', ')}
              </span>
            )}
          </div>

          {!s.feasible ? (
            <div style={{ fontSize: '12px', color: 'var(--subtle-foreground)' }}>
              Not feasible: {String(d.reason ?? '')}
            </div>
          ) : (
            <div style={{
              display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
              gap: '4px 20px', fontSize: '12px', color: 'var(--muted-foreground)',
            }}>
              <span>Cost: <b style={{ color: 'var(--foreground)', fontFamily: 'var(--font-mono)' }}>{inr(s.cost)}</b></span>
              <span>Saving: <b style={{ color: 'var(--success)', fontFamily: 'var(--font-mono)' }}>{s.type === 'dedicated' ? '—' : pct(saving)}</b></span>
              <span>Arrive: <b style={{ color: 'var(--foreground)', fontFamily: 'var(--font-mono)' }}>{time(s.arrival_time)}</b></span>
              <span>Deadline: <b style={{ color: deadlineColor }}>{deadlineLabel}{s.deadline_met && ` +${hours(s.buffer_hours)}`}</b></span>
              <span>Distance: <b style={{ color: 'var(--foreground)', fontFamily: 'var(--font-mono)' }}>{s.distance_km.toFixed(0)} km</b></span>
              {typeof d.pickup_time === 'string' && <span>Pickup: <b style={{ fontFamily: 'var(--font-mono)', color: 'var(--foreground)' }}>{time(d.pickup_time)}</b></span>}
              {typeof d.available_capacity_kg === 'number' && <span>Free cap: <b style={{ fontFamily: 'var(--font-mono)', color: 'var(--foreground)' }}>{Math.round(d.available_capacity_kg)} kg</b></span>}
            </div>
          )}

          {/* Score bars */}
          {s.feasible && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(100px, 1fr))', gap: '8px 16px', marginTop: '12px' }}>
              {Object.entries(s.scores).map(([k, v]) => (
                <div key={k}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '3px', fontSize: '11px', color: 'var(--subtle-foreground)' }}>
                    <span>{title(k)} <span style={{ opacity: 0.6 }}>×{ev.weights[k] ?? '?'}</span></span>
                    <span style={{ fontFamily: 'var(--font-mono)' }}>{v.toFixed(2)}</span>
                  </div>
                  <ScoreBar value={v} color={meta.color} />
                </div>
              ))}
            </div>
          )}

          {whatIf && (
            <div style={{ marginTop: '8px', fontSize: '12px', color: 'var(--subtle-foreground)', padding: '8px 10px', background: 'var(--surface-tertiary)', borderRadius: '6px' }}>
              What-if: score {whatIf.delta.score >= 0 ? '+' : ''}{whatIf.delta.score.toFixed(1)},
              cost {whatIf.delta.cost >= 0 ? '+' : ''}{inr(whatIf.delta.cost)},
              buffer {hours(whatIf.delta.buffer_hours)} —
              {whatIf.hypothetical_meets_deadline ? ' meets' : ' misses'} deadline.
            </div>
          )}
        </div>

        {/* Actions */}
        {s.feasible && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', flexShrink: 0 }}>
            <button className="btn" onClick={onView}>View route</button>
            {canApprove && (
              <button className={`btn ${recommended ? 'btn-success' : ''}`} onClick={onApprove}>
                {recommended ? <CheckCircle2 size={13} /> : null}
                Approve
              </button>
            )}
            {!recommended && <button className="btn" onClick={onWhatIf}>What if?</button>}
          </div>
        )}
      </div>
    </div>
  )
}
