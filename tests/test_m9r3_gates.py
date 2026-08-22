"""M9 r3 — remaining gate proofs (B5/B6 closure).

Event/barrier two-operation races (no sleeps; both tasks genuinely
concurrent, fired at real seams); the dynamic mutation spy over preview
+ creation + worker + rerun with a forbidden-write POSITIVE CONTROL; the
§60 designated target-dimension fixture (recurring characters +
locations, feature-value facets, multi-channel + shared-channel
selectors, capacity matrix, all omission reasons, multi-view packs);
and the B5 regressions (schema-2 generation detail projection, blocked
readiness keeping supported facets selected).
"""

from __future__ import annotations

import asyncio
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


# --- B5 regressions ---------------------------------------------------------------


async def test_schema2_generation_detail_projection(
    client, factory, engine, settings,
):
    """The r2 NameError (undefined `generation` in _project_m9) made every
    schema-2 Generation detail response a 500; the projection now serves
    captured identities + final parameters."""
    settings.executor = "comfy"
    pid = await _seed_project(factory)
    shot, _eva, _rev1, _assets = await _m9_state(
        client, factory, engine, settings, pid
    )
    r = await client.post(f"/shots/{shot}/generations")
    assert r.status_code == 202, r.text
    gid = r.json()["id"]
    detail = (await client.get(f"/generations/{gid}")).json()
    assert detail["model"] == "hunyuan-video-i2v"
    assert detail["workflow_spec_schema_version"] == 2
    assert detail["manifest_hash"]
    assert detail["workflow_template_hash"]
    assert detail["realization_profile_hash"]
    assert detail["visual_reference_pack_hash"]
    assert detail["final_parameters"] == {"steps": 30, "cfg": 1.0}
    assert detail["realization_summary"]["channels"][0]["channel"] == (
        "hero_reference"
    )


async def test_blocked_readiness_keeps_supported_facets_selected(
    client, factory, engine, settings,
):
    """B3 core: with identity supported and face unsupported, the blocked
    response must keep identity `selected` — never corrupt it to
    required_blocked."""
    settings.executor = "comfy"
    pid = await _seed_project(factory)
    shot, eva, rev1, assets = await _m9_state(
        client, factory, engine, settings, pid
    )
    f2 = await _facet(
        client, pid, "entity", entity_id=eva["id"], facet_key="face",
        requirement="required",
    )
    anchor = await client.post(
        f"/visual-facets/{f2['id']}/anchors",
        json={"entity_revision_id": rev1},
    )
    await _approve_anchor(client, anchor.json()["id"], assets, ["front"])

    resp = await client.get(f"/shots/{shot}/realization-readiness")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is False
    by_key = {s["facet_key"]: s for s in body["facet_statuses"]}
    assert by_key["identity"]["status"] == "selected"
    assert by_key["identity"]["selected_items"]
    assert by_key["face"]["status"] == "required_blocked"
    assert by_key["face"]["issue_code"] == (
        "REALIZATION_REQUIRED_FACET_UNSUPPORTED"
    )
    # Environment + parameters surfaces ride along.
    assert body["environment"] is not None
    assert body["parameters"]["final"]["steps"] == 30


# --- B6: mutation spy with worker + positive control -------------------------------


