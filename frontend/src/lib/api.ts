import { z } from 'zod'

const TOKEN_KEY = 'piggyship.token'
const USER_KEY = 'piggyship.user'

export type SessionUser = { username: string; role: 'ADMIN' | 'LOGISTICS_OPERATOR' | 'DRIVER'; vehicle_ids: string[] }

function safeGet(key: string): string | null {
  try { return localStorage.getItem(key) } catch { return null }
}
function safeSet(key: string, value: string | null) {
  try {
    if (value === null) localStorage.removeItem(key)
    else localStorage.setItem(key, value)
  } catch { /* storage unavailable */ }
}

export const session = {
  token: (): string | null => safeGet(TOKEN_KEY),
  user: (): SessionUser | null => {
    const raw = safeGet(USER_KEY)
    try { return raw ? (JSON.parse(raw) as SessionUser) : null } catch { return null }
  },
  save(token: string, user: SessionUser) { safeSet(TOKEN_KEY, token); safeSet(USER_KEY, JSON.stringify(user)) },
  clear() { safeSet(TOKEN_KEY, null); safeSet(USER_KEY, null) },
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

async function request(method: string, path: string, body?: unknown): Promise<unknown> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = session.token()
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) })
  if (res.status === 401 && path !== '/api/auth/login') {
    session.clear()
    window.location.assign('/login')
  }
  const data = res.headers.get('content-type')?.includes('json') ? await res.json() : null
  if (!res.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail
    throw new ApiError(res.status, typeof detail === 'string' ? detail : `Request failed (${res.status})`)
  }
  return data
}

/** Typed request: responses are validated with the given Zod schema. */
export const api = {
  get: async <T>(path: string, schema: z.ZodType<T>) => schema.parse(await request('GET', path)),
  post: async <T>(path: string, body: unknown, schema: z.ZodType<T>) => schema.parse(await request('POST', path, body)),
  patch: async <T>(path: string, body: unknown, schema: z.ZodType<T>) => schema.parse(await request('PATCH', path, body)),
}

export const Any = z.unknown()
