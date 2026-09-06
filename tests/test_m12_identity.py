"""M12 identity proofs (frozen R3 §21 M12-ID).

Occurrence identity is a fresh UUID independent of source, name, transform,
visibility, and same-lineage source evolution.
"""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import text

from soloring.composition.service import (
    create_composition,
    mint_occurrence,
    patch_working_occurrence,
)
from soloring.domain.ids import new_uuid

NOW = "2026-01-01T00:00:00.000Z"
SCOPE = "composition_working_state"


async def _seed_project(factory) -> str:
    pid = new_uuid()
    async with factory() as s:
        async with s.bind.connect() as conn:
            await conn.execute(
                text("INSERT INTO projects (id, name, created_at, updated_at) "
                     "VALUES (:id, 'P', :n, :n)"), {"id": pid, "n": NOW})
            await conn.commit()
    return pid


async def _seed_production(factory, pid, n=2) -> list[str]:
    salt = getattr(_seed_production, "_salt", 0)
    _seed_production._salt = salt + 1
    rids = []
    async with factory() as s:
        async with s.bind.connect() as conn:
            obj = new_uuid()
            await conn.execute(
                text("INSERT INTO production_objects (id, project_id, name, "
                     "created_at, updated_at) VALUES (:o, :p, 'Obj', :n, :n)"),
                {"o": obj, "p": pid, "n": NOW})
            for i in range(n):
                bh = hashlib.sha256(f"m12-id-{salt}-{i}".encode()).hexdigest()
                rid = new_uuid()
                await conn.execute(
                    text("INSERT INTO blobs (hash, path, size_bytes, "
                         "detected_media_type, created_at) VALUES "
                         "(:h, :p, 8, NULL, :n)"),
                    {"h": bh, "p": f"sha256/{bh[:2]}/{bh[2:4]}/{bh}", "n": NOW})
                await conn.execute(
                    text("INSERT INTO production_revisions (id, "
                         "production_object_id, revision_number, snapshot_json, "
                         "snapshot_hash, created_at) VALUES "
                         "(:r, :o, :num, '{}', :h, :n)"),
                    {"r": rid, "o": obj, "num": i + 1, "h": f"{i:064d}", "n": NOW})
                await conn.execute(
                    text("INSERT INTO production_revision_closures "
                         "(production_revision_id, contract_key, "
                         "contract_version, blob_hash, size_bytes, media_type) "
                         "VALUES (:r, 'retained_blob', 1, :bh, 8, NULL)"),
                    {"r": rid, "bh": bh})
                rids.append(rid)
            await conn.commit()
    return rids


def _spec(rid, name="Chair 7", pos=(0, 0, 0)) -> dict:
    return {
        "display_name": name,
        "source": {"kind": "production_revision", "revision_id": rid},
        "visible": True,
        "transform": {"translation_mm": list(pos), "rotation_udeg": [0, 0, 0]},
    }


async def _mint(factory, cid, spec, version) -> str:
    return (await mint_occurrence(
        factory(), cid, scope=SCOPE, expected_working_version=version,
        spec=spec))["occurrence_id"]


async def _comp(factory, pid) -> str:
    return (await create_composition(factory(), pid, name="Lobby",
                                     description=None))["id"]


async def test_occurrence_id_is_fresh_uuid_not_source_or_name(engine, factory):
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)
    cid = await _comp(factory, pid)
    a = await _mint(factory, cid, _spec(rids[0]), 0)
    b = await _mint(factory, cid, _spec(rids[0], name="Different"), 1)
    assert a != rids[0] and b != rids[0]
    assert a != b  # fresh UUID per mint, never derived


async def test_two_occurrences_of_same_revision_receive_distinct_ids(
    engine, factory
):
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid, n=1)
    cid = await _comp(factory, pid)
    a = await _mint(factory, cid, _spec(rids[0]), 0)
    b = await _mint(factory, cid, _spec(rids[0]), 1)
    assert a != b


async def test_display_name_change_preserves_occurrence_id(engine, factory):
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)
    cid = await _comp(factory, pid)
    occ = await _mint(factory, cid, _spec(rids[0]), 0)
    out = await patch_working_occurrence(
        factory(), cid, occ, scope=SCOPE, expected_working_version=1,
        display_name="Window Chair")
    assert out["occurrence_id"] == occ


async def test_transform_change_preserves_occurrence_id(engine, factory):
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)
    cid = await _comp(factory, pid)
    occ = await _mint(factory, cid, _spec(rids[0]), 0)
    out = await patch_working_occurrence(
        factory(), cid, occ, scope=SCOPE, expected_working_version=1,
        transform={"translation_mm": [100, 200, 300],
                   "rotation_udeg": [0, 0, 0]})
    assert out["occurrence_id"] == occ


async def test_visibility_change_preserves_occurrence_id(engine, factory):
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)
    cid = await _comp(factory, pid)
    occ = await _mint(factory, cid, _spec(rids[0]), 0)
    out = await patch_working_occurrence(
        factory(), cid, occ, scope=SCOPE, expected_working_version=1,
        visible=False)
    assert out["occurrence_id"] == occ


async def test_same_production_object_revision_update_preserves_occurrence_id(
    engine, factory
):
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)
    cid = await _comp(factory, pid)
    occ = await _mint(factory, cid, _spec(rids[0]), 0)
    out = await patch_working_occurrence(
        factory(), cid, occ, scope=SCOPE, expected_working_version=1,
        source={"kind": "production_revision", "revision_id": rids[1]})
    assert out["occurrence_id"] == occ


async def test_same_nested_composition_revision_update_preserves_occurrence_id(
    engine, factory
):
    from soloring.composition.readiness import publish_composition_revision

    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)
    inner = await create_composition(factory(), pid, name="Mod",
                                     description=None)
    await _mint(factory, inner["id"], _spec(rids[0]), 0)
    rev1, _ = await publish_composition_revision(
        factory(), inner["id"], expected_working_version=1)
    i_occ = await _first_occurrence(factory, inner["id"])
    await patch_working_occurrence(
        factory(), inner["id"], i_occ,
        scope=SCOPE, expected_working_version=1, display_name="v2")
    rev2, _ = await publish_composition_revision(
        factory(), inner["id"], expected_working_version=2)

    outer = await _comp(factory, pid)
    nested_spec = {
        "display_name": "Mod occurrence",
        "source": {"kind": "composition_revision",
                   "revision_id": rev1["revision_id"]},
        "visible": True,
        "transform": {"translation_mm": [0, 0, 0], "rotation_udeg": [0, 0, 0]},
    }
    occ = await _mint(factory, outer, nested_spec, 0)
    out = await patch_working_occurrence(
        factory(), outer, occ, scope=SCOPE, expected_working_version=1,
        source={"kind": "composition_revision",
                "revision_id": rev2["revision_id"]})
    assert out["occurrence_id"] == occ


async def _first_occurrence(factory, cid) -> str:
    async with factory() as s:
        async with s.bind.connect() as conn:
            return (await conn.execute(
                text("SELECT occurrence_id FROM "
                     "composition_working_occurrences WHERE composition_id = "
                     ":c LIMIT 1"), {"c": cid})).scalar_one()
