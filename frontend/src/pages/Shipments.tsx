import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import RecoveryModal from '../components/RecoveryModal'
import { useEngineNow } from '../hooks/useEngineNow'
import { useLiveData, useShipments } from '../hooks/useLiveData'
import { PRIORITY_META, STATUS_COLORS } from '../lib/constants'
import { parseUtc, timeLeft, title } from '../lib/format'
import { ArrowDown, ArrowUp, ArrowUpDown, Search } from 'lucide-react'
import type { Shipment } from '../lib/schemas'
import type { MapLinkState } from './MapView'

type SortKey = 'id' | 'priority' | 'route' | 'vehicle' | 'deadline' | 'status'

const PRIORITY_RANK = Object.keys(PRIORITY_META)
// Most urgent first, finished last.
const STATUS_RANK = ['misplaced', 'delayed', 'piggybacked', 'in_transit', 'at_origin', 'recovered', 'delivered']
const DONE = ['delivered', 'recovered']
const rank = (order: string[], v: string) => (order.includes(v) ? order.indexOf(v) : order.length)
const text = (a: string, b: string) => a.localeCompare(b, undefined, { numeric: true })

const COLUMNS: { label: string; key?: SortKey }[] = [
  { label: 'Shipment ID', key: 'id' }, { label: 'Priority', key: 'priority' }, { label: 'Route', key: 'route' },
  { label: 'Vehicle', key: 'vehicle' }, { label: 'Deadline', key: 'deadline' }, { label: 'Status', key: 'status' },
  { label: 'Action' },
]

const COMPARE: Record<SortKey, (a: Shipment, b: Shipment) => number> = {
  id: (a, b) => text(a.id, b.id),
  priority: (a, b) => rank(PRIORITY_RANK, a.priority) - rank(PRIORITY_RANK, b.priority),
  route: (a, b) => text(a.expected_route.join('>'), b.expected_route.join('>')),
  vehicle: (a, b) => text(a.current_vehicle_id ?? a.current_hub_id ?? '\uffff', b.current_vehicle_id ?? b.current_hub_id ?? '\uffff'),
  // Delivered/recovered shipments show no deadline, so they sort after every live one.
  deadline: (a, b) => (+DONE.includes(a.status) - +DONE.includes(b.status)) || parseUtc(a.deadline).getTime() - parseUtc(b.deadline).getTime(),
  status: (a, b) => rank(STATUS_RANK, a.status) - rank(STATUS_RANK, b.status),
}

