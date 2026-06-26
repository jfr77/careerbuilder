"""Document generators: cover letter writer, CV tailor (diff view, never
invents experience), and interview trainer. Generated artifacts can be saved
onto a pipeline entry's documents JSON and exported client-side as .txt."""

import difflib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.orm import Session

from .. import llm
from ..auth import current_user
from ..context import job_block, profile_block
from ..db import get_db
from ..models import Job
from ..schemas import CoverLetterRequest, CVTailorRequest, SaveDocumentBody, TrainerRequest
from .pipeline import entry_dict, get_entry_or_404
from .profiles import get_profile_or_404

router = APIRouter(prefix="/api/documents", tags=["documents"],
                   dependencies=[Depends(current_user)])

TONES = {
    "formal_de": "Formal German business letter (Sie-Form), conventional Anschreiben structure.",
    "formal_en": "Formal English business cover letter, professional but not stiff.",
    "startup": "Direct, energetic startup tone in English: short paragraphs, concrete, no fluff or corporate phrases.",
}


def _llm_http(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except llm.LLMUnavailable as e:
        raise HTTPException(503, str(e))
    except llm.LLMError as e:
        raise HTTPException(502, str(e))


def _job_context(db: Session, owner_id: str, pipeline_id=None, job_id=None, pasted=None) -> str:
    """Assemble the job description block from a pipeline entry, a scraped job,
    or pasted text — whichever the request supplies. A pipeline_id is resolved
    through the ownership chokepoint so one user can't read another's entry."""
    parts = []
    if pipeline_id:
        entry = get_entry_or_404(db, pipeline_id, owner_id)
        parts.append(f"Company: {entry.company}\nRole: {entry.role}\nType: {entry.type}"
                     + (f"\nLink: {entry.link}" if entry.link else "")
                     + (f"\nNotes: {entry.notes}" if entry.notes else ""))
        if entry.job_id:
            job = db.get(Job, entry.job_id)
            if job:
                parts.append(job_block(job))
    if job_id:
        job = db.get(Job, job_id)
        if not job:
            raise HTTPException(404, "job not found")
        parts.append(job_block(job))
    if pasted:
        parts.append("Pasted job posting:\n" + pasted[:6000])
    if not parts:
        raise HTTPException(400, "provide a pipeline_id, job_id, or pasted posting")
    return "\n\n".join(parts)


@router.post("/cover-letter")
def cover_letter(profile_id: int, body: CoverLetterRequest, db: Session = Depends(get_db),
                 user: str = Depends(current_user)):
    profile = get_profile_or_404(db, profile_id, user)
    if body.tone not in TONES:
        raise HTTPException(400, f"tone must be one of {sorted(TONES)}")
    job_ctx = _job_context(db, user, body.pipeline_id, None, body.pasted_posting)
    prompt = (
        "Write a one-page cover letter for this candidate and role.\n\n"
        f"CANDIDATE:\n{profile_block(profile)}\n\nCV CONTENT:\n{(profile.cv_base or 'n/a')[:4000]}\n\n"
        f"ROLE:\n{job_ctx}\n\nTONE: {TONES[body.tone]}\n\n"
        "Ground every claim in the candidate's actual profile/CV — do not invent "
        "experience. Return only the letter text, no preamble or commentary."
    )
    draft = _llm_http(llm.complete_text, prompt, max_tokens=1500)
    return {"draft": draft.strip(), "tone": body.tone}


@router.post("/cv-tailor")
def cv_tailor(profile_id: int, body: CVTailorRequest, db: Session = Depends(get_db),
              user: str = Depends(current_user)):
    profile = get_profile_or_404(db, profile_id, user)
    if not profile.cv_base:
        raise HTTPException(400, "this profile has no cv_base yet — add it in the Profile tab")
    job_ctx = _job_context(db, user, body.pipeline_id, body.job_id, body.pasted_posting)
    prompt = (
        "Tailor this master CV to the role below. STRICT RULES: you may only "
        "reorder, rephrase, and select content that already exists in the master "
        "CV — never invent experience, numbers, employers, or skills. Emphasize "
        "what matters most for this role; drop the least relevant lines.\n\n"
        f"MASTER CV:\n{profile.cv_base[:6000]}\n\nROLE:\n{job_ctx}\n\n"
        "Return only the tailored CV text in the same plain-text bullet style "
        "as the master CV. No commentary."
    )
    tailored = _llm_http(llm.complete_text, prompt, max_tokens=2000).strip()

    # diff-style view: unified comparison of base vs tailored, line by line
    diff = []
    for line in difflib.unified_diff(
            profile.cv_base.splitlines(), tailored.splitlines(),
            fromfile="cv_base", tofile="tailored", lineterm="", n=2):
        if line.startswith(("---", "+++")):
            continue
        op = "context"
        if line.startswith("+"):
            op = "add"
        elif line.startswith("-"):
            op = "remove"
        elif line.startswith("@@"):
            op = "hunk"
        diff.append({"op": op, "text": line[1:] if op in ("add", "remove") else line})
    return {"tailored": tailored, "base": profile.cv_base, "diff": diff}


@router.post("/trainer")
def interview_trainer(profile_id: int, body: TrainerRequest, db: Session = Depends(get_db),
                      user: str = Depends(current_user)):
    profile = get_profile_or_404(db, profile_id, user)
    if not body.pipeline_id and not body.industry:
        raise HTTPException(400, "pick a pipeline entry or an industry")
    target = (
        _job_context(db, user, body.pipeline_id) if body.pipeline_id
        else f"Industry: {body.industry} (internship/early-career role)"
    )
    prompt = (
        "Create an interview prep brief for this candidate and target.\n\n"
        f"CANDIDATE:\n{profile_block(profile)}\n\nTARGET:\n{target}\n\n"
        "Respond ONLY with JSON: {\"questions\": [{\"q\": str, \"answer\": "
        "\"<strong sample answer grounded in the candidate's real profile>\"} x5], "
        "\"concepts\": [{\"name\": str, \"explanation\": \"<2-3 sentences>\"} x3], "
        "\"questions_to_ask\": [str, str]}"
    )
    brief = _llm_http(llm.complete_json, prompt, max_tokens=3000)
    return {"brief": brief}


@router.post("/save")
def save_document(body: SaveDocumentBody, db: Session = Depends(get_db),
                  user: str = Depends(current_user)):
    """Attach a generated document to a pipeline entry's documents JSON."""
    if body.doc_type not in ("cover_letter", "cv", "brief"):
        raise HTTPException(400, "doc_type must be cover_letter, cv, or brief")
    entry = get_entry_or_404(db, body.pipeline_id, user)
    docs = dict(entry.documents or {})
    bucket = docs.setdefault(body.doc_type + "s", [])
    item = {
        "title": body.title,
        "content": body.content,
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if body.meta:
        item["meta"] = body.meta
    bucket.append(item)
    entry.documents = docs
    flag_modified(entry, "documents")
    db.commit()
    return entry_dict(entry)
