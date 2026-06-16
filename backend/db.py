"""Database layer: one SQLAlchemy engine bound to DATABASE_URL (Supabase Postgres).

The frontend never talks to the database — every read/write goes through the
FastAPI routes in this package.
"""

import os
import sys

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    sys.exit(
        "\nERROR: DATABASE_URL is not set.\n"
        "Set it to your Supabase session-pooler connection string, e.g.\n"
        '  export DATABASE_URL="postgresql://postgres.<ref>:<password>@aws-0-eu-central-1.pooler.supabase.com:5432/postgres"\n'
        "See README.md for the full Supabase setup.\n"
    )

# Supabase hands out URLs starting with postgres:// in some places; SQLAlchemy
# needs the postgresql:// scheme.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=5)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

REQUIRED_TABLES = [
    "profiles", "jobs", "job_scores", "pipeline",
    "events", "event_saves", "chat_messages", "scrape_runs", "saved_filters",
    "templates",
]


def check_schema():
    """Startup check: verify all tables exist, otherwise point at schema.sql."""
    existing = set(inspect(engine).get_table_names())
    missing = [t for t in REQUIRED_TABLES if t not in existing]
    if missing:
        sys.exit(
            f"\nERROR: missing database tables: {', '.join(missing)}\n"
            "Open the Supabase SQL editor, paste the contents of schema.sql, and run it once.\n"
        )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
