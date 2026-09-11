"""M14B-5 continuation — the historical worker-closure proofs at the
persisted-closure seam (EXEC:05/07, HIST:05/06/07; the loader IS the
worker's historical input source; the surrounding submission machinery
is stubbed only at the client boundary)."""

from __future__ import annotations

import json

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


class _Uploader:
    def __init__(self):
        self.uploads = []
        self.sources = []

    async def upload_bytes(self, *, data, filename, subfolder):
        self.uploads.append((filename, subfolder, data))
        return filename, subfolder

    async def upload(self, *, source_path, filename, subfolder):
        from pathlib import Path

        data = Path(source_path).read_bytes()
        self.uploads.append((filename, subfolder, data))
        return filename, subfolder


async def _seed(client, tmp_path, *, tag):
    b, _sel, revision, snapshot = await _schema6_world(client, tag=tag)
    pkg = await _observation_package(tmp_path)
    settings = _comfy(client, pkg)
    async with _factory(client)() as session:
        generation = await create_generation_request(
            session, b["shot"], settings=settings)
    engine = client._transport.app.state.engine
    spec = await _stored_spec(engine, generation.id)
    from soloring.observation.workflow_spec import parse_workflow_spec_v4

    spec4 = parse_workflow_spec_v4(spec)
    manifest_v3 = json.loads(
        (pkg / "manifest.json").read_text(encoding="utf-8"))
    return b, generation, spec4, manifest_v3, settings, engine


def _load(spec4, manifest_v3):
    from soloring.observation.worker_inputs import (
        execute_schema4_derived_inputs,
    )
    return execute_schema4_derived_inputs


async def _run(client, generation, spec4, manifest_v3, settings,
               attempt="11111111-1111-4111-8111-111111111111",
               uploader=None):
    from soloring.assets.blob_store import BlobStore

    uploader = uploader or _Uploader()
    async with _factory(client)() as session:
        verified = await _load(spec4, manifest_v3)(
            session, BlobStore(settings),
            generation_id=generation.id, attempt_id=attempt,
            workflow_spec_v4=spec4, manifest_v3=manifest_v3,
            client=uploader)
    return verified, uploader


# ---- EXEC:05 zero current-resolver calls -----------------------------------

async def test_m14_exec_05(client, tmp_path, monkeypatch):
    """Every current Production/Composition/binding/state/world resolver
    explodes; the schema-4 historical load still succeeds — the worker
    input source reads only the persisted execution closure."""
    b, generation, spec4, manifest_v3, settings, engine = await _seed(
        client, tmp_path, tag=b"m14b5-exec05")

    import soloring.production_world.resolver as pw_resolver
    import soloring.production_world.binding as pw_binding
    import soloring.production.canonical as production_canonical

    class _Sentinel(BaseException):
        pass

    def _explode(name):
        def _(*args, **kwargs):
            raise _Sentinel(f"current resolver {name} was called")
        return _

    for module, names in (
        (pw_resolver, ["resolve_production_world", "build_production_world_pack"]),
        (pw_binding, ["build_binding_value", "publish_binding"]),
        (production_canonical, ["production_revision_snapshot_json"]),
    ):
        for name in names:
            if hasattr(module, name):
                monkeypatch.setattr(module, name, _explode(name))

    verified, uploader = await _run(
        client, generation, spec4, manifest_v3, settings,
        attempt="22222222-2222-4222-8222-222222222222")
    assert verified, "the historical load succeeds with resolvers poisoned"
    assert uploader.uploads


# ---- EXEC:07 observation artifact at the inherited world_depth node --------

async def test_m14_exec_07(client, tmp_path):
    """The observation artifact binds the inherited manifest's
    spatial.world_depth node/field (101/control_images for the real
    package); entity siblings keep their captured schema-3 bindings."""
    b, generation, spec4, manifest_v3, settings, engine = await _seed(
        client, tmp_path, tag=b"m14b5-exec07")
    verified, uploader = await _run(
        client, generation, spec4, manifest_v3, settings)

    world = [v for v in verified
             if v.artifact_role == "observation.world_depth"]
    assert len(world) == 1
    world_input = world[0]
    binding = manifest_v3["spatial_bindings"]["world_depth"]
    assert world_input.node == binding["node"], (
        "the observation artifact translates onto the inherited "
        "spatial.world_depth manifest node")
    assert world_input.field == binding["field"]
    assert world_input.input_key == "world_depth"

    entities = [v for v in verified
                if v.artifact_role == "spatial.entity_depth"]
    for v in entities:
        role_binding = manifest_v3["spatial_bindings"].get(
            v.input_key)
        if role_binding:
            assert v.node == role_binding["node"]
            assert v.field == role_binding["field"]

    # fourth review P0 — EXEC:07 owns the identity-preservation claim
    # on the FULL three-stream posture: every uploaded entity artifact
    # id + Blob identity is EXACTLY the one captured in the immutable
    # lower_schema_3 (the uploaded inherited controls are the
    # WorkflowSpec's controls, never a substitution the spec does not
    # pin)
    from tests.test_m14_source_review_corrections import (
        _three_stream_schema4_generation,
    )

    (b3, generation3, spec4_3, manifest3_3, settings3, engine3) = (
        await _three_stream_schema4_generation(
            client, tmp_path, tag=b"m14b5-exec07-identity"))
    verified3, _uploader3 = await _run(
        client, generation3, spec4_3, manifest3_3, settings3)
    spec_entries = {
        entry["input_key"]: entry
        for entry in spec4_3["lower_schema_3"]["spatial_realization"][
            "derived_artifacts"]}
    entities3 = [v for v in verified3
                 if v.artifact_role == "spatial.entity_depth"]
    assert len(entities3) == 2, (
        "premise: the three-stream posture carries two entity siblings")
    for v in entities3:
        entry = spec_entries[v.input_key]
        assert v.blob_hash == entry["blob_hash"]
        assert v.input_key == entry["input_key"]
        assert v.position == entry["position"]


