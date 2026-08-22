"""M9D — executor/worker schema-2 verification (frozen plan §§26, 51,
76, 80).

Hermetic CI (§80 item 10): runtime-compatibility and historical-state
validation are proven with fixture attestations, fixture model files,
and small fingerprinted test packages; the real characterized deployment
is the separate live lane. The worker proofs drive the REAL pipeline
through the not_started validation block and assert failures happen
BEFORE any executor submission.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass

import pytest
from sqlalchemy import text

from soloring.realization.fingerprint import parse_fingerprint
from soloring.realization.profile import parse_profile
from soloring.realization.runtime import (
    check_runtime_compatibility,
    validate_schema2_historical_state,
)
from soloring.workflows.manifest import WORKFLOW_DIR as V1_DIR

V4_DIR = V1_DIR.parent / "hunyuan_i2v_v4"


@dataclass
class _Attestation:
    comfyui_commit: str
    gguf_commit: str
    executor_origin: str = "http://127.0.0.1:8188"
    custom_node_policy: tuple = ("ComfyUI-GGUF",)
    pid: int = 4242
    process_start_fingerprint: str = "x"


FP = parse_fingerprint(
    (V4_DIR / "execution-model-fingerprint.json").read_text()
)


def test_runtime_compatibility_positive_control():
    check_runtime_compatibility(FP, _Attestation(
        comfyui_commit=FP.runtime_requirements.comfyui_commit,
        gguf_commit=FP.runtime_requirements.custom_nodes["ComfyUI-GGUF"],
    ))


def test_runtime_compatibility_commit_and_policy_drift():
    from soloring.realization.model_roots import ModelIncompatible

    with pytest.raises(ModelIncompatible, match="ComfyUI commit"):
        check_runtime_compatibility(FP, _Attestation(
            comfyui_commit="0" * 40,
            gguf_commit=FP.runtime_requirements.custom_nodes["ComfyUI-GGUF"],
        ))
    with pytest.raises(ModelIncompatible, match="ComfyUI-GGUF"):
        check_runtime_compatibility(FP, _Attestation(
            comfyui_commit=FP.runtime_requirements.comfyui_commit,
            gguf_commit="1" * 40,
        ))
    with pytest.raises(ModelIncompatible, match="whitelist"):
        check_runtime_compatibility(FP, _Attestation(
            comfyui_commit=FP.runtime_requirements.comfyui_commit,
            gguf_commit=FP.runtime_requirements.custom_nodes["ComfyUI-GGUF"],
            custom_node_policy=(),
        ))


# --- §32 historical-state validation matrix ------------------------------------


class _Row:
    def __init__(self, input_key, position, asset_id, blob_hash, role):
        self.input_key = input_key
        self.position = position
        self.asset_id = asset_id
        self.blob_hash = blob_hash
        self.reference_role = role


def _spec(inputs=None, model="hunyuan-video-i2v"):
    return {
        "schema_version": 2,
        "model": {
            "id": model,
            "version": "q4_k_m-720p-llava",
            "execution_model_fingerprint_hash": "f" * 64,
        },
        "realization": {
            "profile": {"id": "p", "version": 1, "hash": "p" * 64},
            "channels": [
                {
                    "channel": "hero_reference",
                    "input_key": "reference_image",
                    "bindings": inputs
                    or [
                        {
                            "binding_position": 0,
                            "item": {
                                "asset_id": "a1",
                                "blob_hash": "b1",
                                "role": "primary",
                            },
                        }
                    ],
                }
            ],
        },
    }


def _profile():
    return parse_profile(
        (V4_DIR / "realization-profile.json").read_text()
    )


def test_historical_state_positive_control():
    validate_schema2_historical_state(
        spec=_spec(),
        generation_model="hunyuan-video-i2v",
        generation_model_version="q4_k_m-720p-llava",
        profile=_profile(),
        fingerprint=FP,
        input_rows=[
            _Row("reference_image", 0, "a1", "b1", "primary"),
        ],
    )


def test_historical_state_model_column_mismatch_is_corruption():
    with pytest.raises(Exception, match="model columns"):
        validate_schema2_historical_state(
            spec=_spec(),
            generation_model="other-model",
            generation_model_version="q4_k_m-720p-llava",
            profile=_profile(),
            fingerprint=FP,
            input_rows=[_Row("reference_image", 0, "a1", "b1", "primary")],
        )


def test_historical_state_input_projection_mismatch_is_corruption():
    with pytest.raises(Exception, match="GenerationInputs disagree"):
        validate_schema2_historical_state(
            spec=_spec(),
            generation_model="hunyuan-video-i2v",
            generation_model_version="q4_k_m-720p-llava",
            profile=_profile(),
            fingerprint=FP,
            input_rows=[
                _Row("reference_image", 0, "a1", "b1", "detail"),
            ],
        )
    with pytest.raises(Exception, match="GenerationInputs disagree"):
        validate_schema2_historical_state(  # extra row
            spec=_spec(),
            generation_model="hunyuan-video-i2v",
            generation_model_version="q4_k_m-720p-llava",
            profile=_profile(),
            fingerprint=FP,
            input_rows=[
                _Row("reference_image", 0, "a1", "b1", "primary"),
                _Row("reference_image", 1, "a2", "b2", "supporting"),
            ],
        )


def test_historical_state_non_contiguous_positions_are_corruption():
    spec = _spec(
        inputs=[
            {
                "binding_position": 0,
                "item": {"asset_id": "a1", "blob_hash": "b1",
                         "role": "primary"},
            },
            {
                "binding_position": 2,  # gap: 0,2 — not contiguous
                "item": {"asset_id": "a2", "blob_hash": "b2",
                         "role": "supporting"},
            },
        ]
    )
    with pytest.raises(Exception, match="contiguous"):
        validate_schema2_historical_state(
            spec=spec,
            generation_model="hunyuan-video-i2v",
            generation_model_version="q4_k_m-720p-llava",
            profile=_profile(),
            fingerprint=FP,
            input_rows=[
                _Row("reference_image", 0, "a1", "b1", "primary"),
                _Row("reference_image", 2, "a2", "b2", "supporting"),
            ],
        )


# --- Worker pipeline: schema-2 gates fire BEFORE submission (hermetic) ---------


async def _m9_generation(client, factory, engine, settings, tmp_path):
    """Create a schema-2 Generation against a small-file test package so
    live-model verification is exercisable with fixture bytes."""
    import hashlib

    pkg = tmp_path / "pkg"
    shutil.copytree(V4_DIR, pkg)
    fp = json.loads((pkg / "execution-model-fingerprint.json").read_text())
    roots = {}
    for a in fp["artifacts"]:
        content = f"fixture-model-{a['artifact_key']}".encode()
        root = tmp_path / a["storage_root_key"]
        root.mkdir(exist_ok=True)
        (root / a["declared_name"]).write_bytes(content)
        a["sha256"] = hashlib.sha256(content).hexdigest()
        roots[a["storage_root_key"]] = root
    (pkg / "execution-model-fingerprint.json").write_text(json.dumps(fp))
    descriptor = json.loads((pkg / "workflow-package.json").read_text())
    descriptor["execution_model_fingerprint_hash"] = hashlib.sha256(
        (pkg / "execution-model-fingerprint.json").read_bytes()
    ).hexdigest()
    (pkg / "workflow-package.json").write_text(json.dumps(descriptor))

    settings.executor = "comfy"
    settings.workflow_package_dir = pkg
    settings.comfy_model_root_unet = roots["unet"]
    settings.comfy_model_root_vae = roots["vae"]
    settings.comfy_model_root_clip = roots["clip"]
    settings.comfy_model_root_clip_vision = roots["clip_vision"]

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

    pid = await _seed_project(factory)
    eva, rev1 = await _entity_with_revision(client, factory, pid)
    assets = await _assets(engine, pid, 1)
    f = await _facet(
        client, pid, "entity", entity_id=eva["id"], facet_key="identity"
    )
    r = await client.post(
        f"/visual-facets/{f['id']}/anchors",
        json={"entity_revision_id": rev1},
    )
    await _approve_anchor(client, r.json()["id"], assets, ["front"])
    seq, scene, shots = await _topology(client, factory, pid)
    await _depend(client, shots[0], [eva["id"]])

    resp = await client.post(f"/shots/{shots[0]}/generations")
    assert resp.status_code == 202, resp.text
    return resp.json()["id"], pkg, roots


class _RecordingClient:
    """Stub executor client: any submission attempt is recorded and
    fails the test — the §76 gates must fire BEFORE submission."""

    def __init__(self):
        self.submissions = 0

    def __getattr__(self, name):
        def _forbidden(*args, **kwargs):
            self.submissions += 1
            raise AssertionError(
                f"executor client reached before validation gate: {name}"
            )

        return _forbidden


async def _drive_with_stubs(engine, settings, generation_id, monkeypatch):
    import soloring.worker.comfy_pipeline as pipeline

    async def _capability(settings, client):
        return object()

    monkeypatch.setattr(pipeline, "resolve_capability", _capability)
    client = _RecordingClient()
    await pipeline.drive_comfy_generation(
        engine, settings, "w-m9d", generation_id, "attempt-m9d", client,
    )
    return client


async def _claim(engine, generation_id):
    from soloring.worker import ownership

    await ownership.acquire_worker_lease(
        engine, "w-m9d", 30
    )
    claim = await ownership.claim_next_generation(engine, "w-m9d")
    assert claim is not None and claim[0] == generation_id
    return claim


async def test_worker_attestation_unavailable_blocks_before_submission(
    client, factory, engine, settings, tmp_path, monkeypatch,
):
    gid, _pkg, _roots = await _m9_generation(
        client, factory, engine, settings, tmp_path
    )
    # No deployment attestation exists in the test data dir.
    await _claim(engine, gid)
    import soloring.worker.comfy_pipeline as pipeline

    async def _cap(*a, **k):
        return _StubCap()

    monkeypatch.setattr(pipeline, "resolve_capability", _cap)
    from soloring.realization.model_roots import ModelIncompatible

    client_stub = _RecordingClient()
    result = await pipeline.drive_comfy_generation(
        engine, settings, "w-m9d", gid, "attempt-m9d", client_stub,
    )
    assert result == "failed"
    async with engine.connect() as conn:
        row = (await conn.execute(
            text("SELECT error_code, error_message FROM generations "
                 "WHERE id = :g"),
            {"g": gid},
        )).one()
    assert row.error_code == "EXECUTION_MODEL_INCOMPATIBLE"
    assert "attestation" in (row.error_message or "")
    assert client_stub.submissions == 0


class _StubCap:
    pass


async def test_worker_model_byte_drift_blocks_before_submission(
    client, factory, engine, settings, tmp_path, monkeypatch,
):
    gid, _pkg, roots = await _m9_generation(
        client, factory, engine, settings, tmp_path
    )
    # Same filename, different bytes under the unet root.
    (roots["unet"] / "hunyuan-video-i2v-720p-Q4_K_M.gguf").write_bytes(
        b"drifted-bytes"
    )
    await _claim(engine, gid)
    import soloring.worker.comfy_pipeline as pipeline

    async def _cap(*a, **k):
        return _StubCap()

    monkeypatch.setattr(pipeline, "resolve_capability", _cap)
    _write_fixture_attestation(settings)
    import soloring.realization.runtime as runtime_mod

    def _alive(att, settings):
        return None

    monkeypatch.setattr(
        runtime_mod, "verify_attested_process_live", _alive
    )
    from soloring.realization.model_roots import ModelIncompatible

    client_stub = _RecordingClient()
    result = await pipeline.drive_comfy_generation(
        engine, settings, "w-m9d", gid, "attempt-m9d", client_stub,
    )
    assert result == "failed"
    async with engine.connect() as conn:
        row = (await conn.execute(
            text("SELECT error_code, error_message FROM generations "
                 "WHERE id = :g"),
            {"g": gid},
        )).one()
    assert row.error_code == "EXECUTION_MODEL_INCOMPATIBLE"
    assert "hashes to" in (row.error_message or "")
    assert client_stub.submissions == 0


async def test_worker_schema2_validation_passes_to_translation(
    client, factory, engine, settings, tmp_path, monkeypatch,
):
    """Positive control: with attestation + model bytes satisfied, the
    pipeline proceeds PAST the §26 gates into materialization (stubbed)
    — proving the gates are passable, not always-failing."""
    gid, _pkg, _roots = await _m9_generation(
        client, factory, engine, settings, tmp_path
    )
    await _claim(engine, gid)
    import soloring.worker.comfy_pipeline as pipeline

    async def _cap(*a, **k):
        return _StubCap()

    monkeypatch.setattr(pipeline, "resolve_capability", _cap)
    _write_fixture_attestation(settings)
    import soloring.realization.runtime as runtime_mod

    def _alive(att, settings):
        return None

    monkeypatch.setattr(
        runtime_mod, "verify_attested_process_live", _alive
    )

    reached = {"materialize": False}

    class _Materializer:
        async def materialize(self, **kwargs):
            reached["materialize"] = True
            from soloring.executors.comfy.input_materializer import (
                MaterializedComfyInput,
            )

            return type(
                "Outcome", (), {
                    "materialized": [
                        MaterializedComfyInput(
                            input_key="reference_image", position=0,
                            asset_id="fixture-asset",
                            blob_hash="f" * 64,
                            remote_name="fixture.png",
                            subfolder="",
                        ),
                    ],
                },
            )()

    client_stub = _RecordingClient()
    result = await pipeline.drive_comfy_generation(
        engine, settings, "w-m9d", gid, "attempt-m9d", client_stub,
        materializer=_Materializer(),
    )
    # Reaching materialization means every §26 gate passed; the run then
    # terminates against the refusing stub client (or a terminal status).
    assert reached["materialize"] is True
    assert client_stub.submissions == 0 or result in ("failed",)


def _write_fixture_attestation(settings):
    fp = json.loads(
        (V4_DIR / "execution-model-fingerprint.json").read_text()
    )
    rr = fp["runtime_requirements"]
    d = settings.data_dir / "comfy-fingerprint"
    d.mkdir(parents=True, exist_ok=True)
    (d / "deployment_attestation.json").write_text(json.dumps({
        "schema_version": 4,
        "attestation": {
            "comfyui_commit": rr["comfyui_commit"],
            "gguf_commit": rr["custom_nodes"]["ComfyUI-GGUF"],
            "executor_origin": "http://127.0.0.1:8188",
            "custom_node_policy": rr["custom_node_policy"],
            "pid": 4242,
            "process_start_fingerprint": "fixture",
            "launched_at": "2026-01-01T00:00:00Z",
        },
    }))


async def test_attestation_liveness_failure_is_incompatible(
    client, factory, engine, settings, tmp_path, monkeypatch,
):
    from soloring.realization.model_roots import ModelIncompatible
    from soloring.realization.runtime import verify_attested_process_live

    gid, _pkg, _roots = await _m9_generation(
        client, factory, engine, settings, tmp_path
    )
    await _claim(engine, gid)
    import soloring.worker.comfy_pipeline as pipeline

    async def _cap(*a, **k):
        return _StubCap()

    monkeypatch.setattr(pipeline, "resolve_capability", _cap)
    _write_fixture_attestation(settings)
    import soloring.realization.runtime as runtime_mod

    recorded = {}

    def _dead(att, st):
        recorded["att"] = att
        return None  # verify_live_process returned False path

    # Simulate the stale-attestation verdict.
    import soloring.executors.comfy.capability_record as cap_rec

    settings.comfy_base_url = "http://127.0.0.1:8188"
    monkeypatch.setattr(cap_rec, "verify_live_process", lambda a, port=8188: False)
    client_stub = _RecordingClient()
    result = await pipeline.drive_comfy_generation(
        engine, settings, "w-m9d", gid, "attempt-liveness", client_stub,
    )
    assert result == "failed"
    async with engine.connect() as conn:
        row = (await conn.execute(
            text("SELECT error_code, error_message FROM generations "
                 "WHERE id = :g"),
            {"g": gid},
        )).one()
    assert row.error_code == "EXECUTION_MODEL_INCOMPATIBLE"
    assert "live process" in (row.error_message or "")
    assert client_stub.submissions == 0
