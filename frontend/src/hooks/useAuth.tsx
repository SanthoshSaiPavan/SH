import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { z } from 'zod'
import { api, session, type SessionUser } from '../lib/api'

const LoginResponse = z.object({
  token: z.string(),
  user: z.object({
    username: z.string(),
    role: z.enum(['ADMIN', 'LOGISTICS_OPERATOR', 'DRIVER']),
    vehicle_ids: z.array(z.string()),
  }),
})

type AuthValue = {
  user: SessionUser | null
  token: string | null
  login: (username: string, password: string) => Promise<SessionUser>
  logout: () => void
  isOperator: boolean
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(session.user())
  const [token, setToken] = useState<string | null>(session.token())

  const login = useCallback(async (username: string, password: string) => {
    const res = await api.post('/api/auth/login', { username, password }, LoginResponse)
    session.save(res.token, res.user)
    setToken(res.token)
    setUser(res.user)
    return res.user
  }, [])

  const logout = useCallback(() => {
    session.clear()
    setToken(null)
    setUser(null)
  }, [])

  const value = useMemo(() => ({
    user, token, login, logout,
    isOperator: user?.role === 'ADMIN' || user?.role === 'LOGISTICS_OPERATOR',
  }), [user, token, login, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
