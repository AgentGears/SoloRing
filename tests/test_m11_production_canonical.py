"""M11 schema-1 canonical identity proofs (frozen R3 plan §6.3/§20.1).

The exact 200-byte fixture and its SHA-256 are frozen in the plan; the test
compares the shared serializer's output byte-for-byte. No second serializer
exists in M11 code.
"""

import hashlib

from soloring.production.canonical import (
    RetainedBlobClosure,
    build_production_revision_snapshot,
    production_revision_snapshot_bytes,
    production_revision_snapshot_hash,
    production_revision_snapshot_json,
)

FIXTURE = RetainedBlobClosure(
    blob_hash="a" * 64,
    size_bytes=3,
    media_type=None,
)

# Frozen in plan §6.3 — generated once by the already-published serializer.
FIXTURE_BYTES = (
    b'{"consumption":{"blob_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
    b'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","contract_key":"retained_blob",'
    b'"contract_version":1,"media_type":null,"size_bytes":3},'
    b'"schema_version":1}'
)
assert len(FIXTURE_BYTES) == 200  # plan-pinned byte length
FIXTURE_HASH = (
    "96fbc3e879f66e85ac857ac3f7c6ddce02004193fca0280e02b2fbfe84d7dbe8"
)


def test_schema1_exact_utf8_fixture():
    """M11-ID:04 — exact schema-1 bytes pinned."""
    b = production_revision_snapshot_bytes(FIXTURE)
    assert b == FIXTURE_BYTES
    assert production_revision_snapshot_json(FIXTURE) == FIXTURE_BYTES.decode("utf-8")
    assert production_revision_snapshot_hash(FIXTURE) == FIXTURE_HASH
    assert hashlib.sha256(b).hexdigest() == FIXTURE_HASH


def test_schema1_reordered_input_dict_is_byte_identical():
    """M11-ID:05 — the shared serializer is dict-order independent."""
    reordered = {
        "consumption": {
            "media_type": None,
            "size_bytes": 3,
            "blob_hash": "a" * 64,
            "contract_version": 1,
            "contract_key": "retained_blob",
        },
        "schema_version": 1,
    }
    from soloring.domain.canonical import canonical_json_bytes

    assert canonical_json_bytes(reordered) == FIXTURE_BYTES
    assert canonical_json_bytes(build_production_revision_snapshot(FIXTURE)) == FIXTURE_BYTES


def test_schema1_null_media_type_is_explicit():
    """M11-ID:06 — null is explicit canonical state, never omitted."""
    doc = build_production_revision_snapshot(FIXTURE)
    assert doc["consumption"]["media_type"] is None
    assert b'"media_type":null' in production_revision_snapshot_bytes(FIXTURE)


def test_different_blob_or_interpretation_changes_snapshot_hash():
    """M11-ID:07 — any consumption-semantic change changes the hash."""
    base = production_revision_snapshot_hash(FIXTURE)
    other_blob = production_revision_snapshot_hash(
        RetainedBlobClosure(blob_hash="b" * 64, size_bytes=3, media_type=None)
    )
    other_size = production_revision_snapshot_hash(
        RetainedBlobClosure(blob_hash="a" * 64, size_bytes=4, media_type=None)
    )
    other_media = production_revision_snapshot_hash(
        RetainedBlobClosure(blob_hash="a" * 64, size_bytes=3, media_type="image/png")
    )
    assert len({base, other_blob, other_size, other_media}) == 4


def test_schema1_hash_excludes_source_and_display_provenance():
    """M11-ID:03 — Asset/object/filename/path/display metadata never enter."""
    # The builder accepts ONLY the closure; publication of the same closure
    # from any Asset, object name, filename, or path yields identical bytes.
    h1 = production_revision_snapshot_hash(FIXTURE)
    import hashlib

    for variant in (
        RetainedBlobClosure(blob_hash="a" * 64, size_bytes=3, media_type=None),
        RetainedBlobClosure(blob_hash="a" * 64, size_bytes=3, media_type=None),
    ):
        assert production_revision_snapshot_hash(variant) == h1
    # Structurally: the frozen canonical bytes contain only the five facts.
    doc = build_production_revision_snapshot(FIXTURE)
    assert set(doc) == {"schema_version", "consumption"}
    assert set(doc["consumption"]) == {
        "contract_key", "contract_version", "blob_hash", "size_bytes", "media_type",
    }
    assert h1 == hashlib.sha256(FIXTURE_BYTES).hexdigest()


async def test_same_blob_on_two_objects_produces_distinct_revision_ids(
    engine, factory, settings
):
    """M11-ID:02 — Blob identity does not collapse Production Objects."""
    from soloring.assets.blob_store import BlobStore
    from soloring.production.service import (
        create_production_object,
        publish_production_revision,
    )
    from tests.test_m11_publication import _seed_blob_asset, _seed_project

    blob_store = BlobStore(settings)

    pid = await _seed_project(factory)
    data = b"shared-object-bytes"
    aid, bh = await _seed_blob_asset(factory, blob_store, pid, data=data)
    async with factory() as s:
        obj_x = await create_production_object(s, pid, name="Object X")
        obj_y = await create_production_object(s, pid, name="Object Y")
        rx, cx = await publish_production_revision(
            s, blob_store, production_object_id=obj_x["id"], source_asset_id=aid)
        ry, cy = await publish_production_revision(
            s, blob_store, production_object_id=obj_y["id"], source_asset_id=aid)
    assert cx and cy
    assert rx["revision_id"] != ry["revision_id"]
    assert rx["closure"]["blob_hash"] == ry["closure"]["blob_hash"] == bh
    assert rx["snapshot_hash"] == ry["snapshot_hash"]  # same closure content


async def test_duplicate_object_names_have_distinct_uuid_identity(
    engine, factory
):
    """M11-ID:01 — name is not Production Object identity."""
    from sqlalchemy import text

    from soloring.production.service import (
        create_production_object,
        list_production_objects,
    )

    pid = "11111111-1111-1111-1111-111111111111"
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO projects (id, name, created_at, updated_at) "
                "VALUES (:id, 'P', '2026-01-01T00:00:00.000Z', "
                "'2026-01-01T00:00:00.000Z')"
            ),
            {"id": pid},
        )

    async with factory() as session:
        a = await create_production_object(session, pid, name="  Reception Desk  ")
        b = await create_production_object(session, pid, name="Reception Desk")
        assert a["id"] != b["id"]
        assert a["name"] == b["name"] == "Reception Desk"  # trim; no uniqueness
        listed = await list_production_objects(session, pid)
        # Deterministic (created_at, id) order — creation order is NOT the
        # contract when timestamps tie; stable id ordering is.
        ids = [o["id"] for o in listed]
        assert sorted(ids) == sorted([a["id"], b["id"]])
        keyed = [(o["created_at"], o["id"]) for o in listed]
        assert keyed == sorted(keyed)

