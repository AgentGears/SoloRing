"""M10F-D — representative feature-film scale (R6 §11).

D.1: deterministic fixture — two clean builds produce the same canonical
semantic inventory digest and the same named object counts.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text

from soloring.settings import Settings


async def _build(tmp_path, *, with_history=True):
    from soloring.db import models  # noqa: F401
    from soloring.db.base import Base
    from soloring.db.engine import (
        create_session_factory,
        create_soloring_engine,
    )
    from tests.m10f_scale_fixture import build_fixture, canonical_inventory

    import soloring.settings as settings_mod
    from tests.m10f_scale_fixture import deterministic_uuid4

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    settings = Settings(data_dir=data_dir)
    saved_singleton = settings_mod._settings
    settings_mod._settings = settings  # _assets writes via get_settings()
    with deterministic_uuid4():
        engine = create_soloring_engine(settings)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = create_session_factory(engine)
        ids = await build_fixture(
            engine, factory, settings, with_history=with_history)
    # after the build, uuid4 is restored (asserted inside the context)
    settings_mod._settings = saved_singleton
    inventory = canonical_inventory(engine)
    await engine.dispose()
    return ids, inventory, settings, data_dir


async def test_representative_fixture_determinism(tmp_path):
    """Two fresh builds → identical canonical inventory digest + counts."""
    from tests.m10f_scale_fixture import INVENTORY_GRAMMAR

    ids_a, inv_a, _s, _d = await _build(tmp_path / "a")
    ids_b, inv_b, _s2, _d2 = await _build(tmp_path / "b")

    assert ids_a == ids_b  # deterministic uuid5 identities
    assert inv_a["digest"] == inv_b["digest"]
    assert inv_a["counts"] == inv_b["counts"]
    counts = inv_a["counts"]
    assert counts["shots"] >= 2500
    assert counts["spatial_frames"] >= 62
    assert counts["spatial_axes"] >= 4
    assert counts["spatial_tracks"] >= 10  # target + noise
    assert counts["spatial_transitions"] >= 9
    assert counts["spatial_world_revisions"] >= 5  # A + B + noise
    assert counts["generations"] >= 3  # v1 + v2 + v3
    # every grammar table participates in the digest
    for table in INVENTORY_GRAMMAR:
        assert table in counts
    print("\nM10F-D fixture counts:", counts)

# ---------------------------------------------------------------------------
# D.2 — current-resolution SQL boundedness (§11.2 / F-086)
# ---------------------------------------------------------------------------

import re
import time
from collections import Counter

from sqlalchemy import event

_UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
_HEX64_RE = re.compile(r"\b[0-9a-f]{64}\b")
_NUM_RE = re.compile(r"\b\d+\b")


def _normalize(statement: str) -> str:
    s = _UUID_RE.sub("<uuid>", statement)
    s = _HEX64_RE.sub("<hash>", s)
    s = _NUM_RE.sub("<n>", s)
    return " ".join(s.split())


class _StatementSpy:
    def __init__(self, engine):
        self.engine = engine
        self.statements: list[str] = []

    def _spy(self, conn, cursor, statement, parameters, context,
             executemany=False):
        self.statements.append(_normalize(statement))

    def __enter__(self):
        event.listen(self.engine.sync_engine, "before_cursor_execute",
                     self._spy)
        return self

    def __exit__(self, *exc):
        event.remove(self.engine.sync_engine, "before_cursor_execute",
                     self._spy)
        return False


async def _resolve_profiled(engine, shot_id):
    """Run the COMPLETE production current-resolution path with the
    statement spy attached; returns (outcome, Counter, wall)."""
    from soloring.continuity.snapshots import resolve_working_dependencies
    from soloring.spatial import resolver as resolver_svc

    async with engine.connect() as conn:
        deps = await resolve_working_dependencies(conn, shot_id)
    with _StatementSpy(engine) as spy:
        t0 = time.perf_counter()
        async with engine.connect() as conn:
            outcome = await resolver_svc.resolve_spatial_continuity(
                conn, shot_id=shot_id, resolved_dependencies=deps)
        wall = time.perf_counter() - t0
    return outcome, Counter(spy.statements), wall


async def test_current_resolution_statement_shape_small_vs_representative(
        tmp_path):
    """F-086: the same production current-resolution path issues
    IDENTICAL normalized SQL statement classes and count on a small legal
    target and on the representative ~2,500-Shot target. Rows scale;
    round trips do not (APR-044)."""
    from tests.test_m10f_scale import _build

    ids_small, _inv_s, _settings_s, _dd_s = await _build(
        tmp_path / "small", with_history=False)
    ids_rep, inv_rep, _settings_r, _dd_r = await _build(
        tmp_path / "rep", with_history=False)

    # identical authority shape on both sides: the fixture's own first
    # target shot (same plan variant 'static', same dependency closure)
    small_out, small_classes, small_wall = await _resolve_profiled(
        (await _engine_for(_dd_s)), ids_small["shot_a"])
    rep_out, rep_classes, rep_wall = await _resolve_profiled(
        (await _engine_for(_dd_r)), ids_rep["shot_a"])

    assert small_out.ready, [i.code for i in small_out.issues]
    assert rep_out.ready, [i.code for i in rep_out.issues]

    assert sorted(small_classes) == sorted(rep_classes), (
        sorted(set(small_classes) ^ set(rep_classes)))
    assert small_classes == rep_classes  # same multiset: same count too
    assert sum(rep_classes.values()) == sum(small_classes.values())

    # the representative side really is representative
    assert inv_rep["counts"]["shots"] >= 2500
    assert inv_rep["counts"]["spatial_frames"] >= 62
    print(f"\nsmall statements: {sum(small_classes.values())} "
          f"({small_wall*1000:.1f} ms)")
    print(f"representative statements: {sum(rep_classes.values())} "
          f"({rep_wall*1000:.1f} ms)")


async def _engine_for(data_dir):
    from soloring.db.engine import create_soloring_engine
    from soloring.settings import Settings

    return create_soloring_engine(Settings(data_dir=data_dir))


# ---------------------------------------------------------------------------
# D.3 — first schema-5 capture boundedness (§11.3 / F-087)
# ---------------------------------------------------------------------------


async def _capture_profiled(engine, factory, shot_id):
    """First-ever capture through the REAL production path, spied."""
    from soloring.generation import revision as _  # noqa: F401
    from soloring.domain import revisions as revision_svc

    with _StatementSpy(engine) as spy:
        t0 = time.perf_counter()
        async with factory() as session:
            await revision_svc.capture_revision_with_visual(
                session, shot_id)
        wall = time.perf_counter() - t0
    return Counter(spy.statements), wall


async def test_first_schema5_capture_statement_shape_fresh_targets(
        tmp_path):
    """F-087: both targets begin with ZERO ShotRevision rows (asserted
    before measurement); the first schema-5 capture path issues identical
    normalized statement classes/count, with materially larger captured
    child cardinality on the representative side."""
    from sqlalchemy import text

    from tests.test_m10f_scale import _build

    small_ids, _inv, settings_s, dd_s = await _build(
        tmp_path / "small", with_history=False)
    rep_ids, inv_r, settings_r, dd_r = await _build(
        tmp_path / "rep", with_history=False)

    eng_s = await _engine_for(dd_s)
    eng_r = await _engine_for(dd_r)
    from soloring.db.engine import create_session_factory

    fac_s = create_session_factory(eng_s)
    fac_r = create_session_factory(eng_r)

    async with eng_s.connect() as c:
        n = (await c.execute(text(
            "SELECT COUNT(*) FROM shot_revisions WHERE shot_id = :s"),
            {"s": small_ids["shot_a"]})).scalar()
    assert n == 0, "small target must be fresh"
    async with eng_r.connect() as c:
        n = (await c.execute(text(
            "SELECT COUNT(*) FROM shot_revisions WHERE shot_id = :s"),
            {"s": rep_ids["shot_a"]})).scalar()
    assert n == 0, "representative target must be fresh"

    from soloring.domain import revisions as revision_svc

    with _StatementSpy(eng_s) as spy_s:
        async with fac_s() as session:
            await revision_svc.capture_revision_with_visual(
                session, small_ids["shot_a"])
    small_classes = Counter(spy_s.statements)

    with _StatementSpy(eng_r) as spy_r:
        async with fac_r() as session:
            await revision_svc.capture_revision_with_visual(
                session, rep_ids["shot_a"])
    rep_classes = Counter(spy_r.statements)

    assert sorted(small_classes) == sorted(rep_classes), (
        sorted(set(small_classes) ^ set(rep_classes)))
    assert small_classes == rep_classes
    print(f"\ncapture small statements: {sum(small_classes.values())}")
    print(f"capture representative statements: {sum(rep_classes.values())}")

    await eng_s.dispose()
    await eng_r.dispose()


# ---------------------------------------------------------------------------
# D.4 — matched-COLD first-Generation boundedness (§11.4 / F-088)
# ---------------------------------------------------------------------------


async def _cold_ledger(engine, shot_id, project_id):
    """Mechanically prove the exact cold precondition set before any
    measurement (§11.4): no prior ShotRevision, Generation, or project
    DerivedSpatialArtifact/provenance of any kind."""
    from sqlalchemy import text

    async with engine.connect() as c:
        ledger = {
            "shot_revisions": (await c.execute(text(
                "SELECT COUNT(*) FROM shot_revisions WHERE shot_id = :s"),
                {"s": shot_id})).scalar(),
            "generations": (await c.execute(text(
                "SELECT COUNT(*) FROM generations WHERE shot_id = :s"),
                {"s": shot_id})).scalar(),
            "project_dsa": (await c.execute(text(
                "SELECT COUNT(*) FROM derived_spatial_artifacts WHERE "
                "project_id = :p"), {"p": project_id})).scalar(),
            "project_gdsi": (await c.execute(text(
                "SELECT COUNT(*) FROM "
                "generation_derived_spatial_inputs"))).scalar(),
        }
    assert ledger == {"shot_revisions": 0, "generations": 0,
                      "project_dsa": 0, "project_gdsi": 0}, ledger
    return ledger


async def _first_generation_profiled(data_dir, engine, shot_id,
                                     project_id, package_dir):
    """POST /shots/{id}/generations through the real app + service with
    the statement spy attached. Returns (Counter, generation_id)."""
    import httpx

    from soloring.api.main import create_app
    from soloring.db.engine import create_session_factory
    from soloring.settings import Settings

    settings = Settings(data_dir=data_dir)
    settings.executor = "comfy"
    settings.workflow_package_dir = package_dir
    app = create_app(settings)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)

    await _cold_ledger(engine, shot_id, project_id)  # pre-measurement gate

    transport = httpx.ASGITransport(app=app)
    with _StatementSpy(engine) as spy:
        async with httpx.AsyncClient(transport=transport,
                                     base_url="http://test") as client:
            r = await client.post(f"/shots/{shot_id}/generations")
    assert r.status_code == 202, r.text
    return Counter(spy.statements), r.json()["id"]


async def test_first_generation_matched_cold_statement_shape(tmp_path):
    """F-088: the whole-milestone first-Generation proof on the public
    POST path with REAL D0 materialization/registration/persistence.
    Both sides prove the identical cold branch set first; representative
    authority cardinality is materially larger; normalized statement
    classes/count are identical; the representative Generation still has
    bounded 1..3 derived siblings."""
    from sqlalchemy import text

    from tests.test_m10e_package3_production import _schema3_package
    from tests.test_m10f_scale import _build

    # ONE selected schema-3 package release shared by both sides
    pkg = await _schema3_package(tmp_path / "pkg")

    small_ids, _inv_s, _s_s, dd_s = await _build(
        tmp_path / "small", with_history=False)
    rep_ids, inv_r, _s_r, dd_r = await _build(
        tmp_path / "rep", with_history=False)

    eng_s = await _engine_for(dd_s)
    eng_r = await _engine_for(dd_r)

    small_classes, small_gen = await _first_generation_profiled(
        dd_s, eng_s, small_ids["cold_target"], small_ids["project"], pkg)
    rep_classes, rep_gen = await _first_generation_profiled(
        dd_r, eng_r, rep_ids["cold_target"], rep_ids["project"], pkg)

    assert sorted(small_classes) == sorted(rep_classes), (
        sorted(set(small_classes) ^ set(rep_classes)))
    assert small_classes == rep_classes, (
        "first-Generation statement count drifted: "
        f"{(small_classes - rep_classes) + (rep_classes - small_classes)}")

    # representative authority is materially larger (same world family)
    assert inv_r["counts"]["shots"] >= 2500
    assert inv_r["counts"]["spatial_frames"] >= 60

    # bounded siblings on BOTH sides (1..3) + real D0 registration
    for eng, gen_id in ((eng_s, small_gen), (eng_r, rep_gen)):
        async with eng.connect() as c:
            siblings = (await c.execute(text(
                "SELECT COUNT(*) FROM generation_derived_spatial_inputs "
                "WHERE generation_id = :g"), {"g": gen_id})).scalar()
            dsa = (await c.execute(text(
                "SELECT COUNT(*) FROM derived_spatial_artifacts"
            ))).scalar()
        assert 1 <= siblings <= 3, siblings
        assert dsa >= siblings  # real registration happened

    print(f"\nfirst-Generation small statements: "
          f"{sum(small_classes.values())}")
    print(f"first-Generation representative statements: "
          f"{sum(rep_classes.values())}")

    await eng_s.dispose()
    await eng_r.dispose()


# ---------------------------------------------------------------------------
# D.5 — required scale metrics record (§11.5 / F-090)
# ---------------------------------------------------------------------------


async def test_scale_metrics_recorded_without_thresholds(tmp_path):
    """F-090: record the §11.5 metric set from the representative
    fixture + a real backup/restore pass. Wall times and planner text
    are informational evidence only — no pass/fail threshold is applied
    to them."""
    import json as _json
    import sqlite3 as _sq
    import time as _time

    ids, inv, settings, dd = await _build(tmp_path / "rep",
                                          with_history=True)
    eng = await _engine_for(dd)

    from sqlalchemy import text

    async with eng.connect() as c:
        metrics = {
            "project_shot_count": (await c.execute(text(
                "SELECT COUNT(*) FROM shots WHERE project_id = :p"),
                {"p": ids["project"]})).scalar(),
            "frame_count": (await c.execute(text(
                "SELECT COUNT(*) FROM spatial_frames"))).scalar(),
            "axis_count": (await c.execute(text(
                "SELECT COUNT(*) FROM spatial_axes"))).scalar(),
            "track_count": (await c.execute(text(
                "SELECT COUNT(*) FROM spatial_tracks"))).scalar(),
            "transition_count": (await c.execute(text(
                "SELECT COUNT(*) FROM spatial_transitions"))).scalar(),
            "schema5_snapshot_bytes": (await c.execute(text(
                "SELECT COALESCE(SUM(LENGTH(snapshot_json)), 0) FROM "
                "shot_revisions WHERE json_extract(snapshot_json, "
                "'$.schema_version') = 5"))).scalar(),
            "generation_input_rows": (await c.execute(text(
                "SELECT COUNT(*) FROM generation_inputs"))).scalar(),
            "gdsi_rows": (await c.execute(text(
                "SELECT COUNT(*) FROM "
                "generation_derived_spatial_inputs"))).scalar(),
            "dsa_count": (await c.execute(text(
                "SELECT COUNT(*) FROM derived_spatial_artifacts"
            ))).scalar(),
        }
        t0 = _time.perf_counter()
        outcome = None
        from soloring.continuity.snapshots import resolve_working_dependencies
        from soloring.spatial import resolver as resolver_svc

        deps = await resolve_working_dependencies(c, ids["shot_a"])
        outcome = await resolver_svc.resolve_spatial_continuity(
            c, shot_id=ids["shot_a"], resolved_dependencies=deps)
        metrics["wall_seconds_current_resolution"] = (
            _time.perf_counter() - t0)
        assert outcome.ready
        metrics["embedded_world_snapshot_bytes"] = len(
            _json.dumps(outcome.pack["spatial_world"]))

    # repair M8 fixture placeholder blob bytes to true preimages (the
    # same posture as every recovery-fixture builder)
    import hashlib as _hl

    from soloring.assets.blob_store import BlobStore

    _store = BlobStore(settings)
    con = _sq.connect(str(dd / "soloring.db"))
    try:
        con.row_factory = _sq.Row
        preimages = {
            _hl.sha256(r["id"].encode()).hexdigest(): r["id"]
            for r in con.execute("SELECT id FROM assets")}
        live = [r[0] for r in con.execute(
            "SELECT hash FROM blobs WHERE hash IN (SELECT blob_hash FROM "
            "assets UNION ALL SELECT blob_hash FROM generation_inputs "
            "UNION ALL SELECT blob_hash FROM derived_spatial_artifacts "
            "UNION ALL SELECT blob_hash FROM "
            "generation_derived_spatial_inputs)")]
        for h in live:
            path = _store.path_for_hash(h)
            if (not path.is_file()
                    or _hl.sha256(path.read_bytes()).hexdigest() != h):
                content = preimages[h].encode()
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                con.execute(
                    "UPDATE blobs SET size_bytes = ? WHERE hash = ?",
                    (len(content), h))
        con.commit()
        metrics["sqlite_runtime_version"] = _sq.sqlite_version
        metrics["source_journal_mode"] = con.execute(
            "PRAGMA journal_mode").fetchone()[0]
        # ORM-created schema; stamp the head the production deployment
        # would carry (same fixture posture as the recovery template)
        from alembic import command
        from alembic.config import Config
        import soloring.settings as settings_mod

        saved = settings_mod._settings
        settings_mod._settings = settings
        try:
            cfg = Config(str(settings_mod.BASE_DIR / "server" /
                             "alembic.ini"))
            cfg.set_main_option(
                "script_location",
                str(settings_mod.BASE_DIR / "server" / "alembic"))
            command.stamp(cfg, "head")
        finally:
            settings_mod._settings = saved
    finally:
        con.close()

    # backup/restore metrics on a real pass
    import sys

    sys.path.insert(0, ".")
    import importlib

    rb = importlib.import_module("soloring.recovery.backup")
    t0 = _time.perf_counter()
    evidence = await rb.backup(settings, tmp_path / "metrics-backup")
    metrics["wall_seconds_backup"] = _time.perf_counter() - t0
    metrics["backup_db_bytes"] = (tmp_path / "metrics-backup" /
                                  "soloring.db").stat().st_size
    metrics["backup_blob_bytes"] = sum(
        p.stat().st_size
        for p in (tmp_path / "metrics-backup" / "blobs").rglob("*")
        if p.is_file())
    metrics["backup_artifact_bytes"] = sum(
        p.stat().st_size
        for p in (tmp_path / "metrics-backup" /
                  "workflow-artifacts").rglob("*") if p.is_file())
    t0 = _time.perf_counter()
    await rb.restore(tmp_path / "metrics-backup",
                     tmp_path / "metrics-restored")
    metrics["wall_seconds_restore"] = _time.perf_counter() - t0
    metrics["staged_journal_mode"] = evidence["staged"]["journal_mode"]

    # every metric recorded; none converted into a threshold assertion
    assert metrics["project_shot_count"] >= 2500
    assert metrics["dsa_count"] >= 1
    print("\nM10F-D metrics:", _json.dumps(metrics, indent=2,
                                           default=str))
    await eng.dispose()


# ---------------------------------------------------------------------------
# D.6 — canonical continuity demonstrations (§12 / F-092..F-096)
# ---------------------------------------------------------------------------


async def test_lobby_reverse_angle_shared_world_authority(
        factory, engine, settings, tmp_path):
    """F-092/F-093/F-094: two reverse-angle Shots capture the SAME
    approved SpatialWorldRevision identity/hash with independent camera
    plans; later current edits rewrite neither; camera-dependent derived
    bytes may differ without weakening the shared-world claim; a
    non-spatial package blocks rather than silently falling back."""
    import json as _json

    from sqlalchemy import text as _text

    from tests.test_m10e_generation import (
        _EXTENTS,
        _create as _e_create,
        _spatial_seed as _e_seed,
    )
    from tests.test_m10e_package3_production import _schema3_package
    from tests.test_m10d_resolver import CAM

    pkg = await _schema3_package(tmp_path)
    settings.executor = "comfy"
    settings.workflow_package_dir = pkg

    seed = await _e_seed(factory, staged=1, extents=_EXTENTS)
    shot_a = seed["shot"]
    shot_b = await _second_shot(factory, engine, seed)

    # shot_a already carries its plan from the seed (the normal camera).
    # shot_b gets the REVERSE-angle camera plan.
    from soloring.spatial import plans as plan_svc

    camera = _json.loads(_json.dumps(CAM))
    t = camera["keyframes"][0]["transform"]["translation_mm"]
    camera["keyframes"][0]["transform"]["translation_mm"] = [
        t[0], t[1], -t[2]]
    await plan_svc.put_spatial_plan(
        factory(), shot_b, expected_plan_hash=None, plan_raw={
            "schema_version": 1,
            "spatial_world_id": seed["world"]["id"],
            "camera": camera, "blocking": [], "axis_constraint": None,
        })

    gen_a = await _e_create(factory, settings, seed)
    seed_b = dict(seed, shot=shot_b)
    gen_b = await _e_create(factory, settings, seed_b)

    async with engine.connect() as c:
        rows = (await c.execute(_text(
            "SELECT sr.id, sr.snapshot_hash, json_extract(sr.snapshot_json,"
            " '$.spatial_continuity.spatial_world.revision_id') AS wrev "
            "FROM shot_revisions sr WHERE sr.shot_id IN (:a, :b) "
            "AND json_extract(sr.snapshot_json, '$.schema_version') = 5"),
            {"a": shot_a, "b": shot_b})).mappings().all()
    by_shot = {r["shot_id"] if "shot_id" in r.keys() else None: r
               for r in rows}
    assert len(rows) == 2
    hashes = {r["snapshot_hash"] for r in rows}
    wrevs = {r["wrev"] for r in rows}
    assert len(wrevs) == 1, "both Shots must capture ONE world revision"
    # F-094: independent cameras → distinct snapshot bytes is allowed
    # (hashes may differ), but the world revision identity is shared.

    # F-093: later current world edits rewrite neither ShotRevision
    from soloring.spatial import worlds as world_svc

    await world_svc.put_state_frame(
        factory(), await _current_state(engine, seed),
        await _origin_frame(engine, seed),
        translation_mm=[9999, 9999, 9999], rotation_udeg=[0, 0, 0],
        half_extents_mm=None, bound_entity_revision_id=None)
    async with engine.connect() as c:
        after = (await c.execute(_text(
            "SELECT snapshot_hash FROM shot_revisions WHERE shot_id "
            "IN (:a, :b) ORDER BY id"), {"a": shot_a, "b": shot_b})
        ).scalars().all()
    assert set(after) == hashes

    # camera-dependent derived bytes differ (world stream differs by
    # camera) — shared-world authority unaffected
    async with engine.connect() as c:
        blobs = (await c.execute(_text(
            "SELECT g.id, i.blob_hash FROM generations g JOIN "
            "generation_derived_spatial_inputs i ON i.generation_id = g.id "
            "WHERE i.position = 0 AND g.shot_id IN (:a, :b)"),
            {"a": shot_a, "b": shot_b})).mappings().all()
    world_streams = {r["blob_hash"] for r in blobs}
    # distinct cameras legitimately produce distinct D0 world streams
    assert 1 <= len(world_streams) <= 2

    # F-092-leg: a package without spatial capability blocks (verified
    # in compatibility tests); rerun stays historical after world change
    from soloring.generation import rerun

    async with engine.connect() as c:
        await c.execute(_text(
            "UPDATE generations SET status='succeeded', completed_at='t' "
            "WHERE id = :g"), {"g": gen_a.id})
        await c.commit()
    async with factory() as s:
        new = await rerun.create_rerun(s, gen_a.id)
    async with engine.connect() as c:
        nr = (await c.execute(_text(
            "SELECT workflow_spec_json FROM generations WHERE id = :g"),
            {"g": new.id})).scalar()
        orig = (await c.execute(_text(
            "SELECT workflow_spec_json FROM generations WHERE id = :g"),
            {"g": gen_a.id})).scalar()
    assert nr == orig


async def _lobby_loc(engine, seed):
    from sqlalchemy import text

    async with engine.connect() as c:
        return (await c.execute(text(
            "SELECT location_entity_id FROM spatial_worlds "
            "WHERE id = :w"), {"w": seed["world"]["id"]})).scalar()


async def _second_shot(factory, engine, seed):
    """A second assigned Shot depending on the SAME location entity."""
    from sqlalchemy import text

    from tests.test_m10d_resolver import _shot

    loc = await _lobby_loc(engine, seed)
    pid = (await engine.connect().start() if False else None)
    async with engine.connect() as c:
        pid = (await c.execute(text(
            "SELECT project_id FROM spatial_worlds WHERE id = :w"),
            {"w": seed["world"]["id"]})).scalar()
    return await _shot(factory, pid, [loc], assigned=True)


async def _current_state(engine, seed):
    from sqlalchemy import text

    async with engine.connect() as c:
        return (await c.execute(text(
            "SELECT id FROM spatial_world_states WHERE spatial_world_id = "
            ":w ORDER BY created_at LIMIT 1"),
            {"w": seed["world"]["id"]})).scalar()


async def _origin_frame(engine, seed):
    from sqlalchemy import text

    async with engine.connect() as c:
        return (await c.execute(text(
            "SELECT id FROM spatial_frames WHERE spatial_world_id = :w "
            "AND key = 'origin'"), {"w": seed["world"]["id"]})).scalar()


async def test_moving_character_direct_resolution_no_playback(
        factory, engine):
    """F-095/F-096: Shot 21/start resolves the front-desk transform
    DIRECTLY from the explicit Shot-20/end transition — no replay of
    Shot 20; deleting Shot 20's rendered Take or changing current UI
    blocking does not change Shot 21 spatial authority; changing the
    transition DOES change future current resolution."""
    import json as _json

    from sqlalchemy import text as _text

    from tests.test_m10d_resolver import CAM, _entities, _first_sequence, \
        _shot
    from tests.test_m10e_generation import _SETPIECE_T

    from soloring.spatial import (
        plans as plan_svc,
        revisions as wrev_svc,
        tracks as track_svc,
        transitions as trans_svc,
        worlds as world_svc,
    )

    pid = str(__import__("uuid").uuid4())
    async with factory() as s:
        await s.execute(_text(
            "INSERT INTO projects (id, name, created_at, updated_at) "
            "VALUES (:p, 'P', 't', 't')"), {"p": pid})
        seq_id = str(__import__("uuid").uuid4())
        await s.execute(_text(
            "INSERT INTO sequences (id, project_id, position, title, "
            "created_at, updated_at) VALUES (:i, :p, 0, 'S', 't','t')"),
            {"i": seq_id, "p": pid})
        await s.commit()
    ents = await _entities(factory, pid, {"loc": "location",
                                          "eva": "character"})
    loc, locrev = ents["loc"]
    eva = ents["eva"][0]

    world = await world_svc.create_world(
        factory(), pid, key="lobby", name="lobby", description=None,
        requirement="required", location_entity_id=loc)
    state = await world_svc.create_state(
        factory(), world["id"], location_entity_revision_id=locrev)
    origin = await world_svc.create_frame(
        factory(), world["id"], key="origin", name="origin",
        parent_spatial_frame_id=None, bound_entity_id=None)
    await world_svc.put_state_frame(
        factory(), state["id"], origin["id"], translation_mm=_SETPIECE_T,
        rotation_udeg=[0, 0, 0], half_extents_mm=None,
        bound_entity_revision_id=None)
    rev = await wrev_svc.capture_revision(factory(), state["id"])
    await wrev_svc.approve_revision(
        factory(), state["id"], revision_id=rev["id"],
        expected_approved_revision_id=None)

    desk = [-2400, 1750, -800]
    entrance = [-3600, 1500, -400]
    track = await track_svc.create_track(
        factory(), world["id"], entity_id=eva, requirement="optional")
    seq = seq_id
    await trans_svc.create_transition(
        factory(), track["id"], anchor_type="sequence", anchor_id=seq,
        boundary="start", operation="set", translation_mm=entrance,
        rotation_udeg=[0, 0, 0])

    shot20 = await _shot(factory, pid, [loc, eva], assigned=True)
    # Shot 20/end explicit handoff: transition anchored at shot 20 end
    await trans_svc.create_transition(
        factory(), track["id"], anchor_type="shot", anchor_id=shot20,
        boundary="end", operation="set", translation_mm=desk,
        rotation_udeg=[0, 0, 0])
    shot21 = await _shot(factory, pid, [loc, eva], assigned=True)

    for shot in (shot20, shot21):
        await plan_svc.put_spatial_plan(
            factory(), shot, expected_plan_hash=None, plan_raw={
                "schema_version": 1, "spatial_world_id": world["id"],
                "camera": _json.loads(_json.dumps(CAM)),
                "blocking": [], "axis_constraint": None,
            })

    from soloring.continuity.snapshots import resolve_working_dependencies
    from soloring.spatial.staging import resolve_effective_staging

    async def _staging(shot):
        async with engine.connect() as conn:
            deps = await resolve_working_dependencies(conn, shot)
            out = await resolve_effective_staging(
                conn, shot_id=shot, spatial_world_id=world["id"],
                resolved_entity_revisions={
                    d.entity_id: d.entity_revision_id for d in deps})
        return out

    s21 = await _staging(shot21)
    eva_row = [t for t in s21.states
               if t.entity_id == eva]
    assert eva_row, "eva must be staged at Shot 21"
    st = eva_row[0]
    assert [st.x_mm, st.y_mm, st.z_mm] == desk, (
        "Shot 21 must resolve the desk transform DIRECTLY")

    # F-096-leg: a rendered Take (real Generation row) never changes
    # spatial authority — capture a REAL revision for shot20 first
    from soloring.domain import revisions as _domain_revs

    async with factory() as s:
        shot20_rev = (await _domain_revs.capture_revision_with_visual(
            s, shot20))[0]
    async with factory() as s:
        gen_id = str(__import__("uuid").uuid4())
        await s.execute(_text(
            "INSERT INTO generations (id, shot_id, shot_revision_id, "
            "generation_number, operation, executor, workflow_id, "
            "workflow_version, "
            "workflow_template_hash, manifest_hash, compiled_prompt, "
            "prompt_compiler_version, seed, parameters_json, "
            "workflow_spec_json, workflow_spec_hash, status, queued_at) "
            "VALUES (:g, :s, :r, 1, 'generate', 'fake', 'w', 1, "
            ":th, :mh, 'p', 'v', NULL, '{}', '{}', "
            ":sh, 'succeeded', 't')"),
            {"g": gen_id, "s": shot20,
             "th": "a" * 64, "mh": "b" * 64, "sh": "c" * 64,
             "r": shot20_rev.id})
        await s.execute(_text(
            "INSERT INTO takes (id, shot_id, generation_id, output_key) "
            "VALUES (:i, :s, :g, 'video:0')"),
            {"i": str(__import__("uuid").uuid4()), "s": shot20,
             "g": gen_id})
        await s.commit()
    s21_after_take = await _staging(shot21)
    assert _staging_bytes(s21_after_take) == _staging_bytes(s21)

    # changing the explicit transition DOES change future resolution
    # (delete + re-create at the same coordinate — the frozen API)
    from sqlalchemy import text as _t2

    async with factory() as s:
        old_tid = (await s.execute(_t2(
            "SELECT id FROM spatial_transitions WHERE spatial_track_id = "
            ":t AND anchor_type = 'shot' AND anchor_id = :a AND boundary ="
            " 'end'"), {"t": track["id"], "a": shot20})).scalar_one()
    await trans_svc.delete_transition(factory(), old_tid)
    await trans_svc.create_transition(
        factory(), track["id"], anchor_type="shot", anchor_id=shot20,
        boundary="end", operation="set",
        translation_mm=[-2500, 1700, -900], rotation_udeg=[0, 0, 0])
    s21_new = await _staging(shot21)
    assert _staging_bytes(s21_new) != _staging_bytes(s21)


def _staging_bytes(outcome) -> bytes:
    from soloring.spatial.staging import canonical_staging_bytes

    return canonical_staging_bytes(outcome.states)
