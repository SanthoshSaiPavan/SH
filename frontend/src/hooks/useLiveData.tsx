import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { z } from 'zod'
import { api } from '../lib/api'
import { pct } from '../lib/format'
import {
  ActionSchema, AlertSchema, DashboardSchema, HubSchema, LiveStateSchema, RecommendationSchema,
  ShipmentSchema, SimStatusSchema, VehicleSchema,
  type Alert, type Dashboard, type Hub, type LiveState, type Recommendation, type RecoveryAction,
  type Shipment, type SimStatus, type Vehicle,
} from '../lib/schemas'
import { useAuth } from './useAuth'
import { useSocket, useSocketEvent } from './useSocket'

export type Progress = { percent_complete: number; eta?: string }
export type Toast = { id: number; kind: 'success' | 'info' | 'danger'; text: string }

type LiveData = {
  hubs: Record<string, Hub>
  vehicles: Record<string, Vehicle>
  shipments: Record<string, Shipment>
  recommendations: Record<string, Recommendation>
  activeRecoveries: RecoveryAction[]
  progress: Record<string, Progress>
  alerts: Alert[]
  dashboard: Dashboard | null
  sim: SimStatus | null
  toasts: Toast[]
  muted: boolean
  setMuted: (m: boolean) => void
  dismissToast: (id: number) => void
  refreshShipment: (id: string) => Promise<void>
  refreshSim: () => Promise<void>
  refreshAll: () => Promise<void>
}

const LiveDataContext = createContext<LiveData | null>(null)

const byId = <T extends { id: string }>(rows: T[]) => Object.fromEntries(rows.map((r) => [r.id, r]))

function beep(freq: number) {
  try {
    const ctx = new AudioContext()
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.frequency.value = freq
    gain.gain.setValueAtTime(0.08, ctx.currentTime)
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.35)
    osc.connect(gain).connect(ctx.destination)
    osc.start()
    osc.stop(ctx.currentTime + 0.35)
  } catch { /* audio not available */ }
}

/** Initial state comes from REST once (and again after a socket reconnect);
 *  every later change arrives as a Socket.IO event. No polling. */
