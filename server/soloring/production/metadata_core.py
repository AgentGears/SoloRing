"""Set-oriented M11 ProductionRevision metadata/closure verification core.

Performs the EXACT semantic checks of
``load_production_revision_metadata_verified`` (plan §10.1) for N
revisions in a bounded set of queries, so M13's immutable binding
verifier can prove the full M11 closure for every pinned revision
without N+1 round trips or a thinner parallel implementation:
snapshot parse + canonical-encoding equality + recomputed hash,
schema_version, exactly-one closure, closure == canonical consumption
object, closure→Blob byte identity, and media-type grammar.
"""

from __future__ import annotations

import json as _json

from sqlalchemy import text

from soloring.errors import internal_invariant


async def verify_production_revisions_metadata_core(
    conn, revision_ids: list[str],
) -> dict[str, dict]:
    """Verify N ProductionRevisions (§10.1 semantics), set-oriented.

    Returns ``{revision_id: {"snapshot_hash", "blob_hash", "project_id",
    "size_bytes"}}``. Raises internal_invariant on any violation —
    identical failure semantics to the scalar reader.
    """
    if not revision_ids:
        return {}
    ph = ", ".join(f":r{i}" for i in range(len(revision_ids)))
    params = {f"r{i}": v for i, v in enumerate(revision_ids)}

    rows = (await conn.execute(text(
        f"SELECT id, production_object_id, snapshot_json, snapshot_hash "
        f"FROM production_revisions WHERE id IN ({ph})"), params,
    )).fetchall()
    by_id = {r.id: r for r in rows}
    missing = [r for r in revision_ids if r not in by_id]
    if missing:
        raise internal_invariant(
            "pinned ProductionRevision rows missing", 
            details={"revision_ids": missing})

    obj_ids = sorted({r.production_object_id for r in rows})
    oph = ", ".join(f":o{i}" for i in range(len(obj_ids)))
    oparams = {f"o{i}": v for i, v in enumerate(obj_ids)}
    obj_rows = (await conn.execute(text(
        f"SELECT id, project_id FROM production_objects "
        f"WHERE id IN ({oph})"), oparams,
    )).fetchall()
    project_by_object = {r.id: r.project_id for r in obj_rows}

    closure_rows = (await conn.execute(text(
        f"SELECT production_revision_id, contract_key, contract_version, "
        f"blob_hash, size_bytes, media_type FROM "
        f"production_revision_closures WHERE production_revision_id "
        f"IN ({ph})"), params,
    )).fetchall()
    closures_by_rid: dict[str, list] = {}
    for c in closure_rows:
        closures_by_rid.setdefault(c.production_revision_id, []).append(c)

    blob_hashes = sorted({c.blob_hash for c in closure_rows})
    blob_by_hash: dict[str, object] = {}
    if blob_hashes:
        bph = ", ".join(f":b{i}" for i in range(len(blob_hashes)))
        bparams = {f"b{i}": v for i, v in enumerate(blob_hashes)}
        for b in (await conn.execute(text(
            f"SELECT hash, size_bytes FROM blobs WHERE hash IN ({bph})"),
                bparams)).fetchall():
            blob_by_hash[b.hash] = b

    from soloring.domain.canonical import (
        canonical_hash,
        canonical_json_bytes,
    )
    from soloring.production.readiness import _media_type_valid

    out: dict[str, dict] = {}
    for rid in revision_ids:
        row = by_id[rid]
        try:
            parsed = _json.loads(row.snapshot_json)
        except ValueError:
            raise internal_invariant(
                "stored snapshot_json is not parseable JSON",
                details={"revision_id": rid}) from None
        if not isinstance(parsed, dict) or parsed.get("schema_version") != 1:
            raise internal_invariant(
                "snapshot schema_version is not 1",
                details={"revision_id": rid})
        if canonical_json_bytes(parsed) != row.snapshot_json.encode("utf-8"):
            raise internal_invariant(
                "stored snapshot_json is not the canonical encoding of "
                "its content", details={"revision_id": rid})
        if canonical_hash(parsed) != row.snapshot_hash:
            raise internal_invariant(
                "stored snapshot_hash does not match recomputed canonical "
                "hash", details={"revision_id": rid})
        cl = closures_by_rid.get(rid, [])
        if len(cl) != 1:
            raise internal_invariant(
                f"expected exactly one closure row, found {len(cl)}",
                details={"revision_id": rid})
        c = cl[0]
        consumption = parsed.get("consumption")
        if not isinstance(consumption, dict) or (
                c.contract_key != consumption.get("contract_key")
                or c.contract_version != consumption.get("contract_version")
                or c.blob_hash != consumption.get("blob_hash")
                or c.size_bytes != consumption.get("size_bytes")
                or c.media_type != consumption.get("media_type")):
            raise internal_invariant(
                "closure row does not equal the canonical consumption "
                "object", details={"revision_id": rid})
        blob = blob_by_hash.get(c.blob_hash)
        if blob is None or blob.hash != c.blob_hash \
                or blob.size_bytes != c.size_bytes:
            raise internal_invariant(
                "closure Blob row missing or byte identity mismatch",
                details={"revision_id": rid, "blob_hash": c.blob_hash})
        if not _media_type_valid(c.media_type):
            raise internal_invariant(
                "closure media_type violates the schema-1 grammar",
                details={"revision_id": rid})
        if row.production_object_id not in project_by_object:
            raise internal_invariant(
                "ProductionRevision's object is missing",
                details={"revision_id": rid})
        out[rid] = {
            "snapshot_hash": row.snapshot_hash,
            "blob_hash": c.blob_hash,
            "size_bytes": c.size_bytes,
            "project_id": project_by_object[row.production_object_id],
        }
    return out
