"""ContinuityPredicate + ContinuityRelation services (M7D plan §4–§5).

Predicates are Project-scoped identity: ``key`` is tombstone-inclusive
unique per Project and never recycled, with NO supersession lineage (0008
§37 — a dead key stays dead; its semantic successor is a new key).
name/description are mutable display metadata with no semantic effect.

Relations are active-slot identity ``(project_id, subject_entity_id,
predicate_id, object_entity_id)`` with NO mutable columns (0008 §38):
create / list / get / soft-delete only — there is no PATCH, and changing
subject, predicate, or object means delete-old + create-new = a NEW
relation identity. Soft-deleting a Relation FREES the duplicate slot.

Unresolved-id policy (frozen §4.2/§4.3): the M7 vocabulary deliberately
contains no predicate/relation not-found code, and none is manufactured —
unresolved ids on these surfaces use the existing generic validation
contract (422). Relation CONSTRUCTION failures route through the frozen
six-code table: ENTITY_NOT_FOUND for unresolvable endpoints (endpoints are
Entities), INVALID_CONTINUITY_RELATION for self/cross-Project/structural
invalidity, CONTINUITY_RELATION_CONFLICT for duplicate active identity,
and the in-use codes for guarded deletions.

Every mutation is ONE fenced BEGIN IMMEDIATE unit on one checked-out
connection with in-unit active verification (the M6A lesson), through
monkeypatchable seams.
"""

from __future__ import annotations

import contextlib

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from soloring.continuity.entities import _translate_op_error
from soloring.continuity.values import is_valid_key
from soloring.domain.ids import is_uuid, new_uuid
from soloring.domain.normalize import normalize_optional_creative
from soloring.errors import ErrorCode, SoloRingError, validation_error

_RELATION_DISPLAY_ORDER = (
    "subject_entity_id, p.key, object_entity_id, r.id"
)


def _unresolved(kind: str, ident: str) -> SoloRingError:
    """Generic validation contract for unresolved ids (no not-found code
    exists for predicates/relations in the frozen vocabulary — §4.3)."""
    return validation_error(f"{kind} {ident!r} not found (or not active).")


def _invalid_relation(message: str) -> SoloRingError:
    return SoloRingError(
        ErrorCode.INVALID_CONTINUITY_RELATION, message, status_code=422
    )


def _project_not_found(project_id: str) -> SoloRingError:
    return SoloRingError(
        ErrorCode.PROJECT_NOT_FOUND,
        f"Project {project_id} not found.",
        status_code=404,
    )


async def _verify_active_project(conn: AsyncConnection, project_id: str) -> None:
    """Active-Project check INSIDE a held unit (test seam; M6A lesson)."""
    row = (
        await conn.execute(
            text(
                "SELECT 1 FROM projects WHERE id = :pid AND deleted_at IS NULL"
            ),
            {"pid": project_id},
        )
    ).first()
    if row is None:
        raise _project_not_found(project_id)


# --- ContinuityPredicate (§4) ------------------------------------------------


def _validate_predicate(payload) -> dict:
    """Pure validation of the predicate authoring fields (§4.2).

    The frozen vocabulary has no predicate-specific validation code —
    malformed fields use the existing generic validation contract."""
    key = payload.key
    if not is_valid_key(key):
        raise validation_error(
            f"Predicate key {key!r} must match [a-z][a-z0-9_]{{0,63}}."
        )
    name = (payload.name or "").strip()
    if not name:
        raise validation_error("Predicate name must not be empty.")
    return {
        "key": key,
        "name": name,
        "description": normalize_optional_creative(payload.description),
    }


async def create_predicate(session: AsyncSession, project_id: str, payload) -> str:
    if not is_uuid(project_id):
        raise _project_not_found(project_id)
    values = _validate_predicate(payload)
    predicate_id = new_uuid()

    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await _verify_active_project(conn, project_id)

            # Tombstone-inclusive: a deleted key is never recycled (§4.1).
            existing_key = (
                await conn.execute(
                    text(
                        "SELECT id FROM continuity_predicates "
                        "WHERE project_id = :pid AND key = :key"
                    ),
                    {"pid": project_id, "key": values["key"]},
                )
            ).first()
            if existing_key is not None:
                raise SoloRingError(
                    ErrorCode.CONTINUITY_PREDICATE_KEY_CONFLICT,
                    f"Project already owns predicate key {values['key']!r} "
                    "(keys are never recycled, including after deletion).",
                    status_code=409,
                )

            await conn.execute(
                text(
                    "INSERT INTO continuity_predicates "
                    "(id, project_id, key, name, description, created_at, "
                    " updated_at) VALUES (:id, :pid, :key, :name, :desc, "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now'), "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
                ),
                {
                    "id": predicate_id,
                    "pid": project_id,
                    "key": values["key"],
                    "name": values["name"],
                    "desc": values["description"],
                },
            )
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _translate_op_error(
                exc, "continuity predicate creation"
            ) from exc
    return predicate_id


