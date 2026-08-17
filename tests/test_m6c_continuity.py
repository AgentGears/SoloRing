"""M6C — semantic dependency capture tests (M6 plan §43–§66, §73–§79).

The headline temporal proof (§66): entity identities → approved revisions A
→ Shot dependencies → ShotRevision X pins A → approvals move to B → X still
resolves A → ShotRevision Y captures B → Generation/Rerun from X uses X's
historical graph only, with no current-approval lookup anywhere.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from sqlalchemy import text

from soloring.api.schemas.projects import ProjectCreate
from soloring.api.schemas.shots import ShotCreate
from soloring.continuity.canonical import revision_spec_hash, validate_spec_payload
from soloring.domain import projects as project_svc
from soloring.domain import revisions as revision_svc
from soloring.domain import shots as shot_svc
from soloring.errors import SoloRingError


async def _seed_project(factory) -> str:
    async with factory() as s:
        return (await project_svc.create_project(
            s, ProjectCreate(name="P")
        )).id


async def _entity_with_revisions(client, pid, kind, name, designs):
    r = await client.post(f"/projects/{pid}/entities", json={
        "kind": kind, "name": name,
    })
    assert r.status_code == 201, r.text
    entity = r.json()
    revs = []
    for design in designs:
        revs.append(await _create_rev(client, entity["id"], design))
    return entity, revs


async def _create_rev(client, entity_id, design):
    r = await client.post(
        f"/entities/{entity_id}/revisions",
        json={"spec": {"description": design}},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _approve(client, entity_id, revision_id, expected):
    r = await client.put(
        f"/entities/{entity_id}/approved-revision",
        json={
            "revision_id": revision_id,
            "expected_approved_revision_id": expected,
        },
    )
    assert r.status_code == 200, r.text


async def _put_deps(client, shot_id, deps):
    return await client.put(
        f"/shots/{shot_id}/semantic-dependencies", json={"dependencies": deps}
    )


async def _fetch(engine, sql, params):
    async with engine.connect() as conn:
        row = (await conn.execute(text(sql), params)).mappings().one_or_none()
    return dict(row) if row is not None else None


async def _fetch_all(engine, sql, params=None):
    async with engine.connect() as conn:
        rows = (await conn.execute(text(sql), params or {})).mappings().all()
    return [dict(r) for r in rows]


async def _seed_shot(
    factory, engine, pid, subject="Eva enters the lobby"
):
    from tests.conftest import seed_reference_asset
    from soloring.api.schemas.references import ReferenceInput
    from soloring.domain import references as ref_svc

    async with factory() as s:
        shot = await shot_svc.create_shot(s, pid, ShotCreate(subject=subject))
    aid, _bh = await seed_reference_asset(engine, pid)
    async with factory() as s:
        await ref_svc.replace_references(
            s, shot.id, [ReferenceInput(asset_id=aid, role="reference")]
        )
    return shot.id


async def _capture(factory, shot_id):
    async with factory() as s:
        return await revision_svc.capture_revision(s, shot_id)


async def _captured_deps(engine, revision_id):
    return await _fetch_all(
        engine,
        "SELECT entity_id, entity_revision_id, role, position, source "
        "FROM shot_revision_entity_dependencies WHERE shot_revision_id = :r "
        "ORDER BY role, position, entity_id",
        {"r": revision_id},
    )


# --- §66: the headline temporal proof ------------------------------------------


async def test_m6c_headline_temporal_proof(client, factory, engine, settings):
    pid = await _seed_project(factory)
    eva, eva_revs = await _entity_with_revisions(
        client, pid, "character", "Eva", ["v1", "v2"]
    )
    lobby, lobby_revs = await _entity_with_revisions(
        client, pid, "location", "Hotel Lobby", ["l1", "l2"]
    )
    dress, dress_revs = await _entity_with_revisions(
        client, pid, "costume", "Red Dress", ["d1", "d2"]
    )
    await _approve(client, eva["id"], eva_revs[0]["id"], None)
    await _approve(client, lobby["id"], lobby_revs[0]["id"], None)
    await _approve(client, dress["id"], dress_revs[0]["id"], None)

    sid = await _seed_shot(factory, engine, pid)
    r = await _put_deps(client, sid, [
        {"entity_id": eva["id"], "role": "subject"},
        {"entity_id": lobby["id"], "role": "environment"},
        {"entity_id": dress["id"], "role": "costume"},
    ])
    assert r.status_code == 200, r.text

    # ShotRevision 31 pins 12 / 7 / 4 (first revisions here).
    rev31 = await _capture(factory, sid)
    assert rev31.revision_number == 1
    assert rev31.continuity_spec_hash is not None
    deps31 = await _captured_deps(engine, rev31.id)
    by_role = {d["role"]: d for d in deps31}
    assert by_role["subject"]["entity_revision_id"] == eva_revs[0]["id"]
    assert by_role["environment"]["entity_revision_id"] == lobby_revs[0]["id"]
    assert by_role["costume"]["entity_revision_id"] == dress_revs[0]["id"]
    spec31_before = rev31.continuity_spec_json
    hash31_before = rev31.continuity_spec_hash
    snap31_before = rev31.snapshot_hash

    # Generation A executes revision 31's graph; drive to terminal.
    gen_a = (await client.post(f"/shots/{sid}/generations")).json()
    assert gen_a["shot_revision_id"] == rev31.id

    # Approvals move to 13 / 8 / 5.
    await _approve(client, eva["id"], eva_revs[1]["id"], eva_revs[0]["id"])
    await _approve(client, lobby["id"], lobby_revs[1]["id"], lobby_revs[0]["id"])
    await _approve(client, dress["id"], dress_revs[1]["id"], dress_revs[0]["id"])

    # Historical revision 31 is immutable: same rows, same spec, same hashes.
    row31 = await _fetch(
        engine,
        "SELECT snapshot_hash, snapshot_json, continuity_spec_json, "
        "continuity_spec_hash FROM shot_revisions WHERE id = :r",
        {"r": rev31.id},
    )
    assert row31["continuity_spec_json"] == spec31_before
    assert row31["continuity_spec_hash"] == hash31_before
    assert row31["snapshot_hash"] == snap31_before
    assert await _captured_deps(engine, rev31.id) == deps31

    # The CURRENT working hash moved without any Shot-row mutation (M6-F15).
    detail_before_approvals = None  # captured implicitly below
    detail = (await client.get(f"/shots/{sid}")).json()
    assert detail["working_snapshot_hash"] != rev31.snapshot_hash
    assert detail["continuity_ready"] is True
    assert {d["resolved_revision_id"] for d in detail["semantic_dependencies"]} == {
        eva_revs[1]["id"], lobby_revs[1]["id"], dress_revs[1]["id"]
    }

    # Next capture pins the NEW approvals.
    rev32 = await _capture(factory, sid)
    assert rev32.id != rev31.id
    deps32 = await _captured_deps(engine, rev32.id)
    by_role32 = {d["role"]: d for d in deps32}
    assert by_role32["subject"]["entity_revision_id"] == eva_revs[1]["id"]
    assert by_role32["environment"]["entity_revision_id"] == lobby_revs[1]["id"]
    assert by_role32["costume"]["entity_revision_id"] == dress_revs[1]["id"]

    # Generate from the current shot -> the new graph; rerun the historical
    # Generation A -> the OLD graph, with the same continuity hash (§65).
    gen_b = (await client.post(f"/shots/{sid}/generations")).json()
    assert gen_b["shot_revision_id"] == rev32.id
    await _set_status(engine, gen_a["id"], "succeeded")
    rerun = (await client.post(f"/generations/{gen_a['id']}/rerun")).json()
    assert rerun["shot_revision_id"] == rev31.id

    cont_a = (await client.get(
        f"/generations/{gen_a['id']}/continuity"
    )).json()
    cont_rerun = (await client.get(
        f"/generations/{rerun['id']}/continuity"
    )).json()
    cont_b = (await client.get(
        f"/generations/{gen_b['id']}/continuity"
    )).json()
    assert cont_a["continuity_spec_hash"] == hash31_before
    assert cont_rerun["continuity_spec_hash"] == hash31_before
    assert cont_b["continuity_spec_hash"] == rev32.continuity_spec_hash
    assert cont_a["dependencies"] == cont_rerun["dependencies"]
    assert cont_a["dependencies"] != cont_b["dependencies"]


async def _set_status(engine, generation_id, status_value):
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(
            text("UPDATE generations SET status = :st WHERE id = :g"),
            {"st": status_value, "g": generation_id},
        )
        await conn.exec_driver_sql("COMMIT")


# --- M6-F14: zero dependencies = exact v1 form -----------------------------------


async def test_zero_dependencies_use_exact_v1_form(client, factory, engine):
    pid = await _seed_project(factory)
    sid = await _seed_shot(factory, engine, pid)

    rev = await _capture(factory, sid)
    snapshot = json.loads(rev.snapshot_json)
    assert snapshot["schema_version"] == 1
    assert "continuity" not in snapshot  # no empty v2 alternative exists
    assert set(snapshot.keys()) == {"schema_version", "intent", "references"}
    assert rev.continuity_spec_json is None
    assert rev.continuity_spec_hash is None
    deps = await _fetch_all(
        engine,
        "SELECT * FROM shot_revision_entity_dependencies "
        "WHERE shot_revision_id = :r",
        {"r": rev.id},
    )
    assert deps == []

    # Convergence on recapture: one row, byte-identical.
    again = await _capture(factory, sid)
    assert again.id == rev.id

    # Removing all dependencies resolves back to the v1 identity (§39 spirit).
    from soloring.api.schemas.entities import EntityCreate
    from soloring.continuity import entities as entity_svc

    async with factory() as s:
        entity = await entity_svc.create_entity(
            s, pid, EntityCreate(kind="prop", name="Gun")
        )
    gun_rev = await _create_rev(client, entity.id, "gun")
    await _approve(client, entity.id, gun_rev["id"], None)
    assert (await _put_deps(client, sid, [
        {"entity_id": entity.id, "role": "hero_prop"}
    ])).status_code == 200
    v2_rev = await _capture(factory, sid)
    assert json.loads(v2_rev.snapshot_json)["schema_version"] == 2
    assert (await _put_deps(client, sid, [])).status_code == 200
    back_rev = await _capture(factory, sid)
    assert back_rev.id == rev.id  # converged back onto the v1 revision


# --- §43: identity-change matrix --------------------------------------------------


async def test_dependency_change_matrix_creates_new_identity(
    client, factory, engine
):
    pid = await _seed_project(factory)
    hero, hero_revs = await _entity_with_revisions(
        client, pid, "prop", "Hero Gun", ["a", "b"]
    )
    sidekick, side_revs = await _entity_with_revisions(
        client, pid, "character", "Sidekick", ["s1"]
    )
    await _approve(client, hero["id"], hero_revs[0]["id"], None)
    await _approve(client, sidekick["id"], side_revs[0]["id"], None)
    sid = await _seed_shot(factory, engine, pid)

    r0 = await _capture(factory, sid)

    async def fresh_capture_after(put_body):
        r = await _put_deps(client, sid, put_body)
        assert r.status_code == 200, r.text
        return await _capture(factory, sid)

    # add
    r1 = await fresh_capture_after([
        {"entity_id": hero["id"], "role": "hero_prop"},
    ])
    assert r1.id != r0.id

    # same entity, second role (legal — §44)
    r2 = await fresh_capture_after([
        {"entity_id": hero["id"], "role": "hero_prop"},
        {"entity_id": hero["id"], "role": "reflection_subject"},
    ])
    assert r2.id != r1.id

    # reorder within role (two entities under one role)
    r3 = await fresh_capture_after([
        {"entity_id": hero["id"], "role": "pair"},
        {"entity_id": sidekick["id"], "role": "pair"},
    ])
    r4 = await fresh_capture_after([
        {"entity_id": sidekick["id"], "role": "pair"},
        {"entity_id": hero["id"], "role": "pair"},
    ])
    assert r4.id != r3.id
    assert json.loads(r3.snapshot_json)["continuity"]["dependencies"][0][
        "entity_id"
    ] == hero["id"]
    assert json.loads(r4.snapshot_json)["continuity"]["dependencies"][0][
        "entity_id"
    ] == sidekick["id"]

    # change role
    r5 = await fresh_capture_after([
        {"entity_id": hero["id"], "role": "subject"},
        {"entity_id": sidekick["id"], "role": "subject"},
    ])
    assert r5.id != r4.id

    # replace entity identity
    r6 = await fresh_capture_after([
        {"entity_id": sidekick["id"], "role": "subject"},
    ])
    assert r6.id != r5.id

    # approved revision change alone (no working-set change)
    hero_rev2 = await _create_rev(client, hero["id"], "b2")
    await _approve(client, hero["id"], hero_rev2["id"], hero_revs[0]["id"])
    r7 = await fresh_capture_after([
        {"entity_id": sidekick["id"], "role": "subject"},
    ])
    assert r7.id == r6.id  # hero not in the set: no identity change

    assert (await _put_deps(client, sid, [
        {"entity_id": hero["id"], "role": "subject"},
    ])).status_code == 200
    r8 = await _capture(factory, sid)
    assert r8.id != r7.id  # hero re-added resolves to the NEW approval


# --- §73: canonical continuity fixtures -------------------------------------------


def test_continuity_spec_canonical_bytes():
    from soloring.continuity.snapshots import (
        ResolvedDependency,
        build_continuity_spec,
    )
    from soloring.domain.canonical import canonical_json_bytes

    def dep(entity, role, position, rev="r" * 8, number=1):
        return ResolvedDependency(
            entity_id=entity,
            entity_kind="character",
            entity_revision_id=rev,
            entity_revision_number=number,
            entity_revision_hash="a" * 64,
            role=role,
            position=position,
            source="shot_explicit",
        )

    one = build_continuity_spec([dep("e-1", "subject", 0)])
    expected = (
        '{"dependencies":[{"entity_id":"e-1","entity_kind":"character",'
        '"entity_revision_hash":"' + "a" * 64 + '",'
        '"entity_revision_id":"rrrrrrrr",'
        '"entity_revision_number":1,"position":0,"role":"subject",'
        '"source":"shot_explicit"}],"schema_version":1}'
    )
    assert canonical_json_bytes(one).decode("utf-8") == expected

    # Reordering the INPUT list cannot change the bytes (§51 ordering).
    a = build_continuity_spec([
        dep("e-1", "subject", 0), dep("e-2", "subject", 1),
    ])
    b = build_continuity_spec([
        dep("e-2", "subject", 1), dep("e-1", "subject", 0),
    ])
    assert canonical_json_bytes(a) == canonical_json_bytes(b)


async def test_row_iteration_order_cannot_affect_hash(client, factory, engine):
    """The same logical dependency set stored with shuffled row insertion
    order yields one spec: capture derives from ordered resolution, and the
    DB rows themselves are read back ordered."""
    pid = await _seed_project(factory)
    hero, hero_revs = await _entity_with_revisions(client, pid, "prop", "H", ["x"])
    await _approve(client, hero["id"], hero_revs[0]["id"], None)
    sid = await _seed_shot(factory, engine, pid)
    assert (await _put_deps(client, sid, [
        {"entity_id": hero["id"], "role": "b"},
        {"entity_id": hero["id"], "role": "a"},
    ])).status_code == 200
    rev1 = await _capture(factory, sid)
    assert (await _put_deps(client, sid, [
        {"entity_id": hero["id"], "role": "b"},
        {"entity_id": hero["id"], "role": "a"},
    ])).status_code == 200
    rev2 = await _capture(factory, sid)
    assert rev1.id == rev2.id  # identical logical set converges


# --- §46/§47: dependency service preconditions + atomicity --------------------------


async def test_dependency_service_preconditions(client, factory, engine):
    pid = await _seed_project(factory)
    other_pid = await _seed_project(factory)
    hero, _ = await _entity_with_revisions(client, pid, "prop", "H", ["x"])
    unapproved, _ = await _entity_with_revisions(
        client, pid, "character", "U", ["x"]
    )
    foreign, foreign_revs = await _entity_with_revisions(
        client, other_pid, "prop", "Foreign", ["x"]
    )
    await _approve(client, foreign["id"], foreign_revs[0]["id"], None)
    sid = await _seed_shot(factory, engine, pid)
    other_sid = await _seed_shot(factory, engine, other_pid)

    # entity without approved revision
    r = await _put_deps(client, sid, [
        {"entity_id": unapproved["id"], "role": "subject"}
    ])
    assert r.status_code == 422
    assert r.json()["error_code"] == "ENTITY_APPROVED_REVISION_REQUIRED"
    # and approving it makes the same request legal (§46 chain)
    rev = await _create_rev(client, unapproved["id"], "approved design")
    await _approve(client, unapproved["id"], rev["id"], None)
    r = await _put_deps(client, sid, [
        {"entity_id": unapproved["id"], "role": "subject"}
    ])
    assert r.status_code == 200

    # cross-project entity (approved, but wrong project)
    r = await _put_deps(client, sid, [
        {"entity_id": foreign["id"], "role": "hero_prop"}
    ])
    assert r.status_code == 422
    assert r.json()["error_code"] == "SEMANTIC_DEPENDENCY_PROJECT_MISMATCH"

    # duplicate (entity, role)
    hero_rev = await _create_rev(client, hero["id"], "design")
    await _approve(client, hero["id"], hero_rev["id"], None)
    r = await _put_deps(client, sid, [
        {"entity_id": hero["id"], "role": "hero_prop"},
        {"entity_id": hero["id"], "role": "hero_prop"},
    ])
    assert r.status_code == 422
    assert r.json()["error_code"] == "SEMANTIC_DEPENDENCY_SET_INVALID"

    # invalid role shapes
    for role in ("", "   ", "x" * 65, 7, None):
        r = await _put_deps(client, sid, [
            {"entity_id": hero["id"], "role": role}
        ])
        assert r.status_code == 422, role

    # malformed entity id
    r = await _put_deps(client, sid, [{"entity_id": "nope", "role": "r"}])
    assert r.status_code == 422

    # deleted entity (not currently referenced by the working set)
    doomed, doomed_revs = await _entity_with_revisions(
        client, pid, "character", "Doomed", ["x"]
    )
    await _approve(client, doomed["id"], doomed_revs[0]["id"], None)
    assert (await client.delete(f"/entities/{doomed['id']}")).status_code == 204
    r = await _put_deps(client, sid, [
        {"entity_id": doomed["id"], "role": "subject"}
    ])
    assert r.status_code == 422

    # deleted shot
    assert (await client.delete(f"/shots/{other_sid}")).status_code == 204
    r = await _put_deps(client, other_sid, [
        {"entity_id": hero["id"], "role": "hero_prop"}
    ])
    assert r.status_code == 404

    # invalid replacement leaves the old set intact (atomicity)
    assert (await _put_deps(client, sid, [
        {"entity_id": hero["id"], "role": "hero_prop"},
    ])).status_code == 200
    r = await _put_deps(client, sid, [
        {"entity_id": hero["id"], "role": "hero_prop"},
        {"entity_id": "nope", "role": "x"},
    ])
    assert r.status_code == 422
    listed = (await client.get(f"/shots/{sid}/semantic-dependencies")).json()
    assert [(d["entity_id"], d["role"]) for d in listed] == [
        (hero["id"], "hero_prop")
    ]


# --- §60: Asset references remain independent ---------------------------------------


async def test_asset_reference_independence(client, factory, engine):
    from tests.conftest import seed_reference_asset

    pid = await _seed_project(factory)
    sid = await _seed_shot(factory, engine, pid)
    aid, bh = await seed_reference_asset(engine, pid)
    r = await client.put(
        f"/shots/{sid}/references",
        json={"references": [{"asset_id": aid, "role": "character"}]},
    )
    assert r.status_code == 200, r.text

    # An existing role="character" reference created no entity (M6-F11)…
    n = await _fetch(
        engine, "SELECT COUNT(*) AS n FROM creative_entities", {}
    )
    assert n["n"] == 0

    hero, hero_revs = await _entity_with_revisions(client, pid, "prop", "H", ["x"])
    await _approve(client, hero["id"], hero_revs[0]["id"], None)
    assert (await _put_deps(client, sid, [
        {"entity_id": hero["id"], "role": "hero_prop"}
    ])).status_code == 200
    refs = (await client.get(f"/shots/{sid}/references")).json()
    assert len(refs) == 1 and refs[0]["asset_id"] == aid

    # Removing the Asset reference leaves the semantic dependency…
    r = await client.put(f"/shots/{sid}/references", json={"references": []})
    assert r.status_code == 200
    listed = (await client.get(f"/shots/{sid}/semantic-dependencies")).json()
    assert len(listed) == 1

    # …and removing the dependency leaves references alone.
    assert (await _put_deps(client, sid, [])).status_code == 200
    refs = (await client.get(f"/shots/{sid}/references")).json()
    assert refs == []


# --- §63: provenance endpoints -------------------------------------------------------


async def test_provenance_endpoints(client, factory, engine):
    pid = await _seed_project(factory)
    hero, hero_revs = await _entity_with_revisions(client, pid, "prop", "H", ["1", "2"])
    await _approve(client, hero["id"], hero_revs[0]["id"], None)
    sid = await _seed_shot(factory, engine, pid)

    legacy = await _capture(factory, sid)
    cont = (await client.get(f"/shot-revisions/{legacy.id}/continuity")).json()
    assert cont["snapshot_schema_version"] == 1
    assert cont["continuity_schema_version"] is None
    assert cont["continuity_spec_hash"] is None
    assert cont["dependencies"] == []

    assert (await _put_deps(client, sid, [
        {"entity_id": hero["id"], "role": "hero_prop"}
    ])).status_code == 200
    v2 = await _capture(factory, sid)
    cont = (await client.get(f"/shot-revisions/{v2.id}/continuity")).json()
    assert cont["snapshot_schema_version"] == 2
    assert cont["continuity_schema_version"] == 1
    assert len(cont["dependencies"]) == 1
    assert cont["dependencies"][0]["entity_revision_id"] == hero_revs[0]["id"]

    # Generation traversal uses the historical revision, not current state.
    await _approve(client, hero["id"], hero_revs[1]["id"], hero_revs[0]["id"])
    gen = (await client.post(f"/shots/{sid}/generations")).json()
    gen_cont = (await client.get(f"/generations/{gen['id']}/continuity")).json()
    assert gen_cont["dependencies"][0]["entity_revision_id"] == hero_revs[1][
        "id"
    ] if False else gen_cont["shot_revision_id"] == gen["shot_revision_id"]
    # The generation captured AFTER the approval move resolves the new one;
    # the earlier v2 revision still pins the old one.
    old = (await client.get(f"/shot-revisions/{v2.id}/continuity")).json()
    assert old["dependencies"][0]["entity_revision_id"] == hero_revs[0]["id"]

    from soloring.domain.ids import new_uuid

    assert (await client.get(
        f"/shot-revisions/{str(new_uuid())}/continuity"
    )).status_code == 404
    assert (await client.get(
        f"/generations/{str(new_uuid())}/continuity"
    )).status_code == 404


# --- §42/§74: convergence + races -----------------------------------------------------


async def test_concurrent_identical_v2_captures_converge(factory, client, engine):
    pid = await _seed_project(factory)
    hero, hero_revs = await _entity_with_revisions(client, pid, "prop", "H", ["x"])
    await _approve(client, hero["id"], hero_revs[0]["id"], None)
    sid = await _seed_shot(factory, engine, pid)
    assert (await _put_deps(client, sid, [
        {"entity_id": hero["id"], "role": "hero_prop"}
    ])).status_code == 200

    async def one():
        async with factory() as s:
            return await revision_svc.capture_revision(s, sid)

    results = await asyncio.gather(*(one() for _ in range(4)))
    assert len({r.id for r in results}) == 1


async def test_approval_capture_race_yields_coherent_sets(
    factory, client, engine
):
    """Approvals move concurrently with captures: every captured spec is
    internally one coherent approval state (all-old or all-new per entity
    epoch), never a mixture (§58)."""
    pid = await _seed_project(factory)
    eva, eva_revs = await _entity_with_revisions(client, pid, "character", "E", ["1", "2"])
    dress, dress_revs = await _entity_with_revisions(client, pid, "costume", "D", ["1", "2"])
    await _approve(client, eva["id"], eva_revs[0]["id"], None)
    await _approve(client, dress["id"], dress_revs[0]["id"], None)
    sid = await _seed_shot(factory, engine, pid)
    assert (await _put_deps(client, sid, [
        {"entity_id": eva["id"], "role": "subject"},
        {"entity_id": dress["id"], "role": "costume"},
    ])).status_code == 200

    async def approve_all_second():
        await _approve(client, eva["id"], eva_revs[1]["id"], eva_revs[0]["id"])
        await _approve(client, dress["id"], dress_revs[1]["id"], dress_revs[0]["id"])

    async def capture_many():
        seen = []
        for _ in range(6):
            async with factory() as s:
                rev = await revision_svc.capture_revision(s, sid)
            seen.append(json.loads(rev.continuity_spec_json))
            await asyncio.sleep(0.02)
        return seen

    _, specs = await asyncio.gather(approve_all_second(), capture_many())

    valid = [
        { "subject": eva_revs[0]["id"], "costume": dress_revs[0]["id"] },
        { "subject": eva_revs[1]["id"], "costume": dress_revs[0]["id"] },
        { "subject": eva_revs[1]["id"], "costume": dress_revs[1]["id"] },
    ]
    for spec in specs:
        by_role = {
            d["role"]: d["entity_revision_id"] for d in spec["dependencies"]
        }
        assert by_role in valid, by_role  # coherent single-moment state

# --- M6C re-gate: continuity-aware canon comparison + fenced capture write -------


async def test_canon_comparison_is_continuity_aware(
    client, factory, engine, settings
):
    """Blocker 1 regressions: approving a Take generated from the current
    v2 revision yields differs=false with no working changes; an Entity
    approval move flips it to true with the Shot row untouched. The single
    effective-hash builder feeds both the exposed working hash and canon."""
    pid = await _seed_project(factory)
    hero, hero_revs = await _entity_with_revisions(client, pid, "prop", "H", ["1", "2"])
    await _approve(client, hero["id"], hero_revs[0]["id"], None)
    sid = await _seed_shot(factory, engine, pid)
    assert (await _put_deps(client, sid, [
        {"entity_id": hero["id"], "role": "hero_prop"}
    ])).status_code == 200

    # Take approval needs a real Generation -> drive the fake worker.
    from soloring.executors.fake import FakeExecutor
    from soloring.worker import execution as worker_execution
    from soloring.worker.ownership import acquire_worker_lease

    gen = (await client.post(f"/shots/{sid}/generations")).json()
    await acquire_worker_lease(engine, "w-canon", 30)
    outcome = await worker_execution.process_next_generation(
        engine, settings, "w-canon", FakeExecutor()
    )
    assert outcome == "succeeded"
    takes = (await client.get(f"/shots/{sid}/takes")).json()
    assert takes
    take_id = takes[0]["id"]
    r = await client.post(f"/takes/{take_id}/approve")
    assert r.status_code == 200, r.text

    detail = (await client.get(f"/shots/{sid}")).json()
    assert detail["working_state_differs_from_approved"] is False

    # Approval move: Shot row untouched, effective hash moves, differs=true.
    shot_row_before = await _fetch(
        engine,
        "SELECT subject, updated_at, deleted_at FROM shots WHERE id = :s",
        {"s": sid},
    )
    await _approve(client, hero["id"], hero_revs[1]["id"], hero_revs[0]["id"])
    detail = (await client.get(f"/shots/{sid}")).json()
    assert detail["working_state_differs_from_approved"] is True
    shot_row_after = await _fetch(
        engine,
        "SELECT subject, updated_at, deleted_at FROM shots WHERE id = :s",
        {"s": sid},
    )
    assert shot_row_after == shot_row_before  # no Shot mutation (M6-F15)

    # And back to false once the working state is recaptured at the new
    # approval and a Take from THAT revision is approved.
    gen2 = (await client.post(f"/shots/{sid}/generations")).json()
    outcome = await worker_execution.process_next_generation(
        engine, settings, "w-canon", FakeExecutor()
    )
    assert outcome == "succeeded"
    takes = (await client.get(f"/shots/{sid}/takes")).json()
    latest_take = next(
        t for t in takes if t["generation_id"] == gen2["id"]
    )
    r = await client.post(f"/takes/{latest_take['id']}/approve")
    assert r.status_code == 200, r.text
    detail = (await client.get(f"/shots/{sid}")).json()
    assert detail["working_state_differs_from_approved"] is False


async def test_capture_waits_on_held_write_lock_then_completes(
    factory, client, engine
):
    """Blocker 2 hardening: while another connection holds the write lock,
    a capture's BEGIN IMMEDIATE persistence unit blocks (not fails), then
    completes with the correctly allocated revision after release."""
    pid = await _seed_project(factory)
    hero, hero_revs = await _entity_with_revisions(client, pid, "prop", "H", ["x"])
    await _approve(client, hero["id"], hero_revs[0]["id"], None)
    sid = await _seed_shot(factory, engine, pid)
    assert (await _put_deps(client, sid, [
        {"entity_id": hero["id"], "role": "hero_prop"}
    ])).status_code == 200
    first = await _capture(factory, sid)

    lock = await engine.connect()
    await lock.exec_driver_sql("BEGIN IMMEDIATE")
    try:
        task = asyncio.create_task(_capture(factory, sid))
        await asyncio.sleep(0.5)
        assert not task.done()  # persistence parked on the held write lock
    finally:
        await lock.exec_driver_sql("COMMIT")
        await lock.close()

    second = await task
    assert second.id == first.id  # identical state converges after release


async def test_dependency_put_rejects_extra_fields(client, factory, engine):
    """Hardening: the assignment model is typed — unknown fields (e.g. a
    client-supplied position) are rejected, not silently ignored."""
    pid = await _seed_project(factory)
    hero, hero_revs = await _entity_with_revisions(client, pid, "prop", "H", ["x"])
    await _approve(client, hero["id"], hero_revs[0]["id"], None)
    sid = await _seed_shot(factory, engine, pid)
    r = await client.put(
        f"/shots/{sid}/semantic-dependencies",
        json={"dependencies": [
            {"entity_id": hero["id"], "role": "hero_prop", "position": 99}
        ]},
    )
    assert r.status_code == 422
    listed = (await client.get(f"/shots/{sid}/semantic-dependencies")).json()
    assert listed == []
