"""Tab 1 chat: Anthropic-backed assistant with 4 backend-executed tools.
History persists per profile in chat_messages."""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import llm
from ..auth import current_user
from ..context import matches_block, pipeline_block, profile_block
from ..db import get_db
from ..models import ChatMessage, Job, JobScore, PipelineEntry, Profile
from ..schemas import ChatSend
from .profiles import get_profile_or_404

router = APIRouter(prefix="/api/chat", tags=["chat"],
                   dependencies=[Depends(current_user)])

EDITABLE_PROFILE_FIELDS = [
    "name", "location", "education", "experience_summary", "role_expectations",
    "learning_goals", "availability", "cv_base", "skills", "languages",
    "target_industries", "target_companies",
]

TOOLS = [
    {
        "name": "update_profile",
        "description": "Update one field of the active user's profile.",
        "input_schema": {
            "type": "object",
            "properties": {
                "field": {"type": "string", "enum": EDITABLE_PROFILE_FIELDS},
                "value": {"type": "string",
                          "description": "New value. For list fields (skills, languages, "
                                         "target_industries, target_companies) pass a JSON array string."},
            },
            "required": ["field", "value"],
        },
    },
    {
        "name": "add_to_pipeline",
        "description": "Add an application to the active user's pipeline board.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company": {"type": "string"},
                "role": {"type": "string"},
                "type": {"type": "string", "enum": ["fa", "analytics", "consulting", "vc", "other"]},
                "stage": {"type": "string",
                          "enum": ["researching", "applied", "in_progress", "offer", "rejected"]},
            },
            "required": ["company", "role"],
        },
    },
    {
        "name": "update_pipeline_stage",
        "description": "Move an existing pipeline entry (matched by company name) to a new stage.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company": {"type": "string"},
                "stage": {"type": "string",
                          "enum": ["researching", "applied", "in_progress", "offer", "rejected"]},
            },
            "required": ["company", "stage"],
        },
    },
    {
        "name": "search_jobs",
        "description": "Search the scraped jobs pool (open postings) by free text over title/company/location.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
]


def _exec_tool(db: Session, profile: Profile, name: str, args: dict) -> str:
    """Execute one tool call against the DB; returns a string result for the LLM."""
    if name == "update_profile":
        field, value = args.get("field"), args.get("value", "")
        if field not in EDITABLE_PROFILE_FIELDS:
            return f"error: field '{field}' is not editable"
        if field in ("skills", "languages", "target_industries", "target_companies"):
            try:
                parsed = json.loads(value)
                if not isinstance(parsed, list):
                    raise ValueError
                value = parsed
            except (json.JSONDecodeError, ValueError):
                value = [v.strip() for v in str(value).split(",") if v.strip()]
        setattr(profile, field, value)
        db.commit()
        return f"profile.{field} updated"

    if name == "add_to_pipeline":
        entry = PipelineEntry(
            profile_id=profile.id, company=args["company"], role=args["role"],
            type=args.get("type", "other"), stage=args.get("stage", "researching"),
            documents={},
        )
        db.add(entry)
        db.commit()
        return f"added {entry.company} — {entry.role} at stage {entry.stage}"

    if name == "update_pipeline_stage":
        entry = db.scalar(select(PipelineEntry).where(
            PipelineEntry.profile_id == profile.id,
            PipelineEntry.company.ilike(f"%{args['company']}%")))
        if not entry:
            return f"error: no pipeline entry matching company '{args['company']}'"
        entry.stage = args["stage"]
        db.commit()
        return f"moved {entry.company} — {entry.role} to {entry.stage}"

    if name == "search_jobs":
        q = f"%{args.get('query', '')}%"
        jobs = db.scalars(select(Job).where(
            Job.closed_at.is_(None),
            (Job.title.ilike(q) | Job.company.ilike(q) | Job.location.ilike(q)),
        ).limit(10)).all()
        if not jobs:
            return "no open jobs match that query"
        return "\n".join(
            f"- {j.title} at {j.company} ({j.location or 'n/a'}) {j.url or ''}" for j in jobs)

    return f"error: unknown tool {name}"


def _system_prompt(db: Session, profile: Profile) -> str:
    entries = db.scalars(select(PipelineEntry).where(
        PipelineEntry.profile_id == profile.id)).all()
    matches = db.execute(
        select(Job, JobScore)
        .join(JobScore, (JobScore.job_id == Job.id) & (JobScore.profile_id == profile.id))
        .where(Job.closed_at.is_(None))
        .order_by(JobScore.fit_score.desc())
        .limit(8)
    ).all()
    return (
        "You are carreerbuilder, a pragmatic career copilot for an internship/early-career "
        "job search. Be concise and concrete. You can modify the user's data with "
        "the provided tools when they ask; confirm what you changed.\n\n"
        f"ACTIVE PROFILE:\n{profile_block(profile)}\n\n"
        f"THEIR PIPELINE:\n{pipeline_block(entries)}\n\n"
        f"TOP SCRAPED JOB MATCHES:\n{matches_block(matches)}"
    )


def msg_dict(m: ChatMessage):
    return {"id": m.id, "role": m.role, "content": m.content,
            "created_at": m.created_at.isoformat() if m.created_at else None}


@router.get("")
def history(profile_id: int, db: Session = Depends(get_db),
            user: str = Depends(current_user)):
    get_profile_or_404(db, profile_id, user)
    rows = db.scalars(select(ChatMessage).where(ChatMessage.profile_id == profile_id)
                      .order_by(ChatMessage.created_at, ChatMessage.id)).all()
    return [msg_dict(m) for m in rows]


@router.delete("")
def clear_history(profile_id: int, db: Session = Depends(get_db),
                  user: str = Depends(current_user)):
    get_profile_or_404(db, profile_id, user)
    db.execute(delete(ChatMessage).where(ChatMessage.profile_id == profile_id))
    db.commit()
    return {"cleared": True}


@router.post("")
def send(profile_id: int, body: ChatSend, db: Session = Depends(get_db),
         user: str = Depends(current_user)):
    profile = get_profile_or_404(db, profile_id, user)
    if not llm.available():
        raise HTTPException(503, "ANTHROPIC_API_KEY is not set — chat needs the LLM.")

    db.add(ChatMessage(profile_id=profile_id, role="user", content=body.message))
    db.commit()

    # last 20 persisted turns as conversation context, then the tool-use loop
    prior = db.scalars(select(ChatMessage).where(ChatMessage.profile_id == profile_id)
                       .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
                       .limit(20)).all()
    messages = [{"role": m.role, "content": m.content} for m in reversed(prior)]
    system = _system_prompt(db, profile)

    actions, reply_parts = [], []
    try:
        for _ in range(6):  # cap tool round-trips
            resp = llm.complete(messages, system=system, tools=TOOLS, max_tokens=1500)
            reply_parts.extend(b.text for b in resp.content if b.type == "text")
            tool_uses = [b for b in resp.content if b.type == "tool_use"]
            if resp.stop_reason != "tool_use" or not tool_uses:
                break
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for tu in tool_uses:
                result = _exec_tool(db, profile, tu.name, tu.input or {})
                actions.append({"tool": tu.name, "input": tu.input, "result": result})
                results.append({"type": "tool_result", "tool_use_id": tu.id, "content": result})
            messages.append({"role": "user", "content": results})
    except llm.LLMError as e:
        raise HTTPException(502, str(e))

    reply = "\n".join(p for p in reply_parts if p).strip() or "(no reply)"
    db.add(ChatMessage(profile_id=profile_id, role="assistant", content=reply))
    db.commit()
    return {"reply": reply, "actions": actions}
