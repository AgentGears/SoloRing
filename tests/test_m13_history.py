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
        for table in CURRENT_M13_TABLES:
            if table in statement:
                touched.append(table)

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
