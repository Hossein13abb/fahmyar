import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import client, { friendlyError } from '../api/client'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      const raw = localStorage.getItem('fahmyar_user')
      return raw ? JSON.parse(raw) : null
    } catch {
      return null
    }
  })
  const [token, setToken] = useState(() => localStorage.getItem('fahmyar_token'))
  const [booting, setBooting] = useState(true)

  useEffect(() => {
    // اعتبار اولیهٔ نشست از localStorage (توکن منقضی به‌زودی با ۴۰۱ پاک می‌شود)
    setBooting(false)
  }, [])

  const persist = useCallback((newToken, newUser) => {
    localStorage.setItem('fahmyar_token', newToken)
    localStorage.setItem('fahmyar_user', JSON.stringify(newUser))
    setToken(newToken)
    setUser(newUser)
  }, [])

  const login = useCallback(
    async (username, password) => {
      const { data } = await client.post('/api/auth/login', { username, password })
      const jwt = data?.access_token || data?.token
      if (!jwt) throw new Error('توکن از سرور دریافت نشد.')
      persist(jwt, data.user)
      return data.user
    },
    [persist],
  )

  const register = useCallback(
    async (payload) => {
      const { data } = await client.post('/api/auth/register', payload)
      const jwt = data?.access_token || data?.token
      if (!jwt) throw new Error('توکن از سرور دریافت نشد.')
      persist(jwt, data.user)
      return data.user
    },
    [persist],
  )

  const logout = useCallback(() => {
    localStorage.removeItem('fahmyar_token')
    localStorage.removeItem('fahmyar_user')
    setToken(null)
    setUser(null)
  }, [])

  const value = useMemo(
    () => ({
      user,
      token,
      booting,
      isAuthenticated: Boolean(token && user),
      isTeacher: user?.role === 'teacher' || user?.role === 'admin',
      login,
      register,
      logout,
      friendlyError,
    }),
    [user, token, booting, login, register, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth باید داخل AuthProvider استفاده شود')
  return ctx
}
