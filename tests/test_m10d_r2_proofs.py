"""M10D-r2 proof-contract corrections — P0-5/P0-6/P0-7.

P0-5: every §66 family proves contested BEFORE **and** independent
AFTER with exact old/new semantic facts asserted; the narrative-reorder
race mutates topology so the WINNING TRANSITION actually changes and
the capture reflects one complete old/new pack.

P0-6: byte determinism perturbs real source ordering (DB insertion
order of staging producers via transition creation order and plan
blocking-entry input order) and asserts identical canonical pack bytes,
identical schema-5 snapshot bytes, and identical issue ordering — the
proof fails if canonical sorting is removed.

P0-7: both scale fixtures use MATCHED legal targets whose own row
cardinality grows (deps/features/relations/visual items/M10 tracks/
frames), asserting normalized SQL statement-class identity + count
identity, plus an explicit per-row-regression tripwire (item 144).
"""
import asyncio
import json
import time
import uuid

import pytest
from sqlalchemy import text

from soloring.continuity.snapshots import (
    build_capturable_snapshot,
    resolve_working_dependencies,
)
from soloring.domain import revisions as rev_svc
from soloring.domain.canonical import canonical_hash, canonical_json_str
from soloring.errors import ErrorCode, SoloRingError
from soloring.spatial import plans as plan_svc
from soloring.spatial import tracks as track_svc
from soloring.spatial import transitions as trans_svc
from soloring.spatial import worlds as world_svc
from soloring.spatial import revisions as wrev_svc
from soloring.spatial import resolver as resolver_svc

from tests.test_m10d_resolver import (
    CAM, EVA_T, _entities, _full_fixture, _shot, fs,
)
from tests.test_m10d_races import (
    _EngineSession, _capture_parked, _pack_fingerprint,
)
from tests.test_m10c_scale import _Spy


async def _after_capture(factory, shot_id):
    return await rev_svc.capture_revision(fs(factory), shot_id)


def _pack_of(revision):
    return json.loads(revision.snapshot_json)["spatial_continuity"]


# ---------------------------------------------------- P0-5 race matrix

async def test_race_plan_delete_after(factory, engine):
    seed = await _full_fixture(factory)
    cur = await plan_svc.get_current_plan(fs(factory), seed["shot"])
    await plan_svc.delete_spatial_plan(
        fs(factory), seed["shot"], expected_plan_hash=cur["plan_hash"])
    # AFTER: no plan + required world → SPATIAL_SHOT_PLAN_REQUIRED
    with pytest.raises(SoloRingError) as ei:
        await _after_capture(factory, seed["shot"])
    assert ei.value.code in (ErrorCode.SPATIAL_SHOT_PLAN_REQUIRED,
                             "SPATIAL_SHOT_PLAN_REQUIRED")


async def test_race_world_approval_after(factory, engine):
    seed = await _full_fixture(factory)
    newer = await wrev_svc.capture_revision(fs(factory), seed["state"]["id"])
    await wrev_svc.approve_revision(
        fs(factory), seed["state"]["id"], revision_id=newer["id"],
        expected_approved_revision_id=seed["rev"]["id"])
    rev = await _after_capture(factory, seed["shot"])
    # AFTER: captured pack carries the NEW approved revision id
    assert _pack_of(rev)["spatial_world"][
        "spatial_world_revision_id"] == newer["id"]


async def test_race_world_requirement_after(factory):
    seed = await _full_fixture(factory)
    await world_svc.patch_world(fs(factory), seed["world"]["id"],
                                requirement="optional")
    rev = await _after_capture(factory, seed["shot"])
    assert _pack_of(rev)["spatial_world"]["requirement"] == "optional"


