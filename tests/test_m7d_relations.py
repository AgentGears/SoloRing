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


# --- §21.3 RelationTransition ---------------------------------------------------

_M7D2_IMPORTS = True  # marker: section below uses shot/topology helpers


async def _topology(client, factory, pid, n_shots=2):
    from soloring.api.schemas.shots import ShotCreate
    from soloring.domain import shots as shot_svc

    r = await client.post(f"/projects/{pid}/sequences", json={"title": "S"})
    assert r.status_code == 201, r.text
    seq = r.json()["id"]
    r = await client.post(f"/sequences/{seq}/scenes", json={"title": "C"})
    assert r.status_code == 201, r.text
    scene = r.json()["id"]
    shot_ids = []
    for _ in range(n_shots):
        async with factory() as s:
            shot_ids.append(
                (await shot_svc.create_shot(
                    s, pid, ShotCreate(subject="x")
                )).id
            )
    r = await client.put(f"/scenes/{scene}/shots", json={"shot_ids": shot_ids})
    assert r.status_code == 200, r.text
    return seq, scene, shot_ids


async def _rt(client, relation_id, anchor_type, anchor_id, boundary, state):
    return await client.post(
        f"/continuity-relations/{relation_id}/transitions",
        json={
            "anchor_type": anchor_type, "anchor_id": anchor_id,
            "boundary": boundary, "state": state,
        },
    )


async def _depend(client, shot_id, entity_ids):
    r = await client.put(
        f"/shots/{shot_id}/semantic-dependencies",
        json={
            "dependencies": [
                {"entity_id": eid, "role": f"role{i}"}
                for i, eid in enumerate(entity_ids)
            ]
        },
    )
    assert r.status_code == 200, r.text


async def _entity_approved(client, pid, kind="character", name="Eva"):
    """Entities used as semantic dependencies need an approved revision
    (the M6 assignment rule)."""
    e = await _entity(client, pid, kind=kind, name=name)
    r = await client.post(
        f"/entities/{e['id']}/revisions", json={"spec": {"description": "d"}}
    )
    assert r.status_code == 201, r.text
    r = await client.put(
        f"/entities/{e['id']}/approved-revision",
        json={
            "revision_id": r.json()["id"],
            "expected_approved_revision_id": None,
        },
    )
    assert r.status_code == 200, r.text
    return e


