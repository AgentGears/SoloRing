"""M16-A authoritative intra-Shot event authoring routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.api.deps import get_session
from soloring.api.schemas.intra_shot import (
    IntraShotEventCreate,
    IntraShotEventPatch,
    IntraShotEventRead,
)
from soloring.continuity import intra_shot_service

router = APIRouter(tags=["intra-shot"])


@router.post(
    "/shots/{shot_id}/intra-shot/events",
    response_model=IntraShotEventRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_intra_shot_event(
    shot_id: str,
    payload: IntraShotEventCreate,
    session: AsyncSession = Depends(get_session),
) -> IntraShotEventRead:
    return IntraShotEventRead(**await intra_shot_service.create_event(
        session, shot_id, payload))


@router.patch(
    "/intra-shot/events/{event_id}",
    response_model=IntraShotEventRead,
)
async def patch_intra_shot_event(
    event_id: str,
    payload: IntraShotEventPatch,
    session: AsyncSession = Depends(get_session),
) -> IntraShotEventRead:
    return IntraShotEventRead(**await intra_shot_service.patch_event(
        session, event_id, payload))


@router.delete(
    "/intra-shot/events/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_intra_shot_event(
    event_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    await intra_shot_service.delete_event(session, event_id)
