#!/usr/bin/env python3
"""
join_scraper.py — Layer 1 of the job-discovery MVP
====================================================

Monitors join.com company pages for new job postings, stores them in SQLite
with dedup, and flags new matches against your keyword filter. Optionally
scores each new match against your profile via the Anthropic API.

Usage:
    pip install requests beautifulsoup4
    python join_scraper.py                 # scrape watchlist, print new jobs
    python join_scraper.py --all           # print every tracked job, not just new
    python join_scraper.py --add pactos    # add a company slug to the watchlist

    # optional LLM fit scoring (set your key first):
    export ANTHROPIC_API_KEY=sk-ant-...
    python join_scraper.py --score

Schedule it:  crontab -e  →  0 9 * * *  cd /path/to && python join_scraper.py --score >> scraper.log

Notes:
- Scrapes only public company career pages on join.com, politely (1 req/sec,
  honest User-Agent). Check join.com/robots.txt if you scale this up.
- A job that disappears from a company page gets closed_at set automatically
  → closed postings stop appearing in results.
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------- config

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jobs.db")
WATCHLIST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watchlist.json")

# Companies to monitor (join.com slugs). Seeded with relevant Munich startups —
# extend via --add or by editing watchlist.json directly.
DEFAULT_WATCHLIST = [
    "pactos",
    "cocrafter",
    "gotfunded",        # FUNDED
    "firstmomentum12",  # First Momentum Ventures
]

# A job must match at least one include-keyword (case-insensitive) in its title
# to be flagged as relevant. Empty list = everything is relevant.
INCLUDE_KEYWORDS = [
    "founder", "associate", "chief of staff", "intern", "praktik",
    "werkstudent", "strategy", "venture", "growth", "business development",
]

# Jobs whose title matches an exclude-keyword are skipped even if included above.
EXCLUDE_KEYWORDS = [
    "senior", "lead", "head of", "engineer", "developer",
]

REQUEST_DELAY_SECONDS = 1.0
USER_AGENT = "JobDiscoveryMVP/0.1 (personal job search tool)"

# Your profile, used only when --score is passed and ANTHROPIC_API_KEY is set.
CANDIDATE_PROFILE = """\
Final-year Informatics & Economics student at TU München, Munich. 4 years
working student Data Analyst at parcelLab (VC-backed B2B SaaS): dbt, Redshift,
SQL, Python, client-facing analytics for UK/US enterprise accounts. Courses
this semester: Entrepreneurship for Small Software-oriented Enterprises, Legal
Basics for Startups. Personal investment portfolio. Fluent German, English,
Russian. Seeking 6-month internship from Oct 2026 (flexible Sep). Criteria:
build operations from scratch, end-to-end ownership, high-intensity culture,
stakeholder communication, maximum learning density."""

# ---------------------------------------------------------------- storage

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_key     TEXT UNIQUE NOT NULL,   -- join.com numeric id from the URL
    company     TEXT NOT NULL,
    title       TEXT NOT NULL,
    location    TEXT,
    employment  TEXT,
    department  TEXT,
    url         TEXT NOT NULL,
    relevant    INTEGER NOT NULL DEFAULT 0,
    fit_score   INTEGER,
    fit_note    TEXT,
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL,
    closed_at   TEXT
);
"""


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(SCHEMA)
    conn.row_factory = sqlite3.Row
    return conn


def load_watchlist():
    if os.path.exists(WATCHLIST_PATH):
        with open(WATCHLIST_PATH) as f:
            return json.load(f)
    save_watchlist(DEFAULT_WATCHLIST)
    return list(DEFAULT_WATCHLIST)


def save_watchlist(slugs):
    with open(WATCHLIST_PATH, "w") as f:
        json.dump(sorted(set(slugs)), f, indent=2)


# ---------------------------------------------------------------- scraping

JOB_LINK_RE = re.compile(r"^/companies/([^/]+)/(\d+)-")


def fetch(url, session):
    resp = session.get(url, timeout=20)
    resp.raise_for_status()
    return resp.text


