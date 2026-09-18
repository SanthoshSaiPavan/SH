import maplibregl from '../lib/maplibre'
import type { Feature, FeatureCollection, LineString } from 'geojson'
import type { GeoJSONSource, Map as MLMap } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useEffect, useRef, useState } from 'react'
import { ensureRoadPaths, hubLine, hubPairs } from '../lib/roads'
import { CONNECTION_COLORS, MAP_CONFIG, MARKER_ANIMATION_MS, PRIORITY_META } from '../lib/constants'
import type { Hub, Shipment, Vehicle } from '../lib/schemas'

export type RouteOverlay = { id: string; hubs: string[]; color: string; dashed?: boolean }

type Props = {
  hubs: Record<string, Hub>
  vehicles: Record<string, Vehicle>
  shipments: Shipment[]
  routes?: RouteOverlay[]
  showPlannedRoutes?: boolean
  onShipmentClick?: (id: string) => void
  focus?: { lng: number; lat: number; zoom?: number } | null
  className?: string
}

type Animated = { marker: maplibregl.Marker; arrow: HTMLElement; dot: HTMLElement; from: [number, number]; to: [number, number]; start: number }

const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] }

function lineFeatures(routes: RouteOverlay[], hubs: Record<string, Hub>): FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: routes.map((r): Feature<LineString> => ({
      type: 'Feature',
      properties: { color: r.color, dashed: r.dashed ? 1 : 0 },
      geometry: {
        type: 'LineString',
        coordinates: hubLine(r.hubs, hubs),
      },
    })).filter((f) => f.geometry.coordinates.length > 1),
  }
}

export function vehiclePosition(v: Vehicle): [number, number] {
  return v.live ? [v.live.lng, v.live.lat] : [v.current_lng, v.current_lat]
}

export function shipmentPosition(s: Shipment, vehicles: Record<string, Vehicle>): [number, number] | null {
  const carrier = s.current_vehicle_id ? vehicles[s.current_vehicle_id] : undefined
  if (carrier) return vehiclePosition(carrier)
  return s.current_lat !== null && s.current_lng !== null ? [s.current_lng, s.current_lat] : null
}

