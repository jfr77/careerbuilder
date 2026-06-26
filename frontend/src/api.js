// Thin fetch wrapper. Every call goes to the FastAPI backend; the browser
// never talks to Supabase's database or the Anthropic API directly.
//
// Base URL: in local dev VITE_API_URL is empty, so paths stay relative and the
// Vite dev-server proxy forwards /api. In a split deploy (frontend on GitHub
// Pages) VITE_API_URL is the absolute backend origin and requests go there
// cross-origin (the backend allows the Pages origin via CORS_ORIGINS).
//
// Auth: when Supabase auth is enabled we attach the signed-in user's access
// token as a Bearer header. The token is kept in a module variable, refreshed
// by the onAuthStateChange subscription below, so requests stay synchronous.
import { authEnabled, supabase } from './supabase.js'

const API_BASE = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

let accessToken = null
if (authEnabled) {
  // Seed from any persisted session, then track changes (login/logout/refresh).
  supabase.auth.getSession().then(({ data }) => {
    accessToken = data.session?.access_token ?? null
  })
  supabase.auth.onAuthStateChange((_event, session) => {
    accessToken = session?.access_token ?? null
  })
}

async function request(method, path, body) {
  const opts = { method, headers: {} }
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }
  if (accessToken) opts.headers['Authorization'] = `Bearer ${accessToken}`

  const res = await fetch(API_BASE + path, opts)
  if (!res.ok) {
    // A 401 means the session lapsed — bounce to the login screen.
    if (res.status === 401 && authEnabled) {
      accessToken = null
      supabase.auth.signOut().catch(() => {})
    }
    let detail = `${res.status} ${res.statusText}`
    try {
      const data = await res.json()
      if (data.detail) detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
    } catch { /* non-JSON error body */ }
    const err = new Error(detail)
    err.status = res.status
    throw err
  }
  return res.json()
}

export const api = {
  get: (path) => request('GET', path),
  post: (path, body) => request('POST', path, body),
  patch: (path, body) => request('PATCH', path, body),
  del: (path) => request('DELETE', path),
}

export function downloadText(filename, content) {
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = filename
  a.click()
  URL.revokeObjectURL(a.href)
}
