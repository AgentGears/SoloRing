"""M10C-6 tests — byte determinism and the feature-film-scale endpoint
gate (M10C plan §§13-14; matrix 46, 67-70).

Determinism: the same semantic staging state (IDENTICAL identity ids)
inserted into two fresh databases in OPPOSITE insertion orders — the
only difference observable to the resolver is database return order —
must yield EXACT byte-identical canonical staging serialization, with
identical provenance, EntityRevisions, and canonical state order.

Scale: the public staging-preview path (Shot verification, semantic
dependency + exact EntityRevision resolution, applicable Track load,
Transition load, canonical narrative ordering, projection) must issue
the SAME SQL statement classes/count for a small fixture and a
~2,500-Shot representative fixture. Rows may scale; round trips may
not (APR-044).
"""
import asyncio
import time
import uuid

import pytest
from sqlalchemy import text

from soloring.db import models  # noqa: F401  (register tables)
from soloring.db.base import Base
from soloring.db.engine import create_soloring_engine
from soloring.settings import Settings
from soloring.spatial import staging

NS = uuid.uuid5(uuid.NAMESPACE_DNS, "m10c-scale-fixture")


def det(name: str) -> str:
    return str(uuid.uuid5(NS, name))


def _fixture_ids():
    return {
        "project": det("project"), "loc": det("loc"),
        "locrev": det("locrev"), "eva": det("eva"),
        "eva_rev": det("eva-rev"), "car": det("car"),
        "car_rev": det("car-rev"), "seq": det("seq"),
        "seq2": det("seq2"), "scene": det("scene"),
        "world": det("world"), "track_eva": det("track-eva"),
        "track_car": det("track-car"),
        "shots": [det(f"shot-{i}") for i in range(4)],
        "trans_eva_scene_start": det("tr-eva-scene-start"),
        "trans_eva_shot0_end": det("tr-eva-shot0-end"),
        "trans_eva_shot1_start": det("tr-eva-shot1-start"),
        "trans_eva_shot2_clear": det("tr-eva-shot2-clear"),
        "trans_eva_shot2_set": det("tr-eva-shot2-set"),
        "trans_car_scene_start": det("tr-car-scene-start"),
    }


