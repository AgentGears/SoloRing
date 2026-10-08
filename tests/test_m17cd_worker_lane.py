"""M17C-D W4 — the worker schema-5 performance lane (frozen plan
R2-FINAL W4): the exact expected GPI sibling set (the ONE
``expected_gpi_rows`` law), the per-segment §14.4 equality chain
INCLUDING re-derived §14.6 bytes, the retained-byte uploads, and
the submission-document enumeration — every tamper a terminal
typed refusal BEFORE submission."""

from __future__ import annotations

import json
import shutil

import pytest

from tests.test_m17cd_create_path import (
    _facial_world, _performance_manifest, _row, _rows,
)


class StubUploader:
    """Records uploads; returns references in the given namespace."""

    def __init__(self):
        self.uploads: list[tuple[str, str, str]] = []

    async def upload(self, *, source_path, filename, subfolder):
        self.uploads.append((str(source_path), filename, subfolder))
        return filename, subfolder


async def _schema5_generation(client, factory, tmp_path, monkeypatch):
    await _performance_manifest(tmp_path, monkeypatch)
    world = await _facial_world(client, factory)
    r = await client.post(f"/shots/{world['shot']}/generations")
    assert r.status_code == 202, r.text
    generation_id = r.json()["id"]
    spec = json.loads((await _row(client, (
        "SELECT workflow_spec_json FROM generations WHERE id = :g"),
        {"g": generation_id}))["workflow_spec_json"])
    return world, generation_id, spec


def _session_factory(client):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    return async_sessionmaker(
        client._transport.app.state.engine, expire_on_commit=False)


# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_worker_lane_verifies_and_uploads(client, factory,
                                                tmp_path, monkeypatch):
    from soloring.assets.blob_store import BlobStore
    from soloring.performance.worker_inputs import (
        execute_schema5_performance_inputs,
        submission_performance_bindings,
    )

    world, generation_id, spec = await _schema5_generation(
        client, factory, tmp_path, monkeypatch)
    factory_session = _session_factory(client)
    store = BlobStore(client._transport.app.state.settings)
    uploader = StubUploader()
    async with factory_session() as session:
        result = await execute_schema5_performance_inputs(
            session, store, generation_id=generation_id,
            attempt_id="attempt-1", workflow_spec=spec,
            client=uploader)
    verified = result.verified
    assert [(v.artifact_role,
             v.shot_revision_segment_position)
            for v in verified] == [
        ("performance.controls", 0), ("performance.vocal_audio", 0)]
    # two per-segment uploads + the two per-role bundles
    assert len(uploader.uploads) == 4
    for v in verified:
        assert v.execution_reference is not None
        assert v.blob_hash[:16] in v.execution_reference
    assert set(result.role_bundles) == {
        'performance.controls', 'performance.vocal_audio'}
    bindings = submission_performance_bindings(result)
    assert {b["role"] for b in bindings} == {
        "performance.controls", "performance.vocal_audio"}
    rows = [b for b in bindings if "kind" not in b]
    bundles = [b for b in bindings if "kind" in b]
    assert len(rows) == 2 and len(bundles) == 2
    assert all("segment_position" in b and "input_name" in b
               and "gpi_position" in b and "blob_hash" in b
               for b in rows)
    assert all(b["bundle"] for b in bundles)


@pytest.mark.asyncio
async def test_worker_lane_missing_row_refuses(client, factory,
                                               tmp_path, monkeypatch):
    from sqlalchemy import text

    from soloring.assets.blob_store import BlobStore
    from soloring.errors import ErrorCode, SoloRingError
    from soloring.performance.worker_inputs import (
        execute_schema5_performance_inputs,
    )

    world, generation_id, spec = await _schema5_generation(
        client, factory, tmp_path, monkeypatch)
    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        await conn.execute(text(
            "DELETE FROM generation_performance_inputs "
            "WHERE generation_id = :g AND artifact_role = "
            "'performance.vocal_audio'"), {"g": generation_id})
    factory_session = _session_factory(client)
    store = BlobStore(client._transport.app.state.settings)
    async with factory_session() as session:
        with pytest.raises(SoloRingError) as exc:
            await execute_schema5_performance_inputs(
                session, store, generation_id=generation_id,
                attempt_id="attempt-1", workflow_spec=spec,
                client=StubUploader())
    assert exc.value.code == ErrorCode.PERFORMANCE_EXECUTION_BINDING_INVALID
    assert "MISSING" in exc.value.message


