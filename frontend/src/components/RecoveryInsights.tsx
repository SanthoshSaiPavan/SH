import { useState } from 'react'
import { z } from 'zod'
import { api, ApiError } from '../lib/api'
import { PRIORITY_META, STRATEGY_META } from '../lib/constants'
import { hours, inr, pct, time, title } from '../lib/format'
import {
  ScanEventSchema, type Evaluation, type ParetoLabel, type Priority, type ScanEvent, type ScanEventType,
} from '../lib/schemas'

const PARETO_META: Record<ParetoLabel, { label: string; icon: string }> = {
  fastest: { label: 'Fastest', icon: '⚡' },
  cheapest: { label: 'Cheapest', icon: '₹' },
  balanced: { label: 'Balanced', icon: '⚖' },
}

const SCAN_STYLE: Record<ScanEventType, string> = {
  load: 'bg-info/20 text-info', unload: 'bg-surface text-ink', hub_scan: 'bg-surface text-muted',
  short: 'bg-danger/20 text-danger font-semibold', excess: 'bg-warning/20 text-warning font-semibold',
}

/** "Piggyback TRUCK-104" for a strategy id, falling back to the raw id. */
function strategyName(ev: Evaluation, id: string | null | undefined) {
  if (!id) return '—'
  const s = ev.strategies.find((x) => x.id === id)
  if (!s) return id
  return `${STRATEGY_META[s.type].label}${s.type === 'piggyback' && s.vehicle_id ? ` ${s.vehicle_id}` : ''}`
}

export function ParetoBadge({ label }: { label: ParetoLabel | null }) {
  if (!label) return null
  const m = PARETO_META[label]
  return <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-accent/15 text-accent">{m.icon} {m.label}</span>
}

/** P(on-time) coloured against the shipment tier's threshold. */
export function OnTime({ p, threshold, priority }: { p: number | null; threshold?: number; priority: Priority }) {
  if (p === null) return null
  const cls = threshold === undefined ? 'text-ink' : p >= threshold ? 'text-success' : p >= threshold - 0.15 ? 'text-warning' : 'text-danger'
  return (
    <span>
      P(on-time) <b className={cls}>{pct(p)}</b>
      {threshold !== undefined && <span className="opacity-80"> · needs ≥ {pct(threshold)} for {PRIORITY_META[priority].label}</span>}
    </span>
  )
}

export function ParetoStrip({ ev }: { ev: Evaluation }) {
  if (ev.pareto_options.length === 0) return null
  return (
    <div className="mt-5">
      <div className="text-xs text-muted uppercase tracking-wide mb-1.5">Pareto options (no option is both cheaper and faster)</div>
      <div className="flex flex-wrap gap-2">
        {ev.pareto_options.map((o) => (
          <div key={o.strategy_id} className="card px-3 py-2 text-xs">
            <div className="flex items-center gap-2">
              <ParetoBadge label={o.label} />
              <span className="font-semibold">{strategyName(ev, o.strategy_id)}</span>
            </div>
            <div className="text-muted mt-1">
              {inr(o.cost)} · arrive {time(o.arrival_time)} · P(on-time) <b className="text-ink">{pct(o.on_time_probability)}</b>
            </div>
            <div className="text-muted italic mt-0.5">{o.tradeoff}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function SensitivityLine({ ev }: { ev: Evaluation }) {
  const sens = ev.sensitivity
  if (!sens || sens.stable === undefined) return null
  const step = pct(sens.step ?? 0.2)
  if (sens.stable) {
    return <div className="mt-2 text-xs text-success">✓ Recommendation unchanged with each weight ±{step}</div>
  }
  const bestId = ev.strategies[0]?.id
  const flips = (sens.checks ?? []).filter((c) => c.recommended_id !== bestId)
  return (
    <div className="mt-2 text-xs text-warning">
      ⚠ Sensitive to weights:{' '}
      {flips.map((c, i) => (
        <span key={`${c.component}${c.change}`}>
          {i > 0 && '; '}{title(c.component)} {c.change >= 0 ? '+' : '−'}{pct(Math.abs(c.change))} → {strategyName(ev, c.recommended_id)}
        </span>
      ))}
    </div>
  )
}

export function RejectedPanel({ ev, shipmentId }: { ev: Evaluation; shipmentId: string }) {
  if (ev.rejected_options.length === 0) return null
  return (
    <div className="mt-5 card p-4 bg-danger/5" style={{ borderColor: 'var(--accent-danger)' }}>
      <h3 className="font-semibold text-danger">⛔ Rejected by the no-harm rule</h3>
      <div className="text-xs text-muted mt-0.5">
        These trucks could stop for {shipmentId}, but the detour would make cargo already aboard miss its deadline.
      </div>
      <div className="mt-3 space-y-2">
        {ev.rejected_options.map((r) => (
          <div key={`${r.vehicle_id}|${r.detour_hub}`} className="bg-surface/60 rounded p-3 text-sm">
            <div className="flex flex-wrap items-center gap-x-3">
              <span className="mono font-semibold">{r.vehicle_id}</span>
              <span className="text-muted text-xs">detour to <span className="mono">{r.detour_hub}</span> (+{r.detour_km.toFixed(0)} km)</span>
            </div>
            <div className="text-xs mt-1">{r.reason}</div>
            <div className="mt-2 flex flex-wrap gap-2 text-xs">
              {r.victims.map((v) => {
                const pm = PRIORITY_META[v.priority]
                return (
                  <span key={v.shipment_id} className="px-2 py-0.5 rounded-full bg-danger/15">
                    {pm.emoji} <span className="mono">{v.shipment_id}</span> <b style={{ color: pm.color }}>{pm.label}</b>{' '}
                    <span className="text-danger">+{hours(v.late_hours)} late</span>
                  </span>
                )
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function ScanHistory({ shipmentId }: { shipmentId: string }) {
  const [scans, setScans] = useState<ScanEvent[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const toggle = async () => {
    if (scans) { setScans(null); return }
    try {
      setScans(await api.get(`/api/shipments/${shipmentId}/scans`, z.array(ScanEventSchema)))
      setError(null)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e))
    }
  }
  return (
    <div className="card p-4 md:col-span-2">
      <div className="flex items-center"><h3 className="font-semibold">🏷 Scan history</h3><button className="btn ml-auto" onClick={toggle}>{scans ? 'Hide' : 'Load'}</button></div>
      {error && <div className="mt-2 text-xs text-danger">{error}</div>}
      {scans && (
        <div className="mt-2 space-y-1 max-h-56 overflow-y-auto text-xs">
          {scans.length === 0 && <div className="text-muted">No scans recorded.</div>}
          {scans.map((s) => (
            <div key={s.id} className="flex flex-wrap items-center gap-x-3 gap-y-0.5 bg-surface/60 rounded px-2 py-1.5">
              <span className="text-muted">{time(s.scanned_at)}</span>
              <span className={`px-2 py-0.5 rounded-full ${SCAN_STYLE[s.event_type]}`}>{title(s.event_type)}</span>
              {s.hub_id && <span className="mono">{s.hub_id}</span>}
              {s.vehicle_id && <span className="mono">{s.vehicle_id}</span>}
              {!s.expected && <span className="text-warning">unexpected</span>}
              {s.note && <span className="text-muted">{s.note}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
