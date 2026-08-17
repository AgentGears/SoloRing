"""Shot HTTP routes (plan §9, §15, §45, §94)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from soloring.api.deps import get_session
from soloring.api.schemas.shots import (
    SemanticDependencyItem,
    ShotCreate,
    ShotListItem,
    ShotPatch,
    ShotRead,
)
from soloring.continuity import dependencies as dependency_svc
from soloring.domain import shots

router = APIRouter(tags=["shots"])


async def _shot_read(request: Request, shot_id: str) -> ShotRead:
    """Serialize a Shot detail through the one-snapshot read unit (§94).

    M6C (§48/M6-F15): the working hash is the EFFECTIVE snapshot — intent +
    references + dependencies resolved against current approvals, all from
    the single consistent read. Display metadata (entity names) rides along
    but never participates in the hash.
    """
    engine: AsyncEngine = request.app.state.engine
    shot, refs, differs, resolved, effective_hash = (
        await shots.read_shot_detail(engine, shot_id)
    )
    return ShotRead(
        **dict(shot),
        working_snapshot_hash=effective_hash,
        working_state_differs_from_approved=differs,
        semantic_dependencies=[
            SemanticDependencyItem(
                entity_id=d.entity_id,
                entity_kind=d.entity_kind,
                role=d.role,
                position=d.position,
                resolved_revision_id=d.entity_revision_id,
                resolved_revision_number=d.entity_revision_number,
                resolved_revision_hash=d.entity_revision_hash,
            )
            for d in resolved
        ],
        continuity_ready=bool(resolved),
    )


@router.post(
    "/projects/{project_id}/shots",
    response_model=ShotRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_shot(
    project_id: str,
    payload: ShotCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ShotRead:
    shot = await shots.create_shot(session, project_id, payload)
    return await _shot_read(request, shot.id)


@router.get("/projects/{project_id}/shots", response_model=list[ShotListItem])
async def list_shots(
    project_id: str, session: AsyncSession = Depends(get_session)
) -> list[ShotListItem]:
    return await shots.list_shots(session, project_id)


@router.get("/shots/{shot_id}", response_model=ShotRead)
async def get_shot(shot_id: str, request: Request) -> ShotRead:
    return await _shot_read(request, shot_id)


@router.patch("/shots/{shot_id}", response_model=ShotRead)
async def patch_shot(
    shot_id: str,
    payload: ShotPatch,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ShotRead:
    await shots.patch_shot(session, shot_id, payload)
    return await _shot_read(request, shot_id)


@router.delete("/shots/{shot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shot(
    shot_id: str, session: AsyncSession = Depends(get_session)
) -> None:
    await shots.delete_shot(session, shot_id)
