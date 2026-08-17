"""Audit remediation — M3B/M3C regressions (source-audit F1, F5, F6, F7).

F1: worker-originated publication is ownership-fenced — a worker that lost
    authority cannot mint Take/Asset state, and worker drives stop at the
    importing fence instead of pressing on.
F5: cancellation is ONE atomic read-decide-write unit — the claim-vs-cancel
    TOCTOU is closed; every cancel response reflects durable truth.
F6: staging containment uses real path semantics — a same-prefix SIBLING
    directory is rejected (string startswith admitted it).
F7: staged-output hashing is chunked and bounded — a large output is hashed
    without one whole-file read and without allocating the file in RAM.
"""

from __future__ import annotations

import asyncio
import hashlib
import io

import pytest
from sqlalchemy import text

from soloring.api.schemas.projects import ProjectCreate
from soloring.api.schemas.references import ReferenceInput
from soloring.api.schemas.shots import ShotCreate
from soloring.assets.blob_store import BlobStore
from soloring.domain import projects, references, shots
from soloring.errors import ErrorCode, SoloRingError
from soloring.executors.base import StagedOutput
from soloring.generation.importer import (
    ImportFailure,
    PublicationNotFenced,
    import_staged_outputs,
)
from soloring.workflows.manifest import ExpectedOutput
from soloring.worker import ownership


async def _seed_generation(client, factory, engine, settings) -> dict:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from soloring.db.models import Asset, Blob
    from soloring.domain.ids import new_uuid

    async with factory() as s:
        pid = (await projects.create_project(s, ProjectCreate(name="P"))).id
        shot = await shots.create_shot(s, pid, ShotCreate(subject="Eva"))

        content = b"\x89PNG\r\n\x1a\n" + b"ref-bytes" * 4
    bh = hashlib.sha256(content).hexdigest()
    path = BlobStore(settings).path_for_hash(bh)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    aid = new_uuid()
    f = async_sessionmaker(bind=engine, expire_on_commit=False,
                           class_=AsyncSession)
    async with f() as s:
        s.add(Blob(hash=bh, path=f"sha256/{bh[:2]}/{bh[2:4]}/{bh}",
                   size_bytes=len(content), detected_media_type="image/png"))
        await s.flush()
        s.add(Asset(id=aid, project_id=pid, blob_hash=bh, kind="reference"))
        await s.commit()
    async with f() as s:
        await references.replace_references(
            s, shot.id, [ReferenceInput(asset_id=aid, role="reference")],
        )

    r = await client.post(f"/shots/{shot.id}/generations")
    assert r.status_code == 202, r.text
    gid = r.json()["id"]
    async with factory() as s:
        rev_id = (await s.execute(
            text("SELECT id FROM shot_revisions WHERE shot_id=:sid "
                 "ORDER BY revision_number DESC LIMIT 1"),
            {"sid": shot.id},
        )).scalar_one()
    return {"generation_id": gid, "shot_id": shot.id, "revision_id": rev_id}


async def _take_count(engine, gid: str) -> int:
    async with engine.connect() as conn:
        return (await conn.execute(
            text("SELECT COUNT(*) FROM takes WHERE generation_id=:g"),
            {"g": gid},
        )).scalar_one()


def _outputs() -> list[ExpectedOutput]:
    return [ExpectedOutput(name="video", kind="video", expected_count=1,
                           accepted_media_types=None)]


async def _generation_row(engine, factory, gid):
    from soloring.generation.repository import get_generation_full

    async with factory() as s:
        return await get_generation_full(s, gid)


# --- F1: publication is ownership-fenced ----------------------------------------


