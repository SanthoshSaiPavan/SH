import type { ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import Navbar from './components/Navbar'
import Toasts from './components/Toasts'
import UserMenu from './components/UserMenu'
import { AuthProvider, useAuth } from './hooks/useAuth'
import { LiveDataProvider } from './hooks/useLiveData'
import { SocketProvider } from './hooks/useSocket'
import { TEST_DRIVER_USERNAME } from './lib/constants'
import Analytics from './pages/Analytics'
import Dashboard from './pages/Dashboard'
import Driver from './pages/Driver'
import MapView from './pages/MapView'
import Recovery from './pages/Recovery'
import Shipments from './pages/Shipments'
import Simulation from './pages/Simulation'

/** Shown while the app signs in as the selected demo account (no login page). */
function SigningIn() {
  const { error } = useAuth()
  return (
    <div className="min-h-full grid place-items-center p-6 text-sm text-muted">
      {error ? `Can't reach the backend (${error}). Retrying…` : 'Signing in…'}
    </div>
  )
}

function OperatorShell({ children }: { children: ReactNode }) {
  const { user, isOperator } = useAuth()
  if (!user) return <SigningIn />
  if (!isOperator) return <Navigate to="/driver" replace />
  return (
    <div className="min-h-full flex flex-col">
      <Navbar />
      <main className="flex-1 overflow-y-auto overflow-x-hidden relative bg-[var(--background)]">{children}</main>
      <Toasts />
    </div>
  )
}

function DriverShell() {
  const { user, isOperator } = useAuth()
  if (!user) return <SigningIn />
  if (isOperator) return <Navigate to="/" replace />
  if (user.username !== TEST_DRIVER_USERNAME) {
    return (
      <div className="min-h-full flex flex-col">
        <header className="flex justify-end px-5 h-14 items-center">
          <UserMenu />
        </header>
        <div className="flex-1 grid place-items-center p-6">
          <div className="glass p-6 w-full max-w-sm space-y-4 text-center">
            <div className="text-xl font-bold">Access denied</div>
            <div className="text-sm text-muted">The driver dashboard is currently limited to {TEST_DRIVER_USERNAME}. Switch user from the menu.</div>
          </div>
        </div>
      </div>
    )
  }
  return <Driver key={user.username} />
}

export default function App() {
  return (
    <AuthProvider>
      <SocketProvider>
        <LiveDataProvider>
          <BrowserRouter>
            <Routes>
              <Route path="/driver" element={<DriverShell />} />
              <Route path="/" element={<OperatorShell><Dashboard /></OperatorShell>} />
              <Route path="/map" element={<OperatorShell><MapView /></OperatorShell>} />
              <Route path="/shipments" element={<OperatorShell><Shipments /></OperatorShell>} />
              <Route path="/recovery" element={<OperatorShell><Recovery /></OperatorShell>} />
              <Route path="/analytics" element={<OperatorShell><Analytics /></OperatorShell>} />
              <Route path="/simulation" element={<OperatorShell><Simulation /></OperatorShell>} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </BrowserRouter>
        </LiveDataProvider>
      </SocketProvider>
    </AuthProvider>
  )
}
