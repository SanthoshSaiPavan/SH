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
  if (abs >= 48) return `${sign}${Math.floor(abs / 24)}d ${Math.floor(abs % 24)}h`
  const totalMin = Math.round(abs * 60)
  return `${sign}${Math.floor(totalMin / 60)}h ${(totalMin % 60).toString().padStart(2, '0')}m`
}

/** Deadline countdown: "6h 30m left" or "overdue by 3d 4h". */
export const timeLeft = (h: number) => (h < 0 ? `overdue by ${hours(-h)}` : `${hours(h)} left`)

export const title = (s: string) => s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
