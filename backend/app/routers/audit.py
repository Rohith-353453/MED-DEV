from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentProfile
from app.db import get_session
from app.models import AuditLog
from app.schemas import PaginatedAuditLogs

router = APIRouter(prefix="/audit-logs", tags=["audit"])
Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=PaginatedAuditLogs)
async def list_audit_logs(
    profile: CurrentProfile,
    session: Session,
    document_id: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PaginatedAuditLogs:
    query = select(AuditLog).where(AuditLog.actor_profile_id == profile.id)
    if document_id:
        query = query.where(AuditLog.document_id == document_id)
    total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = await session.scalars(query.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset))
    return PaginatedAuditLogs(items=list(items), total=total, limit=limit, offset=offset)
