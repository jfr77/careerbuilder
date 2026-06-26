-- =============================================================================
-- carreerbuilder — schema + seed data for Supabase Postgres
-- Paste this whole file into the Supabase SQL editor and run it ONCE.
-- (Safe to re-run: tables use IF NOT EXISTS, seeds use ON CONFLICT DO NOTHING.)
-- =============================================================================

-- ---------------------------------------------------------------- saved_filters (global)
CREATE TABLE IF NOT EXISTS saved_filters (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    filter_json JSONB NOT NULL DEFAULT '{}',
    owner_id    UUID,  -- Supabase auth.users.id; NULL = legacy/unclaimed
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_saved_filters_owner ON saved_filters (owner_id);

-- ---------------------------------------------------------------- templates (Studio library)
-- Placeholder syntax {{company}} {{role}} {{hiring_manager}} {{source}} {{my_name}}
-- is resolved at draft time from the linked pipeline card + active profile.
CREATE TABLE IF NOT EXISTS templates (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL CHECK (type IN ('cover_letter', 'cv_section', 'outreach')),
    language    TEXT NOT NULL DEFAULT 'en' CHECK (language IN ('de', 'en')),
    body        TEXT NOT NULL,
    is_builtin  BOOLEAN NOT NULL DEFAULT FALSE,
    owner_id    UUID,  -- NULL for built-ins (global) and legacy/unclaimed copies
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_templates_type ON templates (type);
CREATE INDEX IF NOT EXISTS idx_templates_owner ON templates (owner_id);

-- ---------------------------------------------------------------- profiles
CREATE TABLE IF NOT EXISTS profiles (
    id                 BIGSERIAL PRIMARY KEY,
    name               TEXT NOT NULL,
    location           TEXT,
    education          TEXT,
    experience_summary TEXT,
    skills             JSONB NOT NULL DEFAULT '[]',
    languages          JSONB NOT NULL DEFAULT '[]',
    role_expectations  TEXT,
    learning_goals     TEXT,
    target_industries  JSONB NOT NULL DEFAULT '[]',
    target_companies   JSONB NOT NULL DEFAULT '[]',
    availability       TEXT,
    cv_base            TEXT,
    owner_id           UUID,  -- Supabase auth.users.id; NULL = legacy/unclaimed
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_profiles_owner ON profiles (owner_id);

-- ---------------------------------------------------------------- jobs (shared pool)
-- Ingestion is unrestricted: every posting found on a watchlisted company page
-- is stored. Filtering is a query-time concern (GET /api/jobs params).
CREATE TABLE IF NOT EXISTS jobs (
    id           BIGSERIAL PRIMARY KEY,
    job_key      TEXT UNIQUE NOT NULL,
    source       TEXT NOT NULL CHECK (source IN ('join', 'personio', 'manual')),
    company      TEXT NOT NULL,
    company_slug TEXT,
    title        TEXT NOT NULL,
    location     TEXT,
    remote       BOOLEAN,
    employment   TEXT,
    department   TEXT,
    language     TEXT,            -- de|en, heuristic from title/description
    url          TEXT,
    description  TEXT,
    posted_date  DATE,            -- when the source exposes it (Personio createdAt)
    content_hash TEXT,            -- change detection: hash differs -> update row
    missed_runs  INTEGER NOT NULL DEFAULT 0,  -- consecutive runs without the posting; 2+ -> closed
    first_seen   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen    TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at    TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_url ON jobs (url);

-- ---------------------------------------------------------------- scrape_runs (log)
CREATE TABLE IF NOT EXISTS scrape_runs (
    id          BIGSERIAL PRIMARY KEY,
    source      TEXT NOT NULL,
    company     TEXT NOT NULL,
    found       INTEGER NOT NULL DEFAULT 0,
    new         INTEGER NOT NULL DEFAULT 0,
    errors      TEXT,
    duration_ms INTEGER,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_scrape_runs_company ON scrape_runs (source, company, started_at);

-- ---------------------------------------------------------------- job_scores (per profile x job)
CREATE TABLE IF NOT EXISTS job_scores (
    id            BIGSERIAL PRIMARY KEY,
    job_id        BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    profile_id    BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    fit_score     INTEGER CHECK (fit_score BETWEEN 1 AND 10),
    fit_note      TEXT,
    fit_breakdown JSONB,
    scored_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (job_id, profile_id)
);

-- ---------------------------------------------------------------- pipeline (per profile)
CREATE TABLE IF NOT EXISTS pipeline (
    id          BIGSERIAL PRIMARY KEY,
    profile_id  BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    job_id      BIGINT REFERENCES jobs(id) ON DELETE SET NULL,
    company     TEXT NOT NULL,
    role        TEXT NOT NULL,
    type        TEXT NOT NULL DEFAULT 'other'
                CHECK (type IN ('fa', 'analytics', 'consulting', 'vc', 'other')),
    stage       TEXT NOT NULL DEFAULT 'researching'
                CHECK (stage IN ('researching', 'applied', 'in_progress', 'offer', 'rejected')),
    link        TEXT,
    start_date  TEXT,
    end_date    TEXT,
    deadline    TEXT,
    reached_out BOOLEAN NOT NULL DEFAULT FALSE,
    notes       TEXT,
    documents   JSONB NOT NULL DEFAULT '{}',
    -- Excel-tracker parity (all nullable)
    salary_range         TEXT,
    source               TEXT,     -- where found: join|personio|linkedin|referral|other
    cv_version           TEXT,     -- which CV file/version was sent
    cover_letter_version TEXT,
    contact_name         TEXT,
    contact_email        TEXT,
    contact_role         TEXT,
    referral             BOOLEAN,
    referral_name        TEXT,
    follow_up_date       DATE,     -- <= today surfaces a "due" badge on the board
    response_date        DATE,
    interviews           JSONB,    -- [{round, type, date, notes}]
    excitement           INTEGER CHECK (excitement BETWEEN 1 AND 5),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- events (shared pool)
-- Designed for future event scrapers (Meetup/Eventbrite/university feeds):
-- a scraper only needs to INSERT rows here with source set accordingly.
CREATE TABLE IF NOT EXISTS events (
    id         BIGSERIAL PRIMARY KEY,
    title      TEXT NOT NULL,
    kind       TEXT NOT NULL CHECK (kind IN ('event', 'career_fair', 'certification', 'course')),
    provider   TEXT,
    location   TEXT,
    date       TEXT,
    url        TEXT,
    cost       TEXT,
    source     TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ('seed', 'llm', 'manual', 'scraper')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- event_saves (per profile)
CREATE TABLE IF NOT EXISTS event_saves (
    id             BIGSERIAL PRIMARY KEY,
    event_id       BIGINT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    profile_id     BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    saved          BOOLEAN NOT NULL DEFAULT TRUE,
    relevance_note TEXT,
    UNIQUE (event_id, profile_id)
);

-- ---------------------------------------------------------------- chat_messages (per profile)
CREATE TABLE IF NOT EXISTS chat_messages (
    id         BIGSERIAL PRIMARY KEY,
    profile_id BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    role       TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content    TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_jobs_open ON jobs (last_seen) WHERE closed_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_scores_profile ON job_scores (profile_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_profile ON pipeline (profile_id);
CREATE INDEX IF NOT EXISTS idx_chat_profile ON chat_messages (profile_id, created_at);

-- =============================================================================
-- SEED DATA
-- =============================================================================

-- Profile #1: Julian
-- owner_id is the local-dev pseudo-user (AUTH_DISABLED=1 → this UUID). In a
-- real Supabase deploy, reassign it to your auth.users.id after first sign-in
-- (see migrations/001_auth_ownership.sql).
INSERT INTO profiles (id, name, location, education, experience_summary, skills, languages,
                      role_expectations, learning_goals, target_industries, target_companies,
                      availability, cv_base, owner_id)
VALUES (
    1,
    'Julian',
    'Munich',
    'TU München — Informatics & Economics, final year',
    '4 years working student Data Analyst at parcelLab (VC-backed B2B SaaS): dbt, Redshift, SQL, Python, client-facing analytics for UK/US enterprise accounts.',
    '["SQL", "Python", "dbt", "Redshift", "Metabase", "data analytics", "stakeholder communication"]',
    '[{"language": "German", "level": "native"}, {"language": "English", "level": "fluent"}, {"language": "Russian", "level": "native"}, {"language": "Spanish", "level": "learning"}]',
    'Build operations from scratch, end-to-end ownership, high-intensity culture, direct stakeholder exposure, maximum learning density.',
    'Building operations from scratch, GTM execution, end-to-end ownership, venture capital exposure.',
    '["B2B SaaS", "Venture Capital", "Consulting", "Fintech"]',
    '["First Momentum Ventures", "Porsche Consulting", "FINN"]',
    'Oct 2026 preferred (Sep flexible), 6 months',
    E'Julian — Munich\n\nEDUCATION\n- TU München, B.Sc. Informatics & Economics (final year). Coursework: Entrepreneurship for Small Software-oriented Enterprises, Legal Basics for Startups.\n\nEXPERIENCE\n- Data Analyst (working student), parcelLab, Munich — 4 years. VC-backed B2B SaaS.\n  - Built and maintained dbt models on Amazon Redshift powering client-facing analytics.\n  - Ran SQL/Python analyses for UK/US enterprise accounts; presented findings directly to clients.\n  - Owned Metabase dashboards used by customer success and sales teams.\n  - Translated ambiguous stakeholder questions into reproducible data products.\n\nSKILLS\n- SQL, Python, dbt, Redshift, Metabase, data analytics, stakeholder communication.\n\nLANGUAGES\n- German (native), Russian (native), English (fluent), Spanish (learning).\n\nOTHER\n- Personal investment portfolio; active interest in venture capital and startup operations.',
    '00000000-0000-0000-0000-000000000000'
)
ON CONFLICT (id) DO NOTHING;
SELECT setval('profiles_id_seq', GREATEST((SELECT MAX(id) FROM profiles), 1));

-- Julian's pipeline: 12 applied entries (stage=applied, start Oct 2026 unless noted)
INSERT INTO pipeline (profile_id, company, role, type, stage, start_date, reached_out, notes)
SELECT * FROM (VALUES
    (1, 'Porsche Consulting', 'Strategy Intern',                  'consulting', 'applied', 'Oct 2026', FALSE, 'Top fit.'),
    (1, 'Siemens Advanta',    'Strategy & Innovation Intern',     'consulting', 'applied', 'Oct 2026', FALSE, NULL),
    (1, 'Analysys Mason',     'PE Transaction Consulting Intern', 'consulting', 'applied', 'Oct 2026', FALSE, NULL),
    (1, 'First Momentum',     'VC Investment Intern',             'vc',         'applied', 'Jan 2027', FALSE, 'Top fit.'),
    (1, 'CEPRES',             'PE Analyst Intern',                'vc',         'applied', 'Oct 2026', FALSE, NULL),
    (1, 'FINN',               'Strategic Finance & IR Intern',    'analytics',  'applied', 'Oct 2026', FALSE, NULL),
    (1, 'Entrix',             'Founder''s Associate Intern',      'fa',         'applied', 'Oct 2026', FALSE, NULL),
    (1, 'Pactos',             'Founder''s Associate Intern',      'fa',         'applied', 'Oct 2026', FALSE, NULL),
    (1, 'FUNDED',             'Founder''s Associate Intern',      'fa',         'applied', 'Oct 2026', FALSE, NULL),
    (1, 'CoCrafter',          'Growth/Founders Associate Intern', 'fa',         'applied', 'Oct 2026', FALSE, NULL),
    (1, 'Tranched',           'Chief of Staff Intern',            'fa',         'applied', 'Oct 2026', TRUE,  NULL),
    (1, 'Redpine',            'Business Development Intern',      'fa',         'applied', 'Oct 2026', FALSE, NULL)
) AS seed(profile_id, company, role, type, stage, start_date, reached_out, notes)
WHERE NOT EXISTS (SELECT 1 FROM pipeline);

-- Built-in studio templates ({{placeholder}} syntax; built-ins are read-only
-- in the app — duplicate to customize)
INSERT INTO templates (name, type, language, body, is_builtin)
SELECT * FROM (VALUES
('Anschreiben — klassisch (DE)', 'cover_letter', 'de',
E'{{my_name}}\nMünchen\n\n{{company}}\nz. Hd. {{hiring_manager}}\n\nBewerbung als {{role}}\n\nSehr geehrte/r {{hiring_manager}},\n\nmit großem Interesse habe ich Ihre Ausschreibung für die Position {{role}} bei {{company}} (gefunden über {{source}}) gelesen. Die Kombination aus [konkreter Aspekt der Rolle] und [Aspekt des Unternehmens] entspricht genau dem Umfeld, in dem ich arbeiten und lernen möchte.\n\nIn meiner bisherigen Tätigkeit habe ich [wichtigste relevante Erfahrung mit Ergebnis]. Dabei habe ich gelernt, [Fähigkeit, die zur Rolle passt]. Diese Erfahrung möchte ich bei {{company}} einbringen, um [konkreter Beitrag].\n\nÜber die Möglichkeit eines persönlichen Gesprächs freue ich mich sehr.\n\nMit freundlichen Grüßen\n{{my_name}}', TRUE),
('Cover letter — startup tone (EN)', 'cover_letter', 'en',
E'Hi {{hiring_manager}},\n\nI''m {{my_name}}, and I want to work on {{role}} at {{company}}.\n\nWhy me: [one sentence on the single most relevant thing you''ve done, with a number]. [One sentence on a second proof point]. I work fast, take ownership, and don''t need hand-holding.\n\nWhy {{company}}: [one specific, honest reason — product, market, team].\n\nI''d love to show you what I could contribute in a quick call.\n\nBest,\n{{my_name}}', TRUE),
('Founder''s Associate outreach (EN)', 'outreach', 'en',
E'Subject: {{role}} @ {{company}} — quick intro\n\nHi {{hiring_manager}},\n\nI''m {{my_name}} — I saw the {{role}} opening via {{source}} and didn''t want to just disappear into the applicant pile.\n\nIn short: [strongest 1-line proof of generalist execution, with a number]. I''m looking for exactly the kind of end-to-end ownership a founder''s associate role offers, and [specific reason {{company}} stands out].\n\nWould you be open to a 15-minute call this week?\n\n{{my_name}}', TRUE),
('CV Profil / Kurzprofil (DE)', 'cv_section', 'de',
E'PROFIL\n{{my_name}} — [Studiengang/Abschluss], [Stadt]. [Anzahl] Jahre Erfahrung in [Bereich] mit Schwerpunkt [Schwerpunkt]. Nachweisbare Erfolge: [Erfolg mit Zahl]. Sucht {{role}} bei {{company}}, um [Lernziel/Beitrag].', TRUE),
('CV profile / summary (EN)', 'cv_section', 'en',
E'PROFILE\n{{my_name}} — [degree/university], [city]. [N] years of experience in [area], focused on [focus]. Proven impact: [achievement with a number]. Now looking to bring [key strength] to the {{role}} role at {{company}}.', TRUE)
) AS seed(name, type, language, body, is_builtin)
WHERE NOT EXISTS (SELECT 1 FROM templates WHERE is_builtin);

-- Events & certifications: realistic Munich/DACH seed set
INSERT INTO events (title, kind, provider, location, date, url, cost, source)
SELECT * FROM (VALUES
    ('Bits & Pretzels 2026',                          'event',         'Bits & Pretzels',     'Munich',         'Sep 2026',     'https://www.bitsandpretzels.com',                          'from ~€300',  'seed'),
    ('IKOM — TUM Career Fair',                        'career_fair',   'TU München',          'Munich (Garching)', 'Jun 2026',  'https://www.ikom.tum.de',                                  'free',        'seed'),
    ('TUM Entrepreneurship Day',                      'event',         'TUM / UnternehmerTUM','Munich',         'Jul 2026',     'https://www.unternehmertum.de',                            'free',        'seed'),
    ('START Munich — Startup Stammtisch',             'event',         'START Munich',        'Munich',         'monthly',      'https://www.startmunich.de',                               'free',        'seed'),
    ('Munich Startup Demo Night',                     'event',         'Munich Startup',      'Munich',         'quarterly',    'https://www.munich-startup.de',                            'free',        'seed'),
    ('AWS Certified Cloud Practitioner',              'certification', 'Amazon Web Services', 'online',         'self-paced',   'https://aws.amazon.com/certification/certified-cloud-practitioner/', '$100', 'seed'),
    ('Google Cloud Digital Leader',                   'certification', 'Google Cloud',        'online',         'self-paced',   'https://cloud.google.com/learn/certification/cloud-digital-leader',  '$99',  'seed'),
    ('CFA Investment Foundations',                    'certification', 'CFA Institute',       'online',         'self-paced',   'https://www.cfainstitute.org/insights/professional-learning/certificate-programs', '~$350', 'seed'),
    ('dbt Analytics Engineering Certification',       'certification', 'dbt Labs',            'online',         'self-paced',   'https://www.getdbt.com/certifications',                    '$200',        'seed'),
    ('Manage&More Scholarship (UnternehmerTUM)',      'course',        'UnternehmerTUM',      'Munich',         'apply by semester', 'https://www.unternehmertum.de/en/programs/manage-more', 'free',        'seed'),
    ('Slush 2026',                                    'event',         'Slush',               'Helsinki',       'Nov 2026',     'https://www.slush.org',                                    'from ~€200',  'seed')
) AS seed(title, kind, provider, location, date, url, cost, source)
WHERE NOT EXISTS (SELECT 1 FROM events);
