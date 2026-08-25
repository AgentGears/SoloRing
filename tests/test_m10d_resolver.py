"""M10D-2/3 tests — the ONE complete resolver (matrix 49-79, 120-121,
128-129 core).

Production-shaped fixture: approved required world (bound fixed frame +
free frame + axis), M10C staging, ShotSpatialPlan with blocking + axis.
Covers applicable-world selection, exact state/approval, placement
authority, fixed EntityRevision consistency, M10C staging reuse,
current-duration plan revalidation, blocking t0 agreement, Shot/end
handoff, axis-side enforcement, and canonical pack/hash construction.
"""
import json
import uuid

import pytest
from sqlalchemy import text

from soloring.errors import ErrorCode, SoloRingError
from soloring.spatial import plans as plan_svc
from soloring.spatial import resolver
from soloring.spatial import tracks as track_svc
from soloring.spatial import transitions as trans_svc
from soloring.spatial import worlds as world_svc
from soloring.spatial import revisions as rev_svc


def fs(factory):
    return factory()


CAM = {
    "projection": "perspective",
    "focal_length_um": 50000,
    "sensor_width_um": 36000,
    "sensor_height_um": 20250,
    "keyframes": [{
        "time_ms": 0,
        "transform": {"translation_mm": [-3000, 1650, 4200],
                      "rotation_udeg": [0, 0, 0]}}],
}
EVA_T = [500, 0, -1200]


async def _entities(factory, pid, kinds):
    out = {}
    for name, kind in kinds.items():
        eid, rid = str(uuid.uuid4()), str(uuid.uuid4())
        async with factory() as session:
            async with session.begin():
                await session.execute(text(
                    "INSERT INTO creative_entities (id, project_id, kind, "
                    "name, created_at, updated_at) VALUES (:e, :p, :k, :n,"
                    " 't','t')"),
                    {"e": eid, "p": pid, "k": kind, "n": name})
                await session.execute(text(
                    "INSERT INTO entity_revisions (id, entity_id, "
                    "revision_number, schema_version, spec_hash, "
                    "created_at) VALUES (:r, :e, 1, 1, :h, 't')"),
                    {"r": rid, "e": eid, "h": f"{name[:2]:<2}" * 32})
                await session.execute(text(
                    "INSERT INTO entity_approved_revisions (entity_id, "
                    "revision_id, approved_at) VALUES (:e, :r, 't')"),
                    {"e": eid, "r": rid})
        out[name] = (eid, rid)
    return out


async def _world_approved(factory, pid, loc, locrev, *, frames, axes,
                          key="lobby", requirement="required"):
    """Create world + state + frame/axis values + captured + APPROVED
    revision. frames: [(key, translation, bound=(eid,rid)|None)]; axes:
    [(key, frame_key_a, frame_key_b)]."""
    world = await world_svc.create_world(
        fs(factory), pid, key=key, name=key, description=None,
        requirement=requirement, location_entity_id=loc)
    state = await world_svc.create_state(
        fs(factory), world["id"], location_entity_revision_id=locrev)
    fids = {}
    for fkey, t, bound in frames:
        f = await world_svc.create_frame(
            fs(factory), world["id"], key=fkey, name=fkey,
            parent_spatial_frame_id=None,
            bound_entity_id=bound[0] if bound else None)
        fids[fkey] = f["id"]
        await world_svc.put_state_frame(
            fs(factory), state["id"], f["id"], translation_mm=list(t),
            rotation_udeg=[0, 0, 0], half_extents_mm=None,
            bound_entity_revision_id=bound[1] if bound else None)
    for akey, fa, fb in axes:
        a = await world_svc.create_axis(
            fs(factory), world["id"], key=akey, name=akey)
        await world_svc.put_state_axis(
            fs(factory), state["id"], a["id"], a_frame_id=fids[fa],
            b_frame_id=fids[fb])
    rev = await rev_svc.capture_revision(fs(factory), state["id"])
    await rev_svc.approve_revision(
        fs(factory), state["id"], revision_id=rev["id"],
        expected_approved_revision_id=None)
    return world, state, rev, fids


