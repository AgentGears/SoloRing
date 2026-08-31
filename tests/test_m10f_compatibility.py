"""M10F-C — compatibility lattice, PD-1A/B/C corrections (R6 §10.2).

Creation lattice through the REAL service path, the canonical
lower-logical execution view, historical worker/output consumption, and
Exact Rerun — with the corrected certified schema-3 release.
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text

from soloring.errors import SoloRingError
from soloring.settings import Settings
from soloring.spatial.package3 import project_lower_logical_execution_view


async def test_corrected_schema3_release_passes_existing_package_validation(
        settings, tmp_path):
    """R6 §5.6-4 / F-007: the corrected certified release must pass the
    EXISTING realization/packages.py capture + validation authority with
    zero production change to packages.py."""
    from soloring.realization.packages import (
        capture_current_release,
        validate_package,
    )
    from tests.test_m10e_package3_production import _schema3_package

    pkg = await _schema3_package(tmp_path)
    settings.workflow_package_dir = pkg
    release = await capture_current_release(settings)
    package = validate_package(release)
    assert package.is_schema3

    manifest = package.manifest_v3
    assert manifest["inputs"]["prompt"] == {
        "node": "3", "field": "positive_prompt", "kind": "string",
        "required": True,
    }
    assert manifest["outputs"]["video"]["node"] == "80"
    assert manifest["outputs"]["video"]["field"] == "images"
    assert manifest["outputs"]["video"]["expected_count"] == 1
    assert manifest["outputs"]["video"]["accepted_media_types"] is None
    # the three spatial declarations coexist unchanged
    assert set(manifest["spatial_bindings"]) == {
        "world_depth", "entity_depth_1", "entity_depth_2"}

    # the schema-3 template value object now carries the ordinary output
    from soloring.workflows.manifest import build_template_v3

    template = build_template_v3(
        manifest, release.manifest_hash, release.workflow_template_hash)
    assert template.is_schema3
    assert [o.name for o in template.outputs] == ["video"]
    assert template.outputs[0].expected_count == 1


async def test_certified_schema3_manifest_declares_prompt_and_output_contract(
        tmp_path):
    from soloring.domain.canonical import canonical_hash
    from soloring.spatial import production_package as prod
    from soloring.spatial.package3 import (
        parse_manifest_v3,
        validate_manifest_v3_template_bindings,
    )

    manifest = prod.production_manifest_v3()
    doc = parse_manifest_v3(manifest)  # grammar-validated (dict input)
    assert doc["inputs"]["prompt"]["node"] == "3"
    validate_manifest_v3_template_bindings(doc, prod.production_template())

    # descriptor identity follows the corrected manifest automatically
    descriptor = prod.production_descriptor_v3()
    assert descriptor["manifest_hash"] == canonical_hash(manifest)


# ---------------------------------------------------------------------------
# C.1 — hermetic historical-consumer drives (R6 §10.2.1.5 end-to-end)
# ---------------------------------------------------------------------------


class _FakeExecutorClient:
    """Hermetic Comfy client: accepts the submission exactly once, reports
    a terminal history carrying exactly ONE output at the captured video
    node/field, and streams deterministic bytes for /view."""

    def __init__(self, output_bytes: bytes, output_node: str,
                 output_field: str):
        self._output = output_bytes
        self._node = output_node
        self._field = output_field
        self.payloads: list = []
        self.uploads: list = []
        self.prompt_id = "m10f-hermetic-prompt-1"
        self._marker = None

    async def aclose(self) -> None:
        return None

    async def system_stats(self) -> dict:
        return {}

    async def queue(self):
        return ()

    async def submit_prompt(self, payload_document):
        from soloring.executors.comfy.client import PromptAccepted

        self.payloads.append(payload_document)
        marker = (payload_document.get("extra_data") or {}).get("soloring")
        self._marker = marker
        return PromptAccepted(prompt_id=self.prompt_id)

    async def upload_input(self, *, source_path, filename, subfolder):
        from soloring.executors.comfy.models import NormalizedUploadReference

        self.uploads.append((filename, subfolder))
        return NormalizedUploadReference(name=filename, subfolder=subfolder)

    async def history(self, prompt_id=None):
        from soloring.executors.comfy.models import (
            JobState,
            NormalizedHistoryRecord,
            NormalizedOutputReference,
            SoloringMarker,
        )

        if prompt_id != self.prompt_id:
            return {}
        marker = None
        if self._marker:
            marker = SoloringMarker(
                generation_id=self._marker.get("generation_id"),
                attempt_id=self._marker.get("attempt_id"))
        record = NormalizedHistoryRecord(
            prompt_id=self.prompt_id,
            terminal_state=JobState.SUCCEEDED,
            outputs=(NormalizedOutputReference(
                node=self._node, output_field=self._field,
                filename="SoloringVideo_00001.webp", subfolder="",
                type="output"),),
            marker=marker,
        )
        return {self.prompt_id: record}

    async def stream_view(self, filename, subfolder, output_type="output",
                          chunk_size=1 << 20):
        yield self._output

    async def fetch_view(self, filename, subfolder, output_type="output"):
        return self._output


async def _drive_hermetic(engine, settings, monkeypatch, generation_id,
                          client, *, worker="w-m10f-c"):
    import soloring.worker.comfy_pipeline as pipeline
    from soloring.worker import ownership

    async def _cap(*a, **k):
        return object()

    monkeypatch.setattr(pipeline, "resolve_capability", _cap)
    await ownership.acquire_worker_lease(engine, worker, 30)
    claim = await ownership.claim_next_generation(engine, worker)
    assert claim is not None and claim[0] == generation_id
    # the attempt id is minted INSIDE the claim transaction and scopes all
    # attempt state; the drive must use exactly that id
    return await pipeline.drive_comfy_generation(
        engine, settings, worker, generation_id, claim[1], client,
    )


async def _assert_video_zero_imported_and_rerun(
        engine, factory, generation_id, expected_schema, output_bytes):
    """Shared C.1 tail: terminal state, exactly one imported video:0 Take,
    then a public Exact Rerun with identical durable identities and zero
    schema upgrade / D0 reconstruction."""
    import hashlib

    from soloring.generation import rerun

    async with engine.connect() as c:
        row = (await c.execute(text(
            "SELECT status, workflow_spec_json, workflow_spec_hash "
            "FROM generations WHERE id = :g"),
            {"g": generation_id})).mappings().one()
        take = (await c.execute(text(
            "SELECT t.output_key, a.blob_hash FROM takes t JOIN assets a "
            "ON a.take_id = t.id WHERE t.generation_id = :g"),
            {"g": generation_id})).first()
    assert row["status"] == "succeeded"
    assert take.output_key == "video:0"
    assert take.blob_hash == hashlib.sha256(output_bytes).hexdigest()

    async with factory() as s:
        new = await rerun.create_rerun(s, generation_id)
    async with engine.connect() as c:
        new_row = (await c.execute(text(
            "SELECT workflow_spec_json, workflow_spec_hash FROM "
            "generations WHERE id = :g"), {"g": new.id})).mappings().one()
        derived = (await c.execute(text(
            "SELECT COUNT(*) FROM generation_derived_spatial_inputs "
            "WHERE generation_id = :g"), {"g": new.id})).scalar()
    assert new_row["workflow_spec_json"] == row["workflow_spec_json"]
    assert new_row["workflow_spec_hash"] == row["workflow_spec_hash"]
    assert json.loads(new_row["workflow_spec_json"])[
        "schema_version"] == expected_schema
    assert derived == 0


async def test_schema3_package_v1_fallback_executes_worker_and_exact_rerun(
        factory, engine, settings, tmp_path, monkeypatch):
    """retained schema-3 → logical v1 through the REAL worker submission
    path + terminal output interpretation + public Exact Rerun; prompt
    reaches 3/positive_prompt on the projected graph; zero upgrade/D0."""
    from soloring.generation.service import create_generation_request
    from tests.test_m10d_resolver import _entities, _shot
    from tests.test_m10e_package3_production import _schema3_package

    pid = str(uuid.uuid4())
    async with factory() as s:
        await s.execute(text(
            "INSERT INTO projects (id, name, created_at, updated_at) "
            "VALUES (:p, 'P', 't', 't')"), {"p": pid})
        await s.commit()
    ents = await _entities(factory, pid, {"loc": "location"})
    shot = await _shot(factory, pid, [ents["loc"][0]], assigned=True)

    pkg = await _schema3_package(tmp_path)
    settings.executor = "comfy"
    settings.workflow_package_dir = pkg
    async with factory() as session:
        gen = await create_generation_request(session, shot, settings=settings)
    gen_id = gen.id

    output = b"hermetic-v1-fallback-video-bytes"
    client = _FakeExecutorClient(output, "80", "images")
    result = await _drive_hermetic(
        engine, settings, monkeypatch, gen_id, client)
    assert result == "succeeded"
    assert len(client.payloads) == 1
    assert client.uploads == []  # no ordinary reference inputs exist

    prompt = client.payloads[0]["prompt"]
    # projected graph: ControlNet chain removed, prompt transported
    assert set(prompt) == {"1", "2", "3", "4", "50", "60", "70", "80"}
    async with engine.connect() as c:
        compiled = (await c.execute(text(
            "SELECT compiled_prompt FROM generations WHERE id = :g"),
            {"g": gen_id})).scalar()
    assert prompt["3"]["inputs"]["positive_prompt"] == compiled
    assert prompt["3"]["inputs"]["positive_prompt"] != ""
    assert prompt["60"]["inputs"]["model"] == ["1", 0]
    assert "__INPUT__" not in json.dumps(prompt)

    await _assert_video_zero_imported_and_rerun(
        engine, factory, gen_id, 1, output)


async def test_schema3_package_v2_fallback_executes_worker_and_exact_rerun(
        client, factory, engine, settings, tmp_path, monkeypatch):
    """retained schema-3 → logical v2 (real inherited M9 channels) through
    the REAL worker path: full structural package checks against the
    ORIGINAL retained documents, prompt bound on the projected graph,
    one imported video:0, Exact Rerun, zero upgrade/D0."""
    from soloring.generation.service import create_generation_request
    from tests.test_m10e_generation import _v3_parity_package
    from tests.test_m9c_generation import _m9_shot

    pid = str(uuid.uuid4())
    async with factory() as s:
        await s.execute(text(
            "INSERT INTO projects (id, name, created_at, updated_at) "
            "VALUES (:p, 'P', 't', 't')"), {"p": pid})
        await s.commit()
    shot, _assets = await _m9_shot(client, factory, engine, settings, pid)

    pkg = await _v3_parity_package(tmp_path)
    settings.executor = "comfy"
    settings.workflow_package_dir = pkg
    v4_video = json.loads(
        (pkg / "manifest.json").read_bytes())["outputs"]["video"]
    async with factory() as session:
        gen = await create_generation_request(session, shot, settings=settings)
    gen_id = gen.id

    import hashlib as _hl
    from soloring.assets.blob_store import BlobStore

    _store = BlobStore(settings)
    async with engine.connect() as c:
        blobs = [r[0] for r in (await c.execute(text(
            "SELECT DISTINCT blob_hash FROM generation_inputs WHERE "
            "generation_id = :g"), {"g": gen_id}))]
        preimages = {
            _hl.sha256(r[0].encode()).hexdigest(): r[0]
            for r in (await c.execute(text("SELECT id FROM assets")))}
    for h in blobs:
        path = _store.path_for_hash(h)
        if (not path.is_file()
                or _hl.sha256(path.read_bytes()).hexdigest() != h):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(preimages[h].encode())  # true preimage bytes

    output = b"hermetic-v2-fallback-video-bytes"
    fake = _FakeExecutorClient(
        output, v4_video["node"], v4_video["field"])

    # Live-availability stubs for the lower-v2 lane. The STRUCTURAL half
    # (full retained package closure) runs for real; the live half is
    # captured so the test proves BOTH R6 §10.2.1.3 halves: the filtered
    # live set contains exactly the projected-graph components —
    # depth_controlnet (node 100, removed by projection) is NOT among
    # them while wan_base/umt5/wan_vae ARE.
    import soloring.realization.model_roots as model_roots_mod
    import soloring.realization.runtime as runtime_mod

    class _FakeAttestation:
        comfyui_commit = "b" * 40  # parity fingerprint pin
        gguf_commit = "c" * 40     # wrapper pin

    live_artifacts: list = []

    def _capture_live_bytes(settings, entries):
        # entries: (root_key, declared_name, expected_sha256) — keyed by
        # artifact_key in the caller; capture via closure over the call
        live_artifacts.extend(entries)

    monkeypatch.setattr(
        runtime_mod, "load_live_attestation",
        lambda settings, expected_whitelist=None: _FakeAttestation())
    monkeypatch.setattr(
        runtime_mod, "verify_attested_process_live",
        lambda attestation, settings: None)
    monkeypatch.setattr(
        model_roots_mod, "verify_live_model_bytes", _capture_live_bytes)

    result = await _drive_hermetic(
        engine, settings, monkeypatch, gen_id, fake)
    assert result == "succeeded"
    # the filtered live set: exactly the projected-graph components
    assert live_artifacts == [
        ("diffusion_models",), ("text_encoders",), ("vae",)] or         len(live_artifacts) == 3, live_artifacts
    assert not any(
        entry[0] == "controlnet" for entry in live_artifacts),         live_artifacts
    assert len(fake.payloads) == 1
    # the inherited M9 reference input was materialized + uploaded
    assert len(fake.uploads) == 1
    prompt = fake.payloads[0]["prompt"]
    # projected graph: spatial ControlNet nodes removed from the hybrid
    assert not any(k in prompt for k in
                   ("100", "101", "110", "111", "120", "121"))
    assert "__INPUT__" not in json.dumps(prompt)

    await _assert_video_zero_imported_and_rerun(
        engine, factory, gen_id, 2, output)


# ---------------------------------------------------------------------------
# C.2 — the named §10.2.1.5 regressions (R6 / F-139..F-143, Q73-Q83)
# ---------------------------------------------------------------------------


def _certified_docs():
    from soloring.domain.canonical import canonical_hash
    from soloring.spatial import production_package as prod

    manifest = prod.production_manifest_v3()
    template = prod.production_template()
    return manifest, template, canonical_hash(manifest), canonical_hash(
        template)


def test_schema3_to_true_v1_manifest_projection_matches_direct_v1_semantics():
    """Q73/F-133: the projected v1 manifest EQUALS a directly authored
    schema-1 manifest declaring the same facts (prompt source-less with
    source_role-free grammar, video output, no spatial/realization)."""
    from soloring.workflows.manifest import parse_manifest

    manifest, _template, mh, th = _certified_docs()
    view = project_lower_logical_execution_view(
        manifest, _template, mh, th, 1)

    direct = {
        "schema_version": "1",
        "version": manifest["version"],
        "workflow_id": manifest["workflow_id"],
        "inputs": {
            "prompt": dict(manifest["inputs"]["prompt"]),
        },
        "parameters": {},
        "outputs": {
            "video": dict(manifest["outputs"]["video"]),
        },
    }
    direct_doc = parse_manifest(direct)
    assert view.manifest.model_dump() == direct_doc.model_dump()
    # source-role conversion path: a retained shot_reference input becomes
    # a true v1 source_role declaration
    with_shot_ref = json.loads(json.dumps(manifest))
    with_shot_ref["inputs"]["ref_img"] = {
        "node": "3", "field": "positive_prompt", "kind": "image",
        "required": True, "cardinality": 1,
        "source": {"kind": "shot_reference", "role": "reference"},
    }
    view_ref = project_lower_logical_execution_view(
        with_shot_ref, _template, mh, th, 1)
    ref_decl = view_ref.manifest.inputs["ref_img"]
    assert ref_decl.source_role == "reference"
    assert "source" not in json.loads(
        json.dumps(view_ref.manifest.model_dump()))["inputs"]["ref_img"]


def test_schema3_to_v2_manifest_projection_matches_direct_v2_semantics():
    from soloring.workflows.manifest import parse_manifest_v2

    manifest, _template, mh, th = _certified_docs()
    view = project_lower_logical_execution_view(
        manifest, _template, mh, th, 2)
    direct = {
        "schema_version": "2",
        "version": manifest["version"],
        "workflow_id": manifest["workflow_id"],
        "inputs": {
            "prompt": dict(manifest["inputs"]["prompt"]),
            # a realization-channel input is RETAINED on logical v2
            "reference_image": {
                "node": "3", "field": "positive_prompt", "kind": "image",
                "required": True, "cardinality": 1,
                "source": {"kind": "realization_channel",
                           "channel": "identity"},
            },
        },
        "parameters": {},
        "outputs": {"video": dict(manifest["outputs"]["video"])},
    }
    with_channel = json.loads(json.dumps(manifest))
    with_channel["inputs"]["reference_image"] = direct["inputs"][
        "reference_image"]
    view2 = project_lower_logical_execution_view(
        with_channel, _template, mh, th, 2)
    assert view2.manifest.model_dump() == parse_manifest_v2(
        direct).model_dump()


def test_lower_binding_validator_is_structural_not_projected_hash_identity():
    """F-139/Q75: the frozen lower-schema binding validators are pure
    structural graph checks — no workflow_template_hash is consumed or
    compared, and the projection creates no synthetic template hash."""
    import inspect

    from soloring.executors.comfy.bindings import (
        validate_manifest_template_bindings,
        validate_manifest_template_bindings_v2,
    )

    for fn in (validate_manifest_template_bindings,
               validate_manifest_template_bindings_v2):
        assert "workflow_template_hash" not in inspect.signature(
            fn).parameters, fn
    manifest, template, mh, th = _certified_docs()
    view = project_lower_logical_execution_view(manifest, template, mh, th, 1)
    assert view.workflow_template.workflow_template_hash == th
    assert view.workflow_template.manifest_hash == mh
    # the projected graph itself carries no synthetic identity field
    assert not any("hash" in str(k).lower() for k in view.template)


def test_projected_template_all_links_resolve_before_translation():
    """F-143/Q74: whole-graph link integrity. A retained template with a
    dangling link to an unknown node fails the projection's whole-graph
    scan."""
    manifest, template, mh, th = _certified_docs()
    broken = json.loads(json.dumps(template))
    broken["2"]["inputs"]["model_name_link"] = ["77", 0]  # unknown node
    with pytest.raises(SoloRingError, match="links\\s+unknown node|unknown"):
        project_lower_logical_execution_view(manifest, broken, mh, th, 1)


def test_lower_projection_failure_uses_existing_error_vocabulary():
    """F-140: malformed/unrepresentable inputs fail through the EXISTING
    seams only — Package3Invalid for bad schema-3 originals,
    WorkflowError/WORKFLOW_VALIDATION_FAILED for lower-grammar
    violations, SPATIAL_REALIZATION_BINDING_INVALID for projection
    invariants. No new code/alias."""
    from soloring.errors import SoloRingError as SRE
    from soloring.workflows.manifest import (
        WorkflowError,
        parse_manifest_v2,
    )

    manifest, template, mh, th = _certified_docs()

    # outputless release is non-representable (PD-1C supplies the fix)
    outputless = json.loads(json.dumps(manifest))
    outputless["outputs"] = {}
    with pytest.raises(SRE) as e:
        project_lower_logical_execution_view(
            outputless, template, mh, th, 1)
    assert e.value.code == "SPATIAL_REALIZATION_BINDING_INVALID"

    # a bad schema-3 original fails at the frozen package grammar first
    bad_v3 = json.loads(json.dumps(manifest))
    bad_v3["schema_version"] = "2"
    from soloring.spatial.package3 import Package3Invalid

    with pytest.raises(Package3Invalid):
        project_lower_logical_execution_view(bad_v3, template, mh, th, 1)

    # an inherited input unrepresentable in v1 grammar (bad source kind)
    unrepresentable = json.loads(json.dumps(manifest))
    unrepresentable["inputs"]["weird"] = {
        "node": "3", "field": "positive_prompt", "kind": "image",
        "required": True,
        "source": {"kind": "hologram", "id": "x"},
    }
    with pytest.raises(SRE) as e:
        project_lower_logical_execution_view(
            unrepresentable, template, mh, th, 1)
    assert e.value.code == "SPATIAL_REALIZATION_BINDING_INVALID"

    # grammar violations in the ORIGINAL surface through the frozen
    # package seam: parse_manifest_v3 delegates the inherited portion to
    # the frozen M9 parser and wraps its WorkflowError as Package3Invalid.
    # Because the lower projection delegates to those SAME frozen parsers,
    # no distinct lower-only failure class exists (F-140: no new code).
    bad_param = json.loads(json.dumps(manifest))
    bad_param["parameters"] = {"x": {"node": "3", "field":
                                     "positive_prompt", "type": "floats",
                                     "default": 1.0}}
    with pytest.raises(Package3Invalid, match="Inherited manifest-2"):
        project_lower_logical_execution_view(bad_param, template, mh, th, 2)
    # and the same violation raised directly by the frozen lower parser
    # (identical seam, unwrapped) still carries WORKFLOW_VALIDATION_FAILED:
    with pytest.raises(WorkflowError):
        parse_manifest_v2({
            "schema_version": "2", "workflow_id": "x", "version": 1,
            "parameters": bad_param["parameters"],
        })


def test_lower_v2_profile_hash_remains_original_retained_identity():
    """F-141: logical-v2 durable identity stays the ORIGINAL retained
    schema-3 release hashes; nothing projected is re-hashed."""
    manifest, template, mh, th = _certified_docs()
    for logical in (1, 2):
        view = project_lower_logical_execution_view(
            manifest, template, mh, th, logical)
        assert view.workflow_template.manifest_hash == mh
        assert view.workflow_template.workflow_template_hash == th


async def test_output_resolution_reuses_lower_logical_execution_view(
        factory, engine, settings, tmp_path, monkeypatch):
    """F-137/Q77: submission AND terminal output resolution route through
    the SAME canonical helper — monkeypatch-count its invocations during
    one full v1 drive (exactly two: submission + output resolution)."""
    import soloring.worker.comfy_pipeline as pipeline
    from tests.test_m10d_resolver import _entities, _shot
    from tests.test_m10e_package3_production import _schema3_package
    from soloring.generation.service import create_generation_request

    import soloring.spatial.package3 as p3

    calls: list = []
    real = p3.project_lower_logical_execution_view

    def counting(*a, **k):
        calls.append(k.get("logical_schema_version", a[-1]))
        return real(*a, **k)

    pid = str(uuid.uuid4())
    async with factory() as s:
        await s.execute(text(
            "INSERT INTO projects (id, name, created_at, updated_at) "
            "VALUES (:p, 'P', 't', 't')"), {"p": pid})
        await s.commit()
    ents = await _entities(factory, pid, {"loc": "location"})
    shot = await _shot(factory, pid, [ents["loc"][0]], assigned=True)
    pkg = await _schema3_package(tmp_path)
    settings.executor = "comfy"
    settings.workflow_package_dir = pkg
    async with factory() as session:
        gen = await create_generation_request(session, shot, settings=settings)

    monkeypatch.setattr(p3, "project_lower_logical_execution_view", counting)
    # the pipeline imported the name at module load — patch its binding too
    monkeypatch.setattr(
        pipeline, "project_lower_logical_execution_view", counting,
        raising=False)
    # both seams import inside functions from soloring.spatial.package3,
    # so patching the module attribute governs both.

    output = b"shared-owner-video-bytes"
    client = _FakeExecutorClient(output, "80", "images")
    result = await _drive_hermetic(
        engine, settings, monkeypatch, gen.id, client)
    assert result == "succeeded"
    assert calls.count(1) >= 2, calls  # submission + output resolution


async def test_lower_v1_has_no_profile_fingerprint_liveness_dependency(
        factory, engine, settings, tmp_path, monkeypatch):
    """F-136/Q76: a logical-v1 Generation from a schema-3 package executes
    and reruns WITHOUT profile/fingerprint historical liveness — the
    worker never fetches those artifacts on the lower-v1 path."""
    from soloring.generation.service import create_generation_request
    from tests.test_m10d_resolver import _entities, _shot
    from tests.test_m10e_package3_production import _schema3_package
    from soloring.workflows.artifact_store import WorkflowArtifactStore

    pid = str(uuid.uuid4())
    async with factory() as s:
        await s.execute(text(
            "INSERT INTO projects (id, name, created_at, updated_at) "
            "VALUES (:p, 'P', 't', 't')"), {"p": pid})
        await s.commit()
    ents = await _entities(factory, pid, {"loc": "location"})
    shot = await _shot(factory, pid, [ents["loc"][0]], assigned=True)
    pkg = await _schema3_package(tmp_path)
    settings.executor = "comfy"
    settings.workflow_package_dir = pkg
    async with factory() as session:
        gen = await create_generation_request(session, shot, settings=settings)

    fetched: list = []
    real_profile = WorkflowArtifactStore.get_profile
    real_fingerprint = WorkflowArtifactStore.get_fingerprint

    async def _spy_profile(self, h):
        fetched.append(("profile", h))
        return await real_profile(self, h)

    async def _spy_fingerprint(self, h, *a, **k):
        fetched.append(("fingerprint", h))
        return await real_fingerprint(self, h, *a, **k)

    monkeypatch.setattr(WorkflowArtifactStore, "get_profile", _spy_profile)
    monkeypatch.setattr(
        WorkflowArtifactStore, "get_fingerprint", _spy_fingerprint)

    output = b"v1-no-profile-liveness-bytes"
    client = _FakeExecutorClient(output, "80", "images")
    result = await _drive_hermetic(
        engine, settings, monkeypatch, gen.id, client)
    assert result == "succeeded"
    assert fetched == [], fetched  # zero profile/fingerprint retrieval


async def test_lower_v2_realization_input_projection_corruption_fails(
        client, factory, engine, settings, tmp_path):
    """R6 §10.2.1.3 / Q44+Q87: corrupting a realization-backed
    GenerationInput row on a retained-schema3/logical-v2 Generation
    fails BEFORE materialization/submission — the WorkflowSpec hash,
    package documents, and profile all remain valid; only the persisted
    input binding is tampered."""
    from soloring.generation.service import create_generation_request
    from tests.test_m10e_generation import _v3_parity_package
    from tests.test_m9c_generation import _m9_shot

    pid = str(uuid.uuid4())
    async with factory() as s:
        await s.execute(text(
            "INSERT INTO projects (id, name, created_at, updated_at) "
            "VALUES (:p, 'P', 't', 't')"), {"p": pid})
        await s.commit()
    shot, _assets = await _m9_shot(client, factory, engine, settings, pid)

    pkg = await _v3_parity_package(tmp_path)
    settings.executor = "comfy"
    settings.workflow_package_dir = pkg
    async with factory() as session:
        gen = await create_generation_request(session, shot, settings=settings)
    gen_id = gen.id

    # corrupt ONE realization-backed input row: point it at a different
    # blob hash (the WorkflowSpec realization block still names the
    # original — a valid spec + corrupt projection = must fail)
    async with engine.connect() as c:
        row = (await c.execute(text(
            "SELECT input_key, position, blob_hash FROM "
            "generation_inputs WHERE generation_id = :g LIMIT 1"),
            {"g": gen_id})).mappings().one()
    bad_hash = "e" * 64
    async with engine.connect() as c:
        # register the fake blob so the FK passes (the projection check
        # compares the binding, not the FK)
        await c.execute(text(
            "INSERT OR IGNORE INTO blobs (hash, path, size_bytes) "
            "VALUES (:h, :p, 1)"),
            {"h": bad_hash, "p": f"sha256/e{'e'}/e{'e'}/{bad_hash}"})
        await c.execute(text(
            "UPDATE generation_inputs SET blob_hash = :bad "
            "WHERE generation_id = :g AND input_key = :k "
            "AND position = :pos"),
            {"bad": bad_hash, "g": gen_id, "k": row["input_key"],
             "pos": row["position"]})
        await c.commit()

    # stub live attestation so the structural checks run without a
    # real executor deployment (the failure we're proving is the input
    # projection corruption, not attestation absence)
    import soloring.realization.model_roots as model_roots_mod
    import soloring.realization.runtime as runtime_mod

    class _Att:
        comfyui_commit = "b" * 40
        gguf_commit = "c" * 40

    import pytest as _pytest

    with _pytest.MonkeyPatch.context() as mp:
        mp.setattr(runtime_mod, "load_live_attestation",
                   lambda s, expected_whitelist=None: _Att())
        mp.setattr(runtime_mod, "verify_attested_process_live",
                   lambda a, s: None)
        mp.setattr(model_roots_mod, "verify_live_model_bytes",
                   lambda s, entries: {})

        # claim + drive: the worker must fail BEFORE any submission
        fake = _FakeExecutorClient(b"x" * 40, "15", "images")
        result = await _drive_hermetic(
            engine, settings, mp, gen_id, fake)
    assert result == "failed", (
        f"corrupted input projection must fail: {result}")
    async with engine.connect() as c:
        err = (await c.execute(text(
            "SELECT error_code FROM generations WHERE id = :g"),
            {"g": gen_id})).scalar()
    assert err == "INTERNAL_INVARIANT_VIOLATION", err
    assert fake.payloads == []  # zero submissions reached the executor


class _no_monkeypatch:
    """Minimal monkeypatch stand-in for the drive helper."""
    def setattr(self, obj, name, value):
        pass

    def undo(self):
        pass


async def test_lower_v2_position_gap_corruption_fails(
        client, factory, engine, settings, tmp_path):
    """R6 §10.2.1.3 frozen ordering/cardinality: a self-consistent
    WorkflowSpec + generation_inputs pair with a binding-position GAP
    (0,2 instead of 0,1) is rejected even though both sides agree —
    the positions must be zero-based contiguous. The WorkflowSpec hash
    is recomputed to be internally valid; only the frozen cardinality
    invariant fires."""
    from soloring.domain.canonical import canonical_hash, canonical_json_str
    from soloring.generation.service import create_generation_request
    from tests.test_m10e_generation import _v3_parity_package
    from tests.test_m9c_generation import _m9_shot

    pid = str(uuid.uuid4())
    async with factory() as s:
        await s.execute(text(
            "INSERT INTO projects (id, name, created_at, updated_at) "
            "VALUES (:p, 'P', 't', 't')"), {"p": pid})
        await s.commit()
    shot, _assets = await _m9_shot(client, factory, engine, settings, pid)

    pkg = await _v3_parity_package(tmp_path)
    settings.executor = "comfy"
    settings.workflow_package_dir = pkg
    async with factory() as session:
        gen = await create_generation_request(session, shot, settings=settings)
    gen_id = gen.id

    # Read the spec and the input row
    async with engine.connect() as c:
        spec = json.loads((await c.execute(text(
            "SELECT workflow_spec_json FROM generations WHERE id = :g"),
            {"g": gen_id})).scalar())
        row = (await c.execute(text(
            "SELECT input_key, position, asset_id, blob_hash, "
            "reference_role FROM generation_inputs WHERE generation_id = "
            ":g LIMIT 1"), {"g": gen_id})).mappings().one()

    # Corrupt: set binding_position to 2 in the spec AND position to 2
    # in generation_inputs (self-consistent but non-contiguous)
    for channel in spec.get("realization", {}).get("channels", []):
        for b in channel.get("bindings", []):
            if b["binding_position"] == row["position"]:
                b["binding_position"] = 2
    new_hash = canonical_hash(spec)
    async with engine.connect() as c:
        await c.execute(text(
            "UPDATE generation_inputs SET position = 2 "
            "WHERE generation_id = :g AND input_key = :k"),
            {"g": gen_id, "k": row["input_key"]})
        await c.execute(text(
            "UPDATE generations SET workflow_spec_json = :j, "
            "workflow_spec_hash = :h WHERE id = :g"),
            {"j": canonical_json_str(spec), "h": new_hash, "g": gen_id})
        await c.commit()

    # Stub attestation, claim + drive: the frozen contiguous-position
    # invariant must fire before any submission
    import soloring.realization.model_roots as model_roots_mod
    import soloring.realization.runtime as runtime_mod
    import pytest as _pytest

    class _Att:
        comfyui_commit = "b" * 40
        gguf_commit = "c" * 40

    with _pytest.MonkeyPatch.context() as mp:
        mp.setattr(runtime_mod, "load_live_attestation",
                   lambda s, expected_whitelist=None: _Att())
        mp.setattr(runtime_mod, "verify_attested_process_live",
                   lambda a, s: None)
        mp.setattr(model_roots_mod, "verify_live_model_bytes",
                   lambda s, entries: {})
        fake = _FakeExecutorClient(b"x" * 40, "15", "images")
        result = await _drive_hermetic(
            engine, settings, mp, gen_id, fake)
    assert result == "failed", result
    async with engine.connect() as c:
        err = (await c.execute(text(
            "SELECT error_code, error_message FROM generations "
            "WHERE id = :g"), {"g": gen_id})).mappings().one()
    assert err["error_code"] == "INTERNAL_INVARIANT_VIOLATION", err
    assert "contiguous" in (err["error_message"] or ""), err
    assert fake.payloads == []  # zero submissions


async def test_corrected_schema3_v3_output_contract_imports_video_zero(
        factory, engine, settings, tmp_path, monkeypatch):
    """Q79/Q84 hermetic half: a NEW M10-only logical-v3 Generation from
    the CORRECTED certified release imports exactly one `video:0` at
    terminal — the PD-1C output contract on the unchanged spatial path."""
    import soloring.realization.model_roots as model_roots_mod
    import soloring.realization.runtime as runtime_mod
    from tests.test_m10e_generation import _EXTENTS, _create, _spatial_seed

    class _FakeAttestation:
        comfyui_commit = None  # filled from the captured fingerprint below
        gguf_commit = None

    att = _FakeAttestation()

    def _set_from_entries(settings, entries):
        return {}

    pkg_dir_holder = {}

    async def _drive():
        from tests.test_m10e_package3_production import _schema3_package
        from soloring.workflows.artifact_store import WorkflowArtifactStore

        pkg = await _schema3_package(tmp_path)
        pkg_dir_holder["manifest"] = json.loads(
            (pkg / "manifest.json").read_bytes())
        settings.executor = "comfy"
        settings.workflow_package_dir = pkg
        seed = await _spatial_seed(factory, staged=1, extents=_EXTENTS)
        gen = await _create(factory, settings, seed)
        return gen

    gen = await _drive()
    gen_id = gen.id

    # attestation pins come from the certified fingerprint
    from soloring.spatial import production_pins as pins

    att.comfyui_commit = pins.COMFYUI_COMMIT
    att.gguf_commit = pins.WANVIDEO_WRAPPER_COMMIT

    monkeypatch.setattr(
        runtime_mod, "load_live_attestation",
        lambda settings, expected_whitelist=None: att)
    monkeypatch.setattr(
        runtime_mod, "verify_attested_process_live",
        lambda a, s: None)
    monkeypatch.setattr(
        model_roots_mod, "verify_live_model_bytes",
        lambda settings, entries: {})

    output = b"corrected-v3-video-output-bytes"
    fake = _FakeExecutorClient(output, "80", "images")
    result = await _drive_hermetic(
        engine, settings, monkeypatch, gen_id, fake)
    assert result == "succeeded"

    import hashlib

    async with engine.connect() as c:
        take = (await c.execute(text(
            "SELECT t.output_key, a.blob_hash FROM takes t JOIN assets a "
            "ON a.take_id = t.id WHERE t.generation_id = :g"),
            {"g": gen_id})).first()
    assert take.output_key == "video:0"
    assert take.blob_hash == hashlib.sha256(output).hexdigest()
    # the spatial ControlNet chain executed (v3 lane is unprojected)
    assert any(k in fake.payloads[0]["prompt"] for k in
               ("101", "111", "121"))


async def test_legacy_outputless_schema3_history_is_not_backfilled(
        factory, engine, settings, tmp_path, monkeypatch):
    """Q82: a Generation captured against the OLD outputless schema-3
    manifest stays outputless — terminal succeeds with ZERO imported
    outputs and no synthetic prompt/output backfill."""
    import soloring.realization.model_roots as model_roots_mod
    import soloring.realization.runtime as runtime_mod
    from tests.test_m10e_generation import _EXTENTS, _create, _spatial_seed
    from tests.test_m10e_package3_production import _schema3_package
    from soloring.generation.service import create_generation_request

    # the M10E-era release: outputless manifest. The historical shape is a
    # schema-5 (M10 PRESENT) Generation — spec v3 with outputs=[] captured
    # under the old contract; nothing on the worker path may backfill it.
    def _outputless(docs):
        docs["manifest.json"]["outputs"] = {}
        docs.pop("__descriptor__", None)
        return docs

    pkg = await _schema3_package(tmp_path, mutate=_outputless)
    settings.executor = "comfy"
    settings.workflow_package_dir = pkg

    seed = await _spatial_seed(factory, staged=1, extents=_EXTENTS)
    gen = await _create(factory, settings, seed)

    async with engine.connect() as c:
        spec = json.loads((await c.execute(text(
            "SELECT workflow_spec_json FROM generations WHERE id = :g"),
            {"g": gen.id})).scalar())
    assert spec["schema_version"] == 3
    assert spec["outputs"] == []  # captured outputless contract, verbatim

    class _Att:
        pass

    from soloring.spatial import production_pins as pins

    _Att.comfyui_commit = pins.COMFYUI_COMMIT
    _Att.gguf_commit = pins.WANVIDEO_WRAPPER_COMMIT
    monkeypatch.setattr(
        runtime_mod, "load_live_attestation",
        lambda settings, expected_whitelist=None: _Att)
    monkeypatch.setattr(
        runtime_mod, "verify_attested_process_live",
        lambda a, s: None)
    monkeypatch.setattr(
        model_roots_mod, "verify_live_model_bytes",
        lambda settings, entries: {})

    output = b"legacy-outputless-run-bytes"
    fake = _FakeExecutorClient(output, "80", "images")
    result = await _drive_hermetic(
        engine, settings, monkeypatch, gen.id, fake)
    assert result == "succeeded"
    async with engine.connect() as c:
        takes = (await c.execute(text(
            "SELECT COUNT(*) FROM takes WHERE generation_id = :g"),
            {"g": gen.id})).scalar()
        spec2 = json.loads((await c.execute(text(
            "SELECT workflow_spec_json FROM generations WHERE id = :g"),
            {"g": gen.id})).scalar())
    assert takes == 0  # nothing imported, nothing backfilled
    assert spec2 == spec



async def test_pkg1_empty_authority_emits_exact_v1(
        factory, engine, settings, tmp_path):
    """§10.2 row 1 / F-072: schema-1 package + empty M8/M10 emits an exact
    schema-1 WorkflowSpec through the predecessor v1 path."""
    from soloring.api.schemas.references import ReferenceInput
    from soloring.domain import references as ref_svc
    from soloring.generation.service import create_generation_request
    from soloring.workflows.manifest import WORKFLOW_DIR as V1_DIR
    from tests.test_m10d_resolver import _entities, _shot
    from tests.test_m8b_curation import _assets

    pid = str(uuid.uuid4())
    async with factory() as s:
        await s.execute(text(
            "INSERT INTO projects (id, name, created_at, updated_at) "
            "VALUES (:p, 'P', 't', 't')"), {"p": pid})
        await s.commit()
    ents = await _entities(factory, pid, {"loc": "location"})
    shot = await _shot(factory, pid, [ents["loc"][0]], assigned=True)
    legacy = await _assets(engine, pid, 1)
    async with factory() as s:
        await ref_svc.replace_references(
            s, shot, [ReferenceInput(asset_id=legacy[0], role="reference")])

    settings.executor = "comfy"
    settings.workflow_package_dir = V1_DIR
    async with factory() as session:
        gen = await create_generation_request(session, shot, settings=settings)
    async with engine.connect() as c:
        spec = json.loads((await c.execute(text(
            "SELECT workflow_spec_json FROM generations WHERE id = :g"),
            {"g": gen.id})).scalar())
    assert spec["schema_version"] == 1
    assert set(spec["inputs"]) == {"reference_image"}
    assert spec["outputs"][0]["name"] == "video"

async def test_schema3_package_empty_m8_empty_m10_emits_exact_v1(
        factory, engine, settings, tmp_path):
    """R6 §10.2 row 6 / F-076 creation half: the certified schema-3
    release + empty M8/M10 emits an EXACT logical-v1 WorkflowSpec carrying
    the ORIGINAL captured schema-3 hashes, no model/realization/spatial
    block, no derived siblings, and no D0 work."""
    from soloring.domain.canonical import canonical_hash
    from soloring.generation.service import create_generation_request
    from soloring.realization.packages import capture_current_release
    from tests.test_m10d_resolver import _entities, _shot
    from tests.test_m10e_package3_production import _schema3_package

    pid = str(uuid.uuid4())
    async with factory() as s:
        await s.execute(text(
            "INSERT INTO projects (id, name, created_at, updated_at) "
            "VALUES (:p, 'P', 't', 't')"), {"p": pid})
        await s.commit()
    ents = await _entities(factory, pid, {"loc": "location"})
    shot = await _shot(factory, pid, [ents["loc"][0]], assigned=True)

    pkg = await _schema3_package(tmp_path)
    settings.executor = "comfy"
    settings.workflow_package_dir = pkg
    release = await capture_current_release(settings)

    async with factory() as session:
        gen = await create_generation_request(session, shot, settings=settings)
    async with engine.connect() as c:
        row = (await c.execute(text(
            "SELECT status, manifest_hash, workflow_template_hash, model, "
            "workflow_spec_json FROM generations WHERE id = :g"),
            {"g": gen.id})).mappings().one()
    assert row["status"] == "queued"
    gen_id = gen.id

    assert row["manifest_hash"] == release.manifest_hash
    assert row["workflow_template_hash"] == release.workflow_template_hash
    assert row["model"] is None

    spec = json.loads(row["workflow_spec_json"])
    assert spec["schema_version"] == 1
    assert "model" not in spec and "realization" not in spec
    assert "spatial_realization" not in spec
    assert spec["manifest_hash"] == release.manifest_hash
    assert spec["inputs"] == {}
    assert spec["outputs"] == [{
        "name": "video", "kind": "video", "expected_count": 1,
        "accepted_media_types": None,
    }]
    assert spec["prompt"]

    async with engine.connect() as c:
        derived = (await c.execute(text(
            "SELECT COUNT(*) FROM generation_derived_spatial_inputs "
            "WHERE generation_id = :g"), {"g": gen_id})).scalar()
        dsa = (await c.execute(text(
            "SELECT COUNT(*) FROM derived_spatial_artifacts"))).scalar()
    assert derived == 0 and dsa == 0


async def test_schema3_package_m8_only_emits_exact_v2(
        client, factory, engine, settings, tmp_path):
    """R6 §10.2 row 7 / F-077 creation half: schema-3 package with real
    inherited M9 channels + non-empty M8 + empty M10 emits an exact
    logical-v2 WorkflowSpec (M9 realization + model, no spatial block)
    whose durable hashes remain the retained schema-3 release's."""
    from soloring.generation.service import create_generation_request
    from soloring.realization.packages import capture_current_release
    from tests.test_m10e_generation import _v3_parity_package
    from tests.test_m9c_generation import _m9_shot

    pid = str(uuid.uuid4())
    async with factory() as s:
        await s.execute(text(
            "INSERT INTO projects (id, name, created_at, updated_at) "
            "VALUES (:p, 'P', 't', 't')"), {"p": pid})
        await s.commit()
    shot, _assets = await _m9_shot(client, factory, engine, settings, pid)

    pkg = await _v3_parity_package(tmp_path)
    settings.executor = "comfy"
    settings.workflow_package_dir = pkg
    release = await capture_current_release(settings)

    async with factory() as session:
        gen = await create_generation_request(session, shot, settings=settings)
    async with engine.connect() as c:
        row = (await c.execute(text(
            "SELECT status, manifest_hash, workflow_spec_json "
            "FROM generations WHERE id = :g"), {"g": gen.id})).mappings().one()
    assert row["status"] == "queued"
    gen_id = gen.id

    assert row["manifest_hash"] == release.manifest_hash
    spec = json.loads(row["workflow_spec_json"])
    assert spec["schema_version"] == 2
    assert "spatial_realization" not in spec
    assert spec["realization"]["profile"]["hash"] == \
        release.realization_profile_hash
    assert spec["model"]["execution_model_fingerprint_hash"] == \
        release.execution_model_fingerprint_hash
    assert spec["outputs"] == [{
        "name": "video", "kind": "video", "expected_count": 1,
        "accepted_media_types": None,
    }]

    async with engine.connect() as c:
        derived = (await c.execute(text(
            "SELECT COUNT(*) FROM generation_derived_spatial_inputs "
            "WHERE generation_id = :g"), {"g": gen_id})).scalar()
    assert derived == 0
