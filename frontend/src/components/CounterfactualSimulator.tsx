import { useMemo } from 'react'
import { Package, Truck, Clock, AlertTriangle, CheckCircle, IndianRupee } from 'lucide-react'
import type { Strategy, Shipment } from '../lib/schemas'
import { inr, time } from '../lib/format'

interface Props {
  shipment: Shipment
  strategies: Strategy[]
  now: Date
  dedicatedCostBaseline: number
}

export default function CounterfactualSimulator({ shipment, strategies, dedicatedCostBaseline }: Props) {
  const piggyback = useMemo(
    () => strategies.find((s) => s.type === 'piggyback' && s.feasible) || strategies.find((s) => s.type === 'reroute' && s.feasible),
    [strategies]
  )
  const dedicated = useMemo(() => strategies.find((s) => s.type === 'dedicated' && s.feasible), [strategies])
  const doNothing = useMemo(
    () =>
      strategies.find((s) => s.type === 'hold') || ({
        id: 'do_nothing', type: 'hold',
        cost: dedicatedCostBaseline * 1.4,
        feasible: true, arrival_time: null,
        deadline_met: false, duration_hours: 99,
      } as Strategy),
    [strategies, dedicatedCostBaseline]
  )

  return (
    <div>
      {/* Section header */}
      <div style={{ marginBottom: '16px' }}>
        <div style={{ fontSize: '11px', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--subtle-foreground)', marginBottom: '4px' }}>
          Counterfactual Scenario Analysis
        </div>
        <div style={{ fontSize: '13px', color: 'var(--muted-foreground)' }}>
          Projected outcomes at T+2h and T+4h under each recovery path
        </div>
      </div>

      {/* 3-column grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px' }}>
        <ScenarioCard
          title="Do Nothing"
          subtitle="Hold at current location"
          strategy={doNothing}
          shipment={shipment}
          variant="negative"
          icon={<AlertTriangle size={15} />}
        />
        <ScenarioCard
          title={piggyback?.type === 'piggyback' ? 'Piggyback' : 'Reroute'}
          subtitle="Recommended path"
          strategy={piggyback}
          shipment={shipment}
          variant="positive"
          icon={<Package size={15} />}
        />
        <ScenarioCard
          title="Dedicated Dispatch"
          subtitle="Direct vehicle assignment"
          strategy={dedicated}
          shipment={shipment}
          variant="neutral"
          icon={<Truck size={15} />}
        />
      </div>
    </div>
  )
}

type Variant = 'positive' | 'negative' | 'neutral'

const VARIANT_STYLE: Record<Variant, { accent: string; accentBg: string; border: string }> = {
  positive: { accent: 'var(--success)',     accentBg: 'rgba(139,207,114,0.06)',  border: 'rgba(139,207,114,0.20)' },
  negative: { accent: 'var(--destructive)', accentBg: 'rgba(224,100,100,0.06)', border: 'rgba(224,100,100,0.20)' },
  neutral:  { accent: 'var(--warning)',     accentBg: 'rgba(217,164,65,0.06)',   border: 'rgba(217,164,65,0.20)' },
}

function ScenarioCard({
  title, subtitle, strategy, shipment: _shipment, variant, icon,
}: {
  title: string; subtitle: string; strategy?: Strategy; shipment: Shipment
  variant: Variant; icon: React.ReactNode
}) {
  if (!strategy) {
    return (
      <div style={{
        padding: '16px',
        background: 'var(--surface-secondary)',
        border: '1px dashed var(--border)',
        borderRadius: '10px',
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        gap: '6px', minHeight: '200px',
        color: 'var(--subtle-foreground)', fontSize: '13px',
      }}>
        <AlertTriangle size={20} style={{ opacity: 0.3 }} />
        Not feasible
      </div>
    )
  }

  const vs = VARIANT_STYLE[variant]
  const t2h = get2hStatus(strategy)
  const t4h = get4hStatus(strategy)

  return (
    <div style={{
      padding: '16px',
      background: vs.accentBg,
      border: `1px solid ${vs.border}`,
      borderTop: `2px solid ${vs.accent}`,
      borderRadius: '10px',
      display: 'flex', flexDirection: 'column', gap: '12px',
    }}>
      {/* Header */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '7px', marginBottom: '3px' }}>
          <span style={{ color: vs.accent }}>{icon}</span>
          <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--foreground)' }}>{title}</span>
        </div>
        <div style={{ fontSize: '11px', color: 'var(--subtle-foreground)' }}>{subtitle}</div>
      </div>

      {/* Metrics */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
        <MetricCell
          icon={<IndianRupee size={11} />}
          label="Cost"
          value={inr(strategy.cost)}
          valueColor={variant === 'negative' ? 'var(--destructive)' : 'var(--foreground)'}
        />
        <MetricCell
          icon={<Clock size={11} />}
          label="ETA"
          value={strategy.arrival_time ? time(strategy.arrival_time) : 'MISSED'}
          valueColor={!strategy.deadline_met ? 'var(--destructive)' : 'var(--success)'}
        />
      </div>

      {/* SLA outcome */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 10px',
        background: 'var(--surface)',
        border: '1px solid var(--border)', borderRadius: '7px',
        fontSize: '12px',
      }}>
        {strategy.deadline_met
          ? <CheckCircle size={13} style={{ color: 'var(--success)', flexShrink: 0 }} />
          : <AlertTriangle size={13} style={{ color: 'var(--destructive)', flexShrink: 0 }} />
        }
        <span style={{ color: strategy.deadline_met ? 'var(--success)' : 'var(--destructive)', fontWeight: 500 }}>
          {strategy.deadline_met ? 'SLA Met' : 'SLA Breached'}
        </span>
        {typeof strategy.buffer_hours === 'number' && strategy.deadline_met && (
          <span style={{ color: 'var(--subtle-foreground)', marginLeft: 'auto' }}>+{strategy.buffer_hours.toFixed(1)}h buffer</span>
        )}
      </div>

      {/* Timeline T+2h / T+4h */}
      <div style={{ fontSize: '12px' }}>
        <div style={{ fontSize: '10px', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--subtle-foreground)', marginBottom: '8px' }}>
          Projected timeline
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <TimelineRow time="T + 2h" status={t2h} accent={vs.accent} />
          <TimelineRow time="T + 4h" status={t4h} accent={variant === 'negative' ? 'var(--destructive)' : (strategy.deadline_met ? 'var(--success)' : 'var(--warning)')} />
        </div>
      </div>
    </div>
  )
}