async def _shot(factory, pid, deps, *, duration_ms=5000, assigned=True):
    shot = str(uuid.uuid4())
    seq = scene = None
    async with factory() as session:
        async with session.begin():
            if assigned:
                seq, scene = str(uuid.uuid4()), str(uuid.uuid4())
                await session.execute(text(
                    "INSERT INTO sequences (id, project_id, position, "
                    "title) VALUES (:q, :p, (SELECT COALESCE(MAX("
                    "position),0)+1 FROM sequences WHERE project_id=:p), "
                    "'S')"), {"q": seq, "p": pid})
                await session.execute(text(
                    "INSERT INTO scenes (id, sequence_id, position, title)"
                    " VALUES (:c, :q, 0, 'C')"), {"c": scene, "q": seq})
            await session.execute(text(
                "INSERT INTO shots (id, project_id, shot_number, subject, "
                "duration_ms, scene_id, scene_position) VALUES "
                "(:s, :p, (SELECT COALESCE(MAX(shot_number),0)+1 FROM "
                "shots WHERE project_id=:p), 'shot', :d, :c, 0)"),
                {"s": shot, "p": pid, "d": duration_ms,
                 "c": scene if assigned else None})
            for i, eid in enumerate(deps):
                await session.execute(text(
                    "INSERT INTO shot_entity_dependencies (shot_id, "
                    "entity_id, role, position) VALUES (:s, :e, 'cast', "
                    ":i)"), {"s": shot, "e": eid, "i": i})
    return shot


async def _full_fixture(factory, *, eva_fixed=False, with_plan=True,
                        requirement="required", with_axis=True):
    pid = str(uuid.uuid4())
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO projects (id, name, created_at, updated_at) "
                "VALUES (:p, 'P', 't', 't')"), {"p": pid})
    ents = await _entities(factory, pid,
                           {"loc": "location", "eva": "character",
                            "desk": "character"})
    loc, locrev = ents["loc"]
    eva, evarev = ents["eva"]
    desk, deskrev = ents["desk"]
    bound = (eva, evarev) if eva_fixed else None
    if eva_fixed:
        frames = [
            ("origin", [0, 0, 0], None),
            ("eva-frame", [2500, 0, -1500], bound),
            ("desk", [3000, 0, -2000], (desk, deskrev)),
        ]
    else:
        frames = [
            ("origin", [0, 0, 0], None),
            ("desk", [2500, 0, -1500], (desk, deskrev)),
        ]
    axes = [("axis", "origin", "desk")] if with_axis else []
    world, state, rev, fids = await _world_approved(
        factory, pid, loc, locrev, frames=frames, axes=axes,
        requirement=requirement)
    track = await track_svc.create_track(
        fs(factory), world["id"], entity_id=eva,
        requirement="optional") if not eva_fixed else None
    shot = await _shot(factory, pid, [loc, eva, desk])
    blocking = []
    if track is not None and with_plan:
        await trans_svc.create_transition(
            fs(factory), track["id"], anchor_type="sequence",
            anchor_id=(await _first_sequence(factory, pid)),
            boundary="start", operation="set",
            translation_mm=EVA_T, rotation_udeg=[0, 0, 0])
        blocking = [{
            "spatial_track_id": track["id"],
            "screen_direction": "left_to_right",
            "keyframes": [{
                "time_ms": 0,
                "transform": {"translation_mm": EVA_T,
                              "rotation_udeg": [0, 0, 0]}}],
        }]
    plan = None
    if with_plan:
        plan = {
            "schema_version": 1,
            "spatial_world_id": world["id"],
            "camera": json.loads(json.dumps(CAM)),
            "blocking": blocking,
            "axis_constraint": ({"spatial_axis_id": None
                                 if not with_axis else
                                 await _axis_id(factory, world["id"]),
                                 "camera_side": "positive"}
                                if with_axis else None),
        }
        # placeholder axis id replaced by caller-side helper below
        if with_axis:
            plan["axis_constraint"] = {
                "spatial_axis_id": await _axis_id(factory, world["id"]),
                "camera_side": "positive"}
        await plan_svc.put_spatial_plan(
            fs(factory), shot, expected_plan_hash=None, plan_raw=plan)
    return {"pid": pid, "ents": ents, "world": world, "state": state,
            "rev": rev, "fids": fids, "track": track, "shot": shot,
            "eva_t": EVA_T}


async def _first_sequence(factory, pid):
    async with factory() as session:
        return (await session.execute(text(
            "SELECT id FROM sequences WHERE project_id = :p ORDER BY "
            "position LIMIT 1"), {"p": pid})).scalar_one()


async def _axis_id(factory, world_id):
    async with factory() as session:
        return (await session.execute(text(
            "SELECT id FROM spatial_axes WHERE spatial_world_id = :w "
            "ORDER BY key LIMIT 1"), {"w": world_id})).scalar_one()


