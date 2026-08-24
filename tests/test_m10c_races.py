"""M10C-4 tests — temporal races and the moving-character critical proof
(M10C plan §9.3-§9.6; matrix 47-58).

Every race uses real asyncio tasks with Events at the actual coherent-read
snapshot seam and real production mutation services — no sleeps, no
synchronous simulations (§9.6). Both complete serializations are proven:

    BEFORE — reader pins its WAL snapshot, competitor commits, reader's
    later dependency/revision/staging reads still see the complete OLD
    value; AFTER — competitor commits first, the fresh preview sees the
    complete NEW value.

The narrative-reorder race is the M10C-added proof beyond frozen §61.
The EntityRevision-vs-preview coherence race (item 53) is the M10C
precursor of M10D's full class-6 race.
"""
import asyncio
import json
import uuid

import pytest
from sqlalchemy import text

from soloring.continuity.approvals import approve_revision
from soloring.continuity.snapshots import resolve_working_dependencies
from soloring.errors import SoloRingError
from soloring.spatial import staging
from soloring.spatial import tracks as track_svc
from soloring.spatial import transitions as trans_svc
from soloring.spatial import worlds as world_svc


def fs(factory):
    return factory()


async def _seed(factory, *, n_shots=3):
    """Full production-shaped fixture: project, Location+world, movable
    Entity with TWO revisions (rev1 approved, rev2 pending), semantic
    dependency rows on every Shot, narrative topology, one track."""
    pid, loc, locrev = str(uuid.uuid4()), str(uuid.uuid4()), \
        str(uuid.uuid4())
    eva, eva_rev1, eva_rev2 = (str(uuid.uuid4()) for _ in range(3))
    ids = {"pid": pid, "eva": eva, "eva_rev1": eva_rev1,
           "eva_rev2": eva_rev2, "shots": [], "seqs": [], "scenes": []}
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
            await session.execute(text(
                "INSERT INTO creative_entities (id, project_id, kind, name,"
                " created_at, updated_at) VALUES (:e, :p, 'character', "
                "'Eva', 't','t')"), {"e": eva, "p": pid})
            for i, rev in enumerate((eva_rev1, eva_rev2), start=1):
                await session.execute(text(
                    "INSERT INTO entity_revisions (id, entity_id, "
                    "revision_number, schema_version, spec_hash, created_at)"
                    " VALUES (:r, :e, :n, 1, :h, 't')"),
                    {"r": rev, "e": eva, "n": i, "h": f"{i:02d}" * 32})
            await session.execute(text(
                "INSERT INTO entity_approved_revisions (entity_id, "
                "revision_id, approved_at) VALUES (:e, :r, 't')"),
                {"e": eva, "r": eva_rev1})
            seq, scene = str(uuid.uuid4()), str(uuid.uuid4())
            ids["seqs"] = [seq]
            ids["scenes"] = [scene]
            await session.execute(text(
                "INSERT INTO sequences (id, project_id, position, title) "
                "VALUES (:s, :p, 0, 'S')"), {"s": seq, "p": pid})
            await session.execute(text(
                "INSERT INTO scenes (id, sequence_id, position, title) "
                "VALUES (:c, :s, 0, 'C')"), {"c": scene, "s": seq})
            for pos in range(n_shots):
                sh = str(uuid.uuid4())
                ids["shots"].append(sh)
                await session.execute(text(
                    "INSERT INTO shots (id, project_id, shot_number, "
                    "subject, scene_id, scene_position) VALUES "
                    "(:i, :p, :n, 'shot', :c, :pos)"),
                    {"i": sh, "p": pid, "n": pos + 1, "c": scene,
                     "pos": pos})
                await session.execute(text(
                    "INSERT INTO shot_entity_dependencies (shot_id, "
                    "entity_id, role, position) VALUES (:s, :e, 'cast', 0)"),
                    {"s": sh, "e": eva})
    world = await world_svc.create_world(
        fs(factory), pid, key="lobby", name="Lobby", description=None,
        requirement="optional", location_entity_id=loc)
    ids["world"] = world
    ids["track"] = await track_svc.create_track(
        fs(factory), world["id"], entity_id=eva, requirement="optional")
    return ids