async def test_mutation_spy_covers_worker_and_has_positive_control(
    client, factory, engine, settings, tmp_path, monkeypatch,
):
    """§73.2 over preview + creation + WORKER execution + rerun, plus the
    REQUIRED positive control: a deliberate forbidden write under the
    spy must be caught (proving the spy itself is not vacuous)."""
    from sqlalchemy import event
    from sqlalchemy.engine import Engine as SyncEngine

    from tests.test_m9d_worker import (
        _RecordingClient,
        _StubCap,
        _claim,
        _m9_generation,
        _write_fixture_attestation,
    )

    gid, _pkg, _roots = await _m9_generation(
        client, factory, engine, settings, tmp_path
    )
    async with engine.connect() as conn:
        shot = (await conn.execute(
            text("SELECT shot_id FROM generations WHERE id = :g"),
            {"g": gid},
        )).scalar()

    import soloring.realization.runtime as runtime_mod
    import soloring.worker.comfy_pipeline as pipeline

    async def _cap(*a, **k):
        return _StubCap()

    monkeypatch.setattr(pipeline, "resolve_capability", _cap)
    _write_fixture_attestation(settings)

    def _alive(att, st):
        return None

    monkeypatch.setattr(runtime_mod, "verify_attested_process_live", _alive)

    violations: list[str] = []
    table_tokens = (
        "visual_facets", "visual_facet_value_policies", "visual_anchors",
        "visual_anchor_items", "visual_anchor_revisions",
        "visual_anchor_revision_items",
    )
    import re

    patterns = [re.compile(t + r"\b", re.IGNORECASE) for t in table_tokens]
    write_verb = re.compile(
        r"\A\s*(INSERT\s+INTO|UPDATE|DELETE\s+FROM)", re.IGNORECASE
    )

    def before(conn, cursor, statement, params, ctx, many):
        if not write_verb.match(statement or ""):
            return
        up = (statement or "").upper()
        if any(p.search(up) for p in patterns):
            violations.append((statement or "")[:120])

    event.listen(SyncEngine, "before_cursor_execute", before)
    try:
        # Positive control FIRST: a deliberate forbidden write must be
        # caught by this exact spy.
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE visual_facets SET label = label WHERE 1=0")
            )
        assert len(violations) == 1, violations
        violations.clear()

        r = await client.get(f"/shots/{shot}/realization-readiness")
        assert r.status_code == 200, r.text
        # Terminalize the fixture generation so the claim below picks the
        # NEW one (claims take the oldest queued).
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE generations SET status = 'succeeded', "
                    "started_at = '2026-01-01T00:00:00Z', "
                    "completed_at = '2026-01-01T00:00:01Z' WHERE id = :g"
                ),
                {"g": gid},
            )
        r = await client.post(f"/shots/{shot}/generations")
        assert r.status_code == 202, r.text
        # Worker execution attempt (fails at the stub client AFTER the
        # §26 gates — mutations would surface here if any existed).
        await _claim(engine, r.json()["id"])
        stub = _RecordingClient()
        await pipeline.drive_comfy_generation(
            engine, settings, "w-m9d", r.json()["id"], "attempt-spy", stub,
        )
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE generations SET status = 'succeeded', "
                    "started_at = '2026-01-01T00:00:00Z', "
                    "completed_at = '2026-01-01T00:00:01Z' WHERE id = :g"
                ),
                {"g": r.json()["id"]},
            )
        rr = await client.post(f"/generations/{r.json()['id']}/rerun")
        assert rr.status_code == 202, rr.text
    finally:
        event.remove(SyncEngine, "before_cursor_execute", before)

    assert violations == [], violations


# --- B6: two-operation Event/barrier races ------------------------------------------


class _Ev:
    def __init__(self):
        self.competitor_started = asyncio.Event()
        self.competitor_committed = asyncio.Event()


async def _drive_with_competitor(reader, competitor, seam_wrap):
    """Run reader + competitor as GENUINELY CONCURRENT tasks. The seam
    wrapper (installed around a production seam) launches the competitor
    task and blocks the reader on competitor_committed — a barrier, not
    a sequential mutation. Events fire at the competitor's real BEGIN
    IMMEDIATE (where it writes) and at commit."""
    ev = _Ev()
    original_exec = AsyncConnection.exec_driver_sql
    state: dict = {}

    async def competitor_exec(self, statement, *a, **k):
        task = asyncio.current_task()
        up = statement.strip().upper() if isinstance(statement, str) else ""
        if (
            state.get("competitor") is not None
            and task is state["competitor"]
            and up == "BEGIN IMMEDIATE"
        ):
            ev.competitor_started.set()
        if (
            state.get("competitor") is not None
            and task is state["competitor"]
            and up == "COMMIT"
        ):
            result = await original_exec(self, statement, *a, **k)
            ev.competitor_committed.set()
            return result
        return await original_exec(self, statement, *a, **k)

    def wrap(seam_args):
        async def run_competitor():
            state["competitor"] = asyncio.current_task()
            await competitor()
            if not ev.competitor_committed.is_set():
                ev.competitor_committed.set()

        task = asyncio.create_task(run_competitor())
        return task

    seam_wrap.wrap = wrap
    seam_wrap.ev = ev

    AsyncConnection.exec_driver_sql = competitor_exec
    try:
        reader_task = asyncio.create_task(reader())
        result = await reader_task
        return result
    finally:
        AsyncConnection.exec_driver_sql = original_exec


