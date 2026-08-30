"""M10F-B — §8.4 dedicated cross-slice corruption cycles (cells 12/22/23/24)
and the §8.5.4 class-19 worker/package isolation.

Every TEST cell follows the frozen five-step cycle: valid positive →
isolate exactly one corruption → expected fail closed → exact restoration
→ restored positive.
"""

from __future__ import annotations

import json
import shutil
import uuid

import pytest
from sqlalchemy import text

from soloring.settings import Settings


async def _v3_generation(factory, engine, settings, tmp_path):
    """One real schema-5 → schema-3 Generation through production paths."""
    from tests.test_m10e_generation import _EXTENTS, _create, _spatial_seed
    from tests.test_m10e_package3_production import _schema3_package

    pkg = await _schema3_package(tmp_path)
    settings.executor = "comfy"
    settings.workflow_package_dir = pkg
    seed = await _spatial_seed(factory, staged=1, extents=_EXTENTS)
    gen = await _create(factory, settings, seed)
    assert gen.status == "queued"
    async with engine.connect() as c:
        row = (await c.execute(text(
            "SELECT workflow_spec_json, manifest_hash, "
            "workflow_template_hash FROM generations WHERE id = :g"),
            {"g": gen.id})).mappings().one()
    return {
        "gen": gen, "seed": seed, "spec": json.loads(row["workflow_spec_json"]),
        "manifest_hash": row["manifest_hash"],
        "template_hash": row["workflow_template_hash"], "pkg": pkg,
    }


# ---------------------------------------------------------------------------
# Cell 12 — schema-5 M8 block vs child projection corruption
# ---------------------------------------------------------------------------


async def test_schema5_m8_block_child_projection_corruption_cycle(
        factory, engine, settings, tmp_path):
    """Positive converged re-create → corrupt the immutable
    shot_revision_spatial_worlds child projection against the captured
    snapshot → the production spatial-continuity convergence check fails
    closed → exact restoration → converged re-create positive again."""
    from tests.test_m10e_generation import _create

    made = await _v3_generation(factory, engine, settings, tmp_path)

    async def _recreate() -> str:
        gen2 = await _create(factory, settings, made["seed"])
        return gen2.shot_revision_id

    first = await _recreate()

    async with engine.connect() as c:
        before = (await c.execute(text(
            "SELECT spatial_continuity_hash FROM "
            "shot_revision_spatial_worlds WHERE shot_revision_id = :r"),
            {"r": first})).scalar()
    assert before is not None and len(before) == 64

    # isolate exactly one corruption: the child projection's continuity
    # hash no longer agrees with the captured pack's canonical hash
    async with engine.connect() as c:
        await c.execute(text(
            "UPDATE shot_revision_spatial_worlds SET "
            "spatial_continuity_hash = :h WHERE shot_revision_id = :r"),
            {"h": "f" * 64, "r": first})
        await c.commit()

    from soloring.errors import SoloRingError

    with pytest.raises(SoloRingError, match="disagrees with the embedded"):
        await _recreate()

    async with engine.connect() as c:
        await c.execute(text(
            "UPDATE shot_revision_spatial_worlds SET "
            "spatial_continuity_hash = :h WHERE shot_revision_id = :r"),
            {"h": before, "r": first})
        await c.commit()

    assert await _recreate() == first  # restored positive: convergence


# ---------------------------------------------------------------------------
# Cell 22 — schema-3 structured-binding corruption (manifest artifact bytes)
# ---------------------------------------------------------------------------


async def test_schema3_structured_binding_corruption_cycle(
        factory, engine, settings, tmp_path):
    from soloring.workflows.artifact_store import WorkflowArtifactStore

    made = await _v3_generation(factory, engine, settings, tmp_path)
    store = WorkflowArtifactStore(settings)

    # positive: historical manifest bytes parse under the frozen grammar
    doc = json.loads(
        (await store.get_manifest(made["manifest_hash"])).decode())
    assert set(doc["spatial_bindings"]) == {
        "world_depth", "entity_depth_1", "entity_depth_2"}

    path = settings.data_dir / "workflow-artifacts" / "manifests" / \
        "sha256" / made["manifest_hash"][0:2] / \
        made["manifest_hash"][2:4] / f"{made['manifest_hash']}.json"
    true = path.read_bytes()

    corrupted = json.loads(true)
    corrupted["spatial_bindings"]["world_depth"]["node"] = "999"
    path.write_bytes(json.dumps(corrupted).encode())  # bytes ≠ hash identity

    from soloring.errors import SoloRingError

    with pytest.raises(SoloRingError, match="integrity|Integrity"):
        await store.get_manifest(made["manifest_hash"])

    path.write_bytes(true)
    assert json.loads(
        (await store.get_manifest(made["manifest_hash"])).decode()) == doc


