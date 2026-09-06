"""M12 identity-operation proofs (frozen R3 §21 M12-LINEAGE / §12.2)."""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import text

from soloring.composition.impacts import (
    apply_identity_operation,
    preview_identity_operation,
    verify_identity_history,
)
from soloring.composition.service import (
    EditConflict,
    create_composition,
    mint_occurrence,
    patch_working_occurrence,
)
from soloring.errors import SoloRingError
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


_SEED_SALT = [0]


async def _seed_production(factory, pid, n=2) -> list[str]:
    rids = []
    salt = _SEED_SALT[0]
    _SEED_SALT[0] += 1
    async with factory() as s:
        async with s.bind.connect() as conn:
            obj = new_uuid()
            await conn.execute(
                text("INSERT INTO production_objects (id, project_id, name, "
                     "created_at, updated_at) VALUES (:o, :p, 'Obj', :n, :n)"),
                {"o": obj, "p": pid, "n": NOW})
            for i in range(n):
                bh = hashlib.sha256(f"m12-lin-{salt}-{i}".encode()).hexdigest()
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


def _spec(rid, name="Chair") -> dict:
    return {
        "display_name": name,
        "source": {"kind": "production_revision", "revision_id": rid},
        "visible": True,
        "transform": {"translation_mm": [0, 0, 0], "rotation_udeg": [0, 0, 0]},
    }


async def _composition(factory, pid, name="Lobby") -> str:
    return (await create_composition(factory(), pid, name=name, description=None))["id"]


async def _mint(factory, cid, spec, version) -> str:
    return (await mint_occurrence(
        factory(), cid, scope=SCOPE, expected_working_version=version,
        spec=spec))["occurrence_id"]


async def _preview_apply(session, cid, kind, sources, specs, version):
    request = {"kind": kind, "source_occurrence_ids": sources,
               "target_working_specs": specs}
    p = await preview_identity_operation(session, cid, request=request)
    return await apply_identity_operation(
        session, cid, scope=SCOPE, expected_working_version=version,
        expected_request_fingerprint=p["request_fingerprint"],
        expected_impact_fingerprint=p["impact_fingerprint"],
        request=request)


async def test_remove_terminates_source_with_zero_target(engine, factory):
    """M12-LINEAGE:01."""
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)
    cid = await _composition(factory, pid)
    occ = await _mint(factory, cid, _spec(rids[0]), 0)
    out = await _preview_apply(factory(), cid, "remove", [occ], [], 1)
    assert out["target_occurrence_ids"] == []
    async with factory() as s:
        async with s.bind.connect() as conn:
            working = (await conn.execute(
                text("SELECT COUNT(*) FROM composition_working_occurrences "
                     "WHERE occurrence_id = :o"), {"o": occ})).scalar_one()
    assert working == 0
    history = await verify_identity_history(factory(), cid)
    assert history[-1]["kind"] == "remove"


async def test_replace_as_new_terminates_old_and_mints_one_new(engine, factory):
    """M12-LINEAGE:02 + fingerprint binding :10."""
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)
    cid = await _composition(factory, pid)
    occ = await _mint(factory, cid, _spec(rids[0]), 0)
    out = await _preview_apply(
        factory(), cid, "replace_as_new", [occ], [_spec(rids[1], name="Chair 8")], 1)
    new_id = out["target_occurrence_ids"][0]
    assert new_id != occ
    async with factory() as s:
        async with s.bind.connect() as conn:
            old_working = (await conn.execute(
                text("SELECT COUNT(*) FROM composition_working_occurrences "
                     "WHERE occurrence_id = :o"), {"o": occ})).scalar_one()
            new_working = (await conn.execute(
                text("SELECT display_name FROM composition_working_occurrences "
                     "WHERE occurrence_id = :o"), {"o": new_id})).first()
    assert old_working == 0
    assert new_working.display_name == "Chair 8"
    await verify_identity_history(factory(), cid)


