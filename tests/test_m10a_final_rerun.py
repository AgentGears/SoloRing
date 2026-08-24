"""M10A final slice — rerun no-rematerialization negatives (frozen §113)."""
import copy
import json
from pathlib import Path

import pytest
from sqlalchemy import text

from soloring.assets.blob_store import BlobStore
from soloring.spatial.realize import compose_spatial_realization
from soloring.spatial.spec3 import (
    compose_workflow_spec_v3,
    spec_v3_bytes_hash,
)

from tests.test_m10a4_worker_rerun import (  # seed + helpers
    _manifest_doc,
    _seed_spatial_generation,
    _spec,
)
from tests.test_m10a4b_closure import RecordingUploader


async def _full_schema3_generation(factory, engine, settings):
    """Seed a complete schema-3 generation: pack -> D0 materialize -> blob
    -> provenance -> sibling rows -> persisted v3 spec. Returns ids + the
    persisted spec/pack."""
    ids = await _seed_spatial_generation(factory, engine, settings)
    from tests.test_m10a_final_slice import _lobby_pack
    pack = _lobby_pack()
    out = compose_spatial_realization(pack, entity_layers=0)
    # align the block's continuity/blob identity with the seeded history
    block = {**out.spatial_realization_block,
             "spatial_continuity_hash": ids["continuity"]}
    block["derived_artifacts"] = [
        {**a, "blob_hash": ids["blob"]} for a in
        block["derived_artifacts"]]
    out = out.__class__(  # same shape, seeded identities
        specs=out.specs, spec_hashes=out.spec_hashes,
        runtime_fingerprint=out.runtime_fingerprint,
        runtime_fingerprint_hash=out.runtime_fingerprint_hash,
        frames=out.frames, artifact_digests=(ids["blob"],),
        spatial_realization_block=block)
    spec = compose_workflow_spec_v3(
        {"prompt": "p"},
        model={"id": "wan2.1-t2v-1.3b", "version": "fp16",
               "execution_model_fingerprint_hash": "f" * 64},
        realization=None,
        spatial_realization=out.spatial_realization_block)
    spec_json, spec_hash = spec_v3_bytes_hash(spec)
    async with factory() as session:
        await session.execute(text(
            "UPDATE generations SET workflow_spec_json=:sj, "
            "workflow_spec_hash=:sh, status='succeeded', completed_at='t' "
            "WHERE id=:g"),
            {"sj": spec_json, "sh": spec_hash, "g": ids["generation_id"]})
        await session.commit()
    return {**ids, "spec": spec, "spec_json": spec_json,
            "spec_hash": spec_hash, "frames": out.frames[0],
            "digest": out.artifact_digests[0]}


async def test_rerun_with_materializer_unavailable(factory, engine, settings,
                                                   monkeypatch):
    """Exact Rerun never rematerializes: with the entire boxdepth module
    import-blocked, the rerun still copies the derived rows and the
    worker transport still verifies/uploads the retained bytes."""
    ids = await _full_schema3_generation(factory, engine, settings)

    # Break current-M10 and the materializer completely
    import soloring.generation.rerun as rerun_mod
    from soloring.spatial import realize as realize_mod
    monkeypatch.setattr(
        realize_mod, "compose_spatial_realization",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("rematerialization attempted")))
    monkeypatch.setattr(
        "soloring.spatial.boxdepth.materialize",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("materializer must not run during rerun")))

    new_id = await rerun_mod._create_rerun_fenced(engine,
                                                  ids["generation_id"])
    async with factory() as session:
        rows = (await session.execute(text(
            "SELECT input_key, position, artifact_role, "
            "derived_spatial_artifact_id, blob_hash FROM "
            "generation_derived_spatial_inputs WHERE generation_id=:g "
            "ORDER BY position"), {"g": new_id})).mappings().all()
    assert len(rows) == 1 and rows[0]["blob_hash"] == ids["blob"]

    # worker transport on the RERUN generation still verifies + uploads
    # the retained historical bytes (materializer still blocked)
    from soloring.spatial.worker_inputs import execute_schema3_derived_inputs
    uploader = RecordingUploader()
    async with factory() as session:
        verified = await execute_schema3_derived_inputs(
            session, BlobStore(settings), generation_id=new_id,
            workflow_spec=ids["spec"], manifest_v3=_manifest_doc(),
            client=uploader)
    import hashlib
    assert hashlib.sha256(uploader.uploads[0][2]).hexdigest() == ids["blob"]


async def test_rerun_after_current_m10_edit(factory, engine, settings,
                                            monkeypatch):
    """Current M10 edits cannot reinterpret a rerun: mutate spatial world
    rows after capture; the rerun's derived rows + spec stay identical."""
    ids = await _full_schema3_generation(factory, engine, settings)
    async with factory() as session:
        await session.execute(text(
            "UPDATE spatial_worlds SET requirement='optional', "
            "name='Edited' WHERE id=(SELECT spatial_world_id FROM "
            "spatial_world_states LIMIT 1)"))
        await session.execute(text(
            "UPDATE spatial_world_states SET approved_revision_id=NULL "
            "WHERE id=(SELECT spatial_world_state_id FROM "
            "shot_revision_spatial_worlds WHERE shot_revision_id="
            "(SELECT shot_revision_id FROM generations WHERE id=:g))"),
            {"g": ids["generation_id"]})
        await session.commit()

    from soloring.generation import rerun
    new_id = await rerun._create_rerun_fenced(engine, ids["generation_id"])
    async with factory() as session:
        rerun_spec = (await session.execute(text(
            "SELECT workflow_spec_json, workflow_spec_hash FROM generations "
            "WHERE id=:g"), {"g": new_id})).mappings().one()
        rerun_derived = (await session.execute(text(
            "SELECT blob_hash FROM generation_derived_spatial_inputs "
            "WHERE generation_id=:g"), {"g": new_id})).mappings().one()
    assert rerun_spec["workflow_spec_hash"] == ids["spec_hash"]
    assert rerun_derived["blob_hash"] == ids["blob"]
