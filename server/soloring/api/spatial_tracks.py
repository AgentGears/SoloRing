"""M10C-1/2 SpatialTrack + SpatialTransition API routes (M10C plan §§6-7, 11).

Transport-only: every request model is extra=forbid; every authority
decision belongs to the services. PATCH transport distinguishes omitted
(preserve) from explicit values via model_fields_set.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from soloring.api.deps import get_session
from soloring.spatial import tracks as svc
from soloring.spatial import transitions as tsvc

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


class TransitionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    anchor_type: str
    anchor_id: str
    boundary: str
    operation: str
    translation_mm: list[int] | None = None
    rotation_udeg: list[int] | None = None


class TransitionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    anchor_type: str | None = None
    anchor_id: str | None = None
    boundary: str | None = None
    operation: str | None = None
    translation_mm: list[int] | None = None
    rotation_udeg: list[int] | None = None


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


@router.post("/spatial-tracks/{track_id}/transitions", status_code=201)
async def create_transition(track_id: str, body: TransitionCreate,
                            session: AsyncSession = Depends(get_session)):
    return await tsvc.create_transition(
        session, track_id, anchor_type=body.anchor_type,
        anchor_id=body.anchor_id, boundary=body.boundary,
        operation=body.operation, translation_mm=body.translation_mm,
        rotation_udeg=body.rotation_udeg)


@router.patch("/spatial-transitions/{transition_id}", status_code=204)
async def patch_transition(transition_id: str, body: TransitionPatch,
                           session: AsyncSession = Depends(get_session)):
    unset = tsvc.UNSET

    def _or_unset(field: str, value):
        return unset if field not in body.model_fields_set else value

    await tsvc.patch_transition(
        session, transition_id,
        anchor_type=_or_unset("anchor_type", body.anchor_type),
        anchor_id=_or_unset("anchor_id", body.anchor_id),
        boundary=_or_unset("boundary", body.boundary),
        operation=_or_unset("operation", body.operation),
        translation_mm=_or_unset("translation_mm", body.translation_mm),
        rotation_udeg=_or_unset("rotation_udeg", body.rotation_udeg))
    return None


@router.delete("/spatial-transitions/{transition_id}", status_code=204)
async def delete_transition(transition_id: str,
                            session: AsyncSession = Depends(get_session)):
    await tsvc.delete_transition(session, transition_id)
    return None


@router.get("/spatial-worlds/{world_id}/staging")
async def staging_preview(world_id: str, shot_id: str,
                          session: AsyncSession = Depends(get_session)):
    """Current effective staging for this world at the target Shot —
    strictly an authoring/inspection projection (M10C plan §10.4/§10.5);
    NOT the final M10 spatial-continuity contract."""
    from soloring.spatial import staging as staging_svc
    return await staging_svc.preview_staging(
        session, spatial_world_id=world_id, shot_id=shot_id)
