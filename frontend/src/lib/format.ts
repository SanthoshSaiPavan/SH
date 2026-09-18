export const inr = (v: number | null | undefined) =>
  v === null || v === undefined ? '—' : `₹${Math.round(v).toLocaleString('en-IN')}`

export const pct = (v: number | null | undefined, digits = 0) =>
  v === null || v === undefined ? '—' : `${(v * 100).toFixed(digits)}%`

/** Backend timestamps are naive UTC ISO strings. */
export const parseUtc = (iso: string) => new Date(iso.endsWith('Z') || iso.includes('+') ? iso : `${iso}Z`)

export const time = (iso: string | null | undefined) =>
  iso ? parseUtc(iso).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'

export const hours = (h: number | null | undefined) => {
  if (h === null || h === undefined) return '—'
  const sign = h < 0 ? '-' : ''
  const abs = Math.abs(h)
  const hh = Math.floor(abs)
  const mm = Math.round((abs - hh) * 60)
  return `${sign}${hh}h ${mm.toString().padStart(2, '0')}m`
}

export const title = (s: string) => s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
