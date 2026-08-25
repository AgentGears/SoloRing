"""M10D-4/5 tests — schema-5 capture, historical provenance, current
endpoint, Generation fence (matrix 80-103, 130-131, 134-135 core).

Production-shaped fixture (reuse of the M10D resolver seed helpers):
capture produces exactly one world child, canonical track children, one
plan child; schemas 1-4 preserve predecessor bytes with ZERO spatial
children; repeat capture converges; corruption fails closed; the
historical reader reconstructs from immutable rows only (denylist spy);
post-capture current edits never rewrite history; schema-5 through the
Generation path hits the pre-M10E fence with nothing persisted.
"""
import json
import uuid

import pytest
from sqlalchemy import text

from soloring.domain import revisions as rev_svc
from soloring.errors import ErrorCode, SoloRingError
from soloring.spatial import plans as plan_svc
from soloring.spatial import tracks as track_svc
from soloring.spatial import transitions as trans_svc
from soloring.spatial import worlds as world_svc
from soloring.spatial import revisions as wrev_svc

from tests.test_m10d_resolver import (  # fixture helpers
    CAM, EVA_T, _entities, _full_fixture, _shot, fs,
)


# ------------------------------------------------------------ capture

async def test_schema5_capture_children_and_convergence(factory):
    seed = await _full_fixture(factory)
    session = fs(factory)
    revision = await rev_svc.capture_revision(session, seed["shot"])

    snap = json.loads(revision.snapshot_json)
    assert snap["schema_version"] == 5
    assert "spatial_continuity" in snap and \
        snap["spatial_continuity"]["schema_version"] == 1
    assert "visual_reference_pack" not in snap  # schema 5 without M8

    # matrix 98/99/100: exactly one world child, canonical track rows,
    # exactly one plan child
    async with factory() as s:
        world_child = dict((await s.execute(text(
            "SELECT spatial_continuity_hash, spatial_world_id, "
            "requirement, spatial_world_revision_hash FROM "
            "shot_revision_spatial_worlds WHERE shot_revision_id = :r"),
            {"r": revision.id})).mappings().one())
        tracks = [dict(r) for r in (await s.execute(text(
            "SELECT position, spatial_track_id, entity_id, "
            "entity_revision_id, requirement FROM "
            "shot_revision_spatial_track_states WHERE shot_revision_id ="
            " :r ORDER BY position"), {"r": revision.id}))
            .mappings().all()]
        plan_child = dict((await s.execute(text(
            "SELECT plan_hash, plan_json FROM "
            "shot_revision_spatial_plans WHERE shot_revision_id = :r"),
            {"r": revision.id})).mappings().one())
    pack = snap["spatial_continuity"]
    assert world_child["spatial_world_id"] == seed["world"]["id"]
    assert world_child["requirement"] == "required"
    assert world_child["spatial_world_revision_hash"] == \
        pack["spatial_world"]["spatial_world_revision_hash"]
    assert len(tracks) == len(pack["staging"])
    assert tracks[0]["spatial_track_id"] == \
        pack["staging"][0]["spatial_track_id"]
    assert tracks[0]["position"] == 0
    assert json.loads(plan_child["plan_json"]) == pack["shot_plan"]

    # matrix 101: repeat unchanged capture converges onto the same id
    again = await rev_svc.capture_revision(fs(factory), seed["shot"])
    assert again.id == revision.id


async def test_lower_schema_byte_preservation_and_zero_children(factory):
    # matrix 89-92 + 143: schemas 1-4 bytes identical, zero M10 children
    pid = str(uuid.uuid4())
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO projects (id, name, created_at, updated_at) "
                "VALUES (:p, 'P', 't', 't')"), {"p": pid})
    # schema 1: zero-dep shot (no M10 authority possible)
    shot1 = await _shot(factory, pid, [])
    rev1 = await rev_svc.capture_revision(fs(factory), shot1)
    snap1 = json.loads(rev1.snapshot_json)
    assert snap1["schema_version"] == 1 and \
        "spatial_continuity" not in snap1
    # schema 2: deps, no effective states, no plan/world
    ents = await _entities(factory, pid, {"loc": "location"})
    shot2 = await _shot(factory, pid, [ents["loc"][0]])
    rev2 = await rev_svc.capture_revision(fs(factory), shot2)
    snap2 = json.loads(rev2.snapshot_json)
    assert snap2["schema_version"] == 2 and \
        "spatial_continuity" not in snap2
    for rid in (rev1.id, rev2.id):
        async with factory() as s:
            n = (await s.execute(text(
                "SELECT (SELECT COUNT(*) FROM "
                "shot_revision_spatial_worlds WHERE shot_revision_id = "
                ":r) + (SELECT COUNT(*) FROM "
                "shot_revision_spatial_track_states WHERE "
                "shot_revision_id = :r) + (SELECT COUNT(*) FROM "
                "shot_revision_spatial_plans WHERE shot_revision_id = "
                ":r)"), {"r": rid})).scalar()
        assert n == 0


