"""M9 r6 — the §59 new-Generation statement proof (r5-gate closure).

The frozen §59 contract: for ONE target NEW Generation, read + write SQL
round trips — including GenerationInputs persistence — must be
cardinality-independent. This file keeps the r5 representative family
(multi-channel matrix package, ready target persisting multiple
realization-backed GenerationInputs) and measures POST
/shots/{id}/generations small vs representative at ~2,500 Shots.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine as SyncEngine

from tests.test_m8a_visual import (
    _entity_with_revision,
    _facet,
    _feature,
    _seed_project,
)
from tests.test_m8b_curation import _assets
from tests.test_m8c_resolver import (
    _approve_anchor,
    _depend,
    _topology,
)
from tests.test_m9a_package import V4_DIR
from tests.test_m9r5_representative import (
    SCALE_BULK_OPTIONAL_FACETS,
    SCALE_TOTAL_SHOTS,
    _anchor_with_items,
    _matrix_package,
)

import json


async def _scene_id_of(engine, shot_id):
    async with engine.connect() as conn:
        return (await conn.execute(
            text('SELECT scene_id FROM shots WHERE id = :s'),
            {'s': shot_id},
        )).scalar()


async def _multi_input_target(client, factory, engine, pid):
    """A ready multi-channel target whose Generation persists MULTIPLE
    realization-backed GenerationInputs (hero + detail multi-view +
    shared feature-value)."""
    eva, eva_rev = await _entity_with_revision(
        client, factory, pid, name="Eva"
    )
    assets = await _assets(engine, pid, 3)

    f_identity = await _facet(
        client, pid, "entity", entity_id=eva["id"], facet_key="identity",
    )
    await _anchor_with_items(
        client, f_identity["id"], {"entity_revision_id": eva_rev},
        assets, [(assets[0], "primary", "front")],
    )
    f_hair = await _facet(
        client, pid, "entity", entity_id=eva["id"], facet_key="hair",
        requirement="optional",
    )
    await _anchor_with_items(
        client, f_hair["id"], {"entity_revision_id": eva_rev},
        assets, [(assets[1], "primary", "side"),
                  (assets[2], "supporting", "back")],
    )
    feat_cut = await _feature(client, eva["id"])
    f_cut = await _facet(
        client, pid, "feature", feature_id=feat_cut["id"],
        facet_key="cut",
    )
    await _anchor_with_items(
        client, f_cut["id"],
        {"value": "fresh",
         "visual_context_entity_revision_id": eva_rev},
        assets, [(assets[0], "primary", "macro")],
    )

    seq, scene, shots = await _topology(client, factory, pid)
    await _depend(client, shots[0], [eva["id"]])
    await client.post(
        f"/continuity-features/{feat_cut['id']}/transitions",
        json={"anchor_type": "scene", "anchor_id": scene,
              "boundary": "start", "operation": "set", "value": "fresh"},
    )
    return shots[0], eva


async def _count_generation_statements(client, shot_id):
    """POST /generations under the SQL spy: every read AND write round
    trip, including GenerationInputs persistence."""
    n = {"count": 0}

    def before(conn, cursor, statement, params, ctx, many):
        n["count"] += 1

    from sqlalchemy import event

    event.listen(SyncEngine, "before_cursor_execute", before)
    try:
        r = await client.post(f"/shots/{shot_id}/generations")
        assert r.status_code == 202, r.text
    finally:
        event.remove(SyncEngine, "before_cursor_execute", before)
    return n["count"], r.json()["id"]


async def test_generation_statement_count_cardinality_independent(
    client, factory, engine, settings, tmp_path,
):
    matrix_pkg = _matrix_package(tmp_path)
    settings.workflow_package_dir = matrix_pkg
    settings.executor = "comfy"

    pid = await _seed_project(factory)
    shot, eva = await _multi_input_target(client, factory, engine, pid)
    # A SECOND shot of the SAME family: the representative-scale run
    # measures a first Generation on fresh state (the second POST on one
    # shot would reuse the ShotRevision and legitimately cost fewer
    # statements — a different run shape, not a comparable one).
    from soloring.api.schemas.shots import ShotCreate
    from soloring.domain import shots as shot_svc

    async with factory() as s:
        shot_b = (await shot_svc.create_shot(
            s, pid, ShotCreate(subject='target b'))).id
    scene_id = await _scene_id_of(engine, shot)
    r = await client.put(
        f'/scenes/{scene_id}/shots',
        json={'shot_ids': [shot, shot_b]},
    )
    assert r.status_code == 200, r.text
    await _depend(client, shot_b, [eva['id']])

    # --- Small legal target: one Generation, all reads + writes. -------
    small, gid_small = await _count_generation_statements(client, shot)
    async with engine.connect() as conn:
        input_rows_small = (await conn.execute(
            text("SELECT COUNT(*) FROM generation_inputs "
                 "WHERE generation_id = :g"),
            {"g": gid_small},
        )).scalar()
    # The multi-channel target persists MULTIPLE realization inputs
    # (identity 1 + hair 2 + cut 1 = 4) — the row-count dimension §59
    # protects while round trips stay fixed.
    assert input_rows_small >= 4

    # --- Representative volume: ~2,500 Shots + bulk facets. -------------
    import uuid as _uuid

    now = "2026-01-01T00:00:00.000Z"
    async with engine.begin() as conn:
        existing = (await conn.execute(
            text("SELECT COUNT(*) FROM shots WHERE project_id = :p"),
            {"p": pid},
        )).scalar()
        rows = [
            {
                "id": str(_uuid.uuid4()), "project_id": pid,
                "shot_number": 40_000 + k, "title": None,
                "subject": f"bulk {k}", "action": None,
                "environment": None, "framing": None,
                "camera_motion": None, "lens": None, "mood": None,
                "duration_ms": None, "created_at": now, "updated_at": now,
            }
            for k in range(SCALE_TOTAL_SHOTS - existing)
        ]
        await conn.execute(
            text(
                "INSERT INTO shots (id, project_id, shot_number, title, "
                "subject, action, environment, framing, camera_motion, "
                "lens, mood, duration_ms, created_at, updated_at) "
                "VALUES (:id, :project_id, :shot_number, :title, "
                ":subject, :action, :environment, :framing, "
                ":camera_motion, :lens, :mood, :duration_ms, "
                ":created_at, :updated_at)"
            ),
            rows,
        )
        for k in range(SCALE_BULK_OPTIONAL_FACETS):
            await conn.execute(
                text(
                    "INSERT INTO visual_facets (id, project_id, "
                    "target_kind, entity_id, feature_id, facet_key, "
                    "label, description, requirement, created_at, "
                    "updated_at) VALUES (:id, :pid, 'entity', :eid, "
                    "NULL, :key, NULL, NULL, 'optional', :now, :now)"
                ),
                {
                    "id": f"f9000000-0000-4000-8000-{k:012d}",
                    "pid": pid, "eid": eva["id"],
                    "key": f"gen{k:03d}", "now": now,
                },
            )
        bad = (await conn.execute(
            text(
                "SELECT COUNT(*) FROM visual_facets vf LEFT JOIN "
                "creative_entities ce ON ce.id = vf.entity_id "
                "WHERE vf.entity_id IS NOT NULL AND ce.project_id != :p"
            ),
            {"p": pid},
        )).scalar()
        total = (await conn.execute(
            text("SELECT COUNT(*) FROM shots WHERE project_id = :p"),
            {"p": pid},
        )).scalar()
    assert bad == 0
    assert total == SCALE_TOTAL_SHOTS

    # --- Same target family at representative scale: one Generation. ---
    big, gid_big = await _count_generation_statements(client, shot_b)
    assert big == small, (small, big)

    # Same persisted realization-input row count (deterministic compile).
    async with engine.connect() as conn:
        input_rows_big = (await conn.execute(
            text("SELECT COUNT(*) FROM generation_inputs "
                 "WHERE generation_id = :g"),
            {"g": gid_big},
        )).scalar()
    assert input_rows_big == input_rows_small

    # And both Generations carry the full multi-channel realization.
    async with engine.connect() as conn:
        for gid in (gid_small, gid_big):
            spec = json.loads((await conn.execute(
                text("SELECT workflow_spec_json FROM generations "
                     "WHERE id = :g"),
                {"g": gid},
            )).scalar())
            assert spec["schema_version"] == 2
            channels = {c["channel"] for c in spec["realization"]["channels"]}
            assert channels == {"hero", "detail", "shared"}
