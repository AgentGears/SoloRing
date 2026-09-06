"""M12 publication proofs (frozen R3 §21 M12-PUB / M12-NEST / M12-HISTORY)."""

from __future__ import annotations

import hashlib
import json

import pytest
from sqlalchemy import text

from soloring.composition.readiness import (
    COMPOSITION_EMPTY,
    load_composition_revision_detail,
    publish_composition_revision,
    resolve_publication_readiness,
)
from soloring.composition.service import (
    EditConflict,
    create_composition,
    mint_occurrence,
    patch_composition_metadata,
    patch_working_occurrence,
)
from soloring.errors import SoloRingError
from soloring.domain.ids import new_uuid

NOW = "2026-01-01T00:00:00.000Z"


async def _seed_project(factory) -> str:
    pid = new_uuid()
    async with factory() as s:
        async with s.bind.connect() as conn:
            await conn.execute(
                text("INSERT INTO projects (id, name, created_at, updated_at) "
                     "VALUES (:id, 'P', :n, :n)"), {"id": pid, "n": NOW})
            await conn.commit()
    return pid


async def _seed_production(factory, pid, n=1) -> list[str]:
    rids = []
    async with factory() as s:
        async with s.bind.connect() as conn:
            obj = new_uuid()
            await conn.execute(
                text("INSERT INTO production_objects (id, project_id, name, "
                     "created_at, updated_at) VALUES (:o, :p, 'Obj', :n, :n)"),
                {"o": obj, "p": pid, "n": NOW})
            for i in range(n):
                bh = hashlib.sha256(f"m12-pub-{i}".encode()).hexdigest()
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
                         "(production_revision_id, contract_key, contract_version, "
                         "blob_hash, size_bytes, media_type) VALUES "
                         "(:r, 'retained_blob', 1, :bh, 8, NULL)"),
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


async def _composition(factory, pid, name="Lobby") -> str:
    return (await create_composition(factory(), pid, name=name, description=None))["id"]


async def _mint(factory, cid, spec, version) -> dict:
    return await mint_occurrence(
        factory(), cid, scope="composition_working_state",
        expected_working_version=version, spec=spec)


async def test_publish_one_occurrence_pins_exact_source_and_dependency(
    engine, factory
):
    """M12-PUB:01."""
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)
    cid = await _composition(factory, pid)
    m = await _mint(factory, cid, _spec(rids[0]), 0)

    r = await resolve_publication_readiness(factory(), cid)
    assert r["ready"] and r["occurrence_count"] == 1
    assert r["direct_production_source_count"] == 1
    assert r["flattened_production_dependency_count"] == 1

    detail, created = await publish_composition_revision(
        factory(), cid, expected_working_version=1)
    assert created
    parsed = json.loads(detail["snapshot_json"])
    assert parsed["occurrences"][0]["occurrence_id"] == m["occurrence_id"]
    assert parsed["dependencies"]["production_revision_ids"] == [rids[0]]
    assert parsed["dependencies"]["composition_revision_ids"] == []


async def test_publish_rejects_empty_composition(engine, factory):
    """M12-PUB:09 + readiness COMPOSITION_EMPTY."""
    pid = await _seed_project(factory)
    cid = await _composition(factory, pid)
    r = await resolve_publication_readiness(factory(), cid)
    assert r["ready"] is False
    assert [i["code"] for i in r["issues"]] == [COMPOSITION_EMPTY]
    with pytest.raises(SoloRingError) as ei:
        await publish_composition_revision(
            factory(), cid, expected_working_version=0)
    assert ei.value.code == "COMPOSITION_NOT_READY"


async def test_publish_unchanged_working_state_converges(engine, factory):
    """M12-PUB:04 — content-addressed convergence incl. edit→revert."""
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)
    cid = await _composition(factory, pid)
    occ = (await _mint(factory, cid, _spec(rids[0]), 0))["occurrence_id"]

    d1, c1 = await publish_composition_revision(
        factory(), cid, expected_working_version=1)
    assert c1 is True
    # republish unchanged state → converged
    d2, c2 = await publish_composition_revision(
        factory(), cid, expected_working_version=1)
    assert c2 is False and d2["revision_id"] == d1["revision_id"]
    # edit then exact revert: content-addressed convergence to rev 1
    await patch_working_occurrence(
        factory(), cid, occ, scope="composition_working_state",
        expected_working_version=1, display_name="Temporary")
    await patch_working_occurrence(
        factory(), cid, occ, scope="composition_working_state",
        expected_working_version=2, display_name="Chair 7")
    d3, c3 = await publish_composition_revision(
        factory(), cid, expected_working_version=3)
    assert c3 is False and d3["revision_id"] == d1["revision_id"]