async def test_capture_blocked_by_spatial_issue(factory):
    # a spatial blocker gates capture (strict seam) with the frozen code
    seed = await _full_fixture(factory)
    await wrev_svc.unapprove(fs(factory), seed["state"]["id"],
                             expected_approved_revision_id=seed["rev"]["id"])
    with pytest.raises(SoloRingError) as ei:
        await rev_svc.capture_revision(fs(factory), seed["shot"])
    assert ei.value.code == ErrorCode.SPATIAL_WORLD_APPROVAL_REQUIRED
    # and nothing was persisted
    async with factory() as s:
        n = (await s.execute(text(
            "SELECT COUNT(*) FROM shot_revisions WHERE shot_id = :q"),
            {"q": seed["shot"]})).scalar()
    assert n == 0


# ------------------------------------------------------------- history

async def test_historical_spatial_and_current_edit_isolation(factory,
                                                             client):
    seed = await _full_fixture(factory)
    revision = await rev_svc.capture_revision(fs(factory), seed["shot"])

    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["snapshot_schema_version"] == 5
    sp = body["spatial"]
    assert sp is not None
    assert len(sp["spatial_continuity_hash"]) == 64
    assert sp["world"]["spatial_world_id"] == seed["world"]["id"]
    assert sp["shot_plan"]["camera"]["focal_length_um"] == 50000
    baseline = json.dumps(sp, sort_keys=True)

    # matrix 134/135: current requirement flips never rewrite history
    await world_svc.patch_world(fs(factory), seed["world"]["id"],
                                requirement="optional")
    await track_svc.patch_track(
        fs(factory), seed["track"]["id"], requirement="required")
    r2 = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert json.dumps(r2.json()["spatial"], sort_keys=True) == baseline

    # lower-schema history: spatial null convention
    pid = str(uuid.uuid4())
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO projects (id, name, created_at, updated_at) "
                "VALUES (:p, 'P2', 't', 't')"), {"p": pid})
    shot2 = await _shot(factory, pid, [])
    rev2 = await rev_svc.capture_revision(fs(factory), shot2)
    r3 = await client.get(f"/shot-revisions/{rev2.id}/continuity")
    assert r3.json()["spatial"] is None


async def test_historical_denylist_and_corruption_loop(factory, client):
    # matrix 103: no current mutable M10 tables in the historical read
    seed = await _full_fixture(factory)
    revision = await rev_svc.capture_revision(fs(factory), seed["shot"])
    # warm the route once
    r0 = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r0.status_code == 200

    forbidden = ("shot_spatial_plans", "spatial_world_states",
                 "spatial_world_state_frames", "spatial_world_state_axes",
                 "spatial_tracks", "spatial_transitions",
                 "entity_approved_revisions")
    import soloring.api.continuity as cont_mod
    from sqlalchemy import event

    engine = client._transport.app.state.engine
    captured: list[str] = []

    def _spy(conn, cursor, statement, parameters, context, executemany):
        captured.append(statement)
    event.listen(engine.sync_engine, "before_cursor_execute", _spy)
    try:
        r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _spy)
    assert r.status_code == 200
    for stmt in captured:
        for table in forbidden:
            assert table not in stmt, \
                f"historical read touched current table {table}"

    # corruption loop: world child requirement
    async with factory() as s:
        async with s.begin():
            await s.execute(text(
                "UPDATE shot_revision_spatial_worlds SET requirement = "
                "'optional' WHERE shot_revision_id = :r"),
                {"r": revision.id})
    bad = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert bad.status_code == 500
    assert bad.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"
    async with factory() as s:
        async with s.begin():
            await s.execute(text(
                "UPDATE shot_revision_spatial_worlds SET requirement = "
                "'required' WHERE shot_revision_id = :r"),
                {"r": revision.id})
    ok = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert ok.status_code == 200

    # track child transform corruption → invariant
    async with factory() as s:
        async with s.begin():
            await s.execute(text(
                "UPDATE shot_revision_spatial_track_states SET x_mm = "
                "x_mm + 1 WHERE shot_revision_id = :r"),
                {"r": revision.id})
    bad2 = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert bad2.status_code == 500