async def test_concurrent_race_preview_vs_profile_replacement(
    client, factory, engine, settings, tmp_path,
):
    """Two-operation concurrency: the readiness reader and a profile-
    replacing competitor run as CONCURRENT tasks; the barrier fires at
    the capture seam (the reader blocks while the competitor's writes
    commit). The preview then evaluates the complete AFTER release —
    never a mixed artifact set."""
    import hashlib

    import soloring.realization.packages as pkg_mod

    pkg = _pkg_copy(tmp_path)
    settings.workflow_package_dir = pkg
    pid = await _seed_project(factory)
    shot, _eva, _rev1, _assets = await _m9_state(
        client, factory, engine, settings, pid
    )

    real_capture = pkg_mod.capture_release
    state = {"fired": False}

    class Seam:
        pass

    seam = Seam()

    async def racing_capture(package, manifest, template, profile, fp):
        if not state["fired"]:
            state["fired"] = True
            seam.wrap(None)
            await seam.ev.competitor_committed.wait()
        return await real_capture(package, manifest, template, profile, fp)

    async def competitor():
        profile = json.loads((pkg / "realization-profile.json").read_text())
        profile["profile_version"] = 42
        (pkg / "realization-profile.json").write_text(json.dumps(profile))
        descriptor = json.loads((pkg / "workflow-package.json").read_text())
        descriptor["realization_profile_hash"] = hashlib.sha256(
            (pkg / "realization-profile.json").read_bytes()
        ).hexdigest()
        (pkg / "workflow-package.json").write_text(json.dumps(descriptor))

    async def reader():
        return await client.get(f"/shots/{shot}/realization-readiness")

    original = pkg_mod.capture_release
    pkg_mod.capture_release = racing_capture
    try:
        resp = await _drive_with_competitor(reader, competitor, seam)
    finally:
        pkg_mod.capture_release = original

    # The competitor fully committed BEFORE the reader's capture read any
    # bytes → the preview evaluates the complete AFTER release.
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ready"] is True
    assert body["profile"]["version"] == 42


async def test_concurrent_race_creation_vs_m8_unapproval(
    client, factory, engine, settings,
):
    """Two-operation concurrency: the creation reader and an M8-
    unapproving competitor (real BEGIN IMMEDIATE writes) run as
    concurrent tasks; the barrier fires at the reconstruction seam. The
    Generation realizes the CAPTURED authority; the competitor's commit
    lands mid-creation without hybridizing anything."""
    settings.executor = "comfy"
    pid = await _seed_project(factory)
    shot, _eva, rev1, _assets = await _m9_state(
        client, factory, engine, settings, pid
    )

    import soloring.generation.service as service_mod
    from soloring.realization import authority as authority_mod

    real_reconstruct = authority_mod.reconstruct_authority
    state = {"fired": False}

    class Seam:
        pass

    seam = Seam()

    async def racing_reconstruct(conn, revision_id, requirements):
        if not state["fired"]:
            state["fired"] = True
            seam.wrap(None)
            await seam.ev.competitor_committed.wait()
        return await real_reconstruct(conn, revision_id, requirements)

    async def competitor():
        async with engine.connect() as conn:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await conn.execute(
                text(
                    "UPDATE visual_anchors SET approved_revision_id = NULL "
                    "WHERE entity_revision_id = :r"
                ),
                {"r": rev1},
            )
            await conn.exec_driver_sql("COMMIT")

    async def reader():
        return await client.post(f"/shots/{shot}/generations")

    original = authority_mod.reconstruct_authority
    # service imports reconstruct_authorization inside the function from
    # the authority module — patch at the module source.
    authority_mod.reconstruct_authority = racing_reconstruct
    try:
        resp = await _drive_with_competitor(reader, competitor, seam)
    finally:
        authority_mod.reconstruct_authority = original

    assert resp.status_code == 202, resp.text
    async with engine.connect() as conn:
        spec = json.loads((await conn.execute(
            text("SELECT workflow_spec_json FROM generations "
                 "WHERE id = :g"),
            {"g": resp.json()["id"]},
        )).scalar())
    assert spec["schema_version"] == 2
    assert len(spec["realization"]["channels"][0]["bindings"]) == 1
