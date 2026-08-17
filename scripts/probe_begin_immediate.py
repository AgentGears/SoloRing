"""Diagnostic probe: prove the BEGIN IMMEDIATE ownership pattern.

Not a unit test — a one-shot diagnostic that prints what actually works for
SQLAlchemy 2.x async + aiosqlite, so the ownership module can be built on the
proven incantation rather than the plan's illustrative snippet (plan §50:
"The exact SQLAlchemy configuration must be proven in tests early").

Run:  .venv/Scripts/python.exe scripts/probe_begin_immediate.py
"""

from __future__ import annotations

import asyncio
import tempfile
import time
from pathlib import Path

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine

from soloring.db.base import Base


def _attach_pragmas(sync_engine) -> None:
    @event.listens_for(sync_engine, "connect")
    def _set(c, r):  # noqa: ANN001
        cur = c.cursor()
        try:
            for p in (
                "PRAGMA journal_mode=WAL",
                "PRAGMA foreign_keys=ON",
                "PRAGMA busy_timeout=5000",
                "PRAGMA synchronous=NORMAL",
            ):
                cur.execute(p)
        finally:
            cur.close()


async def aproach_a(engine) -> str:
    """engine.connect() + exec_driver_sql('BEGIN IMMEDIATE') + conn.execute()."""
    try:
        async with engine.connect() as conn:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await conn.execute(text("INSERT INTO probe_kv(k,v) VALUES ('a',1)"))
            await conn.exec_driver_sql("COMMIT")
        return "OK"
    except Exception as e:  # noqa: BLE001
        return f"FAILED -> {type(e).__name__}: {e}"


async def aproach_b(url) -> str:
    """engine.begin() on an engine created with isolation_level='IMMEDIATE'."""
    try:
        eng = create_async_engine(url, future=True, isolation_level="IMMEDIATE")
        _attach_pragmas(eng.sync_engine)
        try:
            async with eng.begin() as conn:
                await conn.execute(text("INSERT INTO probe_kv(k,v) VALUES ('b',1)"))
            return "OK"
        finally:
            await eng.dispose()
    except Exception as e:  # noqa: BLE001
        return f"FAILED -> {type(e).__name__}: {e}"


async def concurrency_probe(engine) -> str:
    """Two concurrent BEGIN IMMEDIATE must serialize.

    Writer 1 holds the RESERVED lock for HOLD seconds. Writer 2's BEGIN IMMEDIATE
    must BLOCK (busy_timeout) until writer 1 commits. We measure writer 2's BEGIN
    latency: ~HOLD means serialized; ~0 means no locking (broken).
    """
    HOLD = 0.6

    async def writer(tag: str, hold: float, begin_latency: dict[str, float]) -> None:
        async with engine.connect() as conn:
            t0 = time.monotonic()
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            begin_latency[tag] = time.monotonic() - t0
            await conn.execute(
                text("INSERT INTO probe_kv(k,v) VALUES (:k,1)"), {"k": tag}
            )
            if hold:
                await asyncio.sleep(hold)
            await conn.exec_driver_sql("COMMIT")

    latencies: dict[str, float] = {}
    t0 = time.monotonic()

    async def w1():
        await writer("w1", HOLD, latencies)

    async def w2():
        # small stagger so w1 acquires the lock first
        await asyncio.sleep(0.05)
        await writer("w2", 0.0, latencies)

    await asyncio.gather(w1(), w2())
    elapsed = time.monotonic() - t0
    w2_begin = latencies.get("w2", -1)
    serialized = w2_begin >= HOLD * 0.7
    return (
        f"w2 BEGIN latency={w2_begin:.3f}s, total={elapsed:.3f}s, "
        f"serialized={serialized}"
    )


async def split_connection_hazard(engine) -> str:
    """Demonstrate why the authority check + mutation must share one connection.

    A reads the lease (authority check). Before B (the split writer) commits its
    takeover, A's read is already stale. With separate connections there is no
    atomic fence, so a reader can act on a value a concurrent writer is changing.
    """
    # Seed: worker OLD owns the lease.
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(
            text(
                "INSERT INTO worker_leases(name, worker_id, acquired_at, heartbeat_at) "
                "VALUES ('generation-worker','OLD','t0','t0')"
            )
        )
        await conn.exec_driver_sql("COMMIT")

    # Reader A checks on connection A (no transaction held across the gap).
    async with engine.connect() as conn_a:
        row_a = (
            await conn_a.execute(
                text("SELECT worker_id FROM worker_leases WHERE name='generation-worker'")
            )
        ).scalar()

    # Concurrent takeover by NEW on a separate committed transaction.
    async with engine.connect() as conn_b:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(
            text(
                "UPDATE worker_leases SET worker_id='NEW' "
                "WHERE name='generation-worker'"
            )
        )
        await conn.exec_driver_sql("COMMIT")

    # A's cached read is now stale relative to the committed truth.
    async with engine.connect() as conn_c:
        truth = (
            await conn_c.execute(
                text("SELECT worker_id FROM worker_leases WHERE name='generation-worker'")
            )
        ).scalar()

    stale = row_a != truth
    return f"A_read={row_a!r} but committed_truth={truth!r} -> read_was_stale={stale}"


async def main() -> None:
    tmpdir = Path(tempfile.mkdtemp())
    db = tmpdir / "probe.db"
    url = f"sqlite+aiosqlite:///{db.as_posix()}"

    engine = create_async_engine(url, future=True)
    _attach_pragmas(engine.sync_engine)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS probe_kv (k TEXT PRIMARY KEY, v INTEGER)"
        )

    print("[A ]", await aproach_a(engine))
    print("[B ]", await aproach_b(url))
    print("[C ] concurrency:", await concurrency_probe(engine))
    print("[D ] split-conn hazard:", await split_connection_hazard(engine))

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
