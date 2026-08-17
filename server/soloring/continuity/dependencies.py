"""Shot working semantic dependencies (M6 §43–§47).

Working state references Entity IDENTITY, never a revision: capture-time
resolution against the approved pointer is what pins revisions (M6-F6/§31).

``replace_semantic_dependencies`` is the ONLY write path: full-set
replacement inside ONE BEGIN IMMEDIATE unit (plan §47):

    verify active Shot (seam)
    ↓
    validate the complete proposed set (unique (entity_id, role), role rules)
    ↓
    verify every Entity: active + same Project + approved revision exists
    ↓
    DELETE old working set; INSERT normalized set with positions
    contiguous per role; update Shot.updated_at

Because M6 has no unapprove operation and deletion is blocked while an
active Shot depends on the entity, every legal dependency stays resolvable
at capture time (plan §46's invariant chain).
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from soloring.continuity.entities import _translate_op_error
from soloring.domain.ids import is_uuid
from soloring.domain.normalize import is_valid_role
from soloring.errors import ErrorCode, SoloRingError, not_found

SOURCE_SHOT_EXPLICIT = "shot_explicit"


@dataclass(frozen=True)
class WorkingDependency:
    entity_id: str
    role: str
    position: int


def _shot_not_found(shot_id: str) -> SoloRingError:
    return not_found(ErrorCode.SHOT_NOT_FOUND, f"Shot {shot_id} not found.")


def _set_invalid(message: str) -> SoloRingError:
    return SoloRingError(
        ErrorCode.SEMANTIC_DEPENDENCY_SET_INVALID, message, status_code=422
    )


async def _verify_active_shot(conn: AsyncConnection, shot_id: str) -> str:
    """Active-shot check INSIDE a held BEGIN IMMEDIATE unit (test seam).

    Returns the Shot's project_id for same-Project validation.
    """
    row = (
        await conn.execute(
            text(
                "SELECT project_id FROM shots WHERE id = :sid "
                "AND deleted_at IS NULL"
            ),
            {"sid": shot_id},
        )
    ).first()
    if row is None:
        raise _shot_not_found(shot_id)
    return row.project_id


def _normalize_proposed(proposed: list[dict]) -> list[WorkingDependency]:
    """Validate + normalize the complete proposed set.

    Identity is (shot, entity, role): the same entity may legally occupy
    multiple distinct roles (plan §44); the same (entity, role) twice is a
    duplicate. Positions are server-assigned contiguous per role in list
    order — clients express ordering by list order within each role.
    """
    if not isinstance(proposed, list):
        raise _set_invalid("dependencies must be a list.")
    seen: set[tuple[str, str]] = set()
    per_role_count: dict[str, int] = {}
    normalized: list[WorkingDependency] = []
    for item in proposed:
        if not isinstance(item, dict):
            raise _set_invalid("each dependency must be an object.")
        entity_id = item.get("entity_id")
        role = item.get("role")
        if not isinstance(entity_id, str) or not is_uuid(entity_id):
            raise _set_invalid(f"Invalid entity_id {entity_id!r}.")
        if not is_valid_role(role):
            raise _set_invalid(f"Invalid role {role!r}.")
        key = (entity_id, role)
        if key in seen:
            raise _set_invalid(
                f"Duplicate dependency ({entity_id}, {role})."
            )
        seen.add(key)
        position = per_role_count.get(role, 0)
        per_role_count[role] = position + 1
        normalized.append(
            WorkingDependency(entity_id=entity_id, role=role, position=position)
        )
    return normalized


async def replace_semantic_dependencies(
    session: AsyncSession, shot_id: str, proposed: list[dict]
) -> list[WorkingDependency]:
    """Atomically replace the Shot's complete working dependency set."""
    if not is_uuid(shot_id):
        raise _shot_not_found(shot_id)
    normalized = _normalize_proposed(proposed)

    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            project_id = await _verify_active_shot(conn, shot_id)

            if normalized:
                placeholders = ", ".join(
                    f":e{i}" for i in range(len(normalized))
                )
                params = {
                    f"e{i}": d.entity_id
                    for i, d in enumerate(normalized)
                }
                entities = (
                    await conn.execute(
                        text(
                            "SELECT id, project_id, deleted_at FROM "
                            f"creative_entities WHERE id IN ({placeholders})"
                        ),
                        params,
                    )
                ).mappings().all()
                by_id = {r["id"]: dict(r) for r in entities}
                for dep in normalized:
                    entity = by_id.get(dep.entity_id)
                    if entity is None or entity["deleted_at"] is not None:
                        raise _set_invalid(
                            f"Entity {dep.entity_id} does not exist or is "
                            "deleted."
                        )
                    if entity["project_id"] != project_id:
                        raise SoloRingError(
                            ErrorCode.SEMANTIC_DEPENDENCY_PROJECT_MISMATCH,
                            f"Entity {dep.entity_id} belongs to another "
                            "Project.",
                            status_code=422,
                        )
                    approved = (
                        await conn.execute(
                            text(
                                "SELECT 1 FROM entity_approved_revisions "
                                "WHERE entity_id = :eid"
                            ),
                            {"eid": dep.entity_id},
                        )
                    ).first()
                    if approved is None:
                        raise SoloRingError(
                            ErrorCode.ENTITY_APPROVED_REVISION_REQUIRED,
                            f"Entity {dep.entity_id} has no approved "
                            "EntityRevision.",
                            status_code=422,
                        )

            await conn.execute(
                text(
                    "DELETE FROM shot_entity_dependencies WHERE shot_id = :sid"
                ),
                {"sid": shot_id},
            )
            for dep in normalized:
                await conn.execute(
                    text(
                        "INSERT INTO shot_entity_dependencies "
                        "(shot_id, entity_id, role, position, created_at) "
                        "VALUES (:sid, :eid, :role, :pos, "
                        "strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
                    ),
                    {
                        "sid": shot_id,
                        "eid": dep.entity_id,
                        "role": dep.role,
                        "pos": dep.position,
                    },
                )
            await conn.execute(
                text(
                    "UPDATE shots SET updated_at = "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now') "
                    "WHERE id = :sid AND deleted_at IS NULL"
                ),
                {"sid": shot_id},
            )
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _translate_op_error(
                exc, "semantic dependency replacement"
            ) from exc
    return normalized


async def list_working_dependencies(
    session: AsyncSession, shot_id: str
) -> list[dict]:
    """Working set with each entity's current display metadata and the
    currently approved revision (display only — never hashed)."""
    async with session.bind.connect() as conn:
        await _verify_active_shot(conn, shot_id)
        rows = (
            await conn.execute(
                text(
                    "SELECT sed.entity_id, sed.role, sed.position, "
                    "ce.kind AS entity_kind, ce.name AS entity_name, "
                    "ar.revision_id AS approved_revision_id, "
                    "er.revision_number, er.spec_hash "
                    "FROM shot_entity_dependencies sed "
                    "JOIN creative_entities ce ON ce.id = sed.entity_id "
                    "LEFT JOIN entity_approved_revisions ar "
                    "ON ar.entity_id = sed.entity_id "
                    "LEFT JOIN entity_revisions er "
                    "ON er.id = ar.revision_id "
                    "WHERE sed.shot_id = :sid "
                    "ORDER BY sed.role, sed.position, sed.entity_id"
                ),
                {"sid": shot_id},
            )
        ).mappings().all()
        return [dict(r) for r in rows]