async def test_split_and_merge_cardinality(engine, factory):
    """M12-LINEAGE:03/:04."""
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)
    cid = await _composition(factory, pid)
    occ = await _mint(factory, cid, _spec(rids[0]), 0)
    out = await _preview_apply(
        factory(), cid, "split", [occ],
        [_spec(rids[0], name="Left"), _spec(rids[0], name="Right")], 1)
    a, b = out["target_occurrence_ids"]
    assert a != b
    await verify_identity_history(factory(), cid)
    out2 = await _preview_apply(
        factory(), cid, "merge", [a, b], [_spec(rids[0], name="Merged")], 2)
    assert len(out2["target_occurrence_ids"]) == 1
    await verify_identity_history(factory(), cid)


async def test_fork_preserves_source_and_mints_one_target(engine, factory):
    """M12-LINEAGE:05/:14 — repeated forks legal."""
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)
    cid = await _composition(factory, pid)
    occ = await _mint(factory, cid, _spec(rids[0]), 0)
    out1 = await _preview_apply(
        factory(), cid, "fork", [occ], [_spec(rids[0], name="Fork 1")], 1)
    out2 = await _preview_apply(
        factory(), cid, "fork", [occ], [_spec(rids[0], name="Fork 2")], 2)
    d1, d2 = out1["target_occurrence_ids"][0], out2["target_occurrence_ids"][0]
    assert len({occ, d1, d2}) == 3
    async with factory() as s:
        async with s.bind.connect() as conn:
            still_working = (await conn.execute(
                text("SELECT COUNT(*) FROM composition_working_occurrences "
                     "WHERE occurrence_id = :o"), {"o": occ})).scalar_one()
    assert still_working == 1  # source remains active across both forks
    await verify_identity_history(factory(), cid)


async def test_identity_can_terminate_at_most_once(engine, factory):
    """M12-LINEAGE:06/:12 — terminated source cannot be reused."""
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)
    cid = await _composition(factory, pid)
    occ = await _mint(factory, cid, _spec(rids[0]), 0)
    await _preview_apply(factory(), cid, "remove", [occ], [], 1)
    # a second remove of the same (now terminated) identity
    request = {"kind": "remove", "source_occurrence_ids": [occ],
               "target_working_specs": []}
    p = await preview_identity_operation(factory(), cid, request=request)
    with pytest.raises(SoloRingError) as ei:
        await apply_identity_operation(
            factory(), cid, scope=SCOPE, expected_working_version=2,
            expected_request_fingerprint=p["request_fingerprint"],
            expected_impact_fingerprint=p["impact_fingerprint"],
            request=request)
    assert ei.value.code == "COMPOSITION_EDIT_CONFLICT"
    assert ei.value.details["reason"] == "stale_impact"  # frozen §8.4 fence
    # DB-level partial unique also enforces it
    async with factory() as s:
        async with s.bind.connect() as conn:
            import sqlite3
            op2 = new_uuid()
            await conn.execute(
                text("INSERT INTO composition_identity_operations (id, "
                     "composition_id, operation_kind, working_version_before, "
                     "working_version_after, request_fingerprint, "
                     "impact_fingerprint, operation_json, operation_hash, "
                     "created_at) VALUES (:i, :c, 'remove', 9, 10, :r, :m, "
                     "'{}', :h, :n)"),
                {"i": op2, "c": cid, "r": "9" * 64, "m": "8" * 64,
                 "h": "7" * 64, "n": NOW})
            from sqlalchemy.exc import IntegrityError as SAIntegrityError
            with pytest.raises(SAIntegrityError):
                await conn.execute(
                    text("INSERT INTO composition_identity_operation_sources "
                         "(composition_id, operation_id, occurrence_id, "
                         "terminates_identity) VALUES (:c, :o, :occ, 1)"),
                    {"c": cid, "o": op2, "occ": occ})
            await conn.rollback()


async def test_every_occurrence_has_exactly_one_birth_target(engine, factory):
    """M12-LINEAGE:07 — verifier catches missing birth."""
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)
    cid = await _composition(factory, pid)
    await _mint(factory, cid, _spec(rids[0]), 0)
    await verify_identity_history(factory(), cid)
    # corrupt: insert an orphan occurrence row (FK-bypassed fixture)
    import sqlite3

    orphan = new_uuid()
    db_path = engine.url.database
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys=OFF")
    con.execute(
        "INSERT INTO composition_occurrences (id, composition_id, created_at) "
        "VALUES (?, ?, ?)", (orphan, cid, NOW))
    con.commit()
    con.close()
    with pytest.raises(SoloRingError) as ei:
        await verify_identity_history(factory(), cid)
    assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"


