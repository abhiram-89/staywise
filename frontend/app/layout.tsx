import { Analytics } from '@vercel/analytics/next'
import { DM_Mono, DM_Sans } from 'next/font/google'
import type { Metadata, Viewport } from 'next'
import { Providers } from './providers'
import './globals.css'

const dmSans = DM_Sans({ subsets: ['latin'], variable: '--font-dm-sans' })
const dmMono = DM_Mono({ subsets: ['latin'], weight: ['400', '500'], variable: '--font-dm-mono' })

export const metadata: Metadata = {
  title: 'staywise — Hotel budget forecasting',
  description: 'A connected intelligence workspace for hotel revenue forecasting and operations.',
}

export const viewport: Viewport = {
  colorScheme: 'light dark',
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: 'white' },
    { media: '(prefers-color-scheme: dark)', color: 'black' },
  ],
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" className="bg-[#f6f7f5]">
      <body className={`${dmSans.variable} ${dmMono.variable} antialiased`}>
        <Providers>{children}</Providers>
        {process.env.NODE_ENV === 'production' && <Analytics />}
      </body>
    </html>
  )
}
