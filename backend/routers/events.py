"""Events & certifications.

Architecture note: this module is designed to be fed by future event scrapers
(Meetup / Eventbrite / university feeds). A scraper only needs to call
ingest_event() per item with source='scraper' — the events table is shared
across profiles, while save/dismiss state lives per profile in event_saves.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import llm
from ..auth import current_user
from ..context import profile_block
from ..db import get_db
from ..models import Event, EventSave
from ..schemas import EventSaveBody
from .profiles import get_profile_or_404

router = APIRouter(prefix="/api/events", tags=["events"],
                   dependencies=[Depends(current_user)])

KINDS = {"event", "career_fair", "certification", "course"}


def ingest_event(db: Session, *, title, kind, provider=None, location=None,
                 date=None, url=None, cost=None, source="manual") -> Event:
    """Single write path into the events pool — used by the LLM recommender
    today and by event scrapers later. Dedupes on (title, provider)."""
    existing = db.scalar(select(Event).where(Event.title == title, Event.provider == provider))
    if existing:
        return existing
    ev = Event(title=title, kind=kind if kind in KINDS else "event", provider=provider,
               location=location, date=date, url=url, cost=cost, source=source)
    db.add(ev)
    db.flush()
    return ev


def event_dict(e: Event, save: EventSave | None = None):
    return {
        "id": e.id, "title": e.title, "kind": e.kind, "provider": e.provider,
        "location": e.location, "date": e.date, "url": e.url, "cost": e.cost,
        "source": e.source,
        "saved": save.saved if save else None,
        "relevance_note": save.relevance_note if save else None,
    }


@router.get("")
def list_events(profile_id: int, db: Session = Depends(get_db),
                user: str = Depends(current_user)):
    get_profile_or_404(db, profile_id, user)
    rows = db.execute(
        select(Event, EventSave)
        .outerjoin(EventSave, (EventSave.event_id == Event.id) & (EventSave.profile_id == profile_id))
        .order_by(Event.id)
    ).all()
    # LLM-suggested events are personal: only show them to the profile they
    # were generated for (i.e. where a save row exists). Seeds are global.
    return [event_dict(e, s) for e, s in rows if e.source != "llm" or s is not None]


@router.post("/{event_id}/save")
def set_saved(event_id: int, profile_id: int, body: EventSaveBody,
              db: Session = Depends(get_db), user: str = Depends(current_user)):
    get_profile_or_404(db, profile_id, user)
    if not db.get(Event, event_id):
        raise HTTPException(404, "event not found")
    save = db.scalar(select(EventSave).where(
        EventSave.event_id == event_id, EventSave.profile_id == profile_id))
    if save:
        save.saved = body.saved
    else:
        save = EventSave(event_id=event_id, profile_id=profile_id, saved=body.saved)
        db.add(save)
    db.commit()
    return {"event_id": event_id, "saved": save.saved}


@router.post("/recommend")
def recommend(profile_id: int, db: Session = Depends(get_db),
              user: str = Depends(current_user)):
    """LLM-generated suggestions tailored to the active profile. Stored with
    source='llm' and a per-profile relevance note; the UI labels them as AI
    suggestions to verify."""
    profile = get_profile_or_404(db, profile_id, user)
    prompt = (
        "Suggest 5-8 career events, career fairs, certifications, or courses for "
        "this candidate (based in DACH region, internship/early-career stage):\n\n"
        + profile_block(profile) +
        "\n\nFavor real, well-known items relevant to their target industries, "
        "learning goals, and target companies. Respond ONLY with a JSON array of "
        "objects: {\"title\": str, \"kind\": one of [\"event\",\"career_fair\","
        "\"certification\",\"course\"], \"provider\": str, \"location\": str, "
        "\"date\": str (approximate is fine), \"url\": str or null, "
        "\"cost\": str or null, \"rationale\": \"<one sentence: why this fits "
        "this candidate>\"}"
    )
    try:
        items = llm.complete_json(prompt, max_tokens=2000)
    except llm.LLMUnavailable as e:
        raise HTTPException(503, str(e))
    except llm.LLMError as e:
        raise HTTPException(502, str(e))
    if not isinstance(items, list):
        raise HTTPException(502, "LLM returned an unexpected shape")

    out = []
    for item in items[:8]:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        ev = ingest_event(
            db, title=str(item["title"]), kind=item.get("kind", "event"),
            provider=item.get("provider"), location=item.get("location"),
            date=item.get("date"), url=item.get("url"), cost=item.get("cost"),
            source="llm",
        )
        save = db.scalar(select(EventSave).where(
            EventSave.event_id == ev.id, EventSave.profile_id == profile_id))
        if not save:
            save = EventSave(event_id=ev.id, profile_id=profile_id, saved=False,
                             relevance_note=item.get("rationale"))
            db.add(save)
            db.flush()
        out.append(event_dict(ev, save))
    db.commit()
    return out