async def _resolve(engine, seed, shot=None):
    from soloring.continuity.snapshots import resolve_working_dependencies
    async with engine.connect() as conn:
        deps = await resolve_working_dependencies(
            conn, shot or seed["shot"])
        return await resolver.resolve_spatial_continuity(
            conn, shot_id=shot or seed["shot"],
            resolved_dependencies=deps)


def _codes(outcome):
    return [i.code for i in outcome.issues]


# ------------------------------------------------------------ ready path

async def test_complete_resolution_ready_pack_and_hash(factory, engine):
    seed = await _full_fixture(factory)
    out = await _resolve(engine, seed)
    assert out.ready is True and out.issues == ()
    assert out.pack is not None and len(out.spatial_continuity_hash) == 64
    w = out.pack["spatial_world"]
    assert w["spatial_world_id"] == seed["world"]["id"]
    assert w["requirement"] == "required"
    assert w["spatial_world_revision_id"] == seed["rev"]["id"]
    assert w["location_entity_revision_id"] == \
        seed["ents"]["loc"][1]
    assert len(w["world_snapshot"]["frames"]) == 2
    st = out.pack["staging"]
    assert len(st) == 1 and st[0]["entity_id"] == seed["ents"]["eva"][0]
    assert st[0]["transform"]["translation_mm"] == EVA_T
    assert st[0]["source_transition"]["anchor_type"] == "sequence"
    assert out.pack["shot_plan"]["camera"]["focal_length_um"] == 50000
    assert out.axis_status["violating_keyframe_times_ms"] == []
    # idempotent double-resolution, identical bytes
    out2 = await _resolve(engine, seed)
    assert out2.spatial_continuity_hash == out.spatial_continuity_hash


# ------------------------------------------------------- world selection

async def test_world_selection_matrix(factory, engine):
    # 53/54: zero required + no plan → ready, no pack, optional not auto
    seed = await _full_fixture(factory, requirement="optional",
                               with_plan=False)
    out = await _resolve(engine, seed)
    assert out.ready is True and out.pack is None and \
        out.spatial_continuity_hash is None

    # 50: required world, no plan
    seed50 = await _full_fixture(factory, with_plan=False)
    out50 = await _resolve(engine, seed50)
    assert _codes(out50) == [ErrorCode.SPATIAL_SHOT_PLAN_REQUIRED]

    # 49: two required applicable worlds → ambiguous
    pid = seed50["pid"]
    ents = seed50["ents"]
    loc2, locrev2 = (await _entities(
        factory, pid, {"loc2": "location"}))["loc2"]
    await _world_approved(
        factory, pid, loc2, locrev2,
        frames=[("origin2", [0, 0, 0], None)], axes=[],
        key="lobby2")
    shot49 = await _shot(factory, pid, [
        ents["loc"][0], loc2, ents["eva"][0], ents["desk"][0]])
    out49 = await _resolve(engine, seed50, shot=shot49)
    assert _codes(out49) == [ErrorCode.SPATIAL_CONTEXT_AMBIGUOUS]

    # 51: required world + plan selecting another world → invalid.
    # The plan is authored legally while the OPTIONAL world's Location
    # is a dependency, then the dependency set changes to the required
    # world's Location — the stored plan now selects a foreign world.
    seed51 = await _full_fixture(factory, requirement="required")
    pid51 = seed51["pid"]
    ents51 = seed51["ents"]
    loc2b, locrev2b = (await _entities(
        factory, pid51, {"loc2b": "location"}))["loc2b"]
    w2, _, _, _ = await _world_approved(
        factory, pid51, loc2b, locrev2b,
        frames=[("o", [0, 0, 0], None)], axes=[], key="alt",
        requirement="optional")
    shot51 = await _shot(factory, pid51, [loc2b])
    plan51 = {
        "schema_version": 1, "spatial_world_id": w2["id"],
        "camera": json.loads(json.dumps(CAM)), "blocking": [],
        "axis_constraint": None}
    await plan_svc.put_spatial_plan(
        fs(factory), shot51, expected_plan_hash=None, plan_raw=plan51)
    # dependency set now points at the REQUIRED world's Location only
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "DELETE FROM shot_entity_dependencies WHERE shot_id = :s"),
                {"s": shot51})
            await session.execute(text(
                "INSERT INTO shot_entity_dependencies (shot_id, entity_id,"
                " role, position) VALUES (:s, :e, 'cast', 0)"),
                {"s": shot51, "e": ents51["loc"][0]})
    out51 = await _resolve(engine, seed51, shot=shot51)
    assert _codes(out51) == [ErrorCode.SPATIAL_SHOT_PLAN_INVALID]
    assert any(i.layer == "world_selection" for i in out51.issues)

    # 52: optional world + plan → resolves ready
    seed52 = await _full_fixture(factory, requirement="optional")
    out52 = await _resolve(engine, seed52)
    assert out52.ready is True and out52.pack is not None

    # 55: plan Location removed from dependencies → invalid. The plan
    # is authored legally first, then the dependency is removed.
    seed55 = await _full_fixture(factory)
    stored55 = await plan_svc.get_current_plan(fs(factory),
                                               seed55["shot"])
    assert stored55 is not None  # authored while Location was a dep
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "DELETE FROM shot_entity_dependencies WHERE shot_id = :s "
                "AND entity_id = :e"),
                {"s": seed55["shot"],
                 "e": seed55["ents"]["loc"][0]})
    out55 = await _resolve(engine, seed55)
    assert _codes(out55) == [ErrorCode.SPATIAL_SHOT_PLAN_INVALID]
    assert "ceased to be" in out55.issues[0].message


