"""Ownership transaction tests (plan §50, §51, §106 req. #8).

These prove the BEGIN IMMEDIATE ownership pattern end-to-end through the helper:

  * concurrent writers serialize via the RESERVED lock (plan §50);
  * a fenced check+write is atomic (concurrent takeover -> exactly one winner,
    no split brain);
  * a split-connection check-then-write is demonstrably unsafe (plan §51), which
    is exactly why the helper performs both on one connection under one tx.
"""

from __future__ import annotations

import asyncio
import time

from sqlalchemy import text

from soloring.worker.ownership import (
    LEASE_NAME,
    LeaseAcquisitionResult,
    acquire_worker_lease,
    read_lease,
)


async def test_begin_immediate_serializes_concurrent_writers(engine) -> None:
    """A held BEGIN IMMEDIATE transaction must block a second fenced writer.

    This is the one-connection / one-BEGIN-IMMEDIATE invariant (plan §50) made
    observable: writer 2 cannot proceed until writer 1 commits.
    """
    hold = 0.5

    async def hold_lock() -> None:
        async with engine.connect() as conn:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await asyncio.sleep(hold)
            await conn.exec_driver_sql("COMMIT")

    holder = asyncio.create_task(hold_lock())
    await asyncio.sleep(0.08)  # let the holder acquire the RESERVED lock first

    t0 = time.monotonic()
    await acquire_worker_lease(engine, "worker-B", ttl_seconds=30)
    elapsed = time.monotonic() - t0
    await holder

    assert elapsed >= hold * 0.6, (
        f"fenced op did not block on the held lock (elapsed={elapsed:.3f}s); "
        "BEGIN IMMEDIATE serialization is not in effect"
    )


async def test_concurrent_takeover_has_exactly_one_winner(engine, age_heartbeat) -> None:
    """Two concurrent takeovers must not both succeed (no split brain).

    Because each acquire runs check+write under one BEGIN IMMEDIATE on one
    connection, the operations serialize: the first takes over, the second sees
    a fresh lease owned by the winner and is denied. This is the functional
    proof of plan §106 requirement #8 (ownership helper keeps one connection for
    the full transaction).
    """
    await acquire_worker_lease(engine, "worker-A", ttl_seconds=30)
    await age_heartbeat(engine, seconds=999)

    b, c = await asyncio.gather(
        acquire_worker_lease(engine, "worker-B", ttl_seconds=30),
        acquire_worker_lease(engine, "worker-C", ttl_seconds=30),
    )

    winners = [r for r in (b, c) if r is LeaseAcquisitionResult.TAKEN_OVER]
    denied = [r for r in (b, c) if r is LeaseAcquisitionResult.HELD_BY_OTHER]
    assert len(winners) == 1, f"expected exactly one winner, got {(b, c)}"
    assert len(denied) == 1, f"expected exactly one denied, got {(b, c)}"

    owner = (await read_lease(engine)).worker_id
    assert owner in ("worker-B", "worker-C")


async def test_split_connection_check_then_write_is_unsafe(engine, age_heartbeat) -> None:
    """Negative connection-safety test (plan §51).

    A read of lease authority on connection X is NOT fenced against a concurrent
    write on connection Y. Between X's read and any later write, the committed
    truth can change, so a split check+write can act on stale authority. This is
    precisely why the ownership helper does check+write on ONE connection under
    ONE BEGIN IMMEDIATE rather than composing them across connections.
    """
    await acquire_worker_lease(engine, "worker-A", ttl_seconds=30)

    # Authority "check" on connection X (no transaction held across the gap).
    async with engine.connect() as cx:
        read_owner = (
            await cx.execute(
                text("SELECT worker_id FROM worker_leases WHERE name = :n"),
                {"n": LEASE_NAME},
            )
        ).scalar()
    assert read_owner == "worker-A"

    # A separate committed transaction takes the lease over.
    await age_heartbeat(engine, seconds=999)
    await acquire_worker_lease(engine, "worker-B", ttl_seconds=30)

    truth = (await read_lease(engine)).worker_id
    # The earlier read is now stale relative to the committed truth.
    assert read_owner == "worker-A"
    assert truth == "worker-B"
    assert read_owner != truth


async def test_commit_persists_and_rollback_undoes(engine) -> None:
    """The driver-level COMMIT/ROLLBACK around the fence behave correctly."""
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(
            text("INSERT INTO worker_leases(name, worker_id, acquired_at, heartbeat_at) "
                 "VALUES ('other','x','t','t')")
        )
        await conn.exec_driver_sql("COMMIT")
    async with engine.connect() as conn:
        n = (await conn.execute(text("SELECT count(*) FROM worker_leases WHERE name='other'"))).scalar()
    assert n == 1

    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(text("DELETE FROM worker_leases WHERE name='other'"))
        await conn.exec_driver_sql("ROLLBACK")
    async with engine.connect() as conn:
        n = (await conn.execute(text("SELECT count(*) FROM worker_leases WHERE name='other'"))).scalar()
    assert n == 1  # rollback undid the delete
