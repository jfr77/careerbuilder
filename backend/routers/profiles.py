from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..context import profile_dict
from ..db import get_db
from ..models import Profile
from ..schemas import ProfileCreate, ProfileUpdate

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


def get_profile_or_404(db: Session, profile_id: int) -> Profile:
    profile = db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(404, f"profile {profile_id} not found")
    return profile


@router.get("")
def list_profiles(db: Session = Depends(get_db)):
    rows = db.scalars(select(Profile).order_by(Profile.id)).all()
    return [profile_dict(p) for p in rows]


@router.post("", status_code=201)
def create_profile(body: ProfileCreate, db: Session = Depends(get_db)):
    p = Profile(name=body.name, location=body.location,
                skills=[], languages=[], target_industries=[], target_companies=[])
    db.add(p)
    db.commit()
    return profile_dict(p)


@router.get("/{profile_id}")
def get_profile(profile_id: int, db: Session = Depends(get_db)):
    return profile_dict(get_profile_or_404(db, profile_id))


@router.patch("/{profile_id}")
def update_profile(profile_id: int, body: ProfileUpdate, db: Session = Depends(get_db)):
    p = get_profile_or_404(db, profile_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(p, field, value)
    db.commit()
    return profile_dict(p)


@router.delete("/{profile_id}")
def delete_profile(profile_id: int, db: Session = Depends(get_db)):
    p = get_profile_or_404(db, profile_id)
    if len(db.scalars(select(Profile.id)).all()) <= 1:
        raise HTTPException(400, "cannot delete the last remaining profile")
    # scores, pipeline, chat and event saves cascade via FK ON DELETE CASCADE
    db.delete(p)
    db.commit()
    return {"deleted": profile_id}
