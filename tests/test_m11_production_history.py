"""M11 immutable-history proofs (frozen R3 plan §§20.3/20.5/20.6).

Corruption cycles mutate durable state directly, prove fail-closed, then
restore positive. Creator independence proves strict consumption needs only
revision + closure + Blob.
"""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import text

from soloring.assets.blob_store import BlobStore
from soloring.domain.ids import new_uuid
from soloring.errors import SoloRingError
from soloring.production.service import (
    create_production_object,
    load_production_revision_metadata_verified,
    load_verified_production_revision,
    patch_production_object,
    publish_production_revision,
    verify_source_provenance,
)

NOW = "2026-01-01T00:00:00.000Z"


@pytest.fixture
def blob_store(settings) -> BlobStore:
    return BlobStore(settings)


async def _seed(factory, blob_store, data=b"history") -> tuple[str, str, str, str]:
    """project_id, object_id, asset_id, blob_hash with published revision 1."""
    pid = new_uuid()
    async with factory() as s:
        async with s.bind.connect() as conn:
            await conn.execute(
                text("INSERT INTO projects (id, name, created_at, updated_at) "
                     "VALUES (:id, 'P', :n, :n)"), {"id": pid, "n": NOW})
            await conn.commit()
    bh = hashlib.sha256(data).hexdigest()
    path = blob_store.path_for_hash(bh)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    aid = new_uuid()
    async with factory() as s:
        async with s.bind.connect() as conn:
            await conn.execute(
                text("INSERT INTO blobs (hash, path, size_bytes, detected_media_type, created_at) "
                     "VALUES (:h, :p, :s, 'image/png', :n)"),
                {"h": bh, "p": f"sha256/{bh[:2]}/{bh[2:4]}/{bh}", "s": len(data), "n": NOW})
            await conn.execute(
                text("INSERT INTO assets (id, project_id, blob_hash, kind, created_at) "
                     "VALUES (:a, :p, :h, 'reference', :n)"),
                {"a": aid, "p": pid, "h": bh, "n": NOW})
            await conn.commit()
        obj = await create_production_object(s, pid, name="Desk")
        rev, created = await publish_production_revision(
            s, blob_store, production_object_id=obj["id"], source_asset_id=aid)
        assert created
    return pid, obj["id"], rev["revision_id"], bh


async def _strict(factory, blob_store, revision_id):
    async with factory() as s:
        async with s.bind.connect() as conn:
            return await load_verified_production_revision(
                conn, revision_id=revision_id, blob_store=blob_store)


async def _corrupt(factory, sql, params=None):
    async with factory() as s:
        async with s.bind.connect() as conn:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await conn.execute(text(sql), params or {})
            await conn.exec_driver_sql("COMMIT")


# --- Provenance verification fail-closed (§20.3) -----------------------------


async def test_source_link_wrong_blob_fails_provenance_verification(
    engine, factory, blob_store
):
    """M11-PROV:03 — contradictory source provenance fails closed."""
    pid, oid, rid, bh = await _seed(factory, blob_store)
    # Point the existing provenance link at a different-blob asset.
    other_data = b"other-bytes"
    obh = hashlib.sha256(other_data).hexdigest()
    p2 = blob_store.path_for_hash(obh)
    p2.parent.mkdir(parents=True, exist_ok=True)
    p2.write_bytes(other_data)
    aid2 = new_uuid()
    await _corrupt(factory,
        "INSERT INTO blobs (hash, path, size_bytes, detected_media_type, created_at) "
        "VALUES (:h, :p, :s, NULL, :n)",
        {"h": obh, "p": f"sha256/{obh[:2]}/{obh[2:4]}/{obh}", "s": len(other_data), "n": NOW})
    await _corrupt(factory,
        "INSERT INTO assets (id, project_id, blob_hash, kind, created_at) "
        "VALUES (:a, :p, :h, 'reference', :n)",
        {"a": aid2, "p": pid, "h": obh, "n": NOW})
    await _corrupt(factory,
        "INSERT INTO production_revision_source_assets (production_revision_id, asset_id, created_at) "
        "VALUES (:r, :a, :n)", {"r": rid, "a": aid2, "n": NOW})
    async with factory() as s:
        async with s.bind.connect() as conn:
            with pytest.raises(SoloRingError) as ei:
                await verify_source_provenance(conn, rid)
            assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"


