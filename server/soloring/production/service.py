"""Production Object service — M11A slice (frozen R3 plan §§5.1/11.1).

Create/list/detail/patch of Production Object display metadata only. No
delete route, no revision pointer, no publication logic (M11B).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.assets.blob_store import BlobStore
from soloring.db.timeutil import DB_NOW_SQL
from soloring.domain.ids import new_uuid
from soloring.errors import (
    ErrorCode,
    SoloRingError,
    internal_invariant,
    not_found,
    validation_error,
)
from soloring.production.canonical import RetainedBlobClosure, build_production_revision_snapshot
from soloring.production.readiness import resolve_publication_readiness

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
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        # Active-Project check INSIDE the writer fence: a concurrent Project
        # soft-delete cannot slip between the check and the INSERT (§11.1).
        await _require_active_project(conn, project_id)
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


# --- M11B: publication, immutable readers, provenance (frozen R3 §§9–10) -----

_text = text


def _not_ready_error(readiness) -> SoloRingError:
    return SoloRingError(
        ErrorCode.PRODUCTION_REVISION_NOT_READY,
        "publication readiness unresolved; publish is blocked",
        status_code=409,
        details={
            "readiness": {
                "production_object_id": readiness.production_object_id,
                "source_asset_id": readiness.source_asset_id,
                "ready": False,
                "issues": readiness.issues_as_dicts(),
            }
        },
    )


async def publish_production_revision(
    session: AsyncSession,
    blob_store: BlobStore,
    *,
    production_object_id: str,
    source_asset_id: str,
) -> tuple[dict, bool]:
    """Fenced Publish (frozen R3 plan §9): recompute readiness, then
    BEGIN IMMEDIATE, re-verify relational facts, converge-or-insert."""
    from soloring.db.timeutil import DB_NOW_SQL as _NOW

    readiness = await resolve_publication_readiness(
        session,
        blob_store,
        production_object_id=production_object_id,
        source_asset_id=source_asset_id,
    )
    if not readiness.ready:
        raise _not_ready_error(readiness)

    snapshot_json = readiness.snapshot_json
    snapshot_hash = readiness.snapshot_hash
    closure = readiness.closure
    assert snapshot_json is not None and snapshot_hash is not None and closure is not None

    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        # Fenced relational re-verification against the frozen facts.
        fact = (
            await conn.execute(
                _text(
                    "SELECT po.project_id AS pid, p.deleted_at AS pdeleted, "
                    "a.project_id AS apid, a.blob_hash AS abh, "
                    "b.size_bytes AS bsz, b.detected_media_type AS bmt "
                    "FROM production_objects po "
                    "JOIN projects p ON p.id = po.project_id "
                    "JOIN assets a ON a.id = :aid "
                    "JOIN blobs b ON b.hash = a.blob_hash "
                    "WHERE po.id = :oid"
                ),
                {"oid": production_object_id, "aid": source_asset_id},
            )
        ).first()
        if (
            fact is None
            or fact.pdeleted is not None
            or fact.apid != fact.pid
            or fact.abh != closure.blob_hash
            or fact.bsz != closure.size_bytes
            or fact.bmt != closure.media_type
        ):
            raise not_found(
                ErrorCode.PRODUCTION_OBJECT_NOT_FOUND,
                f"production object {production_object_id!r} not found or "
                "relational facts changed at the publish fence",
            )

        existing = (
            await conn.execute(
                _text(
                    "SELECT id, snapshot_json, snapshot_hash, revision_number "
                    "FROM production_revisions "
                    "WHERE production_object_id = :oid AND snapshot_hash = :h"
                ),
                {"oid": production_object_id, "h": snapshot_hash},
            )
        ).first()
        if existing is not None:
            await _validate_existing_winner(
                conn, existing, production_object_id, snapshot_json, snapshot_hash, closure
            )
            await conn.execute(
                _text(
                    "INSERT OR IGNORE INTO production_revision_source_assets "
                    "(production_revision_id, asset_id, created_at) "
                    f"VALUES (:rid, :aid, {_NOW})"
                ),
                {"rid": existing.id, "aid": source_asset_id},
            )
            await conn.exec_driver_sql("COMMIT")
            revision_id, created = existing.id, False
        else:
            max_no = (
                await conn.execute(
                    _text(
                        "SELECT COALESCE(MAX(revision_number), 0) "
                        "FROM production_revisions "
                        "WHERE production_object_id = :oid"
                    ),
                    {"oid": production_object_id},
                )
            ).scalar_one()
            revision_id = new_uuid()
            await conn.execute(
                _text(
                    "INSERT INTO production_revisions "
                    "(id, production_object_id, revision_number, snapshot_json, "
                    f"snapshot_hash, created_at) VALUES (:id, :oid, :num, :sj, :h, {_NOW})"
                ),
                {
                    "id": revision_id,
                    "oid": production_object_id,
                    "num": max_no + 1,
                    "sj": snapshot_json,
                    "h": snapshot_hash,
                },
            )
            await conn.execute(
                _text(
                    "INSERT INTO production_revision_closures "
                    "(production_revision_id, contract_key, contract_version, "
                    "blob_hash, size_bytes, media_type) "
                    "VALUES (:rid, 'retained_blob', 1, :bh, :sz, :mt)"
                ),
                {
                    "rid": revision_id,
                    "bh": closure.blob_hash,
                    "sz": closure.size_bytes,
                    "mt": closure.media_type,
                },
            )
            await conn.execute(
                _text(
                    "INSERT INTO production_revision_source_assets "
                    "(production_revision_id, asset_id, created_at) "
                    f"VALUES (:rid, :aid, {_NOW})"
                ),
                {"rid": revision_id, "aid": source_asset_id},
            )
            await conn.exec_driver_sql("COMMIT")
            created = True

    async with session.bind.connect() as conn:
        detail = await load_production_revision_metadata_verified(
            conn, revision_id=revision_id
        )
    return detail, created


async def _validate_existing_winner(conn, existing, object_id, snapshot_json, snapshot_hash, closure) -> None:
    import json as _json

    from soloring.domain.canonical import canonical_json_bytes

    if existing.snapshot_json != snapshot_json or existing.snapshot_hash != snapshot_hash:
        raise internal_invariant(
            "existing revision snapshot bytes/hash diverge from recomputed canonical",
            details={"revision_id": existing.id},
        )
    try:
        parsed = _json.loads(existing.snapshot_json)
    except ValueError:
        raise internal_invariant(
            "stored snapshot_json is not parseable JSON",
            details={"revision_id": existing.id},
        )
    if canonical_json_bytes(parsed) != existing.snapshot_json.encode("utf-8"):
        raise internal_invariant(
            "stored snapshot_json is not the canonical encoding of its content",
            details={"revision_id": existing.id},
        )
    closures = (
        await conn.execute(
            _text(
                "SELECT contract_key, contract_version, blob_hash, size_bytes, media_type "
                "FROM production_revision_closures WHERE production_revision_id = :rid"
            ),
            {"rid": existing.id},
        )
    ).all()
    if len(closures) != 1:
        raise internal_invariant(
            f"expected exactly one closure row, found {len(closures)}",
            details={"revision_id": existing.id},
        )
    c = closures[0]
    consumption = build_production_revision_snapshot(closure)["consumption"]
    if (
        c.contract_key != consumption["contract_key"]
        or c.contract_version != consumption["contract_version"]
        or c.blob_hash != consumption["blob_hash"]
        or c.size_bytes != consumption["size_bytes"]
        or c.media_type != consumption["media_type"]
    ):
        raise internal_invariant(
            "closure projection does not equal the canonical consumption object",
            details={"revision_id": existing.id},
        )
    blob = (
        await conn.execute(
            _text("SELECT hash, size_bytes FROM blobs WHERE hash = :h"),
            {"h": closure.blob_hash},
        )
    ).first()
    if blob is None or blob.hash != closure.blob_hash or blob.size_bytes != closure.size_bytes:
        raise internal_invariant(
            "closure Blob row missing or byte identity mismatch",
            details={"revision_id": existing.id, "blob_hash": closure.blob_hash},
        )


async def load_production_revision_metadata_verified(
    conn, *, revision_id: str
) -> dict:
    """Verified metadata reader (plan §10.1) — no physical file hash."""
    import json as _json

    from soloring.domain.canonical import canonical_hash, canonical_json_bytes

    row = (
        await conn.execute(
            _text(
                "SELECT r.id, r.production_object_id, r.revision_number, "
                "r.snapshot_json, r.snapshot_hash, r.created_at "
                "FROM production_revisions r WHERE r.id = :rid"
            ),
            {"rid": revision_id},
        )
    ).first()
    if row is None:
        raise not_found(
            ErrorCode.PRODUCTION_REVISION_NOT_FOUND,
            f"production revision {revision_id!r} not found",
        )
    obj = (
        await conn.execute(
            _text(
                "SELECT po.project_id FROM production_objects po "
                "WHERE po.id = :oid"
            ),
            {"oid": row.production_object_id},
        )
    ).first()
    try:
        parsed = _json.loads(row.snapshot_json)
    except ValueError:
        raise internal_invariant(
            "stored snapshot_json is not parseable JSON",
            details={"revision_id": revision_id},
        )
    if parsed.get("schema_version") != 1:
        raise internal_invariant(
            "snapshot schema_version is not 1",
            details={"revision_id": revision_id},
        )
    if canonical_json_bytes(parsed) != row.snapshot_json.encode("utf-8"):
        raise internal_invariant(
            "stored snapshot_json is not the canonical encoding of its content",
            details={"revision_id": revision_id},
        )
    if canonical_hash(parsed) != row.snapshot_hash:
        raise internal_invariant(
            "stored snapshot_hash does not match recomputed canonical hash",
            details={"revision_id": revision_id},
        )
    closures = (
        await conn.execute(
            _text(
                "SELECT contract_key, contract_version, blob_hash, size_bytes, media_type "
                "FROM production_revision_closures WHERE production_revision_id = :rid"
            ),
            {"rid": revision_id},
        )
    ).all()
    if len(closures) != 1:
        raise internal_invariant(
            f"expected exactly one closure row, found {len(closures)}",
            details={"revision_id": revision_id},
        )
    c = closures[0]
    consumption = parsed.get("consumption")
    if not isinstance(consumption, dict) or (
        c.contract_key != consumption.get("contract_key")
        or c.contract_version != consumption.get("contract_version")
        or c.blob_hash != consumption.get("blob_hash")
        or c.size_bytes != consumption.get("size_bytes")
        or c.media_type != consumption.get("media_type")
    ):
        raise internal_invariant(
            "closure row does not equal the canonical consumption object",
            details={"revision_id": revision_id},
        )
    blob = (
        await conn.execute(
            _text("SELECT hash, size_bytes FROM blobs WHERE hash = :h"),
            {"h": c.blob_hash},
        )
    ).first()
    if blob is None or blob.hash != c.blob_hash or blob.size_bytes != c.size_bytes:
        raise internal_invariant(
            "closure Blob row missing or byte identity mismatch",
            details={"revision_id": revision_id, "blob_hash": c.blob_hash},
        )
    from soloring.production.readiness import _media_type_valid

    if not _media_type_valid(c.media_type):
        raise internal_invariant(
            "closure media_type violates the schema-1 grammar",
            details={"revision_id": revision_id},
        )
    return {
        "revision_id": row.id,
        "production_object_id": row.production_object_id,
        "project_id": obj.project_id if obj else None,
        "revision_number": row.revision_number,
        "snapshot_json": row.snapshot_json,
        "snapshot_hash": row.snapshot_hash,
        "created_at": row.created_at,
        "closure": {
            "contract_key": c.contract_key,
            "contract_version": c.contract_version,
            "blob_hash": c.blob_hash,
            "size_bytes": c.size_bytes,
            "media_type": c.media_type,
        },
    }


async def load_verified_production_revision(
    conn, *, revision_id: str, blob_store: BlobStore
) -> dict:
    """Strict retained-byte consumer (plan §10.2) — §10.1 + physical proof."""
    meta = await load_production_revision_metadata_verified(conn, revision_id=revision_id)
    closure = meta["closure"]
    verification = await blob_store.verify_physical_bytes(
        closure["blob_hash"], closure["size_bytes"]
    )
    if not verification.ok:
        raise internal_invariant(
            "retained closure bytes failed physical verification",
            details={
                "revision_id": revision_id,
                "blob_hash": closure["blob_hash"],
                "reason": verification.reason,
            },
        )
    meta["physical_bytes_verified"] = True
    return meta


async def list_production_revisions(
    session: AsyncSession, production_object_id: str
) -> list[dict]:
    """Revision summaries, deterministic revision_number ASC (plan §11.4)."""
    async with session.bind.connect() as conn:
        rows = (
            await conn.execute(
                _text(
                    "SELECT id, revision_number, snapshot_hash, created_at "
                    "FROM production_revisions "
                    "WHERE production_object_id = :oid "
                    "ORDER BY revision_number ASC"
                ),
                {"oid": production_object_id},
            )
        ).all()
    return [
        {
            "revision_id": r.id,
            "revision_number": r.revision_number,
            "snapshot_hash": r.snapshot_hash,
            "created_at": r.created_at,
        }
        for r in rows
    ]


async def verify_source_provenance(conn, revision_id: str) -> list[dict]:
    """Source provenance verifier (plan §10.3) — contradictions are corruption."""
    links = (
        await conn.execute(
            _text(
                "SELECT prsa.asset_id, a.project_id AS asset_project_id, "
                "a.blob_hash AS asset_blob_hash, prsa.created_at "
                "FROM production_revision_source_assets prsa "
                "JOIN assets a ON a.id = prsa.asset_id "
                "WHERE prsa.production_revision_id = :rid ORDER BY prsa.asset_id"
            ),
            {"rid": revision_id},
        )
    ).all()
    if not links:
        raise internal_invariant(
            "published revision has no source provenance link",
            details={"revision_id": revision_id},
        )
    obj = (
        await conn.execute(
            _text(
                "SELECT po.project_id, prc.blob_hash "
                "FROM production_revisions r "
                "JOIN production_objects po ON po.id = r.production_object_id "
                "JOIN production_revision_closures prc "
                "ON prc.production_revision_id = r.id "
                "WHERE r.id = :rid"
            ),
            {"rid": revision_id},
        )
    ).first()
    if obj is None:
        raise internal_invariant(
            "revision missing object or closure during provenance verification",
            details={"revision_id": revision_id},
        )
    out = []
    for l in links:
        if l.asset_project_id != obj.project_id:
            raise internal_invariant(
                "source provenance link contradicts Production Object Project",
                details={"revision_id": revision_id, "asset_id": l.asset_id},
            )
        if l.asset_blob_hash != obj.blob_hash:
            raise internal_invariant(
                "source provenance link contradicts closure Blob",
                details={"revision_id": revision_id, "asset_id": l.asset_id},
            )
        out.append({"asset_id": l.asset_id, "created_at": l.created_at})
    return out
