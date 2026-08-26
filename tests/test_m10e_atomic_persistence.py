"""M10E-C — atomic Generation + ordinary + derived-sibling persistence
(frozen R3 §15).

One write unit, both SQLite paths (RETURNING and BEGIN IMMEDIATE
fallback), fault-injection rollback of every family, cross-family
input-key collision inside the unit, and orphan-retention of pre-published
owner-free derived artifacts (E-050..E-054)."""
from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from soloring.assets.blob_store import BlobStore
from soloring.errors import ErrorCode, SoloRingError
from soloring.generation import repository as repo
from soloring.generation.drafts import GenerationDraft
from soloring.generation.enums import GenerationOperation
from soloring.generation.input_mapping import ResolvedGenerationInput
from soloring.spatial.derived_inputs import DerivedInputBinding

from tests.test_m10a4_worker_rerun import _fp_json, _mkblob, _spec_json

HEX = "ab" * 32


def _entity_spec_json(continuity: str, entity_id: str,
                      track_id: str) -> str:
    from soloring.domain.canonical import canonical_json_str
    from soloring.spatial.derived import parse_derived_spec

    spec = json.loads(_spec_json("e" * 64, continuity))
    p = spec["derivation"]["parameters"]
    p["scope"] = "entity"
    p["entity_id"] = entity_id
    p["placement_source_kind"] = "spatial_track"
    p["placement_source_id"] = track_id
    p["proxy_geometry"] = {"policy_id": "box-standin-v1"}
    spec["output_contract"]["media_type"] = "image/png"
    spec["output_contract"]["encoding"] = "png-l-mode-8bit"
    return canonical_json_str(
        parse_derived_spec(spec).model_dump(mode="json",
                                            exclude_none=False))


