"""M10B world-authority API routes (frozen r3 §74)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from soloring.api.deps import get_session
from soloring.errors import ErrorCode, SoloRingError
from soloring.spatial import revisions as rev_svc
from soloring.spatial import worlds as svc

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["spatial"])


class WorldCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    name: str
    description: str | None = None
    requirement: str
    location_entity_id: str


class WorldPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    description: str | None = None
    requirement: str | None = None


class StateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    location_entity_revision_id: str


class FrameCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    name: str
    parent_spatial_frame_id: str | None = None
    bound_entity_id: str | None = None


class StateFramePut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    translation_mm: list[int]
    rotation_udeg: list[int]
    half_extents_mm: list[int] | None = None
    bound_entity_revision_id: str | None = None


class AxisCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    name: str


class StateAxisPut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    a_frame_id: str
    b_frame_id: str


class ApprovalPut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision_id: str
    expected_approved_revision_id: str | None = None


class UnapprovalDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_approved_revision_id: str | None = None


@router.post("/projects/{project_id}/spatial-worlds", status_code=201)
async def create_world(project_id: str, body: WorldCreate,
                       session: AsyncSession = Depends(get_session)):
    return await svc.create_world(
        session, project_id, key=body.key, name=body.name,
        description=body.description, requirement=body.requirement,
        location_entity_id=body.location_entity_id)


@router.patch("/spatial-worlds/{world_id}", status_code=204)
async def patch_world(world_id: str, body: WorldPatch,
                      session: AsyncSession = Depends(get_session)):
    await svc.patch_world(
        session, world_id, name=body.name, description=body.description,
        requirement=body.requirement)
    return None


@router.delete("/spatial-worlds/{world_id}", status_code=204)
async def delete_world(world_id: str,
                       session: AsyncSession = Depends(get_session)):
    await svc.delete_world(session, world_id)
    return None


@router.post("/spatial-worlds/{world_id}/states", status_code=201)
async def create_state(world_id: str, body: StateCreate,
                       session: AsyncSession = Depends(get_session)):
    return await svc.create_state(
        session, world_id,
        location_entity_revision_id=body.location_entity_revision_id)


@router.post("/spatial-worlds/{world_id}/frames", status_code=201)
async def create_frame(world_id: str, body: FrameCreate,
                       session: AsyncSession = Depends(get_session)):
    return await svc.create_frame(
        session, world_id, key=body.key, name=body.name,
        parent_spatial_frame_id=body.parent_spatial_frame_id,
        bound_entity_id=body.bound_entity_id)


@router.put("/spatial-world-states/{state_id}/frames/{frame_id}",
            status_code=204)
async def put_state_frame(state_id: str, frame_id: str, body: StateFramePut,
                          session: AsyncSession = Depends(get_session)):
    await svc.put_state_frame(
        session, state_id, frame_id, translation_mm=body.translation_mm,
        rotation_udeg=body.rotation_udeg,
        half_extents_mm=body.half_extents_mm,
        bound_entity_revision_id=body.bound_entity_revision_id)
    return None


@router.delete("/spatial-world-states/{state_id}/frames/{frame_id}",
               status_code=204)
async def delete_state_frame(state_id: str, frame_id: str,
                             session: AsyncSession = Depends(get_session)):
    await svc.delete_state_frame(session, state_id, frame_id)
    return None


@router.post("/spatial-worlds/{world_id}/axes", status_code=201)
async def create_axis(world_id: str, body: AxisCreate,
                      session: AsyncSession = Depends(get_session)):
    return await svc.create_axis(session, world_id, key=body.key,
                                 name=body.name)


@router.put("/spatial-world-states/{state_id}/axes/{axis_id}",
            status_code=204)
async def put_state_axis(state_id: str, axis_id: str, body: StateAxisPut,
                         session: AsyncSession = Depends(get_session)):
    await svc.put_state_axis(session, state_id, axis_id,
                             a_frame_id=body.a_frame_id,
                             b_frame_id=body.b_frame_id)
    return None


@router.delete("/spatial-world-states/{state_id}/axes/{axis_id}",
               status_code=204)
async def delete_state_axis(state_id: str, axis_id: str,
                            session: AsyncSession = Depends(get_session)):
    await svc.delete_state_axis(session, state_id, axis_id)
    return None


@router.post("/spatial-world-states/{state_id}/revisions", status_code=201)
async def capture_revision(state_id: str,
                           session: AsyncSession = Depends(get_session)):
    return await rev_svc.capture_revision(session, state_id)


@router.put("/spatial-world-states/{state_id}/approval")
async def approve(state_id: str, body: ApprovalPut,
                  session: AsyncSession = Depends(get_session)):
    return await rev_svc.approve_revision(
        session, state_id, revision_id=body.revision_id,
        expected_approved_revision_id=body.expected_approved_revision_id)


@router.delete("/spatial-world-states/{state_id}/approval")
async def unapprove(state_id: str, body: UnapprovalDelete,
                    session: AsyncSession = Depends(get_session)):
    return await rev_svc.unapprove(
        session, state_id,
        expected_approved_revision_id=body.expected_approved_revision_id)


@router.get("/spatial-worlds/{world_id}/workspace")
async def world_workspace(world_id: str,
                          session: AsyncSession = Depends(get_session)):
    """Server-owned workspace projection (§50): working state, immutable
    revision history, and approval pointers. UI never recomputes."""
    from sqlalchemy import text as _t
    world = (await session.execute(_t(
        "SELECT id, key, name, requirement, location_entity_id "
        "FROM spatial_worlds WHERE id = :w AND deleted_at IS NULL"),
        {"w": world_id})).mappings().one_or_none()
    if world is None:
        raise SoloRingError(ErrorCode.SPATIAL_WORLD_INVALID,
                            f"World {world_id} not found.", status_code=404)
    states = (await session.execute(_t(
        "SELECT id, location_entity_revision_id, approved_revision_id "
        "FROM spatial_world_states WHERE spatial_world_id = :w "
        "ORDER BY created_at"), {"w": world_id})).mappings().all()
    out_states = []
    for st in states:
        frames = (await session.execute(_t(
            "SELECT m.spatial_frame_id, f.key AS frame_key, "
            "m.bound_entity_id, m.x_mm, m.y_mm, m.z_mm, m.yaw_udeg, "
            "m.pitch_udeg, m.roll_udeg, m.half_x_mm, m.half_y_mm, "
            "m.half_z_mm FROM spatial_world_state_frames m "
            "JOIN spatial_frames f ON f.id = m.spatial_frame_id "
            "WHERE m.spatial_world_state_id = :s "
            "ORDER BY f.key, m.spatial_frame_id"),
            {"s": st["id"]})).mappings().all()
        axes = (await session.execute(_t(
            "SELECT sa.spatial_axis_id, a.key AS axis_key, sa.a_frame_id, "
            "sa.b_frame_id FROM spatial_world_state_axes sa "
            "JOIN spatial_axes a ON a.id = sa.spatial_axis_id "
            "WHERE sa.spatial_world_state_id = :s "
            "ORDER BY a.key, sa.spatial_axis_id"),
            {"s": st["id"]})).mappings().all()
        revisions = (await session.execute(_t(
            "SELECT id, revision_number, snapshot_hash, created_at "
            "FROM spatial_world_revisions WHERE spatial_world_state_id = :s "
            "ORDER BY revision_number DESC"),
            {"s": st["id"]})).mappings().all()
        out_states.append({
            "id": st["id"],
            "location_entity_revision_id":
                st["location_entity_revision_id"],
            "approved_revision_id": st["approved_revision_id"],
            "working_snapshot_hash": await _working_hash(session,
                                                        st["id"]),
            "frames": [dict(f) for f in frames],
            "axes": [dict(a) for a in axes],
            "revisions": [dict(r) for r in revisions],
        })
    # Stable world-level identities (ALL active frames/axes) so the
    # editor can select a newly created identity for its FIRST
    # membership/binding (M10B re-gate P0-4) — separate collections
    # from the per-state membership rows above.
    stable_frames = (await session.execute(_t(
        "SELECT id, key, name, parent_spatial_frame_id, bound_entity_id "
        "FROM spatial_frames WHERE spatial_world_id = :w AND deleted_at "
        "IS NULL ORDER BY key, id"), {"w": world_id})).mappings().all()
    stable_axes = (await session.execute(_t(
        "SELECT id, key, name FROM spatial_axes WHERE spatial_world_id = "
        ":w AND deleted_at IS NULL ORDER BY key, id"),
        {"w": world_id})).mappings().all()
    return {
        "world": dict(world),
        "stable_frames": [dict(f) for f in stable_frames],
        "stable_axes": [dict(a) for a in stable_axes],
        "states": out_states,
    }


async def _working_hash(session: AsyncSession,
                        state_id: str) -> str | None:
    """Server-computed canonical hash of the CURRENT working state (the
    §12 candidate), so the UI's working-vs-approved comparison is real.

    Fail-closed: only the legit 'state does not exist' case projects
    null. Invariant/corruption failures from the authority builder
    PROPAGATE (M10 error discipline — no except-Exception swallows)."""
    from soloring.domain.canonical import canonical_hash
    from soloring.errors import SoloRingError as _SoloRingError
    from soloring.spatial import revisions as _rev

    async with session.bind.connect() as conn:
        try:
            candidate = await _rev._load_candidate(conn, state_id)
        except _SoloRingError as exc:
            if "not found" in exc.message.lower():
                return None  # state absent: honest null
            raise  # invariant/corruption: propagate
    return canonical_hash(_rev._build_canonical(candidate))


class FramePatch(BaseModel):
    """Omitted fields are unchanged; explicit null clears the nullable
    identity fields (parent/bound)."""
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    parent_spatial_frame_id: str | None | None = None
    bound_entity_id: str | None | None = None


class AxisPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = None


@router.patch("/spatial-frames/{frame_id}", status_code=204)
async def patch_frame(frame_id: str, body: FramePatch,
                      session: AsyncSession = Depends(get_session)):
    await svc.patch_frame(
        session, frame_id, name=body.name,
        parent_spatial_frame_id=(
            svc.UNSET if "parent_spatial_frame_id" not in
            body.model_fields_set else body.parent_spatial_frame_id),
        bound_entity_id=(
            svc.UNSET if "bound_entity_id" not in
            body.model_fields_set else body.bound_entity_id))
    return None


@router.delete("/spatial-frames/{frame_id}", status_code=204)
async def delete_frame(frame_id: str,
                       session: AsyncSession = Depends(get_session)):
    await svc.delete_frame(session, frame_id)
    return None


@router.patch("/spatial-axes/{axis_id}", status_code=204)
async def patch_axis(axis_id: str, body: AxisPatch,
                     session: AsyncSession = Depends(get_session)):
    await svc.patch_axis(session, axis_id, name=body.name)
    return None


@router.delete("/spatial-axes/{axis_id}", status_code=204)
async def delete_axis(axis_id: str,
                      session: AsyncSession = Depends(get_session)):
    await svc.delete_axis(session, axis_id)
    return None
