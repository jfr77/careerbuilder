// Shared UI primitives for the carreerbuilder design language:
// ink primary actions, emerald accent used sparingly, paper canvas.
import { createContext, useCallback, useContext, useState } from 'react'

const ToastCtx = createContext(() => {})

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const push = useCallback((msg, kind = 'error') => {
    const id = Math.random().toString(36).slice(2)
    setToasts((t) => [...t, { id, msg, kind }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 6000)
  }, [])
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 flex max-w-md flex-col gap-2">
        {toasts.map((t) => (
          <div key={t.id}
            className={`rounded-xl px-4 py-3 text-sm shadow-lg border ${
              t.kind === 'error' ? 'border-red-200 bg-red-50 text-red-800'
              : 'border-line bg-ink text-white'}`}>
            {t.msg}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}

export const useToast = () => useContext(ToastCtx)

export function Btn({ children, variant = 'default', className = '', ...props }) {
  const styles = {
    default: 'bg-white border border-line hover:border-neutral-400 text-ink',
    primary: 'bg-ink text-white hover:bg-ink-2 border border-transparent',
    accent: 'bg-accent text-white hover:bg-accent-deep border border-transparent',
    danger: 'bg-white border border-red-200 text-red-700 hover:bg-red-50',
    ghost: 'border border-transparent text-neutral-500 hover:text-ink hover:bg-black/5',
  }
  return (
    <button {...props}
      className={`rounded-lg px-3.5 py-2 text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${styles[variant]} ${className}`}>
      {children}
    </button>
  )
}

export function Badge({ children, tone = 'neutral' }) {
  const tones = {
    neutral: 'bg-black/5 text-neutral-600',
    accent: 'bg-accent-soft text-accent-deep',
    green: 'bg-emerald-50 text-emerald-700',
    amber: 'bg-amber-50 text-amber-700',
    red: 'bg-red-50 text-red-700',
    violet: 'bg-violet-50 text-violet-700',
    sky: 'bg-sky-50 text-sky-700',
  }
  return <span className={`inline-block rounded-md px-1.5 py-0.5 text-[11px] font-semibold ${tones[tone]}`}>{children}</span>
}

export function Modal({ title, onClose, children, wide }) {
  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-ink/40 p-4 backdrop-blur-[2px]"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`mt-12 w-full ${wide ? 'max-w-3xl' : 'max-w-lg'} card p-6 shadow-2xl`}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">{title}</h2>
          <Btn variant="ghost" onClick={onClose}>✕</Btn>
        </div>
        {children}
      </div>
    </div>
  )
}

export function Field({ label, children, hint }) {
  return (
    <label className="block">
      <span className="microlabel mb-1.5 block">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-neutral-400">{hint}</span>}
    </label>
  )
}

export const inputCls =
  'w-full rounded-lg border border-line bg-white px-3 py-2 text-sm placeholder:text-neutral-400 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20'

export function Spinner({ label }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-neutral-500">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-accent" />
      {label}
    </span>
  )
}

/* Score ring: conic-gradient donut, the signature element of Discover */
export function FitRing({ score, size = 44 }) {
  if (score == null) {
    return (
      <div className="flex items-center justify-center rounded-full border border-dashed border-neutral-300 text-[10px] font-medium text-neutral-400"
        style={{ width: size, height: size }}>
        n/a
      </div>
    )
  }
  const pct = score * 10
  const color = score >= 8 ? 'var(--color-accent)' : score >= 6 ? '#d97706' : '#9ca3af'
  return (
    <div className="relative grid place-items-center rounded-full"
      style={{
        width: size, height: size,
        background: `conic-gradient(${color} ${pct}%, var(--color-line) ${pct}% 100%)`,
      }}>
      <div className="absolute grid place-items-center rounded-full bg-white"
        style={{ width: size - 10, height: size - 10 }}>
        <span className="text-[13px] font-bold" style={{ color }}>{score}</span>
      </div>
    </div>
  )
}

/* Page header used by every section */
export function PageHead({ title, sub, children }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="display text-2xl font-semibold tracking-tight">{title}</h1>
        {sub && <p className="mt-1 text-sm text-neutral-500">{sub}</p>}
      </div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </div>
  )
}

/* Editable keyword/tag list (scrape constraints, skills, …) */
export function TagEditor({ tags, onChange, placeholder, tone = 'neutral' }) {
  const [draft, setDraft] = useState('')
  const add = () => {
    const v = draft.trim().toLowerCase()
    if (v && !tags.includes(v)) onChange([...tags, v])
    setDraft('')
  }
  return (
    <div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-line bg-white p-2">
      {tags.map((t) => (
        <span key={t} className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium ${
          tone === 'red' ? 'bg-red-50 text-red-700' : 'bg-accent-soft text-accent-deep'}`}>
          {t}
          <button className="opacity-50 hover:opacity-100" onClick={() => onChange(tags.filter((x) => x !== t))}>✕</button>
        </span>
      ))}
      <input
        className="min-w-32 flex-1 bg-transparent px-1 py-0.5 text-sm focus:outline-none"
        value={draft} placeholder={placeholder}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); add() }
          if (e.key === 'Backspace' && !draft && tags.length) onChange(tags.slice(0, -1))
        }}
        onBlur={add}
      />
    </div>
  )
}

/* minimal inline icon set (stroke style, 20px grid) */
export function Icon({ name, className = 'h-5 w-5' }) {
  const paths = {
    chat: 'M4 5h12a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1H8l-4 3V6a1 1 0 0 1 1-1Z',
    discover: 'M9 3a6 6 0 1 0 3.9 10.6l3.7 3.7 1.4-1.4-3.7-3.7A6 6 0 0 0 9 3Zm0 2a4 4 0 1 1 0 8 4 4 0 0 1 0-8Z',
    pipeline: 'M3 4h4v12H3V4Zm5.5 0h4v8h-4V4ZM14 4h4v5h-4V4Z',
    studio: 'M10 2l1.8 4.5L16 8l-4.2 1.5L10 14l-1.8-4.5L4 8l4.2-1.5L10 2Zm6 9 .9 2.3 2.1.7-2.1.7-.9 2.3-.9-2.3-2.1-.7 2.1-.7.9-2.3Z',
    events: 'M5 3v2H3v12h14V5h-2V3h-2v2H7V3H5Zm10 6v4H5V9h10Z',
    profile: 'M10 3a4 4 0 1 1 0 8 4 4 0 0 1 0-8Zm0 9c3.9 0 7 1.8 7 4v1H3v-1c0-2.2 3.1-4 7-4Z',
  }
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" className={className} aria-hidden="true">
      <path d={paths[name] || ''} fillRule="evenodd" />
    </svg>
  )
}