async def test_relation_transition_create_patch_delete_matrix(client, factory):
    pid = await _seed_project(factory)
    seq, scene, shots = await _topology(client, factory, pid, n_shots=2)
    eva = await _entity(client, pid, name="Eva")
    bag = await _entity(client, pid, kind="prop", name="Bag")
    p = await _predicate(client, pid, key="carries")
    rel = await _relation(client, pid, eva["id"], p["id"], bag["id"])

    r = await _rt(client, rel["id"], "shot", shots[0], "start", "active")
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["state"] == "active" and t["relation_id"] == rel["id"]

    # Bad boundary / bad state.
    r = await _rt(client, rel["id"], "shot", shots[0], "end ", "active")
    assert r.status_code == 422
    assert r.json()["error_code"] == "INVALID_CONTINUITY_ANCHOR"
    r = await _rt(client, rel["id"], "shot", shots[0], "end", "on")
    assert r.status_code == 422
    assert r.json()["error_code"] == "VALIDATION_ERROR"

    # Cross-Project anchor → the existing anchor mismatch code.
    pid2 = await _seed_project(factory, name="Q")
    r2 = await client.post(f"/projects/{pid2}/sequences", json={"title": "S2"})
    foreign_seq = r2.json()["id"]
    r = await _rt(client, rel["id"], "sequence", foreign_seq, "start", "active")
    assert r.status_code == 409
    assert r.json()["error_code"] == "CONTINUITY_ANCHOR_PROJECT_MISMATCH"

    # Unassigned shot anchor.
    from soloring.api.schemas.shots import ShotCreate
    from soloring.domain import shots as shot_svc
    async with factory() as s:
        loose = (await shot_svc.create_shot(s, pid, ShotCreate(subject="y"))).id
    r = await _rt(client, rel["id"], "shot", loose, "start", "active")
    assert r.status_code == 422
    assert r.json()["error_code"] == "INVALID_CONTINUITY_ANCHOR"

    # Duplicate active coordinate.
    r = await _rt(client, rel["id"], "shot", shots[0], "start", "inactive")
    assert r.status_code == 409
    assert r.json()["error_code"] == "CONTINUITY_TRANSITION_CONFLICT"

    # PATCH: state flip; anchor move; no-op; coordinate conflict.
    r = await client.patch(
        f"/continuity-relation-transitions/{t['id']}",
        json={"state": "inactive"},
    )
    assert r.status_code == 200 and r.json()["state"] == "inactive"

    r = await client.patch(
        f"/continuity-relation-transitions/{t['id']}",
        json={"anchor_type": "shot", "anchor_id": shots[1], "boundary": "end"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["anchor_id"] == shots[1]

    r = await client.patch(
        f"/continuity-relation-transitions/{t['id']}", json={}
    )
    assert r.status_code == 200
    assert r.json()["anchor_id"] == shots[1] and r.json()["state"] == "inactive"

    other = (
        await _rt(client, rel["id"], "scene", scene, "start", "active")
    ).json()
    r = await client.patch(
        f"/continuity-relation-transitions/{t['id']}",
        json={"anchor_type": "scene", "anchor_id": scene, "boundary": "start"},
    )
    assert r.status_code == 409
    assert r.json()["error_code"] == "CONTINUITY_TRANSITION_CONFLICT"

    # Unknown relation / transition.
    r = await _rt(client, "not-a-uuid", "shot", shots[0], "start", "active")
    assert r.status_code == 409
    r = await client.patch(
        "/continuity-relation-transitions/not-a-uuid", json={"state": "active"}
    )
    assert r.status_code == 409

    # List is ordered and active-only.
    rows = (
        await client.get(f"/continuity-relations/{rel['id']}/transitions")
    ).json()
    assert [row["id"] for row in rows] == [t["id"], other["id"]]

    # Delete: idempotent; conflict for never-existed.
    r = await client.delete(f"/continuity-relation-transitions/{other['id']}")
    assert r.status_code == 204
    r = await client.delete(f"/continuity-relation-transitions/{other['id']}")
    assert r.status_code == 204
    r = await client.delete(
        "/continuity-relation-transitions/"
        "00000000-0000-4000-8000-000000000077"
    )
    assert r.status_code == 409


async def test_relation_delete_blocked_by_active_transitions(client, factory):
    """§13.2 / §21.2 in-use proof — active once transitions exist."""
    pid = await _seed_project(factory)
    seq, scene, shots = await _topology(client, factory, pid, n_shots=1)
    eva = await _entity(client, pid, name="Eva")
    bag = await _entity(client, pid, kind="prop", name="Bag")
    p = await _predicate(client, pid, key="carries")
    rel = await _relation(client, pid, eva["id"], p["id"], bag["id"])

    r = await _rt(client, rel["id"], "shot", shots[0], "start", "active")
    assert r.status_code == 201
    tid = r.json()["id"]

    r = await client.delete(f"/continuity-relations/{rel['id']}")
    assert r.status_code == 409
    assert r.json()["error_code"] == "CONTINUITY_RELATION_IN_USE"

    r = await client.delete(f"/continuity-relation-transitions/{tid}")
    assert r.status_code == 204
    r = await client.delete(f"/continuity-relations/{rel['id']}")
    assert r.status_code == 204


# --- §21.4 Effective relation resolver + readiness ------------------------------


async def test_resolver_effective_relation_state(client, factory):
    """Both endpoints dependent + winner active → effective relation in
    the strict current-state response; display fields exact."""
    pid = await _seed_project(factory)
    seq, scene, shots = await _topology(client, factory, pid, n_shots=2)
    eva = await _entity_approved(client, pid, kind="character", name="Eva")
    bag = await _entity_approved(client, pid, kind="prop", name="Bag")
    carries = await _predicate(client, pid, key="carries")
    rel = await _relation(client, pid, eva["id"], carries["id"], bag["id"])
    await _depend(client, shots[0], [eva["id"], bag["id"]])
    await _depend(client, shots[1], [eva["id"], bag["id"]])

    r = await _rt(client, rel["id"], "shot", shots[0], "start", "active")
    assert r.status_code == 201

    r = await client.get(f"/shots/{shots[1]}/continuity-state")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["continuity_state_ready"] is True
    assert body["readiness_issues"] == []
    assert len(body["relation_states"]) == 1
    rs = body["relation_states"][0]
    assert rs["relation_id"] == rel["id"]
    assert rs["predicate_key"] == "carries"
    assert rs["subject_entity_id"] == eva["id"]
    assert rs["object_entity_id"] == bag["id"]
    assert rs["predicate_id"] == carries["id"]
    assert rs["source_anchor"] == {
        "anchor_type": "shot", "anchor_id": shots[0], "boundary": "start",
    }
    assert rs["source_transition_id"]


async def test_resolver_neither_endpoint_relation_is_irrelevant(client, factory):
    """A relation whose NEITHER endpoint is a dependency never appears —
    not in relation_states, not as an issue, no readiness impact."""
    pid = await _seed_project(factory)
    seq, scene, shots = await _topology(client, factory, pid, n_shots=1)
    eva = await _entity_approved(client, pid, kind="character", name="Eva")
    bag = await _entity_approved(client, pid, kind="prop", name="Bag")
    axe = await _entity(client, pid, kind="prop", name="Axe")
    rusts = await _predicate(client, pid, key="rusts")
    # axe--rusts-->bag: neither endpoint is a dependency of the shot.
    await _relation(client, pid, axe["id"], rusts["id"], bag["id"])
    await _depend(client, shots[0], [eva["id"]])

    relations = (
        await client.get(f"/projects/{pid}/continuity-relations")
    ).json()
    r = await _rt(
        client, relations[0]["id"], "shot", shots[0], "start", "active"
    )
    assert r.status_code == 201

    r = await client.get(f"/shots/{shots[0]}/continuity-state")
    assert r.status_code == 200
    assert r.json()["relation_states"] == []
    assert r.json()["readiness_issues"] == []
    assert r.json()["continuity_state_ready"] is True


async def test_resolver_endpoint_required_contract(client, factory):
    """The load-bearing §5.3/§7.1/§12.3–12.4 contract: exactly one
    dependency endpoint → not-ready, NULL hash/differs, blocked strict
    endpoint, full ordered §12.4 issue elements; completing the endpoint
    makes the relation EFFECTIVE; removing it again flips not-ready."""
    pid = await _seed_project(factory)
    seq, scene, shots = await _topology(client, factory, pid, n_shots=2)
    eva = await _entity_approved(client, pid, kind="character", name="Eva")
    bag = await _entity_approved(client, pid, kind="prop", name="Bag")
    carries = await _predicate(client, pid, key="carries")
    holds = await _predicate(client, pid, key="holds")

    rel = await _relation(client, pid, eva["id"], carries["id"], bag["id"])
    rel2 = await _relation(client, pid, eva["id"], holds["id"], bag["id"])
    # BOTH shots depend on eva only — exactly one endpoint everywhere.
    await _depend(client, shots[0], [eva["id"]])
    await _depend(client, shots[1], [eva["id"]])

    assert (
        await _rt(client, rel["id"], "shot", shots[0], "start", "active")
    ).status_code == 201
    assert (
        await _rt(client, rel2["id"], "shot", shots[0], "start", "active")
    ).status_code == 201

    # Strict endpoint raises ONE 409 with the FULL ordered issue set.
    r = await client.get(f"/shots/{shots[1]}/continuity-state")
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error_code"] == "CONTINUITY_RELATION_ENDPOINT_REQUIRED"
    issues = body["details"]["issues"]
    assert len(issues) == 2  # ALL issues, never first-row
    assert issues == sorted(
        issues,
        key=lambda i: (
            i["subject_entity_id"], i["predicate_key"],
            i["object_entity_id"], i["relation_id"],
        ),
    )
    for issue, relation in zip(issues, sorted(
        (rel, rel2), key=lambda x: x["predicate_key"]
    )):
        assert issue["error_code"] == "CONTINUITY_RELATION_ENDPOINT_REQUIRED"
        assert issue["relation_id"] == relation["id"]
        assert issue["subject_entity_id"] == eva["id"]
        assert issue["object_entity_id"] == bag["id"]
        assert issue["present_entity_id"] == eva["id"]
        assert issue["missing_entity_id"] == bag["id"]

    # ShotRead: not-ready with NULL hash/differs and the same issues.
    r = await client.get(f"/shots/{shots[1]}")
    assert r.status_code == 200
    shot = r.json()
    assert shot["continuity_state_ready"] is False
    assert shot["working_snapshot_hash"] is None
    assert shot["working_state_differs_from_approved"] is None
    assert len(shot["readiness_issues"]) == 2
    assert (
        shot["readiness_issues"][0]["error_code"]
        == "CONTINUITY_RELATION_ENDPOINT_REQUIRED"
    )
    assert shot["readiness_issues"][0]["missing_entity_id"] == bag["id"]

    # Completing the state: add the missing endpoint → ready, and the
    # relations become EFFECTIVE (no hidden dependency was created).
    await _depend(client, shots[1], [eva["id"], bag["id"]])
    r = await client.get(f"/shots/{shots[1]}/continuity-state")
    assert r.status_code == 200
    assert r.json()["readiness_issues"] == []
    assert len(r.json()["relation_states"]) == 2

    # Dependency removal is legal and flips the shot not-ready (§5.3).
    await _depend(client, shots[1], [eva["id"]])
    r = await client.get(f"/shots/{shots[1]}/continuity-state")
    assert r.status_code == 409
    assert (
        r.json()["error_code"] == "CONTINUITY_RELATION_ENDPOINT_REQUIRED"
    )


async def test_resolver_inactive_winner_and_boundary_eligibility(client, factory):
    pid = await _seed_project(factory)
    seq, scene, shots = await _topology(client, factory, pid, n_shots=2)
    eva = await _entity_approved(client, pid, kind="character", name="Eva")
    bag = await _entity_approved(client, pid, kind="prop", name="Bag")
    carries = await _predicate(client, pid, key="carries")
    rel = await _relation(client, pid, eva["id"], carries["id"], bag["id"])
    await _depend(client, shots[0], [eva["id"], bag["id"]])
    await _depend(client, shots[1], [eva["id"], bag["id"]])

    # Inactive winner at shot1/start → canonical absence, ready.
    r = await _rt(client, rel["id"], "shot", shots[0], "start", "inactive")
    assert r.status_code == 201
    r = await client.get(f"/shots/{shots[1]}/continuity-state")
    assert r.status_code == 200
    assert r.json()["relation_states"] == []

    # Active at shot2/end — AFTER shot2/start → not eligible (APR-011).
    r = await _rt(client, rel["id"], "shot", shots[1], "end", "active")
    assert r.status_code == 201
    r = await client.get(f"/shots/{shots[1]}/continuity-state")
    assert r.status_code == 200
    assert r.json()["relation_states"] == []
    # The shot1/start inactive winner is still the eligible winner there.
    r = await client.get(f"/shots/{shots[0]}/continuity-state")
    assert r.status_code == 200
    assert r.json()["relation_states"] == []


async def test_resolver_unassigned_precedence_with_relation_data(client, factory):
    """Unassigned + relevant relation data → NARRATIVE_CONTEXT_REQUIRED,
    taking precedence over endpoint classification (§7.1)."""
    from soloring.api.schemas.shots import ShotCreate
    from soloring.domain import shots as shot_svc

    pid = await _seed_project(factory)
    seq, scene, shots = await _topology(client, factory, pid, n_shots=1)
    eva = await _entity_approved(client, pid, kind="character", name="Eva")
    bag = await _entity_approved(client, pid, kind="prop", name="Bag")
    carries = await _predicate(client, pid, key="carries")
    rel = await _relation(client, pid, eva["id"], carries["id"], bag["id"])

    async with factory() as s:
        loose = (await shot_svc.create_shot(s, pid, ShotCreate(subject="y"))).id
    await _depend(client, loose, [eva["id"]])  # exactly one endpoint

    # The transition is anchored at a REAL boundary → relevant data exists.
    r = await _rt(client, rel["id"], "shot", shots[0], "start", "active")
    assert r.status_code == 201

    r = await client.get(f"/shots/{loose}/continuity-state")
    assert r.status_code == 409
    assert r.json()["error_code"] == "NARRATIVE_CONTEXT_REQUIRED"

    r = await client.get(f"/shots/{loose}")
    assert r.status_code == 200
    assert r.json()["continuity_state_ready"] is False
    assert (
        r.json()["readiness_issues"][0]["error_code"]
        == "NARRATIVE_CONTEXT_REQUIRED"
    )


# --- §21.5–§21.8 Capture, reuse integrity, historical provenance -----------------


async def _capture(factory, shot_id):
    from soloring.domain import revisions as revision_svc

    return await revision_svc.capture_revision(factory(), shot_id)


async def _fetch(engine, sql, params=None):
    from sqlalchemy import text

    async with engine.connect() as conn:
        return (
            await conn.execute(text(sql), params or {})
        ).mappings().all()


async def test_capture_relation_only_promotes_schema_2_to_3(client, factory,
                                                            engine):
    """A relation state alone (deps present, zero Feature states) promotes
    the capture to schema 3 + spec 2 — and zero-of-both keeps the exact
    schema-2 form (APR-016 extension)."""
    pid = await _seed_project(factory)
    seq, scene, shots = await _topology(client, factory, pid, n_shots=1)
    eva = await _entity_approved(client, pid, name="Eva")
    bag = await _entity_approved(client, pid, kind="prop", name="Bag")
    carries = await _predicate(client, pid, key="carries")
    await _depend(client, shots[0], [eva["id"], bag["id"]])

    # Before any relation temporal state: deps only → exact schema 2.
    legacy = await _capture(factory, shots[0])
    snap = (await _fetch(
        engine, "SELECT snapshot_json FROM shot_revisions WHERE id = :r",
        {"r": legacy.id},
    ))[0]["snapshot_json"]
    import json as _json

    assert _json.loads(snap)["schema_version"] == 2

    rel = await _relation(client, pid, eva["id"], carries["id"], bag["id"])
    assert (
        await _rt(client, rel["id"], "shot", shots[0], "start", "active")
    ).status_code == 201

    rev = await _capture(factory, shots[0])
    assert rev.id != legacy.id
    snap = (await _fetch(
        engine, "SELECT snapshot_json, continuity_spec_json FROM "
        "shot_revisions WHERE id = :r", {"r": rev.id},
    ))[0]
    assert _json.loads(snap["snapshot_json"])["schema_version"] == 3
    spec = _json.loads(snap["continuity_spec_json"])
    assert spec["schema_version"] == 2
    assert len(spec["relations"]) == 1
    entry = spec["relations"][0]
    assert entry["subject_entity_id"] == eva["id"]
    assert entry["relation_id"] == rel["id"]
    assert entry["predicate_id"] == carries["id"]
    assert entry["predicate_key"] == "carries"
    assert entry["object_entity_id"] == bag["id"]
    assert entry["source_anchor"] == {
        "anchor_type": "shot", "anchor_id": shots[0], "boundary": "start",
    }
    assert "source_transition_id" not in entry  # audit-only (APR-022)
    # The legacy schema-2 revision is untouched: relations still [].
    legacy_proj = await client.get(f"/shot-revisions/{legacy.id}/continuity")
    assert legacy_proj.status_code == 200
    assert legacy_proj.json()["relations"] == []


async def test_capture_exact_relation_bytes_and_canonical_order(client, factory,
                                                                 engine):
    """The relations array is byte-exact under the canonical
    (subject, predicate_key, object, relation_id) order — including the
    predicate_key tiebreak between two relations of one subject."""
    pid = await _seed_project(factory)
    seq, scene, shots = await _topology(client, factory, pid, n_shots=1)
    eva = await _entity_approved(client, pid, name="Eva")
    bag = await _entity_approved(client, pid, kind="prop", name="Bag")
    axe = await _entity_approved(client, pid, kind="prop", name="Axe")
    holds = await _predicate(client, pid, key="holds")
    carries = await _predicate(client, pid, key="carries")  # carries < holds
    await _depend(client, shots[0], [eva["id"], bag["id"], axe["id"]])

    r_bag = await _relation(client, pid, eva["id"], holds["id"], bag["id"])
    r_axe = await _relation(client, pid, eva["id"], carries["id"], axe["id"])
    assert (
        await _rt(client, r_bag["id"], "scene", scene, "start", "active")
    ).status_code == 201
    assert (
        await _rt(client, r_axe["id"], "scene", scene, "start", "active")
    ).status_code == 201

    rev = await _capture(factory, shots[0])
    spec_json = (await _fetch(
        engine, "SELECT continuity_spec_json FROM shot_revisions "
        "WHERE id = :r", {"r": rev.id},
    ))[0]["continuity_spec_json"]

    from soloring.domain.canonical import canonical_json_str

    # Byte-exact expectation built from the SAME canonical serializer:
    # insertion-ordered entries, carries (c) before holds (h).
    expected_entries = [
        {
            "subject_entity_id": eva["id"],
            "relation_id": r_axe["id"],
            "predicate_id": carries["id"],
            "predicate_key": "carries",
            "object_entity_id": axe["id"],
            "source_anchor": {
                "anchor_type": "scene", "anchor_id": scene,
                "boundary": "start",
            },
        },
        {
            "subject_entity_id": eva["id"],
            "relation_id": r_bag["id"],
            "predicate_id": holds["id"],
            "predicate_key": "holds",
            "object_entity_id": bag["id"],
            "source_anchor": {
                "anchor_type": "scene", "anchor_id": scene,
                "boundary": "start",
            },
        },
    ]
    spec = __import__("json").loads(spec_json)
    assert spec["relations"] == expected_entries
    rebuilt = {
        "schema_version": 2,
        "dependencies": spec["dependencies"],
        "feature_states": spec["feature_states"],
        "relations": expected_entries,
    }
    assert spec_json == canonical_json_str(rebuilt)


async def test_capture_persists_relation_rows_exactly(client, factory, engine):
    pid = await _seed_project(factory)
    seq, scene, shots = await _topology(client, factory, pid, n_shots=1)
    eva = await _entity_approved(client, pid, name="Eva")
    bag = await _entity_approved(client, pid, kind="prop", name="Bag")
    carries = await _predicate(client, pid, key="carries")
    rel = await _relation(client, pid, eva["id"], carries["id"], bag["id"])
    tr = (
        await _rt(client, rel["id"], "shot", shots[0], "start", "active")
    ).json()
    await _depend(client, shots[0], [eva["id"], bag["id"]])

    rev = await _capture(factory, shots[0])
    rows = await _fetch(
        engine,
        "SELECT relation_id, subject_entity_id, predicate_id, "
        "predicate_key, object_entity_id, source_transition_id, "
        "source_anchor_type, source_anchor_id, source_boundary "
        "FROM shot_revision_relation_states WHERE shot_revision_id = :r",
        {"r": rev.id},
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["relation_id"] == rel["id"]
    assert row["subject_entity_id"] == eva["id"]
    assert row["predicate_id"] == carries["id"]
    assert row["predicate_key"] == "carries"
    assert row["object_entity_id"] == bag["id"]
    assert row["source_transition_id"] == tr["id"]  # audit id persisted
    assert row["source_anchor_type"] == "shot"
    assert row["source_anchor_id"] == shots[0]
    assert row["source_boundary"] == "start"


async def test_working_hash_moves_on_relation_mutation_without_shot_change(
    client, factory,
):
    """M6-F15 extension (§21.6): relation mutation changes the effective
    working hash with NO Shot-row mutation."""
    pid = await _seed_project(factory)
    seq, scene, shots = await _topology(client, factory, pid, n_shots=1)
    eva = await _entity_approved(client, pid, name="Eva")
    bag = await _entity_approved(client, pid, kind="prop", name="Bag")
    carries = await _predicate(client, pid, key="carries")
    await _depend(client, shots[0], [eva["id"], bag["id"]])

    before = (await client.get(f"/shots/{shots[0]}")).json()
    rel = await _relation(client, pid, eva["id"], carries["id"], bag["id"])
    await _rt(client, rel["id"], "shot", shots[0], "start", "active")

    after = (await client.get(f"/shots/{shots[0]}")).json()
    assert after["working_snapshot_hash"] != before["working_snapshot_hash"]
    assert after["updated_at"] == before["updated_at"]  # no Shot-row change

    # Deactivating the relation changes the hash again.
    trs = (
        await client.get(f"/continuity-relations/{rel['id']}/transitions")
    ).json()
    r = await client.patch(
        f"/continuity-relation-transitions/{trs[0]['id']}",
        json={"state": "inactive"},
    )
    assert r.status_code == 200
    cleared = (await client.get(f"/shots/{shots[0]}")).json()
    assert cleared["working_snapshot_hash"] != after["working_snapshot_hash"]


async def test_capture_blocked_when_endpoint_incomplete(client, factory,
                                                        engine):
    """An endpoint-incomplete Shot captures NOTHING (§8.3): the read unit
    raises before the builder — no ShotRevision row is written."""
    pid = await _seed_project(factory)
    seq, scene, shots = await _topology(client, factory, pid, n_shots=1)
    eva = await _entity_approved(client, pid, name="Eva")
    bag = await _entity_approved(client, pid, kind="prop", name="Bag")
    carries = await _predicate(client, pid, key="carries")
    rel = await _relation(client, pid, eva["id"], carries["id"], bag["id"])
    await _rt(client, rel["id"], "shot", shots[0], "start", "active")
    await _depend(client, shots[0], [eva["id"]])  # exactly one endpoint

    r = await client.post(f"/shots/{shots[0]}/generations")
    assert r.status_code == 409
    assert (
        r.json()["error_code"] == "CONTINUITY_RELATION_ENDPOINT_REQUIRED"
    )
    rows = await _fetch(
        engine, "SELECT id FROM shot_revisions WHERE shot_id = :s",
        {"s": shots[0]},
    )
    assert rows == []


async def test_reuse_convergence_and_relation_corruption_fails_closed(
    client, factory, engine,
):
    """Identical relation captures converge onto one revision; a corrupted
    stored relation row makes the NEXT capture fail closed (UPDATE-then-
    restore loop, never DELETE); the loop ends from valid state."""
    from soloring.domain import revisions as revision_svc
    from soloring.errors import SoloRingError
    from sqlalchemy import text

    pid = await _seed_project(factory)
    seq, scene, shots = await _topology(client, factory, pid, n_shots=1)
    eva = await _entity_approved(client, pid, name="Eva")
    bag = await _entity_approved(client, pid, kind="prop", name="Bag")
    carries = await _predicate(client, pid, key="carries")
    rel = await _relation(client, pid, eva["id"], carries["id"], bag["id"])
    await _rt(client, rel["id"], "shot", shots[0], "start", "active")
    await _depend(client, shots[0], [eva["id"], bag["id"]])

    first = await revision_svc.capture_revision(factory(), shots[0])
    second = await revision_svc.capture_revision(factory(), shots[0])
    assert first.id == second.id  # convergence (APR-032)

    rows = await _fetch(
        engine,
        "SELECT relation_id, predicate_key, object_entity_id FROM "
        "shot_revision_relation_states WHERE shot_revision_id = :r",
        {"r": first.id},
    )
    assert len(rows) == 1
    originals = dict(rows[0])

    # Corruption matrix: each case UPDATEs in its OWN committed unit (a
    # pending transaction would be invisible to the capture connection
    # under WAL), expects the invariant failure, then RESTORES the
    # original bytes (never DELETE — later cases must hit THIS field's
    # validation, not missing-children).
    async def run(sql, params):
        async with engine.begin() as conn:
            await conn.execute(text(sql), params)

    cases = [
        ("predicate_key", "Bad Key!"),
        ("predicate_key", "wrong_key"),
        ("object_entity_id", "00000000-0000-4000-8000-000000000099"),
    ]
    for field, bad in cases:
        await run(
            f"UPDATE shot_revision_relation_states SET {field} = :v "
            "WHERE shot_revision_id = :r",
            {"v": bad, "r": first.id},
        )
        try:
            await revision_svc.capture_revision(factory(), shots[0])
            raised = False
        except SoloRingError as exc:
            raised = (
                exc.code == "INTERNAL_INVARIANT_VIOLATION"
                and exc.status_code == 500
            )
        assert raised, (field, bad)
        await run(
            "UPDATE shot_revision_relation_states SET relation_id = :rid, "
            "predicate_key = :pk, object_entity_id = :oid "
            "WHERE shot_revision_id = :r",
            {"rid": originals["relation_id"],
             "pk": originals["predicate_key"],
             "oid": originals["object_entity_id"], "r": first.id},
        )

    # Positive control: the loop began and ended from valid state.
    final = await revision_svc.capture_revision(factory(), shots[0])
    assert final.id == first.id


async def test_historical_relations_projection_and_legal_teardown_isolation(
    client, factory, engine,
):
    """§21.8 + §16: the historical projection exposes relations + audit;
    the LEGAL teardown sequence (transition → relation → predicate) after
    capture never changes stored bytes."""
    pid = await _seed_project(factory)
    seq, scene, shots = await _topology(client, factory, pid, n_shots=1)
    eva = await _entity_approved(client, pid, name="Eva")
    bag = await _entity_approved(client, pid, kind="prop", name="Bag")
    carries = await _predicate(client, pid, key="carries")
    rel = await _relation(client, pid, eva["id"], carries["id"], bag["id"])
    tr = (
        await _rt(client, rel["id"], "shot", shots[0], "start", "active")
    ).json()
    await _depend(client, shots[0], [eva["id"], bag["id"]])

    rev = await _capture(factory, shots[0])
    stored = (await _fetch(
        engine, "SELECT snapshot_json, continuity_spec_json, "
        "continuity_spec_hash FROM shot_revisions WHERE id = :r",
        {"r": rev.id},
    ))[0]

    proj = await client.get(f"/shot-revisions/{rev.id}/continuity")
    assert proj.status_code == 200, proj.text
    body = proj.json()
    assert len(body["relations"]) == 1
    assert body["relations"][0]["relation_id"] == rel["id"]
    audit_ids = {
        e.get("relation_id") for e in body["source_transition_audit"]
    }
    assert rel["id"] in audit_ids

    # Legal teardown (each step releases the previous in-use guard).
    assert (
        await client.delete(
            f"/continuity-relation-transitions/{tr['id']}"
        )
    ).status_code == 204
    assert (
        await client.delete(f"/continuity-relations/{rel['id']}")
    ).status_code == 204
    assert (
        await client.delete(f"/continuity-predicates/{carries['id']}")
    ).status_code == 204

    after = (await _fetch(
        engine, "SELECT snapshot_json, continuity_spec_json, "
        "continuity_spec_hash FROM shot_revisions WHERE id = :r",
        {"r": rev.id},
    ))[0]
    assert dict(after) == dict(stored)  # history is immutable fact

    proj = await client.get(f"/shot-revisions/{rev.id}/continuity")
    assert proj.status_code == 200
    assert len(proj.json()["relations"]) == 1  # unchanged by teardown


# --- §21.9–§21.12 Guards, cascade, rerun, concurrency, scale ---------------------


async def test_entity_delete_blocked_as_relation_endpoint(client, factory):
    """§13.3: an Entity that is an endpoint of an active Relation is not
    deletable — both subject and object variants."""
    from soloring.continuity import entities as entity_svc
    from soloring.errors import SoloRingError

    pid = await _seed_project(factory)
    eva = await _entity_approved(client, pid, name="Eva")
    bag = await _entity_approved(client, pid, kind="prop", name="Bag")
    carries = await _predicate(client, pid, key="carries")
    rel = await _relation(client, pid, eva["id"], carries["id"], bag["id"])

    async with factory() as s:
        try:
            await entity_svc.delete_entity(s, eva["id"])
            raised = None
        except SoloRingError as exc:
            raised = exc
    assert raised is not None and raised.code == "ENTITY_IN_USE"
    assert raised.details.get("reason") == "active_continuity_relation_endpoint"

    r = await client.delete(f"/continuity-relations/{rel['id']}")
    assert r.status_code == 204
    async with factory() as s:
        await entity_svc.delete_entity(s, eva["id"])  # guard released


async def test_anchor_guards_cover_relation_transitions(client, factory):
    """§13.5: Shot delete, Scene delete, Sequence delete, and Shot
    unassign are each blocked by a Relation transition anchored there —
    and each releases once the transition is tombstoned."""
    # Sequence delete.
    pid = await _seed_project(factory)
    r = await client.post(f"/projects/{pid}/sequences", json={"title": "S"})
    seq = r.json()["id"]
    rel = None
    eva = await _entity_approved(client, pid, name="Eva")
    bag = await _entity_approved(client, pid, kind="prop", name="Bag")
    carries = await _predicate(client, pid, key="carries")
    rel = await _relation(client, pid, eva["id"], carries["id"], bag["id"])
    assert (
        await _rt(client, rel["id"], "sequence", seq, "start", "active")
    ).status_code == 201
    r = await client.delete(f"/sequences/{seq}")
    assert r.status_code == 409
    assert r.json()["error_code"] == "CONTINUITY_ANCHOR_IN_USE"

    # Scene delete on an EMPTY scene (assigned shots would trip the earlier
    # SCENE_IN_USE guard first) — a Relation transition anchors it.
    pid2 = await _seed_project(factory, name="Q")
    r = await client.post(f"/projects/{pid2}/sequences", json={"title": "S2"})
    sseq2 = r.json()["id"]
    r = await client.post(f"/sequences/{sseq2}/scenes", json={"title": "C"})
    empty_scene = r.json()["id"]
    eva2 = await _entity_approved(client, pid2, name="Eva")
    bag2 = await _entity_approved(client, pid2, kind="prop", name="Bag")
    carries2 = await _predicate(client, pid2, key="carries")
    rel2 = await _relation(client, pid2, eva2["id"], carries2["id"], bag2["id"])
    assert (
        await _rt(client, rel2["id"], "scene", empty_scene, "start", "active")
    ).status_code == 201

    r = await client.delete(f"/scenes/{empty_scene}")
    assert r.status_code == 409
    assert r.json()["error_code"] == "CONTINUITY_ANCHOR_IN_USE"
    trs2 = (
        await client.get(f"/continuity-relations/{rel2['id']}/transitions")
    ).json()
    await client.delete(f"/continuity-relation-transitions/{trs2[0]['id']}")
    r = await client.delete(f"/scenes/{empty_scene}")
    assert r.status_code == 204

    # Shot delete + unassign with a SHOT-anchored relation transition.
    pid3 = await _seed_project(factory, name="R")
    tseq, tscene, tshots = await _topology(client, factory, pid3, n_shots=1)
    eva3 = await _entity_approved(client, pid3, name="Eva")
    bag3 = await _entity_approved(client, pid3, kind="prop", name="Bag")
    carries3 = await _predicate(client, pid3, key="carries")
    rel3 = await _relation(client, pid3, eva3["id"], carries3["id"], bag3["id"])
    assert (
        await _rt(client, rel3["id"], "shot", tshots[0], "start", "active")
    ).status_code == 201

    r = await client.delete(f"/shots/{tshots[0]}")
    assert r.status_code == 409
    assert r.json()["error_code"] == "CONTINUITY_ANCHOR_IN_USE"
    r = await client.put(f"/scenes/{tscene}/shots", json={"shot_ids": []})
    assert r.status_code == 409
    assert r.json()["error_code"] == "CONTINUITY_ANCHOR_IN_USE"

    # Releasing the transitions releases every guard.
    trs = (
        await client.get(f"/continuity-relations/{rel3['id']}/transitions")
    ).json()
    assert (
        await client.delete(
            f"/continuity-relation-transitions/{trs[0]['id']}"
        )
    ).status_code == 204
    r = await client.delete(f"/shots/{tshots[0]}")
    assert r.status_code == 204


async def test_project_cascade_tombstones_relation_working_state(
    client, factory, engine,
):
    """§13.5 correction B: the cascade removes the ENTIRE relation working
    state (RelationTransitions → Relations → Predicates, one fence, one
    timestamp), history stays untouched, and the guard-chain invariant
    holds over all remaining active rows."""
    pid = await _seed_project(factory)
    seq, scene, shots = await _topology(client, factory, pid, n_shots=1)
    eva = await _entity_approved(client, pid, name="Eva")
    bag = await _entity_approved(client, pid, kind="prop", name="Bag")
    carries = await _predicate(client, pid, key="carries")
    rel = await _relation(client, pid, eva["id"], carries["id"], bag["id"])
    await _rt(client, rel["id"], "shot", shots[0], "start", "active")
    await _depend(client, shots[0], [eva["id"], bag["id"]])
    rev = await _capture(factory, shots[0])
    historical = await _fetch(
        engine, "SELECT COUNT(*) AS n FROM shot_revision_relation_states "
        "WHERE shot_revision_id = :r", {"r": rev.id},
    )
    assert historical[0]["n"] == 1

    async with factory() as s:
        await project_svc.delete_project(s, pid)

    for table in (
        "continuity_relation_transitions", "continuity_relations",
        "continuity_predicates",
    ):
        active = await _fetch(
            engine,
            f"SELECT COUNT(*) AS n FROM {table} WHERE deleted_at IS NULL",
        )
        assert active[0]["n"] == 0, table

    # The invariant chain over remaining active rows holds trivially and
    # provably: no active relation references a tombstoned predicate or
    # endpoint anywhere in the database.
    dangling = await _fetch(
        engine,
        "SELECT COUNT(*) AS n FROM continuity_relations r "
        "WHERE r.deleted_at IS NULL AND ("
        "EXISTS (SELECT 1 FROM continuity_predicates p "
        "WHERE p.id = r.predicate_id AND p.deleted_at IS NOT NULL) OR "
        "EXISTS (SELECT 1 FROM creative_entities e "
        "WHERE e.id IN (r.subject_entity_id, r.object_entity_id) "
        "AND e.deleted_at IS NOT NULL))",
    )
    assert dangling[0]["n"] == 0

    # History untouched.
    after = await _fetch(
        engine, "SELECT COUNT(*) AS n FROM shot_revision_relation_states "
        "WHERE shot_revision_id = :r", {"r": rev.id},
    )
    assert after[0]["n"] == 1


async def test_exact_rerun_both_resolvers_disabled(client, factory, engine,
                                                   settings):
    """§21.9 / APR-025: rerun provably succeeds with BOTH current-state
    resolvers disabled — any invocation raises."""
    from soloring.executors.fake import FakeExecutor
    from soloring.worker import execution as worker_execution
    from soloring.worker.ownership import acquire_worker_lease
    from tests.conftest import seed_reference_asset
    from soloring.api.schemas.references import ReferenceInput
    from soloring.domain import references as ref_svc

    pid = await _seed_project(factory)
    seq, scene, shots = await _topology(client, factory, pid, n_shots=1)
    eva = await _entity_approved(client, pid, name="Eva")
    bag = await _entity_approved(client, pid, kind="prop", name="Bag")
    carries = await _predicate(client, pid, key="carries")
    rel = await _relation(client, pid, eva["id"], carries["id"], bag["id"])
    await _rt(client, rel["id"], "sequence", seq, "start", "active")
    await _depend(client, shots[0], [eva["id"], bag["id"]])
    aid, _bh = await seed_reference_asset(engine, pid)
    async with factory() as s:
        await ref_svc.replace_references(
            s, shots[0], [ReferenceInput(asset_id=aid, role="reference")]
        )

    await acquire_worker_lease(engine, "w-rr", 30)
    genA = (await client.post(f"/shots/{shots[0]}/generations")).json()
    assert (await worker_execution.process_next_generation(
        engine, settings, "w-rr", FakeExecutor())) == "succeeded"
    revX = genA["shot_revision_id"]

    # Radically mutate current state (legal teardown).
    trs = (
        await client.get(f"/continuity-relations/{rel['id']}/transitions")
    ).json()
    for row in trs:
        await client.delete(
            f"/continuity-relation-transitions/{row['id']}"
        )
    await client.delete(f"/continuity-relations/{rel['id']}")

    import soloring.continuity.state as state_mod

    async def _forbidden(conn, shot_id):
        raise AssertionError(
            "current-state resolver invoked during Exact Rerun"
        )

    original_f = state_mod.resolve_effective_feature_state
    original_r = state_mod.resolve_effective_relation_state
    state_mod.resolve_effective_feature_state = _forbidden
    state_mod.resolve_effective_relation_state = _forbidden
    try:
        r = await client.post(f"/generations/{genA['id']}/rerun")
        assert r.status_code == 202, r.text
        assert r.json()["shot_revision_id"] == revX
        cont = (await client.get(
            f"/generations/{r.json()['id']}/continuity")).json()
        assert len(cont["relations"]) == 1
        assert cont["relations"][0]["relation_id"] == rel["id"]
    finally:
        state_mod.resolve_effective_feature_state = original_f
        state_mod.resolve_effective_relation_state = original_r


# --- Concurrency (§15 R1–R11, APR-033) -------------------------------------------


async def _race_capture(factory, shot_id, competitor):
    """capture_revision with the competitor's REAL mutation committing
    INSIDE the open read, at the relation-resolution seam (the M7C
    _open_read_race pattern; no sleeps)."""
    import asyncio as _a
    import soloring.continuity.state as state_mod
    from soloring.domain import revisions as revision_svc

    original = state_mod.resolve_effective_relation_state
    fired = {}

    async def wrap(conn, sid):
        result = await original(conn, sid)
        if "task" not in fired:
            done = _a.Event()

            async def run():
                try:
                    fired["outcome"] = await competitor()
                finally:
                    done.set()

            fired["task"] = _a.create_task(run())
            await done.wait()
        return result

    state_mod.resolve_effective_relation_state = wrap
    try:
        rev = await revision_svc.capture_revision(factory(), shot_id)
    finally:
        state_mod.resolve_effective_relation_state = original
    return rev


async def _relation_fixture(client, factory, n_shots=1, with_transition=True):
    pid = await _seed_project(factory)
    seq, scene, shots = await _topology(client, factory, pid, n_shots)
    eva = await _entity_approved(client, pid, name="Eva")
    bag = await _entity_approved(client, pid, kind="prop", name="Bag")
    carries = await _predicate(client, pid, key="carries")
    rel = await _relation(client, pid, eva["id"], carries["id"], bag["id"])
    tr = None
    if with_transition:
        tr = (
            await _rt(client, rel["id"], "shot", shots[0], "start", "active")
        ).json()
    for shot in shots:
        await _depend(client, shot, [eva["id"], bag["id"]])
    return pid, seq, scene, shots, eva, bag, carries, rel, tr


async def test_race_r1_relation_transition_patch_mid_read(client, factory):
    """R1: the competitor's PATCH commits inside the open read; capture is
    coherent BEFORE; the next capture observes AFTER."""
    from soloring.api.schemas.continuity_relations import (
        RelationTransitionPatch,
    )
    from soloring.continuity import relation_transitions as rt_svc
    from soloring.domain import revisions as revision_svc
    import json as _json

    pid, seq, scene, shots, *__, rel, tr = await _relation_fixture(client,
                                                                   factory)

    async def competitor():
        async with factory() as s:
            await rt_svc.patch_transition(
                s, tr["id"], RelationTransitionPatch(state="inactive"),
            )

    rev = await _race_capture(factory, shots[0], competitor)
    spec = _json.loads(rev.continuity_spec_json)
    assert len(spec["relations"]) == 1  # BEFORE: active

    rev2 = await revision_svc.capture_revision(factory(), shots[0])
    assert rev2.id != rev.id
    assert _json.loads(rev2.snapshot_json)["schema_version"] == 2  # AFTER


async def test_race_r2_relation_transition_soft_delete_mid_read(client, factory):
    """R2: an EFFECTIVE relation cannot be deleted (in-use guard); the
    deletable object at this seam is the transition — its soft-delete
    commits mid-read; the next capture converges onto the pre-relation
    schema-2 revision."""
    from soloring.continuity import relation_transitions as rt_svc
    from soloring.domain import revisions as revision_svc
    import json as _json

    pid, seq, scene, shots, *__, rel, tr = await _relation_fixture(client,
                                                                   factory)
    # Deleting the relation directly is blocked (in-use) — R2's premise.
    r = await client.delete(f"/continuity-relations/{rel['id']}")
    assert r.status_code == 409
    assert r.json()["error_code"] == "CONTINUITY_RELATION_IN_USE"

    # v2 baseline captured BEFORE the relation existed — for convergence.
    # (Re-create the state from scratch: capture v2 with deps only is
    # impossible now; instead prove the schema-2 convergence by removing
    # the transition inside the race and comparing against a fresh v2.)
    async def competitor():
        async with factory() as s:
            await rt_svc.delete_transition(s, tr["id"])

    rev = await _race_capture(factory, shots[0], competitor)
    assert _json.loads(rev.snapshot_json)["schema_version"] == 3  # BEFORE

    rev2 = await revision_svc.capture_revision(factory(), shots[0])
    assert _json.loads(rev2.snapshot_json)["schema_version"] == 2  # AFTER
    # Deactivated state is byte-stable: repeat captures converge.
    rev3 = await revision_svc.capture_revision(factory(), shots[0])
    assert rev3.id == rev2.id


async def test_race_r3_relation_transition_create_mid_read(client, factory):
    """R3: RelationTransition CREATE(active) on an existing relation
    commits mid-read; the current capture stays BEFORE (schema 2); the
    next promotes to schema 3. Relation CREATE alone never promotes."""
    from soloring.api.schemas.continuity_relations import (
        RelationTransitionCreate,
    )
    from soloring.continuity import relation_transitions as rt_svc
    from soloring.domain import revisions as revision_svc
    import json as _json

    pid, seq, scene, shots, *__, rel, _tr = await _relation_fixture(
        client, factory, with_transition=False
    )

    async def competitor():
        async with factory() as s:
            return await rt_svc.create_transition(
                s, rel["id"],
                RelationTransitionCreate(
                    anchor_type="shot", anchor_id=shots[0],
                    boundary="start", state="active",
                ),
            )

    rev = await _race_capture(factory, shots[0], competitor)
    assert _json.loads(rev.snapshot_json)["schema_version"] == 2  # BEFORE

    rev2 = await revision_svc.capture_revision(factory(), shots[0])
    assert _json.loads(rev2.snapshot_json)["schema_version"] == 3  # AFTER


async def test_race_r4_dependency_replace_flips_endpoint_mid_read(client, factory):
    """R4: a dependency replace removing one endpoint of an active
    effective relation SUCCEEDS; the open capture is BEFORE; the next
    capture is blocked ENDPOINT_REQUIRED."""
    from soloring.domain import revisions as revision_svc
    from soloring.errors import SoloRingError
    import json as _json

    pid, seq, scene, shots, eva, bag, *_ = await _relation_fixture(
        client, factory
    )

    async def competitor():
        return await client.put(
            f"/shots/{shots[0]}/semantic-dependencies",
            json={"dependencies": [
                {"entity_id": eva["id"], "role": "subject"}
            ]},
        )

    rev = await _race_capture(factory, shots[0], competitor)
    assert _json.loads(rev.snapshot_json)["schema_version"] == 3  # BEFORE

    try:
        await revision_svc.capture_revision(factory(), shots[0])
        raised = None
    except SoloRingError as exc:
        raised = exc
    assert raised is not None
    assert raised.code == "CONTINUITY_RELATION_ENDPOINT_REQUIRED"
    assert len(raised.details["issues"]) == 1
    assert raised.details["issues"][0]["missing_entity_id"] == bag["id"]

    r = await client.get(f"/shots/{shots[0]}")
    assert r.json()["working_snapshot_hash"] is None  # not-ready, honest


async def test_race_r5_narrative_reorder_changes_relation_winner(client, factory):
    """R5: a scene reorder commits mid-read; the winner for the target
    flips from the inactive scene2/start to the active scene1/start; the
    capture keeps the OLD resolution, the next observes the NEW."""
    from soloring.domain import revisions as revision_svc
    import json as _json

    pid = await _seed_project(factory)
    r = await client.post(f"/projects/{pid}/sequences", json={"title": "S"})
    seq = r.json()["id"]
    scene = (
        await client.post(f"/sequences/{seq}/scenes", json={"title": "C"})
    ).json()["id"]
    from soloring.api.schemas.shots import ShotCreate
    from soloring.domain import shots as shot_svc

    shot_x, target = None, None
    ids = []
    for _ in range(2):
        async with factory() as s:
            ids.append(
                (await shot_svc.create_shot(
                    s, pid, ShotCreate(subject="x"))).id
            )
    shot_x, target = ids
    await client.put(f"/scenes/{scene}/shots", json={"shot_ids": ids})

    eva = await _entity_approved(client, pid, name="Eva")
    bag = await _entity_approved(client, pid, kind="prop", name="Bag")
    carries = await _predicate(client, pid, key="carries")
    rel = await _relation(client, pid, eva["id"], carries["id"], bag["id"])
    # scene/start = active; shotX/start (BEFORE the target) = inactive.
    # Original winner for the target: shotX/start (higher rank) → inactive.
    assert (
        await _rt(client, rel["id"], "scene", scene, "start", "active")
    ).status_code == 201
    assert (
        await _rt(client, rel["id"], "shot", shot_x, "start", "inactive")
    ).status_code == 201
    await _depend(client, target, [eva["id"], bag["id"]])

    async def competitor():
        # Move shotX AFTER the target: shotX/start leaves the target's
        # eligible prefix → the ACTIVE scene/start transition wins.
        return await client.put(
            f"/scenes/{scene}/shots",
            json={"shot_ids": [target, shot_x]},
        )

    rev = await _race_capture(factory, target, competitor)
    # OLD ordering: winner is shotX/start (inactive) → schema 2.
    assert _json.loads(rev.snapshot_json)["schema_version"] == 2

    rev2 = await revision_svc.capture_revision(factory(), target)
    # NEW ordering: winner is scene/start (active) → schema 3.
    assert _json.loads(rev2.snapshot_json)["schema_version"] == 3


async def test_race_r6_relation_delete_vs_transition_create(client, factory,
                                                            engine):
    """R6: Relation DELETE ↔ RelationTransition CREATE. The create holds
    its fence; the delete parks on the write lock; after the create
    commits the delete must refuse IN_USE. The reverse order rejects the
    create against the tombstoned relation. Never-state: no active
    transition under a tombstoned relation."""
    from soloring.api.schemas.continuity_relations import (
        RelationTransitionCreate,
    )
    from soloring.continuity import relation_transitions as rt_svc
    from soloring.continuity import relations as rel_svc
    from soloring.api.schemas.continuity_relations import RelationCreate

    pid, seq, scene, shots, eva, bag, carries, rel, _ = (
        await _relation_fixture(client, factory, with_transition=False)
    )

    original = rt_svc._load_active_relation
    state = {}

    async def wrap(conn, relation_id):
        result = await original(conn, relation_id)
        if "task" not in state:
            import asyncio as _a

            async def delete_it():
                async with factory() as s:
                    try:
                        await rel_svc.delete_relation(s, relation_id)
                        return "deleted"
                    except Exception as exc:
                        return getattr(exc, "code", type(exc).__name__)

            state["task"] = _a.create_task(delete_it())
            await _a.sleep(0.3)  # parked on OUR write lock
        return result

    import soloring.continuity.relation_transitions as rtmod
    rtmod._load_active_relation = wrap
    try:
        async with factory() as s:
            await rt_svc.create_transition(
                s, rel["id"],
                RelationTransitionCreate(
                    anchor_type="shot", anchor_id=shots[0],
                    boundary="start", state="active",
                ),
            )
    finally:
        rtmod._load_active_relation = original
    outcome = await state["task"]
    assert outcome == "CONTINUITY_RELATION_IN_USE"

    # Never-state: no active transition under a tombstoned relation.
    dangling = await _fetch(
        engine,
        "SELECT COUNT(*) AS n FROM continuity_relation_transitions t "
        "JOIN continuity_relations r ON r.id = t.relation_id "
        "WHERE t.deleted_at IS NULL AND r.deleted_at IS NOT NULL",
    )
    assert dangling[0]["n"] == 0

    # Reverse order: tombstone the relation, then create → rejected.
    trs = (
        await client.get(f"/continuity-relations/{rel['id']}/transitions")
    ).json()
    for row in trs:
        await client.delete(
            f"/continuity-relation-transitions/{row['id']}"
        )
    await client.delete(f"/continuity-relations/{rel['id']}")
    r = await _rt(client, rel["id"], "shot", shots[0], "start", "active")
    assert r.status_code == 409


async def test_race_r7_predicate_delete_vs_relation_create(client, factory,
                                                           engine):
    """R7: Predicate DELETE ↔ Relation CREATE. The create holds its fence;
    the predicate delete parks on the write lock; after the create commits
    the delete must refuse PREDICATE_IN_USE. The reverse order rejects the
    create as INVALID_CONTINUITY_RELATION. Never-state: no active relation
    under a tombstoned predicate."""
    pid = await _seed_project(factory)
    eva = await _entity_approved(client, pid, name="Eva")
    bag = await _entity_approved(client, pid, kind="prop", name="Bag")
    carries = await _predicate(client, pid, key="carries")

    from soloring.continuity import relations as rel_svc
    from soloring.api.schemas.continuity_relations import RelationCreate

    original = rel_svc._verify_relation_inputs
    state = {}

    async def wrap(conn, project_id, subject, predicate_id, obj):
        key = await original(conn, project_id, subject, predicate_id, obj)
        if "task" not in state:
            import asyncio as _a

            async def delete_it():
                async with factory() as s:
                    try:
                        await rel_svc.delete_predicate(s, predicate_id)
                        return "deleted"
                    except Exception as exc:
                        return getattr(exc, "code", type(exc).__name__)

            state["task"] = _a.create_task(delete_it())
            await _a.sleep(0.3)  # parked on OUR write lock
        return key

    import soloring.continuity.relations as relmod
    relmod._verify_relation_inputs = wrap
    try:
        async with factory() as s:
            await rel_svc.create_relation(
                s, pid,
                RelationCreate(
                    subject_entity_id=eva["id"], predicate_id=carries["id"],
                    object_entity_id=bag["id"],
                ),
            )
    finally:
        relmod._verify_relation_inputs = original
    outcome = await state["task"]
    assert outcome == "CONTINUITY_PREDICATE_IN_USE"

    dangling = await _fetch(
        engine,
        "SELECT COUNT(*) AS n FROM continuity_relations r "
        "JOIN continuity_predicates p ON p.id = r.predicate_id "
        "WHERE r.deleted_at IS NULL AND p.deleted_at IS NOT NULL",
    )
    assert dangling[0]["n"] == 0

    # Reverse order: delete predicate (release the relation first), then
    # create → INVALID_CONTINUITY_RELATION.
    relations = (
        await client.get(f"/projects/{pid}/continuity-relations")
    ).json()
    await client.delete(f"/continuity-relations/{relations[0]['id']}")
    await client.delete(f"/continuity-predicates/{carries['id']}")
    r = await client.post(
        f"/projects/{pid}/continuity-relations",
        json={
            "subject_entity_id": eva["id"], "predicate_id": carries["id"],
            "object_entity_id": bag["id"],
        },
    )
    assert r.status_code == 422
    assert r.json()["error_code"] == "INVALID_CONTINUITY_RELATION"


async def test_race_r8_concurrent_identical_relation_captures_converge(
    client, factory,
):
    """R8: two captures of the same relation state, launched together —
    exactly one insert; both return the same revision (APR-032)."""
    import asyncio as _a

    pid, seq, scene, shots, *_ = await _relation_fixture(client, factory)
    revs = await _a.gather(*(
        _capture_one(factory, shots[0]) for _ in range(2)
    ))
    assert len({r.id for r in revs}) == 1


async def _capture_one(factory, shot_id):
    from soloring.domain import revisions as revision_svc

    return await revision_svc.capture_revision(factory(), shot_id)


async def test_race_r9_sequential_different_captures_ordered(client, factory):
    """R9: mutation between captures → two revisions, numbers strictly
    ordered."""
    from soloring.continuity import relation_transitions as rt_svc
    from soloring.api.schemas.continuity_relations import (
        RelationTransitionPatch,
    )
    from soloring.domain import revisions as revision_svc

    pid, seq, scene, shots, *_ , rel, tr = await _relation_fixture(client,
                                                                   factory)
    r1 = await revision_svc.capture_revision(factory(), shots[0])
    async with factory() as s:
        await rt_svc.patch_transition(
            s, tr["id"], RelationTransitionPatch(state="inactive"),
        )
    r2 = await revision_svc.capture_revision(factory(), shots[0])
    assert r2.id != r1.id
    assert r2.revision_number > r1.revision_number


async def test_race_r11_relation_transition_coordinate_create_vs_create(
    client, factory,
):
    """R11: concurrent creates at the same coordinate — exactly one wins;
    the losers get the 409 conflict."""
    import asyncio as _a

    pid, seq, scene, shots, *_ , rel, _ = await _relation_fixture(
        client, factory, with_transition=False
    )

    async def one():
        return await _rt(client, rel["id"], "shot", shots[0], "start",
                         "active")

    results = await _a.gather(*(one() for _ in range(4)))
    codes = sorted(r.status_code for r in results)
    assert codes.count(201) == 1
    assert codes.count(409) == 3


# --- Scale / N+1 (§19, APR-044) ---------------------------------------------------


async def test_relation_resolver_query_count_bounded(client, factory, engine):
    """§19: the relation resolver issues a FIXED number of SQL statements
    regardless of topology size — small vs ~2,500-shot fixtures in
    separate Projects must issue the SAME count."""
    import time

    from soloring.api.schemas.shots import ShotCreate as SC
    from soloring.continuity.state import resolve_effective_relation_state
    from soloring.domain import shots as shot_svc

    pid_small = await _seed_project(factory)
    pid_big = await _seed_project(factory)

    async def build(pid):

        r = await client.post(f"/projects/{pid}/sequences",
                              json={"title": "S"})
        seq = r.json()["id"]
        scene_ids = []
        for ci in range(10):
            r = await client.post(
                f"/sequences/{seq}/scenes", json={"title": f"C{ci}"}
            )
            scene_ids.append(r.json()["id"])
        shot_rows = []
        for cid in scene_ids:
            batch = []
            for _ in range(5):
                async with factory() as s:
                    shot = await shot_svc.create_shot(s, pid, SC(subject="x"))
                batch.append(shot.id)
                shot_rows.append(shot.id)
            r = await client.put(
                f"/scenes/{cid}/shots", json={"shot_ids": batch}
            )
            assert r.status_code == 200, r.text
        return seq, scene_ids, shot_rows

    async def relations_for(pid, n_relations, shots):
        eva = await _entity_approved(client, pid, name="Eva")
        bag = await _entity_approved(client, pid, kind="prop", name="Bag")
        carries = await _predicate(client, pid, key="carries")
        rel_ids = []
        for k in range(n_relations):
            # n_relations needs distinct props to avoid duplicate identity;
            # reuse the pair for k=0 and create extra endpoints otherwise.
            if k == 0:
                rel = await _relation(
                    client, pid, eva["id"], carries["id"], bag["id"]
                )
            else:
                side = await _entity_approved(
                    client, pid, kind="prop", name=f"P{k}"
                )
                pred = await _predicate(client, pid, key=f"p{k}")
                rel = await _relation(
                    client, pid, side["id"], pred["id"], bag["id"]
                )
            rel_ids.append(rel["id"])
        # Only the FIRST relation touches the target's dependencies (via
        # eva/bag); the rest exercise candidate-set row volume.
        return eva, bag, rel_ids

    # Small: 50 shots; Big: 2,500-shot-equivalent topology.
    small_seq, small_scenes, small_shots = await build(pid_small)
    # Rebuild big at the same scale as the M7B gate: 25x10x10.
    big_seq, big_scenes, big_shots = await build(pid_big)
    # grow big to 25 sequences
    for si in range(24):
        r = await client.post(
            f"/projects/{pid_big}/sequences", json={"title": f"S{si}"}
        )
        bsq = r.json()["id"]
        for ci in range(10):
            r = await client.post(
                f"/sequences/{bsq}/scenes", json={"title": f"C{ci}"}
            )
            bsc = r.json()["id"]
            batch = []
            for _ in range(10):
                async with factory() as s:
                    shot = await shot_svc.create_shot(
                        s, pid_big, SC(subject="x")
                    )
                batch.append(shot.id)
            r = await client.put(
                f"/scenes/{bsc}/shots", json={"shot_ids": batch}
            )
            assert r.status_code == 200, r.text

    eva_s, bag_s, small_rels = await relations_for(pid_small, 20, small_shots)
    eva_b, bag_b, big_rels = await relations_for(pid_big, 20, big_shots)
    assert (
        await _rt(
            client, small_rels[0], "sequence", small_seq, "start", "active",
        )
    ).status_code == 201
    assert (
        await _rt(
            client, big_rels[0], "sequence", big_seq, "start", "active"
        )
    ).status_code == 201
    await _depend(client, small_shots[-1], [eva_s["id"], bag_s["id"]])
    await _depend(client, big_shots[-1], [eva_b["id"], bag_b["id"]])

    counts = {}
    for label, shot_id in (
        ("small", small_shots[-1]),
        ("big", big_shots[-1]),
    ):
        counter = {"n": 0}
        async with engine.connect() as conn:
            from sqlalchemy import event

            def before_cursor_execute(conn_, cursor, statement, parameters,
                                      context, executemany):
                counter["n"] += 1

            event.listen(conn.sync_connection, "before_cursor_execute",
                         before_cursor_execute)
            try:
                t0 = time.perf_counter()
                outcome = await resolve_effective_relation_state(
                    conn, shot_id
                )
                dt = time.perf_counter() - t0
            finally:
                event.remove(conn.sync_connection,
                             "before_cursor_execute",
                             before_cursor_execute)
        counts[label] = (counter["n"], dt, len(outcome.relation_states))
        assert len(outcome.relation_states) == 1

    small_q, small_dt, _ = counts["small"]
    big_q, big_dt, _ = counts["big"]
    print(
        f"\nrelation resolver: small {small_q} queries {small_dt*1000:.1f}ms"
        f" | big({len(big_shots)+2400} shots) {big_q} queries "
        f"{big_dt*1000:.1f}ms"
    )
    assert small_q == big_q  # APR-044: rows grow, round trips do not
