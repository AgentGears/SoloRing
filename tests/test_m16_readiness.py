"""M16:READY — current readiness integration (frozen R6 §9/§22)."""

from __future__ import annotations

from sqlalchemy import text

from tests.m16_seed_b import (
    event,
    get_intra,
    post_event,
    seed_feature_world,
    state,
)


def _codes(proj):
    return [i["code"] for i in proj["intra_shot_issues"]]


async def test_ready_01(client, factory):
    """A structurally invalid set is rejected by the authoring write."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(
        client, sid, event(fid, 1000, state(), state("fresh")))
    bad = await client.post(
        f"/shots/{sid}/intra-shot/events",
        json=event(fid, 2000, state("healing"), state("scarred")))
    assert bad.status_code == 409, bad.text
    assert "INTRA_SHOT_EVENT_BEFORE_STATE_MISMATCH" in bad.text


async def test_ready_02(client, factory):
    """A valid require_handoff event exists while capture stays blocked
    for the missing handoff (readiness blocker, not authoring rejection)."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    created = await client.post(
        f"/shots/{sid}/intra-shot/events",
        json=event(fid, 1000, state(), state("fresh"),
                   persistence="require_handoff"))
    assert created.status_code == 201, created.text
    proj = await get_intra(client, sid)
    assert proj["intra_shot_ready"] is False
    assert "INTRA_SHOT_HANDOFF_REQUIRED" in _codes(proj)


async def test_ready_03(client, factory):
    """A predecessor not-ready condition blocks without redefining the
    predecessor field semantics."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(
        client, sid, event(fid, 1000, state(), state("fresh")))
    detail0 = (await client.get(f"/shots/{sid}")).json()
    assert detail0["intra_shot_ready"] is True
    assert detail0["continuity_state_ready"] is True

    # temporal data that genuinely requires narrative context
    from tests.m16_seed_b import put_transition

    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        seq = (await conn.execute(text(
            "SELECT s.id FROM sequences s WHERE s.project_id = :p "
            "ORDER BY s.position LIMIT 1"), {"p": base["project_id"]}
        )).scalar_one()
    r = await client.post(
        f"/continuity-features/{fid}/transitions",
        json={"anchor_type": "sequence", "anchor_id": seq,
              "boundary": "start", "operation": "set", "value": "fresh"})
    assert r.status_code == 201, r.text

    # break the M7 layer: remove the Shot's narrative assignment
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE shots SET scene_id = NULL, scene_position = NULL "
            "WHERE id = :s"), {"s": sid})

    proj = await get_intra(client, sid)
    assert proj["intra_shot_ready"] is False, proj["intra_shot_issues"]
    assert "INTRA_SHOT_TARGET_INVALID" in _codes(proj)
    detail1 = (await client.get(f"/shots/{sid}")).json()
    # continuity_state_ready keeps its predecessor-only M7 meaning
    assert detail1["continuity_state_ready"] is False


async def test_ready_04(client, factory):
    """Issue ordering and content are deterministic."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(
        client, sid,
        event(fid, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    # corrupt duration to NULL (direct state, the authoring fence makes
    # this unreachable through APIs; the resolver must still fail closed)
    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        await conn.execute(text(
            "PRAGMA foreign_keys=OFF"))
        await conn.execute(text(
            "UPDATE shots SET duration_ms = NULL WHERE id = :s"), {"s": sid})

    a = await get_intra(client, sid)
    b = await get_intra(client, sid)
    assert a["intra_shot_issues"] == b["intra_shot_issues"]
    codes = _codes(a)
    assert codes[0] == "INTRA_SHOT_DURATION_REQUIRED", codes
    assert "INTRA_SHOT_HANDOFF_REQUIRED" in codes
    # duration outranks handoff deterministically
    assert codes.index("INTRA_SHOT_DURATION_REQUIRED") < codes.index(
        "INTRA_SHOT_HANDOFF_REQUIRED")


async def test_ready_05(client, factory):
    """Shot detail and the dedicated intra-shot read consume the same
    resolver result grammar."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(
        client, sid,
        event(fid, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    detail = (await client.get(f"/shots/{sid}")).json()
    proj = await get_intra(client, sid)
    assert detail["intra_shot_ready"] == proj["intra_shot_ready"]
    assert detail["intra_shot_issues"] == proj["intra_shot_issues"]


async def test_ready_06(client, factory):
    """working_snapshot_hash/differs are unavailable while M16 blocks —
    and, per the M16-B fail-closed seam, for ANY event-bearing Shot until
    the M16-C schema-7 snapshot builder exists."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    detail0 = (await client.get(f"/shots/{sid}")).json()
    assert detail0["working_snapshot_hash"] is not None

    await post_event(
        client, sid,
        event(fid, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    detail1 = (await client.get(f"/shots/{sid}")).json()
    assert detail1["intra_shot_ready"] is False
    assert detail1["working_snapshot_hash"] is None
    assert detail1["working_state_differs_from_approved"] is None

    # even an M16-READY event set keeps the working hash unavailable in
    # M16-B: no interim representation of the event-bearing snapshot
    base2 = await seed_feature_world(client, factory)
    sid2, fid2 = base2["shot_id"], base2["feature_id"]
    await post_event(client, sid2, event(fid2, 1000, state(), state("fresh")))
    detail2 = (await client.get(f"/shots/{sid2}")).json()
    assert detail2["intra_shot_ready"] is True
    assert detail2["working_snapshot_hash"] is None
    assert detail2["working_state_differs_from_approved"] is None


async def test_ready_07(client, factory):
    """An event-free real Shot reports intra_shot_ready=true and keeps
    the predecessor working-hash behavior untouched."""
    base = await seed_feature_world(client, factory)
    sid = base["shot_id"]
    detail = (await client.get(f"/shots/{sid}")).json()
    assert detail["intra_shot_ready"] is True
    assert detail["intra_shot_issues"] == []
    assert detail["working_snapshot_hash"] is not None
    proj = await get_intra(client, sid)
    assert proj["intra_shot_ready"] is True
    assert proj["event_set_hash"] is None
    assert proj["events"] == []
