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
