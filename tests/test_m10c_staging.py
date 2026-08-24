"""M10C-3 tests — random-access effective staging resolver (matrix 31-45).

Boundary semantics (inclusive Shot/start, exclusive Shot/end, prior
Shot/end downstream, container-start precedence, clear/re-set),
readiness (required/optional absence), applicability filtering, exact
EntityRevision attachment, unassigned-Shot conditions, corruption
fail-closed (CHECK/index bypassed), and no-prior-Shot-replay proof via
statement capture.
"""
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy import event

from soloring.errors import ErrorCode, SoloRingError
from soloring.spatial import staging
from soloring.spatial import tracks as track_svc
from soloring.spatial import transitions as trans_svc
from soloring.spatial import worlds as world_svc


def fs(factory):
    return factory()


async def _seed(factory, *, n_shots=3, track_specs=(("eva", "optional"),),
                n_sequences=1):
    """Project + world + movable Entities + narrative topology + tracks.

    Entities are named ("eva"...) with deterministic revisions
    rev-<name>; tracks created per (name, requirement) spec.
    """
    pid, loc, locrev = str(uuid.uuid4()), str(uuid.uuid4()), \
        str(uuid.uuid4())
    ids = {"pid": pid, "loc": loc, "entities": {}, "revisions": {},
           "tracks": {}, "seqs": [], "scenes": [], "shots": []}
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO projects (id, name, created_at, updated_at) "
                "VALUES (:p, 'P', 't', 't')"), {"p": pid})
            await session.execute(text(
                "INSERT INTO creative_entities (id, project_id, kind, name,"
                " created_at, updated_at) VALUES (:e, :p, 'location', 'L',"
                " 't','t')"), {"e": loc, "p": pid})
            await session.execute(text(
                "INSERT INTO entity_revisions (id, entity_id, "
                "revision_number, schema_version, spec_hash, created_at) "
                "VALUES (:r, :e, 1, 1, :h, 't')"),
                {"r": locrev, "e": loc, "h": "ab" * 32})
            for name, _req in track_specs:
                eid, rid = str(uuid.uuid4()), str(uuid.uuid4())
                ids["entities"][name] = eid
                ids["revisions"][name] = rid
                await session.execute(text(
                    "INSERT INTO creative_entities (id, project_id, kind, "
                    "name, created_at, updated_at) VALUES (:e, :p, "
                    "'character', :n, 't','t')"),
                    {"e": eid, "p": pid, "n": name})
                await session.execute(text(
                    "INSERT INTO entity_revisions (id, entity_id, "
                    "revision_number, schema_version, spec_hash, created_at)"
                    " VALUES (:r, :e, 1, 1, :h, 't')"),
                    {"r": rid, "e": eid, "h": "cd" * 32})
            shot_no = 0
            for si in range(n_sequences):
                seq, scene = str(uuid.uuid4()), str(uuid.uuid4())
                ids["seqs"].append(seq)
                ids["scenes"].append(scene)
                await session.execute(text(
                    "INSERT INTO sequences (id, project_id, position, "
                    "title) VALUES (:s, :p, :pos, 'S')"),
                    {"s": seq, "p": pid, "pos": si})
                await session.execute(text(
                    "INSERT INTO scenes (id, sequence_id, position, title) "
                    "VALUES (:c, :s, 0, 'C')"), {"c": scene, "s": seq})
                for pos in range(n_shots):
                    sh = str(uuid.uuid4())
                    shot_no += 1
                    ids["shots"].append(sh)
                    await session.execute(text(
                        "INSERT INTO shots (id, project_id, shot_number, "
                        "subject, scene_id, scene_position) VALUES "
                        "(:i, :p, :n, 'shot', :c, :pos)"),
                        {"i": sh, "p": pid, "n": shot_no, "c": scene,
                         "pos": pos})
    world = await world_svc.create_world(
        fs(factory), pid, key="lobby", name="Lobby", description=None,
        requirement="optional", location_entity_id=loc)
    ids["world"] = world
    for name, req in track_specs:
        ids["tracks"][name] = await track_svc.create_track(
            fs(factory), world["id"], entity_id=ids["entities"][name],
            requirement=req)
    return ids


async def _set(factory, ids, track_name, anchor_type, anchor_id, boundary,
              t=(0, 0, 0), r=(0, 0, 0)):
    return await trans_svc.create_transition(
        fs(factory), ids["tracks"][track_name]["id"],
        anchor_type=anchor_type, anchor_id=anchor_id, boundary=boundary,
        operation="set", translation_mm=list(t), rotation_udeg=list(r))


