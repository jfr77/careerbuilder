-- Migration 001: per-user ownership (Supabase Auth).
--
-- Adds a nullable owner_id to every table that holds user-private data so the
-- backend can scope it to the authenticated Supabase user (auth.users.id, a
-- UUID carried in the JWT `sub` claim). Additive and reversible — existing rows
-- get owner_id = NULL ("unclaimed") until backfilled (see the comment at the
-- bottom). Shared/global tables (jobs, events, scrape_runs) are intentionally
-- left untouched: scraped postings are public data shared across all accounts.
--
-- Ownership of profile-derived data (job_scores, pipeline, chat_messages,
-- event_saves) is inherited through profiles.owner_id via their profile_id FK,
-- so only the three top-level private tables need a column.
--
-- Run once against each database (local + Supabase). Safe to re-run.

ALTER TABLE profiles      ADD COLUMN IF NOT EXISTS owner_id UUID;
ALTER TABLE saved_filters ADD COLUMN IF NOT EXISTS owner_id UUID;
ALTER TABLE templates     ADD COLUMN IF NOT EXISTS owner_id UUID;

CREATE INDEX IF NOT EXISTS idx_profiles_owner      ON profiles      (owner_id);
CREATE INDEX IF NOT EXISTS idx_saved_filters_owner ON saved_filters (owner_id);
CREATE INDEX IF NOT EXISTS idx_templates_owner     ON templates     (owner_id);

-- Built-in templates stay global (owner_id NULL, is_builtin = TRUE): every user
-- sees and can duplicate them, but only their own duplicated copies are private.

-- ---------------------------------------------------------------------------
-- BACKFILL (run manually after the first user signs up, replacing the UUID):
--
--   UPDATE profiles      SET owner_id = '<your-auth-user-uuid>' WHERE owner_id IS NULL;
--   UPDATE saved_filters SET owner_id = '<your-auth-user-uuid>' WHERE owner_id IS NULL;
--   UPDATE templates     SET owner_id = '<your-auth-user-uuid>' WHERE owner_id IS NULL AND is_builtin = FALSE;
--
-- Find your UUID in the Supabase dashboard → Authentication → Users, or from
-- the JWT `sub` claim. Until backfilled, the existing seed data (Julian's
-- profile, saved filters, custom templates) is owned by nobody and hidden.