async def _compose(conn, ids, shot):
    """The REAL preview composition phases after the snapshot-pinning
    first read (preview_staging's exact sequence, §10.3)."""
    deps = await resolve_working_dependencies(conn, shot)
    revisions = {d.entity_id: d.entity_revision_id for d in deps}
    return await staging.resolve_effective_staging(
        conn, shot_id=shot, spatial_world_id=ids["world"]["id"],
        resolved_entity_revisions=revisions)


async def _reader_task(engine, ids, shot, entered, release, ret):
    """Pin the WAL snapshot with the composition's own first read, then
    park on the barrier, then complete dependency/revision + staging
    reads on the SAME connection."""
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN")
        await conn.execute(text(
            "SELECT id FROM shots WHERE id = :s"), {"s": shot})
        entered.set()
        await release.wait()
        ret["outcome"] = await _compose(conn, ids, shot)
        await conn.exec_driver_sql("COMMIT")


async def _run_before_race(engine, ids, shot, competitor):
    """Reader pins snapshot → competitor commits → reader completes.
    Returns the reader's outcome (must be the complete BEFORE value)."""
    entered, release = asyncio.Event(), asyncio.Event()
    ret: dict = {}
    reader = asyncio.create_task(
        _reader_task(engine, ids, shot, entered, release, ret))

    async def comp():
        await entered.wait()
        await competitor()
        release.set()

    await asyncio.gather(reader, comp())
    return ret["outcome"]


# ------------------------------------------- transition edit vs preview

async def test_race_transition_edit_before_and_after(factory, engine):
    # matrix 47 (BEFORE) + 48 (AFTER)
    ids = await _seed(factory, n_shots=3)
    shot0, shot1, shot2 = ids["shots"]
    await trans_svc.create_transition(
        fs(factory), ids["track"]["id"], anchor_type="shot",
        anchor_id=shot1, boundary="end", operation="set",
        translation_mm=[100, 0, 0], rotation_udeg=[0, 0, 0])

    # BEFORE: snapshot pinned, then a NEW Scene/start transition commits.
    # The in-flight reader at shot0 must still see the world without it
    # (complete BEFORE: no eligible transition at all).
    async def add_scene_start():
        await trans_svc.create_transition(
            fs(factory), ids["track"]["id"], anchor_type="scene",
            anchor_id=ids["scenes"][0], boundary="start", operation="set",
            translation_mm=[-500, 0, 0], rotation_udeg=[0, 0, 0])
    out = await _run_before_race(engine, ids, shot0, add_scene_start)
    assert out.states == ()
    assert out.absent[0].reason == "no_eligible_transition"

    # AFTER: the same mutation, committed first — a fresh composition at
    # shot0 sees the Scene/start placement as the effective state.
    async with engine.connect() as conn:
        out2 = await _compose(conn, ids, shot0)
    assert out2.states[0].x_mm == -500
    assert out2.states[0].source_anchor_type == "scene"

    # BEFORE variant 2: competitor EDITS the winning transition's value
    # while a reader at shot2 is between snapshot and staging read.
    async def edit_winner():
        trs = await trans_svc.list_transitions(
            fs(factory), ids["track"]["id"])
        winner = next(t for t in trs if t["anchor_type"] == "shot"
                      and t["boundary"] == "end")
        await trans_svc.patch_transition(
            fs(factory), winner["id"], translation_mm=[777, 0, 0])
    out3 = await _run_before_race(engine, ids, shot2, edit_winner)
    assert out3.states[0].x_mm == 100  # complete BEFORE (old value)
    async with engine.connect() as conn:
        out4 = await _compose(conn, ids, shot2)
    assert out4.states[0].x_mm == 777  # complete AFTER (edited value)


