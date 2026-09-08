"""M13 spatial-interpretation proofs (frozen R3 §30.2 M13-INTERP:01-09)."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from tests.m13_seed import NOW, seed_base, seed_second_revision

TRANSFORM = {"translation_mm": [10, -20, 30],
             "rotation_udeg": [0, 0, 0]}
BODY = {"realization_local_to_subject_local": TRANSFORM}


async def _create(client, prid, body=BODY):
    r = await client.post(
        f"/production-revisions/{prid}/spatial-interpretation", json=body)
    return r


async def test_m13_interp_01(client):
    """M13-INTERP:01 — canonical schema-1 golden bytes/hash."""
    base = await seed_base(client, tag=b"m13-interp-01")
    prid = base["production_revision_id"]
    r = await _create(client, prid)
    assert r.status_code == 201, r.text
    out = r.json()
    # golden canonical bytes: canonical JSON sorts keys, tight separators
    from soloring.domain.canonical import canonical_json_str
    from soloring.production_world.canonical import COORDINATE_SYSTEM
    expected = {
        "schema_version": 1,
        "production_revision_id": prid,
        "production_revision_hash": None,  # filled below from parents
        "retained_blob_hash": base["blob_hash"],
        "coordinate_system": COORDINATE_SYSTEM,
        "origin_semantics": "subject_local",
        "realization_local_to_subject_local": {
            "translation_mm": [10, -20, 30],
            "rotation_udeg": [0, 0, 0]},
    }
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT interpretation_json, interpretation_hash "
            "FROM production_revision_spatial_interpretations "
            "WHERE production_revision_id = :r"), {"r": prid})).first()
        snap = (await conn.execute(text(
            "SELECT snapshot_hash FROM production_revisions WHERE id = :r"),
            {"r": prid})).scalar_one()
    expected["production_revision_hash"] = snap
    golden = canonical_json_str(expected)
    assert row.interpretation_json == golden
    import hashlib
    assert row.interpretation_hash == hashlib.sha256(
        golden.encode("utf-8")).hexdigest()
    assert out["interpretation_hash"] == row.interpretation_hash
    assert out["coordinate_system"] == COORDINATE_SYSTEM


async def test_m13_interp_02(client):
    """M13-INTERP:02 — M10 basis/unit/rotation constants are server-owned."""
    base = await seed_base(client, tag=b"m13-interp-02")
    prid = base["production_revision_id"]
    # the caller cannot select or override any coordinate constant
    bad = {"realization_local_to_subject_local": TRANSFORM,
           "coordinate_system": {"handedness": "left"}}
    r = await _create(client, prid, bad)
    assert r.status_code == 422, r.text
    from soloring.production_world.canonical import COORDINATE_SYSTEM
    from soloring.spatial.math import UDEG_MIN
    assert COORDINATE_SYSTEM["linear_unit"] == "millimeter"
    assert COORDINATE_SYSTEM["rotation_unit"] == "microdegree"
    assert COORDINATE_SYSTEM["linear_scale_num"] == 1
    assert COORDINATE_SYSTEM["linear_scale_den"] == 1
    assert UDEG_MIN == -180_000_000


async def test_m13_interp_03(client):
    """M13-INTERP:03 — integral/JS-safe transform grammar."""
    base = await seed_base(client, tag=b"m13-interp-03")
    prid = base["production_revision_id"]
    for bad_vec in ([1.0, 0, 0], [True, 0, 0], [1, 2], [1, 2, 3, 4],
                    [2**53, 0, 0]):
        r = await _create(client, prid, {
            "realization_local_to_subject_local": {
                "translation_mm": bad_vec, "rotation_udeg": [0, 0, 0]}})
        assert r.status_code == 422, (bad_vec, r.text)
    r = await _create(client, prid, {
        "realization_local_to_subject_local": {
            "translation_mm": [0, 0, 0], "rotation_udeg": [1.5, 0, 0]}})
    assert r.status_code == 422


async def test_m13_interp_04(client):
    """M13-INTERP:04 — exactly +180deg canonicalizes to -180deg; stored
    +180deg is corruption."""
    base = await seed_base(client, tag=b"m13-interp-04")
    prid = base["production_revision_id"]
    r = await _create(client, prid, {
        "realization_local_to_subject_local": {
            "translation_mm": [0, 0, 0],
            "rotation_udeg": [180_000_000, 0, 0]}})
    assert r.status_code == 201, r.text
    assert r.json()["realization_local_to_subject_local"][
        "rotation_udeg"][0] == -180_000_000
    # corrupting the stored scalar to the raw +180deg form fails closed
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        await conn.execute(text(
            "UPDATE production_revision_spatial_interpretations "
            "SET yaw_udeg = 180000000 WHERE production_revision_id = :r"),
            {"r": prid})
        await conn.commit()
    r = await client.get(
        f"/production-revisions/{prid}/spatial-interpretation")
    assert r.status_code == 500, r.text
    assert r.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"


async def test_m13_interp_05(client):
    """M13-INTERP:05 — identical create converges."""
    base = await seed_base(client, tag=b"m13-interp-05")
    prid = base["production_revision_id"]
    r1 = await _create(client, prid)
    assert r1.status_code == 201
    r2 = await _create(client, prid)
    assert r2.status_code == 200, r2.text
    assert r2.json()["interpretation_hash"] == r1.json()["interpretation_hash"]
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM "
            "production_revision_spatial_interpretations "
            "WHERE production_revision_id = :r"), {"r": prid})).scalar_one()
    assert n == 1


async def test_m13_interp_06(client):
    """M13-INTERP:06 — conflicting second create rejects."""
    base = await seed_base(client, tag=b"m13-interp-06")
    prid = base["production_revision_id"]
    assert (await _create(client, prid)).status_code == 201
    r = await _create(client, prid, {
        "realization_local_to_subject_local": {
            "translation_mm": [999, 0, 0], "rotation_udeg": [0, 0, 0]}})
    assert r.status_code == 409, r.text


async def test_m13_interp_07(client):
    """M13-INTERP:07 — M11 ProductionRevision bytes remain unchanged."""
    base = await seed_base(client, tag=b"m13-interp-07")
    prid = base["production_revision_id"]
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        before = (await conn.execute(text(
            "SELECT snapshot_json, snapshot_hash FROM production_revisions "
            "WHERE id = :r"), {"r": prid})).first()
    assert (await _create(client, prid)).status_code == 201
    async with engine.connect() as conn:
        after = (await conn.execute(text(
            "SELECT snapshot_json, snapshot_hash FROM production_revisions "
            "WHERE id = :r"), {"r": prid})).first()
    assert (before.snapshot_json, before.snapshot_hash) == (
        after.snapshot_json, after.snapshot_hash)


async def test_m13_interp_08(client):
    """M13-INTERP:08 — stored JSON/hash/projection corruption fails closed."""
    base = await seed_base(client, tag=b"m13-interp-08")
    prid = base["production_revision_id"]
    assert (await _create(client, prid)).status_code == 201
    engine = client._transport.app.state.engine

    async def _corrupt(sql, params):
        async with engine.connect() as conn:
            await conn.execute(text(sql), params)
            await conn.commit()
        r = await client.get(
            f"/production-revisions/{prid}/spatial-interpretation")
        assert r.status_code == 500, r.text
        assert r.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"
        # restore for the next mutation
        async with engine.connect() as conn:
            await conn.execute(text(
                "DELETE FROM production_revision_spatial_interpretations "
                "WHERE production_revision_id = :r"), {"r": prid})
            await conn.commit()
        await _create(client, prid)

    # non-canonical stored JSON (unknown key, non-canonical bytes)
    await _corrupt(
        "UPDATE production_revision_spatial_interpretations SET "
        "interpretation_json = :js WHERE production_revision_id = :r",
        {"js": '{"schema_version":1,"z":1}', "r": prid})
    # hash mismatch
    await _corrupt(
        "UPDATE production_revision_spatial_interpretations SET "
        "interpretation_hash = "
        "'0000000000000000000000000000000000000000000000000000000000000000' "
        "WHERE production_revision_id = :r", {"r": prid})
    # projection mismatch
    await _corrupt(
        "UPDATE production_revision_spatial_interpretations SET x_mm = 424242 "
        "WHERE production_revision_id = :r", {"r": prid})


async def test_m13_interp_09(client):
    """M13-INTERP:09 — provenance equals exact M11 stored parents; an
    unclosed revision is rejected."""
    base = await seed_base(client, tag=b"m13-interp-09")
    prid = base["production_revision_id"]
    r = await _create(client, prid)
    assert r.status_code == 201
    out = r.json()
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        snap = (await conn.execute(text(
            "SELECT snapshot_hash FROM production_revisions WHERE id = :r"),
            {"r": prid})).scalar_one()
        bh = (await conn.execute(text(
            "SELECT blob_hash FROM production_revision_closures "
            "WHERE production_revision_id = :r"), {"r": prid})).scalar_one()
    assert out["production_revision_hash"] == snap
    assert out["retained_blob_hash"] == bh

    # an unclosed revision cannot receive an interpretation
    prid2 = await seed_second_revision(client, base)
    async with engine.connect() as conn:
        await conn.execute(text(
            "DELETE FROM production_revision_closures "
            "WHERE production_revision_id = :r"), {"r": prid2})
        await conn.commit()
    r = await _create(client, prid2)
    assert r.status_code == 422, r.text
    # unknown revision is 404
    r = await _create(client, "ffffffff-ffff-ffff-ffff-ffffffffffff")
    assert r.status_code == 404, r.text
    assert r.json()["error_code"] == "PRODUCTION_REVISION_NOT_FOUND"
    # GET of an absent interpretation on a closed revision is the M13 404
    prid3 = await seed_second_revision(client, base, number=3)
    r = await client.get(
        f"/production-revisions/{prid3}/spatial-interpretation")
    assert r.status_code == 404, r.text
    assert r.json()["error_code"] == (
        "PRODUCTION_SPATIAL_INTERPRETATION_NOT_FOUND")
