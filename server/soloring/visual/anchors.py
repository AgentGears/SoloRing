"""VisualAnchor detail: working state + revisions + approval (§§19–36).

M8A slice ships the detail read (working items + capturability hash
projection inputs). Revision capture/approval land with M8B; the imports
here stay seam-shaped so M8B extends rather than rewrites.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.errors import ErrorCode, SoloRingError


async def get_anchor_detail(session: AsyncSession, anchor_id: str) -> dict:
    """Anchor row + ordered working items (§33 fields land with M8B's
    canonical builder; the item list itself is M8A-visible)."""
    if not (await _active_anchor(session, anchor_id)):
        raise SoloRingError(
            ErrorCode.VISUAL_ANCHOR_NOT_FOUND,
            f"VisualAnchor {anchor_id} not found.",
            status_code=404,
        )
    async with session.bind.connect() as conn:
        items = (
            await conn.execute(
                text(
                    "SELECT asset_id, role, view_key, position "
                    "FROM visual_anchor_items "
                    "WHERE visual_anchor_id = :aid "
                    "ORDER BY position"
                ),
                {"aid": anchor_id},
            )
        ).mappings().all()
    return {
        "anchor_id": anchor_id,
        "items": [dict(r) for r in items],
    }


async def _active_anchor(session: AsyncSession, anchor_id: str) -> bool:
    async with session.bind.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT 1 FROM visual_anchors WHERE id = :aid "
                    "AND deleted_at IS NULL"
                ),
                {"aid": anchor_id},
            )
        ).first()
    return row is not None
