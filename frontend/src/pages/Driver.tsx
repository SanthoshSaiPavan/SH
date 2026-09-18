import { useCallback, useEffect, useRef, useState } from 'react'
import { useAuth } from '../hooks/useAuth'
import UserMenu from '../components/UserMenu'
import { useSocket } from '../hooks/useSocket'
import { api } from '../lib/api'
import { TEST_DRIVER_USERNAME } from '../lib/constants'
import { VehicleSchema } from '../lib/schemas'

type Fix = { lat: number; lng: number; speed: number; heading: number; at: string }
const SEND_INTERVAL_MS = 2000

/** LIVE GPS: a driver's phone streams browser Geolocation over the socket.
 *  If GPS is unavailable nothing is sent; the server marks the vehicle delayed/offline.
 *  Testing exception: for TEST_DRIVER_USERNAME the page keeps resending the last known
 *  position (or the vehicle's current one) while GPS is unavailable. */
export default function Driver() {
  const { user } = useAuth()
  const { socket, connected } = useSocket()
  const vehicleId = user?.vehicle_ids[0]
  const allowFallback = user?.username === TEST_DRIVER_USERNAME
  const [sharing, setSharing] = useState(false)
  const [fix, setFix] = useState<Fix | null>(null)
  const [status, setStatus] = useState('Not sharing')
  const [sent, setSent] = useState(0)
  const [gpsDown, setGpsDown] = useState(false)
  const lastSent = useRef(0)
  const lastFix = useRef<Fix | null>(null)
  const noGeolocation = !('geolocation' in navigator)

  const send = useCallback((f: Fix, label: string) => {
    if (!socket || !vehicleId) return
    lastSent.current = Date.now()
    socket.emit('vehicle:location', { vehicle_id: vehicleId, lat: f.lat, lng: f.lng, speed: f.speed, heading: f.heading, timestamp: f.at },
      (ack: { ok: boolean; error?: string }) => {
        if (ack?.ok) { setSent((n) => n + 1); setStatus(label) } else setStatus(`Rejected: ${ack?.error ?? 'unknown'}`)
      })
  }, [socket, vehicleId])

  useEffect(() => {
    if (!sharing || !vehicleId || !socket || noGeolocation) return
    const watch = navigator.geolocation.watchPosition((pos) => {
      const f: Fix = {
        lat: pos.coords.latitude, lng: pos.coords.longitude,
        speed: pos.coords.speed !== null ? pos.coords.speed * 3.6 : 0,
        heading: pos.coords.heading ?? 0, at: new Date(pos.timestamp).toISOString(),
      }
      setGpsDown(false)
      setFix(f)
      lastFix.current = f
      if (Date.now() - lastSent.current < SEND_INTERVAL_MS) return
      send(f, 'Sharing live position')
    }, (err) => {
      setStatus(`GPS unavailable: ${err.message}. Keeping last known position.`)
      setGpsDown(true)
    }, { enableHighAccuracy: true, maximumAge: 1000 })
    return () => navigator.geolocation.clearWatch(watch)
  }, [sharing, vehicleId, socket, send, noGeolocation])

  // No-GPS fallback (test driver only): resend the last known position every interval.
  useEffect(() => {
    if (!allowFallback || !sharing || !(gpsDown || noGeolocation) || !vehicleId) return
    let cancelled = false
    let timer: number | undefined
    const start = async () => {
      if (!lastFix.current) {
        try {
          const v = await api.get(`/api/vehicles/${vehicleId}`, VehicleSchema)
          lastFix.current = { lat: v.live?.lat ?? v.current_lat, lng: v.live?.lng ?? v.current_lng,
            speed: 0, heading: v.live?.heading ?? 0, at: new Date().toISOString() }
        } catch {
          if (!cancelled) setStatus('GPS unavailable and vehicle position could not be loaded')
          return
        }
      }
      if (cancelled) return
      const tick = () => {
        const f = { ...lastFix.current!, speed: 0, at: new Date().toISOString() }
        setFix(f)
        send(f, 'GPS unavailable: sending last known position (test mode)')
      }
      tick()
      timer = window.setInterval(tick, SEND_INTERVAL_MS)
    }
    void start()
    return () => { cancelled = true; window.clearInterval(timer) }
  }, [allowFallback, sharing, gpsDown, noGeolocation, vehicleId, send])

  // Heartbeat (test driver only): a stationary laptop fires watchPosition once and then goes quiet,
  // so keep resending the last fix; otherwise the vehicle goes delayed/offline.
  useEffect(() => {
    if (!allowFallback || !sharing || gpsDown || noGeolocation) return
    const timer = window.setInterval(() => {
      if (!lastFix.current || Date.now() - lastSent.current < SEND_INTERVAL_MS) return
      const f = { ...lastFix.current, speed: 0, at: new Date().toISOString() }
      setFix(f)
      send(f, 'Sharing last known position (no new GPS fix, test mode)')
    }, SEND_INTERVAL_MS)
    return () => window.clearInterval(timer)
  }, [allowFallback, sharing, gpsDown, noGeolocation, send])

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
            onClick={() => { setSharing(!sharing); setGpsDown(false) }}>{sharing ? 'Stop sharing' : 'Start LIVE GPS'}</button>
          <div className="text-sm">{sharing && noGeolocation && sent === 0 ? 'Geolocation not supported on this device' : status}</div>
          {fix && <div className="text-xs text-muted mono">{fix.lat.toFixed(5)}, {fix.lng.toFixed(5)} · {fix.speed.toFixed(0)} km/h · sent {sent}</div>}
          <p className="text-[11px] text-muted">The dashboard must be in LIVE GPS mode. Phones only allow geolocation on HTTPS (or localhost).</p>
        </div>
      </div>
    </div>
  )
}
