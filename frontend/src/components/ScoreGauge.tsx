/** Circular 0–100 score gauge. */
export default function ScoreGauge({ score, size = 56 }: { score: number; size?: number; label?: string }) {
  const r = (size - 10) / 2
  const c = 2 * Math.PI * r
  const clamped = Math.min(100, Math.max(0, score))
  const color = score >= 50 ? 'var(--accent)' : score > 0 ? 'var(--warning)' : 'var(--destructive)'

  return (
    <div style={{ position: 'relative', width: size, height: size, flexShrink: 0 }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size / 2} cy={size / 2} r={r}
          stroke="rgba(0,0,0,0.08)" strokeWidth={6} fill="none" />
        <circle cx={size / 2} cy={size / 2} r={r}
          stroke={color} strokeWidth={6} fill="none"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - clamped / 100)}
          strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset 0.6s ease-out' }} />
      </svg>
      <div style={{
        position: 'absolute', inset: 0,
        display: 'grid', placeItems: 'center', textAlign: 'center',
      }}>
        <div>
          <div style={{
            fontFamily: 'var(--font-mono)',
            fontWeight: 700,
            fontSize: size / 4,
            lineHeight: 1,
            color: 'var(--foreground)',
            letterSpacing: '-0.02em',
          }}>
            {score.toFixed(0)}
          </div>
        </div>
      </div>
    </div>
  )
}

/** Thin horizontal score bar */
export function ScoreBar({ value, color = 'var(--accent)' }: { value: number; color?: string }) {
  return (
    <div style={{
      height: '6px', borderRadius: '9999px',
      background: 'rgba(0,0,0,0.08)',
      overflow: 'hidden',
    }}>
      <div style={{
        height: '100%', borderRadius: '9999px',
        width: `${Math.max(0, Math.min(100, value * 100))}%`,
        background: color,
        transition: 'width 0.5s ease-out',
      }} />
    </div>
  )
}
