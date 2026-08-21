"""Third re-gate — narrow patch regressions.

P3-3: no-clobber staging publication under a BARRIER-controlled race
      (both finalizers reach the publication primitive simultaneously;
      different bytes → exactly one winner + one integrity conflict).
P3-4: the external-effect authority primitive is RETAINING —
      expired-but-not-taken lease → retain refreshes and BLOCKS takeover;
      taken-over lease → effect refused even when the generation row
      itself is not yet stale/adopted.
P3-5: create_generation_request survives a forced revision-collision
      rollback (no post-rollback ORM dereference).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading

import httpx
import pytest
from sqlalchemy import text

from soloring.api.schemas.projects import ProjectCreate
from soloring.api.schemas.references import ReferenceInput
from soloring.api.schemas.shots import ShotCreate
from soloring.assets.blob_store import BlobStore
from soloring.domain import projects, references, shots
from soloring.errors import ErrorCode
from soloring.executors.base import CancelResult, ExecutionHandle
from soloring.executors.comfy import outputs as outputs_mod
from soloring.executors.comfy.outputs import (
    OutputInvalid,
    ResolvedComfyOutput,
    fetch_output_to_staging,
)
from soloring.worker import ownership
from soloring.worker.execution import _cancel_if_requested

PNG = b"\x89PNG\r\n\x1a\n" + b"payload" * 8


# --- P3-3: barrier-controlled no-clobber race ------------------------------------


async def test_barrier_controlled_conflicting_publication_conflicts(tmp_path,
                                                                    monkeypatch):
    ref = ResolvedComfyOutput(
        output_key="video:0", logical_name="video", expected_kind="video",
        accepted_media_types=None, filename="out.webp", subfolder="",
    )

    def provider(content):
        state = {"pos": 0}

        def fetch(filename, subfolder, _read=1 << 20):
            data = content
            pos = state["pos"]
            if pos >= len(data):
                state["pos"] = 0
                return b""
            chunk = data[pos:pos + _read]
            state["pos"] = pos + len(chunk)
            return chunk

        return fetch

    a_bytes = b"RIFF-AAAAAAAAAAAAAAAA"
    b_bytes = b"RIFF-BBBBBBBBBBBBBBBB"

    # BOTH finalizers reach the publication primitive simultaneously: the
    # barrier sits INSIDE os.link, so neither can observe the other's
    # completed placement first. Under exists()+replace both would succeed
    # and silently clobber; under the link interlock exactly one lands.
    real_link = outputs_mod.os.link
    barrier = threading.Barrier(2, timeout=10)

    def barrier_link(src, dst):
        barrier.wait()
        return real_link(src, dst)

    monkeypatch.setattr(outputs_mod.os, "link", barrier_link)

    results = await asyncio.gather(
        fetch_output_to_staging(provider(a_bytes), ref, tmp_path),
        fetch_output_to_staging(provider(b_bytes), ref, tmp_path),
        return_exceptions=True,
    )
    monkeypatch.undo()

    errors = [r for r in results if isinstance(r, OutputInvalid)]
    successes = [r for r in results if not isinstance(r, Exception)]
    assert len(errors) == 1 and len(successes) == 1, results
    content = successes[0].read_bytes()
    assert content in (a_bytes, b_bytes)
    # No temp debris from either side.
    assert list(tmp_path.glob("*.tmp")) == []


async def test_barrier_controlled_identical_publication_converges(
    tmp_path, monkeypatch,
):
    ref = ResolvedComfyOutput(
        output_key="video:0", logical_name="video", expected_kind="video",
        accepted_media_types=None, filename="out.webp", subfolder="",
    )

    def provider(content):
        state = {"pos": 0}

        def fetch(filename, subfolder, _read=1 << 20):
            data = content
            pos = state["pos"]
            if pos >= len(data):
                state["pos"] = 0
                return b""
            chunk = data[pos:pos + _read]
            state["pos"] = pos + len(chunk)
            return chunk

        return fetch

    payload = b"RIFF-IDENTICAL-VERIFIED-BYTES"
    real_link = outputs_mod.os.link
    barrier = threading.Barrier(2, timeout=10)

    def barrier_link(src, dst):
        barrier.wait()
        return real_link(src, dst)

    monkeypatch.setattr(outputs_mod.os, "link", barrier_link)
    results = await asyncio.gather(
        fetch_output_to_staging(provider(payload), ref, tmp_path),
        fetch_output_to_staging(provider(payload), ref, tmp_path),
    )
    monkeypatch.undo()
    assert results[0] == results[1]
    assert results[0].read_bytes() == payload
    assert list(tmp_path.glob("*.tmp")) == []


async def test_unsupported_no_clobber_filesystem_fails_closed(
    tmp_path, monkeypatch,
):
    """Final M5A re-gate: when os.link cannot provide atomic no-clobber
    publication, the fetch FAILS CLOSED — never degrades to an
    overwrite-capable replace — and any existing staged target is
    preserved byte-for-byte."""
    from soloring.executors.comfy.outputs import OutputFetchFailed

    ref = ResolvedComfyOutput(
        output_key="video:0", logical_name="video", expected_kind="video",
        accepted_media_types=None, filename="out.webp", subfolder="",
    )

    def provider(content):
        state = {"pos": 0}

        def fetch(filename, subfolder, _read=1 << 20):
            data = content
            pos = state["pos"]
            if pos >= len(data):
                state["pos"] = 0
                return b""
            chunk = data[pos:pos + _read]
            state["pos"] = pos + len(chunk)
            return chunk

        return fetch

    def unsupported_link(src, dst):
        raise OSError(1, "Operation not permitted")

    monkeypatch.setattr(outputs_mod.os, "link", unsupported_link)

    # No existing target: fail closed, no target created, no temp debris.
    with pytest.raises(OutputFetchFailed, match="no-clobber"):
        await fetch_output_to_staging(
            provider(b"RIFF-FRESH-BYTES"), ref, tmp_path,
        )
    assert not (tmp_path / "video-0.staged").exists()
    assert list(tmp_path.glob("*.tmp")) == []

    # With an existing staged target: still fail closed, and the existing
    # verified bytes are preserved — never overwritten by the fallback.
    target = tmp_path / "video-0.staged"
    target.write_bytes(b"RIFF-PREEXISTING-WINNER")
    with pytest.raises(OutputFetchFailed, match="no-clobber"):
        await fetch_output_to_staging(
            provider(b"RIFF-DIVERGENT-BYTES"), ref, tmp_path,
        )
    assert target.read_bytes() == b"RIFF-PREEXISTING-WINNER"
    assert list(tmp_path.glob("*.tmp")) == []


# --- P3-4: retaining authority primitive ------------------------------------------


async def _seed_fake_generation(client, factory, engine, settings) -> str:
    import soloring.api.generations as generations_api

    settings.executor = "fake"
    saved = generations_api.get_settings
    generations_api.get_settings = lambda: settings
    try:
        async with factory() as s:
            pid = (await projects.create_project(
                s, ProjectCreate(name="P"))).id
            shot = await shots.create_shot(s, pid, ShotCreate(subject="Eva"))
        bh = hashlib.sha256(PNG).hexdigest()
        path = BlobStore(settings).path_for_hash(bh)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(PNG)
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        from soloring.db.models import Asset, Blob
        from soloring.domain.ids import new_uuid

        aid = new_uuid()
        f = async_sessionmaker(bind=engine, expire_on_commit=False,
                               class_=AsyncSession)
        async with f() as s:
            s.add(Blob(hash=bh, path=f"sha256/{bh[:2]}/{bh[2:4]}/{bh}",
                       size_bytes=len(PNG), detected_media_type="image/png"))
            await s.flush()
            s.add(Asset(id=aid, project_id=pid, blob_hash=bh,
                        kind="reference"))
            await s.commit()
        async with f() as s:
            await references.replace_references(
                s, shot.id,
                [ReferenceInput(asset_id=aid, role="reference")],
            )
        r = await client.post(f"/shots/{shot.id}/generations")
        assert r.status_code == 202, r.text
        return r.json()["id"]
    finally:
        generations_api.get_settings = saved


async def _age_lease_only(engine):
    """Expire the LEASE heartbeat without touching the generation row."""
    from soloring.db.timeutil import db_now_minus_sql

    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(text(
            "UPDATE worker_leases SET heartbeat_at = "
            + db_now_minus_sql(9999) + " WHERE name = 'generation-worker'"
        ))
        await conn.exec_driver_sql("COMMIT")


async def test_retaining_authority_blocks_takeover_after_expired_lease(
    client, factory, engine, settings,
):
    """A's lease is EXPIRED but not yet taken: the retaining primitive
    refreshes it, so a successor can no longer steal the interval — the
    stale-owner external-effect race is closed from both ends."""
    gid = await _seed_fake_generation(client, factory, engine, settings)

    a = "w-r3a"
    await ownership.acquire_worker_lease(
        engine, a, settings.worker_lease_ttl_seconds
    )
    await ownership.claim_next_generation(engine, a)

    await _age_lease_only(engine)  # owner is still A; TTL window spent

    # A proves authority for an external effect: the RETAINING check
    # refreshes the heartbeat inside the proof itself.
    r = await ownership.verify_execution_authority(engine, a, gid)
    assert r is ownership.OwnershipMutationResult.OK

    # The takeover attempt now fails — A holds a fresh interval.
    b = "w-r3b"
    result = await ownership.acquire_worker_lease(
        engine, b, settings.worker_lease_ttl_seconds
    )
    assert result is ownership.LeaseAcquisitionResult.HELD_BY_OTHER


async def test_taken_over_lease_refuses_effect_even_with_fresh_generation(
    client, factory, engine, settings,
):
    """B takes the expired lease BEFORE A's check (generation row itself
    still fresh and owned by A): the conditional refresh fails → the
    external executor cancel never happens."""
    gid = await _seed_fake_generation(client, factory, engine, settings)

    a = "w-r3c"
    await ownership.acquire_worker_lease(
        engine, a, settings.worker_lease_ttl_seconds
    )
    await ownership.claim_next_generation(engine, a)
    handle = ExecutionHandle(kind="fake", job_id="job-1")
    await ownership.persist_owned_executor_handle(
        engine, a, gid, handle.job_id, "{}"
    )

    await _age_lease_only(engine)
    b = "w-r3b2"
    assert await ownership.acquire_worker_lease(
        engine, b, settings.worker_lease_ttl_seconds
    ) is ownership.LeaseAcquisitionResult.TAKEN_OVER

    # Persist the cancellation intent, then stale A tries to reconcile.
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(text(
            "UPDATE generations SET cancel_requested_at = "
            "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :g"
        ), {"g": gid})
        await conn.exec_driver_sql("COMMIT")

    calls = {"cancel": 0}

    class CountingExecutor:
        async def cancel(self, handle):
            calls["cancel"] += 1
            return CancelResult.CANCELLED

    outcome = await _cancel_if_requested(
        engine, a, gid, CountingExecutor(), handle
    )
    assert outcome == "halt"
    assert calls["cancel"] == 0


# --- P3-5: forced revision-collision rollback ------------------------------------


async def test_create_generation_survives_revision_rollback(
    client, factory, engine, settings, monkeypatch,
):
    """The exact third-gate reproduction: capture_revision rolls the
    session back (collision path), expiring previously loaded ORM state.
    The service must build the draft from the PRIMITIVE shot_id — never a
    detached shot.id dereference."""
    import soloring.api.generations as generations_api
    from soloring.domain import revisions as revisions_mod

    settings.executor = "fake"
    saved_settings = generations_api.get_settings
    generations_api.get_settings = lambda: settings
    try:
        async with factory() as s:
            pid = (await projects.create_project(
                s, ProjectCreate(name="P"))).id
            shot = await shots.create_shot(s, pid, ShotCreate(subject="Eva"))
        bh = hashlib.sha256(PNG).hexdigest()
        path = BlobStore(settings).path_for_hash(bh)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(PNG)
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        from soloring.db.models import Asset, Blob
        from soloring.domain.ids import new_uuid

        aid = new_uuid()
        f = async_sessionmaker(bind=engine, expire_on_commit=False,
                               class_=AsyncSession)
        async with f() as s:
            s.add(Blob(hash=bh, path=f"sha256/{bh[:2]}/{bh[2:4]}/{bh}",
                       size_bytes=len(PNG),
                       detected_media_type="image/png"))
            await s.flush()
            s.add(Asset(id=aid, project_id=pid, blob_hash=bh,
                        kind="reference"))
            await s.commit()
        async with f() as s:
            await references.replace_references(
                s, shot.id,
                [ReferenceInput(asset_id=aid, role="reference")],
            )

        real_capture = revisions_mod.capture_revision
        forced = {"done": False}

        async def colliding_capture(session, shot_id_, **kwargs):
            if not forced["done"]:
                forced["done"] = True
                await session.rollback()  # expire pre-loaded ORM state
            return await real_capture(session, shot_id_)

        monkeypatch.setattr(revisions_mod, "capture_revision",
                            colliding_capture)

        r = await client.post(f"/shots/{shot.id}/generations")
        assert r.status_code == 202, r.text
        gid = r.json()["id"]
        async with engine.connect() as conn:
            row = (await conn.execute(text(
                "SELECT shot_id, status FROM generations WHERE id=:g"),
                {"g": gid})).mappings().one()
        assert row["shot_id"] == shot.id
        assert row["status"] == "queued"
    finally:
        generations_api.get_settings = saved_settings
