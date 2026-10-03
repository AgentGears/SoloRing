"""Regressions for defects found by the independent M17C first-pass review."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.m17b_seed import seed_production_object, seed_production_revision
from tests.m17c_seed import ARTICULATION, dialogue_bound_body, make_vp

SQLITE_INT_MIN = -(2**63)
SQLITE_INT_MAX = 2**63 - 1


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


async def _reviewed_retarget_coordinate(client, world, revision_id: str):
    obj = await seed_production_object(
        client, world["project_id"], "M17C first-pass object", b"first-pass")
    p1 = await seed_production_revision(client, obj, b"first-pass-1", 1)
    p2 = await seed_production_revision(client, obj, b"first-pass-2", 2)
    assessment_response = await client.post(
        f"/performance-revisions/{revision_id}/retarget-assessments",
        json={
            "from_production_revision_id": p1["production_revision_id"],
            "to_production_revision_id": p2["production_revision_id"],
        },
    )
    assert assessment_response.status_code == 201, assessment_response.text
    assessment = assessment_response.json()
    assert assessment["overall_verdict"] == "REQUIRES_REVIEW"
    review_response = await client.post(
        f"/performance-retarget-assessments/{assessment['id']}/reviews",
        json={
            "decision": "ACCEPT_FOR_NEW_CANDIDATE",
            "reviewed_by": "reviewer",
            "rationale": None,
        },
    )
    assert review_response.status_code == 201, review_response.text
    return assessment, review_response.json()


@pytest.mark.asyncio
async def test_retarget_missing_revision_binding_fails_closed_without_new_candidate(
    client,
):
    world = await make_vp(client)
    source_candidate = await _create_bound(client, world)
    source_revision = await _adopt(client, source_candidate["id"])
    assessment, review = await _reviewed_retarget_coordinate(
        client, world, source_revision["id"])

    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        before = (await conn.execute(text(
            "SELECT COUNT(*) FROM performance_candidates"
        ))).scalar_one()
        await conn.execute(text(
            "DELETE FROM performance_revision_vocal_bindings "
            "WHERE performance_revision_id=:r"
        ), {"r": source_revision["id"]})

    response = await client.post(
        f"/performance-revisions/{source_revision['id']}/retarget-candidates",
        json={
            "assessment_id": assessment["id"],
            "accepted_review_id": review["id"],
            "producer_id": "m17c-first-pass",
            "producer_version": "1",
            "source_identity": None,
            "parameters_sha256": None,
        },
    )
    assert response.status_code == 500, response.text
    assert response.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"

    async with engine.connect() as conn:
        after = (await conn.execute(text(
            "SELECT COUNT(*) FROM performance_candidates"
        ))).scalar_one()
    assert after == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("origin_num", "origin_den"),
    (
        (SQLITE_INT_MAX + 1, SQLITE_INT_MAX),
        (SQLITE_INT_MIN - 1, SQLITE_INT_MAX),
        (SQLITE_INT_MAX - 2, SQLITE_INT_MAX + 1),
    ),
)
async def test_vocal_origin_outside_sqlite_integer_domain_rejects_before_storage(
    client, origin_num: int, origin_den: int,
):
    world = await make_vp(client)
    body = dialogue_bound_body(
        world["vp"]["id"],
        origin=(origin_num, origin_den),
        articulation_time={key: (2, 1) for key in ARTICULATION},
    )
    response = await client.post(
        f"/creative-entities/{world['subject_id']}/"
        "dialogue-bound-performance-candidates",
        json=body,
    )
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_vocal_origin_sqlite_integer_boundary_is_preserved_exactly(client):
    world = await make_vp(client)
    origin = (SQLITE_INT_MAX, SQLITE_INT_MAX - 1)
    candidate = await _create_bound(
        client,
        world,
        origin=origin,
        articulation_time={key: (2, 1) for key in ARTICULATION},
    )
    binding_response = await client.get(
        f"/performance-candidates/{candidate['id']}/vocal-binding")
    assert binding_response.status_code == 200, binding_response.text
    assert binding_response.json()["performance_origin_ms"] == {
        "num": origin[0],
        "den": origin[1],
    }