def parse_company_page(html, company_slug):
    """Extract job postings from a join.com company page.

    Join renders each posting as an <a> whose href matches
    /companies/{slug}/{numeric_id}-{title-slug}; the anchor text concatenates
    title, location, employment type, and department.
    """
    soup = BeautifulSoup(html, "html.parser")
    jobs = []
    for a in soup.find_all("a", href=True):
        # normalise absolute hrefs to path form
        href = a["href"]
        href_path = re.sub(r"^https?://join\.com", "", href)
        m = JOB_LINK_RE.match(href_path)
        if not m or m.group(1) != company_slug:
            continue
        job_key = m.group(2)
        text = a.get_text(" ", strip=True)

        # The anchor text packs fields together; split heuristically. The
        # employment type can also appear inside the title ("... - Internship"),
        # so always anchor on the LAST occurrence.
        emp_matches = list(re.finditer(r"(Internship|Employee|Working Student|Freelance|Trainee)", text))
        employment = emp_matches[-1].group(1) if emp_matches else None

        location, title, department = None, text, None
        if emp_matches:
            last = emp_matches[-1]
            head = text[:last.start()]
            department = text[last.end():].strip() or None
            # Location: "<City>, <Country>" at the end of head
            loc_match = re.search(r"([A-Za-zÀ-ž .-]+,\s*[A-Za-zÀ-ž .-]+?)\s*$", head)
            if loc_match:
                location = loc_match.group(1).strip()
                title = head[:loc_match.start()].strip()
            else:
                title = head.strip()

        jobs.append({
            "job_key": job_key,
            "company": company_slug,
            "title": title or text,
            "location": location,
            "employment": employment,
            "department": department,
            "url": f"https://join.com{href_path}",
        })
    return jobs


def find_next_page(html, current_url):
    """Join paginates company pages with ?page=N links."""
    soup = BeautifulSoup(html, "html.parser")
    current_page = 1
    m = re.search(r"[?&]page=(\d+)", current_url)
    if m:
        current_page = int(m.group(1))
    for a in soup.find_all("a", href=True):
        pm = re.search(r"[?&]page=(\d+)", a["href"])
        if pm and int(pm.group(1)) == current_page + 1:
            href = a["href"]
            if href.startswith("/"):
                return "https://join.com" + href
            return href
    return None


def scrape_company(slug, session):
    url = f"https://join.com/companies/{slug}"
    all_jobs, seen_pages = [], set()
    while url and url not in seen_pages:
        seen_pages.add(url)
        try:
            html = fetch(url, session)
        except requests.RequestException as e:
            print(f"  ! {slug}: fetch failed ({e})", file=sys.stderr)
            return all_jobs
        all_jobs.extend(parse_company_page(html, slug))
        url = find_next_page(html, url)
        time.sleep(REQUEST_DELAY_SECONDS)
    # dedupe by job_key (pagination overlap safety)
    unique = {j["job_key"]: j for j in all_jobs}
    return list(unique.values())


# ---------------------------------------------------------------- relevance

def is_relevant(title):
    t = title.lower()
    if any(kw in t for kw in (k.lower() for k in EXCLUDE_KEYWORDS)):
        return False
    if not INCLUDE_KEYWORDS:
        return True
    return any(kw in t for kw in (k.lower() for k in INCLUDE_KEYWORDS))


# ---------------------------------------------------------------- LLM scoring

def score_job(job, api_key):
    """Score one job against the candidate profile. Returns (score, note) or (None, None)."""
    prompt = (
        "Candidate profile:\n" + CANDIDATE_PROFILE +
        f"\n\nJob: {job['title']} at {job['company']}"
        f" — {job.get('location') or 'location n/a'},"
        f" {job.get('employment') or 'type n/a'},"
        f" department: {job.get('department') or 'n/a'}.\n\n"
        "Score the candidate's fit for this role 1-10 and give a one-sentence "
        "rationale. Respond ONLY with JSON: {\"score\": <int>, \"note\": \"<sentence>\"}"
    )
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 200,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        resp.raise_for_status()
        text = "".join(b.get("text", "") for b in resp.json().get("content", []))
        data = json.loads(re.sub(r"```json|```", "", text).strip())
        return int(data["score"]), str(data["note"])
    except Exception as e:
        print(f"  ! scoring failed for {job['title']}: {e}", file=sys.stderr)
        return None, None


