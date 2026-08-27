"""M10E races (frozen R3 §22) — real transactions and deterministic
seams; no sleep-based ordering (E-081/E-083/E-084)."""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text

from soloring.assets.blob_store import BlobStore
from soloring.errors import SoloRingError
from soloring.spatial import error_codes as ec
from soloring.spatial.derived import (
    prepare_derived_artifact,
    register_derived_artifact,
)

from tests.test_m10a4_worker_rerun import _fp_json, _mkblob, _spec_json
from tests.test_m10e_generation import (
    _EXTENTS,
    _create,
    _schema3_package,
    _siblings,
    _spatial_seed,
    _spatial_settings,
)

_KINDS = frozenset({"boxdepth_control_video"})
_MEDIA = frozenset({"application/x-npy"})
_ALGS = frozenset({("soloring.boxdepth.rasterizer", "1.0.0")})


async def _project(factory, pid: str) -> None:
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO projects (id, name, created_at, updated_at) "
                "VALUES (:p, 'P', 't', 't')"), {"p": pid})


async def _blob_row(factory, store, blob: str) -> None:
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT OR IGNORE INTO blobs (hash, path, size_bytes, "
                "created_at) VALUES (:h, :pa, 19, 't')"),
                {"h": blob, "pa": str(store.path_for_hash(blob))})


async def test_authority_mutation_during_realization_changes_nothing(
        factory, engine, settings, tmp_path, monkeypatch):
    """§22.2/E-083: current M10 authority mutated between the ShotRevision
    capture seam and D0 composition cannot influence the realization —
    the compiler consumes ONLY the captured pack (deterministic parked
    seam, no sleeps)."""
    from soloring.spatial import realize

    pkg = await _schema3_package(tmp_path)
    s = _spatial_settings(settings, pkg)

    baseline_seed = await _spatial_seed(factory, staged=1, extents=_EXTENTS)
    baseline = await _create(factory, s, baseline_seed)
    baseline_rows = await _siblings(engine, baseline.id)

    raced_seed = await _spatial_seed(factory, staged=1, extents=_EXTENTS)
    real_compose = realize.compose_spatial_realization
    parked = {"fired": False}
    db_path = settings.data_dir / "soloring.db"

    def _mutating_compose(pack, **kwargs):
        if not parked["fired"]:
            parked["fired"] = True
            import sqlite3

            con = sqlite3.connect(db_path)
            con.execute("PRAGMA busy_timeout=10000")
            con.execute("BEGIN IMMEDIATE")
            con.execute(
                "UPDATE spatial_worlds SET requirement = 'optional'")
            con.execute("UPDATE shot_spatial_plans SET plan_json = '{}'")
            con.commit()
            con.close()
        return real_compose(pack, **kwargs)

    monkeypatch.setattr(
        realize, "compose_spatial_realization", _mutating_compose)
    raced = await _create(factory, s, raced_seed)
    raced_rows = await _siblings(engine, raced.id)

    # identical geometry ⇒ identical D0 identities regardless of the
    # concurrent current-authority mutation
    assert [r["blob_hash"] for r in raced_rows] == \
        [r["blob_hash"] for r in baseline_rows]


def _barrier_after(engine, marker_prefix: str):
    """Deterministic contested-order barrier (E-081/APR-033): returns an
    asyncio.Event that fires exactly when the FIRST statement starting
    with ``marker_prefix`` reaches the cursor — the second contender
    awaits it before starting, so its write attempt necessarily meets
    the first contender's OPEN write unit at the real SQLite seam (WAL
    single-writer serializes them). No sleeps; contention is forced."""
    from sqlalchemy import event

    fired = asyncio.Event()

    def _spy(conn, cursor, statement, parameters, context,
             executemany=False):
        if not fired.is_set() and statement.strip().startswith(
                marker_prefix):
            fired.set()

    event.listen(engine.sync_engine, "before_cursor_execute", _spy)
    return fired, lambda: event.remove(engine.sync_engine,
                                       "before_cursor_execute", _spy)


