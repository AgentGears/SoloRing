"""Canon endpoints: takes review + approve/reject (v0.1 §92-§93, §99)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.api.deps import get_session
from soloring.api.schemas.generations import TakeRead
from soloring.assets.models import Asset, Blob
from soloring.db.models import Generation, Shot, Take
from soloring.domain import shots as shot_svc
from soloring.domain.ids import is_uuid
from soloring.domain.now import db_now
from soloring.errors import ErrorCode, not_found

router = APIRouter(tags=["takes"])


async def _take_or_404(session: AsyncSession, take_id: str) -> Take:
    if not is_uuid(take_id):
        raise not_found(ErrorCode.TAKE_NOT_FOUND, f"Take {take_id} not found.")
    take = await session.get(Take, take_id)
    if take is None:
        raise not_found(ErrorCode.TAKE_NOT_FOUND, f"Take {take_id} not found.")
    return take


async def list_takes_for_shot(session: AsyncSession, shot_id: str) -> list[dict]:
    await shot_svc.get_shot(session, shot_id)
    rows = (
        await session.execute(
            select(Take, Asset, Blob.detected_media_type, Generation.workflow_spec_json)
            .join(Asset, Asset.take_id == Take.id, isouter=True)
            .join(Blob, Asset.blob_hash == Blob.hash, isouter=True)
            .join(Generation, Take.generation_id == Generation.id, isouter=True)
            .where(Take.shot_id == shot_id)
            .order_by(Take.created_at, Take.id)
        )
    ).all()
    shot = await session.get(Shot, shot_id)
    out = []
    for take, asset, detected, spec_json in rows:
        h = asset.blob_hash if asset else None
        # Presentation-boundary signal (M5B-7): the CAPTURED logical output
        # kind for this exact output_key — immutable, provenance-backed, and
        # deliberately distinct from byte-level detected_media_type (which
        # stays honestly null for e.g. animated WebP). Never a detector lie.
        output_kind = None
        if spec_json:
            try:
                spec = json.loads(spec_json)
                name = take.output_key.rsplit(":", 1)[0]
                for o in spec.get("outputs", []):
                    if o.get("name") == name:
                        output_kind = o.get("kind")
                        break
            except ValueError:
                output_kind = None
        out.append(
            {
                "id": take.id,
                "shot_id": take.shot_id,
                "generation_id": take.generation_id,
                "output_key": take.output_key,
                "label": take.label,
                "rejected_at": take.rejected_at,
                "created_at": take.created_at,
                "is_approved": shot.approved_take_id == take.id,
                "asset_id": asset.id if asset else None,
                "blob_hash": h,
                "detected_media_type": detected,
                "output_kind": output_kind,
                "blob_url": f"/blobs/{h[:2]}/{h[2:4]}/{h}" if h else None,
            }
        )
    return out


@router.get("/shots/{shot_id}/takes", response_model=list[TakeRead])
async def list_takes(
    shot_id: str, session: AsyncSession = Depends(get_session)
) -> list[dict]:
    return await list_takes_for_shot(session, shot_id)


class ApproveResult(BaseModel):
    take_id: str
    shot_id: str
    approved: bool = True


@router.post("/takes/{take_id}/approve", response_model=ApproveResult)
async def approve_take(
    take_id: str, session: AsyncSession = Depends(get_session)
) -> ApproveResult:
    """Idempotent approval (v0.1 §92, amended in M3B): select canon, never
    rewrite creative state. Amendment: approving a REJECTED Take is a 409
    conflict (TAKE_REJECTED) rather than a silent un-reject — rejection and
    approval must not silently reverse each other. An explicit un-reject
    operation may be added later if the workflow needs it."""
    from soloring.errors import SoloRingError

    take = await _take_or_404(session, take_id)
    if take.rejected_at is not None:
        raise SoloRingError(
            ErrorCode.TAKE_REJECTED,
            "Take is rejected; approving a rejected Take requires an explicit "
            "un-reject operation.",
            status_code=409,
        )
    shot = await session.get(Shot, take.shot_id)
    now = await db_now(session)
    shot.approved_take_id = take.id
    shot.updated_at = now
    await session.commit()
    return ApproveResult(take_id=take.id, shot_id=shot.id)


class RejectResult(BaseModel):
    take_id: str
    shot_id: str
    approved_take_id: str | None


@router.post("/takes/{take_id}/reject", response_model=RejectResult)
async def reject_take(
    take_id: str, session: AsyncSession = Depends(get_session)
) -> RejectResult:
    """Idempotent rejection (v0.1 §93): if this take is canon, clear canon
    atomically; set rejected_at. No auto-promotion."""
    take = await _take_or_404(session, take_id)
    shot = await session.get(Shot, take.shot_id)
    now = await db_now(session)
    if shot.approved_take_id == take.id:
        shot.approved_take_id = None
    shot.updated_at = now
    take.rejected_at = now
    await session.commit()
    return RejectResult(
        take_id=take.id, shot_id=shot.id, approved_take_id=shot.approved_take_id
    )
