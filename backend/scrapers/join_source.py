"""join.com scraper source.

The fetch/parse logic below is lifted unchanged from the original
join_scraper.py (kept at docs/join_scraper_original.py) — it is tested against
real join.com pages, so do not rewrite it. Only the storage layer changed:
scrape_company() returns plain dicts that runner.ingest() writes to Postgres.
"""

import re
import sys
import time

import requests
from bs4 import BeautifulSoup

REQUEST_DELAY_SECONDS = 1.0
USER_AGENT = "JobDiscoveryMVP/0.1 (personal job search tool)"

JOB_LINK_RE = re.compile(r"^/companies/([^/]+)/(\d+)-")


def make_session():
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    return session


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
    """Scrape all open postings for one join.com company slug.

    Returns a list of job dicts in the shared scraper format (without source —
    runner.ingest adds it). Network failures return partial results and log to
    stderr, exactly like the original script.
    """
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
