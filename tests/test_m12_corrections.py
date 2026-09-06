"""M12 source-review correction proofs (F2–F7).

One adversarial owner per finding: fenced metadata CAS under a real
competing writer; explicit-null description semantics; publish zero-commit
negatives under working corruption and project soft-delete; transform
cardinality; normalized-vs-immutable lineage evidence divergence; and
many-direct-nested readiness through the real resolver.
"""

from __future__ import annotations

import asyncio
import hashlib
import json

import pytest
from sqlalchemy import event, text

from soloring.composition.readiness import (
    publish_composition_revision,
    resolve_publication_readiness,
)
from soloring.composition.service import (
    CLEAR_DESCRIPTION,
    EditConflict,
    create_composition,
    mint_occurrence,
    patch_composition_metadata,
    patch_working_occurrence,
)
from soloring.composition.impacts import verify_identity_history
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


async def _seed_production(factory, pid, salt="c") -> str:
    bh = hashlib.sha256(f"m12-fix-{salt}".encode()).hexdigest()
    rid, obj = new_uuid(), new_uuid()
    async with factory() as s:
        async with s.bind.connect() as conn:
            await conn.execute(
                text("INSERT INTO blobs (hash, path, size_bytes, "
                     "detected_media_type, created_at) VALUES "
                     "(:h, :p, 8, NULL, :n)"),
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
                     "VALUES (:r, 'retained_blob', 1, :bh, 8, NULL)"),
                {"r": rid, "bh": bh})
            await conn.commit()
    return rid


def _spec(rid, name="Chair", pos=(0, 0, 0)) -> dict:
    return {
        "display_name": name,
        "source": {"kind": "production_revision", "revision_id": rid},
        "visible": True,
        "transform": {"translation_mm": list(pos), "rotation_udeg": [0, 0, 0]},
    }


async def _comp(factory, pid, name="L") -> str:
    return (await create_composition(factory(), pid, name=name,
                                     description=None))["id"]


async def _mint(factory, cid, spec, version) -> str:
    return (await mint_occurrence(
        factory(), cid, scope=SCOPE, expected_working_version=version,
        spec=spec))["occurrence_id"]


# --- F2a: competing metadata writers under a real parked fence ---------------


async def test_competing_metadata_writers_only_one_commits(engine, factory):
    """Two concurrent metadata PATCHes at the same expected version: the
    loser must fail with stale_metadata_version/fence_race, never silently
    overwrite — the CAS runs under the writer fence."""
    pid = await _seed_project(factory)
    cid = await _comp(factory, pid)
    leader_acquired = asyncio.Event()
    follower_at_seam = asyncio.Event()

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _seam(conn, cursor, statement, parameters, context, executemany):
        if "BEGIN IMMEDIATE" in statement and leader_acquired.is_set():
            follower_at_seam.set()

    leader = await engine.connect()
    try:
        await leader.exec_driver_sql("BEGIN IMMEDIATE")
        leader_acquired.set()

        async def follower_patch():
            return await patch_composition_metadata(
                factory(), cid, expected_metadata_version=0, name="Follower")

        task = asyncio.ensure_future(follower_patch())
        await asyncio.wait_for(follower_at_seam.wait(), timeout=10)
        await asyncio.sleep(0)
        # leader commits its own metadata PATCH first
        await leader.execute(
            text("UPDATE compositions SET name = 'Leader', "
                 "metadata_version = 1 WHERE id = :c"), {"c": cid})
        await leader.exec_driver_sql("COMMIT")
        with pytest.raises(EditConflict) as ei:
            await asyncio.wait_for(task, timeout=30)
        assert ei.value.details["reason"] in (
            "stale_metadata_version", "fence_race")
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _seam)
        await leader.close()
    async with factory() as s:
        async with s.bind.connect() as conn:
            row = (await conn.execute(
                text("SELECT name, metadata_version FROM compositions "
                     "WHERE id = :c"), {"c": cid})).first()
    assert row.name == "Leader" and row.metadata_version == 1


# --- F2b: explicit null clears, omission leaves unchanged --------------------


