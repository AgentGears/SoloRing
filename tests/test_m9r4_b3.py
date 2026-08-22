"""M9 r4 — B3 inspection-consistency + B6 remaining race/scale proofs.

B3: on a blocked compile the selected facet's channel usage stays
consistent (used_items > 0, active true); selected_items carry
binding_position; a channel-minimum-blocked required facet keeps its
channel/input_key.

B6: the remaining three §61 race classes in genuine concurrent-task
Event/barrier form (package switch complete-BEFORE preview; rerun vs
profile replacement; worker vs installed-package replacement), and the
INTEGRATED representative fixture — the full target-dimension state
inside the ~2,500-Shot film-scale database with the statement-count
gate on that exact production path.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

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
from tests.test_m9r3_target import _target_package, _target_state


# --- B3 consistency ---------------------------------------------------------------


async def _blocked_two_facet_state(client, factory, engine, settings, pid):
    eva, rev1 = await _entity_with_revision(client, factory, pid)
    assets = await _assets(engine, pid, 1)
    f_identity = await _facet(
        client, pid, "entity", entity_id=eva["id"], facet_key="identity",
    )
    r = await client.post(
        f"/visual-facets/{f_identity['id']}/anchors",
        json={"entity_revision_id": rev1},
    )
    await _approve_anchor(client, r.json()["id"], assets, ["front"])
    f_face = await _facet(
        client, pid, "entity", entity_id=eva["id"], facet_key="face",
        requirement="required",
    )
    anchor = await client.post(
        f"/visual-facets/{f_face['id']}/anchors",
        json={"entity_revision_id": rev1},
    )
    await _approve_anchor(client, anchor.json()["id"], assets, ["front"])
    seq, scene, shots = await _topology(client, factory, pid)
    await _depend(client, shots[0], [eva["id"]])
    return shots[0]


async def test_blocked_readiness_channel_usage_consistent(
    client, factory, engine, settings,
):
    """The r3 inconsistency: identity selected but hero used_items=0 /
    active=false. Usage now derives from the inspection projection."""
    settings.executor = "comfy"
    pid = await _seed_project(factory)
    shot = await _blocked_two_facet_state(
        client, factory, engine, settings, pid
    )

    resp = await client.get(f"/shots/{shot}/realization-readiness")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is False  # face has no rule
    by_key = {s["facet_key"]: s for s in body["facet_statuses"]}
    assert by_key["identity"]["status"] == "selected"
    assert by_key["identity"]["channel"] == "hero_reference"

    hero = next(c for c in body["channels"] if c["channel"] == "hero_reference")
    assert hero["used_items"] == 1
    assert hero["active"] is True

    # §34: selected rows carry binding_position.
    assert by_key["identity"]["selected_items"][0]["binding_position"] == 0


def test_channel_minimum_blocked_required_keeps_channel():
    """A required facet blocked ONLY by REALIZATION_CHANNEL_MINIMUM_UNMET
    keeps its channel and input_key in the inspection projection."""
    from soloring.realization.authority import (
        CapturedFacet,
        CapturedItem,
        CapturedVisualAuthority,
    )
    from soloring.realization.compiler import compile_realization
    from soloring.realization.profile import parse_profile
    from soloring.workflows.manifest import parse_manifest_v2

    pkg_dir = V4_DIR
    profile_doc = json.loads(
        (pkg_dir / "realization-profile.json").read_text()
    )
    # min_items=2 on the sole channel: identity (1 primary) → required
    # channel below minimum.
    profile_doc["channels"]["hero_reference"]["min_items"] = 2
    profile_doc["channels"]["hero_reference"]["max_items"] = 4
    profile = parse_profile(json.dumps(profile_doc))
    manifest = parse_manifest_v2(
        (pkg_dir / "manifest.json").read_text()
    )

    def item(n, role="primary", position=0):
        return CapturedItem(
            asset_id=f"a{n}", blob_hash=f"{n}" * 64, role=role,
            view_key=None, position=position,
        )

    facet = CapturedFacet(
        visual_facet_id="f1", facet_key="identity", requirement="required",
        target_kind="entity", entity_id="eva", entity_revision_id="rev",
        feature_id=None, feature_value_hash=None, feature_value_json=None,
        visual_context_entity_revision_id=None,
        visual_anchor_id="a-f1", visual_anchor_revision_id="r-f1",
        visual_anchor_snapshot_hash="h" * 64, items=(item(1),),
    )
    authority = CapturedVisualAuthority("a" * 64, (facet,))
    result = compile_realization(
        captured_visual_authority=authority, profile=profile,
        manifest=manifest, profile_hash="p" * 64,
        execution_model_fingerprint_hash="f" * 64,
    )
    assert result.ready is False
    assert result.issues[0]["error_code"] == (
        "REALIZATION_CHANNEL_MINIMUM_UNMET"
    )
    outcome = result.facet_outcomes[0]
    assert outcome.status == "required_blocked"
    assert outcome.issue_code == "REALIZATION_CHANNEL_MINIMUM_UNMET"
    assert outcome.channel == "hero_reference"  # retained (§34)
    assert outcome.input_key == "reference_image"


# --- B6: shared concurrent driver ---------------------------------------------------


class _Race:
    def __init__(self):
        self.competitor_committed = asyncio.Event()


async def _run_reader_vs_competitor(reader, competitor, install_seam):
    """Reader + competitor as CONCURRENT tasks. ``install_seam`` wraps a
    production seam: when the READER task reaches it, the competitor
    task is launched and the reader blocks on competitor_committed (an
    Event barrier) before continuing. No synchronous mutation of reader
    state; both coroutines genuinely interleave on the loop."""
    race = _Race()
    state: dict = {}

    async def competitor_task():
        state["competitor"] = asyncio.current_task()
        await competitor()
        race.competitor_committed.set()

    def wrap(fn):
        async def seam(*args, **kwargs):
            if (
                state.get("competitor") is None
                and asyncio.current_task() is state.get("reader")
            ):
                state["competitor_task"] = asyncio.create_task(
                    competitor_task()
                )
                await race.competitor_committed.wait()
            return await fn(*args, **kwargs)
        return seam

    install_seam(wrap)
    try:
        reader_task = asyncio.create_task(reader())
        state["reader"] = reader_task
        return await reader_task
    finally:
        task = state.get("competitor_task")
        if task is not None:
            await task


def _rewrite_profile(pkg, version):
    profile = json.loads((pkg / "realization-profile.json").read_text())
    profile["profile_version"] = version
    (pkg / "realization-profile.json").write_text(json.dumps(profile))
    descriptor = json.loads((pkg / "workflow-package.json").read_text())
    descriptor["realization_profile_hash"] = hashlib.sha256(
        (pkg / "realization-profile.json").read_bytes()
    ).hexdigest()
    (pkg / "workflow-package.json").write_text(json.dumps(descriptor))


async def test_concurrent_package_switch_after_snapshot_complete_before(
    client, factory, engine, settings, tmp_path,
):
    """§62/§88 Form B as a two-operation Event race: the reader's
    package SNAPSHOT is established (capture_release returned); the
    competitor THEN replaces the installed release; the in-flight
    preview completes on the complete BEFORE identity."""
    import soloring.realization.packages as pkg_mod

    pkg = tmp_path / "pkg_before"
    shutil.copytree(V4_DIR, pkg)
    settings.workflow_package_dir = pkg
    pid = await _seed_project(factory)
    shot = await _blocked_two_facet_state(
        client, factory, engine, settings, pid
    )

    real_capture = pkg_mod.capture_release
    captured = {}

    def install_post(wrap):
        async def composed(package_, manifest_, template_, profile_, fp_):
            release = await real_capture(
                package_, manifest_, template_, profile_, fp_
            )
            captured["release"] = release

            async def noop():
                return None
            await wrap(noop)()
            return release
        pkg_mod.capture_release = composed

    async def reader():
        return await client.get(f"/shots/{shot}/realization-readiness")

    async def competitor():
        _rewrite_profile(pkg, 88)

    try:
        resp = await _run_reader_vs_competitor(
            reader, competitor, install_post
        )
    finally:
        pkg_mod.capture_release = real_capture

    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Complete BEFORE: the preview evaluated the original profile even
    # though the installed release was replaced mid-flight.
    assert body["profile"]["version"] == 1
    assert captured["release"].realization_profile_hash != (
        json.loads((pkg / "workflow-package.json").read_text())[
            "realization_profile_hash"
        ]
    )


async def test_concurrent_rerun_vs_profile_replacement(
    client, factory, engine, settings, tmp_path,
):
    """§61 race 4 as a two-operation Event race at the reader's real
    BEGIN IMMEDIATE: the rerun creation and the profile replacement run
    concurrently; the rerun's durable copy is verbatim BEFORE."""
    pkg = tmp_path / "pkg_rerun"
    shutil.copytree(V4_DIR, pkg)
    settings.workflow_package_dir = pkg
    settings.executor = "comfy"
    pid = await _seed_project(factory)
    eva, rev1 = await _entity_with_revision(client, factory, pid)
    assets = await _assets(engine, pid, 1)
    f = await _facet(
        client, pid, "entity", entity_id=eva["id"], facet_key="identity",
    )
    ar = await client.post(
        f"/visual-facets/{f['id']}/anchors",
        json={"entity_revision_id": rev1},
    )
    await _approve_anchor(client, ar.json()["id"], assets, ["front"])
    seq, scene, shots = await _topology(client, factory, pid)
    await _depend(client, shots[0], [eva["id"]])
    shot = shots[0]
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

    original_exec = AsyncConnection.exec_driver_sql

    def install(wrap):
        async def wrapped_exec(self, statement, *a, **k):
            up = statement.strip().upper() if isinstance(statement, str) \
                else ""
            if up == "BEGIN IMMEDIATE":
                async def noop():
                    return None
                await wrap(noop)()
            return await original_exec(self, statement, *a, **k)
        AsyncConnection.exec_driver_sql = wrapped_exec

    async def reader():
        return await client.post(f"/generations/{source_id}/rerun")

    async def competitor():
        _rewrite_profile(pkg, 77)

    try:
        resp = await _run_reader_vs_competitor(reader, competitor, install)
    finally:
        AsyncConnection.exec_driver_sql = original_exec

    assert resp.status_code == 202, resp.text
    async with engine.connect() as conn:
        copy = (await conn.execute(
            text("SELECT workflow_spec_json, workflow_spec_hash "
                 "FROM generations WHERE id = :g"),
            {"g": resp.json()["id"]},
        )).one()
    assert copy.workflow_spec_json == src.workflow_spec_json
    assert copy.workflow_spec_hash == src.workflow_spec_hash