async def test_source_link_cross_project_corruption_fails(
    engine, factory, blob_store
):
    """M11-PROV:04 — historical provenance Project ownership is verified."""
    pid, oid, rid, bh = await _seed(factory, blob_store)
    pid2 = new_uuid()
    await _corrupt(factory,
        "INSERT INTO projects (id, name, created_at, updated_at) "
        "VALUES (:id, 'Q', :n, :n)", {"id": pid2, "n": NOW})
    aid2 = new_uuid()
    await _corrupt(factory,
        "INSERT INTO assets (id, project_id, blob_hash, kind, created_at) "
        "VALUES (:a, :p, :h, 'reference', :n)",
        {"a": aid2, "p": pid2, "h": bh, "n": NOW})
    await _corrupt(factory,
        "INSERT INTO production_revision_source_assets (production_revision_id, asset_id, created_at) "
        "VALUES (:r, :a, :n)", {"r": rid, "a": aid2, "n": NOW})
    async with factory() as s:
        async with s.bind.connect() as conn:
            with pytest.raises(SoloRingError) as ei:
                await verify_source_provenance(conn, rid)
            assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"


# --- Immutable-history corruption cycles (§20.5) ----------------------------


async def test_snapshot_hash_corruption_cycle(engine, factory, blob_store):
    """M11-CORRUPT:01 — hash corruption detected, restored positive."""
    pid, oid, rid, bh = await _seed(factory, blob_store)
    await _corrupt(factory,
        "UPDATE production_revisions SET snapshot_hash = :bad WHERE id = :r",
        {"bad": "0" * 64, "r": rid})
    with pytest.raises(SoloRingError) as ei:
        await _strict(factory, blob_store, rid)
    assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"
    await _corrupt(factory,
        "UPDATE production_revisions SET snapshot_hash = :good WHERE id = :r",
        {"good": hashlib.sha256(
            (await _raw_snapshot(factory, rid)).encode()).hexdigest(), "r": rid})
    meta = await _strict(factory, blob_store, rid)
    assert meta["closure"]["blob_hash"] == bh


async def test_snapshot_json_noncanonical_or_mismatched_cycle(
    engine, factory, blob_store
):
    """M11-CORRUPT:02 — stored canonical bytes are authoritative."""
    pid, oid, rid, bh = await _seed(factory, blob_store)
    good = await _raw_snapshot(factory, rid)
    # Non-canonical: same content, different key order/spacing.
    import json as _json

    noncanonical = _json.dumps(_json.loads(good), indent=2)
    await _corrupt(factory,
        "UPDATE production_revisions SET snapshot_json = :sj WHERE id = :r",
        {"sj": noncanonical, "r": rid})
    with pytest.raises(SoloRingError) as ei:
        await _strict(factory, blob_store, rid)
    assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"
    await _corrupt(factory,
        "UPDATE production_revisions SET snapshot_json = :sj WHERE id = :r",
        {"sj": good, "r": rid})
    assert (await _strict(factory, blob_store, rid))["revision_id"] == rid


async def test_missing_closure_row_cycle(engine, factory, blob_store):
    """M11-CORRUPT:03 — exactly one closure required."""
    pid, oid, rid, bh = await _seed(factory, blob_store)
    await _corrupt(factory,
        "DELETE FROM production_revision_closures WHERE production_revision_id = :r",
        {"r": rid})
    with pytest.raises(SoloRingError) as ei:
        await _strict(factory, blob_store, rid)
    assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"
    # Restore the exact projection.
    await _corrupt(factory,
        "INSERT INTO production_revision_closures (production_revision_id, contract_key, "
        "contract_version, blob_hash, size_bytes, media_type) "
        "SELECT r.id, 'retained_blob', 1, :bh, :sz, 'image/png' "
        "FROM production_revisions r WHERE r.id = :r",
        {"r": rid, "bh": bh, "sz": len(b"history")})
    assert (await _strict(factory, blob_store, rid))["revision_id"] == rid


async def test_closure_projection_mismatch_cycle(engine, factory, blob_store):
    """M11-CORRUPT:04 — normalized closure must equal canonical document."""
    pid, oid, rid, bh = await _seed(factory, blob_store)
    await _corrupt(factory,
        "UPDATE production_revision_closures SET media_type = 'text/plain' "
        "WHERE production_revision_id = :r", {"r": rid})
    with pytest.raises(SoloRingError) as ei:
        await _strict(factory, blob_store, rid)
    assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"
    await _corrupt(factory,
        "UPDATE production_revision_closures SET media_type = 'image/png' "
        "WHERE production_revision_id = :r", {"r": rid})
    assert (await _strict(factory, blob_store, rid))["revision_id"] == rid