async def _seed_world_rows(factory, engine, settings, *, entities=()):
    """Project + schema-5 ShotRevision rows + one world/derived artifact
    per requested entity (plus the world artifact), all with physical
    Blobs and canonical provenance. Returns ids + bindings."""
    store = BlobStore(settings)
    continuity = "9" * 64
    pid, shot, srev = (str(uuid.uuid4()) for _ in range(3))
    world_art = str(uuid.uuid4())
    loc, locrev, world_id, state_id, wrev = (str(uuid.uuid4())
                                             for _ in range(5))
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO projects (id, name, created_at, updated_at) "
                "VALUES (:p, 'P', 't', 't')"), {"p": pid})
            await session.execute(text(
                "INSERT INTO creative_entities (id, project_id, kind, "
                "name, created_at, updated_at) VALUES (:e, :p, "
                "'location', 'L', 't', 't')"),
                {"e": loc, "p": pid})
            await session.execute(text(
                "INSERT INTO entity_revisions (id, entity_id, "
                "revision_number, schema_version, spec_hash, created_at) "
                "VALUES (:r, :e, 1, 1, :h, 't')"),
                {"r": locrev, "e": loc, "h": HEX})
            await session.execute(text(
                "INSERT INTO spatial_worlds (id, project_id, "
                "location_entity_id, key, name, requirement, created_at, "
                "updated_at) VALUES (:w, :p, :loc, 'lobby', 'L', "
                "'required', 't', 't')"),
                {"w": world_id, "p": pid, "loc": loc})
            await session.execute(text(
                "INSERT INTO spatial_world_states (id, spatial_world_id, "
                "location_entity_revision_id, created_at, updated_at) "
                "VALUES (:s, :w, :lr, 't', 't')"),
                {"s": state_id, "w": world_id, "lr": locrev})
            await session.execute(text(
                "INSERT INTO spatial_world_revisions (id, "
                "spatial_world_state_id, revision_number, snapshot_json, "
                "snapshot_hash, created_at) VALUES (:r, :s, 1, '{}', :h, "
                "'t')"),
                {"r": wrev, "s": state_id, "h": HEX})
            await session.execute(text(
                "INSERT INTO shots (id, project_id, shot_number, subject, "
                "created_at, updated_at) VALUES (:s, :p, 1, 'S', 't', 't')"),
                {"s": shot, "p": pid})
            await session.execute(text(
                "INSERT INTO shot_revisions (id, shot_id, revision_number, "
                "snapshot_json, snapshot_hash, created_at) VALUES "
                "(:r, :s, 1, :snap, :h, 't')"),
                {"r": srev, "s": shot,
                 "snap": json.dumps({"schema_version": 5}), "h": HEX})
            await session.execute(text(
                "INSERT INTO shot_revision_spatial_worlds ("
                "shot_revision_id, spatial_continuity_hash, "
                "spatial_world_id, spatial_world_state_id, "
                "spatial_world_revision_id, spatial_world_revision_hash, "
                "location_entity_id, location_entity_revision_id, "
                "requirement) VALUES (:r, :c, :w, :st, :wr, :wh, :l, :lr, "
                "'required')"),
                {"r": srev, "c": continuity, "w": world_id,
                 "st": state_id, "wr": wrev, "wh": HEX, "l": loc,
                 "lr": locrev})

            world_blob = await _mkblob(store, b"world-control-bytes")
            await session.execute(text(
                "INSERT INTO blobs (hash, path, size_bytes, created_at) "
                "VALUES (:h, :pa, 19, 't')"),
                {"h": world_blob, "pa": str(store.path_for_hash(world_blob))})
            await session.execute(text(
                "INSERT INTO derived_spatial_artifacts (id, project_id, "
                "spec_schema_version, spec_json, spec_hash, "
                "spatial_continuity_schema_version, spatial_continuity_hash, "
                "artifact_kind, artifact_schema_version, algorithm_id, "
                "algorithm_version, runtime_fingerprint_json, "
                "runtime_fingerprint_hash, determinism_class, blob_hash, "
                "media_type, created_at) VALUES (:id, :p, 1, :sj, :sh, 1, "
                ":c, 'boxdepth_control_video', 1, "
                "'soloring.boxdepth.rasterizer', '1.0.0', :fj, :fh, 'D0', "
                ":bh, 'application/x-npy', 't')"),
                {"id": world_art, "p": pid, "sj": _spec_json(
                    world_blob, continuity),
                 "sh": hashlib.sha256(_spec_json(
                     world_blob, continuity).encode()).hexdigest(),
                 "c": continuity, "fj": _fp_json(),
                 "fh": hashlib.sha256(_fp_json().encode()).hexdigest(),
                 "bh": world_blob})

            entity_bindings = []
            for i, (eid, tid) in enumerate(entities):
                art = str(uuid.uuid4())
                blob = await _mkblob(store, f"entity-{i}-control".encode())
                sj = _entity_spec_json(continuity, eid, tid)
                await session.execute(text(
                    "INSERT INTO blobs (hash, path, size_bytes, created_at)"
                    " VALUES (:h, :pa, 15, 't')"),
                    {"h": blob, "pa": str(store.path_for_hash(blob))})
                await session.execute(text(
                    "INSERT INTO derived_spatial_artifacts (id, project_id, "
                    "spec_schema_version, spec_json, spec_hash, "
                    "spatial_continuity_schema_version, "
                    "spatial_continuity_hash, artifact_kind, "
                    "artifact_schema_version, algorithm_id, "
                    "algorithm_version, runtime_fingerprint_json, "
                    "runtime_fingerprint_hash, determinism_class, "
                    "blob_hash, media_type, created_at) VALUES "
                    "(:id, :p, 1, :sj, :sh, 1, :c, "
                    "'boxdepth_control_video', 1, "
                    "'soloring.boxdepth.rasterizer', '1.0.0', :fj, :fh, "
                    "'D0', :bh, 'image/png', 't')"),
                    {"id": art, "p": pid, "sj": sj,
                     "sh": hashlib.sha256(sj.encode()).hexdigest(),
                     "c": continuity, "fj": _fp_json(),
                     "fh": hashlib.sha256(
                         _fp_json().encode()).hexdigest(), "bh": blob})
                entity_bindings.append((art, blob, eid, tid))
    return {
        "pid": pid, "shot": shot, "srev": srev, "continuity": continuity,
        "world": (world_art, world_blob), "entities": entity_bindings,
        "store": store,
    }