async def test_concurrent_worker_vs_installed_package_replacement(
    client, factory, engine, settings, tmp_path, monkeypatch,
):
    """§61 race 5 as a two-operation Event race at the worker's real
    historical-artifact read: the worker validation and the installed-
    package replacement run concurrently; the worker proceeds on the
    captured artifact-store bytes."""
    from tests.test_m9d_worker import (
        _RecordingClient,
        _StubCap,
        _claim,
        _m9_generation,
        _write_fixture_attestation,
    )
    import soloring.realization.runtime as runtime_mod
    import soloring.worker.comfy_pipeline as pipeline
    from soloring.workflows.artifact_store import WorkflowArtifactStore

    gid, pkg, _roots = await _m9_generation(
        client, factory, engine, settings, tmp_path
    )
    await _claim(engine, gid)

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

    real_get_profile = WorkflowArtifactStore.get_profile

    def install(wrap):
        async def wrapped_get_profile(self, h):
            await wrap(lambda: _noop())()
            return await real_get_profile(self, h)
        monkeypatch.setattr(
            WorkflowArtifactStore, "get_profile", wrapped_get_profile
        )

    async def _noop():
        return None

    async def reader():
        stub = _RecordingClient()
        await pipeline.drive_comfy_generation(
            engine, settings, "w-m9d", gid, "attempt-race5b", stub,
            materializer=_Materializer(),
        )
        return stub

    async def competitor():
        _rewrite_profile(pkg, 55)

    try:
        stub = await _run_reader_vs_competitor(reader, competitor, install)
    finally:
        monkeypatch.setattr(
            WorkflowArtifactStore, "get_profile", real_get_profile
        )

    assert reached["materialize"] is True  # historical bytes unaffected


