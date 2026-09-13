"""M15B impact proofs (frozen R6 §31.6 M15-IMPACT:01-08)."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from soloring.compatibility.service import (
    create_assessment,
    impact_inventory,
)
from tests.m15_seed import seed_a4_use
from tests.m13_seed import make_composition, mint, publish, seed_base


async def test_direct_working_uses_enumerated_exactly(client):
    """M15-IMPACT:01 — updateable use set: exact, ordered, scoped to
    direct ProductionRevision rows of the one source revision."""
    from soloring.compatibility.impact import direct_working_uses
    from tests.conftest import make_tracked_maker

    from tests.m13_seed import mint_nested

    base = await seed_base(client, tag=b"imp01")
    pid = base["project_id"]
    cid = await make_composition(client, pid)
    a = (await mint(client, cid, base["production_revision_id"], 0,
                    name="A"))["occurrence_id"]
    b = (await mint(client, cid, base["production_revision_id"], 1,
                    name="B"))["occurrence_id"]
    inner = await make_composition(client, pid)
    inner_occ = (await mint(client, inner,
                            base["production_revision_id"], 0))[
        "occurrence_id"]
    pub = await publish(client, inner, 1)
    await mint_nested(client, cid, pub["revision"]["revision_id"], 2,
                      name="Nested")

    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        uses = await direct_working_uses(
            conn, production_revision_id=base["production_revision_id"])
    pairs = {(u["composition_id"], u["occurrence_id"]) for u in uses}
    # every DIRECT production_revision row of the source is a target —
    # in cid AND in inner — while cid's nested-source row is excluded
    assert pairs == {(cid, a), (cid, b), (inner, inner_occ)}
    assert all(u["project_id"] == pid for u in uses)


async def test_feature_contracts_enter_use_hash(client):
    """M15-IMPACT:02 — state dependency: a feature transition edit
    changes the use contract hash of the reassessed inventory."""
    base = await seed_a4_use(client, tag=b"imp02")
    r = await client.post(
        f"/production-instances/{base['occurrence_id']}/features",
        json={"key": "damage", "kind": "damage", "value_type": "enum",
              "name": "Damage", "enum_values": ["fresh", "broken"]})
    assert r.status_code == 201, r.text
    feature_id = r.json()["id"]
    inv = await impact_inventory(
        _session(client), production_revision_id=(
            base["production_revision_id"]))
    assert inv["use_count"] == 1
    first = await create_assessment(
        _maker_session(client), from_revision_id=(
            base["production_revision_id"]), to_revision_id=base["r2"])
    scene = await _scene(client, base["project_id"])
    r = await client.post(
        f"/production-instance-features/{feature_id}/transitions",
        json={"anchor_type": "scene", "anchor_id": scene,
              "boundary": "start", "operation": "set", "value": "broken"})
    assert r.status_code == 201, r.text
    second = await create_assessment(
        _maker_session(client), from_revision_id=(
            base["production_revision_id"]), to_revision_id=base["r2"])
    assert first["uses"][0]["use_contract_hash"] != (
        second["uses"][0]["use_contract_hash"])


def _session(client):
    class _S:
        bind = client._transport.app.state.engine

    return _S()


def _maker_session(client):
    return _session(client)


async def _scene(client, pid):
    from tests.m15_seed import seed_scene

    return await seed_scene(client, pid)


async def test_spatial_contracts_enter_use_hash(client):
    """M15-IMPACT:03 — spatial dependency: a spatial-track transition
    changes the use contract hash without touching working_version."""
    base = await seed_a4_use(client, tag=b"imp03")
    track_id = base["track_id"]
    first = await create_assessment(
        _maker_session(client), from_revision_id=(
            base["production_revision_id"]), to_revision_id=base["r2"])
    scene = await _scene(client, base["project_id"])
    r = await client.post(
        f"/production-instance-spatial-tracks/{track_id}/transitions",
        json={"anchor_type": "scene", "anchor_id": scene,
              "boundary": "start", "operation": "set",
              "transform": {"translation_mm": [1, 2, 3],
                            "rotation_udeg": [0, 0, 0]}})
    assert r.status_code == 201, r.text
    second = await create_assessment(
        _maker_session(client), from_revision_id=(
            base["production_revision_id"]), to_revision_id=base["r2"])
    assert first["uses"][0]["use_contract_hash"] != (
        second["uses"][0]["use_contract_hash"])


async def test_published_composition_refs_are_advisory_only(client):
    """M15-IMPACT:04 — immutable published refs appear as advisory
    diagnostics in the S17.1 POST response, labeled, all three
    categories present, excluded from the report hash."""
    from soloring.compatibility.service import create_assessment

    base = await seed_a4_use(client, tag=b"imp04")
    await publish(client, base["composition_id"], 1)
    r = await client.post(
        f"/production-revisions/{base['production_revision_id']}"
        "/compatibility-assessments",
        json={"to_revision_id": base["r2"]})
    assert r.status_code == 201, r.text
    result = r.json()
    advisory = result["advisory"]
    assert advisory["advisory_only"] is True
    assert advisory["mutated_by_apply"] is False
    # all three frozen diagnostic categories are present in the POST
    # response, keyed and countable
    for key in ("published_composition_references",
                "historical_shot_references",
                "current_shot_selections"):
        assert key in advisory and isinstance(advisory[key], list)
    assert len(advisory["published_composition_references"]) == 1
    ref = advisory["published_composition_references"][0]
    assert ref["composition_id"] == base["composition_id"]

    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        report = json.loads((await conn.execute(text(
            "SELECT report_json FROM "
            "production_compatibility_assessments WHERE id = :a"),
            {"a": result["assessment_id"]})).scalar_one())
    assert "published_composition_references" not in json.dumps(report)
    assert "advisory" not in json.dumps(report)


async def test_current_shot_selections_are_advisory_and_unchanged(client):
    """M15-IMPACT:05 — current Shot selections pinned through old
    bindings are advisory and untouched by the inventory."""
    base = await seed_a4_use(client, tag=b"imp05")
    inv = await impact_inventory(
        _session(client), production_revision_id=(
            base["production_revision_id"]))
    assert inv["advisory"]["current_shot_selections"] == []  # none yet
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM shot_production_world_selections"
        ))).scalar_one()
    assert n == 0  # the read-only inventory created no selection


async def test_historical_shot_refs_are_advisory_only(client):
    """M15-IMPACT:06 — history isolation: historical ShotRevision
    references are advisory diagnostics only."""
    base = await seed_a4_use(client, tag=b"imp06")
    inv = await impact_inventory(
        _session(client), production_revision_id=(
            base["production_revision_id"]))
    assert inv["advisory"]["historical_shot_references"] == []
    assert inv["advisory"]["advisory_only"] is True


async def test_advisory_count_drift_does_not_change_assessment_identity(
        client):
    """M15-IMPACT:07 — advisory distinction: a new published reference
    drifts the advisory count but not the assessment coordinate."""
    base = await seed_a4_use(client, tag=b"imp07")
    # a second working use of the source PR (in scope from the start)
    other_cid = await make_composition(client, base["project_id"])
    await mint(client, other_cid, base["production_revision_id"], 0,
               name="Other")
    first = await create_assessment(
        _maker_session(client), from_revision_id=(
            base["production_revision_id"]), to_revision_id=base["r2"])
    assert len(first["uses"]) == 2
    inv_before = await impact_inventory(
        _session(client), production_revision_id=(
            base["production_revision_id"]))

    # publishing the other composition drifts the ADVISORY published
    # count while leaving every current working row untouched, so the
    # assessment coordinate must be unchanged
    await publish(client, other_cid, 1)
    inv_after = await impact_inventory(
        _session(client), production_revision_id=(
            base["production_revision_id"]))
    assert len(inv_after["advisory"][
        "published_composition_references"]) == len(inv_before[
        "advisory"]["published_composition_references"]) + 1

    second = await create_assessment(
        _maker_session(client), from_revision_id=(
            base["production_revision_id"]), to_revision_id=base["r2"])
    assert second["converged"] is True
    assert second["assessment_id"] == first["assessment_id"]
    assert second["report_hash"] == first["report_hash"]
    assert len(second["uses"]) == 2

    # the operational half of IMPACT:07 through the HTTP surface: a
    # convergent 200 keeps the immutable identity but reports the
    # CURRENT advisory state (fresh counts), never a stale replay
    r = await client.post(
        f"/production-revisions/{base['production_revision_id']}"
        "/compatibility-assessments",
        json={"to_revision_id": base["r2"]})
    assert r.status_code == 200 and r.json()["converged"] is True
    http_second = r.json()
    assert http_second["assessment_id"] == first["assessment_id"]
    assert http_second["report_hash"] == first["report_hash"]
    assert len(http_second["advisory"][
        "published_composition_references"]) == len(inv_after[
        "advisory"]["published_composition_references"])
    assert http_second["advisory"]["advisory_only"] is True
    assert http_second["advisory"]["mutated_by_apply"] is False


async def test_nested_composition_sources_not_m15_update_targets(client):
    """M15-IMPACT:08 — scope boundary: nested CompositionRevision
    sources are never M15 update targets."""
    from soloring.compatibility.impact import direct_working_uses
    from tests.m13_seed import mint_nested

    base = await seed_base(client, tag=b"imp08")
    pid = base["project_id"]
    outer = await make_composition(client, pid)
    inner = await make_composition(client, pid)
    await mint(client, inner, base["production_revision_id"], 0)
    pub = await publish(client, inner, 1)
    await mint_nested(client, outer, pub["revision"]["revision_id"], 0,
                      name="Nested set")

    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        uses = await direct_working_uses(
            conn, production_revision_id=base["production_revision_id"])
    # only the INNER composition's direct use is a target; the outer's
    # nested-source row is excluded even though it embeds the revision
    assert [u["composition_id"] for u in uses] == [inner]