# ------------------------------------------------- state / approval / corruption

async def test_state_and_approval_issues(factory, engine):
    # 58: state exists, no approval
    seed = await _full_fixture(factory)
    await rev_svc.unapprove(
        fs(factory), seed["state"]["id"],
        expected_approved_revision_id=seed["rev"]["id"])
    out = await _resolve(engine, seed)
    assert _codes(out) == [ErrorCode.SPATIAL_WORLD_APPROVAL_REQUIRED]

    # 57: missing state (different Location revision)
    seed2 = await _full_fixture(factory)
    pid2 = seed2["pid"]
    ents = seed2["ents"]
    loc, _ = ents["loc"]
    newrev = str(uuid.uuid4())
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO entity_revisions (id, entity_id, "
                "revision_number, schema_version, spec_hash, created_at) "
                "VALUES (:r, :e, 2, 1, :h, 't')"),
                {"r": newrev, "e": loc, "h": "ff" * 32})
            await session.execute(text(
                "UPDATE entity_approved_revisions SET revision_id = :r "
                "WHERE entity_id = :e"), {"r": newrev, "e": loc})
    out2 = await _resolve(engine, seed2)
    assert _codes(out2) == [ErrorCode.SPATIAL_WORLD_STATE_REQUIRED]


async def test_world_corruption_fails_invariant(factory, engine):
    # 60: approved pointer → revision of another state
    seed = await _full_fixture(factory)
    other = await _full_fixture(factory)
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "UPDATE spatial_world_states SET approved_revision_id = :r "
                "WHERE id = :s"),
                {"r": other["rev"]["id"], "s": seed["state"]["id"]})
    with pytest.raises(SoloRingError) as ei:
        await _resolve(engine, seed)
    assert ei.value.code == ErrorCode.INTERNAL_INVARIANT_VIOLATION

    # 61: snapshot bytes corruption
    seed2 = await _full_fixture(factory)
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "UPDATE spatial_world_revisions SET snapshot_json = "
                "'{\"corrupted\": true}' WHERE id = :r"),
                {"r": seed2["rev"]["id"]})
    with pytest.raises(SoloRingError):
        await _resolve(engine, seed2)


# ---------------------------------------------------- placement / revision

