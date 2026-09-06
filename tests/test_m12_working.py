"""M12 working-authoring proofs (frozen R3 §21 M12-WORK / M12-ID)."""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import text

from soloring.composition.service import (
    EditConflict,
    create_composition,
    get_composition,
    list_working_occurrences,
    mint_occurrence,
    patch_composition_metadata,
    patch_working_occurrence,
)
from soloring.errors import ErrorCode, SoloRingError
from soloring.domain.ids import new_uuid

NOW = "2026-01-01T00:00:00.000Z"
SPEC = {
    "display_name": "Chair 7",
    "source": {"kind": "production_revision",
               "revision_id": "11111111-1111-1111-1111-111111111111"},
    "visible": True,
    "transform": {"translation_mm": [0, 0, 0], "rotation_udeg": [0, 0, 0]},
}


async def _seed_project(factory) -> str:
    pid = new_uuid()
    async with factory() as s:
        async with s.bind.connect() as conn:
            await conn.execute(
                text("INSERT INTO projects (id, name, created_at, updated_at) "
                     "VALUES (:id, 'P', :n, :n)"), {"id": pid, "n": NOW})
            await conn.commit()
    return pid


async def _seed_production_revision(factory, pid) -> str:
    """One legal M11 revision row (closure verified by M11 machinery elsewhere)."""
    bh = hashlib.sha256(b"m12-working").hexdigest()
    oid, rid = new_uuid(), new_uuid()
    async with factory() as s:
        async with s.bind.connect() as conn:
            await conn.execute(
                text("INSERT INTO blobs (hash, path, size_bytes, detected_media_type, "
                     "created_at) VALUES (:h, :p, 12, NULL, :n)"),
                {"h": bh, "p": f"sha256/{bh[:2]}/{bh[2:4]}/{bh}", "n": NOW})
            await conn.execute(
                text("INSERT INTO production_objects (id, project_id, name, "
                     "created_at, updated_at) VALUES (:o, :p, 'Obj', :n, :n)"),
                {"o": oid, "p": pid, "n": NOW})
            await conn.execute(
                text("INSERT INTO production_revisions (id, production_object_id, "
                     "revision_number, snapshot_json, snapshot_hash, created_at) "
                     "VALUES (:r, :o, 1, '{}', :h, :n)"),
                {"r": rid, "o": oid, "h": "0" * 64, "n": NOW})
            await conn.execute(
                text("INSERT INTO production_revision_closures "
                     "(production_revision_id, contract_key, contract_version, "
                     "blob_hash, size_bytes, media_type) VALUES "
                     "(:r, 'retained_blob', 1, :bh, 12, NULL)"),
                {"r": rid, "bh": bh})
            await conn.commit()
    return rid


async def _composition(factory, pid, name="Lobby") -> str:
    comp = await create_composition(factory(), pid, name=name, description=None)
    return comp["id"]


async def _mint(factory, cid, spec=None, version=0):
    return await mint_occurrence(
        factory(), cid, scope="composition_working_state",
        expected_working_version=version, spec=spec or SPEC)


def _spec_with_revision(rid: str) -> dict:
    s = dict(SPEC)
    s["source"] = {"kind": "production_revision", "revision_id": rid}
    return s


async def test_create_composition_requires_active_project_inside_writer_fence(
    engine, factory
):
    """M12-WORK:01."""
    pid = await _seed_project(factory)
    async with factory() as s:
        async with s.bind.connect() as conn:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await conn.execute(
                text("UPDATE projects SET deleted_at = :n WHERE id = :p"),
                {"n": NOW, "p": pid})
            await conn.exec_driver_sql("COMMIT")
        with pytest.raises(SoloRingError) as ei:
            await create_composition(s, pid, name="Ghost")
        assert ei.value.code == "PROJECT_NOT_FOUND"
    async with factory() as s:
        async with s.bind.connect() as conn:
            n = (await conn.execute(
                text("SELECT COUNT(*) FROM compositions"))).scalar_one()
    assert n == 0


