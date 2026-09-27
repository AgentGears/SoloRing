"""M17C-B D01–D16 + regressions: Shot Performance working mappings
and readiness (frozen R4 §8–§9)."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.m17a_seed import make_shot, place_blob, wave_bytes
from tests.m17b_seed import (
    SMILE,
    HEAD_YAW,
    candidate_body,
    channel as m17b_channel,
    kf as m17b_kf,
    make_entity,
    make_project,
)
from tests.m17c_seed import (
    ARTICULATION,
    dialogue_bound_body,
    make_vp,
)


async def _put_seg(client, shot, position, pr_id, start, end, anchor,
                  vocal_position=None, num=1, den=1):
    return await client.put(
        f"/shots/{shot}/performance-segments/{position}",
        json={
            "performance_revision_id": pr_id,
            "performance_start_ms": {"num": start[0] * num // 1
                                    if isinstance(start, tuple)
                                    else start, "den": den},
            "performance_end_ms": {"num": end, "den": den},
            "shot_anchor_ms": {"num": anchor, "den": den},
            "vocal_mapping_position": vocal_position,
        })


def _seg_body(pr_id, s, e, a, vp=None, den=1):
    return {
        "performance_revision_id": pr_id,
        "performance_start_ms": {"num": s, "den": den},
        "performance_end_ms": {"num": e, "den": den},
        "shot_anchor_ms": {"num": a, "den": den},
        "vocal_mapping_position": vp,
    }


async def _add_dependency(client, shot_id, entity_id, role="subject"):
    r = await client.put(
        f"/shots/{shot_id}/semantic-dependencies",
        json={"dependencies": [
            {"entity_id": entity_id, "role": role}]})
    assert r.status_code == 200, r.text


async def _bound_world(client, *, duration=3000):
    """Lawful dialogue-bound world: VP adopted+selected, vocal mapping
    on the shot, PF-03 candidate adopted, subject a shot dependency."""
    world = await make_vp(client)
    await client.put(
        f"/dialogue-line-revisions/{world['dialogue_line_revision_id']}/"
        "vocal-selection",
        json={"vocal_performance_revision_id": world["vp"]["id"],
              "selected_by": "d"})
    shot = await make_shot(client, world["project_id"], duration)
    await _add_dependency(client, shot, world["subject_id"])
    # vocal segment [48000, 96000) anchored at 0
    r = await client.put(
        f"/shots/{shot}/vocal-segments/0",
        json={
            "vocal_performance_revision_id": world["vp"]["id"],
            "source_start_sample": 48000,
            "source_end_sample_exclusive": 96000,
            "sample_rate_hz": 48000,
            "performance_origin_ms": {"num": 0, "den": 1},
            "shot_anchor_ms": {"num": 0, "den": 1},
        })
    assert r.status_code == 200, r.text
    candidate = (await client.post(
        f"/creative-entities/{world['subject_id']}/"
        "dialogue-bound-performance-candidates",
        json=dialogue_bound_body(
            world["vp"]["id"],
            articulation_time={key: (600, 1) for key in ARTICULATION}),
    )).json()
    pr = (await client.post(
        f"/performance-candidates/{candidate['id']}/adopt",
        json={"adopted_by": "d"})).json()
    world["shot"] = shot
    world["candidate"] = candidate
    world["pr"] = pr
    return world


async def _generic_world(client, *, duration=3000, body=None):
    world = await make_vp(client)
    shot = await make_shot(client, world["project_id"], duration)
    await _add_dependency(client, shot, world["subject_id"])
    candidate = (await client.post(
        f"/creative-entities/{world['subject_id']}/performance-candidates",
        json=body or candidate_body(
            [m17b_channel(SMILE, [m17b_kf(0, 1, 0)])]),
    )).json()
    pr = (await client.post(
        f"/performance-candidates/{candidate['id']}/adopt",
        json={"adopted_by": "d"})).json()
    world["shot"] = shot
    world["pr"] = pr
    return world


def _code(resp):
    return resp.json().get("error_code")


# ---------------------------------------------------------------------------
# D01–D05: generic mappings and interval laws
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_d01_generic_mapping_inside_domain_passes(client):
    world = await _generic_world(client)
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 2000, 0))
    assert r.status_code == 200, r.text
    readiness = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert readiness["ready"] is True
    assert readiness["segments"][0]["readiness"] == "READY"


@pytest.mark.asyncio
async def test_d02_mapping_outside_pr_domain_rejects(client):
    world = await _generic_world(client)
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 6000, 0))
    assert r.status_code == 422, r.text
    assert _code(r) == "PERFORMANCE_SHOT_MAPPING_INVALID"


@pytest.mark.asyncio
async def test_d03_no_picture_intersection_rejects(client):
    world = await _generic_world(client)
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 2000, 5000))
    assert r.status_code == 422, r.text
    assert _code(r) == "MAPPING_NO_SHOT_OVERLAP"


@pytest.mark.asyncio
async def test_d04_negative_anchor_jcut_passes(client):
    world = await _generic_world(client)
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 2000, -250))
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_d05_lcut_ending_after_picture_passes(client):
    world = await _generic_world(client)
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 4500, 2000))
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# D06–D10: dialogue-bound induced-interval laws
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_d06_dialogue_bound_requires_vocal_position(client):
    world = await _bound_world(client)
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 1000, 0))
    assert r.status_code == 422, r.text
    assert _code(r) == "PERFORMANCE_VOCAL_MAPPING_REQUIRED"


@pytest.mark.asyncio
async def test_d07_paired_vocal_mapping_vp_mismatch_rejects(client):
    # another VP on the same line, mapped on vocal position 1
    from tests.test_m17c_binding_transitions import _same_line_alternate_vp
    world = await _bound_world(client)
    alternate = await _same_line_alternate_vp(client, world)
    # the alternate must be current for M17A's vocal PUT to accept it
    await client.put(
        f"/dialogue-line-revisions/{world['dialogue_line_revision_id']}/"
        "vocal-selection",
        json={"vocal_performance_revision_id": alternate["id"],
              "selected_by": "d"})
    r = await client.put(
        f"/shots/{world['shot']}/vocal-segments/1",
        json={
            "vocal_performance_revision_id": alternate["id"],
            "source_start_sample": 0,
            "source_end_sample_exclusive": 48000,
            "sample_rate_hz": 48000,
            "performance_origin_ms": {"num": 0, "den": 1},
            "shot_anchor_ms": {"num": 0, "den": 1},
        })
    assert r.status_code == 200, r.text
    # restore the original as current so the bound PR's own line is
    # back to its lawful selection posture
    await client.put(
        f"/dialogue-line-revisions/{world['dialogue_line_revision_id']}/"
        "vocal-selection",
        json={"vocal_performance_revision_id": world["vp"]["id"],
              "selected_by": "d"})
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 1000, 0,
                       vp=1))
    assert r.status_code == 422, r.text
    assert _code(r) == "PERFORMANCE_VOCAL_MAPPING_MISMATCH"
    # "different VP" message
    assert "!= the immutable revision binding VP" in r.json()["message"]


@pytest.mark.asyncio
async def test_d08_vocal_mapping_outside_binding_rejects(client):
    # vocal mapping spanning [0, 96000): starts before the binding's
    # source_start (48000)
    world = await make_vp(client)
    await client.put(
        f"/dialogue-line-revisions/{world['dialogue_line_revision_id']}/"
        "vocal-selection",
        json={"vocal_performance_revision_id": world["vp"]["id"],
              "selected_by": "d"})
    shot = await make_shot(client, world["project_id"], 3000)
    await _add_dependency(client, shot, world["subject_id"])
    r = await client.put(
        f"/shots/{shot}/vocal-segments/0",
        json={
            "vocal_performance_revision_id": world["vp"]["id"],
            "source_start_sample": 0,
            "source_end_sample_exclusive": 96000,
            "sample_rate_hz": 48000,
            "performance_origin_ms": {"num": 0, "den": 1},
            "shot_anchor_ms": {"num": 0, "den": 1},
        })
    assert r.status_code == 200, r.text
    candidate = (await client.post(
        f"/creative-entities/{world['subject_id']}/"
        "dialogue-bound-performance-candidates",
        json=dialogue_bound_body(
            world["vp"]["id"],
            articulation_time={key: (600, 1) for key in ARTICULATION}),
    )).json()
    pr = (await client.post(
        f"/performance-candidates/{candidate['id']}/adopt",
        json={"adopted_by": "d"})).json()
    r = await client.put(
        f"/shots/{shot}/performance-segments/0",
        json=_seg_body(pr["id"], 0, 1000, 0, vp=0))
    assert r.status_code == 422, r.text
    assert _code(r) == "PERFORMANCE_VOCAL_MAPPING_MISMATCH"
    assert "outside the immutable revision binding" in r.json()["message"]


@pytest.mark.asyncio
async def test_d09_exact_induced_interval_and_anchor_pass(client):
    world = await _bound_world(client)
    # binding origin 0, vocal [48000, 96000) @48kHz -> [1000, 2000) ms
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 1000, 0,
                       vp=0))
    assert r.status_code == 200, r.text
    readiness = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert readiness["ready"] is True
    seg = readiness["segments"][0]
    assert seg["readiness"] == "READY"
    assert seg["vocal_mapping_position"] == 0


@pytest.mark.asyncio
async def test_d10_one_rational_unit_mismatch_rejects(client):
    world = await _bound_world(client)
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 1, 1000, 0,
                       vp=0))
    assert r.status_code == 422, r.text
    assert _code(r) == "PERFORMANCE_VOCAL_MAPPING_MISMATCH"
    assert "no tolerance" in r.json()["message"]
    # anchor mismatch also rejects
    r2 = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 1000, 1,
                       vp=0))
    assert r2.status_code == 422, r2.text


# ---------------------------------------------------------------------------
# D11–D12: STALE selection projection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_d11_selection_change_projects_stale(client):
    from tests.test_m17c_binding_transitions import _same_line_alternate_vp
    world = await _bound_world(client)
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 1000, 0,
                       vp=0))
    assert r.status_code == 200, r.text
    before = (await client.get(
        f"/shots/{world['shot']}/performance-segments")).json()

    alternate = await _same_line_alternate_vp(client, world)
    await client.put(
        f"/dialogue-line-revisions/{world['dialogue_line_revision_id']}/"
        "vocal-selection",
        json={"vocal_performance_revision_id": alternate["id"],
              "selected_by": "d"})

    readiness = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert readiness["ready"] is False
    assert readiness["segments"][0]["readiness"] == "STALE_VOCAL_SELECTION"
    diag = readiness["segments"][0]["readiness_diagnostics"]
    assert diag["selected_vocal_performance_revision_id"] == alternate["id"]

    # the mapping rows are never mutated by the selection change
    after = (await client.get(
        f"/shots/{world['shot']}/performance-segments")).json()
    for a, b in zip(before, after):
        assert {k: a[k] for k in ("mapping_hash", "performance_start_ms",
                                   "performance_end_ms", "shot_anchor_ms",
                                   "vocal_mapping_position")} == \
            {k: b[k] for k in ("mapping_hash", "performance_start_ms",
                                "performance_end_ms", "shot_anchor_ms",
                                "vocal_mapping_position")}


@pytest.mark.asyncio
async def test_d12_restoring_exact_vp_restores_readiness(client):
    from tests.test_m17c_binding_transitions import _same_line_alternate_vp
    world = await _bound_world(client)
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 1000, 0,
                       vp=0))
    assert r.status_code == 200, r.text
    alternate = await _same_line_alternate_vp(client, world)
    await client.put(
        f"/dialogue-line-revisions/{world['dialogue_line_revision_id']}/"
        "vocal-selection",
        json={"vocal_performance_revision_id": alternate["id"],
              "selected_by": "d"})
    mid = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert mid["ready"] is False
    await client.put(
        f"/dialogue-line-revisions/{world['dialogue_line_revision_id']}/"
        "vocal-selection",
        json={"vocal_performance_revision_id": world["vp"]["id"],
              "selected_by": "d"})
    final = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert final["ready"] is True


# ---------------------------------------------------------------------------
# D13–D15: channel-conflict law
# ---------------------------------------------------------------------------

async def _put_simple(client, shot, pos, pr, start, end, anchor,
                      vp=None):
    r = await client.put(
        f"/shots/{shot}/performance-segments/{pos}",
        json=_seg_body(pr, start, end, anchor, vp=vp))
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_d13_shared_channel_overlap_rejects_readiness(client):
    world = await _bound_world(client)
    candidate2 = (await client.post(
        f"/creative-entities/{world['subject_id']}/"
        "dialogue-bound-performance-candidates",
        json=dialogue_bound_body(
            world["vp"]["id"],
            start=(-500, 1), end=(4500, 1),
            articulation_time={key: (900, 1) for key in ARTICULATION}),
    )).json()
    pr2 = (await client.post(
        f"/performance-candidates/{candidate2['id']}/adopt",
        json={"adopted_by": "d"})).json()
    await _put_simple(client, world["shot"], 0,
                      world["pr"]["id"], 0, 1000, 0, vp=0)
    await _put_simple(client, world["shot"], 1,
                      pr2["id"], 0, 1000, 0, vp=0)
    readiness = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert readiness["ready"] is False
    for seg in readiness["segments"]:
        assert seg["readiness"] == "BLOCKED_CHANNEL_CONFLICT"


@pytest.mark.asyncio
async def test_d14_disjoint_body_facial_channels_pass(client):
    world = await _bound_world(client)
    # a BODY-only PR on the same subject: head_yaw only
    body_candidate = (await client.post(
        f"/creative-entities/{world['subject_id']}/performance-candidates",
        json=candidate_body(
            [m17b_channel(HEAD_YAW, [m17b_kf(0, 1, 0)])]),
    )).json()
    body_pr = (await client.post(
        f"/performance-candidates/{body_candidate['id']}/adopt",
        json={"adopted_by": "d"})).json()
    await _put_simple(client, world["shot"], 0,
                      world["pr"]["id"], 0, 1000, 0, vp=0)
    await _put_simple(client, world["shot"], 1,
                      body_pr["id"], 500, 1500, 0)
    readiness = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert readiness["ready"] is True


@pytest.mark.asyncio
async def test_d15_different_subject_overlap_passes(client):
    world = await _bound_world(client)
    other_entity = await make_entity(client, world["project_id"], "Other")
    # BOTH subjects must remain current dependencies (the PUT replaces
    # the whole set)
    r0 = await client.put(
        f"/shots/{world['shot']}/semantic-dependencies",
        json={"dependencies": [
            {"entity_id": world["subject_id"], "role": "subject"},
            {"entity_id": other_entity, "role": "subject"}]})
    assert r0.status_code == 200, r0.text
    # a dialogue-bound PR for the OTHER subject needs its own line/VP;
    # a generic PR suffices for the overlap law
    other_candidate = (await client.post(
        f"/creative-entities/{other_entity}/performance-candidates",
        json=candidate_body(
            [m17b_channel(SMILE, [m17b_kf(0, 1, 0)])]),
    )).json()
    other_pr = (await client.post(
        f"/performance-candidates/{other_candidate['id']}/adopt",
        json={"adopted_by": "d"})).json()
    await _put_simple(client, world["shot"], 0,
                      world["pr"]["id"], 0, 1000, 0, vp=0)
    await _put_simple(client, world["shot"], 1,
                      other_pr["id"], 500, 1500, 0)
    readiness = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert readiness["ready"] is True


# ---------------------------------------------------------------------------
# D16 + regressions: dependency/binding/timing readiness laws
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_d16_subject_not_dependency_blocks(client):
    world = await _bound_world(client)
    await _put_simple(client, world["shot"], 0,
                      world["pr"]["id"], 0, 1000, 0, vp=0)
    # remove the dependency (replace with an unrelated one)
    other = await make_entity(client, world["project_id"], "Unrelated")
    await _add_dependency(client, world["shot"], other)
    readiness = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert readiness["ready"] is False
    assert readiness["segments"][0]["readiness"] == "BLOCKED_SHOT_DEPENDENCY"


@pytest.mark.asyncio
async def test_generic_with_vocal_position_rejects(client):
    world = await _generic_world(client)
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 2000, 0, vp=0))
    assert r.status_code == 422, r.text
    assert _code(r) == "PERFORMANCE_SHOT_MAPPING_INVALID"


@pytest.mark.asyncio
async def test_paired_vocal_mapping_deleted_blocks_integrity(client):
    world = await _bound_world(client)
    await _put_simple(client, world["shot"], 0,
                      world["pr"]["id"], 0, 1000, 0, vp=0)
    # note: _put_simple has no vocal position; redo the lawful PUT
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 1000, 0,
                       vp=0))
    assert r.status_code == 200, r.text
    d = await client.delete(f"/shots/{world['shot']}/vocal-segments/0")
    assert d.status_code == 204, d.text
    readiness = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert readiness["ready"] is False
    assert readiness["segments"][0]["readiness"] == \
        "BLOCKED_BINDING_INTEGRITY"


@pytest.mark.asyncio
async def test_vocal_mapping_edited_after_blocks_timing(client):
    world = await _bound_world(client)
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 1000, 0,
                       vp=0))
    assert r.status_code == 200, r.text
    # re-anchor the vocal mapping to -250: induced interval shifts to
    # [750, 1750) while the stored performance mapping stays [1000,2000)
    r = await client.put(
        f"/shots/{world['shot']}/vocal-segments/0",
        json={
            "vocal_performance_revision_id": world["vp"]["id"],
            "source_start_sample": 48000,
            "source_end_sample_exclusive": 96000,
            "sample_rate_hz": 48000,
            "performance_origin_ms": {"num": 0, "den": 1},
            "shot_anchor_ms": {"num": -250, "den": 1},
        })
    assert r.status_code == 200, r.text
    readiness = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert readiness["ready"] is False
    assert readiness["segments"][0]["readiness"] == "BLOCKED_TIMING_MISMATCH"


@pytest.mark.asyncio
async def test_delete_and_upsert(client):
    world = await _bound_world(client)
    await _put_simple(client, world["shot"], 0,
                      world["pr"]["id"], 0, 1000, 0, vp=0)
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 1000, 0,
                       vp=0))
    assert r.status_code == 200
    d = await client.delete(
        f"/shots/{world['shot']}/performance-segments/0")
    assert d.status_code == 204
    readiness = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert readiness["ready"] is True and readiness["segments"] == []
