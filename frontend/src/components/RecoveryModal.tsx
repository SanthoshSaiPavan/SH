import { useCallback, useEffect, useState } from 'react'
import { z } from 'zod'
import { api, ApiError } from '../lib/api'
import { PRIORITY_META, STRATEGY_META } from '../lib/constants'
import { hours, inr, parseUtc, pct, time, timeLeft, title } from '../lib/format'
import { EvaluationSchema, type Evaluation, type Shipment, type Strategy } from '../lib/schemas'
import { useAuth } from '../hooks/useAuth'
import { useEngineNow } from '../hooks/useEngineNow'
import { useSocket, useSocketEvent } from '../hooks/useSocket'
import ScoreGauge, { ScoreBar } from './ScoreGauge'
import { OnTime, ParetoBadge, ParetoStrip, RejectedPanel, ScanHistory, SensitivityLine } from './RecoveryInsights'

type Props = { shipment: Shipment; onClose: () => void; onViewRoute: (hubs: string[]) => void }

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

const MODE_BADGE: Record<string, string> = {
  auto_executed: 'bg-success/20 text-success', pending_approval: 'bg-primary/20 text-primary', escalated: 'bg-danger/20 text-danger',
}

export default function RecoveryModal({ shipment, onClose, onViewRoute }: Props) {
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
  // A new recommendation for this shipment means the scores changed: reload once.
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
    setAnswer(`${res.answer}${res.source === 'template' ? ' (LLM unavailable: grounded template)' : ''}`)
  }
  const runWhatIf = async (s: Strategy) => {
    const res = await api.post('/api/agent/what-if', { shipment_id: shipment.id, hypothetical_strategy: s.type }, WhatIfSchema)
    setWhatIf((w) => ({ ...w, [s.id]: res }))
  }
  const loadAudit = async () => setAudit(await api.get(`/api/agent/audit-trail/${shipment.id}`, AuditSchema))

  const p = PRIORITY_META[shipment.priority]
  const left = (parseUtc(shipment.deadline).getTime() - now.getTime()) / 3.6e6
  const recommendedId = ev?.recommended?.id

  return (
    <div className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm grid place-items-center p-6" onClick={onClose}>
      <div className="glass w-full max-w-5xl max-h-[92vh] overflow-y-auto p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start gap-4">
          <div>
            <div className="text-xs text-muted uppercase tracking-wide">Recovery options for</div>
            <h2 className="text-xl font-bold mono">{shipment.id}</h2>
            <div className="text-sm text-muted mt-1 flex flex-wrap gap-x-4">
              <span>{p.emoji} Priority: <b style={{ color: p.color }}>{p.label.toUpperCase()}</b></span>
              <span>Deadline: <b className={left < 2 ? 'text-danger' : 'text-ink'}>{timeLeft(left)}</b></span>
              <span>{shipment.weight_kg} kg · {shipment.volume_cbm} m³</span>
              {shipment.misplacement_type && <span className="text-warning">{title(shipment.misplacement_type)} {shipment.current_hub_id ? `at ${shipment.current_hub_id}` : `en route${shipment.current_vehicle_id ? ` on ${shipment.current_vehicle_id}` : ''}`}</span>}
              <span>→ {shipment.destination_hub_id}</span>
              {shipment.manifest_vehicle_id && <span>Manifest: <b className="mono text-ink">{shipment.manifest_vehicle_id}</b></span>}
            </div>
          </div>
          {ev && <span className={`ml-auto text-xs font-semibold px-3 py-1 rounded-full ${MODE_BADGE[ev.recovery_mode] ?? ''}`}>{title(ev.recovery_mode)}</span>}
          <button className="btn" onClick={onClose}>✕</button>
        </div>

        {error && <div className="mt-4 text-sm text-danger">{error}</div>}
        {ev?.recommendation_reason && <div className="mt-3 text-xs text-muted">Recommendation: {ev.recommendation_reason}</div>}
        {!ev && !error && <div className="mt-6 text-muted">Scoring strategies…</div>}

        {ev && (
          <>
            <ParetoStrip ev={ev} />
            <SensitivityLine ev={ev} />
            <RejectedPanel ev={ev} shipmentId={shipment.id} />
            <div className="mt-5 space-y-3">
              {ev.strategies.map((s) => (
                <StrategyRow key={s.id} s={s} ev={ev} shipment={shipment} recommended={s.id === recommendedId}
                  canApprove={isOperator && !busy} onApprove={() => approve(s)}
                  onView={() => onViewRoute(s.hubs)} onWhatIf={() => runWhatIf(s)} whatIf={whatIf[s.id]} />
              ))}
            </div>

            {isOperator && ev.recovery_mode !== 'escalated' && (
              <div className="mt-3 flex gap-2 items-center">
                <input className="input flex-1" placeholder="Reason for rejecting the recommendation (optional)" value={rejectReason} maxLength={500} onChange={(e) => setRejectReason(e.target.value)} />
                <button className="btn btn-danger" disabled={busy} onClick={reject}>Reject & escalate</button>
              </div>
            )}

            {ev.piggyback_candidates.length > 0 && (
              <div className="mt-6">
                <h3 className="font-semibold mb-2">Piggyback candidates (Module 2 match score)</h3>
                <div className="text-[11px] text-muted mb-2">
                  score = {Object.entries(ev.piggyback_weights).map(([k, w]) => `${w}×${k}`).join(' + ')}
                </div>
                <table className="w-full text-xs">
                  <thead className="text-muted text-left">
                    <tr><th className="py-1">Vehicle(s)</th><th>Path</th><th>Pickup</th><th>Arrive</th><th>Detour</th><th>Cost</th>
                      {Object.keys(ev.piggyback_weights).map((k) => <th key={k}>{title(k)}</th>)}<th>Score</th></tr>
                  </thead>
                  <tbody>
                    {ev.piggyback_candidates.map((c) => (
                      <tr key={c.vehicle_id} className="border-t border-[var(--border-subtle)]">
                        <td className="py-1.5 mono">{c.vehicles.join(' → ')}</td>
                        <td>{c.hubs.map((h) => h.replace('HUB-', '')).join('›')}</td>
                        <td>{time(c.pickup_time)}</td><td>{time(c.arrival_time)}</td>
                        <td>{c.detour_km.toFixed(0)} km</td><td>{inr(c.cost)}</td>
                        {['proximity', 'capacity', 'deadline', 'overlap', 'cost_savings'].map((k) => <td key={k} className="mono">{(c.scores[k] ?? 0).toFixed(2)}</td>)}
                        <td className="mono font-bold text-piggy">{c.score.toFixed(1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <div className="mt-6 grid md:grid-cols-2 gap-4">
              <div className="card p-4">
                <div className="flex items-center gap-2">
                  <h3 className="font-semibold">🧠 Decision agent</h3>
                  <button className="btn ml-auto" disabled={explaining} onClick={runExplain}>{explaining ? 'Thinking…' : 'Explain recommendation'}</button>
                </div>
                {explain && (
                  <div className="mt-3 text-sm space-y-2">
                    <p>{explain.explanation}</p>
                    <div className="text-[11px] text-muted">Source: {explain.source === 'llm' ? `LLM (${explain.model}), grounded in engine scores` : 'grounded template (LLM unavailable)'}</div>
                    <div className="flex flex-wrap gap-2 text-[11px]">
                      {(['deadline_risk', 'capacity_risk', 'route_risk'] as const).map((k) => (
                        <span key={k} className={`px-2 py-0.5 rounded-full ${explain.risk[k] ? 'bg-danger/20 text-danger' : 'bg-success/20 text-success'}`}>{title(k)}: {explain.risk[k] ? 'yes' : 'no'}</span>
                      ))}
                      {explain.risk.cost_delta !== null && <span className="px-2 py-0.5 rounded-full bg-surface">vs dedicated: {inr(explain.risk.cost_delta)}</span>}
                    </div>
                    {explain.risk.notes.map((n) => <div key={n} className="text-xs text-warning">⚠ {n}</div>)}
                  </div>
                )}
                <div className="mt-3 flex gap-2">
                  <input className="input flex-1" placeholder="Ask: why was this truck selected?" value={question} maxLength={1000}
                    onChange={(e) => setQuestion(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && ask()} />
                  <button className="btn" onClick={ask}>Ask</button>
                </div>
                {answer && <p className="mt-2 text-sm">{answer}</p>}
              </div>
              <div className="card p-4">
                <div className="flex items-center"><h3 className="font-semibold">📜 Decision audit trail</h3><button className="btn ml-auto" onClick={loadAudit}>Load</button></div>
                <div className="mt-2 space-y-2 max-h-56 overflow-y-auto text-xs">
                  {audit?.length === 0 && <div className="text-muted">No decisions logged yet.</div>}
                  {audit?.map((a) => (
                    <div key={a.id} className="bg-surface/60 rounded p-2">
                      <div className="text-muted">{time(a.created_at)} {a.operator_decision && <b className="text-ink">· {a.operator_decision}</b>} {a.confidence_score !== null && `· score ${a.confidence_score.toFixed(1)}`}</div>
                      {a.operator_query && <div className="text-muted italic">{a.operator_query}</div>}
                      <div className="mt-0.5">{a.explanation}</div>
                    </div>
                  ))}
                </div>
              </div>
              <ScanHistory shipmentId={shipment.id} />
            </div>
          </>
        )}
      </div>
    </div>
  )
}

type RowProps = {
  s: Strategy; ev: Evaluation; shipment: Shipment; recommended: boolean; canApprove: boolean
  onApprove: () => void; onView: () => void; onWhatIf: () => void; whatIf?: z.infer<typeof WhatIfSchema>
}

// `time` is now the Monte Carlo on-time probability, not a time score.
const SCORE_LABEL: Record<string, string> = { time: 'On-time P' }

function StrategyRow({ s, ev, shipment, recommended, canApprove, onApprove, onView, onWhatIf, whatIf }: RowProps) {
  const meta = STRATEGY_META[s.type]
  const dominated = s.feasible && !s.pareto && ev.pareto_options.length > 0
  const saving = ev.dedicated_cost > 0 ? 1 - s.cost / ev.dedicated_cost : 0
  const deadline = !s.feasible ? '—' : s.deadline_met ? (s.buffer_hours < 2 ? '⚠️ Tight' : '✅ Safe') : '🔴 WILL MISS'
  const d = s.details as Record<string, unknown>
  return (
    <div className={`card p-4 ${recommended ? 'border-piggy shadow-[0_0_24px_rgba(168,85,247,.25)]' : ''} ${s.feasible ? '' : 'opacity-50'}`}>
      <div className="flex items-center gap-4">
        <ScoreGauge score={s.score} />
        <div className="flex-1 min-w-0">
          <div className="font-semibold flex items-center gap-2">
            {recommended && <span className="text-piggy">★ RECOMMENDED:</span>}
            <span style={{ color: meta.color }}>{meta.icon} {meta.label.toUpperCase()}</span>
            {s.vehicle_id && <span className="mono text-sm">onto {s.vehicle_id}</span>}
            {s.type === 'reroute' && s.hubs.length > 2 && <span className="text-sm text-muted">via {s.hubs.slice(1, -1).join(', ')}</span>}
            <ParetoBadge label={s.pareto_label} />
            {dominated && <span className="text-[11px] text-muted font-normal">dominated (another option is no costlier and no slower)</span>}
          </div>
          {s.feasible && (
            <div className="text-xs text-muted mt-1">
              <OnTime p={s.on_time_probability} threshold={ev.ontime_threshold[shipment.priority]} priority={shipment.priority} />
            </div>
          )}
          {!s.feasible ? (
            <div className="text-sm text-muted mt-1">Not feasible: {String(d.reason ?? '')}</div>
          ) : (
            <div className="text-xs text-muted mt-1.5 grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-1">
              <span>Cost: <b className="text-ink">{inr(s.cost)}</b></span>
              <span>Savings vs dedicated: <b className="text-ink">{s.type === 'dedicated' ? '—' : pct(saving)}</b></span>
              <span>Arrive: <b className="text-ink">{time(s.arrival_time)}</b> ({hours(s.duration_hours)})</span>
              <span>Deadline: <b className="text-ink">{deadline}</b> {s.deadline_met && `(+${hours(s.buffer_hours)})`}</span>
              <span>Distance: <b className="text-ink">{s.distance_km.toFixed(0)} km</b>{s.detour_km > 0 && ` (+${s.detour_km.toFixed(0)} km detour)`}</span>
              {typeof d.pickup_time === 'string' && <span>Pickup: <b className="text-ink">{time(d.pickup_time)}</b></span>}
              {typeof d.next_vehicle_departure === 'string' && <span>Next vehicle: <b className="text-ink">{time(d.next_vehicle_departure)}</b></span>}
              {typeof d.available_capacity_kg === 'number' && <span>Free capacity: <b className="text-ink">{Math.round(d.available_capacity_kg)} kg</b></span>}
            </div>
          )}
        </div>
        {s.feasible && (
          <div className="flex flex-col gap-1.5 shrink-0">
            <button className="btn" onClick={onView}>View on map</button>
            {canApprove && <button className={`btn ${recommended ? 'btn-success' : ''}`} onClick={onApprove}>Approve</button>}
            {!recommended && <button className="btn" onClick={onWhatIf}>What if?</button>}
          </div>
        )}
      </div>
      {s.feasible && (
        <div className="mt-3 grid grid-cols-4 gap-3 text-[11px]">
          {Object.entries(s.scores).map(([k, v]) => (
            <div key={k}>
              <div className="flex justify-between text-muted"><span>{SCORE_LABEL[k] ?? title(k)} <span className="opacity-60">×{ev.weights[k] ?? '?'}</span></span><span className="mono">{v.toFixed(2)}</span></div>
              <ScoreBar value={v} color={meta.color} />
            </div>
          ))}
        </div>
      )}
      {whatIf && (
        <div className="mt-2 text-xs text-muted">
          What if we {s.type} instead? Score {whatIf.delta.score >= 0 ? '+' : ''}{whatIf.delta.score.toFixed(1)}, cost {whatIf.delta.cost >= 0 ? '+' : ''}{inr(whatIf.delta.cost)},
          buffer {hours(whatIf.delta.buffer_hours)}; {whatIf.hypothetical_meets_deadline ? 'meets' : 'misses'} the deadline.
        </div>
      )}
    </div>
  )
}
