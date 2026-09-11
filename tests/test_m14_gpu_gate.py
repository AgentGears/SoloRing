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
GATE_COMFY_DIR = Path(r"C:/AI/M10R3-evidence/executor/comfy")
GATE_COMFY_EXE = Path(r"C:/AI/ComfyUI/venv/Scripts/python.exe")
GATE_COMFY_PYDEPS = Path(r"C:/AI/M10R3-evidence/executor/pydeps")
GATE_WRAPPER_DIR = (GATE_COMFY_DIR / "custom_nodes"
                    / "ComfyUI-WanVideoWrapper")
GATE_ATTESTATION = (REPO_ROOT / "data" / "m14b6-gate-fingerprint"
                    / "deployment_attestation.json")
PINNED_COMFYUI_COMMIT = "b963f4ad210a42841ab23dfc28a84143a0cce227"
PINNED_WRAPPER_COMMIT = "088128b224242e110d3906c6750e9a3a348a659b"
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


@pytest.fixture(scope="module")
def gate_executor():
    """Launch the certified pinned executor in the M10E production
    posture (ComfyUI b963f4ad + ComfyUI-WanVideoWrapper 088128b2, only
    that node whitelisted) and publish the v4 deployment attestation the
    gate settings consume. On machines without the pinned executor the
    gate skips — it runs on the production class only."""
    import os
    import subprocess
    import time as _time

    if not (GATE_COMFY_DIR.is_dir() and GATE_COMFY_EXE.is_file()
            and GATE_WRAPPER_DIR.is_dir()):
        pytest.skip(
            "the pinned certified executor is not installed — the real "
            "GPU source gate runs on the production machine only")

    def _rev(path: Path) -> str:
        out = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=30)
        if out.returncode != 0:
            pytest.skip(f"cannot read git revision of {path}")
        return out.stdout.strip()

    comfy_commit = _rev(GATE_COMFY_DIR)
    wrapper_commit = _rev(GATE_WRAPPER_DIR)
    assert comfy_commit == PINNED_COMFYUI_COMMIT, (
        f"executor ComfyUI commit {comfy_commit} is not the frozen pin")
    assert wrapper_commit == PINNED_WRAPPER_COMMIT, (
        f"executor WanVideoWrapper commit {wrapper_commit} is not the "
        "frozen pin")

    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-NetTCPConnection -LocalPort 8188 -State Listen "
         "-ErrorAction SilentlyContinue | Select-Object -ExpandProperty "
         "OwningProcess | ForEach-Object { Stop-Process -Id $_ -Force }"],
        capture_output=True, timeout=30)
    log = open(REPO_ROOT / "data" / "m14b6-gate-comfy.log", "wb")
    subprocess.Popen(
        [str(GATE_COMFY_EXE), "main.py", "--listen", "127.0.0.1",
         "--port", "8188", "--disable-all-custom-nodes",
         "--whitelist-custom-nodes", "ComfyUI-WanVideoWrapper",
         "--output-directory", "output"],
        cwd=str(GATE_COMFY_DIR),
        env={**os.environ, "PYTHONPATH": str(GATE_COMFY_PYDEPS)},
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        stdout=log, stderr=subprocess.STDOUT)

    deadline = _time.monotonic() + 180
    while _time.monotonic() < deadline:
        if gate_comfy_serving():
            break
        _time.sleep(1.0)
    else:
        pytest.fail("the certified gate executor did not become ready")

    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-NetTCPConnection -LocalPort 8188 -State Listen | "
         "Select-Object -First 1 -ExpandProperty OwningProcess"],
        capture_output=True, text=True, timeout=30)
    pid = int(out.stdout.strip())

    from soloring.executors.comfy.capability_record import (
        build_deployment_attestation,
        capture_process_start_fingerprint,
    )

    doc = build_deployment_attestation(
        comfyui_commit=comfy_commit,
        gguf_commit=wrapper_commit,  # the single whitelisted custom node
        launched_at=_time.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        pid=pid,
        process_start_fingerprint=capture_process_start_fingerprint(pid),
        executor_origin=GATE_COMFY_URL,
        custom_node_whitelist=("ComfyUI-WanVideoWrapper",))
    GATE_ATTESTATION.parent.mkdir(parents=True, exist_ok=True)
    GATE_ATTESTATION.write_text(json.dumps(doc, indent=2),
                                encoding="utf-8")
    yield {"comfyui_commit": comfy_commit,
           "wrapper_commit": wrapper_commit, "pid": pid}


def _gate_mesh_doc(*, shift_mm: int = 0) -> dict:
    """A gate-visible structural mesh: ~1.2 m across near the world
    origin, where both gate cameras aim. ``shift_mm`` keeps per-world
    blob contents distinct when one test database carries several gate
    worlds."""
    shift = shift_mm
    return {
        "schema_version": 1,
        "kind": "soloring.structural_mesh",
        "coordinate_system": {
            "handedness": "right", "right_axis": "+x", "up_axis": "+y",
            "depth_positive_axis": "+z", "forward_axis": "-z",
            "linear_unit": "millimeter", "vector_convention": "column"},
        "vertices_mm": [
            [-600 + shift, 0, 0], [600 + shift, 0, 0],
            [-600 + shift, 900, 0], [-600 + shift, 0, 1100],
            [600 + shift, 900, 1100], [shift, 1500, 550]],
        "triangles": [[0, 1, 5], [0, 3, 4], [2, 4, 5], [0, 2, 5],
                      [1, 4, 5], [0, 1, 2], [1, 2, 4], [0, 3, 2]],
    }