@pytest.mark.asyncio
async def test_worker_lane_extra_and_wrong_rows_refuse(
        client, factory, tmp_path, monkeypatch):
    from sqlalchemy import text

    from soloring.assets.blob_store import BlobStore
    from soloring.errors import ErrorCode, SoloRingError
    from soloring.performance.worker_inputs import (
        execute_schema5_performance_inputs,
    )

    world, generation_id, spec = await _schema5_generation(
        client, factory, tmp_path, monkeypatch)
    engine = client._transport.app.state.engine
    base = await _rows(client, (
        "SELECT * FROM generation_performance_inputs "
        "WHERE generation_id = :g"), {"g": generation_id})
    factory_session = _session_factory(client)
    store = BlobStore(client._transport.app.state.settings)

    # extra row at an unused coordinate
    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT INTO generation_performance_inputs "
            "(generation_id, input_key, position, artifact_role, "
            "shot_revision_segment_position, performance_revision_id, "
            "vocal_performance_revision_id, binding_hash, "
            "segment_hash, translation_identity, derived_input_hash, "
            "blob_hash, created_at) "
            "SELECT :g, 'performance.controls', 9, "
            "'performance.controls', 0, performance_revision_id, "
            "NULL, NULL, segment_hash, translation_identity, "
            "derived_input_hash, blob_hash, created_at "
            "FROM generation_performance_inputs "
            "WHERE generation_id = :g AND input_key = "
            "'performance.vocal_audio'"),
            {"g": generation_id})
    async with factory_session() as session:
        with pytest.raises(SoloRingError) as exc:
            await execute_schema5_performance_inputs(
                session, store, generation_id=generation_id,
                attempt_id="a", workflow_spec=spec,
                client=StubUploader())
    assert "not in the expected sibling set" in exc.value.message
    async with engine.begin() as conn:
        await conn.execute(text(
            "DELETE FROM generation_performance_inputs "
            "WHERE generation_id = :g AND position = 9"),
            {"g": generation_id})

    # wrong role on a lawful coordinate
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE generation_performance_inputs "
            "SET artifact_role = 'performance.vocal_audio' "
            "WHERE generation_id = :g AND input_key = "
            "'performance.controls'"), {"g": generation_id})
    async with factory_session() as session:
        with pytest.raises(SoloRingError) as exc:
            await execute_schema5_performance_inputs(
                session, store, generation_id=generation_id,
                attempt_id="a", workflow_spec=spec,
                client=StubUploader())
    assert "disagrees with the expected shape" in exc.value.message
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE generation_performance_inputs "
            "SET artifact_role = 'performance.controls' "
            "WHERE generation_id = :g AND input_key = "
            "'performance.controls'"), {"g": generation_id})


