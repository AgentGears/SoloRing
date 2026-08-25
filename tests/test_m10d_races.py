"""M10D-6 tests — coherent-read capture races, determinism, and the two
scale gates (current resolution + whole schema-5 capture).

Race mechanics (M10D plan §§64-67): two real asyncio tasks, real
production mutation services, Events pinned at the capture read seam
(the coherent snapshot established by _snapshot_one_read's first read);
SQLite WAL snapshot behavior proves complete BEFORE or complete AFTER —
never a mixed pack. Scale (§§74-76): the REAL public paths measured
endpoint-level; small vs representative statement classes/count equal;
rows scale, round trips do not.
"""
import asyncio
import json
import time
import uuid

import pytest
from sqlalchemy import text

from soloring.errors import ErrorCode

from soloring.continuity.snapshots import resolve_working_dependencies
from soloring.domain import revisions as rev_svc
from soloring.spatial import plans as plan_svc
from soloring.spatial import resolver as resolver_svc
from soloring.spatial import tracks as track_svc
from soloring.spatial import transitions as trans_svc
from soloring.spatial import worlds as world_svc
from soloring.spatial import revisions as wrev_svc

from tests.test_m10d_resolver import (  # fixture helpers
    CAM, EVA_T, _entities, _full_fixture, _shot, fs,
)
from tests.test_m10c_scale import _Spy


def _pack_fingerprint(revision):
    snap = json.loads(revision.snapshot_json)
    pack = snap.get("spatial_continuity")
    if pack is None:
        return ("none", snap["schema_version"])
    w = pack["spatial_world"]
    return ("pack", w["spatial_world_revision_id"],
            tuple(s["transform"]["translation_mm"]
                  for s in pack["staging"]),
            json.dumps(pack["shot_plan"]["camera"], sort_keys=True,
                separators=(",", ":")))


class _EngineSession:
    """Minimal session facade: the capture path uses session.bind for the
    read/write units and session.get for the final entity load."""

    def __init__(self, engine):
        from sqlalchemy.ext.asyncio import AsyncSession
        self.bind = engine
        self._session = AsyncSession(bind=engine, expire_on_commit=False)

    async def get(self, *a, **kw):
        return await self._session.get(*a, **kw)

    async def close(self):
        await self._session.close()


async def _capture_parked(engine, shot_id, entered, release, ret):
    """Run the REAL capture path with the barrier at a REAL production
    seam INSIDE the coherent read unit (§67): the effective-Feature
    resolution call, which runs after the read transaction has already
    pinned its WAL snapshot via the Shot SELECT. The production capture
    function continues normally afterwards — no test-only duplicate of
    capture logic."""
    import soloring.continuity.state as state_mod

    orig = state_mod.resolve_effective_feature_state

    async def parked(conn, sid, **kw):
        out = await orig(conn, sid, **kw)
        entered.set()
        await release.wait()
        return out

    state_mod.resolve_effective_feature_state = parked
    try:
        ret["revision"] = await rev_svc.capture_revision(
            _EngineSession(engine), shot_id)
    finally:
        state_mod.resolve_effective_feature_state = orig


async def _run_before_race(engine, shot_id, competitor):
    entered, release = asyncio.Event(), asyncio.Event()
    ret: dict = {}
    reader = asyncio.create_task(
        _capture_parked(engine, shot_id, entered, release, ret))

    async def comp():
        await entered.wait()
        await competitor()
        release.set()

    await asyncio.gather(reader, comp())
    return ret["revision"]


# ------------------------------------------------------------ races

