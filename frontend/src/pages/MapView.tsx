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
  const [viewRoute, setViewRoute] = useState<string[] | null>(null)
  const [focus, setFocus] = useState<{ lng: number; lat: number } | null>(null)

  const filtered = useShipments(filters)
  const onMap = useMemo(() => filtered.filter((s) =>
    s.status === 'misplaced' || (s.recovery_strategy && !['recovered', 'delivered'].includes(s.status))), [filtered])

  const overlays = useMemo<RouteOverlay[]>(() => {
    const routes: RouteOverlay[] = activeRecoveries.map((a) => ({ id: a.id, hubs: a.recovery_route?.hubs ?? [], color: '#a855f7' }))
    if (viewRoute) routes.push({ id: 'view', hubs: viewRoute, color: '#64ffda' })
    return routes
  }, [activeRecoveries, viewRoute])

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
    if (link.route) setViewRoute(link.route)
    const pos = link.shipmentId ? positionOf(link.shipmentId) : null
    if (pos) setFocus(pos)
    navigate(location.pathname, { replace: true, state: null })
  }, [link, linkReady, positionOf, navigate, location.pathname])

  return (
    <div className="flex gap-4 p-4 h-[calc(100vh-3.5rem)]">
      <Sidebar filters={filters} onChange={setFilters} />
      <div className="flex-1 min-w-0 flex flex-col gap-3">
        <LiveMap className="flex-1 min-h-[420px]" hubs={hubs} vehicles={vehicles} shipments={onMap} routes={overlays}
          onShipmentClick={openShipment} focus={focus} />
        {viewRoute && <button className="btn self-start" onClick={() => setViewRoute(null)}>Clear highlighted route ({viewRoute.join(' → ')})</button>}
      </div>
      {selected && shipments[selected] && (
        <RecoveryModal shipment={shipments[selected]} onClose={() => setSelected(null)}
          onViewRoute={(h) => { setViewRoute(h); setSelected(null) }} />
      )}
    </div>
  )
}
