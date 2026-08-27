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
            workflow_spec=_spec(ids["continuity"], ids),
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

    from tests.test_m10e_atomic_persistence import (
        _E1,
        _bindings,
        _draft,
        _seed_world_rows,
    )

    seed = await _seed_world_rows(factory, engine, settings,
                                  entities=[_E1])
    async with factory() as session:
        good = await repo.create_generation(
            session, _draft(seed), (), derived_inputs=_bindings(seed))
    assert good.status == 'queued'  # positive control

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
    # the corrupt write rolled back; the positive control remains and a
    # fresh valid create succeeds again (restored positive)
    assert n == 1
    async with factory() as session:
        good2 = await repo.create_generation(
            session, _draft(seed), (), derived_inputs=_bindings(seed))
    assert good2.status == "queued"


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


# --------------------------------- E-106 B3 round: cells 20/21/37 + 3b ----

async def test_cell20_noncanonical_stored_spec_bytes_rejected():
    """Cell 20 via the REAL production check: semantically equal but
    noncanonical (key-reordered) stored WorkflowSpec bytes fail closed;
    the canonical positive control passes."""
    from soloring.errors import ErrorCode, SoloRingError
    from soloring.worker.comfy_pipeline import (
        _verify_schema3_stored_spec_canonical,
    )

    spec = {"schema_version": 3, "b": 2, "a": 1}
    import json as _json

    noncanonical = _json.dumps(spec, indent=2)  # same object, not canonical
    with pytest.raises(SoloRingError) as ei:
        _verify_schema3_stored_spec_canonical(spec, noncanonical)
    assert ei.value.code == ErrorCode.INTERNAL_INVARIANT_VIOLATION
    reordered = _json.dumps({"a": 1, "b": 2, "schema_version": 3})
    with pytest.raises(SoloRingError):
        _verify_schema3_stored_spec_canonical(spec, reordered)
    from soloring.domain.canonical import canonical_json_str

    _verify_schema3_stored_spec_canonical(
        spec, canonical_json_str(spec))  # positive control


async def test_cell21_pending_identity_in_workflow_spec_rejected(
        factory, engine, settings):
    ids = await _seed_spatial_generation(factory, engine, settings)
    assert len(await _verify(factory, settings, ids)) == 1
    spec = _spec(ids["continuity"], ids)
    spec["spatial_realization"]["derived_artifacts"][0][
        "derived_spatial_artifact_id"] = "pending:" + "a" * 16
    async with factory() as session:
        with pytest.raises(SoloRingError) as ei:
            await load_verified_derived_inputs(
                session, BlobStore(settings),
                generation_id=ids["generation_id"], workflow_spec=spec,
                manifest_v3=_manifest_doc())
    # the STRICT history validator fires first (semantic identity
    # violation) — either closed class is fail-closed per §20
    from soloring.errors import ErrorCode as _EC

    assert ei.value.code in (
        ec.DERIVED_SPATIAL_PROVENANCE_MISMATCH,
        _EC.SPATIAL_REALIZATION_BINDING_INVALID)
    # restored positive: the untampered spec verifies again
    assert len(await _verify(factory, settings, ids)) == 1


async def test_cell37_project_ownership_mismatch(factory, engine, settings):
    """The Project half of cell 37: an artifact owned by ANOTHER Project
    (continuity hash still matching) is rejected by the worker verifier."""
    import uuid

    ids = await _seed_spatial_generation(factory, engine, settings)
    assert len(await _verify(factory, settings, ids)) == 1
    other = str(uuid.uuid4())
    await _update(
        engine,
        "INSERT INTO projects (id, name, created_at, updated_at) "
        "VALUES (:p, 'Other', 't', 't')", {"p": other})
    await _update(
        engine,
        "UPDATE derived_spatial_artifacts SET project_id = :p "
        "WHERE id = :a",
        {"p": other, "a": ids["artifact"]})
    try:
        with pytest.raises(SoloRingError) as ei:
            await _verify(factory, settings, ids)
        assert ei.value.code == ec.DERIVED_SPATIAL_PROVENANCE_MISMATCH
    finally:
        await _update(
            engine,
            "UPDATE derived_spatial_artifacts SET project_id = :p "
            "WHERE id = :a", {"p": ids["project"], "a": ids["artifact"]})
    assert len(await _verify(factory, settings, ids)) == 1


