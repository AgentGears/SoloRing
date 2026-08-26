"""M10D-r2 source-gate corrections — production/integrity blockers
P0-1/P0-2/P0-3/P0-4/P0-8 from the round-1 review.

P0-1: fixed placement conflicts with the APPLICABLE Track set (states ∪
absent) — clear winners and no-eligible-transition tracks both conflict.
P0-2: stored plan_json/plan_hash disagreement fails closed as invariant
corruption at resolution (never silently re-normalized).
P0-3: historical embedded-pack grammar failures normalize to
INTERNAL_INVARIANT_VIOLATION (no current-domain 4xx leakage).
P0-4: schema 1-4 history rejects stray rows in ALL THREE M10 child
families.
P0-8: schema-5-with-M8 history preserves captured visual provenance.
"""
import json
import uuid

import pytest
from sqlalchemy import text

from soloring.domain import revisions as rev_svc
from soloring.errors import ErrorCode, SoloRingError
from soloring.spatial import tracks as track_svc
from soloring.spatial import transitions as trans_svc
from soloring.spatial import worlds as world_svc

from tests.test_m10d_resolver import (
    CAM, EVA_T, _entities, _full_fixture, _shot, fs,
)


async def test_fixed_placement_conflicts_with_absent_applicable_track(
        factory, engine):
    """P0-1: an applicable Track is competing placement authority even
    when its temporal state is absent."""
    from soloring.continuity.snapshots import resolve_working_dependencies
    from soloring.spatial import resolver as r

    # case A: applicable optional Track with NO eligible transition
    seed = await _full_fixture(factory, eva_fixed=True)
    # eva is fixed; now add the applicable Track WITHOUT any transition
    eva = seed["ents"]["eva"][0]
    track = await track_svc.create_track(
        fs(factory), seed["world"]["id"], entity_id=eva,
        requirement="optional")
    async with engine.connect() as conn:
        deps = await resolve_working_dependencies(conn, seed["shot"])
        out = await r.resolve_spatial_continuity(
            conn, shot_id=seed["shot"], resolved_dependencies=deps)
    codes = [i.code for i in out.issues]
    assert ErrorCode.SPATIAL_ENTITY_PLACEMENT_CONFLICT in codes, \
        "no-transition applicable Track must conflict with fixed frame"
    # revision-mismatch suppression retained for the conflicted Entity
    for i in out.issues:
        if i.code == ErrorCode.SPATIAL_ENTITY_REVISION_MISMATCH:
            assert i.details.get("entity_id") != eva

    # case B: applicable Track whose winner is CLEAR
    seed2 = await _full_fixture(factory, eva_fixed=True)
    eva2 = seed2["ents"]["eva"][0]
    track2 = await track_svc.create_track(
        fs(factory), seed2["world"]["id"], entity_id=eva2,
        requirement="optional")
    seq = str(uuid.uuid4())
    async with factory() as s:
        async with s.begin():
            await s.execute(text(
                "INSERT INTO sequences (id, project_id, position, title) "
                "VALUES (:q, :p, (SELECT COALESCE(MAX(position),0)+1 FROM "
                "sequences WHERE project_id=:p), 'S2')"),
                {"q": seq, "p": seed2["pid"]})
    await trans_svc.create_transition(
        fs(factory), track2["id"], anchor_type="sequence",
        anchor_id=seq, boundary="start", operation="clear")
    async with engine.connect() as conn:
        deps = await resolve_working_dependencies(conn, seed2["shot"])
        out2 = await r.resolve_spatial_continuity(
            conn, shot_id=seed2["shot"], resolved_dependencies=deps)
    assert ErrorCode.SPATIAL_ENTITY_PLACEMENT_CONFLICT in \
        [i.code for i in out2.issues], \
        "clear-winner applicable Track must conflict with fixed frame"