async def test_mint_records_birth_operation_and_working_membership_atomically(
    engine, factory
):
    """M12-WORK:02 + M12-ID:01."""
    pid = await _seed_project(factory)
    rid = await _seed_production_revision(factory, pid)
    cid = await _composition(factory, pid)
    result = await _mint(factory, cid, _spec_with_revision(rid))
    occ = result["occurrence_id"]
    assert occ != rid  # identity independent from source revision
    async with factory() as s:
        async with s.bind.connect() as conn:
            identity = (await conn.execute(
                text("SELECT composition_id FROM composition_occurrences "
                     "WHERE id = :o"), {"o": occ})).first()
            targets = (await conn.execute(
                text("SELECT COUNT(*) FROM composition_identity_operation_targets "
                     "WHERE occurrence_id = :o"), {"o": occ})).scalar_one()
            ops = (await conn.execute(
                text("SELECT operation_kind, working_version_before, "
                     "working_version_after FROM composition_identity_operations "
                     "WHERE composition_id = :c"), {"c": cid})).first()
            working = (await conn.execute(
                text("SELECT display_name FROM composition_working_occurrences "
                     "WHERE occurrence_id = :o"), {"o": occ})).first()
    assert identity.composition_id == cid
    assert targets == 1  # exactly one birth edge
    assert ops.operation_kind == "mint"
    assert (ops.working_version_before, ops.working_version_after) == (0, 1)
    assert working.display_name == "Chair 7"


async def test_working_mutation_requires_exact_expected_version(engine, factory):
    """M12-WORK:03 + :05."""
    pid = await _seed_project(factory)
    rid = await _seed_production_revision(factory, pid)
    cid = await _composition(factory, pid)
    occ = (await _mint(factory, cid, _spec_with_revision(rid)))["occurrence_id"]
    with pytest.raises(EditConflict) as ei:
        await patch_working_occurrence(
            factory(), cid, occ, scope="composition_working_state",
            expected_working_version=99, display_name="X")
    assert ei.value.details["reason"] == "stale_working_version"
    async with factory() as s:
        async with s.bind.connect() as conn:
            row = (await conn.execute(
                text("SELECT display_name, working_version FROM "
                     "composition_working_occurrences w JOIN compositions c "
                     "ON c.id = w.composition_id WHERE w.occurrence_id = :o"),
                {"o": occ})).first()
    assert row.display_name == "Chair 7"  # stale edit wrote nothing
    assert row.working_version == 1


async def test_successful_working_mutation_increments_version_once(engine, factory):
    """M12-WORK:04."""
    pid = await _seed_project(factory)
    rid = await _seed_production_revision(factory, pid)
    cid = await _composition(factory, pid)
    occ = (await _mint(factory, cid, _spec_with_revision(rid)))["occurrence_id"]
    out = await patch_working_occurrence(
        factory(), cid, occ, scope="composition_working_state",
        expected_working_version=1, display_name="Window Chair")
    assert out["working_version"] == 2
    comp = await get_composition(factory(), cid)
    assert comp["working_version"] == 2


async def test_cross_project_source_is_rejected(engine, factory):
    """M12-WORK:06."""
    pid = await _seed_project(factory)
    other = await _seed_project(factory)
    rid = await _seed_production_revision(factory, other)
    cid = await _composition(factory, pid)
    with pytest.raises(SoloRingError) as ei:
        await _mint(factory, cid, _spec_with_revision(rid))
    assert ei.value.code == ErrorCode.VALIDATION_ERROR


async def test_same_lineage_self_nested_revision_is_rejected(engine, factory):
    """M12-WORK:07 (direct case: R.composition_id == A)."""
    pid = await _seed_project(factory)
    cid = await _composition(factory, pid)
    # minimal direct-SQL revision of cid itself
    rev = new_uuid()
    async with factory() as s:
        async with s.bind.connect() as conn:
            await conn.execute(
                text("INSERT INTO composition_revisions (id, composition_id, "
                     "revision_number, snapshot_json, snapshot_hash, created_at) "
                     "VALUES (:r, :c, 1, '{}', :h, :n)"),
                {"r": rev, "c": cid, "h": "1" * 64, "n": NOW})
            await conn.commit()
    spec = {
        "display_name": "Self",
        "source": {"kind": "composition_revision", "revision_id": rev},
        "visible": True,
        "transform": {"translation_mm": [0, 0, 0], "rotation_udeg": [0, 0, 0]},
    }
    with pytest.raises(SoloRingError) as ei:
        await _mint(factory, cid, spec)
    assert "own lineage" in ei.value.message