async def test_placement_authority(factory, engine):
    # 63: fixed + track → conflict; 64: precedes revision mismatch
    seed = await _full_fixture(factory, eva_fixed=True)
    # eva has a fixed frame AND (via with_plan default) a track — but
    # with eva_fixed the fixture creates no track; add one explicitly
    eva, evarev = seed["ents"]["eva"]
    track = await track_svc.create_track(
        fs(factory), seed["world"]["id"], entity_id=eva,
        requirement="optional")
    await trans_svc.create_transition(
        fs(factory), track["id"], anchor_type="sequence",
        anchor_id=await _first_sequence(factory, seed["pid"]),
        boundary="start", operation="set",
        translation_mm=[1, 2, 3], rotation_udeg=[0, 0, 0])
    out = await _resolve(engine, seed)
    codes = _codes(out)
    assert ErrorCode.SPATIAL_ENTITY_PLACEMENT_CONFLICT in codes
    # no revision-mismatch fabricated for the conflicted entity
    for i in out.issues:
        if i.code == ErrorCode.SPATIAL_ENTITY_REVISION_MISMATCH:
            assert i.details.get("entity_id") != eva

    # 62: two fixed placements for one entity — unauthorable through
    # M10B working-state rules (one placement per Entity per state), so
    # the approved revision is corrupted CONSISTENTLY (snapshot + child
    # + hash) and the resolver must surface the placement conflict
    seed62 = await _full_fixture(factory, eva_fixed=True)
    out62 = await _resolve(engine, seed62)
    assert out62.ready is True  # single fixed placement is legal
    pid62, ents62 = seed62["pid"], seed62["ents"]
    eva62, evarev62 = ents62["eva"]
    loc62b, locrev62b = (await _entities(
        factory, pid62, {"loc62b": "location"}))["loc62b"]
    world62, state62, rev62, fids = await _world_approved(
        factory, pid62, loc62b, locrev62b,
        frames=[("f1", [0, 0, 0], (eva62, evarev62)),
                ("f2", [900, 0, 0], None)],
        axes=[], key="dup")
    # bind f2 to eva in the stored snapshot + child row + recomputed hash
    import soloring.spatial.schemas as _S
    import soloring.domain.canonical as _C
    async with factory() as session:
        snap_row = (await session.execute(text(
            "SELECT snapshot_json FROM spatial_world_revisions "
            "WHERE id = :r"), {"r": rev62["id"]})).scalar_one()
        await session.commit()
        snap = _S.parse_world_revision(json.loads(snap_row))
        for fr in snap["frames"]:
            if fr["frame_key"] == "f2":
                fr["bound_entity_id"] = eva62
                fr["bound_entity_revision_id"] = evarev62
        snap_sorted = _S.parse_world_revision(snap)  # re-sort/validate
        new_hash = _C.canonical_hash(snap_sorted)
        new_json = _C.canonical_json_str(snap_sorted)
        async with session.begin():
            await session.execute(text(
                "UPDATE spatial_world_revisions SET snapshot_json = :j, "
                "snapshot_hash = :h WHERE id = :r"),
                {"j": new_json, "h": new_hash, "r": rev62["id"]})
            await session.execute(text(
                "UPDATE spatial_world_revision_frames SET "
                "bound_entity_id = :e, bound_entity_revision_id = :er "
                "WHERE spatial_world_revision_id = :r AND frame_key = "
                "'f2'"),
                {"e": eva62, "er": evarev62, "r": rev62["id"]})
    # shot without an existing plan, dependencies incl. loc62b
    shot62 = await _shot(factory, pid62, [loc62b, eva62])
    plan62 = {"schema_version": 1, "spatial_world_id": world62["id"],
              "camera": json.loads(json.dumps(CAM)), "blocking": [],
              "axis_constraint": None}
    await plan_svc.put_spatial_plan(
        fs(factory), shot62, expected_plan_hash=None, plan_raw=plan62)
    async with engine.connect() as conn:
        from soloring.continuity.snapshots import             resolve_working_dependencies
        deps = await resolve_working_dependencies(conn, shot62)
        out62b = await resolver.resolve_spatial_continuity(
            conn, shot_id=shot62, resolved_dependencies=deps)
    assert ErrorCode.SPATIAL_ENTITY_PLACEMENT_CONFLICT in         _codes(out62b)

    # 65: fixed bound EntityRevision mismatch
    seed65 = await _full_fixture(factory, eva_fixed=True, with_plan=True)
    eva65, _ = seed65["ents"]["eva"]
    stale = str(uuid.uuid4())
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "UPDATE shots SET duration_ms = 5000 WHERE id = :s"),
                {"s": seed65["shot"]})
    # point the semantic approval at a NEW revision → fixed bound is now
    # stale → mismatch
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO entity_revisions (id, entity_id, "
                "revision_number, schema_version, spec_hash, created_at) "
                "VALUES (:r, :e, 2, 1, :h, 't')"),
                {"r": stale, "e": eva65, "h": "ee" * 32})
            await session.execute(text(
                "UPDATE entity_approved_revisions SET revision_id = :r "
                "WHERE entity_id = :e"), {"r": stale, "e": eva65})
    out65 = await _resolve(engine, seed65)
    assert ErrorCode.SPATIAL_ENTITY_REVISION_MISMATCH in _codes(out65)

    # 66: bound world-internal Entity NOT a Shot dependency stays valid
    seed66 = await _full_fixture(factory)
    desk66, deskrev66 = seed66["ents"]["desk"]
    shot66 = await _shot(factory, seed66["pid"], [
        seed66["ents"]["loc"][0], seed66["ents"]["eva"][0]])
    plan66 = {"schema_version": 1,
              "spatial_world_id": seed66["world"]["id"],
              "camera": json.loads(json.dumps(CAM)), "blocking": [],
              "axis_constraint": None}
    await plan_svc.put_spatial_plan(
        fs(factory), shot66, expected_plan_hash=None, plan_raw=plan66)
    out66 = await _resolve(engine, seed66, shot=shot66)
    assert out66.ready is True  # desk bound but not a dependency


