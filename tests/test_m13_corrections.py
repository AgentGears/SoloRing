"""M13 source-review correction regressions (review round 1, B1/B3/B4/C7)."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from tests.test_m13_binding import (
    _adopt,
    _approved_world,
    _binding_base,
    _interpretation,
    _publish,
)
from tests.m13_seed import make_composition, make_entity, mint, publish
from tests.test_m13_shot_capture import (
    _capture,
    _full_m13_world,
    _select_binding,
)


async def test_correction_b1_issue_candidate_not_current_complete(client):
    """B1 — 0 A4 targets → one new eligible EntityTrack with the
    interpretation absent: the stored zero-entry binding stays
    hash-identical, but current-completeness MUST become false; selection
    rejects and capture blocks (frozen §§10.3/13.1/14.2)."""
    b = await _binding_base(client, tag=b"corr-b1")
    from tests.m13_seed import make_entity

    eid = await make_entity(client, b["project_id"])
    await _adopt(client, b["composition_id"], b["occurrences"][0],
                 {"kind": "creative_entity", "creative_entity_id": eid})
    w = await _approved_world(client, b["project_id"])
    # NO interpretation: the CE subject stays composition-owned (0
    # targets), so the binding publishes with zero entries
    pr = await _publish(client, b["C"], w["revision"]["id"])
    assert pr.status_code == 201, pr.text
    binding_id = pr.json()["binding_id"]
    assert pr.json()["entries"] == []

    # select + verify currently complete
    from tests.test_m13_shot_capture import _shot_for

    shot_id = await _shot_for(client, b["project_id"])
    r = await client.put(
        f"/shots/{shot_id}/production-world-selection",
        json={"binding_id": binding_id, "expected_binding_id": None})
    assert r.status_code == 200, r.text
    out = (await client.get(
        f"/shots/{shot_id}/production-world")).json()
    assert out["binding_current_complete"] is True

    # the interleave: a new eligible EntityTrack appears — one A4 target,
    # interpretation still absent → candidate NOT bindable, entry set
    # unchanged → hash identical. Current-complete must flip FALSE.
    r = await client.post(f"/spatial-worlds/{w['world']['id']}/tracks",
                          json={"entity_id": eid, "requirement": "required"})
    assert r.status_code == 201, r.text
    out = (await client.get(
        f"/shots/{shot_id}/production-world")).json()
    assert out["binding_current_complete"] is False, out
    assert out["ready"] is False
    assert out["stale_details"][0]["code"] == (
        "BINDING_STALE_PLACEMENT_SET_CHANGED")
    assert out["stale_details"][0]["reason"] == (
        "current_candidate_not_bindable")

    # capture blocks on the stale binding
    from soloring.errors import SoloRingError

    with pytest.raises(SoloRingError) as ei:
        await _capture(client, shot_id)
    assert ei.value.code == "PRODUCTION_WORLD_BINDING_STALE"

    # a NEW selection of the same binding is rejected under the fence
    r = await client.request(
        "DELETE", f"/shots/{shot_id}/production-world-selection",
        json={"expected_binding_id": binding_id})
    assert r.status_code == 200, r.text
    r = await client.put(
        f"/shots/{shot_id}/production-world-selection",
        json={"binding_id": binding_id, "expected_binding_id": None})
    assert r.status_code == 409, r.text
    assert r.json()["error_code"] == "PRODUCTION_WORLD_BINDING_STALE"


async def test_correction_b3_historical_get_rejects_corruption(client):
    """B3 — the historical GET itself (not recapture) rejects: corrupted
    captured child, corrupted embedded pack hash, and pack/child drift."""
    b, sel, revision = await _captured(client, tag=b"corr-b3")
    engine = client._transport.app.state.engine
    url = f"/shot-revisions/{revision.id}/production-world"

    # 1. corrupt a captured spatial child value
    async with engine.connect() as conn:
        await conn.execute(text(
            "UPDATE shot_revision_production_instance_spatial_states "
            "SET x_mm = 424242 WHERE shot_revision_id = :r"),
            {"r": revision.id})
        await conn.commit()
    r = await client.get(url)
    assert r.status_code == 500 and r.json()[
        "error_code"] == "INTERNAL_INVARIANT_VIOLATION"
    async with engine.connect() as conn:
        await conn.execute(text(
            "UPDATE shot_revision_production_instance_spatial_states "
            "SET x_mm = 100 WHERE shot_revision_id = :r"),
            {"r": revision.id})
        await conn.commit()
    assert (await client.get(url)).status_code == 200

    # 2. corrupt the stored production_world_hash on the parent row
    async with engine.connect() as conn:
        await conn.execute(text(
            "UPDATE shot_revision_production_worlds SET "
            "production_world_hash = :h WHERE shot_revision_id = :r"),
            {"h": "0" * 64, "r": revision.id})
        await conn.commit()
    r = await client.get(url)
    assert r.status_code == 500 and r.json()[
        "error_code"] == "INTERNAL_INVARIANT_VIOLATION"
    async with engine.connect() as conn:
        from soloring.production_world.resolver import (
            production_world_hash as pwh,
        )

        snap = (await conn.execute(text(
            "SELECT snapshot_json FROM shot_revisions WHERE id = :r"),
            {"r": revision.id})).scalar_one()
        pack = json.loads(snap)["production_world"]
        await conn.execute(text(
            "UPDATE shot_revision_production_worlds SET "
            "production_world_hash = :h WHERE shot_revision_id = :r"),
            {"h": pwh(pack), "r": revision.id})
        await conn.commit()
    assert (await client.get(url)).status_code == 200

    # 3. drift the embedded pack away from the immutable binding: mutate
    # the snapshot's embedded binding value (breaks both the snapshot
    # hash and the binding equality) — re-pin the hash so the failure is
    # specifically the embedded/immutable binding comparison
    async with engine.connect() as conn:
        snap = json.loads((await conn.execute(text(
            "SELECT snapshot_json FROM shot_revisions WHERE id = :r"),
            {"r": revision.id})).scalar_one())
        pack = snap["production_world"]
        pack["binding"]["value"]["subjects"] = []
        snap["production_world"] = pack
        from soloring.domain.canonical import (
            canonical_hash,
            canonical_json_str as cjs,
        )

        new_json = cjs(snap)
        await conn.execute(text(
            "UPDATE shot_revisions SET snapshot_json = :sj, "
            "snapshot_hash = :sh WHERE id = :r"),
            {"sj": new_json, "sh": canonical_hash(snap),
             "r": revision.id})
        await conn.execute(text(
            "UPDATE shot_revision_production_worlds SET "
            "production_world_hash = :h WHERE shot_revision_id = :r"),
            {"h": pwh(pack), "r": revision.id})
        await conn.commit()
    r = await client.get(url)
    assert r.status_code == 500, r.text
    assert r.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"


async def _captured(client, *, tag):
    b = await _full_m13_world(client, tag=tag)
    sel = await _select_binding(client, b)
    revision, _ = await _capture(client, b["shot"])
    return b, sel, revision


async def test_correction_b4_patch_surface(client):
    """B4 — the three frozen PATCH endpoints work with M10/M7 PATCH
    semantics; the selection PUT returns the resolver status projection."""
    b = await _full_m13_world(client, tag=b"corr-b4")
    sel = await _select_binding(client, b)
    cid, oid, track = (sel["cid"], sel["occurrence_id"], sel["track"])
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        seq = (await conn.execute(text(
            "SELECT id FROM sequences WHERE project_id = :p "
            "ORDER BY position LIMIT 1"), {"p": b["pid"]})).scalar_one()

    # PI feature + transition, then PATCH the transition's boundary/value
    r = await client.post(f"/production-instances/{oid}/features",
                          json={"key": "fallen", "kind": "status",
                                "value_type": "text", "name": "Fallen"})
    fid = r.json()["id"]
    r = await client.post(
        f"/production-instance-features/{fid}/transitions",
        json={"anchor_type": "sequence", "anchor_id": seq,
              "boundary": "start", "operation": "set", "value": "down"})
    ftid = r.json()["id"]
    r = await client.patch(
        f"/production-instance-feature-transitions/{ftid}",
        json={"boundary": "end", "value": "up"})
    assert r.status_code == 200, r.text
    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT boundary, value_json FROM "
            "production_instance_feature_transitions WHERE id = :t"),
            {"t": ftid})).first()
    assert row.boundary == "end" and json.loads(row.value_json) == "up"

    # PATCH the PI track requirement
    r = await client.patch(
        f"/production-instance-spatial-tracks/{track}",
        json={"requirement": "optional"})
    assert r.status_code == 200, r.text
    r = await client.get(
        f"/production-instance-spatial-tracks/{track}")
    assert r.json()["requirement"] == "optional"
    r = await client.patch(
        f"/production-instance-spatial-tracks/{track}",
        json={"requirement": "required"})
    assert r.status_code == 200

    # PATCH the PI spatial transition's transform
    stid = (await engine.connect()).execute(text(
        "SELECT id FROM production_instance_spatial_transitions WHERE "
        "spatial_track_id = :t LIMIT 1"), {"t": track}).scalar_one() \
        if False else None
    async with engine.connect() as conn:
        stid = (await conn.execute(text(
            "SELECT id FROM production_instance_spatial_transitions "
            "WHERE spatial_track_id = :t LIMIT 1"),
            {"t": track})).scalar_one()
    r = await client.patch(
        f"/production-instance-spatial-transitions/{stid}",
        json={"transform": {"translation_mm": [55, 0, 0],
                            "rotation_udeg": [0, 0, 0]}})
    assert r.status_code == 200, r.text
    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT x_mm FROM production_instance_spatial_transitions "
            "WHERE id = :t"), {"t": stid})).first()
    assert row.x_mm == 55

    # selection PUT returns the resolver-derived status projection
    sel_row = (await client.get(
        f"/shots/{b['shot']}/production-world-selection")).json()
    r = await client.put(
        f"/shots/{b['shot']}/production-world-selection",
        json={"binding_id": sel["binding_id"],
              "expected_binding_id": sel_row["binding_id"]})
    assert r.status_code == 200, r.text
    out = r.json()
    for key in ("binding_current_complete", "stale_details", "ready",
                "issues", "production_world", "production_world_hash"):
        assert key in out, key
    assert out["ready"] is True
    assert out["production_world_hash"] is not None
    get_out = (await client.get(
        f"/shots/{b['shot']}/production-world")).json()
    assert out == get_out  # the SAME projection as GET


async def test_correction_c7_shadow_pi_rows_are_corruption(client):
    """C7 — PI rows on a creative_entity-adopted bound subject are stored
    authority corruption: current resolution fails closed instead of
    consuming or silently ignoring them."""
    b = await _full_m13_world(client, tag=b"corr-c7")
    cid = await make_composition(client, b["pid"])
    m = await mint(client, cid, b["production_revision_id"], 0)
    await _adopt(client, cid, m["occurrence_id"],
                 {"kind": "production_instance"})
    eid = await make_entity(client, b["project_id"])
    m2 = await mint(client, cid, b["production_revision_id"], 1,
                    name="CE twin")
    await _adopt(client, cid, m2["occurrence_id"],
                 {"kind": "creative_entity", "creative_entity_id": eid})
    from tests.test_m13_binding import _approved_world as _aw

    w = await _aw(client, b["pid"], key="c7lobby")
    pub = await publish(client, cid, 2)
    pr = await _publish(client, pub["revision"]["revision_id"],
                        w["revision"]["id"])
    assert pr.status_code == 201, pr.text
    binding_id = pr.json()["binding_id"]
    ce_occurrence = m2["occurrence_id"]
    from tests.test_m13_shot_capture import _shot_for

    shot_id = await _shot_for(client, b["pid"])
    r = await client.put(
        f"/shots/{shot_id}/production-world-selection",
        json={"binding_id": binding_id, "expected_binding_id": None})
    assert r.status_code == 200, r.text
    # inject a shadow PI track for the CE-adopted occurrence
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        await conn.execute(text(
            "INSERT INTO production_instance_spatial_tracks (id, "
            "spatial_world_id, composition_id, occurrence_id, "
            "requirement, created_at, updated_at) VALUES "
            "(:i, :w, :c, :o, 'optional', '2026-01-01T00:00:00.000Z', "
            "'2026-01-01T00:00:00.000Z')"),
            {"i": "99999999-9999-9999-9999-999999999999",
             "w": w["world"]["id"], "c": cid,
             "o": ce_occurrence})
        await conn.commit()
    r = await client.get(f"/shots/{shot_id}/production-world")
    assert r.status_code == 500, r.text
    assert r.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"


# R2 correction regressions (review round 2: B1/B3/B4 negatives)


async def test_correction_r2_b1_m11_core_in_binding_verifier(client):
    """R2-B1 — the binding verifier runs the full M11 §10.1 semantics:
    a corrupted ProductionRevision snapshot (non-canonical bytes) fails
    the immutable reader even though the copied hash column matches."""
    import json as _json

    from soloring.errors import SoloRingError
    from tests.test_m13_binding import (
        _adopt,
        _approved_world,
        _binding_base,
        _interpretation,
        _publish,
    )

    b = await _binding_base(client, tag=b"r2-b1")
    cid = b["composition_id"]
    oid = b["occurrences"][0]
    await _adopt(client, cid, oid, {"kind": "production_instance"})
    await _interpretation(client, b["production_revision_id"])
    w = await _approved_world(client, b["project_id"])
    r = await client.post(
        f"/spatial-worlds/{w['world']['id']}/production-instance-tracks",
        json={"occurrence_id": oid, "requirement": "required"})
    assert r.status_code == 201
    pr = await _publish(client, b["C"], w["revision"]["id"])
    assert pr.status_code == 201, pr.text
    binding_id = pr.json()["binding_id"]

    engine = client._transport.app.state.engine
    # corrupt the PR snapshot into a NON-canonical encoding whose stored
    # hash column is re-pinned to the binding's copied hash — the §10.1
    # canonical-bytes check must fire (a hash-column comparison alone
    # would pass)
    async with engine.connect() as conn:
        snap = (await conn.execute(text(
            "SELECT snapshot_json FROM production_revisions WHERE id = :r"),
            {"r": b["production_revision_id"]})).scalar_one()
        parsed = _json.loads(snap)
        noncanon = _json.dumps(parsed, indent=2)  # not canonical form
        await conn.execute(text(
            "UPDATE production_revisions SET snapshot_json = :sj "
            "WHERE id = :r"),
            {"sj": noncanon, "r": b["production_revision_id"]})
        await conn.commit()

    from soloring.production_world.binding import read_binding
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    class _S:
        bind = engine

    import pytest
    with pytest.raises(SoloRingError) as ei:
        await read_binding(_S(), binding_id)
    assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"
    assert "canonical" in ei.value.message
    del factory


async def test_correction_r2_b3_position_gap_and_typed_value(client):
    """R2-B3 — the historical GET rejects a contiguous-position break
    and a self-consistent type/value corruption (generic hashes
    re-pinned)."""
    import hashlib
    import json as _json

    from tests.test_m13_history import _captured_world

    b, sel, revision = await _captured_world(client, tag=b"r2-b3")
    engine = client._transport.app.state.engine
    url = f"/shot-revisions/{revision.id}/production-world"

    # add a PI feature so a feature child exists to corrupt
    r = await client.post(
        f"/production-instances/{sel['occurrence_id']}/features",
        json={"key": "fallen", "kind": "status", "value_type": "integer",
              "name": "Fallen", "unit": "deg"})
    assert r.status_code == 201, r.text
    fid = r.json()["id"]
    async with engine.connect() as conn:
        seq = (await conn.execute(text(
            "SELECT id FROM sequences WHERE project_id = :p "
            "ORDER BY position LIMIT 1"), {"p": b["pid"]})).scalar_one()
    r = await client.post(
        f"/production-instance-features/{fid}/transitions",
        json={"anchor_type": "sequence", "anchor_id": seq,
              "boundary": "start", "operation": "set", "value": 5})
    assert r.status_code == 201, r.text
    # recapture so the feature child is persisted
    from tests.test_m13_shot_capture import _capture

    revision2, _ = await _capture(client, b["shot"])
    assert revision2.id != revision.id  # content changed
    url2 = f"/shot-revisions/{revision2.id}/production-world"
    assert (await client.get(url2)).status_code == 200

    # (a) position gap: shift the single row to position 3
    async with engine.connect() as conn:
        await conn.execute(text(
            "UPDATE shot_revision_production_instance_feature_states "
            "SET position = 3 WHERE shot_revision_id = :r"),
            {"r": revision2.id})
        await conn.commit()
    r = await client.get(url2)
    assert r.status_code == 500 and r.json()[
        "error_code"] == "INTERNAL_INVARIANT_VIOLATION"
    async with engine.connect() as conn:
        await conn.execute(text(
            "UPDATE shot_revision_production_instance_feature_states "
            "SET position = 0 WHERE shot_revision_id = :r"),
            {"r": revision2.id})
        await conn.commit()
    assert (await client.get(url2)).status_code == 200

    # (b) self-consistent type/value corruption: value_json "true" with
    # value_type integer, BOTH the row hash and the pack/snapshot hashes
    # re-pinned so only the typed grammar check can catch it
    bad = "true"
    bad_hash = hashlib.sha256(bad.encode("utf-8")).hexdigest()
    async with engine.connect() as conn:
        await conn.execute(text(
            "UPDATE shot_revision_production_instance_feature_states "
            "SET value_json = :vj, value_hash = :vh WHERE "
            "shot_revision_id = :r"),
            {"vj": bad, "vh": bad_hash, "r": revision2.id})
        # re-pin the snapshot pack + hashes to stay self-consistent
        from soloring.domain.canonical import (
            canonical_hash,
            canonical_json_str as cjs,
        )
        from soloring.production_world.resolver import (
            production_world_hash as pwh,
        )

        snap = _json.loads((await conn.execute(text(
            "SELECT snapshot_json FROM shot_revisions WHERE id = :r"),
            {"r": revision2.id})).scalar_one())
        snap["production_world"]["instance_feature_states"][0][
            "value"] = True
        snap["production_world"]["instance_feature_states"][0][
            "value_hash"] = bad_hash
        new_json = cjs(snap)
        await conn.execute(text(
            "UPDATE shot_revisions SET snapshot_json = :sj, "
            "snapshot_hash = :sh WHERE id = :r"),
            {"sj": new_json, "sh": canonical_hash(snap),
             "r": revision2.id})
        await conn.execute(text(
            "UPDATE shot_revision_production_worlds SET "
            "production_world_hash = :h WHERE shot_revision_id = :r"),
            {"h": pwh(snap["production_world"]),
             "r": revision2.id})
        await conn.commit()
    r = await client.get(url2)
    assert r.status_code == 500, r.text
    assert r.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"


async def test_correction_r2_b4_patch_matrix(client):
    """R2-B4 — full operation-transition matrix for both PATCH families:
    clear→set with an omitted payload is a stable semantic rejection;
    explicit nulls follow the M7/M10 predecessor rules."""
    from tests.test_m13_shot_capture import (
        _capture,
        _full_m13_world,
        _select_binding,
    )

    b = await _full_m13_world(client, tag=b"r2-b4")
    sel = await _select_binding(client, b)
    engine = client._transport.app.state.engine

    # --- PI feature transition matrix ---
    r = await client.post(
        f"/production-instances/{sel['occurrence_id']}/features",
        json={"key": "fallen", "kind": "status", "value_type": "text",
              "name": "Fallen"})
    fid = r.json()["id"]
    async with engine.connect() as conn:
        seq = (await conn.execute(text(
            "SELECT id FROM sequences WHERE project_id = :p "
            "ORDER BY position LIMIT 1"), {"p": b["pid"]})).scalar_one()
    r = await client.post(
        f"/production-instance-features/{fid}/transitions",
        json={"anchor_type": "sequence", "anchor_id": seq,
              "boundary": "start", "operation": "clear"})
    ftid = r.json()["id"]

    # clear → set with omitted value: stable 422, no crash
    r = await client.patch(
        f"/production-instance-feature-transitions/{ftid}",
        json={"operation": "set"})
    assert r.status_code == 422, r.text
    assert "explicit value" in r.json()["message"]
    # clear → set with explicit null: rejected (value:null never accepted)
    r = await client.patch(
        f"/production-instance-feature-transitions/{ftid}",
        json={"operation": "set", "value": None})
    assert r.status_code == 422
    # clear → set with an explicit value succeeds
    r = await client.patch(
        f"/production-instance-feature-transitions/{ftid}",
        json={"operation": "set", "value": "down"})
    assert r.status_code == 200, r.text
    # set → set with omitted value preserves
    r = await client.patch(
        f"/production-instance-feature-transitions/{ftid}",
        json={"boundary": "end"})
    assert r.status_code == 200
    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT operation, value_json, boundary FROM "
            "production_instance_feature_transitions WHERE id = :t"),
            {"t": ftid})).first()
    assert row.operation == "set" and _json_loads(row.value_json) == "down"
    assert row.boundary == "end"
    # set → clear with an explicit value payload rejected
    r = await client.patch(
        f"/production-instance-feature-transitions/{ftid}",
        json={"operation": "clear", "value": "x"})
    assert r.status_code == 422

    # --- PI spatial transition matrix ---
    stid = None
    async with engine.connect() as conn:
        stid = (await conn.execute(text(
            "SELECT id FROM production_instance_spatial_transitions "
            "WHERE spatial_track_id = :t LIMIT 1"),
            {"t": sel["track"]})).scalar_one()
    # set → clear (omitted transform) then the matrix
    r = await client.patch(
        f"/production-instance-spatial-transitions/{stid}",
        json={"operation": "clear"})
    assert r.status_code == 200, r.text
    # clear → set with omitted transform: stable 422
    r = await client.patch(
        f"/production-instance-spatial-transitions/{stid}",
        json={"operation": "set"})
    assert r.status_code == 422, r.text
    assert "explicit complete transform" in r.json()["message"]
    # clear → set with transform:null rejected
    r = await client.patch(
        f"/production-instance-spatial-transitions/{stid}",
        json={"operation": "set", "transform": None})
    assert r.status_code == 422
    # clear → set with explicit transform succeeds (+180° canonicalizes)
    r = await client.patch(
        f"/production-instance-spatial-transitions/{stid}",
        json={"operation": "set",
              "transform": {"translation_mm": [1, 2, 3],
                            "rotation_udeg": [180000000, 0, 0]}})
    assert r.status_code == 200, r.text
    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT x_mm, yaw_udeg FROM "
            "production_instance_spatial_transitions WHERE id = :t"),
            {"t": stid})).first()
    assert row.x_mm == 1 and row.yaw_udeg == -180000000
    # set → set with omitted transform preserves
    r = await client.patch(
        f"/production-instance-spatial-transitions/{stid}",
        json={"boundary": "end"})
    assert r.status_code == 200
    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT x_mm, boundary FROM "
            "production_instance_spatial_transitions WHERE id = :t"),
            {"t": stid})).first()
    assert row.x_mm == 1 and row.boundary == "end"


def _json_loads(v):
    import json

    return json.loads(v)