async def test_explicit_null_clears_description_but_omission_keeps_it(
    engine, factory
):
    pid = await _seed_project(factory)
    cid = (await create_composition(factory(), pid, name="L",
                                    description="original"))["id"]
    out = await patch_composition_metadata(
        factory(), cid, expected_metadata_version=0,
        description=CLEAR_DESCRIPTION)
    assert out["description"] is None
    out2 = await patch_composition_metadata(
        factory(), cid, expected_metadata_version=1, name="Renamed")
    assert out2["description"] is None  # omitted → unchanged (still None)
    out3 = await patch_composition_metadata(
        factory(), cid, expected_metadata_version=2, description="set again")
    assert out3["description"] == "set again"
    out4 = await patch_composition_metadata(
        factory(), cid, expected_metadata_version=3, name="NoDescChange")
    assert out4["description"] == "set again"  # omission never clears


async def test_api_explicit_null_vs_omitted_description(client):
    from tests.test_m12_api import _seed

    pid, _ = await _seed(client)
    r = await client.post(f"/projects/{pid}/compositions",
                          json={"name": "L", "description": "original"})
    cid = r.json()["id"]
    r = await client.patch(f"/compositions/{cid}",
                           json={"expected_metadata_version": 0,
                                 "description": None})
    assert r.json()["description"] is None
    r = await client.patch(f"/compositions/{cid}",
                           json={"expected_metadata_version": 1, "name": "R"})
    assert r.json()["description"] is None


# --- F3: publish zero-commit negatives ---------------------------------------


async def test_publish_rejects_transitive_self_lineage_working_corruption_before_commit(  # noqa: E501
    engine, factory
):
    """A corrupt working row referencing a nested revision whose closure
    contains the parent lineage is refused BEFORE any revision is committed."""
    pid = await _seed_project(factory)
    rid = await _seed_production(factory, pid, "a")
    a = await _comp(factory, pid, name="A")
    await _mint(factory, a, _spec(rid), 0)
    a_rev, _ = await publish_composition_revision(
        factory(), a, expected_working_version=1)
    b = await _comp(factory, pid, name="B")
    await _mint(factory, b, {
        "display_name": "A mod",
        "source": {"kind": "composition_revision",
                   "revision_id": a_rev["revision_id"]},
        "visible": True,
        "transform": {"translation_mm": [0, 0, 0], "rotation_udeg": [0, 0, 0]},
    }, 0)
    b_rev, _ = await publish_composition_revision(
        factory(), b, expected_working_version=1)
    # corrupt: place B rev1 into A's working state directly (FK-bypassed)
    import sqlite3

    db_path = engine.url.database
    occ = new_uuid()
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys=OFF")
    con.execute(
        "INSERT INTO composition_occurrences (id, composition_id, created_at) "
        "VALUES (?, ?, ?)", (occ, a, NOW))
    con.execute(
        "INSERT INTO composition_working_occurrences (composition_id, "
        "occurrence_id, display_name, source_kind, "
        "nested_composition_revision_id, visible, x_mm, y_mm, z_mm, yaw_udeg, "
        "pitch_udeg, roll_udeg, updated_at) VALUES "
        "(?, ?, 'B mod', 'composition_revision', ?, 1, 0, 0, 0, 0, 0, 0, ?)",
        (a, occ, b_rev["revision_id"], NOW))
    con.commit()
    con.close()
    with pytest.raises(SoloRingError) as ei:
        await publish_composition_revision(
            factory(), a, expected_working_version=1)
    assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"
    async with factory() as s:
        async with s.bind.connect() as conn:
            n = (await conn.execute(
                text("SELECT COUNT(*) FROM composition_revisions "
                     "WHERE composition_id = :c"), {"c": a})).scalar_one()
    assert n == 1  # only the original valid revision: ZERO corrupt commits


