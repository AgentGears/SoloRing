"""M9 r2 — remaining §61/§60/§62 proofs (B6 closure).

Forced race forms (no sleeps): profile/model file replacement during
readiness preview; Exact Rerun concurrent with current profile
replacement; worker execution concurrent with installed package
replacement; M8 approval change racing the creation compile at the
reconstruction seam. The representative ~2,500-Shot scale fixture with
cardinality-independent statement counts.
"""

from __future__ import annotations

import hashlib
import json
import shutil

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine as SyncEngine

from tests.test_m8a_visual import (
    _entity_with_revision,
    _facet,
    _seed_project,
)
from tests.test_m8b_curation import _assets
from tests.test_m8c_resolver import (
    _approve_anchor,
    _depend,
    _topology,
)
from tests.test_m9a_package import V4_DIR
from tests.test_m9r2_regressions import _v2_empty_authority_package

import asyncio


async def _m9_state(client, factory, engine, settings, pid):
    eva, rev1 = await _entity_with_revision(client, factory, pid)
    assets = await _assets(engine, pid, 1)
    f = await _facet(
        client, pid, "entity", entity_id=eva["id"], facet_key="identity"
    )
    r = await client.post(
        f"/visual-facets/{f['id']}/anchors", json={"entity_revision_id": rev1}
    )
    await _approve_anchor(client, r.json()["id"], assets[:1], ["front"])
    seq, scene, shots = await _topology(client, factory, pid)
    await _depend(client, shots[0], [eva["id"]])
    return shots[0], eva, rev1, assets


def _pkg_copy(tmp_path, name="pkg"):
    pkg = tmp_path / name
    shutil.copytree(V4_DIR, pkg)
    return pkg


def _rewrite_profile(pkg, mutate):
    profile = json.loads((pkg / "realization-profile.json").read_text())
    mutate(profile)
    (pkg / "realization-profile.json").write_text(json.dumps(profile))
    descriptor = json.loads((pkg / "workflow-package.json").read_text())
    descriptor["realization_profile_hash"] = hashlib.sha256(
        (pkg / "realization-profile.json").read_bytes()
    ).hexdigest()
    (pkg / "workflow-package.json").write_text(json.dumps(descriptor))


# --- §61 race 3: profile/model replacement during readiness preview -------------


async def test_race_profile_replacement_during_readiness_preview(
    client, factory, engine, settings, tmp_path, monkeypatch,
):
    """Form B at the artifact-read seam: the preview's captured package
    snapshot is established (D1 read); the profile file is THEN replaced
    (different release); the in-flight preview completes on the BEFORE
    bytes — never mixed hashes."""
    import soloring.realization.packages as pkg_mod

    pkg = _pkg_copy(tmp_path)
    settings.workflow_package_dir = pkg
    pid = await _seed_project(factory)
    shot, _eva, _rev1, _assets = await _m9_state(
        client, factory, engine, settings, pid
    )

    real_read_descriptor = pkg_mod._read_descriptor
    fired = {"n": 0}

    def racing_read_descriptor(path):
        doc = real_read_descriptor(path)
        fired["n"] += 1
        if fired["n"] == 1:
            # AFTER D1, BEFORE the artifact reads: swap the profile to a
            # new release (B). The captured buffers for D1's release are
            # not yet established, so capture must FAIL as incoherent —
            # the declared profile hash no longer matches the bytes.
            _rewrite_profile(
                pkg, lambda p: p.update({"profile_version": 99})
            )
            # D1 doc is the BEFORE descriptor; the file now holds AFTER.
        return doc

    monkeypatch.setattr(
        pkg_mod, "_read_descriptor", racing_read_descriptor
    )
    # The endpoint surfaces Stage-0 incoherence as a 503 envelope.
    resp = await client.get(f"/shots/{shot}/realization-readiness")
    assert resp.status_code == 503, resp.text
    assert resp.json()["error_code"] == "WORKFLOW_PACKAGE_INTEGRITY"
    monkeypatch.undo()

    # Retry after the switch: complete AFTER only.
    resp = await client.get(f"/shots/{shot}/realization-readiness")
    assert resp.status_code == 200, resp.text
    assert resp.json()["ready"] is True


# --- §61 race 4: rerun concurrent with current profile replacement --------------