async def test_publish_changed_working_state_creates_next_revision(engine, factory):
    """M12-PUB:05 + :06 surviving IDs + :08 tokens untouched."""
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid, n=2)
    cid = await _composition(factory, pid)
    occ = (await _mint(factory, cid, _spec(rids[0]), 0))["occurrence_id"]

    d1, _ = await publish_composition_revision(
        factory(), cid, expected_working_version=1)
    await patch_working_occurrence(
        factory(), cid, occ, scope="composition_working_state",
        expected_working_version=1,
        source={"kind": "production_revision", "revision_id": rids[1]})
    d2, created = await publish_composition_revision(
        factory(), cid, expected_working_version=2)
    assert created and d2["revision_number"] == 2
    p1, p2 = json.loads(d1["snapshot_json"]), json.loads(d2["snapshot_json"])
    assert p1["occurrences"][0]["occurrence_id"] == occ
    assert p2["occurrences"][0]["occurrence_id"] == occ  # SAME identity
    assert (p1["occurrences"][0]["source"]["revision_id"] == rids[0]
            and p2["occurrences"][0]["source"]["revision_id"] == rids[1])
    # publication never changed concurrency tokens
    comp = (await _composition(factory, pid, name="unused"), None)[0] or None
    async with factory() as s:
        async with s.bind.connect() as conn:
            row = (await conn.execute(
                text("SELECT working_version, metadata_version FROM compositions "
                     "WHERE id = :c"), {"c": cid})).first()
    assert row.working_version == 2 and row.metadata_version == 0


async def test_publish_rejects_stale_expected_working_version(engine, factory):
    """M12-PUB:10."""
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)
    cid = await _composition(factory, pid)
    occ = (await _mint(factory, cid, _spec(rids[0]), 0))["occurrence_id"]
    # intervening edit advances the version
    await patch_working_occurrence(
        factory(), cid, occ, scope="composition_working_state",
        expected_working_version=1, display_name="Later")
    with pytest.raises(EditConflict) as ei:
        await publish_composition_revision(
            factory(), cid, expected_working_version=1)
    assert ei.value.details["reason"] == "stale_working_version"


async def test_publish_does_not_write_occurrence_identity_or_lineage(
    engine, factory, monkeypatch
):
    """M12-PUB:07 — structural write spy over the publish path."""
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)
    cid = await _composition(factory, pid)
    await _mint(factory, cid, _spec(rids[0]), 0)

    forbidden_writes: list[str] = []
    from sqlalchemy import event

    eng = engine.sync_engine

    @event.listens_for(eng, "before_cursor_execute")
    def _spy(conn, cursor, statement, parameters, context, executemany):
        low = statement.lower()
        if low.lstrip().startswith(("insert", "update", "delete")):
            for tbl in ("composition_occurrences",
                        "composition_identity_operations",
                        "composition_identity_operation_sources",
                        "composition_identity_operation_targets",
                        "composition_working_occurrences"):
                if tbl in low:
                    forbidden_writes.append(statement[:100])

    try:
        await publish_composition_revision(
            factory(), cid, expected_working_version=1)
        # convergence path must also stay identity-neutral
        await publish_composition_revision(
            factory(), cid, expected_working_version=1)
    finally:
        event.remove(eng, "before_cursor_execute", _spy)
    assert forbidden_writes == []


async def test_nested_closure_flattens_and_pins_exactly(engine, factory):
    """M12-NEST:01/02/03/04 — exact pinning + transitive flattening."""
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid, n=2)
    inner = await _composition(factory, pid, name="ReceptionModule")
    i_occ = (await _mint(factory, inner, _spec(rids[0]), 0))["occurrence_id"]
    inner_rev, _ = await publish_composition_revision(
        factory(), inner, expected_working_version=1)

    outer = await _composition(factory, pid, name="Lobby")
    await _mint(factory, outer, _spec(rids[1]), 0)
    nested_spec = {
        "display_name": "Reception",
        "source": {"kind": "composition_revision",
                   "revision_id": inner_rev["revision_id"]},
        "visible": True,
        "transform": {"translation_mm": [0, 0, 0], "rotation_udeg": [0, 0, 0]},
    }
    await _mint(factory, outer, nested_spec, 1)
    r = await resolve_publication_readiness(factory(), outer)
    assert r["flattened_production_dependency_count"] == 2  # both leaves
    assert r["flattened_nested_dependency_count"] == 1
    detail, _ = await publish_composition_revision(
        factory(), outer, expected_working_version=2)
    parsed = json.loads(detail["snapshot_json"])
    assert sorted(parsed["dependencies"]["production_revision_ids"]) == sorted(rids)
    assert parsed["dependencies"]["composition_revision_ids"] == [
        inner_rev["revision_id"]]

    # later nested publication does not change parent history (NEST:01/05)
    await patch_working_occurrence(
        factory(), inner, i_occ, scope="composition_working_state",
        expected_working_version=1, display_name="Changed")
    inner_rev2, _ = await publish_composition_revision(
        factory(), inner, expected_working_version=2)
    again = await load_composition_revision_detail(
        factory(), detail["revision_id"])
    assert again["snapshot_hash"] == detail["snapshot_hash"]
    parsed_again = json.loads(again["snapshot_json"])
    assert parsed_again["dependencies"]["composition_revision_ids"] == [
        inner_rev["revision_id"]]  # exact old revision, not latest


