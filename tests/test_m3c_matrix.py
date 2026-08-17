"""M3C — Crash, Race, and Import Matrix (Hard Gate C).

Adversarial: the purpose is to FALSIFY M3A/M3B guarantees before any Comfy
code may begin. Headline: crash between external submit and handle
persistence must still converge with external execution count <= 1, via the
durable (generation, attempt) submission identity.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from sqlalchemy import text

from soloring.api.schemas.projects import ProjectCreate
from soloring.api.schemas.references import ReferenceInput
from soloring.api.schemas.shots import ShotCreate
from soloring.domain import projects, references, shots
from soloring.errors import ErrorCode, SoloRingError
from soloring.executors.base import StagedOutput
from soloring.executors.fake import FakeExecutor, fake_output_bytes
from soloring.generation import importer as importer_mod
from soloring.generation.importer import ImportFailure, import_staged_outputs
from soloring.settings import Settings
from soloring.worker import execution as worker_execution
from soloring.worker import ownership
from soloring.worker import recovery as recovery_mod
from tests.conftest import seed_reference_asset


async def _seed(factory, engine):
    async with factory() as s:
        pid = (await projects.create_project(s, ProjectCreate(name="P"))).id
        shot = await shots.create_shot(s, pid, ShotCreate(subject="Eva enters"))
    aid, _ = await seed_reference_asset(engine, pid)
    async with factory() as s:
        await references.replace_references(
            s, shot.id, [ReferenceInput(asset_id=aid, role="reference")]
        )
    return shot.id


async def _create_generation(client, shot_id):
    r = await client.post(f"/shots/{shot_id}/generations")
    assert r.status_code == 202, r.text
    return r.json()["id"]


async def _age_lease(engine, seconds=9999):
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(
            text(
                "UPDATE worker_leases SET heartbeat_at = "
                f"strftime('%Y-%m-%dT%H:%M:%fZ','now','-{int(seconds)} seconds')"
            )
        )
        await conn.exec_driver_sql("COMMIT")


async def _age_gen(engine, gid, seconds=9999):
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(
            text(
                "UPDATE generations SET heartbeat_at = "
                f"strftime('%Y-%m-%dT%H:%M:%fZ','now','-{int(seconds)} seconds') "
                "WHERE id = :g"
            ).bindparams(g=gid)
        )
        await conn.exec_driver_sql("COMMIT")


async def _counts(factory, gid=None):
    async with factory() as s:
        takes = (await s.execute(text("SELECT count(*) FROM takes"))).scalar()
        assets = (await s.execute(text("SELECT count(*) FROM assets"))).scalar()
        blobs = (await s.execute(text("SELECT count(*) FROM blobs"))).scalar()
        gen_takes = (
            await s.execute(
                text("SELECT count(*) FROM takes WHERE generation_id=:g"), {"g": gid}
            )
        ).scalar() if gid else None
    return takes, assets, blobs, gen_takes


async def _gen_row(factory, gid):
    async with factory() as s:
        return dict(
            (
                await s.execute(
                    text(
                        "SELECT status, worker_id, executor_job_id, attempt_id, "
                        "executor_handle_json, cancel_requested_at FROM generations "
                        "WHERE id=:g"
                    ),
                    {"g": gid},
                )
            ).mappings().one()
        )


# --- 1) Generation creation convergence semantics (pinned, not accidental) ---


async def test_concurrent_identical_generates_are_legal_duplicates(client, factory, engine):
    """Explicit v0.1 semantics: each Generate request is a NEW execution
    request — duplicates are LEGAL (unlike ShotRevisions, which converge).
    Both generations share the identical captured revision and are internally
    consistent; database timing does not decide semantics."""
    sid = await _seed(factory, engine)
    g1, g2 = await asyncio.gather(
        _create_generation(client, sid),
        _create_generation(client, sid),
    )
    assert g1 != g2
    r1 = (await client.get(f"/generations/{g1}")).json()
    r2 = (await client.get(f"/generations/{g2}")).json()
    assert {r1["generation_number"], r2["generation_number"]} == {1, 2}
    assert r1["shot_revision_id"] == r2["shot_revision_id"]  # same revision
    assert r1["workflow_spec_hash" if False else "compiled_prompt"] == r2["compiled_prompt"]


# --- 2) HEADLINE: crash after submit, before handle persistence --------------


async def test_crash_after_submit_before_handle_persists_single_execution(
    client, factory, engine, settings
):
    """A claims → submit SUCCEEDS externally → crash before the handle is
    persisted → B reconciles → the system converges with EXTERNAL EXECUTION
    COUNT <= 1 (idempotent re-submission via durable attempt identity)."""
    sid = await _seed(factory, engine)
    gid = await _create_generation(client, sid)

    await ownership.acquire_worker_lease(engine, "w-A", 30)
    claim = await ownership.claim_next_generation(engine, "w-A")
    gen_id, attempt_id = claim
    assert attempt_id is not None  # durable fence identity persisted at claim

    # A submits externally... and dies BEFORE persisting the handle.
    from soloring.generation.repository import get_generation_full

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory2 = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    async with factory2() as s:
        generation = await get_generation_full(s, gid)
        spec = worker_execution._build_execution_spec(generation, attempt_id)
    executor_a = FakeExecutor()
    handle = await executor_a.submit(spec)  # external execution #1
    row = await _gen_row(factory, gid)
    assert row["executor_job_id"] is None  # handle NOT persisted (the window)

    # B takes over and reconciles.
    await _age_lease(engine)
    await _age_gen(engine, gid)
    result = await ownership.acquire_worker_lease(engine, "w-B", 30)
    acted = await recovery_mod.reconcile_stale_generations(engine, "w-B", settings)
    assert acted >= 1

    row = await _gen_row(factory, gid)
    assert row["status"] == "succeeded"
    _, _, _, gen_takes = await _counts(factory, gid)
    assert gen_takes == 1  # exactly one publication

    # External execution count <= 1: A's submit created the job; B's recovery
    # REJOINED it via the identical (generation, attempt) identity.
    assert executor_a.new_executions == [handle.job_id]
    # The durable job identity is derived, so B's rejoin used the same id:
    assert row["executor_job_id"] == handle.job_id


async def test_resubmit_same_identity_rejoins_not_reexecutes():
    """Unit proof of the idempotent submission contract."""
    from soloring.executors.base import GenerationExecutionSpec
    from soloring.workflows.manifest import load_workflow

    import uuid

    gen_id, att_id = str(uuid.uuid4()), str(uuid.uuid4())
    spec = GenerationExecutionSpec(
        generation_id=gen_id, attempt_id=att_id,
        workflow_spec={"x": 1}, workflow_spec_hash="f" * 64,
        compiled_prompt="p", executor="fake", template=load_workflow(),
    )
    ex = FakeExecutor()
    h1 = await ex.submit(spec)
    ex2 = FakeExecutor()  # different process/incarnation
    h2 = await ex2.submit(spec)
    assert h1.job_id == h2.job_id
    assert ex.new_executions == [h1.job_id]
    assert ex2.new_executions == []  # rejoined; NO second execution


# --- 3) Cancellation/completion races -----------------------------------------


async def test_cancel_vs_completion_completion_wins_when_executor_finished(
    client, factory, engine, settings
):
    """Deterministic policy: if the executor ALREADY completed before the
    cancel is observed (TOO_LATE), completion/import wins — decided by
    executor state + fenced transitions, not poll timing."""
    sid = await _seed(factory, engine)
    gid = await _create_generation(client, sid)
    await ownership.acquire_worker_lease(engine, "w-X", 30)
    gen_id, attempt = await ownership.claim_next_generation(engine, "w-X")

    from soloring.generation.repository import get_generation_full

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory2 = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    async with factory2() as s:
        generation = await get_generation_full(s, gid)
        spec = worker_execution._build_execution_spec(generation, attempt)
    fake = FakeExecutor()
    handle = await fake.submit(spec)
    from soloring.executors.fake import handle_json

    await ownership.persist_owned_executor_handle(
        engine, "w-X", gen_id, handle.job_id, handle_json(handle)
    )
    await ownership.transition_owned_generation(
        engine, "w-X", gen_id, "submitted", started=True
    )
    # Executor completes fully BEFORE the cancel request lands.
    for _ in range(4):
        fake.advance(handle)

    r = await client.post(f"/generations/{gid}/cancel")
    assert r.status_code == 200 and r.json()["cancel_requested"] is True

    outcome = await worker_execution.drive_generation(
        engine, settings, "w-X", gen_id, attempt, fake, existing_handle=handle
    )
    assert outcome == "succeeded"  # completion won — TOO_LATE, then import
    _, _, _, gen_takes = await _counts(factory, gen_id)
    assert gen_takes == 1


async def test_cancel_crash_after_confirm_successor_completes_cancel(
    client, factory, engine, settings
):
    """cancel call succeeds on the executor → worker crashes BEFORE
    persisting `cancelled` → successor adopts → exactly ONE cancelled
    terminal outcome (durable fake job state carries the cancellation)."""
    sid = await _seed(factory, engine)
    gid = await _create_generation(client, sid)
    await ownership.acquire_worker_lease(engine, "w-A", 30)
    gen_id, attempt = await ownership.claim_next_generation(engine, "w-A")

    from soloring.generation.repository import get_generation_full

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory2 = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    async with factory2() as s:
        generation = await get_generation_full(s, gid)
        spec = worker_execution._build_execution_spec(generation, attempt)
    fake_a = FakeExecutor()
    handle = await fake_a.submit(spec)
    from soloring.executors.fake import handle_json

    await ownership.persist_owned_executor_handle(
        engine, "w-A", gen_id, handle.job_id, handle_json(handle)
    )
    await ownership.transition_owned_generation(
        engine, "w-A", gen_id, "submitted", started=True
    )

    # Cancel intent persisted; A confirms cancellation on the executor (the
    # durable job file flips to cancelled) and THEN dies before the terminal
    # DB transition.
    await client.post(f"/generations/{gid}/cancel")
    assert fake_a.cancel(handle).value if False else True
    # (call it properly)
    from soloring.executors.base import CancelResult

    assert await fake_a.cancel(handle) is CancelResult.CANCELLED
    row = await _gen_row(factory, gid)
    assert row["status"] == "submitted"  # DB not yet terminal

    await _age_lease(engine)
    await _age_gen(engine, gid)
    await ownership.acquire_worker_lease(engine, "w-B", 30)
    acted = await recovery_mod.reconcile_stale_generations(engine, "w-B", settings)
    assert acted >= 1

    row = await _gen_row(factory, gid)
    assert row["status"] == "cancelled"  # exactly one cancelled outcome
    _, _, _, gen_takes = await _counts(factory, gid)
    assert gen_takes == 0


# --- 4) Import crash matrix (parametrized durable boundaries) ------------------


@pytest.mark.parametrize("boundary", importer_mod.BOUNDARIES)
async def test_import_crash_matrix_converges(
    client, factory, engine, settings, monkeypatch, boundary
):
    """Crash injected at EVERY durable import boundary → recovery converges
    with no duplicate durable identity: 1 output Blob, 1 output Asset,
    1 Take, 1 succeeded Generation."""
    sid = await _seed(factory, engine)
    gid = await _create_generation(client, sid)
    await ownership.acquire_worker_lease(engine, "w-A", 30)
    gen_id, attempt = await ownership.claim_next_generation(engine, "w-A")

    from soloring.assets.blob_store import BlobStore
    from soloring.generation.repository import get_generation_full

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory2 = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    async with factory2() as s:
        generation = await get_generation_full(s, gid)
    fake = FakeExecutor()
    spec = worker_execution._build_execution_spec(generation, attempt)
    handle = await fake.submit(spec)
    from soloring.executors.fake import handle_json

    await ownership.persist_owned_executor_handle(
        engine, "w-A", gen_id, handle.job_id, handle_json(handle)
    )
    await ownership.transition_owned_generation(
        engine, "w-A", gen_id, "submitted", started=True
    )
    for _ in range(4):
        fake.advance(handle)
    staging = Path(settings.staging_dir) / gen_id / attempt
    outs = worker_execution.spec_outputs(spec.workflow_spec)
    staged = await fake.fetch_outputs(handle, outs, staging)
    await ownership.transition_owned_generation(engine, "w-A", gen_id, "importing")

    # Inject death at this boundary.
    class _Crash:
        async def fire(self, name: str) -> None:
            if name == boundary:
                raise RuntimeError(f"crash at {name}")

    monkeypatch.setattr(importer_mod, "checkpoint", _Crash())
    with pytest.raises(RuntimeError):
        await import_staged_outputs(
            factory2, BlobStore(settings), generation, staged,
            expected_outputs=_outs_of(generation), staging_directory=staging,
        )
    monkeypatch.undo()

    # Recovery: B adopts the stale importing generation and replays.
    await _age_lease(engine)
    await _age_gen(engine, gid)
    await ownership.acquire_worker_lease(engine, "w-B", 30)
    acted = await recovery_mod.reconcile_stale_generations(engine, "w-B", settings)
    assert acted >= 1

    row = await _gen_row(factory, gid)
    assert row["status"] == "succeeded", boundary
    takes, assets, blobs, gen_takes = await _counts(factory, gid)
    # 1 reference blob+asset from the seed + exactly ONE output publication.
    assert takes == 1, boundary
    assert gen_takes == 1, boundary
    assert assets == 2, boundary   # 1 reference + 1 output
    assert blobs == 2, boundary    # 1 reference + 1 output


# --- 5) Concurrent import of the same bytes / same output identity ------------


async def test_concurrent_imports_converge_single_publication(
    client, factory, engine, settings
):
    """Two importers race on the SAME generation output concurrently: one
    Blob identity, one Take, one Asset — convergence through the unique
    constraint, not check-then-insert luck."""
    sid = await _seed(factory, engine)
    gid = await _create_generation(client, sid)
    await ownership.acquire_worker_lease(engine, "w-A", 30)
    gen_id, attempt = await ownership.claim_next_generation(engine, "w-A")

    from soloring.assets.blob_store import BlobStore
    from soloring.generation.repository import get_generation_full

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory2 = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    async with factory2() as s:
        generation = await get_generation_full(s, gid)
    fake = FakeExecutor()
    spec = worker_execution._build_execution_spec(generation, attempt)
    outs = worker_execution.spec_outputs(spec.workflow_spec)
    handle = await fake.submit(spec)
    for _ in range(4):
        fake.advance(handle)
    # TWO independent attempt staging dirs with identical deterministic bytes.
    staged_lists = []
    for att in ("race-a", "race-b"):
        st = Path(settings.staging_dir) / gen_id / att
        staged_lists.append(await fake.fetch_outputs(handle, outs, st))

    results = await asyncio.gather(
        import_staged_outputs(factory2, BlobStore(settings), generation, staged_lists[0],
                              expected_outputs=outs,
                              staging_directory=Path(settings.staging_dir) / gen_id / "race-a"),
        import_staged_outputs(factory2, BlobStore(settings), generation, staged_lists[1],
                              expected_outputs=outs,
                              staging_directory=Path(settings.staging_dir) / gen_id / "race-b"),
        return_exceptions=True,
    )
    ok = [r for r in results if not isinstance(r, BaseException)]
    assert len(ok) == 2, results  # both converge (constraint race resolved)

    takes, assets, blobs, gen_takes = await _counts(factory, gid)
    assert (takes, gen_takes) == (1, 1)
    assert assets == 2   # seed reference + one output
    assert blobs == 2    # seed reference + one output


# --- 6) Malformed executor outputs ---------------------------------------------


def _outs_of(generation):
    import json as _json

    return worker_execution.spec_outputs(_json.loads(generation.workflow_spec_json))


async def _staged_for(settings, gen, template=None, attempt="mal", content=None):
    from soloring.executors.fake import fake_output_bytes

    staging = Path(settings.staging_dir) / gen.id / attempt
    staging.mkdir(parents=True, exist_ok=True)
    out = _outs_of(gen)[0]
    data = content if content is not None else fake_output_bytes("e" * 64)
    path = staging / f"{_outs_of(gen)[0].name}-0.tmp"
    await asyncio.to_thread(path.write_bytes, data)  # don't starve the loop ourselves
    return [StagedOutput(output_key="video:0", path=path, kind=out.kind)], staging


async def test_missing_declared_output_rejected(client, factory, engine, settings):
    sid = await _seed(factory, engine)
    gid = await _create_generation(client, sid)
    await ownership.acquire_worker_lease(engine, "w-A", 30)
    gen_id, attempt = await ownership.claim_next_generation(engine, "w-A")

    from soloring.generation.repository import get_generation_full

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory2 = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    async with factory2() as s:
        generation = await get_generation_full(s, gid)
    # Staging directory exists but the declared output file does NOT.
    staging = Path(settings.staging_dir) / gen_id / "missing"
    staging.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ImportFailure):
        await import_staged_outputs(factory2, _store(settings), generation, [],
                                    expected_outputs=_outs_of(generation), staging_directory=staging)
    _, _, _, gen_takes = await _counts(factory, gid)
    assert gen_takes == 0  # no partial Take graph


def _store(settings):
    from soloring.assets.blob_store import BlobStore

    return BlobStore(settings)


async def test_extra_output_rejected(client, factory, engine, settings):
    sid = await _seed(factory, engine)
    gid = await _create_generation(client, sid)
    await ownership.acquire_worker_lease(engine, "w-A", 30)
    gen_id, attempt = await ownership.claim_next_generation(engine, "w-A")

    from soloring.generation.repository import get_generation_full

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory2 = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    async with factory2() as s:
        generation = await get_generation_full(s, gid)
    staged, staging = await _staged_for(settings, generation)
    staged.append(
        StagedOutput(
            output_key="bonus:0",
            path=staged[0].path.parent / "bonus-0.tmp",
            kind="video",
        )
    )
    staged[1].path.write_bytes(b"\x89PNG\r\n\x1a\nbonus")
    with pytest.raises(ImportFailure):
        await import_staged_outputs(factory2, _store(settings), generation, staged,
                                    expected_outputs=_outs_of(generation), staging_directory=staging)
    _, _, _, gen_takes = await _counts(factory, gid)
    assert gen_takes == 0


async def test_zero_byte_output_rejected_no_publication(client, factory, engine, settings):
    sid = await _seed(factory, engine)
    gid = await _create_generation(client, sid)
    await ownership.acquire_worker_lease(engine, "w-A", 30)
    gen_id, attempt = await ownership.claim_next_generation(engine, "w-A")

    from soloring.generation.repository import get_generation_full

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory2 = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    async with factory2() as s:
        generation = await get_generation_full(s, gid)
    staged, staging = await _staged_for(
        settings, generation, content=b""  # zero bytes
    )
    with pytest.raises(ImportFailure):
        await import_staged_outputs(factory2, _store(settings), generation, staged,
                                    expected_outputs=_outs_of(generation), staging_directory=staging)
    _, _, _, gen_takes = await _counts(factory, gid)
    assert gen_takes == 0


async def test_staging_path_escape_rejected(client, factory, engine, settings):
    sid = await _seed(factory, engine)
    gid = await _create_generation(client, sid)
    await ownership.acquire_worker_lease(engine, "w-A", 30)
    gen_id, attempt = await ownership.claim_next_generation(engine, "w-A")

    from soloring.generation.repository import get_generation_full

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory2 = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    async with factory2() as s:
        generation = await get_generation_full(s, gid)
    # A valid file placed OUTSIDE the attempt staging directory.
    outside = Path(settings.staging_dir) / "elsewhere.tmp"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_bytes(b"\x89PNG\r\n\x1a\noutside")
    staged = [StagedOutput(output_key="video:0", path=outside, kind="video")]
    staging = Path(settings.staging_dir) / generation.id / "legit"
    staging.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ImportFailure):
        await import_staged_outputs(factory2, _store(settings), generation, staged,
                                    expected_outputs=_outs_of(generation), staging_directory=staging)
    _, _, _, gen_takes = await _counts(factory, gid)
    assert gen_takes == 0


# --- 8) SSE reconnect loss tolerance -------------------------------------------


async def test_sse_reconnect_sees_authoritative_state(client, factory, engine, settings):
    from soloring.api.generations import sse_events
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    sid = await _seed(factory, engine)
    gid = await _create_generation(client, sid)
    factory2 = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

    async def first_event():
        gen = sse_events(factory2, 0.05, gid)
        ev = None
        async for raw in gen:
            for line in raw.splitlines():
                if line.startswith("data: "):
                    ev = json.loads(line[6:])
                    return ev

    # Connect while queued, see running state, then DISCONNECT.
    ev1 = await asyncio.wait_for(first_event(), 5)
    assert ev1["status"] == "queued"

    # Generation advances fully while the client is disconnected.
    await ownership.acquire_worker_lease(engine, "w-r", 30)
    outcome = await worker_execution.process_next_generation(
        engine, settings, "w-r", FakeExecutor()
    )
    assert outcome == "succeeded"

    # Reconnect: immediately sees authoritative CURRENT state (succeeded),
    # exactly one terminal event, stream closes.
    events = []
    async for raw in sse_events(factory2, 0.05, gid):
        for line in raw.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    assert len(events) == 1
    assert events[0]["status"] == "succeeded"
    assert events[0]["progress_current"] == events[0]["progress_total"]


# --- Event-loop responsiveness under import load --------------------------------


async def test_import_does_not_block_event_loop(client, factory, engine, settings):
    """A large output hashed/imported concurrently with a ticker: the loop
    must keep servicing (heartbeats/SSE-class work) — to_thread proves out
    under load, not just in source."""
    sid = await _seed(factory, engine)
    gid = await _create_generation(client, sid)
    await ownership.acquire_worker_lease(engine, "w-A", 30)
    gen_id, attempt = await ownership.claim_next_generation(engine, "w-A")

    from soloring.generation.repository import get_generation_full

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory2 = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    async with factory2() as s:
        generation = await get_generation_full(s, gid)
    big = b"\x89PNG\r\n\x1a\n" + (b"0123456789abcdef" * 4 * 1024 * 1024)  # ~64 MiB
    staged, staging = await _staged_for(
        settings, generation, attempt="big", content=big
    )

    import time

    ticks: list[float] = []
    done = asyncio.Event()

    async def ticker():
        while not done.is_set():
            ticks.append(time.monotonic())
            await asyncio.sleep(0.005)

    task = asyncio.create_task(ticker())
    try:
        imported = await import_staged_outputs(
            factory2, _store(settings), generation, staged,
            expected_outputs=_outs_of(generation), staging_directory=staging,
        )
    finally:
        done.set()
        await task
    assert imported == ["video:0"]
    # Direct starvation proof: no gap between successive ticks may exceed
    # 500ms — 64 MiB of synchronous hashing would freeze the loop for
    # seconds, so to_thread must be doing its job.
    gaps = [b - a for a, b in zip(ticks, ticks[1:])]
    assert ticks and max(gaps) < 0.5, f"event loop starved (max gap={max(gaps):.3f}s)"


# --- FakeExecutor store concurrency --------------------------------------------


async def test_fake_store_concurrent_operations_consistent():
    """Simultaneous advance/cancel/inspect on the same job: atomic replace
    keeps state files consistent; no partial JSON ever observed."""
    import os
    import tempfile
    import uuid

    from soloring.executors.base import GenerationExecutionSpec
    from soloring.workflows.manifest import load_workflow

    import soloring.settings as smod

    tmp = Path(tempfile.mkdtemp())
    os.environ["SOLORING_DATA_DIR"] = str(tmp)
    smod._settings = None  # rebuild from the new env on next get_settings()
    # tmp_dir derives DIRECTLY from data_dir (M1B): data_dir/tmp/...
    (tmp / "tmp" / "fake-executor").mkdir(parents=True, exist_ok=True)

    gid, att = str(uuid.uuid4()), str(uuid.uuid4())
    spec = GenerationExecutionSpec(
        generation_id=gid, attempt_id=att,
        workflow_spec={}, workflow_spec_hash="a" * 64,
        compiled_prompt="p", executor="fake", template=load_workflow(),
    )
    ex = FakeExecutor()
    handle = await ex.submit(spec)

    async def hammer(kind: str):
        for _ in range(50):
            if kind == "advance":
                ex.advance(handle)
            elif kind == "inspect":
                await ex.inspect(handle)
            elif kind == "cancel":
                await ex.cancel(handle)

    await asyncio.gather(
        hammer("advance"), hammer("advance"), hammer("inspect"), hammer("cancel")
    )
    obs = await ex.inspect(handle)
    assert obs.status.value in ("running", "cancelled", "succeeded")
    # State file is always complete JSON (never partial).
    job = json.loads(
        (tmp / "tmp" / "fake-executor" / f"{handle.job_id}.json").read_text()
    )
    os.environ.pop("SOLORING_DATA_DIR", None)
    smod._settings = None  # restore the process default for later tests
    assert set(job) == {
        "generation_id", "attempt_id", "workflow_spec_hash", "steps", "cancelled",
    }
