from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import llm
from ..db import get_db
from ..models import PipelineEntry
from ..schemas import (PIPELINE_STAGES, PIPELINE_TYPES, PasteExtract,
                       PipelineCreate, PipelineImport, PipelineUpdate)
from .profiles import get_profile_or_404

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


def entry_dict(e: PipelineEntry):
    return {
        "id": e.id, "profile_id": e.profile_id, "job_id": e.job_id,
        "company": e.company, "role": e.role, "type": e.type, "stage": e.stage,
        "link": e.link, "start_date": e.start_date, "end_date": e.end_date,
        "deadline": e.deadline, "reached_out": e.reached_out, "notes": e.notes,
        "documents": e.documents or {},
        "salary_range": e.salary_range, "source": e.source,
        "cv_version": e.cv_version, "cover_letter_version": e.cover_letter_version,
        "contact_name": e.contact_name, "contact_email": e.contact_email,
        "contact_role": e.contact_role,
        "referral": e.referral, "referral_name": e.referral_name,
        "follow_up_date": e.follow_up_date.isoformat() if e.follow_up_date else None,
        "response_date": e.response_date.isoformat() if e.response_date else None,
        "interviews": e.interviews, "excitement": e.excitement,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }


def get_entry_or_404(db: Session, entry_id: int) -> PipelineEntry:
    entry = db.get(PipelineEntry, entry_id)
    if not entry:
        raise HTTPException(404, f"pipeline entry {entry_id} not found")
    return entry


@router.get("")
def list_pipeline(profile_id: int, db: Session = Depends(get_db)):
    get_profile_or_404(db, profile_id)
    rows = db.scalars(
        select(PipelineEntry)
        .where(PipelineEntry.profile_id == profile_id)
        .order_by(PipelineEntry.created_at)
    ).all()
    return [entry_dict(e) for e in rows]


@router.post("", status_code=201)
def create_entry(profile_id: int, body: PipelineCreate, db: Session = Depends(get_db)):
    get_profile_or_404(db, profile_id)
    if body.type not in PIPELINE_TYPES:
        raise HTTPException(400, f"type must be one of {sorted(PIPELINE_TYPES)}")
    if body.stage not in PIPELINE_STAGES:
        raise HTTPException(400, f"stage must be one of {sorted(PIPELINE_STAGES)}")
    entry = PipelineEntry(profile_id=profile_id, documents={}, **body.model_dump())
    db.add(entry)
    db.commit()
    return entry_dict(entry)


@router.post("/import", status_code=201)
def import_entries(profile_id: int, body: PipelineImport, db: Session = Depends(get_db)):
    """Bulk create for CSV/Excel import. Rows with an unknown type/stage are
    coerced to safe defaults rather than rejected — spreadsheets are messy."""
    get_profile_or_404(db, profile_id)
    created = 0
    for item in body.entries:
        data = item.model_dump()
        if data["type"] not in PIPELINE_TYPES:
            data["type"] = "other"
        if data["stage"] not in PIPELINE_STAGES:
            data["stage"] = "researching"
        db.add(PipelineEntry(profile_id=profile_id, documents={}, **data))
        created += 1
    db.commit()
    return {"created": created}


@router.patch("/{entry_id}")
def update_entry(entry_id: int, body: PipelineUpdate, db: Session = Depends(get_db)):
    entry = get_entry_or_404(db, entry_id)
    updates = body.model_dump(exclude_unset=True)
    if "type" in updates and updates["type"] not in PIPELINE_TYPES:
        raise HTTPException(400, f"type must be one of {sorted(PIPELINE_TYPES)}")
    if "stage" in updates and updates["stage"] not in PIPELINE_STAGES:
        raise HTTPException(400, f"stage must be one of {sorted(PIPELINE_STAGES)}")
    for field, value in updates.items():
        setattr(entry, field, value)
    entry.updated_at = datetime.now(timezone.utc)
    db.commit()
    return entry_dict(entry)


@router.delete("/{entry_id}")
def delete_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = get_entry_or_404(db, entry_id)
    db.delete(entry)
    db.commit()
    return {"deleted": entry_id}


@router.post("/extract")
def extract_from_paste(body: PasteExtract):
    """Paste-to-add: LLM extracts structured fields from a raw posting/URL.
    Returns a draft the UI shows in an editable confirmation form."""
    prompt = (
        "Extract application-tracking fields from this pasted job posting (may "
        "include a URL and/or raw page text).\n\n---\n" + body.text[:6000] + "\n---\n\n"
        "Respond ONLY with JSON: {\"company\": str, \"role\": str, "
        "\"type\": one of [\"fa\",\"analytics\",\"consulting\",\"vc\",\"other\"] "
        "(fa = founder's associate / chief of staff / generalist startup ops), "
        "\"link\": str or null (a URL found in the text), "
        "\"start_date\": str or null, \"end_date\": str or null, "
        "\"deadline\": str or null, \"notes\": str or null (one short line of "
        "anything else worth keeping)}. Use null when a field is not present; "
        "never invent values."
    )
    try:
        data = llm.complete_json(prompt, max_tokens=400)
    except llm.LLMUnavailable as e:
        raise HTTPException(503, str(e))
    except llm.LLMError as e:
        raise HTTPException(502, str(e))
    if data.get("type") not in PIPELINE_TYPES:
        data["type"] = "other"
    return {k: data.get(k) for k in
            ("company", "role", "type", "link", "start_date", "end_date", "deadline", "notes")}
