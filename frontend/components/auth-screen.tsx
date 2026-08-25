'use client'

import Link from 'next/link'
import { Hotel } from 'lucide-react'

export function AuthScreen({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle: string
  children: React.ReactNode
}) {
  return (
    <div className="auth-shell">
      <section className="auth-card">
        <Link href="/login" className="brand auth-brand">
          <div className="brand-mark"><Hotel size={19} /></div>
          <span>staywise</span>
        </Link>
        <h1>{title}</h1>
        <p className="subheading">{subtitle}</p>
        {children}
      </section>
    </div>
  )
}