async def _clear(factory, ids, track_name, anchor_type, anchor_id,
                 boundary):
    return await trans_svc.create_transition(
        fs(factory), ids["tracks"][track_name]["id"],
        anchor_type=anchor_type, anchor_id=anchor_id, boundary=boundary,
        operation="clear")


async def _resolve(engine, ids, shot, *, names=None, world_id=None):
    names = names or list(ids["entities"].keys())
    revs = {ids["entities"][n]: ids["revisions"][n] for n in names}
    async with engine.connect() as conn:
        return await staging.resolve_effective_staging(
            conn, shot_id=shot,
            spatial_world_id=(world_id or ids["world"]["id"]),
            resolved_entity_revisions=revs)


# -------------------------------------------------------- boundaries

async def test_staging_target_shot_start_inclusive(factory, engine):
    # matrix 31
    ids = await _seed(factory, n_shots=3)
    await _set(factory, ids, "eva", "shot", ids["shots"][1], "start",
               t=(10, 20, 30))
    out = await _resolve(engine, ids, ids["shots"][1])
    assert len(out.states) == 1
    s = out.states[0]
    assert (s.x_mm, s.y_mm, s.z_mm) == (10, 20, 30)
    assert s.source_anchor_type == "shot" and s.source_boundary == "start"
    assert s.entity_revision_id == ids["revisions"]["eva"]


async def test_staging_target_shot_end_excluded_prior_end_downstream(
        factory, engine):
    # matrix 32 + 33
    ids = await _seed(factory, n_shots=3)
    await _set(factory, ids, "eva", "shot", ids["shots"][1], "end",
               t=(7, 8, 9))
    # target Shot 2: its own /end does not apply
    out = await _resolve(engine, ids, ids["shots"][1])
    assert out.states == ()
    assert out.absent[0].reason == "no_eligible_transition"
    # downstream Shot 3 inherits the prior Shot/end placement
    out3 = await _resolve(engine, ids, ids["shots"][2])
    assert out3.states[0].source_boundary == "end"
    assert (out3.states[0].x_mm, out3.states[0].z_mm) == (7, 9)


async def test_staging_scene_start_precedes_first_shot_start(factory,
                                                             engine):
    # matrix 34
    ids = await _seed(factory, n_shots=2)
    await _set(factory, ids, "eva", "scene", ids["scenes"][0], "start",
               t=(1, 1, 1))
    await _set(factory, ids, "eva", "shot", ids["shots"][0], "start",
               t=(2, 2, 2))
    # at the first Shot the Shot/start transition outranks Scene/start
    out = await _resolve(engine, ids, ids["shots"][0])
    assert (out.states[0].x_mm, out.states[0].y_mm) == (2, 2)
    # downstream Shot inherits the LAST transition (Shot/start), not the
    # superseded Scene/start
    out2 = await _resolve(engine, ids, ids["shots"][1])
    assert (out2.states[0].x_mm, out2.states[0].y_mm) == (2, 2)
    # Scene/start alone (no Shot transition) applies to every Shot
    ids2 = await _seed(factory, n_shots=2)
    await _set(factory, ids2, "eva", "scene", ids2["scenes"][0], "start",
               t=(1, 1, 1))
    for sh in ids2["shots"]:
        o = await _resolve(engine, ids2, sh)
        assert (o.states[0].x_mm, o.states[0].y_mm) == (1, 1)


async def test_staging_sequence_start_applies_until_superseded(factory,
                                                               engine):
    ids = await _seed(factory, n_shots=3)
    await _set(factory, ids, "eva", "sequence", ids["seqs"][0], "start",
               t=(5, 0, 0))
    await _set(factory, ids, "eva", "shot", ids["shots"][2], "start",
               t=(6, 0, 0))
    for i, expected in ((0, 5), (1, 5), (2, 6)):
        out = await _resolve(engine, ids, ids["shots"][i])
        assert out.states[0].x_mm == expected


async def test_staging_clear_absent_then_later_set_restored(factory,
                                                            engine):
    # matrix 35 + 36
    ids = await _seed(factory, n_shots=4)
    await _set(factory, ids, "eva", "scene", ids["scenes"][0], "start")
    await _clear(factory, ids, "eva", "shot", ids["shots"][1], "start")
    await _set(factory, ids, "eva", "shot", ids["shots"][2], "start",
               t=(9, 9, 9))
    out0 = await _resolve(engine, ids, ids["shots"][0])
    assert len(out0.states) == 1
    out1 = await _resolve(engine, ids, ids["shots"][1])
    assert out1.states == ()
    assert out1.absent[0].reason == "clear"
    out2 = await _resolve(engine, ids, ids["shots"][2])
    assert out2.states[0].x_mm == 9
    out3 = await _resolve(engine, ids, ids["shots"][3])
    assert out3.states[0].x_mm == 9  # restored state persists downstream


