from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentProfile
from app.db import get_session
from app.models import UserProfile
from app.schemas import ProfilePatch, ProfileRead

router = APIRouter(prefix="/profile", tags=["profile"])
Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("/me", response_model=ProfileRead)
async def get_my_profile(profile: CurrentProfile) -> UserProfile:
    return profile


@router.patch("/me", response_model=ProfileRead)
async def update_my_profile(payload: ProfilePatch, profile: CurrentProfile, session: Session) -> UserProfile:
    changes = payload.model_dump(exclude_unset=True)
    if "preferred_language" in changes and changes["preferred_language"] is None:
        raise HTTPException(status_code=422, detail="Preferred language cannot be null")
    for field, value in changes.items():
        setattr(profile, field, value)
    await session.commit()
    await session.refresh(profile)
    return profile
