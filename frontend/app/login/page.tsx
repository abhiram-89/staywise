'use client'

import { FormEvent, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Eye, EyeOff } from 'lucide-react'
import { AuthScreen } from '@/components/auth-screen'
import { useAuth } from '@/components/auth-provider'

export default function LoginPage() {
  const router = useRouter()
  const { signIn } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    setLoading(true)
    try {
      await signIn(email.trim(), password)
      sessionStorage.removeItem('hbf_pending_email')
      router.replace('/')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not sign in.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthScreen title="Welcome back" subtitle="Sign in to load your hotel workspace from CognoDB.">
      <form onSubmit={submit} className="auth-form">
        {error && <p className="form-error">{error}</p>}
        <label className="control-label">Email
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
        </label>
        <label className="control-label">Password
          <span className="password-field">
            <input type={show ? 'text' : 'password'} required value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
            <button type="button" className="icon-button" onClick={() => setShow((v) => !v)} aria-label="Toggle password">
              {show ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </span>
        </label>
        <button className="button-primary auth-submit" disabled={loading}>{loading ? 'Signing in…' : 'Sign in'}</button>
        <p className="auth-switch">Don’t have an account? <Link href="/signup">Create one</Link></p>
      </form>
    </AuthScreen>
  )
}