async def test_race_requirement_flip_before_and_after(factory, engine):
    # matrix 49 (BEFORE) + 50 (AFTER)
    ids = await _seed(factory, n_shots=1)
    shot = ids["shots"][0]
    # required track with no set → blocker condition visible in absent
    await track_svc.patch_track(fs(factory), ids["track"]["id"],
                                requirement="required")

    # BEFORE: snapshot freezes OPTIONAL — reader sees no required blocker
    await track_svc.patch_track(fs(factory), ids["track"]["id"],
                                requirement="optional")
    async def flip_to_required():
        await track_svc.patch_track(fs(factory), ids["track"]["id"],
                                    requirement="required")
    out = await _run_before_race(engine, ids, shot, flip_to_required)
    assert out.absent[0].requirement == "optional"  # complete BEFORE
    staging.require_track_states(out)  # optional absence passes

    # AFTER: the flip committed; fresh preview sees required
    async with engine.connect() as conn:
        out2 = await _compose(conn, ids, shot)
    assert out2.absent[0].requirement == "required"  # complete AFTER
    with pytest.raises(SoloRingError) as ei:
        staging.require_track_states(out2)
    assert ei.value.status_code == 409


# ------------------------------------------- narrative reorder (M10C-added)

async def test_race_narrative_reorder_before_and_after(factory, engine):
    # matrix 51 + 52 — M10C-added beyond frozen §61: reorder commits vs
    # staging preview must yield one complete topology, never a hybrid.
    # Target = Shot at position 2 (no own transition); a transition on
    # the Shot at position 3 (x=30) is initially AFTER the target. The
    # competitor swaps the two Shots, moving that transition across the
    # target boundary — the winner flips only under the NEW topology.
    ids = await _seed(factory, n_shots=4)
    target, earlier, later = ids["shots"][2], ids["shots"][1], \
        ids["shots"][3]
    await trans_svc.create_transition(
        fs(factory), ids["track"]["id"], anchor_type="shot",
        anchor_id=earlier, boundary="start", operation="set",
        translation_mm=[20, 0, 0], rotation_udeg=[0, 0, 0])
    await trans_svc.create_transition(
        fs(factory), ids["track"]["id"], anchor_type="shot",
        anchor_id=later, boundary="start", operation="set",
        translation_mm=[30, 0, 0], rotation_udeg=[0, 0, 0])

    async def reorder():
        # swap the target (pos 2) with the later Shot (pos 3) via a
        # transient free position (active uniqueness is per-statement)
        async with factory() as session:
            async with session.begin():
                await session.execute(text(
                    "UPDATE shots SET scene_position = 999 "
                    "WHERE id = :a"), {"a": target})
                await session.execute(text(
                    "UPDATE shots SET scene_position = 2 "
                    "WHERE id = :b"), {"b": later})
                await session.execute(text(
                    "UPDATE shots SET scene_position = 3 "
                    "WHERE id = :a"), {"a": target})

    # BEFORE: old topology — the later Shot's transition is not yet
    # eligible; the earlier Shot's (x=20) is the winner
    out = await _run_before_race(engine, ids, target, reorder)
    assert out.states[0].x_mm == 20  # complete OLD ordering

    # AFTER: new topology — the swapped Shot now precedes the target,
    # its transition is eligible and outranks (x=30)
    async with engine.connect() as conn:
        out2 = await _compose(conn, ids, target)
    assert out2.states[0].x_mm == 30  # complete NEW ordering


# ------------------------------------- EntityRevision coherence (item 53)

async def test_race_entityrevision_mutation_during_live_preview(
        factory, engine):
    # matrix 53 — REAL concurrent approval mutation with a REAL barrier
    # at the preview's snapshot seam. BEFORE: the in-flight preview sees
    # the complete OLD revision; AFTER: a fresh preview sees the NEW one.
    ids = await _seed(factory, n_shots=1)
    shot = ids["shots"][0]
    await trans_svc.create_transition(
        fs(factory), ids["track"]["id"], anchor_type="scene",
        anchor_id=ids["scenes"][0], boundary="start", operation="set",
        translation_mm=[1, 2, 3], rotation_udeg=[0, 0, 0])

    async def approve_rev2():
        await approve_revision(
            fs(factory), ids["eva"], ids["eva_rev2"],
            expected_approved_revision_id=ids["eva_rev1"])

    out = await _run_before_race(engine, ids, shot, approve_rev2)
    assert out.states[0].entity_revision_id == ids["eva_rev1"]  # OLD

    async with engine.connect() as conn:
        out2 = await _compose(conn, ids, shot)
    assert out2.states[0].entity_revision_id == ids["eva_rev2"]  # NEW
    # the projection the UI would render carries the exact revision too
    body = await staging.preview_staging(
        fs(factory), spatial_world_id=ids["world"]["id"], shot_id=shot)
    assert body["states"][0]["entity_revision_id"] == ids["eva_rev2"]


