import { PRIORITY_META, STATUS_COLORS } from '../lib/constants'
import { parseUtc, timeLeft, title } from '../lib/format'
import type { Recommendation, Shipment } from '../lib/schemas'
import type { Progress } from '../hooks/useLiveData'

type Props = { shipment: Shipment; recommendation?: Recommendation; progress?: Progress; now: Date; onClick?: () => void }

export default function ShipmentCard({ shipment: s, recommendation, progress, now, onClick }: Props) {
  const p = PRIORITY_META[s.priority]
  const left = (parseUtc(s.deadline).getTime() - now.getTime()) / 3.6e6
  return (
    <button onClick={onClick} className="card p-3 text-left w-full hover:border-primary animate-slide-in">
      <div className="flex items-center gap-2">
        <span>{p.emoji}</span>
        <span className="mono font-semibold text-sm">{s.id}</span>
        <span className="ml-auto text-[10px] px-2 py-0.5 rounded-full font-semibold" style={{ background: `${STATUS_COLORS[s.status]}22`, color: STATUS_COLORS[s.status] }}>
          {title(s.status)}
        </span>
      </div>
      <div className="text-xs text-muted mt-1.5 flex flex-wrap gap-x-3">
        <span>{s.origin_hub_id.replace('HUB-', '')} → {s.destination_hub_id.replace('HUB-', '')}</span>
        <span>{s.weight_kg} kg</span>
        <span className={left < 2 ? 'text-danger' : ''}>⏳ {timeLeft(left)}</span>
        {s.misplacement_type && <span className="text-warning">{title(s.misplacement_type)}</span>}
      </div>
      {recommendation && (
        <div className="text-xs mt-2 text-piggy">
          ★ {title(recommendation.strategy)}{recommendation.vehicle_id ? ` → ${recommendation.vehicle_id}` : ''} · {recommendation.score.toFixed(0)}/100
          {recommendation.recovery_mode === 'escalated' && <span className="text-danger"> · escalated</span>}
        </div>
      )}
      {s.recovery_strategy && (
        <div className="mt-2">
          <div className="text-xs text-success">{title(s.recovery_strategy)}{s.recovery_vehicle_id ? ` on ${s.recovery_vehicle_id}` : ''} · {progress ? `${progress.percent_complete}%` : 'in progress'}</div>
          <div className="h-1 bg-surface rounded mt-1"><div className="h-full bg-success rounded" style={{ width: `${progress?.percent_complete ?? 5}%` }} /></div>
        </div>
      )}
    </button>
  )
}