# ------------------------------------------------------ staging / track state

async def test_track_requirement_issues_and_staging_reuse(factory, engine):
    seed = await _full_fixture(factory)
    # 68: required absent track yields the blocker
    await track_svc.patch_track(fs(factory), seed["track"]["id"],
                                requirement="required")
    await trans_svc.delete_transition(
        fs(factory), (await trans_svc.list_transitions(
            fs(factory), seed["track"]["id"]))[0]["id"])
    out = await _resolve(engine, seed)
    assert ErrorCode.SPATIAL_TRACK_STATE_REQUIRED in _codes(out)
    issue = next(i for i in out.issues
                 if i.code == ErrorCode.SPATIAL_TRACK_STATE_REQUIRED)
    assert issue.details["reason"] == "no_eligible_transition"
    # 69: optional absent stays valid
    await track_svc.patch_track(fs(factory), seed["track"]["id"],
                                requirement="optional")
    # plan still has a blocking entry for the now-stateless track →
    # blocking mismatch (matrix 43)
    out2 = await _resolve(engine, seed)
    assert ErrorCode.SPATIAL_BLOCKING_STATE_MISMATCH in _codes(out2)
    # 44: staged track WITHOUT blocking entry stays valid staging —
    # remove blocking from the plan
    stored = await plan_svc.get_current_plan(fs(factory), seed["shot"])
    plan_raw = json.loads(stored["plan_json"])
    plan_raw["blocking"] = []
    await plan_svc.put_spatial_plan(
        fs(factory), seed["shot"], expected_plan_hash=stored["plan_hash"],
        plan_raw=plan_raw)
    # re-create the transition so the track is staged again
    await trans_svc.create_transition(
        fs(factory), seed["track"]["id"], anchor_type="sequence",
        anchor_id=await _first_sequence(factory, seed["pid"]),
        boundary="start", operation="set",
        translation_mm=EVA_T, rotation_udeg=[0, 0, 0])
    out3 = await _resolve(engine, seed)
    assert out3.ready is True  # 67/70/71: exact staging + provenance used
    assert out3.pack["staging"][0]["transform"]["translation_mm"] == EVA_T


# ------------------------------------------------------ blocking / handoff