async def test_publish_refused_after_project_soft_delete_without_version_change(
    engine, factory
):
    """Project soft-deleted between freeze and fence (working_version
    unchanged) → publish refuses, nothing committed."""
    pid = await _seed_project(factory)
    rid = await _seed_production(factory, pid, "b")
    cid = await _comp(factory, pid)
    await _mint(factory, cid, _spec(rid), 0)
    async with factory() as s:
        async with s.bind.connect() as conn:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await conn.execute(
                text("UPDATE projects SET deleted_at = :n WHERE id = :p"),
                {"n": NOW, "p": pid})
            await conn.exec_driver_sql("COMMIT")
    with pytest.raises(SoloRingError) as ei:
        await publish_composition_revision(
            factory(), cid, expected_working_version=1)
    assert ei.value.code == "COMPOSITION_NOT_FOUND"
    async with factory() as s:
        async with s.bind.connect() as conn:
            n = (await conn.execute(
                text("SELECT COUNT(*) FROM composition_revisions "
                     "WHERE composition_id = :c"), {"c": cid})).scalar_one()
    assert n == 0


async def test_working_patch_refused_after_project_soft_delete(engine, factory):
    pid = await _seed_project(factory)
    rid = await _seed_production(factory, pid, "c")
    cid = await _comp(factory, pid)
    occ = await _mint(factory, cid, _spec(rid), 0)
    async with factory() as s:
        async with s.bind.connect() as conn:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await conn.execute(
                text("UPDATE projects SET deleted_at = :n WHERE id = :p"),
                {"n": NOW, "p": pid})
            await conn.exec_driver_sql("COMMIT")
    with pytest.raises(SoloRingError) as ei:
        await patch_working_occurrence(
            factory(), cid, occ, scope=SCOPE, expected_working_version=1,
            display_name="Ghost edit")
    assert ei.value.code == "COMPOSITION_NOT_FOUND"


# --- F4: transform cardinality negatives --------------------------------------


async def test_transform_cardinality_is_exact_at_service_and_http(
    engine, factory, client
):
    pid = await _seed_project(factory)
    rid = await _seed_production(factory, pid, "d")
    cid = await _comp(factory, pid)
    for bad in (
        {"translation_mm": [1, 2], "rotation_udeg": [0, 0, 0]},
        {"translation_mm": [1, 2, 3, 4], "rotation_udeg": [0, 0, 0]},
        {"translation_mm": [1, 2, 3], "rotation_udeg": [0, 0]},
        {"translation_mm": [1, 2, 3], "rotation_udeg": [0, 0, 0, 0]},
        {"translation_mm": [1, "x", 3], "rotation_udeg": [0, 0, 0]},
    ):
        spec = _spec(rid)
        spec["transform"] = bad
        with pytest.raises(SoloRingError) as ei:
            await mint_occurrence(factory(), cid, scope=SCOPE,
                                  expected_working_version=0, spec=spec)
        assert ei.value.code == "VALIDATION_ERROR"

    # HTTP level
    from tests.test_m12_api import _seed, _mint_body

    hpid, hprid = await _seed(client)
    hcid = (await client.post(f"/projects/{hpid}/compositions",
                              json={"name": "L"})).json()["id"]
    body = _mint_body(hprid, 0)
    body["transform"] = {"translation_mm": [1, 2],
                         "rotation_udeg": [0, 0, 0]}
    r = await client.post(f"/compositions/{hcid}/occurrences", json=body)
    assert r.status_code == 422


# --- F5: normalized evidence vs immutable evidence divergence ----------------


async def test_lineage_verifier_detects_evidence_divergence(engine, factory):
    """Perturb the NORMALIZED edges while leaving the canonical immutable
    evidence intact: the complete field-equivalence verifier must fail."""
    pid = await _seed_project(factory)
    rid = await _seed_production(factory, pid, "e")
    cid = await _comp(factory, pid)
    occ = await _mint(factory, cid, _spec(rid), 0)
    await verify_identity_history(factory(), cid)

    async with factory() as s:
        async with s.bind.connect() as conn:
            op = (await conn.execute(
                text("SELECT id FROM composition_identity_operations "
                     "WHERE composition_id = :c"), {"c": cid})).scalar_one()
            # divergence: flip the normalized terminates flag on a mint —
            # mint has NO sources, so instead tamper the target edge set
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await conn.execute(
                text("DELETE FROM composition_identity_operation_targets "
                     "WHERE operation_id = :o"), {"o": op})
            await conn.exec_driver_sql("COMMIT")
    with pytest.raises(SoloRingError) as ei:
        await verify_identity_history(factory(), cid)
    assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"