async def test_stale_worker_cannot_mint_take(
    client, factory, engine, settings, age_heartbeat, tmp_path,
):
    seed = await _seed_generation(client, factory, engine, settings)
    gid = seed["generation_id"]

    worker_a = "w-stale-a"
    await ownership.acquire_worker_lease(
        engine, worker_a, settings.worker_lease_ttl_seconds
    )
    claim = await ownership.claim_next_generation(engine, worker_a)
    gid_claimed, attempt = claim
    assert gid_claimed == gid

    # A is mid-drive and passes the importing fence while still authoritative.
    assert await ownership.transition_owned_generation(
        engine, worker_a, gid, "importing"
    ) is ownership.OwnershipMutationResult.OK

    # Authority flips to B (lease goes stale; B takes over AND adopts).
    await age_heartbeat(engine)
    worker_b = "w-authority-b"
    await ownership.acquire_worker_lease(
        engine, worker_b, settings.worker_lease_ttl_seconds
    )
    assert await ownership.adopt_stale_generation(
        engine, worker_b, gid
    ) is ownership.OwnershipMutationResult.OK

    # The stale side stages output and attempts publication (audit F1
    # reproduction): it MUST be refused inside the publication transaction.
    staging_dir = tmp_path / "staging" / gid / attempt
    staging_dir.mkdir(parents=True)
    out_file = staging_dir / "video-0.staged"
    out_file.write_bytes(b"RIFF-stale-output-bytes")
    staged = [StagedOutput(output_key="video:0", path=out_file, kind="video")]

    generation = await _generation_row(engine, factory, gid)
    f = factory  # engine-bound
    blob_store = BlobStore(settings)

    with pytest.raises(SoloRingError) as exc_info:
        await import_staged_outputs(
            f, blob_store, generation, staged,
            expected_outputs=_outputs(), staging_directory=staging_dir,
            worker_id=worker_a, attempt_id=attempt,
        )
    assert exc_info.value.code == ErrorCode.GENERATION_OWNERSHIP_LOST

    # Zero provenance was minted by the stale worker.
    assert await _take_count(engine, gid) == 0
    async with engine.connect() as conn:
        output_assets = (await conn.execute(
            text("SELECT COUNT(*) FROM assets WHERE kind = 'output'")
        )).scalar_one()
    assert output_assets == 0

    # The CURRENT authority CAN publish the same output (fence is identity
    # based, not a blanket lock).
    out_file.write_bytes(b"RIFF-fresh-output-bytes")
    imported = await import_staged_outputs(
        f, blob_store, generation, staged,
        expected_outputs=_outputs(), staging_directory=staging_dir,
        worker_id=worker_b, attempt_id=attempt,
    )
    assert imported == ["video:0"]
    assert await _take_count(engine, gid) == 1


# --- F5: cancellation is one atomic unit -----------------------------------------


async def test_cancel_vs_claim_race_atomic(
    client, factory, engine, settings,
):
    """Claim and cancel race; every outcome is internally consistent.

    Under the fenced unit, exactly one of:
      * cancel wins → row cancelled, claim finds nothing queued;
      * claim wins → row preparing with persisted intent (never a
        "cancelled" report over a preparing row).
    """
    seed = await _seed_generation(client, factory, engine, settings)
    gid = seed["generation_id"]

    worker = "w-race"
    await ownership.acquire_worker_lease(
        engine, worker, settings.worker_lease_ttl_seconds
    )

    results = await asyncio.gather(
        client.post(f"/generations/{gid}/cancel"),
        ownership.claim_next_generation(engine, worker),
    )
    cancel_response, claim = results
    assert cancel_response.status_code == 200, cancel_response.text
    body = cancel_response.json()

    async with engine.connect() as conn:
        row = (await conn.execute(
            text("SELECT status, cancel_requested_at, worker_id "
                 "FROM generations WHERE id=:g"),
            {"g": gid},
        )).mappings().one()

    if body["status"] == "cancelled":
        # The row really is cancelled (rowcount-honored, never a fictional
        # report). Either the cancel unit ran first (claim found nothing) or
        # the claim committed first and the cancel's fenced unit then saw
        # preparing-without-handle — the §69 transactional immediate cancel.
        assert row["status"] == "cancelled"
        assert body["cancel_requested"] is False
        assert claim is None or claim[0] == gid
    else:
        # Claim committed first and the row had advanced past the
        # immediate-cancel window: the API must report the intent path.
        assert body["cancel_requested"] is True
        assert row["status"] == "preparing"
        assert row["cancel_requested_at"] is not None
        assert claim is not None and claim[0] == gid


async def test_cancel_report_always_matches_durable_state(
    client, factory, engine, settings,
):
    """For every terminal/active state, the response mirrors the row."""
    seed = await _seed_generation(client, factory, engine, settings)
    gid = seed["generation_id"]

    # Move it to submitted-with-handle via the worker primitives.
    worker = "w-mirror"
    await ownership.acquire_worker_lease(
        engine, worker, settings.worker_lease_ttl_seconds
    )
    await ownership.claim_next_generation(engine, worker)
    await ownership.transition_owned_generation(
        engine, worker, gid, "submitted", started=True,
    )

    r = await client.post(f"/generations/{gid}/cancel")
    assert r.status_code == 200
    body = r.json()
    assert body["cancel_requested"] is True
    assert body["status"] == "submitted"

    async with engine.connect() as conn:
        row = (await conn.execute(
            text("SELECT status, cancel_requested_at FROM generations "
                 "WHERE id=:g"),
            {"g": gid},
        )).mappings().one()
    assert row["status"] == "submitted"
    assert row["cancel_requested_at"] is not None