# --------------------------------------- moving-character critical proof

async def test_critical_moving_character_no_replay_no_take_authority(
        factory, engine):
    # matrix 54-58 — the frozen §84 proof.
    ids = await _seed(factory, n_shots=4)  # Shots 18,19,20,21 by role
    shot20, shot21 = ids["shots"][2], ids["shots"][3]
    # Shot 20/start: Eva at lobby entrance
    await trans_svc.create_transition(
        fs(factory), ids["track"]["id"], anchor_type="shot",
        anchor_id=shot20, boundary="start", operation="set",
        translation_mm=[0, 0, -8000], rotation_udeg=[0, 0, 0])
    # Shot 20/end: explicit transition near the front desk
    await trans_svc.create_transition(
        fs(factory), ids["track"]["id"], anchor_type="shot",
        anchor_id=shot20, boundary="end", operation="set",
        translation_mm=[-1200, 0, -2400], rotation_udeg=[0, 90000000, 0])

    # 55: Shot 21 resolves the front-desk transform DIRECTLY
    async with engine.connect() as conn:
        out = await _compose(conn, ids, shot21)
    assert (out.states[0].x_mm, out.states[0].z_mm) == (-1200, -2400)
    assert out.states[0].source_boundary == "end"
    assert out.states[0].source_anchor_id == shot20

    # 56: no prior-Shot consultation — statement capture during resolve
    from sqlalchemy import event as _event
    captured: list[str] = []

    def _spy(conn_, cursor, statement, parameters, context, executemany):
        captured.append(str(statement) + str(parameters))

    _event.listen(engine.sync_engine, "before_cursor_execute", _spy)
    try:
        async with engine.connect() as conn:
            await _compose(conn, ids, shot21)
    finally:
        _event.remove(engine.sync_engine, "before_cursor_execute", _spy)
    assert not any(shot20 in s for s in captured) or \
        sum(shot20 in s for s in captured) == 0

    # 57: changing Shot 20's rendered Take does not alter Shot 21 staging
    take = str(uuid.uuid4())
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "UPDATE shots SET approved_take_id = :t WHERE id = :s"),
                {"t": take, "s": shot20})
    async with engine.connect() as conn:
        out2 = await _compose(conn, ids, shot21)
    assert staging.canonical_staging_bytes(out2.states) == \
        staging.canonical_staging_bytes(out.states)

    # 58: current-plan blocking/UI-side changes alone do not alter
    # persistent staging (plan_json is NOT staging authority)
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO shot_spatial_plans (shot_id, "
                "spatial_world_id, plan_json, plan_hash, created_at, "
                "updated_at) VALUES (:s, :w, :j, :h, 't', 't')"),
                {"s": shot20, "w": ids["world"]["id"],
                 "j": json.dumps({
                     "schema_version": 1,
                     "spatial_world_id": ids["world"]["id"],
                     "blocking": [{"spatial_track_id":
                                   ids["track"]["id"]}],
                     "camera": {"keyframes": []}}),
                 "h": "1" * 64})
    async with engine.connect() as conn:
        out3 = await _compose(conn, ids, shot21)
    assert staging.canonical_staging_bytes(out3.states) == \
        staging.canonical_staging_bytes(out.states)


# ------------------------------------------- preview endpoint (API level)

async def _api_entity_approved(client, pid, kind, name):
    e = await client.post(f"/projects/{pid}/entities",
                          json={"kind": kind, "name": name})
    assert e.status_code == 201, e.text
    eid = e.json()["id"]
    rev = await client.post(f"/entities/{eid}/revisions",
                            json={"spec": {"description": "d"}})
    assert rev.status_code == 201, rev.text
    app = await client.put(f"/entities/{eid}/approved-revision",
                           json={"revision_id": rev.json()["id"],
                                 "expected_approved_revision_id": None})
    assert app.status_code == 200, app.text
    return eid, rev.json()["id"]


