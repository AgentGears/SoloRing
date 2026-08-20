"""M8C readiness integration: the composed endpoint, semantic
short-circuit (§52.1), M7 blocker surfacing, and ShotRead additive fields
will land with M8D capture — this file covers the endpoint contract."""

from __future__ import annotations

from tests.test_m8a_visual import (
    _entity_with_revision,
    _facet,
    _seed_project,
)
from tests.test_m8b_curation import _assets, _put_payload
from tests.test_m8c_resolver import (
    _approve_anchor,
    _depend,
    _resolver_result,
    _topology,
)


async def test_visual_continuity_endpoint_composed_projection(
    client, factory, engine,
):
    pid = await _seed_project(factory)
    eva, rev1 = await _entity_with_revision(client, factory, pid)
    assets = await _assets(engine, pid, 1)
    f = await _facet(client, pid, "entity", entity_id=eva["id"],
                     facet_key="face")
    r = await client.post(
        f"/visual-facets/{f['id']}/anchors", json={"entity_revision_id": rev1}
    )
    await _approve_anchor(client, r.json()["id"], assets, ["front"])

    seq, scene, shots = await _topology(client, factory, pid)
    await _depend(client, shots[0], [eva["id"]])

    r = await client.get(f"/shots/{shots[0]}/visual-continuity")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["continuity_state_ready"] is True
    assert body["visual_continuity_ready"] is True
    assert body["visual_reference_pack_hash"]
    assert body["visual_continuity_issues"] == []
    statuses = {s["facet_key"]: s["resolved"] for s in body["facet_statuses"]}
    assert statuses["face"] == "approved"
    assert body["visual_reference_pack"]["schema_version"] == 1


async def test_endpoint_short_circuits_on_semantic_not_ready(
    client, factory, engine,
):
    """§52.1: unassigned Shot with relevant Feature data → M7
    NARRATIVE_CONTEXT_REQUIRED; visual fields project blocked with the M7
    blocker surfaced honestly — no partial visual resolution."""
    pid = await _seed_project(factory)
    eva, rev1 = await _entity_with_revision(client, factory, pid)
    from tests.test_m8a_visual import _feature

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

    # An unassigned shot with the entity as dependency: M7 not ready.
    from soloring.api.schemas.shots import ShotCreate
    from soloring.domain import shots as shot_svc

    async with factory() as s:
        loose = (await shot_svc.create_shot(
            s, pid, ShotCreate(subject="y"))).id
    await _depend(client, loose, [eva["id"]])

    r = await client.get(f"/shots/{loose}/visual-continuity")
    assert r.status_code == 200
    body = r.json()
    assert body["continuity_state_ready"] is False
    assert body["visual_continuity_ready"] is False
    assert body["visual_reference_pack_hash"] is None
    codes = {i["error_code"] for i in body["visual_continuity_issues"]}
    assert "NARRATIVE_CONTEXT_REQUIRED" in codes
    assert body["facet_statuses"] == []  # no partial resolution


async def test_endpoint_reports_visual_blockers_after_semantic_ready(
    client, factory, engine,
):
    pid = await _seed_project(factory)
    eva, rev1 = await _entity_with_revision(client, factory, pid)
    f_req = await _facet(client, pid, "entity", entity_id=eva["id"],
                         facet_key="face")  # required, no anchor
    seq, scene, shots = await _topology(client, factory, pid)
    await _depend(client, shots[0], [eva["id"]])

    r = await client.get(f"/shots/{shots[0]}/visual-continuity")
    body = r.json()
    assert body["continuity_state_ready"] is True
    assert body["visual_continuity_ready"] is False
    assert body["visual_reference_pack_hash"] is None
    codes = {i["error_code"] for i in body["visual_continuity_issues"]}
    assert codes == {"VISUAL_REALIZATION_REQUIRED"}
    statuses = {s["facet_key"]: s["resolved"] for s in body["facet_statuses"]}
    assert statuses["face"] == "missing"
