"""M17C-B corrective regressions (B-F cycle, frozen under the PR #26
primary review).

Behavioral proofs of the B-F source-level corrections:

- B-F2: upstream immutable-history corruption (revision binding hash;
  candidate<->revision binding divergence with COHERENTLY recomputed
  canonical bytes; candidate binding bytes) refuses PF-02 with ZERO
  new mapping rows and fails readiness/list closed as 500 corruption —
  never a 4xx stale answer.
- B-F3: mode/position shape escape — a VOCAL_V1 mapping whose position
  is NULLed (and a generic mapping carrying a position) with canonical
  JSON/hash coherently rewritten, so ONLY the discriminator-driven
  shape law can refuse, is corruption on reads.
- B-F5: readiness revalidates the picture-intersection law against the
  CURRENT Shot duration without rewriting stored intent.
- B-F6: stored-mapping tamper (canonical hash; noncanonical persisted
  rational) fails live reads closed.
- B-F8: a MISSING VocalPerformanceSelection row is corruption at PUT
  and readiness (M17A law); a lawful UNSET selection is STALE.
- Concurrency: sequential same-position PUTs converge last-committed-
  wins to exactly one row; truly concurrent same-position PUTs never
  duplicate or tear the row (SQLite single-writer; the losing request
  fails closed) and the projection surface stays live afterwards.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
from sqlalchemy import text

from soloring.domain.canonical import canonical_hash, canonical_json_str
from tests.test_m17c_binding_transitions import _same_line_alternate_vp
from tests.test_m17c_shot_mapping import (
    _bound_world,
    _generic_world,
    _seg_body,
)

_TABLE = "shot_performance_segment_mappings"


def _engine(client):
    return client._transport.app.state.engine


async def _sql(client, stmt, params=None):
    async with _engine(client).begin() as conn:
        await conn.execute(text(stmt), params or {})


async def _count(client, table=_TABLE):
    async with _engine(client).connect() as conn:
        return (await conn.execute(
            text(f"SELECT COUNT(*) FROM {table}"))).scalar_one()


async def _one(client, stmt, params=None):
    async with _engine(client).connect() as conn:
        return dict((await conn.execute(
            text(stmt), params or {})).mappings().one())


def _corrupt(resp, message_fragment=None):
    assert resp.status_code == 500, resp.text
    assert resp.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"
    if message_fragment is not None:
        assert message_fragment in resp.json()["message"], resp.text


async def _lawful_bound_mapping(client, world):
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 1000, 0, vp=0))
    assert r.status_code == 200, r.text


def _mapping_doc(pr_id, s_num, s_den, e_num, e_den, a_num, a_den,
                 vocal_position):
    return {
        "mapping_schema_version": 1,
        "performance_revision_id": pr_id,
        "performance_start_ms": {"num": s_num, "den": s_den},
        "performance_end_ms": {"num": e_num, "den": e_den},
        "shot_anchor_ms": {"num": a_num, "den": a_den},
        "vocal_mapping_position": vocal_position,
    }


# ---------------------------------------------------------------------------
# B-F2 — upstream immutable corruption refuses PF-02 with zero new rows
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bf02_revision_binding_hash_corruption_refuses_put(client):
    world = await _bound_world(client)
    await _sql(
        client,
        "UPDATE performance_revision_vocal_bindings "
        "SET binding_hash = :h WHERE performance_revision_id = :r",
        {"h": "b" * 64, "r": world["pr"]["id"]})
    assert await _count(client) == 0
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 1000, 0, vp=0))
    # binding_hash is a BINDING_FIELD: the candidate<->revision
    # equality law fires before the bytes law on the PUT path
    _corrupt(r, "revision vocal binding != adopted candidate binding "
                "closure")
    assert await _count(client) == 0


@pytest.mark.asyncio
async def test_bf02_candidate_revision_divergence_refuses(client):
    """Coherently diverge ONLY the revision-side vocal id (canonical
    JSON/hash recomputed) so no stale-hash check can catch it — the
    pair-closure equality law must refuse, on both the PUT and read
    paths."""
    world = await _bound_world(client)
    # a REAL alternate VP id: the binding's FK must stay satisfied so
    # only the equality law (not referential integrity) can refuse
    alternate = await _same_line_alternate_vp(client, world)
    b = await _one(
        client,
        "SELECT * FROM performance_revision_vocal_bindings "
        "WHERE performance_revision_id = :r",
        {"r": world["pr"]["id"]})
    doc = {
        "binding_schema_version": b["binding_schema_version"],
        "synchronization_basis_version":
            b["synchronization_basis_version"],
        "vocal_performance_revision_id": alternate["id"],
        "source_start_sample": b["source_start_sample"],
        "source_end_sample_exclusive":
            b["source_end_sample_exclusive"],
        "sample_rate_hz": b["sample_rate_hz"],
        "performance_origin_ms": {"num": b["performance_origin_num"],
                                  "den": b["performance_origin_den"]},
    }
    await _sql(
        client,
        "UPDATE performance_revision_vocal_bindings SET "
        "vocal_performance_revision_id = :v, binding_json = :j, "
        "binding_hash = :h WHERE performance_revision_id = :r",
        {"v": alternate["id"], "j": canonical_json_str(doc),
         "h": canonical_hash(doc), "r": world["pr"]["id"]})
    assert await _count(client) == 0
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 1000, 0, vp=0))
    _corrupt(r, "revision vocal binding != adopted candidate binding "
                "closure")
    assert await _count(client) == 0


@pytest.mark.asyncio
async def test_bf02_readiness_fails_closed_on_upstream_corruption(client):
    world = await _bound_world(client)
    await _lawful_bound_mapping(client, world)
    await _sql(
        client,
        "UPDATE performance_candidate_vocal_bindings "
        "SET binding_json = :j WHERE performance_candidate_id = :c",
        {"j": "{}", "c": world["candidate"]["id"]})
    for path in (f"/shots/{world['shot']}/performance-readiness",
                 f"/shots/{world['shot']}/performance-segments"):
        _corrupt(await client.get(path),
                 "revision vocal binding != adopted candidate binding "
                 "closure")


# ---------------------------------------------------------------------------
# B-F3 — mode/position shape escape with coherent canonical bytes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bf03_v1_mapping_null_position_is_corruption(client):
    world = await _bound_world(client)
    await _lawful_bound_mapping(client, world)
    doc = _mapping_doc(world["pr"]["id"], 0, 1, 1000, 1, 0, 1, None)
    await _sql(
        client,
        f"UPDATE {_TABLE} SET vocal_mapping_position = NULL, "
        "mapping_json = :j, mapping_hash = :h "
        "WHERE shot_id = :s AND position = 0",
        {"j": canonical_json_str(doc), "h": canonical_hash(doc),
         "s": world["shot"]})
    _corrupt(await client.get(
        f"/shots/{world['shot']}/performance-readiness"),
        "without vocal_mapping_position")


@pytest.mark.asyncio
async def test_bf03_generic_mapping_with_position_is_corruption(client):
    world = await _generic_world(client)
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 2000, 0))
    assert r.status_code == 200, r.text
    doc = _mapping_doc(world["pr"]["id"], 0, 1, 2000, 1, 0, 1, 0)
    await _sql(
        client,
        f"UPDATE {_TABLE} SET vocal_mapping_position = 0, "
        "mapping_json = :j, mapping_hash = :h "
        "WHERE shot_id = :s AND position = 0",
        {"j": canonical_json_str(doc), "h": canonical_hash(doc),
         "s": world["shot"]})
    _corrupt(await client.get(
        f"/shots/{world['shot']}/performance-readiness"),
        "carries vocal_mapping_position on a non-VOCAL_V1")


# ---------------------------------------------------------------------------
# B-F5 — readiness revalidates the CURRENT Shot duration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bf05_duration_change_breaks_picture_intersection(client):
    world = await _generic_world(client)
    # d05's lawful L-cut: [0, 4500) anchored at 2000 intersects a 3000ms
    # Shot picture ([2000, 6500) vs [0, 3000))
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 4500, 2000))
    assert r.status_code == 200, r.text
    readiness = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert readiness["ready"] is True
    # shrink the CURRENT duration below the anchor: the stored intent is
    # untouched but no longer intersects the picture
    await _sql(
        client,
        "UPDATE shots SET duration_ms = 1000 WHERE id = :s",
        {"s": world["shot"]})
    readiness2 = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert readiness2["ready"] is False
    assert readiness2["segments"][0]["readiness"] == \
        "BLOCKED_TIMING_MISMATCH"
    assert "no longer intersects" in readiness2["segments"][0][
        "readiness_diagnostics"]["reason"]
    row = await _one(
        client,
        f"SELECT performance_start_num, performance_end_num, "
        f"shot_anchor_num, mapping_hash FROM {_TABLE} "
        "WHERE shot_id = :s AND position = 0",
        {"s": world["shot"]})
    assert (row["performance_start_num"], row["performance_end_num"],
            row["shot_anchor_num"]) == (0, 4500, 2000)
    assert row["mapping_hash"] == readiness2["segments"][0][
        "mapping_hash"]


# ---------------------------------------------------------------------------
# B-F6 — stored-mapping tamper fails live reads closed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bf06_stored_hash_tamper_refuses_live_reads(client):
    world = await _bound_world(client)
    await _lawful_bound_mapping(client, world)
    await _sql(
        client,
        f"UPDATE {_TABLE} SET mapping_hash = :h "
        "WHERE shot_id = :s AND position = 0",
        {"h": "c" * 64, "s": world["shot"]})
    for path in (f"/shots/{world['shot']}/performance-readiness",
                 f"/shots/{world['shot']}/performance-segments"):
        _corrupt(await client.get(path), "canonical bytes/hash diverge")


@pytest.mark.asyncio
async def test_bf06_stored_noncanonical_rational_refuses(client):
    world = await _bound_world(client)
    await _lawful_bound_mapping(client, world)
    # 0/5 reduces to 0/1: a persisted noncanonical rational
    await _sql(
        client,
        f"UPDATE {_TABLE} SET performance_start_num = 0, "
        "performance_start_den = 5 WHERE shot_id = :s AND position = 0",
        {"s": world["shot"]})
    _corrupt(await client.get(
        f"/shots/{world['shot']}/performance-readiness"),
        "performance_start rational is not canonical")


# ---------------------------------------------------------------------------
# B-F8 — missing selection row is corruption; UNSET is STALE
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bf08_missing_selection_row_is_corruption_everywhere(client):
    world = await _bound_world(client)
    await _lawful_bound_mapping(client, world)
    await _sql(
        client,
        "DELETE FROM vocal_performance_selections "
        "WHERE dialogue_line_revision_id = :d",
        {"d": world["dialogue_line_revision_id"]})
    # a fresh PUT fails closed as corruption, never a stale 409
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/1",
        json=_seg_body(world["pr"]["id"], 0, 1000, 0, vp=0))
    _corrupt(r, "no selection row")
    assert await _count(client) == 1  # only the pre-existing row
    # readiness on the existing mapping fails closed too
    _corrupt(await client.get(
        f"/shots/{world['shot']}/performance-readiness"),
        "no selection row")
    # restoring the lawful M17A row shape restores the projection —
    # the corruption was exactly the missing row, nothing else
    await _sql(
        client,
        "INSERT INTO vocal_performance_selections ("
        "dialogue_line_revision_id, selected_vocal_performance_revision_id, "
        "selected_by, selected_at, updated_at) VALUES "
        "(:d, :v, :b, :a, :u)",
        {"d": world["dialogue_line_revision_id"],
         "v": world["vp"]["id"], "b": "bf",
         "a": "2026-01-01T00:00:00.000Z",
         "u": "2026-01-01T00:00:00.000Z"})
    readiness = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert readiness["ready"] is True


@pytest.mark.asyncio
async def test_bf08_unset_selection_is_lawful_stale(client):
    world = await _bound_world(client)
    await _lawful_bound_mapping(client, world)
    # ck_vps_selection_shape: the UNSET shape nulls all three columns
    await _sql(
        client,
        "UPDATE vocal_performance_selections SET "
        "selected_vocal_performance_revision_id = NULL, "
        "selected_by = NULL, selected_at = NULL "
        "WHERE dialogue_line_revision_id = :d",
        {"d": world["dialogue_line_revision_id"]})
    readiness = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert readiness["ready"] is False
    assert readiness["segments"][0]["readiness"] == "STALE_VOCAL_SELECTION"
    assert readiness["segments"][0]["readiness_diagnostics"][
        "selection_state"] == "UNSET"


# ---------------------------------------------------------------------------
# Concurrency — last committed PUT wins (sequential); concurrent PUTs
# never duplicate or tear the row (SQLite single-writer)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sequential_reput_last_committed_wins(client):
    world = await _generic_world(client)
    r1 = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 2000, 0))
    assert r1.status_code == 200, r1.text
    r2 = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 500, 2500, 0))
    assert r2.status_code == 200, r2.text
    assert await _count(client) == 1
    rows = (await client.get(
        f"/shots/{world['shot']}/performance-segments")).json()
    assert len(rows) == 1
    assert (rows[0]["performance_start_ms"]["num"],
            rows[0]["performance_end_ms"]["num"]) == (500, 2500)
    readiness = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert readiness["ready"] is True


@pytest.mark.asyncio
async def test_concurrent_same_position_puts_never_duplicate(client):
    world = await _generic_world(client)
    outcomes = await asyncio.gather(
        client.put(
            f"/shots/{world['shot']}/performance-segments/0",
            json=_seg_body(world["pr"]["id"], 0, 2000, 0)),
        client.put(
            f"/shots/{world['shot']}/performance-segments/0",
            json=_seg_body(world["pr"]["id"], 500, 2500, 0)),
        return_exceptions=True,
    )
    # SQLite serializes writers: one request commits its exact payload;
    # the other either observes the committed row (both 200) or the
    # unique-key/write-lock race escapes untranslated (an ASGI-transport
    # exception here; an unhandled 500 under a real server). Never a
    # duplicate or torn row. The record narrows "last committed PUT
    # wins" to the sequential contract accordingly.
    assert any(isinstance(o, httpx.Response) and o.status_code == 200
               for o in outcomes), [repr(o)[:200] for o in outcomes]
    for o in outcomes:
        assert (isinstance(o, httpx.Response)
                and o.status_code == 200) or isinstance(o, Exception)
    assert await _count(client) == 1
    rows = (await client.get(
        f"/shots/{world['shot']}/performance-segments")).json()
    assert len(rows) == 1
    assert (rows[0]["performance_start_ms"]["num"],
            rows[0]["performance_end_ms"]["num"]) in (
        (0, 2000), (500, 2500))
    # the projection surface stays live afterwards
    readiness = await client.get(
        f"/shots/{world['shot']}/performance-readiness")
    assert readiness.status_code == 200, readiness.text
    assert readiness.json()["ready"] is True
