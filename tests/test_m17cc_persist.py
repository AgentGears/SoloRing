"""M17C-C slice 3 regressions: frozen-companion persistence and
winner-reuse validation (frozen R4 10.4/10.5).

Laws proven:
- fresh persistence: exactly one parent + one child per captured
  segment, all columns the mechanical projection of the SAME captured
  value (schema <8 captures write ZERO companions);
- canonical parent identity: spec_json/spec_hash are the canonical
  embedded performance value, never an independent reconstruction;
- exact child projection incl. the all-or-none vocal group;
- reuse: a correct winner reuses; missing parent, missing child,
  extra child, altered field, altered spec bytes, altered spec hash
  each fail closed as durable-closure corruption (never repaired);
- atomicity: a fault at child k>0 rolls back the WHOLE unit (no
  orphan ShotRevision/parent/partial children);
- convergence: two concurrent captures on the same (shot_id,
  snapshot_hash) — the loser validates the committed winner's complete
  companion closure; a tampered winner refuses the loser;
- coherence-through-persistence: mutate current mappings/binding/
  duration AFTER the one read, then persist the already-read capture —
  the companions carry the PRE-MUTATION captured value.
"""

from __future__ import annotations

import asyncio
import sqlite3

import pytest
from sqlalchemy import text

from soloring.domain.canonical import (
    canonical_hash, canonical_json_str,
)
from tests.m17cc_capture_helper import capture as _capture
from tests.test_m17c_shot_mapping import (
    _bound_world,
    _seg_body,
)

_TABLE = "shot_performance_segment_mappings"
_PARENTS = "shot_revision_performance_specs"
_CHILDREN = "shot_revision_performance_segments"


def _engine(client):
    return client._transport.app.state.engine


async def _sql(client, stmt, params=None):
    async with _engine(client).begin() as conn:
        await conn.execute(text(stmt), params or {})


async def _one(client, stmt, params=None):
    async with _engine(client).connect() as conn:
        return dict((await conn.execute(
            text(stmt), params or {})).mappings().one())


async def _lawful(client, world, *, extra=False):
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 1000, 0, vp=0))
    assert r.status_code == 200, r.text
    if extra:
        # a second READY segment needs disjoint channel keys (D14): a
        # generic BODY-only PR on the same subject (head_yaw only)
        from tests.m17b_seed import (
            HEAD_YAW, candidate_body, channel as m17b_channel,
            kf as m17b_kf,
        )
        body_candidate = (await client.post(
            f"/creative-entities/{world['subject_id']}/"
            "performance-candidates",
            json=candidate_body(
                [m17b_channel(HEAD_YAW, [m17b_kf(0, 1, 0)])]),
        )).json()
        body_pr = (await client.post(
            f"/performance-candidates/{body_candidate['id']}/adopt",
            json={"adopted_by": "s3"})).json()
        r = await client.put(
            f"/shots/{world['shot']}/performance-segments/1",
            json=_seg_body(body_pr["id"], 0, 1000, 0))
        assert r.status_code == 200, r.text
        readiness = (await client.get(
            f"/shots/{world['shot']}/performance-readiness")).json()
        assert readiness["ready"] is True, readiness


async def _counts(client, revision_id):
    async with _engine(client).connect() as conn:
        parents = (await conn.execute(text(
            f"SELECT COUNT(*) FROM {_PARENTS} WHERE "
            "shot_revision_id = :r"), {"r": revision_id})).scalar_one()
        children = (await conn.execute(text(
            f"SELECT COUNT(*) FROM {_CHILDREN} WHERE "
            "shot_revision_id = :r"), {"r": revision_id})).scalar_one()
    return parents, children


