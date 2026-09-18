import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../hooks/useAuth'
import { DEMO_ACCOUNTS } from '../lib/constants'

const ROLE_LABEL = { ADMIN: 'Admin', LOGISTICS_OPERATOR: 'Operator', DRIVER: 'Driver' } as const

/** Top-right user icon: switch freely between the admin, operator and driver demo accounts. */
export default function UserMenu() {
  const { user, switchUser } = useAuth()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false) }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onClick)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onClick); document.removeEventListener('keydown', onKey) }
  }, [open])

  return (
    <div ref={ref} className="relative">
      <button className="flex items-center gap-2 rounded-full border border-[var(--border-subtle)] pl-1 pr-3 py-1 text-xs hover:border-[var(--accent-primary)] transition"
        onClick={() => setOpen(!open)} aria-haspopup="menu" aria-expanded={open} title="Switch user">
        <span className="grid place-items-center w-7 h-7 rounded-full bg-primary/20">
          <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <circle cx="12" cy="8" r="4" /><path d="M4 21c0-4 3.6-7 8-7s8 3 8 7" />
          </svg>
        </span>
        <span className="text-left leading-tight">
          <span className="block font-medium">{user ? ROLE_LABEL[user.role] : 'Signing in…'}</span>
          {user && <span className="block text-muted mono text-[10px]">{user.vehicle_ids[0] ?? user.username}</span>}
        </span>
      </button>
      {open && (
        <div role="menu" className="absolute right-0 mt-2 w-56 bg-card border border-[var(--border-subtle)] rounded-xl shadow-xl p-1 z-30 text-sm">
          <div className="px-3 py-1.5 text-[11px] uppercase tracking-wide text-muted">Switch user</div>
          {DEMO_ACCOUNTS.map((a) => {
            const active = a.username === user?.username
            return (
              <button key={a.username} role="menuitemradio" aria-checked={active}
                className={`w-full flex items-center justify-between px-3 py-1.5 rounded-lg text-left transition ${active ? 'bg-primary/20 text-ink' : 'text-muted hover:text-ink hover:bg-primary/10'}`}
                onClick={() => { switchUser(a.username); setOpen(false) }}>
                <span>{a.label}</span>
                {active && <span aria-hidden="true">✓</span>}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
