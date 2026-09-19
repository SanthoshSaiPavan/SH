import { useLiveData } from '../hooks/useLiveData'
import { time } from '../lib/format'
import ModeToggle from './ModeToggle'
import UserMenu from './UserMenu'
import { Bell, BellOff } from 'lucide-react'
import { SlideTabs } from './ui/slide-tabs'

export default function Navbar() {
  const { sim, muted, setMuted } = useLiveData()

  return (
    <header style={{
      height: '70px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '0 32px',
      background: 'var(--background)',
      borderBottom: '1px solid rgba(0,0,0,0.05)',
      position: 'sticky',
      top: 0,
      zIndex: 50,
    }}>
      {/* Logo */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <div style={{
          width: '32px', height: '32px',
          background: 'var(--foreground)',
          borderRadius: '8px',
          display: 'grid', placeItems: 'center',
        }}>
          <span style={{ fontSize: '13px', fontWeight: 700, color: '#FFFFFF', letterSpacing: '-0.04em' }}>PQ</span>
        </div>
        <span style={{ fontSize: '18px', fontWeight: 600, color: 'var(--foreground)', letterSpacing: '-0.03em' }}>
          PiggyIQ
        </span>
      </div>

      {/* SlideTabs Navigation */}
      <SlideTabs />

      {/* Right side */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <ModeToggle />
        {sim && (
          <span style={{
            fontSize: '12px',
            fontFamily: 'var(--font-mono)',
            color: 'var(--subtle-foreground)',
          }}>
            {time(sim.sim_time)}
          </span>
        )}

        <button
          onClick={() => setMuted(!muted)}
          title={muted ? 'Unmute alerts' : 'Mute alerts'}
          style={{
            width: '36px', height: '36px',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: '#FFFFFF',
            border: '1px solid rgba(0,0,0,0.05)',
            borderRadius: '50%',
            color: 'var(--foreground)',
            cursor: 'pointer',
            boxShadow: '0 2px 8px rgba(0,0,0,0.02)',
          }}
        >
          {muted ? <BellOff size={16} /> : <Bell size={16} />}
        </button>

        <UserMenu />
      </div>
    </header>
  )
}