async def test_concurrent_identical_registrations_converge(
        factory, engine, settings):
    """§22.3/E-084: two real concurrent registrations of the same
    prepared artifact converge on one identity through the real
    BEGIN IMMEDIATE seam — the second contender is RELEASED only once
    the first holds the write lock (deterministic barrier)."""
    pid = "00000000-0000-4000-8000-0000000000c0"
    await _project(factory, pid)
    store = BlobStore(settings)
    blob = await _mkblob(store, b"race-control-bytes")
    await _blob_row(factory, store, blob)
    prepared = prepare_derived_artifact(
        _spec_json(blob, "9" * 64), _fp_json(), blob,
        allowed_artifact_kinds=_KINDS, allowed_media_types=_MEDIA,
        allowed_algorithms=_ALGS)

    async def _register():
        async with factory() as session:
            return await register_derived_artifact(
                session, store, pid, prepared)

    fired, detach = _barrier_after(engine, "BEGIN IMMEDIATE")
    try:
        first = asyncio.create_task(_register())
        await asyncio.wait_for(fired.wait(), timeout=30)
        second = asyncio.create_task(_register())
        a, b = await asyncio.gather(first, second)
    finally:
        detach()
    assert a == b
    async with engine.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM derived_spatial_artifacts"))).scalar()
    assert n == 1


async def test_concurrent_divergent_registration_fails_nondeterministic(
        factory, engine, settings):
    """§22.3: same spec/runtime + different Blob → exactly one identity
    survives; the loser fails DERIVED_SPATIAL_NONDETERMINISTIC. BOTH
    commit orders are forced deterministically (barrier at the write
    seam): each round releases the second contender only after the first
    holds BEGIN IMMEDIATE."""
    store = BlobStore(settings)
    blob = await _mkblob(store, b"race-control-bytes")
    other = await _mkblob(store, b"divergent-control-bytes")
    first = prepare_derived_artifact(
        _spec_json(blob, "9" * 64), _fp_json(), blob,
        allowed_artifact_kinds=_KINDS, allowed_media_types=_MEDIA,
        allowed_algorithms=_ALGS)
    divergent = prepare_derived_artifact(
        first.spec_json, first.runtime_json, other,
        allowed_artifact_kinds=_KINDS, allowed_media_types=_MEDIA,
        allowed_algorithms=_ALGS)
    assert divergent.spec_hash == first.spec_hash
    assert divergent.blob_hash != first.blob_hash

    async def _register(p):
        async with factory() as session:
            return await register_derived_artifact(session, store, _pid, p)

    for leader, follower in ((first, divergent), (divergent, first)):
        _pid = "00000000-0000-4000-8000-0000000000c%d" % (
            1 if leader is first else 2)
        await _project(factory, _pid)
        for h in (leader.blob_hash, follower.blob_hash):
            await _blob_row(factory, store, h)
        fired, detach = _barrier_after(engine, "BEGIN IMMEDIATE")
        try:
            lead_task = asyncio.create_task(_register(leader))
            await asyncio.wait_for(fired.wait(), timeout=30)
            follow_task = asyncio.create_task(_register(follower))
            results = await asyncio.gather(lead_task, follow_task,
                                           return_exceptions=True)
        finally:
            detach()
        ok = [r for r in results if not isinstance(r, Exception)]
        bad = [r for r in results if isinstance(r, Exception)]
        assert len(ok) == 1 and len(bad) == 1, results
        assert isinstance(bad[0], SoloRingError)
        assert bad[0].code == ec.DERIVED_SPATIAL_NONDETERMINISTIC
        async with engine.connect() as conn:
            n = (await conn.execute(text(
                "SELECT COUNT(*) FROM derived_spatial_artifacts "
                "WHERE project_id = :p"), {"p": _pid})).scalar()
        assert n == 1


async def test_concurrent_generation_creations_each_atomic(
        factory, engine, settings, tmp_path):
    """§22.4: concurrent schema-3 creations for the same Shot create
    distinct attempts sharing convergent derived identities; no queued
    Generation exists with missing spatial siblings. The second creation
    is released only after the first contender's Generation INSERT is
    in-flight (deterministic barrier at the write seam)."""
    pkg = await _schema3_package(tmp_path)
    seed = await _spatial_seed(factory, staged=2, extents=_EXTENTS)
    s = _spatial_settings(settings, pkg)

    fired, detach = _barrier_after(engine, "INSERT INTO generations")
    try:
        g1_task = asyncio.create_task(_create(factory, s, seed))
        await asyncio.wait_for(fired.wait(), timeout=60)
        g2_task = asyncio.create_task(_create(factory, s, seed))
        g1, g2 = await asyncio.gather(g1_task, g2_task)
    finally:
        detach()
    assert g1.id != g2.id
    r1 = await _siblings(engine, g1.id)
    r2 = await _siblings(engine, g2.id)
    assert len(r1) == len(r2) == 3
    assert [r["blob_hash"] for r in r1] == [r["blob_hash"] for r in r2]
    async with engine.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM derived_spatial_artifacts"))).scalar()
    assert n == 3