export default function LiveMap({ hubs, vehicles, shipments, routes = [], showPlannedRoutes = true, onShipmentClick, focus, className }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const map = useRef<MLMap | null>(null)
  const [ready, setReady] = useState(false)
  const [roadsVersion, setRoadsVersion] = useState(0)
  const vehicleMarkers = useRef(new Map<string, Animated>())
  const shipmentMarkers = useRef(new Map<string, maplibregl.Marker>())
  const hubMarkers = useRef(new Map<string, maplibregl.Marker>())
  const clickRef = useRef(onShipmentClick)
  useEffect(() => { clickRef.current = onShipmentClick })

  // Map instance + animation loop
  useEffect(() => {
    if (!container.current) return
    const m = new maplibregl.Map({ 
      container: container.current, 
      style: MAP_CONFIG.style, 
      center: MAP_CONFIG.center, 
      zoom: MAP_CONFIG.zoom, 
      attributionControl: { compact: true } 
    })
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    m.on('load', () => {
      m.addSource('planned', { type: 'geojson', data: EMPTY })
      m.addLayer({ id: 'planned', type: 'line', source: 'planned', paint: { 'line-color': ['get', 'color'], 'line-width': 3, 'line-opacity': 0.6, 'line-dasharray': [2, 2] } })
      
      m.addSource('overlay', { type: 'geojson', data: EMPTY })
      // Casing / Border for Google Maps style
      m.addLayer({ id: 'overlay-casing', type: 'line', source: 'overlay', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#FFFFFF', 'line-width': 7, 'line-opacity': 0.9 } })
      // Inner line (colored by strategy)
      m.addLayer({ id: 'overlay', type: 'line', source: 'overlay', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': ['get', 'color'], 'line-width': 4 } })
      
      setReady(true)
    })
    map.current = m
    let frame = 0
    const animate = () => {
      const now = performance.now()
      vehicleMarkers.current.forEach((a) => {
        const t = Math.min(1, (now - a.start) / MARKER_ANIMATION_MS)
        a.marker.setLngLat([a.from[0] + (a.to[0] - a.from[0]) * t, a.from[1] + (a.to[1] - a.from[1]) * t])
      })
      frame = requestAnimationFrame(animate)
    }
    frame = requestAnimationFrame(animate)
    const vMarkers = vehicleMarkers.current
    const sMarkers = shipmentMarkers.current
    const hMarkers = hubMarkers.current
    return () => {
      cancelAnimationFrame(frame)
      vMarkers.clear(); sMarkers.clear(); hMarkers.clear()
      setReady(false)
      m.remove()
    }
  }, [])

  // Hubs
  useEffect(() => {
    const m = map.current
    if (!m) return
    Object.values(hubs).forEach((h) => {
      if (hubMarkers.current.has(h.id)) return
      const el = document.createElement('div')
      el.innerHTML = `<div style="display:flex;align-items:center;gap:4px"><span style="font-size:16px;line-height:1">🏢</span><span style="font:600 10px Inter;color:#cfd8f5;text-shadow:0 0 3px #000">${h.city}</span></div>`
      const marker = new maplibregl.Marker({ element: el, anchor: 'left', offset: [-9, 0] })
        .setLngLat([h.lng, h.lat])
        .setPopup(new maplibregl.Popup({ offset: 10 }).setHTML(`<b>${h.name}</b><br/>${h.id} · ${h.hub_type}<br/>Capacity ${h.capacity_packages}`))
        .addTo(m)
      hubMarkers.current.set(h.id, marker)
    })
  }, [hubs])

  // Vehicles: one marker each, animated from the displayed position to the new one
  useEffect(() => {
    const m = map.current
    if (!m) return
    const now = performance.now()
    Object.values(vehicles).forEach((v) => {
      const to = vehiclePosition(v)
      const connection = v.live?.connection ?? 'offline'
      const existing = vehicleMarkers.current.get(v.id)
      if (existing) {
        const cur = existing.marker.getLngLat()
        if (cur.lng !== to[0] || cur.lat !== to[1]) {
          existing.from = [cur.lng, cur.lat]
          existing.to = to
          existing.start = now
        }
        existing.arrow.style.transform = `rotate(${v.live?.heading ?? 0}deg)`
        existing.dot.style.background = CONNECTION_COLORS[connection] ?? '#8892b0'
        existing.marker.getPopup()?.setHTML(vehiclePopup(v))
        return
      }
      const el = document.createElement('div')
      el.className = 'vehicle-marker cursor-pointer'
      el.innerHTML = `<div style="position:relative; z-index: 10;"><div class="arrow" style="position:absolute;inset:-16px;display:flex;justify-content:center;transition:transform .6s"><div style="width:0;height:0;border-left:6px solid transparent;border-right:6px solid transparent;border-bottom:10px solid #a5b4fc"></div></div><span style="font-size:26px; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3)); position:relative; z-index:2;">🚚</span><div class="dot" style="position:absolute; bottom:-4px; right:-4px; width:12px; height:12px; border-radius:50%; border:2px solid white; z-index:3;"></div></div>`
      const arrow = el.querySelector('.arrow') as HTMLElement
      const dot = el.querySelector('.dot') as HTMLElement
      arrow.style.transform = `rotate(${v.live?.heading ?? 0}deg)`
      dot.style.background = CONNECTION_COLORS[connection] ?? '#8892b0'
      const marker = new maplibregl.Marker({ element: el })
        .setLngLat(to)
        .setPopup(new maplibregl.Popup({ offset: 16 }).setHTML(vehiclePopup(v)))
        .addTo(m)
      vehicleMarkers.current.set(v.id, { marker, arrow, dot, from: to, to, start: now })
    })
  }, [vehicles])

  // Misplaced / recovering shipments (📦 colored by priority tier)
  useEffect(() => {
    const m = map.current
    if (!m) return
    const seen = new Set<string>()
    shipments.forEach((s) => {
      const pos = shipmentPosition(s, vehicles)
      if (!pos) return
      seen.add(s.id)
      const color = PRIORITY_META[s.priority].color
      const existing = shipmentMarkers.current.get(s.id)
      if (existing) {
        existing.setLngLat(pos)
        existing.getElement().style.borderColor = color
        return
      }
      const el = document.createElement('div')
      el.className = 'shipment-marker cursor-pointer'
      el.style.borderColor = color
      el.style.fontSize = '22px'
      el.style.filter = 'drop-shadow(0 2px 4px rgba(0,0,0,0.2))'
      el.style.transform = 'translateY(-50%)'
      el.title = `${s.id} (${s.priority})`
      el.textContent = '📦'
      el.addEventListener('click', (e) => { e.stopPropagation(); clickRef.current?.(s.id) })
      shipmentMarkers.current.set(s.id, new maplibregl.Marker({ element: el }).setLngLat(pos).addTo(m))
    })
    shipmentMarkers.current.forEach((marker, id) => {
      if (!seen.has(id)) { marker.remove(); shipmentMarkers.current.delete(id) }
    })
  }, [shipments, vehicles])

  // Route lines: planned (remaining stops of every vehicle) + overlays (recovery paths),
  // drawn along cached road geometry; missing roads are fetched once, then redrawn.
  useEffect(() => {
    const m = map.current
    if (!m) return
    if (!ready) return
    const planned: RouteOverlay[] = showPlannedRoutes
        ? Object.values(vehicles).map((v) => ({
          id: v.id, color: '#6366f1',
          hubs: v.planned_route.slice(Math.max(0, v.current_stop_index - (v.status === 'at_hub' ? 0 : 1))),
        }))
        : []
    ;(m.getSource('planned') as GeoJSONSource | undefined)?.setData(lineFeatures(planned, hubs))
    ;(m.getSource('overlay') as GeoJSONSource | undefined)?.setData(lineFeatures(routes, hubs))
    const pairs = [...planned, ...routes].flatMap((r) => hubPairs(r.hubs))
    ensureRoadPaths(pairs).then((added) => { if (added) setRoadsVersion((n) => n + 1) }).catch(() => undefined)
  }, [ready, vehicles, hubs, routes, showPlannedRoutes, roadsVersion])

  useEffect(() => {
    if (focus && map.current) map.current.flyTo({ center: [focus.lng, focus.lat], zoom: focus.zoom ?? 7 })
  }, [focus])

  return (
    <div className={`relative ${className ?? ''}`}>
      <div ref={container} className="w-full h-full rounded-2xl overflow-hidden" />
      <div className="absolute left-3 bottom-3 glass px-3 py-2 text-[11px] text-muted space-y-1 pointer-events-none">
        <div className="flex gap-3">
          <span>🏢 hub</span><span>🚚 vehicle</span><span>📦 misplaced</span>
          <span><span style={{ color: '#10b981' }}>●</span> live</span>
          <span><span style={{ color: '#f59e0b' }}>●</span> delayed</span>
          <span><span style={{ color: '#ef4444' }}>●</span> offline</span>
        </div>
        <div className="flex gap-3">
          <span><span style={{ color: '#6366f1' }}>- - -</span> planned route</span>
          <span><span style={{ color: '#a855f7' }}>━━</span> recovery route</span>
        </div>
      </div>
    </div>
  )
}

function vehiclePopup(v: Vehicle) {
  const used = v.used_capacity_kg / v.total_capacity_kg
  const next = v.planned_route[v.current_stop_index] ?? '—'
  return `<b>${v.id}</b> · ${v.vehicle_type}<br/>${v.carrier_name}<br/>` +
    `Next: ${next}<br/>Load ${(used * 100).toFixed(0)}% of ${v.total_capacity_kg.toLocaleString()} kg<br/>` +
    `Speed ${Math.round(v.live?.speed ?? v.speed_kmh)} km/h · ${v.live?.connection ?? 'offline'}`
}