def _rows(i):
    """All raw rows for the deterministic fixture (identity-stable)."""
    return [
        ("projects",
         "INSERT INTO projects (id, name, created_at, updated_at) "
         "VALUES (:id, 'P', 't', 't')", {"id": i["project"]}),
        ("creative_entities",
         "INSERT INTO creative_entities (id, project_id, kind, name, "
         "created_at, updated_at) VALUES (:id, :p, 'location', 'L', "
         "'t', 't')", {"id": i["loc"], "p": i["project"]}),
        ("creative_entities",
         "INSERT INTO creative_entities (id, project_id, kind, name, "
         "created_at, updated_at) VALUES (:id, :p, 'character', 'Eva', "
         "'t', 't')", {"id": i["eva"], "p": i["project"]}),
        ("creative_entities",
         "INSERT INTO creative_entities (id, project_id, kind, name, "
         "created_at, updated_at) VALUES (:id, :p, 'prop', 'Car', "
         "'t', 't')", {"id": i["car"], "p": i["project"]}),
        ("entity_revisions",
         "INSERT INTO entity_revisions (id, entity_id, revision_number, "
         "schema_version, spec_hash, created_at) VALUES (:id, :e, 1, 1, "
         ":h, 't')", {"id": i["locrev"], "e": i["loc"], "h": "0a" * 32}),
        ("entity_revisions",
         "INSERT INTO entity_revisions (id, entity_id, revision_number, "
         "schema_version, spec_hash, created_at) VALUES (:id, :e, 1, 1, "
         ":h, 't')", {"id": i["eva_rev"], "e": i["eva"], "h": "0b" * 32}),
        ("entity_revisions",
         "INSERT INTO entity_revisions (id, entity_id, revision_number, "
         "schema_version, spec_hash, created_at) VALUES (:id, :e, 1, 1, "
         ":h, 't')", {"id": i["car_rev"], "e": i["car"], "h": "0c" * 32}),
        ("approvals",
         "INSERT INTO entity_approved_revisions (entity_id, revision_id, "
         "approved_at) VALUES (:e, :r, 't')",
         {"e": i["eva"], "r": i["eva_rev"]}),
        ("approvals",
         "INSERT INTO entity_approved_revisions (entity_id, revision_id, "
         "approved_at) VALUES (:e, :r, 't')",
         {"e": i["car"], "r": i["car_rev"]}),
        ("sequences",
         "INSERT INTO sequences (id, project_id, position, title) VALUES "
         "(:id, :p, 0, 'S')", {"id": i["seq"], "p": i["project"]}),
        ("scenes",
         "INSERT INTO scenes (id, sequence_id, position, title) VALUES "
         "(:id, :s, 0, 'C')", {"id": i["scene"], "s": i["seq"]}),
        ("shots",
         "INSERT INTO shots (id, project_id, shot_number, subject, "
         "scene_id, scene_position) VALUES (:id, :p, :n, 'shot', :c, "
         ":pos)",
         {"id": i["shots"][0], "p": i["project"], "n": 1,
          "c": i["scene"], "pos": 0}),
        ("shots",
         "INSERT INTO shots (id, project_id, shot_number, subject, "
         "scene_id, scene_position) VALUES (:id, :p, :n, 'shot', :c, "
         ":pos)",
         {"id": i["shots"][1], "p": i["project"], "n": 2,
          "c": i["scene"], "pos": 1}),
        ("shots",
         "INSERT INTO shots (id, project_id, shot_number, subject, "
         "scene_id, scene_position) VALUES (:id, :p, :n, 'shot', :c, "
         ":pos)",
         {"id": i["shots"][2], "p": i["project"], "n": 3,
          "c": i["scene"], "pos": 2}),
        ("shots",
         "INSERT INTO shots (id, project_id, shot_number, subject, "
         "scene_id, scene_position) VALUES (:id, :p, :n, 'shot', :c, "
         ":pos)",
         {"id": i["shots"][3], "p": i["project"], "n": 4,
          "c": i["scene"], "pos": 3}),
        ("deps",
         "INSERT INTO shot_entity_dependencies (shot_id, entity_id, "
         "role, position) VALUES (:s, :e, 'cast', 0)",
         {"s": i["shots"][3], "e": i["eva"]}),
        ("deps",
         "INSERT INTO shot_entity_dependencies (shot_id, entity_id, "
         "role, position) VALUES (:s, :e, 'prop', 1)",
         {"s": i["shots"][3], "e": i["car"]}),
        ("worlds",
         "INSERT INTO spatial_worlds (id, project_id, "
         "location_entity_id, key, name, description, requirement, "
         "created_at, updated_at) VALUES (:id, :p, :l, 'lobby', 'Lobby', "
         "NULL, 'optional', 't', 't')",
         {"id": i["world"], "p": i["project"], "l": i["loc"]}),
        ("tracks",
         "INSERT INTO spatial_tracks (id, spatial_world_id, entity_id, "
         "requirement, created_at, updated_at) VALUES (:id, :w, :e, "
         "'optional', 't', 't')",
         {"id": i["track_eva"], "w": i["world"], "e": i["eva"]}),
        ("tracks",
         "INSERT INTO spatial_tracks (id, spatial_world_id, entity_id, "
         "requirement, created_at, updated_at) VALUES (:id, :w, :e, "
         "'required', 't', 't')",
         {"id": i["track_car"], "w": i["world"], "e": i["car"]}),
        ("transitions",
         "INSERT INTO spatial_transitions (id, spatial_track_id, "
         "anchor_type, anchor_id, boundary, operation, x_mm, y_mm, z_mm, "
         "yaw_udeg, pitch_udeg, roll_udeg, created_at, updated_at) "
         "VALUES (:id, :t, :at, :a, :b, :op, :x, :y, :z, :yaw, :pitch, "
         ":roll, 't', 't')",
         {"id": i["trans_eva_scene_start"], "t": i["track_eva"],
          "at": "scene", "a": i["scene"], "b": "start", "op": "set",
          "x": 100, "y": 0, "z": -1000, "yaw": 0, "pitch": 0,
          "roll": 0}),
        ("transitions",
         "INSERT INTO spatial_transitions (id, spatial_track_id, "
         "anchor_type, anchor_id, boundary, operation, x_mm, y_mm, z_mm, "
         "yaw_udeg, pitch_udeg, roll_udeg, created_at, updated_at) "
         "VALUES (:id, :t, :at, :a, :b, :op, :x, :y, :z, :yaw, :pitch, "
         ":roll, 't', 't')",
         {"id": i["trans_eva_shot1_start"], "t": i["track_eva"],
          "at": "shot", "a": i["shots"][1], "b": "start", "op": "set",
          "x": 200, "y": 0, "z": -2000, "yaw": 1000000, "pitch": 0,
          "roll": 0}),
        ("transitions",
         "INSERT INTO spatial_transitions (id, spatial_track_id, "
         "anchor_type, anchor_id, boundary, operation, x_mm, y_mm, z_mm, "
         "yaw_udeg, pitch_udeg, roll_udeg, created_at, updated_at) "
         "VALUES (:id, :t, :at, :a, :b, :op, :x, :y, :z, :yaw, :pitch, "
         ":roll, 't', 't')",
         {"id": i["trans_eva_shot2_clear"], "t": i["track_eva"],
          "at": "shot", "a": i["shots"][2], "b": "start", "op": "clear",
          "x": None, "y": None, "z": None, "yaw": None, "pitch": None,
          "roll": None}),
        ("transitions",
         "INSERT INTO spatial_transitions (id, spatial_track_id, "
         "anchor_type, anchor_id, boundary, operation, x_mm, y_mm, z_mm, "
         "yaw_udeg, pitch_udeg, roll_udeg, created_at, updated_at) "
         "VALUES (:id, :t, :at, :a, :b, :op, :x, :y, :z, :yaw, :pitch, "
         ":roll, 't', 't')",
         {"id": i["trans_eva_shot2_set"], "t": i["track_eva"],
          "at": "shot", "a": i["shots"][2], "b": "end", "op": "set",
          "x": 300, "y": 0, "z": -3000, "yaw": 0, "pitch": 0,
          "roll": 0}),
        ("transitions",
         "INSERT INTO spatial_transitions (id, spatial_track_id, "
         "anchor_type, anchor_id, boundary, operation, x_mm, y_mm, z_mm, "
         "yaw_udeg, pitch_udeg, roll_udeg, created_at, updated_at) "
         "VALUES (:id, :t, :at, :a, :b, :op, :x, :y, :z, :yaw, :pitch, "
         ":roll, 't', 't')",
         {"id": i["trans_car_scene_start"], "t": i["track_car"],
          "at": "sequence", "a": i["seq"], "b": "start", "op": "set",
          "x": -900, "y": 500, "z": 0, "yaw": 0, "pitch": 0,
          "roll": 0}),
    ]