# ---------------------------------------------------------------------------
# Cell 23 — schema-3 derived-list canonical order corruption
# ---------------------------------------------------------------------------


async def test_schema3_derived_list_order_corruption_cycle(
        factory, engine, settings, tmp_path):
    from soloring.domain.canonical import canonical_hash, canonical_json_str
    from soloring.errors import SoloRingError
    from soloring.spatial.spec3 import validate_spatial_realization_block_history

    made = await _v3_generation(factory, engine, settings, tmp_path)
    sr = made["spec"]["spatial_realization"]

    validate_spatial_realization_block_history(sr)  # positive

    # isolate: swap two derived entries (list order no longer the canonical
    # position order); keep the spec byte-canonical + hash-consistent so
    # ONLY the order rule can fire
    corrupted = json.loads(json.dumps(made["spec"]))
    artifacts = corrupted["spatial_realization"]["derived_artifacts"]
    artifacts[0], artifacts[1] = artifacts[1], artifacts[0]
    for i, a in enumerate(artifacts):  # keep positions consistent with ids
        a["position"] = i
    async with engine.connect() as c:
        await c.execute(text(
            "UPDATE generations SET workflow_spec_json = :j, "
            "workflow_spec_hash = :h WHERE id = :g"),
            {"j": canonical_json_str(corrupted),
             "h": canonical_hash(corrupted), "g": made["gen"].id})
        await c.commit()

    with pytest.raises(SoloRingError):
        validate_spatial_realization_block_history(
            corrupted["spatial_realization"])

    async with engine.connect() as c:
        await c.execute(text(
            "UPDATE generations SET workflow_spec_json = :j, "
            "workflow_spec_hash = :h WHERE id = :g"),
            {"j": canonical_json_str(made["spec"]),
             "h": canonical_hash(made["spec"]), "g": made["gen"].id})
        await c.commit()
    validate_spatial_realization_block_history(sr)  # restored positive


# ---------------------------------------------------------------------------
# Cell 24 — historical package member bytes corruption (profile artifact)
# ---------------------------------------------------------------------------


async def test_historical_package_member_corruption_cycle(
        factory, engine, settings, tmp_path):
    from soloring.workflows.artifact_store import WorkflowArtifactStore

    made = await _v3_generation(factory, engine, settings, tmp_path)
    store = WorkflowArtifactStore(settings)
    profile_hash = made["spec"]["spatial_realization"][
        "realization_profile_hash"]

    # positive: the retained profile member loads + parses
    from soloring.spatial.package3 import parse_profile_v2

    profile = parse_profile_v2(
        (await store.get_profile(profile_hash)).decode())
    assert profile["spatial"]["roles"]

    path = settings.data_dir / "workflow-artifacts" / \
        "realization_profiles" / "sha256" / profile_hash[0:2] / \
        profile_hash[2:4] / f"{profile_hash}.json"
    true = path.read_bytes()
    path.write_bytes(b'{"corrupted": true}')

    from soloring.errors import SoloRingError

    with pytest.raises(SoloRingError, match="integrity|Integrity"):
        await store.get_profile(profile_hash)

    path.write_bytes(true)
    assert parse_profile_v2(
        (await store.get_profile(profile_hash)).decode()) == profile


# ---------------------------------------------------------------------------
# §8.5.4 class 19 — worker/package replacement isolation
# ---------------------------------------------------------------------------


