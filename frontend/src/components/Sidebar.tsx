import { PRIORITY_META, STATUS_COLORS } from '../lib/constants'
import { title } from '../lib/format'

export type Filters = { hubType: string[]; priority: string[]; status: string[] }

const GROUPS: { key: keyof Filters; label: string; options: string[] }[] = [
  { key: 'hubType', label: 'Hub type', options: ['origin', 'distribution', 'transfer', 'destination'] },
  { key: 'priority', label: 'Priority', options: ['critical', 'high', 'medium', 'low'] },
  { key: 'status', label: 'Status', options: ['misplaced', 'piggybacked', 'in_transit', 'recovered', 'delivered'] },
]

export default function Sidebar({ filters, onChange }: { filters: Filters; onChange: (f: Filters) => void }) {
  const toggle = (key: keyof Filters, value: string) => {
    const cur = filters[key]
    onChange({ ...filters, [key]: cur.includes(value) ? cur.filter((v) => v !== value) : [...cur, value] })
  }
  return (
    <aside className="w-48 shrink-0 card p-4 space-y-5 self-start sticky top-20">
      <div className="text-xs uppercase tracking-wide text-muted font-semibold">Filters</div>
      {GROUPS.map((g) => (
        <div key={g.key}>
          <div className="text-sm font-semibold mb-2">{g.label}</div>
          <div className="space-y-1">
            {g.options.map((o) => {
              const color = g.key === 'priority' ? PRIORITY_META[o as keyof typeof PRIORITY_META].color : g.key === 'status' ? STATUS_COLORS[o] : '#64ffda'
              return (
                <label key={o} className="flex items-center gap-2 text-xs text-muted hover:text-ink cursor-pointer">
                  <input type="checkbox" checked={filters[g.key].includes(o)} onChange={() => toggle(g.key, o)} className="accent-[#6366f1]" />
                  <span className="w-2 h-2 rounded-full" style={{ background: color }} />
                  {title(o)}
                </label>
              )
            })}
          </div>
        </div>
      ))}
      <button className="btn w-full justify-center" onClick={() => onChange({ hubType: [], priority: [], status: [] })}>Clear</button>
    </aside>
  )
}
