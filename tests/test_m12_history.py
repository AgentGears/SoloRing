"""M12 historical-isolation proofs (frozen R3 §21 M12-HISTORY)."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from soloring.domain.ids import new_uuid

from tests.test_m12_publication import (
    _composition,
    _mint,
    _seed_production,
    _seed_project,
    _spec,
    load_composition_revision_detail,
    publish_composition_revision,
)
from tests.test_m12_lineage import _preview_apply

NOW = "2026-01-01T00:00:00.000Z"


async def test_old_revision_ignores_current_working_edits(engine, factory):
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)
    cid = await _composition(factory, pid)
    occ = (await _mint(factory, cid, _spec(rids[0]), 0))["occurrence_id"]
    d1, _ = await publish_composition_revision(
        factory(), cid, expected_working_version=1)
    from soloring.composition.service import patch_working_occurrence

    await patch_working_occurrence(
        factory(), cid, occ, scope="composition_working_state",
        expected_working_version=1, display_name="Renamed",
        transform={"translation_mm": [9, 9, 9], "rotation_udeg": [0, 0, 0]})
    d1_again = await load_composition_revision_detail(
        factory(), d1["revision_id"])
    assert d1_again["snapshot_json"] == d1["snapshot_json"]


async def test_old_revision_ignores_composition_display_metadata_changes(
    engine, factory
):
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)
    cid = await _composition(factory, pid)
    await _mint(factory, cid, _spec(rids[0]), 0)
    d1, _ = await publish_composition_revision(
        factory(), cid, expected_working_version=1)
    from soloring.composition.service import patch_composition_metadata

    await patch_composition_metadata(
        factory(), cid, expected_metadata_version=0, name="Renamed Lobby")
    d1_again = await load_composition_revision_detail(
        factory(), d1["revision_id"])
    assert d1_again["snapshot_hash"] == d1["snapshot_hash"]


async def test_old_revision_keeps_occurrence_after_later_remove(engine, factory):
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)
    cid = await _composition(factory, pid)
    occ = (await _mint(factory, cid, _spec(rids[0]), 0))["occurrence_id"]
    d1, _ = await publish_composition_revision(
        factory(), cid, expected_working_version=1)
    await _preview_apply(factory(), cid, "remove", [occ], [], 1)
    d1_again = await load_composition_revision_detail(
        factory(), d1["revision_id"])
    parsed = json.loads(d1_again["snapshot_json"])
    assert parsed["occurrences"][0]["occurrence_id"] == occ


async def test_old_revision_keeps_exact_old_source_after_update(engine, factory):
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid, n=2)
    assert len(rids) == 2
    cid = await _composition(factory, pid)
    occ = (await _mint(factory, cid, _spec(rids[0]), 0))["occurrence_id"]
    d1, _ = await publish_composition_revision(
        factory(), cid, expected_working_version=1)
    from soloring.composition.service import patch_working_occurrence

    await patch_working_occurrence(
        factory(), cid, occ, scope="composition_working_state",
        expected_working_version=1,
        source={"kind": "production_revision", "revision_id": rids[1]})
    d1_again = await load_composition_revision_detail(
        factory(), d1["revision_id"])
    parsed = json.loads(d1_again["snapshot_json"])
    assert parsed["occurrences"][0]["source"]["revision_id"] == rids[0]


async def test_revision_reader_crosschecks_snapshot_and_occurrence_projection(
    engine, factory
):
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)
    cid = await _composition(factory, pid)
    await _mint(factory, cid, _spec(rids[0]), 0)
    detail, _ = await publish_composition_revision(
        factory(), cid, expected_working_version=1)
    rid = detail["revision_id"]
    async with factory() as s:
        async with s.bind.connect() as conn:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await conn.execute(
                text("UPDATE composition_revision_occurrences SET "
                     "display_name = 'Tampered' "
                     "WHERE composition_revision_id = :r"), {"r": rid})
            await conn.exec_driver_sql("COMMIT")
    with pytest.raises(Exception) as ei:
        await load_composition_revision_detail(factory(), rid)
    assert getattr(ei.value, "code", "") == "INTERNAL_INVARIANT_VIOLATION"


async def test_revision_reader_rederives_dependency_closure_independently(
    engine, factory
):
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)
    cid = await _composition(factory, pid)
    await _mint(factory, cid, _spec(rids[0]), 0)
    detail, _ = await publish_composition_revision(
        factory(), cid, expected_working_version=1)
    rid = detail["revision_id"]
    # self-consistent omission: drop a dependency row and rewrite snapshot
    from soloring.domain.canonical import canonical_hash, canonical_json_str

    async with factory() as s:
        async with s.bind.connect() as conn:
            snap = json.loads(detail["snapshot_json"])
            snap["dependencies"]["production_revision_ids"] = []
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await conn.execute(
                text("UPDATE composition_revisions SET snapshot_json = :sj, "
                     "snapshot_hash = :sh WHERE id = :r"),
                {"sj": canonical_json_str(snap),
                 "sh": canonical_hash(snap), "r": rid})
            await conn.execute(
                text("DELETE FROM composition_revision_production_dependencies "
                     "WHERE composition_revision_id = :r"), {"r": rid})
            await conn.exec_driver_sql("COMMIT")
    with pytest.raises(Exception) as ei:
        await load_composition_revision_detail(factory(), rid)
    assert getattr(ei.value, "code", "") == "INTERNAL_INVARIANT_VIOLATION"
