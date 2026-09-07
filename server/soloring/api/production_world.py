"""M13 production-world HTTP routes (frozen R3 §24).

All request models are extra="forbid"; services own authority decisions.
This router hosts the M13 route family; path shapes match §24 exactly.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.api.deps import get_session
from soloring.api.schemas.production_world import (
    AuthoritySubjectAdopt,
    AuthoritySubjectRead,
    PIFeatureCreate,
    PIFeaturePatch,
    PIFeatureRead,
    PITrackCreate,
    PITrackRead,
    PITrackTransitionCreate,
    PITransitionCreate,
    SpatialInterpretationCreate,
    SpatialInterpretationRead,
)
from soloring.production_world import interpretation as interp
from soloring.production_world import instance_spatial
from soloring.production_world import instance_state
from soloring.production_world import subjects

router = APIRouter(tags=["production-world"])


@router.post(
    "/production-revisions/{revision_id}/spatial-interpretation",
    response_model=SpatialInterpretationRead,
)
async def create_spatial_interpretation(
    revision_id: str,
    body: SpatialInterpretationCreate,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> SpatialInterpretationRead:
    value, created = await interp.create_interpretation(
        session, revision_id,
        transform=body.realization_local_to_subject_local.model_dump(),
    )
    if created:
        response.status_code = status.HTTP_201_CREATED
    return SpatialInterpretationRead(**value)


@router.get(
    "/production-revisions/{revision_id}/spatial-interpretation",
    response_model=SpatialInterpretationRead,
)
async def get_spatial_interpretation(
    revision_id: str,
    session: AsyncSession = Depends(get_session),
) -> SpatialInterpretationRead:
    return SpatialInterpretationRead(
        **await interp.get_interpretation(session, revision_id))


@router.post(
    "/compositions/{composition_id}/occurrences/{occurrence_id}"
    "/authority-subject",
    response_model=AuthoritySubjectRead,
)
async def adopt_authority_subject(
    composition_id: str,
    occurrence_id: str,
    body: AuthoritySubjectAdopt,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> AuthoritySubjectRead:
    value, created = await subjects.adopt_subject(
        session, composition_id, occurrence_id,
        kind=body.kind, creative_entity_id=body.creative_entity_id,
    )
    if created:
        response.status_code = status.HTTP_201_CREATED
    return AuthoritySubjectRead(**value)


@router.get(
    "/compositions/{composition_id}/occurrences/{occurrence_id}"
    "/authority-subject",
    response_model=AuthoritySubjectRead,
)
async def get_authority_subject(
    composition_id: str,
    occurrence_id: str,
    session: AsyncSession = Depends(get_session),
) -> AuthoritySubjectRead:
    return AuthoritySubjectRead(
        **await subjects.get_subject(
            session, composition_id, occurrence_id))


# --- Production Instance Feature authoring (frozen §24.3) -------------------


@router.post(
    "/production-instances/{occurrence_id}/features",
    status_code=status.HTTP_201_CREATED,
)
async def create_pi_feature(
    occurrence_id: str,
    body: PIFeatureCreate,
    session: AsyncSession = Depends(get_session),
) -> dict:
    fid = await instance_state.create_feature_for_occurrence(
        session, occurrence_id, body)
    return {"id": fid}


@router.get(
    "/production-instances/{occurrence_id}/features",
    response_model=list[PIFeatureRead],
)
async def list_pi_features(
    occurrence_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[PIFeatureRead]:
    return [PIFeatureRead(**f)
            for f in await instance_state.list_features_for_occurrence(
                session, occurrence_id)]


@router.patch(
    "/production-instance-features/{feature_id}",
)
async def patch_pi_feature(
    feature_id: str,
    body: PIFeaturePatch,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await instance_state.patch_feature(session, feature_id, body)
    return {"ok": True}


@router.delete("/production-instance-features/{feature_id}")
async def delete_pi_feature(
    feature_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await instance_state.delete_feature(session, feature_id)
    return {"ok": True}


@router.get(
    "/production-instance-features/{feature_id}",
    response_model=PIFeatureRead,
)
async def get_pi_feature(
    feature_id: str,
    session: AsyncSession = Depends(get_session),
) -> PIFeatureRead:
    return PIFeatureRead(
        **await instance_state.get_feature(session, feature_id))


@router.post(
    "/production-instance-features/{feature_id}/transitions",
    status_code=status.HTTP_201_CREATED,
)
async def create_pi_feature_transition(
    feature_id: str,
    body: PITransitionCreate,
    session: AsyncSession = Depends(get_session),
) -> dict:
    tid = await instance_state.create_transition(session, feature_id, body)
    return {"id": tid}


@router.delete(
    "/production-instance-feature-transitions/{transition_id}")
async def delete_pi_feature_transition(
    transition_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await instance_state.delete_transition(session, transition_id)
    return {"ok": True}


# --- Production Instance spatial authoring (frozen §24.4) -------------------


@router.post(
    "/spatial-worlds/{world_id}/production-instance-tracks",
    status_code=status.HTTP_201_CREATED,
)
async def create_pi_track(
    world_id: str,
    body: PITrackCreate,
    session: AsyncSession = Depends(get_session),
) -> dict:
    tid = await instance_spatial.create_track(
        session, world_id, occurrence_id=body.occurrence_id,
        requirement=body.requirement)
    return {"id": tid}


@router.get(
    "/spatial-worlds/{world_id}/production-instance-tracks",
    response_model=list[PITrackRead],
)
async def list_pi_tracks(
    world_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[PITrackRead]:
    return [PITrackRead(**t) for t in await instance_spatial.list_tracks(
        session, world_id)]


@router.get(
    "/production-instance-spatial-tracks/{track_id}",
    response_model=PITrackRead,
)
async def get_pi_track(
    track_id: str,
    session: AsyncSession = Depends(get_session),
) -> PITrackRead:
    return PITrackRead(**await instance_spatial.get_track(
        session, track_id))


@router.delete("/production-instance-spatial-tracks/{track_id}")
async def delete_pi_track(
    track_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await instance_spatial.delete_track(session, track_id)
    return {"ok": True}


@router.post(
    "/production-instance-spatial-tracks/{track_id}/transitions",
    status_code=status.HTTP_201_CREATED,
)
async def create_pi_spatial_transition(
    track_id: str,
    body: PITrackTransitionCreate,
    session: AsyncSession = Depends(get_session),
) -> dict:
    tid = await instance_spatial.create_spatial_transition(
        session, track_id, body)
    return {"id": tid}


@router.delete(
    "/production-instance-spatial-transitions/{transition_id}")
async def delete_pi_spatial_transition(
    transition_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await instance_spatial.delete_spatial_transition(
        session, transition_id)
    return {"ok": True}
