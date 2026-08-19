"""M7D — Controlled relations tests (plan §21 proof matrix).

M7D-1 (this file's first section, §21.1–§21.2): ContinuityPredicate and
ContinuityRelation CRUD under the frozen six-code vocabulary — key grammar
through the GENERIC validation contract (no predicate-specific validation
code exists), tombstone-inclusive key lifetime, INVALID_CONTINUITY_RELATION
for structural relation invalidity, active-slot duplicate semantics, and
the unresolved-id policy.

Later slices append: relation transitions + resolver (§21.3–§21.4),
capture/history (§21.5–§21.8), guards/cascade/concurrency/scale/rerun
(§21.9–§21.12).
"""

from __future__ import annotations

from soloring.api.schemas.projects import ProjectCreate
from soloring.continuity import entities as entity_svc
from soloring.domain import projects as project_svc


async def _seed_project(factory, name="P"):
    async with factory() as s:
        return (await project_svc.create_project(
            s, ProjectCreate(name=name))).id


async def _entity(client, pid, kind="character", name="Eva"):
    r = await client.post(
        f"/projects/{pid}/entities", json={"kind": kind, "name": name}
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _predicate(client, pid, key="carries", name="Carries",
                     description=None):
    payload = {"key": key, "name": name}
    if description is not None:
        payload["description"] = description
    r = await client.post(
        f"/projects/{pid}/continuity-predicates", json=payload
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _relation(client, pid, subject, predicate_id, obj):
    r = await client.post(
        f"/projects/{pid}/continuity-relations",
        json={
            "subject_entity_id": subject,
            "predicate_id": predicate_id,
            "object_entity_id": obj,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


# --- §21.1 ContinuityPredicate -------------------------------------------------


async def test_predicate_create_read_roundtrip(client, factory):
    pid = await _seed_project(factory)
    p = await _predicate(
        client, pid, key="carries", name="  Carries  ",
        description="  holds an object  ",
    )
    # name is stripped; description is normalized display metadata.
    assert p["name"] == "Carries"
    assert p["description"] == "holds an object"
    assert p["project_id"] == pid
    assert p["key"] == "carries"

    r = await client.get(f"/continuity-predicates/{p['id']}")
    assert r.status_code == 200
    assert r.json() == p


async def test_predicate_key_grammar_uses_generic_validation(client, factory):
    """The frozen vocabulary has NO predicate-specific validation code —
    malformed authoring fields use the generic VALIDATION_ERROR contract."""
    pid = await _seed_project(factory)
    bad_keys = [
        "Bad-Key", "1starts_digit", "has space", "", "x" * 65, "ünicode",
    ]
    for key in bad_keys:
        r = await client.post(
            f"/projects/{pid}/continuity-predicates",
            json={"key": key, "name": "N"},
        )
        assert r.status_code == 422, (key, r.text)
        assert r.json()["error_code"] == "VALIDATION_ERROR", key

    r = await client.post(
        f"/projects/{pid}/continuity-predicates",
        json={"key": "ok_key", "name": "   "},
    )
    assert r.status_code == 422
    assert r.json()["error_code"] == "VALIDATION_ERROR"


async def test_predicate_key_conflict_includes_tombstone(client, factory):
    """Tombstone-inclusive: a deleted key is never recycled (§4.1)."""
    pid = await _seed_project(factory)
    p = await _predicate(client, pid, key="carries")

    r = await client.post(
        f"/projects/{pid}/continuity-predicates",
        json={"key": "carries", "name": "Again"},
    )
    assert r.status_code == 409
    assert r.json()["error_code"] == "CONTINUITY_PREDICATE_KEY_CONFLICT"

    r = await client.delete(f"/continuity-predicates/{p['id']}")
    assert r.status_code == 204

    r = await client.post(
        f"/projects/{pid}/continuity-predicates",
        json={"key": "carries", "name": "Again"},
    )
    assert r.status_code == 409
    assert r.json()["error_code"] == "CONTINUITY_PREDICATE_KEY_CONFLICT"

    # Keys are Project-scoped: another Project may own the same key.
    pid2 = await _seed_project(factory, name="Q")
    await _predicate(client, pid2, key="carries")


async def test_predicate_patch_display_only(client, factory):
    pid = await _seed_project(factory)
    p = await _predicate(
        client, pid, key="carries", name="Carries", description="old",
    )

    r = await client.patch(
        f"/continuity-predicates/{p['id']}",
        json={"name": "  Carries v2 ", "description": None},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Carries v2"
    assert body["description"] is None  # explicit null clears
    assert body["key"] == "carries"
    assert body["updated_at"] >= p["updated_at"]

    # Omitted fields are preserved.
    r = await client.patch(
        f"/continuity-predicates/{p['id']}", json={"description": "new"}
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Carries v2"
    assert r.json()["description"] == "new"

    # key is immutable identity: not accepted by the patch schema.
    r = await client.patch(
        f"/continuity-predicates/{p['id']}", json={"key": "other"}
    )
    assert r.status_code == 422

    # Empty patch is a legal active-check no-op.
    r = await client.patch(f"/continuity-predicates/{p['id']}", json={})
    assert r.status_code == 200
    assert r.json()["key"] == "carries"

    # Empty name after strip is rejected through the generic contract.
    r = await client.patch(
        f"/continuity-predicates/{p['id']}", json={"name": "  "}
    )
    assert r.status_code == 422
    assert r.json()["error_code"] == "VALIDATION_ERROR"


async def test_predicate_delete_in_use_and_idempotent(client, factory):
    pid = await _seed_project(factory)
    p = await _predicate(client, pid, key="carries")
    eva = await _entity(client, pid, name="Eva")
    bag = await _entity(client, pid, kind="prop", name="Bag")
    await _relation(client, pid, eva["id"], p["id"], bag["id"])

    r = await client.delete(f"/continuity-predicates/{p['id']}")
    assert r.status_code == 409
    assert r.json()["error_code"] == "CONTINUITY_PREDICATE_IN_USE"

    # Removing the relation releases the guard.
    relations = (
        await client.get(f"/projects/{pid}/continuity-relations")
    ).json()
    r = await client.delete(f"/continuity-relations/{relations[0]['id']}")
    assert r.status_code == 204
    r = await client.delete(f"/continuity-predicates/{p['id']}")
    assert r.status_code == 204
    # Idempotent for already-tombstoned.
    r = await client.delete(f"/continuity-predicates/{p['id']}")
    assert r.status_code == 204


async def test_predicate_unresolved_ids_use_generic_contract(client, factory):
    pid = await _seed_project(factory)
    p = await _predicate(client, pid, key="carries")

    r = await client.delete("/continuity-predicates/not-a-uuid")
    assert r.status_code == 422
    assert r.json()["error_code"] == "VALIDATION_ERROR"

    r = await client.get("/continuity-predicates/not-a-uuid")
    assert r.status_code == 422
    assert r.json()["error_code"] == "VALIDATION_ERROR"

    r = await client.patch(
        "/continuity-predicates/00000000-0000-4000-8000-000000000000",
        json={"name": "x"},
    )
    assert r.status_code == 422
    assert r.json()["error_code"] == "VALIDATION_ERROR"

    await client.delete(f"/continuity-predicates/{p['id']}")
    # Tombstoned predicate is unresolved on GET/PATCH.
    r = await client.get(f"/continuity-predicates/{p['id']}")
    assert r.status_code == 422
    r = await client.patch(
        f"/continuity-predicates/{p['id']}", json={"name": "x"}
    )
    assert r.status_code == 422


async def test_predicate_list_ordered_and_lifecycle_filtered(client, factory):
    pid = await _seed_project(factory)
    await _predicate(client, pid, key="allies_with")
    await _predicate(client, pid, key="carries")
    await _predicate(client, pid, key="broken_by")

    r = await client.get(f"/projects/{pid}/continuity-predicates")
    assert r.status_code == 200
    keys = [row["key"] for row in r.json()]
    assert keys == ["allies_with", "broken_by", "carries"]  # ORDER BY key

    tombstone = (
        await client.get(f"/projects/{pid}/continuity-predicates")
    ).json()[2]
    await client.delete(f"/continuity-predicates/{tombstone['id']}")
    r = await client.get(f"/projects/{pid}/continuity-predicates")
    assert [row["key"] for row in r.json()] == ["allies_with", "broken_by"]


async def test_predicate_surface_requires_active_project(client, factory):
    pid = await _seed_project(factory)
    r = await client.get("/projects/not-a-uuid/continuity-predicates")
    assert r.status_code == 404
    r = await client.post(
        "/projects/not-a-uuid/continuity-predicates",
        json={"key": "k", "name": "N"},
    )
    assert r.status_code == 404

    async with factory() as s:
        await project_svc.delete_project(s, pid)
    r = await client.get(f"/projects/{pid}/continuity-predicates")
    assert r.status_code == 404
    r = await client.post(
        f"/projects/{pid}/continuity-predicates",
        json={"key": "k", "name": "N"},
    )
    assert r.status_code == 404


# --- §21.2 ContinuityRelation --------------------------------------------------


async def test_relation_create_read_roundtrip(client, factory):
    pid = await _seed_project(factory)
    eva = await _entity(client, pid, name="Eva")
    bag = await _entity(client, pid, kind="prop", name="Bag")
    p = await _predicate(client, pid, key="carries")

    rel = await _relation(client, pid, eva["id"], p["id"], bag["id"])
    assert rel["project_id"] == pid
    assert rel["subject_entity_id"] == eva["id"]
    assert rel["predicate_id"] == p["id"]
    assert rel["predicate_key"] == "carries"  # denormalized display key
    assert rel["object_entity_id"] == bag["id"]

    r = await client.get(f"/continuity-relations/{rel['id']}")
    assert r.status_code == 200
    assert r.json() == rel


async def test_relation_structural_invalidity_matrix(client, factory):
    pid = await _seed_project(factory)
    pid2 = await _seed_project(factory, name="Q")
    eva = await _entity(client, pid, name="Eva")
    bag = await _entity(client, pid, kind="prop", name="Bag")
    foreign = await _entity(client, pid2, name="Foreign")
    p = await _predicate(client, pid, key="carries")
    p2 = await _predicate(client, pid2, key="carries")

    async def attempt(subject, predicate, obj, expected_code):
        r = await client.post(
            f"/projects/{pid}/continuity-relations",
            json={
                "subject_entity_id": subject,
                "predicate_id": predicate,
                "object_entity_id": obj,
            },
        )
        assert r.status_code in (404, 422), r.text
        assert r.json()["error_code"] == expected_code, r.text

    # Self relation (checked first — pure, no database access).
    await attempt(eva["id"], p["id"], eva["id"], "INVALID_CONTINUITY_RELATION")
    # Malformed endpoint ids.
    await attempt("not-a-uuid", p["id"], bag["id"], "ENTITY_NOT_FOUND")
    # Missing endpoints are Entity lookups (404, existing vocabulary).
    await attempt(
        "00000000-0000-4000-8000-000000000001", p["id"], bag["id"],
        "ENTITY_NOT_FOUND",
    )
    await attempt(
        eva["id"], p["id"], "00000000-0000-4000-8000-000000000002",
        "ENTITY_NOT_FOUND",
    )
    # Cross-Project endpoints make the relation structurally invalid.
    await attempt(
        foreign["id"], p["id"], bag["id"], "INVALID_CONTINUITY_RELATION"
    )
    await attempt(
        eva["id"], p["id"], foreign["id"], "INVALID_CONTINUITY_RELATION"
    )
    # Tombstoned endpoint is an unresolved Entity.
    temp = await _entity(client, pid, name="Temp")
    async with factory() as s:
        await entity_svc.delete_entity(s, temp["id"])
    await attempt(temp["id"], p["id"], bag["id"], "ENTITY_NOT_FOUND")
    # Predicate: missing / cross-Project / tombstoned-same-Project all make
    # the relation structurally invalid (no predicate not-found code exists).
    await attempt(
        eva["id"], "00000000-0000-4000-8000-000000000003", bag["id"],
        "INVALID_CONTINUITY_RELATION",
    )
    await attempt(eva["id"], p2["id"], bag["id"], "INVALID_CONTINUITY_RELATION")
    await client.delete(f"/continuity-predicates/{p2['id']}")
    await attempt(eva["id"], p2["id"], bag["id"], "INVALID_CONTINUITY_RELATION")


async def test_relation_duplicate_active_identity_and_slot_freeing(client, factory):
    """Active-slot identity: duplicate active coordinate conflicts;
    soft-delete FREES the slot and recreation is a NEW identity (§3)."""
    pid = await _seed_project(factory)
    eva = await _entity(client, pid, name="Eva")
    bag = await _entity(client, pid, kind="prop", name="Bag")
    p = await _predicate(client, pid, key="carries")

    rel = await _relation(client, pid, eva["id"], p["id"], bag["id"])

    r = await client.post(
        f"/projects/{pid}/continuity-relations",
        json={
            "subject_entity_id": eva["id"],
            "predicate_id": p["id"],
            "object_entity_id": bag["id"],
        },
    )
    assert r.status_code == 409
    assert r.json()["error_code"] == "CONTINUITY_RELATION_CONFLICT"

    r = await client.delete(f"/continuity-relations/{rel['id']}")
    assert r.status_code == 204

    rel2 = await _relation(client, pid, eva["id"], p["id"], bag["id"])
    assert rel2["id"] != rel["id"]  # NEW relation identity


async def test_relation_delete_idempotent_and_unresolved(client, factory):
    pid = await _seed_project(factory)
    eva = await _entity(client, pid, name="Eva")
    bag = await _entity(client, pid, kind="prop", name="Bag")
    p = await _predicate(client, pid, key="carries")
    rel = await _relation(client, pid, eva["id"], p["id"], bag["id"])

    r = await client.delete(f"/continuity-relations/{rel['id']}")
    assert r.status_code == 204
    # Idempotent for tombstoned.
    r = await client.delete(f"/continuity-relations/{rel['id']}")
    assert r.status_code == 204

    # Never-existed and non-uuid use the generic contract.
    r = await client.delete("/continuity-relations/not-a-uuid")
    assert r.status_code == 422
    assert r.json()["error_code"] == "VALIDATION_ERROR"
    r = await client.get(
        "/continuity-relations/00000000-0000-4000-8000-000000000009"
    )
    assert r.status_code == 422
    assert r.json()["error_code"] == "VALIDATION_ERROR"
    # Tombstoned relation is unresolved on GET.
    r = await client.get(f"/continuity-relations/{rel['id']}")
    assert r.status_code == 422


async def test_relation_has_no_patch_route(client, factory):
    """0008 has no mutable relation columns — PATCH must not exist."""
    pid = await _seed_project(factory)
    eva = await _entity(client, pid, name="Eva")
    bag = await _entity(client, pid, kind="prop", name="Bag")
    p = await _predicate(client, pid, key="carries")
    rel = await _relation(client, pid, eva["id"], p["id"], bag["id"])

    r = await client.patch(
        f"/continuity-relations/{rel['id']}", json={"predicate_id": p["id"]}
    )
    assert r.status_code == 405


async def test_relation_list_display_order_and_filters(client, factory):
    pid = await _seed_project(factory)
    eva = await _entity(client, pid, name="Eva")
    bag = await _entity(client, pid, kind="prop", name="Bag")
    axe = await _entity(client, pid, kind="prop", name="Axe")
    carries = await _predicate(client, pid, key="carries")
    wields = await _predicate(client, pid, key="wields")

    r1 = await _relation(client, pid, eva["id"], carries["id"], bag["id"])
    r2 = await _relation(client, pid, eva["id"], wields["id"], axe["id"])
    r3 = await _relation(client, pid, axe["id"], carries["id"], bag["id"])

    r = await client.get(f"/projects/{pid}/continuity-relations")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 3
    # Display order is the frozen tuple (subject, predicate_key, object, id).
    keys = [
        (row["subject_entity_id"], row["predicate_key"],
         row["object_entity_id"], row["id"])
        for row in rows
    ]
    assert keys == sorted(keys)
    assert {row["id"] for row in rows} == {r1["id"], r2["id"], r3["id"]}

    r = await client.get(
        f"/projects/{pid}/continuity-relations",
        params={"subject_entity_id": eva["id"]},
    )
    assert {row["id"] for row in r.json()} == {r1["id"], r2["id"]}

    r = await client.get(
        f"/projects/{pid}/continuity-relations",
        params={"predicate_id": carries["id"]},
    )
    assert {row["id"] for row in r.json()} == {r1["id"], r3["id"]}

    r = await client.get(
        f"/projects/{pid}/continuity-relations",
        params={"object_entity_id": axe["id"]},
    )
    assert {row["id"] for row in r.json()} == {r2["id"]}

    await client.delete(f"/continuity-relations/{r1['id']}")
    r = await client.get(
        f"/projects/{pid}/continuity-relations",
        params={"subject_entity_id": eva["id"]},
    )
    assert {row["id"] for row in r.json()} == {r2["id"]}

    r = await client.get("/projects/not-a-uuid/continuity-relations")
    assert r.status_code == 404
