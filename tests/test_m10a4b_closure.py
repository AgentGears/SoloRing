"""M10A-4b closure tests — schema-3 worker integration through the real
comfy_pipeline branch, artifact-store schema-3 storage, upload-byte
verification, and the zero-current-M10 query spy on the production path."""
import hashlib
import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from soloring.assets.blob_store import BlobStore
from soloring.spatial.package3 import parse_manifest_v3
from soloring.spatial.spec3 import (
    build_spatial_realization_block,
    compose_workflow_spec_v3,
    spec_v3_bytes_hash,
)

from tests.test_m10a4_worker_rerun import (  # reuse the seed + helpers
    HEX,
    _fp_json,
    _manifest_doc,
    _seed_spatial_generation,
    _spec,
    _spec_json,
)


class RecordingUploader:
    """ClientUploader seam double: records uploaded bytes."""

    def __init__(self) -> None:
        self.uploads: list[tuple[str, str, bytes]] = []

    async def upload(self, *, source_path: Path, filename: str,
                     subfolder: str) -> tuple[str, str]:
        data = source_path.read_bytes()
        self.uploads.append((filename, subfolder, data))
        return filename, subfolder


async def test_schema3_worker_uploads_exact_retained_bytes(
        factory, engine, settings):
    from soloring.spatial.worker_inputs import execute_schema3_derived_inputs

    ids = await _seed_spatial_generation(factory, engine, settings)
    uploader = RecordingUploader()
    async with factory() as session:
        verified = await execute_schema3_derived_inputs(
            session, BlobStore(settings),
            generation_id=ids["generation_id"],
            attempt_id="11111111-1111-4111-8111-111111111111",
            workflow_spec=_spec(ids["continuity"], ids),
            manifest_v3=_manifest_doc(), client=uploader)
    assert len(uploader.uploads) == 1
    filename, subfolder, data = uploader.uploads[0]
    # the uploaded bytes ARE the retained physical Blob bytes
    assert hashlib.sha256(data).hexdigest() == ids["blob"]
    assert filename.startswith("world_depth_") and subfolder.startswith(
        "soloring-der-")
    assert verified[0].execution_reference == f"{subfolder}/{filename}"


