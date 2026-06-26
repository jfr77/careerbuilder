// Supabase Auth client (login only — the browser still never touches the
// database; all data goes through the FastAPI backend).
//
// The URL + anon key are PUBLIC by design (the anon key is safe to ship in the
// bundle; row access is gated by the backend's JWT check, not by this key).
// They come from build-time env (frontend/.env or the Pages build):
//   VITE_SUPABASE_URL       https://<project-ref>.supabase.co
//   VITE_SUPABASE_ANON_KEY  the project's anon/public key
//
// When these are absent (pure local dev against a backend running with
// AUTH_DISABLED=1) auth is disabled and the login screen is skipped.
import { createClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

export const authEnabled = Boolean(url && anonKey)

export const supabase = authEnabled
  ? createClient(url, anonKey, {
      auth: { persistSession: true, autoRefreshToken: true },
    })
  : null
