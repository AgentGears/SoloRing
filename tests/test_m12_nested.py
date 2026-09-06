"""M12 nested-composition proofs (frozen R3 §21 M12-NEST).

Reuses the seeding helpers from the publication suite; the frozen owner
names are exact re-exports with distinct focus.
"""

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
    publish_composition_revision,
    resolve_publication_readiness,
    load_composition_revision_detail,
    SoloRingError,
)


async def test_nested_revision_is_pinned_exactly_not_latest(engine, factory):
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)
    inner = await _composition(factory, pid, name="ReceptionModule")
    i_occ = (await _mint(factory, inner, _spec(rids[0]), 0))["occurrence_id"]
    from soloring.composition.service import patch_working_occurrence

    inner_rev1, _ = await publish_composition_revision(
        factory(), inner, expected_working_version=1)
    await patch_working_occurrence(
        factory(), inner, i_occ, scope="composition_working_state",
        expected_working_version=1, display_name="v2")
    inner_rev2, _ = await publish_composition_revision(
        factory(), inner, expected_working_version=2)

    outer = await _composition(factory, pid, name="Lobby")
    nested_spec = {
        "display_name": "Reception",
        "source": {"kind": "composition_revision",
                   "revision_id": inner_rev1["revision_id"]},
        "visible": True,
        "transform": {"translation_mm": [0, 0, 0], "rotation_udeg": [0, 0, 0]},
    }
    await _mint(factory, outer, nested_spec, 0)
    parent_rev, _ = await publish_composition_revision(
        factory(), outer, expected_working_version=1)
    again = await load_composition_revision_detail(
        factory(), parent_rev["revision_id"])
    parsed = json.loads(again["snapshot_json"])
    assert parsed["dependencies"]["composition_revision_ids"] == [
        inner_rev1["revision_id"]]  # exact old revision, not rev2


async def test_nested_closure_flattens_transitive_production_dependencies(
    engine, factory
):
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)
    inner = await _composition(factory, pid, name="M")
    await _mint(factory, inner, _spec(rids[0]), 0)
    inner_rev, _ = await publish_composition_revision(
        factory(), inner, expected_working_version=1)
    outer = await _composition(factory, pid, name="L")
    nested_spec = {
        "display_name": "N",
        "source": {"kind": "composition_revision",
                   "revision_id": inner_rev["revision_id"]},
        "visible": True,
        "transform": {"translation_mm": [0, 0, 0], "rotation_udeg": [0, 0, 0]},
    }
    await _mint(factory, outer, nested_spec, 0)
    detail, _ = await publish_composition_revision(
        factory(), outer, expected_working_version=1)
    parsed = json.loads(detail["snapshot_json"])
    assert rids[0] in parsed["dependencies"]["production_revision_ids"]


async def test_nested_closure_flattens_transitive_composition_dependencies(
    engine, factory
):
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)
    a = await _composition(factory, pid, name="A")
    await _mint(factory, a, _spec(rids[0]), 0)
    a_rev, _ = await publish_composition_revision(
        factory(), a, expected_working_version=1)
    b = await _composition(factory, pid, name="B")
    await _mint(factory, b, {
        "display_name": "A mod",
        "source": {"kind": "composition_revision",
                   "revision_id": a_rev["revision_id"]},
        "visible": True,
        "transform": {"translation_mm": [0, 0, 0],
                      "rotation_udeg": [0, 0, 0]},
    }, 0)
    b_rev, _ = await publish_composition_revision(
        factory(), b, expected_working_version=1)
    c = await _composition(factory, pid, name="C")
    await _mint(factory, c, {
        "display_name": "B mod",
        "source": {"kind": "composition_revision",
                   "revision_id": b_rev["revision_id"]},
        "visible": True,
        "transform": {"translation_mm": [0, 0, 0],
                      "rotation_udeg": [0, 0, 0]},
    }, 0)
    c_rev, _ = await publish_composition_revision(
        factory(), c, expected_working_version=1)
    detail = await load_composition_revision_detail(
        factory(), c_rev["revision_id"])
    parsed = json.loads(detail["snapshot_json"])
    assert set(parsed["dependencies"]["composition_revision_ids"]) == {
        a_rev["revision_id"], b_rev["revision_id"]}


