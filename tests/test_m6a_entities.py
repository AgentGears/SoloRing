"""M6A — Story World tests (M6 plan §16–§30, §73–§74 subset).

Gate proof (§30): identity stable, revisions immutable, approval explicit
and unchanged by later revision creation, CAS race-safe. Canonicalization
fixtures (§73) pin exact bytes for the revision envelope. Race matrix (§74)
covers convergence and approval CAS under concurrency.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from sqlalchemy import text

from soloring.api.schemas.projects import ProjectCreate
from soloring.continuity.canonical import (
    canonical_json_bytes,
    revision_spec_hash,
    validate_spec_payload,
)
from soloring.domain import projects as project_svc
from soloring.domain.ids import new_uuid
from soloring.errors import SoloRingError

# --- §73 canonical byte fixtures ------------------------------------------------


def test_canonical_character_revision_v1_exact_bytes():
    spec = validate_spec_payload("character", {
        "schema_version": 1,
        "description": "A rain-soaked courier with a fresh cut on her forehead.",
        "notes": None,
    })
    envelope, digest = revision_spec_hash("character", spec)
    expected = (
        '{"entity_kind":"character","schema_version":1,"spec":'
        '{"description":"A rain-soaked courier with a fresh cut on her '
        'forehead.","notes":null,"schema_version":1}}'
    ).encode("utf-8")
    assert envelope == expected
    assert len(digest) == 64


def test_canonical_location_revision_v1_exact_bytes():
    spec = validate_spec_payload("location", {"description": "Hotel lobby"})
    envelope, _ = revision_spec_hash("location", spec)
    expected = (
        '{"entity_kind":"location","schema_version":1,"spec":'
        '{"description":"Hotel lobby","notes":null,"schema_version":1}}'
    ).encode("utf-8")
    assert envelope == expected


def test_canonical_unicode_and_escaped_characters():
    spec = validate_spec_payload("character", {
        "description": "Éva — «wet hair»\nline two\ttabbed \"quoted\"",
        "notes": "柱",
    })
    envelope, _ = revision_spec_hash("character", spec)
    # ensure_ascii=False: characters stay literal UTF-8, control chars escaped.
    decoded = envelope.decode("utf-8")
    assert "Éva — «wet hair»" in decoded
    assert "柱" in decoded
    assert "\\n" in decoded and "\\t" in decoded and '\\"' in decoded


def test_canonical_null_and_reordering_converge():
    a = validate_spec_payload("prop", {
        "notes": None, "description": "Hero revolver", "schema_version": 1,
    })
    b = validate_spec_payload("prop", {
        "schema_version": 1, "description": "Hero revolver", "notes": None,
    })
    assert canonical_json_bytes(a) == canonical_json_bytes(b)
    assert revision_spec_hash("prop", a)[1] == revision_spec_hash("prop", b)[1]


def test_kind_changes_hash_same_spec_shape():
    spec_c = validate_spec_payload("character", {"description": "X"})
    spec_l = validate_spec_payload("location", {"description": "X"})
    assert revision_spec_hash("character", spec_c)[1] != revision_spec_hash(
        "location", spec_l
    )


def test_spec_payload_rejects_unknown_and_bad_shape():
    with pytest.raises(ValueError):
        validate_spec_payload("character", {"description": "x", "lora_id": "no"})
    with pytest.raises(ValueError):
        validate_spec_payload("character", {"schema_version": 2})
    with pytest.raises(ValueError):
        validate_spec_payload("vehicle", {"description": 7})


# --- Service-level entity/revision/approval lifecycle --------------------------


async def _seed_project(factory) -> str:
    async with factory() as s:
        return (await project_svc.create_project(
            s, ProjectCreate(name="P")
        )).id


async def _create_entity(client, project_id: str, kind="character",
                         name="Eva", description=None) -> dict:
    r = await client.post(f"/projects/{project_id}/entities", json={
        "kind": kind, "name": name, "description": description,
    })
    assert r.status_code == 201, r.text
    return r.json()


async def _create_revision(client, entity_id: str, spec: dict) -> dict:
    r = await client.post(f"/entities/{entity_id}/revisions", json={"spec": spec})
    assert r.status_code == 201, r.text
    return r.json()


async def _approve(client, entity_id: str, revision_id: str, expected):
    return await client.put(f"/entities/{entity_id}/approved-revision", json={
        "revision_id": revision_id,
        "expected_approved_revision_id": expected,
    })


async def test_m6a_gate_proof(client, factory):
    """§30: approve rev2; create rev3; approval stays rev2; CAS to rev3."""
    pid = await _seed_project(factory)
    eva = await _create_entity(client, pid)

    r1 = await _create_revision(client, eva["id"], {"description": "v1"})
    r2 = await _create_revision(client, eva["id"], {"description": "v2"})
    assert (r1["revision_number"], r2["revision_number"]) == (1, 2)

    # No auto-approval on creation.
    detail = (await client.get(f"/entities/{eva['id']}")).json()
    assert detail["approved_revision_id"] is None

    r = await _approve(client, eva["id"], r2["id"], None)
    assert r.status_code == 200, r.text

    r3 = await _create_revision(client, eva["id"], {"description": "v3"})
    detail = (await client.get(f"/entities/{eva['id']}")).json()
    assert detail["approved_revision_id"] == r2["id"]  # unchanged by rev3

    r = await _approve(client, eva["id"], r3["id"], r2["id"])
    assert r.status_code == 200, r.text
    detail = (await client.get(f"/entities/{eva['id']}")).json()
    assert detail["approved_revision_id"] == r3["id"]


async def test_revisions_immutable_and_no_update_paths(client, factory):
    pid = await _seed_project(factory)
    eva = await _create_entity(client, pid)
    r1 = await _create_revision(client, eva["id"], {"description": "v1"})
    await _approve(client, eva["id"], r1["id"], None)
    r2 = await _create_revision(client, eva["id"], {"description": "v2"})
    await _approve(client, eva["id"], r2["id"], r1["id"])

    d1 = (await client.get(f"/entity-revisions/{r1['id']}")).json()
    assert d1["spec_hash"] == r1["spec_hash"]  # bytes/hash unchanged

    # No revision PATCH/DELETE route exists (M6-F3).
    assert (await client.patch(
        f"/entity-revisions/{r1['id']}", json={"spec": {}}
    )).status_code == 405
    assert (await client.delete(f"/entity-revisions/{r1['id']}")).status_code == 405
    # No unapprove route (M6-F5).
    assert (await client.delete(
        f"/entities/{eva['id']}/approved-revision"
    )).status_code == 405


async def test_identical_revision_converges(client, factory):
    pid = await _seed_project(factory)
    eva = await _create_entity(client, pid)
    a = await _create_revision(client, eva["id"], {"description": "same"})
    b = await _create_revision(client, eva["id"], {"description": "same"})
    assert a["id"] == b["id"]
    assert a["revision_number"] == b["revision_number"]
    revs = (await client.get(f"/entities/{eva['id']}/revisions")).json()
    assert len(revs) == 1


async def test_rename_does_not_reinterpret_revisions(client, factory):
    pid = await _seed_project(factory)
    eva = await _create_entity(client, pid)
    r1 = await _create_revision(client, eva["id"], {"description": "design"})

    r = await client.patch(
        f"/entities/{eva['id']}", json={"name": "Eva Martínez"}
    )
    assert r.status_code == 200, r.text

    # Same design content after rename converges to the SAME revision.
    again = await _create_revision(client, eva["id"], {"description": "design"})
    assert again["id"] == r1["id"]


async def test_concurrent_identical_revisions_converge(factory):
    pid = await _seed_project(factory)
    from soloring.api.schemas.entities import EntityCreate
    from soloring.continuity import entities as entity_svc
    from soloring.continuity import revisions as revision_svc

    async with factory() as s:
        entity = await entity_svc.create_entity(
            s, pid, EntityCreate(kind="character", name="Eva")
        )

    async def one():
        async with factory() as s:
            return await revision_svc.create_revision(
                s, entity.id, {"description": "raced"}
            )

    results = await asyncio.gather(*(one() for _ in range(6)))
    ids = {r.revision["id"] for r in results}
    assert len(ids) == 1  # one converged row
    # Convergence contract: exactly ONE competitor created the row; the
    # other five converged onto it. gather() preserves input ordering of
    # RESULTS, not which transaction won the creation race — creator
    # status must not be assigned to results[0] (publication-gate fix).
    created_flags = [r.created for r in results]
    assert created_flags.count(True) == 1
    assert created_flags.count(False) == 5


async def test_concurrent_different_revisions_both_succeed(factory):
    pid = await _seed_project(factory)
    from soloring.api.schemas.entities import EntityCreate
    from soloring.continuity import entities as entity_svc
    from soloring.continuity import revisions as revision_svc

    async with factory() as s:
        entity = await entity_svc.create_entity(
            s, pid, EntityCreate(kind="character", name="Eva")
        )

    async def one(i: int):
        async with factory() as s:
            return await revision_svc.create_revision(
                s, entity.id, {"description": f"design {i}"}
            )

    results = await asyncio.gather(*(one(i) for i in range(4)))
    numbers = sorted(r.revision["revision_number"] for r in results)
    assert numbers == [1, 2, 3, 4]


async def test_approval_cas_conflict_matrix(client, factory):
    pid = await _seed_project(factory)
    eva = await _create_entity(client, pid)
    r1 = await _create_revision(client, eva["id"], {"description": "v1"})
    r2 = await _create_revision(client, eva["id"], {"description": "v2"})
    r3 = await _create_revision(client, eva["id"], {"description": "v3"})

    # First approval must expect null.
    r = await _approve(client, eva["id"], r2["id"], r1["id"])
    assert r.status_code == 409
    assert r.json()["error_code"] == "ENTITY_APPROVAL_CONFLICT"

    r = await _approve(client, eva["id"], r2["id"], None)
    assert r.status_code == 200

    # Stale expectation → 409.
    r = await _approve(client, eva["id"], r3["id"], None)
    assert r.status_code == 409
    r = await _approve(client, eva["id"], r3["id"], r1["id"])
    assert r.status_code == 409

    # Idempotent re-approve with the correct expectation.
    r = await _approve(client, eva["id"], r2["id"], r2["id"])
    assert r.status_code == 200

    # Cross-entity revision → 404 ENTITY_REVISION_NOT_FOUND.
    other = await _create_entity(client, pid, kind="location", name="Lobby")
    r = await _approve(client, other["id"], r2["id"], None)
    assert r.status_code == 404
    assert r.json()["error_code"] == "ENTITY_REVISION_NOT_FOUND"


async def test_concurrent_approval_cas_one_wins(factory):
    pid = await _seed_project(factory)
    from soloring.api.schemas.entities import EntityCreate
    from soloring.continuity import approvals as approval_svc
    from soloring.continuity import entities as entity_svc
    from soloring.continuity import revisions as revision_svc

    async with factory() as s:
        entity = await entity_svc.create_entity(
            s, pid, EntityCreate(kind="character", name="Eva")
        )
        r12 = await revision_svc.create_revision(s, entity.id, {"description": "12"})
        r13 = await revision_svc.create_revision(s, entity.id, {"description": "13"})
        r14 = await revision_svc.create_revision(s, entity.id, {"description": "14"})
        await approval_svc.approve_revision(s, entity.id, r12.revision["id"], None)

    async def approve(target: str):
        async with factory() as s:
            try:
                await approval_svc.approve_revision(
                    s, entity.id, target, r12.revision["id"]
                )
                return "ok"
            except Exception as exc:
                return getattr(exc, "code", type(exc).__name__)

    outcomes = await asyncio.gather(
        approve(r13.revision["id"]), approve(r14.revision["id"])
    )
    assert sorted(outcomes) == ["ENTITY_APPROVAL_CONFLICT", "ok"]


async def test_entity_crud_and_validation(client, factory):
    pid = await _seed_project(factory)

    for kind in ("character", "location", "prop", "costume", "vehicle"):
        e = await _create_entity(client, pid, kind=kind, name=f"E-{kind}")
        assert e["kind"] == kind

    r = await client.post(f"/projects/{pid}/entities", json={
        "kind": "song", "name": "X",
    })
    assert r.status_code == 422
    assert r.json()["error_code"] == "ENTITY_KIND_INVALID"

    r = await client.post(f"/projects/{pid}/entities", json={
        "kind": "character", "name": "   ",
    })
    assert r.status_code == 422
    r = await client.post(f"/projects/{pid}/entities", json={
        "kind": "character", "name": "x" * 501,
    })
    assert r.status_code == 422

    eva = await _create_entity(client, pid, description="   ")
    assert eva["description"] is None  # blank → NULL

    # kind is immutable: PATCH with kind is forbidden by the schema.
    r = await client.patch(f"/entities/{eva['id']}", json={"kind": "location"})
    assert r.status_code == 422

    # list + kind filter
    r = await client.get(f"/projects/{pid}/entities?kind=character")
    assert r.status_code == 200
    assert all(e["kind"] == "character" for e in r.json())
    r = await client.get(f"/projects/{pid}/entities?kind=song")
    assert r.status_code == 422

    assert (await client.get(
        f"/entities/{str(new_uuid())}"
    )).status_code == 404


async def test_entity_deletion_rules(client, factory, engine):
    pid = await _seed_project(factory)
    eva = await _create_entity(client, pid)
    rev = await _create_revision(client, eva["id"], {"description": "v1"})
    await _approve(client, eva["id"], rev["id"], None)

    # Deleted entities cannot receive revisions or approvals.
    r = await client.delete(f"/entities/{eva['id']}")
    assert r.status_code == 204
    r = await client.post(f"/entities/{eva['id']}/revisions",
                          json={"spec": {"description": "v2"}})
    assert r.status_code == 404
    r = await _approve(client, eva["id"], rev["id"], rev["id"])
    assert r.status_code == 404
    # Idempotent delete.
    assert (await client.delete(f"/entities/{eva['id']}")).status_code == 204
    # Hidden from lists; historical revision detail still readable.
    assert (await client.get(f"/projects/{pid}/entities")).json() == []
    d = (await client.get(f"/entity-revisions/{rev['id']}")).json()
    assert d["entity_id"] == eva["id"]

    # ENTITY_IN_USE: active working dependency blocks deletion.
    from soloring.api.schemas.shots import ShotCreate
    from soloring.domain import shots as shot_svc

    hero = await _create_entity(client, pid, kind="prop", name="Revolver")
    hrev = await _create_revision(client, hero["id"], {"description": "gun"})
    await _approve(client, hero["id"], hrev["id"], None)
    async with factory() as s:
        shot = await shot_svc.create_shot(s, pid, ShotCreate(subject="s"))
    async with engine.connect() as conn:
        await conn.execute(
            text(
                "INSERT INTO shot_entity_dependencies "
                "(shot_id, entity_id, role, position) "
                "VALUES (:sid, :eid, 'hero_prop', 0)"
            ),
            {"sid": shot.id, "eid": hero["id"]},
        )
        await conn.commit()
    r = await client.delete(f"/entities/{hero['id']}")
    assert r.status_code == 409
    assert r.json()["error_code"] == "ENTITY_IN_USE"

    # A soft-deleted Shot's dependency does NOT block deletion.
    async with engine.connect() as conn:
        await conn.execute(
            text("UPDATE shots SET deleted_at = "
                 "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :sid"),
            {"sid": shot.id},
        )
        await conn.commit()
    assert (await client.delete(f"/entities/{hero['id']}")).status_code == 204


async def test_project_deletion_cascades_entities_not_revisions(
    client, factory
):
    pid = await _seed_project(factory)
    eva = await _create_entity(client, pid)
    rev = await _create_revision(client, eva["id"], {"description": "v1"})
    await _approve(client, eva["id"], rev["id"], None)

    assert (await client.delete(f"/projects/{pid}")).status_code == 204
    r = await client.get(f"/entities/{eva['id']}")
    assert r.status_code == 404  # soft-deleted via cascade
    # Historical provenance preserved.
    d = (await client.get(f"/entity-revisions/{rev['id']}")).json()
    assert d["revision_number"] == 1


async def test_revision_detail_returns_typed_payload(client, factory):
    pid = await _seed_project(factory)
    lobby = await _create_entity(client, pid, kind="location", name="Lobby")
    rev = await _create_revision(client, lobby["id"], {
        "description": "Marble floor", "notes": "night",
    })
    d = (await client.get(f"/entity-revisions/{rev['id']}")).json()
    assert d["entity_kind"] == "location"
    assert d["entity_name"] == "Lobby"
    spec = json.loads(d["spec_json"])
    assert spec["description"] == "Marble floor"
    assert spec["notes"] == "night"
    assert (await client.get(
        f"/entity-revisions/{str(new_uuid())}"
    )).status_code == 404



# --- M6A re-gate: lifecycle race fencing ----------------------------------------
# Blockers 1 & 2: create/patch run as BEGIN IMMEDIATE units whose active
# checks are atomic with the write. The lock-parking proofs fire the
# competing deletion AFTER the in-unit verification has passed and watch it
# park on the held write lock — the exact interleaving that was exploitable
# before fencing.


async def _parked_project_delete(engine, project_id: str) -> None:
    """Competing Project soft-delete + entity cascade on its own connection.

    Parks on the write lock until the fenced unit under test commits.
    """
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(
            text(
                "UPDATE projects SET deleted_at = "
                "strftime('%Y-%m-%dT%H:%M:%fZ','now'), updated_at = "
                "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :pid"
            ),
            {"pid": project_id},
        )
        await conn.execute(
            text(
                "UPDATE creative_entities SET deleted_at = "
                "strftime('%Y-%m-%dT%H:%M:%fZ','now'), updated_at = "
                "strftime('%Y-%m-%dT%H:%M:%fZ','now') "
                "WHERE project_id = :pid AND deleted_at IS NULL"
            ),
            {"pid": project_id},
        )
        await conn.exec_driver_sql("COMMIT")


async def _parked_entity_delete(engine, entity_id: str) -> None:
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(
            text(
                "UPDATE creative_entities SET deleted_at = "
                "strftime('%Y-%m-%dT%H:%M:%fZ','now'), updated_at = "
                "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :eid"
            ),
            {"eid": entity_id},
        )
        await conn.exec_driver_sql("COMMIT")


async def test_create_entity_delete_first_serialization(factory, engine):
    """DELETE wins before the Entity write -> 404, zero rows."""
    pid = await _seed_project(factory)
    from soloring.api.schemas.entities import EntityCreate
    from soloring.continuity import entities as entity_svc
    from soloring.domain import projects as psvc

    async with factory() as s:
        await psvc.delete_project(s, pid)
    async with factory() as s:
        with pytest.raises(SoloRingError) as ei:
            await entity_svc.create_entity(
                s, pid, EntityCreate(kind="character", name="Eva")
            )
    assert ei.value.code == "PROJECT_NOT_FOUND"
    async with engine.connect() as conn:
        n = (await conn.execute(
            text("SELECT COUNT(*) FROM creative_entities")
        )).scalar()
    assert n == 0


async def test_create_entity_create_first_serialization(client, factory, engine):
    """CREATE commits first -> the later cascade tombstones the new Entity."""
    pid = await _seed_project(factory)
    eva = await _create_entity(client, pid)
    assert (await client.delete(f"/projects/{pid}")).status_code == 204
    async with engine.connect() as conn:
        row = (await conn.execute(
            text("SELECT deleted_at FROM creative_entities WHERE id = :e"),
            {"e": eva["id"]},
        )).fetchone()
    assert row.deleted_at is not None  # included in the cascade


async def test_create_entity_delete_race_lock_parking(
    factory, engine, monkeypatch
):
    """Forced interleaving: the deletion is fired AFTER the in-unit
    active-Project verification passes and parks on the held write lock.
    The insert therefore lands under a still-active Project; the deletion
    completes afterwards and cascades. Never an active Entity under a
    deleted Project."""
    from soloring.api.schemas.entities import EntityCreate
    from soloring.continuity import entities as entity_svc

    pid = await _seed_project(factory)
    original = entity_svc._verify_active_project
    state: dict = {}

    async def wrap(conn, project_id):
        await original(conn, project_id)
        if "task" not in state:
            state["task"] = asyncio.create_task(
                _parked_project_delete(engine, project_id)
            )
            await asyncio.sleep(0.3)  # deletion is now parked on our lock

    monkeypatch.setattr(entity_svc, "_verify_active_project", wrap)
    async with factory() as s:
        entity = await entity_svc.create_entity(
            s, pid, EntityCreate(kind="character", name="Eva")
        )
    await state["task"]

    async with engine.connect() as conn:
        project_deleted = (await conn.execute(
            text("SELECT deleted_at FROM projects WHERE id = :p"),
            {"p": pid},
        )).fetchone()[0]
        entity_deleted = (await conn.execute(
            text("SELECT deleted_at FROM creative_entities WHERE id = :e"),
            {"e": entity.id},
        )).fetchone()[0]
    assert project_deleted is not None
    assert entity_deleted is not None  # coherent: cascade caught the entity


async def test_patch_entity_delete_first_serialization(client, factory, engine):
    """DELETE wins first -> PATCH 404, tombstone identity untouched."""
    pid = await _seed_project(factory)
    eva = await _create_entity(client, pid, name="Original")
    assert (await client.delete(f"/entities/{eva['id']}")).status_code == 204
    async with engine.connect() as conn:
        before = (await conn.execute(
            text("SELECT name, updated_at, deleted_at FROM creative_entities "
                 "WHERE id = :e"),
            {"e": eva["id"]},
        )).fetchone()

    r = await client.patch(
        f"/entities/{eva['id']}", json={"name": "Post-mortem"}
    )
    assert r.status_code == 404
    assert r.json()["error_code"] == "ENTITY_NOT_FOUND"

    async with engine.connect() as conn:
        after = (await conn.execute(
            text("SELECT name, updated_at, deleted_at FROM creative_entities "
                 "WHERE id = :e"),
            {"e": eva["id"]},
        )).fetchone()
    assert tuple(after) == tuple(before)  # no post-delete mutation


async def test_patch_entity_patch_first_serialization(client, factory, engine):
    """PATCH wins first -> persists; DELETE tombstones the renamed Entity."""
    pid = await _seed_project(factory)
    eva = await _create_entity(client, pid, name="Original")
    r = await client.patch(f"/entities/{eva['id']}", json={"name": "Renamed"})
    assert r.status_code == 200
    assert (await client.delete(f"/entities/{eva['id']}")).status_code == 204
    async with engine.connect() as conn:
        row = (await conn.execute(
            text("SELECT name, deleted_at FROM creative_entities "
                 "WHERE id = :e"),
            {"e": eva["id"]},
        )).fetchone()
    assert row.name == "Renamed" and row.deleted_at is not None


async def test_patch_entity_delete_race_lock_parking(
    factory, engine, monkeypatch
):
    """Forced interleaving: the competing DELETE fires after the in-unit
    active re-read passes and parks on the held write lock; the PATCH
    updates the still-active row and commits; the DELETE completes after.
    Never a mutation of a committed tombstone."""
    from soloring.api.schemas.entities import EntityCreate, EntityPatch
    from soloring.continuity import entities as entity_svc

    pid = await _seed_project(factory)
    async with factory() as s:
        entity = await entity_svc.create_entity(
            s, pid, EntityCreate(kind="character", name="Original")
        )

    original = entity_svc._verify_active_entity
    state: dict = {}

    async def wrap(conn, entity_id):
        await original(conn, entity_id)
        if "task" not in state:
            state["task"] = asyncio.create_task(
                _parked_entity_delete(engine, entity_id)
            )
            await asyncio.sleep(0.3)  # delete is now parked on our lock

    monkeypatch.setattr(entity_svc, "_verify_active_entity", wrap)
    async with factory() as s:
        patched = await entity_svc.patch_entity(
            s, entity.id, EntityPatch(name="Renamed")
        )
    await state["task"]

    assert patched.name == "Renamed"
    async with engine.connect() as conn:
        row = (await conn.execute(
            text("SELECT name, deleted_at, "
                 "(updated_at <= deleted_at) AS coherent FROM "
                 "creative_entities WHERE id = :e"),
            {"e": entity.id},
        )).fetchone()
    assert row.name == "Renamed"
    assert row.deleted_at is not None
    # The mutation strictly preceded the tombstone (patch-first ordering).
    assert row.coherent == 1


async def test_approval_expected_empty_string_rejected(client, factory):
    """A non-null expectation must be a UUID; '' is not first-approval null."""
    pid = await _seed_project(factory)
    eva = await _create_entity(client, pid)
    rev = await _create_revision(client, eva["id"], {"description": "v1"})
    r = await _approve(client, eva["id"], rev["id"], "")
    assert r.status_code == 422
    # Nothing was approved.
    assert (await client.get(f"/entities/{eva['id']}")).json()[
        "approved_revision_id"
    ] is None
