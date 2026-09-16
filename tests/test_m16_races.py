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
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(
        client, sid,
        event(fid, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    await put_transition(client, fid, sid, operation="set", value="fresh")

    engine = client._transport.app.state.engine

    # a writer repeatedly toggles a SECOND transient event on the same
    # Shot while captures run: every capture must see a coherent set
    toggle = event(fid, 2000, state("fresh"), state("healing"))

    async def writer():
        for _ in range(6):
            r = await client.post(
                f"/shots/{sid}/intra-shot/events", json=toggle)
            if r.status_code == 201:
                eid = r.json()["id"]
            else:
                eid = None
            await asyncio.sleep(0.01)
            if eid:
                d = await client.delete(f"/intra-shot/events/{eid}")
                assert d.status_code == 204, d.text
            await asyncio.sleep(0.01)

    async def capturer():
        for _ in range(6):
            revision, _ = await _capture(client, sid)
            snap = json.loads(revision.snapshot_json)
            block = snap["intra_shot"]
            assert block["schema_version"] == 1
            # coherence: the persistent terminal event is ALWAYS the
            # handoff-bearing one; the toggled transient appears or not
            # as a WHOLE event, never a hybrid row
            for packed in block["events"]:
                if packed["persistence_mode"] == "require_handoff":
                    assert packed["handoff"] is not None
                    assert packed["handoff"]["state"] == state("fresh")
                else:
                    assert packed["handoff"] is None
                    assert packed["time_ms"] == 2000
            await asyncio.sleep(0.01)

    await asyncio.gather(writer(), capturer())
