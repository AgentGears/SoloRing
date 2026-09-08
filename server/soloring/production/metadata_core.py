"""THE M11 ProductionRevision metadata/closure verification core (§10.1).

One semantic implementation shared by the M11 scalar verified reader
(``load_production_revision_metadata_verified``) and the M13 set-oriented
batch wrapper (``verify_production_revisions_metadata_core``):
snapshot parse + canonical-encoding equality + recomputed hash,
schema_version, exactly-one closure, closure == the canonical consumption
object, closure-to-Blob byte identity, and media-type grammar. The scalar
wrapper keeps its public not-found behavior; the batch wrapper keeps
bounded queries for N revisions (frozen §26.1).
"""

from __future__ import annotations

import json as _json

from soloring.errors import internal_invariant


def verify_revision_row_semantics(
    *, revision_id: str, snapshot_json: str, snapshot_hash: str,
    closures: list, blob_by_hash: dict,
) -> dict:
    """Pure per-revision §10.1 semantic verification.

    ``closures`` is the list of closure rows for this revision (each
    exposing contract_key/contract_version/blob_hash/size_bytes/
    media_type); ``blob_by_hash`` maps blob_hash → row exposing hash +
    size_bytes. Raises internal_invariant on any violation — the exact
    failure semantics of the scalar reader. Returns the verified
    snapshot hash and closure facts.
    """
    from soloring.domain.canonical import (
        canonical_hash,
        canonical_json_bytes,
    )
    from soloring.production.readiness import _media_type_valid

    try:
        parsed = _json.loads(snapshot_json)
    except ValueError:
        raise internal_invariant(
            "stored snapshot_json is not parseable JSON",
            details={"revision_id": revision_id}) from None
    if not isinstance(parsed, dict) or parsed.get("schema_version") != 1:
        raise internal_invariant(
            "snapshot schema_version is not 1",
            details={"revision_id": revision_id})
    if canonical_json_bytes(parsed) != snapshot_json.encode("utf-8"):
        raise internal_invariant(
            "stored snapshot_json is not the canonical encoding of "
            "its content", details={"revision_id": revision_id})
    if canonical_hash(parsed) != snapshot_hash:
        raise internal_invariant(
            "stored snapshot_hash does not match recomputed canonical "
            "hash", details={"revision_id": revision_id})
    if len(closures) != 1:
        raise internal_invariant(
            f"expected exactly one closure row, found {len(closures)}",
            details={"revision_id": revision_id})
    c = closures[0]
    consumption = parsed.get("consumption")
    if not isinstance(consumption, dict) or (
            c.contract_key != consumption.get("contract_key")
            or c.contract_version != consumption.get("contract_version")
            or c.blob_hash != consumption.get("blob_hash")
            or c.size_bytes != consumption.get("size_bytes")
            or c.media_type != consumption.get("media_type")):
        raise internal_invariant(
            "closure row does not equal the canonical consumption "
            "object", details={"revision_id": revision_id})
    blob = blob_by_hash.get(c.blob_hash)
    if blob is None or blob.hash != c.blob_hash \
            or blob.size_bytes != c.size_bytes:
        raise internal_invariant(
            "closure Blob row missing or byte identity mismatch",
            details={"revision_id": revision_id, "blob_hash": c.blob_hash})
    if not _media_type_valid(c.media_type):
        raise internal_invariant(
            "closure media_type violates the schema-1 grammar",
            details={"revision_id": revision_id})
    return {
        "snapshot_hash": snapshot_hash,
        "blob_hash": c.blob_hash,
        "size_bytes": c.size_bytes,
        "contract_key": c.contract_key,
        "contract_version": c.contract_version,
        "media_type": c.media_type,
    }


async def verify_production_revisions_metadata_core(
    conn, revision_ids: list[str],
) -> dict[str, dict]:
    """Verify N ProductionRevisions (§10.1 semantics), set-oriented.

    The ONE shared semantic core runs per revision over rows fetched in
    bounded batches. Returns ``{revision_id: {"snapshot_hash",
    "blob_hash", "project_id", "size_bytes"}}``.
    """
    from sqlalchemy import text

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

    out: dict[str, dict] = {}
    for rid in revision_ids:
        row = by_id[rid]
        if row.production_object_id not in project_by_object:
            raise internal_invariant(
                "ProductionRevision's object is missing",
                details={"revision_id": rid})
        verified = verify_revision_row_semantics(
            revision_id=rid,
            snapshot_json=row.snapshot_json,
            snapshot_hash=row.snapshot_hash,
            closures=closures_by_rid.get(rid, []),
            blob_by_hash=blob_by_hash)
        out[rid] = {**verified,
                    "project_id": project_by_object[row.production_object_id]}
    return out
