import type { Alert } from '../lib/schemas'
import { title } from '../lib/format'
import { Bell, AlertTriangle, AlertOctagon, AlertCircle, Info, type LucideIcon } from 'lucide-react'

const SEV: Record<string, { color: string; bg: string; border: string; Icon: LucideIcon }> = {
  critical: { color: 'var(--destructive)', bg: 'rgba(230,57,70,0.05)', border: 'rgba(230,57,70,0.15)', Icon: AlertOctagon },
  high:     { color: '#D97B44',            bg: 'rgba(217,123,68,0.05)',  border: 'rgba(217,123,68,0.15)',  Icon: AlertTriangle },
  medium:   { color: 'var(--warning)',     bg: 'rgba(244,162,97,0.05)',  border: 'rgba(244,162,97,0.15)',  Icon: AlertCircle },
  low:      { color: 'var(--success)',     bg: 'rgba(82,183,136,0.05)', border: 'rgba(82,183,136,0.15)', Icon: Info },
}

const SEV_ORDER: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 }
const rank = (severity: string) => SEV_ORDER[severity] ?? SEV_ORDER.medium

export default function AlertPanel({ alerts, onSelect }: { alerts: Alert[]; onSelect: (id: string) => void }) {
  const criticals = alerts.filter(a => a.severity === 'critical').length
  // Most severe first; the sort is stable, so the incoming order is kept within a severity.
  const sorted = [...alerts].sort((a, b) => rank(a.severity) - rank(b.severity))

  return (
    <div className="card" style={{
      display: 'flex', flexDirection: 'column',
      overflow: 'hidden',
      border: '1px solid rgba(0,0,0,0.03)',
    }}>
      {/* Header */}
      <div style={{
        padding: '16px 20px',
        borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', gap: '8px',
        flexShrink: 0,
      }}>
        <Bell size={15} style={{ color: 'var(--foreground)' }} />
        <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--foreground)' }}>Alerts</span>
        <span style={{
          marginLeft: '4px',
          fontSize: '11px', color: 'var(--subtle-foreground)',
          background: 'var(--background)',
          borderRadius: '4px',
          padding: '2px 8px',
        }}>{alerts.length}</span>
        {criticals > 0 && (
          <span style={{
            fontSize: '11px', fontWeight: 600,
            color: 'var(--destructive)',
            background: 'rgba(230,57,70,0.05)',
            borderRadius: '4px',
            padding: '2px 8px',
          }}>{criticals} critical</span>
        )}
      </div>

      {/* List */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '12px', padding: '12px' }}>
        {alerts.length === 0 && (
          <div style={{
            gridColumn: '1 / -1', display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center', gap: '8px',
            color: 'var(--subtle-foreground)', fontSize: '13px', padding: '20px'
          }}>
            <Bell size={24} style={{ opacity: 0.3 }} />
            <span>No alerts detected</span>
          </div>
        )}
        {sorted.map((a) => {
          const s = SEV[a.severity] ?? SEV.medium
          const Icon = s.Icon
          return (
            <button
              key={`${a.shipment_id}-${a.at}`}
              onClick={() => onSelect(a.shipment_id)}
              className="animate-slide-in"
              style={{
                width: '100%', textAlign: 'left',
                padding: '12px 16px',
                borderRadius: '12px',
                background: s.bg,
                border: `1px solid ${s.border}`,
                borderLeft: `4px solid ${s.color}`,
                cursor: 'pointer',
                transition: 'background 150ms',
              }}
              onMouseEnter={e => (e.currentTarget as HTMLElement).style.filter = 'brightness(0.97)'}
              onMouseLeave={e => (e.currentTarget as HTMLElement).style.filter = ''}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '7px', marginBottom: '4px' }}>
                <Icon size={14} style={{ color: s.color, flexShrink: 0 }} />
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', fontWeight: 600, color: 'var(--foreground)' }}>
                  {a.shipment_id}
                </span>
                <span style={{ fontSize: '12px', color: 'var(--muted-foreground)', flex: 1, marginLeft: '4px' }}>
                  {title(a.type)}
                </span>
                <span style={{ fontSize: '11px', color: 'var(--subtle-foreground)', fontFamily: 'var(--font-mono)', marginLeft: 'auto' }}>
                  {new Date(a.at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </span>
              </div>
              <div style={{ fontSize: '13px', color: 'var(--muted-foreground)', paddingLeft: '21px' }}>
                {a.message}
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
