"""ReferenceService (plan §11).

PUT /shots/{id}/references validates the entire proposed set first, then
atomically deletes the existing set and inserts the new one with server-assigned
contiguous per-role positions. Roles are exact/case-sensitive. The shot's
updated_at advances because reference changes mutate working state.
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.api.schemas.references import ReferenceInput
from soloring.db.models import Asset, Shot, ShotReference
from soloring.domain.ids import is_uuid
from soloring.domain.now import db_now
from soloring.domain.normalize import is_valid_role
from soloring.errors import ErrorCode, SoloRingError, not_found


def _invalid(message: str) -> SoloRingError:
    return SoloRingError(ErrorCode.REFERENCE_SET_INVALID, message, status_code=400)


async def _load_active_shot(session: AsyncSession, shot_id: str) -> Shot:
    if not is_uuid(shot_id):
        raise not_found(ErrorCode.SHOT_NOT_FOUND, f"Shot {shot_id} not found.")
    shot = await session.get(Shot, shot_id)
    if shot is None or shot.deleted_at is not None:
        raise not_found(ErrorCode.SHOT_NOT_FOUND, f"Shot {shot_id} not found.")
    return shot


async def replace_references(
    session: AsyncSession, shot_id: str, items: list[ReferenceInput]
) -> list[ShotReference]:
    shot = await _load_active_shot(session, shot_id)

    # 1. Validate the entire proposed set BEFORE any mutation (plan §11.3/§11.4).
    seen: set[tuple[str, str]] = set()
    asset_ids: set[str] = set()
    for it in items:
        if not is_uuid(it.asset_id):
            raise _invalid(f"Reference asset_id {it.asset_id!r} is not a valid UUID.")
        if not is_valid_role(it.role):
            raise _invalid(f"Reference role {it.role!r} is invalid.")
        key = (it.asset_id, it.role)
        if key in seen:
            raise _invalid(f"Duplicate (asset_id, role): {it.asset_id} / {it.role}.")
        seen.add(key)
        asset_ids.add(it.asset_id)

    # 2. Verify assets exist and belong to the same Project.
    if asset_ids:
        rows = (
            await session.execute(
                select(Asset.id, Asset.project_id).where(Asset.id.in_(asset_ids))
            )
        ).all()
        owner = {r.id: r.project_id for r in rows}
        for aid in asset_ids:
            if aid not in owner:
                raise _invalid(f"Asset {aid} does not exist.")
            if owner[aid] != shot.project_id:
                raise _invalid(f"Asset {aid} belongs to a different Project.")

    # 3. Server-owned contiguous per-role positions (request order preserved).
    counters: dict[str, int] = {}
    new_rows: list[ShotReference] = []
    for it in items:
        pos = counters.get(it.role, 0)
        counters[it.role] = pos + 1
        new_rows.append(
            ShotReference(
                shot_id=shot_id, asset_id=it.asset_id, role=it.role, position=pos
            )
        )

    # 4. Atomic replace (plan §11.3).
    await session.execute(
        delete(ShotReference).where(ShotReference.shot_id == shot_id)
    )
    session.add_all(new_rows)
    shot.updated_at = await db_now(session)
    await session.commit()
    for r in new_rows:
        await session.refresh(r)

    new_rows.sort(key=lambda r: (r.role, r.position))
    return new_rows


async def list_references(session: AsyncSession, shot_id: str) -> list[ShotReference]:
    """The persisted reference set in full canonical order (M2C).

    (role, position, asset_id) — the same deterministic ordering definition
    used for creative identity, so the read stays deterministic even if
    externally corrupted data ever contained duplicate positions.
    """
    await _load_active_shot(session, shot_id)
    res = await session.execute(
        select(ShotReference)
        .where(ShotReference.shot_id == shot_id)
        .order_by(
            ShotReference.role,
            ShotReference.position,
            ShotReference.asset_id,
        )
    )
    return list(res.scalars().all())
