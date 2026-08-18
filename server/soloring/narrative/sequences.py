"""Sequence service (M6 §32, §40–§41).

Every mutation is ONE fenced BEGIN IMMEDIATE unit (the M6A gate lesson):
the active-parent/active-member verification is atomic with the write, via
module-level seams (``_verify_active_project`` re-used from the continuity
package, ``_verify_active_sequence`` here) so race regressions can force
interleavings deterministically. Positions are server-owned, zero-based,
contiguous; narrative order never consults timestamps (plan §37).
"""

from __future__ import annotations

import contextlib

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from soloring.continuity.entities import (
    _translate_op_error,
    _verify_active_project,
)
from soloring.domain.ids import is_uuid, new_uuid
from soloring.domain.normalize import normalize_optional_creative
from soloring.errors import ErrorCode, SoloRingError, not_found
from soloring.narrative.ordering import (
    compact_active,
    next_position,
    reorder_full_set,
)

_COLUMNS = "id, project_id, title, position, created_at, updated_at"


def sequence_not_found(sequence_id: str) -> SoloRingError:
    return not_found(
        ErrorCode.SEQUENCE_NOT_FOUND, f"Sequence {sequence_id} not found."
    )


async def _verify_active_sequence(conn: AsyncConnection, sequence_id: str) -> dict:
    """Active-sequence check INSIDE a held BEGIN IMMEDIATE unit.

    Module-level seam for deterministic race testing (the
    ``_verify_active_project`` precedent). Returns the row for caller use.
    """
    row = (
        await conn.execute(
            text(
                "SELECT id, project_id, title FROM sequences "
                "WHERE id = :sid AND deleted_at IS NULL"
            ),
            {"sid": sequence_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise sequence_not_found(sequence_id)
    return dict(row)


async def create_sequence(
    session: AsyncSession, project_id: str, title: str | None
) -> str:
    if not is_uuid(project_id):
        raise not_found(
            ErrorCode.PROJECT_NOT_FOUND, f"Project {project_id} not found."
        )
    normalized_title = normalize_optional_creative(title)
    sequence_id = new_uuid()
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await _verify_active_project(conn, project_id)
            position = await next_position(conn, "sequences", "project_id", project_id)
            await conn.execute(
                text(
                    "INSERT INTO sequences (id, project_id, title, position, "
                    "created_at, updated_at) VALUES (:id, :pid, :title, :pos, "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now'), "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
                ),
                {"id": sequence_id, "pid": project_id,
                 "title": normalized_title, "pos": position},
            )
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _translate_op_error(exc, "sequence creation") from exc
    return sequence_id


async def list_sequences(session: AsyncSession, project_id: str) -> list[dict]:
    from soloring.narrative.ordering import list_ordered

    if not is_uuid(project_id):
        raise not_found(
            ErrorCode.PROJECT_NOT_FOUND, f"Project {project_id} not found."
        )
    async with session.bind.connect() as conn:
        # A soft-deleted Project is absent for normal reads (hierarchy
        # contract; the M6B re-gate correction).
        await _verify_active_project(conn, project_id)
        return await list_ordered(
            conn, "sequences", "project_id", project_id, _COLUMNS
        )


async def get_sequence(session: AsyncSession, sequence_id: str) -> dict:
    if not is_uuid(sequence_id):
        raise sequence_not_found(sequence_id)
    async with session.bind.connect() as conn:
        row = (
            await conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM sequences "
                    "WHERE id = :sid AND deleted_at IS NULL"
                ),
                {"sid": sequence_id},
            )
        ).mappings().one_or_none()
    if row is None:
        raise sequence_not_found(sequence_id)
    return dict(row)


async def patch_sequence(
    session: AsyncSession, sequence_id: str, patch
) -> None:
    """Partial PATCH (M6B re-gate): omitted fields are preserved; an
    explicit null clears the nullable title; ``{}`` mutates nothing."""
    if not is_uuid(sequence_id):
        raise sequence_not_found(sequence_id)
    provided = patch.model_fields_set
    if "title" not in provided:
        await get_sequence(session, sequence_id)  # active check only
        return
    normalized = normalize_optional_creative(patch.title)
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await _verify_active_sequence(conn, sequence_id)
            rowcount = (
                await conn.execute(
                    text(
                        "UPDATE sequences SET title = :title, updated_at = "
                        "strftime('%Y-%m-%dT%H:%M:%fZ','now') "
                        "WHERE id = :sid AND deleted_at IS NULL"
                    ),
                    {"title": normalized, "sid": sequence_id},
                )
            ).rowcount
            if rowcount != 1:
                await conn.exec_driver_sql("ROLLBACK")
                raise sequence_not_found(sequence_id)
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _translate_op_error(exc, "sequence patch") from exc


async def delete_sequence(session: AsyncSession, sequence_id: str) -> None:
    """Soft-delete; SEQUENCE_IN_USE while any active Scene remains (§41).

    Idempotent for already-deleted Sequences (Project/Shot/Entity policy).
    """
    if not is_uuid(sequence_id):
        raise sequence_not_found(sequence_id)
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            row = (
                await conn.execute(
                    text(
                        "SELECT project_id, deleted_at FROM sequences "
                        "WHERE id = :sid"
                    ),
                    {"sid": sequence_id},
                )
            ).first()
            if row is None:
                await conn.exec_driver_sql("ROLLBACK")
                raise sequence_not_found(sequence_id)
            if row.deleted_at is not None:
                await conn.exec_driver_sql("COMMIT")  # idempotent no-op
                return
            has_scenes = (
                await conn.execute(
                    text(
                        "SELECT 1 FROM scenes WHERE sequence_id = :sid "
                        "AND deleted_at IS NULL LIMIT 1"
                    ),
                    {"sid": sequence_id},
                )
            ).first()
            if has_scenes is not None:
                await conn.exec_driver_sql("ROLLBACK")
                raise SoloRingError(
                    ErrorCode.SEQUENCE_IN_USE,
                    f"Sequence {sequence_id} still contains active Scenes.",
                    status_code=409,
                )
            # M7B §11: an active transition anchored directly to this
            # Sequence must not be left dangling.
            anchored = (
                await conn.execute(
                    text(
                        "SELECT 1 FROM continuity_feature_transitions "
                        "WHERE anchor_type = 'sequence' AND anchor_id = :sid "
                        "AND deleted_at IS NULL LIMIT 1"
                    ),
                    {"sid": sequence_id},
                )
            ).first()
            if anchored is not None:
                await conn.exec_driver_sql("ROLLBACK")
                raise SoloRingError(
                    ErrorCode.CONTINUITY_ANCHOR_IN_USE,
                    f"Sequence {sequence_id} anchors an active Feature "
                    "transition.",
                    status_code=409,
                )
            await conn.execute(
                text(
                    "UPDATE sequences SET deleted_at = "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now'), updated_at = "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :sid"
                ),
                {"sid": sequence_id},
            )
            # Active siblings compact to 0..N-1; the tombstone keeps its
            # coordinates forever (M6B re-gate).
            await compact_active(conn, "sequences", "project_id", row.project_id)
            await conn.exec_driver_sql("COMMIT")
        except SoloRingError:
            raise
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            raise _translate_op_error(exc, "sequence deletion") from exc


async def reorder_sequences(
    session: AsyncSession, project_id: str, ordered_ids: list[str]
) -> None:
    if not is_uuid(project_id):
        raise not_found(
            ErrorCode.PROJECT_NOT_FOUND, f"Project {project_id} not found."
        )
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await _verify_active_project(conn, project_id)
            await reorder_full_set(
                conn, "sequences", "project_id", project_id, ordered_ids
            )
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _translate_op_error(exc, "sequence reorder") from exc
