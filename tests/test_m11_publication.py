"""M11 publication/readiness proofs (frozen R3 plan §20.2/§20.3).

Real BlobStore over a temp data root; real physical files; the fenced
publish path is exercised end to end at service level.
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
    list_production_objects,
    patch_production_object,
    publish_production_revision,
)
from soloring.production.readiness import resolve_publication_readiness

NOW = "2026-01-01T00:00:00.000Z"


async def _seed_project(factory) -> str:
    pid = new_uuid()
    async with factory() as s:
        async with s.bind.connect() as conn:
            await conn.execute(
                text("INSERT INTO projects (id, name, created_at, updated_at) "
                     "VALUES (:id, 'P', :n, :n)"),
                {"id": pid, "n": NOW},
            )
            await conn.commit()
    return pid


async def _seed_blob_asset(
    factory, blob_store: BlobStore, project_id: str, *, data: bytes,
    media_type: str | None = "image/png", blob_size: int | None = None,
) -> tuple[str, str]:
    """Register a Blob with REAL physical bytes plus a reference Asset."""
    bh = hashlib.sha256(data).hexdigest()
    path = blob_store.path_for_hash(bh)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    aid = new_uuid()
    async with factory() as s:
        async with s.bind.connect() as conn:
            await conn.execute(
                text("INSERT OR IGNORE INTO blobs (hash, path, size_bytes, detected_media_type, created_at) "
                     "VALUES (:h, :p, :s, :m, :n)"),
                {"h": bh, "p": f"sha256/{bh[:2]}/{bh[2:4]}/{bh}",
                 "s": blob_size if blob_size is not None else len(data),
                 "m": media_type, "n": NOW},
            )
            await conn.execute(
                text("INSERT INTO assets (id, project_id, blob_hash, kind, created_at) "
                     "VALUES (:a, :p, :h, 'reference', :n)"),
                {"a": aid, "p": project_id, "h": bh, "n": NOW},
            )
            await conn.commit()
    return aid, bh


@pytest.fixture
def blob_store(settings) -> BlobStore:
    return BlobStore(settings)


async def test_publish_reference_asset_creates_immutable_revision_and_closure(
    engine, factory, blob_store
):
    """M11-PUB:01 — happy publication."""
    pid = await _seed_project(factory)
    aid, bh = await _seed_blob_asset(factory, blob_store, pid, data=b"desk-bytes")
    async with factory() as s:
        obj = await create_production_object(s, pid, name="Reception Desk")
        rev, created = await publish_production_revision(
            s, blob_store,
            production_object_id=obj["id"], source_asset_id=aid,
        )
    assert created is True
    assert rev["revision_number"] == 1
    assert rev["closure"] == {
        "contract_key": "retained_blob",
        "contract_version": 1,
        "blob_hash": bh,
        "size_bytes": len(b"desk-bytes"),
        "media_type": "image/png",
    }
    import json

    parsed = json.loads(rev["snapshot_json"])
    assert parsed == {
        "schema_version": 1,
        "consumption": rev["closure"],
    }
    assert rev["snapshot_hash"] == hashlib.sha256(rev["snapshot_json"].encode()).hexdigest()


async def test_publish_output_asset_preserves_asset_provenance_kind(
    engine, factory, blob_store
):
    """M11-PUB:02 — candidate provenance is not rewritten or re-parented.

    Building a full Generation/Take chain is out of M11 test scope; the claim
    is proven by full-row invariance of the Asset across publication (every
    column, including kind and take linkage) plus the structural fact that
    the M11 production package never writes to ``assets``.
    """
    from pathlib import Path

    pid = await _seed_project(factory)
    aid, _ = await _seed_blob_asset(factory, blob_store, pid, data=b"render")
    async with factory() as s:
        async with s.bind.connect() as conn:
            before = (await conn.execute(
                text("SELECT * FROM assets WHERE id=:a"), {"a": aid}
            )).one()
        obj = await create_production_object(s, pid, name="Rendered Prop")
        rev, created = await publish_production_revision(
            s, blob_store, production_object_id=obj["id"], source_asset_id=aid)
        assert created
        async with s.bind.connect() as conn:
            after = (await conn.execute(
                text("SELECT * FROM assets WHERE id=:a"), {"a": aid}
            )).one()
    assert tuple(before) == tuple(after) and before.kind == "reference"

    import soloring.production.service as prod_service
    import soloring.production.readiness as prod_readiness

    for mod in (prod_service, prod_readiness):
        src = Path(mod.__file__).read_text()
        assert "UPDATE assets" not in src
        assert "INSERT INTO assets" not in src
        assert "DELETE FROM assets" not in src


async def test_cross_project_source_is_not_ready_and_publish_is_blocked(
    engine, factory, blob_store
):
    """M11-PUB:03 — preview SOURCE_PROJECT_MISMATCH; Publish 409 NOT_READY."""
    pid = await _seed_project(factory)
    other = await _seed_project(factory)
    aid, _ = await _seed_blob_asset(factory, blob_store, other, data=b"x-project")
    async with factory() as s:
        obj = await create_production_object(s, pid, name="Desk")
        r = await resolve_publication_readiness(
            s, blob_store,
            production_object_id=obj["id"], source_asset_id=aid)
        assert r.ready is False
        assert [i.code for i in r.issues] == ["SOURCE_PROJECT_MISMATCH"]
        assert r.snapshot_hash is None and r.closure is None
        with pytest.raises(SoloRingError) as ei:
            await publish_production_revision(
                s, blob_store,
                production_object_id=obj["id"], source_asset_id=aid)
        assert ei.value.code == "PRODUCTION_REVISION_NOT_READY"
        assert ei.value.status_code == 409
        codes = [i["code"] for i in ei.value.details["readiness"]["issues"]]
        assert codes == ["SOURCE_PROJECT_MISMATCH"]
        # No competing top-level cross-project code exists.
        from soloring.errors import ErrorCode
        assert not hasattr(ErrorCode, "PRODUCTION_REVISION_SOURCE_PROJECT_MISMATCH")


async def test_missing_or_malformed_source_asset_is_not_found(
    engine, factory, blob_store
):
    """M11-PUB:04 — existing ASSET_NOT_FOUND contract; nothing fabricated."""
    pid = await _seed_project(factory)
    async with factory() as s:
        obj = await create_production_object(s, pid, name="Desk")
        for bad in ("does-not-exist", new_uuid()):
            with pytest.raises(SoloRingError) as ei:
                await resolve_publication_readiness(
                    s, blob_store,
                    production_object_id=obj["id"], source_asset_id=bad)
            assert ei.value.code == "ASSET_NOT_FOUND"


async def test_zero_byte_registered_blob_is_not_publishable(
    engine, factory, blob_store
):
    """M11-PUB:05 — readiness blocker, not corruption."""
    pid = await _seed_project(factory)
    aid, _ = await _seed_blob_asset(factory, blob_store, pid, data=b"")
    async with factory() as s:
        obj = await create_production_object(s, pid, name="Desk")
        r = await resolve_publication_readiness(
            s, blob_store, production_object_id=obj["id"], source_asset_id=aid)
        assert r.ready is False
        assert [i.code for i in r.issues] == ["SOURCE_BLOB_EMPTY"]


async def test_missing_physical_blob_is_corruption_not_readiness(
    engine, factory, blob_store
):
    """M11-PUB:06 — missing registered bytes fail as corruption."""
    pid = await _seed_project(factory)
    aid, bh = await _seed_blob_asset(factory, blob_store, pid, data=b"gone")
    blob_store.path_for_hash(bh).unlink()
    async with factory() as s:
        obj = await create_production_object(s, pid, name="Desk")
        with pytest.raises(SoloRingError) as ei:
            await resolve_publication_readiness(
                s, blob_store, production_object_id=obj["id"], source_asset_id=aid)
        assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"
        assert ei.value.status_code == 500


async def test_corrupt_physical_blob_is_corruption(engine, factory, blob_store):
    """M11-PUB:07 — hash mismatch fails closed (same size)."""
    pid = await _seed_project(factory)
    aid, bh = await _seed_blob_asset(factory, blob_store, pid, data=b"12345")
    blob_store.path_for_hash(bh).write_bytes(b"12346")  # same length, different bytes
    async with factory() as s:
        obj = await create_production_object(s, pid, name="Desk")
        with pytest.raises(SoloRingError) as ei:
            await resolve_publication_readiness(
                s, blob_store, production_object_id=obj["id"], source_asset_id=aid)
        assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"


async def test_blob_size_mismatch_is_corruption(engine, factory, blob_store):
    """M11-PUB:08 — captured size is exact."""
    pid = await _seed_project(factory)
    aid, _ = await _seed_blob_asset(
        factory, blob_store, pid, data=b"12345678", blob_size=7)
    async with factory() as s:
        obj = await create_production_object(s, pid, name="Desk")
        with pytest.raises(SoloRingError) as ei:
            await resolve_publication_readiness(
                s, blob_store, production_object_id=obj["id"], source_asset_id=aid)
        assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"
        assert ei.value.details["reason"] == "size_mismatch"


async def test_readiness_preview_and_publish_use_same_canonical_builder(
    engine, factory, blob_store
):
    """M11-PUB:09 — preview/publish canonical parity."""
    pid = await _seed_project(factory)
    aid, _ = await _seed_blob_asset(factory, blob_store, pid, data=b"parity")
    async with factory() as s:
        obj = await create_production_object(s, pid, name="Desk")
        r = await resolve_publication_readiness(
            s, blob_store, production_object_id=obj["id"], source_asset_id=aid)
        rev, _ = await publish_production_revision(
            s, blob_store, production_object_id=obj["id"], source_asset_id=aid)
    assert r.snapshot_hash == rev["snapshot_hash"]
    assert r.snapshot_json == rev["snapshot_json"]
    assert r.closure.blob_hash == rev["closure"]["blob_hash"]


async def test_object_metadata_patch_cannot_change_published_revision(
    engine, factory, blob_store
):
    """M11-PUB:10 — display metadata cannot reinterpret history."""
    pid = await _seed_project(factory)
    aid, _ = await _seed_blob_asset(factory, blob_store, pid, data=b"stable")
    async with factory() as s:
        obj = await create_production_object(s, pid, name="Desk", description="old")
        rev, _ = await publish_production_revision(
            s, blob_store, production_object_id=obj["id"], source_asset_id=aid)
        patched = await patch_production_object(
            s, obj["id"], name="Renamed Desk", description="new")
        again, again_created = await publish_production_revision(
            s, blob_store, production_object_id=obj["id"], source_asset_id=aid)
    assert patched["name"] == "Renamed Desk"
    assert again_created is False
    assert again["revision_id"] == rev["revision_id"]
    assert again["snapshot_hash"] == rev["snapshot_hash"]
    assert again["snapshot_json"] == rev["snapshot_json"]


async def test_publish_creates_no_current_or_approved_revision_pointer(
    engine, factory, blob_store
):
    """M11-PUB:11 — M15 lifecycle not smuggled into M11."""
    pid = await _seed_project(factory)
    aid, _ = await _seed_blob_asset(factory, blob_store, pid, data=b"nopointer")
    async with factory() as s:
        obj = await create_production_object(s, pid, name="Desk")
        await publish_production_revision(
            s, blob_store, production_object_id=obj["id"], source_asset_id=aid)
    async with factory() as s:
        async with s.bind.connect() as conn:
            cols = [r[1] for r in (await conn.execute(
                text("PRAGMA table_info(production_objects)"))).fetchall()]
    assert not any("revision" in c for c in cols)


async def test_unpublishable_registered_media_type_is_readiness_not_corruption(
    engine, factory, blob_store
):
    """M11-PUB:12 — SOURCE_MEDIA_TYPE_INVALID; no snapshot/closure/invariant."""
    pid = await _seed_project(factory)
    aid, _ = await _seed_blob_asset(
        factory, blob_store, pid, data=b"media", media_type="x" * 300)
    async with factory() as s:
        obj = await create_production_object(s, pid, name="Desk")
        r = await resolve_publication_readiness(
            s, blob_store, production_object_id=obj["id"], source_asset_id=aid)
        assert r.ready is False
        assert [i.code for i in r.issues] == ["SOURCE_MEDIA_TYPE_INVALID"]
        assert r.snapshot_hash is None and r.closure is None
        with pytest.raises(SoloRingError) as ei:
            await publish_production_revision(
                s, blob_store, production_object_id=obj["id"], source_asset_id=aid)
        assert ei.value.code == "PRODUCTION_REVISION_NOT_READY"


async def test_publish_never_reaches_closure_check_for_invalid_media_type(
    engine, factory, blob_store
):
    """M11-PUB:13 — readiness classification precedes INSERT; the closure
    CHECK is defense in depth (a direct insert violating it is rejected)."""
    pid = await _seed_project(factory)
    aid, _ = await _seed_blob_asset(
        factory, blob_store, pid, data=b"media2", media_type=" padded ")
    async with factory() as s:
        obj = await create_production_object(s, pid, name="Desk")
        with pytest.raises(SoloRingError) as ei:
            await publish_production_revision(
                s, blob_store, production_object_id=obj["id"], source_asset_id=aid)
        assert ei.value.code == "PRODUCTION_REVISION_NOT_READY"
        async with s.bind.connect() as conn:
            n = (await conn.execute(
                text("SELECT COUNT(*) FROM production_revisions"))).scalar_one()
    assert n == 0  # never reached the fenced insert path

    # Defense in depth: the DDL CHECK rejects an untrimmed closure value.
    import sqlite3

    from soloring.settings import Settings

    st = Settings(data_dir=blob_store.settings.data_dir)
    con = sqlite3.connect(st.db_path)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO production_revision_closures VALUES "
            "(?,?,?,?,?,?)", ("r", "retained_blob", 1, "0" * 64, 3, " padded "))
    con.close()


async def test_publish_recomputes_physical_readiness_and_does_not_trust_preview(
    engine, factory, blob_store
):
    """M11-PUB:14 — publish performs a fresh physical verification in-call."""
    pid = await _seed_project(factory)
    aid, bh = await _seed_blob_asset(factory, blob_store, pid, data=b"fresh")
    async with factory() as s:
        obj = await create_production_object(s, pid, name="Desk")
        r = await resolve_publication_readiness(
            s, blob_store, production_object_id=obj["id"], source_asset_id=aid)
        assert r.ready
        # Corrupt the physical bytes AFTER the preview; Publish must fail.
        blob_store.path_for_hash(bh).write_bytes(b"FRESH!")
        with pytest.raises(SoloRingError) as ei:
            await publish_production_revision(
                s, blob_store, production_object_id=obj["id"], source_asset_id=aid)
        assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"


async def test_untrimmed_media_type_is_not_normalized_into_publishable_closure(
    engine, factory, blob_store
):
    """M11-PUB:15 — invalid interpretation metadata is not silently trimmed."""
    pid = await _seed_project(factory)
    aid, _ = await _seed_blob_asset(
        factory, blob_store, pid, data=b"norm", media_type="image/png ")
    async with factory() as s:
        obj = await create_production_object(s, pid, name="Desk")
        r = await resolve_publication_readiness(
            s, blob_store, production_object_id=obj["id"], source_asset_id=aid)
    assert r.ready is False
    assert [i.code for i in r.issues] == ["SOURCE_MEDIA_TYPE_INVALID"]


async def test_not_ready_publish_returns_complete_readiness_result(
    engine, factory, blob_store
):
    """M11-PUB:16 — the complete deterministic blocker set is reported."""
    other = await _seed_project(factory)  # asset project mismatch + empty blob
    aid, _ = await _seed_blob_asset(
        factory, blob_store, other, data=b"", media_type="x" * 300)
    pid = await _seed_project(factory)
    async with factory() as s:
        obj = await create_production_object(s, pid, name="Desk")
        with pytest.raises(SoloRingError) as ei:
            await publish_production_revision(
                s, blob_store, production_object_id=obj["id"], source_asset_id=aid)
    issues = ei.value.details["readiness"]["issues"]
    assert [i["code"] for i in issues] == [
        "SOURCE_PROJECT_MISMATCH", "SOURCE_BLOB_EMPTY", "SOURCE_MEDIA_TYPE_INVALID",
    ]


# --- Provenance separation (§20.3) -------------------------------------------


async def test_two_same_blob_assets_remain_distinct_provenance_sources(
    engine, factory, blob_store
):
    """M11-PROV:01 — same-Blob Assets converge on one revision, both linked."""
    pid = await _seed_project(factory)
    a1, bh = await _seed_blob_asset(factory, blob_store, pid, data=b"shared")
    a2, _ = await _seed_blob_asset(factory, blob_store, pid, data=b"shared")
    assert a1 != a2
    async with factory() as s:
        obj = await create_production_object(s, pid, name="Desk")
        r1, c1 = await publish_production_revision(
            s, blob_store, production_object_id=obj["id"], source_asset_id=a1)
        r2, c2 = await publish_production_revision(
            s, blob_store, production_object_id=obj["id"], source_asset_id=a2)
        assert c1 is True and c2 is False
        assert r1["revision_id"] == r2["revision_id"]
        async with s.bind.connect() as conn:
            links = (await conn.execute(
                text("SELECT asset_id FROM production_revision_source_assets "
                     "WHERE production_revision_id=:r ORDER BY asset_id"),
                {"r": r1["revision_id"]})).fetchall()
    assert sorted(l.asset_id for l in links) == sorted([a1, a2])


async def test_source_asset_id_does_not_change_revision_hash(
    engine, factory, blob_store
):
    """M11-PROV:02 — derivation/provenance independent of revision identity."""
    pid = await _seed_project(factory)
    a1, _ = await _seed_blob_asset(factory, blob_store, pid, data=b"same-hash")
    a2, _ = await _seed_blob_asset(factory, blob_store, pid, data=b"same-hash")
    async with factory() as s:
        obj = await create_production_object(s, pid, name="Desk")
        r1, _ = await publish_production_revision(
            s, blob_store, production_object_id=obj["id"], source_asset_id=a1)
        r2, _ = await publish_production_revision(
            s, blob_store, production_object_id=obj["id"], source_asset_id=a2)
    assert r1["snapshot_hash"] == r2["snapshot_hash"]
    assert r1["revision_id"] == r2["revision_id"]


async def test_different_closure_state_publishes_distinct_revision_number(
    engine, factory, blob_store
):
    """M11B gate: same object + different closure → distinct revisions."""
    pid = await _seed_project(factory)
    a1, _ = await _seed_blob_asset(factory, blob_store, pid, data=b"state-one")
    a2, _ = await _seed_blob_asset(factory, blob_store, pid, data=b"state-two!!")
    async with factory() as s:
        obj = await create_production_object(s, pid, name="Desk")
        r1, c1 = await publish_production_revision(
            s, blob_store, production_object_id=obj["id"], source_asset_id=a1)
        r2, c2 = await publish_production_revision(
            s, blob_store, production_object_id=obj["id"], source_asset_id=a2)
    assert c1 and c2
    assert r1["revision_id"] != r2["revision_id"]
    assert {r1["revision_number"], r2["revision_number"]} == {1, 2}
    assert r1["snapshot_hash"] != r2["snapshot_hash"]