async def test_metadata_patch_uses_metadata_version_without_advancing_working_version(
    engine, factory
):
    """M12-WORK:09 + :10."""
    pid = await _seed_project(factory)
    rid = await _seed_production_revision(factory, pid)
    cid = await _composition(factory, pid)
    await _mint(factory, cid, _spec_with_revision(rid))
    comp = await patch_composition_metadata(
        factory(), cid, expected_metadata_version=0, name="Grand Lobby")
    assert comp["metadata_version"] == 1
    assert comp["working_version"] == 1  # untouched by metadata edit
    with pytest.raises(EditConflict) as ei:
        await patch_composition_metadata(
            factory(), cid, expected_metadata_version=0, name="Stale")
    assert ei.value.details["reason"] == "stale_metadata_version"
    comp2 = await get_composition(factory(), cid)
    assert comp2["name"] == "Grand Lobby"  # stale patch wrote nothing


async def test_identity_preserving_edits(engine, factory):
    """M12-ID:03/04/05 + same-object source update ID:06."""
    pid = await _seed_project(factory)
    rid1 = await _seed_production_revision(factory, pid)
    cid = await _composition(factory, pid)
    occ = (await _mint(factory, cid, _spec_with_revision(rid1)))["occurrence_id"]

    out = await patch_working_occurrence(
        factory(), cid, occ, scope="composition_working_state",
        expected_working_version=1, display_name="Renamed")
    assert out["occurrence_id"] == occ
    out = await patch_working_occurrence(
        factory(), cid, occ, scope="composition_working_state",
        expected_working_version=2, visible=False)
    assert out["occurrence_id"] == occ
    out = await patch_working_occurrence(
        factory(), cid, occ, scope="composition_working_state",
        expected_working_version=3,
        transform={"translation_mm": [500, 0, 0], "rotation_udeg": [0, 0, 0]})
    assert out["occurrence_id"] == occ

    # same Production Object revision update preserves identity
    bh2 = hashlib.sha256(b"m12-working-2").hexdigest()
    rid2 = new_uuid()
    async with factory() as s:
        async with s.bind.connect() as conn:
            await conn.execute(
                text("INSERT INTO blobs (hash, path, size_bytes, detected_media_type, "
                     "created_at) VALUES (:h, :p, 12, NULL, :n)"),
                {"h": bh2, "p": f"sha256/{bh2[:2]}/{bh2[2:4]}/{bh2}", "n": NOW})
            obj = (await conn.execute(
                text("SELECT production_object_id FROM production_revisions "
                     "WHERE id = :r"), {"r": rid1})).scalar_one()
            await conn.execute(
                text("INSERT INTO production_revisions (id, production_object_id, "
                     "revision_number, snapshot_json, snapshot_hash, created_at) "
                     "VALUES (:r, :o, 2, '{}', :h, :n)"),
                {"r": rid2, "o": obj, "h": "2" * 64, "n": NOW})
            await conn.commit()
    out = await patch_working_occurrence(
        factory(), cid, occ, scope="composition_working_state",
        expected_working_version=4,
        source={"kind": "production_revision", "revision_id": rid2})
    assert out["occurrence_id"] == occ  # same identity, new source revision


async def test_cross_object_source_update_requires_replace_as_new(engine, factory):
    """M12-SCOPE:04 behavior (service level)."""
    pid = await _seed_project(factory)
    rid1 = await _seed_production_revision(factory, pid)
    cid = await _composition(factory, pid)
    occ = (await _mint(factory, cid, _spec_with_revision(rid1)))["occurrence_id"]
    rid_other = new_uuid()
    async with factory() as s:
        async with s.bind.connect() as conn:
            obj2 = new_uuid()
            await conn.execute(
                text("INSERT INTO production_objects (id, project_id, name, "
                     "created_at, updated_at) VALUES (:o, :p, 'Obj2', :n, :n)"),
                {"o": obj2, "p": pid, "n": NOW})
            await conn.execute(
                text("INSERT INTO production_revisions (id, production_object_id, "
                     "revision_number, snapshot_json, snapshot_hash, created_at) "
                     "VALUES (:r, :o, 1, '{}', :h, :n)"),
                {"r": rid_other, "o": obj2, "h": "3" * 64, "n": NOW})
            await conn.commit()
    with pytest.raises(SoloRingError) as ei:
        await patch_working_occurrence(
            factory(), cid, occ, scope="composition_working_state",
            expected_working_version=1,
            source={"kind": "production_revision", "revision_id": rid_other})
    assert ei.value.code == ErrorCode.VALIDATION_ERROR
    assert ei.value.details["identity_change_required"] is True
    assert ei.value.details["allowed_operation"] == "replace_as_new"


