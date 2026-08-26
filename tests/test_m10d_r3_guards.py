"""M10D-r3 source-gate corrections — P0-R2-1/2/3/4 from round 2.

P0-R2-1: the world-approval race mutates to a GENUINELY DISTINCT
immutable revision (working world edit → capture B, asserted B≠A) and
proves BEFORE pack==A on the pinned snapshot, AFTER pack==B.
P0-R2-2: both scale targets populate ALL varying child classes —
dependencies, Feature states, Relation states, visual anchors, visual
items, spatial Tracks — with six mechanical row-growth assertions plus
normalized SQL class/count identity.
P0-R2-3: outer historical snapshot corruption (malformed JSON, non-
object, illegal schema version, bytes/hash disagreement) is
INTERNAL_INVARIANT_VIOLATION.
P0-R2-4: schema5+M8 history reads the frozen top-level
visual_reference_pack, proves non-null visual provenance with non-empty
anchors and exact pack-hash fidelity — the assertion fails if the v5
guard is reverted.
"""
import asyncio
import json
import uuid

import pytest
from sqlalchemy import text

from soloring.continuity.snapshots import resolve_working_dependencies
from soloring.domain import revisions as rev_svc
from soloring.domain.canonical import canonical_hash
from soloring.errors import ErrorCode, SoloRingError
from soloring.spatial import resolver as resolver_svc
from soloring.spatial import worlds as world_svc
from soloring.spatial import revisions as wrev_svc

from tests.test_m10d_resolver import (
    CAM, _entities, _full_fixture, _shot, fs,
)
from tests.test_m10d_races import _capture_parked


# ------------------------------------------------------ P0-R2-1

async def test_race_world_approval_real_mutation_before_and_after(
        factory, engine):
    """The approved revision B is GENUINELY DISTINCT: a legal working
    world mutation first, capture B, assert B != A, then race
    approve A→B against whole ShotRevision capture."""
    seed = await _full_fixture(factory)
    a_id = seed["rev"]["id"]
    # legal working mutation: move the UNBOUND origin frame's working
    # value (bound frames require their exact revision on PUT)
    async with factory() as s:
        fid = (await s.execute(text(
            "SELECT m.spatial_frame_id FROM "
            "spatial_world_state_frames m JOIN spatial_frames f ON "
            "f.id = m.spatial_frame_id WHERE "
            "m.spatial_world_state_id = :st AND f.bound_entity_id IS "
            "NULL ORDER BY m.spatial_frame_id LIMIT 1"),
            {"st": seed["state"]["id"]})).scalar()
    await world_svc.put_state_frame(
        fs(factory), seed["state"]["id"], fid,
        translation_mm=[123, 456, 789], rotation_udeg=[0, 0, 0],
        half_extents_mm=None, bound_entity_revision_id=None)
    b = await wrev_svc.capture_revision(fs(factory),
                                        seed["state"]["id"])
    assert b["id"] != a_id, "capture must yield a DISTINCT revision"

    async def approve_b():
        await wrev_svc.approve_revision(
            fs(factory), seed["state"]["id"], revision_id=b["id"],
            expected_approved_revision_id=a_id)

    # contested BEFORE on the pinned capture snapshot
    entered, release = asyncio.Event(), asyncio.Event()
    ret: dict = {}
    reader = asyncio.create_task(
        _capture_parked(engine, seed["shot"], entered, release, ret))

    async def comp():
        await entered.wait()
        await approve_b()
        release.set()

    await asyncio.gather(reader, comp())
    pack_before = json.loads(ret["revision"].snapshot_json)[
        "spatial_continuity"]
    assert pack_before["spatial_world"][
        "spatial_world_revision_id"] == a_id

    # independent AFTER
    rev_after = await rev_svc.capture_revision(fs(factory),
                                               seed["shot"])
    pack_after = json.loads(rev_after.snapshot_json)[
        "spatial_continuity"]
    assert pack_after["spatial_world"][
        "spatial_world_revision_id"] == b["id"]
    assert pack_after["spatial_world"]["world_snapshot"]["frames"] != \
        pack_before["spatial_world"]["world_snapshot"]["frames"], \
        "the distinct revision must carry the mutated working geometry"


# ------------------------------------------------------ P0-R2-2

