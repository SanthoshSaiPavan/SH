import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { io, type Socket } from 'socket.io-client'
import { useAuth } from './useAuth'

type SocketValue = {
  socket: Socket | null
  connected: boolean
  /** Increments on every (re)connect so consumers can refetch current state once. */
  connectionId: number
  joinRoom: (room: string) => void
  leaveRoom: (room: string) => void
}

const SocketContext = createContext<SocketValue | null>(null)

/** One Socket.IO connection per session: JWT in the handshake, auto-reconnect with
 *  backoff, and rooms re-joined after every reconnect. */
export function SocketProvider({ children }: { children: ReactNode }) {
  const { token, reauth } = useAuth()
  const [socket, setSocket] = useState<Socket | null>(null)
  const [connected, setConnected] = useState(false)
  const [connectionId, setConnectionId] = useState(0)
  const rooms = useRef(new Set<string>())

  useEffect(() => {
    if (!token) return
    const s = io({
      auth: { token },
      transports: ['websocket'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 10000,
    })
    s.on('connect', () => {
      setConnected(true)
      setConnectionId((n) => n + 1)
      rooms.current.forEach((room) => s.emit('room:join', { room }))
    })
    s.on('disconnect', () => setConnected(false))
    s.on('connect_error', (err) => {
      setConnected(false)
      if (err.message === 'invalid token') reauth()
    })
    setSocket(s)
    return () => {
      s.disconnect()
      setSocket(null)
      setConnected(false)
    }
  }, [token, reauth])

  const joinRoom = useCallback((room: string) => {
    rooms.current.add(room)
    socket?.emit('room:join', { room })
  }, [socket])

  const leaveRoom = useCallback((room: string) => {
    rooms.current.delete(room)
    socket?.emit('room:leave', { room })
  }, [socket])

  return (
    <SocketContext.Provider value={{ socket, connected, connectionId, joinRoom, leaveRoom }}>
      {children}
    </SocketContext.Provider>
  )
}

export function useSocket() {
  const ctx = useContext(SocketContext)
  if (!ctx) throw new Error('useSocket must be used inside SocketProvider')
  return ctx
}

/** Subscribe to a server event for the lifetime of the component. */
export function useSocketEvent<T>(event: string, handler: (data: T) => void) {
  const { socket } = useSocket()
  const ref = useRef(handler)
  useEffect(() => { ref.current = handler })
  useEffect(() => {
    if (!socket) return
    const fn = (data: T) => ref.current(data)
    socket.on(event, fn)
    return () => { socket.off(event, fn) }
  }, [socket, event])
}