async def test_blocking_agreement_and_handoff(factory, engine):
    seed = await _full_fixture(factory)
    stored = await plan_svc.get_current_plan(fs(factory), seed["shot"])
    track_id = seed["track"]["id"]

    # 41: t0 translation mismatch
    bad = json.loads(stored["plan_json"])
    bad["blocking"][0]["keyframes"][0]["transform"]["translation_mm"] = \
        [EVA_T[0] + 1, EVA_T[1], EVA_T[2]]
    await plan_svc.put_spatial_plan(
        fs(factory), seed["shot"], expected_plan_hash=stored["plan_hash"],
        plan_raw=bad)
    out = await _resolve(engine, seed)
    assert ErrorCode.SPATIAL_BLOCKING_STATE_MISMATCH in _codes(out)

    # restore + 42: t0 rotation mismatch (1 udeg)
    stored = await plan_svc.get_current_plan(fs(factory), seed["shot"])
    bad2 = json.loads(stored["plan_json"])
    bad2["blocking"][0]["keyframes"][0]["transform"]["rotation_udeg"] = \
        [0, 1, 0]
    await plan_svc.put_spatial_plan(
        fs(factory), seed["shot"], expected_plan_hash=stored["plan_hash"],
        plan_raw=bad2)
    out2 = await _resolve(engine, seed)
    assert ErrorCode.SPATIAL_BLOCKING_STATE_MISMATCH in _codes(out2)

    # restore exact + Shot/end handoff (47): exact final keyframe passes
    stored = await plan_svc.get_current_plan(fs(factory), seed["shot"])
    good = json.loads(stored["plan_json"])
    good["blocking"][0]["keyframes"][0]["transform"]["translation_mm"] = \
        list(EVA_T)
    good["blocking"][0]["keyframes"][0]["transform"]["rotation_udeg"] = \
        [0, 0, 0]
    final_t = [700, 0, -900]
    good["blocking"][0]["keyframes"].append({
        "time_ms": 5000,
        "transform": {"translation_mm": final_t,
                      "rotation_udeg": [0, 0, 0]}})
    await plan_svc.put_spatial_plan(
        fs(factory), seed["shot"], expected_plan_hash=stored["plan_hash"],
        plan_raw=good)
    end_tr = await trans_svc.create_transition(
        fs(factory), track_id, anchor_type="shot",
        anchor_id=seed["shot"], boundary="end", operation="set",
        translation_mm=final_t, rotation_udeg=[0, 0, 0])
    out3 = await _resolve(engine, seed)
    assert out3.ready is True

    # 46: mismatched final keyframe → blocker
    stored = await plan_svc.get_current_plan(fs(factory), seed["shot"])
    bad_final = json.loads(stored["plan_json"])
    bad_final["blocking"][0]["keyframes"][1]["transform"][
        "translation_mm"] = [final_t[0] + 5, final_t[1], final_t[2]]
    await plan_svc.put_spatial_plan(
        fs(factory), seed["shot"], expected_plan_hash=stored["plan_hash"],
        plan_raw=bad_final)
    out4 = await _resolve(engine, seed)
    assert ErrorCode.SPATIAL_BLOCKING_STATE_MISMATCH in _codes(out4)

    # 45: NULL duration + Shot/end set + blocking → blocker
    stored = await plan_svc.get_current_plan(fs(factory), seed["shot"])
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "UPDATE shots SET duration_ms = NULL WHERE id = :s"),
                {"s": seed["shot"]})
    out5 = await _resolve(engine, seed)
    # NULL duration also invalidates the stored plan's t>0 keyframes
    assert ErrorCode.SPATIAL_SHOT_PLAN_INVALID in _codes(out5) or \
        ErrorCode.SPATIAL_BLOCKING_STATE_MISMATCH in _codes(out5)
    # restore duration
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "UPDATE shots SET duration_ms = 5000 WHERE id = :s"),
                {"s": seed["shot"]})

    # 128: tombstoned Shot/end transition is ignored
    stored = await plan_svc.get_current_plan(fs(factory), seed["shot"])
    ok_final = json.loads(stored["plan_json"])
    ok_final["blocking"][0]["keyframes"][1]["transform"][
        "translation_mm"] = list(final_t)
    # remove the final keyframe entirely — handoff requirement appears
    # only for ACTIVE Shot/end events
    del ok_final["blocking"][0]["keyframes"][1]
    await plan_svc.put_spatial_plan(
        fs(factory), seed["shot"], expected_plan_hash=stored["plan_hash"],
        plan_raw=ok_final)
    await trans_svc.delete_transition(fs(factory), end_tr["id"])
    out6 = await _resolve(engine, seed)  # Shot/end deleted → no handoff
    assert out6.ready is True
    # 48: Shot/end set + TRACK WITHOUT a blocking entry stays legal
    cur = await plan_svc.get_current_plan(fs(factory), seed["shot"])
    no_blk = json.loads(cur["plan_json"])
    no_blk["blocking"] = []
    await plan_svc.put_spatial_plan(
        fs(factory), seed["shot"], expected_plan_hash=cur["plan_hash"],
        plan_raw=no_blk)
    await trans_svc.create_transition(
        fs(factory), track_id, anchor_type="shot",
        anchor_id=seed["shot"], boundary="end", operation="set",
        translation_mm=[1, 1, 1], rotation_udeg=[0, 0, 0])
    out7 = await _resolve(engine, seed)
    assert out7.ready is True


# ---------------------------------------------------------- axis / duration