async def _build_db(tmp_path, name, *, reverse):
    """Seeds identical identity ids; when ``reverse``, the TRACK and
    TRANSITION rows are inserted in opposite order (FK-safe: only the
    two collections whose database return order the resolver observes
    are shuffled)."""
    ids = _fixture_ids()
    eng = create_soloring_engine(Settings(data_dir=tmp_path / name))
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        rows = _rows(ids)
        base = [r for r in rows if r[0] not in ("tracks",
                                                "transitions")]
        tracks = [r for r in rows if r[0] == "tracks"]
        transitions = [r for r in rows if r[0] == "transitions"]
        if reverse:
            tracks = list(reversed(tracks))
            transitions = list(reversed(transitions))
        for _kind, sql, params in base + tracks + transitions:
            await conn.execute(text(sql), params)
    return eng, ids


class _Composer:
    """Drives the REAL public preview path on one engine."""

    def __init__(self, engine):
        self.engine = engine

    async def preview(self, ids, shot):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        factory = async_sessionmaker(bind=self.engine,
                                     expire_on_commit=False,
                                     class_=AsyncSession)
        async with factory() as session:
            return await staging.preview_staging(
                session, spatial_world_id=ids["world"], shot_id=shot)


class _Spy:
    def __init__(self, engine):
        self.engine = engine
        self.statements: list[str] = []
        self._fn = None

    def __enter__(self):
        from sqlalchemy import event

        def _spy(conn, cursor, statement, parameters, context,
                 executemany):
            self.statements.append(statement)
        self._fn = _spy
        event.listen(self.engine.sync_engine, "before_cursor_execute",
                     _spy)
        return self

    def __exit__(self, *exc):
        from sqlalchemy import event
        event.remove(self.engine.sync_engine, "before_cursor_execute",
                     self._fn)


