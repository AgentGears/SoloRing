"""M15B tracking proofs (frozen R6 §31.7 M15-TRACK:01-08)."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.m13_seed import make_composition, mint, seed_base
from tests.test_m13_binding import _approved_world, _interpretation


def _tracking(client, cid, occ):
    return client.get(
        f"/compositions/{cid}/occurrences/{occ}/revision-tracking")


def _put(client, cid, occ, mode, version):
    return client.put(
        f"/compositions/{cid}/occurrences/{occ}/revision-tracking",
        json={"mode": mode, "expected_policy_version": version})


async def _seed_use(client, tag=b"trk"):
    base = await seed_base(client, tag=tag)
    cid = await make_composition(client, base["project_id"])
    occ = (await mint(client, cid, base["production_revision_id"], 0,
                      name="Chair"))["occurrence_id"]
    return base, cid, occ


async def test_absence_means_pinned_without_backfill(client):
    """M15-TRACK:01 — never-authored absence reads PINNED/v0; no row is
    created by the read or by an idempotent PINNED PUT; migration
    backfilled nothing."""
    base, cid, occ = await _seed_use(client, b"trk01")
    r = await _tracking(client, cid, occ)
    assert r.status_code == 200 and r.json() == {
        "mode": "PINNED", "policy_version": 0}

    r = await _put(client, cid, occ, "PINNED", 0)
    assert r.status_code == 200 and r.json() == {
        "mode": "PINNED", "policy_version": 0}
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM "
            "composition_occurrence_revision_tracking"
        ))).scalar_one()
    assert n == 0  # no backfill, no row from idempotent no-op


async def test_track_compatible_requires_explicit_opt_in(client):
    """M15-TRACK:02 — TRACK_COMPATIBLE exists only after an explicit
    PUT; the row appears at v1."""
    base, cid, occ = await _seed_use(client, b"trk02")
    r = await _put(client, cid, occ, "TRACK_COMPATIBLE", 0)
    assert r.status_code == 200
    assert r.json() == {"mode": "TRACK_COMPATIBLE", "policy_version": 1}
    r = await _tracking(client, cid, occ)
    assert r.json()["mode"] == "TRACK_COMPATIBLE"


async def test_tracking_offer_never_mutates_source(client):
    """M15-TRACK:03 — no auto-follow: policy reads/writes and discovery
    never touch the working occurrence's source revision."""
    base, cid, occ = await _seed_use(client, b"trk03")
    await _put(client, cid, occ, "TRACK_COMPATIBLE", 0)
    r = await client.get(
        f"/production-objects/{base['production_object_id']}"
        "/revision-updates")
    assert r.status_code == 200, r.text
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        source = (await conn.execute(text(
            "SELECT production_revision_id FROM "
            "composition_working_occurrences WHERE composition_id = :c "
            "AND occurrence_id = :o"),
            {"c": cid, "o": occ})).scalar_one()
    assert source == base["production_revision_id"]


async def test_update_offer_resolves_concrete_revision_ids(client):
    """M15-TRACK:04 — discovery returns concrete id/number/hash
    candidates; nothing persists a symbolic latest."""
    from tests.m13_seed import seed_second_revision

    base, cid, occ = await _seed_use(client, b"trk04")
    r2 = await seed_second_revision(client, base, number=2)
    await _put(client, cid, occ, "TRACK_COMPATIBLE", 0)
    r = await client.get(
        f"/production-objects/{base['production_object_id']}"
        "/revision-updates")
    body = r.json()
    assert body["assessment_created"] is False
    use = body["uses"][0]
    assert use["current_revision_id"] == base["production_revision_id"]
    assert [c["revision_id"] for c in use["candidates"]] == [r2]
    assert use["candidates"][0]["revision_number"] == 2
    assert len(use["candidates"][0]["snapshot_hash"]) == 64
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM "
            "production_compatibility_assessments"))).scalar_one()
    assert n == 0  # no symbolic target persisted, no assessment