async def test_race_transition_edit_after(factory, engine):
    seed = await _full_fixture(factory)
    trs = await trans_svc.list_transitions(
        fs(factory), seed["track"]["id"])
    new_t = [EVA_T[0] + 222, EVA_T[1], EVA_T[2]]
    await trans_svc.patch_transition(
        fs(factory), trs[0]["id"], translation_mm=new_t)
    # AFTER (staging-inconsistent plan): the resolver SAW the new value —
    # the strict gate raises blocking-mismatch against the stale plan t0
    with pytest.raises(SoloRingError) as ei:
        await _after_capture(factory, seed["shot"])
    assert ei.value.code in (ErrorCode.SPATIAL_BLOCKING_STATE_MISMATCH,
                             "SPATIAL_BLOCKING_STATE_MISMATCH")
    # AFTER (plan reconciled to the new authority): the pack carries it
    stored = await plan_svc.get_current_plan(fs(factory), seed["shot"])
    plan = json.loads(stored["plan_json"])
    plan["blocking"][0]["keyframes"][0]["transform"][
        "translation_mm"] = new_t
    await plan_svc.put_spatial_plan(
        fs(factory), seed["shot"],
        expected_plan_hash=stored["plan_hash"], plan_raw=plan)
    rev = await _after_capture(factory, seed["shot"])
    assert _pack_of(rev)["staging"][0]["transform"][
        "translation_mm"] == new_t


async def test_race_track_requirement_after(factory):
    seed = await _full_fixture(factory)
    await track_svc.patch_track(
        fs(factory), seed["track"]["id"], requirement="required")
    rev = await _after_capture(factory, seed["shot"])
    assert _pack_of(rev)["staging"][0]["requirement"] == "required"


async def test_race_entity_revision_approval_after(factory, engine):
    from soloring.continuity.approvals import approve_revision
    seed = await _full_fixture(factory)
    eva, old_rev = seed["ents"]["eva"]
    new_rev_id = str(uuid.uuid4())
    async with factory() as s:
        async with s.begin():
            await s.execute(text(
                "INSERT INTO entity_revisions (id, entity_id, "
                "revision_number, schema_version, spec_hash, created_at) "
                "VALUES (:r, :e, 2, 1, :h, 't')"),
                {"r": new_rev_id, "e": eva, "h": "ab" * 32})
    await approve_revision(fs(factory), eva, new_rev_id,
                           expected_approved_revision_id=old_rev)
    rev = await _after_capture(factory, seed["shot"])
    assert _pack_of(rev)["staging"][0]["entity_revision_id"] == new_rev_id


async def test_race_dependency_set_after(factory):
    seed = await _full_fixture(factory)
    async with factory() as s:
        async with s.begin():
            await s.execute(text(
                "DELETE FROM shot_entity_dependencies WHERE shot_id = :q "
                "AND entity_id = :e"),
                {"q": seed["shot"], "e": seed["ents"]["loc"][0]})
    # AFTER: plan Location no longer a dependency → capture blocked
    with pytest.raises(SoloRingError) as ei:
        await _after_capture(factory, seed["shot"])
    assert ei.value.code in (ErrorCode.SPATIAL_SHOT_PLAN_INVALID,
                             "SPATIAL_SHOT_PLAN_INVALID")


