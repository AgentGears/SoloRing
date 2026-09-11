"""M14B-6 real GPU SHOOT THE WORLD source gate (frozen R2 §39/§40/§42;
proof cells M14-EXEC:08/09/10 — owners live in tests/test_m14_execution.py
and import this harness).

The full production chain on the REAL certified executor: captured
schema-6 ShotRevision → WorldObservationSpec → captured wan21_spatial_v1
v2 / profile schema 3 → SUPPORTED negotiation → retained structural-mesh
closure → real B3 mesh-depth materialization → persisted derived
observation artifact → WorkflowSpec schema 4 → worker historical loader
→ current runtime readiness → real Comfy submission consuming the exact
observation control → real output import → Take candidate.

The gate runs only where the certified executor is serving (the
production machine, launched via scripts/launch_comfy.py); CI skips.
"""

from __future__ import annotations

import json
import shutil
import urllib.request
from pathlib import Path

import pytest
from sqlalchemy import text

REPO_ROOT = Path(__file__).resolve().parents[1]
GATE_COMFY_URL = "http://127.0.0.1:8188"
GATE_MODEL_ROOTS = {
    "diffusion_models": Path(
        r"C:/AI/M10R3-evidence/executor/comfy/models/diffusion_models"),
    "controlnet": Path(
        r"C:/AI/M10R3-evidence/executor/comfy/models/controlnet"),
    "text_encoders": Path(
        r"C:/AI/M10R3-evidence/executor/comfy/models/text_encoders"),
    "vae": Path(r"C:/AI/M10R3-evidence/executor/comfy/models/vae"),
}
PINNED_LIVE_CONTRACT_HASH = (
    "9e5526b1c9f116d900772f3b0afaa2323bd68d6336898f1ff840d04011c55d40")

# the gate cameras differ from every authoring/fixture view (frozen §39
# "a camera different from the representation's authoring/default view")
GATE_CAM_A = {
    "projection": "perspective",
    "focal_length_um": 50000,
    "sensor_width_um": 36000,
    "sensor_height_um": 20250,
    "keyframes": [{
        "time_ms": 0,
        "transform": {"translation_mm": [-3100, 1500, 4300],
                      "rotation_udeg": [0, 2000, 0]}}],
}
GATE_CAM_B = {
    "projection": "perspective",
    "focal_length_um": 50000,
    "sensor_width_um": 36000,
    "sensor_height_um": 20250,
    "keyframes": [{
        "time_ms": 0,
        "transform": {"translation_mm": [-2400, 1900, 3600],
                      "rotation_udeg": [600, -2500, 300]}}],
}


def gate_comfy_serving() -> bool:
    try:
        urllib.request.urlopen(
            f"{GATE_COMFY_URL}/system_stats", timeout=2)
        return True
    except Exception:  # noqa: BLE001 — availability probe only
        return False


requires_live_executor = pytest.mark.skipif(
    not gate_comfy_serving(),
    reason="the certified Comfy executor is not serving — the real GPU "
           "source gate runs on the production machine only")


def _gate_mesh_doc() -> dict:
    """A gate-visible structural mesh: ~1.2 m across at the world
    origin, where both gate cameras aim."""
    return {
        "schema_version": 1,
        "kind": "soloring.structural_mesh",
        "coordinate_system": {
            "handedness": "right", "right_axis": "+x", "up_axis": "+y",
            "depth_positive_axis": "+z", "forward_axis": "-z",
            "linear_unit": "millimeter", "vector_convention": "column"},
        "vertices_mm": [
            [-600, 0, 0], [600, 0, 0], [-600, 900, 0],
            [-600, 0, 1100], [600, 900, 1100], [0, 1500, 550]],
        "triangles": [[0, 1, 5], [0, 3, 4], [2, 4, 5], [0, 2, 5],
                      [1, 4, 5], [0, 1, 2], [1, 2, 4], [0, 3, 2]],
    }


async def gate_world(client, *, tag: bytes, camera: dict):
    """A captured schema-6 world whose direct occurrence carries the
    gate mesh under its exact interpretation and placement, captured at
    the given NEW camera (the plan is re-put at the gate view before the
    binding re-selection and re-capture)."""
    from tests.conftest import make_tracked_maker
    from tests.test_m13_shot_capture import _capture as _m13_capture
    from tests.test_m14_materializer import _observation_world

    b, snapshot, oids, prids = await _observation_world(
        client, tag=tag,
        sources=[{"kind": "mesh", "mesh": _gate_mesh_doc(),
                  "transform": (0, 0, 0), "interpretation": (0, 0, 0)}],
        adopt_first_mesh=False)

    from soloring.spatial import plans as plan_svc

    engine = client._transport.app.state.engine
    maker = make_tracked_maker(engine)
    async with engine.connect() as conn:
        old_hash = (await conn.execute(text(
            "SELECT plan_hash FROM spatial_plans WHERE shot_id = :s"),
            {"s": b["shot"]})).scalar_one()
    await plan_svc.put_spatial_plan(
        maker(), b["shot"], expected_plan_hash=old_hash, plan_raw={
            "schema_version": 1,
            "spatial_world_id": b["world"]["id"],
            "camera": json.loads(json.dumps(camera)),
            "blocking": [],
            "axis_constraint": None,
        })

    binding_id = snapshot["production_world"]["binding"]["binding_id"]
    r = await client.put(
        f"/shots/{b['shot']}/production-world-selection",
        json={"binding_id": binding_id, "expected_binding_id": binding_id})
    assert r.status_code == 200, r.text
    revision, _ = await _m13_capture(client, b["shot"])
    gate_snapshot = json.loads(revision.snapshot_json)
    assert gate_snapshot["schema_version"] == 6
    return b, gate_snapshot, revision, oids, prids


