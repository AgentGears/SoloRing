"""Revision HTTP routes (plan §16, §45)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.api.deps import get_session
from soloring.api.schemas.revisions import RevisionSummary
from soloring.domain import revisions

router = APIRouter(tags=["revisions"])


@router.get(
    "/shots/{shot_id}/revisions",
    response_model=list[RevisionSummary],
)
async def list_revisions(
    shot_id: str, session: AsyncSession = Depends(get_session)
) -> list[RevisionSummary]:
    return await revisions.list_revisions(session, shot_id)