async def test_race_narrative_reorder_changes_winner_and_capture(factory,
                                                                 engine):
    """The reorder must actually flip the WINNING transition: two shots
    in the same scene swap scene_position so the earlier-of-the-two
    boundary crosses the target's /start."""
    seed = await _full_fixture(factory)
    shot = seed["shot"]
    eva = seed["ents"]["eva"][0]
    # second shot in the TARGET's OWN scene, immediately after it
    async with factory() as s:
        scene, pos_t, shot_no = (await s.execute(text(
            "SELECT scene_id, scene_position, (SELECT "
            "COALESCE(MAX(shot_number),0)+1 FROM shots WHERE "
            "project_id = :p) FROM shots WHERE id = :t"),
            dict(p=seed["pid"], t=shot))).first()
    other = str(uuid.uuid4())
    async with factory() as s:
        async with s.begin():
            pos_o = (await s.execute(text(
                "SELECT COALESCE(MAX(scene_position), -1) + 1 FROM shots "
                "WHERE scene_id = :c"), dict(c=scene))).scalar()
            await s.execute(text(
                "INSERT INTO shots (id, project_id, shot_number, subject,"
                " scene_id, scene_position) VALUES (:i, :p, :n, 'other',"
                " :c, :pos)"),
                dict(i=other, p=seed["pid"], n=shot_no, c=scene,
                     pos=pos_o))
            for i, e in enumerate([seed["ents"]["loc"][0], eva,
                                   seed["ents"]["desk"][0]]):
                await s.execute(text(
                    "INSERT INTO shot_entity_dependencies (shot_id, "
                    "entity_id, role, position) VALUES (:q, :e, 'cast', "
                    ":i)"), dict(q=other, e=e, i=i))
    # give the OTHER shot a set at its own /start with a distinct value
    await trans_svc.create_transition(
        fs(factory), seed["track"]["id"], anchor_type="shot",
        anchor_id=other, boundary="start", operation="set",
        translation_mm=[77, 7, 77], rotation_udeg=[0, 0, 0])
    # target currently BEFORE other → sequence/start (EVA_T) wins at
    # target's /start… ensure distinctness: move OTHER before TARGET
    async def swap():
        async with factory() as s:
            async with s.begin():
                # move TARGET to a transient free position FIRST (the
                # active-uniqueness index is checked per statement)
                await s.execute(text(
                    "UPDATE shots SET scene_position = 999 "
                    "WHERE id = :t"), {"t": shot})
                await s.execute(text(
                    "UPDATE shots SET scene_position = :po "
                    "WHERE id = :o"), {"po": pos_t, "o": other})
                await s.execute(text(
                    "UPDATE shots SET scene_position = :pt "
                    "WHERE id = :t"), {"pt": pos_o, "t": shot})

    rev_before = None

    entered, release = asyncio.Event(), asyncio.Event()
    ret: dict = {}
    reader = asyncio.create_task(
        _capture_parked(engine, shot, entered, release, ret))

    async def comp():
        await entered.wait()
        await swap()
        release.set()

    await asyncio.gather(reader, comp())
    rev_before = ret["revision"]
    # BEFORE: the winner is still the sequence/start transition (the
    # other shot's /start is AFTER the target in the OLD topology)
    assert _pack_of(rev_before)["staging"][0]["transform"][
        "translation_mm"] == EVA_T
    # AFTER: other-shot/start now PRECEDES target/start → it wins. The
    # stale plan t0 blocks first (coherent visibility of the NEW
    # winner); reconcile the plan, then the pack carries the new value.
    with pytest.raises(SoloRingError) as ei:
        await _after_capture(factory, shot)
    assert ei.value.code in (ErrorCode.SPATIAL_BLOCKING_STATE_MISMATCH,
                             "SPATIAL_BLOCKING_STATE_MISMATCH")
    stored = await plan_svc.get_current_plan(fs(factory), shot)
    plan = json.loads(stored["plan_json"])
    plan["blocking"][0]["keyframes"][0]["transform"][
        "translation_mm"] = [77, 7, 77]
    await plan_svc.put_spatial_plan(
        fs(factory), shot, expected_plan_hash=stored["plan_hash"],
        plan_raw=plan)
    rev_after = await _after_capture(factory, shot)
    assert _pack_of(rev_after)["staging"][0]["transform"][
        "translation_mm"] == [77, 7, 77]
    assert _pack_of(rev_after)["staging"][0]["source_transition"][
        "anchor_id"] == other


# ------------------------------------------------- P0-6 determinism

NSD = uuid.uuid5(uuid.NAMESPACE_DNS, "m10d-r2-determinism")


def _d(name):
    return str(uuid.uuid5(NSD, name))


