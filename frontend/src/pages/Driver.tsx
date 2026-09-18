import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../hooks/useAuth'
import { useSocket } from '../hooks/useSocket'
import UserMenu from '../components/UserMenu'

type Fix = { lat: number; lng: number; speed: number; heading: number; at: string }
const SEND_INTERVAL_MS = 2000

/** LIVE GPS: a driver's phone streams browser Geolocation over the socket.
 *  If GPS is unavailable nothing is sent; the server marks the vehicle delayed/offline. */
export default function Driver() {
  const { user } = useAuth()
  const { socket, connected } = useSocket()
  const vehicleId = user?.vehicle_ids[0]
  const [sharing, setSharing] = useState(false)
  const [fix, setFix] = useState<Fix | null>(null)
  const [status, setStatus] = useState('Not sharing')
  const [sent, setSent] = useState(0)
  const lastSent = useRef(0)

  useEffect(() => {
    if (!sharing || !vehicleId || !socket) return
    if (!('geolocation' in navigator)) { setStatus('Geolocation not supported on this device'); return }
    const watch = navigator.geolocation.watchPosition((pos) => {
      const f: Fix = {
        lat: pos.coords.latitude, lng: pos.coords.longitude,
        speed: pos.coords.speed !== null ? pos.coords.speed * 3.6 : 0,
        heading: pos.coords.heading ?? 0, at: new Date(pos.timestamp).toISOString(),
      }
      setFix(f)
      if (Date.now() - lastSent.current < SEND_INTERVAL_MS) return
      lastSent.current = Date.now()
      socket.emit('vehicle:location', { vehicle_id: vehicleId, lat: f.lat, lng: f.lng, speed: f.speed, heading: f.heading, timestamp: f.at },
        (ack: { ok: boolean; error?: string }) => {
          if (ack?.ok) { setSent((n) => n + 1); setStatus('Sharing live position') } else setStatus(`Rejected: ${ack?.error ?? 'unknown'}`)
        })
    }, (err) => setStatus(`GPS unavailable: ${err.message}. Keeping last known position.`), { enableHighAccuracy: true, maximumAge: 1000 })
    return () => navigator.geolocation.clearWatch(watch)
  }, [sharing, vehicleId, socket])

  return (
    <div className="min-h-full flex flex-col">
      <header className="flex justify-end px-5 h-14 items-center">
        <UserMenu />
      </header>
      <div className="flex-1 grid place-items-center p-6">
        <div className="glass p-6 w-full max-w-sm space-y-4 text-center">
          <div className="text-4xl">🚚</div>
          <div className="text-xl font-bold mono">{vehicleId ?? 'No vehicle assigned'}</div>
          <div className="text-xs text-muted">{user?.username} · socket {connected ? 'connected' : 'reconnecting…'}</div>
          <button className={`btn w-full justify-center ${sharing ? 'btn-danger' : 'btn-success'}`} disabled={!vehicleId}
            onClick={() => setSharing(!sharing)}>{sharing ? 'Stop sharing' : 'Start LIVE GPS'}</button>
          <div className="text-sm">{status}</div>
          {fix && <div className="text-xs text-muted mono">{fix.lat.toFixed(5)}, {fix.lng.toFixed(5)} · {fix.speed.toFixed(0)} km/h · sent {sent}</div>}
          <p className="text-[11px] text-muted">The dashboard must be in LIVE GPS mode. Phones only allow geolocation on HTTPS (or localhost).</p>
        </div>
      </div>
    </div>
  )
}