@pytest.mark.asyncio
async def test_worker_lane_tampered_spec_and_bytes_refuse(
        client, factory, tmp_path, monkeypatch):
    from soloring.assets.blob_store import BlobStore
    from soloring.errors import ErrorCode, SoloRingError
    from soloring.performance.worker_inputs import (
        execute_schema5_performance_inputs,
    )

    world, generation_id, spec = await _schema5_generation(
        client, factory, tmp_path, monkeypatch)
    factory_session = _session_factory(client)
    store = BlobStore(client._transport.app.state.settings)

    # tampered spec coordinate: the controls hash disagrees
    bad_spec = json.loads(json.dumps(spec))
    bad_spec["performance_execution"]["segments"][0][
        "control_schedule_blob_hash"] = "0" * 64
    async with factory_session() as session:
        with pytest.raises(SoloRingError) as exc:
            await execute_schema5_performance_inputs(
                session, store, generation_id=generation_id,
                attempt_id="a", workflow_spec=bad_spec,
                client=StubUploader())
    assert "control_schedule_blob_hash" in exc.value.message

    # tampered retained bytes: the blob no longer re-derives
    row = await _row(client, (
        "SELECT blob_hash FROM generation_performance_inputs "
        "WHERE generation_id = :g AND artifact_role = "
        "'performance.controls'"), {"g": generation_id})
    path = store.path_for_hash(row["blob_hash"])
    original = path.read_bytes()
    tampered = original.replace(b'"frame":0', b'"frame":9', 1)
    assert tampered != original
    tmp = store.tmp_path()
    tmp.write_bytes(tampered)
    import hashlib

    forged = hashlib.sha256(tampered).hexdigest()
    # write the tampered bytes at a NEW content address, register the
    # blob row (the FK demands it), and repoint the row — the retained
    # bytes then fail the re-derivation compare even though they
    # rehash to their own address
    target = store.path_for_hash(forged)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(tmp, target)
    from sqlalchemy import text

    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT OR IGNORE INTO blobs (hash, path, size_bytes, "
            "created_at) VALUES (:h, :p, :s, datetime('now'))"),
            {"h": forged,
             "p": store.relative_path_for_hash(forged),
             "s": len(tampered)})
        await conn.execute(text(
            "UPDATE generation_performance_inputs "
            "SET blob_hash = :h WHERE generation_id = :g AND "
            "artifact_role = 'performance.controls'"),
            {"h": forged, "g": generation_id})
    # keep the spec coordinate CONSISTENT with the repointed row so
    # the isolated failure is the re-derivation law itself
    staged_spec = json.loads(json.dumps(spec))
    staged_spec["performance_execution"]["segments"][0][
        "control_schedule_blob_hash"] = forged
    async with factory_session() as session:
        with pytest.raises(SoloRingError) as exc:
            await execute_schema5_performance_inputs(
                session, store, generation_id=generation_id,
                attempt_id="a", workflow_spec=staged_spec,
                client=StubUploader())
    assert "re-derived" in exc.value.message


@pytest.mark.asyncio
async def test_worker_lane_submission_marker_carries_bindings(
        client, factory, tmp_path, monkeypatch):
    """The pure translator enumerates the performance bindings under
    the marker's exact namespace — the persisted submission artifact
    (byte-identical to the translator's output) proves which derived
    bytes each run bound."""
    from soloring.executors.comfy.translate import (
        build_comfy_prompt, submission_marker,
    )

    world, generation_id, spec = await _schema5_generation(
        client, factory, tmp_path, monkeypatch)
    from soloring.executors.comfy.input_materializer import (
        MaterializedComfyInput,
    )
    from soloring.workflows.manifest import load_workflow

    from soloring.executors.comfy.input_materializer import (
        MaterializedComfyInput,
    )
    from soloring.workflows import manifest as manifest_module
    from soloring.workflows.manifest import parse_manifest

    # the PATCHED performance manifest (WORKFLOW_DIR already
    # redirected by _schema5_generation) — the spec's parameters
    # carry the rasterization facts it declares
    template_graph = json.loads(
        (manifest_module.WORKFLOW_DIR / "workflow.json").read_bytes())
    manifest_doc = parse_manifest(
        (manifest_module.WORKFLOW_DIR / "manifest.json").read_text(
            encoding="utf-8"))
    materialized = [MaterializedComfyInput(
        input_key="reference_image", position=0, asset_id="a",
        blob_hash="b" * 64, remote_name="ref.png", subfolder="")]

    def _build():
        return build_comfy_prompt(
            workflow_spec=spec, manifest=manifest_doc,
            template=template_graph,
            materialized=materialized, generation_id=generation_id,
            attempt_id="attempt-1", client_id="w1",
            performance_bindings=[{
                "role": "performance.controls", "blob_hash": "a" * 64,
                "input_name": "x.png", "segment_position": 0,
                "translation_identity": "t/1"}])

    payload = _build()
    document = payload.to_document()
    marker = document["extra_data"]["soloring"]
    assert marker["generation_id"] == generation_id
    bindings = marker["performance_bindings"]
    assert bindings[0]["segment_position"] == 0
    assert bindings[0]["blob_hash"] == "a" * 64
    # determinism: same bindings → identical canonical bytes
    again = _build()
    from soloring.domain.canonical import canonical_json_str

    assert canonical_json_str(document) == canonical_json_str(
        again.to_document())