async def test_cell3b_spec_claims_forked_identity(factory, engine,
                                                  settings):
    """E-106 B3b: a WorkflowSpec entry claiming a DIFFERENT artifact/blob
    identity than the sibling row (the spec/execution fork) fails closed."""
    ids = await _seed_spatial_generation(factory, engine, settings)
    assert len(await _verify(factory, settings, ids)) == 1
    spec = _spec(ids["continuity"], ids)
    spec["spatial_realization"]["derived_artifacts"][0][
        "derived_spatial_artifact_id"] = str(_new_uuid())
    async with factory() as session:
        with pytest.raises(SoloRingError) as ei:
            await load_verified_derived_inputs(
                session, BlobStore(settings),
                generation_id=ids["generation_id"], workflow_spec=spec,
                manifest_v3=_manifest_doc())
    assert ei.value.code == ec.DERIVED_SPATIAL_PROVENANCE_MISMATCH

    spec = _spec(ids["continuity"], ids)
    spec["spatial_realization"]["derived_artifacts"][0][
        "blob_hash"] = "cd" * 32
    async with factory() as session:
        with pytest.raises(SoloRingError) as ei:
            await load_verified_derived_inputs(
                session, BlobStore(settings),
                generation_id=ids["generation_id"], workflow_spec=spec,
                manifest_v3=_manifest_doc())
    assert ei.value.code == ec.DERIVED_SPATIAL_PROVENANCE_MISMATCH

    spec = _spec(ids["continuity"], ids)
    spec["spatial_realization"]["derived_artifacts"][0][
        "runtime_fingerprint_hash"] = "ce" * 32
    async with factory() as session:
        with pytest.raises(SoloRingError) as ei:
            await load_verified_derived_inputs(
                session, BlobStore(settings),
                generation_id=ids["generation_id"], workflow_spec=spec,
                manifest_v3=_manifest_doc())
    assert ei.value.code == ec.DERIVED_SPATIAL_PROVENANCE_MISMATCH


def _new_uuid() -> str:
    import uuid

    return uuid.uuid4()


# ---------------------- remaining §21 cells for the exact 53-cell map -------


# --------------------------------------------------------------- append ----

async def test_cells3to5_descriptor_hash_disagreements(settings, tmp_path):
    """Cells 3/4/5 — full five-step E-080 cycle: positive capture ->
    member tamper -> PackageIntegrity -> exact byte restoration ->
    restored positive capture."""
    from soloring.realization.packages import (
        PackageIntegrity,
        capture_current_release,
    )
    from tests.test_m10e_package3_production import _schema3_package, \
        _settings_for

    for member in ("workflow.json", "realization-profile.json",
                   "execution-model-fingerprint.json"):
        d = await _schema3_package(tmp_path / member.replace(".", "_"))
        # positive control
        release = await capture_current_release(
            _settings_for(settings, d))
        assert release.schema_version == 3
        original = (d / member).read_bytes()
        tampered = bytearray(original)
        tampered[-8:] = b"tampered"
        (d / member).write_bytes(bytes(tampered))
        with pytest.raises(PackageIntegrity):
            await capture_current_release(_settings_for(settings, d))
        # exact restoration -> restored positive control
        (d / member).write_bytes(original)
        release2 = await capture_current_release(
            _settings_for(settings, d))
        assert release2.manifest_hash == release.manifest_hash