# -------------------------------------------------------- readiness

async def test_staging_required_absence_blocks_optional_succeeds(factory,
                                                                 engine):
    # matrix 37 + 38
    ids = await _seed(factory, n_shots=1,
                      track_specs=(("eva", "required"), ("car", "optional")))
    # no transitions at all: required blocks, optional is valid absence
    out = await _resolve(engine, ids, ids["shots"][0])
    assert {a.reason for a in out.absent} == {"no_eligible_transition"}
    with pytest.raises(SoloRingError) as ei:
        staging.require_track_states(out)
    assert ei.value.code == ErrorCode.SPATIAL_TRACK_STATE_REQUIRED
    assert ei.value.status_code == 409
    # optional-only absence passes
    ids2 = await _seed(factory, n_shots=1,
                       track_specs=(("car", "optional"),))
    out2 = await _resolve(engine, ids2, ids2["shots"][0])
    staging.require_track_states(out2)  # no raise
    # required track WITH effective set passes
    await _set(factory, ids, "eva", "sequence", ids["seqs"][0], "start")
    out3 = await _resolve(engine, ids, ids["shots"][0])
    staging.require_track_states(out3)


# ---------------------------------------------------- applicability

async def test_staging_unrelated_entity_and_other_world_excluded(
        factory, engine):
    # matrix 39 + 40
    ids = await _seed(factory, n_shots=1,
                      track_specs=(("eva", "optional"), ("car", "optional")))
    await _set(factory, ids, "car", "scene", ids["scenes"][0], "start",
               t=(3, 3, 3))
    # resolve with ONLY eva in the dependency set: car's track and
    # transition are irrelevant — not even "relevant transition data"
    out = await _resolve(engine, ids, ids["shots"][0], names=["eva"])
    assert out.states == () and out.absent[0].entity_id == \
        ids["entities"]["eva"]
    assert out.relevant_transition_data is False
    # other-world tracks: same dependency set resolved against a world
    # with NO tracks of these Entities — nothing applies, nothing blocks
    other_loc, other_locrev = str(uuid.uuid4()), str(uuid.uuid4())
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO creative_entities (id, project_id, kind, name,"
                " created_at, updated_at) VALUES (:e, :p, 'location', "
                "'L2', 't','t')"), {"e": other_loc, "p": ids["pid"]})
            await session.execute(text(
                "INSERT INTO entity_revisions (id, entity_id, "
                "revision_number, schema_version, spec_hash, created_at) "
                "VALUES (:r, :e, 1, 1, :h, 't')"),
                {"r": other_locrev, "e": other_loc, "h": "ff" * 32})
    other_world = await world_svc.create_world(
        fs(factory), ids["pid"], key="other", name="Other",
        description=None, requirement="optional",
        location_entity_id=other_loc)
    out2 = await _resolve(engine, ids, ids["shots"][0],
                          world_id=other_world["id"])
    assert out2.states == () and out2.absent == ()
    assert out2.relevant_transition_data is False


async def test_staging_exact_supplied_revision_emitted(factory, engine):
    # matrix 41: the resolver never re-queries revisions; a DIFFERENT
    # supplied revision id flows through untouched
    ids = await _seed(factory, n_shots=1)
    await _set(factory, ids, "eva", "scene", ids["scenes"][0], "start")
    alt_rev = str(uuid.uuid4())
    async with engine.connect() as conn:
        out = await staging.resolve_effective_staging(
            conn, shot_id=ids["shots"][0],
            spatial_world_id=ids["world"]["id"],
            resolved_entity_revisions={ids["entities"]["eva"]: alt_rev})
    assert out.states[0].entity_revision_id == alt_rev


async def test_staging_unassigned_shot_semantics(factory, engine):
    # matrix 42 + 43
    ids = await _seed(factory, n_shots=1)
    unassigned = str(uuid.uuid4())
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO shots (id, project_id, shot_number, subject) "
                "VALUES (:u, :p, 99, 'x')"),
                {"u": unassigned, "p": ids["pid"]})
    # no relevant data: no fabricated blocker
    out = await _resolve(engine, ids, unassigned)
    assert out.assigned is False
    assert out.relevant_transition_data is False
    assert out.states == () and out.absent == ()
    # relevant data: the condition is carried and strict consumers raise
    await _set(factory, ids, "eva", "scene", ids["scenes"][0], "start")
    out2 = await _resolve(engine, ids, unassigned)
    assert out2.assigned is False
    assert out2.relevant_transition_data is True
    err = staging.narrative_context_required(unassigned)
    assert err.code == ErrorCode.NARRATIVE_CONTEXT_REQUIRED


