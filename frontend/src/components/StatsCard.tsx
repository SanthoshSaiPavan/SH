import React from 'react'

type Props = {
  label: string
  value: string | number
  hint?: string
  color?: 'accent' | 'success' | 'warning' | 'danger' | 'info' | 'default'
  icon?: React.ReactNode
}

export default function StatsCard({ label, value, hint }: Props) {
  return (
    <div className="card" style={{
      padding: '16px 20px',
      display: 'flex',
      flexDirection: 'column',
      gap: '8px',
      border: '1px solid rgba(0,0,0,0.03)',
    }}>
      {/* Label row */}
      <div style={{
        fontSize: '12px', fontWeight: 500,
        color: 'var(--muted-foreground)',
      }}>
        {label}
      </div>

      {/* Value */}
      <div style={{
        fontSize: '28px', fontWeight: 600,
        letterSpacing: '-0.02em', lineHeight: 1,
        color: 'var(--foreground)',
      }}>
        {value}
      </div>

      {/* Hint */}
      {hint && (
        <div style={{ fontSize: '13px', color: 'var(--subtle-foreground)' }}>
          {hint}
        </div>
      )}
    </div>
  )
}
