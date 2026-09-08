"""M13 scale proofs (frozen R3 §30.10 M13-SCALE:01-03 / §26).

Feature-film cardinality changes rows, not SQL round-trip classes: query
counts for binding readiness/publication (incl. the in-fence re-derivation)
and the current Shot resolver (incl. staleness re-derivation) are equal
between a small fixture and the representative §26.2 fixture. Rows/bytes
are recorded honestly; no latency threshold is claimed.
"""

from __future__ import annotations

import hashlib
import json

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.m13_seed import make_entity, make_composition, seed_base

NOW = "2026-01-01T00:00:00.000Z"

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


def _factory(client):
    from tests.conftest import make_tracked_maker

    return make_tracked_maker(client._transport.app.state.engine)


async def _seed_at_scale(client, *, n_occurrences, n_pi_subjects,
                         n_ce_subjects, n_features, n_feature_transitions,
                         n_spatial_transitions, tag):
    """One §26.2-shaped world at the requested cardinality (bulk SQL for
    the row populations; real services for every authority decision)."""
    from soloring.domain.ids import new_uuid
    from soloring.production.canonical import (
        RetainedBlobClosure,
        production_revision_snapshot_json as sj,
        production_revision_snapshot_hash as sh,
    )

    base = await seed_base(client, tag=tag)
    pid = base["project_id"]
    f = _factory(client)

    # narrative anchors (a pool so bulk transitions sit on distinct
    # active coordinates)
    engine = client._transport.app.state.engine
    r = await client.post(f"/projects/{pid}/sequences", json={"title": "S"})
    seq = r.json()["id"]
    seqs = [seq]
    for i in range(9):
        r = await client.post(f"/projects/{pid}/sequences",
                              json={"title": f"S{i}"})
        seqs.append(r.json()["id"])
    r = await client.post(f"/sequences/{seq}/scenes", json={"title": "C"})
    scene = r.json()["id"]
    shot = None  # created below with the frame set
    from tests.test_m13_shot_capture import _entity_approved

    loc, locrev = await _entity_approved(client, pid, "location", "Set")

    # spatial world + approved revision (single frame)
    from soloring.spatial import revisions as rev_svc
    from soloring.spatial import worlds as world_svc

    world = await world_svc.create_world(
        f(), pid, key="lobby", name="Lobby", description=None,
        requirement="required", location_entity_id=loc)
    state = await world_svc.create_state(
        f(), world["id"], location_entity_revision_id=locrev)
    fr = await world_svc.create_frame(
        f(), world["id"], key="origin", name="origin",
        parent_spatial_frame_id=None, bound_entity_id=None)
    await world_svc.put_state_frame(
        f(), state["id"], fr["id"], translation_mm=[0, 0, 0],
        rotation_udeg=[0, 0, 0], half_extents_mm=None,
        bound_entity_revision_id=None)
    rev = await rev_svc.capture_revision(f(), state["id"])
    await rev_svc.approve_revision(
        f(), state["id"], revision_id=rev["id"],
        expected_approved_revision_id=None)

    # composition + bulk direct occurrences (working + identity rows)
    cid = await make_composition(client, pid)
    prid = base["production_revision_id"]
    shot = new_uuid()
    async with engine.connect() as conn:
        await conn.execute(text(
            "INSERT INTO shots (id, project_id, shot_number, subject, "
            "duration_ms, scene_id, scene_position) VALUES "
            "(:s, :p, 1, 'shot', 1000, :c, 0)"),
            {"s": shot, "p": pid, "c": scene})
        await conn.execute(text(
            "INSERT INTO shot_entity_dependencies (shot_id, entity_id, "
            "role, position) VALUES (:s, :e, 'location', 0)"),
            {"s": shot, "e": loc})
        occ_rows, work_rows = [], []
        for i in range(n_occurrences):
            oid = new_uuid()
            occ_rows.append({"id": oid, "cid": cid})
            work_rows.append({
                "cid": cid, "oid": oid, "name": f"Instance {i}",
                "prid": prid,
                "x": 0, "y": 0, "z": 0, "yaw": 0, "pitch": 0,
                "roll": 0})
        await conn.execute(text(
            "INSERT INTO composition_occurrences (id, composition_id, "
            "created_at) VALUES (:id, :cid, :n)"),
            [{**r, "n": NOW} for r in occ_rows])
        await conn.execute(text(
            "INSERT INTO composition_working_occurrences (composition_id,"
            " occurrence_id, display_name, source_kind, "
            "production_revision_id, nested_composition_revision_id, "
            "visible, x_mm, y_mm, z_mm, yaw_udeg, pitch_udeg, roll_udeg, "
            "updated_at) VALUES (:cid, :oid, :name, 'production_revision',"
            " :prid, NULL, 1, :x, :y, :z, :yaw, :pitch, :roll, :n)"),
            [{**r, "n": NOW} for r in work_rows])
        await conn.commit()

    # publish the exact C over the whole working set (real service)
    from soloring.composition.readiness import publish_composition_revision

    async with f() as s:
        pub, _ = await publish_composition_revision(
            s, cid, expected_working_version=0)
    c_id = pub["revision_id"]

    # one interpretation for the shared Production Revision
    r = await client.post(
        f"/production-revisions/{prid}/spatial-interpretation",
        json={"realization_local_to_subject_local": {
            "translation_mm": [0, 0, 0], "rotation_udeg": [0, 0, 0]}})
    assert r.status_code in (200, 201), r.text

    # subject adoptions + PI tracks + features + transitions (bulk)
    pi_ids = [row["oid"] for row in work_rows[:n_pi_subjects]]
    ce_entities = []
    for i in range(n_ce_subjects):
        eid = await make_entity(client, pid, name=f"CE {i}")
        r = await client.post(f"/entities/{eid}/revisions",
                              json={"spec": {"description": f"ce{i}"}})
        r2 = await client.put(
            f"/entities/{eid}/approved-revision",
            json={"revision_id": r.json()["id"],
                  "expected_approved_revision_id": None})
        assert r2.status_code == 200, r2.text
        ce_entities.append(eid)
    # §14.3: every CE subject is an explicit shot semantic dependency
    async with engine.connect() as conn:
        for i, eid in enumerate(ce_entities):
            await conn.execute(text(
                "INSERT INTO shot_entity_dependencies (shot_id, entity_id,"
                " role, position) VALUES (:s, :e, 'cast', :i)"),
                {"s": shot, "e": eid, "i": i + 1})
        await conn.commit()
    async with engine.connect() as conn:
        await conn.execute(text(
            "INSERT INTO composition_occurrence_authority_subjects "
            "(composition_id, occurrence_id, subject_kind, "
            "creative_entity_id, created_at) VALUES "
            "(:c, :o, 'production_instance', NULL, :n)"),
            [{"c": cid, "o": oid, "n": NOW} for oid in pi_ids])
        await conn.execute(text(
            "INSERT INTO composition_occurrence_authority_subjects "
            "(composition_id, occurrence_id, subject_kind, "
            "creative_entity_id, created_at) VALUES "
            "(:c, :o, 'creative_entity', :e, :n)"),
            [{"c": cid, "o": work_rows[n_pi_subjects + i]["oid"],
              "e": ce_entities[i], "n": NOW}
             for i in range(n_ce_subjects)])
        track_rows = [{"id": new_uuid(), "w": world["id"], "c": cid,
                       "o": oid, "n": NOW} for oid in pi_ids]
        await conn.execute(text(
            "INSERT INTO production_instance_spatial_tracks (id, "
            "spatial_world_id, composition_id, occurrence_id, "
            "requirement, created_at, updated_at) VALUES "
            "(:id, :w, :c, :o, 'optional', :n, :n)"), track_rows)
        feature_rows = [
            {"id": new_uuid(), "c": cid,
             "o": pi_ids[i % len(pi_ids)], "n": NOW}
            for i in range(n_features)]
        await conn.execute(text(
            "INSERT INTO production_instance_features (id, composition_id,"
            " occurrence_id, key, kind, value_type, name, created_at, "
            "updated_at) VALUES (:id, :c, :o, :k, 'status', 'text', "
            "'Feature', :n, :n)"),
            [{**r, "k": f"feature_{i}"} for i, r in
             enumerate(feature_rows)])
        await conn.execute(text(
            "INSERT INTO production_instance_feature_transitions (id, "
            "feature_id, anchor_type, anchor_id, boundary, operation, "
            "value_json, value_hash, created_at, updated_at) VALUES "
            "(:id, :f, 'sequence', :q, :b, 'set', :vj, :vh, :n, :n)"),
            [{"id": new_uuid(),
              "f": feature_rows[i % len(feature_rows)]["id"],
              "q": seqs[(i // len(feature_rows)) % len(seqs)],
              "b": "start" if (i // len(feature_rows) // len(seqs)) % 2
              == 0 else "end",
              "vj": '"set"', "vh": hashlib.sha256(
                  b'"set"').hexdigest(), "n": NOW}
             for i in range(n_feature_transitions)])
        await conn.execute(text(
            "INSERT INTO production_instance_spatial_transitions (id, "
            "spatial_track_id, anchor_type, anchor_id, boundary, "
            "operation, x_mm, y_mm, z_mm, yaw_udeg, pitch_udeg, roll_udeg,"
            " created_at, updated_at) VALUES (:id, :t, 'sequence', :q, "
            ":b, 'set', 10, 0, 0, 0, 0, 0, :n, :n)"),
            [{"id": new_uuid(),
              "t": track_rows[i % len(track_rows)]["id"],
              "q": seqs[(i // len(track_rows)) % len(seqs)],
              "b": "start" if (i // len(track_rows) // len(seqs)) % 2
              == 0 else "end",
              "n": NOW} for i in range(n_spatial_transitions)])
        await conn.commit()

    # the M10 plan so the current resolver composes
    from soloring.spatial.plans import put_spatial_plan

    plan = {"schema_version": 1, "spatial_world_id": world["id"],
            "camera": json.loads(json.dumps(CAM)), "blocking": [],
            "axis_constraint": None}
    async with f() as s:
        await put_spatial_plan(s, shot, expected_plan_hash=None,
                               plan_raw=plan)
    return {"pid": pid, "cid": cid, "C": c_id, "W": rev["id"],
            "shot": shot, "world": world,
            "n_subjects": n_pi_subjects + n_ce_subjects,
            "n_entries": n_pi_subjects}


class _QueryCounter:
    def __init__(self, engine):
        self.engine = engine
        self.count = 0

    def __enter__(self):
        @event.listens_for(self.engine.sync_engine,
                           "before_cursor_execute")
        def _count(conn, cursor, statement, parameters, context,
                   executemany):
            self.count += 1

        self._listener = _count
        return self

    def __exit__(self, *exc):
        event.remove(self.engine.sync_engine, "before_cursor_execute",
                     self._listener)


async def _measure(client, fixture) -> dict:
    """Query-class counts for the §26.1 operations."""
    engine = client._transport.app.state.engine
    counts = {}
    with _QueryCounter(engine) as c:
        r = await client.post(
            f"/composition-revisions/{fixture['C']}"
            "/spatial-binding-readiness",
            json={"spatial_world_revision_id": fixture["W"]})
        assert r.status_code == 200, r.text
        counts["readiness"] = c.count
    r = await client.post(
        f"/composition-revisions/{fixture['C']}/spatial-bindings",
        json={"spatial_world_revision_id": fixture["W"]})
    assert r.status_code == 201, r.text
    binding_id = r.json()["binding_id"]
    with _QueryCounter(engine) as c:
        r = await client.post(
            f"/composition-revisions/{fixture['C']}/spatial-bindings",
            json={"spatial_world_revision_id": fixture["W"]})
        assert r.status_code == 200  # converged (in-fence rederive)
        counts["publish_converged"] = c.count
    r = await client.put(
        f"/shots/{fixture['shot']}/production-world-selection",
        json={"binding_id": binding_id, "expected_binding_id": None})
    assert r.status_code == 200, r.text
    with _QueryCounter(engine) as c:
        r = await client.get(
            f"/shots/{fixture['shot']}/production-world")
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["ready"] is True, out["issues"]
        counts["resolver"] = c.count
    counts["binding_bytes"] = len(json.dumps(
        out["production_world"]["binding"]["value"]))
    counts["subject_count"] = len(
        out["production_world"]["binding"]["value"]["subjects"])
    counts["entry_count"] = len(
        out["production_world"]["binding"]["value"]["entries"])
    return counts


async def test_m13_scale_01(client):
    """M13-SCALE:01 — binding readiness + fenced publication query counts
    are independent of occurrence cardinality (small == representative)."""
    small = await _seed_at_scale(
        client, n_occurrences=50, n_pi_subjects=10, n_ce_subjects=5,
        n_features=5, n_feature_transitions=20, n_spatial_transitions=20,
        tag=b"m13-scale-small")
    rep = await _seed_at_scale(
        client, n_occurrences=2000, n_pi_subjects=200, n_ce_subjects=200,
        n_features=200, n_feature_transitions=1000,
        n_spatial_transitions=1000, tag=b"m13-scale-rep")
    small_counts = await _measure(client, small)
    rep_counts = await _measure(client, rep)
    assert small_counts["readiness"] == rep_counts["readiness"], (
        small_counts, rep_counts)
    assert small_counts["publish_converged"] == (
        rep_counts["publish_converged"])
    assert rep_counts["subject_count"] == 400
    assert rep_counts["entry_count"] == 200


async def test_m13_scale_02(client):
    """M13-SCALE:02 — the current Shot resolver (incl. in-read candidate
    staleness re-derivation) query count is cardinality-independent."""
    small = await _seed_at_scale(
        client, n_occurrences=50, n_pi_subjects=10, n_ce_subjects=5,
        n_features=5, n_feature_transitions=20, n_spatial_transitions=20,
        tag=b"m13-scale-small2")
    rep = await _seed_at_scale(
        client, n_occurrences=2000, n_pi_subjects=200, n_ce_subjects=200,
        n_features=200, n_feature_transitions=1000,
        n_spatial_transitions=1000, tag=b"m13-scale-rep2")
    small_counts = await _measure(client, small)
    rep_counts = await _measure(client, rep)
    assert small_counts["resolver"] == rep_counts["resolver"], (
        small_counts, rep_counts)


async def test_m13_scale_03(client):
    """M13-SCALE:03 — schema-6 rows/bytes and the full-binding duplication
    are recorded honestly; no latency threshold is claimed."""
    rep = await _seed_at_scale(
        client, n_occurrences=2000, n_pi_subjects=200, n_ce_subjects=200,
        n_features=200, n_feature_transitions=1000,
        n_spatial_transitions=1000, tag=b"m13-scale-rows")
    counts = await _measure(client, rep)
    engine = client._transport.app.state.engine
    r = await client.get(f"/shots/{rep['shot']}/production-world")
    pack = r.json()["production_world"]
    pack_bytes = len(json.dumps(pack))
    async with engine.connect() as conn:
        child_rows = (await conn.execute(text(
            "SELECT COUNT(*) FROM "
            "shot_revision_production_instance_spatial_states"
        ))).scalar_one()
    print(
        f"\nM13-SCALE record: binding_bytes={counts['binding_bytes']} "
        f"pack_bytes={pack_bytes} subjects={counts['subject_count']} "
        f"entries={counts['entry_count']} "
        f"captured_spatial_rows={child_rows}")
    assert pack_bytes > counts["binding_bytes"]  # duplication recorded