async def test_stored_plan_hash_disagreement_fails_invariant(factory,
                                                             engine):
    """P0-2: canonical plan_json + wrong plan_hash is corruption."""
    from soloring.continuity.snapshots import resolve_working_dependencies
    from soloring.spatial import resolver as r

    seed = await _full_fixture(factory)
    async with factory() as s:
        async with s.begin():
            await s.execute(text(
                "UPDATE shot_spatial_plans SET plan_hash = :h "
                "WHERE shot_id = :q"),
                {"h": "0" * 64, "q": seed["shot"]})
    with pytest.raises(SoloRingError) as ei:
        async with engine.connect() as conn:
            deps = await resolve_working_dependencies(conn, seed["shot"])
            await r.resolve_spatial_continuity(
                conn, shot_id=seed["shot"], resolved_dependencies=deps)
    assert ei.value.code == ErrorCode.INTERNAL_INVARIANT_VIOLATION

    # bytes disagreement also fails (valid hash of DIFFERENT bytes)
    seed2 = await _full_fixture(factory)
    stored = json.loads((await _get_plan(factory, seed2["shot"]))[0])
    stored["camera"]["focal_length_um"] = 99000  # valid grammar
    async with factory() as s:
        async with s.begin():
            await s.execute(text(
                "UPDATE shot_spatial_plans SET plan_json = :j "
                "WHERE shot_id = :q"),
                {"j": json.dumps(stored), "q": seed2["shot"]})
    with pytest.raises(SoloRingError) as ei2:
        async with engine.connect() as conn:
            deps = await resolve_working_dependencies(conn, seed2["shot"])
            await r.resolve_spatial_continuity(
                conn, shot_id=seed2["shot"], resolved_dependencies=deps)
    assert ei2.value.code == ErrorCode.INTERNAL_INVARIANT_VIOLATION


async def _get_plan(factory, shot):
    async with factory() as s:
        row = (await s.execute(text(
            "SELECT plan_json FROM shot_spatial_plans WHERE shot_id = :q"),
            {"q": shot})).scalar_one()
    return row, None


async def test_historical_pack_corruption_is_invariant(factory, client):
    """P0-3: malformed embedded pack → 500 INTERNAL_INVARIANT_VIOLATION,
    never a current-domain 4xx."""
    seed = await _full_fixture(factory)
    revision = await rev_svc.capture_revision(fs(factory), seed["shot"])
    # corrupt the embedded pack inside snapshot_json (grammar-breaking)
    async with factory() as s:
        row = (await s.execute(text(
            "SELECT snapshot_json FROM shot_revisions WHERE id = :r"),
            {"r": revision.id})).scalar_one()
        snap = json.loads(row)
        snap["spatial_continuity"]["schema_version"] = 99
        await s.commit()
        async with s.begin():
            await s.execute(text(
                "UPDATE shot_revisions SET snapshot_json = :j "
                "WHERE id = :r"),
                {"j": json.dumps(snap), "r": revision.id})
    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 500
    assert r.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"


