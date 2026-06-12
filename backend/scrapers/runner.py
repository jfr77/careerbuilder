"""Orchestrates scraper runs and owns the shared Postgres storage layer.

Ingestion is UNRESTRICTED: every posting found on a watchlisted company page
is stored — filtering happens at query time (GET /api/jobs). Storage rules:

- dedup by job_key (unique; URL-derived, so url stays unique too)
- change detection by content_hash: if a posting's content changed, the row is
  updated in place and last_seen bumped
- closed-posting detection: a job missing from 2+ consecutive successful runs
  of its company gets closed_at set; a failed fetch never counts as a miss
- politeness: randomized 1-2s delay between requests, identifiable user-agent,
  per-domain failure backoff (a flaky domain gets skipped for the rest of the
  run after repeated failures)
- every company fetch is logged to scrape_runs (found/new/errors/duration)
"""

import hashlib
import random
import re
import threading
import time
from datetime import datetime, timezone

from sqlalchemy import select

from ..db import SessionLocal
from ..models import Job, ScrapeRun
from . import join_source, personio_source, watchlist

MISSED_RUNS_BEFORE_CLOSE = 2
DOMAIN_FAILURES_BEFORE_SKIP = 3

SOURCES = {
    "join": join_source,
    "personio": personio_source,
}


def polite_delay():
    """Randomized 1-2s pause between requests."""
    time.sleep(random.uniform(1.0, 2.0))


# ---------------------------------------------------------------- enrichment

_DE_HINTS = re.compile(
    r"[äöüß]|\b(und|oder|der|die|das|für|mit|bei|wir|dich|du|dein|unser|"
    r"praktikum|praktikant\w*|werkstudent\w*|mitarbeiter\w*|aufgaben|kenntnisse)\b",
    re.IGNORECASE)
_EN_HINTS = re.compile(
    r"\b(the|and|you|your|our|we|with|for|will|team|join|skills|experience|"
    r"intern|internship|student|responsibilities|requirements)\b",
    re.IGNORECASE)


def detect_language(title: str, description: str | None = None) -> str | None:
    """Cheap de|en heuristic over title + (truncated) description."""
    text = f"{title} {(description or '')[:1500]}"
    de = len(_DE_HINTS.findall(text))
    en = len(_EN_HINTS.findall(text))
    if de == en:
        return None
    return "de" if de > en else "en"


def detect_remote(title: str, location: str | None) -> bool | None:
    """True if the posting clearly says remote; None means unknown."""
    if re.search(r"\bremote\b|\bhome\s*office\b", f"{title} {location or ''}", re.IGNORECASE):
        return True
    return None


CONTENT_FIELDS = ("title", "location", "employment", "department", "url", "description")


def content_hash(j: dict) -> str:
    payload = "|".join(str(j.get(f) or "") for f in CONTENT_FIELDS)
    return hashlib.sha256(payload.encode()).hexdigest()


# ---------------------------------------------------------------- storage

def ingest(db, source: str, company_slug: str, scraped: list[dict],
           now=None, fetch_ok: bool = True):
    """Write one company's scrape results to Postgres.

    Returns (new_count, seen_keys). Closed detection: open rows for this
    source+company_slug missing from MISSED_RUNS_BEFORE_CLOSE consecutive
    successful runs get closed_at set. fetch_ok=False (failed/partial fetch)
    skips miss-counting entirely so an outage never closes postings.
    """
    now = now or datetime.now(timezone.utc)
    seen_keys = set()
    new_count = 0

    for j in scraped:
        seen_keys.add(j["job_key"])
        h = content_hash(j)
        existing = db.scalar(select(Job).where(Job.job_key == j["job_key"]))
        if existing:
            existing.last_seen = now
            existing.missed_runs = 0
            existing.closed_at = None  # reappeared postings reopen
            if existing.content_hash != h:
                for f in CONTENT_FIELDS:
                    if f in j:
                        setattr(existing, f, j[f])
                existing.content_hash = h
                existing.language = detect_language(existing.title, existing.description)
                existing.remote = detect_remote(existing.title, existing.location)
                if j.get("posted_date"):
                    existing.posted_date = j["posted_date"]
        else:
            db.add(Job(
                job_key=j["job_key"],
                source=source,
                company=j["company"],
                company_slug=company_slug,
                title=j["title"],
                location=j.get("location"),
                remote=detect_remote(j["title"], j.get("location")),
                employment=j.get("employment"),
                department=j.get("department"),
                language=detect_language(j["title"], j.get("description")),
                url=j.get("url"),
                description=j.get("description"),
                posted_date=j.get("posted_date"),
                content_hash=h,
                missed_runs=0,
                first_seen=now,
                last_seen=now,
            ))
            new_count += 1

    if fetch_ok:
        open_rows = db.scalars(
            select(Job).where(
                Job.source == source,
                Job.company_slug == company_slug,
                Job.closed_at.is_(None),
            )
        ).all()
        for row in open_rows:
            if row.job_key not in seen_keys:
                row.missed_runs = (row.missed_runs or 0) + 1
                if row.missed_runs >= MISSED_RUNS_BEFORE_CLOSE:
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
    domain_failures: dict[str, int] = {}
    try:
        plan = [(src, slug) for src in SOURCES for slug in watchlist.load(src)]
        with _lock:
            _state["companies_total"] = len(plan)

        for source, slug in plan:
            module = SOURCES[source]
            domain = module.domain_for(slug)
            started = time.monotonic()

            if domain_failures.get(domain, 0) >= DOMAIN_FAILURES_BEFORE_SKIP:
                _log(f"[{source}] {slug}: skipped — {domain} failed "
                     f"{domain_failures[domain]} times this run")
                db.add(ScrapeRun(source=source, company=slug, found=0, new=0,
                                 errors=f"skipped: backoff on {domain}", duration_ms=0))
                db.commit()
                with _lock:
                    _state["companies_done"] += 1
                continue

            _log(f"[{source}] scraping {slug} …")
            session = module.make_session()
            jobs, error = module.scrape_company(slug, session)
            new_count, seen = ingest(db, source, slug, jobs, fetch_ok=error is None)
            duration_ms = int((time.monotonic() - started) * 1000)

            if error:
                domain_failures[domain] = domain_failures.get(domain, 0) + 1
                _log(f"[{source}] {slug}: ERROR {error} ({len(seen)} parsed before failure)")
            else:
                domain_failures.pop(domain, None)
                _log(f"[{source}] {slug}: {len(seen)} open, {new_count} new")

            db.add(ScrapeRun(source=source, company=slug, found=len(seen),
                             new=new_count, errors=error, duration_ms=duration_ms))
            db.commit()

            with _lock:
                _state["new_jobs"] += new_count
                _state["companies_done"] += 1
            polite_delay()

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
