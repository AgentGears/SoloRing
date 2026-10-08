"""M17C-A A01-A17: PF-03 dialogue-bound binding authority."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.m17b_seed import make_entity, make_project
from tests.m17c_seed import (
    ARTICULATION,
    dialogue_bound_body,
    make_alignment,
    make_vp,
)


async def _post(client, subject_id: str, body: dict):
    return await client.post(
        f"/creative-entities/{subject_id}/dialogue-bound-performance-candidates",
        json=body,
    )


@pytest.mark.asyncio
async def test_a01_dialogue_bound_candidate_rejects_body_kind(client):
    world = await make_vp(client)
    body = dialogue_bound_body(world["vp"]["id"])
    body["performance_kind"] = "BODY"
    response = await _post(client, world["subject_id"], body)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_a02_exact_vp_speaker_project_passes(client):
    world = await make_vp(client)
    response = await _post(
        client, world["subject_id"], dialogue_bound_body(world["vp"]["id"]))
    assert response.status_code == 201, response.text
    binding = await client.get(
        f"/performance-candidates/{response.json()['id']}/vocal-binding")
    assert binding.status_code == 200
    assert binding.json()["vocal_performance_revision_id"] == world["vp"]["id"]


@pytest.mark.asyncio
async def test_a03_vp_speaker_mismatch_rejects(client):
    world = await make_vp(client)
    other = await make_entity(client, world["project_id"], "Other")
    response = await _post(
        client, other, dialogue_bound_body(world["vp"]["id"]))
    assert response.status_code == 422
    assert response.json()["error_code"] == "PERFORMANCE_VOCAL_SUBJECT_MISMATCH"


@pytest.mark.asyncio
async def test_a04_cross_project_vp_chain_rejects(client):
    world = await make_vp(client)
    p2 = await make_project(client, name="M17C other project")
    e2 = await make_entity(client, p2, "Other")
    response = await _post(
        client, e2, dialogue_bound_body(world["vp"]["id"]))
    assert response.status_code == 422
    assert response.json()["error_code"] == "PERFORMANCE_VOCAL_PROJECT_MISMATCH"


@pytest.mark.asyncio
async def test_a05_missing_vp_rejects(client):
    pid = await make_project(client, name="M17C missing VP")
    eid = await make_entity(client, pid)
    response = await _post(
        client,
        eid,
        dialogue_bound_body("55555555-5555-4555-8555-555555555555"),
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "VOCAL_PERFORMANCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_a06_corrupted_vp_adopted_candidate_closure_rejects(client):
    world = await make_vp(client)
    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE vocal_performance_revisions SET provenance_hash = :h "
            "WHERE id = :v"), {"h": "b" * 64, "v": world["vp"]["id"]})
    response = await _post(
        client, world["subject_id"], dialogue_bound_body(world["vp"]["id"]))
    assert response.status_code == 500
    assert response.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"


@pytest.mark.asyncio
async def test_a07_corrupted_retained_vp_audio_bytes_rejects(client):
    world = await make_vp(client)
    from soloring.assets.blob_store import BlobStore
    store = BlobStore(client._transport.app.state.settings)
    store.path_for_hash(world["blob_hash"]).write_bytes(b"corrupt")
    response = await _post(
        client, world["subject_id"], dialogue_bound_body(world["vp"]["id"]))
    assert response.status_code == 500
    assert response.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"


@pytest.mark.asyncio
async def test_a08_noncanonical_sync_rational_rejects(client):
    world = await make_vp(client)
    body = dialogue_bound_body(world["vp"]["id"], origin=(0, 2))
    response = await _post(client, world["subject_id"], body)
    assert response.status_code == 422
    assert response.json()["error_code"] == "PERFORMANCE_VOCAL_BINDING_INVALID"


@pytest.mark.asyncio
async def test_a09_source_interval_outside_vp_trim_rejects(client):
    world = await make_vp(client, frames=144000)
    body = dialogue_bound_body(
        world["vp"]["id"], source_start=48000, source_end=144001,
        end=(4000, 1))
    response = await _post(client, world["subject_id"], body)
    assert response.status_code == 422
    assert response.json()["error_code"] == "PERFORMANCE_VOCAL_INTERVAL_INVALID"


@pytest.mark.asyncio
async def test_a10_induced_performance_interval_outside_domain_rejects(client):
    world = await make_vp(client, frames=144000)
    body = dialogue_bound_body(
        world["vp"]["id"], source_start=48000, source_end=144000,
        end=(1500, 1))
    response = await _post(client, world["subject_id"], body)
    assert response.status_code == 422
    assert response.json()["error_code"] == "PERFORMANCE_VOCAL_INTERVAL_INVALID"


@pytest.mark.asyncio
async def test_a11_four_required_articulation_channels_inside_interval_pass(client):
    world = await make_vp(client)
    response = await _post(
        client, world["subject_id"], dialogue_bound_body(world["vp"]["id"]))
    assert response.status_code == 201, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ARTICULATION)
async def test_a12_each_missing_required_articulation_channel_rejects(
        client, missing):
    world = await make_vp(client)
    response = await _post(
        client,
        world["subject_id"],
        dialogue_bound_body(world["vp"]["id"], omit=missing),
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == \
        "PERFORMANCE_REQUIRED_ARTICULATION_MISSING"


@pytest.mark.asyncio
async def test_a13_required_articulation_only_outside_sync_interval_rejects(client):
    world = await make_vp(client)
    body = dialogue_bound_body(
        world["vp"]["id"],
        articulation_time={ARTICULATION[0]: (-100, 1)},
    )
    response = await _post(client, world["subject_id"], body)
    assert response.status_code == 422
    assert response.json()["error_code"] == \
        "PERFORMANCE_REQUIRED_ARTICULATION_MISSING"


@pytest.mark.asyncio
async def test_a14_pre_post_expression_outside_vocal_interval_is_lawful(client):
    world = await make_vp(client)
    body = dialogue_bound_body(
        world["vp"]["id"], pre_post_expression=True)
    response = await _post(client, world["subject_id"], body)
    assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_a15_authored_candidate_needs_no_alignment(client):
    world = await make_vp(client)
    response = await _post(
        client, world["subject_id"], dialogue_bound_body(world["vp"]["id"]))
    assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_a16_alignment_for_exact_bound_vp_passes(client):
    world = await make_vp(client)
    alignment = await make_alignment(
        client, world["vp"]["id"], world["blob_hash"], suffix="a16")
    body = dialogue_bound_body(
        world["vp"]["id"],
        alignment_by_channel={ARTICULATION[0]: alignment["id"]},
    )
    response = await _post(client, world["subject_id"], body)
    assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_a17_alignment_for_different_vp_rejects_even_same_subject_project(client):
    world1 = await make_vp(client, frames=144000)
    world2 = await make_vp(
        client,
        pid=world1["project_id"],
        eid=world1["subject_id"],
        frames=144001,
        tag=b"a17-second",
    )
    alignment = await make_alignment(
        client, world2["vp"]["id"], world2["blob_hash"], suffix="a17")
    body = dialogue_bound_body(
        world1["vp"]["id"],
        alignment_by_channel={ARTICULATION[0]: alignment["id"]},
    )
    response = await _post(client, world1["subject_id"], body)
    assert response.status_code == 422
    assert response.json()["error_code"] == "PERFORMANCE_VOCAL_ALIGNMENT_MISMATCH"