async def list_predicates(session: AsyncSession, project_id: str) -> list[dict]:
    if not is_uuid(project_id):
        raise _project_not_found(project_id)
    async with session.bind.connect() as conn:
        await _verify_active_project(conn, project_id)
        rows = (
            await conn.execute(
                text(
                    "SELECT id, project_id, key, name, description, "
                    "created_at, updated_at FROM continuity_predicates "
                    "WHERE project_id = :pid AND deleted_at IS NULL "
                    "ORDER BY key"
                ),
                {"pid": project_id},
            )
        ).mappings().all()
        return [dict(r) for r in rows]


async def get_predicate(session: AsyncSession, predicate_id: str) -> dict:
    if not is_uuid(predicate_id):
        raise _unresolved("ContinuityPredicate", predicate_id)
    async with session.bind.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT p.id, p.project_id, p.key, p.name, p.description, "
                    "p.created_at, p.updated_at FROM continuity_predicates p "
                    "WHERE p.id = :pid AND p.deleted_at IS NULL "
                    "AND EXISTS (SELECT 1 FROM projects pr "
                    "WHERE pr.id = p.project_id AND pr.deleted_at IS NULL)"
                ),
                {"pid": predicate_id},
            )
        ).mappings().one_or_none()
    if row is None:
        raise _unresolved("ContinuityPredicate", predicate_id)
    return dict(row)


async def patch_predicate(session: AsyncSession, predicate_id: str, patch) -> None:
    """Display-metadata-only PATCH (§4.2): name/description, partial
    field-presence semantics (omitted → preserve; explicit null → clear
    description). ``key`` is not patchable (absent from the schema)."""
    if not is_uuid(predicate_id):
        raise _unresolved("ContinuityPredicate", predicate_id)
    provided = patch.model_fields_set
    if not provided:
        await get_predicate(session, predicate_id)  # active check only
        return

    updates: dict[str, object] = {}
    if "name" in provided:
        name = (patch.name or "").strip()
        if not name:
            raise validation_error("Predicate name must not be empty.")
        updates["name"] = name
    if "description" in provided:
        updates["description"] = normalize_optional_creative(patch.description)

    set_sql = ", ".join(f"{col} = :{col}" for col in updates)
    params = {**updates, "pid": predicate_id}
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await _verify_active_predicate(conn, predicate_id)
            rowcount = (
                await conn.execute(
                    text(
                        "UPDATE continuity_predicates SET "
                        f"{set_sql}, updated_at = "
                        "strftime('%Y-%m-%dT%H:%M:%fZ','now') "
                        "WHERE id = :pid AND deleted_at IS NULL"
                    ),
                    params,
                )
            ).rowcount
            if rowcount != 1:
                raise _unresolved("ContinuityPredicate", predicate_id)
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _translate_op_error(
                exc, "continuity predicate patch"
            ) from exc