async def test_staging_missing_shot_or_world_rejected(factory, engine):
    ids = await _seed(factory, n_shots=1)
    with pytest.raises(SoloRingError) as ei:
        await _resolve(engine, ids, str(uuid.uuid4()))
    assert ei.value.code == ErrorCode.SHOT_NOT_FOUND
    with pytest.raises(SoloRingError) as ei2:
        await _resolve(engine, ids, ids["shots"][0],
                       world_id=str(uuid.uuid4()))
    assert ei2.value.status_code == 404
    # world of ANOTHER project rejected
    other_pid, other_loc, other_locrev = (str(uuid.uuid4()) for _ in range(3))
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO projects (id, name, created_at, updated_at) "
                "VALUES (:p, 'Q', 't', 't')"), {"p": other_pid})
            await session.execute(text(
                "INSERT INTO creative_entities (id, project_id, kind, name,"
                " created_at, updated_at) VALUES (:e, :p, 'location', 'L',"
                " 't','t')"), {"e": other_loc, "p": other_pid})
            await session.execute(text(
                "INSERT INTO entity_revisions (id, entity_id, "
                "revision_number, schema_version, spec_hash, created_at) "
                "VALUES (:r, :e, 1, 1, :h, 't')"),
                {"r": other_locrev, "e": other_loc, "h": "ef" * 32})
    other_world = await world_svc.create_world(
        fs(factory), other_pid, key="q", name="Q", description=None,
        requirement="optional", location_entity_id=other_loc)
    with pytest.raises(SoloRingError, match="another Project"):
        await _resolve(engine, ids, ids["shots"][0],
                       world_id=other_world["id"])


# -------------------------------------------------------- corruption

async def _corrupt(factory, sql, params=None):
    async with factory() as session:
        async with session.begin():
            conn = await session.connection()
            await conn.exec_driver_sql(
                "PRAGMA ignore_check_constraints=ON")
            await conn.execute(text(sql), params or {})
            await conn.exec_driver_sql(
                "PRAGMA ignore_check_constraints=OFF")


async def test_staging_corruption_fails_closed(factory, engine):
    # matrix 44 + §12 cells
    ids = await _seed(factory, n_shots=2)
    tr = await _set(factory, ids, "eva", "shot", ids["shots"][0], "start")

    # invalid operation domain (CHECK bypassed)
    await _corrupt(factory,
                   "UPDATE spatial_transitions SET operation = 'blink' "
                   "WHERE id = :i", {"i": tr["id"]})
    with pytest.raises(SoloRingError) as ei:
        await _resolve(engine, ids, ids["shots"][1])
    assert ei.value.code == ErrorCode.INTERNAL_INVARIANT_VIOLATION
    await _corrupt(factory,
                   "UPDATE spatial_transitions SET operation = 'set' "
                   "WHERE id = :i", {"i": tr["id"]})

    # set with partial transform (aggregate CHECK bypassed)
    await _corrupt(factory,
                   "UPDATE spatial_transitions SET roll_udeg = NULL "
                   "WHERE id = :i", {"i": tr["id"]})
    with pytest.raises(SoloRingError, match="incomplete"):
        await _resolve(engine, ids, ids["shots"][1])
    await _corrupt(factory,
                   "UPDATE spatial_transitions SET roll_udeg = 0 "
                   "WHERE id = :i", {"i": tr["id"]})

    # clear carrying transform
    await _corrupt(factory,
                   "UPDATE spatial_transitions SET operation = 'clear', "
                   "x_mm = 5 WHERE id = :i", {"i": tr["id"]})
    with pytest.raises(SoloRingError, match="non-NULL"):
        await _resolve(engine, ids, ids["shots"][1])
    await _corrupt(factory,
                   "UPDATE spatial_transitions SET operation = 'set', "
                   "x_mm = 0 WHERE id = :i", {"i": tr["id"]})

    # invalid requirement on the track
    await _corrupt(factory,
                   "UPDATE spatial_tracks SET requirement = 'sometimes' "
                   "WHERE id = :t", {"t": ids["tracks"]["eva"]["id"]})
    with pytest.raises(SoloRingError, match="requirement"):
        await _resolve(engine, ids, ids["shots"][1])
    await _corrupt(factory,
                   "UPDATE spatial_tracks SET requirement = 'optional' "
                   "WHERE id = :t", {"t": ids["tracks"]["eva"]["id"]})

    # anchor absent from canonical topology (shot unassigned post-hoc)
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "UPDATE shots SET scene_id = NULL, scene_position = NULL "
                "WHERE id = :s"), {"s": ids["shots"][0]})
    with pytest.raises(SoloRingError, match="not present in the canonical"):
        await _resolve(engine, ids, ids["shots"][1])


