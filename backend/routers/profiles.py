from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user, owns
from ..context import profile_dict
from ..db import get_db
from ..models import Profile
from ..schemas import ProfileCreate, ProfileUpdate

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


def get_profile_or_404(db: Session, profile_id: int, owner_id: str) -> Profile:
    """Fetch a profile that belongs to `owner_id`, else 404.

    This is the single ownership chokepoint: every profile-derived endpoint
    (pipeline, chat, events, documents, scoring) routes through here, so a
    caller can only ever touch their own profiles. A profile owned by someone
    else returns 404 (not 403) so existence isn't leaked across accounts."""
    profile = db.get(Profile, profile_id)
    if not profile or not owns(profile.owner_id, owner_id):
        raise HTTPException(404, f"profile {profile_id} not found")
    return profile


@router.get("")
def list_profiles(db: Session = Depends(get_db), user: str = Depends(current_user)):
    rows = db.scalars(
        select(Profile).where(Profile.owner_id == user).order_by(Profile.id)
    ).all()
    return [profile_dict(p) for p in rows]


@router.post("", status_code=201)
def create_profile(body: ProfileCreate, db: Session = Depends(get_db),
                   user: str = Depends(current_user)):
    p = Profile(name=body.name, location=body.location, owner_id=user,
                skills=[], languages=[], target_industries=[], target_companies=[])
    db.add(p)
    db.commit()
    return profile_dict(p)


@router.get("/{profile_id}")
def get_profile(profile_id: int, db: Session = Depends(get_db),
                user: str = Depends(current_user)):
    return profile_dict(get_profile_or_404(db, profile_id, user))


@router.patch("/{profile_id}")
def update_profile(profile_id: int, body: ProfileUpdate, db: Session = Depends(get_db),
                   user: str = Depends(current_user)):
    p = get_profile_or_404(db, profile_id, user)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(p, field, value)
    db.commit()
    return profile_dict(p)


@router.delete("/{profile_id}")
def delete_profile(profile_id: int, db: Session = Depends(get_db),
                   user: str = Depends(current_user)):
    p = get_profile_or_404(db, profile_id, user)
    own_count = len(db.scalars(select(Profile.id).where(Profile.owner_id == user)).all())
    if own_count <= 1:
        raise HTTPException(400, "cannot delete the last remaining profile")
    # scores, pipeline, chat and event saves cascade via FK ON DELETE CASCADE
    db.delete(p)
    db.commit()
    return {"deleted": profile_id}
