import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { z } from 'zod'
import { api, session, type SessionUser } from '../lib/api'
import { DEMO_ACCOUNTS } from '../lib/constants'

const LoginResponse = z.object({
  token: z.string(),
  user: z.object({
    username: z.string(),
    role: z.enum(['ADMIN', 'LOGISTICS_OPERATOR', 'DRIVER']),
    vehicle_ids: z.array(z.string()),
  }),
})

const RETRY_MS = 3000

type AuthValue = {
  user: SessionUser | null
  token: string | null
  /** Sign in as another demo account. */
  switchUser: (username: string) => void
  /** Drop the current token and sign in again as the same account (e.g. after a rejected token). */
  reauth: () => void
  error: string | null
  isOperator: boolean
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [username, setUsername] = useState<string>(session.user()?.username ?? DEMO_ACCOUNTS[0].username)
  const [user, setUser] = useState<SessionUser | null>(session.token() ? session.user() : null)
  const [token, setToken] = useState<string | null>(session.user() ? session.token() : null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (token && user?.username === username) return
    const account = DEMO_ACCOUNTS.find((a) => a.username === username) ?? DEMO_ACCOUNTS[0]
    let cancelled = false
    let retry: ReturnType<typeof setTimeout> | undefined
    api.post('/api/auth/login', { username: account.username, password: account.password }, LoginResponse)
      .then((res) => {
        if (cancelled) return
        session.save(res.token, res.user)
        setError(null)
        setToken(res.token)
        setUser(res.user)
      })
      .catch((err) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : 'Sign-in failed')
        retry = setTimeout(() => setAttempt((n) => n + 1), RETRY_MS)
      })
    return () => { cancelled = true; clearTimeout(retry) }
  }, [username, token, user, attempt])

  const switchUser = useCallback((next: string) => {
    if (next === username) return
    session.clear()
    setToken(null)
    setUser(null)
    setUsername(next)
  }, [username])

  const reauth = useCallback(() => {
    session.clearToken()
    setToken(null)
  }, [])

  const value = useMemo(() => ({
    user, token, switchUser, reauth, error,
    isOperator: user?.role === 'ADMIN' || user?.role === 'LOGISTICS_OPERATOR',
  }), [user, token, switchUser, reauth, error])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
