'use client'

import { FormEvent, useState } from 'react'
import { Bot, X } from 'lucide-react'
import { sendChat } from '@/lib/api'

type ChatMessage = { role: 'user' | 'assistant'; text: string }

export function AppChatbot() {
  const [open, setOpen] = useState(false)
  const [tall, setTall] = useState(false)
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: 'assistant', text: 'I am MIRA. I can help with import, forecasts, rooms, and email verification. Ask a question.' },
  ])

  const toggle = () => {
    setOpen((current) => {
      if (!current) {
        setTall(false)
        return true
      }
      if (!tall) {
        setTall(true)
        return true
      }
      setTall(false)
      return false
    })
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const text = input.trim()
    if (!text || busy) return
    setInput('')
    setMessages((current) => [...current, { role: 'user', text }])
    setBusy(true)
    try {
      const data = await sendChat(text)
      setMessages((current) => [...current, { role: 'assistant', text: data.reply }])
    } catch (err) {
      setMessages((current) => [
        ...current,
        { role: 'assistant', text: err instanceof Error ? err.message : 'I could not answer that just now.' },
      ])
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={`chatbot ${open ? 'open' : ''} ${tall ? 'tall' : ''}`}>
      {open && (
        <section className="chatbot-panel" aria-label="MIRA assistant">
          <header className="chatbot-head">
            <div className="chatbot-title"><Bot size={16} /><strong>MIRA</strong></div>
            <button className="icon-button" onClick={() => { setOpen(false); setTall(false) }} aria-label="Close MIRA"><X size={16} /></button>
          </header>
          <div className="chatbot-log">
            {messages.map((item, index) => (
              <p key={`${item.role}-${index}`} className={`chat-bubble ${item.role}`}>{item.text}</p>
            ))}
            {busy && <p className="chat-bubble assistant">Thinking…</p>}
          </div>
          <form className="chatbot-form" onSubmit={submit}>
            <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask MIRA about this workspace" aria-label="Chat message" />
            <button className="button-primary" disabled={busy || !input.trim()}>Send</button>
          </form>
        </section>
      )}
      <button className="chatbot-fab" onClick={toggle} aria-label={open ? (tall ? 'Close MIRA' : 'Expand MIRA') : 'Open MIRA'} aria-expanded={open}>
        <Bot size={22} />
        <span>MIRA</span>
      </button>
    </div>
  )
}
