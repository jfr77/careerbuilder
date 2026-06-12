# carreerbuilder

A local-first job discovery and application platform — a personal career
operating system. Multi-profile (Netflix-style switcher, no auth): every
profile gets its own pipeline, fit scores, chat history, documents and saved
events, while the scraped jobs pool is shared.

**Stack:** FastAPI + SQLAlchemy + Supabase Postgres · React + Vite + Tailwind ·
Anthropic API (`claude-sonnet-4-20250514`). All data and LLM calls go through
the backend — the browser never sees Supabase or API keys.

## Setup

### 1. Supabase
1. Create a free project at [supabase.com](https://supabase.com).
2. Open the **SQL editor**, paste the entire contents of [`schema.sql`](schema.sql), run it once.
   This creates all 8 tables and seeds profile #1 (Julian), 12 pipeline entries and ~10 events.
3. On the project page click **Connect** → copy the **Session pooler** connection string.

### 2. Backend
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # then edit:
#   PORT              = backend port (default 8787)
#   DATABASE_URL      = the session-pooler string (URL-encode special chars in the password)
#   ANTHROPIC_API_KEY = optional; enables chat, scoring, recommendations, documents
```
The backend checks on startup that all tables exist and points you back to
`schema.sql` if not.

### 3. Frontend
```bash
cd frontend && npm install
```

## Run

```bash
make dev          # starts backend (:8787 or $PORT) + frontend (:5173), Ctrl-C stops both
PORT=9001 make dev   # any port works — env var beats .env beats the 8787 default
```
or in two terminals:
```bash
.venv/bin/uvicorn backend.main:app --reload --port 8787          # backend
cd frontend && VITE_API_URL=http://localhost:8787 npm run dev    # frontend → http://localhost:5173
```
The frontend talks to the backend only through the Vite `/api` proxy, whose
target is the single `VITE_API_URL` setting (the Makefile passes it for you).

## Test

```bash
make test         # smoke-tests every endpoint against the running backend
```
Works with or without `ANTHROPIC_API_KEY` — without it, LLM endpoints must
return a clean 503 (that's asserted, not skipped).

## The 6 sections (ink sidebar)

| Section | What it does |
|---|---|
| **Chat** | Anthropic-backed copilot that knows the active profile, pipeline and top matches. Can change data via 4 tools: `update_profile`, `add_to_pipeline`, `update_pipeline_stage`, `search_jobs`. History persists per profile. |
| **Discover** | Open jobs joined with the active profile's scores, sorted by fit (score rings). Run scrapers from the UI (async with progress bar), lazy per-profile LLM scoring (1-10 + note + 4-dimension breakdown), per-job re-score, one-click add-to-pipeline. Ingestion is unrestricted — every posting from the watchlisted companies lands in the pool; filters above the list narrow it down. |
| **Pipeline** | Kanban: Researching → Applied → In Progress → Offer → Rejected, cards color-coded by role type. Cards carry type badge, dates, deadline, link, reached-out toggle, notes, attached documents. Paste-to-add extracts fields via LLM into an editable confirm form. Per-card jumps into Studio, prefilled. |
| **Studio** | The AI document workspace: cover letter writer (3 tones, editable, save + .txt export), CV tailor (reorders/rephrases `cv_base` only — never invents — with diff view), interview trainer (5 Q&As, 3 concepts, 2 questions to ask; savable per entry). Controls left, output canvas right. |
| **Events** | Shared pool of Munich/DACH events, fairs, certifications and courses; per-profile save/dismiss. "Get recommendations" asks the LLM for 5-8 tailored suggestions (clearly labeled as AI output to verify). |
| **Profile** | Edit every profile field (saving offers a re-score), create/delete profiles (cascade). Profile switching lives in the sidebar footer (Netflix-style avatars). |

## Scrapers

- `backend/scrapers/join_source.py` — join.com company pages with `?page=N`
  pagination. The parse logic is carried over unchanged from the original
  tested `join_scraper.py` (archived at `docs/join_scraper_original.py`).
- `backend/scrapers/personio_source.py` — Personio's public XML job feed
  (`https://<slug>.jobs.personio.de/xml`), with `/search.json` as fallback.
- `backend/scrapers/runner.py` — shared Postgres ingest: dedup by `job_key`,
  change detection by `content_hash` (changed postings update in place),
  closed-posting detection (missing from **2+ consecutive successful runs** →
  `closed_at`; failed fetches never count as a miss), randomized 1-2s delays,
  per-domain failure backoff, and a `scrape_runs` log row per company fetch
  (`GET /api/scrape/runs`).
- **Ingestion is unrestricted**: every posting on a watchlisted company page
  is stored, regardless of role type — narrowing down happens at query time
  with the Discover filters. Language (de/en) and remote are detected
  heuristically at ingest.
- Watchlists are **global** JSON files in `data/` (`watchlist_join.json`,
  `watchlist_personio.json`), editable from the UI.
- Parser tests run against saved fixtures (`tests/`), never live requests:
  `.venv/bin/python tests/test_scrapers.py`.

## Notes

- Without `ANTHROPIC_API_KEY` the app fully works except LLM features, which
  show a banner and return clear 503s — never a blank crash.
- Out of scope by design: auth, employer-side candidate ranking and HRIS/
  onboarding handoff (see [`docs/ROADMAP.md`](docs/ROADMAP.md)), payments,
  deployment, LinkedIn scraping (paste-to-add covers those postings).