async def test_preview_endpoint_current_staging_projection(client, factory):
    # matrix 63-65 at the transport level: exact EntityRevision,
    # winning-transition provenance, distinct absence states — labeled
    # as CURRENT staging only (no captured-history vocabulary).
    r = await client.post("/projects", json={"name": "P"})
    pid = r.json()["id"]
    loc, _ = await _api_entity_approved(client, pid, "location", "Lobby")
    eva, eva_rev = await _api_entity_approved(client, pid, "character",
                                              "Eva")
    car, car_rev = await _api_entity_approved(client, pid, "prop", "Car")
    wr = await client.post(f"/projects/{pid}/spatial-worlds", json={
        "key": "lobby", "name": "Lobby", "requirement": "optional",
        "location_entity_id": loc})
    world_id = wr.json()["id"]
    eva_track = (await client.post(f"/spatial-worlds/{world_id}/tracks",
                                   json={"entity_id": eva,
                                         "requirement": "optional"})
                 ).json()["id"]
    await client.post(f"/spatial-worlds/{world_id}/tracks",
                      json={"entity_id": car, "requirement": "required"})
    sr = await client.post(f"/projects/{pid}/sequences",
                           json={"title": "S"})
    seq = sr.json()["id"]
    cr = await client.post(f"/sequences/{seq}/scenes", json={"title": "C"})
    scene = cr.json()["id"]
    shots = []
    for i in range(3):
        sh = await client.post(f"/projects/{pid}/shots",
                               json={"subject": f"shot {i}"})
        shots.append(sh.json()["id"])
    await client.put(f"/scenes/{scene}/shots", json={"shot_ids": shots})
    for sh in shots:
        dep = await client.put(f"/shots/{sh}/semantic-dependencies", json={
            "dependencies": [
                {"entity_id": eva, "role": "cast"},
                {"entity_id": car, "role": "prop"}]})
        assert dep.status_code == 200, dep.text
    await client.post(f"/spatial-tracks/{eva_track}/transitions", json={
        "anchor_type": "shot", "anchor_id": shots[1], "boundary": "end",
        "operation": "set", "translation_mm": [-1200, 0, -2400],
        "rotation_udeg": [0, 90000000, 0]})

    # Shot 21 analog: direct resolution with full provenance
    pr = await client.get(
        f"/spatial-worlds/{world_id}/staging?shot_id={shots[2]}")
    assert pr.status_code == 200, pr.text
    body = pr.json()
    assert body["assigned"] is True
    assert body["narrative_context_required"] is False
    assert len(body["states"]) == 1
    st = body["states"][0]
    assert st["entity_revision_id"] == eva_rev
    assert st["entity_name"] == "Eva"
    assert st["source_anchor_type"] == "shot"
    assert st["source_anchor_id"] == shots[1]
    assert st["source_boundary"] == "end"
    assert st["transform"]["translation_mm"] == [-1200, 0, -2400]
    assert st["transform"]["rotation_udeg"] == [0, 90000000, 0]
    # the required Car track has no state: distinct honest absence
    assert len(body["absent"]) == 1
    ab = body["absent"][0]
    assert ab["requirement"] == "required"
    assert ab["reason"] == "no_eligible_transition"
    assert ab["entity_revision_id"] == car_rev
    # no captured/history vocabulary in the projection
    flat = json.dumps(body)
    assert "captured" not in flat.lower()
    assert "ShotRevision" not in flat

    # Shot 1 (before the transition): required-absent + optional-absent
    pr1 = await client.get(
        f"/spatial-worlds/{world_id}/staging?shot_id={shots[0]}")
    b1 = pr1.json()
    assert b1["states"] == [] and len(b1["absent"]) == 2
    assert {a["requirement"] for a in b1["absent"]} == \
        {"required", "optional"}

    # unassigned Shot with relevant transition data
    un = (await client.post(f"/projects/{pid}/shots",
                            json={"subject": "unassigned"})).json()["id"]
    await client.put(f"/shots/{un}/semantic-dependencies", json={
        "dependencies": [{"entity_id": eva, "role": "cast"}]})
    pu = await client.get(
        f"/spatial-worlds/{world_id}/staging?shot_id={un}")
    bu = pu.json()
    assert bu["assigned"] is False
    assert bu["narrative_context_required"] is True

    # missing Shot → honest 404
    pm = await client.get(
        f"/spatial-worlds/{world_id}/staging?shot_id={uuid.uuid4()}")
    assert pm.status_code == 404