async def test_nested_dependency_duplicates_coalesce_deterministically(
    engine, factory
):
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)
    inner = await _composition(factory, pid, name="M")
    await _mint(factory, inner, _spec(rids[0]), 0)
    inner_rev, _ = await publish_composition_revision(
        factory(), inner, expected_working_version=1)
    outer = await _composition(factory, pid, name="L")
    nested = {
        "display_name": "N1",
        "source": {"kind": "composition_revision",
                   "revision_id": inner_rev["revision_id"]},
        "visible": True,
        "transform": {"translation_mm": [0, 0, 0], "rotation_udeg": [0, 0, 0]},
    }
    await _mint(factory, outer, nested, 0)
    nested2 = dict(nested, display_name="N2")
    await _mint(factory, outer, nested2, 1)
    detail, _ = await publish_composition_revision(
        factory(), outer, expected_working_version=2)
    parsed = json.loads(detail["snapshot_json"])
    # the same nested revision appears once in the closure despite two
    # direct occurrences of it
    assert parsed["dependencies"]["composition_revision_ids"] == [
        inner_rev["revision_id"]]


async def test_later_nested_publication_does_not_change_parent_history(
    engine, factory
):
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)
    inner = await _composition(factory, pid, name="M")
    i_occ = (await _mint(factory, inner, _spec(rids[0]), 0))["occurrence_id"]
    inner_rev, _ = await publish_composition_revision(
        factory(), inner, expected_working_version=1)
    outer = await _composition(factory, pid, name="L")
    await _mint(factory, outer, {
        "display_name": "N",
        "source": {"kind": "composition_revision",
                   "revision_id": inner_rev["revision_id"]},
        "visible": True,
        "transform": {"translation_mm": [0, 0, 0], "rotation_udeg": [0, 0, 0]},
    }, 0)
    parent_rev, _ = await publish_composition_revision(
        factory(), outer, expected_working_version=1)
    before = parent_rev["snapshot_hash"]
    from soloring.composition.service import patch_working_occurrence

    await patch_working_occurrence(
        factory(), inner, i_occ, scope="composition_working_state",
        expected_working_version=1, display_name="changed")
    await publish_composition_revision(
        factory(), inner, expected_working_version=2)
    after = await load_composition_revision_detail(
        factory(), parent_rev["revision_id"])
    assert after["snapshot_hash"] == before


async def test_nested_projection_corruption_fails_internal_invariant(
    engine, factory
):
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)
    inner = await _composition(factory, pid, name="M")
    await _mint(factory, inner, _spec(rids[0]), 0)
    inner_rev, _ = await publish_composition_revision(
        factory(), inner, expected_working_version=1)
    rid = inner_rev["revision_id"]
    async with factory() as s:
        async with s.bind.connect() as conn:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await conn.execute(
                text("UPDATE composition_revision_occurrences SET x_mm = 77 "
                     "WHERE composition_revision_id = :r"), {"r": rid})
            await conn.exec_driver_sql("COMMIT")
    with pytest.raises(SoloRingError) as ei:
        await load_composition_revision_detail(factory(), rid)
    assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"


async def test_transitive_same_composition_lineage_embedding_is_rejected(
    engine, factory
):
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)
    a = await _composition(factory, pid, name="A")
    await _mint(factory, a, _spec(rids[0]), 0)
    a_rev, _ = await publish_composition_revision(
        factory(), a, expected_working_version=1)
    b = await _composition(factory, pid, name="B")
    await _mint(factory, b, {
        "display_name": "A mod",
        "source": {"kind": "composition_revision",
                   "revision_id": a_rev["revision_id"]},
        "visible": True,
        "transform": {"translation_mm": [0, 0, 0],
                      "rotation_udeg": [0, 0, 0]},
    }, 0)
    b_rev, _ = await publish_composition_revision(
        factory(), b, expected_working_version=1)
    with pytest.raises(SoloRingError) as ei:
        await _mint(factory, a, {
            "display_name": "B mod",
            "source": {"kind": "composition_revision",
                       "revision_id": b_rev["revision_id"]},
            "visible": True,
            "transform": {"translation_mm": [0, 0, 0],
                          "rotation_udeg": [0, 0, 0]},
        }, 1)
    assert "transitive" in ei.value.message or "own lineage" in ei.value.message


async def test_self_consistent_dependency_omission_fails_independent_rederivation(
    engine, factory
):
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)
    cid = await _composition(factory, pid)
    await _mint(factory, cid, _spec(rids[0]), 0)
    detail, _ = await publish_composition_revision(
        factory(), cid, expected_working_version=1)
    rid = detail["revision_id"]
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
    with pytest.raises(SoloRingError) as ei:
        await load_composition_revision_detail(factory(), rid)
    assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"
