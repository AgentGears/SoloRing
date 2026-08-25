"""M10D-1 ShotSpatialPlan API transport (M10D plan §§6.1, 15, 78).

PUT/DELETE CAS routes with recursive strict request models — every
nested structure rejects undeclared fields (§8.1). The transport is
dumb: canonicalization, ownership, and CAS live in the service and the
ONE pure grammar in spatial/schemas.py.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from sqlalchemy import text

from soloring.api.deps import get_session
from soloring.errors import ErrorCode, SoloRingError
from soloring.spatial import plans as svc

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

router = APIRouter(tags=["spatial"])


class TransformInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    translation_mm: list[int]
    rotation_udeg: list[int]


class KeyframeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    time_ms: int
    transform: TransformInput


class CameraInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    projection: str
    focal_length_um: int
    sensor_width_um: int
    sensor_height_um: int
    keyframes: list[KeyframeInput]


class BlockingEntryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    spatial_track_id: str
    screen_direction: str
    keyframes: list[KeyframeInput]


class AxisConstraintInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    spatial_axis_id: str
    camera_side: str


class ShotSpatialPlanInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: int
    spatial_world_id: str
    camera: CameraInput
    blocking: list[BlockingEntryInput]
    axis_constraint: AxisConstraintInput | None


class SpatialPlanPut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_plan_hash: str | None = None
    plan: ShotSpatialPlanInput


class SpatialPlanDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_plan_hash: str | None = None


def _plan_raw(body: SpatialPlanPut) -> dict:
    return body.plan.model_dump()


@router.put("/shots/{shot_id}/spatial-plan")
async def put_spatial_plan(shot_id: str, body: SpatialPlanPut,
                           session: AsyncSession = Depends(get_session)):
    result = await svc.put_spatial_plan(
        session, shot_id, expected_plan_hash=body.expected_plan_hash,
        plan_raw=_plan_raw(body))
    return {"plan_hash": result["plan_hash"], "plan": result["plan"]}


@router.delete("/shots/{shot_id}/spatial-plan", status_code=204)
async def delete_spatial_plan(shot_id: str, body: SpatialPlanDelete,
                              session: AsyncSession = Depends(get_session)):
    await svc.delete_spatial_plan(
        session, shot_id, expected_plan_hash=body.expected_plan_hash)
    return None


@router.get("/shots/{shot_id}/spatial-plan")
async def get_spatial_plan(shot_id: str,
                           session: AsyncSession = Depends(get_session)):
    """Current stored plan projection (authoring/inspection only)."""
    current = await svc.get_current_plan(session, shot_id)
    if current is None:
        return {"plan_hash": None, "plan": None}
    import json as _json
    return {"plan_hash": current["plan_hash"],
            "plan": _json.loads(current["plan_json"])}


@router.get("/shots/{shot_id}/spatial-continuity")
async def shots_spatial_continuity(shot_id: str, request: Request):
    """The current complete spatial projection (M10D plan §37-38): ONE
    explicit coherent read owns Shot verification, M7 exact semantic
    resolution, the ONE resolver, and the response — never session
    splits. Strictly a CURRENT projection; never labeled captured."""
    from soloring.continuity.snapshots import resolve_working_dependencies
    from soloring.spatial import resolver as resolver_svc
    from soloring.visual.readiness import resolve_visual_readiness
    from soloring.continuity.state import (
        readiness_projection,
        resolve_effective_feature_state,
        resolve_effective_relation_state,
    )

    engine: AsyncEngine = request.app.state.engine
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN")
        try:
            shot = (await conn.execute(text(
                "SELECT id, deleted_at FROM shots WHERE id = :s"),
                {"s": shot_id})).first()
            if shot is None or shot[1] is not None:
                raise SoloRingError(ErrorCode.SHOT_NOT_FOUND,
                                    f"Shot {shot_id} not found.",
                                    status_code=404)
            resolved = await resolve_working_dependencies(conn, shot_id)
            f_out = await resolve_effective_feature_state(conn, shot_id)
            r_out = await resolve_effective_relation_state(conn, shot_id)
            readiness = readiness_projection(f_out, r_out)
            m7_ready = readiness["continuity_state_ready"]
            visual = None
            if m7_ready:
                visual = await resolve_visual_readiness(
                    conn, shot_id, m7_ready, readiness["readiness_issues"],
                    resolved, f_out.states,
                    blob_store=None)
                outcome = await resolver_svc.resolve_spatial_continuity(
                    conn, shot_id=shot_id, resolved_dependencies=resolved)
            else:
                outcome = None
            await conn.exec_driver_sql("COMMIT")
        except Exception:
            import contextlib
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            raise
    if outcome is None:
        return {
            "shot_id": shot_id,
            "m7_continuity_state_ready": m7_ready,
            "m7_readiness_issues": readiness["readiness_issues"],
            "ready": False, "spatial_continuity_hash": None, "issues": [],
            "spatial_continuity": None,
        }
    w = outcome.selected_world
    ver = outcome.approved_world_revision
    spatial = None
    if w is not None:
        spatial = {
            "selected_world": {
                "spatial_world_id": w["id"], "requirement": w["requirement"],
                "location_entity_id": w["location_entity_id"],
            },
            "location_entity_revision_id": (
                outcome.pack["spatial_world"]
                ["location_entity_revision_id"]
                if outcome.pack else None),
            "approved_world_revision": (
                {"id": ver["id"], "revision_number": ver["revision_number"],
                 "snapshot_hash": ver["snapshot_hash"]}
                if ver else None),
            "approved_frames": (
                outcome.pack["spatial_world"]["world_snapshot"]["frames"]
                if outcome.pack else []),
            "approved_axes": (
                outcome.pack["spatial_world"]["world_snapshot"]["axes"]
                if outcome.pack else []),
            "staging": [
                {"spatial_track_id": st.spatial_track_id,
                 "entity_id": st.entity_id,
                 "entity_revision_id": st.entity_revision_id,
                 "requirement": st.requirement,
                 "transform": {
                     "translation_mm": [st.x_mm, st.y_mm, st.z_mm],
                     "rotation_udeg": [st.yaw_udeg, st.pitch_udeg,
                                       st.roll_udeg]},
                 "source_transition": {
                     "id": st.source_transition_id,
                     "anchor_type": st.source_anchor_type,
                     "anchor_id": st.source_anchor_id,
                     "boundary": st.source_boundary}}
                for st in (outcome.staging.states if outcome.staging
                           else [])],
            "plan": outcome.plan, "plan_hash": outcome.plan_hash,
            "axis_status": outcome.axis_status,
            "screen_directions": [
                {"spatial_track_id": b["spatial_track_id"],
                 "screen_direction": b["screen_direction"]}
                for b in (outcome.plan["blocking"] if outcome.plan
                          else [])],
        }
    return {
        "shot_id": shot_id,
        "m7_continuity_state_ready": m7_ready,
        "m7_readiness_issues": readiness["readiness_issues"],
        "ready": outcome.ready,
        "spatial_continuity_hash": outcome.spatial_continuity_hash,
        "issues": [
            {"code": i.code, "layer": i.layer, "message": i.message,
             "details": dict(i.details)} for i in outcome.issues],
        "spatial_continuity": spatial,
    }
