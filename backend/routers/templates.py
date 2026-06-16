"""Studio template library: {{placeholder}} templates for cover letters, CV
sections and outreach messages. Built-ins ship read-only — duplicate to
customize. Rendering fills placeholders from the linked kanban card + the
active profile; "Draft with AI" additionally tailors the result to the job
description via one LLM call (the user always edits before sending anything).
"""

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import llm
from ..context import job_block, profile_block
from ..db import get_db
from ..models import Job, PipelineEntry, Template
from ..schemas import (TEMPLATE_TYPES, TemplateCreate, TemplateDraftRequest,
                       TemplateRenderRequest, TemplateUpdate)
from .pipeline import get_entry_or_404
from .profiles import get_profile_or_404

router = APIRouter(prefix="/api/templates", tags=["templates"])

PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")

# Built-in templates ship read-only (duplicate to customize). Bodies live here
# in Python rather than schema.sql — the long German/English text avoids painful
# SQL escaping, and seed_builtins() upserts them by name at startup, so a fresh
# database self-seeds and an already-seeded one is left untouched (idempotent).
BUILTIN_TEMPLATES = [
    {
        "name": "Anschreiben — klassisch (DE)",
        "type": "cover_letter", "language": "de",
        "body": (
            "{{my_name}}\nMünchen\n\n{{company}}\nz. Hd. {{hiring_manager}}\n\n"
            "Bewerbung als {{role}}\n\nSehr geehrte/r {{hiring_manager}},\n\n"
            "mit großem Interesse habe ich Ihre Ausschreibung für die Position "
            "{{role}} bei {{company}} (gefunden über {{source}}) gelesen. Die "
            "Kombination aus [konkreter Aspekt der Rolle] und [Aspekt des "
            "Unternehmens] entspricht genau dem Umfeld, in dem ich arbeiten und "
            "lernen möchte.\n\nIn meiner bisherigen Tätigkeit habe ich [wichtigste "
            "relevante Erfahrung mit Ergebnis]. Dabei habe ich gelernt, [Fähigkeit, "
            "die zur Rolle passt]. Diese Erfahrung möchte ich bei {{company}} "
            "einbringen, um [konkreter Beitrag].\n\nÜber die Möglichkeit eines "
            "persönlichen Gesprächs freue ich mich sehr.\n\nMit freundlichen "
            "Grüßen\n{{my_name}}"
        ),
    },
    {
        "name": "Cover letter — startup tone (EN)",
        "type": "cover_letter", "language": "en",
        "body": (
            "Hi {{hiring_manager}},\n\nI'm {{my_name}}, and I want to work on "
            "{{role}} at {{company}}.\n\nWhy me: [one sentence on the single most "
            "relevant thing you've done, with a number]. [One sentence on a second "
            "proof point]. I work fast, take ownership, and don't need "
            "hand-holding.\n\nWhy {{company}}: [one specific, honest reason — "
            "product, market, team].\n\nI'd love to show you what I could "
            "contribute in a quick call.\n\nBest,\n{{my_name}}"
        ),
    },
    {
        "name": "Founder's Associate outreach (EN)",
        "type": "outreach", "language": "en",
        "body": (
            "Subject: {{role}} @ {{company}} — quick intro\n\nHi {{hiring_manager}},"
            "\n\nI'm {{my_name}} — I saw the {{role}} opening via {{source}} and "
            "didn't want to just disappear into the applicant pile.\n\nIn short: "
            "[strongest 1-line proof of generalist execution, with a number]. I'm "
            "looking for exactly the kind of end-to-end ownership a founder's "
            "associate role offers, and [specific reason {{company}} stands out]."
            "\n\nWould you be open to a 15-minute call this week?\n\n{{my_name}}"
        ),
    },
    {
        "name": "CV Profil / Kurzprofil (DE)",
        "type": "cv_section", "language": "de",
        "body": (
            "PROFIL\n{{my_name}} — [Studiengang/Abschluss], [Stadt]. [Anzahl] Jahre "
            "Erfahrung in [Bereich] mit Schwerpunkt [Schwerpunkt]. Nachweisbare "
            "Erfolge: [Erfolg mit Zahl]. Sucht {{role}} bei {{company}}, um "
            "[Lernziel/Beitrag]."
        ),
    },
    {
        "name": "CV profile / summary (EN)",
        "type": "cv_section", "language": "en",
        "body": (
            "PROFILE\n{{my_name}} — [degree/university], [city]. [N] years of "
            "experience in [area], focused on [focus]. Proven impact: [achievement "
            "with a number]. Now looking to bring [key strength] to the {{role}} "
            "role at {{company}}."
        ),
    },
]


def seed_builtins():
    """Insert any missing built-in templates (idempotent, matched by name)."""
    from ..db import SessionLocal
    db = SessionLocal()
    try:
        have = set(db.scalars(select(Template.name).where(Template.is_builtin.is_(True))))
        added = 0
        for t in BUILTIN_TEMPLATES:
            if t["name"] not in have:
                db.add(Template(is_builtin=True, **t))
                added += 1
        if added:
            db.commit()
        return added
    finally:
        db.close()