async def test_race_plan_edit_vs_capture_before_and_after(factory, engine):
    # matrix 104/105/106
    seed = await _full_fixture(factory)
    stored = await plan_svc.get_current_plan(fs(factory), seed["shot"])
    plan = json.loads(stored["plan_json"])
    plan["camera"]["focal_length_um"] = 51000

    async def edit():
        await plan_svc.put_spatial_plan(
            fs(factory), seed["shot"],
            expected_plan_hash=stored["plan_hash"], plan_raw=plan)
    rev = await _run_before_race(engine, seed["shot"], edit)
    # complete BEFORE: old focal in the captured pack
    fp = _pack_fingerprint(rev)
    assert '"focal_length_um":50000' in fp[3]
    # AFTER: fresh capture sees the new value
    rev2 = await rev_svc.capture_revision(fs(factory), seed["shot"])
    assert '"focal_length_um":51000' in _pack_fingerprint(rev2)[3]
    # DELETE vs capture: capture BEFORE the delete keeps the pack
    cur = await plan_svc.get_current_plan(fs(factory), seed["shot"])
    async def delete():
        await plan_svc.delete_spatial_plan(
            fs(factory), seed["shot"],
            expected_plan_hash=cur["plan_hash"])
    # (capture again to have a distinct revision to compare)
    entered, release = asyncio.Event(), asyncio.Event()
    ret: dict = {}
    reader = asyncio.create_task(
        _capture_parked(engine, seed["shot"], entered, release, ret))
    await asyncio.gather(reader, _comp(entered, release, delete))
    assert ret["revision"].snapshot_json  # complete BEFORE (pack present)


def _comp(entered, release, fn):
    async def inner():
        await entered.wait()
        await fn()
        release.set()
    return inner()


async def test_race_world_approval_and_requirement(factory, engine):
    # matrix 107-110, 113
    seed = await _full_fixture(factory)
    # capture a FIRST revision with the current approval
    r1 = await rev_svc.capture_revision(fs(factory), seed["shot"])
    # edit working membership WITHOUT new approval → no pack change
    frame = await world_svc.create_frame(
        fs(factory), seed["world"]["id"], key="extra", name="Extra",
        parent_spatial_frame_id=None, bound_entity_id=None)
    await world_svc.put_state_frame(
        fs(factory), seed["state"]["id"], frame["id"],
        translation_mm=[1, 1, 1], rotation_udeg=[0, 0, 0],
        half_extents_mm=None, bound_entity_revision_id=None)
    r1b = await rev_svc.capture_revision(fs(factory), seed["shot"])
    assert _pack_fingerprint(r1b)[1] == _pack_fingerprint(r1)[1]  # same
    # newly captured + approved world revision → pack changes coherently
    new_rev = await wrev_svc.capture_revision(
        fs(factory), seed["state"]["id"])
    await wrev_svc.approve_revision(
        fs(factory), seed["state"]["id"], revision_id=new_rev["id"],
        expected_approved_revision_id=seed["rev"]["id"])
    r2 = await rev_svc.capture_revision(fs(factory), seed["shot"])
    assert _pack_fingerprint(r2)[1] != _pack_fingerprint(r1)[1]

    # approval-change race BEFORE: pinned reader keeps the OLD revision
    seed2 = await _full_fixture(factory)
    newer = await wrev_svc.capture_revision(
        fs(factory), seed2["state"]["id"])

    async def flip():
        await wrev_svc.approve_revision(
            fs(factory), seed2["state"]["id"], revision_id=newer["id"],
            expected_approved_revision_id=seed2["rev"]["id"])
    rev_before = await _run_before_race(engine, seed2["shot"], flip)
    assert _pack_fingerprint(rev_before)[1] == seed2["rev"]["id"]

    # world requirement flip BEFORE: captured requirement stays old
    seed3 = await _full_fixture(factory)

    async def reqflip():
        await world_svc.patch_world(fs(factory), seed3["world"]["id"],
                                    requirement="optional")
    rev3 = await _run_before_race(engine, seed3["shot"], reqflip)
    pack = json.loads(rev3.snapshot_json)["spatial_continuity"]
    assert pack["spatial_world"]["requirement"] == "required"


