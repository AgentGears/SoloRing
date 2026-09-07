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
    SpatialInterpretationCreate,
    SpatialInterpretationRead,
)
from soloring.production_world import interpretation as interp
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
