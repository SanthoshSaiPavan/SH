import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { LoginFormSchema } from '../lib/schemas'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ username: '', password: '' })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const parsed = LoginFormSchema.safeParse(form)
    if (!parsed.success) { setError(parsed.error.issues[0].message); return }
    setBusy(true)
    try {
      const user = await login(parsed.data.username, parsed.data.password)
      navigate(user.role === 'DRIVER' ? '/driver' : '/')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally { setBusy(false) }
  }

  return (
    <div className="min-h-full grid place-items-center p-6" style={{ background: 'radial-gradient(circle at 30% 20%, rgba(99,102,241,.18), transparent 50%), radial-gradient(circle at 80% 80%, rgba(168,85,247,.12), transparent 50%)' }}>
      <form onSubmit={submit} className="glass p-8 w-full max-w-sm space-y-4">
        <div className="flex items-center gap-3">
          <img src="/favicon.svg" className="w-12 h-12" alt="" />
          <div>
            <div className="text-2xl font-bold">Piggy<span className="text-piggy">Ship</span></div>
            <div className="text-xs text-muted">Don't lose shipments. Rescue them.</div>
          </div>
        </div>
        <input className="input w-full" placeholder="Username" autoComplete="username" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
        <input className="input w-full" placeholder="Password" type="password" autoComplete="current-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        {error && <div className="text-sm text-danger">{error}</div>}
        <button className="btn btn-primary w-full justify-center" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
      </form>
    </div>
  )
}