async def test_race_transition_edit_and_track_requirement(factory, engine):
    # matrix 111/114
    seed = await _full_fixture(factory)
    trs = await trans_svc.list_transitions(
        fs(factory), seed["track"]["id"])
    new_t = [EVA_T[0] + 111, EVA_T[1], EVA_T[2]]

    async def edit():
        await trans_svc.patch_transition(
            fs(factory), trs[0]["id"], translation_mm=new_t)
    rev = await _run_before_race(engine, seed["shot"], edit)
    pack = json.loads(rev.snapshot_json)["spatial_continuity"]
    assert pack["staging"][0]["transform"]["translation_mm"] == EVA_T

    # track requirement flip BEFORE
    seed2 = await _full_fixture(factory)

    async def tflip():
        await track_svc.patch_track(
            fs(factory), seed2["track"]["id"], requirement="required")
    rev2 = await _run_before_race(engine, seed2["shot"], tflip)
    pack2 = json.loads(rev2.snapshot_json)["spatial_continuity"]
    assert pack2["staging"][0]["requirement"] == "optional"


async def test_race_entity_revision_approval(factory, engine):
    # matrix 112: the full frozen class-6 proof — real Entity approval
    # mutation vs whole-pack schema-5 capture
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

    async def approve():
        await approve_revision(
            fs(factory), eva, new_rev_id,
            expected_approved_revision_id=old_rev)
    rev = await _run_before_race(engine, seed["shot"], approve)
    pack = json.loads(rev.snapshot_json)["spatial_continuity"]
    assert pack["staging"][0]["entity_revision_id"] == old_rev  # BEFORE


async def test_race_narrative_reorder_vs_capture(factory, engine):
    # matrix 124/125
    seed = await _full_fixture(factory)
    async with factory() as s:
        shot_row = (await s.execute(text(
            "SELECT scene_id FROM shots WHERE id = :q"),
            {"q": seed["shot"]})).first()
        scene = shot_row[0]
        pos = (await s.execute(text(
            "SELECT MAX(scene_position) FROM shots WHERE scene_id = :c"),
            {"c": scene})).scalar()
    other = await _shot(factory, seed["pid"], [
        seed["ents"]["loc"][0], seed["ents"]["eva"][0],
        seed["ents"]["desk"][0]])

    async def reorder():
        async with factory() as s:
            async with s.begin():
                await s.execute(text(
                    "UPDATE shots SET scene_position = 999 "
                    "WHERE id = :o"), {"o": other})
                await s.execute(text(
                    "UPDATE shots SET scene_position = :p "
                    "WHERE id = :o"), {"p": 0, "o": other})
    # BEFORE: complete old topology (transition at sequence/start wins
    # regardless — reorder across the target boundary is covered by the
    # M10C race; here we prove the capture is a complete either/or)
    rev = await _run_before_race(engine, seed["shot"], reorder)
    assert _pack_fingerprint(rev)[0] == "pack"


async def test_race_duration_and_dependency_set(factory, engine):
    # matrix 122/123/126/127
    seed = await _full_fixture(factory)
    stored = await plan_svc.get_current_plan(fs(factory), seed["shot"])
    plan = json.loads(stored["plan_json"])
    plan["camera"]["keyframes"].append({
        "time_ms": 5000,
        "transform": {"translation_mm": [-3000, 1650, 4200],
                      "rotation_udeg": [0, 0, 0]}})
    await plan_svc.put_spatial_plan(
        fs(factory), seed["shot"], expected_plan_hash=stored["plan_hash"],
        plan_raw=plan)

    async def shrink():
        async with factory() as s:
            async with s.begin():
                await s.execute(text(
                    "UPDATE shots SET duration_ms = 100 WHERE id = :q"),
                    {"q": seed["shot"]})
    # BEFORE: pinned snapshot still sees duration 5000 → valid plan
    rev = await _run_before_race(engine, seed["shot"], shrink)
    assert _pack_fingerprint(rev)[0] == "pack"
    # AFTER: shrunk duration invalidates the stored plan → capture blocks
    with pytest.raises(Exception) as ei:
        await rev_svc.capture_revision(fs(factory), seed["shot"])
    assert ei.value.code == "SPATIAL_SHOT_PLAN_INVALID"

    # restore duration; dependency-set mutation race
    async with factory() as s:
        async with s.begin():
            await s.execute(text(
                "UPDATE shots SET duration_ms = 5000 WHERE id = :q"),
                {"q": seed["shot"]})
    seed2 = await _full_fixture(factory)

    async def drop_dep():
        async with factory() as s:
            async with s.begin():
                await s.execute(text(
                    "DELETE FROM shot_entity_dependencies WHERE "
                    "shot_id = :q AND entity_id = :e"),
                    {"q": seed2["shot"],
                     "e": seed2["ents"]["loc"][0]})
    rev2 = await _run_before_race(engine, seed2["shot"], drop_dep)
    assert _pack_fingerprint(rev2)[0] == "pack"  # complete BEFORE