async def test_tracking_policy_cas(client):
    """M15-TRACK:05 — expected-version CAS: mismatch refuses; correct
    version transitions; same-mode PUT is idempotent without bump."""
    base, cid, occ = await _seed_use(client, b"trk05")
    r = await _put(client, cid, occ, "TRACK_COMPATIBLE", 5)
    assert r.status_code == 409
    assert r.json()["details"]["reason"] == "tracking_policy_conflict"

    r = await _put(client, cid, occ, "TRACK_COMPATIBLE", 0)
    assert r.json()["policy_version"] == 1
    r = await _put(client, cid, occ, "TRACK_COMPATIBLE", 1)
    assert r.json() == {"mode": "TRACK_COMPATIBLE",
                        "policy_version": 1}  # idempotent, no bump
    r = await _put(client, cid, occ, "PINNED", 1)
    assert r.json() == {"mode": "PINNED", "policy_version": 2}
    r = await _put(client, cid, occ, "TRACK_COMPATIBLE", 1)
    assert r.status_code == 409  # stale expected version refused


async def test_policy_version_never_aba_after_authored_cycle(client):
    """M15-TRACK:06 — the full cycle v0→1→2; a stale v0 client fails;
    version never resets to an externally visible 0."""
    base, cid, occ = await _seed_use(client, b"trk06")
    await _put(client, cid, occ, "TRACK_COMPATIBLE", 0)   # v1
    await _put(client, cid, occ, "PINNED", 1)             # v2
    r = await _put(client, cid, occ, "TRACK_COMPATIBLE", 0)  # stale v0
    assert r.status_code == 409
    r = await _tracking(client, cid, occ)
    assert r.json() == {"mode": "PINNED", "policy_version": 2}
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT MIN(policy_version) FROM "
            "composition_occurrence_revision_tracking"
        ))).scalar_one()
    assert row >= 1  # authored rows never return to visible 0


async def test_terminated_tracked_occurrence_is_inert_and_not_offered(
        client):
    """M15-TRACK:07 — a tracked occurrence removed from working state
    is excluded from discovery and its policy cannot be mutated."""
    base, cid, occ = await _seed_use(client, b"trk07")
    await _put(client, cid, occ, "TRACK_COMPATIBLE", 0)
    from tests.m13_seed import remove_occurrence

    await remove_occurrence(client, cid, occ, 1)
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        working = (await conn.execute(text(
            "SELECT COUNT(*) FROM composition_working_occurrences "
            "WHERE composition_id = :c AND occurrence_id = :o"),
            {"c": cid, "o": occ})).scalar_one()
    assert working == 0

    r = await client.get(
        f"/production-objects/{base['production_object_id']}"
        "/revision-updates")
    assert all(u["occurrence_id"] != occ for u in r.json()["uses"])

    r = await _put(client, cid, occ, "PINNED", 1)
    assert r.status_code == 409  # inert: policy mutation refused


async def test_discovery_returns_concrete_newer_candidates_and_creates_no_assessment(
        client):
    """M15-TRACK:08 — multiple newer candidates are all returned
    concretely (DESC number, id ASC tiebreak) and no assessment row
    appears; an untracked occurrence is excluded entirely."""
    from tests.m13_seed import seed_second_revision

    base, cid, occ = await _seed_use(client, b"trk08")
    r2 = await seed_second_revision(client, base, number=2)
    r3 = await seed_second_revision(client, base, number=3)
    # an untracked second use: never offered
    cid2 = await make_composition(client, base["project_id"])
    await mint(client, cid2, base["production_revision_id"], 0,
               name="Untracked")
    await _put(client, cid, occ, "TRACK_COMPATIBLE", 0)

    r = await client.get(
        f"/production-objects/{base['production_object_id']}"
        "/revision-updates")
    body = r.json()
    assert body["tracked_use_count"] == 1
    use = body["uses"][0]
    numbers = [c["revision_number"] for c in use["candidates"]]
    assert numbers == [3, 2]
    assert use["assessment_created"] is False
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM "
            "production_compatibility_assessments"))).scalar_one()
    assert n == 0
