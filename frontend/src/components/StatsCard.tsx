type Props = { label: string; value: string | number; hint?: string; color?: string; icon?: string }

export default function StatsCard({ label, value, hint, color = '#6366f1', icon }: Props) {
  return (
    <div className="card p-4 relative overflow-hidden">
      <div className="absolute -right-4 -top-4 w-20 h-20 rounded-full opacity-20 blur-xl" style={{ background: color }} />
      <div className="text-xs uppercase tracking-wide text-muted flex items-center gap-1.5">{icon}{label}</div>
      <div className="text-3xl font-bold mt-1 mono" style={{ color }}>{value}</div>
      {hint && <div className="text-[11px] text-muted mt-1">{hint}</div>}
    </div>
  )
}