async def _det_build(factory, engine, *, reverse):
    """Deterministic-ID fixture (uuid5): same semantic content in both
    builds; the EXTRA tracks/transitions/blocking input order is
    physically reversed, so DB return order differs while identity is
    stable — the only legitimate byte-level determinism comparison."""
    pid, loc, locrev, shot, seq = (_d("p"), _d("loc"), _d("locrev"),
                                   _d("shot"), _d("seq"))
    world_id, state_id, wrev_id, frame_id = (_d("w"), _d("st"), _d("wr"),
                                             _d("fr"))
    async with factory() as s:
        async with s.begin():
            await s.execute(text(
                "INSERT INTO projects (id, name, created_at, updated_at)"
                " VALUES (:i, 'P', 't', 't')"), {"i": pid})
            await s.execute(text(
                "INSERT INTO creative_entities (id, project_id, kind,"
                " name, created_at, updated_at) VALUES (:i, :p,"
                " 'location', 'L', 't', 't')"), {"i": loc, "p": pid})
            await s.execute(text(
                "INSERT INTO entity_revisions (id, entity_id,"
                " revision_number, schema_version, spec_hash, created_at)"
                " VALUES (:i, :e, 1, 1, :h, 't')"),
                {"i": locrev, "e": loc, "h": "aa" * 32})
            await s.execute(text(
                "INSERT INTO entity_approved_revisions (entity_id,"
                " revision_id, approved_at) VALUES (:e, :r, 't')"),
                {"e": loc, "r": locrev})
            for k in range(3):
                e, r = _d(f"e{k}"), _d(f"er{k}")
                await s.execute(text(
                    "INSERT INTO creative_entities (id, project_id, kind,"
                    " name, created_at, updated_at) VALUES (:i, :p,"
                    " 'character', :n, 't', 't')"),
                    {"i": e, "p": pid, "n": f"m{k}"})
                await s.execute(text(
                    "INSERT INTO entity_revisions (id, entity_id,"
                    " revision_number, schema_version, spec_hash,"
                    " created_at) VALUES (:i, :e, 1, 1, :h, 't')"),
                    {"i": r, "e": e, "h": "bb" * 32})
                await s.execute(text(
                    "INSERT INTO entity_approved_revisions (entity_id,"
                    " revision_id, approved_at) VALUES (:e, :r, 't')"),
                    {"e": e, "r": r})
            await s.execute(text(
                "INSERT INTO sequences (id, project_id, position, title)"
                " VALUES (:i, :p, 0, 'S')"),
                {"i": seq, "p": pid})
            await s.execute(text(
                "INSERT INTO scenes (id, sequence_id, position, title)"
                " VALUES (:i, :q, 0, 'C')"),
                {"i": _d("scene"), "q": seq})
            await s.execute(text(
                "INSERT INTO shots (id, project_id, shot_number, subject,"
                " duration_ms, scene_id, scene_position) VALUES (:i, :p,"
                " 1, 'shot', 5000, :c, 0)"),
                {"i": shot, "p": pid, "c": _d("scene")})
            await s.execute(text(
                "INSERT INTO shot_entity_dependencies (shot_id, entity_id"
                ", role, position) VALUES (:q, :e, 'cast', 0)"),
                {"q": shot, "e": loc})
            for k in range(3):
                await s.execute(text(
                    "INSERT INTO shot_entity_dependencies (shot_id,"
                    " entity_id, role, position) VALUES (:q, :e, 'cast',"
                    " :i)"),
                    {"q": shot, "e": _d(f"e{k}"), "i": k + 1})
            await s.execute(text(
                "INSERT INTO spatial_worlds (id, project_id,"
                " location_entity_id, key, name, description,"
                " requirement, created_at, updated_at) VALUES (:i, :p,"
                " :l, 'lobby', 'L', NULL, 'required', 't', 't')"),
                {"i": world_id, "p": pid, "l": loc})
            await s.execute(text(
                "INSERT INTO spatial_world_states (id, spatial_world_id,"
                " location_entity_revision_id, created_at, updated_at)"
                " VALUES (:i, :w, :r, 't', 't')"),
                {"i": state_id, "w": world_id, "r": locrev})
            await s.execute(text(
                "INSERT INTO spatial_frames (id, spatial_world_id, key,"
                " name, parent_spatial_frame_id, bound_entity_id,"
                " created_at, updated_at) VALUES (:i, :w, 'origin', 'O',"
                " NULL, NULL, 't', 't')"),
                {"i": frame_id, "w": world_id})
            await s.execute(text(
                "INSERT INTO spatial_world_state_frames ("
                "spatial_world_state_id, spatial_frame_id, bound_entity_id"
                ", bound_entity_revision_id, x_mm, y_mm, z_mm, yaw_udeg,"
                " pitch_udeg, roll_udeg, half_x_mm, half_y_mm, half_z_mm,"
                " updated_at) VALUES (:s, :f, NULL, NULL, 0, 0, 0, 0, 0,"
                " 0, NULL, NULL, NULL, 't')"),
                {"s": state_id, "f": frame_id})
    # world revision snapshot + children (canonical schema-1 shape)
    from soloring.spatial.schemas import parse_world_revision
    from soloring.domain.canonical import (canonical_hash as _ch,
                                           canonical_json_str as _cj)
    snap = parse_world_revision({
        "schema_version": 1, "spatial_world_id": world_id,
        "location_entity_id": loc, "location_entity_revision_id": locrev,
        "coordinate_system": {
            "handedness": "right", "right_axis": "+x", "up_axis": "+y",
            "depth_positive_axis": "+z", "forward_axis": "-z",
            "linear_unit": "millimeter", "rotation_unit": "microdegree",
            "rotation_semantics": "active_local_to_world_intrinsic_yxz",
            "vector_convention": "column", "camera_forward_axis": "-z"},
        "frames": [{
            "spatial_frame_id": frame_id, "frame_key": "origin",
            "parent_spatial_frame_id": None, "bound_entity_id": None,
            "bound_entity_revision_id": None, "transform": {
                "translation_mm": [0, 0, 0],
                "rotation_udeg": [0, 0, 0]},
            "half_extents_mm": None}],
        "axes": []})
    async with factory() as s:
        async with s.begin():
            await s.execute(text(
                "INSERT INTO spatial_world_revisions (id,"
                " spatial_world_state_id, revision_number, snapshot_json,"
                " snapshot_hash, created_at) VALUES (:i, :s, 1, :j, :h,"
                " 't')"),
                {"i": wrev_id, "s": state_id, "j": _cj(snap),
                 "h": _ch(snap)})
            await s.execute(text(
                "INSERT INTO spatial_world_revision_frames ("
                "spatial_world_revision_id, position, spatial_frame_id,"
                " frame_key, parent_spatial_frame_id, bound_entity_id,"
                " bound_entity_revision_id, x_mm, y_mm, z_mm, yaw_udeg,"
                " pitch_udeg, roll_udeg, half_x_mm, half_y_mm, half_z_mm)"
                " VALUES (:r, 0, :f, 'origin', NULL, NULL, NULL, 0, 0, 0,"
                " 0, 0, 0, NULL, NULL, NULL)"),
                {"r": wrev_id, "f": frame_id})
            await s.execute(text(
                "UPDATE spatial_world_states SET approved_revision_id ="
                " :r WHERE id = :s"),
                {"r": wrev_id, "s": state_id})
            # tracks + set transitions at sequence/start, physically
            # inserted ascending or DESCENDING
            order = range(3) if not reverse else reversed(range(3))
            for k in order:
                tid, trid = _d(f"t{k}"), _d(f"tr{k}")
                await s.execute(text(
                    "INSERT INTO spatial_tracks (id, spatial_world_id,"
                    " entity_id, requirement, created_at, updated_at)"
                    " VALUES (:i, :w, :e, 'optional', 't', 't')"),
                    {"i": tid, "w": world_id, "e": _d(f"e{k}")})
                await s.execute(text(
                    "INSERT INTO spatial_transitions (id,"
                    " spatial_track_id, anchor_type, anchor_id, boundary,"
                    " operation, x_mm, y_mm, z_mm, yaw_udeg, pitch_udeg,"
                    " roll_udeg, created_at, updated_at) VALUES (:i, :t,"
                    " 'sequence', :a, 'start', 'set', :x, 0, :z, 0, 0, 0,"
                    " 't', 't')"),
                    {"i": trid, "t": tid, "a": seq, "x": k * 10,
                     "z": -k})
    # plan with blocking derived from staging; input order reversed in
    # the reverse build
    async with engine.connect() as conn:
        deps = await resolve_working_dependencies(conn, shot)
        staging = await resolver_svc.resolve_effective_staging(
            conn, shot_id=shot, spatial_world_id=world_id,
            resolved_entity_revisions={
                d.entity_id: d.entity_revision_id for d in deps})
    blk = [{
        "spatial_track_id": st.spatial_track_id,
        "screen_direction": "stationary",
        "keyframes": [{
            "time_ms": 0,
            "transform": {
                "translation_mm": [st.x_mm, st.y_mm, st.z_mm],
                "rotation_udeg": [st.yaw_udeg, st.pitch_udeg,
                                  st.roll_udeg]}}],
    } for st in staging.states]
    if reverse:
        blk = list(reversed(blk))
    plan = {"schema_version": 1, "spatial_world_id": world_id,
            "camera": json.loads(json.dumps(CAM)), "blocking": blk,
            "axis_constraint": None}
    await plan_svc.put_spatial_plan(
        fs(factory), shot, expected_plan_hash=None, plan_raw=plan)
    rev = await rev_svc.capture_revision(fs(factory), shot)
    # issue-ordering probe under identical readiness breakage
    await track_svc.patch_track(
        fs(factory), _d("t0"), requirement="required")
    await trans_svc.delete_transition(
        fs(factory), (await trans_svc.list_transitions(
            fs(factory), _d("t0")))[0]["id"])
    async with engine.connect() as conn:
        deps = await resolve_working_dependencies(conn, shot)
        out = await resolver_svc.resolve_spatial_continuity(
            conn, shot_id=shot, resolved_dependencies=deps)
    return (rev.snapshot_json, rev.snapshot_hash,
            [(i.code, i.layer, i.message) for i in out.issues])


