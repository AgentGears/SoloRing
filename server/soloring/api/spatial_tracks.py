"""M10C-1 SpatialTrack API routes (M10C plan §§6.1, 11).

Transport-only: every request model is extra=forbid; every authority
decision belongs to the service. Transition routes (M10C-2) join this
router in spatial_transitions API work below the same tag.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from soloring.api.deps import get_session
from soloring.spatial import tracks as svc

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["spatial"])


class TrackCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_id: str
    requirement: str


class TrackPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirement: str


@router.post("/spatial-worlds/{world_id}/tracks", status_code=201)
async def create_track(world_id: str, body: TrackCreate,
                       session: AsyncSession = Depends(get_session)):
    return await svc.create_track(
        session, world_id, entity_id=body.entity_id,
        requirement=body.requirement)


@router.patch("/spatial-tracks/{track_id}", status_code=204)
async def patch_track(track_id: str, body: TrackPatch,
                      session: AsyncSession = Depends(get_session)):
    await svc.patch_track(session, track_id, requirement=body.requirement)
    return None


@router.delete("/spatial-tracks/{track_id}", status_code=204)
async def delete_track(track_id: str,
                       session: AsyncSession = Depends(get_session)):
    await svc.delete_track(session, track_id)
    return None
