"""M10E-E — Exact Rerun of real schema-3 Generations (frozen R3 §19).

Durable WorkflowSpec bytes verbatim, exact derived payload projection
(only generation_id rebinding), zero current-M10 reads, zero compiler/
materializer/registration calls, historical-mutation isolation, and
fail-closed corruption behavior (E-070..E-077)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import text

from tests.test_m10e_generation import (
    _EXTENTS,
    _create,
    _schema3_package,
    _siblings,
    _spatial_seed,
    _spatial_settings,
    _spec,
)


async def _terminal_generation(factory, engine, settings, tmp_path,
                               *, staged=2):
    pkg = await _schema3_package(tmp_path)
    seed = await _spatial_seed(factory, staged=staged, extents=_EXTENTS)
    gen = await _create(factory, _spatial_settings(settings, pkg), seed)
    async with engine.connect() as conn:
        await conn.execute(text(
            "UPDATE generations SET status='succeeded', completed_at='t' "
            "WHERE id = :g"), {"g": gen.id})
        await conn.commit()
    return gen, seed, pkg


async def test_rerun_copies_spec_bytes_and_derived_projection(
        factory, engine, settings, tmp_path):
    """E-070/E-071: WorkflowSpec JSON/hash verbatim; each sibling's
    identity-bearing tuple copied exactly; only the parent changes."""
    from soloring.generation import rerun

    gen, _, _ = await _terminal_generation(
        factory, engine, settings, tmp_path)
    new = await rerun.create_rerun(
        _session(factory), gen.id)
    src_rows = await _siblings(engine, gen.id)
    new_rows = await _siblings(engine, new.id)
    assert [r["input_key"] for r in src_rows] == \
        [r["input_key"] for r in new_rows]
    for s, n in zip(src_rows, new_rows):
        assert s == n  # full projection equality
    async with engine.connect() as conn:
        src = (await conn.execute(text(
            "SELECT workflow_spec_json, workflow_spec_hash FROM "
            "generations WHERE id = :g"), {"g": gen.id})).mappings().one()
        dst = (await conn.execute(text(
            "SELECT workflow_spec_json, workflow_spec_hash FROM "
            "generations WHERE id = :g"), {"g": new.id})).mappings().one()
    assert dst["workflow_spec_json"] == src["workflow_spec_json"]
    assert dst["workflow_spec_hash"] == src["workflow_spec_hash"]


def _session(factory):
    return factory()


async def test_rerun_zero_current_m10_reads_and_zero_rematerialization(
        factory, engine, settings, tmp_path, monkeypatch):
    """E-072/E-073: spies with positive controls — no current-M10 reads,
    no compose/materialize/register calls during rerun."""
    from sqlalchemy import event

    from soloring.generation import rerun
    from soloring.spatial import boxdepth, realize
    from soloring.spatial import derived as derived_mod
    from soloring.spatial.worker_inputs import current_m10_table_names

    gen, _, _ = await _terminal_generation(
        factory, engine, settings, tmp_path)

    called = {"compose": 0, "materialize": 0, "register": 0}

    async def _no_compose(*a, **k):
        called["compose"] += 1
        raise AssertionError("rerun must not compile spatial authority")

    def _no_materialize(*a, **k):
        called["materialize"] += 1
        raise AssertionError("rerun must not rematerialize D0")

    async def _no_register(*a, **k):
        called["register"] += 1
        raise AssertionError("rerun must not register derived artifacts")

    monkeypatch.setattr(realize, "compose_spatial_realization", _no_compose)
    monkeypatch.setattr(boxdepth, "materialize", _no_materialize)
    monkeypatch.setattr(derived_mod, "register_derived_artifact",
                        _no_register)

    seen: list[str] = []
    forbidden = set(current_m10_table_names())

    def _spy(conn, cursor, statement, parameters, context,
             executemany=False):
        s = statement.lower()
        if s.strip().startswith(("select", "insert", "update")):
            seen.append(s)

    eng = engine.sync_engine
    event.listen(eng, "before_cursor_execute", _spy)
    try:
        new = await rerun.create_rerun(_session(factory), gen.id)
        import re

        hits = [s for s in seen if any(
            re.search(rf"\b{t}\b", s) for t in forbidden)]
        assert hits == [], f"rerun read current M10: {hits[:2]}"
        assert called == {"compose": 0, "materialize": 0, "register": 0}
        assert (await _siblings(engine, new.id))
    finally:
        event.remove(eng, "before_cursor_execute", _spy)


async def test_current_authority_mutation_cannot_change_rerun_identity(
        factory, engine, settings, tmp_path):
    """E-074/§22.5: after the source Generation is terminal, aggressive
    current M10 mutation leaves the rerun's durable identity identical."""
    from soloring.generation import rerun

    gen, seed, _ = await _terminal_generation(
        factory, engine, settings, tmp_path)
    src_rows = await _siblings(engine, gen.id)
    src_spec = await _spec(engine, gen.id)

    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        # wipe/rewrite every current M10 authority surface
        await conn.execute(text(
            "DELETE FROM shot_spatial_plans WHERE shot_id = :s"),
            {"s": seed["shot"]})
        await conn.execute(text(
            "UPDATE spatial_world_revisions SET snapshot_json = '{}', "
            "snapshot_hash = :h WHERE id LIKE '%'"),
            {"h": "0" * 64})
        await conn.execute(text(
            "UPDATE spatial_tracks SET deleted_at = 't', "
            "requirement = 'optional'"))
        await conn.execute(text(
            "UPDATE spatial_worlds SET requirement = 'optional', "
            "deleted_at = 't'"))
        await conn.exec_driver_sql("COMMIT")

    new = await rerun.create_rerun(_session(factory), gen.id)
    assert await _spec(engine, new.id) == src_spec
    assert await _siblings(engine, new.id) == src_rows