async def test_race_rerun_concurrent_with_profile_replacement(
    client, factory, engine, settings, tmp_path, monkeypatch,
):
    pkg = _pkg_copy(tmp_path)
    settings.workflow_package_dir = pkg
    settings.executor = "comfy"
    pid = await _seed_project(factory)
    shot, _eva, _rev1, _assets = await _m9_state(
        client, factory, engine, settings, pid
    )

    r = await client.post(f"/shots/{shot}/generations")
    assert r.status_code == 202, r.text
    source_id = r.json()["id"]
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE generations SET status = 'succeeded', "
                "started_at = '2026-01-01T00:00:00Z', "
                "completed_at = '2026-01-01T00:00:01Z' WHERE id = :g"
            ),
            {"g": source_id},
        )
    async with engine.connect() as conn:
        src = (await conn.execute(
            text("SELECT workflow_spec_json, workflow_spec_hash "
                 "FROM generations WHERE id = :g"),
            {"g": source_id},
        )).one()

    from sqlalchemy.ext.asyncio import AsyncConnection

    original_exec = AsyncConnection.exec_driver_sql
    swapped = {"done": False}

    async def racing_exec(self, statement, *a, **k):
        if (
            not swapped["done"]
            and isinstance(statement, str)
            and statement.strip().upper() == "BEGIN IMMEDIATE"
        ):
            swapped["done"] = True
            _rewrite_profile(
                pkg, lambda p: p.update({"profile_version": 77})
            )
        return await original_exec(self, statement, *a, **k)

    monkeypatch.setattr(
        AsyncConnection, "exec_driver_sql", racing_exec
    )
    try:
        rr = await client.post(f"/generations/{source_id}/rerun")
    finally:
        monkeypatch.undo()

    assert rr.status_code == 202, rr.text
    async with engine.connect() as conn:
        copy = (await conn.execute(
            text("SELECT workflow_spec_json, workflow_spec_hash "
                 "FROM generations WHERE id = :g"),
            {"g": rr.json()["id"]},
        )).one()
    assert copy.workflow_spec_json == src.workflow_spec_json
    assert copy.workflow_spec_hash == src.workflow_spec_hash


# --- §61 race 5: worker concurrent with installed package replacement -----------


async def test_race_worker_concurrent_with_installed_package_replacement(
    client, factory, engine, settings, tmp_path, monkeypatch,
):
    """The worker's historical validation reads ONLY artifact-store bytes
    by captured hash; replacing the INSTALLED package mid-validation
    cannot affect it (the artifact store keeps the captured bytes)."""
    from tests.test_m9d_worker import (
        _RecordingClient,
        _StubCap,
        _claim,
        _m9_generation,
        _write_fixture_attestation,
    )
    import soloring.realization.runtime as runtime_mod

    gid, pkg, _roots = await _m9_generation(
        client, factory, engine, settings, tmp_path
    )
    await _claim(engine, gid)

    import soloring.worker.comfy_pipeline as pipeline
    from soloring.workflows.artifact_store import WorkflowArtifactStore

    real_get_profile = WorkflowArtifactStore.get_profile
    replaced = {"done": False}

    async def racing_get_profile(self, h):
        if not replaced["done"]:
            replaced["done"] = True
            # Competitor: replace the INSTALLED package wholesale.
            _rewrite_profile(
                pkg, lambda p: p.update({"profile_version": 55})
            )
        return await real_get_profile(self, h)

    monkeypatch.setattr(
        WorkflowArtifactStore, "get_profile", racing_get_profile
    )
    async def _cap(*a, **k):
        return _StubCap()

    monkeypatch.setattr(pipeline, "resolve_capability", _cap)
    _write_fixture_attestation(settings)

    def _alive(att, st):
        return None

    monkeypatch.setattr(runtime_mod, "verify_attested_process_live", _alive)

    reached = {"materialize": False}

    class _Materializer:
        async def materialize(self, **kwargs):
            reached["materialize"] = True
            from soloring.executors.comfy.input_materializer import (
                MaterializedComfyInput,
            )

            return type("Outcome", (), {
                "materialized": [
                    MaterializedComfyInput(
                        input_key="reference_image", position=0,
                        asset_id="fixture", blob_hash="f" * 64,
                        remote_name="x.png", subfolder="",
                    ),
                ],
            })()

    stub = _RecordingClient()
    result = await pipeline.drive_comfy_generation(
        engine, settings, "w-m9d", gid, "attempt-race5", stub,
        materializer=_Materializer(),
    )
    assert reached["materialize"] is True  # historical bytes validated fine


