"""Saved job filters: persist a filter dict from the Discover bar under a name
so it can be re-applied later. Scoped per authenticated user (owner_id)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user, owns
from ..db import get_db
from ..models import SavedFilter
from ..schemas import SavedFilterCreate
from .jobs import clean_filter

router = APIRouter(prefix="/api/filters", tags=["filters"],
                   dependencies=[Depends(current_user)])


def filter_dict(f: SavedFilter):
    return {"id": f.id, "name": f.name, "filter": f.filter_json or {},
            "created_at": f.created_at.isoformat() if f.created_at else None}


@router.get("")
def list_filters(db: Session = Depends(get_db), user: str = Depends(current_user)):
    rows = db.scalars(
        select(SavedFilter).where(SavedFilter.owner_id == user)
        .order_by(SavedFilter.created_at)
    ).all()
    return [filter_dict(f) for f in rows]


@router.post("", status_code=201)
def create_filter(body: SavedFilterCreate, db: Session = Depends(get_db),
                  user: str = Depends(current_user)):
    row = SavedFilter(name=body.name.strip(), filter_json=clean_filter(body.filter),
                      owner_id=user)
    db.add(row)
    db.commit()
    return filter_dict(row)


@router.delete("/{filter_id}")
def delete_filter(filter_id: int, db: Session = Depends(get_db),
                  user: str = Depends(current_user)):
    row = db.get(SavedFilter, filter_id)
    if not row or not owns(row.owner_id, user):
        raise HTTPException(404, f"saved filter {filter_id} not found")
    db.delete(row)
    db.commit()
    return {"deleted": filter_id}
