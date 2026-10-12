from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentProfile
from app.db import get_session
from app.models import TimelineEvent
from app.schemas import PaginatedTimeline, TimelineEventPatch, TimelineEventRead

router = APIRouter(prefix="/timeline", tags=["timeline"])
Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=PaginatedTimeline)
async def list_timeline(
    profile: CurrentProfile,
    session: Session,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PaginatedTimeline:
    base = select(TimelineEvent).where(TimelineEvent.owner_id == profile.id)
    total = await session.scalar(select(func.count()).select_from(base.subquery())) or 0
    items = await session.scalars(
        base.order_by(TimelineEvent.event_date.desc().nullslast(), TimelineEvent.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return PaginatedTimeline(items=list(items), total=total, limit=limit, offset=offset)


@router.patch("/{event_id}", response_model=TimelineEventRead)
async def update_timeline_event(
    event_id: str, payload: TimelineEventPatch, profile: CurrentProfile, session: Session
) -> TimelineEvent:
    event = await session.scalar(
        select(TimelineEvent).where(TimelineEvent.id == event_id, TimelineEvent.owner_id == profile.id)
    )
    if event is None:
        raise HTTPException(status_code=404, detail="Timeline event not found")
    changes = payload.model_dump(exclude_unset=True)
    for field in ("event_type", "title"):
        if field in changes and changes[field] is None:
            raise HTTPException(status_code=422, detail=f"{field} cannot be null")
    for field, value in changes.items():
        setattr(event, field, value)
    event.is_user_edited = True
    await session.commit()
    await session.refresh(event)
    return event


@router.delete("/{event_id}", status_code=204)
async def delete_timeline_event(event_id: str, profile: CurrentProfile, session: Session) -> None:
    event = await session.scalar(
        select(TimelineEvent).where(TimelineEvent.id == event_id, TimelineEvent.owner_id == profile.id)
    )
    if event is None:
        raise HTTPException(status_code=404, detail="Timeline event not found")
    await session.delete(event)
    await session.commit()