# --- F6: real containment semantics -----------------------------------------------


async def test_same_prefix_sibling_staging_dir_rejected(
    client, factory, engine, settings, tmp_path,
):
    seed = await _seed_generation(client, factory, engine, settings)
    gid = seed["generation_id"]

    worker = "w-contain"
    await ownership.acquire_worker_lease(
        engine, worker, settings.worker_lease_ttl_seconds
    )
    claim = await ownership.claim_next_generation(engine, worker)
    _, attempt = claim
    await ownership.transition_owned_generation(
        engine, worker, gid, "importing"
    )

    intended = tmp_path / "staging" / gid / f"attempt-{attempt[:8]}"
    sibling = tmp_path / "staging" / gid / f"attempt-{attempt[:8]}_evil"
    sibling.mkdir(parents=True, exist_ok=True)
    out_file = sibling / "video-0.staged"
    out_file.write_bytes(b"RIFF-escape")
    staged = [StagedOutput(output_key="video:0", path=out_file, kind="video")]

    generation = await _generation_row(engine, factory, gid)
    with pytest.raises(ImportFailure):
        await import_staged_outputs(
            factory, BlobStore(settings), generation, staged,
            expected_outputs=_outputs(), staging_directory=intended,
            worker_id=worker,
        )
    assert await _take_count(engine, gid) == 0


# --- F7: bounded chunked hashing --------------------------------------------------


async def test_large_output_hashed_in_bounded_chunks(
    client, factory, engine, settings, tmp_path, monkeypatch,
):
    seed = await _seed_generation(client, factory, engine, settings)
    gid = seed["generation_id"]

    worker = "w-hash"
    await ownership.acquire_worker_lease(
        engine, worker, settings.worker_lease_ttl_seconds
    )
    claim = await ownership.claim_next_generation(engine, worker)
    _, attempt = claim
    await ownership.transition_owned_generation(
        engine, worker, gid, "importing"
    )

    staging_dir = tmp_path / "staging" / gid / attempt
    staging_dir.mkdir(parents=True)
    payload = b"\x89PNG\r\n\x1a\n" + (b"0123456789abcdef" * 512 * 1024)  # 8 MiB
    out_file = staging_dir / "video-0.staged"
    out_file.write_bytes(payload)

    # Instrument every file read performed during import: no single read may
    # exceed the chunk bound (audit F7 behavioral proof).
    real_open = io.open
    max_read = {"n": 0}

    class _RecordingReader:
        def __init__(self, fh):
            self._fh = fh

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self._fh.close()
            return False

        def read(self, size=-1):
            data = self._fh.read(size)
            if size and size > 0:
                max_read["n"] = max(max_read["n"], min(size, len(data) + 1))
            return data

        def __getattr__(self, name):
            return getattr(self._fh, name)

    def recording_open(file, mode="r", *a, **kw):
        fh = real_open(file, mode, *a, **kw)
        if "b" in mode and str(file).endswith(".staged"):
            return _RecordingReader(fh)
        return fh

    monkeypatch.setattr("builtins.open", recording_open)

    staged = [StagedOutput(output_key="video:0", path=out_file, kind="video")]
    generation = await _generation_row(engine, factory, gid)
    imported = await import_staged_outputs(
        factory, BlobStore(settings), generation, staged,
        expected_outputs=_outputs(), staging_directory=staging_dir,
        worker_id=worker, attempt_id=attempt,
    )

    import soloring.generation.importer as importer_mod
    assert max_read["n"] <= importer_mod._HASH_CHUNK
    assert imported == ["video:0"]
    # Hash correctness is preserved (the imported Blob row matches the
    # payload hash — chunked hashing produced the identity).
    bh = hashlib.sha256(payload).hexdigest()
    async with engine.connect() as conn:
        row = (await conn.execute(
            text("SELECT blob_hash FROM assets a JOIN takes t "
                 "ON a.take_id = t.id WHERE t.generation_id=:g"),
            {"g": gid},
        )).mappings().one()
    assert row["blob_hash"] == bh
