import json
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import llm
from ..context import job_block, profile_block
from ..db import get_db
from ..models import Job, JobScore, PipelineEntry
from ..schemas import PromptFilterBody
from .profiles import get_profile_or_404

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

# The one place that defines what a job filter is. GET /api/jobs accepts these
# as query params, the prompt-filter endpoint asks the LLM for the same JSON,
# and saved_filters rows store it verbatim.
FILTER_KEYS = ("q", "location", "employment_type", "source", "company",
               "language", "posted_after", "status", "remote")


def clean_filter(raw: dict) -> dict:
    """Validate/normalize a filter dict down to known keys and sane values."""
    f = {}
    for k in FILTER_KEYS:
        v = raw.get(k)
        if v in (None, "", []):
            continue
        if k == "remote":
            f[k] = bool(v)
        elif k == "status":
            if v in ("open", "closed", "all"):
                f[k] = v
        elif k == "posted_after":
            try:
                f[k] = date.fromisoformat(str(v)[:10]).isoformat()
            except ValueError:
                continue
        elif k == "language":
            v = str(v).lower()
            if v in ("de", "en"):
                f[k] = v
        else:
            f[k] = str(v)
    return f


def apply_filter(stmt, f: dict):
    """Apply a cleaned filter dict to a select over Job."""
    status = f.get("status", "open")
    if status == "open":
        stmt = stmt.where(Job.closed_at.is_(None))
    elif status == "closed":
        stmt = stmt.where(Job.closed_at.is_not(None))

    if f.get("q"):
        like = f"%{f['q']}%"
        stmt = stmt.where(Job.title.ilike(like) | Job.company.ilike(like)
                          | Job.description.ilike(like))
    if f.get("location"):
        stmt = stmt.where(Job.location.ilike(f"%{f['location']}%"))
    if f.get("employment_type"):
        stmt = stmt.where(Job.employment.ilike(f["employment_type"].replace("_", " ")))
    if f.get("source"):
        stmt = stmt.where(Job.source == f["source"])
    if f.get("company"):
        like = f"%{f['company']}%"
        stmt = stmt.where(Job.company.ilike(like) | Job.company_slug.ilike(like))
    if f.get("language"):
        stmt = stmt.where(Job.language == f["language"])
    if f.get("remote"):
        stmt = stmt.where(Job.remote.is_(True))
    if f.get("posted_after"):
        cutoff = date.fromisoformat(f["posted_after"])
        # join postings carry no posted_date; fall back to when we first saw them
        stmt = stmt.where(func.coalesce(Job.posted_date, func.date(Job.first_seen)) >= cutoff)
    return stmt


def run_filter_query(db: Session, profile_id: int, f: dict,
                     sort: str = "newest", page: int = 1, page_size: int = 50):
    """Shared by GET /api/jobs and POST /api/jobs/prompt-filter."""
    page = max(1, page)
    page_size = max(1, min(page_size, 200))

    base = apply_filter(select(Job), f)
    total = db.scalar(select(func.count()).select_from(base.subquery()))

    stmt = apply_filter(
        select(Job, JobScore).outerjoin(
            JobScore, (JobScore.job_id == Job.id) & (JobScore.profile_id == profile_id)), f)
    if sort == "fit":
        stmt = stmt.order_by(JobScore.fit_score.desc().nulls_last(), Job.company)
    else:  # newest first
        stmt = stmt.order_by(func.coalesce(Job.posted_date, func.date(Job.first_seen)).desc(),
                             Job.first_seen.desc())
    rows = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "results": [job_dict(j, s) for j, s in rows],
        "total": total, "page": page, "page_size": page_size, "sort": sort,
        "filter": f,
    }


def job_dict(j: Job, s: JobScore | None = None):
    return {
        "id": j.id, "job_key": j.job_key, "source": j.source, "company": j.company,
        "company_slug": j.company_slug, "title": j.title, "location": j.location,
        "remote": j.remote, "employment": j.employment, "department": j.department,
        "language": j.language, "url": j.url, "description": j.description,
        "posted_date": j.posted_date.isoformat() if j.posted_date else None,
        "first_seen": j.first_seen.isoformat() if j.first_seen else None,
        "last_seen": j.last_seen.isoformat() if j.last_seen else None,
        "closed_at": j.closed_at.isoformat() if j.closed_at else None,
        "fit_score": s.fit_score if s else None,
        "fit_note": s.fit_note if s else None,
        "fit_breakdown": s.fit_breakdown if s else None,
        "scored_at": s.scored_at.isoformat() if s and s.scored_at else None,
    }


@router.get("")
def list_jobs(profile_id: int, q: str | None = None, location: str | None = None,
              employment_type: str | None = None, source: str | None = None,
              company: str | None = None, language: str | None = None,
              posted_after: str | None = None, status: str = "open",
              remote: bool | None = None, sort: str = "newest",
              page: int = 1, page_size: int = 50, db: Session = Depends(get_db)):
    """Filtered, paginated job pool joined with the ACTIVE profile's scores.
    All filtering is query-time — ingestion stores everything."""
    get_profile_or_404(db, profile_id)
    f = clean_filter({"q": q, "location": location, "employment_type": employment_type,
                      "source": source, "company": company, "language": language,
                      "posted_after": posted_after, "status": status, "remote": remote})
    return run_filter_query(db, profile_id, f, sort=sort, page=page, page_size=page_size)


@router.get("/facets")
def job_facets(db: Session = Depends(get_db)):
    """Distinct values for the filter dropdowns, over the open pool."""
    def distinct(col):
        return sorted(v for v in db.scalars(
            select(col).where(Job.closed_at.is_(None)).distinct()) if v)
    return {
        "companies": distinct(Job.company),
        "employment_types": distinct(Job.employment),
        "languages": distinct(Job.language),
        "sources": distinct(Job.source),
    }