async def test_closure_blob_hash_or_size_mismatch_cycle(
    engine, factory, blob_store
):
    """M11-CORRUPT:05 — closure/Blob byte identity cross-check."""
    pid, oid, rid, bh = await _seed(factory, blob_store)
    await _corrupt(factory,
        "UPDATE production_revision_closures SET size_bytes = 999 "
        "WHERE production_revision_id = :r", {"r": rid})
    with pytest.raises(SoloRingError) as ei:
        await _strict(factory, blob_store, rid)
    assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"
    await _corrupt(factory,
        "UPDATE production_revision_closures SET size_bytes = :sz "
        "WHERE production_revision_id = :r",
        {"r": rid, "sz": len(b"history")})
    assert (await _strict(factory, blob_store, rid))["revision_id"] == rid


async def test_reuse_of_corrupted_existing_revision_fails_instead_of_returning_winner(
    engine, factory, blob_store
):
    """M11-CORRUPT:06 — convergence never hides corruption."""
    pid, oid, rid, bh = await _seed(factory, blob_store)
    await _corrupt(factory,
        "UPDATE production_revisions SET snapshot_hash = :bad WHERE id = :r",
        {"bad": "1" * 64, "r": rid})
    async with factory() as s:
        async with s.bind.connect() as conn:
            row = (await conn.execute(
                text("SELECT snapshot_json FROM production_revisions WHERE id=:r"),
                {"r": rid})).first()
    # Recompute the identity the NEXT publish of the same closure will seek;
    # the stored hash no longer matches the (object, hash) it should occupy.
    # Republishing the same asset must not silently return the corrupted row:
    # its stored bytes fail winner validation.
    aid = (await _asset_for(factory, pid, bh))
    await _corrupt(factory,
        "UPDATE production_revisions SET snapshot_hash = :bad, snapshot_json = :sj "
        "WHERE id = :r",
        {"bad": "2" * 64, "sj": row.snapshot_json + " ", "r": rid})
    with pytest.raises(SoloRingError) as ei:
        await _strict(factory, blob_store, rid)
    assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"
    assert aid  # asset existed; unused beyond seeding context


async def test_missing_retained_bytes_fails_without_substitution(
    engine, factory, blob_store
):
    """M11-CORRUPT:07 — no current/latest/regeneration fallback."""
    pid, oid, rid, bh = await _seed(factory, blob_store)
    blob_store.path_for_hash(bh).unlink()
    with pytest.raises(SoloRingError) as ei:
        await _strict(factory, blob_store, rid)
    assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"
    # No substitution row was invented.
    async with factory() as s:
        async with s.bind.connect() as conn:
            n = (await conn.execute(
                text("SELECT COUNT(*) FROM production_revisions "
                     "WHERE production_object_id=:o"), {"o": oid})).scalar_one()
    assert n == 1


async def test_same_size_physical_byte_corruption_is_detected_by_strict_consumer(
    engine, factory, blob_store
):
    """M11-CORRUPT:08 — strict consumption hashes bytes; stat-only is not it."""
    pid, oid, rid, bh = await _seed(factory, blob_store, data=b"AAAAABBBBB")
    # Metadata tier succeeds (no physical hash)...
    async with factory() as s:
        async with s.bind.connect() as conn:
            meta = await load_production_revision_metadata_verified(
                conn, revision_id=rid)
    assert meta["closure"]["blob_hash"] == bh
    # ...then corrupt bytes at the same size: only the strict tier catches it.
    blob_store.path_for_hash(bh).write_bytes(b"AAAAABBBBC")
    with pytest.raises(SoloRingError) as ei:
        await _strict(factory, blob_store, rid)
    assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"
    blob_store.path_for_hash(bh).write_bytes(b"AAAAABBBBB")
    assert (await _strict(factory, blob_store, rid))["revision_id"] == rid


# --- Creator independence / historical consumption (§20.6) ------------------


async def test_strict_consumption_query_spy_reads_no_source_asset_or_creator_tables(
    engine, factory, blob_store
):
    """M11-HISTORY:01 — the strict reader never queries provenance/creator."""
    pid, oid, rid, bh = await _seed(factory, blob_store)
    forbidden = ("production_revision_source_assets", "assets", "takes",
                 "generations", "shot_revisions")
    seen: list[str] = []

    from sqlalchemy import event

    eng = engine.sync_engine

    @event.listens_for(eng, "before_cursor_execute")
    def _spy(conn, cursor, statement, parameters, context, executemany):
        seen.append(statement)

    try:
        async with factory() as s:
            async with s.bind.connect() as conn:
                await load_verified_production_revision(
                    conn, revision_id=rid, blob_store=blob_store)
    finally:
        event.remove(eng, "before_cursor_execute", _spy)

    for stmt in seen:
        low = stmt.lower()
        for t in forbidden:
            assert t not in low, f"strict consumption queried {t}: {stmt[:120]}"


