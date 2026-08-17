"""Narrative endpoints (M6B §40): Sequences, Scenes, Shot membership."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.api.deps import get_session
from soloring.api.schemas.narrative import (
    SceneCreate,
    SceneOrderPut,
    ScenePatch,
    SceneRead,
    SceneShotsPut,
    SequenceCreate,
    SequenceOrderPut,
    SequencePatch,
    SequenceRead,
)
from soloring.narrative import scenes as scene_svc
from soloring.narrative import sequences as sequence_svc

router = APIRouter(tags=["narrative"])


# --- Sequences ----------------------------------------------------------------


@router.get("/projects/{project_id}/sequences", response_model=list[SequenceRead])
async def list_sequences(
    project_id: str, session: AsyncSession = Depends(get_session)
) -> list[SequenceRead]:
    return [SequenceRead(**r) for r in await sequence_svc.list_sequences(
        session, project_id
    )]


@router.post(
    "/projects/{project_id}/sequences",
    response_model=SequenceRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_sequence(
    project_id: str,
    payload: SequenceCreate,
    session: AsyncSession = Depends(get_session),
) -> SequenceRead:
    sid = await sequence_svc.create_sequence(session, project_id, payload.title)
    return SequenceRead(**await sequence_svc.get_sequence(session, sid))


@router.put("/projects/{project_id}/sequences/order")
async def reorder_sequences(
    project_id: str,
    payload: SequenceOrderPut,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await sequence_svc.reorder_sequences(session, project_id, payload.sequence_ids)
    return {"ordered": len(payload.sequence_ids)}


@router.get("/sequences/{sequence_id}", response_model=SequenceRead)
async def get_sequence(
    sequence_id: str, session: AsyncSession = Depends(get_session)
) -> SequenceRead:
    return SequenceRead(**await sequence_svc.get_sequence(session, sequence_id))


@router.patch("/sequences/{sequence_id}", response_model=SequenceRead)
async def patch_sequence(
    sequence_id: str,
    payload: SequencePatch,
    session: AsyncSession = Depends(get_session),
) -> SequenceRead:
    await sequence_svc.patch_sequence(session, sequence_id, payload)
    return SequenceRead(**await sequence_svc.get_sequence(session, sequence_id))


@router.delete("/sequences/{sequence_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sequence(
    sequence_id: str, session: AsyncSession = Depends(get_session)
) -> None:
    await sequence_svc.delete_sequence(session, sequence_id)


# --- Scenes -------------------------------------------------------------------


@router.get("/sequences/{sequence_id}/scenes", response_model=list[SceneRead])
async def list_scenes(
    sequence_id: str, session: AsyncSession = Depends(get_session)
) -> list[SceneRead]:
    return [SceneRead(**r) for r in await scene_svc.list_scenes(
        session, sequence_id
    )]


@router.post(
    "/sequences/{sequence_id}/scenes",
    response_model=SceneRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_scene(
    sequence_id: str,
    payload: SceneCreate,
    session: AsyncSession = Depends(get_session),
) -> SceneRead:
    cid = await scene_svc.create_scene(
        session, sequence_id, payload.title, payload.description
    )
    return SceneRead(**await scene_svc.get_scene(session, cid))


@router.put("/sequences/{sequence_id}/scenes/order")
async def reorder_scenes(
    sequence_id: str,
    payload: SceneOrderPut,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await scene_svc.reorder_scenes(session, sequence_id, payload.scene_ids)
    return {"ordered": len(payload.scene_ids)}


@router.get("/scenes/{scene_id}", response_model=SceneRead)
async def get_scene(
    scene_id: str, session: AsyncSession = Depends(get_session)
) -> SceneRead:
    return SceneRead(**await scene_svc.get_scene(session, scene_id))


@router.patch("/scenes/{scene_id}", response_model=SceneRead)
async def patch_scene(
    scene_id: str,
    payload: ScenePatch,
    session: AsyncSession = Depends(get_session),
) -> SceneRead:
    await scene_svc.patch_scene(session, scene_id, payload)
    return SceneRead(**await scene_svc.get_scene(session, scene_id))


@router.delete("/scenes/{scene_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scene(
    scene_id: str, session: AsyncSession = Depends(get_session)
) -> None:
    await scene_svc.delete_scene(session, scene_id)


# --- Shot membership (§39) ------------------------------------------------------


@router.put("/scenes/{scene_id}/shots")
async def put_scene_shots(
    scene_id: str,
    payload: SceneShotsPut,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await scene_svc.assign_scene_shots(session, scene_id, payload.shot_ids)
    return {"assigned": len(payload.shot_ids)}
