"""Narrative ordering primitives (M6 §37–§38).

Narrative order is determined ONLY by the persisted position columns —
never by created_at/updated_at, row order, UUID, or shot_number (plan §37).

SQLite unique constraints are immediate, so a reorder never performs direct
position swaps: members are first moved into a non-conflicting temporary
range (current_max + member_count + 1, all nonnegative), then written to
their final 0..N-1 positions (plan §38). The primitive runs inside the
caller's BEGIN IMMEDIATE unit.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from soloring.errors import ErrorCode, SoloRingError


def order_invalid(message: str) -> SoloRingError:
    return SoloRingError(
        ErrorCode.NARRATIVE_ORDER_INVALID, message, status_code=422
    )


async def next_position(
    conn: AsyncConnection, table: str, scope_col: str, scope_id: str
) -> int:
    """Contiguous server-owned append position over ACTIVE rows only
    (M6B re-gate): tombstones keep their coordinates and never extend or
    occupy the active range."""
    return (
        await conn.execute(
            text(
                f"SELECT COALESCE(MAX(position), -1) + 1 FROM {table} "
                f"WHERE {scope_col} = :sid AND deleted_at IS NULL"
            ),
            {"sid": scope_id},
        )
    ).scalar()


async def compact_active(
    conn: AsyncConnection, table: str, scope_col: str, scope_id: str
) -> None:
    """Renumber ACTIVE members to exactly 0..N-1 after a soft deletion.

    Ascending-order renumbering only ever writes a position that is <= the
    row's current one and was just vacated by an earlier row (or its own),
    so no intermediate duplicate exists under the active-only partial
    unique index. Tombstones are never touched and keep their coordinates.
    """
    active_ids = (
        await conn.execute(
            text(
                f"SELECT id FROM {table} WHERE {scope_col} = :sid "
                f"AND deleted_at IS NULL ORDER BY position"
            ),
            {"sid": scope_id},
        )
    ).scalars().all()
    for index, member_id in enumerate(active_ids):
        await conn.execute(
            text(
                f"UPDATE {table} SET position = :pos WHERE id = :mid "
                f"AND deleted_at IS NULL"
            ),
            {"pos": index, "mid": member_id},
        )


async def reorder_full_set(
    conn: AsyncConnection,
    table: str,
    scope_col: str,
    scope_id: str,
    ordered_ids: list[str],
) -> None:
    """Atomically rewrite positions for the COMPLETE active member set.

    ``ordered_ids`` must be exactly the set of active members (each exactly
    once); anything else is NARRATIVE_ORDER_INVALID and the caller's
    transaction rolls back untouched. Tombstoned rows never participate:
    their coordinates are immutable history (M6B re-gate).
    """
    if len(set(ordered_ids)) != len(ordered_ids):
        raise order_invalid("Duplicate member ids in ordering request.")

    rows = (
        await conn.execute(
            text(
                f"SELECT id FROM {table} WHERE {scope_col} = :sid "
                f"AND deleted_at IS NULL",
            ),
            {"sid": scope_id},
        )
    ).scalars().all()
    current = set(rows)
    if current != set(ordered_ids):
        raise order_invalid(
            "Ordering request must contain exactly the complete set of "
            "active members, each exactly once."
        )
    if not ordered_ids:
        return

    current_max = (
        await conn.execute(
            text(
                f"SELECT COALESCE(MAX(position), -1) FROM {table} "
                f"WHERE {scope_col} = :sid AND deleted_at IS NULL"
            ),
            {"sid": scope_id},
        )
    ).scalar()
    offset = current_max + len(ordered_ids) + 1

    # Temporary range over ACTIVE rows only: distinct, nonnegative, and
    # strictly above every final position, so no intermediate state
    # violates the active-only UNIQUE(scope, position) index. Tombstones
    # are untouched.
    await conn.execute(
        text(
            f"UPDATE {table} SET position = position + :offset "
            f"WHERE {scope_col} = :sid AND deleted_at IS NULL"
        ),
        {"offset": offset, "sid": scope_id},
    )
    for index, member_id in enumerate(ordered_ids):
        await conn.execute(
            text(
                f"UPDATE {table} SET position = :pos "
                f"WHERE id = :mid AND {scope_col} = :sid "
                f"AND deleted_at IS NULL"
            ),
            {"pos": index, "mid": member_id, "sid": scope_id},
        )


async def list_ordered(
    conn: AsyncConnection,
    table: str,
    scope_col: str,
    scope_id: str,
    columns: str,
) -> list[dict]:
    rows = (
        await conn.execute(
            text(
                f"SELECT {columns} FROM {table} "
                f"WHERE {scope_col} = :sid AND deleted_at IS NULL "
                f"ORDER BY position"
            ),
            {"sid": scope_id},
        )
    ).mappings().all()
    return [dict(r) for r in rows]
