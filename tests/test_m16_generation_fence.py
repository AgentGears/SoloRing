"""M16:EXEC — schema-7 generation fail-closed fence + Exact Rerun (§22)."""

from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.m16_seed_b import (
    event,
    post_event,
    seed_feature_world,
    state,
)
from tests.test_m16_capture import _capture

GEN_ID = "00000000-0000-4000-8000-0000000000a1"
HEX = "0" * 64


async def _insert_terminal_generation(engine, sid, revision_id):
    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT INTO generations (id, shot_id, shot_revision_id, "
            "status, operation, executor, workflow_id, "
            "workflow_version, workflow_template_hash, manifest_hash, "
            "compiled_prompt, prompt_compiler_version, "
            "parameters_json, workflow_spec_json, workflow_spec_hash, "
            "attempt_id, generation_number, "
            "created_at, updated_at) "
            "VALUES (:id, :s, :r, 'succeeded', 'generate', 'comfy', "
            "'wf', 1, :th, :th, 'p', 'v1', '{}', :sj, :sh, 1, 1, "
            "strftime('%Y-%m-%dT%H:%M:%fZ','now'), "
            "strftime('%Y-%m-%dT%H:%M:%fZ','now'))"),
            {"id": GEN_ID, "s": sid, "r": revision_id, "th": HEX,
              "sj": '{"schema_version": 1}', "sh": '0421214960441d55a9859ecf90ddb72f90b7ca185481b2154652c40f392d63af'})


async def test_exec_01_schema7_refused_before_generation_row(client, factory):
    """Any non-empty schema-7 intra_shot authority — including an
    all-transient set — refuses generation creation with the typed code,
    before any Generation row exists."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(client, sid, event(fid, 1000, state(), state("fresh")))
    revision, _ = await _capture(client, sid)
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        before = (await conn.execute(text(
            "SELECT COUNT(*) FROM generations WHERE shot_id = :s"),
            {"s": sid})).scalar_one()
    r = await client.post(f"/shots/{sid}/generations")
    assert r.status_code == 409, r.text
    assert "INTRA_SHOT_REALIZATION_UNSUPPORTED" in r.text
    assert r.json()["details"]["shot_revision_id"] == revision.id
    async with engine.connect() as conn:
        after = (await conn.execute(text(
            "SELECT COUNT(*) FROM generations WHERE shot_id = :s"),
            {"s": sid})).scalar_one()
    assert after == before


async def test_exec_04_no_lowering_or_stripping(client, factory):
    """The refusal is typed and total: no Generation row, no inputs, and
    the captured ShotRevision keeps its schema-7 authority intact."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(client, sid, event(fid, 1000, state(), state("fresh")))
    revision, _ = await _capture(client, sid)
    r = await client.post(f"/shots/{sid}/generations")
    assert r.status_code == 409
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        snap = json.loads((await conn.execute(text(
            "SELECT snapshot_json FROM shot_revisions WHERE id = :r"),
            {"r": revision.id})).scalar_one())
        gi = (await conn.execute(text(
            "SELECT COUNT(*) FROM generation_inputs"))).scalar_one()
    assert snap["schema_version"] == 7
    assert "intra_shot" in snap
    assert gi == 0


async def test_exec_05_exact_rerun_stays_pinned(client, factory):
    """A pre-M16 generation's Exact Rerun remains pinned to its captured
    ShotRevision and never consults current M16 state."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    engine = client._transport.app.state.engine

    # event-free capture + a terminal generation row pinned to it
    revision, _ = await _capture(client, sid)
    await _insert_terminal_generation(engine, sid, revision.id)

    # current M16 authority appears afterwards (a schema-7 revision now
    # exists) — the rerun must stay pinned to the OLD revision
    await post_event(client, sid, event(fid, 1000, state(), state("fresh")))
    await _capture(client, sid)

    from soloring.generation.rerun import create_rerun

    async with AsyncSession(engine, expire_on_commit=False) as session:
        rr = await create_rerun(session, GEN_ID)
    assert rr.shot_revision_id == revision.id
    async with engine.connect() as conn:
        new_snap = json.loads((await conn.execute(text(
            "SELECT snapshot_json FROM shot_revisions WHERE id = :r"),
            {"r": rr.shot_revision_id})).scalar_one())
    assert new_snap["schema_version"] < 7


async def test_exec_02_03_refusal_precedes_artifact_publication(client,
                                                                 factory):
    """EXEC:02/03 — the schema-7 refusal precedes workflow-package
    publication: a refused comfy request leaves an initially empty
    artifact store empty (no manifest/template/package/queue writes)."""
    from soloring.workflows.manifest import WORKFLOW_DIR as V1_DIR

    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(client, sid, event(fid, 1000, state(), state("fresh")))
    await _capture(client, sid)
    settings = client._transport.app.state.settings
    store_root = settings.data_dir / "workflow-artifacts"
    assert not store_root.exists() or not any(store_root.rglob("*.json")), (
        "artifact store not initially empty")

    saved_executor = settings.executor
    saved_pkg = settings.workflow_package_dir
    settings.executor = "comfy"
    settings.workflow_package_dir = V1_DIR
    try:
        r = await client.post(f"/shots/{sid}/generations")
    finally:
        settings.executor = saved_executor
        settings.workflow_package_dir = saved_pkg
    assert r.status_code == 409, r.text
    assert "INTRA_SHOT_REALIZATION_UNSUPPORTED" in r.text
    placed = list(store_root.rglob("*.json")) if store_root.exists() else []
    assert placed == [], (
        f"refused schema-7 request published workflow artifacts: {placed}")
