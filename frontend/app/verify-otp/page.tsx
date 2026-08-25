'use client'

import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { AuthScreen } from '@/components/auth-screen'
import { resendOtp, verifyOtp } from '@/lib/api'

export default function VerifyOtpPage() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [digits, setDigits] = useState(['', '', '', '', '', ''])
  const [seconds, setSeconds] = useState(45)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [devOtp, setDevOtp] = useState('')
  const inputs = useRef<Array<HTMLInputElement | null>>([])

  useEffect(() => {
    const pending = sessionStorage.getItem('hbf_pending_email') || ''
    if (!pending) {
      router.replace('/signup')
      return
    }
    setEmail(pending)
    setDevOtp(sessionStorage.getItem('hbf_dev_otp') || '')
  }, [router])

  useEffect(() => {
    if (seconds <= 0) return undefined
    const id = setTimeout(() => setSeconds((s) => s - 1), 1000)
    return () => clearTimeout(id)
  }, [seconds])

  const setDigit = (index: number, value: string) => {
    const char = value.replace(/\D/g, '').slice(-1)
    const next = [...digits]
    next[index] = char
    setDigits(next)
    if (char && index < 5) inputs.current[index + 1]?.focus()
  }

  const onKeyDown = (index: number, event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Backspace' && !digits[index] && index > 0) inputs.current[index - 1]?.focus()
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const otp = digits.join('')
    if (otp.length !== 6) {
      setError('Enter the 6-digit code sent to your email.')
      return
    }
    setError('')
    setLoading(true)
    try {
      await verifyOtp(email, otp)
      sessionStorage.removeItem('hbf_dev_otp')
      sessionStorage.setItem('hbf_verified_email', email)
      router.replace('/login')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not verify this code.')
    } finally {
      setLoading(false)
    }
  }

  const handleResend = async () => {
    if (seconds > 0) return
    try {
      const data = await resendOtp(email)
      if (data.dev_otp) {
        sessionStorage.setItem('hbf_dev_otp', data.dev_otp)
        setDevOtp(data.dev_otp)
      } else {
        sessionStorage.removeItem('hbf_dev_otp')
        setDevOtp('')
      }
      setSeconds(data.resend_after || 45)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not resend the OTP.')
    }
  }

  const mm = String(Math.floor(seconds / 60)).padStart(2, '0')
  const ss = String(seconds % 60).padStart(2, '0')

  return (
    <AuthScreen title="Verify your email" subtitle={`We sent a 6-digit verification code to ${email || 'your email'}.`}>
      <form onSubmit={submit} className="auth-form">
        {error && <p className="form-error">{error}</p>}
        {devOtp && <p className="form-info">Email delivery is not configured, so the verification code is shown here: <strong>{devOtp}</strong></p>}
        <div className="otp-row" onPaste={(event) => {
          const text = event.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6)
          if (!text) return
          event.preventDefault()
          const next = text.split('')
          while (next.length < 6) next.push('')
          setDigits(next)
          inputs.current[Math.min(text.length, 5)]?.focus()
        }}>
          {digits.map((digit, index) => (
            <input
              key={index}
              value={digit}
              onChange={(e) => setDigit(index, e.target.value)}
              onKeyDown={(e) => onKeyDown(index, e)}
              ref={(el) => { inputs.current[index] = el }}
              maxLength={1}
              inputMode="numeric"
              className="otp-input"
              aria-label={`Digit ${index + 1}`}
            />
          ))}
        </div>
        <button className="button-primary auth-submit" disabled={loading}>{loading ? 'Verifying…' : 'Verify OTP'}</button>
        <p className="auth-switch">
          Didn’t receive the code?{' '}
          {seconds > 0 ? <span>Resend OTP ({mm}:{ss})</span> : <button type="button" className="text-link" onClick={() => void handleResend()}>Resend OTP</button>}
        </p>
      </form>
    </AuthScreen>
  )
}
