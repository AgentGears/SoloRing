"""M17C-A B01-B07/C01-C05: authority-transition companion laws."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text

from tests.m17a_seed import place_blob, wave_bytes
from tests.m17b_seed import (
    SMILE,
    candidate_body,
    channel as m17b_channel,
    kf as m17b_kf,
    seed_production_object,
    seed_production_revision,
)
from tests.m17c_seed import (
    ARTICULATION,
    dialogue_bound_body,
    make_vp,
)


async def _create_bound(client, world, **kwargs):
    response = await client.post(
        f"/creative-entities/{world['subject_id']}/"
        "dialogue-bound-performance-candidates",
        json=dialogue_bound_body(world["vp"]["id"], **kwargs),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _adopt(client, candidate_id: str):
    response = await client.post(
        f"/performance-candidates/{candidate_id}/adopt",
        json={"adopted_by": "director"},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _same_line_alternate_vp(client, world, frames: int = 144001):
    blob_hash = await place_blob(client, wave_bytes(48000, frames))
    candidate = (await client.post(
        f"/dialogue-line-revisions/{world['dialogue_line_revision_id']}/"
        "vocal-candidates",
        json={
            "retained_audio_blob_hash": blob_hash,
            "source_provenance": {
                "schema_version": 1,
                "source_kind": "recorded",
            },
        },
    )).json()
    response = await client.post(
        f"/vocal-candidates/{candidate['id']}/adopt",
        json={"adopted_by": "director"},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _physical_pair(client, project_id: str, tag: bytes):
    obj = await seed_production_object(client, project_id, "M17C object", tag)
    p1 = await seed_production_revision(client, obj, tag + b"-1", 1)
    p2 = await seed_production_revision(client, obj, tag + b"-2", 2)
    return p1, p2


async def _reviewed_assessment(client, revision_id: str, p1: dict, p2: dict):
    assessment = (await client.post(
        f"/performance-revisions/{revision_id}/retarget-assessments",
        json={
            "from_production_revision_id": p1["production_revision_id"],
            "to_production_revision_id": p2["production_revision_id"],
        },
    )).json()
    assert assessment["overall_verdict"] == "REQUIRES_REVIEW"
    review = (await client.post(
        f"/performance-retarget-assessments/{assessment['id']}/reviews",
        json={
            "decision": "ACCEPT_FOR_NEW_CANDIDATE",
            "reviewed_by": "reviewer",
            "rationale": None,
        },
    )).json()
    return assessment, review


async def _retarget(client, revision_id: str, assessment: dict, review: dict):
    return await client.post(
        f"/performance-revisions/{revision_id}/retarget-candidates",
        json={
            "assessment_id": assessment["id"],
            "accepted_review_id": review["id"],
            "producer_id": "m17c-retarget",
            "producer_version": "1",
            "source_identity": None,
            "parameters_sha256": None,
        },
    )


@pytest.mark.asyncio
async def test_b01_candidate_and_binding_creation_is_atomic(client):
    world = await make_vp(client)
    body = dialogue_bound_body(world["vp"]["id"], omit=ARTICULATION[0])
    response = await client.post(
        f"/creative-entities/{world['subject_id']}/"
        "dialogue-bound-performance-candidates",
        json=body,
    )
    assert response.status_code == 422
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        candidates = (await conn.execute(text(
            "SELECT COUNT(*) FROM performance_candidates WHERE subject_id=:s"),
            {"s": world["subject_id"]})).scalar()
        bindings = (await conn.execute(text(
            "SELECT COUNT(*) FROM performance_candidate_vocal_bindings"))).scalar()
    assert candidates == 0
    assert bindings == 0


@pytest.mark.asyncio
async def test_b02_adoption_copies_exact_candidate_binding_closure(client):
    world = await make_vp(client)
    candidate = await _create_bound(client, world)
    cb = (await client.get(
        f"/performance-candidates/{candidate['id']}/vocal-binding")).json()
    revision = await _adopt(client, candidate["id"])
    rb = (await client.get(
        f"/performance-revisions/{revision['id']}/vocal-binding")).json()
    for field in (
        "vocal_performance_revision_id", "source_start_sample",
        "source_end_sample_exclusive", "sample_rate_hz",
        "performance_origin_ms", "synchronization_basis_version",
        "binding_schema_version", "binding_hash",
    ):
        assert rb[field] == cb[field]


@pytest.mark.asyncio
async def test_b03_sequential_duplicate_adoption_returns_same_revision_and_binding(client):
    world = await make_vp(client)
    candidate = await _create_bound(client, world)
    r1 = await _adopt(client, candidate["id"])
    b1 = (await client.get(
        f"/performance-revisions/{r1['id']}/vocal-binding")).json()
    r2 = await _adopt(client, candidate["id"])
    b2 = (await client.get(
        f"/performance-revisions/{r2['id']}/vocal-binding")).json()
    assert r2["id"] == r1["id"]
    assert r2["adoption_id"] == r1["adoption_id"]
    assert b2 == b1


@pytest.mark.asyncio
async def test_b04_concurrent_duplicate_adoption_converges_one_revision_one_binding(client):
    world = await make_vp(client)
    candidate = await _create_bound(client, world)
    a, b = await asyncio.gather(
        client.post(
            f"/performance-candidates/{candidate['id']}/adopt",
            json={"adopted_by": "a"}),
        client.post(
            f"/performance-candidates/{candidate['id']}/adopt",
            json={"adopted_by": "b"}),
    )
    assert a.status_code == 200, a.text
    assert b.status_code == 200, b.text
    assert a.json()["id"] == b.json()["id"]
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        revisions = (await conn.execute(text(
            "SELECT COUNT(*) FROM performance_revisions WHERE "
            "adopted_candidate_id=:c"), {"c": candidate["id"]})).scalar()
        bindings = (await conn.execute(text(
            "SELECT COUNT(*) FROM performance_revision_vocal_bindings "
            "WHERE performance_revision_id=:r"),
            {"r": a.json()["id"]})).scalar()
    assert revisions == 1
    assert bindings == 1


@pytest.mark.asyncio
async def test_b05_winner_revalidation_rejects_missing_revision_binding(client):
    world = await make_vp(client)
    candidate = await _create_bound(client, world)
    revision = await _adopt(client, candidate["id"])
    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        await conn.execute(text(
            "DELETE FROM performance_revision_vocal_bindings "
            "WHERE performance_revision_id=:r"), {"r": revision["id"]})
    response = await client.post(
        f"/performance-candidates/{candidate['id']}/adopt",
        json={"adopted_by": "again"},
    )
    assert response.status_code == 500
    assert response.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"


@pytest.mark.asyncio
async def test_b06_generic_m17b_candidate_and_adoption_remain_valid_without_binding(client):
    world = await make_vp(client)
    response = await client.post(
        f"/creative-entities/{world['subject_id']}/performance-candidates",
        json=candidate_body([
            m17b_channel(SMILE, [m17b_kf(0, 1, 0)])
        ]),
    )
    assert response.status_code == 201, response.text
    revision = await _adopt(client, response.json()["id"])
    missing = await client.get(
        f"/performance-revisions/{revision['id']}/vocal-binding")
    assert missing.status_code == 404
    assert missing.json()["error_code"] == "PERFORMANCE_VOCAL_BINDING_NOT_FOUND"


@pytest.mark.asyncio
async def test_b07_current_vp_selection_change_never_mutates_revision_binding(client):
    world = await make_vp(client)
    candidate = await _create_bound(client, world)
    revision = await _adopt(client, candidate["id"])
    before = (await client.get(
        f"/performance-revisions/{revision['id']}/vocal-binding")).json()
    alternate = await _same_line_alternate_vp(client, world)
    selected = await client.put(
        f"/dialogue-line-revisions/{world['dialogue_line_revision_id']}/"
        "vocal-selection",
        json={
            "vocal_performance_revision_id": alternate["id"],
            "selected_by": "director",
        },
    )
    assert selected.status_code == 200, selected.text
    after = (await client.get(
        f"/performance-revisions/{revision['id']}/vocal-binding")).json()
    assert after == before
    assert after["vocal_performance_revision_id"] == world["vp"]["id"]


@pytest.mark.asyncio
async def test_c01_retarget_non_dialogue_revision_preserves_m17b_behavior(client):
    world = await make_vp(client)
    candidate_response = await client.post(
        f"/creative-entities/{world['subject_id']}/performance-candidates",
        json=candidate_body([
            m17b_channel(SMILE, [m17b_kf(0, 1, 0)])
        ]),
    )
    revision = await _adopt(client, candidate_response.json()["id"])
    p1, p2 = await _physical_pair(client, world["project_id"], b"c01")
    assessment, review = await _reviewed_assessment(
        client, revision["id"], p1, p2)
    retarget = await _retarget(client, revision["id"], assessment, review)
    assert retarget.status_code == 201, retarget.text
    missing = await client.get(
        f"/performance-candidates/{retarget.json()['id']}/vocal-binding")
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_c02_retarget_dialogue_revision_copies_exact_vocal_binding(client):
    world = await make_vp(client)
    source_candidate = await _create_bound(client, world)
    source_revision = await _adopt(client, source_candidate["id"])
    source_binding = (await client.get(
        f"/performance-revisions/{source_revision['id']}/vocal-binding")).json()
    p1, p2 = await _physical_pair(client, world["project_id"], b"c02")
    assessment, review = await _reviewed_assessment(
        client, source_revision["id"], p1, p2)
    retarget = await _retarget(
        client, source_revision["id"], assessment, review)
    assert retarget.status_code == 201, retarget.text
    candidate_binding = (await client.get(
        f"/performance-candidates/{retarget.json()['id']}/vocal-binding")).json()
    for field in (
        "vocal_performance_revision_id", "source_start_sample",
        "source_end_sample_exclusive", "sample_rate_hz",
        "performance_origin_ms", "synchronization_basis_version",
        "binding_schema_version", "binding_hash",
    ):
        assert candidate_binding[field] == source_binding[field]


@pytest.mark.asyncio
async def test_c03_retarget_cannot_drop_source_vocal_binding(client):
    world = await make_vp(client)
    source_candidate = await _create_bound(client, world)
    source_revision = await _adopt(client, source_candidate["id"])
    p1, p2 = await _physical_pair(client, world["project_id"], b"c03")
    assessment, review = await _reviewed_assessment(
        client, source_revision["id"], p1, p2)
    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        await conn.execute(text(
            "DELETE FROM performance_candidate_vocal_bindings "
            "WHERE performance_candidate_id=:c"),
            {"c": source_candidate["id"]})
    retarget = await _retarget(
        client, source_revision["id"], assessment, review)
    assert retarget.status_code == 500
    assert retarget.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"


@pytest.mark.asyncio
async def test_c04_retarget_never_substitutes_current_selected_vp(client):
    world = await make_vp(client)
    source_candidate = await _create_bound(client, world)
    source_revision = await _adopt(client, source_candidate["id"])
    alternate = await _same_line_alternate_vp(client, world)
    selected = await client.put(
        f"/dialogue-line-revisions/{world['dialogue_line_revision_id']}/"
        "vocal-selection",
        json={
            "vocal_performance_revision_id": alternate["id"],
            "selected_by": "director",
        },
    )
    assert selected.status_code == 200
    p1, p2 = await _physical_pair(client, world["project_id"], b"c04")
    assessment, review = await _reviewed_assessment(
        client, source_revision["id"], p1, p2)
    retarget = await _retarget(
        client, source_revision["id"], assessment, review)
    assert retarget.status_code == 201, retarget.text
    binding = (await client.get(
        f"/performance-candidates/{retarget.json()['id']}/vocal-binding")).json()
    assert binding["vocal_performance_revision_id"] == world["vp"]["id"]
    assert binding["vocal_performance_revision_id"] != alternate["id"]


@pytest.mark.asyncio
async def test_c05_corrupted_source_binding_blocks_retarget_authority_live(client):
    world = await make_vp(client)
    source_candidate = await _create_bound(client, world)
    source_revision = await _adopt(client, source_candidate["id"])
    p1, p2 = await _physical_pair(client, world["project_id"], b"c05")
    assessment, review = await _reviewed_assessment(
        client, source_revision["id"], p1, p2)
    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE performance_revision_vocal_bindings "
            "SET binding_hash=:h WHERE performance_revision_id=:r"),
            {"h": "0" * 64, "r": source_revision["id"]})
    retarget = await _retarget(
        client, source_revision["id"], assessment, review)
    assert retarget.status_code == 500
    assert retarget.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"