async def test_staging_corrupt_ambiguous_winner_fails(factory, engine):
    # matrix 44: duplicate winning coordinate with the partial unique
    # index bypassed — no ID/timestamp tie-break is permitted
    ids = await _seed(factory, n_shots=2)
    await _set(factory, ids, "eva", "shot", ids["shots"][0], "start",
               t=(1, 1, 1))
    async with factory() as session:
        async with session.begin():
            conn = await session.connection()
            await conn.exec_driver_sql(
                "DROP INDEX IF EXISTS uq_str_active_coordinate")
            dup = str(uuid.uuid4())
            await conn.execute(text(
                "INSERT INTO spatial_transitions (id, spatial_track_id, "
                "anchor_type, anchor_id, boundary, operation, x_mm, y_mm, "
                "z_mm, yaw_udeg, pitch_udeg, roll_udeg, created_at, "
                "updated_at) VALUES (:i,:t,'shot',:a,'start','set',2,2,2,"
                "0,0,0,'t','t')"),
                {"i": dup, "t": ids["tracks"]["eva"]["id"],
                 "a": ids["shots"][0]})
    with pytest.raises(SoloRingError, match="Ambiguous"):
        await _resolve(engine, ids, ids["shots"][1])


async def test_staging_never_resolves_prior_shot_operationally(factory,
                                                               engine):
    # matrix 45 + critical proof shape: resolving Shot 21 issues no SQL
    # referencing Shot 20 — capture every statement of the resolution.
    ids = await _seed(factory, n_shots=3)
    await _set(factory, ids, "eva", "shot", ids["shots"][1], "end",
               t=(42, 0, 0))  # Shot 20-analog: prior Shot/end
    shot20, shot21 = ids["shots"][1], ids["shots"][2]
    captured: list[str] = []

    def _spy(conn, cursor, statement, parameters, context, executemany):
        captured.append(str(statement) + " | " + str(parameters))

    event.listen(engine.sync_engine, "before_cursor_execute", _spy)
    try:
        async with engine.connect() as conn:
            out = await staging.resolve_effective_staging(
                conn, shot_id=shot21,
                spatial_world_id=ids["world"]["id"],
                resolved_entity_revisions={
                    ids["entities"]["eva"]: ids["revisions"]["eva"]})
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _spy)
    assert out.states[0].x_mm == 42  # inherited placement resolved
    # no statement of THIS resolution references the prior Shot
    assert not any(shot20 in s for s in captured), \
        "prior Shot was operationally consulted"
    # and the canonical bytes are stable across two direct resolutions
    async with engine.connect() as conn:
        out2 = await staging.resolve_effective_staging(
            conn, shot_id=shot21,
            spatial_world_id=ids["world"]["id"],
            resolved_entity_revisions={
                ids["entities"]["eva"]: ids["revisions"]["eva"]})
    assert staging.canonical_staging_bytes(out.states) == \
        staging.canonical_staging_bytes(out2.states)


async def test_staging_projection_shape_and_order(factory, engine):
    ids = await _seed(factory, n_shots=1,
                      track_specs=(("eva", "optional"), ("car", "optional"),
                                   ("zed", "optional")))
    for name in ("car", "eva", "zed"):  # deliberately unsorted creation
        await _set(factory, ids, name, "scene", ids["scenes"][0], "start")
    out = await _resolve(engine, ids, ids["shots"][0])
    order = [(s.entity_id, s.spatial_track_id) for s in out.states]
    assert order == sorted(order)
    proj = out.states[0].projection()
    assert proj["transform"]["translation_mm"] == [0, 0, 0]
    assert proj["transform"]["rotation_udeg"] == [0, 0, 0]
    assert set(proj) == {"spatial_track_id", "entity_id",
                         "entity_revision_id", "requirement", "transform",
                         "source_transition_id", "source_anchor_type",
                         "source_anchor_id", "source_boundary"}
