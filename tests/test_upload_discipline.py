"""Upload discipline instrumentation (plan §22.2, §23, §47, §50.8).

Explicit acceptance proofs (not structural inference):
  * every stream read is bounded by upload_chunk_bytes (no bare read());
  * blocking writes are dispatched off the event loop — a ticker keeps
    progressing while writes sleep synchronously;
  * no DB session is open while bytes are being streamed (session windows are
    disjoint from read times).
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from pathlib import Path

from soloring.assets.upload import _stream_to_temp, upload_reference_asset
from soloring.settings import Settings


class FakeUploadFile:
    """Minimal UploadFile double: records read sizes and read times."""

    def __init__(self, payload: bytes) -> None:
        self._buf = payload
        self._pos = 0
        self.read_sizes: list[int] = []
        self.read_times: list[float] = []
        self.read_lengths: list[int] = []
        self.content_type = "image/png"
        self.filename = "probe.png"

    async def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        if size is None or size < 0:
            chunk = self._buf[self._pos:]
        else:
            chunk = self._buf[self._pos : self._pos + size]
        self._pos += len(chunk)
        if chunk:
            # Only byte-carrying reads timestamp the streaming phase; the
            # final empty read transfers nothing and may abut a session open.
            self.read_times.append(time.monotonic())
            self.read_lengths.append(len(chunk))
        return chunk


async def test_stream_reads_are_bounded(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, upload_chunk_bytes=4096)
    settings.ensure_storage_dirs()
    data = b"\x89PNG\r\n\x1a\n" + b"x" * 40_000

    fake = FakeUploadFile(data)
    tmp = settings.tmp_dir / "bounded.tmp"
    bh, total, detected = await _stream_to_temp(fake, tmp, settings)

    assert total == len(data)
    assert bh == hashlib.sha256(data).hexdigest()
    assert detected == "image/png"
    assert len(fake.read_sizes) >= 5, "upload must actually stream in chunks"
    assert all(s == 4096 for s in fake.read_sizes), (
        f"unbounded read detected: sizes={fake.read_sizes[:5]}..."
    )
    assert tmp.read_bytes() == data
    tmp.unlink()


async def test_streaming_does_not_block_event_loop(tmp_path: Path, monkeypatch) -> None:
    import builtins

    settings = Settings(data_dir=tmp_path, upload_chunk_bytes=4096)
    settings.ensure_storage_dirs()
    data = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 336  # ~86 KiB -> ~21 writes

    write_sleep = 0.03
    holder: dict = {}

    class SlowWriter:
        def __init__(self, inner) -> None:
            self._inner = inner
            self.writes = 0

        def write(self, b: bytes) -> int:
            time.sleep(write_sleep)  # synchronous stall (in a worker thread)
            self.writes += 1
            return self._inner.write(b)

        def close(self) -> None:
            self._inner.close()

    real_open = builtins.open

    def patched_open(file, mode="r", *args, **kwargs):
        fh = real_open(file, mode, *args, **kwargs)
        if "w" in mode:
            w = SlowWriter(fh)
            holder["writer"] = w
            return w
        return fh

    monkeypatch.setattr(builtins, "open", patched_open)

    ticks = 0
    done = asyncio.Event()

    async def ticker() -> None:
        nonlocal ticks
        while not done.is_set():
            ticks += 1
            await asyncio.sleep(0.001)

    task = asyncio.create_task(ticker())
    try:
        tmp = settings.tmp_dir / "slow.tmp"
        bh, total, _ = await _stream_to_temp(FakeUploadFile(data), tmp, settings)
    finally:
        done.set()
        await task

    assert total == len(data)
    assert bh == hashlib.sha256(data).hexdigest()
    writer = holder["writer"]
    blocking_seconds = writer.writes * write_sleep
    assert blocking_seconds >= 0.45, f"expected sustained slow writes, got {writer.writes}"
    # If writes were awaited on the loop, the ticker would stall (~0 ticks
    # during ~0.5s). Via to_thread it keeps ticking throughout.
    assert ticks > 50, f"event loop starved during streaming: ticks={ticks}"
    tmp.unlink()


async def test_no_db_session_open_while_streaming(
    tmp_path: Path, factory, monkeypatch
) -> None:
    """Session windows must be disjoint from byte-read times (plan §47)."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from soloring.api.schemas.projects import ProjectCreate
    from soloring.assets.blob_store import BlobStore
    from soloring.domain import projects

    settings = Settings(data_dir=tmp_path)
    settings.ensure_storage_dirs()

    async with factory() as s:
        pid = (await projects.create_project(s, ProjectCreate(name="P"))).id

    events: list[tuple[str, float]] = []

    class _SessionProxy:
        def __init__(self, real: AsyncSession) -> None:
            self._real = real

        async def __aenter__(self) -> AsyncSession:
            await self._real.__aenter__()
            events.append(("open", time.monotonic()))
            return self._real

        async def __aexit__(self, *exc) -> None:
            try:
                return await self._real.__aexit__(*exc)
            finally:
                events.append(("close", time.monotonic()))

    def tracking_factory():
        return _SessionProxy(factory())

    data = b"\x89PNG\r\n\x1a\n" + b"z" * 100
    fake = FakeUploadFile(data)

    asset, detected = await upload_reference_asset(
        tracking_factory, settings, BlobStore(settings), pid, fake
    )
    assert asset.blob_hash == hashlib.sha256(data).hexdigest()
    assert detected == "image/png"

    # Short, non-overlapping units (project check, row check, persist).
    opens = [t for kind, t in events if kind == "open"]
    closes = [t for kind, t in events if kind == "close"]
    assert len(opens) == len(closes) == 3, events
    for i in range(len(closes) - 1):
        assert closes[i] <= opens[i + 1], "sessions must not overlap"

    # The core discipline: no byte-carrying read happened strictly inside any
    # open-session window.
    windows = list(zip(opens, closes))
    assert fake.read_times, "no reads recorded"
    for rt in fake.read_times:
        for o, c in windows:
            assert not (o < rt < c), (
                f"a DB session was open while upload bytes were being read "
                f"(read at {rt}, window {o}..{c})"
            )