function MetricCell({ icon, label, value, valueColor }: { icon: React.ReactNode; label: string; value: string; valueColor?: string }) {
  return (
    <div style={{ padding: '8px 10px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '7px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '10px', color: 'var(--subtle-foreground)', marginBottom: '4px' }}>
        {icon}{label}
      </div>
      <div style={{ fontSize: '12px', fontWeight: 600, fontFamily: 'var(--font-mono)', color: valueColor ?? 'var(--foreground)' }}>
        {value}
      </div>
    </div>
  )
}

function TimelineRow({ time: t, status, accent }: { time: string; status: string; accent: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
      <span style={{ fontSize: '10px', fontFamily: 'var(--font-mono)', color: 'var(--subtle-foreground)', width: '40px', flexShrink: 0, paddingTop: '1px' }}>{t}</span>
      <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: accent, flexShrink: 0, marginTop: '5px' }} />
      <span style={{ fontSize: '12px', color: 'var(--muted-foreground)' }}>{status}</span>
    </div>
  )
}

function get2hStatus(s: Strategy): string {
  if (s.type === 'hold') return 'Shipment waiting at current hub'
  if (s.type === 'dedicated') return 'Direct vehicle dispatched, en route'
  if (s.type === 'piggyback') return `Loaded onto ${(s as unknown as Record<string, unknown>).vehicle_id ?? 'vehicle'}`
  return 'Rerouting in progress'
}

function get4hStatus(s: Strategy): string {
  if (s.type === 'hold') return 'SLA penalty accumulating'
  if (s.deadline_met) return 'Delivered — SLA satisfied'
  return 'Approaching destination (delayed)'
}
