'use client'

import { FormEvent, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Eye, EyeOff } from 'lucide-react'
import { AuthScreen } from '@/components/auth-screen'
import { signup } from '@/lib/api'

export default function SignupPage() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await signup(email.trim(), password, name.trim())
      router.push('/login')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create the account.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthScreen title="Create your account" subtitle="Sign up to import reports and run hotel budget forecasts.">
      <form onSubmit={submit} className="auth-form">
        {error && <p className="form-error">{error}</p>}
        <label className="control-label">Username
          <input type="text" required minLength={2} value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />
        </label>
        <label className="control-label">Email
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
        </label>
        <label className="control-label">Password
          <span className="password-field">
            <input type={show ? 'text' : 'password'} required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" />
            <button type="button" className="icon-button" onClick={() => setShow((v) => !v)} aria-label="Toggle password">
              {show ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </span>
        </label>
        <p className="field-hint">At least 8 characters.</p>
        <button className="button-primary auth-submit" disabled={loading}>{loading ? 'Creating account…' : 'Create account'}</button>
        <p className="auth-switch">Already have an account? <Link href="/login">Sign in</Link></p>
      </form>
    </AuthScreen>
  )
}