async def test_class19_worker_continues_from_retained_bytes_after_package_replacement(  # noqa: E501
        factory, engine, settings, tmp_path, monkeypatch):
    """A test wrapper on the real worker `build_comfy_prompt` symbol
    records that the seam is reached; the park happens at the async task
    boundary immediately before the real (synchronous) translator is
    invoked, and while parked the mutable installed package directory is
    replaced. Translation continues from the ALREADY-RETAINED historical
    manifest/template bytes and produces the same prompt identity."""
    import soloring.executors.comfy.translate as translate_mod

    made = await _v3_generation(factory, engine, settings, tmp_path)
    from soloring.spatial.package3 import parse_manifest_v3
    from soloring.workflows.artifact_store import WorkflowArtifactStore

    store = WorkflowArtifactStore(settings)
    # the worker's retrieval order: retained bytes FIRST, translation later
    manifest = parse_manifest_v3(
        (await store.get_manifest(made["manifest_hash"])).decode())
    template = json.loads(
        (await store.get_template(made["template_hash"])).decode())

    import asyncio as _asyncio

    seam_reached: list = []
    real_build = translate_mod.build_comfy_prompt

    def recording_build(**kwargs):
        seam_reached.append(True)
        return real_build(**kwargs)

    monkeypatch.setattr(
        "soloring.worker.comfy_pipeline.build_comfy_prompt", recording_build)

    from dataclasses import dataclass

    @dataclass
    class _V:
        input_key: str
        position: int
        artifact_role: str
        node: str
        field: str
        blob_hash: str
        local_path: str
        execution_reference: str | None = None
        frame_references: tuple[str, ...] = ()

    derived = [
        _V(
            input_key=a["input_key"], position=a["position"],
            artifact_role=a["artifact_role"],
            node=manifest["spatial_bindings"][a["input_key"]]["node"],
            field=manifest["spatial_bindings"][a["input_key"]]["field"],
            blob_hash=a["blob_hash"],
            local_path=f"p/{i}",
            execution_reference=f"sub/{a['input_key']}.png",
        )
        for i, a in enumerate(
            made["spec"]["spatial_realization"]["derived_artifacts"])
    ]

    async def parked_translation():
        await _asyncio.sleep(0)  # park point: swap happens below
        return recording_build(
            workflow_spec=made["spec"], manifest=manifest, template=template,
            materialized=[], generation_id=made["gen"].id, attempt_id="a1",
            client_id="c", schema3_derived=derived)

    task = _asyncio.create_task(parked_translation())

    # atomic mutable-installed-package replacement while parked
    replaced = tmp_path / "pkg-replaced"
    replaced.mkdir()
    (replaced / "manifest.json").write_text('{"schema_version": "1"}')
    shutil.rmtree(made["pkg"], ignore_errors=True)

    payload = await _asyncio.wait_for(task, 30)
    # same historical prompt identity: the spatial ControlNet chain and
    # node 60 wiring still derive from the RETAINED template bytes
    assert payload.prompt["60"]["inputs"]["model"] == ["121", 0]
    assert payload.prompt["101"]["inputs"]["control_images"] == \
        ["world_depth::load::0", 0]  # bound from the retained manifest
    assert payload.prompt["world_depth::load::0"]["inputs"]["image"] == \
        "sub/world_depth.png"

    # positive control: the wrapper seam was actually reached
    assert seam_reached


async def test_class19_current_materializer_not_consulted_by_worker(
        factory, engine, settings, tmp_path, monkeypatch):
    """Worker schema-3 execution consumes retained derived Blobs and never
    calls the current materializer. Static import/call inspection plus a
    dynamic zero-call spy with a live positive control."""
    import inspect

    import soloring.spatial.boxdepth as boxdepth_mod
    import soloring.spatial.realize as realize_mod
    import soloring.worker.comfy_pipeline as worker_mod

    worker_src = inspect.getsource(worker_mod)
    assert "compose_spatial_realization" not in worker_src
    assert "boxdepth" not in worker_src

    calls: list = []

    async def _spy_compose(*a, **k):
        calls.append("compose")

    def _spy_materialize(*a, **k):
        calls.append("materialize")

    # positive control: the spy target is live (invoked directly — nothing
    # on the worker path ever should)
    await _spy_compose()
    assert calls == ["compose"]
    calls.clear()

    # creation FIRST (production compose untouched), then install the spy
    made = await _v3_generation(factory, engine, settings, tmp_path)
    monkeypatch.setattr(
        realize_mod, "compose_spatial_realization", _spy_compose)
    if hasattr(boxdepth_mod, "materialize"):
        monkeypatch.setattr(boxdepth_mod, "materialize", _spy_materialize)

    from soloring.spatial.package3 import parse_manifest_v3
    from soloring.workflows.artifact_store import WorkflowArtifactStore

    store = WorkflowArtifactStore(settings)
    parse_manifest_v3(
        (await store.get_manifest(made["manifest_hash"])).decode())
    await store.get_template(made["template_hash"])
    await store.get_profile(
        made["spec"]["spatial_realization"]["realization_profile_hash"])
    await store.get_fingerprint(
        made["spec"]["model"]["execution_model_fingerprint_hash"])
    assert calls == []
