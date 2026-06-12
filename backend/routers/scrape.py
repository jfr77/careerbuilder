from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ScrapeRun
from ..schemas import WatchlistAdd
from ..scrapers import runner, watchlist

router = APIRouter(prefix="/api/scrape", tags=["scrape"])


@router.post("/run", status_code=202)
def run_scrapers():
    """Start an async scrape of all watchlisted companies (both sources).
    The frontend polls /status for progress."""
    if not runner.start_run():
        raise HTTPException(409, "a scrape run is already in progress")
    return {"started": True}


@router.get("/status")
def scrape_status():
    return runner.get_state()


@router.get("/runs")
def recent_runs(limit: int = 50, db: Session = Depends(get_db)):
    """Most recent scrape_runs log rows (one per company per run)."""
    rows = db.scalars(
        select(ScrapeRun).order_by(ScrapeRun.started_at.desc()).limit(min(limit, 200))
    ).all()
    return [{
        "id": r.id, "source": r.source, "company": r.company, "found": r.found,
        "new": r.new, "errors": r.errors, "duration_ms": r.duration_ms,
        "started_at": r.started_at.isoformat() if r.started_at else None,
    } for r in rows]


@router.get("/watchlist")
def get_watchlists():
    return {src: watchlist.load(src) for src in watchlist.DEFAULTS}


@router.post("/watchlist/{source}")
def add_slug(source: str, body: WatchlistAdd):
    try:
        return {"slugs": watchlist.add(source, body.slug)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/watchlist/{source}/{slug}")
def remove_slug(source: str, slug: str):
    try:
        return {"slugs": watchlist.remove(source, slug)}
    except ValueError as e:
        raise HTTPException(400, str(e))
