"""CreativeEntity identity service (M6 §16–§18, §26–§28).

Identity only: name/description are display metadata and never participate
in any hash. Kind is immutable (M6-F2) — PATCH accepts only name and
description. Deletion is soft, guarded by ENTITY_IN_USE when an ACTIVE
Shot's working dependency references the entity; historical ShotRevision
dependencies never block deletion (M6 §26).
"""

from __future__ import annotations

import contextlib

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.api.schemas.entities import EntityCreate, EntityPatch
from soloring.continuity.enums import ENTITY_KINDS
from soloring.db.models import CreativeEntity
from soloring.domain.ids import is_uuid, new_uuid
from soloring.domain.normalize import normalize_optional_creative
from soloring.errors import ErrorCode, SoloRingError, not_found, validation_error
from soloring.generation.repository import busy_error, is_busy_error
from soloring.domain import projects as project_svc

ENTITY_NAME_MAX = 500


def _entity_not_found(entity_id: str) -> SoloRingError:
    return not_found(
        ErrorCode.ENTITY_NOT_FOUND, f"Entity {entity_id} not found."
    )


def _translate_op_error(exc: Exception, what: str) -> SoloRingError:
    """Uniform BUSY/invariant translation for fenced entity mutations."""
    if isinstance(exc, IntegrityError):
        return SoloRingError(
            ErrorCode.INTERNAL_INVARIANT_VIOLATION,
            f"Unexpected integrity error during {what}.",
            status_code=500,
        )
    if isinstance(exc, OperationalError):
        if is_busy_error(exc):
            return busy_error()
        return SoloRingError(
            ErrorCode.INTERNAL_INVARIANT_VIOLATION,
            f"Unexpected database error during {what}.",
            status_code=500,
        )
    return SoloRingError(
        ErrorCode.INTERNAL_INVARIANT_VIOLATION,
        f"Unexpected error during {what}.",
        status_code=500,
    )


async def _verify_active_project(conn, project_id: str) -> None:
    """Active-parent check INSIDE a held BEGIN IMMEDIATE unit (M6A re-gate).

    Extracted as a module-level seam so the create-vs-delete race tests can
    force the interleaving deterministically (the repository's
    ``_execute_generation_insert`` precedent). The write lock the caller
    holds is what makes this check atomic with the subsequent INSERT — an
    early unlocked SELECT demonstrably does not protect the write.
    """
    row = (
        await conn.execute(
            text(
                "SELECT 1 FROM projects WHERE id = :pid AND deleted_at IS NULL"
            ),
            {"pid": project_id},
        )
    ).first()
    if row is None:
        raise not_found(
            ErrorCode.PROJECT_NOT_FOUND, f"Project {project_id} not found."
        )


async def _verify_active_entity(conn, entity_id: str) -> None:
    """Active-entity check INSIDE a held BEGIN IMMEDIATE unit (M6A re-gate).

    Same seam rationale as ``_verify_active_project``: the check must be
    atomic with the mutation, so a concurrent DELETE cannot interleave
    between validation and UPDATE.
    """
    row = (
        await conn.execute(
            text(
                "SELECT 1 FROM creative_entities "
                "WHERE id = :eid AND deleted_at IS NULL"
            ),
            {"eid": entity_id},
        )
    ).first()
    if row is None:
        raise _entity_not_found(entity_id)


async def _get_active(session: AsyncSession, entity_id: str) -> CreativeEntity:
    if not is_uuid(entity_id):
        raise _entity_not_found(entity_id)
    entity = await session.get(CreativeEntity, entity_id)
    if entity is None or entity.deleted_at is not None:
        raise _entity_not_found(entity_id)
    return entity


async def create_entity(
    session: AsyncSession, project_id: str, data: EntityCreate
) -> CreativeEntity:
    """Create an Entity as ONE fenced write unit (M6A re-gate blocker 1).

    Validation/normalization happens outside; the active-Project check and
    the INSERT run inside one BEGIN IMMEDIATE, so a Project soft-deletion
    can never interleave between validation and write. Serializations:
    delete-first -> PROJECT_NOT_FOUND (no row); create-first -> the later
    cascade tombstones the new Entity. Never an active Entity under a
    deleted Project.
    """
    if not is_uuid(project_id):
        raise not_found(
            ErrorCode.PROJECT_NOT_FOUND, f"Project {project_id} not found."
        )
    kind = data.kind.strip()
    if kind not in ENTITY_KINDS:
        raise SoloRingError(
            ErrorCode.ENTITY_KIND_INVALID,
            f"kind must be one of {sorted(ENTITY_KINDS)}.",
            status_code=422,
        )
    name = (data.name or "").strip()
    if not name:
        raise validation_error("Entity name must not be empty.")
    if len(name) > ENTITY_NAME_MAX:
        raise validation_error(f"Entity name must be at most {ENTITY_NAME_MAX} chars.")
    description = normalize_optional_creative(data.description)
    entity_id = new_uuid()

    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await _verify_active_project(conn, project_id)
            await conn.execute(
                text(
                    "INSERT INTO creative_entities "
                    "(id, project_id, kind, name, description, created_at, "
                    " updated_at) VALUES (:id, :pid, :kind, :name, :desc, "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now'), "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
                ),
                {
                    "id": entity_id,
                    "pid": project_id,
                    "kind": kind,
                    "name": name,
                    "desc": description,
                },
            )
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _translate_op_error(exc, "entity creation") from exc

    entity = await session.get(CreativeEntity, entity_id)
    assert entity is not None
    return entity


