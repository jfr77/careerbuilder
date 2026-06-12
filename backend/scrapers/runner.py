"""Orchestrates scraper runs and owns the shared Postgres storage layer.

Preserved behavior from the original scripts:
- dedup by job_key (unique column; existing rows only get last_seen refreshed)
- closed-posting detection: a job that vanished from its company's page gets
  closed_at set — but only if that company's fetch returned anything at all,
  so a failed fetch never mass-closes postings
- polite 1 req/sec delay between requests

Relevance is NOT hardcoded: it follows the user-defined constraints in
data/scrape_settings.json (see settings.py) — empty by default, i.e. no
restrictions.
"""

import threading
import time
from datetime import datetime, timezone

from sqlalchemy import select

from ..db import SessionLocal
from ..models import Job
from . import join_source, personio_source, watchlist
from . import settings as scrape_settings

REQUEST_DELAY_SECONDS = 1.0

SOURCES = {
    "join": join_source,
    "personio": personio_source,
}


def is_relevant(title: str, cfg: dict | None = None) -> bool:
    """Relevance against the USER-defined constraints (data/scrape_settings.json).
    Empty include list = everything is relevant; excludes always win."""
    cfg = cfg or scrape_settings.load()
    t = title.lower()
    if any(kw in t for kw in cfg["exclude_keywords"]):
        return False
    if not cfg["include_keywords"]:
        return True
    return any(kw in t for kw in cfg["include_keywords"])


def ingest(db, source: str, company_slug: str, scraped: list[dict], now=None):
    """Write one company's scrape results to Postgres.

    Returns (new_count, seen_keys). Closed detection happens here: open rows
    for this source+company whose job_key wasn't seen get closed_at set.
    """
    now = now or datetime.now(timezone.utc)
    cfg = scrape_settings.load()
    seen_keys = set()
    new_count = 0

    for j in scraped:
        seen_keys.add(j["job_key"])
        existing = db.scalar(select(Job).where(Job.job_key == j["job_key"]))
        if existing:
            existing.last_seen = now
            existing.closed_at = None  # reappeared postings reopen
        else:
            db.add(Job(
                job_key=j["job_key"],
                source=source,
                company=j["company"],
                title=j["title"],
                location=j.get("location"),
                employment=j.get("employment"),
                department=j.get("department"),
                url=j.get("url"),
                description=j.get("description"),
                relevant=is_relevant(j["title"], cfg),
                first_seen=now,
                last_seen=now,
            ))
            new_count += 1

    # mark postings that vanished from this company's page as closed —
    # skip entirely if the fetch came back empty (may have failed)
    if seen_keys:
        open_rows = db.scalars(
            select(Job).where(
                Job.source == source,
                Job.company == company_slug,
                Job.closed_at.is_(None),
            )
        ).all()
        for row in open_rows:
            if row.job_key not in seen_keys:
                row.closed_at = now

    db.commit()
    return new_count, seen_keys


# ---------------------------------------------------------------- run state
# One scrape run at a time; the UI polls get_state() for progress.

_lock = threading.Lock()
_state = {"running": False, "log": [], "new_jobs": 0, "companies_done": 0,
          "companies_total": 0, "finished_at": None, "error": None}


def get_state():
    with _lock:
        return dict(_state, log=list(_state["log"]))


def _log(msg):
    with _lock:
        _state["log"].append(msg)


def _run():
    db = SessionLocal()
    try:
        plan = [(src, slug) for src in SOURCES for slug in watchlist.load(src)]
        with _lock:
            _state["companies_total"] = len(plan)

        for source, slug in plan:
            module = SOURCES[source]
            session = module.make_session()
            _log(f"[{source}] scraping {slug} …")
            jobs = module.scrape_company(slug, session)
            new_count, seen = ingest(db, source, slug, jobs)
            _log(f"[{source}] {slug}: {len(seen)} open, {new_count} new")
            with _lock:
                _state["new_jobs"] += new_count
                _state["companies_done"] += 1
            time.sleep(REQUEST_DELAY_SECONDS)

        _log("done")
    except Exception as e:
        with _lock:
            _state["error"] = str(e)
        _log(f"error: {e}")
    finally:
        db.close()
        with _lock:
            _state["running"] = False
            _state["finished_at"] = datetime.now(timezone.utc).isoformat()


def start_run() -> bool:
    """Kick off a background scrape of every watchlisted company across both
    sources. Returns False if a run is already in progress."""
    with _lock:
        if _state["running"]:
            return False
        _state.update(running=True, log=[], new_jobs=0, companies_done=0,
                      companies_total=0, finished_at=None, error=None)
    threading.Thread(target=_run, daemon=True).start()
    return True
