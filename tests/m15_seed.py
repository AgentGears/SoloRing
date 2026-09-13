"""Shared M15A test seeding helpers.

Builds the r2→r3 substitution scenario through the real predecessor
seams (m13_seed) and runs assessments through the real service.
"""

from __future__ import annotations

from soloring.compatibility.service import create_assessment
from tests.m13_seed import make_composition, mint, seed_base
from tests.m13_seed import seed_second_revision
from tests.test_m13_binding import _adopt, _approved_world, _interpretation


async def seed_revision_pair(client, *, tag: bytes = b"m15-seed") -> dict:
    """Project + one Production Object with closed r1 and r2."""
    base = await seed_base(client, tag=tag)
    r2 = await seed_second_revision(client, base, number=2)
    return {**base, "r2": r2}


async def seed_a4_use(client, *, tag: bytes = b"m15-a4",
                      source_translation=(0, 0, 0),
                      target_translation=(10, 0, 0),
                      with_target_interpretation=True) -> dict:
    """One working use whose placement consumer is UNIQUE_A4.

    Returns ids plus the world/track coordinates for assertions."""
    base = await seed_revision_pair(client, tag=tag)
    pid = base["project_id"]
    cid = await make_composition(client, pid)
    occ = (await mint(client, cid, base["production_revision_id"], 0,
                      name="Chair 7"))["occurrence_id"]
    w = await _approved_world(client, pid, key="lobby")
    await _interpretation(
        client, base["production_revision_id"],
        translation=source_translation)
    if with_target_interpretation:
        await _interpretation(
            client, base["r2"], translation=target_translation)
    await _adopt(client, cid, occ, {"kind": "production_instance"})
    r = await client.post(
        f"/spatial-worlds/{w['world']['id']}/production-instance-tracks",
        json={"occurrence_id": occ, "requirement": "required"})
    assert r.status_code == 201, r.text
    return {**base, "composition_id": cid, "occurrence_id": occ,
            "world": w, "track_id": r.json()["id"]}


async def assess(client, from_rid: str, to_rid: str) -> dict:
    """Assessment through the real service (factory-free session)."""
    from tests.conftest import make_tracked_maker

    maker = make_tracked_maker(client._transport.app.state.engine)
    return await create_assessment(
        maker(), from_revision_id=from_rid, to_revision_id=to_rid)


async def assess_http(client, from_rid: str, to_rid: str):
    return await client.post(
        f"/production-revisions/{from_rid}/compatibility-assessments",
        json={"to_revision_id": to_rid})


async def seed_scene(client, pid: str) -> str:
    """A real Scene anchor for instance transitions."""
    from tests.conftest import make_tracked_maker
    from tests.test_m8c_resolver import _topology

    maker = make_tracked_maker(client._transport.app.state.engine)
    _seq, scene, _shots = await _topology(client, maker, pid)
    return scene