def test_cells13_15_manifest_grammar_corruptions():
    """Cells 13/15 — five-step cycles at the frozen parser seam: valid
    document (positive) -> isolated corruption -> Package3Invalid ->
    restoration (fresh valid copy) -> restored positive."""
    import json as _json

    from soloring.spatial.package3 import Package3Invalid, parse_manifest_v3

    base = {
        "schema_version": "3", "version": 1, "workflow_id": "wf",
        "inputs": {"world_depth": {}}, "parameters": {}, "outputs": {},
        "spatial_bindings": {
            "world_depth": {"artifact_role": "spatial.world_depth",
                            "node": "101", "field": "control_images",
                            "format": "soloring.spatial.v1"}}}

    # positive control
    assert parse_manifest_v3(
        _json.loads(_json.dumps(base)))["schema_version"] == "3"

    # cell 13: unknown spatial role
    bad_role = _json.loads(_json.dumps(base))
    bad_role["spatial_bindings"]["world_depth"]["artifact_role"] = \
        "spatial.bogus"
    with pytest.raises(Package3Invalid, match="artifact_role"):
        parse_manifest_v3(bad_role)
    # restored positive (fresh untampered copy)
    assert parse_manifest_v3(_json.loads(_json.dumps(base))) is not None

    # cell 15: three entity bindings (capacity 2 exceeded)
    dup = _json.loads(_json.dumps(base))
    for key, node in (("e1", "111"), ("e2", "121"), ("e3", "131")):
        dup["inputs"][key] = {}
        dup["spatial_bindings"][key] = {
            "artifact_role": "spatial.entity_depth", "node": node,
            "field": "control_images", "format": "soloring.spatial.v1"}
    with pytest.raises(Package3Invalid, match="entity_depth"):
        parse_manifest_v3(dup)
    # restored positive
    assert parse_manifest_v3(_json.loads(_json.dumps(base))) is not None


async def test_cell32_blob_db_row_missing(factory, engine, settings):
    """Cell 32 is enforced STRUCTURALLY by the sibling→blobs FK
    (migration 0011 fk_gdsi_blob): deleting the Blob DB row while the
    sibling references it is rejected by the storage layer itself."""
    from sqlalchemy.exc import IntegrityError

    ids = await _seed_spatial_generation(factory, engine, settings)
    assert len(await _verify(factory, settings, ids)) == 1
    with pytest.raises(IntegrityError):
        await _update(engine, "DELETE FROM blobs WHERE hash = :h",
                      {"h": ids["blob"]})
    assert len(await _verify(factory, settings, ids)) == 1


async def test_cells39_40_sibling_coordinate_violations(factory, engine,
                                                        settings):
    """Cells 39/40: world stream not at position zero / non-contiguous
    positions — the frozen coordinate validator fails the whole write
    unit."""
    from soloring.generation import repository as repo
    from soloring.spatial.derived_inputs import DerivedInputBinding
    from soloring.spatial.error_codes import DERIVED_SPATIAL_BINDING_INVALID

    from tests.test_m10e_atomic_persistence import (
        _E1,
        _draft,
        _seed_world_rows,
    )

    seed = await _seed_world_rows(factory, engine, settings,
                                  entities=[_E1])
    good = list(_bindings_for(seed))
    from soloring.generation import repository as _repo

    async with factory() as session:
        ok = await _repo.create_generation(
            session, _draft(seed), (), derived_inputs=tuple(good))
    assert ok.status == "queued"  # positive control

    swapped = [
        DerivedInputBinding(input_key=good[0].input_key, position=1,
                            artifact_role=good[0].artifact_role,
                            derived_spatial_artifact_id=(
                                good[0].derived_spatial_artifact_id),
                            blob_hash=good[0].blob_hash),
        DerivedInputBinding(input_key=good[1].input_key, position=0,
                            artifact_role=good[1].artifact_role,
                            derived_spatial_artifact_id=(
                                good[1].derived_spatial_artifact_id),
                            blob_hash=good[1].blob_hash)]
    async with factory() as session:
        with pytest.raises(SoloRingError) as ei:
            await repo.create_generation(
                session, _draft(seed), (), derived_inputs=tuple(swapped))
    assert ei.value.code == DERIVED_SPATIAL_BINDING_INVALID

    gapped = [
        good[0],
        DerivedInputBinding(input_key=good[1].input_key, position=2,
                            artifact_role=good[1].artifact_role,
                            derived_spatial_artifact_id=(
                                good[1].derived_spatial_artifact_id),
                            blob_hash=good[1].blob_hash)]
    async with factory() as session:
        with pytest.raises(SoloRingError) as ei:
            await repo.create_generation(
                session, _draft(seed), (), derived_inputs=tuple(gapped))
    assert ei.value.code == DERIVED_SPATIAL_BINDING_INVALID
    async with engine.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM generations"))).scalar()
    assert n == 1  # only the positive control survived the rollbacks
    async with factory() as session:
        ok2 = await _repo.create_generation(
            session, _draft(seed), (), derived_inputs=tuple(good))
    assert ok2.status == "queued"  # restored positive