async def _scale_full_target(factory, client, engine, *, n_deps, n_tracks,
                             n_features, n_relations):
    """Matched legal target populating ALL varying child classes:
    dependencies, Feature states, Relation states, visual anchors,
    visual items, spatial Tracks."""
    from soloring.continuity.approvals import approve_revision
    from tests.conftest import seed_reference_asset

    pid = str(uuid.uuid4())
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO projects (id, name, created_at, updated_at) "
                "VALUES (:p, 'P', 't', 't')"), {"p": pid})
    ents = await _entities(factory, pid, {"loc": "location"})
    loc, locrev = ents["loc"]
    movable = {}
    for k in range(n_deps):
        movable[f"m{k}"] = (await _entities(
            factory, pid, {f"m{k}": "character"}))[f"m{k}"]

    seed = await _full_fixture(factory)  # world/state/rev/plan helper
    # reuse the fixture's world but re-point dependencies at OUR shot:
    shot = await _shot(factory, pid, [loc] + [
        v[0] for v in movable.values()])
    world_id = seed["world"]["id"]
    # NOTE: the fixture created its own project; we cannot reuse its
    # world across projects. Build the world in OUR project instead.
    from tests.test_m10d_resolver import _world_approved
    frames = [("origin", [0, 0, 0], None)]
    world, state, wrev, _fids = await _world_approved(
        factory, pid, loc, locrev, frames=frames, axes=[])
    seq = str(uuid.uuid4())
    async with factory() as s:
        async with s.begin():
            await s.execute(text(
                "INSERT INTO sequences (id, project_id, position, title) "
                "VALUES (:q, :p, 0, 'S')"), {"q": seq, "p": pid})
    from soloring.spatial import tracks as track_svc
    from soloring.spatial import transitions as trans_svc
    track_ids = []
    for name, (eid, _r) in list(movable.items())[:n_tracks]:
        t = await track_svc.create_track(
            fs(factory), world["id"], entity_id=eid,
            requirement="optional")
        await trans_svc.create_transition(
            fs(factory), t["id"], anchor_type="sequence",
            anchor_id=seq, boundary="start", operation="set",
            translation_mm=[len(track_ids), 0, -100],
            rotation_udeg=[0, 0, 0])
        track_ids.append(t["id"])

    # Features + transitions for the first n_features movable entities
    # (public M7 API, house test style)
    feat_ids = []
    for k in range(n_features):
        eid = movable[f"m{k}"][0]
        fr2 = await client.post(
            f"/entities/{eid}/continuity-features", json={
                "key": f"state{k}", "kind": "injury",
                "value_type": "enum", "name": f"St{k}",
                "enum_values": ["fresh", "healing", "scarred", "gone"]})
        assert fr2.status_code == 201, fr2.text
        fid2 = fr2.json()["id"]
        tr2 = await client.post(
            f"/continuity-features/{fid2}/transitions", json={
                "anchor_type": "sequence", "anchor_id": seq,
                "boundary": "start", "operation": "set",
                "value": "fresh"})
        assert tr2.status_code == 201, tr2.text
        feat_ids.append(fid2)

    # Relations + transitions for the first n_relations pairs (M7D API)
    rel_ids = []
    for k in range(n_relations):
        s_e = movable[f"m{k}"][0]
        o_e = movable[f"m{(k + 1) % n_deps}"][0]
        pr2 = await client.post(f"/projects/{pid}/continuity-predicates",
                                json={"key": f"p{k}", "name": f"P{k}"})
        assert pr2.status_code == 201, pr2.text
        rr2 = await client.post(f"/projects/{pid}/continuity-relations",
                                json={"subject_entity_id": s_e,
                                      "predicate_id": pr2.json()["id"],
                                      "object_entity_id": o_e})
        assert rr2.status_code == 201, rr2.text
        rt2 = await client.post(
            f"/continuity-relations/{rr2.json()['id']}/transitions",
            json={"anchor_type": "sequence", "anchor_id": seq,
                  "boundary": "start", "state": "active"})
        assert rt2.status_code == 201, rt2.text
        rel_ids.append(rr2.json()["id"])

    # M8 visual anchors + physical-blob items for n_visual entities
    engine_app = client._transport.app.state.engine
    from soloring.assets.blob_store import BlobStore
    from soloring.settings import get_settings
    store = BlobStore(get_settings())
    anchor_ids = []
    for k in range(min(n_features, n_deps)):
        eid, erid = movable[f"m{k}"]
        fr = await client.post(f"/projects/{pid}/visual-facets", json={
            "target_kind": "entity", "entity_id": eid,
            "facet_key": f"fc{k}", "requirement": "optional"})
        assert fr.status_code == 201, fr.text
        ar = await client.post(
            f"/visual-facets/{fr.json()['id']}/anchors", json={
                "entity_revision_id": erid})
        assert ar.status_code == 201, ar.text
        anchor_id = ar.json()["id"]
        anchor_ids.append(anchor_id)
        # the items PUT is a FULL-set replacement: both items in ONE
        # call (exactly one primary) so captured items scale per anchor
        items = []
        for j in range(2):
            aid, bh = await seed_reference_asset(engine_app, pid)
            path = store.path_for_hash(bh)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"r3-scale-" + bh.encode())
            items.append({"asset_id": aid,
                          "role": "primary" if j == 0 else "supporting"})
        wr = await client.put(
            f"/visual-anchors/{anchor_id}/items",
            json={"items": items})
        assert wr.status_code == 200, wr.text
        cr = await client.post(f"/visual-anchors/{anchor_id}/revisions")
        assert cr.status_code == 201, cr.text
        apr = await client.post(
            f"/visual-anchor-revisions/{cr.json()['id']}/approve",
            json={"expected_approved_revision_id": None})
        assert apr.status_code == 200, apr.text

    plan = {"schema_version": 1, "spatial_world_id": world["id"],
            "camera": json.loads(json.dumps(CAM)), "blocking": [],
            "axis_constraint": None}
    from soloring.spatial import plans as plan_svc
    await plan_svc.put_spatial_plan(
        fs(factory), shot, expected_plan_hash=None, plan_raw=plan)
    return {"shot": shot, "pid": pid}