# ---------------------------------------------------------------- main run

def run(score=False, show_all=False):
    watchlist = load_watchlist()
    conn = db()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if score and not api_key:
        print("--score requested but ANTHROPIC_API_KEY is not set; skipping scoring.\n")
        score = False

    new_jobs = []
    seen_keys_this_run = {}

    print(f"Scraping {len(watchlist)} companies from join.com …\n")
    for slug in watchlist:
        jobs = scrape_company(slug, session)
        seen_keys_this_run[slug] = {j["job_key"] for j in jobs}
        print(f"  {slug}: {len(jobs)} open positions")
        for j in jobs:
            relevant = 1 if is_relevant(j["title"]) else 0
            row = conn.execute(
                "SELECT id FROM jobs WHERE job_key = ?", (j["job_key"],)
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE jobs SET last_seen = ?, closed_at = NULL WHERE job_key = ?",
                    (now, j["job_key"]),
                )
            else:
                fit_score, fit_note = (None, None)
                if score and relevant:
                    fit_score, fit_note = score_job(j, api_key)
                conn.execute(
                    """INSERT INTO jobs
                       (job_key, company, title, location, employment, department,
                        url, relevant, fit_score, fit_note, first_seen, last_seen)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (j["job_key"], j["company"], j["title"], j["location"],
                     j["employment"], j["department"], j["url"], relevant,
                     fit_score, fit_note, now, now),
                )
                if relevant:
                    j["fit_score"], j["fit_note"] = fit_score, fit_note
                    new_jobs.append(j)

    # mark postings that vanished from their company page as closed
    for slug, keys in seen_keys_this_run.items():
        if not keys:
            continue  # fetch may have failed; don't close everything
        placeholders = ",".join("?" * len(keys))
        conn.execute(
            f"""UPDATE jobs SET closed_at = ?
                WHERE company = ? AND closed_at IS NULL
                AND job_key NOT IN ({placeholders})""",
            (now, slug, *keys),
        )

    conn.commit()

    print()
    if new_jobs:
        print(f"=== {len(new_jobs)} NEW relevant posting(s) ===\n")
        for j in sorted(new_jobs, key=lambda x: -(x.get("fit_score") or 0)):
            fit = f"  [fit {j['fit_score']}/10] {j['fit_note']}" if j.get("fit_score") else ""
            print(f"• {j['title']}  —  {j['company']}")
            print(f"  {j.get('location') or ''} · {j.get('employment') or ''}")
            print(f"  {j['url']}{chr(10) + fit if fit else ''}\n")
    else:
        print("No new relevant postings since last run.")

    if show_all:
        print("\n=== All tracked relevant postings (open) ===\n")
        rows = conn.execute(
            """SELECT * FROM jobs WHERE relevant = 1 AND closed_at IS NULL
               ORDER BY fit_score DESC NULLS LAST, first_seen DESC"""
        ).fetchall()
        for r in rows:
            fit = f" [fit {r['fit_score']}/10]" if r["fit_score"] else ""
            print(f"• {r['title']} — {r['company']}{fit}")
            print(f"  {r['url']}\n")

    conn.close()


# ---------------------------------------------------------------- cli

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="join.com job scraper MVP")
    p.add_argument("--score", action="store_true",
                   help="LLM-score new relevant jobs (needs ANTHROPIC_API_KEY)")
    p.add_argument("--all", action="store_true",
                   help="also print all tracked open relevant jobs")
    p.add_argument("--add", metavar="SLUG",
                   help="add a company slug to the watchlist and exit")
    args = p.parse_args()

    if args.add:
        wl = load_watchlist()
        wl.append(args.add.strip().lower())
        save_watchlist(wl)
        print(f"Added '{args.add}' — watchlist now: {', '.join(sorted(set(wl)))}")
        sys.exit(0)

    run(score=args.score, show_all=args.all)
