"""M12 historical-isolation proofs (frozen R3 §21 M12-HISTORY)."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text
from sqlalchemy import text as _text

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
    # M15C succession (frozen R6 §27): the working source now moves
    # through the M15 machinery — assessment + explicit review-accepted
    # apply. The identity-fixture second revision carries a raw '{}'
    # snapshot; make it M11-canonical so the assessment verifier
    # accepts it (the frozen claim under test is the OLD revision's
    # byte stability, which is indifferent to the target's snapshot).
    from soloring.production.canonical import (
        RetainedBlobClosure,
        production_revision_snapshot_json as _sj,
    )
    import hashlib as _hl

    async with factory() as s:
        async with s.bind.connect() as conn:
            for _idx, _rid in enumerate(rids):
                _bh = _hl.sha256(
                    f"m12-hist-m15c-r{_idx}".encode()).hexdigest()
                await conn.execute(_text(
                    "INSERT INTO blobs (hash, path, size_bytes, "
                    "detected_media_type, created_at) VALUES "
                    "(:h, :p, 16, NULL, :n)"),
                    {"h": _bh,
                     "p": f"sha256/{_bh[:2]}/{_bh[2:4]}/{_bh}",
                     "n": NOW})
                _closure = RetainedBlobClosure(
                    blob_hash=_bh, size_bytes=16, media_type=None)
                await conn.execute(_text(
                    "DELETE FROM production_revision_closures "
                    "WHERE production_revision_id = :r"),
                    {"r": _rid})
                await conn.execute(_text(
                    "INSERT INTO production_revision_closures "
                    "(production_revision_id, contract_key, "
                    "contract_version, blob_hash, size_bytes, "
                    "media_type) VALUES "
                    "(:r, 'retained_blob', 1, :bh, 16, NULL)"),
                    {"r": _rid, "bh": _bh})
                _snap = _sj(_closure)
                await conn.execute(_text(
                    "UPDATE production_revisions SET snapshot_json = :sj, "
                    "snapshot_hash = :sh WHERE id = :r"),
                    {"sj": _snap,
                     "sh": _hl.sha256(_snap.encode()).hexdigest(),
                     "r": _rid})
            await conn.commit()
    from soloring.compatibility.service import (
        apply_assessment, create_assessment)

    assessment = await create_assessment(
        factory(), from_revision_id=rids[0], to_revision_id=rids[1])
    use = assessment["uses"][0]
    await apply_assessment(
        factory(), assessment_id=assessment["assessment_id"],
        selected_uses=[{
            "composition_id": use["composition_id"],
            "occurrence_id": use["occurrence_id"],
            "expected_working_version": 1,
            "expected_use_contract_hash": use["use_contract_hash"],
            "review_accept": True}])
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