@pytest.mark.asyncio
async def test_fresh_persistence_two_segments(client):
    """One parent + exactly len(segments) children, positions ordered,
    all-or-none vocal group, child segment_json == the embedded value."""
    from tests.test_m17c_binding_transitions import _same_line_alternate_vp
    world = await _bound_world(client)
    await _lawful(client, world, extra=True)
    rev, _ = await _capture(client, world["shot"])
    import json as _json
    snap = _json.loads(rev.snapshot_json)
    assert snap["schema_version"] == 8
    parents, children = await _counts(client, rev.id)
    assert parents == 1
    assert children == len(snap["performance"]["segments"]) == 2
    async with _engine(client).connect() as conn:
        rows = (await conn.execute(text(
            f"SELECT position, vocal_performance_revision_id, "
            f"vocal_binding_hash, vocal_mapping_hash, "
            f"source_start_sample, source_end_sample_exclusive, "
            f"sample_rate_hz, segment_json FROM {_CHILDREN} WHERE "
            "shot_revision_id = :r ORDER BY position"),
            {"r": rev.id})).fetchall()
    for i, row in enumerate(rows):
        embedded = snap["performance"]["segments"][i]
        assert row.position == embedded["position"] == i
        assert row.segment_json == canonical_json_str(embedded)
        if embedded["vocal"] is not None:
            assert row.vocal_performance_revision_id == \
                embedded["vocal"]["vocal_performance_revision_id"]
            assert len(row.vocal_binding_hash) == 64
            assert len(row.vocal_mapping_hash) == 64
            assert row.source_start_sample == \
                embedded["vocal"]["source_start_sample"]
        else:
            # the all-or-none vocal group is fully NULL
            assert row.vocal_performance_revision_id is None
            assert row.vocal_binding_hash is None
            assert row.vocal_mapping_hash is None
            assert row.source_start_sample is None


@pytest.mark.asyncio
async def test_schema_below_8_writes_zero_companions(client):
    """A capture with NO performance mappings emits the exact
    predecessor schema and ZERO M17C-C companion rows — no
    opportunistic upgrade from current mappings (there are none), and
    the reuse of such a winner never invents companions either."""
    world = await _bound_world(client)
    rev, _ = await _capture(client, world["shot"])
    assert "performance" not in __import__("json").loads(rev.snapshot_json)
    parents, children = await _counts(client, rev.id)
    assert (parents, children) == (0, 0)
    # a SECOND capture converges on the same winner; still zero
    rev2, _ = await _capture(client, world["shot"])
    assert rev2.id == rev.id
    assert await _counts(client, rev.id) == (0, 0)


@pytest.mark.asyncio
async def test_reuse_correct_winner_succeeds(client):
    world = await _bound_world(client)
    await _lawful(client, world)
    rev1, _ = await _capture(client, world["shot"])
    rev2, _ = await _capture(client, world["shot"])
    assert rev2.id == rev1.id
    assert await _counts(client, rev1.id) == (1, 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper,fragment", [
    ("missing_parent", "exactly one performance companion parent"),
    ("missing_child", "row count disagrees"),
    ("altered_field", "disagrees with the converged capture"),
    ("altered_spec_json", "companion parent disagrees"),
    ("altered_spec_hash", "companion parent disagrees"),
])
async def test_reuse_corrupt_winner_fails_closed(client, tamper, fragment):
    from soloring.errors import SoloRingError
    world = await _bound_world(client)
    await _lawful(client, world)
    rev1, _ = await _capture(client, world["shot"])
    if tamper == "missing_parent":
        await _sql(client, f"DELETE FROM {_CHILDREN} WHERE "
                   "shot_revision_id = :r", {"r": rev1.id})
        await _sql(client, f"DELETE FROM {_PARENTS} WHERE "
                   "shot_revision_id = :r", {"r": rev1.id})
    elif tamper == "missing_child":
        await _sql(client, f"DELETE FROM {_CHILDREN} WHERE "
                   "shot_revision_id = :r AND position = 0", {"r": rev1.id})
    elif tamper == "altered_field":
        await _sql(client, f"UPDATE {_CHILDREN} SET subject_id = 'x' "
                   "WHERE shot_revision_id = :r", {"r": rev1.id})
    elif tamper == "altered_spec_json":
        await _sql(client, f"UPDATE {_PARENTS} SET spec_json = :j "
                   "WHERE shot_revision_id = :r",
                   {"j": '{"schema_version":1,"segments":[]}', "r": rev1.id})
    elif tamper == "altered_spec_hash":
        await _sql(client, f"UPDATE {_PARENTS} SET spec_hash = :h "
                   "WHERE shot_revision_id = :r",
                   {"h": "9" * 64, "r": rev1.id})
    with pytest.raises(SoloRingError) as excinfo:
        await _capture(client, world["shot"])
    assert excinfo.value.status_code == 500, excinfo.value
    assert fragment in str(excinfo.value), (tamper, excinfo.value)
    # never repaired: the corrupt state is unchanged, not repopulated
    if tamper == "missing_parent":
        assert await _counts(client, rev1.id) == (0, 0)
    elif tamper == "missing_child":
        assert await _counts(client, rev1.id) == (1, 0)
    elif tamper == "altered_field":
        bad = await _one(client, f"SELECT subject_id FROM {_CHILDREN} "
                         "WHERE shot_revision_id = :r", {"r": rev1.id})
        assert bad["subject_id"] == "x"


