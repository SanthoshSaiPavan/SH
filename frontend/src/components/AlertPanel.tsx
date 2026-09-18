import type { Alert } from '../lib/schemas'
import { title } from '../lib/format'

const SEVERITY_COLOR: Record<string, string> = { critical: '#ef4444', high: '#f97316', medium: '#eab308', low: '#22c55e' }

export default function AlertPanel({ alerts, onSelect }: { alerts: Alert[]; onSelect: (id: string) => void }) {
  return (
    <div className="card p-4 flex flex-col min-h-0">
      <h3 className="font-semibold mb-3 flex items-center gap-2">⚠ Alerts <span className="text-xs text-muted">({alerts.length})</span></h3>
      <div className="space-y-2 overflow-y-auto min-h-0 flex-1">
        {alerts.length === 0 && <div className="text-sm text-muted">No alerts yet. Anomalies appear here the moment they are detected.</div>}
        {alerts.map((a) => (
          <button key={`${a.shipment_id}-${a.at}`} onClick={() => onSelect(a.shipment_id)}
            className="w-full text-left p-2.5 rounded-lg bg-surface/60 hover:bg-surface border-l-4 animate-slide-in"
            style={{ borderColor: SEVERITY_COLOR[a.severity] ?? '#6366f1' }}>
            <div className="flex items-center gap-2 text-sm">
              <span className="mono font-semibold">{a.shipment_id}</span>
              <span className="text-xs" style={{ color: SEVERITY_COLOR[a.severity] }}>{title(a.type)} · {a.severity}</span>
              <span className="ml-auto text-[10px] text-muted">{new Date(a.at).toLocaleTimeString()}</span>
            </div>
            <div className="text-xs text-muted mt-0.5">{a.message}</div>
          </button>
        ))}
      </div>
    </div>
  )
}
