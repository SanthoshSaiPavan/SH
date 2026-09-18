import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import LiveMap, { shipmentPosition, type RouteOverlay } from '../components/LiveMap'
import RecoveryModal from '../components/RecoveryModal'
import Sidebar, { type Filters } from '../components/Sidebar'
import { useLiveData, useShipments } from '../hooks/useLiveData'

/** Router state other pages pass when linking here: a shipment to fly to and/or a route to highlight. */
export type MapLinkState = { shipmentId?: string; route?: string[] }

export default function MapView() {
  const { hubs, vehicles, shipments, activeRecoveries } = useLiveData()
  const location = useLocation()
  const navigate = useNavigate()
  const [filters, setFilters] = useState<Filters>({ hubType: [], priority: [], status: [] })
  const [selected, setSelected] = useState<string | null>(null)
  const [viewRoutes, setViewRoutes] = useState<RouteOverlay[] | null>(null)
  const [focus, setFocus] = useState<{ lng: number; lat: number } | null>(null)

  const filtered = useShipments(filters)
  const onMap = useMemo(() => filtered.filter((s) => !['delivered', 'in_transit'].includes(s.status)), [filtered])

  const overlays = useMemo<RouteOverlay[]>(() => {
    const routes: RouteOverlay[] = activeRecoveries.map((a) => ({ id: a.id, hubs: a.recovery_route?.hubs ?? [], color: '#a855f7' }))
    if (viewRoutes) routes.push(...viewRoutes)
    return routes
  }, [activeRecoveries, viewRoutes])

  const positionOf = useCallback((id: string) => {
    const s = shipments[id]
    const pos = s && shipmentPosition(s, vehicles)
    return pos ? { lng: pos[0], lat: pos[1] } : null
  }, [shipments, vehicles])

  const openShipment = (id: string) => {
    const pos = positionOf(id)
    if (pos) setFocus(pos)
    if (shipments[id]?.status === 'misplaced') setSelected(id)
  }

  // Apply a link from another page once the shipment data is loaded, then clear it so a reload doesn't replay it.
  const link = location.state as MapLinkState | null
  const linkReady = !link?.shipmentId || Boolean(shipments[link.shipmentId])
  useEffect(() => {
    if (!link || !linkReady) return
    if (link.route) setViewRoutes([{ id: 'view', hubs: link.route, color: '#64ffda' }])
    const pos = link.shipmentId ? positionOf(link.shipmentId) : null
    if (pos) setFocus(pos)
    navigate(location.pathname, { replace: true, state: null })
  }, [link, linkReady, positionOf, navigate, location.pathname])

  return (
    <div style={{ padding: '32px', maxWidth: '1440px', margin: '0 auto', height: 'calc(100vh - 70px)', display: 'flex', gap: '24px' }}>
      <Sidebar filters={filters} onChange={setFilters} />
      <div className="flex-1 min-w-0 flex flex-col gap-3">
        <LiveMap className="flex-1 min-h-[420px]" hubs={hubs} vehicles={vehicles} shipments={onMap} routes={overlays}
          onShipmentClick={openShipment} focus={focus} />
        {viewRoutes && <button className="btn self-start" onClick={() => setViewRoutes(null)}>Clear highlighted route(s)</button>}
      </div>
      {selected && shipments[selected] && (
        <RecoveryModal shipment={shipments[selected]} onClose={() => setSelected(null)}
          onViewRoutes={(r) => { setViewRoutes(r); setSelected(null) }} />
      )}
    </div>
  )
}