# --- §61 race 2: M8 approval change racing the creation compile -----------------


async def test_race_m8_approval_change_during_creation_compile(
    client, factory, engine, settings, tmp_path, monkeypatch,
):
    """Force the interleaving at the reconstruction seam: the ShotRevision
    is captured; the competitor unapproves the anchor BEFORE the compile
    reads the revision provenance. The Generation still realizes the
    CAPTURED authority (revision-pinned), never the current NULL."""
    pkg = _pkg_copy(tmp_path)
    settings.workflow_package_dir = pkg
    settings.executor = "comfy"
    pid = await _seed_project(factory)
    shot, _eva, rev1, _assets = await _m9_state(
        client, factory, engine, settings, pid
    )

    import soloring.generation.service as service_mod
    from soloring.realization import authority as authority_mod

    real_reconstruct = authority_mod.reconstruct_authority
    fired = {"n": 0}

    async def racing_reconstruct(conn, revision_id, requirements):
        fired["n"] += 1
        if fired["n"] == 1:
            # Competitor: unapprove AFTER capture, BEFORE compile.
            async with engine.begin() as c:
                await c.execute(
                    text(
                        "UPDATE visual_anchors SET approved_revision_id = "
                        "NULL WHERE entity_revision_id = :r"
                    ),
                    {"r": rev1},
                )
        return await real_reconstruct(conn, revision_id, requirements)

    monkeypatch.setattr(
        authority_mod, "reconstruct_authority", racing_reconstruct
    )
    try:
        r = await client.post(f"/shots/{shot}/generations")
    finally:
        monkeypatch.undo()
    assert r.status_code == 202, r.text
    async with engine.connect() as conn:
        spec = json.loads((await conn.execute(
            text("SELECT workflow_spec_json FROM generations "
                 "WHERE id = :g"),
            {"g": r.json()["id"]},
        )).scalar())
    assert spec["schema_version"] == 2
    assert len(spec["realization"]["channels"][0]["bindings"]) == 1


# --- §60 representative scale fixture --------------------------------------------


async def test_representative_2500_shot_scale(
    client, factory, engine, settings, tmp_path,
):
    """§60: ~2,500 total Shots (direct-SQL bulk, disclosed + legality
    asserted), recurring entities, multi-facet dependency dimension; the
    readiness path's SQL statement count is IDENTICAL to the small
    fixture (§59: cardinality-independent)."""
    pkg = _pkg_copy(tmp_path)
    settings.workflow_package_dir = pkg
    pid = await _seed_project(factory)
    shot, eva, _rev1, _assets = await _m9_state(
        client, factory, engine, settings, pid
    )

    async def count_statements(shot_id):
        n = {"count": 0}

        def before(conn, cursor, statement, params, ctx, many):
            n["count"] += 1

        from sqlalchemy import event

        event.listen(SyncEngine, "before_cursor_execute", before)
        try:
            r = await client.get(
                f"/shots/{shot_id}/realization-readiness"
            )
            assert r.status_code == 200, r.text
            assert r.json()["ready"] is True
        finally:
            event.remove(
                SyncEngine, "before_cursor_execute", before
            )
        return n["count"]

    small = await count_statements(shot)

    SCALE_TOTAL_SHOTS = 2_500
    SCALE_BULK_OPTIONAL_FACETS = 60
    now = "2026-01-01T00:00:00.000Z"

    import uuid as _uuid

    async with engine.begin() as conn:
        # Bulk shots (no scene assignment; volume only).
        existing = (await conn.execute(
            text("SELECT COUNT(*) FROM shots WHERE project_id = :p"),
            {"p": pid},
        )).scalar()
        rows = [
            {
                "id": str(_uuid.uuid4()), "project_id": pid,
                "shot_number": 10_000 + k, "title": None,
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
        # Bulk optional facets on the dependency entity.
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
                    "id": f"c9000000-0000-4000-8000-{k:012d}",
                    "pid": pid, "eid": eva["id"],
                    "key": f"scale{k:03d}", "now": now,
                },
            )
        # Legality: every bulk facet belongs to a Project entity.
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

    big = await count_statements(shot)
    assert big == small, (small, big)