# --- B6: integrated representative fixture -------------------------------------------


async def test_integrated_target_dimension_at_film_scale(
    client, factory, engine, settings, tmp_path,
):
    """§60 INTEGRATED: the full target-dimension state (characters +
    locations, feature-value facets, multi-channel + shared-channel,
    multi-view packs) inside the ~2,500-Shot representative database;
    the statement-count gate runs on THAT exact production path and must
    be cardinality-independent."""
    from sqlalchemy import event
    from sqlalchemy.engine import Engine as SyncEngine

    pkg = _target_package(tmp_path)
    settings.workflow_package_dir = pkg
    pid = await _seed_project(factory)
    shot, eva, lobby = await _target_state(
        client, factory, engine, settings, pid
    )

    async def count_statements(shot_id):
        n = {"count": 0}

        def before(conn, cursor, statement, params, ctx, many):
            n["count"] += 1

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
    now = "2026-01-01T00:00:00.000Z"
    import uuid as _uuid

    async with engine.begin() as conn:
        existing = (await conn.execute(
            text("SELECT COUNT(*) FROM shots WHERE project_id = :p"),
            {"p": pid},
        )).scalar()
        rows = [
            {
                "id": str(_uuid.uuid4()), "project_id": pid,
                "shot_number": 20_000 + k, "title": None,
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
        for k in range(60):
            await conn.execute(
                text(
                    "INSERT INTO visual_facets (id, project_id, "
                    "target_kind, entity_id, feature_id, facet_key, "
                    "label, description, requirement, created_at, "
                    "updated_at) VALUES (:id, :pid, 'entity', :eid, "
                    "NULL, :key, NULL, NULL, 'optional', :now, :now)"
                ),
                {
                    "id": f"d9000000-0000-4000-8000-{k:012d}",
                    "pid": pid, "eid": eva["id"],
                    "key": f"film{k:03d}", "now": now,
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

    big = await count_statements(shot)
    assert big == small, (small, big)
