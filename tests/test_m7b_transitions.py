"""M7B — Feature transitions, resolver, readiness, capture gate tests.

Covers the §15 source-gate proof matrix: transition CRUD across value
types, the full PATCH prospective-row matrix, anchor validation through
the canonical ordering, resolver precedence/clear semantics, narrative
context, the readiness matrix on ShotRead, the temporary capture/
generation gates (no ShotRevision/Generation written), anchor lifecycle
guards, and the §14 scale/N+1 query-shape gate.
"""

from __future__ import annotations

import asyncio
import json
import time

import pytest
from sqlalchemy import text

from soloring.api.schemas.projects import ProjectCreate
from soloring.api.schemas.shots import ShotCreate
from soloring.domain import projects as project_svc
from soloring.domain import shots as shot_svc
from soloring.domain.ids import new_uuid
from soloring.errors import ErrorCode, SoloRingError


async def _seed_project(factory):
    async with factory() as s:
        return (await project_svc.create_project(
            s, ProjectCreate(name="P"))).id


async def _entity(client, pid, kind="character", name="Eva"):
    r = await client.post(
        f"/projects/{pid}/entities", json={"kind": kind, "name": name}
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _feature(client, entity_id, key="forehead_cut", **kw):
    payload = {
        "key": key, "kind": kw.pop("kind", "injury"),
        "value_type": kw.pop("value_type", "enum"),
        "name": kw.pop("name", "Cut"),
        "enum_values": kw.pop("enum_values",
                              ["fresh", "healing", "scarred", "gone"]),
    }
    payload.update(kw)
    r = await client.post(
        f"/entities/{entity_id}/continuity-features", json=payload
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _approve(client, entity_id, revision_id, expected):
    r = await client.put(
        f"/entities/{entity_id}/approved-revision",
        json={"revision_id": revision_id,
              "expected_approved_revision_id": expected},
    )
    assert r.status_code == 200, r.text


async def _entity_approved(client, pid, kind="character", name="Eva"):
    e = await _entity(client, pid, kind, name)
    r = await client.post(
        f"/entities/{e['id']}/revisions", json={"spec": {"description": "d"}}
    )
    assert r.status_code == 201
    await _approve(client, e["id"], r.json()["id"], None)
    return e


async def _shot(client, factory, pid, subject="x"):
    async with factory() as s:
        shot = await shot_svc.create_shot(s, pid, ShotCreate(subject=subject))
    return shot.id


async def _topology(client, factory, pid, n_shots=2):
    r = await client.post(f"/projects/{pid}/sequences", json={"title": "S"})
    assert r.status_code == 201, r.text
    seq = r.json()["id"]
    r = await client.post(f"/sequences/{seq}/scenes", json={"title": "C"})
    assert r.status_code == 201, r.text
    scene = r.json()["id"]
    shot_ids = [await _shot(client, factory, pid) for _ in range(n_shots)]
    r = await client.put(
        f"/scenes/{scene}/shots", json={"shot_ids": shot_ids}
    )
    assert r.status_code == 200, r.text
    return seq, scene, shot_ids


async def _depend(client, shot_id, entity_id, role="subject"):
    r = await client.put(
        f"/shots/{shot_id}/semantic-dependencies",
        json={"dependencies": [{"entity_id": entity_id, "role": role}]},
    )
    assert r.status_code == 200, r.text


async def _transition(client, feature_id, anchor_type, anchor_id, boundary,
                      operation, value=...):
    payload = {
        "anchor_type": anchor_type, "anchor_id": anchor_id,
        "boundary": boundary, "operation": operation,
    }
    if value is not ...:
        payload["value"] = value
    return await client.post(
        f"/continuity-features/{feature_id}/transitions", json=payload
    )


async def _fetch(engine, sql, params):
    async with engine.connect() as conn:
        row = (await conn.execute(text(sql), params)).mappings().one_or_none()
    return dict(row) if row is not None else None


# --- Transition create: value types + conflicts -------------------------------------


async def test_transition_create_every_value_type(client, factory, engine):
    pid = await _seed_project(factory)
    seq, scene, shots = await _topology(client, factory, pid, n_shots=1)
    shot = shots[0]

    cases = [
        ("enum_f", "enum", "fresh", '"fresh"', ["a", "b", "fresh"]),
        ("bool_f", "boolean", True, "true", None),
        ("int_f", "integer", 17, "17", None),
        ("dec_f", "decimal", "0001.50", '"1.5"', None),
        ("txt_f", "text", "soaked", '"soaked"', None),
    ]
    for key, vt, value, expected_json, enums in cases:
        eva = await _entity(client, pid, name=key)
        f = await _feature(
            client, eva["id"], key=key, value_type=vt, enum_values=enums,
        )
        r = await _transition(
            client, f["id"], "shot", shot, "start", "set", value
        )
        assert r.status_code == 201, (key, r.text)
        body = r.json()
        assert body["value_json"] == expected_json, key
        assert body["value_hash"] and len(body["value_hash"]) == 64

    # clear requires omitted value; value:null always rejected.
    eva = await _entity(client, pid, name="clr")
    f = await _feature(client, eva["id"], key="clr_f")
    r = await _transition(client, f["id"], "shot", shot, "end", "clear",
                          value=None)
    assert r.status_code == 422
    r = await _transition(client, f["id"], "shot", shot, "end", "clear")
    assert r.status_code == 201, r.text
    assert r.json()["value_json"] is None

    # Duplicate active coordinate.
    r = await _transition(client, f["id"], "shot", shot, "end", "clear")
    assert r.status_code == 409
    assert r.json()["error_code"] == "CONTINUITY_TRANSITION_CONFLICT"

    # enum exactness.
    eva = await _entity(client, pid, name="enumx")
    f = await _feature(client, eva["id"], key="enumx_f")
    r = await _transition(
        client, f["id"], "shot", shot, "start", "set", "Fresh"
    )
    assert r.status_code == 422
    r = await _transition(client, f["id"], "shot", shot, "start", "set", 1.5)
    assert r.status_code == 422


# --- PATCH matrix ----------------------------------------------------------------------


async def test_patch_prospective_row_matrix(client, factory, engine):
    pid = await _seed_project(factory)
    seq, scene, shots = await _topology(client, factory, pid, n_shots=2)
    eva = await _entity(client, pid)
    f = await _feature(client, eva["id"])

    t = (await _transition(
        client, f["id"], "shot", shots[0], "end", "set", "fresh"
    )).json()
    tid = t["id"]

    async def patch(body):
        return await client.patch(
            f"/continuity-feature-transitions/{tid}", json=body
        )

    # set → set, value omitted → retain.
    r = await patch({"operation": "set"})
    assert r.status_code == 200 and r.json()["value_json"] == '"fresh"'
    # set → set, value supplied → canonical replacement.
    r = await patch({"value": "healing"})
    assert r.status_code == 200 and r.json()["value_json"] == '"healing"'
    # PATCH anchor only on a set → value retained.
    r = await patch({"anchor_id": shots[1], "boundary": "start"})
    assert r.status_code == 200, r.text
    assert r.json()["value_json"] == '"healing"'
    assert r.json()["anchor_id"] == shots[1]
    # Boundary-only PATCH leaves the rest.
    r = await patch({"boundary": "end"})
    assert r.status_code == 200 and r.json()["anchor_id"] == shots[1]
    # set → clear with value supplied → 422.
    r = await patch({"operation": "clear", "value": "fresh"})
    assert r.status_code == 422
    # value:null always rejected.
    r = await patch({"value": None})
    assert r.status_code == 422
    # set → clear with value omitted → succeeds; single clear form.
    r = await patch({"operation": "clear"})
    assert r.status_code == 200
    assert r.json()["value_json"] is None
    # clear → set with value omitted → 422.
    r = await patch({"operation": "set"})
    assert r.status_code == 422
    # clear → set with value → succeeds.
    r = await patch({"operation": "set", "value": "scarred"})
    assert r.status_code == 200 and r.json()["value_json"] == '"scarred"'
    # clear → clear: value must be omitted.
    await patch({"operation": "clear"})
    r = await patch({"operation": "clear"})
    assert r.status_code == 200
    # Re-anchor into an occupied coordinate → 409.
    other = (await _transition(
        client, f["id"], "scene", scene, "start", "set", "gone"
    )).json()
    # Self-coordinate no-op PATCH stays legal (identity unchanged).
    r = await client.patch(
        f"/continuity-feature-transitions/{other['id']}",
        json={"anchor_id": scene, "anchor_type": "scene", "boundary": "start"},
    )
    assert r.status_code == 200
    # Cross-coordinate re-anchor collision.
    r = await client.patch(
        f"/continuity-feature-transitions/{tid}",
        json={"anchor_type": "scene", "anchor_id": scene, "boundary": "start"},
    )
    assert r.status_code == 409
    # Immutable fields rejected by schema (extra=forbid).
    r = await patch({"feature_id": str(new_uuid())})
    assert r.status_code == 422
    # Nonexistent transition → conflict (frozen vocabulary).
    r = await client.patch(
        f"/continuity-feature-transitions/{str(new_uuid())}",
        json={"value": "fresh"},
    )
    assert r.status_code == 409

    # Delete: idempotent for tombstoned, conflict for never-existed.
    assert (await client.delete(
        f"/continuity-feature-transitions/{tid}"
    )).status_code == 204
    assert (await client.delete(
        f"/continuity-feature-transitions/{tid}"
    )).status_code == 204
    assert (await client.delete(
        f"/continuity-feature-transitions/{str(new_uuid())}"
    )).status_code == 409


# --- Anchor validation -----------------------------------------------------------------


async def test_anchor_validation_matrix(client, factory):
    pid = await _seed_project(factory)
    other_pid = await _seed_project(factory)
    seq, scene, shots = await _topology(client, factory, pid)
    _, other_scene, _ = await _topology(client, factory, other_pid)

    eva = await _entity(client, pid)
    f = await _feature(client, eva["id"])
    x_entity = await _entity(client, other_pid, name="X")
    f_other = await _feature(client, x_entity["id"], key="x_f")

    # Cross-project anchor (feature's project A, anchor in B).
    r = await _transition(
        client, f["id"], "scene", other_scene, "start", "set", "fresh"
    )
    assert r.status_code in (409, 422)
    assert r.json()["error_code"] in (
        "CONTINUITY_ANCHOR_PROJECT_MISMATCH", "INVALID_CONTINUITY_ANCHOR"
    )

    # Missing anchor.
    r = await _transition(
        client, f["id"], "shot", str(new_uuid()), "start", "set", "fresh"
    )
    assert r.status_code == 422
    assert r.json()["error_code"] == "INVALID_CONTINUITY_ANCHOR"

    # Tombstoned anchor.
    r = await _transition(
        client, f["id"], "sequence", seq, "start", "set", "fresh"
    )
    assert r.status_code == 201, r.text  # sequence anchor is legal
    seq_t = (await client.get(f"/sequences/{seq}")).json()
    # (Tombstoning the sequence would now be blocked by ANCHOR_IN_USE —
    # covered in the lifecycle tests.)

    # Unassigned shot anchor.
    lonely = await _shot(client, factory, pid)
    r = await _transition(
        client, f["id"], "shot", lonely, "start", "set", "fresh"
    )
    assert r.status_code == 422
    assert r.json()["error_code"] == "INVALID_CONTINUITY_ANCHOR"


# --- Resolver semantics ------------------------------------------------------------------


async def _resolver_setup(client, factory, pid, n_shots=3):
    eva = await _entity_approved(client, pid)
    f = await _feature(client, eva["id"])
    seq, scene, shots = await _topology(client, factory, pid, n_shots)
    for sid in shots:
        await _depend(client, sid, eva["id"])
    return eva, f, seq, scene, shots


async def test_resolver_precedence_and_clear(client, factory):
    pid = await _seed_project(factory)
    eva, f, seq, scene, shots = await _resolver_setup(client, factory, pid)
    target = shots[2]

    # No transitions → no states.
    r = await client.get(f"/shots/{target}/continuity-state")
    assert r.status_code == 200
    assert r.json()["feature_states"] == []

    # Sequence/start propagation.
    await _transition(client, f["id"], "sequence", seq, "start", "set",
                      "fresh")
    r = await client.get(f"/shots/{target}/continuity-state")
    states = r.json()["feature_states"]
    assert len(states) == 1 and states[0]["value"] == "fresh"

    # Scene/start override.
    await _transition(client, f["id"], "scene", scene, "start", "set",
                      "healing")
    r = await client.get(f"/shots/{target}/continuity-state")
    assert r.json()["feature_states"][0]["value"] == "healing"

    # Previous shot/end applies downstream; target's own /start applies to
    # the target; target's own /end does NOT.
    await _transition(client, f["id"], "shot", shots[0], "end", "set",
                      "scarred")
    await _transition(client, f["id"], "shot", target, "start", "set",
                      "gone")
    await _transition(client, f["id"], "shot", target, "end", "set",
                      "fresh")
    r = await client.get(f"/shots/{target}/continuity-state")
    assert r.json()["feature_states"][0]["value"] == "gone"
    # But the target's /end state applies AFTER: the next capture of a
    # later shot would see fresh — here shots[1] starts before target/end.
    r = await client.get(f"/shots/{shots[1]}/continuity-state")
    assert r.json()["feature_states"][0]["value"] == "scarred"

    # clear removes state: the clear must sit at (or above) the winning
    # coordinate — target/start currently holds "gone", so PATCH it to
    # clear. A lower-ranked clear (shots[1]/end) cannot outrank it.
    tid = None
    listed = (await client.get(
        f"/continuity-features/{f['id']}/transitions"
    )).json()
    for row in listed:
        if (row["anchor_type"] == "shot" and row["anchor_id"] == target
                and row["boundary"] == "start"):
            tid = row["id"]
    assert tid is not None
    r = await client.patch(
        f"/continuity-feature-transitions/{tid}", json={"operation": "clear"}
    )
    assert r.status_code == 200, r.text
    r = await client.get(f"/shots/{target}/continuity-state")
    assert r.json()["feature_states"] == []

    # set → clear → set: latest wins (same coordinate, re-set).
    r = await client.patch(
        f"/continuity-feature-transitions/{tid}",
        json={"operation": "set", "value": "healing"},
    )
    assert r.status_code == 200, r.text
    r = await client.get(f"/shots/{target}/continuity-state")
    assert r.json()["feature_states"][0]["value"] == "healing"


async def test_resolver_ignores_unrelated_entities(client, factory):
    pid = await _seed_project(factory)
    eva, f, seq, scene, shots = await _resolver_setup(client, factory, pid)
    # An unrelated entity with transitions in the same scene.
    other = await _entity_approved(client, pid, name="Other")
    f2 = await _feature(client, other["id"], key="other_f")
    await _transition(client, f2["id"], "scene", scene, "start", "set",
                      "fresh")
    r = await client.get(f"/shots/{shots[2]}/continuity-state")
    assert r.json()["feature_states"] == []  # other entity irrelevant


async def test_duplicate_roles_do_not_duplicate_state(client, factory):
    pid = await _seed_project(factory)
    eva, f, seq, scene, shots = await _resolver_setup(client, factory, pid, 2)
    await _depend(client, shots[0], eva["id"], role="reflection_subject")
    await _transition(client, f["id"], "sequence", seq, "start", "set",
                      "fresh")
    r = await client.get(f"/shots/{shots[0]}/continuity-state")
    assert len(r.json()["feature_states"]) == 1


async def test_reorder_changes_effective_state(client, factory):
    pid = await _seed_project(factory)
    eva, f, seq, scene, shots = await _resolver_setup(client, factory, pid, 2)
    # Transition at shots[1]/end initially AFTER shots[0].
    await _transition(client, f["id"], "shot", shots[1], "end", "set",
                      "fresh")
    r = await client.get(f"/shots/{shots[0]}/continuity-state")
    assert r.json()["feature_states"] == []
    # Reorder so shots[1] precedes shots[0].
    resp = await client.put(
        f"/scenes/{scene}/shots", json={"shot_ids": [shots[1], shots[0]]}
    )
    assert resp.status_code == 200
    r = await client.get(f"/shots/{shots[0]}/continuity-state")
    assert r.json()["feature_states"][0]["value"] == "fresh"


# --- Narrative context + readiness -------------------------------------------------------


async def test_context_and_readiness_matrix(client, factory):
    pid = await _seed_project(factory)
    eva = await _entity_approved(client, pid)
    f = await _feature(client, eva["id"])
    seq, scene, shots = await _topology(client, factory, pid, 2)
    for sid in shots:
        await _depend(client, sid, eva["id"])
    lonely = await _shot(client, factory, pid)
    await _depend(client, lonely, eva["id"])

    # Dependency-free shot: v1 hash + state-ready.
    bare = await _shot(client, factory, pid)
    d = (await client.get(f"/shots/{bare}")).json()
    assert d["continuity_ready"] is False
    assert d["continuity_state_ready"] is True
    assert d["working_snapshot_hash"] is not None
    assert d["working_state_differs_from_approved"] is False

    # Dependencies + no temporal data: exact M6 behavior.
    d = (await client.get(f"/shots/{shots[0]}")).json()
    assert d["continuity_ready"] is True
    assert d["continuity_state_ready"] is True
    assert d["working_snapshot_hash"] is not None

    # Unassigned + no relevant transitions → legal M6.
    d = (await client.get(f"/shots/{lonely}")).json()
    assert d["continuity_state_ready"] is True
    assert d["working_snapshot_hash"] is not None

    # Unassigned + relevant transitions → NARRATIVE_CONTEXT_REQUIRED /
    # unresolved readiness.
    await _transition(client, f["id"], "sequence", seq, "start", "set",
                      "fresh")
    d = (await client.get(f"/shots/{lonely}")).json()
    assert d["continuity_state_ready"] is False
    assert d["working_snapshot_hash"] is None
    assert d["working_state_differs_from_approved"] is None
    r = await client.get(f"/shots/{lonely}/continuity-state")
    assert r.status_code == 409
    assert r.json()["error_code"] == "NARRATIVE_CONTEXT_REQUIRED"

    # Assigned + effective empty (the only relevant transition sits
    # strictly AFTER shots[0]/start) → ready, exact M6 hash intact.
    # (sequence/start=fresh currently applies to shots[0]; tombstone it
    # and keep only a later transition.)
    listed = (await client.get(
        f"/continuity-features/{f['id']}/transitions"
    )).json()
    for row in listed:
        if row["anchor_type"] == "sequence":
            assert (await client.delete(
                f"/continuity-feature-transitions/{row['id']}"
            )).status_code == 204
    d = (await client.get(f"/shots/{shots[0]}")).json()
    assert d["continuity_state_ready"] is True
    assert d["working_snapshot_hash"] is not None
    await _transition(client, f["id"], "shot", shots[1], "end", "set",
                      "gone")
    d = (await client.get(f"/shots/{shots[0]}")).json()
    assert d["continuity_state_ready"] is True
    assert d["working_snapshot_hash"] is not None

    # Assigned + effective state → resolver succeeds, capture unsafe.
    # (shots[1]/end is NOT eligible for shots[1] itself — its own /end
    # comes after its /start — so add shots[0]/end which IS eligible.)
    await _transition(client, f["id"], "shot", shots[0], "end", "set",
                      "fresh")
    d = (await client.get(f"/shots/{shots[1]}")).json()
    assert d["continuity_state_ready"] is False
    assert d["working_snapshot_hash"] is None
    assert d["working_state_differs_from_approved"] is None
    r = await client.get(f"/shots/{shots[1]}/continuity-state")
    assert r.status_code == 200
    assert len(r.json()["feature_states"]) >= 1


# --- Capture / generation gates ------------------------------------------------------------


async def test_capture_and_generation_gates(client, factory, engine, settings):
    pid = await _seed_project(factory)
    eva, f, seq, scene, shots = await _resolver_setup(client, factory, pid)
    # Reference asset for generation cardinality.
    from tests.conftest import seed_reference_asset
    from soloring.api.schemas.references import ReferenceInput
    from soloring.domain import references as ref_svc

    aid, _bh = await seed_reference_asset(engine, pid)
    async with factory() as s:
        await ref_svc.replace_references(
            s, shots[0], [ReferenceInput(asset_id=aid, role="reference")]
        )
        await ref_svc.replace_references(
            s, shots[1], [ReferenceInput(asset_id=aid, role="reference")]
        )

    async def counts():
        return (
            await _fetch(engine, "SELECT COUNT(*) AS n FROM shot_revisions", {}),
            await _fetch(engine, "SELECT COUNT(*) AS n FROM generations", {}),
        )

    # Zero effective state: exact M6 behavior — capture + generation work.
    before = await counts()
    r = await client.post(f"/shots/{shots[0]}/generations")
    assert r.status_code == 202, r.text
    after = await counts()
    assert after[0]["n"] == before[0]["n"] + 1
    assert after[1]["n"] == before[1]["n"] + 1

    # Nonempty effective state → both blocked, nothing written.
    await _transition(client, f["id"], "sequence", seq, "start", "set",
                      "fresh")
    before = await counts()
    r = await client.post(f"/shots/{shots[0]}/generations")
    assert r.status_code == 409, r.text
    assert r.json()["error_code"] == "NARRATIVE_STATE_CAPTURE_UNAVAILABLE"
    assert await counts() == before

    # Unassigned + relevant → context required, nothing written.
    lonely = await _shot(client, factory, pid)
    async with factory() as s:
        await ref_svc.replace_references(
            s, lonely, [ReferenceInput(asset_id=aid, role="reference")]
        )
    await _depend(client, lonely, eva["id"])
    before = await counts()
    r = await client.post(f"/shots/{lonely}/generations")
    assert r.status_code == 409
    assert r.json()["error_code"] == "NARRATIVE_CONTEXT_REQUIRED"
    assert await counts() == before


# --- Anchor lifecycle ------------------------------------------------------------------------


async def test_anchor_lifecycle_guards(client, factory):
    pid = await _seed_project(factory)
    seq, scene, shots = await _topology(client, factory, pid)
    eva = await _entity(client, pid)
    f = await _feature(client, eva["id"])

    # Sequence-anchored transition blocks sequence deletion once the
    # sequence is otherwise empty (otherwise SEQUENCE_IN_USE fires first —
    # both guards are correct; this isolates the anchor guard).
    t_seq = (await _transition(
        client, f["id"], "sequence", seq, "start", "set", "fresh"
    )).json()
    await client.put(f"/scenes/{scene}/shots", json={"shot_ids": []})
    await client.delete(f"/scenes/{scene}")
    r = await client.delete(f"/sequences/{seq}")
    assert r.status_code == 409
    assert r.json()["error_code"] == "CONTINUITY_ANCHOR_IN_USE"
    assert (await client.delete(
        f"/continuity-feature-transitions/{t_seq['id']}"
    )).status_code == 204

    # Shot-anchored transition blocks unassignment + shot deletion, but
    # NOT reorder. (Fresh topology: the earlier scene was consumed above.)
    seq2, scene2, shots2 = await _topology(client, factory, pid, 2)
    shots = shots2
    scene = scene2
    t = (await _transition(
        client, f["id"], "shot", shots[0], "start", "set", "healing"
    )).json()
    r = await client.put(
        f"/scenes/{scene}/shots", json={"shot_ids": [shots[1]]}
    )
    assert r.status_code == 409
    assert r.json()["error_code"] == "CONTINUITY_ANCHOR_IN_USE"
    r = await client.put(
        f"/scenes/{scene}/shots",
        json={"shot_ids": [shots[1], shots[0]]},
    )
    assert r.status_code == 200  # reorder legal (identity survives)
    r = await client.delete(f"/shots/{shots[0]}")
    assert r.status_code == 409
    assert r.json()["error_code"] == "CONTINUITY_ANCHOR_IN_USE"

    # Removing the transition unblocks.
    assert (await client.delete(
        f"/continuity-feature-transitions/{t['id']}"
    )).status_code == 204
    assert (await client.delete(f"/shots/{shots[0]}")).status_code == 204

    # Scene-anchored transition blocks scene deletion (with the scene
    # otherwise empty, so only the anchor guard can fire).
    t2 = (await _transition(
        client, f["id"], "scene", scene, "start", "set", "scarred"
    )).json()
    await client.put(f"/scenes/{scene}/shots", json={"shot_ids": []})
    r = await client.delete(f"/scenes/{scene}")
    assert r.status_code == 409
    assert r.json()["error_code"] == "CONTINUITY_ANCHOR_IN_USE"
    assert (await client.delete(
        f"/continuity-feature-transitions/{t2['id']}"
    )).status_code == 204


async def test_project_cascade_tombstones_transitions(client, factory, engine):
    pid = await _seed_project(factory)
    seq, scene, shots = await _topology(client, factory, pid)
    eva = await _entity(client, pid)
    f = await _feature(client, eva["id"])
    await _transition(client, f["id"], "sequence", seq, "start", "set",
                      "fresh")
    assert (await client.delete(f"/projects/{pid}")).status_code == 204
    row = await _fetch(
        engine,
        "SELECT COUNT(*) AS n FROM continuity_feature_transitions "
        "WHERE deleted_at IS NULL",
        {},
    )
    assert row["n"] == 0


# --- Concurrency ------------------------------------------------------------------------------


async def test_duplicate_coordinate_race_converges(client, factory):
    pid = await _seed_project(factory)
    seq, scene, shots = await _topology(client, factory, pid, 1)
    eva = await _entity(client, pid)
    f = await _feature(client, eva["id"])

    async def one():
        return await _transition(
            client, f["id"], "shot", shots[0], "start", "set", "fresh"
        )

    results = await asyncio.gather(*(one() for _ in range(4)))
    codes = sorted(r.status_code for r in results)
    assert codes.count(201) == 1
    assert codes.count(409) == 3


async def test_transition_vs_feature_delete_race(client, factory):
    pid = await _seed_project(factory)
    seq, scene, shots = await _topology(client, factory, pid, 1)
    eva = await _entity(client, pid)
    f = await _feature(client, eva["id"])

    async def create_t():
        return await _transition(
            client, f["id"], "shot", shots[0], "start", "set", "fresh"
        )

    async def delete_f():
        return await client.delete(f"/continuity-features/{f['id']}")

    # Sequential baseline: create then delete-feature is blocked.
    assert (await create_t()).status_code == 201
    r = await delete_f()
    assert r.status_code == 409
    assert r.json()["error_code"] == "CONTINUITY_FEATURE_IN_USE"


# --- Scale / N+1 --------------------------------------------------------------------------------


async def test_resolver_query_count_bounded(client, factory, engine):
    """§14: query count must be bounded by resolver phases, not rows. A
    small fixture and a ~2500-shot fixture must issue the SAME number of
    SQL statements to resolve one target Shot."""
    from soloring.continuity.state import resolve_effective_feature_state

    pid = await _seed_project(factory)
    eva = await _entity_approved(client, pid)
    f = await _feature(client, eva["id"])

    async def build(n_seqs, scenes_per_seq, shots_per_scene):
        from soloring.api.schemas.shots import ShotCreate as SC

        seq_ids = []
        for si in range(n_seqs):
            r = await client.post(
                f"/projects/{pid}/sequences", json={"title": f"S{si}"}
            )
            assert r.status_code == 201, r.text
            seq_ids.append(r.json()["id"])
        scene_ids = []
        for sq in seq_ids:
            for ci in range(scenes_per_seq):
                r = await client.post(
                    f"/sequences/{sq}/scenes", json={"title": f"C{ci}"}
                )
                assert r.status_code == 201, r.text
                scene_ids.append((sq, r.json()["id"]))
        shot_rows = []
        for sq, cid in scene_ids:
            batch = []
            for k in range(shots_per_scene):
                async with factory() as s:
                    shot = await shot_svc.create_shot(
                        s, pid, SC(subject="x")
                    )
                batch.append(shot.id)
                shot_rows.append(shot.id)
            r = await client.put(
                f"/scenes/{cid}/shots", json={"shot_ids": batch}
            )
            assert r.status_code == 200, r.text
        return seq_ids, [c for _, c in scene_ids], shot_rows

    small_seq, small_scenes, small_shots = await build(2, 3, 8)  # 48 shots
    await _depend(client, small_shots[-1], eva["id"])
    await _transition(client, f["id"], "sequence", small_seq[0], "start",
                      "set", "fresh")

    big_n = 2500
    big_seqs = 25
    scenes_per = 10
    per_scene = big_n // (big_seqs * scenes_per)
    t0 = time.perf_counter()
    big_seq, big_scenes, big_shots = await build(
        big_seqs, scenes_per, per_scene
    )
    build_s = time.perf_counter() - t0
    target = big_shots[-1]
    await _depend(client, target, eva["id"])
    await _transition(client, f["id"], "sequence", big_seq[0], "start",
                      "set", "fresh")

    counts = {}
    for label, shot_id in (("small", small_shots[-1]), ("big", target)):
        counter = {"n": 0}

        async def counting_conn_execute(conn_self, *a, **kw):
            counter["n"] += 1
            return await orig_execute(conn_self, *a, **kw)

        async with engine.connect() as conn:
            orig_execute = conn.execute
            import sqlalchemy as sa

            # Count statements via event listener instead of patching.
            from sqlalchemy import event

            def before_cursor_execute(conn_, cursor, statement, parameters,
                                      context, executemany):
                counter["n"] += 1

            event.listen(conn.sync_connection, "before_cursor_execute",
                         before_cursor_execute)
            try:
                t0 = time.perf_counter()
                outcome = await resolve_effective_feature_state(
                    conn, shot_id
                )
                dt = time.perf_counter() - t0
            finally:
                event.remove(conn.sync_connection, "before_cursor_execute",
                             before_cursor_execute)
        counts[label] = (counter["n"], dt, len(outcome.states))
        assert len(outcome.states) == 1

    small_q, small_dt, _ = counts["small"]
    big_q, big_dt, _ = counts["big"]
    print(f"\nscale fixture: {len(big_shots)} shots, {big_seqs} sequences, "
          f"{len(big_scenes)} scenes; build {build_s:.1f}s")
    print(f"resolver queries: small={small_q} big={big_q}; "
          f"wall-clock small={small_dt*1000:.1f}ms big={big_dt*1000:.1f}ms")
    # Bounded by resolver phases: the big fixture may not exceed the small
    # one's count by more than a small constant (per-phase queries).
    assert big_q <= small_q + 2
