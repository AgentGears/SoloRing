"""Production Object service — M11A slice (frozen R3 plan §§5.1/11.1).

Create/list/detail/patch of Production Object display metadata only. No
delete route, no revision pointer, no publication logic (M11B).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.db.timeutil import DB_NOW_SQL
from soloring.domain.ids import new_uuid
from soloring.errors import ErrorCode, SoloRingError, not_found, validation_error

_NAME_MAX = 500


def _normalize_name(name: object) -> str:
    if not isinstance(name, str):
        raise validation_error("name must be a string")
    n = name.strip()
    if not n:
        raise validation_error("name must not be empty")
    if len(n) > _NAME_MAX:
        raise validation_error(f"name must be at most {_NAME_MAX} characters")
    return n


def _normalize_description(description: object) -> str | None:
    if description is None:
        return None
    if not isinstance(description, str):
        raise validation_error("description must be a string or null")
    d = description.strip()
    return d or None


async def _require_active_project(conn, project_id: str) -> None:
    row = await conn.execute(
        text("SELECT id FROM projects WHERE id = :pid AND deleted_at IS NULL"),
        {"pid": project_id},
    )
    if row.first() is None:
        raise not_found(
            ErrorCode.PROJECT_NOT_FOUND,
            f"project {project_id!r} not found or not active",
        )


async def create_production_object(
    session: AsyncSession, project_id: str, *, name: object, description: object = None
) -> dict:
    n = _normalize_name(name)
    d = _normalize_description(description)
    obj_id = new_uuid()
    async with session.bind.connect() as conn:
        await _require_active_project(conn, project_id)
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(
            text(
                "INSERT INTO production_objects "
                "(id, project_id, name, description, created_at, updated_at) "
                "VALUES (:id, :pid, :name, :desc, "
                f"{DB_NOW_SQL}, {DB_NOW_SQL})"
            ),
            {"id": obj_id, "pid": project_id, "name": n, "desc": d},
        )
        await conn.exec_driver_sql("COMMIT")
    return await get_production_object(session, obj_id)


async def get_production_object(session: AsyncSession, object_id: str) -> dict:
    async with session.bind.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT po.id, po.project_id, po.name, po.description, "
                    "po.created_at, po.updated_at, p.deleted_at "
                    "FROM production_objects po JOIN projects p ON p.id = po.project_id "
                    "WHERE po.id = :oid"
                ),
                {"oid": object_id},
            )
        ).first()
    if row is None:
        raise not_found(
            ErrorCode.PRODUCTION_OBJECT_NOT_FOUND,
            f"production object {object_id!r} not found",
        )
    if row.deleted_at is not None:
        # Unavailable to current-authoring APIs; history remains inspectable.
        raise not_found(
            ErrorCode.PRODUCTION_OBJECT_NOT_FOUND,
            f"production object {object_id!r} not found",
        )
    return {
        "id": row.id,
        "project_id": row.project_id,
        "name": row.name,
        "description": row.description,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


async def list_production_objects(
    session: AsyncSession, project_id: str
) -> list[dict]:
    async with session.bind.connect() as conn:
        await _require_active_project(conn, project_id)
        rows = (
            await conn.execute(
                text(
                    "SELECT id, project_id, name, description, created_at, updated_at "
                    "FROM production_objects WHERE project_id = :pid "
                    "ORDER BY created_at, id"
                ),
                {"pid": project_id},
            )
        ).all()
    return [
        {
            "id": r.id,
            "project_id": r.project_id,
            "name": r.name,
            "description": r.description,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        }
        for r in rows
    ]


async def patch_production_object(
    session: AsyncSession, object_id: str, *, name: object = None, description: object = None
) -> dict:
    if name is None and description is None:
        raise validation_error("nothing to patch: provide name and/or description")
    sets: list[str] = []
    params: dict = {"oid": object_id}
    if name is not None:
        params["name"] = _normalize_name(name)
        sets.append("name = :name")
    if description is not None:
        params["desc"] = _normalize_description(description)
        sets.append("description = :desc")
    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        cur = await conn.execute(
            text(
                "UPDATE production_objects SET "
                + ", ".join(sets)
                + f", updated_at = {DB_NOW_SQL} "
                "WHERE id = :oid "
                "AND project_id IN (SELECT id FROM projects WHERE deleted_at IS NULL)"
            ),
            params,
        )
        await conn.exec_driver_sql("COMMIT")
        if cur.rowcount != 1:
            raise not_found(
                ErrorCode.PRODUCTION_OBJECT_NOT_FOUND,
                f"production object {object_id!r} not found",
            )
    return await get_production_object(session, object_id)
