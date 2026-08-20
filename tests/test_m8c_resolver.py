"""M8C — resolver and readiness (frozen plan §§42–52; M8C gate).

Critical tests §83–§85 (requirement survival across EntityRevision/Feature
value changes; EntityRevision context preventing accidental reuse) plus
not-applicable, optional-omit, corruption fail-closed, one-path parity,
and semantic-not-ready short-circuiting.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from soloring.api.schemas.projects import ProjectCreate
from soloring.api.schemas.shots import ShotCreate
from soloring.domain import projects as project_svc
from soloring.domain import shots as shot_svc
from tests.conftest import seed_reference_asset
from tests.test_m8a_visual import (
    _entity_with_revision,
    _facet,
    _feature,
    _seed_project,
)
from tests.test_m8b_curation import _assets, _put_payload


async def _topology(client, factory, pid):
    r = await client.post(f"/projects/{pid}/sequences", json={"title": "S"})
    seq = r.json()["id"]
    r = await client.post(f"/sequences/{seq}/scenes", json={"title": "C"})
    scene = r.json()["id"]
    from soloring.api.schemas.shots import ShotCreate as SC

    ids = []
    for _ in range(2):
        async with factory() as s:
            shot = await shot_svc.create_shot(s, pid, SC(subject="x"))
        ids.append(shot.id)
    r = await client.put(f"/scenes/{scene}/shots", json={"shot_ids": ids})
    assert r.status_code == 200, r.text
    return seq, scene, ids


async def _depend(client, shot_id, entity_ids):
    r = await client.put(
        f"/shots/{shot_id}/semantic-dependencies",
        json={"dependencies": [
            {"entity_id": eid, "role": f"r{i}"}
            for i, eid in enumerate(entity_ids)
        ]},
    )
    assert r.status_code == 200, r.text


async def _approve_anchor(client, anchor_id, assets, view_keys=None):
    await client.put(
        f"/visual-anchors/{anchor_id}/items",
        json=_put_payload(assets, view_keys=view_keys),
    )
    r = await client.post(f"/visual-anchors/{anchor_id}/revisions")
    assert r.status_code == 201, r.text
    rev_id = r.json()["id"]
    r = await client.post(
        f"/visual-anchor-revisions/{rev_id}/approve",
        json={"expected_approved_revision_id": None},
    )
    assert r.status_code == 200
    return rev_id


async def _resolver_result(engine, shot_id):
    """Call the ONE resolver on its own coherent read unit (§44)."""
    from soloring.continuity.snapshots import resolve_working_dependencies
    from soloring.continuity.state import resolve_effective_feature_state
    from soloring.visual.resolver import resolve_visual_reference_pack_async

    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN")
        try:
            deps = await resolve_working_dependencies(conn, shot_id)
            states = await resolve_effective_feature_state(conn, shot_id)
            result = await resolve_visual_reference_pack_async(
                shot_id, (deps, states.states), conn=conn
            )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
    return result


async def test_required_entity_facet_survives_revision_change(
    client, factory, engine,
):
    """§83: Eva/face required; rev3 approved → ready; new revision dep →
    no rev4 anchor → NOT ready VISUAL_REALIZATION_REQUIRED."""
    pid = await _seed_project(factory)
    eva, rev1 = await _entity_with_revision(client, factory, pid)
    assets = await _assets(engine, pid, 1)
    f = await _facet(client, pid, "entity", entity_id=eva["id"],
                     facet_key="face")
    r = await client.post(
        f"/visual-facets/{f['id']}/anchors", json={"entity_revision_id": rev1}
    )
    anchor_id = r.json()["id"]
    await _approve_anchor(client, anchor_id, assets, ["front"])

    seq, scene, shots = await _topology(client, factory, pid)
    await _depend(client, shots[0], [eva["id"]])

    result = await _resolver_result(engine, shots[0])
    assert result.visual_continuity_ready is True
    assert result.visual_reference_pack_hash
    assert len(result.pack["anchors"]) == 1

    # Eva moves to revision 2 (new approved design revision).
    r = await client.post(
        f"/entities/{eva['id']}/revisions", json={"spec": {"description": "2"}}
    )
    rev2 = r.json()["id"]
    await client.put(
        f"/entities/{eva['id']}/approved-revision",
        json={"revision_id": rev2, "expected_approved_revision_id": rev1},
    )
    result = await _resolver_result(engine, shots[0])
    assert result.visual_continuity_ready is False
    codes = {i["error_code"] for i in result.issues}
    assert codes == {"VISUAL_REALIZATION_REQUIRED"}


async def test_required_feature_facet_survives_value_change(
    client, factory, engine,
):
    """§84: cut-realization required; fresh approved → ready; value →
    healing with no realization → NOT ready. none → not_applicable →
    unaffected."""
    pid = await _seed_project(factory)
    eva, rev1 = await _entity_with_revision(client, factory, pid)
    feat = await _feature(client, eva["id"])
    assets = await _assets(engine, pid, 1)

    f = await _facet(
        client, pid, "feature", feature_id=feat["id"],
        facet_key="cut-realization",
    )
    r = await client.put(
        f"/visual-facets/{f['id']}/value-policies",
        json={"policies": [{"value": "none", "policy": "not_applicable"}]},
    )
    assert r.status_code == 200

    r = await client.post(
        f"/visual-facets/{f['id']}/anchors",
        json={"value": "fresh", "visual_context_entity_revision_id": rev1},
    )
    anchor_id = r.json()["id"]
    await _approve_anchor(client, anchor_id, assets, ["front-detail"])

    seq, scene, shots = await _topology(client, factory, pid)
    await _depend(client, shots[0], [eva["id"]])
    r = await client.post(
        f"/continuity-features/{feat['id']}/transitions",
        json={"anchor_type": "scene", "anchor_id": scene,
              "boundary": "start", "operation": "set", "value": "fresh"},
    )
    assert r.status_code == 201, r.text

    result = await _resolver_result(engine, shots[0])
    assert result.visual_continuity_ready is True
    assert result.pack["anchors"][0]["target"]["feature_value_json"] == (
        '"fresh"'
    )

    # shots[1] resolves the same entity; its feature value is whatever
    # the last eligible transition sets.
    await _depend(client, shots[1], [eva["id"]])

    # Value changes to healing — no realization exists.
    r = await client.post(
        f"/continuity-features/{feat['id']}/transitions",
        json={"anchor_type": "shot", "anchor_id": shots[1],
              "boundary": "start", "operation": "set", "value": "healing"},
    )
    assert r.status_code == 201
    result = await _resolver_result(engine, shots[1])
    assert result.visual_continuity_ready is False
    assert {i["error_code"] for i in result.issues} == {
        "VISUAL_REALIZATION_REQUIRED"
    }

    # Value becomes none → not_applicable → ready with empty pack.
    # (PATCH the winning transition — its coordinate is unique.)
    trs = (
        await client.get(f"/continuity-features/{feat['id']}/transitions")
    ).json()
    winner = [
        t for t in trs
        if t["anchor_type"] == "shot" and t["anchor_id"] == shots[1]
    ][0]
    r = await client.patch(
        f"/continuity-feature-transitions/{winner['id']}",
        json={"operation": "set", "value": "none"},
    )
    assert r.status_code == 200, r.text
    result = await _resolver_result(engine, shots[1])
    assert result.visual_continuity_ready is True
    assert result.pack is None  # not_applicable omits from pack (§10)


async def test_entity_revision_context_prevents_accidental_reuse(
    client, factory, engine,
):
    """§85: rev12/fresh approved; Eva → rev13 with value still fresh → the
    rev12 anchor does NOT apply; required facet → not ready."""
    pid = await _seed_project(factory)
    eva, rev1 = await _entity_with_revision(client, factory, pid)
    feat = await _feature(client, eva["id"])
    assets = await _assets(engine, pid, 1)
    f = await _facet(
        client, pid, "feature", feature_id=feat["id"],
        facet_key="cut-realization",
    )
    r = await client.post(
        f"/visual-facets/{f['id']}/anchors",
        json={"value": "fresh", "visual_context_entity_revision_id": rev1},
    )
    await _approve_anchor(client, r.json()["id"], assets, ["front"])

    seq, scene, shots = await _topology(client, factory, pid)
    await _depend(client, shots[0], [eva["id"]])
    await client.post(
        f"/continuity-features/{feat['id']}/transitions",
        json={"anchor_type": "scene", "anchor_id": scene,
              "boundary": "start", "operation": "set", "value": "fresh"},
    )
    result = await _resolver_result(engine, shots[0])
    assert result.visual_continuity_ready is True

    # Eva advances to rev2 — value stays fresh.
    r = await client.post(
        f"/entities/{eva['id']}/revisions", json={"spec": {"description": "2"}}
    )
    rev2 = r.json()["id"]
    await client.put(
        f"/entities/{eva['id']}/approved-revision",
        json={"revision_id": rev2, "expected_approved_revision_id": rev1},
    )
    result = await _resolver_result(engine, shots[0])
    assert result.visual_continuity_ready is False
    assert {i["error_code"] for i in result.issues} == {
        "VISUAL_REALIZATION_REQUIRED"
    }


async def test_optional_facets_omit_without_blocking(client, factory, engine):
    pid = await _seed_project(factory)
    eva, rev1 = await _entity_with_revision(client, factory, pid)
    f_req = await _facet(client, pid, "entity", entity_id=eva["id"],
                         facet_key="face")
    f_opt = await _facet(client, pid, "entity", entity_id=eva["id"],
                         facet_key="hair", requirement="optional")
    assets = await _assets(engine, pid, 1)

    r = await client.post(
        f"/visual-facets/{f_req['id']}/anchors",
        json={"entity_revision_id": rev1},
    )
    await _approve_anchor(client, r.json()["id"], assets, ["front"])

    seq, scene, shots = await _topology(client, factory, pid)
    await _depend(client, shots[0], [eva["id"]])

    result = await _resolver_result(engine, shots[0])
    assert result.visual_continuity_ready is True  # optional missing: fine
    assert len(result.pack["anchors"]) == 1  # only face
    statuses = {s.facet_key: s.resolved for s in result.facet_statuses}
    assert statuses["hair"] == "missing"
    assert statuses["face"] == "approved"

    # Optional facet approved later → included, no required change.
    r = await client.post(
        f"/visual-facets/{f_opt['id']}/anchors",
        json={"entity_revision_id": rev1},
    )
    await _approve_anchor(client, r.json()["id"], assets, ["side"])
    result = await _resolver_result(engine, shots[0])
    assert result.visual_continuity_ready is True
    assert len(result.pack["anchors"]) == 2


async def test_unapproved_required_anchor_blocks(client, factory, engine):
    pid = await _seed_project(factory)
    eva, rev1 = await _entity_with_revision(client, factory, pid)
    assets = await _assets(engine, pid, 1)
    f = await _facet(client, pid, "entity", entity_id=eva["id"])
    r = await client.post(
        f"/visual-facets/{f['id']}/anchors", json={"entity_revision_id": rev1}
    )
    anchor_id = r.json()["id"]
    # Working set + revision captured but NOT approved.
    await client.put(
        f"/visual-anchors/{anchor_id}/items",
        json=_put_payload(assets),
    )
    await client.post(f"/visual-anchors/{anchor_id}/revisions")

    seq, scene, shots = await _topology(client, factory, pid)
    await _depend(client, shots[0], [eva["id"]])
    result = await _resolver_result(engine, shots[0])
    assert result.visual_continuity_ready is False
    assert {i["error_code"] for i in result.issues} == {
        "VISUAL_ANCHOR_APPROVAL_REQUIRED"
    }


async def test_approved_revision_corruption_fails_closed(
    client, factory, engine,
):
    """§48: corruption of an applicable APPROVED revision (even on an
    optional facet) is INTERNAL_INVARIANT_VIOLATION — never silent."""
    pid = await _seed_project(factory)
    eva, rev1 = await _entity_with_revision(client, factory, pid)
    assets = await _assets(engine, pid, 1)
    f = await _facet(client, pid, "entity", entity_id=eva["id"],
                     facet_key="face", requirement="optional")
    r = await client.post(
        f"/visual-facets/{f['id']}/anchors", json={"entity_revision_id": rev1}
    )
    anchor_id = r.json()["id"]
    await _approve_anchor(client, anchor_id, assets, ["front"])

    seq, scene, shots = await _topology(client, factory, pid)
    await _depend(client, shots[0], [eva["id"]])

    detail = (await client.get(f"/visual-anchors/{anchor_id}")).json()
    rid = detail["approved_revision_id"]
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE visual_anchor_revisions SET snapshot_hash = :h "
                "WHERE id = :rid"
            ),
            {"h": "0" * 64, "rid": rid},
        )
    with pytest.raises(Exception) as ei:
        await _resolver_result(engine, shots[0])
    assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"


async def test_canonical_pack_ordering_entity_before_feature(
    client, factory, engine,
):
    """§50: entity anchors sort before feature anchors; semantic keys
    order within each kind."""
    pid = await _seed_project(factory)
    eva, rev1 = await _entity_with_revision(client, factory, pid)
    feat = await _feature(client, eva["id"])
    assets = await _assets(engine, pid, 2)

    f_face = await _facet(client, pid, "entity", entity_id=eva["id"],
                          facet_key="face")
    f_cut = await _facet(
        client, pid, "feature", feature_id=feat["id"],
        facet_key="cut-realization",
    )
    r = await client.post(
        f"/visual-facets/{f_face['id']}/anchors",
        json={"entity_revision_id": rev1},
    )
    await _approve_anchor(client, r.json()["id"], assets, ["front", "side"])
    r = await client.post(
        f"/visual-facets/{f_cut['id']}/anchors",
        json={"value": "fresh", "visual_context_entity_revision_id": rev1},
    )
    await _approve_anchor(client, r.json()["id"], assets, ["detail"])

    seq, scene, shots = await _topology(client, factory, pid)
    await _depend(client, shots[0], [eva["id"]])
    await client.post(
        f"/continuity-features/{feat['id']}/transitions",
        json={"anchor_type": "scene", "anchor_id": scene,
              "boundary": "start", "operation": "set", "value": "fresh"},
    )

    result = await _resolver_result(engine, shots[0])
    kinds = [a["target"]["kind"] for a in result.pack["anchors"]]
    assert kinds == ["entity", "feature"]
    # Item order is position-authoritative within the anchor.
    face_items = result.pack["anchors"][0]["items"]
    assert [it["view_key"] for it in face_items] == ["front", "side"]

    # Hash determinism: same state → same hash.
    again = await _resolver_result(engine, shots[0])
    assert again.visual_reference_pack_hash == (
        result.visual_reference_pack_hash
    )


async def test_same_value_new_transition_uuid_same_applicability(
    client, factory, engine,
):
    """§47: applicability follows semantic identity, not transition rows."""
    pid = await _seed_project(factory)
    eva, rev1 = await _entity_with_revision(client, factory, pid)
    feat = await _feature(client, eva["id"])
    assets = await _assets(engine, pid, 1)
    f = await _facet(
        client, pid, "feature", feature_id=feat["id"], facet_key="cut",
    )
    r = await client.post(
        f"/visual-facets/{f['id']}/anchors",
        json={"value": "fresh", "visual_context_entity_revision_id": rev1},
    )
    await _approve_anchor(client, r.json()["id"], assets, ["front"])

    seq, scene, shots = await _topology(client, factory, pid)
    await _depend(client, shots[0], [eva["id"]])
    await client.post(
        f"/continuity-features/{feat['id']}/transitions",
        json={"anchor_type": "scene", "anchor_id": scene,
              "boundary": "start", "operation": "set", "value": "fresh"},
    )
    h1 = (await _resolver_result(engine, shots[0])).visual_reference_pack_hash

    # Replace the transition with an equivalent one at the same coordinate
    # (delete + recreate = new UUID, same semantic value).
    rows = (
        await client.get(f"/continuity-features/{feat['id']}/transitions")
    ).json()
    await client.delete(
        f"/continuity-feature-transitions/{rows[0]['id']}"
    )
    await client.post(
        f"/continuity-features/{feat['id']}/transitions",
        json={"anchor_type": "scene", "anchor_id": scene,
              "boundary": "start", "operation": "set", "value": "fresh"},
    )
    h2 = (await _resolver_result(engine, shots[0])).visual_reference_pack_hash
    assert h1 == h2  # same semantic value → same pack bytes
