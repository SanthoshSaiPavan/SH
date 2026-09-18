import { NavLink } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { useLiveData } from '../hooks/useLiveData'
import { useSocket } from '../hooks/useSocket'
import { time } from '../lib/format'
import ModeToggle from './ModeToggle'

const LINKS = [
  ['/', 'Dashboard'], ['/shipments', 'Shipments'], ['/recovery', 'Recovery'],
  ['/analytics', 'Analytics'], ['/simulation', 'Simulation'],
] as const

export default function Navbar() {
  const { user, logout } = useAuth()
  const { connected } = useSocket()
  const { sim, muted, setMuted } = useLiveData()
  return (
    <header className="flex items-center gap-6 px-5 h-14 border-b border-[var(--border-subtle)] bg-card/80 backdrop-blur sticky top-0 z-20">
      <div className="flex items-center gap-2 font-bold text-lg">
        <img src="/favicon.svg" className="w-7 h-7" alt="" />
        <span>Piggy<span className="text-piggy">Ship</span></span>
      </div>
      <nav className="flex gap-1">
        {LINKS.map(([to, label]) => (
          <NavLink key={to} to={to} end={to === '/'}
            className={({ isActive }) => `px-3 py-1.5 rounded-lg text-sm font-medium transition ${isActive ? 'bg-primary/20 text-ink' : 'text-muted hover:text-ink'}`}>
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="ml-auto flex items-center gap-4 text-xs">
        <ModeToggle />
        {sim && <span className="mono text-muted" title="Engine clock">⏱ {time(sim.sim_time)}</span>}
        <span className="flex items-center gap-1.5" title="Socket connection">
          <span className={`w-2 h-2 rounded-full ${connected ? 'bg-success' : 'bg-danger'}`} />
          {connected ? 'Live' : 'Reconnecting…'}
        </span>
        <button className="text-muted hover:text-ink" onClick={() => setMuted(!muted)} title="Alert sounds">{muted ? '🔇' : '🔔'}</button>
        <span className="text-muted">{user?.username} · {user?.role}</span>
        <button className="btn" onClick={logout}>Logout</button>
      </div>
    </header>
  )
}
