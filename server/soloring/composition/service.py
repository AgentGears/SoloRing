"""Composition working-state authoring (frozen M12 R3 §7).

Mint itself is an identity operation: every path follows the FK-safe order
(validate → mint UUIDs in memory → insert operation → insert occurrence
rows → insert edges → mutate working membership → increment version).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.composition.canonical import (
    WorkingSpec,
    build_impact_value,
    build_operation_value,
    build_request_value,
    impact_fingerprint,
    operation_hash,
    operation_json,
    request_fingerprint,
)
from soloring.db.timeutil import DB_NOW_SQL
from soloring.domain.ids import new_uuid
from soloring.errors import (
    ErrorCode,
    SoloRingError,
    internal_invariant,
    not_found,
    validation_error,
)
from soloring.spatial.math import Transform

_NAME_MAX = 500
SCOPE = "composition_working_state"


class EditConflict(SoloRingError):
    """COMPOSITION_EDIT_CONFLICT with a closed reason value (frozen §13)."""

    def __init__(self, reason: str, message: str, details: dict | None = None):
        super().__init__(
            ErrorCode.COMPOSITION_EDIT_CONFLICT,
            message,
            status_code=409,
            details={"reason": reason, **(details or {})},
        )


def _require_scope(scope: object) -> None:
    if scope != SCOPE:
        raise validation_error(
            "scope must be explicitly 'composition_working_state' "
            f"(got {scope!r}); unknown or omitted scopes are never coerced",
        )


def _norm_name(value: object, what: str) -> str:
    if not isinstance(value, str):
        raise validation_error(f"{what} must be a string")
    n = value.strip()
    if not n or len(n) > _NAME_MAX:
        raise validation_error(f"{what} must be 1..{_NAME_MAX} trimmed characters")
    return n


def _norm_visible(value: object) -> bool:
    if not isinstance(value, bool):
        raise validation_error("visible must be a boolean")
    return value


def _norm_transform(value: object) -> Transform:
    if not isinstance(value, dict) or set(value) != {
        "translation_mm", "rotation_udeg"
    }:
        raise validation_error(
            "transform must be exactly {translation_mm, rotation_udeg} "
            "and is never silently invented",
        )
    for key in ("translation_mm", "rotation_udeg"):
        vec = value[key]
        if not isinstance(vec, list) or len(vec) != 3:
            raise validation_error(
                f"transform.{key} must be exactly 3 integers",)
        if not all(isinstance(v, int) and not isinstance(v, bool)
                   for v in vec):
            raise validation_error(f"transform.{key} must be integers")
    try:
        return Transform(
            translation_mm=tuple(value["translation_mm"]),
            rotation_udeg=tuple(value["rotation_udeg"]),
        )
    except (ValueError, TypeError) as exc:
        raise validation_error(f"invalid transform: {exc}") from exc


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


async def _require_composition(conn, composition_id: str) -> dict:
    row = (
        await conn.execute(
            text(
                "SELECT c.id, c.project_id, c.name, c.description, "
                "c.metadata_version, c.working_version, c.created_at, "
                "c.updated_at, p.deleted_at AS project_deleted_at "
                "FROM compositions c JOIN projects p ON p.id = c.project_id "
                "WHERE c.id = :cid"
            ),
            {"cid": composition_id},
        )
    ).first()
    if row is None or row.project_deleted_at is not None:
        raise not_found(
            ErrorCode.COMPOSITION_NOT_FOUND,
            f"composition {composition_id!r} not found",
        )
    return {
        "id": row.id,
        "project_id": row.project_id,
        "name": row.name,
        "description": row.description,
        "metadata_version": row.metadata_version,
        "working_version": row.working_version,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


async def _validate_source(
    conn, *, project_id: str, parent_composition_id: str,
    source_kind: str, revision_id: str,
) -> None:
    """Closed source grammar, same-Project, transitive same-lineage rule."""
    if source_kind == "production_revision":
        row = (
            await conn.execute(
                text(
                    "SELECT pr.id, po.project_id AS project_id "
                    "FROM production_revisions pr "
                    "JOIN production_objects po ON po.id = pr.production_object_id "
                    "WHERE pr.id = :rid"
                ),
                {"rid": revision_id},
            )
        ).first()
        if row is None:
            raise validation_error("source Production Revision does not exist")
        if row.project_id != project_id:
            raise validation_error("source Production Revision belongs to another Project")
        return
    if source_kind == "composition_revision":
        row = (
            await conn.execute(
                text(
                    "SELECT cr.id, cr.composition_id, c.project_id AS project_id "
                    "FROM composition_revisions cr "
                    "JOIN compositions c ON c.id = cr.composition_id "
                    "WHERE cr.id = :rid"
                ),
                {"rid": revision_id},
            )
        ).first()
        if row is None:
            raise validation_error("source Composition Revision does not exist")
        if row.project_id != project_id:
            raise validation_error("source Composition Revision belongs to another Project")
        if row.composition_id == parent_composition_id:
            raise validation_error(
                "a Composition cannot nest a revision from its own lineage"
            )
        # Transitive same-lineage embedding: any revision in the nested
        # revision's frozen closure owned by the parent Composition (frozen §3.8).
        clash = (
            await conn.execute(
                text(
                    "SELECT COUNT(*) FROM composition_revision_nested_dependencies d "
                    "JOIN composition_revisions cr ON cr.id = d.nested_composition_revision_id "
                    "WHERE d.composition_revision_id = :rid "
                    "AND cr.composition_id = :cid"
                ),
                {"rid": revision_id, "cid": parent_composition_id},
            )
        ).scalar_one()
        if clash:
            raise validation_error(
                "transitive same-lineage nesting rejected: the nested revision's "
                "frozen closure contains a revision of the parent Composition"
            )
        return
    raise validation_error(
        "source_kind must be 'production_revision' or 'composition_revision'"
    )


async def _working_spec(
    conn, *, project_id: str, parent_composition_id: str,
    spec: dict,
) -> WorkingSpec:
    """The ONE shared working/target-spec validator (frozen §8.2)."""
    if not isinstance(spec, dict) or set(spec) != {
        "display_name", "source", "visible", "transform"
    }:
        raise validation_error(
            "target spec must be exactly {display_name, source, visible, transform}"
        )
    source = spec["source"]
    if not isinstance(source, dict) or set(source) != {"kind", "revision_id"}:
        raise validation_error("source must be exactly {kind, revision_id}")
    if not isinstance(source["revision_id"], str):
        raise validation_error("source revision_id must be a string")
    await _validate_source(
        conn,
        project_id=project_id,
        parent_composition_id=parent_composition_id,
        source_kind=source["kind"],
        revision_id=source["revision_id"],
    )
    return WorkingSpec(
        display_name=_norm_name(spec["display_name"], "display_name"),
        source_kind=source["kind"],
        revision_id=source["revision_id"],
        visible=_norm_visible(spec["visible"]),
        transform=_norm_transform(spec["transform"]),
    )


# --- Composition metadata ----------------------------------------------------


async def create_composition(
    session: AsyncSession, project_id: str, *, name: object, description: object = None
) -> dict:
    n = _norm_name(name, "name")
    d = None if description is None else _norm_name(description, "description")
    cid = new_uuid()
    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await _require_active_project(conn, project_id)
        await conn.execute(
            text(
                "INSERT INTO compositions "
                "(id, project_id, name, description, metadata_version, "
                f"working_version, created_at, updated_at) VALUES "
                f"(:id, :pid, :name, :desc, 0, 0, {DB_NOW_SQL}, {DB_NOW_SQL})"
            ),
            {"id": cid, "pid": project_id, "name": n, "desc": d},
        )
        await conn.exec_driver_sql("COMMIT")
    return await get_composition(session, cid)


async def get_composition(session: AsyncSession, composition_id: str) -> dict:
    async with session.bind.connect() as conn:
        comp = await _require_composition(conn, composition_id)
        working = (
            await conn.execute(
                text("SELECT COUNT(*) FROM composition_working_occurrences "
                     "WHERE composition_id = :cid"), {"cid": composition_id},
            )
        ).scalar_one()
        published = (
            await conn.execute(
                text("SELECT COUNT(*) FROM composition_revisions "
                     "WHERE composition_id = :cid"), {"cid": composition_id},
            )
        ).scalar_one()
    return {**comp, "working_occurrence_count": working,
            "published_revision_count": published}


async def list_compositions(session: AsyncSession, project_id: str) -> list[dict]:
    async with session.bind.connect() as conn:
        await _require_active_project(conn, project_id)
        rows = (
            await conn.execute(
                text(
                    "SELECT id, project_id, name, description, metadata_version, "
                    "working_version, created_at, updated_at "
                    "FROM compositions WHERE project_id = :pid "
                    "ORDER BY created_at, id"
                ),
                {"pid": project_id},
            )
        ).all()
    return [dict(r._mapping) for r in rows]


# Sentinel distinguishing "description explicitly set to null" from "field
# omitted" (frozen §7.2). The router sets CLEAR_DESCRIPTION for explicit
# JSON null; omission arrives as the default None.
CLEAR_DESCRIPTION = object()


async def patch_composition_metadata(
    session: AsyncSession, composition_id: str, *,
    expected_metadata_version: int, name: object = None,
    description: object = None,
) -> dict:
    if not isinstance(expected_metadata_version, int) or isinstance(
        expected_metadata_version, bool
    ):
        raise validation_error("expected_metadata_version must be an integer")
    if name is None and description is None:
        raise validation_error("nothing to patch: provide name and/or description")
    sets: list[str] = []
    params: dict = {"cid": composition_id, "mv": expected_metadata_version}
    if name is not None:
        params["name"] = _norm_name(name, "name")
        sets.append("name = :name")
    if description is CLEAR_DESCRIPTION:
        sets.append("description = NULL")
    elif description is not None:
        if not isinstance(description, str):
            raise validation_error("description must be a string or null")
        params["desc"] = description.strip() or None
        sets.append("description = :desc")

    # The CAS runs entirely under the writer fence: compare the version and
    # verify exactly one affected row, so a competing metadata writer can
    # never be silently overwritten (frozen §7.2).
    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        comp = await _require_composition(conn, composition_id)
        if comp["metadata_version"] != expected_metadata_version:
            raise EditConflict(
                "stale_metadata_version",
                "composition metadata changed since read; refetch and retry",
            )
        cur = await conn.execute(
            text(
                "UPDATE compositions SET " + ", ".join(sets)
                + ", metadata_version = metadata_version + 1, "
                f"updated_at = {DB_NOW_SQL} "
                "WHERE id = :cid AND metadata_version = :mv"
            ),
            params,
        )
        if cur.rowcount != 1:
            raise EditConflict(
                "fence_race",
                "metadata version changed at the fence; refetch and retry",
            )
        await conn.exec_driver_sql("COMMIT")
    return await get_composition(session, composition_id)


# --- Working occurrences -----------------------------------------------------


async def _terminated_ids(conn, composition_id: str, ids: list[str]) -> set[str]:
    if not ids:
        return set()
    rows = (
        await conn.execute(
            text(
                "SELECT s.occurrence_id FROM "
                "composition_identity_operation_sources s "
                "JOIN composition_identity_operations o "
                "ON o.id = s.operation_id "
                "WHERE o.composition_id = :cid AND s.terminates_identity = 1 "
                "AND s.occurrence_id IN ("
                + ",".join(f":i{n}" for n in range(len(ids))) + ")"
            ),
            {"cid": composition_id, **{f"i{n}": i for n, i in enumerate(ids)}},
        )
    ).fetchall()
    return {r[0] for r in rows}


async def mint_occurrence(
    session: AsyncSession, composition_id: str, *,
    scope: object, expected_working_version: int, spec: dict,
) -> dict:
    _require_scope(scope)
    if not isinstance(expected_working_version, int) or isinstance(
        expected_working_version, bool
    ):
        raise validation_error("expected_working_version must be an integer")

    async with session.bind.connect() as conn:
        # Frozen §7.3: the whole validate→write unit runs under the fence.
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        comp = await _require_composition(conn, composition_id)
        wspec = await _working_spec(
            conn,
            project_id=comp["project_id"],
            parent_composition_id=composition_id,
            spec=spec,
        )
        if comp["working_version"] != expected_working_version:
            raise EditConflict(
                "stale_working_version",
                "working state changed since read; refetch and retry",
            )

        request_value = build_request_value(
            composition_id=composition_id, kind="mint",
            source_occurrence_ids=[], target_specs=[wspec],
        )
        req_fp = request_fingerprint(request_value)
        impact_value = build_impact_value(
            composition_id=composition_id,
            working_version=comp["working_version"],
            source_occurrence_ids=[], source_dispositions=[],
            live_blocking_references=[],
        )
        imp_fp = impact_fingerprint(impact_value)

        occurrence_id = new_uuid()  # minted in memory; FK-safe order
        op_value = build_operation_value(
            composition_id=composition_id, kind="mint",
            working_version_before=comp["working_version"],
            working_version_after=comp["working_version"] + 1,
            request_fp=req_fp, impact_fp=imp_fp,
            sources=[],
            targets=[{"occurrence_id": occurrence_id,
                      "working_spec": wspec.canonical_value()}],
        )

        op_id = new_uuid()
        await conn.execute(
            text(
                "INSERT INTO composition_identity_operations "
                "(id, composition_id, operation_kind, working_version_before, "
                "working_version_after, request_fingerprint, impact_fingerprint, "
                f"operation_json, operation_hash, created_at) VALUES "
                "(:id, :cid, 'mint', :before, :after, :req, :imp, :opjson, :ophash, "
                f"{DB_NOW_SQL})"
            ),
            {"id": op_id, "cid": composition_id,
             "before": comp["working_version"],
             "after": comp["working_version"] + 1,
             "req": req_fp, "imp": imp_fp,
             "opjson": operation_json(op_value),
             "ophash": operation_hash(op_value)},
        )
        await conn.execute(
            text(
                f"INSERT INTO composition_occurrences (id, composition_id, created_at) "
                f"VALUES (:oid, :cid, {DB_NOW_SQL})"
            ),
            {"oid": occurrence_id, "cid": composition_id},
        )
        await conn.execute(
            text(
                "INSERT INTO composition_identity_operation_targets "
                "(composition_id, operation_id, occurrence_id) "
                "VALUES (:cid, :opid, :oid)"
            ),
            {"cid": composition_id, "opid": op_id, "oid": occurrence_id},
        )
        await conn.execute(
            text(
                "INSERT INTO composition_working_occurrences "
                "(composition_id, occurrence_id, display_name, source_kind, "
                "production_revision_id, nested_composition_revision_id, visible, "
                "x_mm, y_mm, z_mm, yaw_udeg, pitch_udeg, roll_udeg, updated_at) VALUES "
                "(:cid, :oid, :name, :kind, :prid, :nrid, :vis, :x, :y, :z, "
                f":yaw, :pitch, :roll, {DB_NOW_SQL})"
            ),
            _spec_row_params(composition_id, occurrence_id, wspec),
        )
        await conn.execute(
            text("UPDATE compositions SET working_version = working_version + 1 "
                 f"WHERE id = :cid"),
            {"cid": composition_id},
        )
        await conn.exec_driver_sql("COMMIT")
    return {
        "occurrence_id": occurrence_id,
        "working_version": expected_working_version + 1,
        **wspec.canonical_value(),
    }


def _spec_row_params(composition_id: str, occurrence_id: str, spec: WorkingSpec) -> dict:
    t = spec.transform
    return {
        "cid": composition_id, "oid": occurrence_id,
        "name": spec.display_name,
        "kind": spec.source_kind,
        "prid": spec.revision_id if spec.source_kind == "production_revision" else None,
        "nrid": spec.revision_id if spec.source_kind == "composition_revision" else None,
        "vis": 1 if spec.visible else 0,
        "x": t.translation_mm[0], "y": t.translation_mm[1], "z": t.translation_mm[2],
        "yaw": t.rotation_udeg[0], "pitch": t.rotation_udeg[1],
        "roll": t.rotation_udeg[2],
    }


async def list_working_occurrences(
    session: AsyncSession, composition_id: str
) -> list[dict]:
    async with session.bind.connect() as conn:
        await _require_composition(conn, composition_id)
        rows = (
            await conn.execute(
                text(
                    "SELECT occurrence_id, display_name, source_kind, "
                    "production_revision_id, nested_composition_revision_id, "
                    "visible, x_mm, y_mm, z_mm, yaw_udeg, pitch_udeg, roll_udeg, "
                    "updated_at FROM composition_working_occurrences "
                    "WHERE composition_id = :cid ORDER BY occurrence_id"
                ),
                {"cid": composition_id},
            )
        ).all()
    return [dict(r._mapping) for r in rows]


async def patch_working_occurrence(
    session: AsyncSession, composition_id: str, occurrence_id: str, *,
    scope: object, expected_working_version: int,
    display_name: object = None, visible: object = None,
    transform: object = None, source: object = None,
) -> dict:
    """Identity-preserving edit (frozen §7.4/§7.5); explicit field set only."""
    _require_scope(scope)
    if not isinstance(expected_working_version, int) or isinstance(
        expected_working_version, bool
    ):
        raise validation_error("expected_working_version must be an integer")
    if display_name is None and visible is None and transform is None and source is None:
        raise validation_error("nothing to patch")

    async with session.bind.connect() as conn:
        comp = await _require_composition(conn, composition_id)
        row = (
            await conn.execute(
                text("SELECT * FROM composition_working_occurrences "
                     "WHERE composition_id = :cid AND occurrence_id = :oid"),
                {"cid": composition_id, "oid": occurrence_id},
            )
        ).first()
        if row is None:
            raise not_found(
                ErrorCode.COMPOSITION_OCCURRENCE_NOT_FOUND,
                f"occurrence {occurrence_id!r} not found in working state",
            )
        terminated = await _terminated_ids(conn, composition_id, [occurrence_id])
        if terminated:
            raise internal_invariant(
                "terminated identity remains in working state",
                details={"occurrence_id": occurrence_id},
            )
        if comp["working_version"] != expected_working_version:
            raise EditConflict(
                "stale_working_version",
                "working state changed since read; refetch and retry",
            )

        sets: list[str] = []
        params: dict = {"cid": composition_id, "oid": occurrence_id}

        if display_name is not None:
            params["name"] = _norm_name(display_name, "display_name")
            sets.append("display_name = :name")
        if visible is not None:
            v = _norm_visible(visible)
            params["vis"] = 1 if v else 0
            sets.append("visible = :vis")
        if transform is not None:
            t = _norm_transform(transform)
            params.update({"x": t.translation_mm[0], "y": t.translation_mm[1],
                           "z": t.translation_mm[2], "yaw": t.rotation_udeg[0],
                           "pitch": t.rotation_udeg[1], "roll": t.rotation_udeg[2]})
            sets += ["x_mm = :x", "y_mm = :y", "z_mm = :z",
                     "yaw_udeg = :yaw", "pitch_udeg = :pitch", "roll_udeg = :roll"]

        if source is not None:
            if not isinstance(source, dict) or set(source) != {"kind", "revision_id"}:
                raise validation_error("source must be exactly {kind, revision_id}")
            await _validate_source(
                conn,
                project_id=comp["project_id"],
                parent_composition_id=composition_id,
                source_kind=source["kind"],
                revision_id=source["revision_id"],
            )
            # identity-preservation predicate (frozen §7.5): same lineage only
            old_kind = row.source_kind
            if source["kind"] != old_kind:
                raise SoloRingError(
                    ErrorCode.VALIDATION_ERROR,
                    "source kind switch changes identity; use replace_as_new",
                    status_code=422,
                    details={"identity_change_required": True,
                             "allowed_operation": "replace_as_new"},
                )
            if old_kind == "production_revision":
                owner_rows = (await conn.execute(
                    text(
                        "SELECT id, production_object_id FROM production_revisions "
                        "WHERE id IN (:a, :b)"),
                    {"a": row.production_revision_id,
                     "b": source["revision_id"]},
                )).fetchall()
                owners = {r.id: r.production_object_id for r in owner_rows}
                old_owner = owners.get(row.production_revision_id)
                new_owner = owners.get(source["revision_id"])
                if old_owner is None or new_owner is None:
                    raise validation_error(
                        "current or proposed source Production Revision is missing"
                    )
                if old_owner != new_owner:
                    raise SoloRingError(
                        ErrorCode.VALIDATION_ERROR,
                        "Production Revision from another Production Object "
                        "changes identity; use replace_as_new",
                        status_code=422,
                        details={"identity_change_required": True,
                                 "allowed_operation": "replace_as_new"},
                    )
            else:
                owner_rows = (await conn.execute(
                    text(
                        "SELECT id, composition_id FROM composition_revisions "
                        "WHERE id IN (:a, :b)"),
                    {"a": row.nested_composition_revision_id,
                     "b": source["revision_id"]},
                )).fetchall()
                owners = {r.id: r.composition_id for r in owner_rows}
                old_owner = owners.get(row.nested_composition_revision_id)
                new_owner = owners.get(source["revision_id"])
                if old_owner is None or new_owner is None:
                    raise validation_error(
                        "current or proposed source Composition Revision is missing"
                    )
                if old_owner != new_owner:
                    raise SoloRingError(
                        ErrorCode.VALIDATION_ERROR,
                        "nested Composition Revision from another Composition "
                        "changes identity; use replace_as_new",
                        status_code=422,
                        details={"identity_change_required": True,
                                 "allowed_operation": "replace_as_new"},
                    )
            params["prid"] = (source["revision_id"]
                              if source["kind"] == "production_revision" else None)
            params["nrid"] = (source["revision_id"]
                              if source["kind"] == "composition_revision" else None)
            sets += ["production_revision_id = :prid",
                     "nested_composition_revision_id = :nrid",
                     "source_kind = :skind"]
            params["skind"] = source["kind"]

        # The mutation runs entirely under the writer fence (frozen §7.4):
        # active-Project revalidation, termination check, and version CAS
        # all happen after BEGIN IMMEDIATE.
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        fenced = (await conn.execute(
            text(
                "SELECT c.working_version, p.deleted_at AS project_deleted_at "
                "FROM compositions c JOIN projects p ON p.id = c.project_id "
                "WHERE c.id = :cid"
            ),
            {"cid": composition_id},
        )).first()
        if fenced is None or fenced.project_deleted_at is not None:
            raise not_found(
                ErrorCode.COMPOSITION_NOT_FOUND,
                f"composition {composition_id!r} not found or inactive at fence",
            )
        still_row = (await conn.execute(
            text("SELECT 1 FROM composition_working_occurrences "
                 "WHERE composition_id = :cid AND occurrence_id = :oid"),
            {"cid": composition_id, "oid": occurrence_id},
        )).first()
        if still_row is None:
            raise not_found(
                ErrorCode.COMPOSITION_OCCURRENCE_NOT_FOUND,
                f"occurrence {occurrence_id!r} left working state before fence",
            )
        still_terminated = await _terminated_ids(
            conn, composition_id, [occurrence_id])
        if still_terminated:
            raise internal_invariant(
                "terminated identity remains in working state",
                details={"occurrence_id": occurrence_id},
            )
        if fenced.working_version != expected_working_version:
            raise EditConflict("fence_race", "working version changed at the fence")
        await conn.execute(
            text(
                "UPDATE composition_working_occurrences SET "
                + ", ".join(sets)
                + f", updated_at = {DB_NOW_SQL} "
                "WHERE composition_id = :cid AND occurrence_id = :oid"
            ),
            params,
        )
        await conn.execute(
            text("UPDATE compositions SET working_version = working_version + 1 "
                 f"WHERE id = :cid"),
            {"cid": composition_id},
        )
        await conn.exec_driver_sql("COMMIT")
    return {
        "occurrence_id": occurrence_id,
        "working_version": expected_working_version + 1,
    }