async def test_transitive_same_lineage_embedding_is_rejected(engine, factory):
    """M12-NEST:07 / M12-WORK:07 transitive case."""
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)
    a = await _composition(factory, pid, name="A")
    b = await _composition(factory, pid, name="B")
    # B rev1 contains A rev? — build: A publishes rev1 (contains pr), B
    # publishes rev1 containing A rev1; then A must reject B rev1 (its closure
    # contains A's own revision).
    await _mint(factory, a, _spec(rids[0]), 0)
    a_rev, _ = await publish_composition_revision(
        factory(), a, expected_working_version=1)
    nested_spec = {
        "display_name": "A module",
        "source": {"kind": "composition_revision",
                   "revision_id": a_rev["revision_id"]},
        "visible": True,
        "transform": {"translation_mm": [0, 0, 0], "rotation_udeg": [0, 0, 0]},
    }
    await _mint(factory, b, nested_spec, 0)
    b_rev, _ = await publish_composition_revision(
        factory(), b, expected_working_version=1)
    # now minting B rev1 INTO A must fail: B's closure contains A rev1
    with pytest.raises(SoloRingError) as ei:
        await _mint(factory, a, {
            "display_name": "B module",
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
    """M12-NEST:08 / M12-PUB:11 / M12-HISTORY:06 — snapshot and normalized
    rows cannot collude to omit a required dependency."""
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)
    cid = await _composition(factory, pid)
    await _mint(factory, cid, _spec(rids[0]), 0)
    detail, _ = await publish_composition_revision(
        factory(), cid, expected_working_version=1)
    rid = detail["revision_id"]

    # Corrupt BOTH representations consistently: remove the dependency from
    # the snapshot (recompute a self-consistent hash) and from both normalized
    # tables. Only independent rederivation from direct sources catches it.
    from soloring.domain.canonical import canonical_hash, canonical_json_str

    async with factory() as s:
        async with s.bind.connect() as conn:
            snap = json.loads(detail["snapshot_json"])
            snap["dependencies"]["production_revision_ids"] = []
            sj = canonical_json_str(snap)
            sh = canonical_hash(snap)
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await conn.execute(
                text("UPDATE composition_revisions SET snapshot_json = :sj, "
                     "snapshot_hash = :sh WHERE id = :r"),
                {"sj": sj, "sh": sh, "r": rid})
            await conn.execute(
                text("DELETE FROM composition_revision_production_dependencies "
                     "WHERE composition_revision_id = :r"), {"r": rid})
            await conn.exec_driver_sql("COMMIT")
    with pytest.raises(SoloRingError) as ei:
        await load_composition_revision_detail(factory(), rid)
    assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"


async def test_old_revision_ignores_current_working_edits(engine, factory):
    """M12-HISTORY:01/02/03/04."""
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid, n=2)
    cid = await _composition(factory, pid)
    occ = (await _mint(factory, cid, _spec(rids[0]), 0))["occurrence_id"]
    d1, _ = await publish_composition_revision(
        factory(), cid, expected_working_version=1)
    snapshot_before = d1["snapshot_json"]

    await patch_working_occurrence(
        factory(), cid, occ, scope="composition_working_state",
        expected_working_version=1, display_name="Renamed",
        transform={"translation_mm": [9, 9, 9], "rotation_udeg": [0, 0, 0]},
        source={"kind": "production_revision", "revision_id": rids[1]})
    await patch_composition_metadata(
        factory(), cid, expected_metadata_version=0, name="Renamed Lobby")

    d1_again = await load_composition_revision_detail(factory(), d1["revision_id"])
    assert d1_again["snapshot_json"] == snapshot_before


async def test_projection_corruption_fails_internal_invariant(engine, factory):
    """M12-HISTORY:05 / M12-NEST:06."""
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
                text("UPDATE composition_revision_occurrences SET display_name = "
                     "'Tampered' WHERE composition_revision_id = :r"),
                {"r": rid})
            await conn.exec_driver_sql("COMMIT")
    with pytest.raises(SoloRingError) as ei:
        await load_composition_revision_detail(factory(), rid)
    assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"
