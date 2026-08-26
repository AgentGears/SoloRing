"""M10D-r4 source-gate corrections — P0-R3-1 / P0-R3-2.

P0-R3-1: a real schema-5 capture WITHOUT M8 authority returns
historical visual == null (the legal M8-absent cell) while spatial
provenance remains complete. Schema 4 without the mandatory pack is
corruption.

P0-R3-2: the four outer-snapshot corruption cells each run against a
FRESH valid revision — no sequential-mutation ordering dependence. The
hash-disagreement cell starts from a valid canonical snapshot S with
stored hash H(S), changes a hash-bearing value, leaves the hash, and
proves the read fails on the bytes/hash comparison (not on an earlier
branch). A fifth cell proves canonical-BYTE disagreement independently:
semantically identical value stored as noncanonical JSON with the
correct hash still fails.
"""
import json
import uuid

import pytest
from sqlalchemy import text

from soloring.domain import revisions as rev_svc

from tests.test_m10d_resolver import _full_fixture, fs


async def _fresh_schema5(factory):
    seed = await _full_fixture(factory)
    revision = await rev_svc.capture_revision(fs(factory), seed["shot"])
    snap = json.loads(revision.snapshot_json)
    assert snap["schema_version"] == 5
    assert "visual_reference_pack" not in snap  # legal M8-absent cell
    return seed, revision


async def test_schema5_without_m8_visual_null_spatial_intact(factory,
                                                             client):
    """P0-R3-1."""
    seed, revision = await _fresh_schema5(factory)
    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["spatial"] is not None
    assert body["spatial"]["world"]["spatial_world_id"] == \
        seed["world"]["id"]
    # the legal M8-absent cell: visual is NULL — never a fabricated
    # {hash: null, anchors: []} projection
    assert body["visual"] is None


async def test_schema4_missing_pack_is_corruption(factory, client):
    """Schema 4 without its mandatory visual_reference_pack is
    corruption (invariant), not the absent cell."""
    seed = await _full_fixture(factory)
    revision = await rev_svc.capture_revision(fs(factory), seed["shot"])
    snap = json.loads(revision.snapshot_json)
    assert "visual_reference_pack" not in snap  # schema-5 M8-absent base
    snap["schema_version"] = 4  # fabricate the mandatory-pack shape
    # (the pack key is deliberately absent — the schema-4 corruption)
    from soloring.domain.canonical import (canonical_hash,
                                           canonical_json_str)
    async with factory() as s:
        async with s.begin():
            await s.execute(text(
                "UPDATE shot_revisions SET snapshot_json = :j, "
                "snapshot_hash = :h WHERE id = :r"),
                {"j": canonical_json_str(snap),
                 "h": canonical_hash(snap), "r": revision.id})
    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 500
    assert r.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"


async def _assert_invariant(client, rid):
    r = await client.get(f"/shot-revisions/{rid}/continuity")
    assert r.status_code == 500, r.text
    assert r.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"


async def test_outer_snapshot_corruption_cells_fresh_revisions(factory,
                                                               client):
    """P0-R3-2: each cell starts from a FRESH valid revision — no
    sequential-mutation ordering dependence."""
    # cell 1: malformed JSON
    _seed, rev1 = await _fresh_schema5(factory)
    async with factory() as s:
        async with s.begin():
            await s.execute(text(
                "UPDATE shot_revisions SET snapshot_json = 'not json' "
                "WHERE id = :r"), {"r": rev1.id})
    await _assert_invariant(client, rev1.id)

    # cell 2: non-object container
    _seed2, rev2 = await _fresh_schema5(factory)
    async with factory() as s:
        async with s.begin():
            await s.execute(text(
                "UPDATE shot_revisions SET snapshot_json = '[1,2,3]' "
                "WHERE id = :r"), {"r": rev2.id})
    await _assert_invariant(client, rev2.id)

    # cell 3: illegal schema version
    _seed3, rev3 = await _fresh_schema5(factory)
    async with factory() as s:
        async with s.begin():
            await s.execute(text(
                "UPDATE shot_revisions SET snapshot_json = :j "
                "WHERE id = :r"),
                {"j": json.dumps({"schema_version": 9}),
                 "r": rev3.id})
    await _assert_invariant(client, rev3.id)


async def test_hash_disagreement_on_valid_shape_fails(factory, client):
    """P0-R3-2 core cell: start from a VALID canonical snapshot S with
    stored hash H(S); change a hash-bearing value; leave the hash; the
    read must fail on the bytes/hash comparison — the schema version is
    legal and the JSON decodes, so no earlier branch can absorb it."""
    from soloring.domain.canonical import canonical_json_str

    seed, revision = await _fresh_schema5(factory)
    async with factory() as s:
        row = (await s.execute(text(
            "SELECT snapshot_json FROM shot_revisions WHERE id = :r"),
            {"r": revision.id})).scalar_one()
    snap = json.loads(row)
    # legal schema 5, decodable object — mutate one hash-bearing value
    snap["spatial_continuity"]["shot_plan"]["camera"]["focal_length_um"] \
        = 99000
    async with factory() as s2:
        async with s2.begin():
            # store the tampered bytes; snapshot_hash stays H(S)
            await s2.execute(text(
                "UPDATE shot_revisions SET snapshot_json = :j "
                "WHERE id = :r"),
                {"j": canonical_json_str(snap), "r": revision.id})
    await _assert_invariant(client, revision.id)


async def test_noncanonical_bytes_with_correct_hash_fails(factory, client):
    """Companion cell: semantically identical value stored as
    NONCANONICAL JSON while retaining the correct canonical hash — the
    canonical-bytes comparison itself fails."""
    seed, revision = await _fresh_schema5(factory)
    async with factory() as s:
        row = (await s.execute(text(
            "SELECT snapshot_json FROM shot_revisions WHERE id = :r"),
            {"r": revision.id})).scalar_one()
    # same object, noncanonical formatting (spaces + reordered keys)
    noncanonical = json.dumps(json.loads(row), indent=2, sort_keys=False)
    assert noncanonical != row
    async with factory() as s2:
        async with s2.begin():
            await s2.execute(text(
                "UPDATE shot_revisions SET snapshot_json = :j "
                "WHERE id = :r"),
                {"j": noncanonical, "r": revision.id})
    await _assert_invariant(client, revision.id)