def _bindings_for(seed):
    from tests.test_m10e_atomic_persistence import _bindings

    return _bindings(seed)


async def test_cells42_43_extra_missing_sibling_vs_spec(factory, engine,
                                                        settings):
    """Cells 42/43: extra/missing sibling rows versus the WorkflowSpec
    fail closed at the worker's spec<->row set check."""
    ids = await _seed_spatial_generation(factory, engine, settings)
    assert len(await _verify(factory, settings, ids)) == 1

    await _update(
        engine,
        "INSERT INTO generation_derived_spatial_inputs (generation_id, "
        "input_key, position, artifact_role, "
        "derived_spatial_artifact_id, blob_hash) VALUES (:g, "
        "'entity_depth_1', 1, 'spatial.entity_depth', :a, :b)",
        {"g": ids["generation_id"], "a": ids["artifact"],
         "b": ids["blob"]})
    try:
        with pytest.raises(SoloRingError) as ei:
            await _verify(factory, settings, ids)
        assert ei.value.code == ec.DERIVED_SPATIAL_BINDING_INVALID
    finally:
        await _update(
            engine,
            "DELETE FROM generation_derived_spatial_inputs WHERE "
            "generation_id = :g AND input_key = 'entity_depth_1'",
            {"g": ids["generation_id"]})
    assert len(await _verify(factory, settings, ids)) == 1

    await _update(
        engine,
        "DELETE FROM generation_derived_spatial_inputs WHERE "
        "generation_id = :g", {"g": ids["generation_id"]})
    try:
        with pytest.raises(SoloRingError) as ei:
            await _verify(factory, settings, ids)
        assert ei.value.code == ec.DERIVED_SPATIAL_BINDING_INVALID
    finally:
        await _update(
            engine,
            "INSERT INTO generation_derived_spatial_inputs (generation_id,"
            " input_key, position, artifact_role, "
            "derived_spatial_artifact_id, blob_hash) VALUES (:g, "
            "'world_depth', 0, 'spatial.world_depth', :a, :b)",
            {"g": ids["generation_id"], "a": ids["artifact"],
             "b": ids["blob"]})
    assert len(await _verify(factory, settings, ids)) == 1




# ------------------- E-106 round-2: cells 22/51 + duplicate shadow -------

async def test_cell22_nonempty_structured_bindings_rejected(
        factory, engine, settings):
    """Cell 22 as HISTORICAL corruption: a stored WorkflowSpec tampered
    with non-empty structured_bindings (rehashed consistently) is
    rejected by the strict history validator before any consumption."""
    ids = await _seed_spatial_generation(factory, engine, settings)
    assert len(await _verify(factory, settings, ids)) == 1
    spec = _spec(ids["continuity"], ids)
    spec["spatial_realization"]["structured_bindings"] = [
        {"anything": "non-empty"}]
    async with factory() as session:
        with pytest.raises(SoloRingError) as ei:
            await load_verified_derived_inputs(
                session, BlobStore(settings),
                generation_id=ids["generation_id"], workflow_spec=spec,
                manifest_v3=_manifest_doc())
    from soloring.errors import ErrorCode as _EC

    assert ei.value.code == _EC.SPATIAL_REALIZATION_BINDING_INVALID
    # restored positive: the untampered spec verifies again
    assert len(await _verify(factory, settings, ids)) == 1


