"""M10D-1 ShotSpatialPlan API transport (M10D plan §§6.1, 15, 78).

PUT/DELETE CAS routes with recursive strict request models — every
nested structure rejects undeclared fields (§8.1). The transport is
dumb: canonicalization, ownership, and CAS live in the service and the
ONE pure grammar in spatial/schemas.py.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from soloring.api.deps import get_session
from soloring.spatial import plans as svc

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

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
