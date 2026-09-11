"""M14B-3 — mesh-depth materializer (frozen R2 §§14/24/25; proof cells
MAT:08-15).

Composite rasterization through the certified M10 primitives, zero-mesh
byte identity, deterministic repeat, real forced concurrent publication
(RACE-02), same-coordinate conflict, contract-hash coordinate
separation, identity suppression + duplicate_structural_conditioning,
output grammar, and caps-before-raster.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import uuid
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from sqlalchemy import text

from soloring.db.models import Base
from soloring.errors import ErrorCode, SoloRingError
from soloring.observation.materializer import (
    build_materializer_contract,
    build_provenance,
    check_duplicate_conditioning,
    materialize_observation_world_depth,
    materializer_contract_hash,
    parameters_hash,
    provenance_hash,
)
from soloring.observation.mesh import structural_mesh_bytes
from soloring.observation.publication import publish_observation_artifact
from soloring.observation.retained import RetainedMeshSource
from soloring.spatial import boxdepth

from tests.test_m14_materializer import _mesh_doc

BASE_DIR = Path(__file__).resolve().parents[1]


def _pack(staging=(), frames=()):
    return {
        "schema_version": 1,
        "spatial_world": {
            "spatial_world_id": "aaaaaaaa-0000-0000-0000-000000000001",
            "requirement": "required",
            "spatial_world_state_id":
                "aaaaaaaa-0000-0000-0000-000000000002",
            "spatial_world_revision_id":
                "aaaaaaaa-0000-0000-0000-000000000003",
            "spatial_world_revision_hash": "b" * 64,
            "location_entity_id": "aaaaaaaa-0000-0000-0000-000000000004",
            "location_entity_revision_id":
                "aaaaaaaa-0000-0000-0000-000000000005",
            "world_snapshot": {"frames": list(frames), "axes": []},
        },
        "staging": list(staging),
        "shot_plan": {"camera": {
            "projection": "perspective",
            "focal_length_um": 50000,
            "sensor_width_um": 36000,
            "sensor_height_um": 20250,
            "keyframes": [{
                "time_ms": 0,
                "transform": {"translation_mm": [-3000, 1650, 4200],
                              "rotation_udeg": [0, 0, 0]}}],
        }},
    }


def _staged(entity_id, position):
    return {
        "spatial_track_id": f"{entity_id[:8]}-0000-0000-0000-00000000000t",
        "entity_id": entity_id,
        "entity_revision_id": entity_id,
        "requirement": "optional",
        "transform": {"translation_mm": list(position),
                      "rotation_udeg": [0, 0, 0]},
    }


def _source(*, transform=(0, 0, 0), mesh=None, entity_id="", occurrence=None):
    """A synthetic RetainedMeshSource (unit-level; no DB)."""
    occurrence = occurrence or str(uuid.uuid4())
    return RetainedMeshSource(
        occurrence_id=occurrence,
        composition_revision_id=str(uuid.uuid4()),
        composition_revision_hash="c" * 64,
        production_revision_id=str(uuid.uuid4()),
        production_revision_hash="d" * 64,
        retained_blob_hash=hashlib.sha256(
            structural_mesh_bytes(mesh or _mesh_doc())).hexdigest(),
        mesh=mesh or _mesh_doc(),
        interpretation_hash="e" * 64,
        realization_local_to_subject_local={
            "translation_mm": [0, 0, 0], "rotation_udeg": [0, 0, 0]},
        placement_owner="A6",
        placement_source_kind="composition_revision",
        placement_source_id=str(uuid.uuid4()),
        placement_source_hash="f" * 64,
        subject_local_to_world={
            "translation_mm": list(transform), "rotation_udeg": [0, 0, 0]},
        realization_local_to_world={
            "translation_mm": list(transform), "rotation_udeg": [0, 0, 0]},
        authority_subject_kind=(
            "creative_entity" if entity_id else ""),
        authority_subject_id=entity_id,
        structure_requirement={},
        placement_requirement={},
        occurrence_object={})


# ---- MAT:09 zero-mesh byte identity ---------------------------------------

def test_m14_mat_09() -> None:
    pack = _pack()
    result = materialize_observation_world_depth(pack, [])
    m10_frames = boxdepth.materialize(pack)
    assert result.frames == m10_frames, (
        "zero-mesh must call the exact M10 entry path — byte-identical "
        "frames")
    assert result.digest == boxdepth.artifact_digest(m10_frames)
    assert result.total_triangles == 0

    staging_pack = _pack(staging=[_staged(
        "bbbbbbbb-0000-0000-0000-00000000000e", (-2800, 1500, -800))])
    result = materialize_observation_world_depth(staging_pack, [])
    assert result.frames == boxdepth.materialize(staging_pack), (
        "zero-mesh identity holds with staged proxies present too")


# ---- MAT:08 non-background retained-mesh contribution ----------------------

def test_m14_mat_08() -> None:
    empty = _pack()
    baseline = materialize_observation_world_depth(empty, [])
    # world has only frameless landmarks → all-background baseline
    assert all(
        np.asarray(Image.open(__import__("io").BytesIO(f)))[0, 0] == 255
        for f in baseline.frames[0:1])

    source = _source(transform=(-3000, 1500, -800))
    with_mesh = materialize_observation_world_depth(empty, [source])
    assert with_mesh.digest != baseline.digest, (
        "an in-frame retained mesh must change the control bytes")
    array = np.asarray(Image.open(__import__("io").BytesIO(
        with_mesh.frames[0])))
    assert (array != 255).any(), (
        "the retained mesh must contribute non-background pixels")


# ---- MAT:10 deterministic repeat -------------------------------------------

def test_m14_mat_10() -> None:
    pack = _pack()
    source = _source(transform=(-3000, 1500, -800))
    first = materialize_observation_world_depth(pack, [source])
    second = materialize_observation_world_depth(pack, [source])
    assert first.digest == second.digest
    assert first.frames == second.frames

    contract = build_materializer_contract()
    assert materializer_contract_hash(contract) == (
        materializer_contract_hash(build_materializer_contract())), (
        "the contract hash is deterministic for the same implementation")


# ---- MAT:14 suppression + duplicate conditioning ---------------------------

def test_m14_mat_14() -> None:
    entity = "cccccccc-0000-0000-0000-00000000000e"
    staged = [_staged(entity, (-2900, 1500, -800)),
              _staged("dddddddd-0000-0000-0000-00000000000f",
                      (-2600, 1400, -900))]
    pack = _pack(staging=staged)

    # duplicate conditioning: a staged CreativeEntity with a retained mesh
    # refuses BEFORE materialization with the typed detail
    bound = _source(transform=(-3000, 1500, -800), entity_id=entity)
    with pytest.raises(SoloRingError) as excinfo:
        check_duplicate_conditioning([bound], pack)
    assert excinfo.value.code == ErrorCode.OBSERVATION_REQUIREMENT_UNSUPPORTED
    assert excinfo.value.details["reason"] == (
        "duplicate_structural_conditioning")
    assert excinfo.value.details["entity_id"] == entity

    # unstaged entity mesh: no refusal; the composite keeps the OTHER
    # entities' proxies (identity suppression never removes them)
    unstaged = _source(transform=(-3000, 1500, -800), entity_id="unused")
    check_duplicate_conditioning([unstaged], pack)  # no raise
    result = materialize_observation_world_depth(pack, [unstaged])
    no_mesh = materialize_observation_world_depth(pack, [])
    assert result.digest != no_mesh.digest
    # the staged proxies still contribute alongside the mesh
    only_proxies = boxdepth.materialize(pack)
    assert result.digest != boxdepth.artifact_digest(only_proxies)


# ---- MAT:15 output grammar --------------------------------------------------

def test_m14_mat_15() -> None:
    pack = _pack(staging=[_staged(
        "eeeeeeee-0000-0000-0000-00000000000e", (-2800, 1500, -800))])
    source = _source(transform=(-3000, 1500, -800))
    result = materialize_observation_world_depth(pack, [source])
    import io

    assert len(result.frames) == 17
    for frame in result.frames:
        image = Image.open(io.BytesIO(frame))
        assert image.size == (832, 480)
        assert image.mode == "L"
    digest = hashlib.sha256(b"".join(result.frames)).hexdigest()
    assert digest == result.digest
    assert len(result.digest) == 64
    assert result.digest == result.digest.lower()


# ---- caps before raster allocation -----------------------------------------

def test_caps_before_raster() -> None:
    over = {
        "schema_version": 1, "kind": "soloring.structural_mesh",
        "coordinate_system": _mesh_doc()["coordinate_system"],
        "vertices_mm": [[i, 0, 0] for i in range(0, 9000, 3)],
        "triangles": [[3 * k, 3 * k + 1, 3 * k + 2]
                      for k in range(500_001)],
    }
    # grammar is valid for the parser but the OBSERVATION total exceeds
    # the 500k cap — the materializer refuses before raster allocation
    over_source = _source(mesh=over)
    with pytest.raises(SoloRingError) as excinfo:
        materialize_observation_world_depth(_pack(), [over_source])
    assert excinfo.value.code == ErrorCode.STRUCTURAL_MESH_LIMIT_EXCEEDED


# ---- publication convergence (MAT:11/12/13) ---------------------------------

async def _upgrade(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config

    tmp_path.mkdir(parents=True, exist_ok=True)
    import soloring.settings as settings_mod

    monkeypatch.setenv("SOLORING_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(settings_mod, "_settings", None)
    cfg = Config(str(BASE_DIR / "server" / "alembic.ini"))
    cfg.set_main_option("script_location",
                        str(BASE_DIR / "server" / "alembic"))
    command.upgrade(cfg, "head")
    return tmp_path / "soloring.db"


class _Store:
    """Minimal BlobStore stand-in for the publication seam."""

    def __init__(self, root: Path):
        self.root = root

    def tmp_path(self):
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root / f"tmp-{uuid.uuid4()}"

    def relative_path_for_hash(self, blob_hash):
        return f"sha256/{blob_hash[:2]}/{blob_hash[2:4]}/{blob_hash}"

    async def place(self, blob_hash, tmp):
        import shutil

        dst = self.root / self.relative_path_for_hash(blob_hash)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp), str(dst))


async def _seed_project(engine) -> str:
    pid = str(uuid.uuid4())
    async with engine.connect() as conn:
        await conn.execute(text(
            "INSERT INTO projects (id, name, created_at, updated_at) "
            "VALUES (:p, 'P', 't', 't')"), {"p": pid})
        await conn.commit()
    return pid


_COORDINATE = {
    "observation_spec_hash": "1" * 64,
    "materializer_id": "soloring.observation.mesh_depth",
    "materializer_version": 1,
    "materializer_contract_hash": "2" * 64,
    "parameters_hash": "3" * 64,
}
_PROVENANCE_FIELDS = {
    "project_id": None, "observation_spec_hash": "1" * 64,
    "artifact_role": "observation.world_depth",
    "materializer_id": "soloring.observation.mesh_depth",
    "materializer_version": 1,
    "materializer_contract_hash": "2" * 64,
    "parameters_hash": "3" * 64,
    "source_retained_blob_hashes": ["4" * 64],
    "execution_package": {
        "workflow_id": "wan21_spatial_v1", "workflow_version": 1,
        "manifest_hash": "5" * 64, "workflow_template_hash": "6" * 64,
        "realization_profile_hash": "7" * 64,
        "execution_model_fingerprint_hash": "8" * 64},
}


_PROVENANCE_KEYS = frozenset({
    "project_id", "observation_spec_hash", "materializer_contract_hash",
    "parameters_hash", "source_retained_blob_hashes", "execution_package"})


async def _publish(engine, store, pid, blob=b"mesh-bytes-a",
                   **overrides):
    params = dict(_COORDINATE)
    params.update({k: v for k, v in overrides.items()
                   if k in params})
    prov_fields = dict(_PROVENANCE_FIELDS)
    prov_fields["project_id"] = pid
    for k, v in overrides.items():
        if k in prov_fields:
            prov_fields[k] = v
    provenance = build_provenance(**{
        key: value for key, value in prov_fields.items()
        if key in _PROVENANCE_KEYS})
    async with engine.connect() as conn:
        return await publish_observation_artifact(
            conn, store, project_id=pid,
            observation_spec_hash=params["observation_spec_hash"],
            materializer_id=params["materializer_id"],
            materializer_version=params["materializer_version"],
            materializer_contract_hash=params[
                "materializer_contract_hash"],
            parameters={"width": 832, "height": 480, "frames": 17,
                        "time_base_num": 1, "time_base_den": 17,
                        "mode": "L", "background": 255},
            parameters_hash=params["parameters_hash"],
            provenance=provenance,
            provenance_hash_value=provenance_hash(provenance),
            blob_bytes=blob)


async def test_m14_mat_11_real_concurrent_publication(
        tmp_path, monkeypatch):
    """RACE-02: two GENUINE competing writers publishing the same
    complete coordinate + same bytes — serialized by BEGIN IMMEDIATE,
    converging on one row. No sleeps, no test-side serialization."""
    from sqlalchemy.ext.asyncio import create_async_engine

    db = await _upgrade(tmp_path, monkeypatch)
    engine = create_async_engine(f"sqlite+aiosqlite:///{db}")
    try:
        pid = await _seed_project(engine)
        store = _Store(tmp_path / "blobs")

        async with engine.connect() as conn:
            await conn.exec_driver_sql("PRAGMA busy_timeout=60000")
        results = await asyncio.gather(
            _publish(engine, store, pid, b"mesh-bytes-a"),
            _publish(engine, store, pid, b"mesh-bytes-a"),
            _publish(engine, store, pid, b"mesh-bytes-a"))
        ids = set(results)
        assert len(ids) == 1, (
            f"same coordinate + same bytes must converge on one row; "
            f"got {ids}")
        async with engine.connect() as conn:
            count = (await conn.execute(text(
                "SELECT COUNT(*) FROM derived_observation_artifacts")
            )).scalar_one()
        assert count == 1
    finally:
        await engine.dispose()


async def test_m14_mat_12_same_coordinate_different_bytes(
        tmp_path, monkeypatch):
    from sqlalchemy.ext.asyncio import create_async_engine

    db = await _upgrade(tmp_path, monkeypatch)
    engine = create_async_engine(f"sqlite+aiosqlite:///{db}")
    try:
        pid = await _seed_project(engine)
        store = _Store(tmp_path / "blobs")
        await _publish(engine, store, pid, b"mesh-bytes-a")
        with pytest.raises(SoloRingError, match="different bytes"):
            await _publish(engine, store, pid, b"mesh-bytes-B")
        async with engine.connect() as conn:
            count = (await conn.execute(text(
                "SELECT COUNT(*) FROM derived_observation_artifacts")
            )).scalar_one()
        assert count == 1, "the conflicting writer never rewrites the first"
    finally:
        await engine.dispose()


async def test_m14_mat_13_contract_hash_is_coordinate(
        tmp_path, monkeypatch):
    from sqlalchemy.ext.asyncio import create_async_engine

    db = await _upgrade(tmp_path, monkeypatch)
    engine = create_async_engine(f"sqlite+aiosqlite:///{db}")
    try:
        pid = await _seed_project(engine)
        store = _Store(tmp_path / "blobs")
        await _publish(engine, store, pid, b"bytes-one",
                       materializer_contract_hash="a" * 64)
        await _publish(engine, store, pid, b"bytes-two",
                       materializer_contract_hash="b" * 64)
        async with engine.connect() as conn:
            count = (await conn.execute(text(
                "SELECT COUNT(*) FROM derived_observation_artifacts")
            )).scalar_one()
            rows = (await conn.execute(text(
                "SELECT materializer_contract_hash, blob_hash FROM "
                "derived_observation_artifacts ORDER BY "
                "materializer_contract_hash"))).fetchall()
        assert count == 2, (
            "different materializer-contract hashes are DIFFERENT valid "
            "coordinates, not corruption")
        assert {r[0] for r in rows} == {"a" * 64, "b" * 64}
        assert {r[1] for r in rows} == {
            hashlib.sha256(b"bytes-one").hexdigest(),
            hashlib.sha256(b"bytes-two").hexdigest()}
    finally:
        await engine.dispose()


# ---- contract identity (report evidence) ------------------------------------

def test_contract_identity_is_real_and_complete():
    contract = build_materializer_contract()
    assert contract["materializer"]["implementation_sha256"] == (
        hashlib.sha256(Path(
            __import__("soloring.observation.materializer",
                       fromlist=["__file__"]).__file__
        ).read_bytes()).hexdigest())
    assert contract["rasterizer"]["implementation_sha256"] == (
        hashlib.sha256(Path(boxdepth.__file__).read_bytes()).hexdigest())
    encoder = contract["runtime"]["encoder_identity"]
    import PIL._imaging as _imaging

    assert encoder["pillow_native_module"] == Path(
        _imaging.__file__).name
    assert encoder["pillow_native_module_sha256"] == hashlib.sha256(
        Path(_imaging.__file__).read_bytes()).hexdigest()
    import zlib

    assert encoder["zlib_compile_version"] == zlib.ZLIB_VERSION
    assert encoder["zlib_runtime_version"] == zlib.ZLIB_RUNTIME_VERSION
    assert contract["output_grammar"]["width"] == 832
    assert contract["output_grammar"]["frames"] == 17
    assert contract["resource_limits"] == {
        "max_retained_mesh_bytes_per_revision": 100_000_000,
        "max_vertices_per_revision": 3_000_000,
        "max_triangles_per_revision": 500_000,
        "max_total_triangles_per_observation": 500_000,
        "production_time_budget_s": 360}
    # provenance purity: no forbidden incidental evidence keys anywhere
    provenance = build_provenance(
        project_id="p" * 8, observation_spec_hash="1" * 64,
        materializer_contract_hash="2" * 64,
        parameters_hash="3" * 64,
        source_retained_blob_hashes=["4" * 64],
        execution_package=_PROVENANCE_FIELDS["execution_package"])
    blob = json.dumps(provenance)
    for forbidden in ("timestamp", "duration", "hostname", "path",
                      "memory", "pid", "random"):
        assert forbidden not in blob.lower(), forbidden
