"""EntityRevision creation, listing, and detail (M6 §19, §22).

Immutable by construction: the only write path is creation. There is no
revision PATCH or DELETE service and no API route for either (M6-F3).

Creation flow (plan §22): validate + canonicalize + hash OUTSIDE the write
transaction, then one BEGIN IMMEDIATE unit re-verifying the active entity,
checking (entity_id, spec_hash) convergence, allocating MAX(revision_number)+1,
and inserting the EntityRevision row plus its typed spec row. Under
IMMEDIATE concurrent writers serialize, so the convergence lookup inside
the write unit makes identical concurrent creations converge to one row
and makes a revision-number collision structurally impossible — an
IntegrityError here is an invariant violation, never a retryable collision
(the same fencing the rerun primitive uses).
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.continuity.canonical import (
    canonical_json_bytes,
    revision_spec_hash,
    validate_spec_payload,
)
from soloring.continuity.entities import _entity_not_found
from soloring.continuity.enums import SPEC_TABLE_BY_KIND
from soloring.db.models import CreativeEntity, EntityRevision
from soloring.domain.ids import is_uuid, new_uuid
from soloring.errors import ErrorCode, SoloRingError, not_found, validation_error
from soloring.generation.repository import busy_error, is_busy_error


@dataclass(frozen=True)
class RevisionCreateResult:
    revision: dict
    created: bool


def _revision_not_found(revision_id: str) -> SoloRingError:
    return not_found(
        ErrorCode.ENTITY_REVISION_NOT_FOUND,
        f"EntityRevision {revision_id} not found.",
    )


async def _load_active_entity(session: AsyncSession, entity_id: str):
    if not is_uuid(entity_id):
        raise _entity_not_found(entity_id)
    entity = await session.get(CreativeEntity, entity_id)
    if entity is None or entity.deleted_at is not None:
        raise _entity_not_found(entity_id)
    return entity


async def create_revision(
    session: AsyncSession, entity_id: str, payload: object
) -> RevisionCreateResult:
    """Create (or converge on) an EntityRevision for the entity's kind."""
    entity = await _load_active_entity(session, entity_id)

    try:
        spec = validate_spec_payload(entity.kind, payload)
    except ValueError as exc:
        raise validation_error(str(exc)) from exc

    spec_bytes = canonical_json_bytes(spec)
    _, spec_hash = revision_spec_hash(entity.kind, spec)
    spec_json = spec_bytes.decode("utf-8")
    spec_table = SPEC_TABLE_BY_KIND[entity.kind]

    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")

            # Re-verify inside the write unit: the entity must still be
            # active when the revision lands.
            active = (
                await conn.execute(
                    text(
                        "SELECT kind FROM creative_entities "
                        "WHERE id = :eid AND deleted_at IS NULL"
                    ),
                    {"eid": entity_id},
                )
            ).first()
            if active is None:
                await conn.exec_driver_sql("ROLLBACK")
                raise _entity_not_found(entity_id)
            assert active[0] == entity.kind  # kind is immutable (M6-F2)

            existing = (
                await conn.execute(
                    text(
                        "SELECT id, revision_number, schema_version, "
                        "spec_hash, created_at FROM entity_revisions "
                        "WHERE entity_id = :eid AND spec_hash = :h",
                    ),
                    {"eid": entity_id, "h": spec_hash},
                )
            ).mappings().one_or_none()
            if existing is not None:
                await conn.exec_driver_sql("COMMIT")
                return RevisionCreateResult(revision=dict(existing), created=False)

            number = (
                await conn.execute(
                    text(
                        "SELECT COALESCE(MAX(revision_number), 0) + 1 "
                        "FROM entity_revisions WHERE entity_id = :eid"
                    ),
                    {"eid": entity_id},
                )
            ).scalar()

            revision_id = new_uuid()
            await conn.execute(
                text(
                    "INSERT INTO entity_revisions "
                    "(id, entity_id, revision_number, schema_version, "
                    " spec_hash, created_at) "
                    "VALUES (:id, :eid, :num, 1, :h, "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
                ),
                {"id": revision_id, "eid": entity_id, "num": number, "h": spec_hash},
            )
            await conn.execute(
                text(
                    f"INSERT INTO {spec_table} (revision_id, spec_json) "
                    "VALUES (:rid, :sj)"
                ),
                {"rid": revision_id, "sj": spec_json},
            )
            await conn.exec_driver_sql("COMMIT")
        except IntegrityError:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            raise SoloRingError(
                ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                "Unexpected integrity error during entity revision creation.",
                status_code=500,
            )
        except OperationalError as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if is_busy_error(exc):
                raise busy_error() from exc
            raise SoloRingError(
                ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                "Unexpected database error during entity revision creation.",
                status_code=500,
            ) from exc

    revision = dict(
        id=revision_id,
        entity_id=entity_id,
        revision_number=number,
        schema_version=1,
        spec_hash=spec_hash,
    )
    return RevisionCreateResult(revision=revision, created=True)


async def list_revisions(session: AsyncSession, entity_id: str) -> list[dict]:
    """Summary rows ordered by revision_number (spec_json not selected)."""
    from sqlalchemy import select

    await _load_active_entity(session, entity_id)
    res = await session.execute(
        select(
            EntityRevision.id,
            EntityRevision.entity_id,
            EntityRevision.revision_number,
            EntityRevision.schema_version,
            EntityRevision.spec_hash,
            EntityRevision.created_at,
        )
        .where(EntityRevision.entity_id == entity_id)
        .order_by(EntityRevision.revision_number)
    )
    return [dict(r) for r in res.mappings().all()]


async def get_revision_detail(
    session: AsyncSession, revision_id: str
) -> dict:
    """Full detail incl. the typed design payload (plan §28)."""
    if not is_uuid(revision_id):
        raise _revision_not_found(revision_id)
    row = (
        await session.execute(
            text(
                "SELECT er.id, er.entity_id, er.revision_number, "
                "er.schema_version, er.spec_hash, er.created_at, "
                "ce.kind AS entity_kind, ce.name AS entity_name "
                "FROM entity_revisions er "
                "JOIN creative_entities ce ON ce.id = er.entity_id "
                "WHERE er.id = :rid"
            ),
            {"rid": revision_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise _revision_not_found(revision_id)

    spec_table = SPEC_TABLE_BY_KIND[row["entity_kind"]]
    spec_json = (
        await session.execute(
            text(f"SELECT spec_json FROM {spec_table} WHERE revision_id = :rid"),
            {"rid": revision_id},
        )
    ).scalar_one_or_none()

    return {
        **dict(row),
        "spec_json": spec_json,
    }
