// Auth gate: a session hook + a login/sign-up screen, shown only when Supabase
// auth is enabled. When it's disabled (local dev, no VITE_SUPABASE_* env) the
// gate is transparent and the app renders straight through.
import { useEffect, useState } from 'react'
import { authEnabled, supabase } from './supabase.js'
import { Btn, inputCls } from './ui.jsx'

// Returns { status, session }: status is 'loading' | 'in' | 'out'.
// When auth is disabled we report 'in' immediately with a null session.
export function useSession() {
  const [state, setState] = useState(
    authEnabled ? { status: 'loading', session: null } : { status: 'in', session: null }
  )

  useEffect(() => {
    if (!authEnabled) return
    supabase.auth.getSession().then(({ data }) => {
      setState({ status: data.session ? 'in' : 'out', session: data.session })
    })
    const { data: sub } = supabase.auth.onAuthStateChange((_event, session) => {
      setState({ status: session ? 'in' : 'out', session })
    })
    return () => sub.subscription.unsubscribe()
  }, [])

  return state
}

export function signOut() {
  if (authEnabled) supabase.auth.signOut()
}

export function Login() {
  const [mode, setMode] = useState('login') // 'login' | 'signup'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError(null); setNotice(null)
    try {
      if (mode === 'signup') {
        const { error } = await supabase.auth.signUp({ email, password })
        if (error) throw error
        setNotice('Account created. If email confirmation is on, check your inbox, then sign in.')
        setMode('login')
      } else {
        const { error } = await supabase.auth.signInWithPassword({ email, password })
        if (error) throw error
        // onAuthStateChange flips the gate to the app.
      }
    } catch (err) {
      setError(err.message || 'Authentication failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid min-h-screen place-items-center bg-ink px-4">
      <div className="w-full max-w-sm rounded-2xl border border-white/10 bg-ink-2 p-7 shadow-2xl">
        <div className="mb-6 flex items-center gap-2.5">
          <span className="display grid h-8 w-8 place-items-center rounded-lg bg-accent text-base font-bold text-white">c</span>
          <span className="display text-[17px] font-semibold tracking-tight text-white">carreerbuilder</span>
        </div>
        <h1 className="mb-1 text-lg font-semibold text-white">
          {mode === 'login' ? 'Sign in' : 'Create account'}
        </h1>
        <p className="mb-5 text-sm text-neutral-400">
          {mode === 'login' ? 'Welcome back.' : 'Start your own pipeline.'}
        </p>
        <form onSubmit={submit} className="space-y-3">
          <input className={inputCls} type="email" required placeholder="Email"
            value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
          <input className={inputCls} type="password" required placeholder="Password"
            value={password} onChange={(e) => setPassword(e.target.value)}
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'} />
          {error && <p className="text-xs text-red-400">{error}</p>}
          {notice && <p className="text-xs text-emerald-400">{notice}</p>}
          <Btn type="submit" variant="primary" className="w-full justify-center" disabled={busy}>
            {busy ? '…' : mode === 'login' ? 'Sign in' : 'Sign up'}
          </Btn>
        </form>
        <button
          className="mt-4 w-full text-center text-xs text-neutral-400 hover:text-neutral-200"
          onClick={() => { setMode(mode === 'login' ? 'signup' : 'login'); setError(null); setNotice(null) }}>
          {mode === 'login' ? "No account? Sign up" : 'Have an account? Sign in'}
        </button>
      </div>
    </div>
  )
}