async def _verify_active_predicate(
    conn: AsyncConnection, predicate_id: str
) -> dict:
    """Active-predicate check INSIDE a held BEGIN IMMEDIATE unit (seam)."""
    row = (
        await conn.execute(
            text(
                "SELECT id, project_id, key FROM continuity_predicates "
                "WHERE id = :pid AND deleted_at IS NULL"
            ),
            {"pid": predicate_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise _unresolved("ContinuityPredicate", predicate_id)
    return dict(row)


async def delete_predicate(session: AsyncSession, predicate_id: str) -> None:
    """Soft-delete; CONTINUITY_PREDICATE_IN_USE while an active Relation
    references the predicate (§13.1). Idempotent for already-tombstoned.
    Historical shot_revision_relation_states rows never block deletion."""
    if not is_uuid(predicate_id):
        raise _unresolved("ContinuityPredicate", predicate_id)
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            row = (
                await conn.execute(
                    text(
                        "SELECT deleted_at FROM continuity_predicates "
                        "WHERE id = :pid"
                    ),
                    {"pid": predicate_id},
                )
            ).first()
            if row is None:
                raise _unresolved("ContinuityPredicate", predicate_id)
            if row.deleted_at is not None:
                await conn.exec_driver_sql("COMMIT")  # idempotent no-op
                return
            in_use = (
                await conn.execute(
                    text(
                        "SELECT 1 FROM continuity_relations "
                        "WHERE predicate_id = :pid AND deleted_at IS NULL "
                        "LIMIT 1"
                    ),
                    {"pid": predicate_id},
                )
            ).first()
            if in_use is not None:
                raise SoloRingError(
                    ErrorCode.CONTINUITY_PREDICATE_IN_USE,
                    f"ContinuityPredicate {predicate_id} is referenced by "
                    "an active Relation.",
                    status_code=409,
                )
            await conn.execute(
                text(
                    "UPDATE continuity_predicates SET deleted_at = "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now'), updated_at = "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :pid"
                ),
                {"pid": predicate_id},
            )
            await conn.exec_driver_sql("COMMIT")
        except SoloRingError:
            raise
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            raise _translate_op_error(
                exc, "continuity predicate deletion"
            ) from exc


# --- ContinuityRelation (§5) -------------------------------------------------


async def _verify_relation_inputs(
    conn: AsyncConnection,
    project_id: str,
    subject_entity_id: str,
    predicate_id: str,
    object_entity_id: str,
) -> str:
    """Validate relation construction inside the held unit (§5.1).

    Deterministic order: self-relation (pure) → subject → object →
    predicate → duplicate identity. Returns the predicate key for the
    display payload."""
    if subject_entity_id == object_entity_id:
        raise _invalid_relation(
            "A Relation cannot connect an Entity to itself."
        )

    for side, eid in (("subject", subject_entity_id), ("object", object_entity_id)):
        row = (
            await conn.execute(
                text(
                    "SELECT project_id, deleted_at FROM creative_entities "
                    "WHERE id = :eid"
                ),
                {"eid": eid},
            )
        ).first()
        if row is None or row.deleted_at is not None:
            raise SoloRingError(
                ErrorCode.ENTITY_NOT_FOUND,
                f"Relation {side} endpoint {eid} not found (or not active).",
                status_code=404,
            )
        if row.project_id != project_id:
            raise _invalid_relation(
                f"Relation {side} endpoint {eid} belongs to another Project."
            )

    predicate = (
        await conn.execute(
            text(
                "SELECT project_id, deleted_at, key "
                "FROM continuity_predicates WHERE id = :pid"
            ),
            {"pid": predicate_id},
        )
    ).first()
    if (
        predicate is None
        or predicate.deleted_at is not None
        or predicate.project_id != project_id
    ):
        raise _invalid_relation(
            f"ContinuityPredicate {predicate_id} is not an active predicate "
            f"of this Project."
        )

    return str(predicate.key)


async def create_relation(
    session: AsyncSession, project_id: str, payload
) -> str:
    if not is_uuid(project_id):
        raise _project_not_found(project_id)
    if not is_uuid(payload.subject_entity_id) or not is_uuid(payload.object_entity_id):
        raise SoloRingError(
            ErrorCode.ENTITY_NOT_FOUND,
            "Relation endpoints must be valid Entity ids.",
            status_code=404,
        )
    if not is_uuid(payload.predicate_id):
        raise _invalid_relation(
            f"ContinuityPredicate {payload.predicate_id!r} is not an active "
            "predicate of this Project."
        )

    relation_id = new_uuid()
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await _verify_active_project(conn, project_id)
            await _verify_relation_inputs(
                conn,
                project_id,
                payload.subject_entity_id,
                payload.predicate_id,
                payload.object_entity_id,
            )
            duplicate = (
                await conn.execute(
                    text(
                        "SELECT id FROM continuity_relations "
                        "WHERE project_id = :pid AND deleted_at IS NULL "
                        "AND subject_entity_id = :s AND predicate_id = :pr "
                        "AND object_entity_id = :o"
                    ),
                    {
                        "pid": project_id,
                        "s": payload.subject_entity_id,
                        "pr": payload.predicate_id,
                        "o": payload.object_entity_id,
                    },
                )
            ).first()
            if duplicate is not None:
                raise SoloRingError(
                    ErrorCode.CONTINUITY_RELATION_CONFLICT,
                    "An active Relation already occupies "
                    "(subject, predicate, object) for this Project.",
                    status_code=409,
                )
            await conn.execute(
                text(
                    "INSERT INTO continuity_relations "
                    "(id, project_id, subject_entity_id, predicate_id, "
                    " object_entity_id, created_at) "
                    "VALUES (:id, :pid, :s, :pr, :o, "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
                ),
                {
                    "id": relation_id,
                    "pid": project_id,
                    "s": payload.subject_entity_id,
                    "pr": payload.predicate_id,
                    "o": payload.object_entity_id,
                },
            )
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _translate_op_error(
                exc, "continuity relation creation"
            ) from exc
    return relation_id


async def list_relations(
    session: AsyncSession,
    project_id: str,
    subject_entity_id: str | None = None,
    object_entity_id: str | None = None,
    predicate_id: str | None = None,
) -> list[dict]:
    if not is_uuid(project_id):
        raise _project_not_found(project_id)
    async with session.bind.connect() as conn:
        await _verify_active_project(conn, project_id)
        sql = (
            "SELECT r.id, r.project_id, r.subject_entity_id, "
            "r.predicate_id, p.key AS predicate_key, r.object_entity_id, "
            "r.created_at FROM continuity_relations r "
            "JOIN continuity_predicates p ON p.id = r.predicate_id "
            "WHERE r.project_id = :pid AND r.deleted_at IS NULL "
        )
        params: dict[str, str] = {"pid": project_id}
        if subject_entity_id is not None:
            sql += "AND r.subject_entity_id = :s "
            params["s"] = subject_entity_id
        if object_entity_id is not None:
            sql += "AND r.object_entity_id = :o "
            params["o"] = object_entity_id
        if predicate_id is not None:
            sql += "AND r.predicate_id = :pr "
            params["pr"] = predicate_id
        sql += f"ORDER BY {_RELATION_DISPLAY_ORDER}"
        rows = (
            await conn.execute(text(sql), params)
        ).mappings().all()
        return [dict(r) for r in rows]


async def get_relation(session: AsyncSession, relation_id: str) -> dict:
    if not is_uuid(relation_id):
        raise _unresolved("ContinuityRelation", relation_id)
    async with session.bind.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT r.id, r.project_id, r.subject_entity_id, "
                    "r.predicate_id, p.key AS predicate_key, "
                    "r.object_entity_id, r.created_at "
                    "FROM continuity_relations r "
                    "JOIN continuity_predicates p ON p.id = r.predicate_id "
                    "WHERE r.id = :rid AND r.deleted_at IS NULL "
                    "AND EXISTS (SELECT 1 FROM projects pr "
                    "WHERE pr.id = r.project_id AND pr.deleted_at IS NULL)"
                ),
                {"rid": relation_id},
            )
        ).mappings().one_or_none()
    if row is None:
        raise _unresolved("ContinuityRelation", relation_id)
    return dict(row)


