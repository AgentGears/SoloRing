"""Explicit approved-revision pointer with optimistic CAS (M6 §23–§25).

Approval is explicit and monotonic in availability (M6-F5): there is no
unapprove operation and no API to clear the pointer. Because a working
dependency can only be assigned to an entity WITH an approval (M6C §46),
and approvals never disappear, a legal dependency can never become
unresolvable — that invariant chain is why capture-time resolution is
total.

The compare-and-swap runs inside ONE BEGIN IMMEDIATE (plan §9, §25): the
expected-current comparison happens while holding the write lock, so two
editing surfaces cannot silently overwrite story-world canon — one wins,
the other receives 409 ENTITY_APPROVAL_CONFLICT, never a raw BUSY.
"""

from __future__ import annotations

import contextlib

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.continuity.entities import _entity_not_found
from soloring.domain.ids import is_uuid
from soloring.errors import ErrorCode, SoloRingError, validation_error
from soloring.generation.repository import busy_error, is_busy_error


def _revision_not_found(revision_id: str, entity_id: str) -> SoloRingError:
    return SoloRingError(
        ErrorCode.ENTITY_REVISION_NOT_FOUND,
        f"EntityRevision {revision_id} not found for entity {entity_id}.",
        status_code=404,
    )


def _conflict(entity_id: str, expected: str | None, actual: str | None) -> SoloRingError:
    return SoloRingError(
        ErrorCode.ENTITY_APPROVAL_CONFLICT,
        f"Approved revision for entity {entity_id} changed "
        f"(expected {expected!r}, currently {actual!r}).",
        status_code=409,
    )


async def get_approved_revision_id(
    session: AsyncSession, entity_id: str
) -> str | None:
    """The current approved revision id, or None (read-only helper)."""
    return (
        await session.execute(
            text(
                "SELECT revision_id FROM entity_approved_revisions "
                "WHERE entity_id = :eid"
            ),
            {"eid": entity_id},
        )
    ).scalar_one_or_none()


async def approve_revision(
    session: AsyncSession,
    entity_id: str,
    revision_id: str,
    expected_approved_revision_id: str | None,
) -> dict:
    """CAS the approved-revision pointer (plan §25).

    Returns the approval state after the operation. Approving the already-
    approved revision with the matching expectation is idempotent.
    """
    if not is_uuid(entity_id):
        raise _entity_not_found(entity_id)
    if not is_uuid(revision_id):
        raise _revision_not_found(revision_id, entity_id)
    if (
        expected_approved_revision_id is not None
        and not is_uuid(expected_approved_revision_id)
    ):
        # An empty string is NOT first-approval null (M6A re-gate): the
        # expectation is validated syntactically, never coerced.
        raise validation_error(
            "expected_approved_revision_id must be a UUID or null."
        )
    expected = expected_approved_revision_id

    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")

            entity = (
                await conn.execute(
                    text(
                        "SELECT id FROM creative_entities "
                        "WHERE id = :eid AND deleted_at IS NULL"
                    ),
                    {"eid": entity_id},
                )
            ).first()
            if entity is None:
                await conn.exec_driver_sql("ROLLBACK")
                raise _entity_not_found(entity_id)

            revision = (
                await conn.execute(
                    text(
                        "SELECT id, entity_id FROM entity_revisions "
                        "WHERE id = :rid"
                    ),
                    {"rid": revision_id},
                )
            ).first()
            if revision is None or revision.entity_id != entity_id:
                await conn.exec_driver_sql("ROLLBACK")
                raise _revision_not_found(revision_id, entity_id)

            current = (
                await conn.execute(
                    text(
                        "SELECT revision_id FROM entity_approved_revisions "
                        "WHERE entity_id = :eid"
                    ),
                    {"eid": entity_id},
                )
            ).scalar_one_or_none()

            if current != expected:
                await conn.exec_driver_sql("ROLLBACK")
                raise _conflict(entity_id, expected, current)

            if current == revision_id:
                # Idempotent: already approved with matching expectation.
                approved_at = (
                    await conn.execute(
                        text(
                            "SELECT approved_at FROM entity_approved_revisions "
                            "WHERE entity_id = :eid"
                        ),
                        {"eid": entity_id},
                    )
                ).scalar_one_or_none()
                await conn.exec_driver_sql("COMMIT")
            else:
                await conn.execute(
                    text(
                        "INSERT INTO entity_approved_revisions "
                        "(entity_id, revision_id, approved_at) "
                        "VALUES (:eid, :rid, "
                        "strftime('%Y-%m-%dT%H:%M:%fZ','now')) "
                        "ON CONFLICT(entity_id) DO UPDATE SET "
                        "revision_id = :rid, approved_at = "
                        "strftime('%Y-%m-%dT%H:%M:%fZ','now')"
                    ),
                    {"eid": entity_id, "rid": revision_id},
                )
                # Read while still holding the write lock, BEFORE commit: the
                # timestamp belongs to THIS mutation — a later approval can
                # never leak its timestamp into this response.
                approved_at = (
                    await conn.execute(
                        text(
                            "SELECT approved_at FROM entity_approved_revisions "
                            "WHERE entity_id = :eid"
                        ),
                        {"eid": entity_id},
                    )
                ).scalar_one_or_none()
                await conn.exec_driver_sql("COMMIT")

            return {
                "entity_id": entity_id,
                "revision_id": revision_id,
                "approved_at": approved_at,
            }
        except IntegrityError:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            raise SoloRingError(
                ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                "Unexpected integrity error during approval.",
                status_code=500,
            )
        except OperationalError as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if is_busy_error(exc):
                raise busy_error() from exc
            raise SoloRingError(
                ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                "Unexpected database error during approval.",
                status_code=500,
            ) from exc