async def test_scale_full_w1_matrix_matched_targets(factory, client,
                                                    engine):
    """P0-R2-2: both matched targets populate dependencies, Feature
    states, Relation states, visual anchors, visual items, and spatial
    Tracks; the representative has materially more rows in EVERY class;
    normalized SQL statement classes/count identical."""
    from tests.test_m10d_r2_proofs import (
        _classify_stmts, _measure_capture,
    )

    small = await _scale_full_target(
        factory, client, engine, n_deps=4, n_tracks=3, n_features=3,
        n_relations=2)
    classes_s, rev_s = await _measure_capture(engine, small["shot"])
    snap_s = json.loads(rev_s.snapshot_json)
    assert snap_s["schema_version"] == 5
    assert "visual_reference_pack" in snap_s

    rep = await _scale_full_target(
        factory, client, engine, n_deps=30, n_tracks=20, n_features=15,
        n_relations=10)
    classes_r, rev_r = await _measure_capture(engine, rep["shot"])
    snap_r = json.loads(rev_r.snapshot_json)
    assert snap_r["schema_version"] == 5
    assert "visual_reference_pack" in snap_r

    async def counts(rid):
        async with factory() as s:
            async def q(sql):
                return (await s.execute(text(sql), {
                    "r": rid})).scalar()
            return {
                "deps": await q("SELECT COUNT(*) FROM "
                                "shot_revision_entity_dependencies "
                                "WHERE shot_revision_id = :r"),
                "features": await q(
                    "SELECT COUNT(*) FROM "
                    "shot_revision_feature_states WHERE "
                    "shot_revision_id = :r"),
                "relations": await q(
                    "SELECT COUNT(*) FROM "
                    "shot_revision_relation_states WHERE "
                    "shot_revision_id = :r"),
                "anchors": await q(
                    "SELECT COUNT(*) FROM "
                    "shot_revision_visual_anchors WHERE "
                    "shot_revision_id = :r"),
                "items": await q(
                    "SELECT COUNT(*) FROM "
                    "shot_revision_visual_anchor_items WHERE "
                    "shot_revision_id = :r"),
                "tracks": await q(
                    "SELECT COUNT(*) FROM "
                    "shot_revision_spatial_track_states WHERE "
                    "shot_revision_id = :r"),
            }

    cs = await counts(rev_s.id)
    cr_ = await counts(rev_r.id)
    # every populated class present in the small target
    for key in ("deps", "features", "relations", "anchors", "items",
                "tracks"):
        assert cs[key] > 0, f"small target missing {key} rows"
        assert cr_[key] > cs[key], f"{key} rows did not grow"
    # normalized SQL statement classes/count identical
    assert len(classes_s) == len(classes_r)
    assert classes_s == classes_r
    print(f"\nfull W1 matrix: stmts {len(classes_s)}=={len(classes_r)}; "
          f"{cs} -> {cr_}")