async def test_lower_schema_stray_children_in_all_families(factory, client):
    """P0-4: schema 1-4 with stray rows in track-states or plans is
    corruption, not a null projection."""
    pid = str(uuid.uuid4())
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO projects (id, name, created_at, updated_at) "
                "VALUES (:p, 'P', 't', 't')"), {"p": pid})
    plain = await _shot(factory, pid, [])
    rev = await rev_svc.capture_revision(fs(factory), plain)
    # stray PLAN child (world family was already covered in r1)
    async with factory() as s:
        async with s.begin():
            await s.execute(text(
                "INSERT INTO shot_revision_spatial_plans ("
                "shot_revision_id, plan_hash, plan_json) VALUES "
                "(:r, :h, :j)"),
                {"r": rev.id, "h": "1" * 64, "j": "{}"})
    r = await client.get(f"/shot-revisions/{rev.id}/continuity")
    assert r.status_code == 500
    assert r.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"
    # stray TRACK child (fresh session; ids from a second fixture seed)
    seed2 = await _full_fixture(factory)
    async with factory() as s:
        async with s.begin():
            await s.execute(text(
                "DELETE FROM shot_revision_spatial_plans WHERE "
                "shot_revision_id = :r"), {"r": rev.id})
            await s.execute(text(
                "INSERT INTO shot_revision_spatial_track_states ("
                "shot_revision_id, position, spatial_track_id, entity_id, "
                "entity_revision_id, requirement, x_mm, y_mm, z_mm, "
                "yaw_udeg, pitch_udeg, roll_udeg, source_transition_id, "
                "source_anchor_type, source_anchor_id, source_boundary) "
                "VALUES (:r, 0, :t, :e, :er, 'optional', 0,0,0,0,0,0, "
                ":tid, 'sequence', :a, 'start')"),
                {"r": rev.id, "t": seed2["track"]["id"],
                 "e": seed2["ents"]["eva"][0],
                 "er": seed2["ents"]["eva"][1],
                 "tid": (await trans_svc.list_transitions(
                     fs(factory), seed2["track"]["id"]))[0]["id"],
                 "a": str(uuid.uuid4())})
    r2 = await client.get(f"/shot-revisions/{rev.id}/continuity")
    assert r2.status_code == 500


async def test_schema5_with_m8_preserves_visual_provenance(factory, client):
    """P0-8: M7 + M8 + M10 -> schema 5 with visual_reference_pack, and
    the HISTORICAL projection keeps captured visual AND spatial
    provenance. Real M8 chain through the public API (house M8 test
    style): facet (entity target, optional) -> anchor bound to the
    exact semantic revision -> empty working set -> capture -> approve;
    then the real ShotRevision capture composes the schema-5+M8 cell."""
    seed = await _full_fixture(factory)
    pid = seed["pid"]
    eva, evarev = seed["ents"]["eva"]

    fr = await client.post(f"/projects/{pid}/visual-facets", json={
        "target_kind": "entity", "entity_id": eva,
        "facet_key": "wardrobe", "requirement": "optional"})
    assert fr.status_code == 201, fr.text
    facet_id = fr.json()["id"]
    ar = await client.post(f"/visual-facets/{facet_id}/anchors", json={
        "entity_revision_id": evarev})
    assert ar.status_code == 201, ar.text
    anchor_id = ar.json()["id"]
    # a real working item: Blob + reference Asset (M8 house seeding)
    from tests.conftest import seed_reference_asset
    from soloring.db.engine import create_soloring_engine
    from soloring.db.base import Base
    from soloring.settings import Settings
    from sqlalchemy.ext.asyncio import AsyncSession
    from soloring.assets.blob_store import BlobStore
    from soloring.settings import get_settings
    seed_engine = client._transport.app.state.engine
    asset_id, bh = await seed_reference_asset(seed_engine, pid)
    store = BlobStore(get_settings())
    path = store.path_for_hash(bh)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"m10d-r2-fixture-" + bh.encode())
    wr = await client.put(f"/visual-anchors/{anchor_id}/items", json={
        "items": [{"asset_id": asset_id, "role": "primary"}]})
    assert wr.status_code == 200, wr.text
    cr = await client.post(f"/visual-anchors/{anchor_id}/revisions")
    assert cr.status_code == 201, cr.text
    apr = await client.post(
        f"/visual-anchor-revisions/{cr.json()['id']}/approve",
        json={"expected_approved_revision_id": None})
    assert apr.status_code == 200, apr.text

    revision = await rev_svc.capture_revision(fs(factory), seed["shot"])
    snap = json.loads(revision.snapshot_json)
    assert snap["schema_version"] == 5
    assert "visual_reference_pack" in snap, \
        "non-empty approved M8 authority must ride inside schema 5"
    assert "spatial_continuity" in snap

    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["snapshot_schema_version"] == 5
    assert body["spatial"] is not None
    assert body["spatial"]["world"]["spatial_world_id"] == \
        seed["world"]["id"]
    assert "visual" in body