async def test_lineage_verifier_requires_active_working_membership(engine, factory):
    """A live nonterminated occurrence missing from working membership
    (working row deleted) is corruption, not silence."""
    pid = await _seed_project(factory)
    rid = await _seed_production(factory, pid, "f")
    cid = await _comp(factory, pid)
    occ = await _mint(factory, cid, _spec(rid), 0)
    async with factory() as s:
        async with s.bind.connect() as conn:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await conn.execute(
                text("DELETE FROM composition_working_occurrences "
                     "WHERE occurrence_id = :o AND composition_id = :c"),
                {"o": occ, "c": cid})
            await conn.exec_driver_sql("COMMIT")
    with pytest.raises(SoloRingError) as ei:
        await verify_identity_history(factory(), cid)
    assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"


async def test_lineage_verifier_detects_operation_field_tamper(engine, factory):
    """Row column tampered while canonical evidence intact → divergence."""
    pid = await _seed_project(factory)
    rid = await _seed_production(factory, pid, "g")
    cid = await _comp(factory, pid)
    await _mint(factory, cid, _spec(rid), 0)
    async with factory() as s:
        async with s.bind.connect() as conn:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await conn.execute(
                text("UPDATE composition_identity_operations SET "
                     "request_fingerprint = :rf WHERE composition_id = :c"),
                {"rf": "f" * 64, "c": cid})
            await conn.exec_driver_sql("COMMIT")
    with pytest.raises(SoloRingError) as ei:
        await verify_identity_history(factory(), cid)
    assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"


# --- F6: many-direct-nested readiness through the REAL resolver -------------


