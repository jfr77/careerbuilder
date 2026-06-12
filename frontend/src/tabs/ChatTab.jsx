import { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import { Badge, Btn, PageHead, Spinner, useToast } from '../ui.jsx'

const SUGGESTIONS = [
  'Which of my open applications should I prioritize?',
  'Move Pactos to in progress',
  'What gaps does my profile have for VC roles?',
]

export default function ChatTab({ profile }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [lastActions, setLastActions] = useState([])
  const toast = useToast()
  const bottomRef = useRef(null)

  useEffect(() => {
    setMessages([]); setLastActions([])
    api.get(`/api/chat?profile_id=${profile.id}`).then(setMessages).catch((e) => toast(e.message))
  }, [profile.id])

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, sending])

  const send = async (text) => {
    const msg = (text ?? input).trim()
    if (!msg || sending) return
    setInput('')
    setSending(true)
    setMessages((m) => [...m, { id: `tmp-${Date.now()}`, role: 'user', content: msg }])
    try {
      const res = await api.post(`/api/chat?profile_id=${profile.id}`, { message: msg })
      setMessages((m) => [...m, { id: `a-${Date.now()}`, role: 'assistant', content: res.reply }])
      setLastActions(res.actions || [])
    } catch (e) {
      toast(e.message)
    } finally {
      setSending(false)
    }
  }

  const clear = async () => {
    try {
      await api.del(`/api/chat?profile_id=${profile.id}`)
      setMessages([]); setLastActions([])
    } catch (e) { toast(e.message) }
  }

  return (
    <div className="mx-auto flex h-[calc(100vh-120px)] max-w-3xl flex-col">
      <PageHead title="Chat"
        sub={`Knows ${profile.name}'s profile, pipeline and matches — and can update them.`}>
        {messages.length > 0 && <Btn variant="ghost" onClick={clear}>Clear history</Btn>}
      </PageHead>

      <div className="card flex-1 space-y-3 overflow-y-auto p-5">
        {messages.length === 0 && !sending && (
          <div className="grid h-full place-items-center">
            <div className="text-center">
              <p className="display mb-4 text-lg text-neutral-300">What's on your mind?</p>
              <div className="flex flex-col items-center gap-2">
                {SUGGESTIONS.map((s) => (
                  <button key={s} onClick={() => send(s)}
                    className="rounded-full border border-line bg-white px-4 py-2 text-sm text-neutral-600 transition-colors hover:border-accent hover:text-accent-deep">
                    {s}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
              m.role === 'user' ? 'rounded-br-md bg-ink text-white' : 'rounded-bl-md bg-paper text-ink'}`}>
              {m.content}
            </div>
          </div>
        ))}
        {sending && <Spinner label="thinking…" />}
        {lastActions.length > 0 && (
          <div className="flex flex-wrap gap-1.5 pt-1">
            {lastActions.map((a, i) => (
              <Badge key={i} tone={String(a.result).startsWith('error') ? 'red' : 'accent'}>
                ⚙ {a.tool}: {a.result}
              </Badge>
            ))}
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="mt-3 flex gap-2">
        <textarea
          className="flex-1 resize-none rounded-2xl border border-line bg-white px-4 py-3 text-sm focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20"
          rows={2}
          placeholder={`Message as ${profile.name}…`}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
        />
        <Btn variant="primary" onClick={() => send()} disabled={sending || !input.trim()}>Send</Btn>
      </div>
    </div>
  )
}