async def test_cell51_list_order_violation_rejected(
        factory, engine, settings, tmp_path):
    """Cell 51 as HISTORICAL corruption: rotating the derived_artifacts
    LIST while keeping every row coordinate correct is invisible to a
    dict-based check — the strict history validator enforces list order
    == canonical position order before the dict conversion. Full five-step
    cycle against a REAL service-created generation."""
    from soloring.spatial import production_package as prod
    from soloring.spatial.package3 import parse_manifest_v3

    from tests.test_m10e_generation import (
        _EXTENTS,
        _create,
        _schema3_package,
        _spatial_seed,
        _spatial_settings,
    )

    pkg = await _schema3_package(tmp_path)
    seed = await _spatial_seed(factory, staged=2, extents=_EXTENTS)
    gen = await _create(factory, _spatial_settings(settings, pkg), seed)
    manifest_v3 = parse_manifest_v3(prod.production_manifest_v3())

    async with engine.connect() as conn:
        stored = (await conn.execute(text(
            "SELECT workflow_spec_json FROM generations WHERE id=:g"),
            {"g": gen.id})).scalar()
    import json as _json

    spec = _json.loads(stored)

    async def _load(spec_obj):
        async with factory() as session:
            return await load_verified_derived_inputs(
                session, BlobStore(settings), generation_id=gen.id,
                workflow_spec=spec_obj, manifest_v3=manifest_v3)

    assert len(await _load(spec)) == 3  # positive control

    arts = spec["spatial_realization"]["derived_artifacts"]
    spec["spatial_realization"]["derived_artifacts"] = [
        arts[2], arts[0], arts[1]]  # coordinates all correct, order not
    with pytest.raises(SoloRingError) as ei:
        await _load(spec)
    from soloring.errors import ErrorCode as _EC

    assert ei.value.code == _EC.SPATIAL_REALIZATION_BINDING_INVALID

    # restore exact bytes and re-prove the positive control
    assert len(await _load(_json.loads(stored))) == 3


async def test_duplicate_input_key_shadow_rejected(factory, engine,
                                                   settings):
    """A duplicate input_key entry that a dict comprehension would
    silently shadow is rejected by the strict history validator."""
    ids = await _seed_spatial_generation(factory, engine, settings)
    assert len(await _verify(factory, settings, ids)) == 1
    spec = _spec(ids["continuity"], ids)
    arts = spec["spatial_realization"]["derived_artifacts"]
    spec["spatial_realization"]["derived_artifacts"] = [arts[0], arts[0]]
    async with factory() as session:
        with pytest.raises(SoloRingError) as ei:
            await load_verified_derived_inputs(
                session, BlobStore(settings),
                generation_id=ids["generation_id"], workflow_spec=spec,
                manifest_v3=_manifest_doc())
    from soloring.errors import ErrorCode as _EC

    assert ei.value.code == _EC.SPATIAL_REALIZATION_BINDING_INVALID


# ----------------- E-080 five-step cycles for cells 18/19/20 (real fn) ---

class _Gen:
    def __init__(self, spec_json: str, spec_hash: str) -> None:
        self.workflow_spec_json = spec_json
        self.workflow_spec_hash = spec_hash


async def test_cells18_19_20_five_step_cycle():
    """Positive control → isolated corruption → fail-closed → exact
    restoration → restored positive, through the REAL production loader
    (parse + hash + canonical-bytes)."""
    import json as _json

    from soloring.domain.canonical import canonical_hash, canonical_json_str
    from soloring.errors import SoloRingError
    from soloring.worker.comfy_pipeline import (
        _load_verified_schema3_workflow_spec,
    )

    spec = _spec("9" * 64, {"artifact": "x", "blob": "ab" * 32,
                            "spec_hash": "cd" * 32,
                            "runtime_hash": "ef" * 32})
    good_json = canonical_json_str(spec)
    good_hash = canonical_hash(spec)
    # positive control
    assert _load_verified_schema3_workflow_spec(
        _Gen(good_json, good_hash)) == spec

    # cell 18: malformed stored JSON
    with pytest.raises(SoloRingError, match="not valid JSON"):
        _load_verified_schema3_workflow_spec(
            _Gen("{broken", good_hash))
    # restored positive
    assert _load_verified_schema3_workflow_spec(
        _Gen(good_json, good_hash)) == spec

    # cell 19: stored hash disagreement (content kept, hash wrong)
    with pytest.raises(SoloRingError, match="disagree"):
        _load_verified_schema3_workflow_spec(
            _Gen(good_json, "00" * 32))
    assert _load_verified_schema3_workflow_spec(
        _Gen(good_json, good_hash)) == spec

    # cell 20: noncanonical but semantically equal bytes (hash of the
    # canonical object still matches — only the BYTES differ)
    reordered = _json.dumps(spec, sort_keys=True, indent=1)
    if reordered == good_json:
        reordered = _json.dumps(
            {k: spec[k] for k in reversed(list(spec))}, indent=1)
    with pytest.raises(SoloRingError, match="not canonical"):
        _load_verified_schema3_workflow_spec(
            _Gen(reordered, good_hash))
    # restored positive
    assert _load_verified_schema3_workflow_spec(
        _Gen(good_json, good_hash)) == spec
