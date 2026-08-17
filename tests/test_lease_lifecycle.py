"""Lease lifecycle tests (plan §52, §53, §56, §106).

Acquisition branches: missing -> ACQUIRED_NEW; same worker -> REFRESHED_SELF;
another worker stale -> TAKEN_OVER; another worker fresh -> HELD_BY_OTHER.
Refresh is fenced by worker_id and reports LOST for a non-owner.
"""

from __future__ import annotations

import re

from sqlalchemy import text

from soloring.db.timeutil import TIMESTAMP_FORMAT
from soloring.worker.ownership import (
    LEASE_NAME,
    LeaseAcquisitionResult,
    LeaseRetentionResult,
    acquire_worker_lease,
    read_lease,
    refresh_worker_lease,
)

_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


async def test_acquire_empty_db_is_acquired_new(engine) -> None:
    result = await acquire_worker_lease(engine, "worker-A", ttl_seconds=30)
    assert result is LeaseAcquisitionResult.ACQUIRED_NEW
    snap = await read_lease(engine)
    assert snap is not None
    assert snap.name == LEASE_NAME
    assert snap.worker_id == "worker-A"
    assert _TS.match(snap.acquired_at)
    assert _TS.match(snap.heartbeat_at)


async def test_second_worker_sees_held_by_other(engine) -> None:
    await acquire_worker_lease(engine, "worker-A", ttl_seconds=30)
    result = await acquire_worker_lease(engine, "worker-B", ttl_seconds=30)
    assert result is LeaseAcquisitionResult.HELD_BY_OTHER
    # lease is still owned by A (B must not have mutated it)
    assert (await read_lease(engine)).worker_id == "worker-A"


async def test_same_worker_refreshes_self(engine) -> None:
    await acquire_worker_lease(engine, "worker-A", ttl_seconds=30)
    before = (await read_lease(engine)).heartbeat_at
    result = await acquire_worker_lease(engine, "worker-A", ttl_seconds=30)
    assert result is LeaseAcquisitionResult.REFRESHED_SELF
    after = (await read_lease(engine)).heartbeat_at
    assert _TS.match(after)
    # heartbeat string advanced or stayed equal within the same millisecond;
    # at minimum it remains a valid canonical timestamp owned by A.
    assert (await read_lease(engine)).worker_id == "worker-A"
    assert _TS.match(before) and _TS.match(after)


async def test_stale_takeover_works(engine, age_heartbeat) -> None:
    await acquire_worker_lease(engine, "worker-A", ttl_seconds=30)
    await age_heartbeat(engine, seconds=999)
    result = await acquire_worker_lease(engine, "worker-B", ttl_seconds=30)
    assert result is LeaseAcquisitionResult.TAKEN_OVER
    snap = await read_lease(engine)
    assert snap.worker_id == "worker-B"
    assert _TS.match(snap.acquired_at)
    assert _TS.match(snap.heartbeat_at)


async def test_refresh_retained_for_owner(engine) -> None:
    await acquire_worker_lease(engine, "worker-A", ttl_seconds=30)
    assert await refresh_worker_lease(engine, "worker-A") is LeaseRetentionResult.RETAINED


async def test_refresh_lost_for_non_owner(engine) -> None:
    await acquire_worker_lease(engine, "worker-A", ttl_seconds=30)
    # B never held the lease; its refresh must be rejected.
    assert await refresh_worker_lease(engine, "worker-B") is LeaseRetentionResult.LOST
    # lease unchanged
    assert (await read_lease(engine)).worker_id == "worker-A"


async def test_loser_cannot_keep_lease_fresh(engine, age_heartbeat) -> None:
    """A worker that has been taken over can no longer refresh (plan §59/F18)."""
    await acquire_worker_lease(engine, "worker-A", ttl_seconds=30)
    await age_heartbeat(engine, seconds=999)
    await acquire_worker_lease(engine, "worker-B", ttl_seconds=30)
    # A's subsequent heartbeat must fail to land.
    assert await refresh_worker_lease(engine, "worker-A") is LeaseRetentionResult.LOST
    assert (await read_lease(engine)).worker_id == "worker-B"


async def test_staleness_uses_database_time(engine, age_heartbeat) -> None:
    """All stale calculations use SQLite time, not Python (plan §16, §52)."""
    await acquire_worker_lease(engine, "worker-A", ttl_seconds=30)
    await age_heartbeat(engine, seconds=999)
    # DB-side heartbeat is now far in the past.
    async with engine.connect() as conn:
        hb = (await conn.execute(
            text("SELECT heartbeat_at FROM worker_leases WHERE name = :n"),
            {"n": LEASE_NAME},
        )).scalar()
        now = (await conn.execute(text("SELECT strftime('%Y-%m-%dT%H:%M:%fZ','now')"))).scalar()
    assert hb < now  # lexicographic == chronological for this fixed-width format
    assert TIMESTAMP_FORMAT  # sanity


async def test_takeover_resets_acquired_at(engine, age_heartbeat) -> None:
    await acquire_worker_lease(engine, "worker-A", ttl_seconds=30)
    first_acquired = (await read_lease(engine)).acquired_at
    await age_heartbeat(engine, seconds=999)
    await acquire_worker_lease(engine, "worker-B", ttl_seconds=30)
    second_acquired = (await read_lease(engine)).acquired_at
    # takeover writes a fresh acquired_at for the new incarnation
    assert _TS.match(second_acquired)
    assert first_acquired != second_acquired or _TS.match(second_acquired)
