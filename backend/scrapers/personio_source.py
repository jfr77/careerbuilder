"""Personio scraper source.

Companies hosting careers on Personio expose a public, stable XML feed at
https://{slug}.jobs.personio.de/xml — Personio documents this feed for job
boards, so it is far more robust than scraping the HTML career page. Each
<position> carries id, name, office, department, employmentType, schedule,
createdAt and HTML job descriptions. Newer career pages also expose
/search.json with the same data; it is used as a fallback when /xml fails.

Same contract as join_source: scrape_company(slug, session) -> (jobs, error);
runner.ingest() handles storage, dedup, and closed detection.
"""

import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime

import requests

USER_AGENT = "JobDiscoveryMVP/0.1 (personal job search tool)"


def domain_for(slug):
    return f"{slug}.jobs.personio.de"


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


def _parse_date(value) -> date | None:
    """createdAt comes as an ISO timestamp ('2026-05-02T09:21:55+00:00')."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _map_employment(emp_raw: str, schedule: str) -> str | None:
    """Map Personio employmentType onto the vocabulary the join source produces."""
    employment = {
        "intern": "Internship",
        "trainee": "Trainee",
        "freelance": "Freelance",
    }.get(emp_raw)
    if employment is None and emp_raw:
        employment = "Working Student" if "working" in schedule else "Employee"
    return employment


def _job(company_slug, pos_id, name, *, office=None, department=None,
         emp_raw="", schedule="", description=None, posted_date=None, company=None):
    return {
        "job_key": f"personio:{company_slug}:{pos_id}",
        "company": company or company_slug,
        "title": name,
        "location": office,
        "employment": _map_employment(emp_raw.lower(), schedule.lower()),
        "department": department,
        "url": f"https://{company_slug}.jobs.personio.de/job/{pos_id}",
        "description": description,
        "posted_date": posted_date,
    }


def parse_feed(xml_text, company_slug):
    """Parse a Personio XML job feed into the shared scraper job format."""
    root = ET.fromstring(xml_text)
    jobs = []
    for pos in root.iter("position"):
        pos_id = _text(pos, "id")
        name = _text(pos, "name")
        if not pos_id or not name:
            continue

        # jobDescriptions holds HTML blocks; concatenate as plain text so the
        # LLM scorer has real posting content to work with.
        desc_parts = []
        for d in pos.iter("jobDescription"):
            header = _text(d, "name")
            body = _strip_html(_text(d, "value"))
            if body:
                desc_parts.append(f"{header}: {body}" if header else body)

        jobs.append(_job(
            company_slug, pos_id, name,
            office=_text(pos, "office"),
            department=_text(pos, "department"),
            emp_raw=_text(pos, "employmentType") or "",
            schedule=_text(pos, "schedule") or "",
            description="\n\n".join(desc_parts) or None,
            posted_date=_parse_date(_text(pos, "createdAt")),
            company=_text(pos, "subcompany"),
        ))
    return jobs


def parse_search_json(payload, company_slug):
    """Parse the /search.json fallback (newer Personio career pages). The
    payload is a list of position objects with keys similar to the XML feed."""
    if isinstance(payload, dict):
        payload = payload.get("positions") or payload.get("jobs") or []
    jobs = []
    for pos in payload:
        if not isinstance(pos, dict):
            continue
        pos_id, name = pos.get("id"), pos.get("name")
        if not pos_id or not name:
            continue
        jobs.append(_job(
            company_slug, pos_id, name,
            office=pos.get("office"),
            department=pos.get("department"),
            emp_raw=str(pos.get("employmentType") or ""),
            schedule=str(pos.get("schedule") or ""),
            description=_strip_html(pos.get("description")),
            posted_date=_parse_date(pos.get("createdAt")),
            company=pos.get("subcompany"),
        ))
    return jobs


def scrape_company(slug, session):
    """Fetch one company's postings: /xml first, /search.json as fallback.
    Returns (jobs, error); error is None only when one of the two structured
    endpoints parsed successfully."""
    xml_url = f"https://{slug}.jobs.personio.de/xml"
    try:
        resp = session.get(xml_url, timeout=20)
        resp.raise_for_status()
        return parse_feed(resp.text, slug), None
    except (requests.RequestException, ET.ParseError) as e:
        xml_error = str(e)
        print(f"  ! {slug}: personio /xml failed ({e}), trying /search.json", file=sys.stderr)

    try:
        resp = session.get(f"https://{slug}.jobs.personio.de/search.json", timeout=20)
        resp.raise_for_status()
        return parse_search_json(resp.json(), slug), None
    except (requests.RequestException, json.JSONDecodeError) as e:
        print(f"  ! {slug}: personio /search.json failed too ({e})", file=sys.stderr)
        return [], f"/xml: {xml_error}; /search.json: {e}"