def _classify(statement: str) -> str:
    s = statement.strip()
    for table in ("shot_entity_dependencies", "entity_approved_revisions",
                  "creative_entities", "spatial_transitions",
                  "spatial_tracks", "spatial_worlds", "sequences",
                  "scenes", "shots", "entity_revisions"):
        if table in s:
            return f"select/{table}" if s.upper().startswith(
                "SELECT") else f"other/{table}"
    return "other"


async def test_byte_identical_staging_bytes_under_shuffled_db_return_order(
        tmp_path):
    """Determinism gate (matrix 46): identical identity ids, opposite
    insertion orders in two databases — the canonical staging BYTES are
    exactly equal, with identical provenance and order."""
    eng_a, ids_a = await _build_db(tmp_path, "a", reverse=False)
    eng_b, ids_b = await _build_db(tmp_path, "b", reverse=True)
    try:
        target = ids_a["shots"][3]  # after clear+re-set boundary
        body_a = await _Composer(eng_a).preview(ids_a, target)
        body_b = await _Composer(eng_b).preview(ids_b, target)

        # states identical incl. exact ids, provenance, and order
        assert body_a["states"] == body_b["states"]
        assert len(body_a["states"]) == 2  # eva + car both set
        order = [(s["entity_id"], s["spatial_track_id"])
                 for s in body_a["states"]]
        assert order == sorted(order)
        eva_state = next(s for s in body_a["states"]
                         if s["entity_id"] == ids_a["eva"])
        assert eva_state["source_boundary"] == "end"  # re-set won
        assert eva_state["source_transition_id"] == \
            ids_a["trans_eva_shot2_set"]

        # and the canonical BYTES from the resolver are exactly equal
        async def _resolve_bytes(eng, ids):
            from soloring.continuity.snapshots import \
                resolve_working_dependencies
            async with eng.connect() as conn:
                deps = await resolve_working_dependencies(
                    conn, ids["shots"][3])
                revisions = {d.entity_id: d.entity_revision_id
                             for d in deps}
                outcome = await staging.resolve_effective_staging(
                    conn, shot_id=ids["shots"][3],
                    spatial_world_id=ids["world"],
                    resolved_entity_revisions=revisions)
                return staging.canonical_staging_bytes(outcome.states)

        bytes_a = await _resolve_bytes(eng_a, ids_a)
        bytes_b = await _resolve_bytes(eng_b, ids_b)
        assert bytes_a == bytes_b  # exact byte identity
        assert len(bytes_a) > 0
    finally:
        await eng_a.dispose()
        await eng_b.dispose()


# ------------------------------------------------------------- scale gate

