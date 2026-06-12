"""Personio scraper source.

Companies hosting careers on Personio expose a public, stable XML feed at
https://{slug}.jobs.personio.de/xml — Personio documents this feed for job
boards, so it is far more robust than scraping the HTML career page. Each
<position> carries id, name, office, department, employmentType, schedule and
HTML job descriptions.

Same contract as join_source: scrape_company(slug, session) -> list of job
dicts; runner.ingest() handles storage, dedup, and closed detection. Polite
1 req/sec delay between companies is enforced by the runner; the feed itself
is a single request per company.
"""

import re
import sys
import xml.etree.ElementTree as ET

import requests

USER_AGENT = "JobDiscoveryMVP/0.1 (personal job search tool)"


def make_session():
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    return session


def _text(el, tag):
    child = el.find(tag)
    if child is None or child.text is None:
        return None
    value = child.text.strip()
    return value or None


def _strip_html(html):
    if not html:
        return None
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def parse_feed(xml_text, company_slug):
    """Parse a Personio XML job feed into the shared scraper job format."""
    root = ET.fromstring(xml_text)
    jobs = []
    for pos in root.iter("position"):
        pos_id = _text(pos, "id")
        name = _text(pos, "name")
        if not pos_id or not name:
            continue

        # employmentType in the feed is e.g. "intern", "permanent", "trainee";
        # map onto the same vocabulary the join source produces.
        emp_raw = (_text(pos, "employmentType") or "").lower()
        schedule = (_text(pos, "schedule") or "").lower()
        employment = {
            "intern": "Internship",
            "trainee": "Trainee",
            "freelance": "Freelance",
        }.get(emp_raw)
        if employment is None and emp_raw:
            employment = "Working Student" if "working" in schedule else "Employee"

        # jobDescriptions holds HTML blocks; concatenate as plain text so the
        # LLM scorer has real posting content to work with.
        desc_parts = []
        for d in pos.iter("jobDescription"):
            header = _text(d, "name")
            body = _strip_html(_text(d, "value"))
            if body:
                desc_parts.append(f"{header}: {body}" if header else body)
        description = "\n\n".join(desc_parts) or None

        jobs.append({
            "job_key": f"personio:{company_slug}:{pos_id}",
            "company": company_slug,
            "title": name,
            "location": _text(pos, "office"),
            "employment": employment,
            "department": _text(pos, "department"),
            "url": f"https://{company_slug}.jobs.personio.de/job/{pos_id}",
            "description": description,
        })
    return jobs


def scrape_company(slug, session):
    """Fetch and parse one company's Personio feed. Failures return [] and log
    to stderr (the runner then skips closed-detection for that company)."""
    url = f"https://{slug}.jobs.personio.de/xml"
    try:
        resp = session.get(url, timeout=20)
        resp.raise_for_status()
        return parse_feed(resp.text, slug)
    except (requests.RequestException, ET.ParseError) as e:
        print(f"  ! {slug}: personio fetch/parse failed ({e})", file=sys.stderr)
        return []
