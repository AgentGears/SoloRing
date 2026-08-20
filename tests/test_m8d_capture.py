"""M8D — immutable Shot capture and history (frozen plan §§53–60; M8D
gate incl. §89–§91 critical tests)."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from soloring.domain import revisions as revision_svc
from tests.test_m8a_visual import (
    _entity_with_revision,
    _facet,
    _feature,
    _seed_project,
)
from tests.test_m8b_curation import _assets
from tests.test_m8c_resolver import (
    _approve_anchor,
    _depend,
    _topology,
)


async def _visual_fixture(client, factory, engine, pid, with_feature=False):
    eva, rev1 = await _entity_with_revision(client, factory, pid)
    assets = await _assets(engine, pid, 2)
    f_face = await _facet(client, pid, "entity", entity_id=eva["id"],
                          facet_key="face")
    r = await client.post(
        f"/visual-facets/{f_face['id']}/anchors",
        json={"entity_revision_id": rev1},
    )
    face_anchor = r.json()["id"]
    await _approve_anchor(
        client, face_anchor, assets, ["front", "side"]
    )
    seq, scene, shots = await _topology(client, factory, pid)
    await _depend(client, shots[0], [eva["id"]])
    return eva, rev1, assets, f_face, face_anchor, (seq, scene, shots)


async def _capture(factory, shot_id):
    async with factory() as s:
        return await revision_svc.capture_revision(s, shot_id)


async def _fetch(engine, sql, params=None):
    async with engine.connect() as conn:
        return (
            await conn.execute(text(sql), params or {})
        ).mappings().all()


async def test_schema4_over_schema2_base_and_normalized_projection(
    client, factory, engine,
):
    """Deps + NO M7 state + approved visual → schema 4 over the schema-2
    base; normalized rows exactly project the canonical bytes (§57)."""
    pid = await _seed_project(factory)
    eva, rev1, assets, f, anchor, (seq, scene, shots) = (
        await _visual_fixture(client, factory, engine, pid)
    )
    rev = await _capture(factory, shots[0])
    snap = json.loads(rev.snapshot_json)
    assert snap["schema_version"] == 4
    assert snap["visual_reference_pack"]["schema_version"] == 1
    assert len(snap["visual_reference_pack"]["anchors"]) == 1
    # The schema-2 continuity base is preserved exactly inside schema 4.
    assert snap["continuity"]["schema_version"] == 1

    anchors = await _fetch(
        engine,
        "SELECT position, visual_facet_id, visual_anchor_id, "
        "visual_anchor_revision_id FROM shot_revision_visual_anchors "
        "WHERE shot_revision_id = :r",
        {"r": rev.id},
    )
    assert len(anchors) == 1
    items = await _fetch(
        engine,
        "SELECT anchor_position, item_position, asset_id, role "
        "FROM shot_revision_visual_anchor_items "
        "WHERE shot_revision_id = :r",
        {"r": rev.id},
    )
    assert len(items) == 2
    roles = sorted(i["role"] for i in items)
    assert roles == ["primary", "supporting"]


async def test_schema4_over_schema3_base(client, factory, engine):
    pid = await _seed_project(factory)
    eva, rev1, assets, f, anchor, (seq, scene, shots) = (
        await _visual_fixture(client, factory, engine, pid)
    )
    feat = await _feature(client, eva["id"])
    await client.post(
        f"/continuity-features/{feat['id']}/transitions",
        json={"anchor_type": "scene", "anchor_id": scene,
              "boundary": "start", "operation": "set", "value": "fresh"},
    )
    rev = await _capture(factory, shots[0])
    snap = json.loads(rev.snapshot_json)
    assert snap["schema_version"] == 4
    assert snap["continuity"]["schema_version"] == 2
    assert snap["continuity"]["feature_states"]
    assert snap["visual_reference_pack"]["anchors"]


async def test_no_empty_schema4_lower_bytes_preserved(
    client, factory, engine,
):
    """§89: optional-only facets with nothing approved → exact lower
    schema bytes; no VisualFacets at all → exact lower bytes."""
    pid = await _seed_project(factory)
    eva, rev1 = await _entity_with_revision(client, factory, pid)
    f_opt = await _facet(
        client, pid, "entity", entity_id=eva["id"], facet_key="hair",
        requirement="optional",
    )
    seq, scene, shots = await _topology(client, factory, pid)
    await _depend(client, shots[0], [eva["id"]])

    rev_lower = await _capture(factory, shots[0])
    assert json.loads(rev_lower.snapshot_json)["schema_version"] == 2

    # Same shot with an APPROVED optional realization → schema 4.
    assets = await _assets(engine, pid, 1)
    r = await client.post(
        f"/visual-facets/{f_opt['id']}/anchors",
        json={"entity_revision_id": rev1},
    )
    await _approve_anchor(client, r.json()["id"], assets, ["side"])
    rev4 = await _capture(factory, shots[0])
    assert json.loads(rev4.snapshot_json)["schema_version"] == 4
    assert rev4.snapshot_hash != rev_lower.snapshot_hash

    # A shot with NO facets keeps exact schema 1/2/3 bytes (a fresh shot
    # with no deps captures schema 1).
    from soloring.api.schemas.shots import ShotCreate
    from soloring.domain import shots as shot_svc

    async with factory() as s:
        bare = (await shot_svc.create_shot(
            s, pid, ShotCreate(subject="y"))).id
    rev_bare = await _capture(factory, bare)
    assert json.loads(rev_bare.snapshot_json)["schema_version"] == 1
    assert rev_bare.continuity_spec_json is None


async def test_required_unresolved_blocks_capture_no_fallback(
    client, factory, engine,
):
    """§90: required facet unresolved → capture FAILS; no lower schema,
    no schema 4 with partial pack."""
    pid = await _seed_project(factory)
    eva, rev1 = await _entity_with_revision(client, factory, pid)
    await _facet(client, pid, "entity", entity_id=eva["id"])  # required
    seq, scene, shots = await _topology(client, factory, pid)
    await _depend(client, shots[0], [eva["id"]])

    with pytest.raises(Exception) as ei:
        await _capture(factory, shots[0])
    assert ei.value.code == "VISUAL_REALIZATION_REQUIRED"
    assert ei.value.status_code == 409
    rows = await _fetch(
        engine, "SELECT id FROM shot_revisions WHERE shot_id = :s",
        {"s": shots[0]},
    )
    assert rows == []


async def test_historical_isolation_current_changes_never_rewrite(
    client, factory, engine,
):
    """§60/§87: after capture, every current mutation (approve new rev,
    edit working set, change requirement, unapprove, soft-delete) leaves
    stored bytes + normalized rows untouched."""
    pid = await _seed_project(factory)
    eva, rev1, assets, f, anchor_id, (seq, scene, shots) = (
        await _visual_fixture(client, factory, engine, pid)
    )
    rev = await _capture(factory, shots[0])
    frozen = (
        await _fetch(
            engine,
            "SELECT snapshot_json, snapshot_hash, continuity_spec_json, "
            "continuity_spec_hash FROM shot_revisions WHERE id = :r",
            {"r": rev.id},
        )
    )[0]
    frozen_children = await _fetch(
        engine,
        "SELECT * FROM shot_revision_visual_anchors "
        "WHERE shot_revision_id = :r",
        {"r": rev.id},
    )
    frozen_items = await _fetch(
        engine,
        "SELECT * FROM shot_revision_visual_anchor_items "
        "WHERE shot_revision_id = :r",
        {"r": rev.id},
    )

    # Mutate current state: working edit + new revision + approve it.
    detail = (await client.get(f"/visual-anchors/{anchor_id}")).json()
    old_rev = detail["approved_revision_id"]
    await client.put(
        f"/visual-anchors/{anchor_id}/items",
        json={"items": [
            {"asset_id": assets[1], "role": "primary",
             "view_key": "new-hero"},
        ]},
    )
    r = await client.post(f"/visual-anchors/{anchor_id}/revisions")
    new_rev = r.json()["id"]
    await client.post(
        f"/visual-anchor-revisions/{new_rev}/approve",
        json={"expected_approved_revision_id": old_rev},
    )
    await client.patch(
        f"/visual-facets/{f['id']}", json={"requirement": "optional"}
    )

    now = (
        await _fetch(
            engine,
            "SELECT snapshot_json, snapshot_hash, continuity_spec_json, "
            "continuity_spec_hash FROM shot_revisions WHERE id = :r",
            {"r": rev.id},
        )
    )[0]
    assert dict(now) == dict(frozen)
    assert (
        await _fetch(
            engine,
            "SELECT * FROM shot_revision_visual_anchors "
            "WHERE shot_revision_id = :r",
            {"r": rev.id},
        )
        == frozen_children
    )
    assert (
        await _fetch(
            engine,
            "SELECT * FROM shot_revision_visual_anchor_items "
            "WHERE shot_revision_id = :r",
            {"r": rev.id},
        )
        == frozen_items
    )

    # A NEW capture observes the new authority (schema 4, new hash).
    rev2 = await _capture(factory, shots[0])
    assert rev2.id != rev.id
    assert rev2.snapshot_hash != rev.snapshot_hash


async def test_visual_reuse_integrity_corruption_loop(
    client, factory, engine,
):
    """§57 reuse: corrupted visual projection on an existing schema-4
    revision → INTERNAL_INVARIANT_VIOLATION; restore → convergence."""
    from soloring.errors import SoloRingError

    pid = await _seed_project(factory)
    eva, rev1, assets, f, anchor_id, (seq, scene, shots) = (
        await _visual_fixture(client, factory, engine, pid)
    )
    rev = await _capture(factory, shots[0])
    again = await _capture(factory, shots[0])
    assert again.id == rev.id  # convergence

    # Corrupt one normalized anchor row (UPDATE, never DELETE).
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE shot_revision_visual_anchors SET facet_key = 'bad' "
                "WHERE shot_revision_id = :r"
            ),
            {"r": rev.id},
        )
    async with factory() as s:
        with pytest.raises(SoloRingError) as ei:
            await revision_svc.capture_revision(s, shots[0])
        assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE shot_revision_visual_anchors SET facet_key = "
                "'face' WHERE shot_revision_id = :r"
            ),
            {"r": rev.id},
        )
    final = await _capture(factory, shots[0])
    assert final.id == rev.id


async def test_exact_rerun_with_m8_resolver_disabled(
    client, factory, engine, settings,
):
    """§59/APR-025: rerun succeeds with BOTH M7 resolvers AND the M8
    visual resolver disabled; historical captured authority is used."""
    from soloring.executors.fake import FakeExecutor
    from soloring.worker import execution as worker_execution
    from soloring.worker.ownership import acquire_worker_lease
    from tests.conftest import seed_reference_asset
    from soloring.api.schemas.references import ReferenceInput
    from soloring.domain import references as ref_svc

    pid = await _seed_project(factory)
    eva, rev1, assets, f, anchor_id, (seq, scene, shots) = (
        await _visual_fixture(client, factory, engine, pid)
    )
    aid, _bh = await seed_reference_asset(engine, pid)
    async with factory() as s:
        await ref_svc.replace_references(
            s, shots[0], [ReferenceInput(asset_id=aid, role="reference")]
        )

    await acquire_worker_lease(engine, "w-m8", 30)
    genA = (await client.post(f"/shots/{shots[0]}/generations")).json()
    assert (await worker_execution.process_next_generation(
        engine, settings, "w-m8", FakeExecutor())) == "succeeded"
    revX = genA["shot_revision_id"]
    snap = json.loads(
        (await _fetch(
            engine, "SELECT snapshot_json FROM shot_revisions "
            "WHERE id = :r", {"r": revX},
        ))[0]["snapshot_json"]
    )
    assert snap["schema_version"] == 4

    # Radically mutate current visual authority (legal teardown).
    detail = (await client.get(f"/visual-anchors/{anchor_id}")).json()
    approved = detail["approved_revision_id"]
    await client.post(
        f"/visual-anchors/{anchor_id}/unapprove",
        json={"expected_approved_revision_id": approved},
    )

    import soloring.continuity.state as state_mod
    import soloring.visual.resolver as resolver_mod

    async def _forbidden(*args, **kwargs):
        raise AssertionError(
            "current-state resolver invoked during Exact Rerun"
        )

    of = state_mod.resolve_effective_feature_state
    orl = state_mod.resolve_effective_relation_state
    ov = resolver_mod.resolve_visual_reference_pack_async
    state_mod.resolve_effective_feature_state = _forbidden
    state_mod.resolve_effective_relation_state = _forbidden
    resolver_mod.resolve_visual_reference_pack_async = _forbidden
    try:
        r = await client.post(f"/generations/{genA['id']}/rerun")
        assert r.status_code == 202, r.text
        assert r.json()["shot_revision_id"] == revX
    finally:
        state_mod.resolve_effective_feature_state = of
        state_mod.resolve_effective_relation_state = orl
        resolver_mod.resolve_visual_reference_pack_async = ov


async def test_blob_retention_via_restrictive_fks(client, factory, engine):
    """§91: referenced Asset/Blob deletion rejected by the FK graph."""
    pid = await _seed_project(factory)
    eva, rev1, assets, f, anchor_id, (seq, scene, shots) = (
        await _visual_fixture(client, factory, engine, pid)
    )
    rev = await _capture(factory, shots[0])
    asset_id = assets[0]
    blob_hash = (
        await _fetch(
            engine, "SELECT blob_hash FROM assets WHERE id = :a",
            {"a": asset_id},
        )
    )[0]["blob_hash"]
    for sql, params in (
        ("DELETE FROM assets WHERE id = :a", {"a": asset_id}),
        ("DELETE FROM blobs WHERE hash = :h", {"h": blob_hash}),
    ):
        with pytest.raises(Exception):
            async with engine.begin() as conn:
                await conn.execute(text(sql), params)