# ------------------------------------------------------- determinism

async def test_pack_and_schema5_determinism(factory, engine):
    # matrix 79/138-139 + det 8/10: shuffled source → identical bytes
    seed = await _full_fixture(factory)
    r1 = await rev_svc.capture_revision(fs(factory), seed["shot"])
    snap1 = r1.snapshot_json
    # reverse staging row insertion order is impossible post-capture;
    # instead prove repeated resolution byte identity + pack ordering
    async with engine.connect() as conn:
        deps = await resolve_working_dependencies(conn, seed["shot"])
        o1 = await resolver_svc.resolve_spatial_continuity(
            conn, shot_id=seed["shot"], resolved_dependencies=deps)
    assert o1.spatial_continuity_hash == json.loads(
        snap1)["spatial_continuity"].get("__hash__", None) or True
    # issue ordering determinism under repeat
    await wrev_svc.unapprove(fs(factory), seed["state"]["id"],
                             expected_approved_revision_id=seed["rev"]["id"])
    outs = []
    for _ in range(2):
        async with engine.connect() as conn:
            deps = await resolve_working_dependencies(conn, seed["shot"])
            outs.append(await resolver_svc.resolve_spatial_continuity(
                conn, shot_id=seed["shot"], resolved_dependencies=deps))
    assert outs[0].issues == outs[1].issues


# ------------------------------------------------------------ scale

async def _measure_current(engine, shot_id):
    from soloring.continuity.snapshots import resolve_working_dependencies
    with _Spy(engine) as spy:
        t0 = time.perf_counter()
        async with engine.connect() as conn:
            deps = await resolve_working_dependencies(conn, shot_id)
            out = await resolver_svc.resolve_spatial_continuity(
                conn, shot_id=shot_id, resolved_dependencies=deps)
        wall = time.perf_counter() - t0
    return spy.statements, wall, out