async def _build_scale_db(tmp_path, *, n_shots):
    """One world reused across all Shots; recurring entities; required +
    optional tracks; sequence/scene/shot transitions incl. clear and
    re-entry; unrelated noise world/tracks/transitions."""
    ids = _fixture_ids()
    eng = create_soloring_engine(Settings(data_dir=tmp_path /
                                          f"scale-{n_shots}"))
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for _kind, sql, params in _rows(ids):
            await conn.execute(text(sql), params)
        # bulk narrative + dependencies to feature scale
        n_scenes = max(1, n_shots // 50)
        scene_rows = [
            {"id": det(f"noise-scene-{k}"), "s": ids["seq2"],
             "pos": k}
            for k in range(n_scenes)]
        await conn.execute(text(
            "INSERT INTO sequences (id, project_id, position, title) "
            "VALUES (:id, :p, 1, 'Bulk')"),
            {"id": ids["seq2"], "p": ids["project"]})
        await conn.execute(text(
            "INSERT INTO scenes (id, sequence_id, position, title) "
            "VALUES (:id, :s, :pos, 'Bulk')"), scene_rows)
        shot_rows, dep_rows = [], []
        for k in range(n_shots):
            shot_rows.append({
                "id": det(f"bulk-shot-{k}"), "p": ids["project"],
                "n": 100 + k, "c": det(f"noise-scene-{k % n_scenes}"),
                "pos": k // n_scenes})
            dep_rows.append({
                "s": det(f"bulk-shot-{k}"), "e": ids["eva"]})
        await conn.execute(text(
            "INSERT INTO shots (id, project_id, shot_number, subject, "
            "scene_id, scene_position) VALUES (:id, :p, :n, 'bulk', :c, "
            ":pos)"), shot_rows)
        await conn.execute(text(
            "INSERT INTO shot_entity_dependencies (shot_id, entity_id, "
            "role, position) VALUES (:s, :e, 'cast', 0)"), dep_rows)
        # recurring transitions across the bulk topology (every 100th
        # shot gets a set; every 150th a clear; every 200th a re-set)
        bulk_target = det("bulk-shot-target")
        await conn.execute(text(
            "INSERT INTO shots (id, project_id, shot_number, subject, "
            "scene_id, scene_position) VALUES (:id, :p, :n, 'target', "
            ":c, :pos)"),
            {"id": bulk_target, "p": ids["project"], "n": 99999,
             "c": det("noise-scene-0"), "pos": 99999})
        await conn.execute(text(
            "INSERT INTO shot_entity_dependencies (shot_id, entity_id, "
            "role, position) VALUES (:s, :e, 'cast', 0)"),
            {"s": bulk_target, "e": ids["eva"]})
        await conn.execute(text(
            "INSERT INTO shot_entity_dependencies (shot_id, entity_id, "
            "role, position) VALUES (:s, :e, 'prop', 1)"),
            {"s": bulk_target, "e": ids["car"]})
        t_rows = []
        for k in range(0, n_shots, 100):
            t_rows.append({
                "id": det(f"bulk-tr-set-{k}"), "t": ids["track_eva"],
                "at": "shot", "a": det(f"bulk-shot-{k}"), "b": "start",
                "op": "set", "x": k % 1000, "y": 0, "z": -1000,
                "yaw": 0, "pitch": 0, "roll": 0})
        for k in range(75, n_shots, 150):
            t_rows.append({
                "id": det(f"bulk-tr-clear-{k}"), "t": ids["track_eva"],
                "at": "shot", "a": det(f"bulk-shot-{k}"), "b": "start",
                "op": "clear", "x": None, "y": None, "z": None,
                "yaw": None, "pitch": None, "roll": None})
        for k in range(200, n_shots, 200):
            t_rows.append({
                "id": det(f"bulk-tr-reset-{k}"), "t": ids["track_eva"],
                "at": "shot", "a": det(f"bulk-shot-{k}"), "b": "end",
                "op": "set", "x": 7, "y": 8, "z": 9, "yaw": 0,
                "pitch": 0, "roll": 0})
        if t_rows:
            await conn.execute(text(
                "INSERT INTO spatial_transitions (id, spatial_track_id, "
                "anchor_type, anchor_id, boundary, operation, x_mm, "
                "y_mm, z_mm, yaw_udeg, pitch_udeg, roll_udeg, "
                "created_at, updated_at) VALUES (:id, :t, :at, :a, :b, "
                ":op, :x, :y, :z, :yaw, :pitch, :roll, 't', 't')"),
                t_rows)
        # unrelated noise: other world (own Location), its own
        # tracks/transitions
        noise_world = det("noise-world")
        noise_loc = det("noise-loc")
        await conn.execute(text(
            "INSERT INTO creative_entities (id, project_id, kind, name, "
            "created_at, updated_at) VALUES (:id, :p, 'location', 'NL', "
            "'t', 't')"), {"id": noise_loc, "p": ids["project"]})
        await conn.execute(text(
            "INSERT INTO spatial_worlds (id, project_id, "
            "location_entity_id, key, name, description, requirement, "
            "created_at, updated_at) VALUES (:id, :p, :l, 'noise', 'N', "
            "NULL, 'optional', 't', 't')"),
            {"id": noise_world, "p": ids["project"], "l": noise_loc})
        noise_ent = det("noise-ent")
        await conn.execute(text(
            "INSERT INTO creative_entities (id, project_id, kind, name, "
            "created_at, updated_at) VALUES (:id, :p, 'vehicle', 'V', "
            "'t', 't')"), {"id": noise_ent, "p": ids["project"]})
        noise_track = det("noise-track")
        await conn.execute(text(
            "INSERT INTO spatial_tracks (id, spatial_world_id, "
            "entity_id, requirement, created_at, updated_at) VALUES "
            "(:id, :w, :e, 'optional', 't', 't')"),
            {"id": noise_track, "w": noise_world, "e": noise_ent})
        noise_rows = [{
            "id": det(f"noise-tr-{k}"), "t": noise_track, "at": "shot",
            "a": det(f"bulk-shot-{k}"), "b": "start", "op": "set",
            "x": 1, "y": 2, "z": 3, "yaw": 0, "pitch": 0, "roll": 0}
            for k in range(0, n_shots, 10)]
        await conn.execute(text(
            "INSERT INTO spatial_transitions (id, spatial_track_id, "
            "anchor_type, anchor_id, boundary, operation, x_mm, y_mm, "
            "z_mm, yaw_udeg, pitch_udeg, roll_udeg, created_at, "
            "updated_at) VALUES (:id, :t, :at, :a, :b, :op, :x, :y, :z, "
            ":yaw, :pitch, :roll, 't', 't')"), noise_rows)
        ids["bulk_target"] = bulk_target
    return eng, ids


async def _measure(tmp_path, *, n_shots):
    eng, ids = await _build_scale_db(tmp_path, n_shots=n_shots)
    try:
        composer = _Composer(eng)
        with _Spy(eng) as spy:
            t0 = time.perf_counter()
            body = await composer.preview(ids, ids["bulk_target"])
            wall = time.perf_counter() - t0
        classes = [_classify(s) for s in spy.statements]
        return {
            "n_shots": n_shots,
            "statement_count": len(spy.statements),
            "statement_classes": classes,
            "states": len(body["states"]),
            "absent": len(body["absent"]),
            "wall_seconds": wall,
        }
    finally:
        await eng.dispose()


async def test_endpoint_query_shape_identical_small_vs_2500_shots(
        tmp_path):
    """Scale gate (matrix 67-70): the COMPLETE public staging-preview
    path issues the same SQL statement classes/count at ~2,500 Shots as
    at small scale; rows scale, round trips do not."""
    small = await _measure(tmp_path, n_shots=40)
    big = await _measure(tmp_path, n_shots=2500)

    assert big["n_shots"] >= 2500
    # same statement classes/count — endpoint level, narrative loader
    # included (APR-044: rows increase; round trips do not)
    assert small["statement_classes"] == big["statement_classes"]
    assert small["statement_count"] == big["statement_count"]
    assert small["statement_count"] <= 12  # fixed shape, sanity bound

    # the representative fixture really exercises the target family
    assert big["states"] >= 2  # required and optional tracks staged

    # evidence record (wall-clock is informational, not a gate)
    print(f"\nsmall: {small}")
    print(f"representative: {big}")