def template_dict(t: Template):
    return {
        "id": t.id, "name": t.name, "type": t.type, "language": t.language,
        "body": t.body, "is_builtin": t.is_builtin,
        "placeholders": sorted(set(PLACEHOLDER_RE.findall(t.body))),
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


def get_template_or_404(db: Session, template_id: int) -> Template:
    t = db.get(Template, template_id)
    if not t:
        raise HTTPException(404, f"template {template_id} not found")
    return t


def placeholder_values(profile, entry: PipelineEntry | None) -> dict:
    """{{placeholder}} -> value, from the user profile + linked kanban card."""
    values = {"my_name": profile.name}
    if entry:
        values.update({
            "company": entry.company,
            "role": entry.role,
            "hiring_manager": entry.contact_name,
            "source": entry.source,
        })
    return {k: v for k, v in values.items() if v}


def fill(body: str, values: dict) -> tuple[str, list[str]]:
    """Replace known placeholders; return (text, unresolved placeholder names)."""
    unresolved = []

    def sub(m):
        name = m.group(1)
        if values.get(name):
            return values[name]
        unresolved.append(name)
        return m.group(0)  # keep {{name}} visible for the editor to flag

    return PLACEHOLDER_RE.sub(sub, body), sorted(set(unresolved))


def validate(data: dict):
    if "type" in data and data["type"] not in TEMPLATE_TYPES:
        raise HTTPException(400, f"type must be one of {sorted(TEMPLATE_TYPES)}")
    if "language" in data and data["language"] not in ("de", "en"):
        raise HTTPException(400, "language must be de or en")


@router.get("")
def list_templates(db: Session = Depends(get_db)):
    rows = db.scalars(select(Template).order_by(
        Template.is_builtin.desc(), Template.type, Template.name)).all()
    return [template_dict(t) for t in rows]


@router.post("", status_code=201)
def create_template(body: TemplateCreate, db: Session = Depends(get_db)):
    data = body.model_dump()
    validate(data)
    t = Template(**data, is_builtin=False)
    db.add(t)
    db.commit()
    return template_dict(t)


@router.post("/{template_id}/duplicate", status_code=201)
def duplicate_template(template_id: int, db: Session = Depends(get_db)):
    src = get_template_or_404(db, template_id)
    copy = Template(name=f"{src.name} (copy)", type=src.type,
                    language=src.language, body=src.body, is_builtin=False)
    db.add(copy)
    db.commit()
    return template_dict(copy)


@router.patch("/{template_id}")
def update_template(template_id: int, body: TemplateUpdate, db: Session = Depends(get_db)):
    t = get_template_or_404(db, template_id)
    if t.is_builtin:
        raise HTTPException(403, "built-in templates are read-only — duplicate it to customize")
    updates = body.model_dump(exclude_unset=True)
    validate(updates)
    for field, value in updates.items():
        setattr(t, field, value)
    t.updated_at = datetime.now(timezone.utc)
    db.commit()
    return template_dict(t)


@router.delete("/{template_id}")
def delete_template(template_id: int, db: Session = Depends(get_db)):
    t = get_template_or_404(db, template_id)
    if t.is_builtin:
        raise HTTPException(403, "built-in templates cannot be deleted")
    db.delete(t)
    db.commit()
    return {"deleted": template_id}


@router.post("/{template_id}/render")
def render_template(template_id: int, profile_id: int, body: TemplateRenderRequest,
                    db: Session = Depends(get_db)):
    """Pure placeholder fill from card + profile — no LLM involved."""
    profile = get_profile_or_404(db, profile_id)
    t = get_template_or_404(db, template_id)
    entry = get_entry_or_404(db, body.pipeline_id) if body.pipeline_id else None
    text, unresolved = fill(t.body, placeholder_values(profile, entry))
    return {"text": text, "unresolved": unresolved,
            "template_id": t.id, "template_name": t.name,
            "pipeline_id": entry.id if entry else None}


@router.post("/{template_id}/draft")
def draft_with_ai(template_id: int, profile_id: int, body: TemplateDraftRequest,
                  db: Session = Depends(get_db)):
    """Template + job description + profile -> one tailored, fully resolved
    draft for the editor. Nothing is ever sent anywhere automatically."""
    profile = get_profile_or_404(db, profile_id)
    t = get_template_or_404(db, template_id)
    entry = get_entry_or_404(db, body.pipeline_id) if body.pipeline_id else None
    if not entry and not (body.pasted_posting or "").strip():
        raise HTTPException(400, "pick a pipeline entry or paste a posting")

    prefilled, _ = fill(t.body, placeholder_values(profile, entry))

    job_parts = []
    if entry:
        job_parts.append(f"Company: {entry.company}\nRole: {entry.role}"
                         + (f"\nNotes: {entry.notes}" if entry.notes else ""))
        if entry.job_id and (job := db.get(Job, entry.job_id)):
            job_parts.append(job_block(job))
    if body.pasted_posting:
        job_parts.append("Pasted job posting:\n" + body.pasted_posting[:6000])

    prompt = (
        "Fill in and tailor this application template for the candidate and "
        "role below. Keep the template's structure, tone and language exactly "
        "(German templates stay German). Replace every remaining {{placeholder}} "
        "and every [bracketed instruction] with specific content grounded in the "
        "candidate's real profile/CV — never invent experience, numbers or names. "
        "If the hiring manager's name is unknown, use an appropriate generic "
        "salutation for that language.\n\n"
        f"TEMPLATE ({t.name}):\n{prefilled}\n\n"
        f"CANDIDATE:\n{profile_block(profile)}\n\nCV CONTENT:\n{(profile.cv_base or 'n/a')[:4000]}\n\n"
        f"ROLE:\n{chr(10).join(job_parts)}\n\n"
        "Return only the finished text, no preamble or commentary."
    )
    try:
        draft = llm.complete_text(prompt, max_tokens=1500).strip()
    except llm.LLMUnavailable as e:
        raise HTTPException(503, str(e))
    except llm.LLMError as e:
        raise HTTPException(502, str(e))

    _, unresolved = fill(draft, {})  # anything the LLM left unfilled
    return {"text": draft, "unresolved": unresolved,
            "template_id": t.id, "template_name": t.name,
            "pipeline_id": entry.id if entry else None}
