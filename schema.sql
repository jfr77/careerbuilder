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
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

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
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

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
INSERT INTO profiles (id, name, location, education, experience_summary, skills, languages,
                      role_expectations, learning_goals, target_industries, target_companies,
                      availability, cv_base)
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
    E'Julian — Munich\n\nEDUCATION\n- TU München, B.Sc. Informatics & Economics (final year). Coursework: Entrepreneurship for Small Software-oriented Enterprises, Legal Basics for Startups.\n\nEXPERIENCE\n- Data Analyst (working student), parcelLab, Munich — 4 years. VC-backed B2B SaaS.\n  - Built and maintained dbt models on Amazon Redshift powering client-facing analytics.\n  - Ran SQL/Python analyses for UK/US enterprise accounts; presented findings directly to clients.\n  - Owned Metabase dashboards used by customer success and sales teams.\n  - Translated ambiguous stakeholder questions into reproducible data products.\n\nSKILLS\n- SQL, Python, dbt, Redshift, Metabase, data analytics, stakeholder communication.\n\nLANGUAGES\n- German (native), Russian (native), English (fluent), Spanish (learning).\n\nOTHER\n- Personal investment portfolio; active interest in venture capital and startup operations.'
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
