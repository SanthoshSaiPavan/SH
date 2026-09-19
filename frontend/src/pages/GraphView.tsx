import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useLiveData } from '../hooks/useLiveData'
import { useSimMode } from '../hooks/useSimMode'
import { api } from '../lib/api'
import { time, title } from '../lib/format'
import { createGraphScene, EDGE_LAYER_META, type CameraPreset, type EdgeLayer, type GraphScene } from '../lib/graphScene'
import { GraphSnapshotSchema, type GraphNode, type GraphSnapshot } from '../lib/schemas'

const ALL_LAYERS: Record<EdgeLayer, boolean> = { leg: true, wait: true, board: true, unload: true, onboard: false, detour: false }
const REFRESH_MS = 10_000 // follow-live refresh, triggered by simulation ticks

const fmtT = (t: number) => `+${t.toFixed(1)} h`

export default function GraphView() {
  const { sim } = useLiveData()
  // Demo/Live follows the navbar's LIVE GPS | DEMO mode, so both switches stay in sync.
  const { mode: source, setMode: setSource, busy } = useSimMode()
  const [hours, setHours] = useState(24)
  const [hoursDraft, setHoursDraft] = useState(24)
  const [layers, setLayers] = useState(ALL_LAYERS)
  const [preset, setPreset] = useState<CameraPreset>('3d')
  const [follow, setFollow] = useState(true)
  const [snap, setSnap] = useState<GraphSnapshot | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<GraphNode | null>(null)
  const [reload, setReload] = useState(0)
  const hostRef = useRef<HTMLDivElement>(null)
  const sceneRef = useRef<GraphScene | null>(null)
  const lastFetch = useRef(0)
  const layersRef = useRef(layers)

  useEffect(() => {
    const scene = createGraphScene(hostRef.current!, setSelected)
    sceneRef.current = scene
    return () => { scene.dispose(); sceneRef.current = null }
  }, [])

  // Debounce the time-window slider.
  useEffect(() => {
    const id = setTimeout(() => setHours(hoursDraft), 300)
    return () => clearTimeout(id)
  }, [hoursDraft])

  useEffect(() => {
    let cancelled = false
    lastFetch.current = Date.now()
    api.get(`/api/graph?source=${source}&hours=${hours}`, GraphSnapshotSchema)
      .then((s) => { if (!cancelled) { setSnap(s); setError(null) } })
      .catch((e: Error) => { if (!cancelled) setError(e.message) })
    return () => { cancelled = true }
  }, [source, hours, reload])

  // Follow live: re-fetch on a simulation tick, at most every REFRESH_MS.
  useEffect(() => {
    if (follow && sim && Date.now() - lastFetch.current >= REFRESH_MS) setReload((r) => r + 1)
  }, [follow, sim?.tick_number]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!snap) return
    sceneRef.current?.update(snap, layersRef.current)
    setSelected((cur) => {
      const still = cur && snap.nodes.find((n) => n.id === cur.id)
      sceneRef.current?.select(still ? still.id : null)
      return still ?? null
    })
  }, [snap])

  useEffect(() => { layersRef.current = layers; sceneRef.current?.setLayers(layers) }, [layers])
  useEffect(() => { sceneRef.current?.setCamera(preset) }, [preset])

  const stats = useMemo(() => snap && {
    nodes: snap.nodes.length,
    edges: snap.edges.length,
    vehicles: new Set(snap.nodes.flatMap((n) => (n.vehicle_id ? [n.vehicle_id] : []))).size,
  }, [snap])

  return (
    <div className="p-6 grid gap-4 grid-cols-1 lg:grid-cols-[272px_minmax(0,1fr)_256px] lg:h-[calc(100vh-70px)]">
      <aside className="card p-5 flex flex-col gap-5 overflow-y-auto">
        <div>
          <h1 className="text-lg font-semibold">Time-Expanded Graph</h1>
          <p className="text-xs text-muted">Module 4: (hub, time) nodes and vehicle legs</p>
        </div>

        <Section label="Data source">
          <div className="flex rounded-full bg-[var(--surface-tertiary)] p-1" role="radiogroup" aria-label="Data source">
            {(['demo', 'live'] as const).map((s) => (
              <button key={s} role="radio" aria-checked={source === s} disabled={busy} onClick={() => setSource(s)}
                className={`flex-1 rounded-full py-2 text-xs font-medium transition-colors disabled:opacity-60 ${source === s ? 'bg-[var(--foreground)] text-white' : 'text-muted'}`}>
                {s === 'demo' ? `Demo · ${snap?.route_id ?? 'RT-09'}` : 'Live network'}
              </button>
            ))}
          </div>
          <p className="text-[11px] text-muted">
            {source === 'demo'
              ? 'TRUCK-101..110 and misplaced SHP-501..505 on Hyderabad ⇄ Warangal ⇄ Vijayawada.'
              : 'Every online vehicle schedule and hub timeline, including detour variants.'}
            {' '}Switches the app between DEMO simulation and LIVE GPS, same as the navbar.
          </p>
        </Section>

        <Section label="Edge layers">
          {(Object.keys(EDGE_LAYER_META) as EdgeLayer[]).map((k) => (
            <label key={k} className="flex items-center gap-2.5 text-sm cursor-pointer">
              <input type="checkbox" checked={layers[k]} onChange={() => setLayers((l) => ({ ...l, [k]: !l[k] }))} className="accent-[#18181A]" />
              <span className="w-[18px] h-[3px] rounded" style={{ background: EDGE_LAYER_META[k].color }} />
              {EDGE_LAYER_META[k].label}
            </label>
          ))}
        </Section>

        <Section label="Time horizon">
          <input type="range" min={6} max={72} step={2} value={hoursDraft} onChange={(e) => setHoursDraft(Number(e.target.value))} className="w-full accent-[#18181A]" aria-label="Time horizon in hours" />
          <div className="flex justify-between text-[11px]"><span className="text-muted">now</span><span className="font-medium">+{hoursDraft} h</span></div>
        </Section>

        <Section label="Graph size">
          <div className="grid grid-cols-3 gap-2">
            {(['nodes', 'edges', 'vehicles'] as const).map((k) => (
              <div key={k} className="rounded-xl bg-[var(--surface-secondary)] p-2.5">
                <div className="text-lg font-semibold">{stats ? stats[k] : '–'}</div>
                <div className="text-[11px] text-muted">{k}</div>
              </div>
            ))}
          </div>
        </Section>

        <Section label="Camera">
          <div className="flex gap-1.5">
            {(['3d', 'top', 'side'] as const).map((p) => (
              <button key={p} onClick={() => setPreset(p)}
                className={`flex-1 rounded-full py-1.5 text-xs font-medium border border-black/5 ${preset === p ? 'bg-[var(--accent)]' : 'bg-[var(--surface-secondary)]'}`}>
                {p === '3d' ? '3D' : title(p)}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-2 text-xs cursor-pointer">
            <input type="checkbox" checked={follow} onChange={() => setFollow((f) => !f)} className="accent-[#18181A]" />
            Follow live (refresh every {REFRESH_MS / 1000} s)
          </label>
          <p className="text-[11px] text-muted">Drag to orbit · scroll to zoom · right-drag to pan · click a node to inspect</p>
        </Section>
      </aside>

      <div className="relative rounded-2xl overflow-hidden bg-[var(--dark-surface)] min-h-[520px]">
        <div ref={hostRef} className="absolute inset-0" />
        <div className="absolute top-4 left-4 flex items-center gap-2 rounded-full bg-[var(--dark-surface-2)] px-3 py-1.5 text-[11px] font-medium text-white pointer-events-none">
          <span className={`w-2 h-2 rounded-full ${error ? 'bg-[var(--destructive)]' : 'bg-[var(--success)]'}`} />
          {error ? `Graph unavailable: ${error}` : `${source === 'demo' ? `DEMO · ${snap?.route_id ?? ''}` : 'LIVE NETWORK'}${snap ? ` · graph time ${time(snap.now)}` : ' · loading…'}`}
        </div>
        <div className="absolute bottom-4 left-4 flex gap-3.5 rounded-full bg-[var(--dark-surface-2)] px-3 py-1.5 text-[11px] text-[var(--dark-muted)] pointer-events-none">
          <span>↑ time</span><span>floor = hub geography</span><span className="text-[var(--accent)] font-medium">lime = recommended path</span>
        </div>
      </div>

      <Inspector node={selected} snap={snap} />
    </div>
  )
}

function Section({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <div className="text-[11px] uppercase font-semibold tracking-wide text-[var(--subtle-foreground)]">{label}</div>
      {children}
    </section>
  )
}

function Inspector({ node, snap }: { node: GraphNode | null; snap: GraphSnapshot | null }) {
  const edges = useMemo(() => {
    if (!node || !snap) return []
    const at = new Map(snap.nodes.map((n) => [n.id, n]))
    return snap.edges.flatMap((e) => {
      if (e.target === node.id) return [{ dir: 'in', e, other: at.get(e.source)! }]
      if (e.source === node.id) return [{ dir: 'out', e, other: at.get(e.target)! }]
      return []
    })
  }, [node, snap])
  const recs = snap?.recommendations ?? []

  return (
    <aside className="card p-5 flex flex-col gap-4 overflow-y-auto">
      <div className="text-[11px] uppercase font-semibold tracking-wide text-[var(--subtle-foreground)]">Inspector</div>
      {!node ? (
        <p className="text-xs text-muted">Click a node in the graph to see its hub, time, capacity and connecting edges.</p>
      ) : (
        <>
          <div className="flex flex-col gap-1">
            <span className="self-start rounded-full bg-[var(--accent)] px-2 py-0.5 text-[11px] font-medium">{node.kind} node</span>
            <div className="text-base font-semibold">{node.vehicle_id ? `${node.vehicle_id} @ ${node.hub}` : node.hub}</div>
          </div>
          <dl className="text-xs">
            {([
              ['Hub', node.hub],
              ['Time', fmtT(node.t)],
              ...(node.vehicle_id ? [
                ['Free capacity', `${Math.round(node.remaining_kg ?? 0)} of ${Math.round(node.total_kg ?? 0)} kg`],
                ['Variant', node.variant ?? 'main'],
              ] : []),
            ] as [string, string][]).map(([k, v]) => (
              <div key={k} className="flex justify-between py-2 border-b border-[var(--surface-tertiary)]">
                <dt className="text-muted">{k}</dt><dd className="font-medium">{v}</dd>
              </div>
            ))}
          </dl>
          <div className="flex flex-col gap-1.5">
            <div className="text-[11px] uppercase font-semibold tracking-wide text-[var(--subtle-foreground)]">Edges</div>
            {edges.length === 0 && <p className="text-xs text-muted">None inside the time window.</p>}
            {edges.map(({ dir, e, other }) => (
              <div key={`${e.source}>${e.target}`} className="flex items-center gap-2 rounded-lg bg-[var(--surface-secondary)] px-2.5 py-2">
                <span className="w-1 self-stretch rounded" style={{ background: EDGE_LAYER_META[(e.kind in EDGE_LAYER_META ? e.kind : 'wait') as EdgeLayer].color }} />
                <div className="text-[11px]">
                  <div className="font-medium">{dir} · {e.kind}</div>
                  <div className="text-muted">{dir === 'in' ? 'from' : 'to'} {other.kind} {other.hub} {fmtT(other.t)}{e.km ? ` · ${e.km} km` : ''}</div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
      {recs.map((r) => (
        <div key={r.shipment_id} className="rounded-xl bg-[var(--dark-surface)] p-3.5 text-xs text-white flex flex-col gap-1.5">
          <div className="font-semibold text-[var(--accent)]">{r.shipment_id} · recommended</div>
          <div>
            Entry {r.hub} {fmtT(r.t)}
            {r.legs.map((l) => ` → ${l.vehicle_id} ${l.from_hub} ${fmtT(l.dep_t)} → ${l.to_hub} ${fmtT(l.arr_t)}`).join('')}
          </div>
        </div>
      ))}
    </aside>
  )
}
