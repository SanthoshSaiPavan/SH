import type { ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import Navbar from './components/Navbar'
import Toasts from './components/Toasts'
import { AuthProvider, useAuth } from './hooks/useAuth'
import { LiveDataProvider } from './hooks/useLiveData'
import { SocketProvider } from './hooks/useSocket'
import Analytics from './pages/Analytics'
import Dashboard from './pages/Dashboard'
import Driver from './pages/Driver'
import Login from './pages/Login'
import Recovery from './pages/Recovery'
import Shipments from './pages/Shipments'
import Simulation from './pages/Simulation'

function OperatorShell({ children }: { children: ReactNode }) {
  const { user, isOperator } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  if (!isOperator) return <Navigate to="/driver" replace />
  return (
    <div className="min-h-full flex flex-col">
      <Navbar />
      <main className="flex-1">{children}</main>
      <Toasts />
    </div>
  )
}

function DriverShell() {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  return <Driver />
}

export default function App() {
  return (
    <AuthProvider>
      <SocketProvider>
        <LiveDataProvider>
          <BrowserRouter>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/driver" element={<DriverShell />} />
              <Route path="/" element={<OperatorShell><Dashboard /></OperatorShell>} />
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