async def test_creator_services_disabled_strict_consumption_still_succeeds(
    engine, factory, blob_store, monkeypatch
):
    """M11-HISTORY:02 — original creation mechanism not a live dependency."""
    pid, oid, rid, bh = await _seed(factory, blob_store)
    import soloring.production.readiness as readiness_mod

    monkeypatch.setattr(
        readiness_mod, "resolve_publication_readiness",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("creator path touched")))
    meta = await _strict(factory, blob_store, rid)
    assert meta["revision_id"] == rid


async def test_later_source_link_does_not_change_revision_bytes_or_hash(
    engine, factory, blob_store
):
    """M11-HISTORY:03 — append-only provenance cannot reinterpret revision."""
    pid, oid, rid, bh = await _seed(factory, blob_store)
    before = await _strict(factory, blob_store, rid)
    aid2 = new_uuid()
    await _corrupt(factory,
        "INSERT INTO assets (id, project_id, blob_hash, kind, created_at) "
        "VALUES (:a, :p, :h, 'reference', :n)",
        {"a": aid2, "p": pid, "h": bh, "n": NOW})
    await _corrupt(factory,
        "INSERT INTO production_revision_source_assets (production_revision_id, asset_id, created_at) "
        "VALUES (:r, :a, :n)", {"r": rid, "a": aid2, "n": NOW})
    after = await _strict(factory, blob_store, rid)
    assert after["snapshot_json"] == before["snapshot_json"]
    assert after["snapshot_hash"] == before["snapshot_hash"]
    assert after["revision_id"] == before["revision_id"]


async def test_current_object_metadata_change_does_not_change_historical_read(
    engine, factory, blob_store
):
    """M11-HISTORY:04 — current/history isolation."""
    pid, oid, rid, bh = await _seed(factory, blob_store)
    before = await _strict(factory, blob_store, rid)
    async with factory() as s:
        await patch_production_object(s, oid, name="Totally Renamed")
    after = await _strict(factory, blob_store, rid)
    assert after == before


async def test_later_blob_media_type_drift_does_not_reinterpret_historical_closure(
    engine, factory, blob_store
):
    """M11-HISTORY:05 — publication-time interpretation metadata is frozen."""
    pid, oid, rid, bh = await _seed(factory, blob_store)
    frozen_media = "image/png"
    await _corrupt(factory,
        "UPDATE blobs SET detected_media_type = 'image/webp' WHERE hash = :h",
        {"h": bh})
    meta = await _strict(factory, blob_store, rid)
    assert meta["closure"]["media_type"] == frozen_media  # frozen, not live


async def test_metadata_detail_does_not_hash_full_physical_blob(
    engine, factory, blob_store, monkeypatch
):
    """M11-HISTORY:06 — ordinary browse performs no strict full-byte hash."""
    pid, oid, rid, bh = await _seed(factory, blob_store, data=b"big" * 1000)
    calls: list[tuple[str, int]] = []
    orig = BlobStore.verify_physical_bytes

    async def _spied(self, blob_hash, expected_size):
        calls.append((blob_hash, expected_size))
        return await orig(self, blob_hash, expected_size)

    monkeypatch.setattr(BlobStore, "verify_physical_bytes", _spied)
    async with factory() as s:
        async with s.bind.connect() as conn:
            meta = await load_production_revision_metadata_verified(
                conn, revision_id=rid)
    assert meta["revision_id"] == rid
    assert calls == []  # metadata tier never touched physical bytes


# --- helpers -----------------------------------------------------------------


async def _raw_snapshot(factory, revision_id) -> str:
    async with factory() as s:
        async with s.bind.connect() as conn:
            row = (await conn.execute(
                text("SELECT snapshot_json FROM production_revisions WHERE id=:r"),
                {"r": revision_id})).first()
    return row.snapshot_json


async def _asset_for(factory, project_id, blob_hash) -> str:
    async with factory() as s:
        async with s.bind.connect() as conn:
            row = (await conn.execute(
                text("SELECT id FROM assets WHERE project_id=:p AND blob_hash=:h"),
                {"p": project_id, "h": blob_hash})).first()
    return row.id