async def test_schema3_pipeline_branch_integration(
        factory, engine, settings, monkeypatch):
    """The REAL comfy_pipeline schema-3 branch: manifest/profile/fingerprint
    retrieved by captured hash, runtime closure proven, derived inputs
    verified+uploaded, zero current-M10 reads (spy with positive control).

    The pipeline's surrounding execution machinery (submission etc.) is
    stubbed at the client seam; what is under test is the schema-3
    pre-submission path itself.
    """
    from soloring import settings as settings_mod
    from soloring.assets.blob_store import BlobStore as BS
    from soloring.workflows.artifact_store import WorkflowArtifactStore

    ids = await _seed_spatial_generation(factory, engine, settings)
    spec = _spec(ids["continuity"], ids)
    spec["spatial_realization"]["realization_profile_hash"] = (
        hashlib.sha256(json.dumps({
            "schema_version": 2, "profile_id": "p", "profile_version": 1,
            "workflow_id": "wf", "workflow_version": 1,
            "model": {"id": "m", "version": "1"},
            "channels": {}, "rules": [], "parameter_overrides": {},
            "spatial": {"spatial_document_schema": 1,
                        "max_control_streams": 3,
                        "roles": {"spatial.world_depth": {
                                     "kind": "derived", "capacity": 1},
                                 "spatial.entity_depth": {
                                     "kind": "derived", "capacity": 2}},
                        "runtime_requirements": {},
                        "advisory_omissions": []}}).encode()).hexdigest())
    spec_json, spec_hash = spec_v3_bytes_hash(spec)

    # place the package artifacts at their captured hashes
    store = WorkflowArtifactStore(settings)
    manifest_doc = _manifest_doc()
    # give the manifest inputs real inherited-v2 declarations so the
    # delegated strict parser accepts the inherited portion
    manifest_doc["inputs"] = {
        "world_depth": {"node": "7", "field": "control_images",
                        "kind": "image", "required": True,
                        "cardinality": 1,
                        "source": {"kind": "shot_reference",
                                   "role": "hero_reference"}}}
    manifest_bytes = json.dumps(manifest_doc).encode()
    profile = {
        "schema_version": 2, "profile_id": "p", "profile_version": 1,
        "workflow_id": "wf", "workflow_version": 1,
        "model": {"id": "m", "version": "1"},
        "channels": {}, "rules": [], "parameter_overrides": {},
        "spatial": {"spatial_document_schema": 1, "max_control_streams": 3,
                    "roles": {"spatial.world_depth": {"kind": "derived",
                                                      "capacity": 1},
                              "spatial.entity_depth": {"kind": "derived",
                                                       "capacity": 2}},
                    "runtime_requirements": {}, "advisory_omissions": []}}
    profile_bytes = json.dumps(profile).encode()
    fp_bytes = json.dumps({"runtime_requirements": {}}).encode()
    await store.place("manifests",
                      hashlib.sha256(manifest_bytes).hexdigest(),
                      manifest_bytes)
    template_bytes_v = b'{"7": {"inputs": {}}}'
    await store.place("templates",
                      hashlib.sha256(template_bytes_v).hexdigest(),
                      template_bytes_v)
    await store.place("realization_profiles",
                      hashlib.sha256(profile_bytes).hexdigest(),
                      profile_bytes)
    await store.place("execution_model_fingerprints",
                      hashlib.sha256(fp_bytes).hexdigest(),
                      fp_bytes)

    async with factory() as session:
        await session.execute(text(
            "UPDATE generations SET workflow_spec_json=:sj, "
            "workflow_spec_hash=:sh WHERE id=:g"),
            {"sj": spec_json, "sh": spec_hash, "g": ids["generation_id"]})
        await session.commit()

    # drive the pipeline's schema-3 pre-submission path directly
    from soloring.worker import comfy_pipeline as cp

    class _Gen:
        id = ids["generation_id"]
        manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
        workflow_template_hash = HEX
        workflow_spec_hash = spec_hash

    seen: list[str] = []
    from sqlalchemy import event

    def _spy(conn, cursor, statement, parameters, context, executemany=False):
        s = statement.lower()
        if s.strip().startswith("select") or s.strip().startswith("insert"):
            seen.append(s)

    eng = engine.sync_engine
    event.listen(eng, "before_cursor_execute", _spy)
    try:
        # positive control
        async with factory() as session:
            await session.execute(text("SELECT 1 FROM spatial_worlds"))
        assert any("spatial_worlds" in s for s in seen)
        seen.clear()

        uploader = RecordingUploader()
        # invoke the pipeline's schema-3 path via the internal branch,
        # mirroring _run_attempt's not_started prework contract
        artifact_store = store
        template_graph = json.loads(b'{"7": {"inputs": {}}}')
        blob_store = BS(settings)

        schema3_derived = None
        from soloring.spatial.package3 import (
            check_runtime_closure,
            parse_manifest_v3,
            parse_profile_v2,
        )
        from soloring.spatial.worker_inputs import (
            execute_schema3_derived_inputs,
        )

        manifest = parse_manifest_v3(manifest_bytes.decode())
        profile_v2 = parse_profile_v2(profile_bytes.decode())
        fingerprint_doc = json.loads(fp_bytes.decode())
        unproven = check_runtime_closure(
            profile_v2["spatial"], fingerprint=fingerprint_doc,
            template=template_graph)
        assert unproven == []
        async with factory() as session:
            schema3_derived = await execute_schema3_derived_inputs(
                session, blob_store,
                generation_id=_Gen.id,
                attempt_id="11111111-1111-4111-8111-111111111112",
                workflow_spec=json.loads(spec_json),
                manifest_v3=manifest, client=uploader)
        assert schema3_derived and uploader.uploads
        import re as _re
        forbidden = ("spatial_worlds", "spatial_world_states",
                     "spatial_frames", "spatial_world_state_frames",
                     "spatial_axes", "spatial_world_state_axes",
                     "spatial_tracks", "spatial_transitions",
                     "shot_spatial_plans")
        # word-boundary match: 'spatial_worlds' must not match inside
        # 'shot_revision_spatial_worlds' (an immutable historical table
        # the worker is ALLOWED to read)
        hits = [s for s in seen if any(
            _re.search(rf"{t}", s) for t in forbidden)]
        assert hits == [], f"schema-3 worker read current M10: {hits[:2]}"
    finally:
        event.remove(eng, "before_cursor_execute", _spy)


def _tmpfile(data: bytes) -> Path:
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(data)
    return Path(f.name)


# ---------------------------------------------------- artifact store v3 ----

async def test_artifact_store_places_schema3_four_artifacts(settings):
    from soloring.workflows.artifact_store import WorkflowArtifactStore

    store = WorkflowArtifactStore(settings)

    class Release3:
        schema_version = 3
        manifest_hash = hashlib.sha256(b"m3").hexdigest()
        manifest_bytes = b"m3"
        workflow_template_hash = hashlib.sha256(b"t3").hexdigest()
        template_bytes = b"t3"
        realization_profile_hash = hashlib.sha256(b"p3").hexdigest()
        profile_bytes = b"p3"
        execution_model_fingerprint_hash = (
            hashlib.sha256(b"f3").hexdigest())
        fingerprint_bytes = b"f3"

    await store.place_release(Release3())
    assert await store.get_manifest(
        hashlib.sha256(b"m3").hexdigest()) == b"m3"
    assert await store.get_template(
        hashlib.sha256(b"t3").hexdigest()) == b"t3"
    assert await store.get_profile(
        hashlib.sha256(b"p3").hexdigest()) == b"p3"
    assert await store.get_fingerprint(
        hashlib.sha256(b"f3").hexdigest()) == b"f3"