async def list_entities(
    session: AsyncSession, project_id: str, kind: str | None = None
) -> list[CreativeEntity]:
    await project_svc.get_project(session, project_id)
    query = select(CreativeEntity).where(
        CreativeEntity.project_id == project_id,
        CreativeEntity.deleted_at.is_(None),
    )
    if kind is not None:
        normalized = kind.strip()
        if normalized not in ENTITY_KINDS:
            raise SoloRingError(
                ErrorCode.ENTITY_KIND_INVALID,
                f"kind filter must be one of {sorted(ENTITY_KINDS)}.",
                status_code=422,
            )
        query = query.where(CreativeEntity.kind == normalized)
    query = query.order_by(CreativeEntity.kind, CreativeEntity.name)
    res = await session.execute(query)
    return list(res.scalars().all())


async def get_entity(session: AsyncSession, entity_id: str) -> CreativeEntity:
    return await _get_active(session, entity_id)


async def patch_entity(
    session: AsyncSession, entity_id: str, data: EntityPatch
) -> CreativeEntity:
    """Patch identity fields as ONE fenced mutation (M6A re-gate blocker 2).

    Field validation/normalization happens outside; the active re-read and
    the UPDATE run inside one BEGIN IMMEDIATE with a deleted_at-conditional
    WHERE, so a concurrent DELETE cannot interleave between check and
    write. Serializations: patch-first -> persists, DELETE tombstones the
    renamed Entity after; delete-first -> 404 with the tombstone's identity
    metadata untouched. Never a post-delete mutation.
    """
    if not is_uuid(entity_id):
        raise _entity_not_found(entity_id)
    provided = data.model_fields_set
    updates: dict[str, object] = {}
    if "name" in provided:
        name = (data.name or "").strip()
        if not name:
            raise validation_error("Entity name must not be empty.")
        if len(name) > ENTITY_NAME_MAX:
            raise validation_error(
                f"Entity name must be at most {ENTITY_NAME_MAX} chars."
            )
        updates["name"] = name
    if "description" in provided:
        updates["description"] = normalize_optional_creative(data.description)
    if not updates:
        return await _get_active(session, entity_id)

    set_sql = ", ".join(f"{col} = :{col}" for col in updates)
    params = {**updates, "eid": entity_id}
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await _verify_active_entity(conn, entity_id)
            rowcount = (
                await conn.execute(
                    text(
                        "UPDATE creative_entities SET "
                        f"{set_sql}, updated_at = "
                        "strftime('%Y-%m-%dT%H:%M:%fZ','now') "
                        "WHERE id = :eid AND deleted_at IS NULL"
                    ),
                    params,
                )
            ).rowcount
            if rowcount != 1:  # impossible under the held write lock
                await conn.exec_driver_sql("ROLLBACK")
                raise _entity_not_found(entity_id)
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _translate_op_error(exc, "entity patch") from exc

    entity = await session.get(CreativeEntity, entity_id)
    assert entity is not None
    return entity


async def delete_entity(session: AsyncSession, entity_id: str) -> None:
    """Soft-delete under BEGIN IMMEDIATE (plan §9, §26).

    Rejects ENTITY_IN_USE when the entity appears in a working dependency
    of an ACTIVE Shot. Historical ShotRevision dependencies do not block:
    deleted identities stay readable through historical provenance.
    Idempotent for already-deleted entities (matching Project/Shot policy).
    """
    if not is_uuid(entity_id):
        raise _entity_not_found(entity_id)
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            row = (
                await conn.execute(
                    text(
                        "SELECT id, deleted_at FROM creative_entities "
                        "WHERE id = :eid"
                    ),
                    {"eid": entity_id},
                )
            ).mappings().one_or_none()
            if row is None:
                await conn.exec_driver_sql("ROLLBACK")
                raise _entity_not_found(entity_id)
            if row["deleted_at"] is not None:
                await conn.exec_driver_sql("COMMIT")  # idempotent no-op
                return

            in_use = (
                await conn.execute(
                    text(
                        "SELECT 1 FROM shot_entity_dependencies sed "
                        "JOIN shots sh ON sh.id = sed.shot_id "
                        "WHERE sed.entity_id = :eid AND sh.deleted_at IS NULL "
                        "LIMIT 1"
                    ),
                    {"eid": entity_id},
                )
            ).first()
            if in_use is not None:
                await conn.exec_driver_sql("ROLLBACK")
                raise SoloRingError(
                    ErrorCode.ENTITY_IN_USE,
                    f"Entity {entity_id} is a working dependency of an "
                    "active Shot.",
                    status_code=409,
                )

            # M7A re-gate blocker 3: an Entity with active ContinuityFeatures
            # is not deletable — orphaned working-state identity under a
            # tombstoned Entity is illegal.
            has_features = (
                await conn.execute(
                    text(
                        "SELECT 1 FROM continuity_features "
                        "WHERE entity_id = :eid AND deleted_at IS NULL "
                        "LIMIT 1"
                    ),
                    {"eid": entity_id},
                )
            ).first()
            if has_features is not None:
                await conn.exec_driver_sql("ROLLBACK")
                raise SoloRingError(
                    ErrorCode.ENTITY_IN_USE,
                    f"Entity {entity_id} still owns active ContinuityFeatures.",
                    status_code=409,
                    details={"reason": "active_continuity_features"},
                )

            await conn.execute(
                text(
                    "UPDATE creative_entities SET deleted_at = "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now'), updated_at = "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :eid"
                ),
                {"eid": entity_id},
            )
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _translate_op_error(exc, "entity deletion") from exc