export default function Shipments() {
  const { shipments } = useLiveData()
  const navigate = useNavigate()
  const now = useEngineNow()
  const [q, setQ] = useState('')
  const [status, setStatus] = useState<string[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 } | null>(null)
  const filtered = useShipments({ q, status, priority: [] })
  const rows = useMemo(() => {
    if (!sort) return filtered
    const cmp = COMPARE[sort.key]
    return [...filtered].sort((a, b) => sort.dir * cmp(a, b) || text(a.id, b.id))
  }, [filtered, sort])
  const toggleSort = (key: SortKey) =>
    setSort((cur) => (cur?.key === key ? { key, dir: cur.dir === 1 ? -1 : 1 } : { key, dir: 1 }))

  const tabs = [
    { label: 'All', value: '' },
    { label: 'In Transit', value: 'in_transit' },
    { label: 'Misplaced', value: 'misplaced' },
    { label: 'Piggybacked', value: 'piggybacked' },
  ]

  return (
    <div style={{ padding: '32px', maxWidth: '1440px', margin: '0 auto' }}>
      
      {/* Search and Tabs (Match the pill tabs in the reference image) */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <h1 style={{ margin: 0, fontSize: '20px', fontWeight: 600, letterSpacing: '-0.02em', color: 'var(--foreground)' }}>
            Shipments <span style={{ color: 'var(--subtle-foreground)', fontSize: '14px', marginLeft: '8px', padding: '2px 8px', background: 'rgba(0,0,0,0.05)', borderRadius: '999px' }}>{rows.length}</span>
          </h1>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {/* Pill tabs */}
          <div style={{ display: 'flex', gap: '6px' }}>
            {tabs.map((t) => {
              const active = status[0] === t.value || (status.length === 0 && t.value === '')
              return (
                <button
                  key={t.label}
                  onClick={() => setStatus(t.value ? [t.value] : [])}
                  style={{
                    padding: '8px 16px',
                    borderRadius: '999px',
                    fontSize: '13px', fontWeight: 500,
                    background: active ? 'var(--dark-surface)' : 'var(--surface)',
                    color: active ? 'var(--dark-foreground)' : 'var(--muted-foreground)',
                    border: 'none',
                    cursor: 'pointer',
                    boxShadow: active ? 'none' : '0 2px 5px rgba(0,0,0,0.02), 0 0 0 1px rgba(0,0,0,0.03)',
                    transition: 'all 150ms'
                  }}
                >
                  {t.label}
                </button>
              )
            })}
          </div>

          <div style={{ position: 'relative', marginLeft: '8px' }}>
            <Search size={14} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--subtle-foreground)', pointerEvents: 'none' }} />
            <input
              className="input"
              style={{ paddingLeft: '34px', width: '240px' }}
              placeholder="Search ID or tracking…"
              value={q} maxLength={40}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="card" style={{ padding: '8px', border: '1px solid rgba(0,0,0,0.03)' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              {COLUMNS.map(({ label, key }) => {
                const active = key && sort?.key === key
                const Icon = !active ? ArrowUpDown : sort.dir === 1 ? ArrowUp : ArrowDown
                return (
                  <th key={label} aria-sort={active ? (sort.dir === 1 ? 'ascending' : 'descending') : undefined} style={{
                    padding: '16px 20px', textAlign: 'left',
                    fontSize: '12px', fontWeight: 500, color: active ? 'var(--foreground)' : 'var(--subtle-foreground)',
                    borderBottom: '1px solid var(--border)'
                  }}>
                    {key ? (
                      <button onClick={() => toggleSort(key)} style={{
                        display: 'inline-flex', alignItems: 'center', gap: '4px', padding: 0,
                        background: 'none', border: 'none', font: 'inherit', color: 'inherit', cursor: 'pointer',
                      }}>
                        {label}<Icon size={12} style={{ opacity: active ? 1 : 0.4 }} />
                      </button>
                    ) : label}
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={7} style={{ textAlign: 'center', padding: '64px', color: 'var(--subtle-foreground)' }}>
                  No shipments match the current filters
                </td>
              </tr>
            )}
            {rows.map((s) => {
              const left = (parseUtc(s.deadline).getTime() - now.getTime()) / 3.6e6
              const isMisplaced = s.status === 'misplaced'
              const statusColor = STATUS_COLORS[s.status] ?? 'var(--muted-foreground)'
              const p = PRIORITY_META[s.priority]
              
              return (
                <tr
                  key={s.id}
                  style={{
                    cursor: isMisplaced ? 'pointer' : 'default',
                    borderBottom: '1px solid rgba(0,0,0,0.03)',
                    transition: 'background 150ms'
                  }}
                  onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = isMisplaced ? 'rgba(0,0,0,0.01)' : '' }}
                  onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent' }}
                  onClick={() => isMisplaced && setSelected(s.id)}
                >
                  {/* ID */}
                  <td style={{ padding: '16px 20px', fontFamily: 'var(--font-mono)', fontSize: '13px', fontWeight: 600, color: 'var(--foreground)' }}>
                    {s.id}
                  </td>
                  
                  {/* Priority */}
                  <td style={{ padding: '16px 20px' }}>
                    <span style={{ fontSize: '13px', fontWeight: 500, color: p.color }}>
                      {p.label}
                    </span>
                  </td>
                  
                  {/* Route */}
                  <td style={{ padding: '16px 20px', fontSize: '13px', color: 'var(--muted-foreground)' }}>
                    {s.expected_route.map((h) => h.replace('HUB-', '')).join(' › ')}
                  </td>
                  
                  {/* Vehicle */}
                  <td style={{ padding: '16px 20px', fontSize: '13px', color: 'var(--foreground)' }}>
                    {s.current_vehicle_id ?? s.current_hub_id ?? '—'}
                  </td>
                  
                  {/* Deadline */}
                  <td style={{ padding: '16px 20px', fontFamily: 'var(--font-mono)', fontSize: '13px', color: left < 0 ? 'var(--destructive)' : 'var(--muted-foreground)' }}>
                    {['delivered', 'recovered'].includes(s.status) ? '—' : timeLeft(left)}
                  </td>
                  
                  {/* Status */}
                  <td style={{ padding: '16px 20px' }}>
                    <span style={{
                      display: 'inline-flex', alignItems: 'center', gap: '6px',
                      fontSize: '12px', fontWeight: 500,
                      color: 'var(--foreground)'
                    }}>
                      <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: statusColor, flexShrink: 0 }} />
                      {title(s.status)}
                    </span>
                  </td>
                  
                  {/* Action */}
                  <td style={{ padding: '16px 20px' }}>
                    {isMisplaced ? (
                      <button className="btn btn-accent" style={{ height: '32px', fontSize: '12px' }}>
                        Recover
                      </button>
                    ) : (
                      <span style={{ fontSize: '12px', color: 'var(--subtle-foreground)' }}>—</span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {selected && shipments[selected] && (
        <RecoveryModal
          shipment={shipments[selected]}
          onClose={() => setSelected(null)}
          onViewRoutes={(routes) => navigate('/map', { state: { shipmentId: selected, routes } satisfies MapLinkState })}
        />
      )}
    </div>
  )
}