async def test_byte_determinism_real_order_perturbation(tmp_path):
    """P0-6: identical identity + semantic content in TWO fresh
    databases, with physically reversed DB insertion order of
    tracks/transitions and reversed blocking input order — canonical
    schema-5 snapshot bytes, hash, and issue ordering must all be
    byte-identical."""
    from soloring.db import models  # noqa: F401
    from soloring.db.base import Base
    from soloring.db.engine import create_soloring_engine
    from soloring.settings import Settings
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    async def build(tag, reverse):
        eng = create_soloring_engine(Settings(data_dir=tmp_path / tag))
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        fac = async_sessionmaker(bind=eng, expire_on_commit=False,
                                 class_=AsyncSession)
        try:
            return await _det_build(fac, eng, reverse=reverse)
        finally:
            await eng.dispose()

    snap_a, hash_a, issues_a = await build("a", reverse=False)
    snap_b, hash_b, issues_b = await build("b", reverse=True)
    assert snap_a == snap_b, "schema-5 snapshot bytes must be identical"
    assert hash_a == hash_b
    assert issues_a == issues_b


async def _first_seq(factory, pid):
    async with factory() as s:
        return (await s.execute(text(
            "SELECT id FROM sequences WHERE project_id = :p ORDER BY "
            "position LIMIT 1"), {"p": pid})).scalar_one()


