#!/usr/bin/env python3
"""Scraper parser + ingest tests against saved fixtures — no live requests.

Run:  .venv/bin/python tests/test_scrapers.py
Same plain-assert style as test_api.py. The ingest tests run against an
in-memory SQLite database (the Job/ScrapeRun tables use no Postgres-only
types), so nothing here touches Supabase.
"""

import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# backend.db needs DATABASE_URL at import time; the engine is created lazily,
# so a placeholder is enough — these tests never connect to it.
os.environ.setdefault("DATABASE_URL", "postgresql://placeholder:placeholder@localhost:5432/placeholder")

from backend.models import Job  # noqa: E402
from backend.scrapers import join_source, personio_source, runner  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
PASS, FAIL = 0, 0


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


# ---------------------------------------------------------------- join parser

def test_join():
    html1 = (FIXTURES / "join_company_page1.html").read_text()
    html2 = (FIXTURES / "join_company_page2.html").read_text()

    jobs = join_source.parse_company_page(html1, "acme")
    check("join: 3 postings for acme (other company ignored)", len(jobs) == 3, jobs)
    by_key = {j["job_key"]: j for j in jobs}

    fa = by_key.get("1001001", {})
    check("join: title split", fa.get("title") == "Founders Associate Intern (m/w/d)", fa)
    check("join: location split", fa.get("location") == "Munich, Germany", fa)
    check("join: employment split", fa.get("employment") == "Internship", fa)
    check("join: department split", fa.get("department") == "Operations", fa)
    check("join: url built", fa.get("url") == "https://join.com/companies/acme/1001001-founders-associate-intern", fa)

    ws = by_key.get("1001002", {})
    check("join: working student employment", ws.get("employment") == "Working Student", ws)

    senior = by_key.get("1001003", {})
    check("join: absolute href normalized", senior.get("job_key") == "1001003", senior)

    nxt = join_source.find_next_page(html1, "https://join.com/companies/acme")
    check("join: pagination link found", nxt == "https://join.com/companies/acme?page=2", nxt)
    check("join: no next page on last page",
          join_source.find_next_page(html2, "https://join.com/companies/acme?page=2") is None)


# ------------------------------------------------------------ personio parser

def test_personio():
    xml = (FIXTURES / "personio_feed.xml").read_text()
    jobs = personio_source.parse_feed(xml, "acme")
    check("personio: 2 valid positions (broken one skipped)", len(jobs) == 2, jobs)
    by_key = {j["job_key"]: j for j in jobs}

    intern = by_key.get("personio:acme:2515434", {})
    check("personio: intern employment mapped", intern.get("employment") == "Internship", intern)
    check("personio: company from subcompany", intern.get("company") == "ACME GmbH", intern)
    check("personio: posted_date from createdAt", intern.get("posted_date") == date(2026, 5, 2), intern)
    check("personio: description has stripped html with headers",
          "Was erwartet dich bei uns:" in (intern.get("description") or "")
          and "<p>" not in (intern.get("description") or ""), intern.get("description"))

    senior = by_key.get("personio:acme:2515435", {})
    check("personio: permanent mapped to Employee", senior.get("employment") == "Employee", senior)
    check("personio: url built", senior.get("url") == "https://acme.jobs.personio.de/job/2515435", senior)

    # search.json fallback parser accepts the same data as a list of dicts
    payload = [{"id": 7, "name": "Working Student Data", "office": "Munich",
                "department": "Data", "employmentType": "permanent",
                "schedule": "part-time, working student", "createdAt": "2026-06-01T00:00:00+00:00"}]
    sj = personio_source.parse_search_json(payload, "acme")
    check("personio: search.json parsed", len(sj) == 1 and sj[0]["job_key"] == "personio:acme:7", sj)
    check("personio: search.json working student mapping", sj[0]["employment"] == "Working Student", sj)


# ------------------------------------------------------------- enrichment

def test_enrichment():
    check("language: german detected",
          runner.detect_language("Werkstudent Marketing und Kommunikation") == "de")
    check("language: english detected",
          runner.detect_language("Founders Associate Intern", "You will join our team and own projects") == "en")
    check("remote: detected from location", runner.detect_remote("Engineer", "Remote, Germany") is True)
    check("remote: unknown stays None", runner.detect_remote("Engineer", "Munich") is None)

    j1 = {"title": "A", "location": "B", "employment": "C", "department": "D", "url": "E", "description": "F"}
    check("content_hash: stable", runner.content_hash(j1) == runner.content_hash(dict(j1)))
    check("content_hash: changes with content", runner.content_hash(j1) != runner.content_hash({**j1, "title": "X"}))


# ------------------------------------------------------------- ingest (sqlite)

def make_db():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    eng = create_engine("sqlite://")
    Job.__table__.create(eng)
    return sessionmaker(bind=eng)()


def job(key, title="Intern", **kw):
    return {"job_key": key, "company": "acme", "title": title,
            "location": "Munich, Germany", "employment": "Internship",
            "department": "Ops", "url": f"https://join.com/companies/acme/{key}-x", **kw}


def test_ingest():
    db = make_db()
    t0 = datetime(2026, 6, 1, tzinfo=timezone.utc)

    new, seen = runner.ingest(db, "join", "acme", [job("1"), job("2")], now=t0)
    check("ingest: stores everything unfiltered", new == 2 and len(seen) == 2)

    # re-run identical -> zero new, zero duplicates
    new, _ = runner.ingest(db, "join", "acme", [job("1"), job("2")], now=t0)
    check("ingest: re-run creates zero duplicates", new == 0 and db.query(Job).count() == 2)

    # content change -> in-place update, still no new row
    new, _ = runner.ingest(db, "join", "acme", [job("1", title="Intern (extended deadline)"), job("2")], now=t0)
    row = db.query(Job).filter_by(job_key="1").one()
    check("ingest: changed content updates row", new == 0 and row.title == "Intern (extended deadline)")

    # job 2 vanishes: 1st miss -> still open, 2nd miss -> closed
    runner.ingest(db, "join", "acme", [job("1")], now=t0)
    row2 = db.query(Job).filter_by(job_key="2").one()
    check("ingest: first miss stays open", row2.closed_at is None and row2.missed_runs == 1)
    runner.ingest(db, "join", "acme", [job("1")], now=t0)
    db.refresh(row2)
    check("ingest: second consecutive miss closes", row2.closed_at is not None)

    # failed fetch (fetch_ok=False) never counts as a miss
    row1 = db.query(Job).filter_by(job_key="1").one()
    runner.ingest(db, "join", "acme", [], now=t0, fetch_ok=False)
    db.refresh(row1)
    check("ingest: failed fetch never closes/counts", row1.closed_at is None and row1.missed_runs == 0)

    # reappearing posting reopens and resets the miss counter
    runner.ingest(db, "join", "acme", [job("1"), job("2")], now=t0)
    db.refresh(row2)
    check("ingest: reappeared posting reopens", row2.closed_at is None and row2.missed_runs == 0)


if __name__ == "__main__":
    for fn in (test_join, test_personio, test_enrichment, test_ingest):
        print(fn.__name__)
        fn()
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)