# ------------------------------------------------------ P0-R2-3

async def test_outer_snapshot_corruption_is_invariant(factory, client):
    seed = await _full_fixture(factory)
    revision = await rev_svc.capture_revision(fs(factory), seed["shot"])
    rid = revision.id

    async def corrupt(value):
        async with factory() as s:
            async with s.begin():
                await s.execute(text(
                    "UPDATE shot_revisions SET snapshot_json = :j "
                    "WHERE id = :r"), {"j": value, "r": rid})
        r = await client.get(f"/shot-revisions/{rid}/continuity")
        assert r.status_code == 500
        assert r.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"

    await corrupt("not json at all")            # malformed JSON
    await corrupt("[1, 2, 3]")                  # non-object container
    # legal JSON, wrong shape: schema_version bogus + recompute nothing
    await corrupt(json.dumps({"schema_version": 9}))

    # bytes/hash disagreement: decode-valid object whose canonical bytes
    # differ from the stored hash
    async with factory() as s:
        row = (await s.execute(text(
            "SELECT snapshot_json FROM shot_revisions WHERE id = :r"),
            {"r": rid})).scalar_one()
    snap = json.loads(row)
    snap["intent"] = {**snap.get("intent", {}), "subject": "tampered"}
    async with factory() as s2:
        async with s2.begin():
            await s2.execute(text(
                "UPDATE shot_revisions SET snapshot_json = :j "
                "WHERE id = :r"),
                {"j": json.dumps(snap), "r": rid})
    r2 = await client.get(f"/shot-revisions/{rid}/continuity")
    assert r2.status_code == 500
    assert r2.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"


# ------------------------------------------------------ P0-R2-4

async def test_schema5_m8_visual_provenance_non_vacuous(factory, client):
    """Non-vacuous P0-8 proof: visual provenance is NOT None, anchors
    are non-empty, the pack hash equals the canonical hash of the
    frozen top-level visual_reference_pack, and spatial provenance is
    complete. Reverting the (4,5) guard makes body["visual"] null and
    this test FAIL."""
    seed = await _full_fixture(factory)
    pid = seed["pid"]
    eva, evarev = seed["ents"]["eva"]
    from tests.conftest import seed_reference_asset
    from soloring.assets.blob_store import BlobStore
    from soloring.settings import get_settings

    fr = await client.post(f"/projects/{pid}/visual-facets", json={
        "target_kind": "entity", "entity_id": eva,
        "facet_key": "wardrobe", "requirement": "optional"})
    facet_id = fr.json()["id"]
    ar = await client.post(f"/visual-facets/{facet_id}/anchors", json={
        "entity_revision_id": evarev})
    anchor_id = ar.json()["id"]
    engine_app = client._transport.app.state.engine
    store = BlobStore(get_settings())
    aid, bh = await seed_reference_asset(engine_app, pid)
    path = store.path_for_hash(bh)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"r3-visual-" + bh.encode())
    wr = await client.put(f"/visual-anchors/{anchor_id}/items", json={
        "items": [{"asset_id": aid, "role": "primary"}]})
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
    assert "visual_reference_pack" in snap

    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["spatial"] is not None
    # NON-VACUOUS visual assertions
    assert body["visual"] is not None, \
        "schema-5 history must preserve captured visual provenance"
    assert len(body["visual"]["anchors"]) >= 1
    anchor = body["visual"]["anchors"][0]
    # the §72 row exposes the captured anchor revision identity — find
    # it under whichever key the frozen projection uses
    rev_id = anchor.get("captured_visual_anchor_revision_id")
    assert rev_id == cr.json()["id"],         f"captured anchor revision not projected: {sorted(anchor)}"
    assert len(anchor["items"]) >= 1
    # pack-hash fidelity against the frozen top-level value
    assert body["visual"]["visual_reference_pack_hash"] == \
        canonical_hash(snap["visual_reference_pack"])