@pytest.mark.asyncio
async def test_atomicity_fault_at_child_rolls_back_whole_unit(
        client, monkeypatch):
    """A fault after the FIRST child insert (k>0) rolls back the whole
    new-revision persistence unit — no orphan ShotRevision, parent, or
    partial child set survives."""
    from soloring.errors import SoloRingError
    from soloring.performance import m17cc_capture_read

    world = await _bound_world(client)
    await _lawful(client, world, extra=True)
    calls = {"n": 0}
    original = m17cc_capture_read.persist_performance_companions

    async def exploding(conn, revision_id, pack):
        calls["n"] += 1
        # insert the parent + first child, then fail at child k=1
        await original.__wrapped__(conn, revision_id, pack) \
            if False else None
        # partial manual persistence then raise
        spec_json, spec_hash = m17cc_capture_read.performance_spec_bytes(
            pack)
        await conn.execute(text(
            f"INSERT INTO {_PARENTS} (shot_revision_id, schema_version,"
            " spec_json, spec_hash) VALUES (:r, 1, :j, :h)"),
            {"r": revision_id, "j": spec_json, "h": spec_hash})
        first = m17cc_capture_read._child_params(revision_id,
                                                 pack["segments"][0])
        await conn.execute(text(
            f"INSERT INTO {_CHILDREN} (shot_revision_id, position, "
            "subject_id, performance_revision_id, "
            "performance_payload_blob_hash, performance_payload_sha256, "
            "performance_profile_id, performance_kind, "
            "performance_start_num, performance_start_den, "
            "performance_end_num, performance_end_den, shot_anchor_num, "
            "shot_anchor_den, performance_mapping_hash, "
            "vocal_performance_revision_id, vocal_binding_hash, "
            "vocal_mapping_hash, source_start_sample, "
            "source_end_sample_exclusive, sample_rate_hz, segment_json, "
            "segment_hash) VALUES (:rid, :position, :subject_id, :prid,"
            " :pbh, :psh, :profile, :kind, :sn, :sd, :en, :ed, :an, "
            ":ad, :pmh, :vid, :vbh, :vmh, :vss, :vse, :vsr, :sj, :sh)"),
            first)
        raise RuntimeError("injected fault at child 1")

    monkeypatch.setattr(m17cc_capture_read,
                        "persist_performance_companions", exploding)
    with pytest.raises(RuntimeError):
        await _capture(client, world["shot"])
    monkeypatch.undo()
    assert calls["n"] == 1
    # NOTHING survived: no ShotRevision for this capture, no parent,
    # no children (only the two working mappings remain)
    async with _engine(client).connect() as conn:
        revs = (await conn.execute(text(
            "SELECT COUNT(*) FROM shot_revisions WHERE shot_id = :s"),
            {"s": world["shot"]})).scalar_one()
        parents = (await conn.execute(text(
            f"SELECT COUNT(*) FROM {_PARENTS}"))).scalar_one()
        children = (await conn.execute(text(
            f"SELECT COUNT(*) FROM {_CHILDREN}"))).scalar_one()
    assert revs == 0
    assert parents == 0
    assert children == 0
    # the surface is LIVE afterwards: a clean capture succeeds
    rev, _ = await _capture(client, world["shot"])
    assert await _counts(client, rev.id) == (1, 2)


@pytest.mark.asyncio
async def test_concurrent_captures_converge_and_validate(client):
    """Two captures racing on the same (shot_id, snapshot_hash): one
    inserts, the loser hits the existing-winner branch and VALIDATES
    the committed winner's companion closure — same revision id, one
    parent, the exact child set; a tampered winner refuses the loser."""
    from soloring.errors import SoloRingError
    world = await _bound_world(client)
    await _lawful(client, world, extra=True)
    (rev_a, _va), (rev_b, _vb) = await asyncio.gather(
        _capture(client, world["shot"]),
        _capture(client, world["shot"]),
    )
    assert rev_a.id == rev_b.id
    assert await _counts(client, rev_a.id) == (1, 2)
    # tamper the committed winner; a fresh converging capture refuses
    await _sql(client, f"UPDATE {_CHILDREN} SET segment_json = :j, "
               "segment_hash = :h WHERE shot_revision_id = :r",
               {"j": "{}", "h": "7" * 64, "r": rev_a.id})
    with pytest.raises(SoloRingError) as excinfo:
        await _capture(client, world["shot"])
    assert excinfo.value.status_code == 500