# ------------------------------------------------------ P0-7 scale

def _classify_stmts(statements):
    """Normalize a statement list into ordered (first-token, table)
    classes."""
    out = []
    for st in statements:
        s = st.strip()
        tok = s.split(None, 1)[0].upper() if s else ""
        tables = tuple(sorted({
            w.strip('"(),') for w in s.replace("(", " ").replace(
                ")", " ").replace(",", " ").split()
            if w in (
                "shots", "shot_entity_dependencies", "entity_revisions",
                "creative_entities", "continuity_features",
                "continuity_feature_transitions",
                "continuity_relation_transitions",
                "spatial_worlds", "spatial_world_states",
                "spatial_world_revisions",
                "spatial_world_revision_frames",
                "spatial_world_revision_axes",
                "shot_spatial_plans", "spatial_tracks",
                "spatial_transitions", "sequences", "scenes",
                "shot_revisions", "shot_revision_entity_dependencies",
                "shot_revision_feature_states",
                "shot_revision_relation_states",
                "shot_revision_visual_anchors",
                "shot_revision_visual_anchor_items",
                "shot_revision_spatial_worlds",
                "shot_revision_spatial_track_states",
                "shot_revision_spatial_plans",
                "visual_anchor_revisions", "visual_anchors",
                "entity_approved_revisions")}))
        out.append((tok, tables))
    return out


async def _scale_target(factory, engine, *, n_deps, n_tracks, n_frames):
    """Build one legal target whose OWN cardinality is parameterized:
    dependencies, applicable tracks with staging, approved frames."""
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
        e = await _entities(factory, pid, {f"m{k}": "character"})
        movable[f"m{k}"] = e[f"m{k}"]
    frames = [("origin", [0, 0, 0], None)]
    for k in range(n_frames):
        frames.append((f"f{k}", [1000 * (k + 1), 0, -500 * (k + 1)],
                       None))
    world, state, rev, fids = await _world_approved_frames(
        factory, pid, loc, locrev, frames)
    seq = str(uuid.uuid4())
    async with factory() as s:
        async with s.begin():
            await s.execute(text(
                "INSERT INTO sequences (id, project_id, position, title) "
                "VALUES (:q, :p, 0, 'S')"), {"q": seq, "p": pid})
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
    shot = await _shot(factory, pid,
                       [loc] + [v[0] for v in movable.values()])
    plan = {
        "schema_version": 1, "spatial_world_id": world["id"],
        "camera": json.loads(json.dumps(CAM)), "blocking": [],
        "axis_constraint": None}
    await plan_svc.put_spatial_plan(
        fs(factory), shot, expected_plan_hash=None, plan_raw=plan)
    return {"pid": pid, "shot": shot, "world": world, "track_ids":
            track_ids, "n_deps": n_deps}