async def test_identity_operation_json_hash_matches_normalized_edges(
    engine, factory
):
    """M12-LINEAGE:08."""
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)
    cid = await _composition(factory, pid)
    occ = await _mint(factory, cid, _spec(rids[0]), 0)
    out = await _preview_apply(
        factory(), cid, "replace_as_new", [occ], [_spec(rids[1], name="New")], 1)
    async with factory() as s:
        async with s.bind.connect() as conn:
            op = (await conn.execute(
                text("SELECT operation_json, operation_hash FROM "
                     "composition_identity_operations "
                     "WHERE id = :i"),
                {"i": out["operation_id"]})).first()
    from soloring.domain.canonical import canonical_hash

    assert canonical_hash(__import__("json").loads(op.operation_json)) == op.operation_hash


async def test_identity_targets_use_same_validator_as_mint(engine, factory):
    """M12-LINEAGE:11 — cross-project source cannot sneak through apply."""
    pid = await _seed_project(factory)
    other_pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)
    other_rids = await _seed_production(factory, other_pid)
    cid = await _composition(factory, pid)
    occ = await _mint(factory, cid, _spec(rids[0]), 0)
    request = {"kind": "replace_as_new", "source_occurrence_ids": [occ],
               "target_working_specs": [_spec(other_rids[0], name="Bad")]}
    with pytest.raises(SoloRingError) as ei:
        await preview_identity_operation(factory(), cid, request=request)
    assert ei.value.code == "VALIDATION_ERROR"


async def test_apply_rejects_stale_request_or_impact_after_intervening_change(
    engine, factory
):
    """M12-RACE:05 service-level — exact request replay required."""
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)
    cid = await _composition(factory, pid)
    occ = await _mint(factory, cid, _spec(rids[0]), 0)
    request = {"kind": "replace_as_new", "source_occurrence_ids": [occ],
               "target_working_specs": [_spec(rids[1], name="New")]}
    p = await preview_identity_operation(factory(), cid, request=request)
    # tamper fingerprints
    with pytest.raises(EditConflict) as ei:
        await apply_identity_operation(
            factory(), cid, scope=SCOPE, expected_working_version=1,
            expected_request_fingerprint="0" * 64,
            expected_impact_fingerprint=p["impact_fingerprint"],
            request=request)
    assert ei.value.details["reason"] == "stale_request"
    with pytest.raises(EditConflict) as ei:
        await apply_identity_operation(
            factory(), cid, scope=SCOPE, expected_working_version=1,
            expected_request_fingerprint=p["request_fingerprint"],
            expected_impact_fingerprint="0" * 64,
            request=request)
    assert ei.value.details["reason"] == "stale_impact"
    # an intervening working edit changes working_version → stale fence
    await patch_working_occurrence(
        factory(), cid, occ, scope=SCOPE,
        expected_working_version=1, display_name="Intervening")
    with pytest.raises(EditConflict) as ei:
        await apply_identity_operation(
            factory(), cid, scope=SCOPE, expected_working_version=1,
            expected_request_fingerprint=p["request_fingerprint"],
            expected_impact_fingerprint=p["impact_fingerprint"],
            request=request)
    assert ei.value.details["reason"] == "stale_working_version"
    # zero partial mutation from the failed applies
    async with factory() as s:
        async with s.bind.connect() as conn:
            n_ops = (await conn.execute(
                text("SELECT COUNT(*) FROM composition_identity_operations "
                     "WHERE composition_id = :c"), {"c": cid})).scalar_one()
    assert n_ops == 1  # only the original mint


async def test_terminated_occurrence_cannot_return_to_working_state(
    engine, factory
):
    """M12-WORK:08 — PATCH on a terminated identity is refused."""
    pid = await _seed_project(factory)
    rids = await _seed_production(factory, pid)
    cid = await _composition(factory, pid)
    occ = await _mint(factory, cid, _spec(rids[0]), 0)
    await _preview_apply(factory(), cid, "remove", [occ], [], 1)
    with pytest.raises(SoloRingError):
        await patch_working_occurrence(
            factory(), cid, occ, scope=SCOPE,
            expected_working_version=2, display_name="Zombie")
