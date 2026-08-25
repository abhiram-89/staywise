'use client'

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { ApiError, fetchMe, login as loginApi, setHotelId } from '@/lib/api'
import type { User } from '@/lib/types'

type AuthContextValue = {
  token: string | null
  user: User | null
  ready: boolean
  signIn: (email: string, password: string) => Promise<void>
  signOut: () => void
  updateName: (name: string) => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

const GUEST_PATHS = ['/login', '/signup']

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const [token, setToken] = useState<string | null>(null)
  const [user, setUser] = useState<User | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const stored = localStorage.getItem('hbf_token')
    const rawUser = localStorage.getItem('hbf_user')
    if (!stored) {
      setReady(true)
      return
    }
    setToken(stored)
    if (rawUser) {
      try {
        setUser(JSON.parse(rawUser))
      } catch {
        localStorage.removeItem('hbf_user')
      }
    }
    fetchMe()
      .then((data) => {
        const next = { email: data.email, name: data.name }
        setUser(next)
        localStorage.setItem('hbf_user', JSON.stringify(next))
        if (data.hotel_id) setHotelId(data.hotel_id)
      })
      .catch((err: ApiError) => {
        if (err.status === 401 || err.status === 403) {
          localStorage.removeItem('hbf_token')
          localStorage.removeItem('hbf_user')
          setToken(null)
          setUser(null)
        }
      })
      .finally(() => setReady(true))
  }, [])

  const signOut = useCallback(() => {
    localStorage.removeItem('hbf_token')
    localStorage.removeItem('hbf_user')
    localStorage.removeItem('hbf_hotel_id')
    setToken(null)
    setUser(null)
    router.replace('/login')
  }, [router])

  const signIn = useCallback(async (email: string, password: string) => {
    const data = await loginApi(email, password)
    const next = { email: data.email, name: data.name }
    localStorage.setItem('hbf_token', data.access_token)
    localStorage.setItem('hbf_user', JSON.stringify(next))
    setUser(next)
    setToken(data.access_token)
  }, [])

  const updateName = useCallback((name: string) => {
    setUser((current) => {
      if (!current) return current
      const next = { ...current, name }
      localStorage.setItem('hbf_user', JSON.stringify(next))
      return next
    })
  }, [])

  useEffect(() => {
    if (!ready) return
    const guest = GUEST_PATHS.includes(pathname)
    if (!token && !guest) router.replace('/login')
    if (token && guest) router.replace('/')
  }, [ready, token, pathname, router])

  const value = useMemo(
    () => ({ token, user, ready, signIn, signOut, updateName }),
    [token, user, ready, signIn, signOut, updateName],
  )

  if (!ready) {
    return (
      <div className="boot-screen">
        <div className="brand-mark"><span>SW</span></div>
        <p>Loading staywise…</p>
      </div>
    )
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