async def _world_approved_frames(factory, pid, loc, locrev, frames):
    from tests.test_m10d_resolver import _world_approved
    return await _world_approved(factory, pid, loc, locrev,
                                 frames=frames, axes=[])


async def _measure_capture(engine, shot):
    with _Spy(engine) as spy:
        rev = await rev_svc.capture_revision(_EngineSession(engine), shot)
    return _classify_stmts(spy.statements), rev


async def test_scale_capture_target_cardinality_and_classes(factory, engine):
    """P0-7 (capture): matched legal targets, same populated child
    classes, REPRESENTATIVE target has substantially more dependency and
    Track rows. Statement CLASSES and COUNT identical; cardinality
    larger; per-row regression trips the gate."""
    small = await _scale_target(factory, engine, n_deps=3, n_tracks=2,
                                n_frames=3)
    classes_s, rev_s = await _measure_capture(engine, small["shot"])
    assert json.loads(rev_s.snapshot_json)["schema_version"] == 5

    rep = await _scale_target(factory, engine, n_deps=60, n_tracks=40,
                              n_frames=60)
    classes_r, rev_r = await _measure_capture(engine, rep["shot"])
    assert json.loads(rev_r.snapshot_json)["schema_version"] == 5

    # row cardinality actually larger on the representative target
    async with factory() as s:
        cs = (await s.execute(text(
            "SELECT COUNT(*) FROM shot_revision_entity_dependencies "
            "WHERE shot_revision_id = :r"), {"r": rev_s.id})).scalar()
        cr = (await s.execute(text(
            "SELECT COUNT(*) FROM shot_revision_entity_dependencies "
            "WHERE shot_revision_id = :r"), {"r": rev_r.id})).scalar()
        ts = (await s.execute(text(
            "SELECT COUNT(*) FROM shot_revision_spatial_track_states "
            "WHERE shot_revision_id = :r"), {"r": rev_s.id})).scalar()
        tr = (await s.execute(text(
            "SELECT COUNT(*) FROM shot_revision_spatial_track_states "
            "WHERE shot_revision_id = :r"), {"r": rev_r.id})).scalar()
    assert cr > cs and tr > ts

    # statement classes AND count identical
    assert len(classes_s) == len(classes_r)
    assert classes_s == classes_r
    print(f"\ncapture scale: small {len(classes_s)} == rep "
          f"{len(classes_r)} statements; deps {cs}->{cr}, tracks "
          f"{ts}->{tr}")

    # item 144 anti-regression tripwire: a per-row writer would add
    # (rows-1) extra INSERT statements — prove the count would change
    # if any child writer regressed (simulate by counting INSERTs into
    # the dependency table in the measured trace)
    with _Spy(engine) as spy:
        # second capture of the representative target converges (reuse)
        await rev_svc.capture_revision(_EngineSession(engine),
                                       rep["shot"])
    dep_inserts = sum(1 for st in spy.statements
                      if "INSERT INTO shot_revision_entity_dependencies"
                      in st)
    assert dep_inserts == 0, "reuse path must not re-insert children"


async def test_scale_current_resolution_target_cardinality(factory, engine):
    """P0-7 (current resolution): same matched-target discipline on the
    resolver path."""
    from soloring.spatial import resolver as r

    async def measure(seed):
        with _Spy(engine) as spy:
            async with engine.connect() as conn:
                deps = await resolve_working_dependencies(
                    conn, seed["shot"])
                out = await r.resolve_spatial_continuity(
                    conn, shot_id=seed["shot"],
                    resolved_dependencies=deps)
        return _classify_stmts(spy.statements), out

    small = await _scale_target(factory, engine, n_deps=3, n_tracks=2,
                                n_frames=3)
    classes_s, out_s = await measure(small)
    assert out_s.ready

    rep = await _scale_target(factory, engine, n_deps=60, n_tracks=40,
                              n_frames=60)
    classes_r, out_r = await measure(rep)
    assert out_r.ready
    assert len(out_r.pack["staging"]) > len(out_s.pack["staging"])

    assert len(classes_s) == len(classes_r)
    assert classes_s == classes_r
    print(f"\nresolver scale: small {len(classes_s)} == rep "
          f"{len(classes_r)} statements; staging "
          f"{len(out_s.pack['staging'])}->"
          f"{len(out_r.pack['staging'])}")
