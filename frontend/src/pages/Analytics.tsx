import maplibregl from '../lib/maplibre'
import { useEffect, useRef, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Cell, LabelList, Legend, Line, LineChart, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { z } from 'zod'
import { useLiveData } from '../hooks/useLiveData'
import { api } from '../lib/api'
import { MAP_CONFIG, STRATEGY_CHART_COLORS, STRATEGY_META } from '../lib/constants'
import { inr } from '../lib/format'
import { StrategyTypeSchema } from '../lib/schemas'

const RateSchema = z.object({ totals: z.record(z.string(), z.number()) }).loose()
const SavingsSchema = z.object({ today: z.number(), week: z.number(), month: z.number(), series: z.array(z.object({ date: z.string(), saved: z.number() })) })
const UsageSchema = z.array(z.object({ strategy: StrategyTypeSchema, count: z.number(), share: z.number(), avg_recovery_hours: z.number().nullable() }))
const HeatSchema = z.array(z.object({ hub_id: z.string(), name: z.string(), lat: z.number(), lng: z.number(), count: z.number() }))

const AXIS = { stroke: '#8892b0', fontSize: 11, tickLine: false, axisLine: false }
const TOOLTIP = { contentStyle: { background: '#111827', border: '1px solid rgba(99,102,241,.3)', borderRadius: 8, fontSize: 12 }, labelStyle: { color: '#f0f4ff' }, itemStyle: { color: '#f0f4ff' }, cursor: { fill: 'rgba(99,102,241,.08)' } }
const OUTCOME_COLORS: Record<string, string> = { completed: '#10b981', failed: '#ef4444', in_progress: '#8892b0' }

export default function Analytics() {
  const { activeRecoveries } = useLiveData()
  const [rate, setRate] = useState<z.infer<typeof RateSchema> | null>(null)
  const [savings, setSavings] = useState<z.infer<typeof SavingsSchema> | null>(null)
  const [usage, setUsage] = useState<z.infer<typeof UsageSchema>>([])
  const [heat, setHeat] = useState<z.infer<typeof HeatSchema>>([])

  // Reload when recoveries start or finish (socket-driven), not on a timer.
  useEffect(() => {
    Promise.all([
      api.get('/api/analytics/recovery-rate', RateSchema).then(setRate),
      api.get('/api/analytics/cost-savings', SavingsSchema).then(setSavings),
      api.get('/api/analytics/strategy-usage', UsageSchema).then(setUsage),
      api.get('/api/analytics/heatmap', HeatSchema).then(setHeat),
    ]).catch(() => undefined)
  }, [activeRecoveries.length])

  const outcomes = Object.entries(rate?.totals ?? {}).map(([name, value]) => ({ name, value }))
  const finished = (rate?.totals.completed ?? 0) + (rate?.totals.failed ?? 0)
  const successRate = finished ? (rate!.totals.completed ?? 0) / finished : null
  const usageRows = usage.map((u) => ({ ...u, label: STRATEGY_META[u.strategy].label, sharePct: Math.round(u.share * 100) }))

  return (
    <div className="p-4 space-y-4">
      <h1 className="text-xl font-bold">Analytics & performance</h1>
      <div className="grid lg:grid-cols-2 gap-4">
        <Panel title="Recovery outcomes" subtitle={successRate === null ? 'No finished recoveries yet' : `${Math.round(successRate * 100)}% success of ${finished} finished`}>
          <ResponsiveContainer width="100%" height={240}>
            <PieChart>
              <Pie data={outcomes} dataKey="value" nameKey="name" innerRadius={60} outerRadius={90} paddingAngle={2} stroke="#111827" strokeWidth={2}
                label={({ name, value }) => `${String(name).replace('_', ' ')}: ${value}`}>
                {outcomes.map((o) => <Cell key={o.name} fill={OUTCOME_COLORS[o.name] ?? '#6366f1'} />)}
              </Pie>
              <Tooltip {...TOOLTIP} />
              <Legend wrapperStyle={{ fontSize: 12, color: '#8892b0' }} />
            </PieChart>
          </ResponsiveContainer>
        </Panel>
        <Panel title="Cost savings vs dedicated recovery" subtitle={savings ? `${inr(savings.today)} last 24h · ${inr(savings.week)} week · ${inr(savings.month)} month (engine clock)` : ''}>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={savings?.series ?? []} margin={{ top: 10, right: 16, left: 8, bottom: 0 }}>
              <CartesianGrid stroke="#1e2538" vertical={false} />
              <XAxis dataKey="date" {...AXIS} />
              <YAxis {...AXIS} tickFormatter={(v) => inr(v)} width={70} />
              <Tooltip {...TOOLTIP} formatter={(v) => [inr(Number(v)), 'Saved']} />
              <Line type="monotone" dataKey="saved" stroke="#3987e5" strokeWidth={2} dot={{ r: 4, fill: '#3987e5', stroke: '#111827', strokeWidth: 2 }} />
            </LineChart>
          </ResponsiveContainer>
        </Panel>
        <Panel title="Strategy usage" subtitle="Share of executed recoveries">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={usageRows} margin={{ top: 20, right: 16, left: 0, bottom: 0 }} barCategoryGap="30%">
              <CartesianGrid stroke="#1e2538" vertical={false} />
              <XAxis dataKey="label" {...AXIS} />
              <YAxis {...AXIS} unit="%" />
              <Tooltip {...TOOLTIP} formatter={(v, _n, p) => [`${v}% (${(p.payload as { count: number }).count})`, 'Share']} />
              <Bar dataKey="sharePct" radius={[4, 4, 0, 0]}>
                {usageRows.map((u) => <Cell key={u.strategy} fill={STRATEGY_CHART_COLORS[u.strategy]} />)}
                <LabelList dataKey="sharePct" position="top" fill="#8892b0" fontSize={11} formatter={(v) => `${v}%`} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Panel>
        <Panel title="Average recovery time by strategy" subtitle="Hours from approval to recovered (engine clock)">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={usageRows} margin={{ top: 20, right: 16, left: 0, bottom: 0 }} barCategoryGap="30%">
              <CartesianGrid stroke="#1e2538" vertical={false} />
              <XAxis dataKey="label" {...AXIS} />
              <YAxis {...AXIS} unit=" h" />
              <Tooltip {...TOOLTIP} formatter={(v) => [v === null ? 'no data' : `${v} h`, 'Avg time']} />
              <Bar dataKey="avg_recovery_hours" radius={[4, 4, 0, 0]}>
                {usageRows.map((u) => <Cell key={u.strategy} fill={STRATEGY_CHART_COLORS[u.strategy]} />)}
                <LabelList dataKey="avg_recovery_hours" position="top" fill="#8892b0" fontSize={11} formatter={(v) => (v === null || v === undefined ? '' : `${v} h`)} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Panel>
      </div>
      <Panel title="Misplacement heatmap" subtitle="Misplacements per hub (circle size and shade = count)">
        <HeatMap rows={heat} />
        <table className="w-full text-xs mt-3">
          <thead className="text-muted text-left"><tr><th className="py-1">Hub</th><th>Misplacements</th></tr></thead>
          <tbody>{heat.map((h) => <tr key={h.hub_id} className="border-t border-[var(--border-subtle)]"><td className="py-1">{h.name}</td><td className="mono">{h.count}</td></tr>)}</tbody>
        </table>
      </Panel>
    </div>
  )
}

function Panel({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className="card p-4">
      <h3 className="font-semibold">{title}</h3>
      {subtitle && <div className="text-xs text-muted mb-2">{subtitle}</div>}
      {children}
    </div>
  )
}

function HeatMap({ rows }: { rows: z.infer<typeof HeatSchema> }) {
  const ref = useRef<HTMLDivElement>(null)
  const map = useRef<maplibregl.Map | null>(null)
  const rowsRef = useRef(rows)
  useEffect(() => {
    if (!ref.current) return
    const m = new maplibregl.Map({ container: ref.current, style: MAP_CONFIG.style, center: MAP_CONFIG.center, zoom: 3.8 })
    m.on('load', () => {
      m.addSource('heat', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
      m.addLayer({
        id: 'heat', type: 'circle', source: 'heat',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['get', 'count'], 1, 8, 10, 28],
          'circle-color': ['interpolate', ['linear'], ['get', 'count'], 1, '#fcd9c4', 5, '#eb6834', 10, '#8f2d0c'],
          'circle-opacity': 0.8, 'circle-stroke-color': '#111827', 'circle-stroke-width': 2,
        },
      })
      map.current = m
      setHeatData(m, rowsRef.current)
    })
    return () => { map.current = null; m.remove() }
  }, [])
  useEffect(() => {
    rowsRef.current = rows
    if (map.current) setHeatData(map.current, rows)
  }, [rows])
  return <div ref={ref} className="h-80 rounded-xl overflow-hidden" />
}

function setHeatData(m: maplibregl.Map, rows: z.infer<typeof HeatSchema>) {
  const source = m.getSource('heat') as maplibregl.GeoJSONSource | undefined
  source?.setData({
    type: 'FeatureCollection',
    features: rows.map((r) => ({ type: 'Feature', properties: { count: r.count }, geometry: { type: 'Point', coordinates: [r.lng, r.lat] } })),
  })
}