async def test_many_direct_nested_sources_resolve_in_bounded_queries(
    engine, factory
):
    """100 direct nested occurrences through the real readiness path must
    use bounded (set-oriented) queries, not 2-per-nested-revision."""
    pid = await _seed_project(factory)
    leaf_rid = await _seed_production(factory, pid, "leaf")
    # build 100 independently published modules
    module_ids = []
    for i in range(100):
        m = await _comp(factory, pid, name=f"M{i}")
        await _mint(factory, m, _spec(leaf_rid), 0)
        rev, _ = await publish_composition_revision(
            factory(), m, expected_working_version=1)
        module_ids.append(rev["revision_id"])

    outer = await _comp(factory, pid, name="Outer")
    for i, mrev in enumerate(module_ids):
        await _mint(factory, outer, {
            "display_name": f"Mod {i}",
            "source": {"kind": "composition_revision", "revision_id": mrev},
            "visible": True,
            "transform": {"translation_mm": [0, 0, 0],
                          "rotation_udeg": [0, 0, 0]},
        }, i)

    from sqlalchemy import event as _event

    selects: list[str] = []

    @_event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _spy(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().lower().startswith("select"):
            selects.append(statement)

    try:
        r = await resolve_publication_readiness(factory(), outer)
    finally:
        _event.remove(engine.sync_engine, "before_cursor_execute", _spy)
    assert r["ready"] and r["occurrence_count"] == 100
    assert r["flattened_nested_dependency_count"] == 100
    assert r["flattened_production_dependency_count"] == 1
    # bounded: integrity + closure + ownership resolved set-oriented
    assert len(selects) < 30, len(selects)


# --- F7: preview scope rejection ---------------------------------------------


async def test_identity_preview_rejects_missing_shot_local_and_unknown_scope(
    client
):
    from tests.test_m12_api import _seed, _mint_body

    pid, prid = await _seed(client)
    cid = (await client.post(f"/projects/{pid}/compositions",
                             json={"name": "L"})).json()["id"]
    occ = (await client.post(f"/compositions/{cid}/occurrences",
                             json=_mint_body(prid, 0))).json()["occurrence_id"]
    request = {"kind": "remove", "source_occurrence_ids": [occ],
               "target_working_specs": []}
    for bad_scope in (None, "shot_local", "story_state", "unknown_v2"):
        body = {"request": request}
        if bad_scope is not None:
            body["scope"] = bad_scope
        r = await client.post(
            f"/compositions/{cid}/identity-operations/preview", json=body)
        assert r.status_code == 422, (bad_scope, r.text)


async def test_publish_rejects_raw_noncanonical_rotation_before_commit(
    engine, factory
):
    """F3 residual: a raw working row with yaw=+180000000 (which Transform
    would silently canonicalize to -180000000 in the snapshot) must be
    refused BEFORE commit — proving COUNT(composition_revisions) unchanged."""
    pid = await _seed_project(factory)
    rid = await _seed_production(factory, pid, "raw180")
    cid = await _comp(factory, pid)
    occ = await _mint(factory, cid, _spec(rid), 0)
    async with factory() as s:
        async with s.bind.connect() as conn:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await conn.execute(
                text("UPDATE composition_working_occurrences SET yaw_udeg = "
                     "180000000 WHERE occurrence_id = :o AND composition_id "
                     "= :c"), {"o": occ, "c": cid})
            await conn.exec_driver_sql("COMMIT")
    with pytest.raises(SoloRingError) as ei:
        await publish_composition_revision(
            factory(), cid, expected_working_version=1)
    assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"
    assert "canonical" in ei.value.message
    async with factory() as s:
        async with s.bind.connect() as conn:
            n = (await conn.execute(
                text("SELECT COUNT(*) FROM composition_revisions "
                     "WHERE composition_id = :c"), {"c": cid})).scalar_one()
    assert n == 0  # ZERO commits of invalid immutable authority


async def test_readiness_rejects_raw_noncanonical_rotation(engine, factory):
    pid = await _seed_project(factory)
    rid = await _seed_production(factory, pid, "raw180b")
    cid = await _comp(factory, pid)
    occ = await _mint(factory, cid, _spec(rid), 0)
    async with factory() as s:
        async with s.bind.connect() as conn:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await conn.execute(
                text("UPDATE composition_working_occurrences SET pitch_udeg ="
                     " 180000000 WHERE occurrence_id = :o"),
                {"o": occ})
            await conn.exec_driver_sql("COMMIT")
    with pytest.raises(SoloRingError) as ei:
        await resolve_publication_readiness(factory(), cid)
    assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"


def test_lineage_evidence_validator_is_the_one_shared_contract():
    """F5 residual: both verifiers consume composition.evidence — the
    identical checklist cannot diverge again."""
    import inspect

    from soloring.composition import evidence, impacts
    import importlib as _il

    rb_mod = _il.import_module("soloring.recovery.backup")
    imp_src = inspect.getsource(impacts.verify_identity_history)
    rb_src = inspect.getsource(rb_mod._verify_m12_lineage)
    assert "validate_operation_evidence" in imp_src
    assert "validate_operation_evidence" in rb_src
    # the shared contract enforces full source AND target cardinality
    sig = inspect.signature(evidence.validate_operation_evidence)
    assert "normalized_sources" in sig.parameters
    assert "row_impact_fingerprint" in sig.parameters


# --- F5 final: malformed evidence must fail the EXACT grammar gate --------


def _valid_evidence() -> dict:
    from soloring.composition.canonical import (
        WorkingSpec,
        build_request_value,
        request_fingerprint as rfp,
    )
    from soloring.spatial.math import Transform

    spec = WorkingSpec(
        display_name="Chair 8", source_kind="production_revision",
        revision_id="33333333-3333-3333-3333-333333333333", visible=True,
        transform=Transform((1000, 0, 0), (0, 0, 0)))
    req = build_request_value(
        composition_id="22222222-2222-2222-2222-222222222222",
        kind="replace_as_new",
        source_occurrence_ids=["00000000-0000-0000-0000-000000000001"],
        target_specs=[spec])
    return {
        "schema_version": 1,
        "composition_id": "22222222-2222-2222-2222-222222222222",
        "kind": "replace_as_new",
        "working_version_before": 8,
        "working_version_after": 9,
        "request_fingerprint": rfp(req),
        "impact_fingerprint": "b" * 64,
        "sources": [{"occurrence_id": "00000000-0000-0000-0000-000000000001",
                     "terminates_identity": True}],
        "targets": [{
            "occurrence_id": "00000000-0000-0000-0000-000000000002",
            "working_spec": spec.canonical_value()}],
    }


_ROW = dict(
    row_composition_id="22222222-2222-2222-2222-222222222222",
    row_kind="replace_as_new",
    row_before=8,
    row_after=9,
)
_NORM_SOURCES = [("00000000-0000-0000-0000-000000000001", 1)]
_NORM_TARGETS = ["00000000-0000-0000-0000-000000000002"]


def _validate(doc):
    from soloring.composition.evidence import validate_operation_evidence

    validate_operation_evidence(
        doc,
        row_request_fingerprint=doc["request_fingerprint"],
        row_impact_fingerprint=doc["impact_fingerprint"],
        normalized_sources=_NORM_SOURCES,
        normalized_targets=_NORM_TARGETS,
        **_ROW)


def test_evidence_rejects_missing_and_extra_source_keys():
    import copy

    doc = _valid_evidence()
    assert_no_error = doc
    _validate(assert_no_error)  # baseline: the pristine document passes

    missing = copy.deepcopy(doc)
    del missing["sources"][0]["terminates_identity"]
    with pytest.raises(ValueError, match="source entry keys"):
        _validate(missing)

    extra = copy.deepcopy(doc)
    extra["sources"][0]["note"] = "x"
    with pytest.raises(ValueError, match="source entry keys"):
        _validate(extra)


def test_evidence_rejects_non_boolean_terminates_identity():
    import copy

    doc = _valid_evidence()
    doc["sources"][0]["terminates_identity"] = "yes"  # truthy string
    with pytest.raises(ValueError, match="JSON boolean"):
        _validate(doc)
    doc2 = _valid_evidence()
    doc2["sources"][0]["terminates_identity"] = 1  # truthy int
    with pytest.raises(ValueError, match="JSON boolean"):
        _validate(doc2)


def test_evidence_rejects_malformed_target_object():
    import copy

    doc = copy.deepcopy(_valid_evidence())
    doc["targets"][0]["extra"] = "field"
    with pytest.raises(ValueError, match="target entry keys"):
        _validate(doc)

    doc2 = copy.deepcopy(_valid_evidence())
    doc2["targets"][0] = {"occurrence_id": "x"}  # missing working_spec
    with pytest.raises(ValueError, match="target entry keys"):
        _validate(doc2)

    doc3 = copy.deepcopy(_valid_evidence())
    doc3["targets"][0]["occurrence_id"] = 42  # non-string id
    with pytest.raises(ValueError, match="occurrence_id must be a string"):
        _validate(doc3)


def test_evidence_rejects_non_string_revision_id():
    import copy

    doc = copy.deepcopy(_valid_evidence())
    doc["targets"][0]["working_spec"]["source"]["revision_id"] = 12345
    with pytest.raises(ValueError, match="revision_id must be"):
        _validate(doc)
    doc2 = copy.deepcopy(_valid_evidence())
    doc2["targets"][0]["working_spec"]["source"]["revision_id"] = ""
    with pytest.raises(ValueError, match="revision_id must be"):
        _validate(doc2)


def test_evidence_rejects_non_hex_impact_fingerprint():
    import copy

    doc = copy.deepcopy(_valid_evidence())
    doc["impact_fingerprint"] = "Z" * 64  # equal-to-row is supplied, but hex
    with pytest.raises(ValueError, match="impact_fingerprint not 64"):
        _validate(doc)
    doc2 = copy.deepcopy(_valid_evidence())
    doc2["impact_fingerprint"] = "abc"  # wrong length
    with pytest.raises(ValueError, match="impact_fingerprint not 64"):
        _validate(doc2)
    doc3 = copy.deepcopy(_valid_evidence())
    doc3["request_fingerprint"] = "G" * 64
    with pytest.raises(ValueError, match="request_fingerprint not 64"):
        _validate(doc3)


def test_evidence_rejects_unknown_kind_before_indexing():
    import copy

    doc = copy.deepcopy(_valid_evidence())
    doc["kind"] = "explode"  # not in the frozen domain
    with pytest.raises(ValueError, match="frozen domain"):
        _validate(doc)


def test_recovery_local_spec_validator_is_gone():
    """The dormant second interpretation was removed."""
    import importlib

    rb = importlib.import_module("soloring.recovery.backup")
    import inspect

    src = inspect.getsource(rb._verify_m12_lineage)
    assert "_spec_from_value" not in src