def gate_settings(client, tmp_path: Path):
    """Real-executor settings: the certified v2 package (capturing the
    LIVE materializer contract identity), the certified model roots,
    and the freshly published v4 launcher attestation copied into the
    test data dir."""
    from tests.test_m14_package import _v2_package

    settings = client._transport.app.state.settings
    pkg = _v2_package(tmp_path / "gate-v2")
    settings.executor = "comfy"
    settings.workflow_package_dir = pkg
    settings.comfy_base_url = GATE_COMFY_URL
    settings.comfy_model_root_diffusion_models = GATE_MODEL_ROOTS[
        "diffusion_models"]
    settings.comfy_model_root_controlnet = GATE_MODEL_ROOTS["controlnet"]
    settings.comfy_model_root_text_encoders = GATE_MODEL_ROOTS[
        "text_encoders"]
    settings.comfy_model_root_vae = GATE_MODEL_ROOTS["vae"]

    attestation = (REPO_ROOT / "data" / "comfy-fingerprint" /
                   "deployment_attestation.json")
    assert attestation.is_file(), (
        "the certified v4 launcher attestation is missing — launch the "
        "executor via scripts/launch_comfy.py before the source gate")
    dst = (settings.data_dir / "comfy-fingerprint" /
           "deployment_attestation.json")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(attestation, dst)
    return settings


class RecordingClient:
    """A transparent wrapper around the REAL ComfyClient that records
    every uploaded input's exact bytes — the submitted-control proof
    without touching the submission itself."""

    def __init__(self, inner):
        self._inner = inner
        self.uploads: list[tuple[str, bytes]] = []

    async def upload_input(self, *, source_path, filename, subfolder):
        data = Path(source_path).read_bytes()
        ref = await self._inner.upload_input(
            source_path=source_path, filename=filename,
            subfolder=subfolder)
        self.uploads.append((f"{subfolder}/{filename}", data))
        return ref

    def __getattr__(self, name):
        return getattr(self._inner, name)


async def drive_real(client, settings, generation_id: str):
    """Acquire the lease, claim the Generation, and drive it through
    the REAL pipeline against the live executor."""
    from soloring.executors.comfy.client import ComfyClient
    from soloring.worker import ownership
    from soloring.worker.comfy_pipeline import drive_comfy_generation

    engine = client._transport.app.state.engine
    worker = "w-m14b6-gate"
    await ownership.acquire_worker_lease(engine, worker, 3000)
    claim = await ownership.claim_next_generation(engine, worker)
    assert claim is not None and claim[0] == generation_id
    real_client = ComfyClient(GATE_COMFY_URL, client_id=worker,
                              timeout=120.0)
    recording = RecordingClient(real_client)
    try:
        status = await drive_comfy_generation(
            engine, settings, worker, generation_id, claim[1], recording,
            submission_grace_seconds=900.0,
            disappearance_grace_seconds=900.0,
            outage_grace_seconds=900.0)
    finally:
        await real_client.aclose()
    return status, recording


async def take_blob(engine, generation_id: str):
    async with engine.connect() as conn:
        return (await conn.execute(text(
            "SELECT t.output_key, a.blob_hash FROM takes t JOIN assets a "
            "ON a.take_id = t.id WHERE t.generation_id = :g"),
            {"g": generation_id})).mappings().one_or_none()


async def observation_artifact(engine, generation_id: str) -> dict:
    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT a.id, a.blob_hash, a.materializer_contract_hash, "
            "a.provenance_json, a.provenance_hash FROM "
            "generation_derived_observation_inputs i "
            "JOIN derived_observation_artifacts a "
            "ON a.id = i.derived_observation_artifact_id "
            "WHERE i.generation_id = :g"),
            {"g": generation_id})).mappings().one()
    return dict(row)


_AUTHORITY_TABLES = (
    ("production_revisions", "id"),
    ("production_revision_closures", "production_revision_id"),
    ("production_revision_spatial_interpretations",
     "production_revision_id"),
    ("production_revision_source_assets", "production_revision_id"),
    ("composition_revisions", "id"),
    ("composition_identity_operations", "id"),
    ("composition_identity_operation_sources", "operation_id"),
    ("composition_identity_operation_targets", "operation_id"),
    ("composition_occurrences", "id"),
    ("composition_occurrence_authority_subjects", "occurrence_id"),
    ("production_world_bindings", "binding_id"),
    ("production_instance_features", "id"),
    ("production_instance_feature_transitions", "id"),
    ("production_instance_spatial_tracks", "id"),
    ("production_instance_spatial_transitions", "id"),
    ("spatial_worlds", "id"),
    ("spatial_world_states", "id"),
    ("spatial_world_state_frames", "state_id"),
    ("spatial_world_revisions", "id"),
    ("spatial_world_axes", "id"),
    ("shot_revisions", "id"),
    ("shot_revision_spatial_worlds", "shot_revision_id"),
    ("shot_revision_production_worlds", "shot_revision_id"),
    ("blobs", "hash"),
)


async def authority_snapshot(engine) -> dict[str, str]:
    """A content digest over every production-authority table (frozen
    §39 non-mutation inventory), ordered by primary key."""
    import hashlib

    snapshot: dict[str, str] = {}
    async with engine.connect() as conn:
        for table, order in _AUTHORITY_TABLES:
            rows = (await conn.execute(text(
                f"SELECT * FROM {table} ORDER BY {order}"))).fetchall()
            digest = hashlib.sha256(repr(
                [tuple(row) for row in rows]).encode("utf-8")).hexdigest()
            snapshot[table] = digest
    return snapshot