async def gate_world(client, *, tag: bytes, camera: dict):
    """A captured schema-6 world in the full production posture: the
    gate mesh occurrence under its exact interpretation and placement,
    TWO Track-staged characters (the certified template consumes three
    control streams — world + two entity depths), and the plan re-put
    at the given NEW camera before the binding re-selection and
    re-capture."""
    from tests.conftest import make_tracked_maker
    from tests.test_m13_shot_capture import (
        _capture as _m13_capture,
        _entity_approved,
    )
    from tests.test_m14_materializer import _observation_world

    import zlib

    b, snapshot, oids, prids = await _observation_world(
        client, tag=tag,
        sources=[{"kind": "mesh",
                  "mesh": _gate_mesh_doc(
                      shift_mm=zlib.crc32(tag) % 400),
                  "transform": (0, 0, 0), "interpretation": (0, 0, 0)}],
        adopt_first_mesh=False)

    engine = client._transport.app.state.engine
    maker = make_tracked_maker(engine)

    # the second staged character (the first is the world's eva)
    mark, _markrev = await _entity_approved(
        client, b["pid"], "character", "Mark")
    async with engine.connect() as conn:
        await conn.execute(text(
            "INSERT INTO shot_entity_dependencies (shot_id, entity_id, "
            "role, position) VALUES (:s, :e, 'cast', 9)"),
            {"s": b["shot"], "e": mark})
        await conn.commit()

    from soloring.spatial import plans as plan_svc
    from soloring.spatial import tracks as track_svc
    from soloring.spatial import transitions as trans_svc

    async with engine.connect() as conn:
        seq = (await conn.execute(text(
            "SELECT id FROM sequences WHERE project_id = :p "
            "ORDER BY position LIMIT 1"),
            {"p": b["pid"]})).scalar_one()
    blocking = []
    for entity, translation in ((b["eva"], [-1500, 0, 200]),
                                (mark, [1300, 0, -900])):
        track = await track_svc.create_track(
            maker(), b["world"]["id"], entity_id=entity,
            requirement="optional")
        await trans_svc.create_transition(
            maker(), track["id"], anchor_type="sequence", anchor_id=seq,
            boundary="start", operation="set",
            translation_mm=list(translation), rotation_udeg=[0, 0, 0])
        blocking.append({
            "spatial_track_id": track["id"],
            "screen_direction": "left_to_right",
            "keyframes": [{
                "time_ms": 0,
                "transform": {"translation_mm": list(translation),
                              "rotation_udeg": [0, 0, 0]}}],
        })

    async with engine.connect() as conn:
        old_hash = (await conn.execute(text(
            "SELECT plan_hash FROM shot_spatial_plans "
            "WHERE shot_id = :s"),
            {"s": b["shot"]})).scalar_one()
    await plan_svc.put_spatial_plan(
        maker(), b["shot"], expected_plan_hash=old_hash, plan_raw={
            "schema_version": 1,
            "spatial_world_id": b["world"]["id"],
            "camera": json.loads(json.dumps(camera)),
            "blocking": blocking,
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

    attestation = GATE_ATTESTATION
    assert attestation.is_file(), (
        "the gate attestation is missing — the gate_executor fixture "
        "launches and attests the certified executor first")
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
    ("composition_spatial_bindings", "id"),
    ("composition_spatial_binding_subjects", "binding_id"),
    ("composition_spatial_binding_entries", "binding_id"),
    ("shot_production_world_selections", "shot_id"),
    ("shot_revision_production_instance_feature_states",
     "shot_revision_id"),
    ("shot_revision_production_instance_spatial_states",
     "shot_revision_id"),
    ("production_instance_features", "id"),
    ("production_instance_feature_transitions", "id"),
    ("production_instance_spatial_tracks", "id"),
    ("production_instance_spatial_transitions", "id"),
    ("spatial_worlds", "id"),
    ("spatial_world_states", "id"),
    ("spatial_world_state_frames", "spatial_world_state_id"),
    ("spatial_world_revisions", "id"),
    ("spatial_axes", "id"),
    ("spatial_world_revision_axes", "spatial_world_revision_id"),
    ("shot_revisions", "id"),
    ("shot_revision_spatial_worlds", "shot_revision_id"),
    ("shot_revision_production_worlds", "shot_revision_id"),
)

# NOTE: the blobs table is deliberately NOT in the inventory — it is
# content-addressed storage for execution products (the imported Take
# video is REQUIRED to add a row); the retained bytes stay pinned by
# the immutable closure rows above, whose digests are asserted.


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