def _draft(seed) -> GenerationDraft:
    return GenerationDraft(
        shot_id=seed["shot"], shot_revision_id=seed["srev"],
        operation=GenerationOperation.GENERATE, executor="comfy",
        workflow_id="wf", workflow_version=1,
        workflow_template_hash=HEX, manifest_hash=HEX,
        model="m", model_version="1",
        compiled_prompt="p", negative_prompt=None,
        prompt_compiler_version="v1", seed=None,
        parameters_json="{}", workflow_spec_json='{"schema_version": 3}',
        workflow_spec_hash=HEX,
    )


def _bindings(seed):
    out = [DerivedInputBinding(
        input_key="world_depth", position=0,
        artifact_role="spatial.world_depth",
        derived_spatial_artifact_id=seed["world"][0],
        blob_hash=seed["world"][1])]
    for i, (art, blob, eid, tid) in enumerate(seed["entities"]):
        out.append(DerivedInputBinding(
            input_key=f"entity_depth_{i + 1}", position=i + 1,
            artifact_role="spatial.entity_depth",
            derived_spatial_artifact_id=art, blob_hash=blob))
    return tuple(out)


async def _counts(engine, generation_id=None):
    async with engine.connect() as conn:
        async def q(sql: str, params: dict | None = None):
            return (await conn.execute(text(sql), params or {})).scalar()

        gid = {"g": generation_id} if generation_id else None
        return {
            "generations": await q("SELECT COUNT(*) FROM generations"),
            "inputs": await q(
                "SELECT COUNT(*) FROM generation_inputs"),
            "siblings": await q(
                "SELECT COUNT(*) FROM generation_derived_spatial_inputs"
                + (" WHERE generation_id = :g" if gid else ""), gid),
            "artifacts": await q(
                "SELECT COUNT(*) FROM derived_spatial_artifacts"),
        }


_E1 = ("00000000-0000-4000-8000-00000000000a",
       "00000000-0000-4000-8000-0000000000aa")
_E2 = ("00000000-0000-4000-8000-00000000000b",
       "00000000-0000-4000-8000-0000000000bb")


async def test_atomic_unit_returning_path(factory, engine, settings):
    seed = await _seed_world_rows(factory, engine, settings,
                                  entities=[_E1, _E2])
    async with factory() as session:
        gen = await repo.create_generation(
            session, _draft(seed), (), derived_inputs=_bindings(seed))
        assert gen.status == "queued"
    counts = await _counts(engine, gen.id)
    assert counts["siblings"] == 3
    assert counts["generations"] == 1


async def test_atomic_unit_fenced_path_parity(
        factory, engine, settings, monkeypatch):
    """E-052: the BEGIN IMMEDIATE fallback has the same atomic semantics."""
    seed = await _seed_world_rows(factory, engine, settings,
                                  entities=[_E1])
    monkeypatch.setattr(repo, "sqlite_supports_returning",
                        lambda: False)
    async with factory() as session:
        gen = await repo.create_generation(
            session, _draft(seed), (), derived_inputs=_bindings(seed))
    counts = await _counts(engine, gen.id)
    assert counts["siblings"] == 2
    assert counts["generations"] == 1


async def test_fault_at_derived_binding_rolls_back_all(
        factory, engine, settings):
    """E-051: a bad derived artifact reference rolls back the Generation
    and both input families completely."""
    seed = await _seed_world_rows(factory, engine, settings,
                                  entities=[_E1])
    bindings = list(_bindings(seed))
    bindings[1] = DerivedInputBinding(
        input_key=bindings[1].input_key, position=1,
        artifact_role="spatial.entity_depth",
        derived_spatial_artifact_id=str(uuid.uuid4()),  # missing artifact
        blob_hash=bindings[1].blob_hash)
    async with factory() as session:
        with pytest.raises(SoloRingError) as ei:
            await repo.create_generation(
                session, _draft(seed), (), derived_inputs=tuple(bindings))
    from soloring.spatial.error_codes import (
        DERIVED_SPATIAL_PROVENANCE_MISMATCH,
    )

    assert ei.value.code == DERIVED_SPATIAL_PROVENANCE_MISMATCH
    counts = await _counts(engine)
    assert counts == {"generations": 0, "inputs": 0, "siblings": 0,
                      "artifacts": 2}


