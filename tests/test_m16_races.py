"""M16:RACE — capture serialization and concurrent-read coherence (§22)."""

from __future__ import annotations

import asyncio
import json

from sqlalchemy import text

from tests.m16_seed_b import (
    event,
    post_event,
    put_transition,
    seed_feature_world,
    state,
)
from tests.test_m16_capture import _capture


def _start_daemon(coro):
    return asyncio.ensure_future(coro)


async def test_race_08(client, factory):
    """RACE:08 — capture versus event/handoff mutation sees ONE coherent
    snapshot: a concurrent writer racing the capture read can never
    produce a hybrid (the captured intra_shot block is either fully the
    pre-mutation or fully the post-mutation state)."""
    base = await seed_feature_world(
        client, factory, extra_feature_keys=("wardrobe",))
    sid = base["shot_id"]
    cut, wardrobe = base["feature_id"], base["wardrobe_feature_id"]
    await post_event(
        client, sid,
        event(cut, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    await put_transition(client, cut, sid, operation="set", value="fresh")

    mutations = {"n": 0}

    # a writer repeatedly toggles a transient event on a DISTINCT legal
    # target while captures run: every mutation must LAND (201) and be
    # removable (204) — a real race, not a skipped one
    toggle = event(wardrobe, 2000, state(), state("torn"),
                   ordinal=1)

    async def writer():
        for _ in range(5):
            r = await client.post(
                f"/shots/{sid}/intra-shot/events", json=toggle)
            assert r.status_code == 201, r.text
            mutations["n"] += 1
            eid = r.json()["id"]
            await asyncio.sleep(0.008)
            d = await client.delete(f"/intra-shot/events/{eid}")
            assert d.status_code == 204, d.text
            await asyncio.sleep(0.008)

    async def capturer():
        for _ in range(5):
            revision, _ = await _capture(client, sid)
            snap = json.loads(revision.snapshot_json)
            block = snap["intra_shot"]
            assert block["schema_version"] == 1
            for packed in block["events"]:
                if packed["persistence_mode"] == "require_handoff":
                    assert packed["handoff"] is not None
                    assert packed["handoff"]["state"] == state("fresh")
                    assert packed["target"]["id"] == cut
                else:
                    assert packed["handoff"] is None
                    assert packed["time_ms"] == 2000
                    assert packed["target"]["id"] == wardrobe
            await asyncio.sleep(0.008)

    await asyncio.gather(writer(), capturer())
    assert mutations["n"] == 5
