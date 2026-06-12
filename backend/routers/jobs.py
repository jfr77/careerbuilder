from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import llm
from ..context import job_block, profile_block
from ..db import get_db
from ..models import Job, JobScore, PipelineEntry
from .profiles import get_profile_or_404

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


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
def list_jobs(profile_id: int, db: Session = Depends(get_db)):
    """All open jobs joined with the ACTIVE profile's scores,
    fit desc, unscored last. Filtering happens client-side on this payload."""
    get_profile_or_404(db, profile_id)
    rows = db.execute(
        select(Job, JobScore)
        .outerjoin(JobScore, (JobScore.job_id == Job.id) & (JobScore.profile_id == profile_id))
        .where(Job.closed_at.is_(None))
    ).all()
    out = [job_dict(j, s) for j, s in rows]
    out.sort(key=lambda r: (r["fit_score"] is None, -(r["fit_score"] or 0), r["company"]))
    return out


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