async def test_cross_family_key_collision_fails_in_unit(
        factory, engine, settings):
    """§21 cell 52: an ordinary input_key colliding with a derived key is
    a deterministic pre-persistence failure inside the write unit."""
    from soloring.db.models import Asset

    seed = await _seed_world_rows(factory, engine, settings,
                                  entities=[])
    aid = str(uuid.uuid4())
    bh = seed["world"][1]
    async with factory() as session:
        session.add(Asset(id=aid, project_id=seed["pid"], blob_hash=bh,
                          kind="reference"))
        await session.commit()
    ordinary = (ResolvedGenerationInput(
        input_key="world_depth", position=0, asset_id=aid, blob_hash=bh,
        reference_role="primary"),)
    async with factory() as session:
        with pytest.raises(SoloRingError) as ei:
            await repo.create_generation(
                session, _draft(seed), ordinary,
                derived_inputs=_bindings(seed))
    assert ei.value.code == ErrorCode.SPATIAL_REALIZATION_BINDING_INVALID
    assert (await _counts(engine))["generations"] == 0


async def test_entity_order_violation_fails(
        factory, engine, settings):
    """§21 cell 41: entity streams must follow canonical
    (entity_id, placement) order — reversed bindings fail closed."""
    seed = await _seed_world_rows(factory, engine, settings,
                                  entities=[_E1, _E2])
    b = list(_bindings(seed))
    # swap the two entity streams (positions stay contiguous; identity
    # order is what violates the canonical comparator)
    b[1], b[2] = b[2], b[1]
    b[1] = DerivedInputBinding(
        input_key=b[1].input_key, position=1,
        artifact_role=b[1].artifact_role,
        derived_spatial_artifact_id=b[1].derived_spatial_artifact_id,
        blob_hash=b[1].blob_hash)
    b[2] = DerivedInputBinding(
        input_key=b[2].input_key, position=2,
        artifact_role=b[2].artifact_role,
        derived_spatial_artifact_id=b[2].derived_spatial_artifact_id,
        blob_hash=b[2].blob_hash)
    async with factory() as session:
        with pytest.raises(SoloRingError) as ei:
            await repo.create_generation(
                session, _draft(seed), (), derived_inputs=tuple(b))
    from soloring.spatial.error_codes import DERIVED_SPATIAL_BINDING_INVALID

    assert ei.value.code == DERIVED_SPATIAL_BINDING_INVALID
    assert (await _counts(engine))["generations"] == 0


async def test_pre_published_artifacts_survive_rollback(
        factory, engine, settings):
    """E-054: a persistence failure after registration leaves the
    owner-free Blob/provenance reusable; a retry converges on the SAME
    artifact identities."""
    seed = await _seed_world_rows(factory, engine, settings,
                                  entities=[_E1])
    # ordinary input referencing a MISSING asset → rollback after the
    # derived family was validated/inserted inside the unit
    ordinary = (ResolvedGenerationInput(
        input_key="reference_image", position=0,
        asset_id=str(uuid.uuid4()), blob_hash="c" * 64,
        reference_role="primary"),)
    async with factory() as session:
        with pytest.raises(SoloRingError):
            await repo.create_generation(
                session, _draft(seed), ordinary,
                derived_inputs=_bindings(seed))
    counts = await _counts(engine)
    assert counts["generations"] == 0 and counts["siblings"] == 0
    assert counts["artifacts"] == 2  # orphaned, retained, reusable

    async with factory() as session:
        gen = await repo.create_generation(
            session, _draft(seed), (), derived_inputs=_bindings(seed))
    async with engine.connect() as conn:
        rows = [dict(r) for r in (await conn.execute(text(
            "SELECT derived_spatial_artifact_id, blob_hash FROM "
            "generation_derived_spatial_inputs WHERE generation_id = :g "
            "ORDER BY position"), {"g": gen.id})).mappings().all()]
    assert [r["derived_spatial_artifact_id"] for r in rows] == [
        seed["world"][0], seed["entities"][0][0]]
    async with engine.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM derived_spatial_artifacts"))).scalar()
    assert n == 2  # convergence, not duplication
