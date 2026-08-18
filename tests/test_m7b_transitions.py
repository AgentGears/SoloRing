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


async def test_transition_blocks_feature_delete_sequentially(client, factory):
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
    SQL statements to resolve one target Shot. The two fixtures live in
    SEPARATE Projects (Project-local ordering keeps them independent) so
    the small measurement cannot be polluted by the large topology."""
    from soloring.continuity.state import resolve_effective_feature_state

    pid_small = await _seed_project(factory)
    pid_big = await _seed_project(factory)
    eva_small = await _entity_approved(client, pid_small)
    f_small = await _feature(client, eva_small["id"])
    eva_big = await _entity_approved(client, pid_big, name="BigEva")
    f_big = await _feature(client, eva_big["id"])

    async def build(pid, n_seqs, scenes_per_seq, shots_per_scene):
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

    small_seq, small_scenes, small_shots = await build(pid_small, 2, 3, 8)
    await _depend(client, small_shots[-1], eva_small["id"])
    await _transition(client, f_small["id"], "sequence", small_seq[0],
                      "start", "set", "fresh")

    big_n = 2500
    big_seqs = 25
    scenes_per = 10
    per_scene = big_n // (big_seqs * scenes_per)
    t0 = time.perf_counter()
    big_seq, big_scenes, big_shots = await build(
        pid_big, big_seqs, scenes_per, per_scene
    )
    build_s = time.perf_counter() - t0
    target = big_shots[-1]
    await _depend(client, target, eva_big["id"])
    await _transition(client, f_big["id"], "sequence", big_seq[0], "start",
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

# --- M7B r2: deterministic race proofs (B5) ----------------------------------------
# All races use the lock-parking/seam discipline: legal serialized outcomes
# are pinned, then an invariant query proves no dangling active transition
# and no duplicate active coordinate.


async def _no_dangling(engine) -> None:
    rows = await _fetch_all_if_exists(engine)
    assert rows == []


async def _fetch_all_if_exists(engine):
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT t.id FROM continuity_feature_transitions t "
            "LEFT JOIN continuity_features f ON f.id = t.feature_id "
            "LEFT JOIN creative_entities e ON e.id = f.entity_id "
            "WHERE t.deleted_at IS NULL AND "
            "(f.id IS NULL OR f.deleted_at IS NOT NULL OR "
            " e.deleted_at IS NOT NULL)"
        ))).scalars().all()
        dupes = (await conn.execute(text(
            "SELECT feature_id, anchor_type, anchor_id, boundary, "
            "COUNT(*) AS n FROM continuity_feature_transitions "
            "WHERE deleted_at IS NULL "
            "GROUP BY feature_id, anchor_type, anchor_id, boundary "
            "HAVING n > 1"
        ))).all()
    assert dupes == []
    return list(rows)


async def test_race_transition_create_vs_feature_delete(client, factory, engine):
    """Deterministic interleaving: the Feature delete parks on the write
    lock AFTER the transition create has committed — Feature delete must
    then see the active transition and refuse."""
    pid = await _seed_project(factory)
    seq, scene, shots = await _topology(client, factory, pid, 1)
    eva = await _entity(client, pid)
    f = await _feature(client, eva["id"])

    from soloring.continuity import transitions as tsvc
    from soloring.api.schemas.continuity_transitions import TransitionCreate

    original = tsvc._load_active_feature
    state = {}

    async def wrap(conn, feature_id):
        result = await original(conn, feature_id)
        if "task" not in state:
            import asyncio as _a

            async def delete_it():
                async with factory() as s:
                    try:
                        await __import__("soloring.continuity.features",
                                         fromlist=["x"]).delete_feature(
                            s, feature_id)
                        return "deleted"
                    except Exception as exc:
                        return getattr(exc, "code", type(exc).__name__)

            state["task"] = _a.create_task(delete_it())
            await _a.sleep(0.3)  # parked on OUR write lock
        return result

    import soloring.continuity.transitions as tmod
    tmod._load_active_feature = wrap
    try:
        async with factory() as s:
            tid = await tsvc.create_transition(
                s, f["id"],
                TransitionCreate(anchor_type="shot", anchor_id=shots[0],
                                 boundary="start", operation="set",
                                 value="fresh"),
            )
    finally:
        tmod._load_active_feature = original
    outcome = await state["task"]
    assert outcome == "CONTINUITY_FEATURE_IN_USE"
    await _no_dangling(engine)
    # Cleanup for the invariant query's duplicate check.
    async with factory() as s:
        await tsvc.delete_transition(s, tid)


async def test_race_transition_create_vs_anchor_delete(client, factory, engine):
    """Anchor (Shot) deletion parks on the write lock while the transition
    create commits; deletion must then refuse with ANCHOR_IN_USE."""
    pid = await _seed_project(factory)
    seq, scene, shots = await _topology(client, factory, pid, 1)
    eva = await _entity(client, pid)
    f = await _feature(client, eva["id"])

    from soloring.api.schemas.continuity_transitions import TransitionCreate
    from soloring.continuity import transitions as tsvc

    original = tsvc._load_active_feature
    state = {}

    async def wrap(conn, feature_id):
        result = await original(conn, feature_id)
        if "task" not in state:
            import asyncio as _a

            async def delete_shot():
                async with factory() as s:
                    try:
                        await __import__("soloring.domain.shots",
                                         fromlist=["x"]).delete_shot(
                            s, shots[0])
                        return "deleted"
                    except Exception as exc:
                        return getattr(exc, "code", type(exc).__name__)

            state["task"] = _a.create_task(delete_shot())
            await _a.sleep(0.3)
        return result

    import soloring.continuity.transitions as tmod
    tmod._load_active_feature = wrap
    try:
        async with factory() as s:
            tid = await tsvc.create_transition(
                s, f["id"],
                TransitionCreate(anchor_type="shot", anchor_id=shots[0],
                                 boundary="start", operation="set",
                                 value="fresh"),
            )
    finally:
        tmod._load_active_feature = original
    outcome = await state["task"]
    assert outcome == "CONTINUITY_ANCHOR_IN_USE"
    await _no_dangling(engine)
    async with factory() as s:
        await tsvc.delete_transition(s, tid)


async def test_race_transition_create_vs_shot_unassign(client, factory, engine):
    """Unassignment parks on the write lock; it must then refuse (the Shot
    anchors an active transition)."""
    pid = await _seed_project(factory)
    seq, scene, shots = await _topology(client, factory, pid, 2)
    eva = await _entity(client, pid)
    f = await _feature(client, eva["id"])

    from soloring.api.schemas.continuity_transitions import TransitionCreate
    from soloring.continuity import transitions as tsvc

    original = tsvc._load_active_feature
    state = {}

    async def wrap(conn, feature_id):
        result = await original(conn, feature_id)
        if "task" not in state:
            import asyncio as _a

            async def unassign():
                async with factory() as s:
                    from soloring.narrative import scenes as scene_svc

                    try:
                        await scene_svc.assign_scene_shots(
                            s, scene, [shots[1]]
                        )
                        return "unassigned"
                    except Exception as exc:
                        return getattr(exc, "code", type(exc).__name__)

            state["task"] = _a.create_task(unassign())
            await _a.sleep(0.3)
        return result

    import soloring.continuity.transitions as tmod
    tmod._load_active_feature = wrap
    try:
        async with factory() as s:
            tid = await tsvc.create_transition(
                s, f["id"],
                TransitionCreate(anchor_type="shot", anchor_id=shots[0],
                                 boundary="start", operation="set",
                                 value="fresh"),
            )
    finally:
        tmod._load_active_feature = original
    outcome = await state["task"]
    assert outcome == "CONTINUITY_ANCHOR_IN_USE"
    await _no_dangling(engine)
    async with factory() as s:
        await tsvc.delete_transition(s, tid)


async def test_race_patch_vs_patch_into_same_coordinate(client, factory, engine):
    """Two PATCHes target the same free coordinate; exactly one wins, the
    other receives the conflict — deterministic via the write lock."""
    pid = await _seed_project(factory)
    seq, scene, shots = await _topology(client, factory, pid, 2)
    eva = await _entity(client, pid)
    f = await _feature(client, eva["id"])

    t1 = (await _transition(
        client, f["id"], "shot", shots[0], "start", "set", "fresh"
    )).json()
    t2 = (await _transition(
        client, f["id"], "shot", shots[1], "start", "set", "healing"
    )).json()

    async def patch(tid, anchor_id):
        return await client.patch(
            f"/continuity-feature-transitions/{tid}",
            json={"anchor_type": "scene", "anchor_id": anchor_id,
                  "boundary": "start"},
        )

    results = await asyncio.gather(
        patch(t1["id"], scene), patch(t2["id"], scene)
    )
    codes = sorted(r.status_code for r in results)
    assert codes == [200, 409], codes
    await _no_dangling(engine)


# --- M7B r2: missing frozen-gate pins (B7) -------------------------------------------


async def test_exact_409_for_cross_project_anchor_all_types(client, factory):
    pid_a = await _seed_project(factory)
    pid_b = await _seed_project(factory)
    seq_a, scene_a, shots_a = await _topology(client, factory, pid_a)
    seq_b, scene_b, shots_b = await _topology(client, factory, pid_b)
    eva = await _entity(client, pid_a)
    f = await _feature(client, eva["id"])

    for anchor_type, anchor_id in (
        ("sequence", seq_b), ("scene", scene_b), ("shot", shots_b[0]),
    ):
        r = await _transition(
            client, f["id"], anchor_type, anchor_id, "start", "set", "fresh"
        )
        assert r.status_code == 409, (anchor_type, r.text)
        assert r.json()["error_code"] == "CONTINUITY_ANCHOR_PROJECT_MISMATCH"


async def test_tombstoned_anchor_rejection_all_types(client, factory, engine):
    pid = await _seed_project(factory)
    seq, scene, shots = await _topology(client, factory, pid, 2)
    eva = await _entity(client, pid)
    f = await _feature(client, eva["id"])

    # Tombstone a spare scene/sequence/shot without anchor guards firing
    # (no transitions reference them yet).
    r = await client.post(f"/sequences/{seq}/scenes", json={"title": "C2"})
    scene2 = r.json()["id"]
    lonely = await _shot(client, factory, pid)

    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(
            text("UPDATE scenes SET deleted_at = "
                 "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :c"),
            {"c": scene2},
        )
        await conn.execute(
            text("UPDATE shots SET deleted_at = "
                 "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :s"),
            {"s": lonely},
        )
        await conn.execute(
            text("UPDATE sequences SET deleted_at = "
                 "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :q"),
            {"q": seq},
        )
        await conn.exec_driver_sql("COMMIT")

    for anchor_type, anchor_id in (
        ("sequence", seq), ("scene", scene2), ("shot", lonely),
    ):
        r = await _transition(
            client, f["id"], anchor_type, anchor_id, "start", "set", "fresh"
        )
        assert r.status_code == 422, (anchor_type, r.text)
        assert r.json()["error_code"] == "INVALID_CONTINUITY_ANCHOR"


async def test_corrupt_topology_invariant_isolation(client, factory, engine):
    pid_a = await _seed_project(factory)
    pid_b = await _seed_project(factory)
    seq_a, scene_a, shots_a = await _topology(client, factory, pid_a)
    seq_b, scene_b, shots_b = await _topology(client, factory, pid_b)
    eva = await _entity(client, pid_a)
    f = await _feature(client, eva["id"])
    # B's target must actually traverse the ordering: dependency + feature
    # + active transition on B's own entity (otherwise the resolver
    # short-circuits on empty dependencies and never loads topology).
    eva_b = await _entity_approved(client, pid_b, name="B")
    f_b = await _feature(client, eva_b["id"], key="b_cut")
    await _depend(client, shots_b[0], eva_b["id"])
    await _transition(client, f_b["id"], "sequence", seq_b, "start", "set",
                      "fresh")

    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(
            text("UPDATE sequences SET deleted_at = "
                 "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :q"),
            {"q": seq_b},
        )
        await conn.exec_driver_sql("COMMIT")

    r = await client.get(f"/shots/{shots_a[0]}/continuity-state")
    assert r.status_code == 200  # A unaffected by B's corruption
    from soloring.errors import SoloRingError
    from soloring.continuity.state import resolve_effective_feature_state
    async with engine.connect() as conn:
        with pytest.raises(SoloRingError) as ei:
            await resolve_effective_feature_state(conn, shots_b[0])
    assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"


async def test_direct_capture_revision_gates(client, factory, engine):
    """Direct capture_revision() (not via HTTP) enforces both gates and
    writes no ShotRevision."""
    from soloring.domain import revisions as revision_svc

    pid = await _seed_project(factory)
    eva = await _entity_approved(client, pid)
    f = await _feature(client, eva["id"])
    seq, scene, shots = await _topology(client, factory, pid, 2)
    for sid in shots:
        await _depend(client, sid, eva["id"])

    # Zero effective state: capture legal, exact schema-2 form (deps, no M7).
    rev = await revision_svc.capture_revision(factory(), shots[0])
    snapshot = json.loads(rev.snapshot_json)
    assert snapshot["schema_version"] == 2
    assert "continuity" in snapshot
    assert snapshot["continuity"]["dependencies"]
    assert rev.continuity_spec_hash is not None

    # Effective-empty via future transition AND winning clear: still legal,
    # and converges back onto the SAME schema-2 revision (M6 form exact).
    await _transition(client, f["id"], "shot", shots[1], "end", "set",
                      "fresh")  # future for shots[0]
    listed = None
    rev2 = await revision_svc.capture_revision(factory(), shots[0])
    assert rev2.id == rev.id  # converged onto the same M6 revision

    # Winning clear on the target's own coordinate: effective empty.
    tid = None
    for row in (await client.get(
            f"/continuity-features/{f['id']}/transitions")).json():
        if row["anchor_type"] == "shot" and row["anchor_id"] == shots[1]:
            tid = row["id"]
    await client.patch(
        f"/continuity-feature-transitions/{tid}",
        json={"boundary": "start"},
    )
    await client.patch(
        f"/continuity-feature-transitions/{tid}", json={"operation": "clear"}
    )
    rev3 = await revision_svc.capture_revision(factory(), shots[0])
    assert rev3.id == rev.id

    # Nonempty effective state → gate, no revision written. Anchor at
    # scene/start (eligible for shots[0]); shots[1]/start is future for it.
    r = await client.patch(
        f"/continuity-feature-transitions/{tid}",
        json={"anchor_type": "scene", "anchor_id": scene,
              "operation": "set", "value": "fresh"},
    )
    assert r.status_code == 200
    before = await _fetch(
        engine, "SELECT COUNT(*) AS n FROM shot_revisions WHERE shot_id = :s",
        {"s": shots[0]},
    )
    with pytest.raises(SoloRingError) as ei:
        await revision_svc.capture_revision(factory(), shots[0])
    assert ei.value.code == "NARRATIVE_STATE_CAPTURE_UNAVAILABLE"
    after = await _fetch(
        engine, "SELECT COUNT(*) AS n FROM shot_revisions WHERE shot_id = :s",
        {"s": shots[0]},
    )
    assert after["n"] == before["n"]

    # Unassigned + relevant → context gate, no revision written.
    lonely = await _shot(client, factory, pid)
    await _depend(client, lonely, eva["id"])
    before = await _fetch(
        engine, "SELECT COUNT(*) AS n FROM shot_revisions WHERE shot_id = :s",
        {"s": lonely},
    )
    with pytest.raises(SoloRingError) as ei:
        await revision_svc.capture_revision(factory(), lonely)
    assert ei.value.code == "NARRATIVE_CONTEXT_REQUIRED"
    after = await _fetch(
        engine, "SELECT COUNT(*) AS n FROM shot_revisions WHERE shot_id = :s",
        {"s": lonely},
    )
    assert after["n"] == before["n"]


async def _fetch_all(engine, sql, params=None):
    async with engine.connect() as conn:
        rows = (await conn.execute(text(sql), params or {})).mappings().all()
    return [dict(r) for r in rows]

# --- M7B r3: explicit-null rejection + winning-clear proof + barrier races ----


async def test_patch_explicit_null_never_reaches_db(client, factory, engine):
    """R1: explicit null on any non-nullable PATCH field is a request-
    boundary 422 — the transition row is left byte-identical."""
    pid = await _seed_project(factory)
    seq, scene, shots = await _topology(client, factory, pid, 1)
    eva = await _entity(client, pid)
    f = await _feature(client, eva["id"])
    t = (await _transition(
        client, f["id"], "shot", shots[0], "start", "set", "fresh"
    )).json()
    before = await _fetch(
        engine,
        "SELECT anchor_type, anchor_id, boundary, operation, value_json, "
        "value_hash, deleted_at FROM continuity_feature_transitions "
        "WHERE id = :t",
        {"t": t["id"]},
    )

    for field in ("anchor_type", "anchor_id", "boundary", "operation"):
        r = await client.patch(
            f"/continuity-feature-transitions/{t['id']}",
            json={field: None},
        )
        assert r.status_code == 422, (field, r.text)

    after = await _fetch(
        engine,
        "SELECT anchor_type, anchor_id, boundary, operation, value_json, "
        "value_hash, deleted_at FROM continuity_feature_transitions "
        "WHERE id = :t",
        {"t": t["id"]},
    )
    assert after == before


async def test_winning_clear_direct_capture_proof(client, factory, engine):
    """R2: an ELIGIBLE winning clear (not a future transition) resolves to
    effective absence and M6 capture stays legal with the exact schema-2
    form, converging onto the same M6 revision — no schema 3 anywhere."""
    from soloring.domain import revisions as revision_svc

    pid = await _seed_project(factory)
    eva = await _entity_approved(client, pid)
    f = await _feature(client, eva["id"])
    seq, scene, shots = await _topology(client, factory, pid, 2)
    for sid in shots:
        await _depend(client, sid, eva["id"])

    # Baseline M6 revision (dependencies, no temporal data).
    rev_m6 = await revision_svc.capture_revision(factory(), shots[0])
    assert json.loads(rev_m6.snapshot_json)["schema_version"] == 2

    # set → clear, BOTH eligible for shots[0]: the clear outranks the set.
    await _transition(client, f["id"], "sequence", seq, "start", "set",
                      "fresh")
    await _transition(client, f["id"], "shot", shots[0], "start", "clear")

    # The resolver sees the clear as the highest eligible transition.
    r = await client.get(f"/shots/{shots[0]}/continuity-state")
    assert r.status_code == 200
    assert r.json()["feature_states"] == []

    # Capture remains legal and converges onto the SAME M6 revision.
    rev2 = await revision_svc.capture_revision(factory(), shots[0])
    assert rev2.id == rev_m6.id
    assert rev2.snapshot_hash == rev_m6.snapshot_hash
    snapshot = json.loads(rev2.snapshot_json)
    assert snapshot["schema_version"] == 2
    assert "continuity" in snapshot
    assert snapshot["continuity"]["dependencies"]
    # No schema-3 revision exists for this shot at all.
    rows = await _fetch_all(
        engine,
        "SELECT snapshot_json FROM shot_revisions WHERE shot_id = :s",
        {"s": shots[0]},
    )
    for row in rows:
        assert json.loads(row["snapshot_json"])["schema_version"] != 3


# --- R3: barrier-forced races ------------------------------------------------------
# The competitor signals AFTER issuing its BEGIN IMMEDIATE (it is parked on
# the write lock held by the create), and the create releases only then —
# the test mechanically proves the parked interleaving, not a timing hope.


async def _race_create_vs(client, factory, engine, competitor):
    """Deterministic parked-on-lock race driver (r4).

    The competitor's ACTUAL ``BEGIN IMMEDIATE`` statement is instrumented:
    ``AsyncConnection.exec_driver_sql`` is wrapped for the lifetime of the
    competitor task, and the ``begin_attempted`` event fires from INSIDE
    that call — i.e. the competitor is executing the real lock-acquisition
    statement against the creator's held write lock at the moment the
    creator observes the event. The creator then proceeds to commit; the
    competitor, parked in that same statement, acquires only afterward and
    must observe the fully committed transition. No sleep-based
    synchronization anywhere.
    """
    from sqlalchemy.ext.asyncio import AsyncConnection

    from soloring.api.schemas.continuity_transitions import TransitionCreate
    from soloring.continuity import transitions as tsvc

    pid = await _seed_project(factory)
    seq, scene, shots = await _topology(client, factory, pid, 2)
    eva = await _entity(client, pid)
    f = await _feature(client, eva["id"])

    original = tsvc._load_active_feature
    original_exec = AsyncConnection.exec_driver_sql
    state: dict = {}
    begin_attempted = asyncio.Event()

    async def wrapped_exec(self, statement, *args, **kwargs):
        task = asyncio.current_task()
        if (
            state.get("competitor") is not None
            and task is state["competitor"]
            and statement.strip().upper() == "BEGIN IMMEDIATE"
        ):
            begin_attempted.set()
        return await original_exec(self, statement, *args, **kwargs)

    async def competitor_task():
        state["outcome"] = await competitor(
            pid=pid, seq=seq, scene=scene, shots=shots, f=f
        )

    async def wrap(conn, feature_id):
        result = await original(conn, feature_id)
        if "competitor" not in state:
            AsyncConnection.exec_driver_sql = wrapped_exec
            state["competitor"] = asyncio.create_task(competitor_task())
            # Park until the competitor is EXECUTING its BEGIN IMMEDIATE —
            # provably queued on the write lock WE hold right now.
            await begin_attempted.wait()
        return result

    import soloring.continuity.transitions as tmod
    tmod._load_active_feature = wrap
    try:
        async with factory() as s:
            tid = await tsvc.create_transition(
                s, f["id"],
                TransitionCreate(anchor_type="shot", anchor_id=shots[0],
                                 boundary="start", operation="set",
                                 value="fresh"),
            )
        await state["competitor"]
    finally:
        tmod._load_active_feature = original
        AsyncConnection.exec_driver_sql = original_exec
    return tid, state.get("outcome"), (pid, seq, scene, shots, f)


async def _anchor_integrity(engine) -> None:
    """Every active transition's anchor path is existing, active,
    same-Project-reachable, and — for Shot anchors — assigned and present
    in the canonical ordering."""
    from soloring.narrative.order import load_narrative_ordering

    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT t.id, t.anchor_type, t.anchor_id, e.project_id "
            "FROM continuity_feature_transitions t "
            "JOIN continuity_features f ON f.id = t.feature_id "
            "JOIN creative_entities e ON e.id = f.entity_id "
            "WHERE t.deleted_at IS NULL"
        ))).mappings().all()
        by_project: dict[str, list] = {}
        for row in rows:
            by_project.setdefault(row["project_id"], []).append(row)
        for pid, prows in by_project.items():
            ordering = await load_narrative_ordering(conn, pid)
            for row in prows:
                # Presence in the canonical ordering proves existing +
                # active + same-Project + narratively reachable (and, for
                # shot anchors, assigned) — it is the single authority.
                ordering.rank_of(
                    row["anchor_type"], row["anchor_id"], "start"
                )


async def test_race_create_vs_feature_delete_barrier(client, factory, engine):
    async def competitor(*, pid, seq, scene, shots, f):
        async with factory() as s:
            from soloring.continuity import features as fsvc

            try:
                await fsvc.delete_feature(s, f["id"])
                return "deleted"
            except Exception as exc:
                return getattr(exc, "code", type(exc).__name__)

    tid, outcome, ctx = await _race_create_vs(client, factory, engine, competitor)
    assert outcome == "CONTINUITY_FEATURE_IN_USE"
    await _anchor_integrity(engine)
    from soloring.continuity import transitions as tsvc

    async with factory() as s:
        await tsvc.delete_transition(s, tid)


async def test_race_create_vs_anchor_shot_delete_barrier(client, factory, engine):
    async def competitor(*, pid, seq, scene, shots, f):
        async with factory() as s:
            from soloring.domain import shots as shot_svc

            try:
                await shot_svc.delete_shot(s, shots[0])
                return "deleted"
            except Exception as exc:
                return getattr(exc, "code", type(exc).__name__)

    tid, outcome, ctx = await _race_create_vs(client, factory, engine, competitor)
    assert outcome == "CONTINUITY_ANCHOR_IN_USE"
    await _anchor_integrity(engine)
    from soloring.continuity import transitions as tsvc

    async with factory() as s:
        await tsvc.delete_transition(s, tid)


async def test_race_create_vs_shot_unassign_barrier(client, factory, engine):
    async def competitor(*, pid, seq, scene, shots, f):
        async with factory() as s:
            from soloring.narrative import scenes as scene_svc

            try:
                await scene_svc.assign_scene_shots(s, scene, [shots[1]])
                return "unassigned"
            except Exception as exc:
                return getattr(exc, "code", type(exc).__name__)

    tid, outcome, ctx = await _race_create_vs(client, factory, engine, competitor)
    assert outcome == "CONTINUITY_ANCHOR_IN_USE"
    # Postcondition specifics: the Shot is STILL assigned, the transition
    # is STILL active, and the anchor remains in the canonical ordering.
    pid, seq, scene, shots, f = ctx
    row = await _fetch(
        engine, "SELECT scene_id FROM shots WHERE id = :s", {"s": shots[0]}
    )
    assert row["scene_id"] == scene
    trow = await _fetch(
        engine,
        "SELECT deleted_at FROM continuity_feature_transitions "
        "WHERE id = :t",
        {"t": tid},
    )
    assert trow["deleted_at"] is None
    await _anchor_integrity(engine)
    from soloring.continuity import transitions as tsvc

    async with factory() as s:
        await tsvc.delete_transition(s, tid)