async def delete_relation(session: AsyncSession, relation_id: str) -> None:
    """Soft-delete; CONTINUITY_RELATION_IN_USE while active
    RelationTransitions exist (§13.2). Idempotent for tombstoned; frees the
    active identity slot (recreation is a NEW relation identity). Historical
    shot_revision_relation_states rows never block deletion."""
    if not is_uuid(relation_id):
        raise _unresolved("ContinuityRelation", relation_id)
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            row = (
                await conn.execute(
                    text(
                        "SELECT deleted_at FROM continuity_relations "
                        "WHERE id = :rid"
                    ),
                    {"rid": relation_id},
                )
            ).first()
            if row is None:
                raise _unresolved("ContinuityRelation", relation_id)
            if row.deleted_at is not None:
                await conn.exec_driver_sql("COMMIT")  # idempotent no-op
                return
            in_use = (
                await conn.execute(
                    text(
                        "SELECT 1 FROM continuity_relation_transitions "
                        "WHERE relation_id = :rid AND deleted_at IS NULL "
                        "LIMIT 1"
                    ),
                    {"rid": relation_id},
                )
            ).first()
            if in_use is not None:
                raise SoloRingError(
                    ErrorCode.CONTINUITY_RELATION_IN_USE,
                    f"ContinuityRelation {relation_id} has active "
                    "RelationTransitions.",
                    status_code=409,
                )
            await conn.execute(
                text(
                    "UPDATE continuity_relations SET deleted_at = "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :rid"
                ),
                {"rid": relation_id},
            )
            await conn.exec_driver_sql("COMMIT")
        except SoloRingError:
            raise
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            raise _translate_op_error(
                exc, "continuity relation deletion"
            ) from exc
