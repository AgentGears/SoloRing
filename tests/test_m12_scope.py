"""M12 scope proofs (frozen R3 §21 M12-SCOPE) — exact owner names."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from sqlalchemy import text

from soloring.composition.service import (
    create_composition,
    mint_occurrence,
    patch_working_occurrence,
)
from soloring.errors import SoloRingError
from soloring.domain.ids import new_uuid

NOW = "2026-01-01T00:00:00.000Z"
SCOPE = "composition_working_state"


async def _seed(factory):
    pid = new_uuid()
    async with factory() as s:
        async with s.bind.connect() as conn:
            await conn.execute(
                text("INSERT INTO projects (id, name, created_at, updated_at) "
                     "VALUES (:id, 'P', :n, :n)"), {"id": pid, "n": NOW})
            await conn.commit()
    bh = hashlib.sha256(b"m12-scope").hexdigest()
    rid, obj = new_uuid(), new_uuid()
    async with factory() as s:
        async with s.bind.connect() as conn:
            await conn.execute(
                text("INSERT INTO blobs (hash, path, size_bytes, "
                     "detected_media_type, created_at) VALUES "
                     "(:h, :p, 9, NULL, :n)"),
                {"h": bh, "p": f"sha256/{bh[:2]}/{bh[2:4]}/{bh}", "n": NOW})
            await conn.execute(
                text("INSERT INTO production_objects (id, project_id, name, "
                     "created_at, updated_at) VALUES (:o, :p, 'Obj', :n, :n)"),
                {"o": obj, "p": pid, "n": NOW})
            await conn.execute(
                text("INSERT INTO production_revisions (id, "
                     "production_object_id, revision_number, snapshot_json, "
                     "snapshot_hash, created_at) VALUES "
                     "(:r, :o, 1, '{}', :h, :n)"),
                {"r": rid, "o": obj, "h": "0" * 64, "n": NOW})
            await conn.execute(
                text("INSERT INTO production_revision_closures "
                     "(production_revision_id, contract_key, "
                     "contract_version, blob_hash, size_bytes, media_type) "
                     "VALUES (:r, 'retained_blob', 1, :bh, 9, NULL)"),
                {"r": rid, "bh": bh})
            await conn.commit()
    return pid, rid


def _spec(rid, name="Chair") -> dict:
    return {
        "display_name": name,
        "source": {"kind": "production_revision", "revision_id": rid},
        "visible": True,
        "transform": {"translation_mm": [0, 0, 0], "rotation_udeg": [0, 0, 0]},
    }


async def _occurrence(factory, pid, rid) -> tuple[str, str]:
    cid = (await create_composition(factory(), pid, name="L",
                                    description=None))["id"]
    occ = (await mint_occurrence(
        factory(), cid, scope=SCOPE, expected_working_version=0,
        spec=_spec(rid)))["occurrence_id"]
    return cid, occ


async def test_occurrence_patch_requires_composition_working_scope(
    engine, factory
):
    pid, rid = await _seed(factory)
    cid, occ = await _occurrence(factory, pid, rid)
    for bad in (None, "shot_local", "story_state", "anything_else"):
        with pytest.raises(SoloRingError) as ei:
            await patch_working_occurrence(
                factory(), cid, occ, scope=bad,
                expected_working_version=1, display_name="X")
        assert ei.value.code == "VALIDATION_ERROR"


async def test_shot_local_scope_is_rejected_not_promoted(engine, factory):
    pid, rid = await _seed(factory)
    cid = (await create_composition(factory(), pid, name="L",
                                    description=None))["id"]
    with pytest.raises(SoloRingError) as ei:
        await mint_occurrence(
            factory(), cid, scope="shot_local", expected_working_version=0,
            spec=_spec(rid))
    assert ei.value.code == "VALIDATION_ERROR"
    async with factory() as s:
        async with s.bind.connect() as conn:
            n = (await conn.execute(
                text("SELECT COUNT(*) FROM "
                     "composition_working_occurrences"))).scalar_one()
    assert n == 0  # reusable Composition untouched


async def test_unknown_scope_is_rejected(engine, factory):
    pid, rid = await _seed(factory)
    cid, occ = await _occurrence(factory, pid, rid)
    with pytest.raises(SoloRingError):
        await patch_working_occurrence(
            factory(), cid, occ, scope="future_scope_v2",
            expected_working_version=1, visible=False)


async def test_source_lineage_change_requires_replace_as_new(engine, factory):
    pid, rid = await _seed(factory)
    cid, occ = await _occurrence(factory, pid, rid)
    # a Production Revision from ANOTHER Production Object
    rid2, obj2 = new_uuid(), new_uuid()
    async with factory() as s:
        async with s.bind.connect() as conn:
            await conn.execute(
                text("INSERT INTO production_objects (id, project_id, name, "
                     "created_at, updated_at) VALUES (:o, :p, 'Obj2', :n, :n)"),
                {"o": obj2, "p": pid, "n": NOW})
            await conn.execute(
                text("INSERT INTO production_revisions (id, "
                     "production_object_id, revision_number, snapshot_json, "
                     "snapshot_hash, created_at) VALUES "
                     "(:r, :o, 1, '{}', :h, :n)"),
                {"r": rid2, "o": obj2, "h": "1" * 64, "n": NOW})
            await conn.commit()
    with pytest.raises(SoloRingError) as ei:
        await patch_working_occurrence(
            factory(), cid, occ, scope=SCOPE,
            expected_working_version=1,
            source={"kind": "production_revision", "revision_id": rid2})
    assert ei.value.details.get("identity_change_required") is True
    assert ei.value.details.get("allowed_operation") == "replace_as_new"


def test_no_generic_occurrence_delete_route_or_service():
    from soloring.composition import service as comp_service

    src = Path(comp_service.__file__).read_text()
    assert "async def delete" not in src
    assert "DELETE FROM composition_occurrences" not in src
    api = Path("server/soloring/api/compositions.py")
    api_src = api.read_text()
    assert "@router.delete" not in api_src


def test_no_arbitrary_property_override_storage():
    from soloring.composition import service as comp_service

    src = Path(comp_service.__file__).read_text()
    assert "property_path" not in src
    assert "arbitrary" not in src.lower()