export function LiveDataProvider({ children }: { children: ReactNode }) {
  const { isOperator } = useAuth()
  const { connectionId } = useSocket()
  const [hubs, setHubs] = useState<Record<string, Hub>>({})
  const [vehicles, setVehicles] = useState<Record<string, Vehicle>>({})
  const [shipments, setShipments] = useState<Record<string, Shipment>>({})
  const [recommendations, setRecommendations] = useState<Record<string, Recommendation>>({})
  const [activeRecoveries, setActive] = useState<RecoveryAction[]>([])
  const [progress, setProgress] = useState<Record<string, Progress>>({})
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [dashboard, setDashboard] = useState<Dashboard | null>(null)
  const [sim, setSim] = useState<SimStatus | null>(null)
  const [toasts, setToasts] = useState<Toast[]>([])
  const [muted, setMuted] = useState(false)
  const mutedRef = useRef(muted)
  useEffect(() => { mutedRef.current = muted }, [muted])

  const toast = useCallback((kind: Toast['kind'], text: string) => {
    const id = Date.now() + Math.random()
    setToasts((t) => [...t.slice(-3), { id, kind, text }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 6000)
  }, [])

  const refreshShipment = useCallback(async (id: string) => {
    const s = await api.get(`/api/shipments/${id}`, ShipmentSchema)
    setShipments((prev) => ({ ...prev, [id]: s }))
  }, [])
  const refreshDashboard = useCallback(async () => {
    setDashboard(await api.get('/api/analytics/dashboard', DashboardSchema))
  }, [])
  const refreshActive = useCallback(async () => {
    setActive(await api.get('/api/recovery/active', z.array(ActionSchema)))
  }, [])
  const refreshSim = useCallback(async () => {
    setSim(await api.get('/api/simulation/status', SimStatusSchema))
  }, [])

  const refreshAll = useCallback(async () => {
    const [h, v, s, recs] = await Promise.all([
      api.get('/api/hubs', z.array(HubSchema)),
      api.get('/api/vehicles', z.array(VehicleSchema)),
      api.get('/api/shipments', z.array(ShipmentSchema)),
      api.get('/api/piggyback/opportunities', z.array(RecommendationSchema)),
    ])
    setHubs(byId(h))
    setVehicles(byId(v))
    setShipments(byId(s))
    // Alerts raised before this page connected: rebuild them from the shipments' own detection data.
    setAlerts((prev) => {
      const known = new Set(prev.map((x) => x.shipment_id))
      const missed: Alert[] = s.filter((x) => x.status === 'misplaced' && !known.has(x.id)).map((x) => ({
        shipment_id: x.id, type: x.misplacement_type ?? 'misplaced', severity: x.priority, priority: x.priority,
        message: `Detected ${x.misplacement_type?.replace('_', ' ') ?? 'misplacement'}${x.current_hub_id ? ` at ${x.current_hub_id}` : ''} (before this session)`,
        at: x.misplacement_detected_at ? Date.parse(`${x.misplacement_detected_at}Z`) : Date.now(),
      }))
      return [...prev, ...missed]
    })
    setRecommendations(Object.fromEntries(recs.map((r) => [r.shipment_id, r])))
    await Promise.all([refreshDashboard(), refreshActive(), refreshSim()])
  }, [refreshDashboard, refreshActive, refreshSim])

  useEffect(() => {
    if (!isOperator) return
    refreshAll().catch((err) => toast('danger', `Failed to load data: ${err.message}`))
  }, [isOperator, connectionId, refreshAll, toast])

  useSocketEvent<LiveState>('vehicle:location:update', (raw) => {
    const loc = LiveStateSchema.safeParse(raw)
    if (!loc.success) return
    setVehicles((prev) => {
      const v = prev[loc.data.vehicle_id]
      if (!v) return prev
      return {
        ...prev,
        [v.id]: {
          ...v,
          status: loc.data.status ?? v.status,
          used_capacity_kg: loc.data.used_capacity_kg ?? v.used_capacity_kg,
          live: { ...(v.live ?? {}), ...loc.data, connection: v.live?.connection ?? 'live' },
        },
      }
    })
  })

  useSocketEvent<{ vehicle_id: string; status: string }>('vehicle:status', ({ vehicle_id, status }) => {
    setVehicles((prev) => {
      const v = prev[vehicle_id]
      if (!v?.live) return prev
      return { ...prev, [vehicle_id]: { ...v, live: { ...v.live, connection: status } } }
    })
  })

  useSocketEvent<unknown>('shipment:alert', (raw) => {
    const alert = AlertSchema.safeParse(raw)
    if (!alert.success) return
    setAlerts((a) => [{ ...alert.data, at: Date.now() }, ...a].slice(0, 50))
    if (!mutedRef.current) beep(alert.data.severity === 'critical' ? 880 : 620)
    refreshShipment(alert.data.shipment_id).catch(() => undefined)
    refreshDashboard().catch(() => undefined)
  })

  useSocketEvent<{ shipment_id: string }>('shipment:created', (d) => {
    refreshShipment(d.shipment_id).catch(() => undefined)
    refreshDashboard().catch(() => undefined)
  })

  useSocketEvent<unknown>('piggyback:recommendation', (raw) => {
    const rec = RecommendationSchema.safeParse(raw)
    if (!rec.success) return
    setRecommendations((r) => ({ ...r, [rec.data.shipment_id]: rec.data }))
    if (rec.data.reason && rec.data.reason !== 'initial recommendation') {
      const p = rec.data.on_time_probability
      toast('info', `${rec.data.shipment_id}: ${rec.data.reason}${typeof p === 'number' ? ` (P(on-time) ${pct(p)})` : ''}`)
    }
  })

  useSocketEvent<{ shipment_id: string; strategy: string; vehicle_id: string | null; system_initiated?: boolean }>(
    'recovery:started', (d) => {
      setRecommendations((r) => {
        const { [d.shipment_id]: _removed, ...rest } = r
        return rest
      })
      toast('info', `${d.system_initiated ? 'Auto-executed' : 'Recovery started'}: ${d.shipment_id} → ${d.strategy}${d.vehicle_id ? ` on ${d.vehicle_id}` : ''}`)
      refreshShipment(d.shipment_id).catch(() => undefined)
      refreshActive().catch(() => undefined)
      refreshDashboard().catch(() => undefined)
    })

  useSocketEvent<{ shipment_id: string; at_hub?: string; loaded_on?: string } & Progress>('recovery:progress', (d) => {
    setProgress((p) => ({ ...p, [d.shipment_id]: { percent_complete: d.percent_complete, eta: d.eta } }))
    // Only hub/vehicle hand-offs change the shipment record; timed progress does not.
    if (d.at_hub || d.loaded_on) refreshShipment(d.shipment_id).catch(() => undefined)
  })

  useSocketEvent<{ shipment_id: string; cost_saved: number; time_taken: number }>('recovery:completed', (d) => {
    if (!mutedRef.current) beep(1040)
    toast('success', `${d.shipment_id} recovered — saved ₹${Math.round(d.cost_saved).toLocaleString('en-IN')}`)
    setProgress((p) => ({ ...p, [d.shipment_id]: { percent_complete: 100 } }))
    refreshShipment(d.shipment_id).catch(() => undefined)
    refreshActive().catch(() => undefined)
    refreshDashboard().catch(() => undefined)
  })

  useSocketEvent<{ tick_number: number; timestamp: string; mode: 'demo' | 'live'; running: boolean; speed: number }>(
    'simulation:tick', (d) => {
      setSim((s) => (s ? { ...s, tick_number: d.tick_number, sim_time: d.timestamp, mode: d.mode, running: d.running, speed: d.speed } : s))
    })

  const value = useMemo<LiveData>(() => ({
    hubs, vehicles, shipments, recommendations, activeRecoveries, progress, alerts, dashboard, sim,
    toasts, muted, setMuted, refreshShipment, refreshSim, refreshAll,
    dismissToast: (id: number) => setToasts((t) => t.filter((x) => x.id !== id)),
  }), [hubs, vehicles, shipments, recommendations, activeRecoveries, progress, alerts, dashboard,
    sim, toasts, muted, refreshShipment, refreshSim, refreshAll])

  return <LiveDataContext.Provider value={value}>{children}</LiveDataContext.Provider>
}

export function useLiveData() {
  const ctx = useContext(LiveDataContext)
  if (!ctx) throw new Error('useLiveData must be used inside LiveDataProvider')
  return ctx
}

/** Shipment list with filters, derived from the live store. */
export function useShipments(filters: { status?: string[]; priority?: string[]; hubType?: string[]; q?: string } = {}) {
  const { shipments, hubs } = useLiveData()
  return useMemo(() => Object.values(shipments).filter((s) => {
    if (filters.status?.length && !filters.status.includes(s.status)) return false
    if (filters.priority?.length && !filters.priority.includes(s.priority)) return false
    if (filters.hubType?.length) {
      const hub = hubs[s.current_hub_id ?? s.destination_hub_id]
      if (!hub || !filters.hubType.includes(hub.hub_type)) return false
    }
    if (filters.q) {
      const q = filters.q.toLowerCase()
      if (!s.id.toLowerCase().includes(q) && !s.tracking_number.toLowerCase().includes(q)) return false
    }
    return true
  }).sort((a, b) => a.id.localeCompare(b.id)), [shipments, hubs, filters.status, filters.priority, filters.hubType, filters.q])
}
