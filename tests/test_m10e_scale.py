"""M10E scale (frozen R3 §23) — APR-044 boundedness: the materializer is
invoked exactly once per emitted control stream, and normalized SQL
statement classes stay stable as captured authority cardinality grows
(E-085..E-087)."""
from __future__ import annotations

import re
from collections import Counter

import pytest
from sqlalchemy import event, text

from tests.test_m10e_generation import (
    _EXTENTS,
    _create,
    _schema3_package,
    _siblings,
    _spatial_seed,
    _spatial_settings,
)

_UUID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_HEX64 = re.compile(r"\b[0-9a-f]{64}\b")
_NUM = re.compile(r"\b\d+\b")


def _normalize(statement: str) -> str:
    s = _UUID.sub("<uuid>", statement)
    s = _HEX64.sub("<hash>", s)
    s = _NUM.sub("<n>", s)
    return " ".join(s.split())


async def _seed_with_frames(factory, *, extra_frames, staged=1):
    """A schema-5 seed whose captured world cardinality grows with
    ``extra_frames`` (more fixed frames on the approved world revision)."""
    import uuid

    from tests.test_m10d_resolver import CAM, _entities, _first_sequence, \
        _shot
    from soloring.spatial import plans as plan_svc
    from soloring.spatial import tracks as track_svc
    from soloring.spatial import transitions as trans_svc
    from soloring.spatial import revisions as wrev_svc
    from soloring.spatial import worlds as world_svc

    pid = str(uuid.uuid4())
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO projects (id, name, created_at, updated_at) "
                "VALUES (:p, 'P', 't', 't')"), {"p": pid})
    ents = await _entities(
        factory, pid, {"loc": "location", "c0": "character"})
    loc, locrev = ents["loc"]
    world = await world_svc.create_world(
        factory(), pid, key="lobby", name="lobby", description=None,
        requirement="required", location_entity_id=loc)
    state = await world_svc.create_state(
        factory(), world["id"], location_entity_revision_id=locrev)
    for i in range(extra_frames):
        f = await world_svc.create_frame(
            factory(), world["id"], key=f"f{i}", name=f"f{i}",
            parent_spatial_frame_id=None, bound_entity_id=None)
        await world_svc.put_state_frame(
            factory(), state["id"], f["id"],
            translation_mm=[-3000 + 40 * i, 1650, -100 * i],
            rotation_udeg=[0, 0, 0],
            half_extents_mm=([120, 90, 60] if i % 2 == 0 else None),
            bound_entity_revision_id=None)
    rev = await wrev_svc.capture_revision(factory(), state["id"])
    await wrev_svc.approve_revision(
        factory(), state["id"], revision_id=rev["id"],
        expected_approved_revision_id=None)
    ent, _ = ents["c0"]
    shot = await _shot(factory, pid, [loc, ent], assigned=True)
    track = await track_svc.create_track(
        factory(), world["id"], entity_id=ent, requirement="optional")
    await trans_svc.create_transition(
        factory(), track["id"], anchor_type="sequence",
        anchor_id=await _first_sequence(factory, pid),
        boundary="start", operation="set",
        translation_mm=[-3600, 1500, -400], rotation_udeg=[0, 0, 0])
    await plan_svc.put_spatial_plan(
        factory(), shot, expected_plan_hash=None, plan_raw={
            "schema_version": 1,
            "spatial_world_id": world["id"],
            "camera": CAM,
            "blocking": [{
                "spatial_track_id": track["id"],
                "screen_direction": "left_to_right",
                "keyframes": [{
                    "time_ms": 0,
                    "transform": {"translation_mm": [-3600, 1500, -400],
                                  "rotation_udeg": [0, 0, 0]}}],
            }],
            "axis_constraint": None,
        })
    return {"pid": pid, "shot": shot}


async def test_materializer_called_once_per_stream(factory, engine,
                                                   settings, tmp_path,
                                                   monkeypatch):
    """E-087: the production D0 materializer is invoked exactly once per
    emitted control stream — never per frame, frame primitive, Track
    property, or upstream authority row."""
    from soloring.spatial import boxdepth

    pkg = await _schema3_package(tmp_path)
    seed = await _spatial_seed(factory, staged=2, extents=_EXTENTS)
    calls = {"n": 0}
    real = boxdepth.materialize

    def _counting(pack):
        calls["n"] += 1
        return real(pack)

    monkeypatch.setattr(boxdepth, "materialize", _counting)
    gen = await _create(factory, _spatial_settings(settings, pkg), seed)
    rows = await _siblings(engine, gen.id)
    assert len(rows) == 3  # 1 world + 2 entity streams
    assert calls["n"] == 3


async def test_sql_statement_shape_stable_under_cardinality(
        factory, engine, settings, tmp_path):
    """E-085/E-086: matched small vs representative fixtures (captured
    world frame cardinality 2→24, identical execution-table classes) keep
    a stable normalized SQL statement-class multiset through the creation
    path; no per-frame/per-Track DB replay."""
    pkg = await _schema3_package(tmp_path)
    s = _spatial_settings(settings, pkg)

    async def _profiled(frames: int):
        seed = await _seed_with_frames(factory, extra_frames=frames)
        statements: list[str] = []

        def _spy(conn, cursor, statement, parameters, context,
                 executemany=False):
            statements.append(_normalize(statement))

        eng = engine.sync_engine
        event.listen(eng, "before_cursor_execute", _spy)
        try:
            gen = await _create(factory, s, seed)
            assert gen.status == "queued"
        finally:
            event.remove(eng, "before_cursor_execute", _spy)
        return Counter(statements)

    small = await _profiled(2)
    big = await _profiled(24)
    assert small == big, (
        "normalized SQL statement classes drifted with captured "
        "authority cardinality")