@router.post("/prompt-filter")
def prompt_filter(profile_id: int, body: PromptFilterBody, db: Session = Depends(get_db)):
    """One LLM call turns a free-text prompt into the structured filter JSON,
    then a normal DB query runs — the LLM never scores individual jobs.
    Returns the parsed filter (for editable chips) plus the results."""
    get_profile_or_404(db, profile_id)
    today = date.today().isoformat()
    prompt = (
        "Convert this job-search request into a filter JSON object.\n\n"
        f"Request: {body.prompt!r}\n\nToday is {today}.\n\n"
        "Respond ONLY with JSON using exactly these keys (omit or null any the "
        "request does not mention):\n"
        '{"q": "<keyword(s) for title/company/description, e.g. \'founder associate\' '
        "— keep it short, this is a substring match>\", "
        '"location": "<city/region substring>", '
        '"employment_type": one of ["Internship","Working Student","Employee","Trainee","Freelance"], '
        '"source": one of ["join","personio","manual"], '
        '"company": "<company name substring>", '
        '"language": "de" or "en" (posting language), '
        '"posted_after": "YYYY-MM-DD" (resolve relative spans like \'last 2 weeks\' '
        f"against {today}), "
        '"status": "open" (default) or "closed" or "all", '
        '"remote": true (only if remote work is explicitly required)}\n'
        "Never invent constraints that are not in the request."
    )
    try:
        raw = llm.complete_json(prompt, max_tokens=400)
    except llm.LLMUnavailable as e:
        raise HTTPException(503, str(e))
    except llm.LLMError as e:
        raise HTTPException(502, str(e))
    if not isinstance(raw, dict):
        raise HTTPException(502, f"LLM returned a non-object filter: {json.dumps(raw)[:200]}")
    f = clean_filter(raw)
    return run_filter_query(db, profile_id, f)


def _score_one(db: Session, job: Job, profile) -> JobScore:
    """Score one job against the live profile row via the LLM and upsert."""
    prompt = (
        "Candidate profile:\n" + profile_block(profile) +
        "\n\nJob posting:\n" + job_block(job) +
        "\n\nScore the candidate's fit for this role. Respond ONLY with JSON:\n"
        '{"score": <int 1-10>, "note": "<one sentence>", "breakdown": {'
        '"skills_match": <int 1-10>, "learning_goal_match": <int 1-10>, '
        '"role_expectation_match": <int 1-10>, "culture_criteria_match": <int 1-10>}}'
    )
    data = llm.complete_json(prompt, max_tokens=400)
    score = max(1, min(10, int(data.get("score", 5))))

    existing = db.scalar(select(JobScore).where(
        JobScore.job_id == job.id, JobScore.profile_id == profile.id))
    if existing:
        existing.fit_score = score
        existing.fit_note = str(data.get("note", ""))
        existing.fit_breakdown = data.get("breakdown")
        existing.scored_at = datetime.now(timezone.utc)
        db.commit()
        return existing
    row = JobScore(job_id=job.id, profile_id=profile.id, fit_score=score,
                   fit_note=str(data.get("note", "")), fit_breakdown=data.get("breakdown"))
    db.add(row)
    db.commit()
    return row


@router.post("/{job_id}/score")
def score_job(job_id: int, profile_id: int, db: Session = Depends(get_db)):
    """Score (or re-score) one job for one profile."""
    profile = get_profile_or_404(db, profile_id)
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    try:
        s = _score_one(db, job, profile)
    except llm.LLMUnavailable as e:
        raise HTTPException(503, str(e))
    except llm.LLMError as e:
        raise HTTPException(502, str(e))
    return job_dict(job, s)


@router.post("/score-unscored")
def score_unscored(profile_id: int, limit: int = 15, db: Session = Depends(get_db)):
    """Lazy bulk scoring: score up to `limit` open relevant jobs that have no
    score yet for this profile. The UI can call repeatedly until done=0."""
    profile = get_profile_or_404(db, profile_id)
    if not llm.available():
        raise HTTPException(503, "ANTHROPIC_API_KEY is not set — scoring needs the LLM.")
    jobs = db.scalars(
        select(Job)
        .outerjoin(JobScore, (JobScore.job_id == Job.id) & (JobScore.profile_id == profile_id))
        .where(Job.closed_at.is_(None), JobScore.id.is_(None))
        .limit(limit)
    ).all()
    done, errors = 0, []
    for job in jobs:
        try:
            _score_one(db, job, profile)
            done += 1
        except llm.LLMError as e:
            errors.append(f"{job.title}: {e}")
    remaining = db.scalar(
        select(Job.id)
        .outerjoin(JobScore, (JobScore.job_id == Job.id) & (JobScore.profile_id == profile_id))
        .where(Job.closed_at.is_(None), JobScore.id.is_(None))
        .limit(1)
    )
    return {"scored": done, "remaining": remaining is not None, "errors": errors}


@router.post("/{job_id}/add-to-pipeline", status_code=201)
def add_to_pipeline(job_id: int, profile_id: int, db: Session = Depends(get_db)):
    get_profile_or_404(db, profile_id)
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    dupe = db.scalar(select(PipelineEntry).where(
        PipelineEntry.profile_id == profile_id, PipelineEntry.job_id == job_id))
    if dupe:
        raise HTTPException(409, f"already in pipeline ({dupe.company} — {dupe.role})")
    entry = PipelineEntry(
        profile_id=profile_id, job_id=job.id, company=job.company, role=job.title,
        type="other", stage="researching", link=job.url, documents={},
    )
    db.add(entry)
    db.commit()
    return {"id": entry.id, "company": entry.company, "role": entry.role, "stage": entry.stage}
