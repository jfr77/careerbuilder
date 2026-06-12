from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Job
from ..schemas import ScrapeSettingsBody, WatchlistAdd
from ..scrapers import runner, watchlist
from ..scrapers import settings as scrape_settings

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


@router.get("/settings")
def get_settings():
    """User-defined scrape constraints. Empty lists = no restrictions."""
    return scrape_settings.load()


@router.put("/settings")
def update_settings(body: ScrapeSettingsBody, db: Session = Depends(get_db)):
    """Save the constraints and re-apply them to every job already in the pool,
    so tightening or loosening keywords immediately reshapes the Discover list."""
    cfg = scrape_settings.save(body.include_keywords, body.exclude_keywords)
    reclassified = 0
    for job in db.scalars(select(Job)).all():
        rel = runner.is_relevant(job.title, cfg)
        if job.relevant != rel:
            job.relevant = rel
            reclassified += 1
    db.commit()
    return {**cfg, "reclassified": reclassified}


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