async def test_rerun_execution_fails_closed_on_corrupt_history(
        factory, engine, settings, tmp_path):
    """E-075: corrupt physical derived bytes fail the rerun's worker
    verification closed — never rematerialize."""
    from soloring.assets.blob_store import BlobStore
    from soloring.errors import SoloRingError
    from soloring.generation import rerun
    from soloring.spatial import error_codes as ec
    from soloring.spatial.package3 import parse_manifest_v3
    from soloring.spatial import production_package as prod
    from soloring.spatial.worker_inputs import load_verified_derived_inputs

    gen, _, _ = await _terminal_generation(
        factory, engine, settings, tmp_path, staged=1)
    new = await rerun.create_rerun(_session(factory), gen.id)
    rows = await _siblings(engine, new.id)
    BlobStore(settings).path_for_hash(rows[0]["blob_hash"]).write_bytes(
        b"tampered")

    spec = await _spec(engine, new.id)
    async with factory() as session:
        with pytest.raises(SoloRingError) as ei:
            await load_verified_derived_inputs(
                session, BlobStore(settings), generation_id=new.id,
                workflow_spec=spec,
                manifest_v3=parse_manifest_v3(prod.production_manifest_v3()))
    assert ei.value.code == ec.DERIVED_SPATIAL_BLOB_CORRUPT


async def test_rerun_reuses_retained_blob_identities(
        factory, engine, settings, tmp_path):
    """§29: the rerun worker reuses the exact same derived artifact IDs /
    blob hashes as the source attempt."""
    from soloring.assets.blob_store import BlobStore
    from soloring.generation import rerun
    from soloring.spatial.package3 import parse_manifest_v3
    from soloring.spatial import production_package as prod
    from soloring.spatial.worker_inputs import load_verified_derived_inputs

    class _Up:
        async def upload(self, *, source_path: Path, filename: str,
                         subfolder: str):
            return filename, subfolder

    gen, _, _ = await _terminal_generation(
        factory, engine, settings, tmp_path, staged=2)
    new = await rerun.create_rerun(_session(factory), gen.id)
    spec = await _spec(engine, new.id)
    async with factory() as session:
        verified = await load_verified_derived_inputs(
            session, BlobStore(settings), generation_id=new.id,
            workflow_spec=spec,
            manifest_v3=parse_manifest_v3(prod.production_manifest_v3()))
    assert [v.blob_hash for v in verified] == \
        [r["blob_hash"] for r in await _siblings(engine, gen.id)]
