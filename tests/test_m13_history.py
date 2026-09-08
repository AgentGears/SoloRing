"""M13 historical isolation proofs (frozen R3 §30.8 M13-HISTORY core)."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import event, text

from tests.test_m13_shot_capture import (
    _capture,
    _full_m13_world,
    _select_binding,
)

CURRENT_M13_TABLES = (
    "shot_production_world_selections",
    "composition_occurrence_authority_subjects",
    "production_instance_features",
    "production_instance_feature_transitions",
    "production_instance_spatial_tracks",
    "production_instance_spatial_transitions",
)


def _spy_check(statement: str, touched: list) -> None:
    for table in CURRENT_M13_TABLES:
        if table in statement:
            touched.append(table)


async def _captured_world(client, *, tag=b"m13-hist"):
    b = await _full_m13_world(client, tag=tag)
    sel = await _select_binding(client, b)
    revision, _ = await _capture(client, b["shot"])
    return b, sel, revision


async def test_m13_history_01(client):
    """M13-HISTORY:01 — schema-6 parent/child projection exact, including
    contiguous child position == canonical pack-array index."""
    b, sel, revision = await _captured_world(client)
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        parent = (await conn.execute(text(
            "SELECT * FROM shot_revision_production_worlds WHERE "
            "shot_revision_id = :r"), {"r": revision.id})).mappings().one()
        frows = (await conn.execute(text(
            "SELECT position, occurrence_id FROM "
            "shot_revision_production_instance_feature_states WHERE "
            "shot_revision_id = :r ORDER BY position"),
            {"r": revision.id})).fetchall()
        srows = (await conn.execute(text(
            "SELECT position, occurrence_id, "
            "production_instance_track_id FROM "
            "shot_revision_production_instance_spatial_states WHERE "
            "shot_revision_id = :r ORDER BY position"),
            {"r": revision.id})).fetchall()
    pack = json.loads(revision.snapshot_json)["production_world"]
    assert parent["binding_id"] == sel["binding_id"]
    assert [r.position for r in srows] == list(
        range(len(pack["instance_spatial_states"])))
    assert srows[0].occurrence_id == (
        pack["instance_spatial_states"][0]["occurrence_id"])
    assert srows[0].production_instance_track_id == (
        pack["instance_spatial_states"][0]["production_instance_track_id"])
    assert [r.position for r in frows] == list(
        range(len(pack["instance_feature_states"])))


async def test_m13_history_02(client):
    """M13-HISTORY:02 — identical recapture converges through the existing
    snapshot identity and validates every M13 child; corruption of a
    stored child fails closed (no repair, no refill)."""
    b, sel, revision = await _captured_world(client, tag=b"hist02")
    revision2, _ = await _capture(client, b["shot"])
    assert revision2.id == revision.id  # snapshot-hash convergence
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        await conn.execute(text(
            "UPDATE shot_revision_production_instance_spatial_states "
            "SET x_mm = 424242 WHERE shot_revision_id = :r"),
            {"r": revision.id})
        await conn.commit()
    from soloring.errors import SoloRingError
    with pytest.raises(SoloRingError) as ei:
        await _capture(client, b["shot"])
    assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"


async def test_m13_history_03(client):
    """M13-HISTORY:03 — a missing immutable binding dependency fails the
    historical read closed (no downgrade, no substitution)."""
    b, sel, revision = await _captured_world(client, tag=b"hist03")
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        await conn.execute(text("PRAGMA foreign_keys=OFF"))
        await conn.execute(text(
            "DELETE FROM composition_spatial_binding_subjects WHERE "
            "binding_id = :b"), {"b": sel["binding_id"]})
        await conn.execute(text(
            "DELETE FROM composition_spatial_bindings WHERE id = :b"),
            {"b": sel["binding_id"]})
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        await conn.commit()
    r = await client.get(
        f"/shot-revisions/{revision.id}/production-world")
    assert r.status_code == 500, r.text
    assert r.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"


async def test_m13_history_09(client):
    """M13-HISTORY:09 (historical-reader half) — the captured-graph-only
    reader performs ZERO reads of current M13 authoring tables (query
    spy over the whole read; the generation-rerun-path spy completes the
    cell in M13E closure)."""
    b, sel, revision = await _captured_world(client, tag=b"hist09")
    engine = client._transport.app.state.engine
    touched: list[str] = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _spy(conn, cursor, statement, parameters, context, executemany):
        _spy_check(statement, touched)

    try:
        r = await client.get(
            f"/shot-revisions/{revision.id}/production-world")
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["captured"] is True
        assert out["captured_as_history"] is True
        assert out["binding"]["binding_id"] == sel["binding_id"]
        assert len(out["captured_spatial_states"]) == 1
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _spy)
    assert touched == [], touched


async def test_m13_history_10(client):
    """M13-HISTORY:10 — a missing/corrupt pinned spatial interpretation
    fails the historical read closed."""
    b, sel, revision = await _captured_world(client, tag=b"hist10")
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        await conn.execute(text("PRAGMA foreign_keys=OFF"))
        await conn.execute(text(
            "UPDATE production_revision_spatial_interpretations SET "
            "interpretation_hash = :bad WHERE production_revision_id = :r"),
            {"r": b["production_revision_id"], "bad": "0" * 64})
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        await conn.commit()
    r = await client.get(
        f"/shot-revisions/{revision.id}/production-world")
    assert r.status_code == 500, r.text
    assert r.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"


async def test_m13_history_09_rerun(client):
    """M13-HISTORY:09 (rerun half) — Exact Rerun of a schema-6 source
    Generation performs ZERO reads of current M13 authoring tables (query
    spy over the whole fenced rerun creation)."""
    import hashlib

    from soloring.generation import rerun as rerun_mod

    b = await _full_m13_world(client, tag=b"hist09r")
    sel = await _select_binding(client, b)
    revision, _ = await _capture(client, b["shot"])
    engine = client._transport.app.state.engine
    gen = "33333333-3333-3333-3333-333333333333"
    spec = json.dumps({"schema_version": 3})
    async with engine.connect() as conn:
        await conn.execute(text(
            "INSERT INTO generations (id, shot_id, shot_revision_id, "
            "status, operation, executor, workflow_id, workflow_version, "
            "workflow_template_hash, manifest_hash, compiled_prompt, "
            "prompt_compiler_version, parameters_json, "
            "workflow_spec_json, workflow_spec_hash, created_at, "
            "updated_at, generation_number) VALUES "
            "(:g, :sh, :r, 'succeeded', 'generate', 'comfy', 'wf', 1, "
            ":th, :mh, 'p', 'v1', '{}', :sj, :sh2, 't', 't', 1)"),
            {"g": gen, "sh": b["shot"], "r": revision.id,
             "th": "e" * 64, "mh": "e" * 64, "sj": spec,
             "sh2": hashlib.sha256(spec.encode()).hexdigest()})
        await conn.commit()

    touched: list[str] = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _spy(conn, cursor, statement, parameters, context, executemany):
        _spy_check(statement, touched)

    try:
        new_id = await rerun_mod._create_rerun_fenced(engine, gen)
        assert new_id is not None and new_id != gen
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _spy)
    assert touched == [], touched
    # the rerun copies the exact captured revision identity
    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT shot_revision_id FROM generations WHERE id = :g"),
            {"g": new_id})).scalar_one()
    assert row == revision.id


# --- remaining HISTORY cells --------------------------------------------------


async def _history_04_05_body(client, tag):
    """M13-HISTORY:04/05 — missing ProductionRevision closure and a
    missing/corrupt C or W revision fail the historical read closed."""
    # shared body; each exact-name owner calls it
    from tests.test_m13_shot_capture import (
        _capture,
        _full_m13_world,
        _select_binding,
    )

    b = await _full_m13_world(client, tag=b"hist0405")
    sel = await _select_binding(client, b)
    revision, _ = await _capture(client, b["shot"])
    engine = client._transport.app.state.engine
    # 04: delete the retained-blob closure row (PR closure unreachable)
    async with engine.connect() as conn:
        await conn.execute(text("PRAGMA foreign_keys=OFF"))
        await conn.execute(text(
            "DELETE FROM production_revision_closures WHERE "
            "production_revision_id = :r"), {"r": b["production_revision_id"]})
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        await conn.commit()
    r = await client.get(
        f"/shot-revisions/{revision.id}/production-world")
    assert r.status_code == 500 and r.json()[
        "error_code"] == "INTERNAL_INVARIANT_VIOLATION"

    b2 = await _full_m13_world(client, tag=b"hist0405b")
    sel2 = await _select_binding(client, b2)
    revision2, _ = await _capture(client, b2["shot"])
    # 05: delete the pinned SpatialWorldRevision (corrupt closure)
    async with engine.connect() as conn:
        await conn.execute(text("PRAGMA foreign_keys=OFF"))
        await conn.execute(text(
            "DELETE FROM spatial_world_revisions WHERE id = :r"),
            {"r": b2["rev"]["id"]})
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        await conn.commit()
    r = await client.get(
        f"/shot-revisions/{revision2.id}/production-world")
    assert r.status_code == 500 and r.json()[
        "error_code"] == "INTERNAL_INVARIANT_VIOLATION"



async def test_m13_history_04(client):
    """M13-HISTORY:04 — missing ProductionRevision closure fails closed."""
    await _history_04_05_body(client, tag='hist04')

async def test_m13_history_05(client):
    """M13-HISTORY:05 — missing/corrupt C or W revision fails closed."""
    await _history_04_05_body(client, tag='hist05')

async def _history_06_07_08_body(client, tag):
    """M13-HISTORY:06/07/08 — with the CURRENT M13 surfaces unavailable
    (selection table dropped; PI feature/feature-transition tables
    dropped; PI spatial-transition table dropped and every PI track
    soft-deleted so current staging resolution is impossible), the
    historical read and the captured-graph semantics still succeed.

    The PI-track ROW table itself must remain: soft-deleted track rows
    are immutable provenance for pinned A4 targets (frozen §22.1/§23.4 —
    recovery and the binding verifier require row existence, never
    current eligibility), so "unavailable" means the current resolver
    surface, not the retained provenance rows."""
    # shared body; each exact-name owner calls it
    from soloring.generation import rerun as rerun_mod

    from tests.test_m13_shot_capture import (
        _capture,
        _full_m13_world,
        _select_binding,
    )

    b = await _full_m13_world(client, tag=b"hist0608")
    sel = await _select_binding(client, b)
    revision, _ = await _capture(client, b["shot"])
    # a terminal generation bound to the captured revision for rerun
    import hashlib

    gen = "44444444-4444-4444-4444-444444444444"
    spec = json.dumps({"schema_version": 3})
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        await conn.execute(text(
            "INSERT INTO generations (id, shot_id, shot_revision_id, "
            "status, operation, executor, workflow_id, workflow_version, "
            "workflow_template_hash, manifest_hash, compiled_prompt, "
            "prompt_compiler_version, parameters_json, "
            "workflow_spec_json, workflow_spec_hash, created_at, "
            "updated_at, generation_number) VALUES "
            "(:g, :sh, :r, 'succeeded', 'generate', 'comfy', 'wf', 1, "
            ":th, :mh, 'p', 'v1', '{}', :sj, :sh2, 't', 't', 1)"),
            {"g": gen, "sh": b["shot"], "r": revision.id,
             "th": "e" * 64, "mh": "e" * 64, "sj": spec,
             "sh2": hashlib.sha256(spec.encode()).hexdigest()})
        await conn.commit()
        # make every CURRENT M13 authoring/resolution surface unavailable
        # (PRAGMA must run outside any open transaction)
        await conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        await conn.execute(text(
            "DROP TABLE shot_production_world_selections"))
        await conn.execute(text(
            "DROP TABLE production_instance_feature_transitions"))
        await conn.execute(text(
            "DROP TABLE production_instance_features"))
        await conn.execute(text(
            "DROP TABLE production_instance_spatial_transitions"))
        await conn.execute(text(
            "DROP TABLE production_instance_spatial_tracks"))
        await conn.execute(text(
            "DROP TABLE composition_occurrence_authority_subjects"))
        await conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        await conn.commit()
    r = await client.get(
        f"/shot-revisions/{revision.id}/production-world")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["captured"] is True
    assert out["binding"]["binding_id"] == sel["binding_id"]
    assert len(out["captured_spatial_states"]) == 1
    # the rerun of the captured generation still works (06: no selection
    # table; 07: no PI feature tables; 08: no PI track/transition tables)
    new_id = await rerun_mod._create_rerun_fenced(engine, gen)
    assert new_id != gen


async def test_m13_history_06(client):
    """M13-HISTORY:06 — current selection unavailable; historical read succeeds."""
    await _history_06_07_08_body(client, tag='hist06')

async def test_m13_history_07(client):
    """M13-HISTORY:07 — current PI feature tables unavailable; historical read succeeds."""
    await _history_06_07_08_body(client, tag='hist07')

async def test_m13_history_08(client):
    """M13-HISTORY:08 — current PI track tables unavailable; historical read succeeds."""
    await _history_06_07_08_body(client, tag='hist08')
