-- Migration 002: Row Level Security (Supabase only).
--
-- WHY THIS MATTERS: Supabase auto-exposes every public table over PostgREST
-- using the *anon* key — and that key ships publicly in the frontend bundle.
-- Without RLS, anyone with the anon key could read/write the whole database
-- directly, bypassing the FastAPI backend entirely. Enabling RLS closes that
-- hole: the anon/authenticated roles become subject to these policies, while
-- the backend keeps working untouched because its connection role (`postgres`)
-- has BYPASSRLS.
--
-- Uses auth.uid() (the logged-in user's UUID from the JWT), which only exists
-- on Supabase — so this lives here, NOT in schema.sql (which also loads into a
-- plain local Postgres for tests). Run once on Supabase, after schema.sql.
-- Idempotent: re-running drops and recreates each policy.

-- ── User-owned tables: a row is visible/writable only by its owner ──────────
alter table profiles      enable row level security;
alter table saved_filters enable row level security;
alter table templates     enable row level security;

drop policy if exists own_profiles on profiles;
create policy own_profiles on profiles
  for all to authenticated
  using (owner_id = auth.uid()) with check (owner_id = auth.uid());

drop policy if exists own_saved_filters on saved_filters;
create policy own_saved_filters on saved_filters
  for all to authenticated
  using (owner_id = auth.uid()) with check (owner_id = auth.uid());

-- Templates: built-ins are readable by everyone; private copies only by owner.
drop policy if exists read_templates on templates;
create policy read_templates on templates
  for select to authenticated
  using (is_builtin or owner_id = auth.uid());

drop policy if exists write_templates on templates;
create policy write_templates on templates
  for all to authenticated
  using (owner_id = auth.uid()) with check (owner_id = auth.uid());

-- ── Child tables: ownership inherited through the parent profile ────────────
alter table job_scores    enable row level security;
alter table pipeline      enable row level security;
alter table chat_messages enable row level security;
alter table event_saves   enable row level security;

drop policy if exists own_job_scores on job_scores;
create policy own_job_scores on job_scores for all to authenticated
  using     (exists (select 1 from profiles p where p.id = job_scores.profile_id    and p.owner_id = auth.uid()))
  with check(exists (select 1 from profiles p where p.id = job_scores.profile_id    and p.owner_id = auth.uid()));

drop policy if exists own_pipeline on pipeline;
create policy own_pipeline on pipeline for all to authenticated
  using     (exists (select 1 from profiles p where p.id = pipeline.profile_id      and p.owner_id = auth.uid()))
  with check(exists (select 1 from profiles p where p.id = pipeline.profile_id      and p.owner_id = auth.uid()));

drop policy if exists own_chat_messages on chat_messages;
create policy own_chat_messages on chat_messages for all to authenticated
  using     (exists (select 1 from profiles p where p.id = chat_messages.profile_id and p.owner_id = auth.uid()))
  with check(exists (select 1 from profiles p where p.id = chat_messages.profile_id and p.owner_id = auth.uid()));

drop policy if exists own_event_saves on event_saves;
create policy own_event_saves on event_saves for all to authenticated
  using     (exists (select 1 from profiles p where p.id = event_saves.profile_id   and p.owner_id = auth.uid()))
  with check(exists (select 1 from profiles p where p.id = event_saves.profile_id   and p.owner_id = auth.uid()));

-- ── Shared pool: read-only to any logged-in user; only the backend writes ───
alter table jobs   enable row level security;
alter table events enable row level security;

drop policy if exists read_jobs on jobs;
create policy read_jobs on jobs for select to authenticated using (true);

drop policy if exists read_events on events;
create policy read_events on events for select to authenticated using (true);

-- ── Backend-only table: RLS on, no policy → denied to anon/authenticated ────
alter table scrape_runs enable row level security;

-- Note: the FastAPI backend (postgres role, BYPASSRLS) is unaffected by all of
-- the above and remains the only writer to jobs/events/scrape_runs.
