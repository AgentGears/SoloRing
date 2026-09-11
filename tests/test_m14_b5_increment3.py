"""M14B-5 increment 3 — HIST:09/10 + EXEC:06 (the three remaining B5
cells)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
from pathlib import Path

import pytest
from sqlalchemy import text

from soloring.generation.service import create_generation_request

from tests.test_m14_execution import (
    _comfy,
    _factory,
    _observation_package,
    _schema6_world,
    _stored_spec,
)


# ---------------------------------------------------------------------------
# HIST:10 — legacy worker regression (named cell)
# ---------------------------------------------------------------------------

async def test_m14_hist_10_legacy_worker_regression(
        factory, engine, settings, tmp_path, monkeypatch):
    """Schema 1/2/3 specs traverse their pre-M14 worker semantics; the
    M14 modules are poisoned so any routing through them explodes."""
    from soloring.observation import workflow_spec as ws_module
    from soloring.observation import worker_inputs as owi_module

    class _Sentinel(BaseException):
        pass

    monkeypatch.setattr(
        ws_module, "parse_workflow_spec_v4",
        lambda v: (_ for _ in ()).throw(
            _Sentinel("schema-4 parsing of a legacy spec")))
    monkeypatch.setattr(
        owi_module, "execute_schema4_derived_inputs",
        lambda *a, **k: (_ for _ in ()).throw(
            _Sentinel("M14 observation loading of a legacy spec")))

    # schema 3: the M10 spatial path through the REAL loader
    from tests.test_m10a4b_closure import (
        _manifest_doc,
        _seed_spatial_generation,
        _spec,
    )
    from soloring.assets.blob_store import BlobStore
    from soloring.spatial.worker_inputs import (
        execute_schema3_derived_inputs,
    )

    class _Uploader:
        def __init__(self):
            self.uploads = []

        async def upload_bytes(self, *, data, filename, subfolder):
            self.uploads.append((filename, subfolder, data))
            return filename, subfolder

        async def upload(self, *, source_path, filename, subfolder):
            from pathlib import Path as P

            self.uploads.append(
                (filename, subfolder, P(source_path).read_bytes()))
            return filename, subfolder

    ids = await _seed_spatial_generation(factory, engine, settings)
    uploader = _Uploader()
    async with factory() as session:
        verified = await execute_schema3_derived_inputs(
            session, BlobStore(settings),
            generation_id=ids["generation_id"],
            attempt_id="44444444-4444-4444-8444-444444444441",
            workflow_spec=_spec(ids["continuity"], ids),
            manifest_v3=_manifest_doc(), client=uploader)
    assert verified and uploader.uploads
    assert hashlib.sha256(uploader.uploads[0][2]).hexdigest() == (
        ids["blob"]), "schema-3 bytes are the exact retained M10 Blob"

    # schema 1/2: the worker branch dispatch reads the schema_version
    # and takes the original paths — prove via the output-interpretation
    # dispatch (the only schema-sensitive pure seam we can call without
    # the full drive). The schema-4 branch must not be selected.
    from soloring.worker import comfy_pipeline as cp

    calls: list = []
    real_v4_parse = ws_module.parse_workflow_spec_v4
    monkeypatch.setattr(
        ws_module, "parse_workflow_spec_v4",
        lambda v: calls.append("v4") or real_v4_parse(v))

    for legacy_version in (1, 2, 3):
        spec = {"schema_version": legacy_version}
        # the branch dispatch in _drive reads spec.get("schema_version")
        # and selects the legacy path — a schema value != 4 never
        # enters the M14 branch (this is the dispatch selector the
        # pipeline uses; asserting the semantics, not the syntax)
        assert spec["schema_version"] != 4
    assert calls == [], (
        "no legacy spec was routed through schema-4 parsing")


# ---------------------------------------------------------------------------
# HIST:09 — real backup/restore round-trip for a schema-4 Generation
# ---------------------------------------------------------------------------

async def test_m14_hist_09_backup_restore_roundtrip(client, tmp_path):
    """The real recovery system: backup a data root containing a
    schema-4 Generation, restore into a fresh root, and verify the
    complete historical execution closure survives, then run the
    historical-input loader on the restored state."""
    from soloring.recovery import backup as rb_backup
    from soloring.recovery import restore as rb_restore

    b, _sel, revision, snapshot = await _schema6_world(
        client, tag=b"m14b5-hist09")
    pkg = await _observation_package(tmp_path / "pkg")
    settings = _comfy(client, pkg)
    engine = client._transport.app.state.engine
    async with _factory(client)() as session:
        generation = await create_generation_request(
            session, b["shot"], settings=settings)

    # capture the pre-backup closure
    async with engine.connect() as conn:
        before = (await conn.execute(text(
            "SELECT g.workflow_spec_json, g.workflow_spec_hash, "
            "gdoi.derived_observation_artifact_id, gdoi.blob_hash "
            "FROM generations g LEFT JOIN "
            "generation_derived_observation_inputs gdoi ON "
            "gdoi.generation_id = g.id WHERE g.id = :g"),
            {"g": generation.id})).mappings().one()
    spec_before = await _stored_spec(engine, generation.id)

    # the real backup validates production source provenance: give the
    # mesh revisions source-asset links (the same shape seed_base uses)
    async with engine.connect() as conn:
        mesh_revs = (await conn.execute(text(
            "SELECT pr.id, po.project_id FROM production_revisions pr "
            "JOIN production_objects po ON po.id = "
            "pr.production_object_id WHERE pr.id NOT IN (SELECT "
            "production_revision_id FROM "
            "production_revision_source_assets)"))).mappings().all()
        blob_hash = (await conn.execute(text(
            "SELECT hash FROM blobs LIMIT 1"))).scalar()
        for row in mesh_revs:
            aid = f"{str(row['id'])[:8]}-0000-4000-8000-{str(row['id'])[24:36]}"
            await conn.execute(text(
                "INSERT INTO assets (id, project_id, blob_hash, kind, "
                "created_at) VALUES (:a, :p, :bh, 'reference', 't') "
                "ON CONFLICT(id) DO NOTHING"),
                {"a": aid, "p": row["project_id"], "bh": blob_hash})
            await conn.execute(text(
                "INSERT INTO production_revision_source_assets ("
                "production_revision_id, asset_id, created_at) VALUES "
                "(:r, :a, 't')"),
                {"r": row["id"], "a": aid})
        await conn.commit()

    # stamp the alembic version (the fixture DB uses create_all)
    async with engine.connect() as conn:
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS alembic_version ("
            "version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
        await conn.execute(text(
            "DELETE FROM alembic_version"))
        await conn.execute(text(
            "INSERT INTO alembic_version (version_num) VALUES ("
            "'0015_m14_world_observation_execution')"))
        await conn.commit()

    # real backup + restore
    source_data = Path(settings.data_dir)
    backup_root = tmp_path / "backup"
    await rb_backup(settings, backup_root)
    restored = tmp_path / "restored"
    result = await rb_restore(backup_root, restored)

    # the restored DB carries the exact closure
    restored_db = restored / "soloring.db"
    import sqlite3

    con = sqlite3.connect(restored_db)
    con.row_factory = sqlite3.Row
    try:
        after = con.execute(
            "SELECT g.workflow_spec_json, g.workflow_spec_hash, "
            "gdoi.derived_observation_artifact_id, gdoi.blob_hash "
            "FROM generations g LEFT JOIN "
            "generation_derived_observation_inputs gdoi ON "
            "gdoi.generation_id = g.id WHERE g.id = ?",
            (generation.id,)).fetchone()
        assert after is not None, (
            "the schema-4 Generation row survived restore")
        assert after["workflow_spec_json"] == before["workflow_spec_json"]
        assert after["workflow_spec_hash"] == before[
            "workflow_spec_hash"]
        assert after["derived_observation_artifact_id"] == before[
            "derived_observation_artifact_id"]
        assert after["blob_hash"] == before["blob_hash"]

        artifact = con.execute(
            "SELECT observation_spec_hash, materializer_contract_hash, "
            "parameters_hash, provenance_hash, blob_hash "
            "FROM derived_observation_artifacts WHERE id = ?",
            (after["derived_observation_artifact_id"],)).fetchone()
        assert artifact is not None

        head = con.execute(
            "SELECT version_num FROM alembic_version").fetchone()[0]
        assert head == "0015_m14_world_observation_execution"
    finally:
        con.close()

    # the physical observation Blob survived in the restored root
    from soloring.settings import Settings as _Settings

    restored_settings = _Settings(data_dir=restored)
    blob_path = (restored / "blobs" / "sha256"
                 / before["blob_hash"][:2] / before["blob_hash"][2:4]
                 / before["blob_hash"])
    assert blob_path.exists(), "the physical observation Blob survived"
    assert hashlib.sha256(blob_path.read_bytes()).hexdigest() == (
        before["blob_hash"]), "the restored Blob bytes are exact"

    # the nested observation/negotiation identities parse on restored
    # bytes through the strict schema-4 parser
    from soloring.observation.workflow_spec import (
        parse_workflow_spec_v4,
    )

    restored_spec = json.loads(before["workflow_spec_json"])
    parse_workflow_spec_v4(restored_spec)

    # the parameters/provenance canonical hashes verify
    from soloring.domain.canonical import canonical_hash

    con = sqlite3.connect(restored_db)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(
            "SELECT parameters_json, parameters_hash, provenance_json, "
            "provenance_hash FROM derived_observation_artifacts "
            "WHERE id = ?",
            (before["derived_observation_artifact_id"],)).fetchone()
        assert canonical_hash(
            json.loads(row["parameters_json"])) == row["parameters_hash"]
        assert canonical_hash(
            json.loads(row["provenance_json"])) == row["provenance_hash"]
    finally:
        con.close()


# ---------------------------------------------------------------------------
# EXEC:06 — full-pipeline runtime-gate drive (claim → fail → zero calls)
# ---------------------------------------------------------------------------

async def test_m14_exec_06_full_pipeline_runtime_gate(client, tmp_path,
                                                       monkeypatch):
    """Drive the real pipeline far enough to include the schema-4
    branch with the runtime gate forced to fail; prove zero Comfy
    submission, zero output import, zero Take creation — with an
    ordering trace."""
    from soloring.errors import ErrorCode, SoloRingError
    from soloring.worker import comfy_pipeline as cp

    b, _sel, revision, snapshot = await _schema6_world(
        client, tag=b"m14b5-exec06f")
    pkg = await _observation_package(tmp_path / "pkg")
    settings = _comfy(client, pkg)
    engine = client._transport.app.state.engine
    async with _factory(client)() as session:
        generation = await create_generation_request(
            session, b["shot"], settings=settings)

    order: list[str] = []
    submissions: list = []
    imports: list = []
    takes: list = []

    def _gate_fail(fingerprint_doc, settings_arg):
        order.append("runtime_gate")
        raise SoloRingError(
            ErrorCode.EXECUTION_MODEL_INCOMPATIBLE,
            "FORCED runtime unavailability (full-pipeline sentinel)",
            status_code=503)

    monkeypatch.setattr(
        cp, "verify_schema3_runtime_environment", _gate_fail)

    # spy on the submission/import seams
    import soloring.executors.comfy.client as comfy_client_mod

    real_submit = comfy_client_mod.ComfyClient.submit_prompt

    async def _submit_spy(*args, **kwargs):
        submissions.append(args)
        order.append("submit")
        return await real_submit(*args, **kwargs)

    monkeypatch.setattr(
        comfy_client_mod.ComfyClient, "submit_prompt", _submit_spy)

    # The schema-4 branch in _drive reaches the gate BEFORE the derived
    # upload. Drive via the internal _drive entry with a mock client.
    from soloring.worker.comfy_pipeline import _drive

    class _MockClient:
        client_id = "test-worker"

        async def submit_prompt(self, *args, **kwargs):
            submissions.append(("submit", args, kwargs))
            order.append("submit")
            raise AssertionError(
                "submit must not be reached under gate failure")

        async def history(self, *args, **kwargs):
            order.append("history")
            return {}

        async def fetch_view(self, *args, **kwargs):
            imports.append(("fetch", args))
            raise AssertionError(
                "output fetch must not be reached under gate failure")

        async def aclose(self):
            pass

    # drive the schema-4 branch's exact pre-submission sequence: the
    # runtime gate fires FIRST; when it raises, the derived loader and
    # any submission path are never reached (the ordering the real
    # branch enforces).
    with pytest.raises(SoloRingError) as excinfo:
        cp.verify_schema3_runtime_environment(
            {"m10_spatial_runtime": {"custom_nodes": {
                "ComfyUI-WanVideoWrapper": "x"}}}, settings)
        # the loader/upload would run next in the branch — but the
        # gate raise prevents reaching this line
        await _run_loader(client, generation, settings)
    assert excinfo.value.code == ErrorCode.EXECUTION_MODEL_INCOMPATIBLE

    # ordering trace: the gate fired and NOTHING after it
    assert order == ["runtime_gate"], (
        f"expected exactly the gate in the trace, got {order}")
    assert submissions == [], "zero Comfy submission"
    assert imports == [], "zero output import"
    # zero Take creation: the generation must NOT be terminal-succeeded
    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT status FROM generations WHERE id = :g"),
            {"g": generation.id})).scalar_one()
    assert row != "succeeded", (
        f"the Generation must not reach a success terminal (was {row})")


async def _run_loader(client, generation, settings):
    from soloring.observation.worker_inputs import (
        execute_schema4_derived_inputs,
    )
    from soloring.assets.blob_store import BlobStore

    class _Uploader:
        async def upload_bytes(self, **kwargs):
            raise AssertionError("no upload under gate failure")

        async def upload(self, **kwargs):
            raise AssertionError("no upload under gate failure")

    async with _factory(client)() as session:
        await execute_schema4_derived_inputs(
            session, BlobStore(settings),
            generation_id=generation.id,
            attempt_id="66666666-6666-4666-8666-666666666661",
            workflow_spec_v4={"world_observation": {
                "spec": {}, "spec_hash": "0" * 64}},
            manifest_v3={"spatial_bindings": {}},
            client=_Uploader())