async def test_axis_enforcement(factory, engine):
    seed = await _full_fixture(factory)
    stored = await plan_svc.get_current_plan(fs(factory), seed["shot"])

    # camera at origin side check: origin frame [0,0,0], desk [2500,0,
    # -1500]; camera [-3000,1650,4200] — cross sign vs positive side
    # 73/74: flip the camera across the line by declaring the other side
    stored = await plan_svc.get_current_plan(fs(factory), seed["shot"])
    flipped = json.loads(stored["plan_json"])
    flipped["axis_constraint"]["camera_side"] = \
        "negative" if stored else "negative"
    # determine which side the current camera is on by trying negative
    await plan_svc.put_spatial_plan(
        fs(factory), seed["shot"], expected_plan_hash=stored["plan_hash"],
        plan_raw=flipped)
    out = await _resolve(engine, seed)
    if out.ready:
        # camera is on the negative side; flipping to positive violates
        flipped2 = json.loads(
            (await plan_svc.get_current_plan(
                fs(factory), seed["shot"]))["plan_json"])
        flipped2["axis_constraint"]["camera_side"] = "positive"
        cur = await plan_svc.get_current_plan(fs(factory), seed["shot"])
        await plan_svc.put_spatial_plan(
            fs(factory), seed["shot"], expected_plan_hash=cur["plan_hash"],
            plan_raw=flipped2)
        out2 = await _resolve(engine, seed)
        assert ErrorCode.SPATIAL_AXIS_CONSTRAINT_VIOLATION in \
            _codes(out2)
    else:
        assert ErrorCode.SPATIAL_AXIS_CONSTRAINT_VIOLATION in \
            _codes(out)

    # 75: camera exactly on the axis line → violation (cross == 0)
    cur = await plan_svc.get_current_plan(fs(factory), seed["shot"])
    online = json.loads(cur["plan_json"])
    online["axis_constraint"]["camera_side"] = "positive"
    # origin [0,0,0] → desk [2500,0,-1500]: camera on the line through
    # origin with direction (2500, -1500) in X/Z: pick t=0.4 → exactly
    # on the line
    online["camera"]["keyframes"][0]["transform"]["translation_mm"] = \
        [1000, 1650, -600]
    await plan_svc.put_spatial_plan(
        fs(factory), seed["shot"], expected_plan_hash=cur["plan_hash"],
        plan_raw=online)
    out75 = await _resolve(engine, seed)
    assert ErrorCode.SPATIAL_AXIS_CONSTRAINT_VIOLATION in \
        _codes(out75)

    # 72: axis exists (active, in-world) but is ABSENT from the exact
    # approved revision — write-time ownership passes; the resolver
    # rejects it against the approved revision
    later_axis = await world_svc.create_axis(
        fs(factory), seed["world"]["id"], key="later", name="later")
    cur = await plan_svc.get_current_plan(fs(factory), seed["shot"])
    ghost = json.loads(cur["plan_json"])
    ghost["axis_constraint"]["spatial_axis_id"] = later_axis["id"]
    ghost["camera"]["keyframes"][0]["transform"]["translation_mm"] = \
        [-3000, 1650, 4200]
    await plan_svc.put_spatial_plan(
        fs(factory), seed["shot"], expected_plan_hash=cur["plan_hash"],
        plan_raw=ghost)
    out72 = await _resolve(engine, seed)
    assert ErrorCode.SPATIAL_SHOT_PLAN_INVALID in _codes(out72)
    assert any(i.layer == "axis" for i in out72.issues)


async def test_current_duration_revalidation(factory, engine):
    # matrix 120/121: duration shrink invalidates stored plan readiness
    # WITHOUT changing stored plan hash
    seed = await _full_fixture(factory)
    stored = await plan_svc.get_current_plan(fs(factory), seed["shot"])
    # extend the plan to use the full 5000ms window
    ext = json.loads(stored["plan_json"])
    ext["camera"]["keyframes"].append({
        "time_ms": 5000,
        "transform": {"translation_mm": [-3000, 1650, 4200],
                      "rotation_udeg": [0, 0, 0]}})
    await plan_svc.put_spatial_plan(
        fs(factory), seed["shot"], expected_plan_hash=stored["plan_hash"],
        plan_raw=ext)
    after = await plan_svc.get_current_plan(fs(factory), seed["shot"])

    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "UPDATE shots SET duration_ms = 1000 WHERE id = :s"),
                {"s": seed["shot"]})
    out = await _resolve(engine, seed)
    assert _codes(out) == [ErrorCode.SPATIAL_SHOT_PLAN_INVALID]
    assert out.plan_hash is None  # unparseable in current context
    unchanged = await plan_svc.get_current_plan(fs(factory), seed["shot"])
    assert unchanged["plan_hash"] == after["plan_hash"]  # bytes unchanged

    # restore duration → ready again (idempotent revalidation)
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "UPDATE shots SET duration_ms = 5000 WHERE id = :s"),
                {"s": seed["shot"]})
    out2 = await _resolve(engine, seed)
    assert out2.ready is True


async def test_pack_determinism_and_issue_order(factory, engine):
    # matrix 78/79 (pack staging canonical order is by construction;
    # issue ordering is precedence-ranked, deterministic)
    seed = await _full_fixture(factory)
    out = await _resolve(engine, seed)
    staging = out.pack["staging"]
    order = [(s["entity_id"], s["spatial_track_id"]) for s in staging]
    assert order == sorted(order)
    # deterministic issues under repeated resolution
    await track_svc.patch_track(fs(factory), seed["track"]["id"],
                                requirement="required")
    await trans_svc.delete_transition(
        fs(factory), (await trans_svc.list_transitions(
            fs(factory), seed["track"]["id"]))[0]["id"])
    outs = [await _resolve(engine, seed) for _ in range(2)]
    assert outs[0].issues == outs[1].issues
