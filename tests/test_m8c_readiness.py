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


async def test_shot_read_projects_visual_blocked_with_relation_blocker(
    client, factory, engine,
):
    """r2 B1: ShotRead must not default visual-ready when M7 Relations are
    not ready, and the composed endpoint must surface the RELATION
    dimension (§52.1 includes CONTINUITY_RELATION_ENDPOINT_REQUIRED) —
    both read paths, one fixture."""
    from tests.test_m7d_relations import _predicate, _relation, _rt

    pid = await _seed_project(factory)
    eva, rev1 = await _entity_with_revision(client, factory, pid)
    r = await client.post(f"/projects/{pid}/entities",
                          json={"kind": "prop", "name": "Bag"})
    bag = r.json()["id"]
    carries = await _predicate(client, pid, key="carries")
    rel = await _relation(client, pid, eva["id"], carries["id"], bag)
    seq, scene, shots = await _topology(client, factory, pid)
    await _depend(client, shots[0], [eva["id"]])  # exactly one endpoint
    assert (
        await _rt(client, rel["id"], "shot", shots[0], "start", "active")
    ).status_code == 201

    # ShotRead path: visual false/NULL with the M7 relation blocker
    # surfaced honestly — never a fabricated ready=true default.
    r = await client.get(f"/shots/{shots[0]}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["continuity_state_ready"] is False
    assert body["visual_continuity_ready"] is False
    assert body["visual_reference_pack_hash"] is None
    codes = {i["error_code"] for i in body["visual_continuity_issues"]}
    assert codes == {"CONTINUITY_RELATION_ENDPOINT_REQUIRED"}

    # Composed endpoint path: same relation blocker, no partial
    # resolution, facet statuses empty.
    r = await client.get(f"/shots/{shots[0]}/visual-continuity")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["continuity_state_ready"] is False
    assert body["visual_continuity_ready"] is False
    assert body["visual_reference_pack_hash"] is None
    codes = {i["error_code"] for i in body["visual_continuity_issues"]}
    assert codes == {"CONTINUITY_RELATION_ENDPOINT_REQUIRED"}
    assert body["facet_statuses"] == []


async def test_shot_read_projects_visual_blocked_with_narrative_blocker(
    client, factory, engine,
):
    """r2 B1 (ShotRead half): the M7 NARRATIVE_CONTEXT_REQUIRED blocker
    must flow through ShotRead's visual fields — the r1 code defaulted
    visual_continuity_ready=true whenever the visual result was absent."""
    pid = await _seed_project(factory)
    eva, rev1 = await _entity_with_revision(client, factory, pid)
    from tests.test_m8a_visual import _feature

    feat = await _feature(client, eva["id"])
    seq, scene, shots = await _topology(client, factory, pid)
    await _depend(client, shots[0], [eva["id"]])
    await client.post(
        f"/continuity-features/{feat['id']}/transitions",
        json={"anchor_type": "scene", "anchor_id": scene,
              "boundary": "start", "operation": "set", "value": "fresh"},
    )

    # Unassigned shot with the entity as dependency: M7 not ready.
    from soloring.api.schemas.shots import ShotCreate
    from soloring.domain import shots as shot_svc

    async with factory() as s:
        loose = (await shot_svc.create_shot(
            s, pid, ShotCreate(subject="y"))).id
    await _depend(client, loose, [eva["id"]])

    r = await client.get(f"/shots/{loose}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["continuity_state_ready"] is False
    assert body["visual_continuity_ready"] is False
    assert body["visual_reference_pack_hash"] is None
    codes = {i["error_code"] for i in body["visual_continuity_issues"]}
    assert "NARRATIVE_CONTEXT_REQUIRED" in codes
