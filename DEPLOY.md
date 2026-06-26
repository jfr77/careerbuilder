# Deploying carreerbuilder

The app is two halves that deploy separately:

| Half | Hosts | Why |
|---|---|---|
| **Frontend** (React/Vite static build) | **GitHub Pages** | Pages serves static files only. |
| **Backend** (FastAPI + Postgres) | **Render** (or Railway/Fly) | Pages can't run Python; the API needs a server. |

Auth is **Supabase Auth**: users sign in on the frontend, the backend verifies
their JWT and scopes every profile's data to its owner. The browser still never
touches the database — only the backend does.

```
┌──────────────┐   Bearer JWT    ┌────────────────┐   DATABASE_URL   ┌──────────┐
│ GitHub Pages │ ──────────────► │  Render (API)  │ ───────────────► │ Supabase │
│  (frontend)  │ ◄────────────── │   FastAPI      │ ◄─────────────── │ Postgres │
└──────────────┘    JSON         └────────────────┘                  └──────────┘
        │  signInWithPassword / token                                    ▲
        └────────────────────────────────────────────────────────────────┘
                         Supabase Auth (login only)
```

---

## 1. Supabase

1. **Auth** → **Providers** → enable **Email**. For the simplest start, turn
   *off* "Confirm email" (Auth → Providers → Email) so sign-up logs you in
   immediately; turn it back on later for real multi-user.
2. Collect three values:
   - **Project URL** — `https://<project-ref>.supabase.co` (Project Settings → API)
   - **anon public key** — Project Settings → API → Project API keys → `anon`
   - **JWT Secret** — Project Settings → API → JWT Settings → **JWT Secret**
3. Make sure the schema is loaded: SQL editor → paste `schema.sql` → run. If the
   database already existed, also run `migrations/001_auth_ownership.sql` once
   (adds the `owner_id` columns).

## 2. Backend on Render

1. Push this repo to GitHub. In Render: **New +** → **Blueprint** → pick the
   repo. It reads [`render.yaml`](render.yaml) and creates `carreerbuilder-api`.
2. Set the prompted env vars:
   - `DATABASE_URL` — Supabase **session-pooler** string (URL-encode the password)
   - `SUPABASE_JWT_SECRET` — from step 1
   - `ANTHROPIC_API_KEY` — optional (enables chat/scoring/documents)
   - `CORS_ORIGINS` — your Pages origin, e.g. `https://<your-username>.github.io`
3. Deploy. Confirm `https://<service>.onrender.com/api/health` returns
   `{"ok": true, ...}`. Note the service URL for the next step.

## 3. Frontend on GitHub Pages

1. Repo **Settings → Pages → Source: GitHub Actions**.
2. Repo **Settings → Secrets and variables → Actions → Variables** → add:
   - `VITE_API_URL` — the Render URL from step 2
   - `VITE_SUPABASE_URL` — Supabase project URL
   - `VITE_SUPABASE_ANON_KEY` — anon public key
   - `VITE_BASE` — `/<repo-name>/` (e.g. `/carreerbuilder/`) for a project site;
     use `/` only if this is a `<user>.github.io` root repo
3. Push to `main` (or run the **Deploy frontend to GitHub Pages** workflow). It
   builds `frontend/dist` and publishes it. Your app is at
   `https://<your-username>.github.io/<repo-name>/`.

## 4. Claim the seed data (one-time)

The seeded "Julian" profile, its pipeline, and any pre-existing saved filters
have `owner_id = '00000000-…'` (the local-dev user) and are invisible to a real
account. After your first sign-in, find your UID in Supabase
(**Authentication → Users**) and run in the SQL editor:

```sql
update profiles      set owner_id = '<your-uid>' where owner_id = '00000000-0000-0000-0000-000000000000';
update saved_filters set owner_id = '<your-uid>' where owner_id is null;
update templates     set owner_id = '<your-uid>' where owner_id is null and is_builtin = false;
```

Skip this if you'd rather start with an empty pipeline — just create a new
profile in the app.

---

## Local development

No deploy needed. Two options:

- **Without auth** (simplest): run the backend with `AUTH_DISABLED=1` and leave
  `VITE_SUPABASE_*` unset. The login screen is skipped and you act as the fixed
  dev user that owns the seed data.
  ```bash
  AUTH_DISABLED=1 make dev
  ```
- **With auth** (mirrors prod): set `SUPABASE_JWT_SECRET` on the backend and
  `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` in `frontend/.env.local`.

Requires **Node 18+** for the Vite build/dev server.

## Notes & hardening

- **Render free tier sleeps** after inactivity; the first request after idle
  takes a few seconds to wake. Fine for personal use.
- The backend is the only database client, so ownership is enforced in app code
  (the `owner_id` checks). Enabling Supabase **Row Level Security** would add
  defense-in-depth but isn't required for this single-client setup.
- Never set `AUTH_DISABLED=1` on a deployed backend — it disables auth entirely.
