"""M10E corruption matrix (frozen R3 §21) — worker/bind-relevant cells,
each with positive control → isolated corruption → expected fail-closed
class → exact restoration → restored positive control (APR-072).

Cells covered here: 31 (provenance Blob mismatch), 33/34 (physical Blob
missing/corrupt), 36 (sibling artifact/blob composite mismatch), 37
(sibling Project/spatial-continuity mismatch), 38 (role/scope mismatch),
44 (input key mismatch versus manifest/spec). Package-artifact and
descriptor cells live in test_m10e_package3_production.py; composition
cells (pending:/structured/extra/missing/order/collision) live in the
generation + atomic-persistence files; stored-spec tamper detection is
the worker pipeline's canonical-hash precondition (comfy_pipeline
schema-3 branch) and is exercised through the M10A4b harness."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from soloring.assets.blob_store import BlobStore
from soloring.errors import SoloRingError
from soloring.spatial import error_codes as ec
from soloring.spatial.package3 import parse_manifest_v3
from soloring.spatial.worker_inputs import load_verified_derived_inputs

from tests.test_m10a4_worker_rerun import (
    _manifest_doc,
    _seed_spatial_generation,
    _spec,
)


async def _verify(factory, settings, ids):
    async with factory() as session:
        return await load_verified_derived_inputs(
            session, BlobStore(settings),
            generation_id=ids["generation_id"],
            workflow_spec=_spec(ids["continuity"]),
            manifest_v3=_manifest_doc())


async def _update(engine, sql, params):
    async with engine.connect() as conn:
        await conn.execute(text(sql), params)
        await conn.commit()


async def _restore_spatial_row(engine, ids):
    await _update(
        engine,
        "UPDATE derived_spatial_artifacts SET project_id = :p, "
        "spatial_continuity_hash = :c, blob_hash = :b WHERE id = :a",
        {"p": ids["project"], "c": ids["continuity"],
         "b": ids["blob"], "a": ids["artifact"]})


async def test_cell31_provenance_blob_mismatch(factory, engine, settings):
    """Cell 31 is enforced STRUCTURALLY by migration 0011's composite FK
    (derived_spatial_artifacts.blob_hash ↔ siblings/blobs): a tampering
    update cannot even be applied — the positive control stays valid."""
    from sqlalchemy.exc import IntegrityError

    ids = await _seed_spatial_generation(factory, engine, settings)
    assert len(await _verify(factory, settings, ids)) == 1  # positive
    with pytest.raises(IntegrityError):
        await _update(
            engine,
            "UPDATE derived_spatial_artifacts SET blob_hash = :b "
            "WHERE id = :a",
            {"b": "ff" * 32, "a": ids["artifact"]})
    assert len(await _verify(factory, settings, ids)) == 1  # unchanged


async def test_cell33_physical_blob_missing(factory, engine, settings):
    ids = await _seed_spatial_generation(factory, engine, settings)
    assert len(await _verify(factory, settings, ids)) == 1
    path = BlobStore(settings).path_for_hash(ids["blob"])
    saved = path.read_bytes()
    path.unlink()
    try:
        with pytest.raises(SoloRingError) as ei:
            await _verify(factory, settings, ids)
        assert ei.value.code == ec.DERIVED_SPATIAL_BLOB_MISSING
    finally:
        path.write_bytes(saved)
    assert len(await _verify(factory, settings, ids)) == 1


async def test_cell34_physical_blob_corrupt(factory, engine, settings):
    ids = await _seed_spatial_generation(factory, engine, settings)
    assert len(await _verify(factory, settings, ids)) == 1
    path = BlobStore(settings).path_for_hash(ids["blob"])
    saved = path.read_bytes()
    path.write_bytes(b"corrupted!")
    try:
        with pytest.raises(SoloRingError) as ei:
            await _verify(factory, settings, ids)
        assert ei.value.code == ec.DERIVED_SPATIAL_BLOB_CORRUPT
    finally:
        path.write_bytes(saved)
    assert len(await _verify(factory, settings, ids)) == 1


async def test_cell36_sibling_composite_mismatch(factory, engine,
                                                 settings):
    """Cell 36 is enforced STRUCTURALLY by the sibling composite FK
    (derived_spatial_artifact_id, blob_hash): the tampering update is
    rejected by the storage layer itself."""
    from sqlalchemy.exc import IntegrityError

    ids = await _seed_spatial_generation(factory, engine, settings)
    assert len(await _verify(factory, settings, ids)) == 1
    with pytest.raises(IntegrityError):
        await _update(
            engine,
            "UPDATE generation_derived_spatial_inputs SET blob_hash = :b "
            "WHERE generation_id = :g",
            {"b": "ee" * 32, "g": ids["generation_id"]})
    assert len(await _verify(factory, settings, ids)) == 1


async def test_cell37_project_continuity_mismatch(factory, engine,
                                                  settings):
    ids = await _seed_spatial_generation(factory, engine, settings)
    assert len(await _verify(factory, settings, ids)) == 1
    await _update(
        engine,
        "UPDATE derived_spatial_artifacts SET spatial_continuity_hash = "
        ":c WHERE id = :a",
        {"c": "ef" * 32, "a": ids["artifact"]})
    try:
        with pytest.raises(SoloRingError) as ei:
            await _verify(factory, settings, ids)
        assert ei.value.code == ec.DERIVED_SPATIAL_PROVENANCE_MISMATCH
    finally:
        await _restore_spatial_row(engine, ids)
    assert len(await _verify(factory, settings, ids)) == 1


async def test_cell38_role_scope_mismatch(factory, engine, settings):
    """Cell 38 (sibling role vs artifact scope) is owned by the ATOMIC
    PERSISTENCE validator (M10E §15.2): a world-role sibling bound to an
    entity-scope artifact fails inside the write unit and rolls the whole
    Generation back."""
    from soloring.generation import repository as repo
    from soloring.generation.drafts import GenerationDraft
    from soloring.generation.enums import GenerationOperation
    from soloring.spatial.derived_inputs import DerivedInputBinding

    from tests.test_m10e_atomic_persistence import (
        _E1,
        _bindings,
        _draft,
        _seed_world_rows,
    )

    seed = await _seed_world_rows(factory, engine, settings,
                                  entities=[_E1])
    bindings = list(_bindings(seed))
    # bind the position-0 WORLD role to the ENTITY-scope artifact: the
    # frozen coordinate validator passes (still 1 world + 1 entity role),
    # and the role/scope agreement check inside the write unit fires.
    bindings[0] = DerivedInputBinding(
        input_key=bindings[0].input_key, position=0,
        artifact_role="spatial.world_depth",
        derived_spatial_artifact_id=seed["entities"][0][0],
        blob_hash=seed["entities"][0][1])
    async with factory() as session:
        with pytest.raises(SoloRingError) as ei:
            await repo.create_generation(
                session, _draft(seed), (), derived_inputs=tuple(bindings))
    assert ei.value.code == ec.DERIVED_SPATIAL_BINDING_INVALID
    async with engine.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM generations"))).scalar()
    assert n == 0


async def test_cell44_input_key_mismatch_vs_manifest(factory, engine,
                                                     settings):
    ids = await _seed_spatial_generation(factory, engine, settings)
    assert len(await _verify(factory, settings, ids)) == 1
    await _update(
        engine,
        "UPDATE generation_derived_spatial_inputs SET input_key = 'other' "
        "WHERE generation_id = :g",
        {"g": ids["generation_id"]})
    try:
        with pytest.raises(SoloRingError) as ei:
            await _verify(factory, settings, ids)
        assert ei.value.code == ec.DERIVED_SPATIAL_BINDING_INVALID
    finally:
        await _update(
            engine,
            "UPDATE generation_derived_spatial_inputs SET input_key = "
            "'world_depth' WHERE generation_id = :g",
            {"g": ids["generation_id"]})
    assert len(await _verify(factory, settings, ids)) == 1