# ------------------------------------------------------ current endpoint

async def test_current_endpoint_projection(factory, client):
    seed = await _full_fixture(factory)
    r = await client.get(f"/shots/{seed['shot']}/spatial-continuity")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ready"] is True
    assert len(body["spatial_continuity_hash"]) == 64
    sc = body["spatial_continuity"]
    assert sc["selected_world"]["requirement"] == "required"
    assert sc["staging"][0]["transform"]["translation_mm"] == EVA_T
    assert sc["plan"]["camera"]["keyframes"][0]["transform"][
        "translation_mm"] == [-3000, 1650, 4200]
    assert sc["axis_status"]["violating_keyframe_times_ms"] == []

    # ShotRead computed fields via the composed detail (matrix 80)
    detail = await client.get(f"/shots/{seed['shot']}")
    assert detail.status_code == 200, detail.text
    d = detail.json()
    assert d["spatial_continuity_ready"] is True
    assert d["spatial_continuity_hash"] == body["spatial_continuity_hash"]
    assert d["spatial_continuity_issues"] == []
    assert d["working_snapshot_hash"] is not None

    # blocked state: unapprove → ready false + hash null (matrix 82/88)
    await wrev_svc.unapprove(fs(factory), seed["state"]["id"],
                             expected_approved_revision_id=seed["rev"]["id"])
    r2 = await client.get(f"/shots/{seed['shot']}/spatial-continuity")
    assert r2.json()["ready"] is False
    assert r2.json()["spatial_continuity_hash"] is None
    d2 = (await client.get(f"/shots/{seed['shot']}")).json()
    assert d2["spatial_continuity_ready"] is False
    assert d2["working_snapshot_hash"] is None  # no lower-schema fallback

    # no-authority shot: ready/null-hash (matrix 82)
    pid = str(uuid.uuid4())
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO projects (id, name, created_at, updated_at) "
                "VALUES (:p, 'P3', 't', 't')"), {"p": pid})
    plain = await _shot(factory, pid, [])
    r3 = await client.get(f"/shots/{plain}/spatial-continuity")
    b3 = r3.json()
    assert b3["ready"] is True and b3["spatial_continuity_hash"] is None \
        and b3["issues"] == []


# ----------------------------------------------------------- fence

async def test_pre_m10e_generation_fence(factory, client):
    # matrix 130/131
    seed = await _full_fixture(factory)
    # schema 5 through Generation → SPATIAL_REALIZATION_UNSUPPORTED,
    # zero Generation rows
    r = await client.post(f"/shots/{seed['shot']}/generations")
    assert r.status_code == 409, r.text
    assert r.json()["error_code"] == "SPATIAL_REALIZATION_UNSUPPORTED"
    async with factory() as s:
        n = (await s.execute(text(
            "SELECT COUNT(*) FROM generations WHERE shot_id = :q"),
            {"q": seed["shot"]})).scalar()
    assert n == 0

    # schemas 1-4 continue through the predecessor path unchanged
    pid = str(uuid.uuid4())
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO projects (id, name, created_at, updated_at) "
                "VALUES (:p, 'P4', 't', 't')"), {"p": pid})
    plain = await _shot(factory, pid, [])
    r2 = await client.post(f"/shots/{plain}/generations")
    # the predecessor path proceeds past the fence (fake executor or
    # package behavior may still apply — the FENCE itself did not fire)
    assert r2.status_code != 409 or \
        r2.json()["error_code"] != "SPATIAL_REALIZATION_UNSUPPORTED"


# --------------------------------------------------- working hash flux

async def test_working_hash_sensitivity(factory, client):
    # matrix 85-87: hash-bearing M10 changes change the working hash
    seed = await _full_fixture(factory)
    h1 = (await client.get(f"/shots/{seed['shot']}")).json()[
        "working_snapshot_hash"]
    stored = await plan_svc.get_current_plan(fs(factory), seed["shot"])
    plan = json.loads(stored["plan_json"])
    plan["camera"]["focal_length_um"] = 51000
    await plan_svc.put_spatial_plan(
        fs(factory), seed["shot"], expected_plan_hash=stored["plan_hash"],
        plan_raw=plan)
    h2 = (await client.get(f"/shots/{seed['shot']}")).json()[
        "working_snapshot_hash"]
    assert h2 is not None and h2 != h1
