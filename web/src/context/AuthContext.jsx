import { createContext, useContext, useState, useEffect } from 'react'
import { api } from '../api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) {
      setLoading(false)
      return
    }
    api.auth.me()
      .then((u) => setUser({ id: u.id, email: u.email, name: u.name }))
      .catch(() => {
        localStorage.removeItem('token')
        localStorage.removeItem('jobsdb_user')
        setUser(null)
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    const onLogout = () => setUser(null)
    window.addEventListener('auth-logout', onLogout)
    return () => window.removeEventListener('auth-logout', onLogout)
  }, [])

  const login = async (email, password) => {
    const res = await api.auth.login(email, password)
    localStorage.setItem('token', res.token)
    localStorage.setItem('jobsdb_user', JSON.stringify(res.user))
    setUser(res.user)
  }

  const register = async (email, password, name) => {
    const res = await api.auth.register(email, password, name)
    localStorage.setItem('token', res.token)
    localStorage.setItem('jobsdb_user', JSON.stringify(res.user))
    setUser(res.user)
  }

  const logout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('jobsdb_user')
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
