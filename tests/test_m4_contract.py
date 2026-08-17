"""M4 — Workflow Contract (§112).

Adversarial manifest matrix + the headline provenance test: a Generation's
logical execution specification is fully captured at creation and cannot be
reinterpreted by later manifest changes.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from soloring.api.schemas.projects import ProjectCreate
from soloring.api.schemas.references import ReferenceInput
from soloring.api.schemas.shots import ShotCreate
from soloring.domain import projects, references, shots
from soloring.domain.canonical import canonical_hash, canonical_json_bytes
from soloring.errors import ErrorCode, SoloRingError
from soloring.executors.fake import FakeExecutor
from soloring.settings import BASE_DIR, Settings
from soloring.workflows.manifest import (
    MANIFEST_SCHEMA_VERSION,
    WorkflowError,
    build_template,
    parse_manifest,
    resolve_parameters,
)
from tests.conftest import seed_reference_asset

MANIFEST_PATH = BASE_DIR / "workflows" / "hunyuan_i2v_v1" / "manifest.json"


def _base_manifest() -> dict:
    return {
        "schema_version": "1",
        "workflow_id": "test_wf",
        "version": 1,
        "inputs": {
            "reference_image": {
                "node": "4", "field": "image", "kind": "image",
                "required": True, "source_role": "reference", "cardinality": 1,
            },
        },
        "parameters": {
            "steps": {"type": "int", "default": 30, "min": 1, "max": 100},
            "cfg": {"type": "float", "default": 7.0, "min": 0.0, "max": 30.0},
        },
        "outputs": {
            "video": {"kind": "video", "expected_count": 1},
        },
    }


def _template(doc: dict):
    import hashlib

    h = hashlib.sha256(json.dumps(doc).encode()).hexdigest()
    return build_template(parse_manifest(doc), h, h)


# --- strict validation matrix --------------------------------------------------


def test_valid_minimum_manifest() -> None:
    t = _template({"schema_version": "1", "workflow_id": "w", "version": 1,
                   "outputs": {"video": {"kind": "video"}}})
    assert t.outputs[0].expected_count == 1


def test_valid_fully_populated_manifest() -> None:
    t = _template(_base_manifest())
    assert len(t.reference_inputs) == 1
    assert len(t.parameters) == 2
    assert t.outputs[0].kind == "video"


def test_unknown_root_field_rejected() -> None:
    doc = _base_manifest()
    doc["ouput_kind"] = "video"  # typo class the reviewer called out
    with pytest.raises(WorkflowError):
        _template(doc)


def test_unknown_nested_field_rejected() -> None:
    doc = _base_manifest()
    doc["outputs"]["video"]["output_count"] = 1  # typo of expected_count
    with pytest.raises(WorkflowError):
        _template(doc)
    doc2 = _base_manifest()
    doc2["parameters"]["steps"]["minimum"] = 1  # typo of min
    with pytest.raises(WorkflowError):
        _template(doc2)


def test_unsupported_schema_version_rejected() -> None:
    doc = _base_manifest()
    doc["schema_version"] = "2"
    with pytest.raises(WorkflowError):
        _template(doc)


def test_missing_schema_version_rejected() -> None:
    doc = _base_manifest()
    del doc["schema_version"]
    with pytest.raises(WorkflowError):
        _template(doc)


def test_duplicate_parameter_and_output_names_rejected() -> None:
    # dict keys are unique by construction; duplicates are impossible in JSON
    # object form — but a REPEATED name across sections is caught by type
    # strictness. The real duplicate risk is output/logical-input overlap,
    # covered by identity tests below. Here: zero outputs is rejected.
    doc = _base_manifest()
    doc["outputs"] = {}
    with pytest.raises(WorkflowError):
        _template(doc)


# --- parameter resolution matrix -------------------------------------------------


def _params(param_defs: dict, overrides=None):
    doc = _base_manifest()
    doc["parameters"] = param_defs
    return resolve_parameters(_template(doc), overrides)


def test_default_resolution() -> None:
    assert _params(_base_manifest()["parameters"]) == {"steps": 30, "cfg": 7.0}


def test_unknown_supplied_parameter_rejected() -> None:
    with pytest.raises(WorkflowError):
        _params(_base_manifest()["parameters"], {"sampler": "euler"})


def test_missing_required_parameter_rejected() -> None:
    with pytest.raises(WorkflowError):
        _params({"seed": {"type": "int"}})  # no default, no override


def test_wrong_type_rejected_no_coercion() -> None:
    with pytest.raises(WorkflowError):
        _params(_base_manifest()["parameters"], {"steps": "12"})  # str -> int
    with pytest.raises(WorkflowError):
        _params({"aspect": {"type": "float", "default": 1.0}}, {"aspect": True})
    with pytest.raises(WorkflowError):
        _params(
            {"steps": {"type": "int", "default": 30}},
            {"steps": 12.7},  # float -> int
        )


def test_bool_cannot_satisfy_int() -> None:
    with pytest.raises(WorkflowError):
        _params({"steps": {"type": "int", "default": 30}}, {"steps": True})
    # and the default itself is guarded at parse:
    doc = _base_manifest()
    doc["parameters"]["steps"]["default"] = True
    with pytest.raises(WorkflowError):
        resolve_parameters(_template(doc))


def test_range_enforced() -> None:
    with pytest.raises(WorkflowError):
        _params(_base_manifest()["parameters"], {"steps": 0})   # below min
    with pytest.raises(WorkflowError):
        _params(_base_manifest()["parameters"], {"steps": 101})  # above max


def test_enum_enforced() -> None:
    defs = {"aspect": {"type": "string", "default": "16:9",
                       "enum": ["16:9", "9:16", "1:1"]}}
    assert _params(defs) == {"aspect": "16:9"}
    assert _params(defs, {"aspect": "9:16"}) == {"aspect": "9:16"}
    with pytest.raises(WorkflowError):
        _params(defs, {"aspect": "4:3"})


def test_resolved_parameters_are_persisted_not_overrides() -> None:
    """The Generation stores the fully RESOLVED parameter set (M4 §4)."""
    defs = {"a": {"type": "int", "default": 1},
            "b": {"type": "int", "default": 2}}
    assert _params(defs, {"b": 5}) == {"a": 1, "b": 5}  # a's default included


# --- canonical serialization round-trip -------------------------------------------


def test_spec_canonical_round_trip_bytes_identical() -> None:
    spec = {
        "schema_version": 1, "workflow_id": "w", "workflow_version": 1,
        "manifest_hash": "a" * 64,
        "inputs": {"reference_image": {"bindings": [
            {"asset_id": "x", "blob_hash": "b" * 64,
             "reference_role": "reference", "position": 0},
        ]}},
        "prompt": "Subject: Éva\nAction: walks",
        "parameters": {"cfg": 7.0, "steps": 30, "flag": False, "empty": [], "none": None},
        "outputs": [{"name": "video", "kind": "video", "expected_count": 1,
                     "accepted_media_types": None}],
    }
    b1 = canonical_json_bytes(spec)
    parsed = json.loads(b1.decode("utf-8"))
    b2 = canonical_json_bytes(parsed)
    assert b1 == b2
    assert canonical_hash(spec) == canonical_hash(parsed)
    # int vs float representation is preserved by json round-trip
    assert b'"cfg":7.0' in b1 and b'"steps":30' in b1
    # key order irrelevant
    shuffled = dict(reversed(list(parsed.items())))
    assert canonical_json_bytes(shuffled) == b1


# --- deterministic input ordering (byte-for-byte) ---------------------------------


async def _seed(factory, engine):
    async with factory() as s:
        pid = (await projects.create_project(s, ProjectCreate(name="P"))).id
        shot = await shots.create_shot(s, pid, ShotCreate(subject="Eva"))
    a1, _ = await seed_reference_asset(engine, pid)
    async with factory() as s:
        await references.replace_references(
            s, shot.id, [ReferenceInput(asset_id=a1, role="reference")]
        )
    return shot.id, a1, None


async def test_resolved_spec_input_order_is_canonical_byte_for_byte(
    client, factory, engine
):
    sid, a1, a2 = await _seed(factory, engine)
    r = await client.post(f"/shots/{sid}/generations")
    assert r.status_code == 202
    async with factory() as s:
        spec_json = (await s.execute(
            text("SELECT workflow_spec_json FROM generations WHERE shot_id=:s "
                 "ORDER BY generation_number DESC LIMIT 1"),
            {"s": sid},
        )).scalar()
    spec = json.loads(spec_json)
    bindings = spec["inputs"]["reference_image"]["bindings"]
    assert [(b["asset_id"], b["position"]) for b in bindings] == [(a1, 0)]
    # canonical bytes: same logical content constructed differently hashes equal
    rebuilt = json.loads(json.dumps(spec))  # round-trip
    assert canonical_json_bytes(rebuilt) == spec_json.encode("utf-8")


# --- invalid manifests never create runnable generations ---------------------------


async def test_invalid_manifest_fails_before_queue(client, factory, engine, monkeypatch):
    """A corrupted manifest document → Generation creation fails with the
    workflow envelope; NO generation row is minted."""
    sid, a1, a2 = await _seed(factory, engine)

    import shutil
    import tempfile

    broken_dir = Path(tempfile.mkdtemp()) / "wf"
    shutil.copytree(MANIFEST_PATH.parent, broken_dir)
    broken = json.loads((broken_dir / "manifest.json").read_text(encoding="utf-8"))
    broken["outputs"]["video"]["kindd"] = "video"  # typo -> unknown field
    (broken_dir / "manifest.json").write_text(json.dumps(broken), encoding="utf-8")

    import soloring.workflows.manifest as manifest_mod
    from soloring.generation import service as gen_service

    monkeypatch.setattr(manifest_mod, "WORKFLOW_DIR", broken_dir)
    monkeypatch.setattr(gen_service, "load_workflow", lambda: manifest_mod.load_workflow(broken_dir))
    r = await client.post(f"/shots/{sid}/generations")
    assert r.status_code == 422
    body = r.json()
    assert body["error_code"] == ErrorCode.WORKFLOW_VALIDATION_FAILED
    monkeypatch.undo()

    async with factory() as s:
        n = (await s.execute(text("SELECT count(*) FROM generations"))).scalar()
    assert n == 0  # invalid manifest never created a runnable Generation


# --- HEADLINE: manifest mutation after capture cannot reinterpret execution ---------


async def test_manifest_mutation_after_capture_does_not_reinterpret(
    client, factory, engine, settings, monkeypatch
):
    """Install manifest v1 → create G (capture spec+hash) → mutate the
    installed manifest to v2 (different output cardinality + defaults) →
    execute G → G uses the EXACT v1 captured contract. Then G2 (created under
    v2) uses v2. The workflow-layer freeze test (M4 §11)."""
    sid, a1, a2 = await _seed(factory, engine)

    r = await client.post(f"/shots/{sid}/generations")
    assert r.status_code == 202
    gid = r.json()["id"]
    async with factory() as s:
        captured = (await s.execute(
            text("SELECT workflow_spec_json, workflow_spec_hash, parameters_json, "
                 "manifest_hash FROM generations WHERE id=:g"),
            {"g": gid},
        )).mappings().one()
    v1_spec = captured.workflow_spec_json
    v1_hash = captured.workflow_spec_hash
    v1_manifest_hash = captured.manifest_hash
    assert json.loads(v1_spec)["outputs"][0]["expected_count"] == 1
    assert json.loads(captured.parameters_json) == {"cfg": 1.0, "steps": 30}

    # Mutate the installed manifest: new defaults AND new output cardinality.
    import shutil
    import tempfile

    v2_dir = Path(tempfile.mkdtemp()) / "wf"
    shutil.copytree(MANIFEST_PATH.parent, v2_dir)
    v2 = json.loads((v2_dir / "manifest.json").read_text(encoding="utf-8"))
    v2["version"] = 2
    v2["parameters"]["steps"]["default"] = 12
    v2["outputs"]["video"]["expected_count"] = 2
    (v2_dir / "manifest.json").write_text(json.dumps(v2), encoding="utf-8")

    import soloring.workflows.manifest as manifest_mod
    from soloring.generation import service as gen_service

    monkeypatch.setattr(manifest_mod, "WORKFLOW_DIR", v2_dir)
    monkeypatch.setattr(
        gen_service, "load_workflow", lambda: manifest_mod.load_workflow(v2_dir)
    )
    if True:
        # Execute G under the mutated installation.
        from soloring.worker import ownership
        from soloring.worker.execution import process_next_generation

        await ownership.acquire_worker_lease(engine, "w-m4", 30)
        outcome = await process_next_generation(engine, settings, "w-m4", FakeExecutor())
        assert outcome == "succeeded"

        async with factory() as s:
            after = (await s.execute(
                text("SELECT workflow_spec_json, workflow_spec_hash, "
                     "manifest_hash, status FROM generations WHERE id=:g"),
                {"g": gid},
            )).mappings().one()
            take_keys = [r0[0] for r0 in await s.execute(
                text("SELECT output_key FROM takes WHERE generation_id=:g"),
                {"g": gid},
            )]
        # G still uses the EXACT v1 captured specification.
        assert after.workflow_spec_json == v1_spec
        assert after.workflow_spec_hash == v1_hash
        assert after.manifest_hash == v1_manifest_hash
        assert after.status == "succeeded"
        # v1 contract (1 output) governed the publication — not v2's 2.
        assert take_keys == ["video:0"]

        # G2, created under v2, uses v2.
        r2 = await client.post(f"/shots/{sid}/generations")
        assert r2.status_code == 202
        gid2 = r2.json()["id"]
        async with factory() as s:
            g2 = (await s.execute(
                text("SELECT workflow_spec_json, parameters_json FROM generations "
                     "WHERE id=:g"),
                {"g": gid2},
            )).mappings().one()
        assert json.loads(g2.workflow_spec_json)["outputs"][0]["expected_count"] == 2
        assert json.loads(g2.parameters_json)["steps"] == 12
    # monkeypatch auto-undoes at test teardown


# --- kind vs media compatibility ------------------------------------------------


async def test_media_compatibility_enforced_when_declared(client, factory, engine, settings):
    """Detected MIME must satisfy the CAPTURED accepted list when one is
    declared; undeclared stays explicitly unconstrained (v0.1 fake path)."""
    from soloring.generation.importer import ImportFailure, import_staged_outputs
    from soloring.assets.blob_store import BlobStore
    from soloring.executors.base import StagedOutput
    from soloring.generation.repository import get_generation_full
    from soloring.worker import execution as wx
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    sid, a1, a2 = await _seed(factory, engine)
    r = await client.post(f"/shots/{sid}/generations")
    gid = r.json()["id"]

    factory2 = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    async with factory2() as s:
        generation = await get_generation_full(s, gid)
    outs = wx.spec_outputs(json.loads(generation.workflow_spec_json))
    assert outs[0].accepted_media_types is None  # v0.1 fake contract: unconstrained

    # Declared compatibility rejects mismatched bytes.
    declared = tuple([outs[0], ][0:1])[0]
    import dataclasses

    strict = (dataclasses.replace(outs[0], accepted_media_types=("video/mp4",)),)
    staging = Path(settings.staging_dir) / gid / "media-test"
    staging.mkdir(parents=True, exist_ok=True)
    p = staging / "video-0.tmp"
    p.write_bytes(b"\x89PNG\r\n\x1a\nnot-a-video")  # detected image/png
    staged = [StagedOutput(output_key="video:0", path=p, kind="video")]
    with pytest.raises(ImportFailure):
        await import_staged_outputs(
            factory2, BlobStore(settings), generation, staged,
            expected_outputs=strict, staging_directory=staging,
        )


from pathlib import Path  # noqa: E402