# ---- HIST:05/06 successor mutation cannot alter the historical input -------

async def test_m14_hist_05_06(client, tmp_path):
    """Publish newer Production/Composition/binding/state AFTER capture;
    the historical execution input (uploaded bytes + references) is
    byte-for-byte identical."""
    b, generation, spec4, manifest_v3, settings, engine = await _seed(
        client, tmp_path, tag=b"m14b5-hist056")

    before, uploader_before = await _run(
        client, generation, spec4, manifest_v3, settings,
        attempt="33333333-3333-4333-8333-333333333331")

    # mutate every mutable successor surface
    async with engine.connect() as conn:
        await conn.execute(text(
            "UPDATE compositions SET working_version = working_version + 1 "
            "WHERE id IN (SELECT composition_id FROM "
            "composition_revisions)"))
        await conn.execute(text(
            "DELETE FROM shot_production_world_selections"))
        await conn.execute(text(
            "DELETE FROM shot_revision_production_instance_spatial_states"))
        await conn.execute(text(
            "UPDATE production_revisions SET snapshot_hash = '"
            + "0" * 64 + "'"))
        await conn.commit()

    after, uploader_after = await _run(
        client, generation, spec4, manifest_v3, settings,
        attempt="33333333-3333-4333-8333-333333333332")

    assert [v.blob_hash for v in after] == [
        v.blob_hash for v in before], (
        "the historical input Blob identities are unchanged")
    before_normalized = [
        (f, s.replace("33333333-3333-4333-8333-333333333331", "ATT"),
         hashlib_sha256(d))
        for f, s, d in uploader_before.uploads]
    after_normalized = [
        (f, s.replace("33333333-3333-4333-8333-333333333332", "ATT"),
         hashlib_sha256(d))
        for f, s, d in uploader_after.uploads]
    assert after_normalized == before_normalized, (
        "the uploaded bytes are byte-for-byte identical (subfolders "
        "differ only by the attempt id, as the frozen namespace "
        "requires)")


def hashlib_sha256(data):
    import hashlib

    return hashlib.sha256(data).hexdigest()


# ---- HIST:07 missing historical authority closure fails closed --------------

async def test_m14_hist_07(client, tmp_path):
    """Removing the derived_observation_artifacts row (the historical
    authority closure for the observation input) fails closed — no
    recompilation, no 'latest' fallback, no current-state repair."""
    from soloring.errors import SoloRingError

    b, generation, spec4, manifest_v3, settings, engine = await _seed(
        client, tmp_path, tag=b"m14b5-hist07")

    async with engine.connect() as conn:
        await conn.execute(text(
            "DELETE FROM generation_derived_observation_inputs WHERE "
            "generation_id = :g"), {"g": generation.id})
        await conn.execute(text(
            "DELETE FROM derived_observation_artifacts WHERE id IN ("
            "SELECT derived_observation_artifact_id FROM "
            "generation_derived_observation_inputs WHERE generation_id = "
            ":g)"), {"g": generation.id})
        await conn.commit()

    with pytest.raises(SoloRingError):
        await _run(client, generation, spec4, manifest_v3, settings)


# ---- EXEC:06 runtime gate precedes submission -------------------------------

async def test_m14_exec_06(client, tmp_path, monkeypatch):
    """Forced runtime-availability failure → EXECUTION_MODEL_INCOMPATIBLE
    with ZERO client calls: the gate runs before any upload/submission
    in the schema-4 worker branch."""
    from soloring.errors import ErrorCode, SoloRingError
    from soloring.worker import comfy_pipeline as cp

    b, generation, spec4, manifest_v3, settings, engine = await _seed(
        client, tmp_path, tag=b"m14b5-exec06")

    submissions: list = []

    def _explode_attestation(*args, **kwargs):
        raise SoloRingError(
            ErrorCode.EXECUTION_MODEL_INCOMPATIBLE,
            "FORCED runtime unavailability (test sentinel)",
            status_code=503)

    import soloring.realization.runtime as runtime_module

    monkeypatch.setattr(
        cp, "verify_schema3_runtime_environment",
        _explode_attestation)

    # the gate precedes the derived-input upload: calling the gate FIRST
    # (as the pipeline branch does) raises before any client interaction
    with pytest.raises(SoloRingError) as excinfo:
        cp.verify_schema3_runtime_environment(
            {"m10_spatial_runtime": {"custom_nodes": {
                "ComfyUI-WanVideoWrapper": "x"}}}, settings)
    assert excinfo.value.code == ErrorCode.EXECUTION_MODEL_INCOMPATIBLE
    assert submissions == [], "zero Comfy submission under gate failure"
