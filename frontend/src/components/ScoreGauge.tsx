type Props = { score: number; size?: number; label?: string }

/** Circular 0–100 gauge. Colour follows the autonomy thresholds (≥85 / ≥50). */
export default function ScoreGauge({ score, size = 64, label }: Props) {
  const r = size / 2 - 5
  const c = 2 * Math.PI * r
  const color = score >= 85 ? '#10b981' : score >= 50 ? '#6366f1' : score > 0 ? '#f59e0b' : '#ef4444'
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} stroke="#1e2538" strokeWidth={6} fill="none" />
        <circle cx={size / 2} cy={size / 2} r={r} stroke={color} strokeWidth={6} fill="none"
          strokeDasharray={c} strokeDashoffset={c * (1 - Math.min(100, Math.max(0, score)) / 100)}
          strokeLinecap="round" style={{ transition: 'stroke-dashoffset .6s ease' }} />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center leading-none">
        <div>
          <div className="mono font-bold" style={{ color, fontSize: size / 4 }}>{score.toFixed(0)}</div>
          {label && <div className="text-[9px] text-muted mt-0.5">{label}</div>}
        </div>
      </div>
    </div>
  )
}

export function ScoreBar({ value, color = '#6366f1' }: { value: number; color?: string }) {
  return (
    <div className="h-1.5 bg-surface rounded-full overflow-hidden">
      <div className="h-full rounded-full" style={{ width: `${Math.max(0, Math.min(100, value * 100))}%`, background: color, transition: 'width .5s' }} />
    </div>
  )
}