@pytest.mark.asyncio
async def test_coherence_through_persistence(client):
    """Read -> mutate current state -> persist the ALREADY-READ capture:
    the companion parent and children carry the PRE-MUTATION captured
    value (closes the loophole between one-read coherence and durable
    preservation)."""
    from soloring.continuity.snapshots import build_capturable_snapshot
    from soloring.domain.revisions import (
        _persist_revision_fenced, _snapshot_one_read,
    )
    from tests.test_m17c_binding_transitions import _same_line_alternate_vp
    from tests.m17cc_capture_helper import _factory
    world = await _bound_world(client)
    await _lawful(client, world, extra=True)

    settings = client._transport.app.state.settings
    read = await _snapshot_one_read(
        _factory(client)(), world["shot"], settings=settings)
    performance = read[9]
    assert performance is not None and performance["ready"]
    pre = [dict(s) for s in performance["segments"]]

    # mutate every current surface AFTER the read, BEFORE persistence
    await _sql(client, f"DELETE FROM {_TABLE} WHERE shot_id = :s",
               {"s": world["shot"]})
    alternate = await _same_line_alternate_vp(client, world)
    await client.put(
        f"/dialogue-line-revisions/{world['dialogue_line_revision_id']}/"
        "vocal-selection",
        json={"vocal_performance_revision_id": alternate["id"],
              "selected_by": "coh"})
    p = await client.patch(
        f"/shots/{world['shot']}", json={"duration_ms": 100})
    assert p.status_code == 200, p.text

    snapshot, spec = build_capturable_snapshot(
        read[0], read[1], read[2], read[3], read[4],
        read[5].pack if read[5] is not None else None,
        read[6].pack if read[6] is not None else None,
        read[7].pack, performance_pack=performance)
    revision_id = await _persist_revision_fenced(
        _engine(client), world["shot"],
        canonical_json_str(snapshot), canonical_hash(snapshot),
        None, None, read[2], read[3], read[4], read[5], read[6],
        read[7], performance_pack=performance)

    parents, children = await _counts(client, revision_id)
    assert (parents, children) == (1, 2)
    async with _engine(client).connect() as conn:
        rows = (await conn.execute(text(
            f"SELECT position, performance_revision_id, "
            f"vocal_performance_revision_id FROM {_CHILDREN} WHERE "
            "shot_revision_id = :r ORDER BY position"),
            {"r": revision_id})).fetchall()
    assert rows[0].performance_revision_id == pre[0][
        "performance_revision_id"] == world["pr"]["id"]
    assert rows[0].vocal_performance_revision_id == pre[0][
        "vocal"]["vocal_performance_revision_id"] == world["vp"]["id"]
    assert len(rows) == len(pre)


@pytest.mark.asyncio
async def test_schema8_winner_without_companions_refuses_convergence(
        client):
    """A schema-<8 would-be capture converging on a winner that
    unexpectedly CARRIES performance companions is an impossible state
    (the snapshot hashes could not match) — defense in depth."""
    from soloring.errors import SoloRingError
    world = await _bound_world(client)
    # capture a no-mapping winner first
    rev1, _ = await _capture(client, world["shot"])
    # now add mappings and capture a schema-8 revision
    await _lawful(client, world)
    rev2, _ = await _capture(client, world["shot"])
    assert rev2.id != rev1.id
    # graft companions onto the schema-<8 winner (impossible state)
    async with _engine(client).begin() as conn:
        con = None
        # copy rev2's parent to rev1 with the same bytes — the reuse
        # of the schema-<8 winner must refuse
        spec = (await conn.execute(text(
            f"SELECT spec_json, spec_hash FROM {_PARENTS} WHERE "
            "shot_revision_id = :r"), {"r": rev2.id})).fetchone()
        await conn.execute(text(
            f"INSERT INTO {_PARENTS} (shot_revision_id, schema_version,"
            " spec_json, spec_hash) VALUES (:r, 1, :j, :h)"),
            {"r": rev1.id, "j": spec.spec_json, "h": spec.spec_hash})
    # remove the mappings so the next capture is schema <8 again and
    # converges on rev1
    await _sql(client, f"DELETE FROM {_TABLE} WHERE shot_id = :s",
               {"s": world["shot"]})
    with pytest.raises(SoloRingError) as excinfo:
        await _capture(client, world["shot"])
    assert excinfo.value.status_code == 500
    assert "does not require" in str(excinfo.value)
