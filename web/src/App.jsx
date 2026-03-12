import { Navigate } from 'react-router-dom'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import Layout from './components/Layout'
import Login from './pages/Login'
import Register from './pages/Register'
import Dashboard from './pages/Dashboard'
import MonitorSettings from './pages/MonitorSettings'
import JobsDBLogin from './pages/JobsDBLogin'
import JobList from './pages/JobList'
import Logs from './pages/Logs'
import ExternalJobs from './pages/ExternalJobs'
import ManualApply from './pages/ManualApply'
import ExcludedCompanies from './pages/ExcludedCompanies'
import Help from './pages/Help'
import { ToastHost } from './components/Toast'

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="min-h-screen flex items-center justify-center"><div className="animate-spin w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full" /></div>
  if (!user) return <Navigate to="/login" replace />
  return children
}

function AppRoutes() {
  const { user, logout } = useAuth()
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Layout user={user} onLogout={logout} />
          </ProtectedRoute>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="monitor" element={<MonitorSettings />} />
        <Route path="manual-apply" element={<ManualApply />} />
        <Route path="excluded-companies" element={<ExcludedCompanies />} />
        <Route path="jobsdb-login" element={<JobsDBLogin />} />
        <Route path="jobs" element={<JobList />} />
        <Route path="logs" element={<Logs />} />
        <Route path="external" element={<ExternalJobs />} />
        <Route path="help" element={<Help />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ToastHost />
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  )
}
