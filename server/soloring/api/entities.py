"""Story World API (M6 §28).

Identity, immutable design revisions, and the explicit approved-revision
pointer. No story-state, realization, or continuity-anchor controls exist
here (M6 boundary).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.api.deps import get_session
from soloring.api.schemas.entities import (
    ApprovalPut,
    ApprovalRead,
    EntityCreate,
    EntityPatch,
    EntityRead,
    EntityRevisionDetail,
    EntityRevisionSummary,
    RevisionCreate,
)
from soloring.continuity import approvals as approval_svc
from soloring.continuity import entities as entity_svc
from soloring.continuity import revisions as revision_svc

router = APIRouter(tags=["entities"])


async def _entity_read(session: AsyncSession, entity_id: str) -> EntityRead:
    entity = await entity_svc.get_entity(session, entity_id)
    approved = await approval_svc.get_approved_revision_id(session, entity_id)
    return EntityRead(
        id=entity.id,
        project_id=entity.project_id,
        kind=entity.kind,
        name=entity.name,
        description=entity.description,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
        approved_revision_id=approved,
    )


@router.get(
    "/projects/{project_id}/entities", response_model=list[EntityRead]
)
async def list_entities(
    project_id: str,
    kind: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[EntityRead]:
    entities = await entity_svc.list_entities(session, project_id, kind=kind)
    results = []
    for entity in entities:
        approved = await approval_svc.get_approved_revision_id(session, entity.id)
        results.append(EntityRead(
            id=entity.id,
            project_id=entity.project_id,
            kind=entity.kind,
            name=entity.name,
            description=entity.description,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
            approved_revision_id=approved,
        ))
    return results


@router.post(
    "/projects/{project_id}/entities",
    response_model=EntityRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_entity(
    project_id: str,
    payload: EntityCreate,
    session: AsyncSession = Depends(get_session),
) -> EntityRead:
    entity = await entity_svc.create_entity(session, project_id, payload)
    approved = await approval_svc.get_approved_revision_id(session, entity.id)
    return EntityRead(
        id=entity.id,
        project_id=entity.project_id,
        kind=entity.kind,
        name=entity.name,
        description=entity.description,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
        approved_revision_id=approved,
    )


@router.get("/entities/{entity_id}", response_model=EntityRead)
async def get_entity(
    entity_id: str, session: AsyncSession = Depends(get_session)
) -> EntityRead:
    return await _entity_read(session, entity_id)


@router.patch("/entities/{entity_id}", response_model=EntityRead)
async def patch_entity(
    entity_id: str,
    payload: EntityPatch,
    session: AsyncSession = Depends(get_session),
) -> EntityRead:
    await entity_svc.patch_entity(session, entity_id, payload)
    return await _entity_read(session, entity_id)


@router.delete(
    "/entities/{entity_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_entity(
    entity_id: str, session: AsyncSession = Depends(get_session)
) -> None:
    await entity_svc.delete_entity(session, entity_id)


@router.get(
    "/entities/{entity_id}/revisions", response_model=list[EntityRevisionSummary]
)
async def list_revisions(
    entity_id: str, session: AsyncSession = Depends(get_session)
) -> list[EntityRevisionSummary]:
    return [
        EntityRevisionSummary(**r)
        for r in await revision_svc.list_revisions(session, entity_id)
    ]


@router.post(
    "/entities/{entity_id}/revisions",
    response_model=EntityRevisionSummary,
    status_code=status.HTTP_201_CREATED,
)
async def create_revision(
    entity_id: str,
    payload: RevisionCreate,
    session: AsyncSession = Depends(get_session),
) -> EntityRevisionSummary:
    result = await revision_svc.create_revision(
        session, entity_id, payload.spec
    )
    detail = await revision_svc.get_revision_detail(
        session, result.revision["id"]
    )
    return EntityRevisionSummary(
        id=detail["id"],
        entity_id=detail["entity_id"],
        revision_number=detail["revision_number"],
        schema_version=detail["schema_version"],
        spec_hash=detail["spec_hash"],
        created_at=detail["created_at"],
    )


@router.get("/entity-revisions/{revision_id}", response_model=EntityRevisionDetail)
async def get_revision(
    revision_id: str, session: AsyncSession = Depends(get_session)
) -> EntityRevisionDetail:
    return EntityRevisionDetail(
        **await revision_svc.get_revision_detail(session, revision_id)
    )


@router.put("/entities/{entity_id}/approved-revision", response_model=ApprovalRead)
async def put_approved_revision(
    entity_id: str,
    payload: ApprovalPut,
    session: AsyncSession = Depends(get_session),
) -> ApprovalRead:
    return ApprovalRead(**await approval_svc.approve_revision(
        session,
        entity_id,
        payload.revision_id,
        payload.expected_approved_revision_id,
    ))