async def test_scope_is_mandatory_and_closed(engine, factory):
    """M12-SCOPE:01/02/03 (service level)."""
    pid = await _seed_project(factory)
    rid = await _seed_production_revision(factory, pid)
    cid = await _composition(factory, pid)
    for bad in (None, "shot_local", "story_state", "unknown_scope"):
        with pytest.raises(SoloRingError) as ei:
            await mint_occurrence(
                factory(), cid, scope=bad, expected_working_version=0,
                spec=_spec_with_revision(rid))
        assert ei.value.code == ErrorCode.VALIDATION_ERROR


async def test_transform_is_explicit_and_grammar_enforced(engine, factory):
    """No silent [0,0,0]; JS-safe domain; rotation normalization."""
    from soloring.spatial.math import JS_SAFE_MAX

    pid = await _seed_project(factory)
    rid = await _seed_production_revision(factory, pid)
    cid = await _composition(factory, pid)
    spec = _spec_with_revision(rid)
    spec["transform"] = {"translation_mm": [JS_SAFE_MAX + 1, 0, 0],
                         "rotation_udeg": [0, 0, 0]}
    with pytest.raises(SoloRingError):
        await _mint(factory, cid, spec)
    # +180000000 canonicalizes to -180000000 before storage
    spec["transform"] = {"translation_mm": [0, 0, 0],
                         "rotation_udeg": [180000000, 0, 0]}
    out = await _mint(factory, cid, spec)
    async with factory() as s:
        async with s.bind.connect() as conn:
            yaw = (await conn.execute(
                text("SELECT yaw_udeg FROM composition_working_occurrences "
                     "WHERE occurrence_id = :o"),
                {"o": out["occurrence_id"]})).scalar_one()
    assert yaw == -180000000


# --- frozen proof-map owner aliases (M12-WORK:05/:08/:10) -------------------


async def test_stale_working_version_writes_nothing(engine, factory):
    """Alias owner: stale edit produces zero partial writes."""
    pid = await _seed_project(factory)
    rid = await _seed_production_revision(factory, pid)
    cid = await _composition(factory, pid)
    occ = (await _mint(factory, cid, _spec_with_revision(rid), 0))["occurrence_id"]
    with pytest.raises(EditConflict):
        await patch_working_occurrence(
            factory(), cid, occ, scope="composition_working_state",
            expected_working_version=99, display_name="X")
    async with factory() as s:
        async with s.bind.connect() as conn:
            row = (await conn.execute(
                text("SELECT display_name FROM composition_working_occurrences "
                     "WHERE occurrence_id = :o"), {"o": occ})).first()
    assert row.display_name == "Chair 7"


async def test_terminated_occurrence_cannot_return_to_working_state(
    engine, factory
):
    """Alias owner: terminated identity refuses ordinary PATCH."""
    from soloring.composition.impacts import (
        apply_identity_operation,
        preview_identity_operation,
    )

    pid = await _seed_project(factory)
    rid = await _seed_production_revision(factory, pid)
    cid = await _composition(factory, pid)
    occ = (await _mint(factory, cid, _spec_with_revision(rid), 0))["occurrence_id"]
    request = {"kind": "remove", "source_occurrence_ids": [occ],
               "target_working_specs": []}
    p = await preview_identity_operation(factory(), cid, request=request)
    await apply_identity_operation(
        factory(), cid, scope="composition_working_state",
        expected_working_version=1,
        expected_request_fingerprint=p["request_fingerprint"],
        expected_impact_fingerprint=p["impact_fingerprint"],
        request=request)
    with pytest.raises(SoloRingError):
        await patch_working_occurrence(
            factory(), cid, occ, scope="composition_working_state",
            expected_working_version=2, display_name="Zombie")


async def test_stale_metadata_version_writes_nothing(engine, factory):
    """Alias owner: stale metadata PATCH cannot overwrite newer metadata."""
    pid = await _seed_project(factory)
    rid = await _seed_production_revision(factory, pid)
    cid = await _composition(factory, pid)
    await _mint(factory, cid, _spec_with_revision(rid), 0)
    await patch_composition_metadata(
        factory(), cid, expected_metadata_version=0, name="First")
    with pytest.raises(EditConflict):
        await patch_composition_metadata(
            factory(), cid, expected_metadata_version=0, name="Stale")
    comp = await get_composition(factory(), cid)
    assert comp["name"] == "First"