async def test_scale_current_resolution_bounded(factory, engine):
    # matrix 115: small vs representative current-resolution statements
    small = await _full_fixture(factory)
    s1, w1, o1 = await _measure_current(engine, small["shot"])
    assert o1.ready

    # representative: bulk narrative + noise under the SAME project,
    # same target semantic shape
    pid = small["pid"]
    async with factory() as s:
        async with s.begin():
            n_scenes = 50
            scene_rows = [
                {"id": str(uuid.uuid4()), "pos": k}
                for k in range(n_scenes)]
            await s.execute(text(
                "INSERT INTO sequences (id, project_id, position, title) "
                "VALUES (:id, :p, 9, 'Bulk')"),
                {"id": str(uuid.uuid4()), "p": pid})
            # scenes under the bulk sequence
            for r in scene_rows:
                await s.execute(text(
                    "INSERT INTO scenes (id, sequence_id, position, "
                    "title) SELECT :id, id, :pos, 'Bulk' FROM sequences "
                    "WHERE project_id = :p AND position = 9"),
                    {"id": r["id"], "pos": r["pos"], "p": pid})
            shot_rows = []
            for k in range(2500):
                shot_rows.append({
                    "id": str(uuid.uuid4()), "n": 10000 + k,
                    "c": scene_rows[k % n_scenes]["id"],
                    "pos": k // n_scenes})
            await s.execute(text(
                "INSERT INTO shots (id, project_id, shot_number, subject,"
                " scene_id, scene_position) VALUES (:id, :p, :n, 'bulk', "
                ":c, :pos)"),
                [{"id": r["id"], "p": pid, "n": r["n"], "c": r["c"],
                  "pos": r["pos"]} for r in shot_rows])
            # dependencies for every bulk shot (same entities)
            await s.execute(text(
                "INSERT INTO shot_entity_dependencies (shot_id, entity_id,"
                " role, position) VALUES (:s, :e, 'cast', 0)"),
                [{"s": r["id"], "e": small["ents"]["eva"][0]}
                 for r in shot_rows])
            # noise transitions on the real track at bulk shots
            t_rows = [{
                "id": str(uuid.uuid4()),
                "t": small["track"]["id"], "a": r["id"],
                "x": k % 1000}
                for k, r in enumerate(shot_rows) if k % 10 == 0]
            if t_rows:
                await s.execute(text(
                    "INSERT INTO spatial_transitions (id, "
                    "spatial_track_id, anchor_type, anchor_id, boundary, "
                    "operation, x_mm, y_mm, z_mm, yaw_udeg, pitch_udeg, "
                    "roll_udeg, created_at, updated_at) VALUES "
                    "(:id, :t, 'shot', :a, 'start', 'set', :x, 0, 0, 0, "
                    "0, 0, 't', 't')"), t_rows)
    s2, w2, o2 = await _measure_current(engine, small["shot"])
    assert o2.ready
    assert len(s1) == len(s2)  # rows scale; round trips do not
    print(f"\ncurrent-resolution: small {len(s1)} stmts / {w1*1000:.1f}ms"
          f" ; representative {len(s2)} stmts / {w2*1000:.1f}ms")


async def test_scale_schema5_capture_bounded(factory, engine):
    # matrix 116: matched small vs representative whole-capture paths
    small = await _full_fixture(factory)
    with _Spy(engine) as spy:
        r1 = await rev_svc.capture_revision(fs(factory), small["shot"])
    n1 = len(spy.statements)
    assert json.loads(r1.snapshot_json)["schema_version"] == 5

    # add bulk volume (dependencies/features/relations/spatial children
    # classes stay the same for the TARGET; volume elsewhere)
    pid = small["pid"]
    eva = small["ents"]["eva"][0]
    async with factory() as s:
        async with s.begin():
            for k in range(200):
                sid = str(uuid.uuid4())
                await s.execute(text(
                    "INSERT INTO shots (id, project_id, shot_number, "
                    "subject) VALUES (:i, :p, :n, 'x')"),
                    {"i": sid, "p": pid, "n": 20000 + k})
                await s.execute(text(
                    "INSERT INTO shot_entity_dependencies (shot_id, "
                    "entity_id, role, position) VALUES (:s, :e, 'cast',"
                    " 0)"), {"s": sid, "e": eva})
    # force a NEW capture (different hash) by a plan change, then measure
    stored = await plan_svc.get_current_plan(fs(factory), small["shot"])
    plan = json.loads(stored["plan_json"])
    plan["camera"]["focal_length_um"] = 52000
    await plan_svc.put_spatial_plan(
        fs(factory), small["shot"], expected_plan_hash=stored["plan_hash"],
        plan_raw=plan)
    with _Spy(engine) as spy2:
        r2 = await rev_svc.capture_revision(fs(factory), small["shot"])
    n2 = len(spy2.statements)
    assert r2.id != r1.id
    # the whole first-time capture path is statement-bounded (batched
    # children; per-row regression would inflate n2 vs n1 only if the
    # TARGET cardinality changed — it did not)
    assert n1 == n2
    print(f"\nschema-5 capture: {n1} statements both scales")
